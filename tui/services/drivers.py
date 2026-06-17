"""Drivers/middleware de tokens — listagem, status e instalação (GTK-free).

Reusa `src/certificate/driver_database.py`. Status via uma única chamada
`pacman -Qq`. Instalação: oficial via `pkexec pacman` (bloqueante, worker);
AUR abre um terminal com yay/paru.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.certificate import driver_database as dd


@dataclass(frozen=True)
class DriverItem:
    nome: str
    packages: tuple[str, ...]
    source: str            # "official" | "aur"
    categoria: str
    categoria_label: str
    descricao: str
    instalado: bool
    _blob: str = field(default="", repr=False, compare=False)


def pcscd_status() -> tuple[bool, bool]:
    """(ativo, habilitado) do pcscd.service."""
    return dd.get_pcscd_status()


def listar_drivers() -> list[DriverItem]:
    """Lista todos os drivers com status de instalação (1 chamada ao pacman)."""
    instalados = dd.get_installed_packages()
    by_cat = dd.get_drivers_by_category()
    out: list[DriverItem] = []
    for cat in dd.CATEGORY_ORDER:
        label = dd.CATEGORY_META.get(cat, (cat, "", ""))[0]
        for drv in by_cat.get(cat, []):
            inst = dd.is_driver_installed(drv, instalados)
            blob = " ".join((drv.name, drv.description, label, " ".join(drv.packages))).lower()
            out.append(DriverItem(
                nome=drv.name, packages=tuple(drv.packages), source=drv.source,
                categoria=cat, categoria_label=label, descricao=drv.description,
                instalado=inst, _blob=blob,
            ))
    return out


def buscar(itens: list[DriverItem], consulta: str) -> list[DriverItem]:
    q = consulta.strip().lower()
    if not q:
        return itens
    tokens = q.split()
    return [d for d in itens if all(t in d._blob for t in tokens)]


def instalar(item: DriverItem) -> tuple[bool, str, bool]:
    """Instala o driver. Retorna (ok, mensagem, abriu_terminal).

    - oficial: `pkexec pacman -S` (bloqueante; pode abrir diálogo do polkit).
    - AUR: abre um terminal por pacote (yay/paru); ok=True se abriu.
    """
    if item.instalado:
        return True, "Já instalado.", False

    if item.source == "official":
        ok, msg = dd.install_official_packages(list(item.packages))
        return ok, msg, False

    # AUR
    abriu_algum = False
    for pkg in item.packages:
        if dd.open_aur_install(pkg):
            abriu_algum = True
    if abriu_algum:
        return True, "Terminal aberto para instalar via AUR (yay/paru).", True
    return False, "Não foi possível abrir o terminal (instale yay/paru).", False
