"""NSS database configuration for Firefox and Chrome/Chromium.

Registers PKCS#11 modules so browsers can use A3 certificate tokens.
Uses certutil and modutil from nss-tools package.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from src.browser.browser_detect import BrowserProfile, find_all_profiles

log = logging.getLogger(__name__)

MODUTIL_CMD = "modutil"
CERTUTIL_CMD = "certutil"


def _find_tool(name: str) -> Optional[str]:
    """Check if an NSS tool is available."""
    try:
        result = subprocess.run(
            ["which", name],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def is_nss_tools_available() -> bool:
    return _find_tool(MODUTIL_CMD) is not None


def list_registered_modules(nss_db_path: Path) -> list[str]:
    """List PKCS#11 modules registered in an NSS database."""
    db_prefix = f"sql:{nss_db_path}"
    try:
        result = subprocess.run(
            [MODUTIL_CMD, "-list", "-dbdir", db_prefix],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.splitlines()
    except Exception as exc:
        log.error("Failed to list NSS modules: %s", exc)
    return []


def is_module_registered(nss_db_path: Path, module_name: str) -> bool:
    """Check if a PKCS#11 module is already registered."""
    lines = list_registered_modules(nss_db_path)
    for line in lines:
        if module_name.lower() in line.lower():
            return True
    return False


def register_pkcs11_module(
    nss_db_path: Path,
    module_path: str,
    module_name: str = "BigCertificados_Token",
) -> bool:
    """Register a PKCS#11 module in an NSS database.

    Args:
        nss_db_path: Path to NSS database directory.
        module_path: Full path to .so PKCS#11 library.
        module_name: Human-readable module name for NSS.

    Returns:
        True if registration succeeded or module already exists.
    """
    if is_module_registered(nss_db_path, module_name):
        log.info("Module '%s' already registered in %s", module_name, nss_db_path)
        return True

    db_prefix = f"sql:{nss_db_path}"

    try:
        result = subprocess.run(
            [
                MODUTIL_CMD, "-add", module_name,
                "-libfile", module_path,
                "-dbdir", db_prefix,
                "-force",
            ],
            capture_output=True, text=True, timeout=15,
            input="\n",  # auto-confirm
        )
        if result.returncode == 0:
            log.info(
                "Registered PKCS#11 module '%s' (%s) in %s",
                module_name, module_path, nss_db_path,
            )
            return True
        else:
            log.error("modutil failed: %s", result.stderr)
            return False
    except Exception as exc:
        log.error("Failed to register module: %s", exc)
        return False


def unregister_pkcs11_module(
    nss_db_path: Path,
    module_name: str = "BigCertificados_Token",
) -> bool:
    """Remove a PKCS#11 module from an NSS database."""
    db_prefix = f"sql:{nss_db_path}"

    try:
        result = subprocess.run(
            [MODUTIL_CMD, "-delete", module_name, "-dbdir", db_prefix, "-force"],
            capture_output=True, text=True, timeout=15,
            input="\n",
        )
        return result.returncode == 0
    except Exception as exc:
        log.error("Failed to unregister module: %s", exc)
        return False


def register_in_all_browsers(module_path: str) -> dict[str, bool]:
    """Register PKCS#11 module in all detected browser profiles.

    Returns dict mapping browser name → success status.
    """
    results: dict[str, bool] = {}
    profiles = find_all_profiles()

    seen_dbs: set[str] = set()

    for profile in profiles:
        db_key = str(profile.nss_db_path)
        if db_key in seen_dbs:
            results[f"{profile.browser} ({profile.name})"] = True
            continue
        seen_dbs.add(db_key)

        success = register_pkcs11_module(profile.nss_db_path, module_path)
        results[f"{profile.browser} ({profile.name})"] = success

    return results


def ensure_nss_db(nss_db_path: Path) -> bool:
    """Ensure an NSS database exists (for Chrome/Chromium ~/.pki/nssdb)."""
    if (nss_db_path / "cert9.db").exists():
        return True

    nss_db_path.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [CERTUTIL_CMD, "-d", f"sql:{nss_db_path}", "-N", "--empty-password"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception as exc:
        log.error("Failed to create NSS database: %s", exc)
        return False
