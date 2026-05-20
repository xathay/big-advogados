"""Transcritor de áudio com cadeia de custódia.

Transcrição forense de áudios (M4A/OPUS/MP3/OGG/WAV/FLAC) com:
- SHA-256 do arquivo original antes de qualquer processamento
- Metadados verificáveis (modelo, parâmetros, ambiente, data ISO 8601)
- Três saídas (txt, md, pdf) + JSON/CSV opcionais
- PDF com identidade visual do escritório + declaração formal

Pipeline 100% local via faster-whisper. Nenhum áudio sai da máquina.
"""

from src.transcritor.config import TranscritorConfig, load_config
from src.transcritor.metadata import AudioMetadata, compute_metadata
from src.transcritor.engine import TranscriptionResult, Segment, transcribe

__all__ = [
    "TranscritorConfig",
    "load_config",
    "AudioMetadata",
    "compute_metadata",
    "TranscriptionResult",
    "Segment",
    "transcribe",
]
