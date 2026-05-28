"""Gerador de PDF da declaração técnica + transcrição.

Implementa fielmente o template visual do escritório (cf. projeto-piloto
``build_anexo_12.py``), via reportlab nativo — sem dependência de
LibreOffice nem de PNGs externos. O logo "LA" e o footer-bar são
desenhados via canvas.

Dois modos de operação:

- **Modo simples** — quando nenhuma flag de caso é passada (sem
  ``--processo``), gera um documento mínimo por áudio, com cadeia de
  custódia e cláusula de prevalência. Útil para uso doméstico/triagem.

- **Modo formal (declaração técnica)** — ativado por presença de
  ``--processo``. Replica o Anexo 12 do projeto-piloto: 5 seções
  numeradas (Objeto, Metodologia, Cadeia de custódia, Transcrições,
  Encerramento), anexo técnico com parâmetros de execução e
  encerramento com assinatura(s). Suporta múltiplos áudios em um único
  PDF (modo lote).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
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

# ─────────────────────────── Paleta (extraída do FODT do escritório) ───────────────────────────
COLOR_NAVY = colors.HexColor("#1B3A5C")
COLOR_OXBLOOD = colors.HexColor("#5C1A14")
COLOR_ORANGE = colors.HexColor("#B5470F")
COLOR_PERGAMINHO = colors.HexColor("#F2EBDD")
COLOR_CREME = colors.HexColor("#FCE7C9")
COLOR_CINZA_CLARO = colors.HexColor("#F4F6FA")
COLOR_TEXTO = colors.HexColor("#1A1612")
COLOR_TEXTO_DIM = colors.HexColor("#4A4138")
COLOR_BRANCO = colors.HexColor("#FFFFFF")

CLAUSULA_PREVALENCIA = (
    "Em caso de divergência entre esta transcrição e o áudio original, "
    "prevalece integralmente o áudio gravado, juntado em sua integridade nativa."
)


# ─────────────────────────── Estrutura de dados pro modo formal ───────────────────────────

@dataclass(frozen=True)
class DadosCaso:
    """Dados do processo/caso para o template formal (modo declaração técnica).

    Se `processo` estiver definido, ativa o template formal. Caso contrário,
    cai no modo simples.
    """

    processo: str = ""
    """Número do processo principal (ex.: '0000000-00.0000.0.00.0000')."""

    cliente: str = ""
    """Nome da parte que o subscritor representa (ex.: 'Fulana de Tal')."""

    contraparte: str = ""
    """Nome da parte adversa (ex.: 'Empresa Adversa Ltda')."""

    documento: str = ""
    """Descrição do documento ao qual a declaração se anexa
    (ex.: 'Anexo às contrarrazões ao Agravo de Instrumento nº 0000000...')."""

    juizo: str = ""
    """Identificação do órgão julgador (ex.: 'Câmara Cível do Tribunal de Justiça')."""

    posicao_cliente: str = "Agravada"
    """Polo processual do cliente (Agravada, Autora, Ré, Apelante, etc.)."""

    posicao_contraparte: str = "Agravante"
    """Polo processual da contraparte."""

    data_declaracao: str = ""
    """Data da declaração no formato extenso (ex.: '20 de maio de 2026').
    Se vazio, usa data corrente."""

    local: str = "Salvador/BA"
    """Cidade onde a declaração é firmada."""

    remetente_nome: str = ""
    """Nome do advogado que enviou os áudios (ex.: 'Dr. Fulano de Tal')."""

    remetente_oab: str = ""
    """OAB do remetente (ex.: 'OAB/BA 00.000')."""

    @property
    def modo_formal(self) -> bool:
        return bool(self.processo.strip())


@dataclass(frozen=True)
class CoSubscritor:
    """Segundo advogado que assina o documento (opcional)."""

    nome: str
    oab: str


@dataclass(frozen=True)
class AudioEntry:
    """Um áudio para inclusão no PDF (modo lote suporta múltiplos)."""

    metadata: AudioMetadata
    transcription: TranscriptionResult
    data_recebimento: str = ""
    """Data/hora extraída do nome do arquivo ou passada via CLI (ex.: '01/01/2026 — 00h00')."""

    segmentos_destacados: tuple[int, ...] = field(default_factory=tuple)
    """Índices (1-based) dos segmentos a destacar visualmente na tabela
    (background creme + texto bold-oxblood). Selecionados manualmente
    pelo advogado pela CLI flag --destacar-segmento."""


# ─────────────────────────── Resolução de fontes ───────────────────────────

def _fc_match(family: str, style: str = "Regular") -> Optional[Path]:
    """Usa fontconfig para localizar o arquivo TTF de uma família+estilo."""
    if not shutil.which("fc-match"):
        return None
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}\n", f"{family}:style={style}"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    path_str = result.stdout.strip()
    if not path_str:
        return None
    path = Path(path_str)
    return path if path.is_file() else None


def _register_font(nome_fonte: str) -> str:
    """Registra a fonte (e variantes Bold/Italic) via fontconfig.

    Retorna o nome a usar no reportlab. Cai para Helvetica se não encontrar.
    Também registra Ubuntu Mono para os timestamps, se disponível.
    """
    if nome_fonte.lower() in ("helvetica", "times-roman", "courier"):
        return nome_fonte

    path = _fc_match(nome_fonte, "Regular")
    if path is None:
        log.warning("Fonte %s não encontrada via fontconfig, caindo para Helvetica", nome_fonte)
        return "Helvetica"

    try:
        pdfmetrics.registerFont(TTFont(nome_fonte, str(path)))
        log.info("Fonte registrada: %s -> %s", nome_fonte, path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao registrar %s: %s", nome_fonte, exc)
        return "Helvetica"

    # Variantes
    for style_name, suffix in (("Bold", "-Bold"), ("Italic", "-Italic"), ("BoldItalic", "-BoldItalic")):
        variant_path = _fc_match(nome_fonte, style_name)
        if variant_path and variant_path != path:
            try:
                pdfmetrics.registerFont(TTFont(nome_fonte + suffix, str(variant_path)))
            except Exception:  # noqa: BLE001
                pass

    # Ubuntu Mono pros timestamps
    mono_path = _fc_match("Ubuntu Mono", "Regular")
    if mono_path:
        try:
            pdfmetrics.registerFont(TTFont("UbuntuMono", str(mono_path)))
            log.debug("Ubuntu Mono registrada: %s", mono_path)
        except Exception:  # noqa: BLE001
            pass

    return nome_fonte


# ─────────────────────────── Helpers de formatação ───────────────────────────

def _escape(text: str) -> str:
    """Escape mínimo pra Pango/reportlab markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_size(bytes_count: int) -> str:
    if bytes_count < 1024:
        return f"{bytes_count} B"
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    return f"{bytes_count / (1024 * 1024):.2f} MB"


