"""Helpers para inspecionar arquivos .deb usando `ar` e `tar` do sistema.

.deb e um arquivo ar contendo (entre outros) data.tar.{zst,xz,gz}.
Em vez de re-implementar parsing de ar/zst em Python, fazemos pipe
para os utilitarios do sistema, que estao na base de Arch e Debian.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _data_member_name(deb_path: Path) -> Optional[str]:
    """Retorna o nome do membro data.tar.* dentro do .deb."""
    result = subprocess.run(
        ["ar", "t", str(deb_path)],
        capture_output=True, text=True, check=True,
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("data.tar"):
            return line
    return None


def _tar_decompress_flag(member_name: str) -> list[str]:
    if member_name.endswith(".zst"):
        return ["--zstd"]
    if member_name.endswith(".xz"):
        return ["--xz"]
    if member_name.endswith(".gz"):
        return ["-z"]
    return []


def extract_file_from_deb(deb_path: Path, path_inside: str) -> Optional[bytes]:
    """Extrai um arquivo de dentro do .deb e retorna os bytes.

    ``path_inside`` deve ser o path relativo dentro do data.tar (sem `/`
    no inicio, ex.: ``usr/share/doc/foo/license.txt``). Retorna ``None``
    se nao encontrado.
    """
    member = _data_member_name(deb_path)
    if member is None:
        return None

    ar_proc = subprocess.Popen(
        ["ar", "p", str(deb_path), member],
        stdout=subprocess.PIPE,
    )
    try:
        tar_proc = subprocess.Popen(
            [
                "tar",
                *_tar_decompress_flag(member),
                "-xOf", "-",
                f"./{path_inside}",
            ],
            stdin=ar_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if ar_proc.stdout is not None:
            ar_proc.stdout.close()
        out, _ = tar_proc.communicate(timeout=60)
        ar_proc.wait(timeout=5)
        if tar_proc.returncode != 0:
            return None
        return out if out else None
    except subprocess.TimeoutExpired:
        ar_proc.kill()
        return None
