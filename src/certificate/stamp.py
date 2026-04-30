"""Visible signature stamp generator for PDF signing."""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont

from src.certificate.parser import CertificateInfo

log = logging.getLogger(__name__)

# Validador oficial do ITI (Instituto Nacional de Tecnologia da Informação).
# Aceita upload de PDFs PAdES e retorna relatório de validação. Base regulatória:
# Portaria ITI nº 22 de 28/09/2023. Endpoint confirmado em 2026-04-29.
VERIFY_URL = "https://validar.iti.gov.br"
VERIFY_LABEL = "validar.iti.gov.br"

# PDF box: 280pt x 80pt at 3.5:1 aspect.
# PNG raster: 1120 x 320 px (4x oversampling for crisp QR + text).
STAMP_W = 1120
STAMP_H = 320
PAD = 24
BORDER = 2

QR_SIZE = 256
QR_RIGHT_PAD = 16

# Palette — neutral, professional. Orange accent borrows from office identity
# but stays subdued so the stamp does not read as branded marketing.
COLOR_BORDER = (203, 213, 224)        # #CBD5E0
COLOR_ACCENT = (224, 122, 17)         # #E07A11 — orange filete
COLOR_BULLET = (16, 185, 129)         # #10B981 — green "validated"
COLOR_TITLE = (16, 42, 67)            # #102A43 — navy
COLOR_TEXT = (45, 55, 72)             # #2D3748
COLOR_DIM = (90, 104, 120)            # #5A6878
COLOR_BG = (255, 255, 255)


def generate_stamp_image(
    cert_info: CertificateInfo,
    signing_date: datetime,
    reason: str = "",
    pdf_hash: str = "",
) -> Image.Image:
    """Generate the visible signature stamp (Direction B layout).

    pdf_hash is the SHA-256 (hex) of the *input* PDF (before signing).
    Anyone holding the original document can reproduce this hash to confirm
    integrity; anyone holding only the signed PDF should re-validate the
    embedded PAdES signature via VERIFY_URL.

    Layout:
        ┌────────────────────────────────────────┬────┐
        │ ●  DOCUMENTO ASSINADO DIGITALMENTE     │    │
        │ ─── (orange filete) ───────────        │ QR │
        │ Leonardo Athayde Luna                  │    │
        │ CPF ***.xxx.xxx-** · OAB · dd/mm hh:mm │    │
        │ AC <Issuer> · Serial <truncated>       │    │
        │ Hash SHA-256: <prefix>…<suffix>        │    │
        │ Verifique em validar.iti.gov.br        │    │
        └────────────────────────────────────────┴────┘
    """
    img = Image.new("RGBA", (STAMP_W, STAMP_H), COLOR_BG + (255,))
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rectangle(
        [0, 0, STAMP_W - 1, STAMP_H - 1],
        outline=COLOR_BORDER, width=BORDER,
    )

    # ── Right column: QR code ──────────────────────────────
    qr_x = STAMP_W - QR_SIZE - QR_RIGHT_PAD
    qr_y = (STAMP_H - QR_SIZE) // 2
    qr_img = _build_qr(cert_info, signing_date, pdf_hash)
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.Resampling.NEAREST)
    img.paste(qr_img, (qr_x, qr_y))

    # Vertical divider between text and QR
    div_x = qr_x - 14
    draw.line(
        [(div_x, PAD + 8), (div_x, STAMP_H - PAD - 8)],
        fill=COLOR_BORDER, width=1,
    )

    # ── Left column: text ──────────────────────────────────
    text_left = PAD + 4
    text_right = div_x - 14

    font_title = _load_font(bold=True, size=22)
    font_name = _load_font(bold=True, size=30)
    font_body = _load_font(bold=False, size=20)
    font_mono = _load_mono_font(size=17)
    font_dim = _load_font(bold=False, size=17)

    y = PAD

    # Header: bullet + title
    bullet_r = 7
    bullet_cx = text_left + bullet_r
    bullet_cy = y + 14
    draw.ellipse(
        [bullet_cx - bullet_r, bullet_cy - bullet_r,
         bullet_cx + bullet_r, bullet_cy + bullet_r],
        fill=COLOR_BULLET,
    )
    draw.text(
        (text_left + 2 * bullet_r + 10, y),
        "DOCUMENTO ASSINADO DIGITALMENTE",
        fill=COLOR_TITLE, font=font_title,
    )
    y += 32

    # Orange filete
    draw.line(
        [(text_left, y + 4), (text_right, y + 4)],
        fill=COLOR_ACCENT, width=2,
    )
    y += 14

    # Signer name
    holder = cert_info.holder_name or cert_info.common_name or "—"
    draw.text((text_left, y), holder, fill=COLOR_TEXT, font=font_name)
    y += 40

    # CPF + OAB + date
    cpf_part = _mask_cpf(cert_info.cpf)
    date_str = signing_date.strftime("%d/%m/%Y %H:%M:%S")
    tz = signing_date.strftime("%Z") or signing_date.strftime("%z")
    line2_parts = []
    if cpf_part:
        line2_parts.append(f"CPF {cpf_part}")
    if cert_info.oab:
        oab_label = cert_info.oab if cert_info.oab.upper().startswith("OAB") else f"OAB {cert_info.oab}"
        line2_parts.append(oab_label)
    line2_parts.append(f"{date_str} {tz}".strip())
    draw.text(
        (text_left, y),
        " · ".join(line2_parts),
        fill=COLOR_TEXT, font=font_body,
    )
    y += 26

    # Issuer + cert serial
    issuer = cert_info.issuer_cn or "AC ICP-Brasil"
    serial = _truncate_serial(cert_info.serial_number)
    line3 = f"{issuer} · Serial {serial}" if serial else issuer
    draw.text((text_left, y), line3, fill=COLOR_DIM, font=font_body)
    y += 24

    # Hash of original document (truncated, monospace for legibility)
    if pdf_hash:
        draw.text(
            (text_left, y),
            f"Hash SHA-256 do documento: {_truncate_hash(pdf_hash)}",
            fill=COLOR_DIM, font=font_mono,
        )
        y += 22

    # Verifier URL
    draw.text(
        (text_left, y),
        f"Verifique em {VERIFY_LABEL}",
        fill=COLOR_DIM, font=font_dim,
    )

    return img


