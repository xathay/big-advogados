"""Dependency check dialog — shows system packages, Python modules, and services."""

from __future__ import annotations

import importlib
import logging
import re
import subprocess
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

log = logging.getLogger(__name__)


class DependencyCheckDialog(Adw.Dialog):

    def __init__(self) -> None:
        super().__init__()
        self.set_title("Dependências do Sistema")
        self.set_content_width(550)
        self.set_content_height(600)
        self._build_ui()

    def _build_ui(self) -> None:
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

        dep_row_data: list[dict] = []

        # ── System packages ──
        sys_group = Adw.PreferencesGroup()
        sys_group.set_title("Pacotes do Sistema")
        sys_group.set_description("Instalados via pacman")

        sys_deps = [
            ("pcscd", "pcsclite", "Serviço de leitura de tokens (smartcards)",
             "system-run-symbolic"),
            ("modutil", "nss", "Registro de certificados em navegadores",
             "preferences-system-network-symbolic"),
            ("opensc-tool", "opensc", "Acesso a tokens USB padrão (OpenSC)",
             "application-x-addon-symbolic"),
            ("ccid", "ccid", "Drivers de leitores de cartão/token",
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
        py_group.set_description("Componentes internos do aplicativo")

        py_deps = [
            ("PyKCS11", "python-pykcs11", "Comunicação com tokens A3"),
            ("pyudev", "python-pyudev", "Detecção de dispositivos USB"),
            ("cryptography", "python-cryptography", "Leitura de certificados digitais"),
            ("asn1crypto", "python-asn1crypto", "Decodificação de certificados"),
            ("oscrypto", "python-oscrypto", "Operações criptográficas"),
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
                dep_row_data,
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
        self.set_child(toolbar)

    @staticmethod
    def _is_valid_package_name(name: str) -> bool:
        """Validate package name to prevent command injection."""
        return bool(re.match(r"^[a-zA-Z0-9@._+-]+$", name))

    def _on_install_single_pkg(
        self,
        btn: Gtk.Button,
        pkg: str,
        row: Adw.ActionRow,
        suffix_box: Gtk.Box,
    ) -> None:
        if not self._is_valid_package_name(pkg):
            log.error("Invalid package name rejected: %s", pkg)
            return

        btn.set_sensitive(False)
        btn.set_label("Instalando…")

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
        btn.set_sensitive(False)

        action = "stop" if currently_active else "start"
        enable_action = "disable" if currently_active else "enable"

        def toggle_thread() -> None:
            try:
                subprocess.run(
                    ["pkexec", "systemctl", enable_action, svc_name],
                    capture_output=True, text=True, timeout=30,
                )
                result = subprocess.run(
                    ["pkexec", "systemctl", action, svc_name],
                    capture_output=True, text=True, timeout=30,
                )
                success = result.returncode == 0
            except Exception:
                success = False
            GLib.idle_add(on_done, success)

        def on_done(success: bool) -> bool:
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
    ) -> None:
        btn.set_sensitive(False)
        btn.set_label("Resolvendo…")

        pkgs = list({
            d["pkg"] for d in dep_row_data
            if d["type"] == "pkg" and self._is_valid_package_name(d["pkg"])
        })
        svcs = [d for d in dep_row_data if d["type"] == "svc"]

        def resolve_thread() -> None:
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
