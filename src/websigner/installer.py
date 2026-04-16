"""WebSigner native messaging host installer.

Registers BigCertificados as the native messaging host for the Web Signer
browser extension, replacing the Softplan binary if present.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import subprocess
from pathlib import Path
from typing import Optional

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

    # Check if extension is installed in Firefox
    for base in [Path.home() / ".config" / "mozilla" / "firefox", Path.home() / ".mozilla" / "firefox"]:
        if not base.is_dir():
            continue
        for xpi in base.rglob("websigner@softplan_com_br.xpi"):
            status["extension_installed"] = True
            break

    return status


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
