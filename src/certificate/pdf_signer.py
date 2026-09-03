"""PDF digital signer using endesive — supports A1 (PFX) and A3 (PKCS#11) certificates."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from src.certificate.parser import CertificateInfo, parse_certificate

if TYPE_CHECKING:
    from src.certificate.a3_manager import A3Manager
    from src.certificate.vidaas_manager import VidaaSManager

log = logging.getLogger(__name__)


@dataclass
class SignatureResult:
    """Result of a PDF signing operation."""

    input_path: str
    output_path: str
    success: bool
    error: str = ""
    cert_info: Optional[CertificateInfo] = None


@dataclass
class SignatureOptions:
    """Options for PDF digital signature."""

    reason: str = "Documento assinado digitalmente"
    location: str = ""
    contact: str = ""
    visible: bool = True
    page: int = -1  # -1 = last page (ignored when signature_page == "append")
    position: str = "bottom"  # bottom, top (ignored when signature_page == "append")
    # "embed"  → stamp on the document's last page (overlay).
    # "append" → append a dedicated certification page at the end.
    signature_page: str = "embed"


def _pdf_signature_count(pdf_bytes: bytes) -> int:
    """Count PDF signature byte ranges without inspecting document contents."""
    return pdf_bytes.count(b"/ByteRange")


def _write_validated_signed_pdf(
    output_path: str,
    original_pdf: bytes,
    signature_increment: bytes,
) -> None:
    """Validate the new CMS signature and atomically publish the output PDF.

    ``endesive`` verifies cryptographic integrity and signature correctness.
    Certificate-chain trust is intentionally not used as the success criterion
    here because the local trust store may not contain the ICP-Brasil chain.
    """
    if not signature_increment:
        raise ValueError("A biblioteca de assinatura não produziu dados assinados")

    signed_pdf = original_pdf + signature_increment
    previous_count = _pdf_signature_count(original_pdf)

    try:
        from endesive.pdf import verify as verify_pdf

        verification_results = verify_pdf(signed_pdf)
    except Exception as exc:
        raise ValueError("Não foi possível validar o PDF assinado") from exc

    if len(verification_results) <= previous_count:
        raise ValueError("A nova assinatura não foi encontrada no PDF resultante")

    hash_ok, signature_ok, _certificate_trusted = verification_results[-1]
    if not hash_ok or not signature_ok:
        raise ValueError("A validação criptográfica da nova assinatura falhou")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{out.name}.", suffix=".tmp", dir=out.parent)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(signed_pdf)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_name, out)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def sign_pdf(
    pdf_path: str,
    pfx_path: str,
    pfx_password: str,
    output_path: str,
    options: Optional[SignatureOptions] = None,
) -> SignatureResult:
    """Sign a PDF file with an A1 (PFX/P12) certificate.

    Args:
        pdf_path: Path to the PDF to sign.
        pfx_path: Path to the PFX/P12 certificate file.
        pfx_password: Password for the PFX file.
        output_path: Path for the signed PDF output.
        options: Signature appearance and metadata options.

    Returns:
        SignatureResult with success status and details.
    """
    if options is None:
        options = SignatureOptions()

    pdf_file = Path(pdf_path)
    pfx_file = Path(pfx_path)

    if not pdf_file.is_file():
        return SignatureResult(pdf_path, output_path, False, "Arquivo PDF não encontrado")

    if not pfx_file.is_file():
        return SignatureResult(pdf_path, output_path, False, "Certificado PFX não encontrado")

    # Load PFX
    try:
        pfx_data = pfx_file.read_bytes()
        pwd_bytes = pfx_password.encode("utf-8") if pfx_password else None
        private_key, certificate, chain = pkcs12.load_key_and_certificates(
            pfx_data, pwd_bytes,
        )
    except ValueError as exc:
        log.error("PFX password error: %s", exc)
        return SignatureResult(pdf_path, output_path, False, "Senha do certificado incorreta")

    if private_key is None or certificate is None:
        return SignatureResult(
            pdf_path, output_path, False,
            "Certificado ou chave privada não encontrados no PFX",
        )

    cert_info = parse_certificate(certificate)

    if cert_info.is_expired:
        return SignatureResult(
            pdf_path, output_path, False,
            f"Certificado expirado em {cert_info.not_after:%d/%m/%Y}",
            cert_info,
        )

    try:
        other_certs = list(chain) if chain else []
        pdf_bytes = pdf_file.read_bytes()

        now = datetime.now(timezone.utc)
        local_now = datetime.now().astimezone()
        signing_date = now.strftime("D:%Y%m%d%H%M%S+00'00'")

        # SHA-256 of the input PDF — embedded in stamp + certification page.
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest() if options.visible else ""

        if options.visible and options.signature_page == "append":
            from src.certificate.certification_page import append_certification_page
            pdf_bytes, sig_page, sig_box = append_certification_page(
                pdf_bytes, cert_info, local_now, pdf_hash, options.reason,
            )
        else:
            sig_page = options.page
            if sig_page == -1:
                sig_page = _count_pdf_pages(pdf_bytes) - 1
                if sig_page < 0:
                    sig_page = 0

            # A4 = 595 x 842 pt. Aspect 3.5:1 to match stamp PNG.
            margin = 20
            box_height = 80
            box_width = 280
            if options.position == "bottom":
                sig_box = (margin, margin, margin + box_width, margin + box_height)
            else:
                sig_box = (margin, 842 - margin - box_height, margin + box_width, 842 - margin)

        udct = {
            "sigflags": 3,
            "sigpage": sig_page,
            "sigfield": "Signature1",
            "auto_sigfield": True,
            "sigandcertify": True,
            "contact": options.contact or cert_info.email or "",
            "location": options.location,
            "signingdate": signing_date,
            "reason": options.reason,
            "aligned": 0,
        }

        tmp_stamp_path: str | None = None
        if options.visible:
            from src.certificate.stamp import generate_stamp_image
            import tempfile

            stamp_img = generate_stamp_image(
                cert_info, local_now, reason=options.reason, pdf_hash=pdf_hash,
            )
            tmp_stamp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            stamp_img.save(tmp_stamp.name, format="PNG")
            tmp_stamp.close()
            tmp_stamp_path = tmp_stamp.name
            udct["signaturebox"] = sig_box
            udct["signature_img"] = tmp_stamp_path
            udct["signature_img_distort"] = False
            udct["signature_img_centred"] = True

        try:
            from endesive.pdf import cms as pdf_cms

            signed_data = pdf_cms.sign(
                pdf_bytes, udct,
                private_key, certificate, other_certs,
                algomd="sha256",
            )

            _write_validated_signed_pdf(output_path, pdf_bytes, signed_data)
        finally:
            if tmp_stamp_path:
                try:
                    import os
                    os.unlink(tmp_stamp_path)
                except OSError:
                    pass

        log.info("PDF signed: %s -> %s", pdf_path, output_path)
        return SignatureResult(pdf_path, output_path, True, cert_info=cert_info)

    except Exception as exc:
        log.error("PDF signing failed: %s", exc, exc_info=True)
        return SignatureResult(pdf_path, output_path, False, str(exc))


class _PKCS11HSM:
    """HSM adapter for endesive — signs via PKCS#11 token session."""

    def __init__(self, session: object, cert_der: bytes) -> None:
        self._session = session
        self._cert_der = cert_der
        self._key_id: object = None

        import PyKCS11
        # Find the private key on the token
        priv_keys = session.findObjects([  # type: ignore[union-attr]
            (PyKCS11.CKA_CLASS, PyKCS11.CKO_PRIVATE_KEY),
        ])
        if priv_keys:
            self._priv_key = priv_keys[0]
        else:
            self._priv_key = None

    def certificate(self) -> tuple:
        """Return (key_id, certificate_der_bytes)."""
        return (self._priv_key, self._cert_der)

    def sign(self, keyid: object, data: bytes, hashalgo: str) -> bytes:
        """Sign data using PKCS#11 C_Sign mechanism."""
        import PyKCS11

        mech_map = {
            "sha256": PyKCS11.CKM_SHA256_RSA_PKCS,
            "sha384": PyKCS11.CKM_SHA384_RSA_PKCS,
            "sha512": PyKCS11.CKM_SHA512_RSA_PKCS,
            "sha1": PyKCS11.CKM_SHA1_RSA_PKCS,
        }

        mechanism = PyKCS11.Mechanism(
            mech_map.get(hashalgo, PyKCS11.CKM_SHA256_RSA_PKCS), None,
        )

        signature = self._session.sign(  # type: ignore[union-attr]
            self._priv_key, data, mechanism,
        )
        return bytes(bytearray(signature))


