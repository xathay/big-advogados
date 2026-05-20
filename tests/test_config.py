"""Testes do carregamento e validação da config."""

from __future__ import annotations

from pathlib import Path

from src.transcritor.config import (
    AdvogadoConfig,
    TranscritorConfig,
    load_config,
    write_default_config,
)


def test_carrega_defaults_quando_arquivo_nao_existe(tmp_path: Path) -> None:
    config_file = tmp_path / "transcritor.toml"
    cfg = load_config(config_file)

    assert isinstance(cfg, TranscritorConfig)
    assert cfg.modelo.nome == "large-v3"
    assert cfg.transcricao.idioma == "pt"
    assert cfg.transcricao.beam_size == 10
    assert cfg.transcricao.temperature == 0.0
    # E deve ter escrito o arquivo template
    assert config_file.is_file()


def test_carrega_overrides_do_toml(tmp_path: Path) -> None:
    config_file = tmp_path / "custom.toml"
    config_file.write_text(
        """
[modelo]
nome = "medium"
device = "cpu"

[transcricao]
idioma = "en"
beam_size = 5

[advogado]
nome = "Fulano de Tal"
oab = "OAB/SP 12345"
""",
        encoding="utf-8",
    )
    cfg = load_config(config_file)

    assert cfg.modelo.nome == "medium"
    assert cfg.modelo.device == "cpu"
    assert cfg.transcricao.idioma == "en"
    assert cfg.transcricao.beam_size == 5
    assert cfg.advogado.nome == "Fulano de Tal"
    assert cfg.advogado.preenchido


def test_advogado_nao_preenchido_quando_sem_dados() -> None:
    a = AdvogadoConfig()
    assert not a.preenchido

    a_parcial = AdvogadoConfig(nome="Fulano")  # sem OAB
    assert not a_parcial.preenchido


def test_write_default_cria_estrutura(tmp_path: Path) -> None:
    config_file = tmp_path / "config" / "transcritor.toml"
    write_default_config(config_file)
    assert config_file.is_file()
    content = config_file.read_text()
    assert "[modelo]" in content
    assert "large-v3" in content
    assert "[advogado]" in content
