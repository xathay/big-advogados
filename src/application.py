"""BigCertificados — GtkApplication setup."""

from __future__ import annotations

import importlib
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
CURRENT_VERSION = "1.1.0"


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
        src_root = os.path.dirname(os.path.dirname(__file__))
        icon_dir = os.path.join(src_root, "data", "icons")
        icon_theme = Gtk.IconTheme.get_for_display(self._window.get_display())
        icon_theme.add_search_path(icon_dir)

        # Ensure .desktop + icon are installed for Wayland app_id matching
        self._ensure_desktop_integration(src_root)

        self._window.present()

    # ------------------------------------------------------------------
    # Desktop integration (icon / .desktop file)
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_desktop_integration(src_root: str) -> None:
        """Install .desktop file and SVG icon into user-local XDG paths.

        Under Wayland the compositor resolves the window icon via
        app_id → .desktop file → Icon= key → icon theme lookup, so both
        the desktop entry and the icon must be discoverable.
        """
        xdg_data = os.environ.get(
            "XDG_DATA_HOME",
            os.path.join(os.path.expanduser("~"), ".local", "share"),
        )
        desktop_dir = os.path.join(xdg_data, "applications")
        icon_dir = os.path.join(
            xdg_data, "icons", "hicolor", "scalable", "apps",
        )

        desktop_src = os.path.join(
            src_root, "data", "com.bigcertificados.desktop",
        )
        icon_src = os.path.join(
            src_root, "data", "icons", "bigcertificados.svg",
        )

        pairs = [
            (desktop_src, os.path.join(desktop_dir, "com.bigcertificados.desktop")),
            (icon_src, os.path.join(icon_dir, "bigcertificados.svg")),
        ]

        for src, dst in pairs:
            if not os.path.exists(src):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            # Re-create symlink if target changed (e.g. repo moved)
            if os.path.islink(dst):
                if os.readlink(dst) == os.path.abspath(src):
                    continue
                os.remove(dst)
            elif os.path.exists(dst):
                continue  # real file installed by package manager — don't touch
            try:
                os.symlink(os.path.abspath(src), dst)
            except OSError:
                log.debug("Could not create symlink %s → %s", dst, src)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)

        # Use AdwStyleManager instead of deprecated GtkSettings dark theme
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

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
        dialog.set_content_width(550)
        dialog.set_content_height(600)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(520)
        clamp.set_tightening_threshold(400)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Tracking for "resolve all" button
        dep_row_data: list[dict] = []

        # ── System packages ──
        sys_group = Adw.PreferencesGroup()
        sys_group.set_title("Pacotes do Sistema")
        sys_group.set_description("Instalados via pacman")

        sys_deps = [
            ("pcscd", "pcsclite", "PC/SC daemon para smartcards",
             "system-run-symbolic"),
            ("modutil", "nss", "NSS tools para navegadores",
             "preferences-system-network-symbolic"),
            ("opensc-tool", "opensc", "OpenSC smartcard middleware",
             "application-x-addon-symbolic"),
            ("ccid", "ccid", "Drivers CCID para leitores",
             "drive-removable-media-symbolic"),
            ("pikepdf", "python-pikepdf", "Manipulação de PDFs",
             "x-office-document-symbolic"),
            ("reportlab", "python-reportlab", "Geração de PDFs",
             "x-office-document-symbolic"),
            ("PIL", "python-pillow", "Processamento de imagens",
             "image-x-generic-symbolic"),
        ]

        for cmd_or_mod, pkg, desc, icon_name in sys_deps:
            row = Adw.ActionRow()
            row.set_title(desc)
            row.set_subtitle(f"Pacote: {pkg}")
            row.set_icon_name(icon_name)

            # Check: for "ccid" check driver dir, for python modules try import,
            # otherwise check `which`
            is_installed = False
            if cmd_or_mod == "ccid":
                from pathlib import Path
                is_installed = Path("/usr/lib/pcsc/drivers").is_dir()
            elif cmd_or_mod in ("pikepdf", "reportlab", "PIL"):
                try:
                    importlib.import_module(cmd_or_mod)
                    is_installed = True
                except ImportError:
                    is_installed = False
            else:
                try:
                    result = subprocess.run(
                        ["which", cmd_or_mod],
                        capture_output=True, text=True, timeout=5,
                    )
                    is_installed = result.returncode == 0
                except Exception:
                    is_installed = False

            suffix_box = Gtk.Box(spacing=8)
            suffix_box.set_valign(Gtk.Align.CENTER)

            if is_installed:
                ok_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                ok_icon.add_css_class("success")
                suffix_box.append(ok_icon)
            else:
                err_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
                err_icon.add_css_class("error")
                suffix_box.append(err_icon)

                install_btn = Gtk.Button()
                install_btn.set_icon_name("folder-download-symbolic")
                install_btn.set_tooltip_text(f"Instalar {pkg}")
                install_btn.add_css_class("flat")
                install_btn.connect(
                    "clicked",
                    self._on_install_single_pkg,
                    pkg, row, suffix_box,
                )
                suffix_box.append(install_btn)

                dep_row_data.append({
                    "type": "pkg", "pkg": pkg,
                    "row": row, "suffix_box": suffix_box,
                })

            row.add_suffix(suffix_box)
            sys_group.add(row)

        box.append(sys_group)

        # ── Python dependencies ──
        py_group = Adw.PreferencesGroup()
        py_group.set_title("Módulos Python")
        py_group.set_description("Bibliotecas de runtime")

        py_deps = [
            ("PyKCS11", "python-pykcs11", "Comunicação PKCS#11"),
            ("pyudev", "python-pyudev", "Detecção USB via udev"),
            ("cryptography", "python-cryptography", "Parsing de certificados"),
            ("asn1crypto", "python-asn1crypto", "ASN.1 para certificados"),
            ("oscrypto", "python-oscrypto", "Criptografia nativa"),
            ("endesive", "python-endesive", "Assinatura digital de PDFs"),
        ]

        for mod, pkg, desc in py_deps:
            row = Adw.ActionRow()
            row.set_title(desc)
            row.set_subtitle(f"Módulo: {mod} | Pacote: {pkg}")
            row.set_icon_name("application-x-executable-symbolic")

            is_installed = False
            try:
                importlib.import_module(mod if mod != "PyKCS11" else "PyKCS11")
                is_installed = True
            except ImportError:
                is_installed = False

            suffix_box = Gtk.Box(spacing=8)
            suffix_box.set_valign(Gtk.Align.CENTER)

            if is_installed:
                ok_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                ok_icon.add_css_class("success")
                suffix_box.append(ok_icon)
            else:
                err_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
                err_icon.add_css_class("error")
                suffix_box.append(err_icon)

                install_btn = Gtk.Button()
                install_btn.set_icon_name("folder-download-symbolic")
                install_btn.set_tooltip_text(f"Instalar {pkg}")
                install_btn.add_css_class("flat")
                install_btn.connect(
                    "clicked",
                    self._on_install_single_pkg,
                    pkg, row, suffix_box,
                )
                suffix_box.append(install_btn)

                dep_row_data.append({
                    "type": "pkg", "pkg": pkg,
                    "row": row, "suffix_box": suffix_box,
                })

            row.add_suffix(suffix_box)
            py_group.add(row)

        box.append(py_group)

        # ── Services ──
        svc_group = Adw.PreferencesGroup()
        svc_group.set_title("Serviços do Sistema")
        svc_group.set_description("Gerenciados pelo systemd")

        services = [
            ("pcscd", "PC/SC Smart Card Daemon"),
            ("pcscd.socket", "Ativação sob demanda do pcscd"),
        ]

        for svc_name, desc in services:
            row = Adw.ActionRow()
            row.set_title(desc)
            row.set_subtitle(f"Serviço: {svc_name}")
            row.set_icon_name("system-run-symbolic")

            is_active = False
            status_text = "Desconhecido"
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", svc_name],
                    capture_output=True, text=True, timeout=5,
                )
                status_text = result.stdout.strip()
                is_active = status_text == "active"
            except Exception:
                pass

            is_enabled = False
            try:
                result = subprocess.run(
                    ["systemctl", "is-enabled", svc_name],
                    capture_output=True, text=True, timeout=5,
                )
                is_enabled = result.stdout.strip() in ("enabled", "enabled-runtime")
            except Exception:
                pass

            suffix_box = Gtk.Box(spacing=8)
            suffix_box.set_valign(Gtk.Align.CENTER)

            status_label = Gtk.Label(label=status_text.capitalize())
            if is_active:
                status_label.add_css_class("success")
            else:
                status_label.add_css_class("warning")
            suffix_box.append(status_label)

            toggle_btn = Gtk.Button()
            if is_active:
                toggle_btn.set_icon_name("media-playback-pause-symbolic")
                toggle_btn.set_tooltip_text(f"Desativar {svc_name}")
                toggle_btn.add_css_class("flat")
            else:
                toggle_btn.set_icon_name("media-playback-start-symbolic")
                toggle_btn.set_tooltip_text(f"Ativar {svc_name}")
                toggle_btn.add_css_class("flat")
            toggle_btn.connect(
                "clicked",
                self._on_toggle_service,
                svc_name, is_active, row, suffix_box, status_label, toggle_btn,
            )
            suffix_box.append(toggle_btn)

            if not is_active:
                dep_row_data.append({
                    "type": "svc", "svc": svc_name,
                    "row": row, "suffix_box": suffix_box,
                    "status_label": status_label, "toggle_btn": toggle_btn,
                })

            row.add_suffix(suffix_box)
            svc_group.add(row)

        box.append(svc_group)

        # ── Resolve all button ──
        if dep_row_data:
            resolve_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            resolve_box.set_margin_top(8)
            resolve_box.set_halign(Gtk.Align.CENTER)

            resolve_btn = Gtk.Button(label="Resolver todas as dependências")
            resolve_btn.add_css_class("suggested-action")
            resolve_btn.add_css_class("pill")
            resolve_btn.connect(
                "clicked",
                self._on_resolve_all_deps,
                dep_row_data, dialog,
            )
            resolve_box.append(resolve_btn)

            resolve_hint = Gtk.Label(
                label="Instala pacotes faltantes e ativa serviços necessários"
            )
            resolve_hint.add_css_class("dim-label")
            resolve_hint.add_css_class("caption")
            resolve_box.append(resolve_hint)

            box.append(resolve_box)
        else:
            all_ok_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            all_ok_box.set_margin_top(8)
            all_ok_box.set_halign(Gtk.Align.CENTER)

            ok_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            ok_icon.set_pixel_size(32)
            ok_icon.add_css_class("success")
            all_ok_box.append(ok_icon)

            ok_label = Gtk.Label(label="Tudo instalado e configurado!")
            ok_label.add_css_class("title-4")
            all_ok_box.append(ok_label)

            box.append(all_ok_box)

        clamp.set_child(box)
        scroll.set_child(clamp)
        toolbar.set_content(scroll)
        dialog.set_child(toolbar)

        if self._window:
            dialog.present(self._window)

    def _on_install_single_pkg(
        self,
        btn: Gtk.Button,
        pkg: str,
        row: Adw.ActionRow,
        suffix_box: Gtk.Box,
    ) -> None:
        """Install a single system package in background."""
        btn.set_sensitive(False)
        btn.set_label("Instalando…")

        import threading

        def install_thread() -> None:
            try:
                result = subprocess.run(
                    ["pkexec", "pacman", "-S", "--noconfirm", "--needed", pkg],
                    capture_output=True, text=True, timeout=120,
                )
                success = result.returncode == 0
            except Exception:
                success = False
            GLib.idle_add(on_done, success)

        def on_done(success: bool) -> bool:
            # Remove old suffix children
            child = suffix_box.get_first_child()
            while child:
                next_c = child.get_next_sibling()
                suffix_box.remove(child)
                child = next_c

            if success:
                ok_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                ok_icon.add_css_class("success")
                suffix_box.append(ok_icon)
            else:
                err_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
                err_icon.add_css_class("error")
                suffix_box.append(err_icon)

                retry_btn = Gtk.Button(label="Tentar novamente")
                retry_btn.add_css_class("suggested-action")
                retry_btn.add_css_class("pill")
                retry_btn.connect(
                    "clicked",
                    self._on_install_single_pkg,
                    pkg, row, suffix_box,
                )
                suffix_box.append(retry_btn)
            return False

        threading.Thread(target=install_thread, daemon=True).start()

    def _on_toggle_service(
        self,
        btn: Gtk.Button,
        svc_name: str,
        currently_active: bool,
        row: Adw.ActionRow,
        suffix_box: Gtk.Box,
        status_label: Gtk.Label,
        toggle_btn: Gtk.Button,
    ) -> None:
        """Toggle a systemd service on/off in background."""
        btn.set_sensitive(False)

        import threading

        action = "stop" if currently_active else "start"
        enable_action = "disable" if currently_active else "enable"

        def toggle_thread() -> None:
            try:
                # Enable/disable first
                subprocess.run(
                    ["pkexec", "systemctl", enable_action, svc_name],
                    capture_output=True, text=True, timeout=30,
                )
                # Then start/stop
                result = subprocess.run(
                    ["pkexec", "systemctl", action, svc_name],
                    capture_output=True, text=True, timeout=30,
                )
                success = result.returncode == 0
            except Exception:
                success = False
            GLib.idle_add(on_done, success)

        def on_done(success: bool) -> bool:
            # Re-check actual state
            new_active = False
            new_status = "Desconhecido"
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", svc_name],
                    capture_output=True, text=True, timeout=5,
                )
                new_status = result.stdout.strip()
                new_active = new_status == "active"
            except Exception:
                pass

            status_label.set_label(new_status.capitalize())
            for css in ("success", "warning", "error"):
                status_label.remove_css_class(css)
            status_label.add_css_class("success" if new_active else "warning")

            toggle_btn.set_sensitive(True)
            if new_active:
                toggle_btn.set_icon_name("media-playback-pause-symbolic")
                toggle_btn.set_tooltip_text(f"Desativar {svc_name}")
            else:
                toggle_btn.set_icon_name("media-playback-start-symbolic")
                toggle_btn.set_tooltip_text(f"Ativar {svc_name}")

            # Update the closure for next click
            toggle_btn.disconnect_by_func(self._on_toggle_service)
            toggle_btn.connect(
                "clicked",
                self._on_toggle_service,
                svc_name, new_active, row, suffix_box, status_label, toggle_btn,
            )
            return False

        threading.Thread(target=toggle_thread, daemon=True).start()

    def _on_resolve_all_deps(
        self,
        btn: Gtk.Button,
        dep_row_data: list[dict],
        dialog: Adw.Dialog,
    ) -> None:
        """Install all missing packages and activate services step by step."""
        btn.set_sensitive(False)
        btn.set_label("Resolvendo…")

        import threading

        # Collect unique packages to install
        pkgs = list({d["pkg"] for d in dep_row_data if d["type"] == "pkg"})
        svcs = [d for d in dep_row_data if d["type"] == "svc"]

        def resolve_thread() -> None:
            # Step 1: Install all packages at once
            pkg_ok = True
            if pkgs:
                try:
                    result = subprocess.run(
                        ["pkexec", "pacman", "-S", "--noconfirm", "--needed"] + pkgs,
                        capture_output=True, text=True, timeout=180,
                    )
                    pkg_ok = result.returncode == 0
                except Exception:
                    pkg_ok = False

            GLib.idle_add(update_pkg_rows, pkg_ok)

            # Step 2: Enable and start services
            for svc_info in svcs:
                svc_name = svc_info["svc"]
                try:
                    subprocess.run(
                        ["pkexec", "systemctl", "enable", "--now", svc_name],
                        capture_output=True, text=True, timeout=30,
                    )
                except Exception:
                    pass
                GLib.idle_add(update_svc_row, svc_info)

            GLib.idle_add(on_all_done)

        def update_pkg_rows(pkg_ok: bool) -> bool:
            for d in dep_row_data:
                if d["type"] != "pkg":
                    continue
                suffix_box = d["suffix_box"]
                child = suffix_box.get_first_child()
                while child:
                    next_c = child.get_next_sibling()
                    suffix_box.remove(child)
                    child = next_c

                if pkg_ok:
                    ok_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                    ok_icon.add_css_class("success")
                    suffix_box.append(ok_icon)
                else:
                    err_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
                    err_icon.add_css_class("warning")
                    suffix_box.append(err_icon)
            return False

        def update_svc_row(svc_info: dict) -> bool:
            svc_name = svc_info["svc"]
            status_label = svc_info["status_label"]
            toggle_btn = svc_info["toggle_btn"]

            new_active = False
            new_status = "Desconhecido"
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", svc_name],
                    capture_output=True, text=True, timeout=5,
                )
                new_status = result.stdout.strip()
                new_active = new_status == "active"
            except Exception:
                pass

            status_label.set_label(new_status.capitalize())
            for css in ("success", "warning", "error"):
                status_label.remove_css_class(css)
            status_label.add_css_class("success" if new_active else "warning")

            toggle_btn.set_sensitive(True)
            if new_active:
                toggle_btn.set_icon_name("media-playback-pause-symbolic")
                toggle_btn.set_tooltip_text(f"Desativar {svc_name}")
            return False

        def on_all_done() -> bool:
            btn.set_sensitive(True)
            btn.set_label("Resolver todas as dependências")
            return False

        threading.Thread(target=resolve_thread, daemon=True).start()

    def _on_password_settings(self, *_args: object) -> None:
        dialog = PasswordSettingsDialog()
        if self._window:
            dialog.present(self._window)

    def _on_about(self, *_args: object) -> None:
        about = Adw.AboutDialog()
        about.set_application_name("BigCertificados")
        about.set_developer_name("BigLinux Team")
        about.set_version("1.1.0")
        about.set_comments(
            "Gerenciador completo de certificados digitais para "
            "advogados e profissionais do Direito no GNU/Linux.\n\n"
            "Recursos:\n"
            "• Certificados A3 via token USB (PKCS#11)\n"
            "• Certificados A1 (PFX/P12)\n"
            "• VidaaS Connect — certificado A3 na nuvem\n"
            "• Assinatura digital de PDFs (wizard guiado ICP-Brasil)\n"
            "• Dashboard com status de certificados e ações rápidas\n"
            "• Configuração automática de navegadores (Firefox, Chrome, Brave)\n"
            "• 36 sistemas judiciais organizados por estado\n"
            "• 68 drivers de tokens catalogados\n"
            "• Integração com PJe, e-SAJ, eProc, PROJUDI e PJeOffice Pro\n"
            "• Detecção automática de tokens USB via udev"
        )
        about.set_website("https://github.com/xathay/big-advogados")
        about.set_application_icon("bigcertificados")
        about.set_license_type(Gtk.License.MIT_X11)
        about.set_release_notes(
            "<p>Novidades na versão 1.1.0:</p>"
            "<ul>"
            "<li>URLs de sistemas judiciais atualizados — 10 links quebrados corrigidos</li>"
            "<li>Migração para eProc (TRF2, TRF4, TJRS)</li>"
            "<li>Dashboard simplificado sem scroll desnecessário (Adw.StatusPage)</li>"
            "<li>Certificados unificados com abas ViewStack (A3 + A1)</li>"
            "<li>Correção de warnings do pyudev no terminal</li>"
            "<li>AdwStyleManager — respeita tema do sistema por padrão</li>"
            "</ul>"
            "<p>Versão 1.0.0:</p>"
            "<ul>"
            "<li>Interface com sidebar categorizada (NavigationSplitView)</li>"
            "<li>Dashboard com visão geral dos certificados e ações rápidas</li>"
            "<li>Assinador de PDFs com wizard guiado de 4 passos</li>"
            "<li>Sistemas judiciais com sidebar colapsável (OverlaySplitView)</li>"
            "<li>VidaaS Connect — assinatura em nuvem via Valid Certificadora</li>"
            "<li>68 drivers de tokens catalogados com instalação automática</li>"
            "</ul>"
        )
        about.set_developers([
            "Leonardo Athayde <leoathayde@gmail.com>",
        ])
        about.set_copyright("© 2026 BigLinux Team")
        about.add_credit_section("Contribuidores", [
            "Rafael Ruscher <rruscher@gmail.com>",
        ])

        if self._window:
            about.present(self._window)
