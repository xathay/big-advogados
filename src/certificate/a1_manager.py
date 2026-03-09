"""A1 certificate manager — handles PFX/P12 files."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from cryptography import x509

from src.certificate.parser import CertificateInfo, parse_certificate
from src.utils.xdg import data_dir

log = logging.getLogger(__name__)


class A1Manager:
    """Manages A1 certificates (PFX/P12 files)."""

    def __init__(self) -> None:
        self._storage_dir = data_dir() / "certificates"
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def load_pfx(self, pfx_path: str, password: str) -> Optional[CertificateInfo]:
        """Load and parse a PFX/P12 file.

        Args:
            pfx_path: Path to the .pfx or .p12 file.
            password: Password to decrypt the PFX.

        Returns:
            CertificateInfo if successful, None otherwise.
        """
        path = Path(pfx_path)
        if not path.is_file():
            log.error("PFX file not found: %s", pfx_path)
            return None

        try:
            pfx_data = path.read_bytes()
            pwd_bytes = password.encode("utf-8") if password else None

            private_key, certificate, chain = pkcs12.load_key_and_certificates(
                pfx_data, pwd_bytes
            )

            if certificate is None:
                log.error("No certificate found in PFX file")
                return None

            info = parse_certificate(certificate)
            log.info("Loaded A1 certificate: %s", info.common_name)
            return info

        except ValueError as exc:
            log.error("Invalid password or corrupted PFX: %s", exc)
            return None
        except Exception as exc:
            log.error("Failed to load PFX: %s", exc)
            return None

    def install_in_nss(
        self, pfx_path: str, password: str, nss_db_path: Path,
    ) -> bool:
        """Install PFX certificate in an NSS database for browser use.

        Uses pk12util from nss-tools.
        """
        import subprocess

        try:
            result = subprocess.run(
                [
                    "pk12util",
                    "-i", pfx_path,
                    "-d", f"sql:{nss_db_path}",
                    "-W", password,
                ],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                log.info("Certificate installed in NSS: %s", nss_db_path)
                return True
            else:
                log.error("pk12util failed: %s", result.stderr)
                return False
        except FileNotFoundError:
            log.error("pk12util not found — install nss package")
            return False
        except Exception as exc:
            log.error("Failed to install certificate: %s", exc)
            return False

    def install_in_all_browsers(self, pfx_path: str, password: str) -> dict[str, bool]:
        """Install PFX in all detected browser NSS databases."""
        from src.browser.browser_detect import find_all_profiles

        results: dict[str, bool] = {}
        seen_dbs: set[str] = set()

        for profile in find_all_profiles():
            db_key = str(profile.nss_db_path)
            if db_key in seen_dbs:
                results[f"{profile.browser} ({profile.name})"] = True
                continue
            seen_dbs.add(db_key)

            success = self.install_in_nss(pfx_path, password, profile.nss_db_path)
            results[f"{profile.browser} ({profile.name})"] = success

        return results

    def get_certificate_chain(self, pfx_path: str, password: str) -> list[CertificateInfo]:
        """Extract the full certificate chain from the PFX."""
        path = Path(pfx_path)
        if not path.is_file():
            return []

        try:
            pfx_data = path.read_bytes()
            pwd_bytes = password.encode("utf-8") if password else None

            private_key, certificate, chain = pkcs12.load_key_and_certificates(
                pfx_data, pwd_bytes
            )

            certs: list[CertificateInfo] = []
            if certificate:
                certs.append(parse_certificate(certificate))
            if chain:
                for ca_cert in chain:
                    certs.append(parse_certificate(ca_cert))
            return certs

        except Exception as exc:
            log.error("Failed to extract chain: %s", exc)
            return []
