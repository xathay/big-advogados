"""Orquestrador de transcrição para o TUI — modo simples (1 PDF por áudio).

Reusa exatamente o pipeline de `src.transcritor` (mesmos metadados, mesma
engine determinística, mesmos writers/PDF) que a CLI `big-advogados
transcrever`. A diferença é só o reporte de progresso via callbacks, para
alimentar a ProgressBar do Textual.

Roda em worker thread (faster-whisper é bloqueante); os callbacks devem
ser marshalled para o thread da UI por quem chama (App.call_from_thread).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from src.transcritor import config as cfg_module
from src.transcritor.engine import transcribe
from src.transcritor.metadata import compute_metadata, get_environment_metadata
from src.transcritor.writers import (
    write_markdown,
    write_metadata_json,
    write_segments_csv,
    write_txt,
)

SAIDAS_VALIDAS = {"txt", "md", "pdf", "json", "csv"}

ProgressCb = Callable[[float], None]   # fração 0.0–1.0
LogCb = Callable[[str], None]


@dataclass(frozen=True)
class SaidaGerada:
    formato: str
    path: Path


@dataclass
class ResultadoTranscricao:
    arquivo: Path
    sha256: str
    duracao_segundos: Optional[float]
    n_segmentos: int
    idioma: str
    saidas: list[SaidaGerada] = field(default_factory=list)


def transcrever_arquivo(
    arquivo: Path,
    cfg: cfg_module.TranscritorConfig,
    saidas: set[str],
    on_progress: Optional[ProgressCb] = None,
    on_log: Optional[LogCb] = None,
) -> ResultadoTranscricao:
    """Transcreve um áudio e gera as saídas pedidas. Bloqueante."""

    def _log(msg: str) -> None:
        if on_log:
            on_log(msg)

    saidas = {s for s in saidas if s in SAIDAS_VALIDAS} or {"pdf"}

    _log(f"Calculando SHA-256 de {arquivo.name}…")
    audio = compute_metadata(arquivo)
    _log(f"SHA-256: {audio.sha256}")
    env = get_environment_metadata()

    total = audio.duracao_segundos or 0.0

    def _progress(current_seconds: float, total_seconds: float) -> None:
        if on_progress and total_seconds > 0:
            on_progress(min(current_seconds / total_seconds, 1.0))

    _log("Transcrevendo (faster-whisper, local)…")
    result = transcribe(arquivo, cfg, progress_callback=_progress)
    if on_progress:
        on_progress(1.0)
    _log(
        f"Concluído: {len(result.segments)} segmentos, "
        f"idioma {result.idioma_detectado} (prob {result.probabilidade_idioma:.2f})"
    )

    base = arquivo.with_suffix("")
    geradas: list[SaidaGerada] = []

    if "txt" in saidas:
        out = base.parent / f"{base.name}.transcricao.txt"
        write_txt(out, result)
        geradas.append(SaidaGerada("txt", out))
    if "md" in saidas:
        out = base.parent / f"{base.name}.transcricao.md"
        write_markdown(out, audio, env, result)
        geradas.append(SaidaGerada("md", out))
    if "pdf" in saidas:
        # Import lazy: reportlab só é exigido quando o PDF é realmente gerado,
        # para o app carregar mesmo sem a dependência instalada.
        from src.transcritor.pdf_builder import build_pdf

        out = base.parent / f"{base.name}.transcricao.pdf"
        build_pdf(out, audio, env, result, cfg.identidade_visual, cfg.advogado)
        geradas.append(SaidaGerada("pdf", out))
    if "json" in saidas:
        out = base.parent / f"{base.name}.metadata.json"
        write_metadata_json(out, audio, env, result)
        geradas.append(SaidaGerada("json", out))
    if "csv" in saidas:
        out = base.parent / f"{base.name}.segments.csv"
        write_segments_csv(out, result)
        geradas.append(SaidaGerada("csv", out))

    for s in geradas:
        _log(f"Escrito: {s.path.name}")

    return ResultadoTranscricao(
        arquivo=arquivo,
        sha256=audio.sha256,
        duracao_segundos=audio.duracao_segundos,
        n_segmentos=len(result.segments),
        idioma=result.idioma_detectado,
        saidas=geradas,
    )