def _fmt_duracao_curta(segundos: Optional[float]) -> str:
    if segundos is None:
        return "—"
    return f"{segundos:.2f} s"


_MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def _data_extenso(d: datetime) -> str:
    """'20 de maio de 2026'"""
    return f"{d.day} de {_MESES_PT[d.month]} de {d.year}"


def _mono(text: str, size: int = 8) -> Paragraph:
    """Retorna paragrafo monospace pra hashes/timestamps."""
    style = ParagraphStyle(
        "mono", fontName="UbuntuMono", fontSize=size,
        textColor=COLOR_TEXTO, leading=size + 2,
    )
    return Paragraph(_escape(text), style)


def _highlight_box(paragrafo: Paragraph, largura_disponivel: float = None) -> Table:
    """Envolve um Paragraph em uma mini-Table de 1 célula com background
    pergaminho, replicando o efeito 'highlighter' do template do escritório
    em frases-chave (cláusula de prevalência, etc.)."""
    if largura_disponivel is None:
        largura_disponivel = PAGE_W - 4 * cm
    t = Table([[paragrafo]], colWidths=[largura_disponivel])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PERGAMINHO),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


# ─────────────────────────── Estilos ───────────────────────────

def _smallcaps(text: str) -> str:
    """Simula small-caps: tudo em UPPERCASE; o letter-spacing fica a cargo
    do `charSpace` do ParagraphStyle. Útil porque Ubuntu não tem variante
    small-caps real e reportlab não suporta a tag <smallcaps>."""
    return text.upper()


