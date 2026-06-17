"""PJeOffice Pro — status e verificação de atualização (GTK-free).

Reusa `src/utils/updater.py`. O módulo só toca GLib dentro de
`check_pjeoffice_updates_async`, que NÃO importamos — usamos as funções
síncronas num worker thread do Textual.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.utils import updater


@dataclass(frozen=True)
class PJeStatus:
    instalado: bool
    versao_instalada: Optional[str]
    versao_canonica: str


def status() -> PJeStatus:
    instalada = updater.get_installed_pjeoffice_version()
    return PJeStatus(
        instalado=instalada is not None,
        versao_instalada=instalada,
        versao_canonica=updater.PJEOFFICE_VERSION,
    )


def verificar_atualizacao(versao_instalada: Optional[str]):
    """Consulta a página oficial. Retorna (info|None, erro|None). Bloqueante."""
    base = versao_instalada or updater.PJEOFFICE_VERSION
    try:
        info = updater.check_pjeoffice_updates(base)
    except Exception as exc:  # noqa: BLE001
        return None, f"Falha ao consultar atualização: {exc}"
    return info, None


def url_download() -> str:
    return updater.PJEOFFICE_BASE_URL
