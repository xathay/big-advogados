"""VidaaS Connect dependency checker and installer.

Verifies and manages system dependencies required for VidaaS Connect
cloud certificates: opensc, pcsclite, ccid.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)

OPENSC_SEARCH_PATHS = (
    "/usr/lib/opensc-pkcs11.so",
    "/usr/lib/pkcs11/opensc-pkcs11.so",
    "/usr/lib64/opensc-pkcs11.so",
    "/usr/lib/x86_64-linux-gnu/opensc-pkcs11.so",
)

PCSCD_DRIVER_DIR = "/usr/lib/pcsc/drivers"


class DependencyStatus(NamedTuple):
    opensc_installed: bool
    pcscd_installed: bool
    ccid_installed: bool
    pcscd_running: bool
    opensc_module_path: str | None


def find_opensc_module() -> str | None:
    """Find the OpenSC PKCS#11 module on the system."""
    for path in OPENSC_SEARCH_PATHS:
        if Path(path).is_file():
            return path
    return None


def check_dependencies() -> DependencyStatus:
    """Check all VidaaS-related system dependencies."""
    opensc_path = find_opensc_module()

    return DependencyStatus(
        opensc_installed=opensc_path is not None,
        pcscd_installed=shutil.which("pcscd") is not None,
        ccid_installed=Path(PCSCD_DRIVER_DIR).is_dir(),
        pcscd_running=_is_service_active("pcscd"),
        opensc_module_path=opensc_path,
    )


def _is_service_active(service: str) -> bool:
    """Check if a systemd service is active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False


def is_pcscd_socket_enabled() -> bool:
    """Check if pcscd.socket is enabled (on-demand activation)."""
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", "pcscd.socket"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "enabled"
    except Exception:
        return False


def ensure_pcscd_running() -> bool:
    """Start pcscd if not already running.

    Uses pkexec for privilege elevation. Enables the socket-activated
    service so pcscd starts on demand in future sessions.

    Returns True if pcscd is running after this call.
    """
    if _is_service_active("pcscd"):
        return True

    try:
        result = subprocess.run(
            ["pkexec", "systemctl", "enable", "--now", "pcscd.socket"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.error("Failed to enable pcscd.socket: %s", result.stderr)
            return False

        # Also start the service itself for immediate use
        subprocess.run(
            ["pkexec", "systemctl", "start", "pcscd.service"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return _is_service_active("pcscd")
    except Exception as exc:
        log.error("Failed to start pcscd: %s", exc)
        return False


def get_missing_packages() -> list[str]:
    """Return list of system packages that need to be installed."""
    missing: list[str] = []
    status = check_dependencies()
    if not status.opensc_installed:
        missing.append("opensc")
    if not status.pcscd_installed:
        missing.append("pcsclite")
    if not status.ccid_installed:
        missing.append("ccid")
    return missing


def install_packages(packages: list[str]) -> tuple[bool, str]:
    """Install system packages via pacman with privilege elevation.

    Returns (success, output_message).
    """
    if not packages:
        return True, "Nenhum pacote para instalar"

    cmd = ["pkexec", "pacman", "-S", "--noconfirm", "--needed"] + packages
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            log.info("Installed packages: %s", ", ".join(packages))
            return True, result.stdout
        log.error("pacman failed: %s", result.stderr)
        return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Timeout ao instalar pacotes"
    except Exception as exc:
        log.error("Package installation failed: %s", exc)
        return False, str(exc)


def run_pcsc_scan(timeout: int = 5) -> str:
    """Run pcsc_scan for diagnostics. Returns output text."""
    pcsc_scan = shutil.which("pcsc_scan")
    if pcsc_scan is None:
        return "pcsc_scan não encontrado — instale pcsc-tools"

    try:
        result = subprocess.run(
            [pcsc_scan],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        return "pcsc_scan: timeout (nenhum leitor detectado)"
    except Exception as exc:
        return f"Erro ao executar pcsc_scan: {exc}"
