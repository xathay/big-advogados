"""Lock screen shown when the app starts with password protection enabled."""

from __future__ import annotations

from collections.abc import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from src.utils.app_lock import (
    verify_password,
    get_lockout_remaining,
    record_failed_attempt,
    reset_failed_attempts,
)


class LockDialog(Adw.Dialog):
    """Modal lock dialog that blocks app access until password is entered."""

    def __init__(self, on_unlocked: Callable[[], None]) -> None:
        super().__init__()
        self._on_unlocked = on_unlocked
        self._unlock_btn: Gtk.Button | None = None
        self._lockout_timer_id: int = 0

        self.set_title("Big Advogados")
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
        self._unlock_btn = Gtk.Button(label="Desbloquear")
        self._unlock_btn.add_css_class("suggested-action")
        self._unlock_btn.add_css_class("pill")
        self._unlock_btn.set_halign(Gtk.Align.CENTER)
        self._unlock_btn.set_size_request(200, -1)
        self._unlock_btn.connect("clicked", self._on_submit)
        box.append(self._unlock_btn)

        toolbar.set_content(box)
        self.set_child(toolbar)

        # Check if already locked out on startup
        remaining = get_lockout_remaining()
        if remaining > 0:
            self._start_lockout(remaining)

    def _on_submit(self, *_args: object) -> None:
        password = self._password_row.get_text()
        if not password:
            self._show_error("Digite a senha")
            return

        # Check active lockout
        remaining = get_lockout_remaining()
        if remaining > 0:
            self._start_lockout(remaining)
            self._password_row.set_text("")
            return

        if verify_password(password):
            reset_failed_attempts()
            self.force_close()
            self._on_unlocked()
        else:
            delay = record_failed_attempt()
            self._start_lockout(delay)

        self._password_row.set_text("")

    def _start_lockout(self, seconds: float) -> None:
        """Disable input and show countdown until lockout expires."""
        self._password_row.set_sensitive(False)
        if self._unlock_btn:
            self._unlock_btn.set_sensitive(False)
        self._show_error(f"Aguarde {int(seconds)}s antes de tentar novamente")

        # Cancel any existing timer
        if self._lockout_timer_id:
            GLib.source_remove(self._lockout_timer_id)

        self._lockout_timer_id = GLib.timeout_add_seconds(
            max(1, int(seconds)), self._end_lockout,
        )

    def _end_lockout(self) -> bool:
        """Re-enable input after lockout expires."""
        self._lockout_timer_id = 0
        # Double-check the lockout actually expired
        remaining = get_lockout_remaining()
        if remaining > 0:
            self._start_lockout(remaining)
            return False
        self._password_row.set_sensitive(True)
        if self._unlock_btn:
            self._unlock_btn.set_sensitive(True)
        self._show_error("")
        self._error_label.set_visible(False)
        return False  # Don't repeat

    def _show_error(self, message: str) -> None:
        self._error_label.set_label(message)
        self._error_label.set_visible(bool(message))
