"""Optional certification page appended at the end of a signed PDF.

Mirrors the convention used by PJe, e-CAC and Adobe Sign: instead of
overlaying the visual stamp on the last page of the document (which often
collides with letterheads and footers), append a dedicated A4 page that
holds the stamp plus validation instructions and the full SHA-256 of the
original document.
"""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO

import pikepdf
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from src.certificate.parser import CertificateInfo
from src.certificate.stamp import VERIFY_LABEL

log = logging.getLogger(__name__)

# A4 = 595 x 842 pt
PAGE_W, PAGE_H = A4

# Stamp dimensions on the page (must match pdf_signer.SignatureOptions)
STAMP_W = 280
STAMP_H = 80

# Stamp position: centered horizontally, upper third of the page.
STAMP_X = (PAGE_W - STAMP_W) / 2
STAMP_Y = PAGE_H - 240  # y of stamp bottom edge, 240pt below top

# Palette mirrors stamp.py
COLOR_NAVY = (16 / 255, 42 / 255, 67 / 255)
COLOR_ORANGE = (224 / 255, 122 / 255, 17 / 255)
COLOR_TEXT = (45 / 255, 55 / 255, 72 / 255)
COLOR_DIM = (90 / 255, 104 / 255, 120 / 255)


def append_certification_page(
    pdf_bytes: bytes,
    cert_info: CertificateInfo,
    signing_date: datetime,
    pdf_hash: str,
    reason: str = "",
) -> tuple[bytes, int, tuple[float, float, float, float]]:
    """Append a certification page to the PDF.

    Returns:
        (new_pdf_bytes, sig_page_index, sig_box) where sig_box is the
        rectangle (x1, y1, x2, y2) in PDF points where the stamp image
        should be placed by endesive.
    """
    cert_page_bytes = _build_certification_page_pdf(
        cert_info, signing_date, pdf_hash, reason,
    )

    with pikepdf.open(BytesIO(pdf_bytes)) as src:
        with pikepdf.open(BytesIO(cert_page_bytes)) as cert:
            src.pages.append(cert.pages[0])
        out = BytesIO()
        src.save(out)
        new_bytes = out.getvalue()
        new_page_index = len(src.pages) - 1

    sig_box = (STAMP_X, STAMP_Y, STAMP_X + STAMP_W, STAMP_Y + STAMP_H)
    return new_bytes, new_page_index, sig_box


def _build_certification_page_pdf(
    cert_info: CertificateInfo,
    signing_date: datetime,
    pdf_hash: str,
    reason: str,
) -> bytes:
    """Build a single-page A4 PDF with the certification layout.

    Leaves a blank rectangle at (STAMP_X, STAMP_Y) of size STAMP_W x STAMP_H
    where endesive will later place the stamp image.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # ── Header ─────────────────────────────────────────────
    c.setFillColorRGB(*COLOR_NAVY)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 80, "PÁGINA DE CERTIFICAÇÃO")
    c.drawCentredString(PAGE_W / 2, PAGE_H - 102, "DA ASSINATURA DIGITAL")

    c.setFillColorRGB(*COLOR_DIM)
    c.setFont("Helvetica", 10)
    c.drawCentredString(
        PAGE_W / 2, PAGE_H - 124,
        "MP nº 2.200-2/2001 · Lei nº 14.063/2020 · ICP-Brasil",
    )

    # Orange filete
    c.setStrokeColorRGB(*COLOR_ORANGE)
    c.setLineWidth(1.2)
    c.line(120, PAGE_H - 144, PAGE_W - 120, PAGE_H - 144)

    # ── Stamp area: leave blank for endesive ───────────────
    # (no drawing here — sig_box reserved for stamp image)

    # ── Validation instructions ────────────────────────────
    y = STAMP_Y - 70  # below stamp
    c.setFillColorRGB(*COLOR_TEXT)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(80, y, "Como verificar a autenticidade desta assinatura:")
    y -= 20

    c.setFont("Helvetica", 10)
    steps = [
        f"1. Acesse {VERIFY_LABEL} (Validador oficial do ITI).",
        "2. Clique em \"Escolher Arquivo\" e envie este PDF.",
        "3. Marque \"Concordo com os termos\" e clique em \"Validar\".",
        "4. Confira no relatório se o status é \"Aprovado\".",
    ]
    for step in steps:
        c.drawString(96, y, step)
        y -= 16

    y -= 12

    # ── Original document hash ─────────────────────────────
    c.setFont("Helvetica-Bold", 11)
    c.drawString(80, y, "Hash SHA-256 do documento original (antes da assinatura):")
    y -= 20

    c.setFont("Courier", 9)
    c.setFillColorRGB(*COLOR_DIM)
    # Wrap hash to two lines if needed (64 chars fits at Courier 9 in 435pt)
    if pdf_hash:
        c.drawString(96, y, pdf_hash[:32])
        y -= 12
        c.drawString(96, y, pdf_hash[32:])
        y -= 18

    c.setFillColorRGB(*COLOR_TEXT)
    c.setFont("Helvetica", 9)
    c.drawString(
        80, y,
        "Este hash identifica unicamente o conteúdo do documento original.",
    )
    y -= 12
    c.drawString(
        80, y,
        "Quem detém o PDF não-assinado pode reproduzi-lo via "
        "`sha256sum <arquivo.pdf>` para conferência independente.",
    )

    # ── Footer ────────────────────────────────────────────
    c.setFillColorRGB(*COLOR_DIM)
    c.setFont("Helvetica", 8)
    c.drawCentredString(
        PAGE_W / 2, 60,
        f"Documento assinado em {signing_date.strftime('%d/%m/%Y às %H:%M:%S')} "
        f"({signing_date.strftime('%Z') or signing_date.strftime('%z')}).",
    )
    if reason and reason != "Documento assinado digitalmente":
        c.drawCentredString(PAGE_W / 2, 48, f"Motivo: {reason}")

    c.showPage()
    c.save()
    return buf.getvalue()
