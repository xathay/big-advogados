"""Database of Brazilian digital certificate tokens and their PKCS#11 modules.

Maps USB vendor:product IDs to token metadata and PKCS#11 library paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class TokenInfo:
    vendor: str
    model: str
    vid: int
    pid: int
    pkcs11_module: str
    search_paths: tuple[str, ...] = ()
    description: str = ""
    is_reader: bool = False  # True if it's a smartcard reader, not a standalone token


def _usb_key(vid: int, pid: int) -> str:
    return f"{vid:04x}:{pid:04x}"


# ---------------------------------------------------------------------------
# Comprehensive list of tokens used in Brazil for digital certificates
# ---------------------------------------------------------------------------

_TOKEN_LIST: list[TokenInfo] = [
    # ── SafeNet / Thales ──────────────────────────────────────────────
    TokenInfo(
        vendor="SafeNet (Thales)", model="eToken 5110",
        vid=0x0529, pid=0x0620,
        pkcs11_module="libeToken.so",
        search_paths=(
            "/usr/lib/libeToken.so",
            "/usr/lib64/libeToken.so",
            "/usr/lib/x86_64-linux-gnu/libeToken.so",
            "/opt/safenet/lib/libeToken.so",
        ),
        description="Token USB criptográfico, muito usado por CAs brasileiras",
    ),
    TokenInfo(
        vendor="SafeNet (Thales)", model="eToken 5110+ FIPS",
        vid=0x0529, pid=0x0620,
        pkcs11_module="libeToken.so",
        search_paths=(
            "/usr/lib/libeToken.so",
            "/usr/lib64/libeToken.so",
        ),
        description="Versão FIPS 140-2 do eToken 5110",
    ),
    TokenInfo(
        vendor="SafeNet (Thales)", model="eToken 5300",
        vid=0x0529, pid=0x0621,
        pkcs11_module="libeToken.so",
        search_paths=(
            "/usr/lib/libeToken.so",
            "/usr/lib64/libeToken.so",
        ),
        description="Token USB-C criptográfico",
    ),
    TokenInfo(
        vendor="SafeNet (Thales)", model="eToken 5300-C",
        vid=0x0529, pid=0x0621,
        pkcs11_module="libeToken.so",
        search_paths=(
            "/usr/lib/libeToken.so",
            "/usr/lib64/libeToken.so",
        ),
        description="Token USB-C compacto",
    ),
    TokenInfo(
        vendor="SafeNet (Thales)", model="eToken 7300",
        vid=0x0529, pid=0x0622,
        pkcs11_module="libeToken.so",
        search_paths=(
            "/usr/lib/libeToken.so",
            "/usr/lib64/libeToken.so",
        ),
        description="Token USB com display",
    ),
    TokenInfo(
        vendor="SafeNet (Thales)", model="eToken PRO 72K",
        vid=0x0529, pid=0x0600,
        pkcs11_module="libeTPkcs11.so",
        search_paths=(
            "/usr/lib/libeTPkcs11.so",
            "/usr/lib64/libeTPkcs11.so",
        ),
        description="Token USB legado (descontinuado, ainda em uso)",
    ),
    TokenInfo(
        vendor="SafeNet (Thales)", model="eToken PRO Java",
        vid=0x0529, pid=0x0514,
        pkcs11_module="libeTPkcs11.so",
        search_paths=(
            "/usr/lib/libeTPkcs11.so",
            "/usr/lib64/libeTPkcs11.so",
        ),
        description="Token USB legado baseado em Java Card",
    ),

    # ── Gemalto / Thales ──────────────────────────────────────────────
    TokenInfo(
        vendor="Gemalto (Thales)", model="IDBridge CT40",
        vid=0x08E6, pid=0x3437,
        pkcs11_module="libIDPrimePKCS11.so",
        search_paths=(
            "/usr/lib/libIDPrimePKCS11.so",
            "/usr/lib64/libIDPrimePKCS11.so",
            "/usr/lib/x86_64-linux-gnu/libIDPrimePKCS11.so",
        ),
        description="Leitor de smartcard USB Gemalto",
        is_reader=True,
    ),
    TokenInfo(
        vendor="Gemalto (Thales)", model="IDBridge CT710",
        vid=0x08E6, pid=0x3438,
        pkcs11_module="libIDPrimePKCS11.so",
        search_paths=(
            "/usr/lib/libIDPrimePKCS11.so",
            "/usr/lib64/libIDPrimePKCS11.so",
        ),
        description="Leitor USB de contato e sem contato",
        is_reader=True,
    ),
    TokenInfo(
        vendor="Gemalto (Thales)", model="IDBridge K30",
        vid=0x08E6, pid=0x34EC,
        pkcs11_module="libIDPrimePKCS11.so",
        search_paths=(
            "/usr/lib/libIDPrimePKCS11.so",
            "/usr/lib64/libIDPrimePKCS11.so",
        ),
        description="Token USB compacto Gemalto",
    ),
    TokenInfo(
        vendor="Gemalto (Thales)", model="IDBridge K50",
        vid=0x08E6, pid=0x3479,
        pkcs11_module="libIDPrimePKCS11.so",
        search_paths=(
            "/usr/lib/libIDPrimePKCS11.so",
            "/usr/lib64/libIDPrimePKCS11.so",
        ),
        description="Token USB Gemalto com biometria",
    ),
    TokenInfo(
        vendor="Gemalto (Thales)", model="IDPrime MD 830",
        vid=0x08E6, pid=0x3438,
        pkcs11_module="libIDPrimePKCS11.so",
        search_paths=(
            "/usr/lib/libIDPrimePKCS11.so",
            "/usr/lib64/libIDPrimePKCS11.so",
        ),
        description="Smart card Gemalto IDPrime",
    ),
    TokenInfo(
        vendor="Gemalto (Thales)", model="IDPrime MD 840",
        vid=0x08E6, pid=0x3438,
        pkcs11_module="libIDPrimePKCS11.so",
        search_paths=(
            "/usr/lib/libIDPrimePKCS11.so",
            "/usr/lib64/libIDPrimePKCS11.so",
        ),
        description="Smart card Gemalto IDPrime 840",
    ),

    # ── Watchdata ─────────────────────────────────────────────────────
    TokenInfo(
        vendor="Watchdata", model="ProxKey",
        vid=0x058F, pid=0x9540,
        pkcs11_module="libwdpkcs.so",
        search_paths=(
            "/usr/lib/libwdpkcs.so",
            "/usr/lib/watchdata/ICP/lib/libwdpkcs.so",
            "/opt/watchdata/lib64/libwdpkcs.so",
            "/usr/lib64/libwdpkcs.so",
        ),
        description="Token USB Watchdata, muito usado no Brasil",
    ),
    TokenInfo(
        vendor="Watchdata", model="GD e-Pass",
        vid=0x058F, pid=0x9520,
        pkcs11_module="libwdpkcs.so",
        search_paths=(
            "/usr/lib/libwdpkcs.so",
            "/usr/lib/watchdata/ICP/lib/libwdpkcs.so",
        ),
        description="Token USB GD/Watchdata",
    ),

    # ── Feitian ───────────────────────────────────────────────────────
    TokenInfo(
        vendor="Feitian", model="ePass 2003",
        vid=0x096E, pid=0x0807,
        pkcs11_module="libepsng_p11.so",
        search_paths=(
            "/usr/lib/libepsng_p11.so",
            "/opt/ePass2003/lib/x86_64/libepsng_p11.so",
            "/opt/ePass2003/lib/libepsng_p11.so.1.1.0",
        ),
        description="Token USB Feitian ePass 2003",
    ),
    TokenInfo(
        vendor="Feitian", model="ePass 3003 Auto",
        vid=0x096E, pid=0x0808,
        pkcs11_module="libepsng_p11.so",
        search_paths=(
            "/usr/lib/libepsng_p11.so",
            "/opt/ePass2003/lib/x86_64/libepsng_p11.so",
        ),
        description="Token USB Feitian com auto-detect",
    ),
    TokenInfo(
        vendor="Feitian", model="BioPass FIDO2",
        vid=0x096E, pid=0x060B,
        pkcs11_module="libepsng_p11.so",
        search_paths=(
            "/usr/lib/libepsng_p11.so",
            "/opt/ePass2003/lib/x86_64/libepsng_p11.so",
        ),
        description="Token biométrico Feitian com FIDO2",
    ),
    TokenInfo(
        vendor="Feitian", model="Rockey 200",
        vid=0x096E, pid=0x0305,
        pkcs11_module="libepsng_p11.so",
        search_paths=(
            "/usr/lib/libepsng_p11.so",
        ),
        description="Dongles de segurança Feitian",
    ),
    TokenInfo(
        vendor="Feitian", model="ePass FIDO-NFC",
        vid=0x096E, pid=0x0854,
        pkcs11_module="libepsng_p11.so",
        search_paths=(
            "/usr/lib/libepsng_p11.so",
        ),
        description="Token FIDO com NFC",
    ),

    # ── Taglio ────────────────────────────────────────────────────────
    TokenInfo(
        vendor="Taglio", model="DinKey",
        vid=0x04B9, pid=0x0300,
        pkcs11_module="libneloersen.so",
        search_paths=(
            "/usr/lib/libneloersen.so",
            "/usr/lib64/libneloersen.so",
        ),
        description="Token Taglio DinKey para ICP-Brasil",
    ),

    # ── GD Burti ──────────────────────────────────────────────────────
    TokenInfo(
        vendor="GD Burti", model="StarSign CUT S",
        vid=0x04E6, pid=0x5816,
        pkcs11_module="libgdpkcs11.so",
        search_paths=(
            "/usr/lib/libgdpkcs11.so",
            "/usr/lib64/libgdpkcs11.so",
        ),
        description="Token USB GD Burti StarSign",
    ),

    # ── Oberthur / IDEMIA ─────────────────────────────────────────────
    TokenInfo(
        vendor="Oberthur (IDEMIA)", model="IDOne Cosmo V7",
        vid=0x08E6, pid=0x34EC,
        pkcs11_module="libOcsCryptoki.so",
        search_paths=(
            "/usr/lib/libOcsCryptoki.so",
            "/usr/lib64/libOcsCryptoki.so",
        ),
        description="Smartcard IDEMIA IDOne",
    ),

    # ── Bit4id ────────────────────────────────────────────────────────
    TokenInfo(
        vendor="Bit4id", model="miniLector EVO",
        vid=0x25DD, pid=0x3111,
        pkcs11_module="libbit4ipki.so",
        search_paths=(
            "/usr/lib/libbit4ipki.so",
            "/usr/lib/bit4id/libbit4ipki.so",
        ),
        description="Leitor de smartcard Bit4id",
        is_reader=True,
    ),
    TokenInfo(
        vendor="Bit4id", model="Digital-DNA Key",
        vid=0x25DD, pid=0x3111,
        pkcs11_module="libbit4xpki.so",
        search_paths=(
            "/usr/lib/libbit4xpki.so",
            "/usr/lib/bit4id/libbit4xpki.so",
        ),
        description="Token Bit4id Digital-DNA",
    ),

    # ── Athena ────────────────────────────────────────────────────────
    TokenInfo(
        vendor="Athena", model="ASEDrive IIIe",
        vid=0x0DC3, pid=0x0802,
        pkcs11_module="libASEP11.so",
        search_paths=(
            "/usr/lib/libASEP11.so",
            "/usr/lib64/libASEP11.so",
        ),
        description="Leitor USB Athena ASEDrive",
        is_reader=True,
    ),
    TokenInfo(
        vendor="Athena", model="ASECard Crypto",
        vid=0x0DC3, pid=0x1004,
        pkcs11_module="libASEP11.so",
        search_paths=(
            "/usr/lib/libASEP11.so",
            "/usr/lib64/libASEP11.so",
        ),
        description="Smartcard criptográfico Athena",
    ),

    # ── ACS (Advanced Card Systems) ───────────────────────────────────
    TokenInfo(
        vendor="ACS", model="ACR38U",
        vid=0x072F, pid=0x90CC,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
            "/usr/lib/x86_64-linux-gnu/opensc-pkcs11.so",
        ),
        description="Leitor de smartcard ACS ACR38",
        is_reader=True,
    ),
    TokenInfo(
        vendor="ACS", model="ACR39U",
        vid=0x072F, pid=0x2200,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Leitor de smartcard ACS ACR39",
        is_reader=True,
    ),

    # ── Cherry ────────────────────────────────────────────────────────
    TokenInfo(
        vendor="Cherry", model="ST-2000",
        vid=0x046A, pid=0x003E,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Leitor Cherry SmartTerminal",
        is_reader=True,
    ),
    TokenInfo(
        vendor="Cherry", model="SmartTerminal",
        vid=0x046A, pid=0x0070,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Teclado Cherry com leitor integrado",
        is_reader=True,
    ),

    # ── SCM Microsystems ──────────────────────────────────────────────
    TokenInfo(
        vendor="SCM Microsystems", model="SCR 3310",
        vid=0x04E6, pid=0x5116,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Leitor USB SCM SCR 3310",
        is_reader=True,
    ),
    TokenInfo(
        vendor="SCM Microsystems", model="SCR 3500",
        vid=0x04E6, pid=0x5410,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Leitor USB compacto SCM",
        is_reader=True,
    ),

    # ── HID Global / OMNIKEY ──────────────────────────────────────────
    TokenInfo(
        vendor="HID Global", model="OMNIKEY 3021",
        vid=0x076B, pid=0x3021,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Leitor USB HID OMNIKEY",
        is_reader=True,
    ),
    TokenInfo(
        vendor="HID Global", model="OMNIKEY 5021 CL",
        vid=0x076B, pid=0x5321,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Leitor sem contato HID OMNIKEY",
        is_reader=True,
    ),

    # ── Broadcom ──────────────────────────────────────────────────────
    TokenInfo(
        vendor="Broadcom", model="5880 (integrado)",
        vid=0x0A5C, pid=0x5800,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Leitor integrado em notebooks Dell/Lenovo",
        is_reader=True,
    ),

    # ── C3PO ──────────────────────────────────────────────────────────
    TokenInfo(
        vendor="C3PO", model="LTC31",
        vid=0x0783, pid=0x0003,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Leitor USB C3PO LTC31",
        is_reader=True,
    ),

    # ── Yubico ────────────────────────────────────────────────────────
    TokenInfo(
        vendor="Yubico", model="YubiKey 5 NFC",
        vid=0x1050, pid=0x0407,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
            "/usr/lib/libykcs11.so",
        ),
        description="YubiKey com PIV para certificados",
    ),
    TokenInfo(
        vendor="Yubico", model="YubiKey 5C",
        vid=0x1050, pid=0x0407,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
            "/usr/lib/libykcs11.so",
        ),
        description="YubiKey USB-C com PIV",
    ),
    TokenInfo(
        vendor="Yubico", model="YubiKey 5Ci",
        vid=0x1050, pid=0x0406,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/libykcs11.so",
        ),
        description="YubiKey com Lightning + USB-C",
    ),

    # ── Alcor Micro ───────────────────────────────────────────────────
    TokenInfo(
        vendor="Alcor Micro", model="AU9540",
        vid=0x058F, pid=0x9540,
        pkcs11_module="opensc-pkcs11.so",
        search_paths=(
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ),
        description="Controlador interno de smartcard Alcor Micro",
        is_reader=True,
    ),

    # ── Kryptus (fabricante brasileiro) ───────────────────────────────
    TokenInfo(
        vendor="Kryptus", model="kNET HSM Token",
        vid=0x0000, pid=0x0000,  # VID:PID varies
        pkcs11_module="libkNET_pkcs11.so",
        search_paths=(
            "/usr/lib/libkNET_pkcs11.so",
            "/opt/kryptus/lib/libkNET_pkcs11.so",
        ),
        description="Token HSM brasileiro Kryptus",
    ),

    # ── AET Europe / SafeSign ─────────────────────────────────────────
    TokenInfo(
        vendor="AET Europe", model="SafeSign Token",
        vid=0x0000, pid=0x0000,  # Uses smartcard via reader
        pkcs11_module="libaetpkcs11.so",
        search_paths=(
            "/usr/lib/libaetpkcs11.so",
            "/usr/lib64/libaetpkcs11.so",
            "/usr/lib/x86_64-linux-gnu/libaetpkcs11.so",
        ),
        description="Middleware SafeSign para smartcards ICP-Brasil",
    ),

    # ── G&D (Giesecke+Devrient) ──────────────────────────────────────
    TokenInfo(
        vendor="G&D", model="StarSign CUT Token",
        vid=0x04E6, pid=0x5816,
        pkcs11_module="libstarsignpkcs11.so",
        search_paths=(
            "/usr/lib/libstarsignpkcs11.so",
        ),
        description="Token G&D StarSign CUT",
    ),

    # ── Valid Certificadora ───────────────────────────────────────────
    TokenInfo(
        vendor="Valid", model="Token Valid (SafeNet rebrand)",
        vid=0x0529, pid=0x0620,
        pkcs11_module="libeToken.so",
        search_paths=(
            "/usr/lib/libeToken.so",
            "/usr/lib64/libeToken.so",
        ),
        description="Token rebranded SafeNet vendido pela Valid",
    ),

    # ── Soluti ────────────────────────────────────────────────────────
    TokenInfo(
        vendor="Soluti", model="Token Soluti (SafeNet rebrand)",
        vid=0x0529, pid=0x0620,
        pkcs11_module="libeToken.so",
        search_paths=(
            "/usr/lib/libeToken.so",
            "/usr/lib64/libeToken.so",
        ),
        description="Token rebranded SafeNet vendido pela Soluti",
    ),

    # ── Certisign ─────────────────────────────────────────────────────
    TokenInfo(
        vendor="Certisign", model="Token Certisign (SafeNet rebrand)",
        vid=0x0529, pid=0x0620,
        pkcs11_module="libeToken.so",
        search_paths=(
            "/usr/lib/libeToken.so",
            "/usr/lib64/libeToken.so",
        ),
        description="Token rebranded SafeNet vendido pela Certisign",
    ),

    # ── Serasa Experian ───────────────────────────────────────────────
    TokenInfo(
        vendor="Serasa Experian", model="Token Serasa (SafeNet rebrand)",
        vid=0x0529, pid=0x0620,
        pkcs11_module="libeToken.so",
        search_paths=(
            "/usr/lib/libeToken.so",
            "/usr/lib64/libeToken.so",
        ),
        description="Token rebranded SafeNet vendido pela Serasa",
    ),
]


class TokenDatabase:
    """Lookup token info by USB VID:PID or list all known tokens."""

    def __init__(self) -> None:
        self._by_usb: dict[str, list[TokenInfo]] = {}
        self._by_module: dict[str, list[TokenInfo]] = {}
        for token in _TOKEN_LIST:
            key = _usb_key(token.vid, token.pid)
            self._by_usb.setdefault(key, []).append(token)
            self._by_module.setdefault(token.pkcs11_module, []).append(token)

    def lookup_by_usb(self, vid: int, pid: int) -> list[TokenInfo]:
        return self._by_usb.get(_usb_key(vid, pid), [])

    def lookup_by_module(self, module_name: str) -> list[TokenInfo]:
        return self._by_module.get(module_name, [])

    def find_pkcs11_library(self, vid: int, pid: int) -> Optional[str]:
        """Find the first existing PKCS#11 library for a given USB device."""
        tokens = self.lookup_by_usb(vid, pid)
        for token in tokens:
            for path_str in token.search_paths:
                if Path(path_str).is_file():
                    return path_str
        # Fallback: try OpenSC
        for fallback in (
            "/usr/lib/opensc-pkcs11.so",
            "/usr/lib/pkcs11/opensc-pkcs11.so",
        ):
            if Path(fallback).is_file():
                return fallback
        return None

    def all_tokens(self) -> list[TokenInfo]:
        return list(_TOKEN_LIST)

    def all_usb_ids(self) -> set[tuple[int, int]]:
        """Return all known USB VID:PID pairs (excluding 0000:0000 placeholders)."""
        return {
            (t.vid, t.pid)
            for t in _TOKEN_LIST
            if t.vid != 0 and t.pid != 0
        }

    def unique_modules(self) -> set[str]:
        return set(self._by_module.keys())
