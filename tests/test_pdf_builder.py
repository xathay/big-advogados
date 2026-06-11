"""Testes do gerador de PDF (sem precisar de fontes do escritório)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.transcritor.pdf_builder import build_pdf


def test_pdf_eh_gerado_e_nao_vazio(
    tmp_path: Path, cfg_minima, fake_audio_meta, fake_env_meta, fake_result,
) -> None:
    out = tmp_path / "transcricao.pdf"
    build_pdf(
        out,
        fake_audio_meta,
        fake_env_meta,
        fake_result,
        cfg_minima.identidade_visual,
        cfg_minima.advogado,
    )
    assert out.is_file()
    assert out.stat().st_size > 2000  # PDF de capa+conteúdo deve ter alguns KB
    # Verifica que é um PDF válido pelo magic bytes
    with out.open("rb") as f:
        assert f.read(4) == b"%PDF"


def test_pdf_funciona_sem_logo_nem_footer(
    tmp_path: Path, cfg_minima, fake_audio_meta, fake_env_meta, fake_result,
) -> None:
    """Logo/footer ausentes não devem fazer o PDF falhar — apenas suprime-os."""
    out = tmp_path / "sem_imagens.pdf"
    build_pdf(
        out,
        fake_audio_meta,
        fake_env_meta,
        fake_result,
        cfg_minima.identidade_visual,
        cfg_minima.advogado,
    )
    assert out.is_file()


def test_pdf_funciona_sem_advogado_preenchido(
    tmp_path: Path, cfg_minima, fake_audio_meta, fake_env_meta, fake_result,
) -> None:
    from src.transcritor.config import AdvogadoConfig

    out = tmp_path / "sem_advogado.pdf"
    build_pdf(
        out,
        fake_audio_meta,
        fake_env_meta,
        fake_result,
        cfg_minima.identidade_visual,
        AdvogadoConfig(),  # tudo vazio
    )
    assert out.is_file()


@pytest.mark.skipif(
    shutil.which("pdftotext") is None,
    reason="pdftotext (poppler-utils) não instalado",
)
def test_pdf_contem_textos_obrigatorios(
    tmp_path: Path, cfg_minima, fake_audio_meta, fake_env_meta, fake_result,
) -> None:
    """Valida com pdftotext que o conteúdo essencial chegou ao PDF."""
    out = tmp_path / "validar.pdf"
    build_pdf(
        out,
        fake_audio_meta,
        fake_env_meta,
        fake_result,
        cfg_minima.identidade_visual,
        cfg_minima.advogado,
    )

    result = subprocess.run(
        ["pdftotext", "-layout", str(out), "-"],
        capture_output=True, text=True, check=True,
    )
    texto = result.stdout

    # build_pdf (API antiga) gera o modo simples. Normaliza whitespace —
    # pdftotext quebra linhas no meio das frases.
    texto = " ".join(texto.split())
    assert "Transcrição de áudio" in texto
    assert "SHA-256" in texto
    assert "Bom dia, doutor." in texto
    assert "prevalece integralmente o áudio gravado" in texto


@pytest.mark.skipif(
    shutil.which("pdftotext") is None,
    reason="pdftotext (poppler-utils) não instalado",
)
def test_pdf_formal_contem_textos_obrigatorios(
    tmp_path: Path, cfg_minima, fake_audio_meta, fake_env_meta, fake_result,
) -> None:
    """Modo formal (declaração técnica) — dados de caso 100% fictícios."""
    from src.transcritor.pdf_builder import AudioEntry, DadosCaso, build_pdf_formal

    out = tmp_path / "formal.pdf"
    build_pdf_formal(
        out,
        [AudioEntry(metadata=fake_audio_meta, transcription=fake_result)],
        fake_env_meta,
        cfg_minima.identidade_visual,
        cfg_minima.advogado,
        DadosCaso(
            processo="0000000-00.0000.0.00.0000",
            cliente="Parte Exemplo",
            contraparte="Empresa Exemplo Ltda",
        ),
    )

    result = subprocess.run(
        ["pdftotext", "-layout", str(out), "-"],
        capture_output=True, text=True, check=True,
    )
    texto = " ".join(result.stdout.split())

    assert "DECLARAÇÃO TÉCNICA E TRANSCRIÇÕES INTEGRAIS" in texto
    assert "0000000-00.0000.0.00.0000" in texto
    assert "Parte Exemplo" in texto
    assert "Empresa Exemplo Ltda" in texto
    assert "Bom dia, doutor." in texto
    assert cfg_minima.advogado.nome in texto
    assert cfg_minima.advogado.oab in texto
    # Saída restrita ao dono — conteúdo de cliente é sigiloso
    assert (out.stat().st_mode & 0o777) == 0o600


def test_determinismo_dois_pdfs_seguidos(
    tmp_path: Path, cfg_minima, fake_audio_meta, fake_env_meta, fake_result,
) -> None:
    """Gerar 2x deve produzir conteúdo equivalente.

    Nota: bytes podem diferir porque PDFs incluem timestamps internos, mas
    o conteúdo extraído deve ser o mesmo. Aqui só validamos que tamanhos
    são próximos (margem de 5%).
    """
    out1 = tmp_path / "v1.pdf"
    out2 = tmp_path / "v2.pdf"
    for out in (out1, out2):
        build_pdf(
            out, fake_audio_meta, fake_env_meta, fake_result,
            cfg_minima.identidade_visual, cfg_minima.advogado,
        )

    s1, s2 = out1.stat().st_size, out2.stat().st_size
    delta = abs(s1 - s2) / max(s1, s2)
    assert delta < 0.05, f"Tamanhos divergiram demais: {s1} vs {s2}"
