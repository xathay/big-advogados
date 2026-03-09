"""PKCS#11 manager for A3 certificate tokens."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from cryptography import x509

from src.certificate.parser import CertificateInfo, parse_certificate
from src.certificate.token_database import TokenDatabase

log = logging.getLogger(__name__)

try:
    import PyKCS11
    from PyKCS11 import PyKCS11Lib, CKA_CLASS, CKO_CERTIFICATE, CKA_VALUE, CKA_LABEL, CKA_ID
except ImportError:
    PyKCS11 = None  # type: ignore[assignment]


@dataclass
class TokenSlotInfo:
    slot_id: int
    label: str
    manufacturer: str
    model: str
    serial: str
    has_token: bool


class A3Manager:
    """Manages interaction with A3 (PKCS#11) certificate tokens."""

    def __init__(self, token_db: TokenDatabase) -> None:
        self._token_db = token_db
        self._pkcs11: Optional[PyKCS11Lib] = None
        self._current_module: Optional[str] = None
        self._session: Optional[object] = None
        self._lock = threading.Lock()

    @property
    def is_available(self) -> bool:
        return PyKCS11 is not None

    def load_module(self, module_path: str) -> bool:
        """Load a PKCS#11 module (.so library)."""
        if not self.is_available:
            log.error("PyKCS11 not installed")
            return False

        with self._lock:
            try:
                self._close_session()
                self._pkcs11 = PyKCS11Lib()
                self._pkcs11.load(module_path)
                self._current_module = module_path
                log.info("Loaded PKCS#11 module: %s", module_path)
                return True
            except Exception as exc:
                log.error("Failed to load PKCS#11 module %s: %s", module_path, exc)
                self._pkcs11 = None
                self._current_module = None
                return False

    def load_module_for_device(self, vid: int, pid: int) -> bool:
        """Find and load the appropriate PKCS#11 module for a USB device."""
        module_path = self._token_db.find_pkcs11_library(vid, pid)
        if module_path is None:
            log.warning("No PKCS#11 module found for %04x:%04x", vid, pid)
            return False
        return self.load_module(module_path)

    def get_slots(self) -> list[TokenSlotInfo]:
        """List available token slots."""
        if self._pkcs11 is None:
            return []

        slots = []
        with self._lock:
            try:
                for slot_id in self._pkcs11.getSlotList(tokenPresent=True):
                    try:
                        token_info = self._pkcs11.getTokenInfo(slot_id)
                        slots.append(TokenSlotInfo(
                            slot_id=slot_id,
                            label=token_info.label.strip(),
                            manufacturer=token_info.manufacturerID.strip(),
                            model=token_info.model.strip(),
                            serial=token_info.serialNumber.strip(),
                            has_token=True,
                        ))
                    except Exception as exc:
                        log.debug("Could not get token info for slot %d: %s", slot_id, exc)
            except Exception as exc:
                log.error("Failed to enumerate slots: %s", exc)

        return slots

    def login(self, slot_id: int, pin: str) -> bool:
        """Open a session and login with PIN."""
        if self._pkcs11 is None:
            return False

        with self._lock:
            try:
                self._close_session()
                session = self._pkcs11.openSession(
                    slot_id, PyKCS11.CKF_SERIAL_SESSION
                )
                session.login(pin)
                self._session = session
                log.info("Logged in to slot %d", slot_id)
                return True
            except Exception as exc:
                log.error("Login failed for slot %d: %s", slot_id, exc)
                return False

    def list_certificates(self, slot_id: Optional[int] = None) -> list[CertificateInfo]:
        """List certificates from token. Requires prior login or uses slot directly."""
        if self._pkcs11 is None:
            return []

        certs: list[CertificateInfo] = []
        with self._lock:
            try:
                if self._session is None and slot_id is not None:
                    session = self._pkcs11.openSession(
                        slot_id, PyKCS11.CKF_SERIAL_SESSION
                    )
                else:
                    session = self._session

                if session is None:
                    return []

                # Find certificate objects
                objects = session.findObjects([
                    (CKA_CLASS, CKO_CERTIFICATE),
                ])

                for obj in objects:
                    try:
                        attrs = session.getAttributeValue(obj, [
                            CKA_VALUE, CKA_LABEL, CKA_ID,
                        ])
                        der_bytes = bytes(attrs[0])
                        cert = x509.load_der_x509_certificate(der_bytes)
                        cert_info = parse_certificate(cert)
                        certs.append(cert_info)
                    except Exception as exc:
                        log.debug("Could not parse certificate object: %s", exc)

            except Exception as exc:
                log.error("Failed to list certificates: %s", exc)

        return certs

    def logout(self) -> None:
        with self._lock:
            self._close_session()

    def _close_session(self) -> None:
        if self._session is not None:
            try:
                self._session.logout()
            except Exception:
                pass
            try:
                self._session.closeSession()
            except Exception:
                pass
            self._session = None

    @property
    def current_module(self) -> Optional[str]:
        return self._current_module

    def try_all_modules(self) -> Optional[str]:
        """Try loading each known PKCS#11 module until one works."""
        from pathlib import Path

        for module_name in sorted(self._token_db.unique_modules()):
            tokens = self._token_db.lookup_by_module(module_name)
            for token in tokens:
                for path in token.search_paths:
                    if Path(path).is_file():
                        if self.load_module(path):
                            slots = self.get_slots()
                            if slots:
                                return path
        return None