def _make_styles(font_name: str) -> dict:
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "Titulo",
            parent=base["Title"],
            fontName=font_name + "-Bold",
            fontSize=15,
            textColor=COLOR_OXBLOOD,
            alignment=TA_CENTER,
            leading=20,
            spaceAfter=10,
            charSpace=2.0,   # letter-spacing — small-caps look
        ),
        "subtitulo": ParagraphStyle(
            "Subtitulo",
            parent=base["Italic"],
            fontName=font_name + "-Italic",
            fontSize=11,
            textColor=COLOR_TEXTO_DIM,
            alignment=TA_CENTER,
            leading=15,
            spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName=font_name + "-Bold",
            fontSize=11,
            textColor=COLOR_OXBLOOD,
            spaceBefore=16,
            spaceAfter=8,
            leading=14,
            charSpace=1.2,   # letter-spacing pra section headings
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=font_name + "-Bold",
            fontSize=10.5,
            textColor=COLOR_NAVY,
            spaceBefore=10,
            spaceAfter=4,
            charSpace=0.8,
        ),
        "corpo": ParagraphStyle(
            "Corpo",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=11,
            textColor=COLOR_TEXTO,
            alignment=TA_JUSTIFY,
            leading=15,
            spaceAfter=8,
        ),
        "caixa_meta": ParagraphStyle(
            "CaixaMeta",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9.5,
            textColor=COLOR_TEXTO,
            leading=13,
        ),
        "caixa_meta_label": ParagraphStyle(
            "CaixaMetaLabel",
            parent=base["BodyText"],
            fontName=font_name + "-Bold",
            fontSize=9.5,
            textColor=COLOR_OXBLOOD,
            leading=13,
        ),
        "lista_anexo": ParagraphStyle(
            "ListaAnexo",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10,
            textColor=COLOR_TEXTO,
            leading=14,
            leftIndent=20,
            bulletIndent=10,
        ),
        "encerramento_nome": ParagraphStyle(
            "EncerramentoNome",
            parent=base["BodyText"],
            fontName=font_name + "-Bold",
            fontSize=11,
            textColor=COLOR_TEXTO,
            alignment=TA_CENTER,
            leading=14,
        ),
        "encerramento_oab": ParagraphStyle(
            "EncerramentoOAB",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10,
            textColor=COLOR_TEXTO,
            alignment=TA_CENTER,
            leading=12,
        ),
        "encerramento_assinatura": ParagraphStyle(
            "EncerramentoAssinatura",
            parent=base["BodyText"],
            fontName=font_name + "-Italic",
            fontSize=9,
            textColor=COLOR_TEXTO_DIM,
            alignment=TA_CENTER,
            leading=12,
        ),
        "local_data": ParagraphStyle(
            "LocalData",
            parent=base["BodyText"],
            fontName=font_name + "-Italic",
            fontSize=10,
            textColor=COLOR_TEXTO,
            alignment=TA_CENTER,
            leading=14,
            spaceAfter=20,
        ),
    }


# ─────────────────────────── Componentes visuais ───────────────────────────

