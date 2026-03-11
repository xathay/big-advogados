"""PDF digital signer using endesive — supports A1 (PFX) certificates."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12

from src.certificate.parser import CertificateInfo, parse_certificate

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

        # Clean up temp stamp file
        if options.visible:
            try:
                import os
                os.unlink(tmp_stamp.name)
            except OSError:
                pass

        log.info("PDF signed: %s -> %s", pdf_path, output_path)
        return SignatureResult(pdf_path, output_path, True, cert_info=cert_info)

    except Exception as exc:
        log.error("PDF signing failed: %s", exc, exc_info=True)
        return SignatureResult(pdf_path, output_path, False, str(exc))


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
