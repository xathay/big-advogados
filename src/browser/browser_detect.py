"""Detect installed browsers and their profile directories."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class BrowserProfile:
    browser: str
    name: str
    path: Path
    nss_db_path: Path


def find_firefox_profiles() -> list[BrowserProfile]:
    """Find all Firefox profiles with NSS databases."""
    profiles: list[BrowserProfile] = []
    mozilla_dir = Path.home() / ".mozilla" / "firefox"

    if not mozilla_dir.is_dir():
        return profiles

    # Parse profiles.ini
    ini_path = mozilla_dir / "profiles.ini"
    if ini_path.is_file():
        current_section: dict[str, str] = {}
        for line in ini_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("[Profile"):
                if current_section:
                    _add_firefox_profile(mozilla_dir, current_section, profiles)
                current_section = {}
            elif "=" in line:
                key, _, val = line.partition("=")
                current_section[key.strip()] = val.strip()
        if current_section:
            _add_firefox_profile(mozilla_dir, current_section, profiles)

    # Fallback: scan for *.default* directories
    if not profiles:
        for d in mozilla_dir.iterdir():
            if d.is_dir() and (d / "cert9.db").exists():
                profiles.append(BrowserProfile(
                    browser="Firefox",
                    name=d.name,
                    path=d,
                    nss_db_path=d,
                ))

    return profiles


def _add_firefox_profile(
    mozilla_dir: Path,
    section: dict[str, str],
    profiles: list[BrowserProfile],
) -> None:
    name = section.get("Name", "unknown")
    path_str = section.get("Path", "")
    is_relative = section.get("IsRelative", "1") == "1"

    if not path_str:
        return

    if is_relative:
        profile_path = mozilla_dir / path_str
    else:
        profile_path = Path(path_str)

    if profile_path.is_dir():
        profiles.append(BrowserProfile(
            browser="Firefox",
            name=name,
            path=profile_path,
            nss_db_path=profile_path,
        ))


def find_chromium_profiles() -> list[BrowserProfile]:
    """Find Chromium/Chrome NSS database."""
    profiles: list[BrowserProfile] = []
    nss_db = Path.home() / ".pki" / "nssdb"

    if nss_db.is_dir():
        # Chrome/Chromium share a single NSS db
        for browser_name, config_dir in [
            ("Google Chrome", Path.home() / ".config" / "google-chrome"),
            ("Chromium", Path.home() / ".config" / "chromium"),
            ("Brave", Path.home() / ".config" / "BraveSoftware" / "Brave-Browser"),
            ("Vivaldi", Path.home() / ".config" / "vivaldi"),
            ("Microsoft Edge", Path.home() / ".config" / "microsoft-edge"),
        ]:
            if config_dir.is_dir():
                profiles.append(BrowserProfile(
                    browser=browser_name,
                    name="Default",
                    path=config_dir,
                    nss_db_path=nss_db,
                ))

    return profiles


def find_all_profiles() -> list[BrowserProfile]:
    """Find all browser profiles with NSS databases."""
    return find_firefox_profiles() + find_chromium_profiles()
