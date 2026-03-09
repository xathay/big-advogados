"""Lock screen shown when the app starts with password protection enabled."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from src.utils.app_lock import verify_password

MAX_ATTEMPTS = 3


class LockDialog(Adw.Dialog):
    """Modal lock dialog that blocks app access until password is entered."""

    def __init__(self, on_unlocked: "Callable[[], None]") -> None:
        super().__init__()
        self._on_unlocked = on_unlocked
        self._attempts = 0

        self.set_title("BigCertificados")
        self.set_content_width(400)
        self.set_content_height(480)
        self.set_can_close(False)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        toolbar.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(32)
        box.set_margin_end(32)

        # Icon
        icon = Gtk.Image.new_from_icon_name("channel-secure-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        box.append(icon)

        # Subtitle
        subtitle = Gtk.Label(label="Digite a senha para desbloquear")
        subtitle.add_css_class("dim-label")
        box.append(subtitle)

        # Password entry row in a PreferencesGroup
        group = Adw.PreferencesGroup()
        self._password_row = Adw.PasswordEntryRow()
        self._password_row.set_title("Senha")
        self._password_row.connect("entry-activated", self._on_submit)
        group.add(self._password_row)
        box.append(group)

        # Error label
        self._error_label = Gtk.Label()
        self._error_label.add_css_class("error")
        self._error_label.set_visible(False)
        self._error_label.set_wrap(True)
        box.append(self._error_label)

        # Unlock button
        unlock_btn = Gtk.Button(label="Desbloquear")
        unlock_btn.add_css_class("suggested-action")
        unlock_btn.add_css_class("pill")
        unlock_btn.set_halign(Gtk.Align.CENTER)
        unlock_btn.set_size_request(200, -1)
        unlock_btn.connect("clicked", self._on_submit)
        box.append(unlock_btn)

        toolbar.set_content(box)
        self.set_child(toolbar)

    def _on_submit(self, *_args: object) -> None:
        password = self._password_row.get_text()
        if not password:
            self._show_error("Digite a senha")
            return

        if verify_password(password):
            self.force_close()
            self._on_unlocked()
        else:
            self._attempts += 1
            remaining = MAX_ATTEMPTS - self._attempts
            if remaining > 0:
                self._show_error(
                    f"Senha incorreta — {remaining} tentativa(s) restante(s)"
                )
            else:
                self._show_error("Número máximo de tentativas atingido")
                self._password_row.set_sensitive(False)

        self._password_row.set_text("")

    def _show_error(self, message: str) -> None:
        self._error_label.set_label(message)
        self._error_label.set_visible(True)
