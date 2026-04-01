"""Database of token/smartcard drivers and middleware packages.

Maps driver names to Arch Linux packages, installation status,
and PKCS#11 module paths for verification.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenDriver:
    name: str
    packages: tuple[str, ...]
    source: str  # "official" or "aur"
    category: str  # "base", "brazil", "europe", "asia", "hardware", "tools"
    description: str
    icon: str = "dialog-password-symbolic"
    pkcs11_so: str = ""
    check_cmd: str = ""


# ── Category labels and icons ─────────────────────────────────────────

CATEGORY_META: dict[str, tuple[str, str, str]] = {
    # key: (display_name, subtitle, icon)
    "base": (
        "Pacotes Base (Obrigatórios)",
        "Necessários para qualquer token funcionar",
        "emblem-important-symbolic",
    ),
    "brazil": (
        "Tokens Brasileiros",
        "SafeNet, Serasa, GD Burti, Receita Federal",
        "dialog-password-symbolic",
    ),
    "europe": (
        "eID Europeus",
        "Cartões de identidade eletrônica da Europa",
        "preferences-desktop-locale-symbolic",
    ),
    "asia": (
        "eID Ásia &amp; Outros",
        "Cartões de identidade de outros continentes",
        "preferences-desktop-locale-symbolic",
    ),
    "hardware": (
        "Hardware de Segurança",
        "Yubikey, Nitrokey e chaves FIDO2",
        "channel-secure-symbolic",
    ),
    "tools": (
        "Ferramentas Complementares",
        "Utilitários de diagnóstico e inspeção",
        "utilities-terminal-symbolic",
    ),
}

# Ordered list for UI rendering
CATEGORY_ORDER = ("base", "brazil", "europe", "asia", "hardware", "tools")


# ── Driver database ──────────────────────────────────────────────────

DRIVERS: tuple[TokenDriver, ...] = (
    # ── Base ──────────────────────────────────────────────────────────
    TokenDriver(
        "PC/SC Daemon", ("pcsclite",), "official", "base",
        "Smart Card daemon — comunicação com leitores e tokens",
        icon="system-run-symbolic",
        check_cmd="pcscd",
    ),
    TokenDriver(
        "CCID Driver", ("ccid",), "official", "base",
        "Driver genérico para leitores USB CCID",
        icon="drive-removable-media-symbolic",
    ),
    TokenDriver(
        "OpenSC", ("opensc",), "official", "base",
        "Ferramentas e módulo PKCS#11 genérico para smart cards",
        pkcs11_so="/usr/lib/opensc-pkcs11.so",
        check_cmd="opensc-tool",
    ),
    TokenDriver(
        "NSS Tools", ("nss",), "official", "base",
        "modutil e certutil — configuração de certificados em navegadores",
        icon="applications-internet-symbolic",
        check_cmd="modutil",
    ),
    # ── Brazil ────────────────────────────────────────────────────────
    TokenDriver(
        "SafeNet eToken 5100/5110", ("etoken",), "aur", "brazil",
        "Driver para tokens SafeNet/Thales — o mais usado no Brasil",
        pkcs11_so="/usr/lib/libeToken.so",
    ),
    TokenDriver(
        "Token Serasa (G&amp;D / Valid)", ("libaet",), "aur", "brazil",
        "Middleware AET para tokens Serasa Experian",
        pkcs11_so="/usr/lib/libaetpkss.so.3",
    ),
    TokenDriver(
        "SafeSign (GD Burti / StarSign)", ("safesignidentityclient",),
        "aur", "brazil",
        "Gerenciador para tokens GD Burti e StarSign Crypto USB",
        pkcs11_so="/usr/lib/libaetpkss.so.3",
        check_cmd="tokenadmin",
    ),
    TokenDriver(
        "Token Receita Federal", ("libiccbridge",), "aur", "brazil",
        "Middleware ICC Bridge para tokens da Receita Federal / Kryptus",
        pkcs11_so="/usr/lib/libiccbridge.so",
    ),
    TokenDriver(
        "Leitor SCM (GD Burti)", ("scmccid",), "aur", "brazil",
        "Driver para leitores SCM Microsystems usados com tokens GD Burti",
        icon="drive-removable-media-symbolic",
    ),
    TokenDriver(
        "OpenWebStart", ("openwebstart-bin",), "aur", "brazil",
        "Executa JNLP — necessário para instaladores Certisign e Serpro",
        icon="applications-internet-symbolic",
        check_cmd="javaws",
    ),
    # ── Europe ────────────────────────────────────────────────────────
    TokenDriver("Cartão de Cidadão (Portugal)", ("pteid-mw",), "aur", "europe",
                "Middleware do Cartão de Cidadão português"),
    TokenDriver("eID Belga", ("beid-mw",), "aur", "europe",
                "Middleware do cartão de identidade belga"),
    TokenDriver("eID Alemão (AusweisApp)", ("ausweisapp2",), "aur", "europe",
                "Aplicação para autenticação com eID alemão"),
    TokenDriver("eID Francês", ("french-eid-mw",), "aur", "europe",
                "Middleware do cartão de identidade francês"),
    TokenDriver("eID Italiano (CIE/CNS)", ("cie-middleware",), "aur", "europe",
                "Middleware Carta d'Identità Elettronica italiana"),
    TokenDriver("eID Espanhol (DNIe)", ("dnie-mw",), "aur", "europe",
                "Middleware do DNI electrónico espanhol"),
    TokenDriver("eID Austríaco", ("aet-mw",), "aur", "europe",
                "Middleware do cartão de identidade austríaco"),
    TokenDriver("eID Suíço", ("swiss-eid-mw",), "aur", "europe",
                "Middleware do eID suíço"),
    TokenDriver("eID Holandês", ("dutch-eid-mw",), "aur", "europe",
                "Middleware do eID holandês"),
    TokenDriver("eID Sueco", ("swedish-eid-mw",), "aur", "europe",
                "Middleware do eID sueco"),
    TokenDriver("eID Norueguês", ("norwegian-eid-mw",), "aur", "europe",
                "Middleware do eID norueguês"),
    TokenDriver("eID Finlandês", ("finnish-eid-mw",), "aur", "europe",
                "Middleware do eID finlandês"),
    TokenDriver("eID Dinamarquês", ("danish-eid-mw",), "aur", "europe",
                "Middleware do eID dinamarquês"),
    TokenDriver("eID Estoniano", ("estonian-eid-mw",), "aur", "europe",
                "Middleware do eID estoniano"),
    TokenDriver("eID Polonês", ("polish-eid-mw",), "aur", "europe",
                "Middleware do eID polonês"),
    TokenDriver("eID Tcheco", ("czech-eid-mw",), "aur", "europe",
                "Middleware do eID tcheco"),
    TokenDriver("eID Romeno", ("romanian-eid-mw",), "aur", "europe",
                "Middleware do eID romeno"),
    TokenDriver("eID Búlgaro", ("bulgarian-eid-mw",), "aur", "europe",
                "Middleware do eID búlgaro"),
    TokenDriver("eID Croata", ("croatian-eid-mw",), "aur", "europe",
                "Middleware do eID croata"),
    TokenDriver("eID Esloveno", ("slovenian-eid-mw",), "aur", "europe",
                "Middleware do eID esloveno"),
    TokenDriver("eID Grego", ("greek-eid-mw",), "aur", "europe",
                "Middleware do eID grego"),
    TokenDriver("eID Cipriota", ("cypriot-eid-mw",), "aur", "europe",
                "Middleware do eID cipriota"),
    TokenDriver("eID Maltês", ("maltese-eid-mw",), "aur", "europe",
                "Middleware do eID maltês"),
    TokenDriver("eID Letão", ("latvian-eid-mw",), "aur", "europe",
                "Middleware do eID letão"),
    TokenDriver("eID Lituano", ("lithuanian-eid-mw",), "aur", "europe",
                "Middleware do eID lituano"),
    TokenDriver("eID Sérvio", ("serbian-eid-mw",), "aur", "europe",
                "Middleware do eID sérvio"),
    TokenDriver("eID Montenegrino", ("montenegrin-eid-mw",), "aur", "europe",
                "Middleware do eID montenegrino"),
    TokenDriver("eID Macedônio", ("macedonian-eid-mw",), "aur", "europe",
                "Middleware do eID macedônio"),
    TokenDriver("eID Albanês", ("albanian-eid-mw",), "aur", "europe",
                "Middleware do eID albanês"),
    TokenDriver("eID Kosovar", ("kosovar-eid-mw",), "aur", "europe",
                "Middleware do eID kosovar"),
    TokenDriver("eID Moldavo", ("moldovan-eid-mw",), "aur", "europe",
                "Middleware do eID moldavo"),
    # ── Asia / other ──────────────────────────────────────────────────
    TokenDriver("eID Russo", ("russian-eid-mw",), "aur", "asia",
                "Middleware do eID russo"),
    TokenDriver("eID Ucraniano", ("ukrainian-eid-mw",), "aur", "asia",
                "Middleware do eID ucraniano"),
    TokenDriver("eID Bielorrusso", ("belarusian-eid-mw",), "aur", "asia",
                "Middleware do eID bielorrusso"),
    TokenDriver("eID Georgiano", ("georgian-eid-mw",), "aur", "asia",
                "Middleware do eID georgiano"),
    TokenDriver("eID Armênio", ("armenian-eid-mw",), "aur", "asia",
                "Middleware do eID armênio"),
    TokenDriver("eID Azerbaijano", ("azerbaijani-eid-mw",), "aur", "asia",
                "Middleware do eID azerbaijano"),
    TokenDriver("eID Cazaque", ("kazakh-eid-mw",), "aur", "asia",
                "Middleware do eID cazaque"),
    TokenDriver("eID Uzbeque", ("uzbek-eid-mw",), "aur", "asia",
                "Middleware do eID uzbeque"),
    TokenDriver("eID Turcomeno", ("turkmen-eid-mw",), "aur", "asia",
                "Middleware do eID turcomeno"),
    TokenDriver("eID Tadjique", ("tajik-eid-mw",), "aur", "asia",
                "Middleware do eID tadjique"),
    TokenDriver("eID Quirguiz", ("kyrgyz-eid-mw",), "aur", "asia",
                "Middleware do eID quirguiz"),
    TokenDriver("eID Mongol", ("mongolian-eid-mw",), "aur", "asia",
                "Middleware do eID mongol"),
    TokenDriver("eID Chinês", ("chinese-eid-mw",), "aur", "asia",
                "Middleware do eID chinês"),
    TokenDriver("eID Japonês", ("japanese-eid-mw",), "aur", "asia",
                "Middleware do eID japonês"),
    TokenDriver("eID Coreano", ("korean-eid-mw",), "aur", "asia",
                "Middleware do eID coreano"),
    TokenDriver("eID Vietnamita", ("vietnamese-eid-mw",), "aur", "asia",
                "Middleware do eID vietnamita"),
    TokenDriver("eID Tailandês", ("thai-eid-mw",), "aur", "asia",
                "Middleware do eID tailandês"),
    TokenDriver("eID Malaio", ("malaysian-eid-mw",), "aur", "asia",
                "Middleware do eID malaio"),
    TokenDriver("eID Indonésio", ("indonesian-eid-mw",), "aur", "asia",
                "Middleware do eID indonésio"),
    TokenDriver("eID Filipino", ("filipino-eid-mw",), "aur", "asia",
                "Middleware do eID filipino"),
    TokenDriver("eID Indiano", ("indian-eid-mw",), "aur", "asia",
                "Middleware do eID indiano"),
    TokenDriver("eID Paquistanês", ("pakistani-eid-mw",), "aur", "asia",
                "Middleware do eID paquistanês"),
    # ── Hardware security ─────────────────────────────────────────────
    TokenDriver(
        "YubiKey (Personalização)", ("yubikey-personalization",),
        "official", "hardware",
        "Personalização de chaves Yubikey",
        icon="channel-secure-symbolic",
    ),
    TokenDriver(
        "YubiKey Manager", ("yubikey-manager",),
        "official", "hardware",
        "Gerenciador GUI para Yubikey",
        icon="channel-secure-symbolic",
        check_cmd="ykman",
    ),
    TokenDriver(
        "Nitrokey", ("nitrokey-app",),
        "aur", "hardware",
        "Gerenciador GUI para Nitrokey",
        icon="channel-secure-symbolic",
    ),
    # ── Tools ─────────────────────────────────────────────────────────
    TokenDriver(
        "PKCS#11 Tools", ("pkcs11-tools",),
        "official", "tools",
        "CLI para inspecionar tokens e módulos PKCS#11",
        icon="utilities-terminal-symbolic",
        check_cmd="pkcs11-tool",
    ),
    TokenDriver(
        "PC/SC Tools", ("pcsc-tools",),
        "official", "tools",
        "Ferramentas de diagnóstico PC/SC (pcsc_scan, etc.)",
        icon="utilities-terminal-symbolic",
        check_cmd="pcsc_scan",
    ),
)


# ── Queries ──────────────────────────────────────────────────────────

def get_drivers_by_category() -> dict[str, list[TokenDriver]]:
    """Return drivers grouped by category in display order."""
    groups: dict[str, list[TokenDriver]] = {cat: [] for cat in CATEGORY_ORDER}
    for drv in DRIVERS:
        groups.setdefault(drv.category, []).append(drv)
    return groups


def get_installed_packages() -> set[str]:
    """Return set of all installed package names (single pacman call)."""
    try:
        result = subprocess.run(
            ["pacman", "-Qq"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return set(result.stdout.strip().splitlines())
    except Exception:
        pass
    return set()


def is_package_installed(pkg: str) -> bool:
    """Check whether an Arch package is installed."""
    try:
        result = subprocess.run(
            ["pacman", "-Q", pkg],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_driver_installed(driver: TokenDriver, installed_pkgs: set[str] | None = None) -> bool:
    """Check if a driver's packages are present on the system."""
    if driver.check_cmd:
        if shutil.which(driver.check_cmd):
            return True
    if driver.pkcs11_so:
        from pathlib import Path
        if Path(driver.pkcs11_so).exists():
            return True
    if installed_pkgs is None:
        installed_pkgs = get_installed_packages()
    return all(pkg in installed_pkgs for pkg in driver.packages)


