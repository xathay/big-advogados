#!/usr/bin/env python3
"""BigCertificados WebSigner — native messaging host.

Replaces the Softplan websigner binary, implementing the same protocol
so the Web Signer browser extension can list certificates and sign data
using certificates managed by BigCertificados.

Protocol: Native Messaging (4-byte LE length prefix + JSON).
Launched by Firefox/Chrome when the Web Signer extension connects.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
import subprocess
import sys
import tempfile
from base64 import b64decode, b64encode
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Logging — write to file so it doesn't contaminate stdout (native messaging)
# ---------------------------------------------------------------------------

LOG_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "big-certificados"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_DIR / "websigner-host.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("websigner-host")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "big-certificados"
CONFIG_FILE = CONFIG_DIR / "websigner.json"
REPORTED_VERSION = "2.15.4"

# Digest algorithm OID → name mapping
DIGEST_OIDS: dict[str, str] = {
    "1.3.14.3.2.26": "sha1",
    "2.16.840.1.101.3.4.2.1": "sha256",
    "2.16.840.1.101.3.4.2.2": "sha384",
    "2.16.840.1.101.3.4.2.3": "sha512",
}

DIGEST_NAMES: dict[str, str] = {
    "sha-1": "sha1",
    "sha1": "sha1",
    "sha-256": "sha256",
    "sha256": "sha256",
    "sha-384": "sha384",
    "sha384": "sha384",
    "sha-512": "sha512",
    "sha512": "sha512",
}


# ---------------------------------------------------------------------------
# Native messaging I/O
# ---------------------------------------------------------------------------

def read_message() -> Optional[dict]:
    """Read one native messaging message from stdin."""
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length or len(raw_length) != 4:
        return None
    length = struct.unpack("<I", raw_length)[0]
    if length > 10 * 1024 * 1024:
        return None
    data = sys.stdin.buffer.read(length)
    if len(data) != length:
        return None
    return json.loads(data)


def send_message(msg: dict) -> None:
    """Send one native messaging message to stdout."""
    data = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def reply_success(request_id: str, response: Any) -> None:
    send_message({"requestId": request_id, "success": True, "response": response})


def reply_error(request_id: str, message: str, code: str = "error") -> None:
    send_message({
        "requestId": request_id,
        "success": False,
        "exception": {"message": message, "code": code},
    })


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load BigCertificados websigner config."""
    if CONFIG_FILE.is_file():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# NSS database discovery
# ---------------------------------------------------------------------------

def find_nss_databases() -> list[Path]:
    """Find all NSS databases on the system."""
    paths: list[Path] = []

    # Firefox profiles — check both traditional and XDG paths
    for base in [Path.home() / ".mozilla" / "firefox", Path.home() / ".config" / "mozilla" / "firefox"]:
        if not base.is_dir():
            continue
        ini = base / "profiles.ini"
        if ini.is_file():
            for profile_path in _parse_profiles_ini(base, ini):
                if (profile_path / "cert9.db").exists():
                    paths.append(profile_path)
        else:
            for d in base.iterdir():
                if d.is_dir() and (d / "cert9.db").exists():
                    paths.append(d)

    # Shared NSS database (Chromium-based browsers)
    shared = Path.home() / ".pki" / "nssdb"
    if shared.is_dir() and (shared / "cert9.db").exists():
        paths.append(shared)

    return paths


def _parse_profiles_ini(base: Path, ini: Path) -> list[Path]:
    """Parse Firefox profiles.ini and return profile paths."""
    results: list[Path] = []
    section: dict[str, str] = {}
    for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("[Profile"):
            if section:
                _emit_profile(base, section, results)
            section = {}
        elif "=" in line:
            key, _, val = line.partition("=")
            section[key.strip()] = val.strip()
    if section:
        _emit_profile(base, section, results)
    return results


def _emit_profile(base: Path, section: dict[str, str], out: list[Path]) -> None:
    path_str = section.get("Path", "")
    if not path_str:
        return
    is_relative = section.get("IsRelative", "1") == "1"
    profile_path = base / path_str if is_relative else Path(path_str)
    if profile_path.is_dir():
        out.append(profile_path)


# ---------------------------------------------------------------------------
# Certificate operations
# ---------------------------------------------------------------------------

