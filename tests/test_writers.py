"""Testes dos writers TXT, MD, JSON, CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.transcritor.writers import (
    write_markdown,
    write_metadata_json,
    write_segments_csv,
    write_txt,
)


def test_txt_inclui_todos_segmentos(tmp_path: Path, fake_result) -> None:
    out = tmp_path / "saida.txt"
    write_txt(out, fake_result)
    content = out.read_text()
    assert "Bom dia, doutor." in content
    assert "00:00:00,000" in content
    assert "00:00:09,800" in content
    # 3 segmentos → 3 linhas
    assert len([l for l in content.splitlines() if l.strip()]) == 3


def test_markdown_tem_secoes_obrigatorias(tmp_path: Path, fake_audio_meta, fake_env_meta, fake_result) -> None:
    out = tmp_path / "saida.md"
    write_markdown(out, fake_audio_meta, fake_env_meta, fake_result)
    md = out.read_text()
    assert "# Transcrição —" in md
    assert "## Cadeia de custódia" in md
    assert "## Parâmetros de transcrição" in md
    assert "## Cláusula de prevalência" in md
    assert "## Transcrição" in md
    assert "SHA-256" in md
    assert "Bom dia, doutor." in md


def test_markdown_cita_versao_whisper(tmp_path: Path, fake_audio_meta, fake_env_meta, fake_result) -> None:
    out = tmp_path / "saida.md"
    write_markdown(out, fake_audio_meta, fake_env_meta, fake_result)
    md = out.read_text()
    assert "1.0.3" in md  # versão fictícia do conftest


def test_json_eh_valido_e_estruturado(tmp_path: Path, fake_audio_meta, fake_env_meta, fake_result) -> None:
    out = tmp_path / "saida.json"
    write_metadata_json(out, fake_audio_meta, fake_env_meta, fake_result)
    data = json.loads(out.read_text())
    assert "audio" in data
    assert "ambiente" in data
    assert "parametros" in data
    assert "segmentos" in data
    assert len(data["segmentos"]) == 3
    assert data["audio"]["sha256"] == "0" * 64
    assert data["segmentos"][0]["text"] == "Bom dia, doutor."


def test_csv_tem_header_e_linhas(tmp_path: Path, fake_result) -> None:
    out = tmp_path / "saida.csv"
    write_segments_csv(out, fake_result)
    with out.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["start_seconds", "end_seconds", "timestamp_range", "text"]
    assert len(rows) == 4  # header + 3 segmentos
    assert rows[1][3] == "Bom dia, doutor."


def test_txt_vazio_quando_sem_segmentos(tmp_path: Path) -> None:
    from src.transcritor.engine import TranscriptionResult

    r = TranscriptionResult(
        segments=(),
        idioma_detectado="pt",
        probabilidade_idioma=0.0,
        modelo="tiny",
        device="cpu",
        compute_type="int8",
    )
    out = tmp_path / "vazio.txt"
    write_txt(out, r)
    assert out.read_text() == ""
