"""Release metadata and repository privacy guardrails."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

from src.version import VERSION


ROOT = Path(__file__).resolve().parents[1]


def _publishable_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    )
    return [ROOT / name.decode("utf-8") for name in output.split(b"\0") if name]


def test_application_version_is_consistent() -> None:
    pkgbuild = (ROOT / "PKGBUILD").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    with (ROOT / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)

    package_version = re.search(r"^pkgver=(\S+)$", pkgbuild, re.MULTILINE)
    assert package_version is not None
    assert package_version.group(1) == VERSION
    assert f"Status-v{VERSION}-" in readme
    assert project["project"]["dynamic"] == ["version"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "src.version.VERSION",
    }


def test_tracked_files_do_not_contain_local_or_secret_material() -> None:
    forbidden = (
        b"/home/" + b"athayde/",
        b"/home/" + b"leonardo/",
        b"leoathayde" + b"@gmail.com",
        b"rruscher" + b"@gmail.com",
        b"-----BEGIN " + b"PRIVATE KEY-----",
        b"-----BEGIN RSA " + b"PRIVATE KEY-----",
        b"-----BEGIN EC " + b"PRIVATE KEY-----",
    )
    findings: list[str] = []

    for path in _publishable_files():
        content = path.read_bytes()
        if any(marker in content for marker in forbidden):
            findings.append(str(path.relative_to(ROOT)))

    assert findings == []
