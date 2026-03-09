"""X.509 certificate parser with Brazilian ICP-Brasil specific fields."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID, ExtensionOID

log = logging.getLogger(__name__)

# ICP-Brasil OIDs for subject alternative name fields
OID_CPF = "2.16.76.1.3.1"
OID_CNPJ = "2.16.76.1.3.3"
OID_NOME_RESPONSAVEL = "2.16.76.1.3.2"
OID_RG = "2.16.76.1.3.5"
OID_INSS = "2.16.76.1.3.6"
OID_TITULO_ELEITOR = "2.16.76.1.3.7"
OID_OAB = "2.16.76.1.4.2.1"


@dataclass
class CertificateInfo:
    common_name: str = ""
    serial_number: str = ""
    issuer: str = ""
    issuer_cn: str = ""
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None
    cpf: str = ""
    cnpj: str = ""
    email: str = ""
    oab: str = ""
    key_usage: str = ""
    is_expired: bool = False
    days_to_expire: int = 0
    subject_dn: str = ""
    pem_data: str = ""

    @property
    def holder_name(self) -> str:
        return self.common_name.split(":")[0].strip() if self.common_name else ""

    @property
    def validity_status(self) -> str:
        if self.is_expired:
            return "EXPIRADO"
        if self.days_to_expire <= 30:
            return f"EXPIRA EM {self.days_to_expire} DIAS"
        return "VÁLIDO"


def parse_certificate(cert: x509.Certificate) -> CertificateInfo:
    """Parse an X.509 certificate and extract Brazilian ICP-Brasil fields."""
    info = CertificateInfo()

    # Subject fields
    try:
        cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if cn_attrs:
            info.common_name = cn_attrs[0].value
    except Exception:
        pass

    try:
        email_attrs = cert.subject.get_attributes_for_oid(NameOID.EMAIL_ADDRESS)
        if email_attrs:
            info.email = email_attrs[0].value
    except Exception:
        pass

    info.serial_number = format(cert.serial_number, "x").upper()
    info.subject_dn = cert.subject.rfc4514_string()

    # Issuer
    try:
        info.issuer = cert.issuer.rfc4514_string()
        issuer_cn = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
        if issuer_cn:
            info.issuer_cn = issuer_cn[0].value
    except Exception:
        pass

    # Validity
    info.not_before = cert.not_valid_before_utc
    info.not_after = cert.not_valid_after_utc
    now = datetime.now(cert.not_valid_after_utc.tzinfo)
    info.is_expired = now > cert.not_valid_after_utc
    info.days_to_expire = max(0, (cert.not_valid_after_utc - now).days)

    # Key usage
    try:
        ku_ext = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
        ku = ku_ext.value
        usages = []
        if ku.digital_signature:
            usages.append("Assinatura Digital")
        if ku.key_encipherment:
            usages.append("Cifragem de Chave")
        if ku.content_commitment:
            usages.append("Não Repúdio")
        info.key_usage = ", ".join(usages)
    except (x509.ExtensionNotFound, Exception):
        pass

    # ICP-Brasil specific: extract CPF, CNPJ, OAB from SAN otherName
    _extract_icp_brasil_fields(cert, info)

    # PEM data
    info.pem_data = cert.public_bytes(Encoding.PEM).decode("ascii")

    return info


def _extract_icp_brasil_fields(cert: x509.Certificate, info: CertificateInfo) -> None:
    """Extract CPF, CNPJ, and OAB from ICP-Brasil certificate extensions."""
    try:
        san_ext = cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san = san_ext.value

        # Try email from SAN
        if not info.email:
            try:
                emails = san.get_values_for_type(x509.RFC822Name)
                if emails:
                    info.email = emails[0]
            except Exception:
                pass

        # otherName fields (ICP-Brasil specific)
        for name in san:
            if not isinstance(name, x509.OtherName):
                continue

            oid = name.type_id.dotted_string
            raw = name.value

            # Decode the DER-encoded value
            try:
                decoded = _decode_der_string(raw)
            except Exception:
                continue

            if oid == OID_CPF:
                # Format: date(8) + CPF(11) + ...
                cpf_match = re.search(r"\d{11}", decoded)
                if cpf_match:
                    cpf = cpf_match.group()
                    info.cpf = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

            elif oid == OID_CNPJ:
                cnpj_match = re.search(r"\d{14}", decoded)
                if cnpj_match:
                    cnpj = cnpj_match.group()
                    info.cnpj = (
                        f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/"
                        f"{cnpj[8:12]}-{cnpj[12:]}"
                    )

            elif oid == OID_OAB:
                info.oab = decoded.strip()

    except (x509.ExtensionNotFound, Exception) as exc:
        log.debug("Could not extract ICP-Brasil SAN fields: %s", exc)


def _decode_der_string(raw: bytes) -> str:
    """Best-effort decode of a DER-encoded string value."""
    # DER strings typically have a tag byte + length + content
    # Common tags: 0x0C (UTF8String), 0x13 (PrintableString), 0x16 (IA5String)
    if len(raw) < 2:
        return raw.decode("utf-8", errors="replace")

    tag = raw[0]
    if tag in (0x0C, 0x13, 0x16, 0x04):
        length = raw[1]
        start = 2
        if length & 0x80:
            num_bytes = length & 0x7F
            length = int.from_bytes(raw[2:2 + num_bytes], "big")
            start = 2 + num_bytes
        return raw[start:start + length].decode("utf-8", errors="replace")

    # Fallback: try decoding entire value
    return raw.decode("utf-8", errors="replace")


def parse_pfx(pfx_data: bytes, password: str) -> Optional[CertificateInfo]:
    """Parse a PFX/P12 file and extract certificate info."""
    from cryptography.hazmat.primitives.serialization import pkcs12

    try:
        private_key, certificate, chain = pkcs12.load_key_and_certificates(
            pfx_data, password.encode("utf-8") if password else None
        )
        if certificate:
            return parse_certificate(certificate)
    except Exception as exc:
        log.error("Failed to parse PFX: %s", exc)

    return None
