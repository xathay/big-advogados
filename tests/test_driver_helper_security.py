"""Security tests for the privileged driver installation helper."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

_HELPER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "big-drivers-install.py"
_SPEC = importlib.util.spec_from_file_location("big_drivers_install", _HELPER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
driver_helper = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(driver_helper)


def test_verified_source_copy_hashes_the_copied_bytes(tmp_path) -> None:
    source = tmp_path / "pacote.deb"
    destination = tmp_path / "copia-verificada.deb"
    payload = b"conteudo-do-pacote"
    source.write_bytes(payload)

    digest, size = driver_helper.copy_verified_source(source, destination)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert size == len(payload)
    assert destination.read_bytes() == payload


def test_verified_source_copy_refuses_symlink(tmp_path) -> None:
    source = tmp_path / "pacote-real.deb"
    source.write_bytes(b"pacote")
    link = tmp_path / "pacote-link.deb"
    link.symlink_to(source)

    with pytest.raises(SystemExit):
        driver_helper.copy_verified_source(link, tmp_path / "destino.deb")


def test_staging_validation_refuses_escaping_symlink(tmp_path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "escape").symlink_to("../../fora")

    with pytest.raises(SystemExit):
        driver_helper.validate_staging_tree(staging)


def test_staging_validation_allows_relative_internal_symlink(tmp_path) -> None:
    staging = tmp_path / "staging"
    library_dir = staging / "usr" / "lib"
    library_dir.mkdir(parents=True)
    (library_dir / "libdriver.so.1").write_bytes(b"biblioteca")
    (library_dir / "libdriver.so").symlink_to("libdriver.so.1")

    driver_helper.validate_staging_tree(staging)
