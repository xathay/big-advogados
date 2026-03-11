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
)
from src.browser.nss_config import import_pfx_chain_for_papers

log = logging.getLogger(__name__)


class SignerView(Gtk.ScrolledWindow):
    """View for signing PDFs with digital certificates."""

    def __init__(self) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._pdf_paths: list[str] = []
        self._pfx_path: Optional[str] = None
        self._pfx_password: Optional[str] = None
        self._signing_in_progress = False

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.set_margin_top(12)
        self._content.set_margin_bottom(12)
        self._content.set_margin_start(12)
        self._content.set_margin_end(12)
        self.set_child(self._content)

        self._build_empty_state()
        self._build_form()

    # ── Build UI ─────────────────────────────────────────────────

    def _build_empty_state(self) -> None:
        """Build the initial empty state with instructions."""
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("document-edit-symbolic")
        self._status_page.set_title("Assinador de PDF")
        self._status_page.set_description(
            "Assine documentos PDF com seu certificado digital A1.\n"
            "Selecione os arquivos PDF e o certificado para começar."
        )
        self._content.append(self._status_page)

    def _build_form(self) -> None:
        """Build the signing form (hidden until user starts)."""
        self._form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._form_box.set_visible(False)
        self._content.append(self._form_box)

        # ── PDF files section ──
        pdf_group = Adw.PreferencesGroup()
        pdf_group.set_title("Documentos PDF")
        pdf_group.set_description("Arquivos que serão assinados digitalmente")
        self._form_box.append(pdf_group)

        # PDF file list
        self._pdf_list_box = Gtk.ListBox()
        self._pdf_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._pdf_list_box.add_css_class("boxed-list")
        pdf_group.add(self._pdf_list_box)

        # Add/remove PDF buttons
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

        # ── Certificate section ──
        cert_group = Adw.PreferencesGroup()
        cert_group.set_title("Certificado Digital")
        cert_group.set_description("Certificado A1 (PFX/P12) para assinatura")
        self._form_box.append(cert_group)

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
        self._cert_row.add_suffix(change_cert_btn)

        cert_group.add(self._cert_row)

        # ── Signature options ──
        opts_group = Adw.PreferencesGroup()
        opts_group.set_title("Opções da Assinatura")
        self._form_box.append(opts_group)

        # Reason
        self._reason_row = Adw.EntryRow()
        self._reason_row.set_title("Motivo")
        self._reason_row.set_text("Documento assinado digitalmente")
        opts_group.add(self._reason_row)

        # Location
        self._location_row = Adw.EntryRow()
        self._location_row.set_title("Local")
        self._location_row.set_text("")
        opts_group.add(self._location_row)

        # Visible signature toggle
        self._visible_row = Adw.SwitchRow()
        self._visible_row.set_title("Carimbo visível")
        self._visible_row.set_subtitle("Insere selo de assinatura no rodapé do PDF")
        self._visible_row.set_active(True)
        opts_group.add(self._visible_row)

        # Page position
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

        # ── Sign button ──
        self._sign_btn = Gtk.Button(label="Assinar PDF(s)")
        self._sign_btn.add_css_class("suggested-action")
        self._sign_btn.add_css_class("pill")
        self._sign_btn.set_halign(Gtk.Align.CENTER)
        self._sign_btn.set_margin_top(16)
        self._sign_btn.set_margin_bottom(8)
        self._sign_btn.set_sensitive(False)
        self._sign_btn.connect("clicked", self._on_sign_clicked)
        self._form_box.append(self._sign_btn)

        # ── Progress ──
        self._progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._progress_box.set_visible(False)
        self._progress_box.set_margin_top(8)
        self._form_box.append(self._progress_box)

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)
        self._progress_box.append(self._progress_bar)

        self._progress_label = Gtk.Label()
        self._progress_label.add_css_class("dim-label")
        self._progress_box.append(self._progress_label)

        # ── Results ──
        self._results_group = Adw.PreferencesGroup()
        self._results_group.set_title("Resultados")
        self._results_group.set_visible(False)
        self._form_box.append(self._results_group)

        # ── Papers configuration ──
        papers_group = Adw.PreferencesGroup()
        papers_group.set_title("Visualizador de PDFs")
        papers_group.set_description(
            "Importe o certificado no sistema para que o Papers "
            "(GNOME) valide as assinaturas digitais"
        )
        self._form_box.append(papers_group)

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

        # ── Select PDFs button (initially visible) ──
        select_btn = Gtk.Button(label="Selecionar Arquivos PDF")
        select_btn.add_css_class("suggested-action")
        select_btn.add_css_class("pill")
        select_btn.set_halign(Gtk.Align.CENTER)
        select_btn.set_margin_top(8)
        select_btn.connect("clicked", self._on_add_pdf_clicked)
        self._select_initial_btn = select_btn
        self._content.append(select_btn)

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

    # ── Certificate selection ────────────────────────────────────

    def _on_select_cert_clicked(self, _widget: Gtk.Widget) -> None:
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
        file_label.set_ellipsize(3)
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

        ok_btn = Gtk.Button(label="Confirmar")
        ok_btn.add_css_class("suggested-action")
        btn_box.append(ok_btn)

        box.append(btn_box)

        def on_confirm(*_args: object) -> None:
            password = pwd_entry.get_text()
            ok_btn.set_sensitive(False)
            cancel_btn.set_sensitive(False)

            def validate_thread() -> None:
                from src.certificate.a1_manager import A1Manager
                mgr = A1Manager()
                cert_info = mgr.load_pfx(pfx_path, password)
                GLib.idle_add(on_validate_result, cert_info, password)

            def on_validate_result(
                cert_info: object, pwd: str,
            ) -> bool:
                if cert_info is not None:
                    self._pfx_path = pfx_path
                    self._pfx_password = pwd
                    self._update_cert_row(cert_info)
                    dialog.close()
                else:
                    error_label.set_label("Senha incorreta ou arquivo inválido")
                    error_label.set_visible(True)
                    ok_btn.set_sensitive(True)
                    cancel_btn.set_sensitive(True)
                    pwd_entry.grab_focus()
                return False

            threading.Thread(target=validate_thread, daemon=True).start()

        ok_btn.connect("clicked", on_confirm)
        pwd_entry.connect("activate", on_confirm)

        toolbar.set_content(box)
        dialog.set_child(toolbar)

        window = self.get_root()
        dialog.present(window)

    def _update_cert_row(self, cert_info: object) -> None:
        """Update the certificate row with loaded certificate info."""
        from src.certificate.parser import CertificateInfo
        if not isinstance(cert_info, CertificateInfo):
            return

        holder = cert_info.holder_name or cert_info.common_name
        self._cert_row.set_title(holder)

        subtitle_parts = []
        if cert_info.cpf:
            subtitle_parts.append(f"CPF: {cert_info.cpf}")
        if cert_info.oab:
            subtitle_parts.append(f"OAB: {cert_info.oab}")
        if cert_info.issuer_cn:
            subtitle_parts.append(f"AC: {cert_info.issuer_cn}")

        self._cert_row.set_subtitle(" | ".join(subtitle_parts) if subtitle_parts else os.path.basename(self._pfx_path or ""))

        # Validity indicator
        if cert_info.is_expired:
            self._cert_row.set_icon_name("dialog-error-symbolic")
        elif cert_info.days_to_expire <= 30:
            self._cert_row.set_icon_name("dialog-warning-symbolic")
        else:
            self._cert_row.set_icon_name("emblem-ok-symbolic")

        self._update_sign_button_state()

    # ── State transitions ────────────────────────────────────────

    def _transition_to_form(self) -> None:
        """Show the signing form, hide the empty state."""
        self._status_page.set_visible(False)
        self._select_initial_btn.set_visible(False)
        self._form_box.set_visible(True)

    def _transition_to_empty(self) -> None:
        """Show the empty state, hide the form."""
        self._status_page.set_visible(True)
        self._select_initial_btn.set_visible(True)
        self._form_box.set_visible(False)

    def _update_sign_button_state(self) -> None:
        """Enable/disable sign button based on current state."""
        can_sign = (
            len(self._pdf_paths) > 0
            and self._pfx_path is not None
            and self._pfx_password is not None
            and not self._signing_in_progress
        )
        self._sign_btn.set_sensitive(can_sign)

        count = len(self._pdf_paths)
        if count == 1:
            self._sign_btn.set_label("Assinar PDF")
        else:
            self._sign_btn.set_label(f"Assinar {count} PDFs")

    # ── Signing ──────────────────────────────────────────────────

    def _on_sign_clicked(self, _btn: Gtk.Button) -> None:
        """Start the signing process."""
        if not self._pdf_paths or not self._pfx_path or not self._pfx_password:
            return

        self._signing_in_progress = True
        self._sign_btn.set_sensitive(False)
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

        pfx_path = self._pfx_path
        pfx_password = self._pfx_password
        pdf_paths = list(self._pdf_paths)

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

                result = sign_pdf(
                    pdf_path, pfx_path, pfx_password,
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

        # Replace old results group in the form
        # Find and remove old results group
        child = self._form_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            if isinstance(child, Adw.PreferencesGroup) and child != self._results_group:
                title = child.get_title()
                if title == "Resultados":
                    self._form_box.remove(child)
            child = next_child

        self._form_box.append(self._results_group)
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
        self._pfx_path = None
        self._pfx_password = None
        self._signing_in_progress = False
        self._update_pdf_list()
        self._transition_to_empty()
        self._cert_row.set_title("Nenhum certificado selecionado")
        self._cert_row.set_subtitle("Clique para selecionar o arquivo PFX")
        self._cert_row.set_icon_name("application-certificate-symbolic")


def _format_size(size_bytes: int) -> str:
    """Format file size for display."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
