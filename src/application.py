"""BigCertificados — GtkApplication setup."""

from __future__ import annotations

import logging
import os
import subprocess
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib  # noqa: E402

from src.window import MainWindow
from src.browser.nss_config import is_nss_tools_available
from src.ui.password_settings import PasswordSettingsDialog

log = logging.getLogger(__name__)

APP_ID = "com.bigcertificados"
CURRENT_VERSION = "0.1.0"


class BigCertificadosApp(Adw.Application):
    """Main application class."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window: MainWindow | None = None

    def do_activate(self) -> None:
        if self._window is None:
            self._window = MainWindow(application=self)

        # Register icon search path for our custom icons
        icon_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "icons",
        )
        icon_theme = Gtk.IconTheme.get_for_display(self._window.get_display())
        icon_theme.add_search_path(icon_dir)

        self._window.present()

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._setup_actions()

    def _setup_actions(self) -> None:
        # Setup browsers action
        action = Gio.SimpleAction.new("setup-browsers", None)
        action.connect("activate", self._on_setup_browsers)
        self.add_action(action)

        # Check dependencies action
        action = Gio.SimpleAction.new("check-deps", None)
        action.connect("activate", self._on_check_deps)
        self.add_action(action)

        # Password settings action
        action = Gio.SimpleAction.new("password-settings", None)
        action.connect("activate", self._on_password_settings)
        self.add_action(action)

        # About action
        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", self._on_about)
        self.add_action(action)

    def _on_setup_browsers(self, *_args: object) -> None:
        if self._window:
            self._window.setup_browsers()

    def _on_check_deps(self, *_args: object) -> None:
        dialog = Adw.Dialog()
        dialog.set_title("Dependências do Sistema")
        dialog.set_content_width(500)
        dialog.set_content_height(400)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        deps = [
            ("pcscd", "pcsclite", "PC/SC daemon para smartcards"),
            ("modutil", "nss", "NSS tools para configuração de navegadores"),
            ("opensc-tool", "opensc", "OpenSC smartcard middleware"),
        ]

        group = Adw.PreferencesGroup()
        group.set_title("Status das Dependências")

        for cmd, pkg, desc in deps:
            row = Adw.ActionRow()
            row.set_title(desc)
            row.set_subtitle(f"Comando: {cmd} | Pacote: {pkg}")

            try:
                result = subprocess.run(
                    ["which", cmd],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                    icon.add_css_class("success")
                    label = Gtk.Label(label="Instalado")
                    label.add_css_class("success")
                else:
                    icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
                    icon.add_css_class("error")
                    label = Gtk.Label(label="Não encontrado")
                    label.add_css_class("error")
            except Exception:
                icon = Gtk.Image.new_from_icon_name("dialog-question-symbolic")
                label = Gtk.Label(label="Erro ao verificar")

            row.add_suffix(label)
            row.add_suffix(icon)
            group.add(row)

        # pcscd service status
        service_row = Adw.ActionRow()
        service_row.set_title("Serviço pcscd")
        service_row.set_subtitle("systemctl status pcscd")
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "pcscd"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip() == "active":
                svc_label = Gtk.Label(label="Ativo")
                svc_label.add_css_class("success")
            else:
                svc_label = Gtk.Label(label=result.stdout.strip())
                svc_label.add_css_class("warning")
        except Exception:
            svc_label = Gtk.Label(label="Erro")

        service_row.add_suffix(svc_label)
        group.add(service_row)

        box.append(group)

        # Python dependencies
        py_group = Adw.PreferencesGroup()
        py_group.set_title("Dependências Python")

        py_deps = [
            ("PyKCS11", "Comunicação PKCS#11"),
            ("pyudev", "Detecção USB via udev"),
            ("cryptography", "Parsing de certificados"),
        ]

        for mod, desc in py_deps:
            row = Adw.ActionRow()
            row.set_title(desc)
            row.set_subtitle(f"Módulo: {mod}")

            try:
                __import__(mod if mod != "PyKCS11" else "PyKCS11")
                label = Gtk.Label(label="OK")
                label.add_css_class("success")
            except ImportError:
                label = Gtk.Label(label="Não instalado")
                label.add_css_class("error")

            row.add_suffix(label)
            py_group.add(row)

        box.append(py_group)
        scroll.set_child(box)
        toolbar.set_content(scroll)
        dialog.set_child(toolbar)

        if self._window:
            dialog.present(self._window)

    def _on_password_settings(self, *_args: object) -> None:
        dialog = PasswordSettingsDialog()
        if self._window:
            dialog.present(self._window)

    def _on_about(self, *_args: object) -> None:
        about = Adw.AboutDialog()
        about.set_application_name("BigCertificados")
        about.set_developer_name("BigLinux Team")
        about.set_version(CURRENT_VERSION)
        about.set_comments(
            "Gerenciador de certificados digitais para advogados "
            "e profissionais do Direito no GNU/Linux.\n\n"
            "Suporte a tokens A3 (PKCS#11) e certificados A1 (PFX).\n\n"
            "Integração com navegadores, sistemas judiciais "
            "eletrônicos e PJeOffice Pro."
        )
        about.set_website("https://github.com/xathay/big-advogados")
        about.set_application_icon("bigcertificados")
        about.set_license_type(Gtk.License.MIT_X11)
        about.set_developers(["Leonardo Athayde <leoathayde@gmail.com>"])
        about.set_copyright("© 2025 BigLinux Team")

        if self._window:
            about.present(self._window)
