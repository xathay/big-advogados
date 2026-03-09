"""USB device monitor using pyudev for automatic token detection."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from gi.repository import GLib

try:
    import pyudev
except ImportError:
    pyudev = None  # type: ignore[assignment]

from src.certificate.token_database import TokenDatabase

log = logging.getLogger(__name__)

DeviceCallback = Callable[[str, int, int, str], None]  # action, vid, pid, devnode


class UdevMonitor:
    """Monitors USB subsystem for token insertion/removal events.

    Detected devices are matched against TokenDatabase and callbacks
    are dispatched on the GLib main loop thread.
    """

    def __init__(self, token_db: TokenDatabase) -> None:
        self._token_db = token_db
        self._callbacks: list[DeviceCallback] = []
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False

    def connect(self, callback: DeviceCallback) -> None:
        self._callbacks.append(callback)

    def _dispatch(self, action: str, vid: int, pid: int, devnode: str) -> None:
        for cb in self._callbacks:
            GLib.idle_add(cb, action, vid, pid, devnode)

    def scan_existing(self) -> list[tuple[int, int, str]]:
        """Scan currently connected USB devices and return known tokens."""
        if pyudev is None:
            log.warning("pyudev not installed, cannot scan devices")
            return []

        found: list[tuple[int, int, str]] = []
        context = pyudev.Context()
        known_ids = self._token_db.all_usb_ids()

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
            if (vid, pid) in known_ids:
                devnode = device.device_node or ""
                found.append((vid, pid, devnode))
                log.info("Found token: %04x:%04x at %s", vid, pid, devnode)

        return found

    def start(self) -> None:
        if pyudev is None:
            log.warning("pyudev not installed, USB monitoring disabled")
            return
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="udev-monitor"
        )
        self._monitor_thread.start()
        log.info("USB monitor started")

    def stop(self) -> None:
        self._running = False
        log.info("USB monitor stopped")

    def _monitor_loop(self) -> None:
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem="usb")

        known_ids = self._token_db.all_usb_ids()

        for device in iter(monitor.poll, None):
            if not self._running:
                break

            action = device.action
            if action not in ("add", "remove"):
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

            if (vid, pid) in known_ids:
                devnode = device.device_node or ""
                log.info("Token %s: %04x:%04x at %s", action, vid, pid, devnode)
                self._dispatch(action, vid, pid, devnode)