def list_certificates_from_nss() -> list[dict]:
    """List user certificates from all NSS databases."""
    certs: list[dict] = []
    seen_thumbprints: set[str] = set()

    for nss_path in find_nss_databases():
        try:
            result = subprocess.run(
                ["certutil", "-L", "-d", f"sql:{nss_path}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                continue

            for line in result.stdout.splitlines()[4:]:
                line = line.strip()
                if not line or line.startswith("Certificate Nickname"):
                    continue
                # Parse: nickname + spaces + trust flags
                parts = line.rsplit(None, 1)
                if len(parts) < 2:
                    continue
                nickname = parts[0].strip()
                trust = parts[1].strip()

                # Only user certificates (private key present)
                if trust != "u,u,u":
                    continue

                cert_info = _extract_cert_from_nss(nss_path, nickname)
                if cert_info and cert_info["thumbprint"] not in seen_thumbprints:
                    seen_thumbprints.add(cert_info["thumbprint"])
                    certs.append(cert_info)

        except Exception as exc:
            log.error("Failed to list certs from %s: %s", nss_path, exc)

    return certs


def _extract_cert_from_nss(nss_path: Path, nickname: str) -> Optional[dict]:
    """Extract a certificate's details from NSS database."""
    try:
        # Get DER-encoded certificate
        result = subprocess.run(
            ["certutil", "-L", "-d", f"sql:{nss_path}", "-n", nickname, "-r"],
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        der_data = result.stdout
        if not der_data:
            return None

        thumbprint = hashlib.sha1(der_data).hexdigest()

        # Parse certificate using cryptography library
        from cryptography import x509

        cert = x509.load_der_x509_certificate(der_data)
        subject_name = cert.subject.rfc4514_string()
        issuer_name = cert.issuer.rfc4514_string()

        # Extract CN for display
        subject_cn = ""
        issuer_cn = ""
        for attr in cert.subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                subject_cn = str(attr.value)
                break
        for attr in cert.issuer:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                issuer_cn = str(attr.value)
                break

        return {
            "thumbprint": thumbprint,
            "subjectName": subject_name,
            "issuerName": issuer_name,
            "content": b64encode(der_data).decode("ascii"),
            "validityStart": cert.not_valid_before_utc.isoformat(),
            "validityEnd": cert.not_valid_after_utc.isoformat(),
            "pkiBrazil": {
                "cpf": _extract_cpf(cert),
            },
            # Store NSS path + nickname for signing
            "_nssDbPath": str(nss_path),
            "_nssNickname": nickname,
        }
    except Exception as exc:
        log.error("Failed to extract cert '%s' from %s: %s", nickname, nss_path, exc)
        return None


def _extract_cpf(cert) -> str:
    """Extract CPF from ICP-Brasil certificate."""
    from cryptography import x509 as x509mod

    try:
        san = cert.extensions.get_extension_for_oid(
            x509mod.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        for name in san.value:
            if isinstance(name, x509mod.OtherName):
                # CPF OID: 2.16.76.1.3.1
                if name.type_id.dotted_string == "2.16.76.1.3.1":
                    raw = name.value
                    # DER: skip tag+length, decode UTF-8
                    text = raw[2:].decode("utf-8", errors="replace") if len(raw) > 2 else ""
                    # CPF is digits 8..19 in the OtherName value
                    if len(text) >= 19:
                        return text[8:19]
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# PFX operations — for signing
# ---------------------------------------------------------------------------

_pfx_cache: dict[str, tuple] = {}  # thumbprint → (private_key, cert, chain)


def _find_pfx_path() -> Optional[str]:
    """Find the user's PFX file from BigCertificados config or known locations."""
    config = load_config()
    pfx_path = config.get("pfx_path")
    if pfx_path and Path(pfx_path).is_file():
        return pfx_path

    # Search known directories
    search_dirs = [
        Path.home() / "Nextcloud" / "Certificados Digitais (A1 e A3)",
        Path.home() / "Certificados",
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path.home(),
    ]
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in d.rglob("*.p12"):
            return str(f)
        for f in d.rglob("*.pfx"):
            return str(f)
    return None


def _ask_password(pfx_path: str) -> Optional[str]:
    """Prompt the user for a PFX password using a GUI dialog."""
    filename = os.path.basename(pfx_path)

    # Try zenity first (GNOME), then kdialog (KDE)
    for cmd in [
        [
            "zenity", "--password",
            "--title=Big Advogados — Senha do Certificado",
            f"--text=Digite a senha do certificado:\n{filename}",
        ],
        [
            "kdialog", "--password",
            f"Big Advogados — Senha do certificado:\n{filename}",
            "--title", "Big Advogados",
        ],
    ]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return result.stdout.strip()
            return None  # User cancelled
        except FileNotFoundError:
            continue
    return None


def _load_pfx(pfx_path: str, password: str) -> Optional[tuple]:
    """Load a PFX file and return (private_key, cert, chain)."""
    from cryptography.hazmat.primitives.serialization import pkcs12

    try:
        pfx_data = Path(pfx_path).read_bytes()
        pwd_bytes = password.encode("utf-8") if password else None
        private_key, cert, chain = pkcs12.load_key_and_certificates(pfx_data, pwd_bytes)
        return (private_key, cert, chain)
    except Exception as exc:
        log.error("Failed to load PFX: %s", exc)
        return None


def _get_private_key_for_thumbprint(thumbprint: str):
    """Get the private key for a certificate by thumbprint, loading PFX if needed."""
    # Check cache
    if thumbprint in _pfx_cache:
        return _pfx_cache[thumbprint][0]

    pfx_path = _find_pfx_path()
    if not pfx_path:
        log.error("No PFX file found for signing")
        return None

    password = _ask_password(pfx_path)
    if password is None:
        log.info("User cancelled password dialog")
        return None

    loaded = _load_pfx(pfx_path, password)
    if not loaded:
        return None

    private_key, cert, chain = loaded

    # Verify thumbprint matches
    from cryptography.hazmat.primitives.serialization import Encoding

    cert_der = cert.public_bytes(Encoding.DER)
    cert_thumb = hashlib.sha1(cert_der).hexdigest()

    if cert_thumb == thumbprint:
        _pfx_cache[thumbprint] = loaded
        return private_key

    log.error("PFX thumbprint %s doesn't match requested %s", cert_thumb, thumbprint)
    return None


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def _resolve_digest_algorithm(alg: str) -> str:
    """Convert digest algorithm OID or name to a normalized name."""
    lower = alg.lower().replace(" ", "").replace("-", "")
    if alg in DIGEST_OIDS:
        return DIGEST_OIDS[alg]
    if lower in DIGEST_NAMES:
        return DIGEST_NAMES[lower]
    # Try as-is
    return lower


def sign_hash(thumbprint: str, hash_b64: str, digest_algorithm: str) -> Optional[str]:
    """Sign a pre-computed hash. Returns base64 signature."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, utils

    private_key = _get_private_key_for_thumbprint(thumbprint)
    if private_key is None:
        return None

    hash_bytes = b64decode(hash_b64)
    alg_name = _resolve_digest_algorithm(digest_algorithm)

    alg_map = {
        "sha1": hashes.SHA1(),
        "sha256": hashes.SHA256(),
        "sha384": hashes.SHA384(),
        "sha512": hashes.SHA512(),
    }
    hash_alg = alg_map.get(alg_name)
    if hash_alg is None:
        log.error("Unsupported digest algorithm: %s", digest_algorithm)
        return None

    try:
        signature = private_key.sign(
            hash_bytes,
            padding.PKCS1v15(),
            utils.Prehashed(hash_alg),
        )
        return b64encode(signature).decode("ascii")
    except Exception as exc:
        log.error("Signing failed: %s", exc)
        return None


def sign_data(thumbprint: str, data_b64: str, digest_algorithm: str) -> Optional[str]:
    """Sign raw data. Returns base64 signature."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key = _get_private_key_for_thumbprint(thumbprint)
    if private_key is None:
        return None

    data_bytes = b64decode(data_b64)
    alg_name = _resolve_digest_algorithm(digest_algorithm)

    alg_map = {
        "sha1": hashes.SHA1(),
        "sha256": hashes.SHA256(),
        "sha384": hashes.SHA384(),
        "sha512": hashes.SHA512(),
    }
    hash_alg = alg_map.get(alg_name)
    if hash_alg is None:
        log.error("Unsupported digest algorithm: %s", digest_algorithm)
        return None

    try:
        signature = private_key.sign(data_bytes, padding.PKCS1v15(), hash_alg)
        return b64encode(signature).decode("ascii")
    except Exception as exc:
        log.error("Signing failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def handle_command(message: dict) -> None:
    """Dispatch a command from the extension."""
    request_id = message.get("requestId", "")
    command = message.get("command", "")
    request = message.get("request", {})

    log.info("Command: %s (requestId=%s, domain=%s)", command, request_id, message.get("domain", "?"))

    try:
        if command == "getInfo":
            reply_success(request_id, {"os": "Linux", "version": REPORTED_VERSION})

        elif command == "listCertificates":
            certs = list_certificates_from_nss()
            # Strip internal fields before sending to extension
            clean_certs = []
            for c in certs:
                clean = {k: v for k, v in c.items() if not k.startswith("_")}
                clean_certs.append(clean)
            reply_success(request_id, clean_certs)

        elif command == "readCertificate":
            cert_thumb = request.get("certificateThumbprint", "")
            certs = list_certificates_from_nss()
            for c in certs:
                if c["thumbprint"] == cert_thumb:
                    reply_success(request_id, c["content"])
                    return
            reply_error(request_id, f"Certificate not found: {cert_thumb}", "cert_not_found")

        elif command == "signHash":
            cert_thumb = request.get("certificateThumbprint", "")
            hash_value = request.get("hash", "")
            digest_alg = request.get("digestAlgorithm", "")
            log.info("signHash: thumb=%s..., alg=%s, hash_len=%d",
                     cert_thumb[:16], digest_alg, len(hash_value))
            sig = sign_hash(cert_thumb, hash_value, digest_alg)
            if sig:
                log.info("signHash: success, sig_len=%d", len(sig))
                reply_success(request_id, sig)
            else:
                log.error("signHash: failed")
                reply_error(request_id, "Signing failed or was cancelled", "sign_error")

        elif command == "signData":
            cert_thumb = request.get("certificateThumbprint", "")
            data = request.get("data", "")
            digest_alg = request.get("digestAlgorithm", "")
            log.info("signData: thumb=%s..., alg=%s, data_len=%d",
                     cert_thumb[:16], digest_alg, len(data))
            sig = sign_data(cert_thumb, data, digest_alg)
            if sig:
                log.info("signData: success, sig_len=%d", len(sig))
                reply_success(request_id, sig)
            else:
                log.error("signData: failed")
                reply_error(request_id, "Signing failed or was cancelled", "sign_error")

        elif command in ("authorizeSignatures", "preauthorizeSignatures"):
            # Extension asks native host to show authorization dialog.
            # We auto-approve and return the certificate info so the
            # extension can proceed to signData/signHash.
            cert_thumb = request.get("certificateThumbprint", "")
            cert_data = None
            for c in list_certificates_from_nss():
                if c["thumbprint"] == cert_thumb:
                    cert_data = c
                    break
            reply_success(request_id, {
                "authorized": True,
                "dontAskAgain": True,
                "certificate": {
                    "thumbprint": cert_thumb,
                    "subjectName": cert_data["subjectName"] if cert_data else "",
                    "issuerName": cert_data["issuerName"] if cert_data else "",
                },
            })

        elif command == "signHashBatch":
            cert_thumb = request.get("certificateThumbprint", "")
            batch = request.get("batch", [])
            digest_alg = request.get("digestAlgorithm", "")
            signatures = []
            for item in batch:
                h = item.get("hash", item) if isinstance(item, dict) else item
                sig = sign_hash(cert_thumb, h, digest_alg)
                if sig is None:
                    reply_error(request_id, "Batch signing failed", "sign_error")
                    return
                signatures.append(sig)
            reply_success(request_id, signatures)

        else:
            log.warning("Unknown command: %s", command)
            reply_error(request_id, f"Unknown command: {command}", "unknown_command")

    except Exception as exc:
        log.exception("Error handling command %s", command)
        reply_error(request_id, str(exc), "internal_error")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("BigCertificados WebSigner native host started (PID %d)", os.getpid())
    try:
        while True:
            message = read_message()
            if message is None:
                log.info("stdin closed, shutting down")
                break
            handle_command(message)
            # Check keepAlive
            if not message.get("keepAlive", True):
                log.info("keepAlive=false, shutting down")
                break
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("Fatal error in main loop")
    finally:
        # Clear sensitive data
        _pfx_cache.clear()
        log.info("Shutdown complete")


if __name__ == "__main__":
    main()
