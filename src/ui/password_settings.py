"""Dialog for setting, changing, or removing the app lock password."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: E402

from src.utils.app_lock import is_lock_enabled, set_password, verify_password, remove_password


class PasswordSettingsDialog(Adw.Dialog):
    """Adw.Dialog for managing the app lock password."""

    def __init__(self) -> None:
        super().__init__()
        self._locked = is_lock_enabled()
        self.set_title("Proteção por Senha")
        self.set_content_width(420)
        self.set_content_height(520)
        self.set_can_close(True)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        if self._locked:
            self._build_change_or_remove_ui(box)
        else:
            self._build_set_password_ui(box)

        scroll.set_child(box)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

    def _build_set_password_ui(self, box: Gtk.Box) -> None:
        """UI for setting a new password (protection currently disabled)."""
        status = Adw.StatusPage()
        status.set_icon_name("system-lock-screen-symbolic")
        status.set_title("Proteção desativada")
        status.set_description(
            "Defina uma senha para proteger o acesso ao gerenciador "
            "de certificados."
        )
        status.set_vexpand(False)
        box.append(status)

        group = Adw.PreferencesGroup()
        group.set_title("Nova Senha")

        self._new_pw = Adw.PasswordEntryRow()
        self._new_pw.set_title("Senha")
        group.add(self._new_pw)

        self._confirm_pw = Adw.PasswordEntryRow()
        self._confirm_pw.set_title("Confirmar senha")
        group.add(self._confirm_pw)

        box.append(group)

        # Error/success label
        self._error_label = Gtk.Label()
        self._error_label.add_css_class("error")
        self._error_label.set_visible(False)
        self._error_label.set_wrap(True)
        box.append(self._error_label)

        # Set button
        btn = Gtk.Button(label="Ativar Proteção")
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_size_request(200, -1)
        btn.connect("clicked", self._on_set_password)
        box.append(btn)

    def _build_change_or_remove_ui(self, box: Gtk.Box) -> None:
        """UI for changing or removing the password (protection currently enabled)."""
        status = Adw.StatusPage()
        status.set_icon_name("channel-secure-symbolic")
        status.set_title("Proteção ativada")
        status.set_description(
            "Altere ou remova a senha de proteção."
        )
        status.set_vexpand(False)
        box.append(status)

        group = Adw.PreferencesGroup()
        group.set_title("Senha Atual")

        self._current_pw = Adw.PasswordEntryRow()
        self._current_pw.set_title("Senha atual")
        group.add(self._current_pw)

        box.append(group)

        # New password section
        group2 = Adw.PreferencesGroup()
        group2.set_title("Nova Senha (deixe vazio para remover)")

        self._new_pw = Adw.PasswordEntryRow()
        self._new_pw.set_title("Nova senha")
        group2.add(self._new_pw)

        self._confirm_pw = Adw.PasswordEntryRow()
        self._confirm_pw.set_title("Confirmar nova senha")
        group2.add(self._confirm_pw)

        box.append(group2)

        # Error/success label
        self._error_label = Gtk.Label()
        self._error_label.add_css_class("error")
        self._error_label.set_visible(False)
        self._error_label.set_wrap(True)
        box.append(self._error_label)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)

        btn_remove = Gtk.Button(label="Remover Senha")
        btn_remove.add_css_class("destructive-action")
        btn_remove.add_css_class("pill")
        btn_remove.connect("clicked", self._on_remove_password)
        btn_box.append(btn_remove)

        btn_change = Gtk.Button(label="Alterar Senha")
        btn_change.add_css_class("suggested-action")
        btn_change.add_css_class("pill")
        btn_change.connect("clicked", self._on_change_password)
        btn_box.append(btn_change)

        box.append(btn_box)

    def _on_set_password(self, *_args: object) -> None:
        new_pw = self._new_pw.get_text()
        confirm = self._confirm_pw.get_text()

        if len(new_pw) < 4:
            self._show_error("A senha deve ter pelo menos 4 caracteres")
            return

        if new_pw != confirm:
            self._show_error("As senhas não coincidem")
            return

        set_password(new_pw)
        self._show_success("Proteção ativada com sucesso!")

    def _on_change_password(self, *_args: object) -> None:
        current = self._current_pw.get_text()
        new_pw = self._new_pw.get_text()
        confirm = self._confirm_pw.get_text()

        if not verify_password(current):
            self._show_error("Senha atual incorreta")
            return

        if len(new_pw) < 4:
            self._show_error("A nova senha deve ter pelo menos 4 caracteres")
            return

        if new_pw != confirm:
            self._show_error("As novas senhas não coincidem")
            return

        set_password(new_pw)
        self._show_success("Senha alterada com sucesso!")

    def _on_remove_password(self, *_args: object) -> None:
        current = self._current_pw.get_text()

        if not verify_password(current):
            self._show_error("Senha atual incorreta")
            return

        remove_password()
        self._show_success("Proteção removida com sucesso!")

    def _show_error(self, message: str) -> None:
        self._error_label.set_label(message)
        self._error_label.remove_css_class("success")
        self._error_label.add_css_class("error")
        self._error_label.set_visible(True)

    def _show_success(self, message: str) -> None:
        self._error_label.set_label(message)
        self._error_label.remove_css_class("error")
        self._error_label.add_css_class("success")
        self._error_label.set_visible(True)
