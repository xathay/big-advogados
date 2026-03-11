"""Token detection view — shows status of connected tokens."""

from __future__ import annotations

import logging
import subprocess
import threading
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango  # noqa: E402

from src.certificate.token_database import TokenDatabase, TokenInfo

log = logging.getLogger(__name__)


class TokenDetectView(Gtk.ScrolledWindow):
    """View showing detected tokens and their status."""

    def __init__(self, token_db: TokenDatabase) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._token_db = token_db
        self._token_rows: dict[str, Adw.ActionRow] = {}

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        # Header
        header = Gtk.Label(label="Tokens Detectados")
        header.add_css_class("title-2")
        header.set_halign(Gtk.Align.START)
        content.append(header)

        # Status page (no token connected)
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("dialog-information-symbolic")
        self._status_page.set_title("Nenhum token detectado")
        self._status_page.set_description(
            "Conecte seu token USB de certificado digital.\n"
            "O dispositivo será reconhecido automaticamente."
        )
        content.append(self._status_page)

        # Token list group (hidden initially)
        self._token_group = Adw.PreferencesGroup()
        self._token_group.set_title("Dispositivos Conectados")
        self._token_group.set_visible(False)
        content.append(self._token_group)

        # Scan button
        scan_btn = Gtk.Button(label="Buscar Dispositivos")
        scan_btn.add_css_class("suggested-action")
        scan_btn.set_halign(Gtk.Align.CENTER)
        scan_btn.set_margin_top(8)
        scan_btn.connect("clicked", self._on_scan_clicked)
        content.append(scan_btn)

        self.set_child(content)

    def _on_scan_clicked(self, _button: Gtk.Button) -> None:
        self.emit_scan_request()

    def emit_scan_request(self) -> None:
        """Can be overridden or connected to from window."""
        pass

    def add_token(self, vid: int, pid: int, devnode: str) -> None:
        """Add a detected token to the list."""
        key = f"{vid:04x}:{pid:04x}"
        if key in self._token_rows:
            return

        tokens = self._token_db.lookup_by_usb(vid, pid)
        if tokens:
            token = tokens[0]
            title = f"{token.vendor} — {token.model}"
            subtitle = f"USB {key} • {token.description}"
            icon = "media-removable-symbolic" if not token.is_reader else "drive-removable-media-symbolic"
        else:
            title = f"Dispositivo USB {key}"
            subtitle = f"Dispositivo em {devnode}"
            icon = "drive-removable-media-symbolic"

        row = Adw.ActionRow()
        row.set_title(title)
        row.set_subtitle(subtitle)
        row.set_icon_name(icon)
        row.set_activatable(True)

        # Module status indicator
        module_path = self._token_db.find_pkcs11_library(vid, pid)
        if module_path:
            status_label = Gtk.Label(label="Módulo OK")
            status_label.add_css_class("success")
            row.add_suffix(status_label)

            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            row.add_suffix(arrow)
        else:
            pkg = self._token_db.suggest_package(vid, pid)
            if pkg:
                status_label = Gtk.Label(label=f"Driver: {pkg}")
                status_label.add_css_class("warning")
                row.add_suffix(status_label)

                install_btn = Gtk.Button()
                install_btn.set_icon_name("software-install-symbolic")
                install_btn.set_tooltip_text(f"Instalar {pkg}")
                install_btn.set_valign(Gtk.Align.CENTER)
                install_btn.add_css_class("flat")
                install_btn.connect("clicked", self._on_install_driver, pkg, row)
                row.add_suffix(install_btn)
            else:
                status_label = Gtk.Label(label="Módulo não encontrado")
                status_label.add_css_class("error")
                row.add_suffix(status_label)

        self._token_rows[key] = row
        self._token_group.add(row)
        self._token_group.set_visible(True)
        self._status_page.set_visible(False)

    def remove_token(self, vid: int, pid: int) -> None:
        """Remove a token from the list."""
        key = f"{vid:04x}:{pid:04x}"
        row = self._token_rows.pop(key, None)
        if row:
            self._token_group.remove(row)

        if not self._token_rows:
            self._token_group.set_visible(False)
            self._status_page.set_visible(True)

    def clear(self) -> None:
        for key in list(self._token_rows):
            row = self._token_rows.pop(key)
            self._token_group.remove(row)
        self._token_group.set_visible(False)
        self._status_page.set_visible(True)

    def _on_install_driver(
        self, _btn: Gtk.Button, package: str, row: Adw.ActionRow,
    ) -> None:
        """Suggest driver installation via terminal (yay/pacman)."""
        _btn.set_sensitive(False)

        # Determine if it's an AUR or pacman package
        is_pacman = package == "opensc"
        if is_pacman:
            cmd = ["pkexec", "pacman", "-S", "--noconfirm", package]
        else:
            cmd = ["yay", "-S", "--noconfirm", package]

        def install_thread() -> None:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=300,
                )
                GLib.idle_add(on_done, result.returncode == 0, result.stderr)
            except Exception as exc:
                GLib.idle_add(on_done, False, str(exc))

        def on_done(success: bool, error: str) -> bool:
            _btn.set_sensitive(True)
            if success:
                row.set_subtitle(f"✓ {package} instalado com sucesso — reconecte o token")
                _btn.set_icon_name("emblem-ok-symbolic")
                _btn.set_sensitive(False)
                log.info("Driver package '%s' installed successfully", package)
            else:
                row.set_subtitle(f"Falha ao instalar {package}")
                log.error("Failed to install %s: %s", package, error)
            return False

        threading.Thread(target=install_thread, daemon=True).start()
