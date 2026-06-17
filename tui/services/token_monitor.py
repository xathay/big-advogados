"""Detecção de tokens USB sem GLib — equivalente asyncio do udev_monitor.

`src/utils/udev_monitor.py` despacha eventos via `GLib.idle_add` (acoplado
ao loop GTK). Aqui replicamos a mesma lógica de scan/poll sobre `pyudev`,
mas entregamos os eventos por um callback simples — o lado Textual marshalla
para a thread da UI com `App.call_from_thread`.

Reusa `TokenDatabase` (puro, GTK-free). `pyudev` é import lazy: sem ele, o
scan retorna vazio e o hotplug fica inerte (degrada graciosamente).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from src.certificate.token_database import TokenDatabase

log = logging.getLogger(__name__)

# (action, vid, pid, devnode) — action ∈ {"add", "remove"}
EventCallback = Callable[[str, int, int, str], None]


@dataclass(frozen=True)
class TokenDetectado:
    vendor: str
    model: str
    vid: int
    pid: int
    devnode: str
    is_reader: bool = False

    @property
    def nome(self) -> str:
        partes = [p for p in (self.vendor, self.model) if p]
        base = " ".join(partes) or f"{self.vid:04x}:{self.pid:04x}"
        return f"{base} (leitor)" if self.is_reader else base


def _import_pyudev():
    try:
        import pyudev  # type: ignore
        return pyudev
    except ImportError:
        return None


def _nome_token(db: TokenDatabase, vid: int, pid: int) -> tuple[str, str, bool]:
    infos = db.lookup_by_usb(vid, pid)
    if infos:
        t = infos[0]
        return t.vendor, t.model, t.is_reader
    return "", "", False


def pyudev_disponivel() -> bool:
    return _import_pyudev() is not None


def scan_tokens(db: Optional[TokenDatabase] = None) -> list[TokenDetectado]:
    """Lista tokens conhecidos atualmente conectados."""
    pyudev = _import_pyudev()
    if pyudev is None:
        return []

    db = db or TokenDatabase()
    known = db.all_usb_ids()
    achados: list[TokenDetectado] = []
    context = pyudev.Context()
    for device in context.list_devices(subsystem="usb", DEVTYPE="usb_device"):
        vid_str = device.get("ID_VENDOR_ID", "")
        pid_str = device.get("ID_MODEL_ID", "")
        if not vid_str or not pid_str:
            continue
        try:
            vid = int(vid_str, 16)
            pid = int(pid_str, 16)
        except ValueError:
            continue
        if (vid, pid) in known:
            vendor, model, is_reader = _nome_token(db, vid, pid)
            achados.append(TokenDetectado(
                vendor=vendor, model=model, vid=vid, pid=pid,
                devnode=device.device_node or "", is_reader=is_reader,
            ))
    return achados


class TokenHotplug:
    """Monitora add/remove de tokens conhecidos numa thread daemon."""

    def __init__(self, db: Optional[TokenDatabase] = None) -> None:
        self._db = db or TokenDatabase()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self, on_event: EventCallback) -> bool:
        pyudev = _import_pyudev()
        if pyudev is None or self._running:
            return False
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, args=(on_event,), daemon=True, name="tui-udev",
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False

    def _loop(self, on_event: EventCallback) -> None:
        pyudev = _import_pyudev()
        if pyudev is None:
            return
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem="usb")
        known = self._db.all_usb_ids()

        for device in iter(lambda: monitor.poll(timeout=1.0), None):
            if not self._running:
                break
            if device is None:
                continue
            if device.action not in ("add", "remove"):
                continue
            vid_str = device.get("ID_VENDOR_ID", "")
            pid_str = device.get("ID_MODEL_ID", "")
            if not vid_str or not pid_str:
                continue
            try:
                vid = int(vid_str, 16)
                pid = int(pid_str, 16)
            except ValueError:
                continue
            if (vid, pid) in known:
                try:
                    on_event(device.action, vid, pid, device.device_node or "")
                except Exception as exc:  # noqa: BLE001
                    log.debug("on_event raised: %s", exc)