class _PageDecorator:
    """Callable de onPage: desenha logo na 1ª página e footer em todas as páginas.

    Tanto o logo quanto o footer-bar são imagens PNG completas (extraídas do
    ODT do escritório). Posições, ícones e cores já estão dentro das imagens
    — basta colá-las no lugar certo.
    """

    LOGO_W = 5.0 * cm        # largura visual do logo no PDF
    LOGO_H = 1.6 * cm        # altura proporcional (relação ~3.16:1 do PNG)
    FOOTER_H = 1.05 * cm     # altura do footer (proporcional à largura A4)

    def __init__(self, advogado: AdvogadoConfig, identidade: IdentidadeVisualConfig) -> None:
        self.advogado = advogado
        self.identidade = identidade

    def __call__(self, canvas, doc) -> None:
        # Logo só na primeira página (topo-esquerdo)
        if doc.page == 1 and self.identidade.logo_existe:
            try:
                canvas.drawImage(
                    str(self.identidade.logo),
                    2.2 * cm, PAGE_H - 2.0 * cm - self.LOGO_H,
                    width=self.LOGO_W, height=self.LOGO_H,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao desenhar logo: %s", exc)

        # Footer-bar em todas as páginas, full-width (encosta nas margens
        # esquerda/direita da página, não nas margens do conteúdo)
        if self.identidade.footer_bar_existe:
            try:
                canvas.drawImage(
                    str(self.identidade.footer_bar),
                    0, 0,
                    width=PAGE_W, height=self.FOOTER_H,
                    preserveAspectRatio=True, anchor="sw", mask="auto",
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao desenhar footer-bar: %s", exc)


# ─────────────────────────── Componentes de conteúdo ───────────────────────────

def _caixa_metadados_documento(caso: DadosCaso, advogado: AdvogadoConfig, font_name: str) -> Table:
    """Caixa beige após o subtítulo, com Documento / Data / Subscritor."""
    data_decl = caso.data_declaracao or _data_extenso(datetime.now())
    rows = []
    if caso.documento:
        rows.append([_kv("Documento", caso.documento, font_name)])
    rows.append([_kv("Data da declaração", data_decl, font_name)])
    rows.append([_kv("Subscritor", f"{advogado.nome} — {advogado.oab}", font_name)])

    t = Table(rows, colWidths=[PAGE_W - 4 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PERGAMINHO),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, COLOR_ORANGE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, -1), (0, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _kv(label: str, value: str, font_name: str) -> Paragraph:
    """Linha 'Label: value' com label em bold oxblood."""
    style = ParagraphStyle(
        "kv", fontName=font_name, fontSize=9.5,
        textColor=COLOR_TEXTO, leading=13,
    )
    return Paragraph(
        f'<font name="{font_name}-Bold" color="#5C1A14">{_escape(label)}:</font> {_escape(value)}',
        style,
    )


def _caixa_audio(audio: AudioEntry, font_name: str, numero: Optional[int] = None) -> Table:
    """Caixa pergaminho com identificação do arquivo (na seção III)."""
    rows = [
        [_kv("Arquivo original (M4A)", audio.metadata.arquivo, font_name)],
        [_kv_mono("SHA-256 (original)", audio.metadata.sha256, font_name)],
    ]
    detalhe_extra = []
    if audio.metadata.duracao_segundos:
        detalhe_extra.append(f"Duração: {audio.metadata.duracao_segundos:.2f} s")
    if audio.data_recebimento:
        detalhe_extra.append(f"Recebido em: {audio.data_recebimento}")
    if detalhe_extra:
        rows.append([_kv_inline("  ·  ".join(detalhe_extra), font_name)])

    t = Table(rows, colWidths=[PAGE_W - 4 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PERGAMINHO),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, -1), (0, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _kv_mono(label: str, value: str, font_name: str) -> Paragraph:
    style = ParagraphStyle("kvm", fontName=font_name, fontSize=9.5, textColor=COLOR_TEXTO, leading=13)
    return Paragraph(
        f'<font name="{font_name}-Bold" color="#5C1A14">{_escape(label)}:</font> '
        f'<font name="UbuntuMono" size="8.5">{_escape(value)}</font>',
        style,
    )


def _kv_inline(text: str, font_name: str) -> Paragraph:
    style = ParagraphStyle("kvinline", fontName=font_name + "-Bold",
                           fontSize=9.5, textColor=COLOR_OXBLOOD, leading=13)
    return Paragraph(_escape(text), style)


def _tabela_segmentos(audio: AudioEntry, font_name: str) -> Table:
    """Tabela 2-col (Tempo (s) | Conteúdo transcrito) com header navy."""
    th_style = ParagraphStyle(
        "th", fontName=font_name + "-Bold", fontSize=8.5,
        textColor=COLOR_BRANCO, alignment=TA_LEFT, leading=11,
        charSpace=1.5,  # letter-spacing nos headers
    )
    th_center = ParagraphStyle(
        "thc", fontName=font_name + "-Bold", fontSize=8.5,
        textColor=COLOR_BRANCO, alignment=TA_CENTER, leading=11,
        charSpace=1.5,
    )
    header = [
        Paragraph(_smallcaps("Tempo (s)"), th_center),
        Paragraph(_smallcaps("Conteúdo transcrito"), th_style),
    ]
    rows = [header]

    tempo_style = ParagraphStyle(
        "tempo", fontName="UbuntuMono", fontSize=8,
        textColor=COLOR_OXBLOOD, alignment=TA_CENTER, leading=11,
    )
    conteudo_style = ParagraphStyle(
        "conteudo", fontName=font_name, fontSize=10,
        textColor=COLOR_TEXTO, alignment=TA_LEFT, leading=13,
    )
    tempo_destaque_style = ParagraphStyle(
        "tempo_d", fontName="UbuntuMono", fontSize=8,
        textColor=COLOR_OXBLOOD, alignment=TA_CENTER, leading=11,
    )
    conteudo_destaque_style = ParagraphStyle(
        "conteudo_d", fontName=font_name + "-Bold", fontSize=10,
        textColor=COLOR_OXBLOOD, alignment=TA_LEFT, leading=13,
    )

    destacados = set(audio.segmentos_destacados)
    for idx, seg in enumerate(audio.transcription.segments, start=1):
        tempo = f"{_fmt_timestamp(seg.start)} → {_fmt_timestamp(seg.end)}"
        if idx in destacados:
            rows.append([
                Paragraph(tempo, tempo_destaque_style),
                Paragraph(_escape(seg.text.strip()), conteudo_destaque_style),
            ])
        else:
            rows.append([
                Paragraph(tempo, tempo_style),
                Paragraph(_escape(seg.text.strip()), conteudo_style),
            ])

    t = Table(rows, colWidths=[3.5 * cm, PAGE_W - 4 * cm - 3.5 * cm], repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 1), (-1, 1), 0.5, COLOR_NAVY),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, COLOR_NAVY),
    ]
    # Zebrado sutil — branco vs cinza-clarissimo. Destacados sobrescrevem.
    for i in range(1, len(rows)):
        if i in destacados:
            cmds.append(("BACKGROUND", (0, i), (-1, i), COLOR_CREME))
        else:
            cmds.append((
                "BACKGROUND", (0, i), (-1, i),
                COLOR_CINZA_CLARO if i % 2 == 0 else COLOR_BRANCO,
            ))
    t.setStyle(TableStyle(cmds))
    return t


def _fmt_timestamp(seconds: float) -> str:
    """'MM:SS,mm' — formato curto pra tabela (não SRT)."""
    if seconds < 0:
        seconds = 0
    total_ms = int(round(seconds * 1000))
    m, rem = divmod(total_ms, 60_000)
    s, ms_ = divmod(rem, 1000)
    return f"{m:02d}:{s:02d},{ms_ // 10:02d}"


# ─────────────────────────── Construção do PDF ───────────────────────────

def _build_simple(
    output_path: Path,
    audio: AudioEntry,
    env: EnvironmentMetadata,
    identidade: IdentidadeVisualConfig,
    advogado: AdvogadoConfig,
    font_name: str,
    styles: dict,
) -> None:
    """Modo simples — 1 áudio, layout enxuto (sem declaração formal)."""
    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=4 * cm,
        bottomMargin=2.5 * cm,
        title=f"Transcrição — {audio.metadata.arquivo}",
        author=advogado.nome or "Big Advogados",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[frame],
                     onPage=_PageDecorator(advogado, identidade)),
    ])

    story: list = []
    story.append(Paragraph("Transcrição de áudio", styles["titulo"]))
    story.append(Paragraph(_escape(audio.metadata.arquivo), styles["subtitulo"]))
    story.append(Spacer(1, 4 * mm))

    story.append(_caixa_audio(audio, font_name))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(
        f'<font name="{font_name}-Bold" color="#5C1A14">'
        f'{_escape(CLAUSULA_PREVALENCIA)}</font>',
        styles["corpo"],
    ))

    story.append(Spacer(1, 6 * mm))
    story.append(_tabela_segmentos(audio, font_name))

    doc.build(story)


