"""Manager for VidaaS Connect cloud certificates.

Handles both PKCS#11 (local virtual token via OpenSC) and REST API
(remote signing) modes for VidaaS Connect certificates.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

from src.certificate.parser import CertificateInfo
from src.utils.vidaas_deps import (
    check_dependencies,
    ensure_pcscd_running,
    find_opensc_module,
    get_missing_packages,
)

if TYPE_CHECKING:
    from src.certificate.a3_manager import A3Manager
    from src.certificate.vidaas_api import VidaaSAPIClient

log = logging.getLogger(__name__)

# Slot labels that indicate a VidaaS virtual token
_VIDAAS_SLOT_KEYWORDS = ("vidaas", "valid", "cloud", "vtoken")


class VidaaSMode(Enum):
    PKCS11 = auto()
    REST_API = auto()


class VidaaSState(Enum):
    DISCONNECTED = auto()
    CHECKING_DEPS = auto()
    STARTING_PCSCD = auto()
    SCANNING_SLOTS = auto()
    WAITING_AUTH = auto()
    CONNECTED = auto()
    ERROR = auto()


@dataclass
class VidaaSStatus:
    state: VidaaSState
    message: str = ""
    mode: VidaaSMode | None = None
    slot_label: str = ""
    slot_id: int = -1


class VidaaSManager:
    """Manages VidaaS Connect certificate lifecycle.

    Provides two connection modes:
    - PKCS#11: Uses OpenSC to access VidaaS virtual token via pcscd.
    - REST_API: Connects directly to VidaaS API for remote signing.
    """

    def __init__(self, a3_manager: A3Manager) -> None:
        self._a3 = a3_manager
        self._state = VidaaSState.DISCONNECTED
        self._mode: VidaaSMode | None = None
        self._lock = threading.Lock()
        self._opensc_path: str | None = None
        self._api_client: VidaaSAPIClient | None = None
        self._active_slot_id: int = -1
        self._active_cert_der: bytes = b""

    @property
    def state(self) -> VidaaSState:
        return self._state

    @property
    def mode(self) -> VidaaSMode | None:
        return self._mode

    @property
    def is_connected(self) -> bool:
        return self._state == VidaaSState.CONNECTED

    @property
    def api_client(self) -> VidaaSAPIClient | None:
        return self._api_client

    def get_status(self) -> VidaaSStatus:
        """Return current VidaaS connection status."""
        return VidaaSStatus(
            state=self._state,
            mode=self._mode,
            slot_id=self._active_slot_id,
        )

    # ── PKCS#11 Mode ──────────────────────────────────────────────────

    def detect_vidaas_token(self) -> VidaaSStatus:
        """Attempt to detect a VidaaS virtual token via PKCS#11.

        Checks dependencies, starts pcscd if needed, loads OpenSC module,
        and scans for VidaaS-like slots.

        Returns VidaaSStatus with the detection result.
        """
        with self._lock:
            self._state = VidaaSState.CHECKING_DEPS

            # Check system dependencies
            deps = check_dependencies()
            missing = get_missing_packages()
            if missing:
                self._state = VidaaSState.ERROR
                return VidaaSStatus(
                    state=self._state,
                    message=f"Pacotes faltando: {', '.join(missing)}",
                )

            # Ensure pcscd is running
            self._state = VidaaSState.STARTING_PCSCD
            if not deps.pcscd_running:
                if not ensure_pcscd_running():
                    self._state = VidaaSState.ERROR
                    return VidaaSStatus(
                        state=self._state,
                        message="Não foi possível iniciar o serviço pcscd",
                    )

            # Find and load OpenSC module
            self._state = VidaaSState.SCANNING_SLOTS
            opensc = deps.opensc_module_path or find_opensc_module()
            if opensc is None:
                self._state = VidaaSState.ERROR
                return VidaaSStatus(
                    state=self._state,
                    message="Módulo opensc-pkcs11.so não encontrado",
                )

            self._opensc_path = opensc

            if not self._a3.load_module(opensc):
                self._state = VidaaSState.ERROR
                return VidaaSStatus(
                    state=self._state,
                    message=f"Falha ao carregar módulo {opensc}",
                )

            # Scan slots for VidaaS token
            slots = self._a3.get_slots()
            if not slots:
                self._state = VidaaSState.DISCONNECTED
                return VidaaSStatus(
                    state=self._state,
                    message="Nenhum token detectado — verifique o app VidaaS no celular",
                )

            # Look for VidaaS-specific slot
            vidaas_slot = None
            for slot in slots:
                label_lower = slot.label.lower()
                if any(kw in label_lower for kw in _VIDAAS_SLOT_KEYWORDS):
                    vidaas_slot = slot
                    break

            # If no VidaaS-specific slot found, use first available
            if vidaas_slot is None:
                vidaas_slot = slots[0]
                log.info(
                    "No VidaaS-labeled slot found; using first slot: %s",
                    vidaas_slot.label,
                )

            self._active_slot_id = vidaas_slot.slot_id
            self._mode = VidaaSMode.PKCS11
            self._state = VidaaSState.CONNECTED

            return VidaaSStatus(
                state=self._state,
                mode=self._mode,
                message=f"Token detectado: {vidaas_slot.label}",
                slot_label=vidaas_slot.label,
                slot_id=vidaas_slot.slot_id,
            )

    def connect_pkcs11(self, pin: str) -> VidaaSStatus:
        """Login to the VidaaS PKCS#11 slot with PIN.

        Must call detect_vidaas_token() first.
        """
        if self._active_slot_id < 0:
            return VidaaSStatus(
                state=VidaaSState.ERROR,
                message="Token não detectado — execute a detecção primeiro",
            )

        with self._lock:
            if not self._a3.login(self._active_slot_id, pin):
                self._state = VidaaSState.ERROR
                return VidaaSStatus(
                    state=self._state,
                    message="PIN incorreto ou falha no login",
                )

            self._state = VidaaSState.CONNECTED
            self._mode = VidaaSMode.PKCS11
            return VidaaSStatus(
                state=self._state,
                mode=self._mode,
                message="Conectado via PKCS#11",
                slot_id=self._active_slot_id,
            )

    def list_certificates(self) -> list[CertificateInfo]:
        """List certificates from the connected VidaaS source."""
        if self._mode == VidaaSMode.PKCS11:
            return self._a3.list_certificates(self._active_slot_id)

        if self._mode == VidaaSMode.REST_API and self._api_client is not None:
            return self._list_certificates_api()

        return []

    def get_cert_der(self) -> bytes:
        """Return DER bytes of the active certificate from PKCS#11."""
        return self._active_cert_der

    def set_active_cert_der(self, cert_der: bytes) -> None:
        """Set the active certificate DER bytes (from token enumeration)."""
        self._active_cert_der = cert_der

    # ── REST API Mode ─────────────────────────────────────────────────

    def connect_api(
        self,
        client_id: str,
        client_secret: str,
        username: str,
    ) -> VidaaSStatus:
        """Connect via VidaaS REST API.

        Note: The API client is a scaffold — endpoints must be confirmed
        with Valid Certificadora's official documentation.
        """
        from src.certificate.vidaas_api import VidaaSAPIClient, VidaaSCredentials

        creds = VidaaSCredentials(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
        )
        self._api_client = VidaaSAPIClient(creds)

        with self._lock:
            self._state = VidaaSState.WAITING_AUTH
            if not self._api_client.authenticate():
                self._state = VidaaSState.ERROR
                return VidaaSStatus(
                    state=self._state,
                    message="Falha na autenticação com API VidaaS",
                )

            self._mode = VidaaSMode.REST_API
            self._state = VidaaSState.CONNECTED
            return VidaaSStatus(
                state=self._state,
                mode=self._mode,
                message="Conectado via API REST",
            )

    def _list_certificates_api(self) -> list[CertificateInfo]:
        """List certificates from VidaaS REST API."""
        if self._api_client is None:
            return []

        from cryptography import x509

        from src.certificate.parser import parse_certificate

        certs: list[CertificateInfo] = []
        for vc in self._api_client.list_certificates():
            try:
                cert = x509.load_pem_x509_certificate(vc.cert_pem.encode())
                certs.append(parse_certificate(cert))
            except Exception as exc:
                log.debug("Could not parse VidaaS API certificate: %s", exc)
        return certs

    # ── Disconnect ────────────────────────────────────────────────────

    def disconnect(self) -> None:
        """Disconnect from VidaaS (both modes)."""
        with self._lock:
            if self._mode == VidaaSMode.PKCS11:
                self._a3.logout()
            self._api_client = None
            self._mode = None
            self._state = VidaaSState.DISCONNECTED
            self._active_slot_id = -1
            self._active_cert_der = b""
            log.info("Disconnected from VidaaS")