def sign_pdf_a3(
    pdf_path: str,
    a3_manager: A3Manager,
    cert_der: bytes,
    output_path: str,
    options: Optional[SignatureOptions] = None,
) -> SignatureResult:
    """Sign a PDF file using an A3 token (PKCS#11).

    Args:
        pdf_path: Path to the PDF to sign.
        a3_manager: A3Manager with active session.
        cert_der: DER-encoded certificate bytes from token.
        output_path: Path for the signed PDF output.
        options: Signature appearance and metadata options.

    Returns:
        SignatureResult with success status and details.
    """
    if options is None:
        options = SignatureOptions()

    pdf_file = Path(pdf_path)

    if not pdf_file.is_file():
        return SignatureResult(pdf_path, output_path, False, "Arquivo PDF não encontrado")

    if not a3_manager.has_active_session:
        return SignatureResult(
            pdf_path, output_path, False,
            "Sessão com o token não está ativa — reinsira o token",
        )

    # Parse the certificate from token
    try:
        certificate = x509.load_der_x509_certificate(cert_der)
        cert_info = parse_certificate(certificate)
    except Exception as exc:
        log.error("Failed to parse A3 certificate: %s", exc)
        return SignatureResult(pdf_path, output_path, False, "Certificado do token inválido")

    if cert_info.is_expired:
        return SignatureResult(
            pdf_path, output_path, False,
            f"Certificado expirado em {cert_info.not_after:%d/%m/%Y}",
            cert_info,
        )

    try:
        pdf_bytes = pdf_file.read_bytes()

        now = datetime.now(timezone.utc)
        local_now = datetime.now().astimezone()
        signing_date = now.strftime("D:%Y%m%d%H%M%S+00'00'")

        # SHA-256 of the input PDF — embedded in stamp + certification page.
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest() if options.visible else ""

        if options.visible and options.signature_page == "append":
            from src.certificate.certification_page import append_certification_page
            pdf_bytes, sig_page, sig_box = append_certification_page(
                pdf_bytes, cert_info, local_now, pdf_hash, options.reason,
            )
        else:
            sig_page = options.page
            if sig_page == -1:
                sig_page = _count_pdf_pages(pdf_bytes) - 1
                if sig_page < 0:
                    sig_page = 0

            # A4 = 595 x 842 pt. Aspect 3.5:1 to match stamp PNG.
            margin = 20
            box_height = 80
            box_width = 280
            if options.position == "bottom":
                sig_box = (margin, margin, margin + box_width, margin + box_height)
            else:
                sig_box = (margin, 842 - margin - box_height, margin + box_width, 842 - margin)

        udct = {
            "sigflags": 3,
            "sigpage": sig_page,
            "sigfield": "Signature1",
            "auto_sigfield": True,
            "sigandcertify": True,
            "contact": options.contact or cert_info.email or "",
            "location": options.location,
            "signingdate": signing_date,
            "reason": options.reason,
            "aligned": 0,
        }

        tmp_stamp_path: str | None = None
        if options.visible:
            from src.certificate.stamp import generate_stamp_image
            import tempfile

            stamp_img = generate_stamp_image(
                cert_info, local_now, reason=options.reason, pdf_hash=pdf_hash,
            )
            tmp_stamp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            stamp_img.save(tmp_stamp.name, format="PNG")
            tmp_stamp.close()
            tmp_stamp_path = tmp_stamp.name
            udct["signaturebox"] = sig_box
            udct["signature_img"] = tmp_stamp_path
            udct["signature_img_distort"] = False
            udct["signature_img_centred"] = True

        try:
            # Create PKCS#11 HSM adapter for endesive
            session = a3_manager.get_session()
            hsm = _PKCS11HSM(session, cert_der)

            from endesive.pdf import cms as pdf_cms

            signed_data = pdf_cms.sign(
                pdf_bytes, udct,
                None, None, [],
                algomd="sha256",
                hsm=hsm,
            )

            _write_validated_signed_pdf(output_path, pdf_bytes, signed_data)
        finally:
            if tmp_stamp_path:
                try:
                    import os
                    os.unlink(tmp_stamp_path)
                except OSError:
                    pass

        log.info("PDF signed (A3): %s -> %s", pdf_path, output_path)
        return SignatureResult(pdf_path, output_path, True, cert_info=cert_info)

    except Exception as exc:
        log.error("PDF A3 signing failed: %s", exc, exc_info=True)
        error_msg = str(exc)
        if "CKR_" in error_msg:
            error_msg = f"Erro no token: {error_msg}"
        return SignatureResult(pdf_path, output_path, False, error_msg)