def _build_formal(
    output_path: Path,
    audios: Sequence[AudioEntry],
    env: EnvironmentMetadata,
    identidade: IdentidadeVisualConfig,
    advogado: AdvogadoConfig,
    caso: DadosCaso,
    co_subscritor: Optional[CoSubscritor],
    font_name: str,
    styles: dict,
) -> None:
    """Modo formal — declaração técnica completa (1+ áudios)."""
    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=4 * cm,
        bottomMargin=2.5 * cm,
        title=f"Declaração técnica — {caso.processo}",
        author=advogado.nome or "Big Advogados",
        subject=caso.documento,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[frame],
                     onPage=_PageDecorator(advogado, identidade)),
    ])

    story: list = []

    # ─── Título + subtítulo ─────────────────────────────────────────────────
    story.append(Paragraph(
        _smallcaps("Declaração técnica e transcrições integrais"),
        styles["titulo"],
    ))
    subtitulo = _build_subtitulo(audios, caso)
    story.append(Paragraph(subtitulo, styles["subtitulo"]))
    story.append(Spacer(1, 2 * mm))

    # ─── Caixa de metadados do documento ────────────────────────────────────
    story.append(_caixa_metadados_documento(caso, advogado, font_name))
    story.append(Spacer(1, 6 * mm))

    # ─── I — Objeto ─────────────────────────────────────────────────────────
    story.append(Paragraph(_smallcaps("I. Objeto"), styles["h1"]))
    story.append(Paragraph(_texto_objeto(audios, caso), styles["corpo"]))
    story.append(Paragraph(
        _escape(
            "Os arquivos sonoros, em seu formato original (M4A, formato em que o "
            "WhatsApp distribui mensagens de voz), permanecem disponíveis para "
            "escuta direta."
        ),
        styles["corpo"],
    ))
    # Cláusula de prevalência em destaque pergaminho (formato Anexo 12)
    story.append(_highlight_box(Paragraph(
        f'<font name="{font_name}-Bold" color="#5C1A14">'
        f'{_escape(CLAUSULA_PREVALENCIA)}</font>',
        styles["corpo"],
    )))
    story.append(Spacer(1, 4 * mm))

    # ─── II — Metodologia ───────────────────────────────────────────────────
    story.append(Paragraph(
        _smallcaps("II. Da metodologia adotada na transcrição"), styles["h1"],
    ))
    for para in _texto_metodologia(env):
        story.append(Paragraph(para, styles["corpo"]))

    # ─── III — Cadeia de custódia ───────────────────────────────────────────
    story.append(Paragraph(
        _smallcaps("III. Da cadeia de custódia dos arquivos sonoros"), styles["h1"],
    ))
    story.append(Paragraph(
        _escape(
            "Para a preservação da cadeia de custódia, calculou-se o resumo "
            "criptográfico SHA-256 de cada arquivo de áudio, conforme adiante. "
            "Trata-se de função de hash criptográfico de uso consagrado em foro "
            "forense:"
        ),
        styles["corpo"],
    ))
    story.append(_highlight_box(Paragraph(
        f'<font name="{font_name}-Bold" color="#5C1A14">'
        f'{_escape("a alteração de um único bit do arquivo produz um hash radicalmente distinto, de modo que qualquer modificação ulterior do conteúdo sonoro é imediatamente detectável por simples conferência.")}</font>',
        styles["corpo"],
    )))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        _escape(
            "Os resumos abaixo podem ser verificados, por qualquer parte ou perito, "
            "mediante execução do comando padrão sha256sum (sistemas POSIX) ou "
            "ferramenta equivalente em sistema Windows. A verificação é gratuita, "
            "instantânea e independente."
        ),
        styles["corpo"],
    ))
    for audio in audios:
        story.append(_caixa_audio(audio, font_name))
        story.append(Spacer(1, 3 * mm))

    # ─── IV — Transcrições ──────────────────────────────────────────────────
    story.append(Paragraph(_smallcaps("IV. Das transcrições integrais"), styles["h1"]))
    story.append(Paragraph(_texto_transcricoes_intro(), styles["corpo"]))

    for idx, audio in enumerate(audios, start=1):
        story.append(_subheading_audio(audio, idx, caso, styles, font_name))
        story.append(Spacer(1, 1 * mm))
        story.append(_caixa_identificacao_audio(audio, caso, font_name))
        story.append(Spacer(1, 2 * mm))
        story.append(_tabela_segmentos(audio, font_name))
        story.append(Spacer(1, 4 * mm))

    # ─── V — Encerramento ───────────────────────────────────────────────────
    story.append(Paragraph(_smallcaps("V. Encerramento"), styles["h1"]))

    n = len(audios)
    audios_pl = "do áudio" if n == 1 else f"dos {_num_extenso(n)} arquivos de áudio"
    resumos_pl = ("pelo respectivo resumo criptográfico SHA-256" if n == 1
                  else "pelos respectivos resumos criptográficos SHA-256")

    # Parágrafo 1: declaração principal — inline com bold-oxblood no fecho
    parte_a = _escape(
        f"O subscritor, na qualidade de patrono da {caso.posicao_cliente} e "
        f"profissional regularmente inscrito na Ordem dos Advogados do Brasil, "
        f"declara, sob as penas da lei, que: (i) as transcrições constantes do "
        f"item IV, supra, correspondem fielmente ao conteúdo sonoro {audios_pl} "
        f"identificados {resumos_pl}; (ii) tais transcrições foram produzidas "
        f"com a metodologia descrita no item II, supra, integralmente "
        f"reproduzível por qualquer parte ou perito; e (iii) prevalece, em "
        f"qualquer hipótese e para todos os fins probatórios, "
    )
    parte_destaque = (
        f'<font name="{font_name}-Bold" color="#5C1A14">'
        f'{_escape("o áudio original juntado aos autos")}</font>'
    )
    parte_b = _escape(
        ", como prova primária, ao qual se reporta este documento como "
        "instrumento auxiliar de leitura."
    )
    story.append(Paragraph(parte_a + parte_destaque + parte_b, styles["corpo"]))

    # Parágrafo 2: complemento sobre captura forense Verifact
    story.append(Paragraph(
        _escape(
            "Acrescenta o subscritor que toda a documentação digital aqui referida "
            "poderá, querendo a parte contrária ou determinando o e. Tribunal, ser "
            "submetida a captura técnica forense por plataforma especializada "
            "(Verifact ou equivalente), assegurada a integridade bit-a-bit do "
            "material."
        ),
        styles["corpo"],
    ))

    # ─── Anexo técnico ──────────────────────────────────────────────────────
    story.append(Paragraph(
        _smallcaps("Anexo técnico — parâmetros de execução"), styles["h2"],
    ))
    story.append(Paragraph(
        "Registram-se, para fins de reprodutibilidade da transcrição, "
        "os parâmetros adotados na execução da ferramenta:",
        styles["corpo"],
    ))
    for item in _lista_anexo_tecnico(audios, env):
        story.append(Paragraph(f"•&nbsp;&nbsp;{_escape(item)}", styles["lista_anexo"]))

    # ─── Assinatura ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    data_decl = caso.data_declaracao or _data_extenso(datetime.now())
    story.append(Paragraph(
        f'<i>{_escape(caso.local)}, {_escape(data_decl)}.</i>',
        styles["local_data"],
    ))

    story.append(KeepTogether(_bloco_assinatura(advogado, co_subscritor, styles, font_name)))

    doc.build(story)


