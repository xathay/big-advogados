"""Tipos imutaveis que representam uma entrada do catalogo de drivers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TokenMatch:
    vid: int
    pid: int
    name: str


@dataclass(frozen=True)
class DriverDistributor:
    name: str
    url: str
    note: str


@dataclass(frozen=True)
class DriverSource:
    format: str  # "deb" (unico suportado v1)
    url: str
    sha256: str
    size_bytes: int
    label: str


@dataclass(frozen=True)
class DriverLicense:
    type: str
    file_in_archive: str
    file_in_archive_fallback: Optional[str]
    summary: str


@dataclass(frozen=True)
class InstallDir:
    """Diretorio a copiar do arquivo de origem para o destino.

    Quando ``shared`` e ``False``, ``to_path`` e interpretado como
    relativo ao prefixo do driver (ex.: ``lib`` -> prefix/lib). Quando
    ``True``, ``to_path`` e absoluto (ex.: ``/usr/share/safesign``) e o
    helper privilegiado deve checar conflitos antes de escrever.
    """
    from_path: str
    to_path: str
    shared: bool


@dataclass(frozen=True)
class DriverSpec:
    id: str
    vendor: str
    vendor_url: str
    product: str
    version: str
    arch: str
    description: str
    distributor: DriverDistributor
    source: DriverSource
    license: DriverLicense
    install_prefix: str
    install_dirs: tuple[InstallDir, ...]
    tokens: tuple[TokenMatch, ...]
