"""VidaaS Connect REST API client.

Scaffold implementation for the VidaaS Connect cloud signing API.
Actual endpoints and authentication flow must be confirmed with
Valid Certificadora's official documentation or SDK.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

log = logging.getLogger(__name__)

_BASE_URL = "https://certificado.vidaas.com.br/v0"
_AUTH_URL = "https://certificado.vidaas.com.br/v0/oauth/token"
_DEFAULT_TIMEOUT = 30  # seconds


@dataclass
class VidaaSCredentials:
    client_id: str
    client_secret: str
    username: str


@dataclass
class VidaaSCertificate:
    cert_id: str
    subject_cn: str
    issuer_cn: str
    not_before: str
    not_after: str
    key_type: str
    cert_pem: str


class VidaaSSignatureStatus(Enum):
    PENDING = auto()
    AUTHORIZED = auto()
    COMPLETED = auto()
    REJECTED = auto()
    EXPIRED = auto()
    ERROR = auto()


@dataclass
class VidaaSSignatureResult:
    status: VidaaSSignatureStatus
    transaction_id: str = ""
    signature_bytes: bytes = b""
    error_message: str = ""


class VidaaSAPIError(Exception):
    """Error from VidaaS API."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class VidaaSAPIClient:
    """HTTP client for VidaaS Connect REST API.

    Uses urllib from stdlib to avoid extra dependencies.
    All network calls include timeouts and proper error handling.
    """

    def __init__(self, credentials: VidaaSCredentials) -> None:
        self._credentials = credentials
        self._access_token: str | None = None
        self._token_expiry: float = 0.0

    @property
    def is_authenticated(self) -> bool:
        return (
            self._access_token is not None
            and time.time() < self._token_expiry
        )

    def authenticate(self) -> bool:
        """Authenticate with VidaaS API using OAuth2 client_credentials."""
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
            "username": self._credentials.username,
            "scope": "sign",
        }

        try:
            data = self._post(_AUTH_URL, payload, authenticated=False)
            self._access_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            self._token_expiry = time.time() + expires_in - 60  # margin
            log.info("VidaaS API authenticated successfully")
            return self._access_token is not None
        except VidaaSAPIError as exc:
            log.error("VidaaS authentication failed: %s", exc)
            return False

    def list_certificates(self) -> list[VidaaSCertificate]:
        """List certificates available in the user's VidaaS account."""
        try:
            data = self._get(f"{_BASE_URL}/certificates")
            certs: list[VidaaSCertificate] = []
            for item in data.get("certificates", []):
                certs.append(VidaaSCertificate(
                    cert_id=item.get("id", ""),
                    subject_cn=item.get("subject_cn", ""),
                    issuer_cn=item.get("issuer_cn", ""),
                    not_before=item.get("not_before", ""),
                    not_after=item.get("not_after", ""),
                    key_type=item.get("key_type", "RSA"),
                    cert_pem=item.get("certificate", ""),
                ))
            return certs
        except VidaaSAPIError as exc:
            log.error("Failed to list VidaaS certificates: %s", exc)
            return []

    def request_signature(
        self,
        cert_id: str,
        hash_bytes: bytes,
        hash_algorithm: str = "sha256",
    ) -> str:
        """Request a signature — triggers push notification to phone.

        Returns transaction_id for polling.
        """
        payload = {
            "certificate_id": cert_id,
            "hash": base64.b64encode(hash_bytes).decode("ascii"),
            "hash_algorithm": hash_algorithm,
            "signature_type": "CAdES",
        }

        data = self._post(f"{_BASE_URL}/sign", payload)
        tx_id = data.get("transaction_id", "")
        if not tx_id:
            raise VidaaSAPIError("No transaction_id in response")

        log.info("VidaaS signature requested, transaction: %s", tx_id)
        return tx_id

    def check_signature_status(
        self,
        transaction_id: str,
    ) -> VidaaSSignatureResult:
        """Check the status of a pending signature."""
        try:
            data = self._get(
                f"{_BASE_URL}/sign/{transaction_id}/status",
            )
            status_str = data.get("status", "error").lower()
            status_map = {
                "pending": VidaaSSignatureStatus.PENDING,
                "authorized": VidaaSSignatureStatus.AUTHORIZED,
                "completed": VidaaSSignatureStatus.COMPLETED,
                "rejected": VidaaSSignatureStatus.REJECTED,
                "expired": VidaaSSignatureStatus.EXPIRED,
            }
            status = status_map.get(status_str, VidaaSSignatureStatus.ERROR)

            result = VidaaSSignatureResult(
                status=status,
                transaction_id=transaction_id,
                error_message=data.get("error", ""),
            )

            if status == VidaaSSignatureStatus.COMPLETED:
                sig_b64 = data.get("signature", "")
                if sig_b64:
                    result.signature_bytes = base64.b64decode(sig_b64)

            return result
        except VidaaSAPIError as exc:
            return VidaaSSignatureResult(
                status=VidaaSSignatureStatus.ERROR,
                transaction_id=transaction_id,
                error_message=str(exc),
            )

    def wait_for_signature(
        self,
        transaction_id: str,
        timeout: int = 120,
        poll_interval: float = 2.0,
        on_status: Callable[[VidaaSSignatureResult], None] | None = None,
    ) -> VidaaSSignatureResult:
        """Poll until signature is complete, rejected, or times out.

        Args:
            transaction_id: ID from request_signature().
            timeout: Max seconds to wait.
            poll_interval: Seconds between polls.
            on_status: Optional callback(VidaaSSignatureResult) for UI updates.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.check_signature_status(transaction_id)

            if on_status is not None:
                on_status(result)

            if result.status == VidaaSSignatureStatus.COMPLETED:
                return result
            if result.status in (
                VidaaSSignatureStatus.REJECTED,
                VidaaSSignatureStatus.EXPIRED,
                VidaaSSignatureStatus.ERROR,
            ):
                return result

            time.sleep(poll_interval)

        return VidaaSSignatureResult(
            status=VidaaSSignatureStatus.EXPIRED,
            transaction_id=transaction_id,
            error_message="Tempo de autorização expirado",
        )

    # ── HTTP helpers ──────────────────────────────────────────────────

    def _get(self, url: str) -> dict:
        """Authenticated GET request."""
        req = urllib.request.Request(url, method="GET")
        self._add_auth_header(req)
        return self._execute(req)

    def _post(
        self,
        url: str,
        payload: dict,
        authenticated: bool = True,
    ) -> dict:
        """POST request with JSON body."""
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        if authenticated:
            self._add_auth_header(req)
        return self._execute(req)

    def _add_auth_header(self, req: urllib.request.Request) -> None:
        if self._access_token:
            req.add_header("Authorization", f"Bearer {self._access_token}")

    def _execute(self, req: urllib.request.Request) -> dict:
        """Execute an HTTP request and return parsed JSON."""
        try:
            with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
                data = resp.read()
                return json.loads(data)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            log.error(
                "VidaaS API HTTP %d: %s", exc.code, body[:500],
            )
            raise VidaaSAPIError(
                f"HTTP {exc.code}: {body[:200]}", exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise VidaaSAPIError(f"Connection error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise VidaaSAPIError(f"Invalid JSON response: {exc}") from exc