# ─────────────────────────── Templates de texto ───────────────────────────

def _build_subtitulo(audios: Sequence[AudioEntry], caso: DadosCaso) -> str:
    """Subtítulo em itálico com remetente + datas dos áudios + caso."""
    partes = []

    if caso.remetente_nome:
        partes.append(f"Áudios remetidos via WhatsApp pelo {caso.remetente_nome}")
    else:
        partes.append("Áudios remetidos via WhatsApp")

    datas = [a.data_recebimento for a in audios if a.data_recebimento]
    if datas:
        # Pega datas únicas e formata
        datas_unicas = []
        for d in datas:
            d_curta = d.split("—")[0].strip() if "—" in d else d
            if d_curta not in datas_unicas:
                datas_unicas.append(d_curta)
        if len(datas_unicas) == 1:
            partes.append(f"em {datas_unicas[0]}")
        elif len(datas_unicas) == 2:
            partes.append(f"nos dias {datas_unicas[0]} e {datas_unicas[1]}")
        else:
            partes.append(f"nos dias {', '.join(datas_unicas[:-1])} e {datas_unicas[-1]}")

    caso_str = ""
    if caso.cliente and caso.contraparte:
        caso_str = f"Caso {caso.cliente} x {caso.contraparte}"
    if caso.processo:
        caso_str = (
            f"{caso_str} (autos n.º {caso.processo})"
            if caso_str
            else f"Autos n.º {caso.processo}"
        )

    texto = " ".join(partes).strip()
    if caso_str:
        texto = f"{texto} — {caso_str}"
    return _escape(texto)


