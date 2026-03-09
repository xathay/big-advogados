"""PIN dialog for token authentication."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: E402


class PinDialog(Adw.Dialog):
    """Dialog to request the token PIN from the user."""

    def __init__(self, token_label: str = "") -> None:
        super().__init__()
        self.set_title("Digite o PIN")
        self.set_content_width(360)
        self.set_content_height(200)

        self._pin: str = ""
        self._confirmed = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        # Description
        if token_label:
            desc = Gtk.Label(label=f"Token: {token_label}")
            desc.add_css_class("dim-label")
            box.append(desc)

        # PIN entry
        self._pin_entry = Gtk.PasswordEntry()
        self._pin_entry.set_placeholder_text("PIN do certificado")
        self._pin_entry.set_show_peek_icon(True)
        self._pin_entry.connect("activate", self._on_confirm)
        box.append(self._pin_entry)

        # Buttons
        btn_box = Gtk.Box(spacing=12, homogeneous=True)
        btn_box.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", self._on_cancel)
        btn_box.append(cancel_btn)

        ok_btn = Gtk.Button(label="Entrar")
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", self._on_confirm)
        btn_box.append(ok_btn)

        box.append(btn_box)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)
        toolbar.set_content(box)
        self.set_child(toolbar)

    @property
    def pin(self) -> str:
        return self._pin

    @property
    def confirmed(self) -> bool:
        return self._confirmed

    def _on_confirm(self, *_args: object) -> None:
        self._pin = self._pin_entry.get_text()
        self._confirmed = True
        self.close()

    def _on_cancel(self, *_args: object) -> None:
        self._confirmed = False
        self.close()
