"""Carregamento e validação da configuração do transcritor.

Arquivo: ~/.config/big-advogados/transcritor.toml

Na primeira execução, escreve um template com defaults seguros. O usuário
edita os campos de identidade (logo, dados do advogado) antes de gerar
PDFs assinados em nome dele.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Python 3.11+ tem tomllib na stdlib; fallback para tomli em 3.10
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
CONFIG_DIR = XDG_CONFIG / "big-advogados"
CONFIG_FILE = CONFIG_DIR / "transcritor.toml"
IDENTITY_DIR = CONFIG_DIR / "identity"


Device = Literal["auto", "cpu", "cuda"]
ComputeType = Literal["default", "int8", "int8_float16", "float16", "float32"]


@dataclass(frozen=True)
class ModeloConfig:
    nome: str = "large-v3"
    device: Device = "auto"
    compute_type: ComputeType = "default"


@dataclass(frozen=True)
class TranscricaoConfig:
    idioma: str = "pt"
    beam_size: int = 10
    temperature: float = 0.0
    vad_filter: bool = True
    word_timestamps: bool = True
    condition_on_previous_text: bool = True


@dataclass(frozen=True)
class IdentidadeVisualConfig:
    logo: Path = field(default_factory=lambda: IDENTITY_DIR / "logo-principal.png")
    footer_bar: Path = field(default_factory=lambda: IDENTITY_DIR / "footer-bar.png")
    fonte_corpo: str = "Ubuntu"

    @property
    def logo_existe(self) -> bool:
        return self.logo.is_file()

    @property
    def footer_bar_existe(self) -> bool:
        return self.footer_bar.is_file()


@dataclass(frozen=True)
class AdvogadoConfig:
    nome: str = ""
    oab: str = ""
    escritorio: str = ""
    endereco: str = ""
    email: str = ""
    cnpj: str = ""

    @property
    def preenchido(self) -> bool:
        """True se nome e OAB estão definidos — mínimo para emitir declaração."""
        return bool(self.nome.strip() and self.oab.strip())


@dataclass(frozen=True)
class TranscritorConfig:
    modelo: ModeloConfig = field(default_factory=ModeloConfig)
    transcricao: TranscricaoConfig = field(default_factory=TranscricaoConfig)
    identidade_visual: IdentidadeVisualConfig = field(default_factory=IdentidadeVisualConfig)
    advogado: AdvogadoConfig = field(default_factory=AdvogadoConfig)


_TEMPLATE = """# Configuração do Transcritor de Áudio — Big Advogados
# Documentação: https://github.com/xathay/big-advogados/blob/main/docs/

[modelo]
# Modelos disponíveis: tiny, base, small, medium, large-v3
# large-v3 é o mais preciso (recomendado para uso jurídico) mas
# requer ~3GB de download e ~10GB de RAM em CPU.
nome = "large-v3"
device = "auto"            # auto | cpu | cuda
compute_type = "default"   # default | int8 | int8_float16 | float16 | float32

[transcricao]
idioma = "pt"
beam_size = 10
temperature = 0.0
vad_filter = true
word_timestamps = true
condition_on_previous_text = true

[identidade_visual]
# Caminhos absolutos para logo e barra-rodapé do PDF.
# Defaults assumem que você colocou imagens em ~/.config/big-advogados/identity/
logo = "{logo_default}"
footer_bar = "{footer_default}"
fonte_corpo = "Ubuntu"

[advogado]
nome = ""
oab = ""
escritorio = ""
endereco = ""
email = ""
cnpj = ""
"""


def _coerce_path(value: object, fallback: Path) -> Path:
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser()
    return fallback


def _parse_modelo(data: dict) -> ModeloConfig:
    defaults = ModeloConfig()
    return ModeloConfig(
        nome=str(data.get("nome", defaults.nome)),
        device=str(data.get("device", defaults.device)),  # type: ignore[arg-type]
        compute_type=str(data.get("compute_type", defaults.compute_type)),  # type: ignore[arg-type]
    )


def _parse_transcricao(data: dict) -> TranscricaoConfig:
    defaults = TranscricaoConfig()
    return TranscricaoConfig(
        idioma=str(data.get("idioma", defaults.idioma)),
        beam_size=int(data.get("beam_size", defaults.beam_size)),
        temperature=float(data.get("temperature", defaults.temperature)),
        vad_filter=bool(data.get("vad_filter", defaults.vad_filter)),
        word_timestamps=bool(data.get("word_timestamps", defaults.word_timestamps)),
        condition_on_previous_text=bool(
            data.get("condition_on_previous_text", defaults.condition_on_previous_text)
        ),
    )


def _parse_identidade(data: dict) -> IdentidadeVisualConfig:
    defaults = IdentidadeVisualConfig()
    return IdentidadeVisualConfig(
        logo=_coerce_path(data.get("logo"), defaults.logo),
        footer_bar=_coerce_path(data.get("footer_bar"), defaults.footer_bar),
        fonte_corpo=str(data.get("fonte_corpo", defaults.fonte_corpo)),
    )


def _parse_advogado(data: dict) -> AdvogadoConfig:
    defaults = AdvogadoConfig()
    return AdvogadoConfig(
        nome=str(data.get("nome", defaults.nome)),
        oab=str(data.get("oab", defaults.oab)),
        escritorio=str(data.get("escritorio", defaults.escritorio)),
        endereco=str(data.get("endereco", defaults.endereco)),
        email=str(data.get("email", defaults.email)),
        cnpj=str(data.get("cnpj", defaults.cnpj)),
    )


def write_default_config(path: Path = CONFIG_FILE) -> None:
    """Escreve o template padrão na localização informada."""
    path.parent.mkdir(parents=True, exist_ok=True)
    IDENTITY_DIR.mkdir(parents=True, exist_ok=True)
    content = _TEMPLATE.format(
        logo_default=IDENTITY_DIR / "logo-principal.png",
        footer_default=IDENTITY_DIR / "footer-bar.png",
    )
    path.write_text(content, encoding="utf-8")


def load_config(path: Path = CONFIG_FILE) -> TranscritorConfig:
    """Carrega a config; cria template se o arquivo não existir."""
    if not path.is_file():
        write_default_config(path)
        return TranscritorConfig()

    with path.open("rb") as f:
        raw = tomllib.load(f)

    return TranscritorConfig(
        modelo=_parse_modelo(raw.get("modelo", {})),
        transcricao=_parse_transcricao(raw.get("transcricao", {})),
        identidade_visual=_parse_identidade(raw.get("identidade_visual", {})),
        advogado=_parse_advogado(raw.get("advogado", {})),
    )
