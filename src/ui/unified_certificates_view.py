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


class UnifiedCertificatesView(Gtk.Box):
    """Unified view for managing A1 and A3 digital certificates.

    Uses an ViewStack with internal tabs — A3 (Token USB) and A1 (PFX) —
    to give each section full height for scrolling.
    """

    def __init__(self, token_db: TokenDatabase) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Stack with two pages: A3 and A1
        self._stack = Adw.ViewStack()

        self.token_view = TokenDetectView(token_db)
        self.cert_view = CertificateView()

        # A3 page: detect → certs transition
        self._a3_stack = Gtk.Stack()
        self._a3_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._a3_stack.set_transition_duration(200)
        self._a3_stack.add_named(self.token_view, "detect")
        self._a3_stack.add_named(self.cert_view, "certs")
        self._a3_stack.set_visible_child_name("detect")

        page_a3 = self._stack.add_titled(self._a3_stack, "a3", "Token USB (A3)")
        page_a3.set_icon_name("drive-removable-media-symbolic")

        # A1 page
        self.a1_view = A1CertificateView()
        page_a1 = self._stack.add_titled(self.a1_view, "a1", "Certificado A1")
        page_a1.set_icon_name("application-certificate-symbolic")

        # Switcher bar
        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self._stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        switcher.set_margin_top(4)
        switcher.set_margin_bottom(4)
        self.append(switcher)

        self._stack.set_vexpand(True)
        self.append(self._stack)

    def show_a3_certificates(self, certs: list) -> None:
        """Display loaded A3 certificates inline."""
        self._a3_stack.set_visible_child_name("certs")
        self.cert_view.show_certificates_list(certs)

    def reset_a3_view(self) -> None:
        """Return to token detection (after token removal, etc.)."""
        self._a3_stack.set_visible_child_name("detect")
        self.cert_view.clear()
