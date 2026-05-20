"""Saídas auxiliares: TXT, Markdown, JSON e CSV.

Cada writer recebe os dataclasses já calculados pelo pipeline e gera
o arquivo correspondente. PDF tem módulo próprio (pdf_builder.py).
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from src.transcritor.engine import TranscriptionResult
from src.transcritor.metadata import AudioMetadata, EnvironmentMetadata


def write_txt(path: Path, result: TranscriptionResult) -> None:
    """Transcrição plana com timestamps no início de cada linha."""
    lines = []
    for seg in result.segments:
        texto = seg.text.strip()
        if not texto:
            continue
        lines.append(f"[{seg.start_timestamp} → {seg.end_timestamp}] {texto}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_markdown(
    path: Path,
    audio: AudioMetadata,
    env: EnvironmentMetadata,
    result: TranscriptionResult,
) -> None:
    """Markdown com cabeçalho de metadados + transcrição por segmentos."""
    duracao_fmt = (
        f"{audio.duracao_segundos:.2f}s" if audio.duracao_segundos is not None else "—"
    )
    sha_quebrado = " ".join(audio.sha256[i : i + 16] for i in range(0, 64, 16))

    out = [
        f"# Transcrição — {audio.arquivo}",
        "",
        "## Cadeia de custódia",
        "",
        f"| Campo | Valor |",
        f"|---|---|",
        f"| Arquivo | `{audio.arquivo}` |",
        f"| Tamanho | {audio.tamanho_bytes} bytes |",
        f"| Formato | {audio.formato or '—'} |",
        f"| Duração | {duracao_fmt} |",
        f"| SHA-256 | `{sha_quebrado}` |",
        f"| Caminho absoluto | `{audio.caminho_absoluto}` |",
        f"| Transcrito em | {env.data_iso} |",
        f"| Hostname | {env.hostname} |",
        f"| Sistema | {env.sistema_operacional} |",
        f"| Python | {env.python_versao} |",
        f"| faster-whisper | {env.faster_whisper_versao or 'indeterminada'} |",
        "",
        "## Parâmetros de transcrição",
        "",
        f"| Campo | Valor |",
        f"|---|---|",
        f"| Modelo | {result.modelo} |",
        f"| Device | {result.device} |",
        f"| Compute type | {result.compute_type} |",
        f"| Idioma detectado | {result.idioma_detectado} (probabilidade {result.probabilidade_idioma:.3f}) |",
        "",
        "## Cláusula de prevalência",
        "",
        "> Em caso de divergência entre esta transcrição e o áudio original, "
        "prevalece integralmente o áudio gravado, juntado em sua integridade nativa.",
        "",
        "## Transcrição",
        "",
    ]

    for seg in result.segments:
        texto = seg.text.strip()
        if not texto:
            continue
        out.append(f"**[{seg.start_timestamp} → {seg.end_timestamp}]** {texto}")
        out.append("")

    path.write_text("\n".join(out), encoding="utf-8")


def write_metadata_json(
    path: Path,
    audio: AudioMetadata,
    env: EnvironmentMetadata,
    result: TranscriptionResult,
) -> None:
    """JSON estruturado com tudo — útil para integração com outras ferramentas."""
    data = {
        "audio": asdict(audio),
        "ambiente": asdict(env),
        "parametros": {
            "modelo": result.modelo,
            "device": result.device,
            "compute_type": result.compute_type,
            "idioma_detectado": result.idioma_detectado,
            "probabilidade_idioma": result.probabilidade_idioma,
        },
        "segmentos": [
            {
                "start": seg.start,
                "end": seg.end,
                "start_timestamp": seg.start_timestamp,
                "end_timestamp": seg.end_timestamp,
                "text": seg.text,
            }
            for seg in result.segments
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_segments_csv(path: Path, result: TranscriptionResult) -> None:
    """CSV com 4 colunas: start_seconds, end_seconds, timestamp_range, text."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["start_seconds", "end_seconds", "timestamp_range", "text"])
        for seg in result.segments:
            writer.writerow([
                f"{seg.start:.3f}",
                f"{seg.end:.3f}",
                f"{seg.start_timestamp} → {seg.end_timestamp}",
                seg.text.strip(),
            ])
