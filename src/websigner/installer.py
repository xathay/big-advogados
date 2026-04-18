"""WebSigner native messaging host installer.

Registers BigCertificados as the native messaging host for the Web Signer
browser extension, replacing the Softplan binary if present.
"""

from __future__ import annotations

import io
import json
import logging
import os
import stat
import subprocess
import zipfile
from configparser import ConfigParser
from pathlib import Path

log = logging.getLogger(__name__)

# Extension IDs that the native host accepts
FIREFOX_EXTENSION_IDS = ["websigner@softplan_com_br", "websigner@softplan.com.br"]
CHROME_EXTENSION_ID = "bbafmabaelnnkondpfpjmdklbmfnbmol"

NATIVE_APP_NAME = "br.com.softplan.webpki"

# Paths where browsers look for native messaging manifests
FIREFOX_MANIFEST_DIRS = [
    Path.home() / ".mozilla" / "native-messaging-hosts",
    Path.home() / ".config" / "mozilla" / "native-messaging-hosts",
    Path("/usr/lib/mozilla/native-messaging-hosts"),
    Path("/usr/share/mozilla/native-messaging-hosts"),
]

CHROME_MANIFEST_DIRS = [
    Path.home() / ".config" / "google-chrome" / "NativeMessagingHosts",
    Path.home() / ".config" / "chromium" / "NativeMessagingHosts",
    Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts",
    Path("/etc/opt/chrome/native-messaging-hosts"),
    Path("/etc/chromium/native-messaging-hosts"),
]


def _find_native_host_script() -> str:
    """Find the path to the native_host.py script."""
    # Check installed location first
    installed = Path("/usr/lib/big-certificados/websigner-host")
    if installed.is_file():
        return str(installed)

    # Development location
    this_dir = Path(__file__).resolve().parent
    script = this_dir / "native_host.py"
    if script.is_file():
        return str(script)

    raise FileNotFoundError("Cannot find websigner native host script")


def _create_wrapper_script(target_dir: Path) -> str:
    """Create a wrapper shell script that launches the Python native host."""
    wrapper = target_dir / "bigcertificados-websigner"
    native_host = _find_native_host_script()

    # If native_host is already an executable wrapper, use it directly
    if native_host.endswith("websigner-host"):
        return native_host

    content = f"""#!/bin/sh
exec python3 "{native_host}" "$@"
"""
    target_dir.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(content)
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(wrapper)


def _build_firefox_manifest(host_path: str) -> dict:
    return {
        "name": NATIVE_APP_NAME,
        "description": "BigCertificados PKI Connector",
        "path": host_path,
        "type": "stdio",
        "allowed_extensions": FIREFOX_EXTENSION_IDS,
    }


def _build_chrome_manifest(host_path: str) -> dict:
    return {
        "name": NATIVE_APP_NAME,
        "description": "BigCertificados PKI Connector",
        "path": host_path,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{CHROME_EXTENSION_ID}/"],
    }


