"""PDF signer view — select PDFs and sign with digital certificate."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio  # noqa: E402

from src.certificate.pdf_signer import (
    SignatureOptions,
    SignatureResult,
    batch_sign,
    sign_pdf,
    sign_pdf_a3,
    sign_pdf_vidaas,
)
from src.certificate.a3_manager import A3Manager, TokenSlotInfo
from src.certificate.parser import CertificateInfo
from src.certificate.vidaas_manager import VidaaSManager, VidaaSMode, VidaaSState
from src.browser.nss_config import import_pfx_chain_for_papers
from src.ui.certificate_widgets import show_pfx_password_dialog

log = logging.getLogger(__name__)

CERT_TYPE_A1 = 0
CERT_TYPE_A3 = 1
CERT_TYPE_VIDAAS = 2


class SignerView(Gtk.ScrolledWindow):
    """View for signing PDFs with digital certificates."""

    def __init__(self, a3_manager: Optional[A3Manager] = None) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._pdf_paths: list[str] = []
        self._pfx_path: Optional[str] = None
        self._pfx_password: Optional[str] = None
        self._cert_type: int = CERT_TYPE_A1
        self._a3_manager: Optional[A3Manager] = a3_manager
        self._a3_slot_id: Optional[int] = None
        self._a3_pin: Optional[str] = None
        self._a3_cert_info: Optional[CertificateInfo] = None
        self._a3_cert_der: Optional[bytes] = None
        self._vidaas_manager: Optional[VidaaSManager] = None
        self._vidaas_cert_info: Optional[CertificateInfo] = None
        self._signing_in_progress = False

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.set_margin_top(12)
        self._content.set_margin_bottom(12)
        self._content.set_margin_start(12)
        self._content.set_margin_end(12)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)
        clamp.set_child(self._content)
        self.set_child(clamp)

        self._build_empty_state()
        self._build_form()

    # ── Build UI ─────────────────────────────────────────────────

    def _build_empty_state(self) -> None:
        """Build the initial empty state with instructions."""
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("document-edit-symbolic")
        self._status_page.set_title("Assinador de PDF")
        self._status_page.set_description(
            "Assine documentos PDF com certificado digital A1 ou token A3.\n"
            "Selecione os arquivos PDF e o certificado para começar."
        )
        self._content.append(self._status_page)

    def _build_form(self) -> None:
        """Build the signing wizard as a 4-step flow."""
        self._form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._form_box.set_visible(False)
        self._content.append(self._form_box)

        # ── Step indicator ──
        self._step_labels: list[Gtk.Label] = []
        step_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        step_bar.set_halign(Gtk.Align.CENTER)
        step_bar.set_margin_top(8)
        step_bar.set_margin_bottom(12)

        step_names = ["Documentos", "Certificado", "Opções", "Assinar"]
        for i, name in enumerate(step_names):
            pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            pill.set_margin_start(4)
            pill.set_margin_end(4)

            num = Gtk.Label(label=str(i + 1))
            num.add_css_class("caption")
            num.add_css_class("accent")
            num.set_width_chars(3)
            num.set_xalign(0.5)
            pill.append(num)

            lbl = Gtk.Label(label=name)
            lbl.add_css_class("caption")
            pill.append(lbl)

            self._step_labels.append(lbl)
            step_bar.append(pill)

            if i < len(step_names) - 1:
                sep = Gtk.Label(label="›")
                sep.add_css_class("dim-label")
                sep.set_margin_start(4)
                sep.set_margin_end(4)
                step_bar.append(sep)

        self._form_box.append(step_bar)

        # ── Wizard Stack ──
        self._wizard_stack = Gtk.Stack()
        self._wizard_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._wizard_stack.set_transition_duration(200)
        self._wizard_stack.set_vexpand(True)
        self._form_box.append(self._wizard_stack)

        # ══ Step 1: PDF files ══
        step1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        step1.set_margin_top(4)

        pdf_group = Adw.PreferencesGroup()
        pdf_group.set_title("Documentos PDF")
        pdf_group.set_description("Arquivos que serão assinados digitalmente")
        step1.append(pdf_group)

        self._pdf_list_box = Gtk.ListBox()
        self._pdf_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._pdf_list_box.add_css_class("boxed-list")
        pdf_group.add(self._pdf_list_box)

        pdf_btn_box = Gtk.Box(spacing=8)
        pdf_btn_box.set_halign(Gtk.Align.CENTER)
        pdf_btn_box.set_margin_top(8)

        add_pdf_btn = Gtk.Button()
        add_pdf_btn.set_icon_name("list-add-symbolic")
        add_pdf_btn.set_tooltip_text("Adicionar mais PDFs")
        add_pdf_btn.add_css_class("circular")
        add_pdf_btn.connect("clicked", self._on_add_pdf_clicked)
        pdf_btn_box.append(add_pdf_btn)

        clear_pdf_btn = Gtk.Button()
        clear_pdf_btn.set_icon_name("edit-clear-all-symbolic")
        clear_pdf_btn.set_tooltip_text("Limpar lista")
        clear_pdf_btn.add_css_class("circular")
        clear_pdf_btn.connect("clicked", self._on_clear_pdfs_clicked)
        pdf_btn_box.append(clear_pdf_btn)

        pdf_group.add(pdf_btn_box)

        # Nav: Next
        step1_nav = self._make_nav_box(None, "Próximo: Certificado")
        self._step1_next = step1_nav._next_btn  # noqa: SLF001
        self._step1_next.connect("clicked", lambda _b: self._go_to_step("step2"))
        self._step1_next.set_sensitive(False)
        step1.append(step1_nav)

        self._wizard_stack.add_named(step1, "step1")

        # ══ Step 2: Certificate ══
        step2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        step2.set_margin_top(4)

        cert_group = Adw.PreferencesGroup()
        cert_group.set_title("Certificado Digital")
        cert_group.set_description("Selecione o tipo e o certificado para assinatura")
        step2.append(cert_group)

        self._cert_type_row = Adw.ComboRow()
        self._cert_type_row.set_title("Tipo de Certificado")
        self._cert_type_row.set_subtitle("Escolha o tipo de certificado digital")
        self._cert_type_row.set_icon_name("dialog-password-symbolic")
        type_model = Gtk.StringList.new([
            "Certificado A1 (PFX/P12)",
            "Token A3 (Smart Card)",
            "VidaaS Connect (Nuvem)",
        ])
        self._cert_type_row.set_model(type_model)
        self._cert_type_row.set_selected(CERT_TYPE_A1)
        self._cert_type_row.connect("notify::selected", self._on_cert_type_changed)
        cert_group.add(self._cert_type_row)

        self._cert_row = Adw.ActionRow()
        self._cert_row.set_title("Nenhum certificado selecionado")
        self._cert_row.set_subtitle("Clique para selecionar o arquivo PFX")
        self._cert_row.set_icon_name("application-certificate-symbolic")
        self._cert_row.set_activatable(True)
        self._cert_row.connect("activated", self._on_select_cert_clicked)

        change_cert_btn = Gtk.Button()
        change_cert_btn.set_icon_name("document-open-symbolic")
        change_cert_btn.set_tooltip_text("Selecionar certificado")
        change_cert_btn.set_valign(Gtk.Align.CENTER)
        change_cert_btn.add_css_class("flat")
        change_cert_btn.connect("clicked", self._on_select_cert_clicked)
        self._change_cert_btn = change_cert_btn
        self._cert_row.add_suffix(change_cert_btn)

        self._remove_cert_btn = Gtk.Button()
        self._remove_cert_btn.set_icon_name("edit-clear-symbolic")
        self._remove_cert_btn.set_tooltip_text("Remover certificado")
        self._remove_cert_btn.set_valign(Gtk.Align.CENTER)
        self._remove_cert_btn.add_css_class("flat")
        self._remove_cert_btn.add_css_class("error")
        self._remove_cert_btn.set_visible(False)
        self._remove_cert_btn.connect("clicked", self._on_remove_cert_clicked)
        self._cert_row.add_suffix(self._remove_cert_btn)

        cert_group.add(self._cert_row)

        # Nav: Back / Next
        step2_nav = self._make_nav_box("Voltar", "Próximo: Opções")
        step2_nav._back_btn.connect("clicked", lambda _b: self._go_to_step("step1"))  # noqa: SLF001
        self._step2_next = step2_nav._next_btn  # noqa: SLF001
        self._step2_next.connect("clicked", lambda _b: self._go_to_step("step3"))
        self._step2_next.set_sensitive(False)
        step2.append(step2_nav)

        self._wizard_stack.add_named(step2, "step2")

        # ══ Step 3: Signature options ══
        step3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        step3.set_margin_top(4)

        opts_group = Adw.PreferencesGroup()
        opts_group.set_title("Opções da Assinatura")
        step3.append(opts_group)

        self._reason_row = Adw.EntryRow()
        self._reason_row.set_title("Motivo")
        self._reason_row.set_text("Documento assinado digitalmente")
        opts_group.add(self._reason_row)

        self._location_row = Adw.EntryRow()
        self._location_row.set_title("Local")
        self._location_row.set_text("")
        opts_group.add(self._location_row)

        self._visible_row = Adw.SwitchRow()
        self._visible_row.set_title("Carimbo visível")
        self._visible_row.set_subtitle("Insere selo de assinatura no rodapé do PDF")
        self._visible_row.set_active(True)
        opts_group.add(self._visible_row)

        self._page_row = Adw.ComboRow()
        self._page_row.set_title("Página do carimbo")
        page_model = Gtk.StringList.new([
            "Última página",
            "Primeira página",
            "Todas as páginas",
        ])
        self._page_row.set_model(page_model)
        self._page_row.set_selected(0)
        opts_group.add(self._page_row)

        # Papers configuration
        papers_group = Adw.PreferencesGroup()
        papers_group.set_title("Visualizador de PDFs")
        papers_group.set_description(
            "Importe o certificado no sistema para que o Papers "
            "(GNOME) valide as assinaturas digitais"
        )
        step3.append(papers_group)

        self._papers_row = Adw.ActionRow()
        self._papers_row.set_title("Configurar Papers")
        self._papers_row.set_subtitle("Importar cadeia de certificados no NSS")
        self._papers_row.set_icon_name("org.gnome.Papers")
        self._papers_row.set_activatable(True)
        self._papers_row.connect("activated", self._on_configure_papers)

        papers_btn = Gtk.Button()
        papers_btn.set_icon_name("emblem-system-symbolic")
        papers_btn.set_tooltip_text("Configurar Papers")
        papers_btn.set_valign(Gtk.Align.CENTER)
        papers_btn.add_css_class("flat")
        papers_btn.connect("clicked", self._on_configure_papers)
        self._papers_row.add_suffix(papers_btn)

        papers_group.add(self._papers_row)

        # Nav: Back / Sign
        step3_nav = self._make_nav_box("Voltar", None)
        step3_nav._back_btn.connect("clicked", lambda _b: self._go_to_step("step2"))  # noqa: SLF001
        step3.append(step3_nav)

        # Sign button (replaces "Next" on last form step)
        self._sign_btn = Gtk.Button(label="Assinar PDF(s)")
        self._sign_btn.add_css_class("suggested-action")
        self._sign_btn.add_css_class("pill")
        self._sign_btn.set_halign(Gtk.Align.CENTER)
        self._sign_btn.set_margin_top(8)
        self._sign_btn.set_margin_bottom(8)
        self._sign_btn.set_sensitive(False)
        self._sign_btn.connect("clicked", self._on_sign_clicked)
        step3.append(self._sign_btn)

        self._wizard_stack.add_named(step3, "step3")

        # ══ Step 4: Progress + Results ══
        self._step4_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._step4_box.set_margin_top(4)

        self._progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._progress_box.set_margin_top(8)
        self._step4_box.append(self._progress_box)

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)
        self._progress_box.append(self._progress_bar)

        self._progress_label = Gtk.Label()
        self._progress_label.add_css_class("dim-label")
        self._progress_box.append(self._progress_label)

        self._results_group = Adw.PreferencesGroup()
        self._results_group.set_title("Resultados")
        self._results_group.set_visible(False)
        self._step4_box.append(self._results_group)

        # "New signing" button
        self._new_signing_btn = Gtk.Button(label="Nova Assinatura")
        self._new_signing_btn.add_css_class("pill")
        self._new_signing_btn.set_halign(Gtk.Align.CENTER)
        self._new_signing_btn.set_margin_top(16)
        self._new_signing_btn.connect("clicked", lambda _b: self._go_to_step("step1"))
        self._step4_box.append(self._new_signing_btn)

        self._wizard_stack.add_named(self._step4_box, "step4")

        # ── Select PDFs button (initially visible) ──
        select_btn = Gtk.Button(label="Selecionar Arquivos PDF")
        select_btn.add_css_class("suggested-action")
        select_btn.add_css_class("pill")
        select_btn.set_halign(Gtk.Align.CENTER)
        select_btn.set_margin_top(8)
        select_btn.connect("clicked", self._on_add_pdf_clicked)
        self._select_initial_btn = select_btn
        self._content.append(select_btn)

    def _make_nav_box(
        self, back_label: str | None, next_label: str | None,
    ) -> Gtk.Box:
        """Create a navigation bar with optional Back/Next buttons."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_margin_top(16)
        box.set_margin_bottom(8)

        if back_label:
            back_btn = Gtk.Button(label=back_label)
            back_btn.add_css_class("pill")
            box.append(back_btn)
            box._back_btn = back_btn  # noqa: SLF001

        if next_label:
            next_btn = Gtk.Button(label=next_label)
            next_btn.add_css_class("suggested-action")
            next_btn.add_css_class("pill")
            box.append(next_btn)
            box._next_btn = next_btn  # noqa: SLF001

        return box

    def _go_to_step(self, step_name: str) -> None:
        """Navigate to a wizard step and update the step indicator."""
        self._wizard_stack.set_visible_child_name(step_name)

        step_index = {"step1": 0, "step2": 1, "step3": 2, "step4": 3}.get(step_name, 0)
        for i, lbl in enumerate(self._step_labels):
            if i == step_index:
                lbl.remove_css_class("dim-label")
                lbl.add_css_class("accent")
            else:
                lbl.remove_css_class("accent")
                lbl.add_css_class("dim-label")

    # ── PDF file management ──────────────────────────────────────

    def _on_add_pdf_clicked(self, _widget: Gtk.Widget) -> None:
        """Open file chooser for PDF files (multiple selection)."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Selecionar Documentos PDF")

        filter_pdf = Gtk.FileFilter()
        filter_pdf.set_name("Documentos PDF (*.pdf)")
        filter_pdf.add_mime_type("application/pdf")
        filter_pdf.add_pattern("*.pdf")
        filter_pdf.add_pattern("*.PDF")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_pdf)
        dialog.set_filters(filters)
        dialog.set_default_filter(filter_pdf)

        window = self.get_root()
        dialog.open_multiple(window, None, self._on_pdfs_chosen)

    def _on_pdfs_chosen(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult,
    ) -> None:
        try:
            files = dialog.open_multiple_finish(result)
            if files:
                for i in range(files.get_n_items()):
                    gfile = files.get_item(i)
                    path = gfile.get_path()
                    if path and path not in self._pdf_paths:
                        self._pdf_paths.append(path)
                self._update_pdf_list()
                self._transition_to_form()
        except GLib.Error as exc:
            if exc.code != 2:  # user cancelled
                log.error("File dialog error: %s", exc)

    def _update_pdf_list(self) -> None:
        """Refresh the PDF file list display."""
        # Clear existing rows
        while True:
            row = self._pdf_list_box.get_row_at_index(0)
            if row is None:
                break
            self._pdf_list_box.remove(row)

        for path in self._pdf_paths:
            row = Adw.ActionRow()
            row.set_title(os.path.basename(path))
            row.set_subtitle(os.path.dirname(path))
            row.set_icon_name("application-pdf-symbolic")

            # File size
            try:
                size = Path(path).stat().st_size
                size_str = _format_size(size)
                size_label = Gtk.Label(label=size_str)
                size_label.add_css_class("dim-label")
                size_label.set_valign(Gtk.Align.CENTER)
                row.add_suffix(size_label)
            except OSError:
                pass

            # Remove button
            remove_btn = Gtk.Button()
            remove_btn.set_icon_name("edit-delete-symbolic")
            remove_btn.set_tooltip_text("Remover da lista")
            remove_btn.set_valign(Gtk.Align.CENTER)
            remove_btn.add_css_class("flat")
            remove_btn.add_css_class("error")
            remove_btn.connect("clicked", self._on_remove_pdf, path)
            row.add_suffix(remove_btn)

            self._pdf_list_box.append(row)

        self._update_sign_button_state()

    def _on_remove_pdf(self, _btn: Gtk.Button, path: str) -> None:
        if path in self._pdf_paths:
            self._pdf_paths.remove(path)
            self._update_pdf_list()

            if not self._pdf_paths:
                self._transition_to_empty()

    def _on_clear_pdfs_clicked(self, _btn: Gtk.Button) -> None:
        self._pdf_paths.clear()
        self._update_pdf_list()
        self._transition_to_empty()

    # ── Certificate type switching ─────────────────────────────

    def _on_cert_type_changed(self, row: Adw.ComboRow, _pspec: object) -> None:
        """Handle certificate type change between A1, A3, and VidaaS."""
        self._cert_type = row.get_selected()
        self._clear_certificate_state()

        if self._cert_type == CERT_TYPE_A1:
            self._cert_row.set_subtitle("Clique para selecionar o arquivo PFX")
            self._change_cert_btn.set_icon_name("document-open-symbolic")
            self._change_cert_btn.set_tooltip_text("Selecionar certificado")
        elif self._cert_type == CERT_TYPE_A3:
            self._cert_row.set_subtitle("Clique para detectar o token A3")
            self._change_cert_btn.set_icon_name("media-removable-symbolic")
            self._change_cert_btn.set_tooltip_text("Detectar token")
        elif self._cert_type == CERT_TYPE_VIDAAS:
            self._cert_row.set_subtitle("Clique para conectar ao VidaaS Connect")
            self._change_cert_btn.set_icon_name("network-wireless-symbolic")
            self._change_cert_btn.set_tooltip_text("Conectar VidaaS")

    def _on_remove_cert_clicked(self, _btn: Gtk.Button) -> None:
        """Remove the currently selected certificate."""
        self._clear_certificate_state()

    def _clear_certificate_state(self) -> None:
        """Reset all certificate state to unselected."""
        self._pfx_path = None
        self._pfx_password = None
        self._a3_slot_id = None
        self._a3_pin = None
        self._a3_cert_info = None
        self._a3_cert_der = None

        self._cert_row.set_title("Nenhum certificado selecionado")
        self._cert_row.set_icon_name("application-certificate-symbolic")
        self._remove_cert_btn.set_visible(False)

        if self._cert_type == CERT_TYPE_A1:
            self._cert_row.set_subtitle("Clique para selecionar o arquivo PFX")
        else:
            self._cert_row.set_subtitle("Clique para detectar o token A3")

        self._update_sign_button_state()

    # ── Certificate selection ────────────────────────────────────

    def _on_select_cert_clicked(self, _widget: Gtk.Widget) -> None:
        """Route certificate selection based on type."""
        if self._cert_type == CERT_TYPE_A1:
            self._select_a1_cert()
        elif self._cert_type == CERT_TYPE_A3:
            self._select_a3_cert()
        elif self._cert_type == CERT_TYPE_VIDAAS:
            self._select_vidaas_cert()

    def _select_vidaas_cert(self) -> None:
        """Detect VidaaS cloud certificate via PKCS#11."""
        if self._a3_manager is None:
            self._cert_row.set_subtitle("Suporte a PKCS#11 indisponível")
            return

        if self._vidaas_manager is None:
            self._vidaas_manager = VidaaSManager(self._a3_manager)

        self._cert_row.set_subtitle("Detectando VidaaS Connect...")
        self._cert_row.set_sensitive(False)

        vidaas = self._vidaas_manager

        def detect_thread() -> None:
            status = vidaas.detect_vidaas_token()
            GLib.idle_add(on_vidaas_detected, status)

        def on_vidaas_detected(status) -> bool:
            self._cert_row.set_sensitive(True)

            if status.state != VidaaSState.CONNECTED:
                self._cert_row.set_subtitle(status.message)
                return False

            # Token found — list certificates
            certs = vidaas.list_certificates()
            if not certs:
                self._cert_row.set_subtitle(
                    "Token VidaaS detectado mas sem certificados — "
                    "verifique o app no celular"
                )
                return False

            # Use first certificate
            cert_info = certs[0]
            self._vidaas_cert_info = cert_info
            self._update_cert_row(cert_info)
            self._update_sign_button_state()
            return False

        threading.Thread(target=detect_thread, daemon=True).start()

    def _select_a1_cert(self) -> None:
        """Open file chooser for PFX/P12 certificate."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Selecionar Certificado A1 (PFX)")

        filter_pfx = Gtk.FileFilter()
        filter_pfx.set_name("Certificados PFX/P12 (*.pfx, *.p12)")
        filter_pfx.add_pattern("*.pfx")
        filter_pfx.add_pattern("*.PFX")
        filter_pfx.add_pattern("*.p12")
        filter_pfx.add_pattern("*.P12")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_pfx)
        dialog.set_filters(filters)
        dialog.set_default_filter(filter_pfx)

        window = self.get_root()
        dialog.open(window, None, self._on_cert_chosen)

    def _on_cert_chosen(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult,
    ) -> None:
        try:
            file = dialog.open_finish(result)
            if file:
                path = file.get_path()
                if path:
                    self._prompt_pfx_password(path)
        except GLib.Error as exc:
            if exc.code != 2:
                log.error("File dialog error: %s", exc)

    def _prompt_pfx_password(self, pfx_path: str) -> None:
        """Ask for PFX password and validate it."""
        def on_success(path: str, password: str, cert_info: CertificateInfo) -> None:
            self._pfx_path = path
            self._pfx_password = password
            self._update_cert_row(cert_info)
            self._remove_cert_btn.set_visible(True)

        show_pfx_password_dialog(self, pfx_path, on_success, ok_label="Confirmar")

    def _update_cert_row(self, cert_info: CertificateInfo) -> None:
        """Update the certificate row with loaded certificate info."""

        holder = cert_info.holder_name or cert_info.common_name
        self._cert_row.set_title(holder)

        subtitle_parts = []
        if cert_info.cpf:
            subtitle_parts.append(f"CPF: {cert_info.cpf}")
        if cert_info.oab:
            subtitle_parts.append(f"OAB: {cert_info.oab}")
        if cert_info.issuer_cn:
            subtitle_parts.append(f"AC: {cert_info.issuer_cn}")

        if self._cert_type == CERT_TYPE_A1:
            fallback = os.path.basename(self._pfx_path or "")
        else:
            fallback = "Token A3"

        self._cert_row.set_subtitle(" | ".join(subtitle_parts) if subtitle_parts else fallback)

        # Validity indicator
        if cert_info.is_expired:
            self._cert_row.set_icon_name("dialog-error-symbolic")
        elif cert_info.days_to_expire <= 30:
            self._cert_row.set_icon_name("dialog-warning-symbolic")
        else:
            self._cert_row.set_icon_name("emblem-ok-symbolic")

        self._remove_cert_btn.set_visible(True)
        self._update_sign_button_state()

    # ── A3 Token selection ───────────────────────────────────────

    def _select_a3_cert(self) -> None:
        """Detect A3 tokens and let the user select a certificate."""
        mgr = self._a3_manager
        if mgr is None or not mgr.is_available:
            self._cert_row.set_subtitle("Suporte a token A3 indisponível (PyKCS11)")
            return

        self._cert_row.set_subtitle("Detectando tokens...")
        self._cert_row.set_sensitive(False)

        def detect_thread() -> None:
            module = mgr.try_all_modules()
            if module:
                slots = mgr.get_slots()
            else:
                slots = []
            GLib.idle_add(on_detect_done, slots)

        def on_detect_done(slots: list) -> bool:
            self._cert_row.set_sensitive(True)

            if not slots:
                self._cert_row.set_subtitle(
                    "Nenhum token detectado — insira o token e tente novamente"
                )
                return False

            if len(slots) == 1:
                self._a3_prompt_pin(slots[0])
            else:
                self._a3_select_slot(slots)
            return False

        threading.Thread(target=detect_thread, daemon=True).start()

    def _a3_select_slot(self, slots: list) -> None:
        """Show slot/token selection when multiple tokens found."""
        dialog = Adw.Dialog()
        dialog.set_title("Selecionar Token")
        dialog.set_content_width(400)
        dialog.set_content_height(300)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        desc = Gtk.Label(label="Vários tokens detectados. Selecione um:")
        desc.add_css_class("dim-label")
        box.append(desc)

        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.add_css_class("boxed-list")

        for slot in slots:
            row = Adw.ActionRow()
            row.set_title(slot.label or f"Slot {slot.slot_id}")
            row.set_subtitle(f"{slot.manufacturer} — {slot.model}")
            row.set_icon_name("drive-removable-media-symbolic")
            row.set_activatable(True)
            row.connect("activated", lambda _r, s=slot, d=dialog: (
                d.close(), self._a3_prompt_pin(s),
            ))
            list_box.append(row)

        box.append(list_box)
        toolbar.set_content(box)
        dialog.set_child(toolbar)

        window = self.get_root()
        dialog.present(window)

    def _a3_prompt_pin(self, slot: TokenSlotInfo) -> None:
        """Ask for the token PIN and authenticate."""
        from src.ui.pin_dialog import PinDialog

        mgr = self._a3_manager
        if mgr is None:
            return

        pin_dialog = PinDialog(token_label=slot.label or f"Slot {slot.slot_id}")

        def on_pin_closed(_dialog: object) -> None:
            if not pin_dialog.confirmed or not pin_dialog.pin:
                return

            pin = pin_dialog.pin
            self._cert_row.set_subtitle("Autenticando no token...")
            self._cert_row.set_sensitive(False)

            def login_thread() -> None:
                success = mgr.login(slot.slot_id, pin)
                if success:
                    certs = mgr.list_certificates()
                else:
                    certs = []
                GLib.idle_add(on_login_done, success, certs, pin, slot.slot_id)

            def on_login_done(
                success: bool, certs: list, pin: str, slot_id: int,
            ) -> bool:
                self._cert_row.set_sensitive(True)

                if not success:
                    self._cert_row.set_subtitle("PIN incorreto ou falha na autenticação")
                    return False

                if not certs:
                    self._cert_row.set_subtitle("Nenhum certificado encontrado no token")
                    mgr.logout()
                    return False

                # Store A3 state
                self._a3_slot_id = slot_id
                self._a3_pin = pin

                if len(certs) == 1:
                    self._a3_cert_info = certs[0]
                    self._a3_cert_der = self._get_a3_cert_der()
                    self._update_cert_row(certs[0])
                else:
                    self._a3_select_certificate(certs)

                return False

            threading.Thread(target=login_thread, daemon=True).start()

        pin_dialog.connect("closed", on_pin_closed)
        window = self.get_root()
        pin_dialog.present(window)

    def _a3_select_certificate(self, certs: list) -> None:
        """Let user pick a certificate when token has multiple."""
        dialog = Adw.Dialog()
        dialog.set_title("Selecionar Certificado")
        dialog.set_content_width(400)
        dialog.set_content_height(350)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        desc = Gtk.Label(label="Vários certificados encontrados. Selecione:")
        desc.add_css_class("dim-label")
        box.append(desc)

        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.add_css_class("boxed-list")

        for cert in certs:
            row = Adw.ActionRow()
            holder = cert.holder_name or cert.common_name
            row.set_title(holder)
            parts = []
            if cert.cpf:
                parts.append(f"CPF: {cert.cpf}")
            if cert.oab:
                parts.append(f"OAB: {cert.oab}")
            row.set_subtitle(" | ".join(parts) if parts else "")
            row.set_icon_name("application-certificate-symbolic")
            row.set_activatable(True)
            row.connect("activated", lambda _r, c=cert, d=dialog: (
                d.close(),
                setattr(self, '_a3_cert_info', c),
                setattr(self, '_a3_cert_der', self._get_a3_cert_der()),
                self._update_cert_row(c),
            ))
            list_box.append(row)

        box.append(list_box)
        toolbar.set_content(box)
        dialog.set_child(toolbar)

        window = self.get_root()
        dialog.present(window)

    def _get_a3_cert_der(self) -> Optional[bytes]:
        """Get the DER bytes of the currently selected A3 certificate."""
        if self._a3_manager is None or not self._a3_cert_info:
            return None
        try:
            if self._a3_manager._session is None:
                return None
            import PyKCS11
            session = self._a3_manager._session
            objects = session.findObjects([
                (PyKCS11.CKA_CLASS, PyKCS11.CKO_CERTIFICATE),
            ])
            for obj in objects:
                attrs = session.getAttributeValue(obj, [PyKCS11.CKA_VALUE])
                der_bytes = bytes(attrs[0])
                from cryptography import x509
                cert = x509.load_der_x509_certificate(der_bytes)
                from src.certificate.parser import parse_certificate
                info = parse_certificate(cert)
                if info.common_name == self._a3_cert_info.common_name:
                    return der_bytes
        except Exception as exc:
            log.error("Failed to get A3 certificate DER: %s", exc)
        return None

    # ── State transitions ────────────────────────────────────────

    def _transition_to_form(self) -> None:
        """Show the signing wizard, hide the empty state."""
        self._status_page.set_visible(False)
        self._select_initial_btn.set_visible(False)
        self._form_box.set_visible(True)
        self._go_to_step("step1")

    def _transition_to_empty(self) -> None:
        """Show the empty state, hide the wizard."""
        self._status_page.set_visible(True)
        self._select_initial_btn.set_visible(True)
        self._form_box.set_visible(False)

    def _update_sign_button_state(self) -> None:
        """Enable/disable sign button and wizard nav based on current state."""
        has_pdfs = len(self._pdf_paths) > 0

        if self._cert_type == CERT_TYPE_A1:
            has_cert = self._pfx_path is not None and self._pfx_password is not None
        elif self._cert_type == CERT_TYPE_A3:
            has_cert = (
                self._a3_cert_info is not None
                and self._a3_pin is not None
                and self._a3_slot_id is not None
            )
        else:
            has_cert = self._vidaas_cert_info is not None

        can_sign = has_pdfs and has_cert and not self._signing_in_progress
        self._sign_btn.set_sensitive(can_sign)

        # Update wizard step navigation
        self._step1_next.set_sensitive(has_pdfs)
        self._step2_next.set_sensitive(has_cert)

        count = len(self._pdf_paths)
        if count == 1:
            self._sign_btn.set_label("Assinar PDF")
        else:
            self._sign_btn.set_label(f"Assinar {count} PDFs")

    # ── Signing ──────────────────────────────────────────────────

    def _on_sign_clicked(self, _btn: Gtk.Button) -> None:
        """Start the signing process."""
        if not self._pdf_paths:
            return

        if self._cert_type == CERT_TYPE_A1:
            if not self._pfx_path or not self._pfx_password:
                return
        elif self._cert_type == CERT_TYPE_A3:
            if not self._a3_cert_der or not self._a3_pin or self._a3_manager is None:
                return
        elif self._cert_type == CERT_TYPE_VIDAAS:
            if self._vidaas_manager is None or not self._vidaas_manager.is_connected:
                return
            if self._vidaas_cert_info is None:
                return

        self._signing_in_progress = True
        self._sign_btn.set_sensitive(False)
        self._go_to_step("step4")
        self._progress_box.set_visible(True)
        self._results_group.set_visible(False)
        self._progress_bar.set_fraction(0.0)
        self._progress_label.set_label("Preparando assinatura...")

        # Clear previous results
        while True:
            child = self._results_group.get_first_child()
            # Skip the group's internal title/description widgets
            if child is None:
                break
            # PreferencesGroup adds internal children; we use a flag approach
            break

        # Build options
        options = SignatureOptions(
            reason=self._reason_row.get_text() or "Documento assinado digitalmente",
            location=self._location_row.get_text(),
            visible=self._visible_row.get_active(),
            page=self._get_selected_page(),
        )

        pdf_paths = list(self._pdf_paths)
        cert_type = self._cert_type

        # Capture signing parameters
        pfx_path: Optional[str] = None
        pfx_password: Optional[str] = None
        a3_manager: Optional[A3Manager] = None
        a3_cert_der: Optional[bytes] = None

        vidaas_manager: Optional[VidaaSManager] = None
        vidaas_cert_info: Optional[CertificateInfo] = None

        if cert_type == CERT_TYPE_A1:
            pfx_path = self._pfx_path
            pfx_password = self._pfx_password
        elif cert_type == CERT_TYPE_A3:
            a3_manager = self._a3_manager
            a3_cert_der = self._a3_cert_der
        elif cert_type == CERT_TYPE_VIDAAS:
            vidaas_manager = self._vidaas_manager
            vidaas_cert_info = self._vidaas_cert_info

        def signing_thread() -> None:
            results: list[SignatureResult] = []
            total = len(pdf_paths)

            for i, pdf_path in enumerate(pdf_paths):
                GLib.idle_add(
                    self._update_progress, i, total,
                    os.path.basename(pdf_path),
                )

                # Output: same dir, _assinado suffix
                p = Path(pdf_path)
                output = str(p.parent / f"{p.stem}_assinado{p.suffix}")

                if cert_type == CERT_TYPE_A1:
                    result = sign_pdf(
                        pdf_path, pfx_path, pfx_password,
                        output, options,
                    )
                elif cert_type == CERT_TYPE_A3:
                    result = sign_pdf_a3(
                        pdf_path, a3_manager, a3_cert_der,
                        output, options,
                    )
                elif cert_type == CERT_TYPE_VIDAAS:
                    result = sign_pdf_vidaas(
                        pdf_path, vidaas_manager, vidaas_cert_info,
                        output, options,
                    )
                results.append(result)

            GLib.idle_add(self._on_signing_done, results)

        threading.Thread(target=signing_thread, daemon=True).start()

    def _get_selected_page(self) -> int:
        """Get the page option value."""
        selected = self._page_row.get_selected()
        if selected == 0:
            return -1  # last page
        elif selected == 1:
            return 0  # first page
        else:
            return -2  # all pages (handled in signer)

    def _update_progress(
        self, current: int, total: int, filename: str,
    ) -> bool:
        fraction = current / total if total > 0 else 0
        self._progress_bar.set_fraction(fraction)
        self._progress_label.set_label(f"Assinando: {filename} ({current + 1}/{total})")
        return False

    def _on_signing_done(self, results: list[SignatureResult]) -> bool:
        """Show signing results."""
        self._signing_in_progress = False
        self._progress_box.set_visible(False)
        self._update_sign_button_state()

        # Build results group
        self._results_group = Adw.PreferencesGroup()
        self._results_group.set_title("Resultados")

        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count

        if fail_count == 0:
            self._results_group.set_description(
                f"✓ {success_count} documento(s) assinado(s) com sucesso"
            )
        else:
            self._results_group.set_description(
                f"✓ {success_count} sucesso(s), ✗ {fail_count} falha(s)"
            )

        for result in results:
            row = Adw.ActionRow()
            row.set_title(os.path.basename(result.input_path))

            if result.success:
                row.set_subtitle(os.path.basename(result.output_path))
                row.set_icon_name("emblem-ok-symbolic")

                # Open folder button
                open_btn = Gtk.Button()
                open_btn.set_icon_name("folder-open-symbolic")
                open_btn.set_tooltip_text("Abrir pasta")
                open_btn.set_valign(Gtk.Align.CENTER)
                open_btn.add_css_class("flat")
                open_btn.connect(
                    "clicked", self._on_open_folder,
                    os.path.dirname(result.output_path),
                )
                row.add_suffix(open_btn)
            else:
                row.set_subtitle(result.error)
                row.set_icon_name("dialog-error-symbolic")

            self._results_group.add(row)

        # Replace old results group in step4
        child = self._step4_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            if isinstance(child, Adw.PreferencesGroup) and child != self._results_group:
                title = child.get_title()
                if title == "Resultados":
                    self._step4_box.remove(child)
            child = next_child

        # Insert results before the "Nova Assinatura" button
        self._step4_box.insert_child_after(self._results_group, self._progress_box)
        self._results_group.set_visible(True)

        # Update progress bar to complete
        self._progress_bar.set_fraction(1.0)

        # Status bar update
        window = self.get_root()
        if hasattr(window, "_set_status"):
            if fail_count == 0:
                window._set_status(f"{success_count} PDF(s) assinado(s) com sucesso")
            else:
                window._set_status(f"{success_count} sucesso(s), {fail_count} falha(s)")

        return False

    def _on_open_folder(self, _btn: Gtk.Button, folder_path: str) -> None:
        """Open folder in file manager."""
        try:
            Gio.AppInfo.launch_default_for_uri(
                f"file://{folder_path}", None,
            )
        except Exception as exc:
            log.error("Failed to open folder: %s", exc)

    # ── Papers configuration ─────────────────────────────────────

    def _on_configure_papers(self, _widget: Gtk.Widget) -> None:
        """Import certificate chain into NSS for Papers validation."""
        if not self._pfx_path or not self._pfx_password:
            self._show_papers_toast("Selecione um certificado primeiro")
            return

        self._papers_row.set_subtitle("Importando certificados...")
        self._papers_row.set_sensitive(False)

        pfx_path = self._pfx_path
        pfx_password = self._pfx_password

        def import_thread() -> None:
            results = import_pfx_chain_for_papers(pfx_path, pfx_password)
            GLib.idle_add(on_import_done, results)

        def on_import_done(results: dict[str, bool]) -> bool:
            self._papers_row.set_sensitive(True)

            success = sum(1 for v in results.values() if v)
            total = len(results)

            if total == 0:
                self._papers_row.set_subtitle("Nenhum certificado encontrado no PFX")
                self._papers_row.set_icon_name("dialog-warning-symbolic")
            elif success == total:
                names = ", ".join(results.keys())
                self._papers_row.set_subtitle(
                    f"✓ {success} certificado(s) importado(s)"
                )
                self._papers_row.set_icon_name("emblem-ok-symbolic")
                self._show_papers_toast(
                    f"Papers configurado — {success} certificado(s) importado(s)"
                )
            else:
                failed = [k for k, v in results.items() if not v]
                self._papers_row.set_subtitle(
                    f"✓ {success} importado(s), ✗ {total - success} falha(s)"
                )
                self._papers_row.set_icon_name("dialog-warning-symbolic")

            return False

        threading.Thread(target=import_thread, daemon=True).start()

    def _show_papers_toast(self, message: str) -> None:
        """Show inline status on the Papers row subtitle."""
        self._papers_row.set_subtitle(message)

    def reset(self) -> None:
        """Reset the view to initial state."""
        self._pdf_paths.clear()
        self._signing_in_progress = False
        self._clear_certificate_state()
        self._cert_type_row.set_selected(CERT_TYPE_A1)
        self._update_pdf_list()
        self._transition_to_empty()


def _format_size(size_bytes: int) -> str:
    """Format file size for display."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
