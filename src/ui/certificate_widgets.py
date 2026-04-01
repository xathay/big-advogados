"""Shared certificate display widgets used across multiple views."""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from src.certificate.parser import CertificateInfo


def create_validity_banner(cert: CertificateInfo, prefix: str = "") -> Gtk.Box:
    """Create a colored validity status card for a certificate.

    Args:
        cert: The certificate info to display.
        prefix: Optional prefix for the label (e.g. "CERTIFICADO A1").
    """
    bar = Gtk.Box(spacing=8)
    bar.set_halign(Gtk.Align.FILL)
    bar.add_css_class("card")
    bar.set_margin_bottom(8)

    inner = Gtk.Box(spacing=8)
    inner.set_margin_top(12)
    inner.set_margin_bottom(12)
    inner.set_margin_start(12)
    inner.set_margin_end(12)

    label_prefix = f"{prefix} " if prefix else ""

    if cert.is_expired:
        icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        icon.add_css_class("error")
        label = Gtk.Label(label=f"{label_prefix}CERTIFICADO EXPIRADO".strip())
        label.add_css_class("error")
    elif cert.days_to_expire <= 30:
        icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        icon.add_css_class("warning")
        label = Gtk.Label(label=f"EXPIRA EM {cert.days_to_expire} DIAS")
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


def add_info_row(
    group: Adw.PreferencesGroup,
    title: str,
    value: str,
    icon_name: str = "",
) -> None:
    """Add a read-only info row to a preferences group."""
    row = Adw.ActionRow()
    row.set_title(title)
    row.set_subtitle(value)
    if icon_name:
        row.set_icon_name(icon_name)
    row.set_subtitle_selectable(True)
    group.add(row)


def build_holder_group(cert: CertificateInfo) -> Adw.PreferencesGroup:
    """Build the 'Titular do Certificado' preferences group."""
    group = Adw.PreferencesGroup()
    group.set_title("Titular do Certificado")

    add_info_row(group, "Nome", cert.holder_name, "avatar-default-symbolic")
    if cert.cpf:
        add_info_row(group, "CPF", cert.cpf, "contact-new-symbolic")
    if cert.cnpj:
        add_info_row(group, "CNPJ", cert.cnpj, "contact-new-symbolic")
    if cert.oab:
        add_info_row(group, "OAB", cert.oab, "emblem-documents-symbolic")
    if cert.email:
        add_info_row(group, "E-mail", cert.email, "mail-unread-symbolic")

    return group


def build_cert_details_group(
    cert: CertificateInfo,
    cert_type_label: str = "",
) -> Adw.PreferencesGroup:
    """Build the 'Dados do Certificado' preferences group."""
    group = Adw.PreferencesGroup()
    group.set_title("Dados do Certificado")

    if cert_type_label:
        add_info_row(group, "Tipo", cert_type_label)
    add_info_row(group, "Nome Comum (CN)", cert.common_name)
    add_info_row(group, "Número de Série", cert.serial_number)
    add_info_row(group, "Emissora (CA)", cert.issuer_cn)
    if cert.not_before:
        add_info_row(
            group, "Válido Desde",
            cert.not_before.strftime("%d/%m/%Y %H:%M"),
        )
    if cert.not_after:
        add_info_row(
            group, "Válido Até",
            cert.not_after.strftime("%d/%m/%Y %H:%M"),
        )
    if cert.key_usage:
        add_info_row(group, "Uso da Chave", cert.key_usage)

    return group


def clear_container(box: Gtk.Box) -> None:
    """Remove all children from a Gtk.Box."""
    child = box.get_first_child()
    while child:
        next_child = child.get_next_sibling()
        box.remove(child)
        child = next_child


def show_pfx_password_dialog(
    parent: Gtk.Widget,
    pfx_path: str,
    on_success: Callable[[str, str, CertificateInfo], None],
    ok_label: str = "Abrir",
) -> None:
    """Show a dialog to enter PFX password (shared between A1 and Signer views).

    Args:
        parent: The parent widget (used to get the window root).
        pfx_path: Path to the PFX/P12 file.
        on_success: Callback(pfx_path, password, cert_info) on successful load.
        ok_label: Label for the confirm button.
    """
    from src.certificate.a1_manager import A1Manager

    dialog = Adw.Dialog()
    dialog.set_title("Senha do Certificado")
    dialog.set_content_width(400)
    dialog.set_content_height(220)

    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    toolbar.add_top_bar(header)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_margin_top(24)
    box.set_margin_bottom(24)
    box.set_margin_start(24)
    box.set_margin_end(24)

    filename = os.path.basename(pfx_path)
    file_label = Gtk.Label(label=f"Arquivo: {filename}")
    file_label.add_css_class("dim-label")
    file_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
    box.append(file_label)

    pwd_entry = Gtk.PasswordEntry()
    pwd_entry.props.placeholder_text = "Senha do certificado PFX"
    pwd_entry.set_show_peek_icon(True)
    box.append(pwd_entry)

    error_label = Gtk.Label()
    error_label.add_css_class("error")
    error_label.set_visible(False)
    box.append(error_label)

    btn_box = Gtk.Box(spacing=12, homogeneous=True)
    btn_box.set_halign(Gtk.Align.END)

    cancel_btn = Gtk.Button(label="Cancelar")
    cancel_btn.connect("clicked", lambda _b: dialog.close())
    btn_box.append(cancel_btn)

    ok_btn = Gtk.Button(label=ok_label)
    ok_btn.add_css_class("suggested-action")
    btn_box.append(ok_btn)

    box.append(btn_box)

    def on_confirm(*_args: object) -> None:
        password = pwd_entry.get_text()
        ok_btn.set_sensitive(False)
        cancel_btn.set_sensitive(False)
        pwd_entry.set_sensitive(False)

        def load_thread() -> None:
            mgr = A1Manager()
            cert_info = mgr.load_pfx(pfx_path, password)
            GLib.idle_add(on_load_result, cert_info, password)

        def on_load_result(
            cert_info: Optional[CertificateInfo], pwd: str,
        ) -> bool:
            if cert_info:
                dialog.close()
                on_success(pfx_path, pwd, cert_info)
            else:
                error_label.set_label("Senha incorreta ou arquivo inválido")
                error_label.set_visible(True)
                ok_btn.set_sensitive(True)
                cancel_btn.set_sensitive(True)
                pwd_entry.set_sensitive(True)
                pwd_entry.grab_focus()
            return False

        threading.Thread(target=load_thread, daemon=True).start()

    ok_btn.connect("clicked", on_confirm)
    pwd_entry.connect("activate", on_confirm)

    toolbar.set_content(box)
    dialog.set_child(toolbar)

    window = parent.get_root()
    dialog.present(window)
