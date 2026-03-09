"""Certificate details view — shows parsed certificate information."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Pango  # noqa: E402

from src.certificate.parser import CertificateInfo


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

        # Scrolled container for certificate details
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_vexpand(True)
        self._scroll.set_visible(False)
        content.append(self._scroll)

        self._details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._details_box.set_margin_top(8)
        self._details_box.set_margin_bottom(8)
        self._details_box.set_margin_start(8)
        self._details_box.set_margin_end(8)
        self._scroll.set_child(self._details_box)

        self.set_child(content)

    def show_certificate(self, cert: CertificateInfo) -> None:
        """Display certificate details."""
        self._status_page.set_visible(False)
        self._scroll.set_visible(True)

        # Clear old content
        child = self._details_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._details_box.remove(child)
            child = next_child

        # Validity banner
        validity_bar = self._create_validity_bar(cert)
        self._details_box.append(validity_bar)

        # Holder info group
        holder_group = Adw.PreferencesGroup()
        holder_group.set_title("Titular do Certificado")

        self._add_info_row(holder_group, "Nome", cert.holder_name, "avatar-default-symbolic")
        if cert.cpf:
            self._add_info_row(holder_group, "CPF", cert.cpf, "contact-new-symbolic")
        if cert.cnpj:
            self._add_info_row(holder_group, "CNPJ", cert.cnpj, "contact-new-symbolic")
        if cert.oab:
            self._add_info_row(holder_group, "OAB", cert.oab, "emblem-documents-symbolic")
        if cert.email:
            self._add_info_row(holder_group, "E-mail", cert.email, "mail-unread-symbolic")

        self._details_box.append(holder_group)

        # Certificate details group
        cert_group = Adw.PreferencesGroup()
        cert_group.set_title("Dados do Certificado")

        self._add_info_row(cert_group, "Nome Comum (CN)", cert.common_name)
        self._add_info_row(cert_group, "Número de Série", cert.serial_number)
        self._add_info_row(cert_group, "Emissora (CA)", cert.issuer_cn)
        if cert.not_before:
            self._add_info_row(
                cert_group, "Válido Desde",
                cert.not_before.strftime("%d/%m/%Y %H:%M"),
            )
        if cert.not_after:
            self._add_info_row(
                cert_group, "Válido Até",
                cert.not_after.strftime("%d/%m/%Y %H:%M"),
            )
        if cert.key_usage:
            self._add_info_row(cert_group, "Uso da Chave", cert.key_usage)

        self._details_box.append(cert_group)

    def show_certificates_list(self, certs: list[CertificateInfo]) -> None:
        """Show a list of certificates to choose from."""
        if not certs:
            self._status_page.set_title("Nenhum certificado encontrado")
            self._status_page.set_description(
                "O token não contém certificados ou o PIN está incorreto."
            )
            self._status_page.set_visible(True)
            self._scroll.set_visible(False)
            return

        if len(certs) == 1:
            self.show_certificate(certs[0])
            return

        self._status_page.set_visible(False)
        self._scroll.set_visible(True)

        # Clear
        child = self._details_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._details_box.remove(child)
            child = next_child

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
        self._scroll.set_visible(False)

    def _create_validity_bar(self, cert: CertificateInfo) -> Gtk.Box:
        bar = Gtk.Box(spacing=8)
        bar.set_halign(Gtk.Align.FILL)
        bar.add_css_class("card")
        bar.set_margin_bottom(8)

        inner = Gtk.Box(spacing=8)
        inner.set_margin_top(12)
        inner.set_margin_bottom(12)
        inner.set_margin_start(12)
        inner.set_margin_end(12)

        if cert.is_expired:
            icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
            icon.add_css_class("error")
            label = Gtk.Label(label="CERTIFICADO EXPIRADO")
            label.add_css_class("error")
        elif cert.days_to_expire <= 30:
            icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            icon.add_css_class("warning")
            label = Gtk.Label(
                label=f"EXPIRA EM {cert.days_to_expire} DIAS"
            )
            label.add_css_class("warning")
        else:
            icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            icon.add_css_class("success")
            label = Gtk.Label(
                label=f"VÁLIDO — expira em {cert.days_to_expire} dias"
            )
            label.add_css_class("success")

        label.add_css_class("heading")
        inner.append(icon)
        inner.append(label)
        bar.append(inner)
        return bar

    @staticmethod
    def _add_info_row(
        group: Adw.PreferencesGroup,
        title: str,
        value: str,
        icon_name: str = "",
    ) -> None:
        row = Adw.ActionRow()
        row.set_title(title)
        row.set_subtitle(value)
        if icon_name:
            row.set_icon_name(icon_name)
        row.set_subtitle_selectable(True)
        group.add(row)
