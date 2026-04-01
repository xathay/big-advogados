"""Certificate details view — shows parsed certificate information."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Pango  # noqa: E402

from src.certificate.parser import CertificateInfo
from src.ui.certificate_widgets import (
    build_cert_details_group,
    build_holder_group,
    clear_container,
    create_validity_banner,
)


class CertificateView(Gtk.ScrolledWindow):
    """Detailed view of a digital certificate."""

    def __init__(self) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        # Status page (no certificate loaded)
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("channel-secure-symbolic")
        self._status_page.set_title("Nenhum certificado selecionado")
        self._status_page.set_description(
            "Selecione um token e insira o PIN para visualizar os certificados."
        )
        content.append(self._status_page)

        # Certificate details (hidden initially)
        self._details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._details_box.set_margin_top(8)
        self._details_box.set_margin_bottom(8)
        self._details_box.set_visible(False)
        content.append(self._details_box)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)
        clamp.set_child(content)
        self.set_child(clamp)

    def show_certificate(self, cert: CertificateInfo) -> None:
        """Display certificate details."""
        self._status_page.set_visible(False)
        self._details_box.set_visible(True)

        # Clear old content
        clear_container(self._details_box)

        # Validity banner
        self._details_box.append(create_validity_banner(cert))

        # Holder info group
        self._details_box.append(build_holder_group(cert))

        # Certificate details group
        self._details_box.append(build_cert_details_group(cert))

    def show_certificates_list(self, certs: list[CertificateInfo]) -> None:
        """Show a list of certificates to choose from."""
        if not certs:
            self._status_page.set_title("Nenhum certificado encontrado")
            self._status_page.set_description(
                "O token não contém certificados ou o PIN está incorreto."
            )
            self._status_page.set_visible(True)
            self._details_box.set_visible(False)
            return

        if len(certs) == 1:
            self.show_certificate(certs[0])
            return

        self._status_page.set_visible(False)
        self._details_box.set_visible(True)

        # Clear
        clear_container(self._details_box)

        group = Adw.PreferencesGroup()
        group.set_title("Certificados Encontrados")
        group.set_description("Selecione o certificado para ver os detalhes")

        for cert in certs:
            row = Adw.ActionRow()
            row.set_title(cert.holder_name or cert.common_name)
            row.set_subtitle(f"{cert.issuer_cn} • {cert.validity_status}")
            row.set_icon_name("channel-secure-symbolic")
            row.set_activatable(True)
            row.connect("activated", lambda _r, c=cert: self.show_certificate(c))

            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            row.add_suffix(arrow)
            group.add(row)

        self._details_box.append(group)

    def clear(self) -> None:
        self._status_page.set_title("Nenhum certificado selecionado")
        self._status_page.set_description(
            "Selecione um token e insira o PIN para visualizar os certificados."
        )
        self._status_page.set_visible(True)
        self._details_box.set_visible(False)
