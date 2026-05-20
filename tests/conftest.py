"""Configuração comum dos testes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Garante que `from src.X` funciona quando pytest roda da raiz do repo
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from src.transcritor.config import (
    AdvogadoConfig,
    IdentidadeVisualConfig,
    ModeloConfig,
    TranscricaoConfig,
    TranscritorConfig,
)
from src.transcritor.engine import Segment, TranscriptionResult
from src.transcritor.metadata import AudioMetadata, EnvironmentMetadata


@pytest.fixture
def tmp_audio(tmp_path: Path) -> Path:
    """Áudio falso (~1KB de bytes deterministicos) para testes de SHA-256/metadata."""
    path = tmp_path / "exemplo.m4a"
    path.write_bytes(b"AUDIO_FAKE_PARA_TESTE_DE_SHA256\n" * 32)
    return path


@pytest.fixture
def cfg_minima(tmp_path: Path) -> TranscritorConfig:
    return TranscritorConfig(
        modelo=ModeloConfig(nome="tiny", device="cpu", compute_type="int8"),
        transcricao=TranscricaoConfig(idioma="pt"),
        identidade_visual=IdentidadeVisualConfig(
            logo=tmp_path / "logo_inexistente.png",
            footer_bar=tmp_path / "footer_inexistente.png",
            fonte_corpo="Helvetica",
        ),
        advogado=AdvogadoConfig(
            nome="Advogado Exemplo",
            oab="OAB/BA 00.000",
            escritorio="Escritório de Advocacia Exemplo",
        ),
    )


@pytest.fixture
def fake_result() -> TranscriptionResult:
    """Resultado de transcrição fictício com 3 segmentos."""
    return TranscriptionResult(
        segments=(
            Segment(start=0.0, end=2.5, text="Bom dia, doutor."),
            Segment(start=2.6, end=6.1, text="Estou enviando o áudio para conferência."),
            Segment(start=6.2, end=9.8, text="Por favor, retorne quando puder."),
        ),
        idioma_detectado="pt",
        probabilidade_idioma=0.987,
        modelo="tiny",
        device="cpu",
        compute_type="int8",
    )


@pytest.fixture
def fake_audio_meta(tmp_audio: Path) -> AudioMetadata:
    return AudioMetadata(
        arquivo=tmp_audio.name,
        caminho_absoluto=str(tmp_audio),
        tamanho_bytes=tmp_audio.stat().st_size,
        sha256="0" * 64,
        duracao_segundos=9.8,
        formato="m4a",
    )


@pytest.fixture
def fake_env_meta() -> EnvironmentMetadata:
    return EnvironmentMetadata(
        data_iso="2026-05-20T20:30:00-03:00",
        hostname="arch-test",
        sistema_operacional="Linux 7.0.9 x86_64",
        python_versao="3.11.0",
        faster_whisper_versao="1.0.3",
    )