def _texto_objeto(audios: Sequence[AudioEntry], caso: DadosCaso) -> str:
    n = len(audios)
    audios_str_2 = "do áudio remetido" if n == 1 else f"dos {_num_extenso(n)} áudios remetidos"

    remetente = caso.remetente_nome or "patrono da parte adversa"
    remetente_oab = f" ({caso.remetente_oab})" if caso.remetente_oab else ""

    datas = [a.data_recebimento for a in audios if a.data_recebimento]
    datas_curtas = []
    for d in datas:
        d_curta = d.split("—")[0].strip() if "—" in d else d
        if d_curta not in datas_curtas:
            datas_curtas.append(d_curta)
    datas_str = _join_datas(datas_curtas) if datas_curtas else "datas indicadas"

    return _escape(
        f"O subscritor, na qualidade de advogado constituído da {caso.posicao_cliente} "
        f"e por dever de transparência probatória, junta aos autos a transcrição "
        f"integral, com marcação temporal por segmento, {audios_str_2} via aplicativo "
        f"WhatsApp pelo patrono da {caso.posicao_contraparte}, {remetente}{remetente_oab}, "
        f"em {datas_str}, e esclarece a metodologia adotada para a sua produção."
    )


def _texto_metodologia(env: EnvironmentMetadata) -> list[str]:
    versao_whisper = env.faster_whisper_versao or "(versão indeterminada)"
    return [
        _escape(
            "A escolha do meio técnico, em hipóteses como a presente, deve recair "
            "sobre ferramenta que assegure, ao mesmo tempo, fidelidade ao conteúdo "
            "sonoro, reprodutibilidade por terceiros e verificabilidade independente. "
            "Por essa razão, o subscritor optou pela utilização de programa de "
            "computador livre, de código aberto e publicamente auditável, cujo "
            "funcionamento pode ser reproduzido por qualquer pessoa — parte adversa, "
            "perito, magistrado ou colaborador do juízo — em máquina pessoal, sem "
            "custos, e com resultado idêntico."
        ),
        _escape(
            f"Especificamente, foi utilizada a ferramenta faster-whisper (versão "
            f"{versao_whisper}) — implementação do modelo Whisper, originalmente "
            f"desenvolvido pela OpenAI e disponibilizado sob licença permissiva (MIT). "
            f"A ferramenta é mantida em repositório público, com código-fonte "
            f"integralmente acessível, e seu modelo \"large-v3\" — utilizado nesta "
            f"transcrição — foi treinado em vasto corpus de áudio multilíngue, sendo "
            f"amplamente empregado em produção em escala industrial e referência "
            f"atual em conversão de voz em texto."
        ),
        _escape(
            "Para assegurar a reprodutibilidade da transcrição, foram adotados "
            "parâmetros de execução determinísticos, descritos em Anexo Técnico ao "
            "final deste documento. Qualquer parte ou perito, executando a mesma "
            "ferramenta sobre o mesmo arquivo sonoro com os mesmos parâmetros, "
            "obterá resultado equivalente."
        ),
    ]


def _texto_transcricoes_intro() -> str:
    return _escape(
        "Seguem-se, em sequência cronológica, as transcrições integrais dos "
        "áudios, organizadas por segmentos com marcação temporal. Cada segmento "
        "corresponde a uma unidade fonética identificada pela ferramenta na "
        "detecção de atividade vocal. Os segmentos podem ser conferidos "
        "diretamente pela escuta do áudio nativo correspondente, identificado "
        "pelo respectivo SHA-256 acima."
    )


def _subheading_audio(audio: AudioEntry, idx: int, caso: DadosCaso, styles: dict, font_name: str) -> Paragraph:
    if audio.data_recebimento:
        titulo = f"Áudio {idx} — {audio.data_recebimento}"
    else:
        titulo = f"Áudio {idx} — {audio.metadata.arquivo}"
    return Paragraph(_escape(titulo), styles["h2"])