def install_native_host() -> dict[str, bool]:
    """Install the native messaging host for all browsers.

    Creates per-user manifests in the user's config directories.
    Returns dict mapping target → success.
    """
    results: dict[str, bool] = {}

    # Create wrapper script in user-local directory
    local_bin = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "big-certificados"
    try:
        host_path = _create_wrapper_script(local_bin)
    except Exception as exc:
        log.error("Failed to create wrapper script: %s", exc)
        return {"wrapper": False}

    # Install per-user Firefox manifest
    for user_dir in [
        Path.home() / ".mozilla" / "native-messaging-hosts",
        Path.home() / ".config" / "mozilla" / "native-messaging-hosts",
    ]:
        manifest = _build_firefox_manifest(host_path)
        try:
            user_dir.mkdir(parents=True, exist_ok=True)
            manifest_file = user_dir / f"{NATIVE_APP_NAME}.json"
            manifest_file.write_text(json.dumps(manifest, indent=2))
            results[f"Firefox ({user_dir})"] = True
            log.info("Installed Firefox manifest: %s", manifest_file)
        except Exception as exc:
            results[f"Firefox ({user_dir})"] = False
            log.error("Failed to install Firefox manifest: %s", exc)

    # Install per-user Chrome/Chromium manifests
    for user_dir in [
        Path.home() / ".config" / "google-chrome" / "NativeMessagingHosts",
        Path.home() / ".config" / "chromium" / "NativeMessagingHosts",
        Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts",
    ]:
        manifest = _build_chrome_manifest(host_path)
        try:
            user_dir.mkdir(parents=True, exist_ok=True)
            manifest_file = user_dir / f"{NATIVE_APP_NAME}.json"
            manifest_file.write_text(json.dumps(manifest, indent=2))
            results[f"Chrome ({user_dir.parent.name})"] = True
        except Exception as exc:
            results[f"Chrome ({user_dir.parent.name})"] = False
            log.error("Failed to install Chrome manifest: %s", exc)

    return results


def uninstall_native_host() -> dict[str, bool]:
    """Remove per-user native messaging manifests."""
    results: dict[str, bool] = {}
    user_dirs = [
        Path.home() / ".mozilla" / "native-messaging-hosts",
        Path.home() / ".config" / "mozilla" / "native-messaging-hosts",
        Path.home() / ".config" / "google-chrome" / "NativeMessagingHosts",
        Path.home() / ".config" / "chromium" / "NativeMessagingHosts",
        Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts",
    ]
    for d in user_dirs:
        manifest = d / f"{NATIVE_APP_NAME}.json"
        if manifest.is_file():
            try:
                manifest.unlink()
                results[str(d)] = True
            except Exception as exc:
                results[str(d)] = False
                log.error("Failed to remove manifest: %s", exc)
    return results


def check_installation_status() -> dict:
    """Check if the native messaging host is properly installed.

    Returns dict with:
        installed: bool
        host_path: str or None
        manifest_paths: list of found manifests
        softplan_binary_found: bool
        extension_installed: bool (check Firefox profile)
    """
    status: dict = {
        "installed": False,
        "host_path": None,
        "manifest_paths": [],
        "softplan_binary_found": Path("/opt/softplan-websigner/websigner").is_file(),
        "extension_installed": False,
        "bigcertificados_host": False,
    }

    # Check for manifests
    all_dirs = FIREFOX_MANIFEST_DIRS + CHROME_MANIFEST_DIRS
    for d in all_dirs:
        manifest = d / f"{NATIVE_APP_NAME}.json"
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text())
                status["manifest_paths"].append(str(manifest))
                host_path = data.get("path", "")
                if host_path:
                    status["host_path"] = host_path
                    status["installed"] = Path(host_path).is_file()
                    if "bigcertificados" in host_path.lower() or "big-certificados" in host_path.lower():
                        status["bigcertificados_host"] = True
            except Exception:
                pass

    # Check if Softplan extension is installed in Firefox
    for base in [Path.home() / ".config" / "mozilla" / "firefox", Path.home() / ".mozilla" / "firefox"]:
        if not base.is_dir():
            continue
        for xpi in base.rglob("websigner@softplan_com_br.xpi"):
            status["extension_installed"] = True
            break

    # Check if BigCertificados bridge extension is installed
    status["bridge_installed"] = False
    for profile_path in _find_firefox_profiles():
        xpi_path = profile_path / "extensions" / f"{BRIDGE_EXTENSION_ID}.xpi"
        if xpi_path.is_file():
            status["bridge_installed"] = True
            break

    return status


BRIDGE_EXTENSION_ID = "webpki-bridge@bigcertificados"


