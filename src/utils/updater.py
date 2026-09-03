"""PJeOffice Pro update checker — scrapes official download page for latest version."""

from __future__ import annotations

import json
import logging
import re
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from src.utils.xdg import config_dir

log = logging.getLogger(__name__)

# Canonical PJeOffice version — single source of truth for the application
PJEOFFICE_VERSION = "2.5.16u"

# Known installed version (kept for backward compat; aliases PJEOFFICE_VERSION)
PJEOFFICE_KNOWN_VERSION = PJEOFFICE_VERSION

# Official download page
PJEOFFICE_BASE_URL = "https://pje-office.pje.jus.br/pro/"

# Canonical installer artifact — single source of truth shared by the GTK
# installer dialog and the TUI installer service. The SHA-256 pins the exact
# linux_x64 zip of PJEOFFICE_VERSION published by the TRF3/CNJ.
PJEOFFICE_DOWNLOAD_URL = (
    f"{PJEOFFICE_BASE_URL}pjeoffice-pro-v{PJEOFFICE_VERSION}-linux_x64.zip"
)
PJEOFFICE_SHA256 = "6087391759c7cba11fb5ef815fe8be91713b46a8607c12eb664a9d9a6882c4c7"

SETTINGS_FILE = "settings.json"
CHECK_INTERVAL_HOURS = 24


@dataclass
class PJeOfficeUpdateInfo:
    """Information about an available PJeOffice Pro update."""
    version: str
    download_url: str
    sha256: str


def _settings_path() -> Path:
    return config_dir() / SETTINGS_FILE


def load_settings() -> dict:
    """Load app settings from disk."""
    path = _settings_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("Failed to read settings, using defaults")
    return {}


def save_settings(settings: dict) -> None:
    """Save app settings to disk."""
    path = _settings_path()
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def is_pjeoffice_auto_update_enabled() -> bool:
    """Check if automatic PJeOffice update checking is enabled."""
    return load_settings().get("pjeoffice_auto_check_updates", True)


def set_pjeoffice_auto_update_enabled(enabled: bool) -> None:
    """Enable or disable automatic PJeOffice update checking."""
    settings = load_settings()
    settings["pjeoffice_auto_check_updates"] = enabled
    save_settings(settings)


def should_check_pjeoffice_now() -> bool:
    """Whether enough time has passed since last PJeOffice update check."""
    settings = load_settings()
    last_check = settings.get("last_pjeoffice_update_check")
    if not last_check:
        return True
    try:
        last_dt = datetime.fromisoformat(last_check)
        elapsed = datetime.now(timezone.utc) - last_dt
        return elapsed.total_seconds() > CHECK_INTERVAL_HOURS * 3600
    except (ValueError, TypeError):
        return True


def _record_pjeoffice_check() -> None:
    """Record timestamp of the last PJeOffice update check."""
    settings = load_settings()
    settings["last_pjeoffice_update_check"] = datetime.now(timezone.utc).isoformat()
    save_settings(settings)


def get_installed_pjeoffice_version() -> Optional[str]:
    """Try to detect the installed PJeOffice Pro version."""
    jar_path = Path("/usr/share/pjeoffice-pro/pjeoffice-pro.jar")
    if not jar_path.exists():
        return None

    # Check if we stored the installed version
    settings = load_settings()
    stored = settings.get("pjeoffice_installed_version")
    if stored:
        return stored

    return PJEOFFICE_KNOWN_VERSION


def _parse_version(version_str: str) -> str:
    """Normalize version string for comparison."""
    return version_str.lstrip("vV").strip()


def _version_key(version_str: str) -> tuple[tuple[int, int | str], ...]:
    """Build a deterministic key for dotted versions with optional suffixes."""
    normalized = _parse_version(version_str)
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.findall(r"\d+|[A-Za-z]+", normalized)
    )


def check_pjeoffice_updates(installed_version: str) -> Optional[PJeOfficeUpdateInfo]:
    """Check the official PJeOffice Pro download page for a newer version.

    Fetches the directory listing and looks for the latest linux_x64.zip.
    Returns PJeOfficeUpdateInfo if a newer version exists, None otherwise.
    """
    req = urllib.request.Request(
        PJEOFFICE_BASE_URL,
        headers={"User-Agent": "BigCertificados/0.1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    # Find all linux_x64.zip links with version
    pattern = r'pjeoffice-pro-v([\d.]+[A-Za-z]*)-linux_x64\.zip'
    versions = set(re.findall(pattern, html))

    if not versions:
        log.debug("No PJeOffice versions found on download page")
        _record_pjeoffice_check()
        return None

    latest = max(versions, key=_version_key)

    if _version_key(latest) > _version_key(installed_version):
        download_url = f"{PJEOFFICE_BASE_URL}pjeoffice-pro-v{latest}-linux_x64.zip"

        # Try to find SHA-256 file
        sha256 = ""
        sha_pattern = rf'pjeoffice-pro-v{re.escape(latest)}-linux_x64\.zip\.sha256'
        sha_match = re.search(sha_pattern, html)
        if sha_match:
            try:
                sha_url = f"{PJEOFFICE_BASE_URL}pjeoffice-pro-v{latest}-linux_x64.zip.sha256"
                sha_req = urllib.request.Request(
                    sha_url,
                    headers={"User-Agent": "BigCertificados/0.1.0"},
                )
                with urllib.request.urlopen(sha_req, timeout=10) as sha_resp:
                    candidate = sha_resp.read().decode("utf-8").strip().split()[0]
                    if re.fullmatch(r"[0-9a-fA-F]{64}", candidate):
                        sha256 = candidate.lower()
            except Exception:
                log.debug("Could not fetch SHA-256 for PJeOffice %s", latest)

        _record_pjeoffice_check()
        return PJeOfficeUpdateInfo(
            version=latest,
            download_url=download_url,
            sha256=sha256,
        )

    _record_pjeoffice_check()
    return None


def check_pjeoffice_updates_async(
    installed_version: str,
    callback: Callable[[Optional[PJeOfficeUpdateInfo], Optional[str]], None],
) -> None:
    """Check for PJeOffice updates in a background thread.

    callback(update_info, error_message) is called on the main thread via GLib.
    """
    from gi.repository import GLib

    def _worker() -> None:
        try:
            result = check_pjeoffice_updates(installed_version)
            GLib.idle_add(callback, result, None)
        except Exception as exc:
            log.debug("PJeOffice update check failed: %s", exc)
            GLib.idle_add(callback, None, str(exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
