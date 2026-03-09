"""App lock — optional password protection for BigCertificados.

Stores a PBKDF2-hashed password in ~/.config/bigcertificados/applock.json.
The password never leaves the machine and is never stored in plaintext.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from src.utils.xdg import config_dir

log = logging.getLogger(__name__)

LOCK_FILE = "applock.json"
PBKDF2_ITERATIONS = 600_000  # OWASP recommended minimum for SHA-256


def _lock_path() -> Path:
    return config_dir() / LOCK_FILE


def _hash_password(password: str, salt: bytes) -> str:
    """Derive a key from the password using PBKDF2-HMAC-SHA256."""
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return dk.hex()


def is_lock_enabled() -> bool:
    """Check if password protection is configured."""
    path = _lock_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("hash") and data.get("salt"))
    except (json.JSONDecodeError, OSError):
        return False


def set_password(password: str) -> None:
    """Set (or update) the app lock password."""
    salt = secrets.token_bytes(32)
    pw_hash = _hash_password(password, salt)

    data = {
        "hash": pw_hash,
        "salt": salt.hex(),
        "iterations": PBKDF2_ITERATIONS,
    }
    path = _lock_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Restrict file permissions to owner only
    path.chmod(0o600)
    log.info("App lock password set")


def verify_password(password: str) -> bool:
    """Verify a password against the stored hash."""
    path = _lock_path()
    if not path.exists():
        return False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        salt = bytes.fromhex(data["salt"])
        stored_hash = data["hash"]
        iterations = data.get("iterations", PBKDF2_ITERATIONS)
    except (json.JSONDecodeError, OSError, KeyError, ValueError):
        log.warning("Corrupted lock file")
        return False

    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return secrets.compare_digest(dk.hex(), stored_hash)


def remove_password() -> None:
    """Remove the app lock password (disables protection)."""
    path = _lock_path()
    if path.exists():
        path.unlink()
        log.info("App lock password removed")
