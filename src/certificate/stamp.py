"""Visible signature stamp generator for PDF signing."""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from src.certificate.parser import CertificateInfo

log = logging.getLogger(__name__)

# Colors
COLOR_HEADER_BG = (0, 42, 67)       # #002A43 — dark navy
COLOR_HEADER_TEXT = (255, 255, 255)  # white
COLOR_BODY_BG = (248, 249, 250)     # #F8F9FA — light gray
COLOR_BODY_TEXT = (51, 51, 51)       # #333333
COLOR_ACCENT = (10, 132, 255)       # #0a84ff — bright blue
COLOR_BORDER = (10, 132, 255)       # #0a84ff
COLOR_DIM = (128, 128, 128)         # #808080 — subtle gray

# Stamp dimensions (pixels at 150 DPI → approx 350x80 pt)
STAMP_WIDTH = 730
STAMP_HEIGHT = 170
BORDER_WIDTH = 3
HEADER_HEIGHT = 36
PADDING = 12
LINE_HEIGHT = 22


def generate_stamp_image(
    cert_info: CertificateInfo,
    signing_date: datetime,
    reason: str = "",
) -> Image.Image:
    """Generate a professional signature stamp image.

    Creates a stamp with:
    - Dark header bar with "ASSINADO DIGITALMENTE"
    - Body with signer name, CPF, OAB, issuer, date
    - Blue accent border

    Returns:
        PIL Image with RGBA transparency.
    """
    img = Image.new("RGBA", (STAMP_WIDTH, STAMP_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Load fonts
    font_bold = _load_font(bold=True, size=14)
    font_header = _load_font(bold=True, size=13)
    font_normal = _load_font(bold=False, size=12)
    font_small = _load_font(bold=False, size=10)

    # ── Border rectangle ──
    draw.rounded_rectangle(
        [0, 0, STAMP_WIDTH - 1, STAMP_HEIGHT - 1],
        radius=6,
        fill=COLOR_BODY_BG + (240,),
        outline=COLOR_BORDER + (200,),
        width=BORDER_WIDTH,
    )

    # ── Header bar ──
    draw.rounded_rectangle(
        [BORDER_WIDTH, BORDER_WIDTH,
         STAMP_WIDTH - BORDER_WIDTH - 1, BORDER_WIDTH + HEADER_HEIGHT],
        radius=4,
        fill=COLOR_HEADER_BG + (230,),
    )

    # Shield symbol + header text
    header_text = "\u2756  ASSINADO DIGITALMENTE"
    draw.text(
        (PADDING + BORDER_WIDTH + 4, BORDER_WIDTH + 8),
        header_text, fill=COLOR_HEADER_TEXT, font=font_header,
    )

    # ── Body content ──
    y = BORDER_WIDTH + HEADER_HEIGHT + 10

    # Signer name (bold)
    holder = cert_info.holder_name or cert_info.common_name
    if holder:
        draw.text((PADDING + BORDER_WIDTH, y), f"Signatário: {holder}",
                   fill=COLOR_BODY_TEXT, font=font_bold)
        y += LINE_HEIGHT

    # CPF and OAB on the same line
    id_parts = []
    if cert_info.cpf:
        id_parts.append(f"CPF: {cert_info.cpf}")
    if cert_info.oab:
        id_parts.append(f"OAB: {cert_info.oab}")
    if id_parts:
        draw.text((PADDING + BORDER_WIDTH, y), "  |  ".join(id_parts),
                   fill=COLOR_BODY_TEXT, font=font_normal)
        y += LINE_HEIGHT

    # Issuer
    if cert_info.issuer_cn:
        draw.text((PADDING + BORDER_WIDTH, y),
                   f"Autoridade Certificadora: {cert_info.issuer_cn}",
                   fill=COLOR_BODY_TEXT, font=font_normal)
        y += LINE_HEIGHT

    # Date (local timezone)
    tz_name = signing_date.strftime("%Z") or signing_date.strftime("%z")
    date_str = signing_date.strftime(f"%d/%m/%Y %H:%M:%S {tz_name}")
    draw.text((PADDING + BORDER_WIDTH, y), f"Data: {date_str}",
               fill=COLOR_BODY_TEXT, font=font_normal)
    y += LINE_HEIGHT

    # Reason (if provided)
    if reason and reason != "Documento assinado digitalmente":
        draw.text((PADDING + BORDER_WIDTH, y), f"Motivo: {reason}",
                   fill=COLOR_DIM, font=font_small)
        y += LINE_HEIGHT - 4

    # Bottom-right: signature hash indicator
    hash_text = f"SHA-256 | ICP-Brasil"
    bbox = draw.textbbox((0, 0), hash_text, font=font_small)
    text_width = bbox[2] - bbox[0]
    draw.text(
        (STAMP_WIDTH - BORDER_WIDTH - PADDING - text_width,
         STAMP_HEIGHT - BORDER_WIDTH - 18),
        hash_text, fill=COLOR_DIM, font=font_small,
    )

    # Accent line below header
    draw.line(
        [(BORDER_WIDTH + 2, BORDER_WIDTH + HEADER_HEIGHT + 2),
         (STAMP_WIDTH - BORDER_WIDTH - 2, BORDER_WIDTH + HEADER_HEIGHT + 2)],
        fill=COLOR_ACCENT + (150,), width=2,
    )

    return img


def stamp_to_bytes(img: Image.Image) -> bytes:
    """Convert stamp PIL Image to PNG bytes."""
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _load_font(bold: bool = False, size: int = 12) -> ImageFont.FreeTypeFont:
    """Load a TrueType font, with fallback to default."""
    font_paths = [
        # Ubuntu (preferred)
        "/usr/share/fonts/ubuntu/Ubuntu-B.ttf" if bold else "/usr/share/fonts/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/ubuntu/Ubuntu-M.ttf" if bold else "/usr/share/fonts/ubuntu/Ubuntu-L.ttf",
        # DejaVu Sans
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # Noto Sans
        "/usr/share/fonts/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/TTF/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/NotoSans-Regular.ttf",
        # Liberation Sans
        "/usr/share/fonts/TTF/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/LiberationSans-Regular.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue

    log.debug("No TrueType font found, using PIL default")
    return ImageFont.load_default(size)
