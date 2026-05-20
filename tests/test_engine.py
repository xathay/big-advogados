"""Testes do engine (sem dep do faster-whisper real)."""

from __future__ import annotations

from src.transcritor.engine import Segment, _format_timestamp


def test_format_timestamp_zero() -> None:
    assert _format_timestamp(0.0) == "00:00:00,000"


def test_format_timestamp_segundos_inteiros() -> None:
    assert _format_timestamp(5.0) == "00:00:05,000"


def test_format_timestamp_milisegundos() -> None:
    assert _format_timestamp(1.234) == "00:00:01,234"


def test_format_timestamp_uma_hora_dez_minutos() -> None:
    assert _format_timestamp(3600 + 600 + 30.5) == "01:10:30,500"


def test_format_timestamp_negativo_clipa_zero() -> None:
    assert _format_timestamp(-1.5) == "00:00:00,000"


def test_segment_timestamps_seguem_srt() -> None:
    seg = Segment(start=1.5, end=4.25, text="teste")
    assert seg.start_timestamp == "00:00:01,500"
    assert seg.end_timestamp == "00:00:04,250"


def test_transcription_result_texto_completo(fake_result) -> None:
    texto = fake_result.texto_completo
    assert "Bom dia, doutor." in texto
    assert "Por favor, retorne quando puder." in texto


def test_transcription_result_duracao_falada(fake_result) -> None:
    assert fake_result.duracao_falada == 9.8


def test_transcription_result_segmentos_vazios_duracao_zero() -> None:
    from src.transcritor.engine import TranscriptionResult

    r = TranscriptionResult(
        segments=(),
        idioma_detectado="pt",
        probabilidade_idioma=0.0,
        modelo="tiny",
        device="cpu",
        compute_type="int8",
    )
    assert r.duracao_falada == 0.0
    assert r.texto_completo == ""
