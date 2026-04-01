"""A1 certificate view — load and display PFX/P12 certificates."""

from __future__ import annotations

import logging
import threading
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio  # noqa: E402

from src.certificate.a1_manager import A1Manager
from src.certificate.parser import CertificateInfo
from src.ui.certificate_widgets import (
    build_cert_details_group,
    build_holder_group,
    clear_container,
    create_validity_banner,
    show_pfx_password_dialog,
)

log = logging.getLogger(__name__)


class A1CertificateView(Gtk.ScrolledWindow):
    """View for loading and displaying A1 (PFX/P12) certificates."""

    def __init__(self) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._a1_manager = A1Manager()
        self._current_pfx_path: Optional[str] = None
        self._current_password: Optional[str] = None
        self._cert_info: Optional[CertificateInfo] = None

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        # Status page (no certificate loaded)
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("document-open-symbolic")
        self._status_page.set_title("Certificado A1 (PFX)")
        self._status_page.set_description(
            "Carregue seu certificado digital A1 em formato PFX ou P12.\n"
            "Este tipo de certificado é um arquivo digital que não requer token USB."
        )
        content.append(self._status_page)

        # Load button
        self._load_btn = Gtk.Button(label="Selecionar Arquivo PFX")
        self._load_btn.add_css_class("suggested-action")
        self._load_btn.add_css_class("pill")
        self._load_btn.set_halign(Gtk.Align.CENTER)
        self._load_btn.set_margin_top(8)
        self._load_btn.connect("clicked", self._on_load_clicked)
        content.append(self._load_btn)

        # Certificate details (hidden initially)
        self._details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._details_box.set_margin_top(8)
        self._details_box.set_margin_bottom(8)
        self._details_box.set_visible(False)
        content.append(self._details_box)

        # Action buttons (hidden initially)
        self._actions_box = Gtk.Box(spacing=12, homogeneous=True)
        self._actions_box.set_halign(Gtk.Align.CENTER)
        self._actions_box.set_margin_top(12)
        self._actions_box.set_visible(False)
        content.append(self._actions_box)

        install_btn = Gtk.Button(label="Instalar no Navegador")
        install_btn.add_css_class("suggested-action")
        install_btn.connect("clicked", self._on_install_browser_clicked)
        self._actions_box.append(install_btn)

        another_btn = Gtk.Button(label="Carregar Outro")
        another_btn.connect("clicked", self._on_load_clicked)
        self._actions_box.append(another_btn)

        remove_btn = Gtk.Button(label="Remover Certificado")
        remove_btn.add_css_class("destructive-action")
        remove_btn.connect("clicked", self._on_remove_clicked)
        self._actions_box.append(remove_btn)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)
        clamp.set_child(content)
        self.set_child(clamp)

    def _on_load_clicked(self, _button: Gtk.Button) -> None:
        """Open file chooser for PFX/P12 file."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Selecionar Certificado A1 (PFX)")

        # File filter
        filter_pfx = Gtk.FileFilter()
        filter_pfx.set_name("Certificados PFX/P12 (*.pfx, *.p12)")
        filter_pfx.add_pattern("*.pfx")
        filter_pfx.add_pattern("*.PFX")
        filter_pfx.add_pattern("*.p12")
        filter_pfx.add_pattern("*.P12")

        filter_all = Gtk.FileFilter()
        filter_all.set_name("Todos os arquivos")
        filter_all.add_pattern("*")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_pfx)
        filters.append(filter_all)
        dialog.set_filters(filters)
        dialog.set_default_filter(filter_pfx)

        window = self.get_root()
        dialog.open(window, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.open_finish(result)
            if file:
                path = file.get_path()
                if path:
                    self._prompt_password(path)
        except GLib.Error as exc:
            if exc.code != 2:  # 2 = user cancelled
                log.error("File dialog error: %s", exc)

    def _prompt_password(self, pfx_path: str) -> None:
        """Show password dialog for the PFX file."""
        def on_success(path: str, password: str, cert_info: CertificateInfo) -> None:
            self._current_pfx_path = path
            self._current_password = password
            self._cert_info = cert_info
            self._show_certificate(cert_info)

        show_pfx_password_dialog(self, pfx_path, on_success)

    def _show_certificate(self, cert: CertificateInfo) -> None:
        """Display the loaded certificate details."""
        self._status_page.set_visible(False)
        self._load_btn.set_visible(False)

        self._details_box.set_visible(True)
        self._actions_box.set_visible(True)

        # Clear old content
        clear_container(self._details_box)

        # Validity banner
        self._details_box.append(create_validity_banner(cert, prefix="A1"))

        # File info
        if self._current_pfx_path:
            import os
            file_group = Adw.PreferencesGroup()
            file_group.set_title("Arquivo")
            row = Adw.ActionRow()
            row.set_title("Arquivo PFX")
            row.set_subtitle(os.path.basename(self._current_pfx_path))
            row.set_icon_name("document-open-symbolic")
            file_group.add(row)
            self._details_box.append(file_group)

        # Holder info
        self._details_box.append(build_holder_group(cert))

        # Certificate details
        self._details_box.append(
            build_cert_details_group(cert, cert_type_label="A1 (Arquivo PFX)")
        )

    def _on_remove_clicked(self, _button: Gtk.Button) -> None:
        """Remove the loaded certificate and reset the view."""
        dialog = Adw.AlertDialog()
        dialog.set_heading("Remover Certificado")
        dialog.set_body(
            "Deseja remover o certificado carregado?\n"
            "O arquivo original no disco não será apagado."
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("remove", "Remover")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_remove_response)

        window = self.get_root()
        dialog.present(window)

    def _on_remove_response(
        self, dialog: Adw.AlertDialog, response: str,
    ) -> None:
        """Handle removal confirmation."""
        if response != "remove":
            return

        self._current_pfx_path = None
        self._current_password = None
        self._cert_info = None

        # Clear details
        clear_container(self._details_box)

        self._details_box.set_visible(False)
        self._actions_box.set_visible(False)
        self._status_page.set_visible(True)
        self._load_btn.set_visible(True)

    def _on_install_browser_clicked(self, _button: Gtk.Button) -> None:
        """Install PFX certificate in browser NSS databases."""
        if not self._current_pfx_path or not self._current_password:
            return

        window = self.get_root()
        pfx = self._current_pfx_path
        pwd = self._current_password

        # Show progress
        _button.set_sensitive(False)
        _button.set_label("Instalando...")

        def install_thread() -> None:
            results = self._a1_manager.install_in_all_browsers(pfx, pwd)
            GLib.idle_add(on_install_done, results)

        def on_install_done(results: dict[str, bool]) -> bool:
            _button.set_sensitive(True)
            _button.set_label("Instalar no Navegador")

            success_count = sum(1 for v in results.values() if v)
            total = len(results)

            if total == 0:
                self._show_toast("Nenhum navegador detectado")
            elif success_count == total:
                self._show_toast(f"Certificado instalado em {total} navegador(es)")
            else:
                self._show_toast(
                    f"Instalado em {success_count}/{total} navegador(es)"
                )
            return False

        threading.Thread(target=install_thread, daemon=True).start()

    def _show_toast(self, message: str) -> None:
        """Show an inline status message."""
        window = self.get_root()
        if isinstance(window, Adw.ApplicationWindow):
            # Use the status bar from the main window
            from src.window import MainWindow
            if isinstance(window, MainWindow):
                window._set_status(message)
