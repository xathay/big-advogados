"""Configure Brave browser Shields for PJe Office compatibility.

Brave Shields blocks the connection from PJe websites to the local
PJe Office server (localhost:8801) by default.  This module disables
Shields on known judicial domains so PJe Office is detected properly.

Solution developed by the BigLinux / BigCommunity team.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# Chromium epoch: microseconds since 1601-01-01
_CHROMIUM_EPOCH_OFFSET = 11644473600

# PJe SSO domain (used by all tribunals for authentication)
PJE_SSO_DOMAIN = "sso.cloud.pje.jus.br"


def _chromium_timestamp() -> str:
    """Return current time as a Chromium-format timestamp string."""
    return str(int((time.time() + _CHROMIUM_EPOCH_OFFSET) * 1_000_000))


def find_brave_prefs() -> Optional[Path]:
    """Find the Brave browser Default profile Preferences file."""
    prefs = Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "Default" / "Preferences"
    if prefs.is_file():
        return prefs
    return None


def is_brave_installed() -> bool:
    """Check if Brave browser is installed."""
    return (
        shutil.which("brave") is not None
        or shutil.which("brave-browser") is not None
        or (Path.home() / ".config" / "BraveSoftware" / "Brave-Browser").is_dir()
    )


def is_brave_running() -> bool:
    """Check if Brave has any running processes."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "brave"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def extract_domains_from_urls(urls: list[str]) -> list[str]:
    """Extract unique hostnames from a list of URLs."""
    domains: set[str] = set()
    for url in urls:
        parsed = urlparse(url)
        if parsed.hostname:
            domains.add(parsed.hostname)
    return sorted(domains)


def configure_brave_shields(
    domains: list[str],
    disable: bool = True,
) -> tuple[bool, str]:
    """Configure Brave Shields for the given domains.

    Must be called with Brave browser CLOSED — otherwise Brave
    overwrites the Preferences file on exit.

    Args:
        domains: List of hostnames to configure.
        disable: True to disable shields (allow PJe Office), False to re-enable.

    Returns:
        (success, message) tuple.
    """
    prefs_path = find_brave_prefs()
    if prefs_path is None:
        return False, "Brave não encontrado ou sem perfil configurado"

    if is_brave_running():
        return False, "Feche o Brave completamente antes de configurar"

    try:
        prefs_text = prefs_path.read_text(encoding="utf-8")
        prefs = json.loads(prefs_text)
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to read Brave Preferences: %s", exc)
        return False, f"Erro ao ler configurações do Brave: {exc}"

    # Navigate to content_settings.exceptions.braveShields
    profile = prefs.setdefault("profile", {})
    content_settings = profile.setdefault("content_settings", {})
    exceptions = content_settings.setdefault("exceptions", {})
    shields = exceptions.setdefault("braveShields", {})

    # setting=2 means Shields disabled; setting=1 means enabled
    setting_value = 2 if disable else 1
    ts = _chromium_timestamp()
    configured = 0

    for domain in domains:
        key = f"{domain},*"
        existing = shields.get(key, {}).get("setting")
        if existing != setting_value:
            shields[key] = {
                "last_modified": ts,
                "setting": setting_value,
            }
            configured += 1

    if configured == 0:
        return True, "Todos os domínios já estavam configurados"

    # Write back — create backup first
    backup = prefs_path.with_suffix(".bak")
    try:
        shutil.copy2(prefs_path, backup)
    except OSError:
        pass

    try:
        prefs_path.write_text(
            json.dumps(prefs, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    except OSError as exc:
        log.error("Failed to write Brave Preferences: %s", exc)
        # Restore backup
        if backup.is_file():
            shutil.copy2(backup, prefs_path)
        return False, f"Erro ao salvar configurações: {exc}"

    action = "desativado" if disable else "ativado"
    return True, f"Shields {action} em {configured} domínio(s) judicial(is)"


def get_pje_domains() -> list[str]:
    """Return the comprehensive list of PJe-related domains that need
    Shields disabled for PJe Office to work."""
    # Import here to avoid circular imports
    from src.ui.systems_view import JUDICIAL_SYSTEMS

    urls = [s["url"] for s in JUDICIAL_SYSTEMS]
    domains = extract_domains_from_urls(urls)

    # Always include the SSO domain
    if PJE_SSO_DOMAIN not in domains:
        domains.append(PJE_SSO_DOMAIN)

    return sorted(domains)


def import_pjeoffice_cert_nss() -> tuple[bool, str]:
    """Extract PJe Office self-signed certificate and import into
    the Chromium/Brave NSS database (~/.pki/nssdb).

    PJe Office must be running on port 8801 for this to work.
    """
    nss_db = Path.home() / ".pki" / "nssdb"
    if not nss_db.is_dir():
        nss_db.mkdir(parents=True, exist_ok=True)
        # Initialize NSS db
        try:
            subprocess.run(
                ["certutil", "-d", f"sql:{nss_db}", "-N", "--empty-password"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            pass

    # Extract cert from PJe Office HTTPS server
    try:
        extract = subprocess.run(
            ["openssl", "s_client", "-connect", "127.0.0.1:8801"],
            input="",
            capture_output=True, text=True, timeout=5,
        )
    except Exception as exc:
        return False, f"PJe Office não está rodando: {exc}"

    if extract.returncode != 0 and not extract.stdout:
        return False, "Não foi possível conectar ao PJe Office (porta 8801)"

    # Parse PEM cert from openssl output
    try:
        pem_result = subprocess.run(
            ["openssl", "x509", "-outform", "PEM"],
            input=extract.stdout,
            capture_output=True, text=True, timeout=5,
        )
        pem_cert = pem_result.stdout
    except Exception as exc:
        return False, f"Erro ao extrair certificado: {exc}"

    if not pem_cert or "BEGIN CERTIFICATE" not in pem_cert:
        return False, "Certificado do PJe Office não encontrado"

    # Write to temp file and import
    cert_path = Path.home() / ".cache" / "bigcertificados" / "pjeoffice-cert.pem"
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cert_path.write_text(pem_cert, encoding="utf-8")

    # Remove old entry if exists
    subprocess.run(
        ["certutil", "-d", f"sql:{nss_db}", "-D", "-n", "PJeOffice Pro localhost"],
        capture_output=True, text=True, timeout=5,
    )

    # Import as trusted
    try:
        result = subprocess.run(
            [
                "certutil", "-d", f"sql:{nss_db}",
                "-A", "-t", "C,,",
                "-n", "PJeOffice Pro localhost",
                "-i", str(cert_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False, f"Erro ao importar certificado: {result.stderr}"
    except Exception as exc:
        return False, f"certutil falhou: {exc}"

    return True, "Certificado do PJe Office importado no NSS"
