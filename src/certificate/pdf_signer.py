"""PDF digital signer using endesive — supports A1 (PFX) and A3 (PKCS#11) certificates."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12

from src.certificate.parser import CertificateInfo, parse_certificate

if TYPE_CHECKING:
    from src.certificate.a3_manager import A3Manager

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
    page: int = -1  # -1 = last page
    position: str = "bottom"  # bottom, top


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

        # Determine signature page
        sig_page = options.page
        if sig_page == -1:
            sig_page = _count_pdf_pages(pdf_bytes) - 1
            if sig_page < 0:
                sig_page = 0

        now = datetime.now(timezone.utc)
        local_now = datetime.now().astimezone()
        signing_date = now.strftime("D:%Y%m%d%H%M%S+00'00'")

        # Signature box: A4 = 595 x 842 pt
        margin = 20
        box_height = 80
        box_width = 360

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
                cert_info, local_now, reason=options.reason,
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

            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                f.write(pdf_bytes)
                f.write(signed_data)
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

    if a3_manager._session is None:
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

        # Determine signature page
        sig_page = options.page
        if sig_page == -1:
            sig_page = _count_pdf_pages(pdf_bytes) - 1
            if sig_page < 0:
                sig_page = 0

        now = datetime.now(timezone.utc)
        local_now = datetime.now().astimezone()
        signing_date = now.strftime("D:%Y%m%d%H%M%S+00'00'")

        # Signature box: A4 = 595 x 842 pt
        margin = 20
        box_height = 80
        box_width = 360

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

        if options.visible:
            from src.certificate.stamp import generate_stamp_image
            import tempfile

            stamp_img = generate_stamp_image(
                cert_info, local_now, reason=options.reason,
            )
            tmp_stamp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            stamp_img.save(tmp_stamp.name, format="PNG")
            tmp_stamp.close()
            udct["signaturebox"] = sig_box
            udct["signature_img"] = tmp_stamp.name
            udct["signature_img_distort"] = False
            udct["signature_img_centred"] = True

        # Create PKCS#11 HSM adapter for endesive
        hsm = _PKCS11HSM(a3_manager._session, cert_der)

        from endesive.pdf import cms as pdf_cms

        signed_data = pdf_cms.sign(
            pdf_bytes, udct,
            None, None, [],
            algomd="sha256",
            hsm=hsm,
        )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            f.write(pdf_bytes)
            f.write(signed_data)

        # Clean up temp stamp file
        if options.visible:
            try:
                import os
                os.unlink(tmp_stamp.name)
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


def _build_signature_text(info: CertificateInfo, now: datetime) -> str:
    """Build the visible signature stamp text."""
    lines = []
    lines.append("ASSINADO DIGITALMENTE")

    holder = info.holder_name or info.common_name
    if holder:
        lines.append(f"Por: {holder}")

    if info.cpf:
        lines.append(f"CPF: {info.cpf}")

    if info.oab:
        lines.append(f"OAB: {info.oab}")

    if info.issuer_cn:
        lines.append(f"AC: {info.issuer_cn}")

    lines.append(f"Data: {now.strftime('%d/%m/%Y %H:%M:%S UTC')}")

    return "\n".join(lines)


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


class _VidaaSRemoteHSM:
    """HSM adapter for endesive — signs via VidaaS REST API.

    This triggers a push notification to the user's phone for each
    signing operation. The API polls until the user authorizes.
    """

    def __init__(
        self,
        api_client: "VidaaSAPIClient",
        cert_id: str,
        cert_der: bytes,
        on_status: Optional[callable] = None,
    ) -> None:
        self._api = api_client
        self._cert_id = cert_id
        self._cert_der = cert_der
        self._on_status = on_status

    def certificate(self) -> tuple:
        return (self._cert_id, self._cert_der)

    def sign(self, keyid: object, data: bytes, hashalgo: str) -> bytes:
        """Sign data via VidaaS API (triggers push notification)."""
        import hashlib

        hash_func = getattr(hashlib, hashalgo, hashlib.sha256)
        data_hash = hash_func(data).digest()

        tx_id = self._api.request_signature(
            self._cert_id, data_hash, hashalgo,
        )

        result = self._api.wait_for_signature(
            tx_id, timeout=120, on_status=self._on_status,
        )

        from src.certificate.vidaas_api import VidaaSSignatureStatus

        if result.status == VidaaSSignatureStatus.COMPLETED:
            return result.signature_bytes
        if result.status == VidaaSSignatureStatus.REJECTED:
            raise RuntimeError("Assinatura rejeitada pelo usuário no celular")
        if result.status == VidaaSSignatureStatus.EXPIRED:
            raise TimeoutError("Tempo de autorização expirado no celular")
        raise RuntimeError(f"Erro na assinatura VidaaS: {result.error_message}")


def sign_pdf_vidaas(
    pdf_path: str,
    vidaas_manager: "VidaaSManager",
    cert_info: CertificateInfo,
    output_path: str,
    options: Optional[SignatureOptions] = None,
    on_status: Optional[callable] = None,
) -> SignatureResult:
    """Sign a PDF using VidaaS Connect certificate.

    Automatically selects PKCS#11 or API REST mode based on the
    VidaaSManager's current connection mode.

    Args:
        pdf_path: Path to the PDF to sign.
        vidaas_manager: Connected VidaaSManager instance.
        cert_info: Certificate information.
        output_path: Path for signed PDF output.
        options: Signature appearance options.
        on_status: Callback for API mode authorization status updates.

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
        return _sign_pdf_vidaas_api(
            pdf_path, vidaas_manager, cert_info, output_path,
            options, on_status,
        )

    return SignatureResult(
        pdf_path, output_path, False, "VidaaS não conectado",
    )


