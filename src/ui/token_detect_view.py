"""Token detection view — shows status of connected tokens."""

from __future__ import annotations

import html
import logging
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GObject, Pango  # noqa: E402

from src.certificate.token_database import TokenDatabase, TokenInfo
from src.drivers import DriverCatalog, DriverSpec
from src.ui.driver_install_dialog import DriverInstallDialog

log = logging.getLogger(__name__)


class TokenDetectView(Gtk.ScrolledWindow):
    """View showing detected tokens and their status."""

    __gsignals__ = {
        "scan-requested": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(
        self,
        token_db: TokenDatabase,
        driver_catalog: Optional[DriverCatalog] = None,
    ) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._token_db = token_db
        self._driver_catalog = driver_catalog or DriverCatalog()
        self._token_rows: dict[str, Adw.ActionRow] = {}

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

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

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)
        clamp.set_child(content)
        self.set_child(clamp)

    @property
    def token_count(self) -> int:
        """Number of currently detected tokens."""
        return len(self._token_rows)

    def get_row(self, vid: int, pid: int) -> Adw.ActionRow | None:
        """Get the row widget for a token by USB vendor/product ID."""
        key = f"{vid:04x}:{pid:04x}"
        return self._token_rows.get(key)

    def _on_scan_clicked(self, _button: Gtk.Button) -> None:
        self.emit("scan-requested")

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

        # Adw.PreferencesRow has use-markup=True by default, so unescaped
        # characters like '&' (present in vendors like "G&D") break Pango
        # parsing and render the label as blank.
        row = Adw.ActionRow()
        row.set_title(html.escape(title))
        row.set_subtitle(html.escape(subtitle))
        row.set_icon_name(icon)
        row.set_activatable(True)

        # Status do módulo do token:
        #   1. Driver vendor presente → verde "Módulo OK"
        #   2. Driver disponível no catálogo big-drivers → amarelo "Driver
        #      disponível" + botão de instalação (abre DriverInstallDialog)
        #   3. Sem driver nem entrada no catálogo → vermelho "Módulo não
        #      encontrado"
        vendor_module = self._token_db.find_vendor_pkcs11_library(vid, pid)
        spec = self._driver_catalog.for_token(vid, pid) if not vendor_module else None
        if vendor_module:
            status_label = Gtk.Label(label="Módulo OK")
            status_label.add_css_class("success")
            row.add_suffix(status_label)

            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            row.add_suffix(arrow)
        elif spec is not None:
            status_label = Gtk.Label(label="Driver disponível")
            status_label.add_css_class("warning")
            row.add_suffix(status_label)

            install_btn = Gtk.Button()
            install_btn.set_icon_name("software-install-symbolic")
            install_btn.set_tooltip_text(f"Instalar {spec.product}")
            install_btn.set_valign(Gtk.Align.CENTER)
            install_btn.add_css_class("flat")
            install_btn.connect("clicked", self._on_install_driver, spec, row)
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
        self, _btn: Gtk.Button, spec: DriverSpec, row: Adw.ActionRow,
    ) -> None:
        """Abre o DriverInstallDialog com o spec correspondente."""
        dialog = DriverInstallDialog(
            spec,
            on_done=lambda success: self._on_driver_installed(success, row, spec),
        )
        dialog.present(self.get_root())

    def _on_driver_installed(
        self, success: bool, row: Adw.ActionRow, spec: DriverSpec,
    ) -> None:
        if success:
            row.set_subtitle(f"✓ {spec.product} instalado — desconecte e reconecte o token")
            log.info("Driver '%s' instalado", spec.id)
        else:
            log.info("Instalacao de '%s' nao completou", spec.id)