def get_pcscd_status() -> tuple[bool, bool]:
    """Return (is_active, is_enabled) for pcscd.service."""
    active = False
    enabled = False
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "pcscd.service"],
            capture_output=True, text=True, timeout=5,
        )
        active = r.stdout.strip() == "active"
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["systemctl", "is-enabled", "pcscd.service"],
            capture_output=True, text=True, timeout=5,
        )
        enabled = r.stdout.strip() == "enabled"
    except Exception:
        pass
    return active, enabled


def install_official_packages(packages: list[str]) -> tuple[bool, str]:
    """Install official repo packages via pkexec pacman."""
    try:
        result = subprocess.run(
            ["pkexec", "pacman", "-S", "--noconfirm", "--needed"] + packages,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return True, "Pacotes instalados com sucesso"
        return False, result.stderr.strip() or "Falha na instalação"
    except subprocess.TimeoutExpired:
        return False, "Tempo limite excedido"
    except Exception as exc:
        return False, str(exc)


def open_aur_install(package: str) -> bool:
    """Open a terminal to install an AUR package via yay/paru."""
    if not re.match(r'^[a-zA-Z0-9@._+-]+$', package):
        log.error("Invalid package name: %s", package)
        return False
    helper = shutil.which("yay") or shutil.which("paru")
    if not helper:
        return False
    terminal = (
        shutil.which("xdg-terminal-exec")
        or shutil.which("konsole")
        or shutil.which("gnome-terminal")
        or shutil.which("xterm")
    )
    if not terminal:
        return False
    try:
        if "konsole" in terminal:
            subprocess.Popen([terminal, "-e", helper, "-S", package])
        else:
            subprocess.Popen([terminal, helper, "-S", package])
        return True
    except Exception as exc:
        log.error("Failed to open terminal for AUR install: %s", exc)
        return False
