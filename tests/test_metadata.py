"""Testes da cadeia de custódia."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.transcritor.metadata import (
    compute_metadata,
    compute_sha256,
    get_environment_metadata,
    to_dict,
)


def test_sha256_eh_deterministico(tmp_audio: Path) -> None:
    """Duas chamadas no mesmo arquivo devem dar o mesmo hash."""
    h1 = compute_sha256(tmp_audio)
    h2 = compute_sha256(tmp_audio)
    assert h1 == h2
    assert len(h1) == 64
    # Confirma que bate com hashlib direto
    expected = hashlib.sha256(tmp_audio.read_bytes()).hexdigest()
    assert h1 == expected


def test_sha256_muda_quando_arquivo_muda(tmp_audio: Path) -> None:
    h_antes = compute_sha256(tmp_audio)
    tmp_audio.write_bytes(tmp_audio.read_bytes() + b"X")
    h_depois = compute_sha256(tmp_audio)
    assert h_antes != h_depois


def test_compute_metadata_preenche_campos_basicos(tmp_audio: Path) -> None:
    meta = compute_metadata(tmp_audio)
    assert meta.arquivo == tmp_audio.name
    assert meta.tamanho_bytes == tmp_audio.stat().st_size
    assert len(meta.sha256) == 64
    assert meta.caminho_absoluto == str(tmp_audio.resolve())


def test_compute_metadata_falha_se_arquivo_nao_existe(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_metadata(tmp_path / "nao-existe.m4a")


def test_environment_metadata_tem_campos_obrigatorios() -> None:
    env = get_environment_metadata()
    assert env.hostname
    assert env.sistema_operacional
    assert env.python_versao
    assert "T" in env.data_iso  # ISO 8601


def test_to_dict_eh_serializavel_json(fake_audio_meta, fake_env_meta) -> None:
    import json

    d = to_dict(fake_audio_meta, fake_env_meta)
    json.dumps(d)  # não deve levantar
    assert d["audio"]["sha256"] == "0" * 64
    assert d["ambiente"]["hostname"] == "arch-test"
