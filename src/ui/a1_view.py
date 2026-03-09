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
        load_btn = Gtk.Button(label="Selecionar Arquivo PFX")
        load_btn.add_css_class("suggested-action")
        load_btn.add_css_class("pill")
        load_btn.set_halign(Gtk.Align.CENTER)
        load_btn.set_margin_top(8)
        load_btn.connect("clicked", self._on_load_clicked)
        content.append(load_btn)

        # Certificate details (hidden initially)
        self._details_scroll = Gtk.ScrolledWindow()
        self._details_scroll.set_vexpand(True)
        self._details_scroll.set_visible(False)
        content.append(self._details_scroll)

        self._details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._details_box.set_margin_top(8)
        self._details_box.set_margin_bottom(8)
        self._details_box.set_margin_start(8)
        self._details_box.set_margin_end(8)
        self._details_scroll.set_child(self._details_box)

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

        self.set_child(content)

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
        dialog = Adw.Dialog()
        dialog.set_title("Senha do Certificado")
        dialog.set_content_width(400)
        dialog.set_content_height(220)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        # File name label
        import os
        filename = os.path.basename(pfx_path)
        file_label = Gtk.Label(label=f"Arquivo: {filename}")
        file_label.add_css_class("dim-label")
        file_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        box.append(file_label)

        # Password entry
        pwd_entry = Gtk.PasswordEntry()
        pwd_entry.props.placeholder_text = "Senha do certificado PFX"
        pwd_entry.set_show_peek_icon(True)
        box.append(pwd_entry)

        # Error label (hidden initially)
        error_label = Gtk.Label()
        error_label.add_css_class("error")
        error_label.set_visible(False)
        box.append(error_label)

        # Buttons
        btn_box = Gtk.Box(spacing=12, homogeneous=True)
        btn_box.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", lambda _b: dialog.close())
        btn_box.append(cancel_btn)

        ok_btn = Gtk.Button(label="Abrir")
        ok_btn.add_css_class("suggested-action")
        btn_box.append(ok_btn)

        box.append(btn_box)

        def on_confirm(*_args: object) -> None:
            password = pwd_entry.get_text()
            ok_btn.set_sensitive(False)
            cancel_btn.set_sensitive(False)
            pwd_entry.set_sensitive(False)

            def load_thread() -> None:
                cert_info = self._a1_manager.load_pfx(pfx_path, password)
                GLib.idle_add(on_load_result, cert_info, password)

            def on_load_result(
                cert_info: Optional[CertificateInfo], pwd: str,
            ) -> bool:
                if cert_info:
                    self._current_pfx_path = pfx_path
                    self._current_password = pwd
                    self._cert_info = cert_info
                    self._show_certificate(cert_info)
                    dialog.close()
                else:
                    error_label.set_label("Senha incorreta ou arquivo inválido")
                    error_label.set_visible(True)
                    ok_btn.set_sensitive(True)
                    cancel_btn.set_sensitive(True)
                    pwd_entry.set_sensitive(True)
                    pwd_entry.grab_focus()
                return False

            threading.Thread(target=load_thread, daemon=True).start()

        ok_btn.connect("clicked", on_confirm)
        pwd_entry.connect("activate", on_confirm)

        toolbar.set_content(box)
        dialog.set_child(toolbar)

        window = self.get_root()
        dialog.present(window)

    def _show_certificate(self, cert: CertificateInfo) -> None:
        """Display the loaded certificate details."""
        self._status_page.set_visible(False)

        # Find and hide the load button
        child = self.get_first_child()
        while child:
            if isinstance(child, Gtk.Button) and not isinstance(child, Gtk.MenuButton):
                if child.get_label() == "Selecionar Arquivo PFX":
                    child.set_visible(False)
                    break
            child = child.get_next_sibling()

        self._details_scroll.set_visible(True)
        self._actions_box.set_visible(True)

        # Clear old content
        child = self._details_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._details_box.remove(child)
            child = next_child

        # Validity banner
        validity_bar = self._create_validity_bar(cert)
        self._details_box.append(validity_bar)

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
        holder_group = Adw.PreferencesGroup()
        holder_group.set_title("Titular do Certificado")

        self._add_info_row(holder_group, "Nome", cert.holder_name, "avatar-default-symbolic")
        if cert.cpf:
            self._add_info_row(holder_group, "CPF", cert.cpf, "contact-new-symbolic")
        if cert.cnpj:
            self._add_info_row(holder_group, "CNPJ", cert.cnpj, "contact-new-symbolic")
        if cert.oab:
            self._add_info_row(holder_group, "OAB", cert.oab, "emblem-documents-symbolic")
        if cert.email:
            self._add_info_row(holder_group, "E-mail", cert.email, "mail-unread-symbolic")

        self._details_box.append(holder_group)

        # Certificate details
        cert_group = Adw.PreferencesGroup()
        cert_group.set_title("Dados do Certificado")

        self._add_info_row(cert_group, "Tipo", "A1 (Arquivo PFX)")
        self._add_info_row(cert_group, "Nome Comum (CN)", cert.common_name)
        self._add_info_row(cert_group, "Número de Série", cert.serial_number)
        self._add_info_row(cert_group, "Emissora (CA)", cert.issuer_cn)
        if cert.not_before:
            self._add_info_row(
                cert_group, "Válido Desde",
                cert.not_before.strftime("%d/%m/%Y %H:%M"),
            )
        if cert.not_after:
            self._add_info_row(
                cert_group, "Válido Até",
                cert.not_after.strftime("%d/%m/%Y %H:%M"),
            )
        if cert.key_usage:
            self._add_info_row(cert_group, "Uso da Chave", cert.key_usage)

        self._details_box.append(cert_group)

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

    def _create_validity_bar(self, cert: CertificateInfo) -> Gtk.Box:
        bar = Gtk.Box(spacing=8)
        bar.set_halign(Gtk.Align.FILL)
        bar.add_css_class("card")
        bar.set_margin_bottom(8)

        inner = Gtk.Box(spacing=8)
        inner.set_margin_top(12)
        inner.set_margin_bottom(12)
        inner.set_margin_start(12)
        inner.set_margin_end(12)

        if cert.is_expired:
            icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
            icon.add_css_class("error")
            label = Gtk.Label(label="CERTIFICADO A1 EXPIRADO")
            label.add_css_class("error")
        elif cert.days_to_expire <= 30:
            icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            icon.add_css_class("warning")
            label = Gtk.Label(
                label=f"EXPIRA EM {cert.days_to_expire} DIAS"
            )
            label.add_css_class("warning")
        else:
            icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            icon.add_css_class("success")
            label = Gtk.Label(
                label=f"CERTIFICADO A1 VÁLIDO — expira em {cert.days_to_expire} dias"
            )
            label.add_css_class("success")

        label.add_css_class("heading")
        inner.append(icon)
        inner.append(label)
        bar.append(inner)
        return bar

    @staticmethod
    def _add_info_row(
        group: Adw.PreferencesGroup,
        title: str,
        value: str,
        icon_name: str = "",
    ) -> None:
        row = Adw.ActionRow()
        row.set_title(title)
        row.set_subtitle(value)
        if icon_name:
            row.set_icon_name(icon_name)
        row.set_subtitle_selectable(True)
        group.add(row)