def batch_sign(
    pdf_paths: list[str],
    pfx_path: str,
    pfx_password: str,
    output_dir: str,
    options: Optional[SignatureOptions] = None,
    progress_callback: Optional[callable] = None,
) -> list[SignatureResult]:
    """Sign multiple PDF files with the same certificate.

    Args:
        pdf_paths: List of PDF file paths to sign.
        pfx_path: Path to the PFX/P12 certificate.
        pfx_password: Password for the PFX.
        output_dir: Directory for signed outputs.
        options: Signature options.
        progress_callback: Called with (current, total) for progress tracking.

    Returns:
        List of SignatureResult for each file.
    """
    results: list[SignatureResult] = []
    total = len(pdf_paths)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, pdf_path in enumerate(pdf_paths):
        name = Path(pdf_path).stem
        ext = Path(pdf_path).suffix
        output_path = str(out_dir / f"{name}_assinado{ext}")

        result = sign_pdf(pdf_path, pfx_path, pfx_password, output_path, options)
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, total)

    return results


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Count pages in a PDF using pikepdf."""
    try:
        import pikepdf
        from io import BytesIO
        with pikepdf.open(BytesIO(pdf_bytes)) as pdf:
            return len(pdf.pages)
    except Exception:
        return 1


# ── VidaaS Connect signing ───────────────────────────────────────────


def sign_pdf_vidaas(
    pdf_path: str,
    vidaas_manager: "VidaaSManager",
    cert_info: CertificateInfo,
    output_path: str,
    options: Optional[SignatureOptions] = None,
    on_status: Optional[callable] = None,
) -> SignatureResult:
    """Sign a PDF using VidaaS Connect certificate.

    Only the locally verifiable PKCS#11 integration is enabled. The former
    REST scaffold was based on unconfirmed endpoints and is fail-closed.

    Args:
        pdf_path: Path to the PDF to sign.
        vidaas_manager: Connected VidaaSManager instance.
        cert_info: Certificate information.
        output_path: Path for signed PDF output.
        options: Signature appearance options.
        on_status: Reserved for future, documented remote-signing support.

    Returns:
        SignatureResult with success status and details.
    """
    from src.certificate.vidaas_manager import VidaaSMode

    if vidaas_manager.mode == VidaaSMode.PKCS11:
        cert_der = vidaas_manager.get_cert_der()
        if not cert_der:
            return SignatureResult(
                pdf_path, output_path, False,
                "Certificado VidaaS não carregado",
            )
        return sign_pdf_a3(
            pdf_path, vidaas_manager._a3, cert_der, output_path, options,
        )

    if vidaas_manager.mode == VidaaSMode.REST_API:
        return SignatureResult(
            pdf_path,
            output_path,
            False,
            "Assinatura VidaaS por API REST está desabilitada até validação oficial",
            cert_info,
        )

    return SignatureResult(pdf_path, output_path, False, "VidaaS não conectado")
