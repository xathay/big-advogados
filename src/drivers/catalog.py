"""Carregamento e indexacao do catalogo de drivers (data/drivers/*.toml)."""
from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Optional

from src.drivers.types import (
    DriverDistributor, DriverLicense, DriverSource, DriverSpec,
    InstallDir, TokenMatch,
)

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Path do catalogo no pacote instalado.
_INSTALLED_CATALOG = Path("/usr/lib/big-certificados/data/drivers")
# Path do catalogo no checkout de desenvolvimento.
_DEV_CATALOG = Path(__file__).resolve().parents[2] / "data" / "drivers"


def _parse(data: dict, source_path: Path) -> Optional[DriverSpec]:
    try:
        if data.get("schema_version") != SCHEMA_VERSION:
            log.warning(
                "Pulando %s — schema_version %s nao bate com %d",
                source_path, data.get("schema_version"), SCHEMA_VERSION,
            )
            return None

        d = data["driver"]
        dist = data["distributor"]
        src = data["source"]
        lic = data["license"]
        inst = data["install"]

        dirs: list[InstallDir] = []
        for entry in inst.get("dirs", []):
            dirs.append(InstallDir(
                from_path=entry["from"], to_path=entry["to"], shared=False,
            ))
        for entry in inst.get("shared_dirs", []):
            dirs.append(InstallDir(
                from_path=entry["from"], to_path=entry["to"], shared=True,
            ))

        tokens = tuple(
            TokenMatch(vid=t["vid"], pid=t["pid"], name=t["name"])
            for t in data.get("tokens", [])
        )

        return DriverSpec(
            id=d["id"],
            vendor=d["vendor"],
            vendor_url=d.get("vendor_url", ""),
            product=d["product"],
            version=d["version"],
            arch=d.get("arch", "x86_64"),
            description=d["description"],
            distributor=DriverDistributor(
                name=dist["name"],
                url=dist["url"],
                note=dist.get("note", ""),
            ),
            source=DriverSource(
                format=src["format"],
                url=src["url"],
                sha256=src["sha256"],
                size_bytes=src["size_bytes"],
                label=src["label"],
            ),
            license=DriverLicense(
                type=lic["type"],
                file_in_archive=lic["file_in_archive"],
                file_in_archive_fallback=lic.get("file_in_archive_fallback"),
                summary=lic["summary"],
            ),
            install_prefix=inst["prefix"],
            install_dirs=tuple(dirs),
            tokens=tokens,
        )
    except (KeyError, TypeError) as exc:
        log.error("Falha ao parsear catalogo %s: %s", source_path, exc)
        return None


class DriverCatalog:
    """Indexa drivers do catalogo por id e por (VID, PID) de token."""

    def __init__(self, catalog_dirs: Optional[list[Path]] = None):
        self._by_id: dict[str, DriverSpec] = {}
        self._by_token: dict[tuple[int, int], DriverSpec] = {}

        for d in catalog_dirs or self._default_dirs():
            if d.is_dir():
                self._load_dir(d)

    @staticmethod
    def _default_dirs() -> list[Path]:
        if _INSTALLED_CATALOG.is_dir():
            return [_INSTALLED_CATALOG]
        return [_DEV_CATALOG]

    def _load_dir(self, dirpath: Path) -> None:
        for path in sorted(dirpath.glob("*.toml")):
            try:
                with path.open("rb") as f:
                    data = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                log.error("Falha ao ler catalogo %s: %s", path, exc)
                continue
            spec = _parse(data, path)
            if spec is None:
                continue
            self._by_id[spec.id] = spec
            for tok in spec.tokens:
                self._by_token[(tok.vid, tok.pid)] = spec

    def get(self, driver_id: str) -> Optional[DriverSpec]:
        return self._by_id.get(driver_id)

    def for_token(self, vid: int, pid: int) -> Optional[DriverSpec]:
        return self._by_token.get((vid, pid))

    def all(self) -> tuple[DriverSpec, ...]:
        return tuple(self._by_id.values())

    def is_installed(self, spec: DriverSpec) -> bool:
        """Heuristica: prefix existe e contem pelo menos um .so em lib/."""
        prefix = Path(spec.install_prefix)
        if not prefix.is_dir():
            return False
        return any(prefix.glob("lib/*.so*"))
