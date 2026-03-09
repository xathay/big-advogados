"""XDG-compliant path helpers."""

from __future__ import annotations

import os
from pathlib import Path

APP_ID = "com.bigcertificados"
APP_NAME = "bigcertificados"


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d
