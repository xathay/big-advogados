"""Cadeia de custódia — SHA-256, metadados do áudio e do ambiente.

A cadeia de custódia é o coração da validade probatória da transcrição.
Cada metadado aqui registrado deve permitir verificação independente
por perito ou parte adversa.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import platform
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AudioMetadata:
    """Metadados verificáveis de um arquivo de áudio antes da transcrição."""

    arquivo: str
    """Nome do arquivo (basename, sem path)."""

    caminho_absoluto: str
    """Path absoluto no momento do processamento."""

    tamanho_bytes: int

    sha256: str
    """SHA-256 em hex (64 chars)."""

    duracao_segundos: Optional[float]
    """Duração via ffprobe; None se ffprobe não disponível."""

    formato: Optional[str]
    """Formato detectado por ffprobe (m4a, opus, mp3, etc.)."""


@dataclass(frozen=True)
class EnvironmentMetadata:
    """Metadados do ambiente onde a transcrição rodou."""

    data_iso: str
    """Data/hora ISO 8601 com timezone."""

    hostname: str

    sistema_operacional: str
    """uname -a equivalente: 'Linux 7.0.9-1-cachyos x86_64'."""

    python_versao: str

    faster_whisper_versao: Optional[str]
    """Versão da lib faster-whisper instalada; None se indeterminada."""


# Lê em blocos de 1MB — equilibrio entre throughput de I/O e uso de RAM.
_HASH_CHUNK = 1024 * 1024


def compute_sha256(path: Path) -> str:
    """Calcula SHA-256 do arquivo, lendo em chunks de 1MB."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def probe_audio(path: Path) -> tuple[Optional[float], Optional[str]]:
    """Extrai duração e formato via ffprobe. Retorna (None, None) se indisponível."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration,format_name",
                "-of", "default=noprint_wrappers=1:nokey=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, None

    if result.returncode != 0:
        return None, None

    duracao: Optional[float] = None
    formato: Optional[str] = None
    for line in result.stdout.splitlines():
        if line.startswith("duration="):
            try:
                duracao = float(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("format_name="):
            formato = line.split("=", 1)[1].strip() or None
    return duracao, formato


def compute_metadata(path: Path) -> AudioMetadata:
    """Calcula SHA-256 + dados verificáveis do arquivo de áudio."""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Áudio não encontrado: {path}")

    sha = compute_sha256(path)
    duracao, formato = probe_audio(path)

    return AudioMetadata(
        arquivo=path.name,
        caminho_absoluto=str(path),
        tamanho_bytes=path.stat().st_size,
        sha256=sha,
        duracao_segundos=duracao,
        formato=formato,
    )


def get_environment_metadata() -> EnvironmentMetadata:
    """Coleta dados do ambiente que devem aparecer no relatório de transcrição."""
    try:
        whisper_versao = importlib.metadata.version("faster-whisper")
    except importlib.metadata.PackageNotFoundError:
        whisper_versao = None

    uname = platform.uname()
    so = f"{uname.system} {uname.release} {uname.machine}".strip()

    return EnvironmentMetadata(
        data_iso=dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        hostname=platform.node() or "desconhecido",
        sistema_operacional=so,
        python_versao=platform.python_version(),
        faster_whisper_versao=whisper_versao,
    )


def to_dict(audio: AudioMetadata, env: EnvironmentMetadata) -> dict:
    """Empacota tudo num dict serializável (para JSON ou logs)."""
    return {
        "audio": asdict(audio),
        "ambiente": asdict(env),
    }