def _sign_pdf_vidaas_api(
    pdf_path: str,
    vidaas_manager: "VidaaSManager",
    cert_info: CertificateInfo,
    output_path: str,
    options: Optional[SignatureOptions] = None,
    on_status: Optional[callable] = None,
) -> SignatureResult:
    """Sign a PDF via VidaaS REST API (remote signing with phone auth)."""
    if options is None:
        options = SignatureOptions()

    pdf_file = Path(pdf_path)
    if not pdf_file.is_file():
        return SignatureResult(pdf_path, output_path, False, "Arquivo PDF não encontrado")

    api_client = vidaas_manager.api_client
    if api_client is None:
        return SignatureResult(
            pdf_path, output_path, False, "Cliente API VidaaS não conectado",
        )

    if cert_info.is_expired:
        return SignatureResult(
            pdf_path, output_path, False,
            f"Certificado expirado em {cert_info.not_after:%d/%m/%Y}",
            cert_info,
        )

    try:
        pdf_bytes = pdf_file.read_bytes()

        sig_page = options.page
        if sig_page == -1:
            sig_page = _count_pdf_pages(pdf_bytes) - 1
            if sig_page < 0:
                sig_page = 0

        now = datetime.now(timezone.utc)
        local_now = datetime.now().astimezone()
        signing_date = now.strftime("D:%Y%m%d%H%M%S+00'00'")

        margin = 20
        box_height = 80
        box_width = 360

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

        if options.visible:
            from src.certificate.stamp import generate_stamp_image
            import tempfile

            stamp_img = generate_stamp_image(
                cert_info, local_now, reason=options.reason,
            )
            tmp_stamp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            stamp_img.save(tmp_stamp.name, format="PNG")
            tmp_stamp.close()
            udct["signaturebox"] = sig_box
            udct["signature_img"] = tmp_stamp.name
            udct["signature_img_distort"] = False
            udct["signature_img_centred"] = True

        # Build remote HSM adapter
        from cryptography.x509 import load_der_x509_certificate
        cert_der = cert_info.certificate.public_bytes(
            serialization.Encoding.DER,
        ) if hasattr(cert_info, "certificate") else b""

        hsm = _VidaaSRemoteHSM(
            api_client,
            cert_id=cert_info.serial_number or "",
            cert_der=cert_der,
            on_status=on_status,
        )

        from endesive.pdf import cms as pdf_cms

        signed_data = pdf_cms.sign(
            pdf_bytes, udct,
            None, None, [],
            algomd="sha256",
            hsm=hsm,
        )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            f.write(pdf_bytes)
            f.write(signed_data)

        if options.visible:
            try:
                import os
                os.unlink(tmp_stamp.name)
            except OSError:
                pass

        log.info("PDF signed (VidaaS API): %s -> %s", pdf_path, output_path)
        return SignatureResult(pdf_path, output_path, True, cert_info=cert_info)

    except TimeoutError:
        return SignatureResult(
            pdf_path, output_path, False,
            "Tempo de autorização expirado — verifique o app VidaaS no celular",
        )
    except Exception as exc:
        log.error("VidaaS API PDF signing failed: %s", exc, exc_info=True)
        return SignatureResult(pdf_path, output_path, False, str(exc))
