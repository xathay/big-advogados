"""Main application window."""

from __future__ import annotations

import logging
import threading
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio  # noqa: E402

from src.certificate.a3_manager import A3Manager
from src.certificate.token_database import TokenDatabase
from src.ui.a1_view import A1CertificateView
from src.ui.certificate_view import CertificateView
from src.ui.token_detect_view import TokenDetectView
from src.ui.systems_view import SystemsView
from src.ui.pin_dialog import PinDialog
from src.ui.lock_screen import LockDialog
from src.utils.udev_monitor import UdevMonitor
from src.utils.app_lock import is_lock_enabled
from src.browser.nss_config import register_in_all_browsers, is_nss_tools_available

log = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """Main application window with navigation between views."""

    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application)

        self.set_title("BigCertificados")
        self.set_default_size(800, 600)
        self.set_size_request(360, 400)

        # Core objects
        self._token_db = TokenDatabase()
        self._a3_manager = A3Manager(self._token_db)
        self._udev_monitor = UdevMonitor(self._token_db)

        self._unlocked = False

        # Build UI
        self._build_ui()

        # Connect udev events
        self._udev_monitor.connect(self._on_usb_event)

        # If lock is enabled, show lock screen first; otherwise unlock immediately
        if is_lock_enabled():
            self._show_lock()
        else:
            self._unlock()

    def _build_ui(self) -> None:
        # Main toolbar view
        toolbar_view = Adw.ToolbarView()

        # Header bar
        header = Adw.HeaderBar()

        # View switcher in header
        self._view_stack = Adw.ViewStack()

        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self._view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text("Menu")

        menu = Gio.Menu()
        menu.append("Configurar Navegadores", "app.setup-browsers")
        menu.append("Proteção por Senha", "app.password-settings")
        menu.append("Verificar Dependências", "app.check-deps")
        menu.append("Sobre", "app.about")

        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

        toolbar_view.add_top_bar(header)

        # ── Views ──
        # Token Detection View
        self._token_view = TokenDetectView(self._token_db)
        self._token_view.emit_scan_request = self._do_scan
        self._view_stack.add_titled_with_icon(
            self._token_view, "tokens", "Tokens",
            "drive-removable-media-symbolic",
        )

        # A1 Certificate View
        self._a1_view = A1CertificateView()
        self._view_stack.add_titled_with_icon(
            self._a1_view, "a1", "Certificado A1",
            "application-certificate-symbolic",
        )

        # Certificate View
        self._cert_view = CertificateView()
        self._view_stack.add_titled_with_icon(
            self._cert_view, "certificates", "Certificados",
            "security-high-symbolic",
        )

        # Systems View
        self._systems_view = SystemsView()
        self._view_stack.add_titled_with_icon(
            self._systems_view, "systems", "Sistemas",
            "preferences-system-network-symbolic",
        )

        toolbar_view.set_content(self._view_stack)

        # Bottom bar for status
        self._status_bar = Gtk.Label(label="Pronto")
        self._status_bar.add_css_class("dim-label")
        self._status_bar.set_margin_top(4)
        self._status_bar.set_margin_bottom(4)
        self._status_bar.set_margin_start(12)
        self._status_bar.set_halign(Gtk.Align.START)
        toolbar_view.add_bottom_bar(self._status_bar)

        self.set_content(toolbar_view)

        # Wire up token row activation
        for row in self._token_view._token_rows.values():
            row.connect("activated", self._on_token_row_activated)

    def _show_lock(self) -> None:
        """Show the lock dialog as a modal."""
        dialog = LockDialog(on_unlocked=self._unlock)
        dialog.present(self)

    def _unlock(self) -> None:
        """Unlock the app — start scanning."""
        self._unlocked = True
        GLib.idle_add(self._initial_scan)

    def _initial_scan(self) -> bool:
        """Run initial USB scan on startup."""
        self._do_scan()
        self._udev_monitor.start()
        return False  # Don't repeat

    def _do_scan(self) -> None:
        self._set_status("Buscando dispositivos USB...")
        self._token_view.clear()

        def scan_thread() -> None:
            found = self._udev_monitor.scan_existing()
            GLib.idle_add(self._on_scan_result, found)

        threading.Thread(target=scan_thread, daemon=True).start()

    def _on_scan_result(self, found: list[tuple[int, int, str]]) -> bool:
        for vid, pid, devnode in found:
            self._token_view.add_token(vid, pid, devnode)

            # Wire up the new row
            key = f"{vid:04x}:{pid:04x}"
            row = self._token_view._token_rows.get(key)
            if row:
                row.connect(
                    "activated",
                    self._on_token_row_activated,
                    vid, pid,
                )

        if found:
            self._set_status(f"{len(found)} dispositivo(s) encontrado(s)")
        else:
            self._set_status("Nenhum token detectado")
            # Try loading any available module
            self._try_auto_detect()

        return False

    def _try_auto_detect(self) -> None:
        """Try to find tokens via PKCS#11 module probing."""
        if not self._a3_manager.is_available:
            return

        def probe_thread() -> None:
            module = self._a3_manager.try_all_modules()
            if module:
                GLib.idle_add(self._on_module_found, module)

        threading.Thread(target=probe_thread, daemon=True).start()

    def _on_module_found(self, module_path: str) -> bool:
        self._set_status(f"Módulo encontrado: {module_path}")
        slots = self._a3_manager.get_slots()
        if slots:
            self._prompt_pin(slots[0])
        return False

    def _on_usb_event(
        self, action: str, vid: int, pid: int, devnode: str,
    ) -> bool:
        if action == "add":
            self._token_view.add_token(vid, pid, devnode)
            self._set_status(f"Token conectado: {vid:04x}:{pid:04x}")

            key = f"{vid:04x}:{pid:04x}"
            row = self._token_view._token_rows.get(key)
            if row:
                row.connect(
                    "activated",
                    self._on_token_row_activated,
                    vid, pid,
                )

        elif action == "remove":
            self._token_view.remove_token(vid, pid)
            self._set_status(f"Token removido: {vid:04x}:{pid:04x}")
            self._cert_view.clear()

        return False

    def _on_token_row_activated(
        self, row: Adw.ActionRow, vid: int = 0, pid: int = 0,
    ) -> None:
        # Load PKCS#11 module
        if vid and pid:
            success = self._a3_manager.load_module_for_device(vid, pid)
            if not success:
                self._set_status("Módulo PKCS#11 não encontrado para este dispositivo")
                return

        slots = self._a3_manager.get_slots()
        if slots:
            self._prompt_pin(slots[0])
        else:
            self._set_status("Nenhum slot de token disponível")

    def _prompt_pin(self, slot_info: object) -> None:
        from src.certificate.a3_manager import TokenSlotInfo
        if not isinstance(slot_info, TokenSlotInfo):
            return

        dialog = PinDialog(token_label=slot_info.label)
        dialog.connect("closed", self._on_pin_dialog_closed, slot_info)
        dialog.present(self)

    def _on_pin_dialog_closed(
        self, dialog: PinDialog, slot_info: object,
    ) -> None:
        from src.certificate.a3_manager import TokenSlotInfo
        if not isinstance(slot_info, TokenSlotInfo):
            return

        if not dialog.confirmed or not dialog.pin:
            return

        self._set_status("Autenticando...")
        pin = dialog.pin

        def login_thread() -> None:
            success = self._a3_manager.login(slot_info.slot_id, pin)
            if success:
                certs = self._a3_manager.list_certificates()
                GLib.idle_add(self._on_certificates_loaded, certs)
            else:
                GLib.idle_add(self._on_login_failed)

        threading.Thread(target=login_thread, daemon=True).start()

    def _on_certificates_loaded(self, certs: list) -> bool:
        self._cert_view.show_certificates_list(certs)
        self._view_stack.set_visible_child_name("certificates")
        self._set_status(f"{len(certs)} certificado(s) encontrado(s)")
        return False

    def _on_login_failed(self) -> bool:
        self._set_status("Falha na autenticação — PIN incorreto?")
        self._cert_view.clear()
        return False

    def _set_status(self, text: str) -> None:
        self._status_bar.set_label(text)

    def setup_browsers(self) -> None:
        """Register PKCS#11 module in all detected browsers."""
        module = self._a3_manager.current_module
        if not module:
            self._set_status("Nenhum módulo PKCS#11 carregado")
            return

        if not is_nss_tools_available():
            self._set_status("nss-tools não instalado (pacman -S nss)")
            return

        self._set_status("Configurando navegadores...")

        def setup_thread() -> None:
            results = register_in_all_browsers(module)
            summary = ", ".join(
                f"{name}: {'OK' if ok else 'FALHA'}"
                for name, ok in results.items()
            )
            GLib.idle_add(self._set_status, f"Navegadores: {summary}")

        threading.Thread(target=setup_thread, daemon=True).start()
