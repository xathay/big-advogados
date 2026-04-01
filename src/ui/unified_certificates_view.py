"""Unified certificate management view — A1 (PFX) and A3 (Token USB).

Combines A1 certificate loading and A3 token detection into a single
scrollable view with both sections visible simultaneously.
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: E402

from src.certificate.token_database import TokenDatabase
from src.ui.a1_view import A1CertificateView
from src.ui.certificate_view import CertificateView
from src.ui.token_detect_view import TokenDetectView


class UnifiedCertificatesView(Gtk.ScrolledWindow):
    """Unified view for managing A1 and A3 digital certificates.

    Shows both A3 (Token USB) and A1 (PFX) sections vertically
    in a single scrollable area, no internal tab switching.
    """

    def __init__(self, token_db: TokenDatabase) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_vexpand(True)

        # ── A3 section: Token USB detection + certificates ──
        self._a3_frame = Gtk.Frame()
        self._a3_frame.set_margin_start(0)
        self._a3_frame.set_margin_end(0)
        self._a3_frame.add_css_class("view")

        self._a3_stack = Gtk.Stack()
        self._a3_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._a3_stack.set_transition_duration(200)

        self.token_view = TokenDetectView(token_db)
        self._a3_stack.add_named(self.token_view, "detect")

        self.cert_view = CertificateView()
        self._a3_stack.add_named(self.cert_view, "certs")

        self._a3_stack.set_visible_child_name("detect")
        self._a3_frame.set_child(self._a3_stack)
        content.append(self._a3_frame)

        # Separator between sections
        content.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # ── A1 section: PFX file loading ──
        self.a1_view = A1CertificateView()
        content.append(self.a1_view)

        self.set_child(content)

    def show_a3_certificates(self, certs: list) -> None:
        """Display loaded A3 certificates inline."""
        self._a3_stack.set_visible_child_name("certs")
        self.cert_view.show_certificates_list(certs)

    def reset_a3_view(self) -> None:
        """Return to token detection (after token removal, etc.)."""
        self._a3_stack.set_visible_child_name("detect")
        self.cert_view.clear()
