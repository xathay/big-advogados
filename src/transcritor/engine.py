"""Wrapper sobre faster-whisper.

Encapsula a lib de modo que o resto do código não importe faster_whisper
diretamente — facilita testes (mocking) e troca futura de backend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.transcritor.config import TranscritorConfig

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Segment:
    """Um trecho contínuo de fala com tempo de início e fim em segundos."""

    start: float
    end: float
    text: str

    @property
    def start_timestamp(self) -> str:
        """Timestamp formatado HH:MM:SS,mmm — convenção SRT."""
        return _format_timestamp(self.start)

    @property
    def end_timestamp(self) -> str:
        return _format_timestamp(self.end)


@dataclass(frozen=True)
class TranscriptionResult:
    """Resultado completo da transcrição de um arquivo."""

    segments: tuple[Segment, ...]
    idioma_detectado: str
    """Código de idioma ISO 639-1 (ex.: 'pt')."""

    probabilidade_idioma: float
    """0.0–1.0 — confiança do Whisper sobre o idioma."""

    modelo: str
    """Nome do modelo usado (large-v3, medium, etc.)."""

    device: str
    """'cpu' ou 'cuda' efetivamente usado."""

    compute_type: str

    @property
    def texto_completo(self) -> str:
        """Junta todos os segmentos em um único bloco de texto."""
        return "\n".join(s.text.strip() for s in self.segments if s.text.strip())

    @property
    def duracao_falada(self) -> float:
        """Duração total falada (último end timestamp)."""
        return self.segments[-1].end if self.segments else 0.0


def _format_timestamp(seconds: float) -> str:
    """Converte segundos float em HH:MM:SS,mmm (formato SRT)."""
    if seconds < 0:
        seconds = 0
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _resolve_device_and_compute(cfg: TranscritorConfig) -> tuple[str, str]:
    """Auto-detecta CUDA quando device='auto'.

    Cai para CPU+int8 se CUDA não estiver disponível ou faster-whisper
    falhar ao inicializar uma GPU.
    """
    requested = cfg.modelo.device
    compute = cfg.modelo.compute_type

    if requested == "cuda":
        return "cuda", compute if compute != "default" else "float16"

    if requested == "cpu":
        return "cpu", compute if compute != "default" else "int8"

    # auto: testa CUDA
    try:
        import ctranslate2  # type: ignore

        if ctranslate2.get_cuda_device_count() > 0:
            log.info("CUDA detectado — usando GPU")
            return "cuda", compute if compute != "default" else "float16"
    except Exception as exc:
        log.debug("CUDA probe falhou: %s", exc)

    log.info("Usando CPU (sem CUDA)")
    return "cpu", compute if compute != "default" else "int8"


def transcribe(
    audio_path: Path,
    cfg: TranscritorConfig,
    progress_callback: Optional[callable] = None,
) -> TranscriptionResult:
    """Roda faster-whisper no áudio e retorna resultado tipado.

    O `progress_callback`, se fornecido, recebe (segmento_atual, total_estimado_segundos)
    a cada segmento. Útil pra UI; pode ser ignorado em modo CLI silencioso.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper não está instalado. Instale com: "
            "pip install faster-whisper"
        ) from exc

    device, compute_type = _resolve_device_and_compute(cfg)
    log.info(
        "Carregando modelo %s (device=%s, compute_type=%s)",
        cfg.modelo.nome, device, compute_type,
    )

    model = WhisperModel(
        cfg.modelo.nome,
        device=device,
        compute_type=compute_type,
    )

    log.info("Transcrevendo %s", audio_path)
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=cfg.transcricao.idioma,
        beam_size=cfg.transcricao.beam_size,
        temperature=cfg.transcricao.temperature,
        vad_filter=cfg.transcricao.vad_filter,
        word_timestamps=cfg.transcricao.word_timestamps,
        condition_on_previous_text=cfg.transcricao.condition_on_previous_text,
    )

    segments: list[Segment] = []
    total_duration = getattr(info, "duration", None)
    for seg in segments_iter:
        segments.append(Segment(
            start=float(seg.start),
            end=float(seg.end),
            text=seg.text,
        ))
        if progress_callback and total_duration:
            try:
                progress_callback(float(seg.end), float(total_duration))
            except Exception as exc:  # noqa: BLE001
                log.debug("progress_callback raised: %s", exc)

    return TranscriptionResult(
        segments=tuple(segments),
        idioma_detectado=getattr(info, "language", cfg.transcricao.idioma),
        probabilidade_idioma=float(getattr(info, "language_probability", 0.0)),
        modelo=cfg.modelo.nome,
        device=device,
        compute_type=compute_type,
    )