def _build_xpi() -> bytes:
    """Build an XPI (ZIP) from the bridge extension directory."""
    bridge_dir = Path(__file__).resolve().parent / "firefox-bridge"
    if not bridge_dir.is_dir():
        raise FileNotFoundError(f"Bridge extension directory not found: {bridge_dir}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(bridge_dir.iterdir()):
            if file_path.is_file():
                zf.write(file_path, file_path.name)
    return buf.getvalue()


def _find_firefox_profiles() -> list[Path]:
    """Find all Firefox profile directories."""
    profiles: list[Path] = []
    for base in [
        Path.home() / ".config" / "mozilla" / "firefox",
        Path.home() / ".mozilla" / "firefox",
    ]:
        profiles_ini = base / "profiles.ini"
        if not profiles_ini.is_file():
            continue
        parser = ConfigParser()
        parser.read(str(profiles_ini))
        for section in parser.sections():
            if not section.startswith("Profile"):
                continue
            path_val = parser.get(section, "Path", fallback="")
            is_relative = parser.getboolean(section, "IsRelative", fallback=True)
            if not path_val:
                continue
            if is_relative:
                profile_path = base / path_val
            else:
                profile_path = Path(path_val)
            if profile_path.is_dir():
                profiles.append(profile_path)
    return profiles


def _ensure_unsigned_extensions_allowed(profile_path: Path) -> None:
    """Set xpinstall.signatures.required=false in user.js so unsigned XPI loads."""
    user_js = profile_path / "user.js"
    pref_line = 'user_pref("xpinstall.signatures.required", false);\n'

    if user_js.is_file():
        content = user_js.read_text(encoding="utf-8")
        if "xpinstall.signatures.required" in content:
            return  # already set (true or false) — don't override
    with open(user_js, "a", encoding="utf-8") as f:
        f.write(pref_line)
    log.info("Set xpinstall.signatures.required=false in %s", user_js)


def install_bridge_extension() -> dict[str, bool]:
    """Package and install the WebPKI bridge extension into Firefox profiles.

    The XPI is placed in <profile>/extensions/<extension-id>.xpi.
    Firefox loads extensions from this directory on startup.
    Also sets xpinstall.signatures.required=false so the unsigned
    extension is accepted.

    Returns dict mapping profile name → success.
    """
    results: dict[str, bool] = {}

    try:
        xpi_data = _build_xpi()
    except FileNotFoundError as exc:
        log.error("Cannot build bridge XPI: %s", exc)
        return {"build": False}

    profiles = _find_firefox_profiles()
    if not profiles:
        log.warning("No Firefox profiles found")
        return {"no_profiles": False}

    for profile_path in profiles:
        profile_name = profile_path.name
        ext_dir = profile_path / "extensions"
        xpi_path = ext_dir / f"{BRIDGE_EXTENSION_ID}.xpi"
        try:
            ext_dir.mkdir(parents=True, exist_ok=True)
            xpi_path.write_bytes(xpi_data)
            _ensure_unsigned_extensions_allowed(profile_path)
            results[profile_name] = True
            log.info("Installed bridge extension to %s", xpi_path)
        except Exception as exc:
            results[profile_name] = False
            log.error("Failed to install bridge to %s: %s", profile_path, exc)

    return results


def uninstall_bridge_extension() -> dict[str, bool]:
    """Remove the bridge extension from all Firefox profiles."""
    results: dict[str, bool] = {}
    for profile_path in _find_firefox_profiles():
        xpi_path = profile_path / "extensions" / f"{BRIDGE_EXTENSION_ID}.xpi"
        if xpi_path.is_file():
            try:
                xpi_path.unlink()
                results[profile_path.name] = True
            except Exception as exc:
                results[profile_path.name] = False
                log.error("Failed to remove bridge from %s: %s", profile_path, exc)
    return results


def configure_pfx_path(pfx_path: str) -> bool:
    """Save the PFX certificate path for the native host to use."""
    from src.websigner.native_host import load_config, save_config

    config = load_config()
    config["pfx_path"] = pfx_path
    try:
        save_config(config)
        return True
    except Exception as exc:
        log.error("Failed to save PFX path: %s", exc)
        return False