def _caixa_identificacao_audio(audio: AudioEntry, caso: DadosCaso, font_name: str) -> Table:
    """Caixa antes da tabela de segmentos: Arquivo + SHA + Remetente + Destinatário."""
    duracao = (f" (duração: {audio.metadata.duracao_segundos:.2f} s)"
               if audio.metadata.duracao_segundos else "")
    rows = [
        [_kv("Arquivo", f"{audio.metadata.arquivo}{duracao}", "Ubuntu")],
        [_kv_mono("SHA-256", audio.metadata.sha256, "Ubuntu")],
    ]
    if caso.remetente_nome:
        rem = caso.remetente_nome
        if caso.remetente_oab:
            rem = f"{rem} ({caso.posicao_contraparte}, {caso.remetente_oab})"
        rows.append([_kv("Remetente", rem, "Ubuntu")])
    rows.append([_kv("Destinatário",
                     f"{caso.posicao_cliente or 'Subscritor'} — patrono da {caso.posicao_cliente or 'parte representada'}",
                     "Ubuntu")])

    t = Table(rows, colWidths=[PAGE_W - 4 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PERGAMINHO),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, -1), (0, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _lista_anexo_tecnico(audios: Sequence[AudioEntry], env: EnvironmentMetadata) -> list[str]:
    if not audios:
        return []
    primeiro = audios[0]
    r = primeiro.transcription
    return [
        f"ferramenta: faster-whisper (versão {env.faster_whisper_versao or '—'})",
        "repositório público: github.com/SYSTRAN/faster-whisper",
        "licença: MIT",
        f"modelo: {r.modelo}",
        f"idioma: {r.idioma_detectado} (português)" if r.idioma_detectado == "pt" else f"idioma: {r.idioma_detectado}",
        "beam_size: 10",
        "temperature: 0.0 (decodificação determinística)",
        "vad_filter: True (filtragem por detecção de atividade vocal)",
        "word_timestamps: True (marcação temporal em nível de palavra)",
        "condition_on_previous_text: True",
        f"device: {r.device}",
        f"compute_type: {r.compute_type}",
    ]


def _bloco_assinatura(advogado: AdvogadoConfig, co: Optional[CoSubscritor],
                      styles: dict, font_name: str) -> list:
    if co:
        # 2 colunas
        col1 = [
            Paragraph(_escape(advogado.nome), styles["encerramento_nome"]),
            Paragraph(_escape(advogado.oab), styles["encerramento_oab"]),
            Paragraph("[assinado eletronicamente]", styles["encerramento_assinatura"]),
        ]
        col2 = [
            Paragraph(_escape(co.nome), styles["encerramento_nome"]),
            Paragraph(_escape(co.oab), styles["encerramento_oab"]),
            Paragraph("[assinado eletronicamente]", styles["encerramento_assinatura"]),
        ]
        t = Table([[col1, col2]], colWidths=[(PAGE_W - 4 * cm) / 2] * 2)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return [t]
    else:
        return [
            Paragraph(_escape(advogado.nome), styles["encerramento_nome"]),
            Paragraph(_escape(advogado.oab), styles["encerramento_oab"]),
            Paragraph("[assinado eletronicamente]", styles["encerramento_assinatura"]),
        ]


def _num_extenso(n: int) -> str:
    return {1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco",
            6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez"}.get(n, str(n))


def _join_datas(datas: list[str]) -> str:
    if not datas:
        return ""
    if len(datas) == 1:
        return datas[0]
    if len(datas) == 2:
        return f"{datas[0]} e {datas[1]}"
    return f"{', '.join(datas[:-1])} e {datas[-1]}"


# ─────────────────────────── API pública ───────────────────────────

def build_pdf(
    output_path: Path,
    audio: AudioMetadata,
    env: EnvironmentMetadata,
    result: TranscriptionResult,
    identidade: IdentidadeVisualConfig,
    advogado: AdvogadoConfig,
    objeto_texto: Optional[str] = None,  # kept for backwards compat (ignored)
) -> None:
    """API antiga (1 áudio). Gera no modo simples."""
    font_name = _register_font(identidade.fonte_corpo)
    styles = _make_styles(font_name)
    entry = AudioEntry(metadata=audio, transcription=result)
    _build_simple(output_path, entry, env, identidade, advogado, font_name, styles)
    log.info("PDF gerado: %s", output_path)


def build_pdf_formal(
    output_path: Path,
    audios: Sequence[AudioEntry],
    env: EnvironmentMetadata,
    identidade: IdentidadeVisualConfig,
    advogado: AdvogadoConfig,
    caso: DadosCaso,
    co_subscritor: Optional[CoSubscritor] = None,
) -> None:
    """API formal — múltiplos áudios + dados de caso → declaração técnica."""
    if not audios:
        raise ValueError("Lista de áudios vazia")
    if not caso.modo_formal:
        raise ValueError("Modo formal requer pelo menos --processo")
    font_name = _register_font(identidade.fonte_corpo)
    styles = _make_styles(font_name)
    _build_formal(output_path, audios, env, identidade, advogado, caso,
                  co_subscritor, font_name, styles)
    log.info("PDF formal gerado: %s", output_path)
