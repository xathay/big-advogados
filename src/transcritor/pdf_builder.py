"""Gerador de PDF da declaração técnica + transcrição.

Layout segue o plano em docs/plano-transcritor-audio.md:
- Capa: título + cadeia de custódia em destaque
- Seção I: Objeto (texto fixo parametrizado por caso/processo)
- Seção II: Ferramenta utilizada (faster-whisper, modelo, parâmetros)
- Seção III: Cadeia de custódia (SHA-256 + metadados verificáveis)
- Seção IV: Transcrição em tabela 2-col (tempo | conteúdo)
- Encerramento: declaração formal do advogado

Usa reportlab nativo (sem HTML/CSS) para manter o projeto sem deps novas
de PDF além das que já existem (reportlab já é dep transitiva).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from src.transcritor.config import AdvogadoConfig, IdentidadeVisualConfig
from src.transcritor.engine import TranscriptionResult
from src.transcritor.metadata import AudioMetadata, EnvironmentMetadata

log = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4

# Paleta exata do plano
COLOR_NAVY = colors.HexColor("#1B3A5C")
COLOR_ORANGE = colors.HexColor("#E07A11")
COLOR_PERGAMINHO = colors.HexColor("#F2EBDD")
COLOR_TEXTO = colors.HexColor("#2D3748")
COLOR_DIM = colors.HexColor("#5A6878")
COLOR_OXBLOOD = colors.HexColor("#6E1A1A")

CLAUSULA_PREVALENCIA = (
    "Em caso de divergência entre esta transcrição e o áudio original, "
    "prevalece integralmente o áudio gravado, juntado em sua integridade nativa."
)


def _register_font(nome_fonte: str) -> str:
    """Tenta registrar a fonte pedida; cai para Helvetica se não achar.

    Retorna o nome a ser usado nos styles do reportlab.
    """
    # reportlab tem Helvetica built-in; outras precisam de TTF
    if nome_fonte.lower() in ("helvetica", "times-roman", "courier"):
        return nome_fonte

    # Procura Ubuntu, Roboto, etc. nos paths típicos do Linux
    candidates = [
        f"/usr/share/fonts/TTF/{nome_fonte}-R.ttf",
        f"/usr/share/fonts/ubuntu/{nome_fonte}-R.ttf",
        f"/usr/share/fonts/truetype/{nome_fonte.lower()}/{nome_fonte}-R.ttf",
        f"/usr/share/fonts/truetype/{nome_fonte.lower()}-font-family/{nome_fonte}-R.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            try:
                pdfmetrics.registerFont(TTFont(nome_fonte, path))
                log.info("Fonte registrada: %s -> %s", nome_fonte, path)
                return nome_fonte
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao registrar %s: %s", path, exc)

    log.warning("Fonte %s não encontrada, caindo para Helvetica", nome_fonte)
    return "Helvetica"


def _make_styles(font_name: str) -> dict:
    base = getSampleStyleSheet()
    return {
        "titulo_capa": ParagraphStyle(
            "TituloCapa",
            parent=base["Title"],
            fontName=font_name,
            fontSize=22,
            textColor=COLOR_NAVY,
            alignment=TA_LEFT,
            leading=26,
            spaceAfter=8,
        ),
        "subtitulo_capa": ParagraphStyle(
            "SubtituloCapa",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=12,
            textColor=COLOR_DIM,
            alignment=TA_LEFT,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName=font_name,
            fontSize=14,
            textColor=COLOR_NAVY,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=12,
            textColor=COLOR_ORANGE,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "corpo": ParagraphStyle(
            "Corpo",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=11,
            textColor=COLOR_TEXTO,
            alignment=TA_JUSTIFY,
            leading=15,
            spaceAfter=6,
        ),
        "corpo_mono": ParagraphStyle(
            "CorpoMono",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=9,
            textColor=COLOR_TEXTO,
            alignment=TA_LEFT,
            leading=12,
        ),
        "dim": ParagraphStyle(
            "Dim",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9,
            textColor=COLOR_DIM,
            alignment=TA_LEFT,
        ),
        "clausula": ParagraphStyle(
            "Clausula",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=11,
            textColor=COLOR_OXBLOOD,
            alignment=TA_JUSTIFY,
            leading=15,
            leftIndent=12,
            borderColor=COLOR_OXBLOOD,
            borderWidth=0,
            borderPadding=8,
        ),
        "centro": ParagraphStyle(
            "Centro",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10,
            textColor=COLOR_DIM,
            alignment=TA_CENTER,
        ),
    }


def _fmt_size(bytes_count: int) -> str:
    """Formata bytes em KB/MB legíveis."""
    if bytes_count < 1024:
        return f"{bytes_count} B"
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    return f"{bytes_count / (1024 * 1024):.2f} MB"


def _fmt_duracao(segundos: Optional[float]) -> str:
    if segundos is None:
        return "—"
    minutos = int(segundos // 60)
    s = int(segundos % 60)
    return f"{minutos}m {s:02d}s ({segundos:.2f}s)"


def _build_cadeia_custodia_table(
    audio: AudioMetadata,
    env: EnvironmentMetadata,
    font_name: str,
) -> Table:
    """Tabela com a cadeia de custódia — destaque visual da capa."""
    sha_quebrado = " ".join(audio.sha256[i : i + 16] for i in range(0, 64, 16))
    data = [
        ["Arquivo", audio.arquivo],
        ["Tamanho", _fmt_size(audio.tamanho_bytes)],
        ["Formato", audio.formato or "—"],
        ["Duração", _fmt_duracao(audio.duracao_segundos)],
        ["SHA-256", sha_quebrado],
        ["Transcrição em", env.data_iso],
        ["Sistema", env.sistema_operacional],
    ]
    table = Table(data, colWidths=[3.2 * cm, 13 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), COLOR_NAVY),
        ("TEXTCOLOR", (1, 0), (1, -1), COLOR_TEXTO),
        ("FONTNAME", (1, 4), (1, 4), "Courier"),  # SHA mono
        ("FONTSIZE", (1, 4), (1, 4), 8),
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PERGAMINHO),
        ("LINEBEFORE", (0, 0), (0, -1), 3, COLOR_OXBLOOD),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _build_segmentos_table(
    result: TranscriptionResult,
    font_name: str,
) -> Table:
    """Tabela de 2 colunas (tempo | conteúdo) com linhas alternadas."""
    header = [
        Paragraph("<b>Tempo</b>", ParagraphStyle("th", fontName=font_name, fontSize=10, textColor=colors.white, alignment=TA_CENTER)),
        Paragraph("<b>Conteúdo</b>", ParagraphStyle("th", fontName=font_name, fontSize=10, textColor=colors.white, alignment=TA_LEFT)),
    ]
    rows = [header]
    for seg in result.segments:
        tempo = f"{seg.start_timestamp}\n→ {seg.end_timestamp}"
        rows.append([
            Paragraph(tempo, ParagraphStyle("tempo", fontName="Courier", fontSize=8, textColor=COLOR_DIM, alignment=TA_CENTER, leading=10)),
            Paragraph(seg.text.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                      ParagraphStyle("conteudo", fontName=font_name, fontSize=10, textColor=COLOR_TEXTO, alignment=TA_LEFT, leading=13)),
        ])

    table = Table(rows, colWidths=[3.2 * cm, 13 * cm], repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, COLOR_DIM),
    ]
    # Linhas alternadas (zebrado)
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), COLOR_PERGAMINHO))
    table.setStyle(TableStyle(style_cmds))
    return table


class _HeaderFooter:
    """Callable para reportlab onPage — desenha logo (header) e barra (footer)."""

    def __init__(self, identidade: IdentidadeVisualConfig) -> None:
        self.identidade = identidade

    def __call__(self, canvas, doc) -> None:
        canvas.saveState()

        # Logo no topo direito
        if self.identidade.logo_existe:
            try:
                canvas.drawImage(
                    str(self.identidade.logo),
                    PAGE_W - 4.5 * cm, PAGE_H - 2.5 * cm,
                    width=3 * cm, height=1.5 * cm,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao desenhar logo: %s", exc)

        # Barra-rodapé
        if self.identidade.footer_bar_existe:
            try:
                canvas.drawImage(
                    str(self.identidade.footer_bar),
                    0, 0,
                    width=PAGE_W, height=1.5 * cm,
                    preserveAspectRatio=False, mask="auto",
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao desenhar footer_bar: %s", exc)

        # Número da página (mesmo sem footer_bar, sempre desenha)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(COLOR_DIM)
        canvas.drawRightString(PAGE_W - 1.5 * cm, 0.8 * cm, f"Página {doc.page}")
        canvas.restoreState()


def build_pdf(
    output_path: Path,
    audio: AudioMetadata,
    env: EnvironmentMetadata,
    result: TranscriptionResult,
    identidade: IdentidadeVisualConfig,
    advogado: AdvogadoConfig,
    objeto_texto: Optional[str] = None,
) -> None:
    """Gera o PDF da declaração técnica + transcrição."""
    font_name = _register_font(identidade.fonte_corpo)
    styles = _make_styles(font_name)

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=3 * cm,
        bottomMargin=2.2 * cm,
        title=f"Transcrição — {audio.arquivo}",
        author=advogado.nome or "Big Advogados",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="normal",
    )
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[frame], onPage=_HeaderFooter(identidade)),
    ])

    story: list = []

    # ───────────────────────── CAPA ─────────────────────────
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(
        "Declaração técnica e transcrição integral",
        styles["titulo_capa"],
    ))
    story.append(Paragraph(
        f"Áudio: <b>{audio.arquivo}</b><br/>"
        f"Transcrito em {env.data_iso}",
        styles["subtitulo_capa"],
    ))

    story.append(Paragraph("Cadeia de custódia", styles["h2"]))
    story.append(_build_cadeia_custodia_table(audio, env, font_name))
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(CLAUSULA_PREVALENCIA, styles["clausula"]))

    story.append(PageBreak())

    # ────────────────────── SEÇÃO I — OBJETO ──────────────────────
    story.append(Paragraph("I — Objeto", styles["h1"]))
    objeto_default = (
        "O presente documento tem por objeto apresentar a transcrição integral "
        "do arquivo de áudio identificado na seção 'Cadeia de custódia' acima, "
        "obtida por ferramenta de transcrição automática de fala (Speech-to-Text), "
        "executada localmente, sem qualquer envio do áudio a serviços de nuvem."
    )
    story.append(Paragraph(objeto_texto or objeto_default, styles["corpo"]))

    # ────────────────────── SEÇÃO II — FERRAMENTA ──────────────────────
    story.append(Paragraph("II — Ferramenta utilizada", styles["h1"]))
    versao_whisper = env.faster_whisper_versao or "indeterminada"
    story.append(Paragraph(
        f"<b>faster-whisper</b> versão {versao_whisper} — implementação CTranslate2 "
        "do modelo Whisper desenvolvido pela OpenAI. Licença MIT. "
        "Repositório público: <font color='#1B3A5C'>github.com/SYSTRAN/faster-whisper</font>.",
        styles["corpo"],
    ))
    story.append(Spacer(1, 4 * mm))

    params = [
        ["Modelo", result.modelo],
        ["Device", result.device],
        ["Compute type", result.compute_type],
        ["Idioma (parametrizado)", "pt"],
        ["Idioma (detectado)", f"{result.idioma_detectado} (prob: {result.probabilidade_idioma:.3f})"],
        ["Beam size", "10"],
        ["Temperature", "0.0"],
        ["VAD filter", "true"],
        ["Word timestamps", "true"],
    ]
    t = Table(params, colWidths=[5 * cm, 11 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), COLOR_NAVY),
        ("TEXTCOLOR", (1, 0), (1, -1), COLOR_TEXTO),
        ("GRID", (0, 0), (-1, -1), 0.25, COLOR_DIM),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    # ────────────────────── SEÇÃO III — CADEIA DE CUSTÓDIA ──────────────────────
    story.append(Paragraph("III — Cadeia de custódia (detalhada)", styles["h1"]))
    story.append(Paragraph(
        "Os metadados abaixo permitem verificação independente. Qualquer perito "
        "que aplique os mesmos parâmetros sobre o mesmo arquivo deve obter o "
        "mesmo SHA-256 e, com o modelo informado, transcrição equivalente.",
        styles["corpo"],
    ))
    detalhes = [
        ["Caminho absoluto (no momento da transcrição)", audio.caminho_absoluto],
        ["Hostname", env.hostname],
        ["Python", env.python_versao],
    ]
    t2 = Table(detalhes, colWidths=[7 * cm, 9 * cm])
    t2.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), COLOR_NAVY),
        ("TEXTCOLOR", (1, 0), (1, -1), COLOR_TEXTO),
        ("GRID", (0, 0), (-1, -1), 0.25, COLOR_DIM),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t2)

    # ────────────────────── SEÇÃO IV — TRANSCRIÇÃO ──────────────────────
    story.append(PageBreak())
    story.append(Paragraph("IV — Transcrição", styles["h1"]))
    if not result.segments:
        story.append(Paragraph(
            "<i>Nenhum segmento de fala detectado pelo VAD.</i>",
            styles["corpo"],
        ))
    else:
        story.append(_build_segmentos_table(result, font_name))

    # ────────────────────── ENCERRAMENTO ──────────────────────
    story.append(Spacer(1, 1 * cm))
    if advogado.preenchido:
        encerramento = (
            f"Por ser expressão da verdade, firmo a presente declaração técnica.<br/><br/>"
            f"<b>{advogado.nome}</b><br/>"
            f"{advogado.oab}"
        )
        if advogado.escritorio:
            encerramento += f"<br/>{advogado.escritorio}"
        story.append(Paragraph(encerramento, styles["corpo"]))
    else:
        story.append(Paragraph(
            "<i>Dados do advogado não configurados — preencha a seção [advogado] "
            "em ~/.config/big-advogados/transcritor.toml para emitir declarações "
            "assinadas.</i>",
            styles["dim"],
        ))

    doc.build(story)
    log.info("PDF gerado: %s", output_path)
