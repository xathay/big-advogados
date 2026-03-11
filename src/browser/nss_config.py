"""NSS database configuration for Firefox and Chrome/Chromium.

Registers PKCS#11 modules so browsers can use A3 certificate tokens.
Also imports CA certificates for PDF signature validation in Papers/Evince.
Uses certutil and modutil from nss-tools package.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

from src.browser.browser_detect import BrowserProfile, find_all_profiles

log = logging.getLogger(__name__)

MODUTIL_CMD = "modutil"
CERTUTIL_CMD = "certutil"
SHARED_NSS_DB = Path.home() / ".pki" / "nssdb"


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


def import_ca_certificate(
    nss_db_path: Path,
    cert: x509.Certificate,
    nickname: str,
) -> bool:
    """Import a CA certificate into an NSS database as trusted.

    Uses trust flags CT,C,C (trusted for client auth, email, object signing).
    """
    if not ensure_nss_db(nss_db_path):
        log.error("Cannot ensure NSS db at %s", nss_db_path)
        return False

    db_prefix = f"sql:{nss_db_path}"
    pem_data = cert.public_bytes(Encoding.PEM)

    with tempfile.NamedTemporaryFile(suffix=".pem", delete=True) as tmp:
        tmp.write(pem_data)
        tmp.flush()

        try:
            result = subprocess.run(
                [
                    CERTUTIL_CMD, "-A",
                    "-d", db_prefix,
                    "-n", nickname,
                    "-t", "CT,C,C",
                    "-i", tmp.name,
                ],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                log.info("Imported CA '%s' into %s", nickname, nss_db_path)
                return True
            else:
                log.error("certutil import failed: %s", result.stderr.strip())
                return False
        except Exception as exc:
            log.error("Failed to import CA certificate: %s", exc)
            return False


def import_pfx_chain_for_papers(
    pfx_path: str,
    pfx_password: str,
) -> dict[str, bool]:
    """Import all certificates from a PFX into the shared NSS database.

    Imports the signing certificate and its CA chain so that
    Papers/Evince (via poppler+NSS) can validate PDF signatures.

    Returns dict mapping certificate CN → success status.
    """
    from cryptography.hazmat.primitives.serialization import pkcs12

    results: dict[str, bool] = {}
    pfx_file = Path(pfx_path)

    if not pfx_file.is_file():
        return {"Erro": False}

    try:
        pfx_data = pfx_file.read_bytes()
        pwd_bytes = pfx_password.encode("utf-8") if pfx_password else None
        _key, cert, chain = pkcs12.load_key_and_certificates(pfx_data, pwd_bytes)
    except (ValueError, Exception) as exc:
        log.error("Failed to load PFX: %s", exc)
        return {"Erro ao carregar PFX": False}

    all_certs: list[tuple[str, x509.Certificate]] = []

    if cert is not None:
        cn = _extract_cn(cert)
        all_certs.append((cn, cert))

    if chain:
        for ca_cert in chain:
            cn = _extract_cn(ca_cert)
            all_certs.append((f"CA: {cn}", ca_cert))

    for nickname, certificate in all_certs:
        ok = import_ca_certificate(SHARED_NSS_DB, certificate, nickname)
        results[nickname] = ok

    return results


def is_cert_in_nss(nss_db_path: Path, nickname: str) -> bool:
    """Check if a certificate with the given nickname exists in NSS db."""
    db_prefix = f"sql:{nss_db_path}"
    try:
        result = subprocess.run(
            [CERTUTIL_CMD, "-L", "-d", db_prefix, "-n", nickname],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def list_nss_certificates(nss_db_path: Path) -> list[str]:
    """List all certificate nicknames in an NSS database."""
    db_prefix = f"sql:{nss_db_path}"
    try:
        result = subprocess.run(
            [CERTUTIL_CMD, "-L", "-d", db_prefix],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            nicknames = []
            for line in result.stdout.splitlines()[4:]:
                line = line.strip()
                if line and not line.startswith("Certificate Nickname"):
                    parts = line.rsplit(None, 1)
                    if len(parts) >= 1:
                        nicknames.append(parts[0].strip())
            return nicknames
    except Exception as exc:
        log.error("Failed to list NSS certificates: %s", exc)
    return []


def _extract_cn(cert: x509.Certificate) -> str:
    """Extract Common Name from a certificate."""
    try:
        for attr in cert.subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                return str(attr.value)
    except Exception:
        pass
    return cert.subject.rfc4514_string()[:60]