def stamp_to_bytes(img: Image.Image) -> bytes:
    """Convert stamp PIL Image to PNG bytes."""
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_qr(
    cert_info: CertificateInfo,
    signing_date: datetime,
    pdf_hash: str = "",
) -> Image.Image:
    """Build a QR code carrying signature metadata + verifier URL.

    Encoded as plain text (multi-line) so that a phone scanner shows the
    info immediately, plus the verifier URL for re-checking the embedded
    PAdES signature. The full SHA-256 hash is included so that anyone
    holding the original PDF can reproduce and compare it.
    """
    holder = cert_info.holder_name or cert_info.common_name or "—"
    cpf = _mask_cpf(cert_info.cpf) or "—"
    date_str = signing_date.strftime("%d/%m/%Y %H:%M:%S")
    tz = signing_date.strftime("%Z") or signing_date.strftime("%z")
    issuer = cert_info.issuer_cn or "AC ICP-Brasil"
    serial = cert_info.serial_number or "—"

    lines = [
        "ASSINATURA DIGITAL ICP-Brasil",
        f"Signatario: {holder}",
        f"CPF: {cpf}",
        f"Data: {date_str} {tz}".strip(),
        f"AC: {issuer}",
        f"Serial: {serial}",
    ]
    if pdf_hash:
        lines.append(f"SHA-256: {pdf_hash}")
    lines.append(f"Validar em: {VERIFY_URL}")
    payload = "\n".join(lines)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGBA")


def _mask_cpf(cpf: str) -> str:
    """Mask CPF per LGPD: ***.456.789-** from 123.456.789-00."""
    if not cpf:
        return ""
    if len(cpf) >= 14:
        return f"***.{cpf[4:7]}.{cpf[8:11]}-**"
    return cpf


def _truncate_serial(serial: str) -> str:
    """Show serial as first 8 + last 4 hex chars to fit in stamp."""
    if not serial:
        return ""
    if len(serial) <= 14:
        return serial
    return f"{serial[:8]}…{serial[-4:]}"


def _truncate_hash(h: str) -> str:
    """Show SHA-256 as first 16 + last 8 hex chars (full 64-char hash in QR)."""
    if not h:
        return ""
    if len(h) <= 28:
        return h
    return f"{h[:16]}…{h[-8:]}"


def _load_mono_font(size: int = 12) -> ImageFont.FreeTypeFont:
    """Load a monospace font for hash/serial display."""
    paths = [
        "/usr/share/fonts/ubuntu/UbuntuMono-R.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/LiberationMono-Regular.ttf",
        "/usr/share/fonts/noto/NotoSansMono-Regular.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return _load_font(bold=False, size=size)


def _load_font(bold: bool = False, size: int = 12) -> ImageFont.FreeTypeFont:
    """Load a TrueType font, with fallback to default."""
    font_paths = [
        "/usr/share/fonts/ubuntu/Ubuntu-B.ttf" if bold else "/usr/share/fonts/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/ubuntu/Ubuntu-M.ttf" if bold else "/usr/share/fonts/ubuntu/Ubuntu-L.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/TTF/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/NotoSans-Regular.ttf",
        "/usr/share/fonts/TTF/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/LiberationSans-Regular.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue

    log.debug("No TrueType font found, using PIL default")
    return ImageFont.load_default(size)
