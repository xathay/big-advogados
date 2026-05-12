"""WebSigner / e-SAJ setup dialog — GTK4 UI.

Runs the bundled native messaging host installer + bridge extension installer
and reports per-target results in a log view. No network access required.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

log = logging.getLogger(__name__)


class WebSignerSetupDialog(Adw.Dialog):
    """Dialog that registers the native messaging host and drops the bridge XPI."""

    def __init__(self, on_finished: Optional[Callable[[], None]] = None) -> None:
        super().__init__()
        self.set_title("Configurar e-SAJ")
        self.set_content_width(620)
        self.set_content_height(540)

        self._on_finished = on_finished
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)

        title = Gtk.Label(label="Configurar e-SAJ — TJSP")
        title.add_css_class("title-3")
        main_box.append(title)

        info = Gtk.Label(
            label=(
                "Registra o conector PKI do Big Advogados para Firefox, "
                "Chrome, Chromium e Brave, e instala a ponte WebPKI nos "
                "perfis do Firefox.\n\n"
                "Para uso permanente em peticionamento, recomendado Firefox ESR "
                "+ extensão Web Signer da Mozilla AMO."
            )
        )
        info.add_css_class("dim-label")
        info.set_wrap(True)
        info.set_justify(Gtk.Justification.CENTER)
        main_box.append(info)

        self._status_label = Gtk.Label(label="Pronto para configurar")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.add_css_class("heading")
        self._status_label.set_margin_top(8)
        main_box.append(self._status_label)

        log_frame = Gtk.Frame()
        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_vexpand(True)
        log_scroll.set_min_content_height(260)

        self._log_view = Gtk.TextView()
        self._log_view.set_editable(False)
        self._log_view.set_cursor_visible(False)
        self._log_view.set_monospace(True)
        self._log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._log_view.set_top_margin(8)
        self._log_view.set_bottom_margin(8)
        self._log_view.set_left_margin(8)
        self._log_view.set_right_margin(8)
        self._log_buffer = self._log_view.get_buffer()

        log_scroll.set_child(self._log_view)
        log_frame.set_child(log_scroll)
        main_box.append(log_frame)

        btn_box = Gtk.Box(spacing=12, homogeneous=True)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        self._close_btn = Gtk.Button(label="Cancelar")
        self._close_btn.connect("clicked", lambda _: self.close())
        btn_box.append(self._close_btn)

        self._run_btn = Gtk.Button(label="Configurar")
        self._run_btn.add_css_class("suggested-action")
        self._run_btn.connect("clicked", self._on_run)
        btn_box.append(self._run_btn)

        main_box.append(btn_box)
        toolbar.set_content(main_box)
        self.set_child(toolbar)

    def _log_append(self, text: str) -> None:
        GLib.idle_add(self._log_append_ui, text)

    def _log_append_ui(self, text: str) -> bool:
        end_iter = self._log_buffer.get_end_iter()
        self._log_buffer.insert(end_iter, text + "\n")
        mark = self._log_buffer.get_insert()
        self._log_view.scroll_mark_onscreen(mark)
        return False

    def _set_status(self, text: str) -> None:
        GLib.idle_add(self._set_status_ui, text)

    def _set_status_ui(self, text: str) -> bool:
        self._status_label.set_label(text)
        return False

    def _on_run(self, _btn: Gtk.Button) -> None:
        self._run_btn.set_sensitive(False)
        self._run_btn.set_label("Configurando…")
        threading.Thread(target=self._run_thread, daemon=True).start()

    def _run_thread(self) -> None:
        from src.websigner import installer

        try:
            self._set_status("Registrando conector PKI nos navegadores…")
            self._log_append("Etapa 1/2 — Native messaging host")
            self._log_append("")
            host_results = installer.install_native_host()
            for target, ok in host_results.items():
                mark = "✓" if ok else "✗"
                self._log_append(f"  {mark} {target}")
            self._log_append("")

            self._set_status("Instalando ponte WebPKI nos perfis do Firefox…")
            self._log_append("Etapa 2/2 — Bridge extension (Firefox profiles)")
            self._log_append("")
            bridge_results = installer.install_bridge_extension()
            if bridge_results == {"build": False}:
                self._log_append("  ✗ Falha ao empacotar XPI da bridge")
            elif bridge_results == {"no_profiles": False}:
                self._log_append("  ⚠ Nenhum perfil Firefox encontrado — abra o Firefox uma vez e reexecute")
            else:
                for profile, ok in bridge_results.items():
                    mark = "✓" if ok else "✗"
                    self._log_append(f"  {mark} {profile}")
            self._log_append("")

            self._log_append("═══════════════════════════════════════════")
            self._log_append("  Configuração concluída")
            self._log_append("")
            self._log_append("  Próximos passos manuais:")
            self._log_append("  1. Abrir Firefox ESR")
            self._log_append("  2. Instalar extensão oficial Web Signer:")
            self._log_append("     https://addons.mozilla.org/firefox/addon/websigner/")
            self._log_append("  3. Configurar o caminho do certificado A1 (.p12)")
            self._log_append("     na seção WebSigner — e-SAJ")
            self._log_append("═══════════════════════════════════════════")

            self._set_status("Configuração concluída")
            GLib.idle_add(self._on_finished_ui)

        except Exception as exc:
            log.exception("WebSigner setup failed")
            self._log_append(f"ERRO: {exc}")
            self._set_status("Falha na configuração")
            GLib.idle_add(self._on_failed_ui)

    def _on_finished_ui(self) -> bool:
        self._run_btn.set_label("Concluído ✓")
        self._run_btn.add_css_class("success")
        self._close_btn.set_label("Fechar")
        if self._on_finished:
            self._on_finished()
        return False

    def _on_failed_ui(self) -> bool:
        self._run_btn.set_label("Tentar Novamente")
        self._run_btn.set_sensitive(True)
        self._run_btn.remove_css_class("suggested-action")
        self._run_btn.add_css_class("destructive-action")
        return False
