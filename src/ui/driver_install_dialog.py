"""Dialog de instalacao de driver proprietario PKCS#11.

Mostra fabricante, distribuidor, fonte, tamanho e licenca antes de
baixar qualquer coisa. Apos o download e verificacao SHA-256, abre a
EULA em modal separado para aceite explicito. So entao chama o helper
privilegiado via pkexec.

Tudo o que e visivel ao usuario fica explicito: nada e instalado em
silencio, nada vem de fonte nao identificada.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from src.drivers import DriverInstaller, DriverSpec, InstallProgress, InstallStage

log = logging.getLogger(__name__)


class DriverInstallDialog(Adw.Dialog):
    """Modal para instalar um DriverSpec ate o fim, com EULA explicita."""

    def __init__(
        self,
        spec: DriverSpec,
        on_done: Optional[Callable[[bool], None]] = None,
    ) -> None:
        super().__init__()
        self._spec = spec
        self._on_done_cb = on_done
        self._installer = DriverInstaller()
        self._eula_text: Optional[str] = None
        self._deb_path: Optional[Path] = None
        self._success = False

        self.set_title(f"Instalar {spec.product}")
        self.set_content_width(640)
        self.set_content_height(560)
        self.set_can_close(True)

        self._build_ui()

    # ── UI construction ─────────────────────────────────────────────

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        outer.set_margin_top(8)
        outer.set_margin_bottom(16)
        outer.set_margin_start(20)
        outer.set_margin_end(20)

        # Cabecalho: produto + fabricante.
        title = Gtk.Label(label=self._spec.product)
        title.add_css_class("title-2")
        title.set_halign(Gtk.Align.START)
        outer.append(title)

        subtitle = Gtk.Label(label=f"por {self._spec.vendor}  ·  v{self._spec.version}")
        subtitle.add_css_class("dim-label")
        subtitle.set_halign(Gtk.Align.START)
        outer.append(subtitle)

        desc = Gtk.Label(label=self._spec.description)
        desc.set_wrap(True)
        desc.set_xalign(0)
        outer.append(desc)

        # Bloco de informacoes verificaveis: fonte, tamanho, distribuidor.
        info = Adw.PreferencesGroup()

        src_row = Adw.ActionRow()
        src_row.set_title("Fonte do instalador")
        src_row.set_subtitle(self._spec.source.label)
        info.add(src_row)

        dist_row = Adw.ActionRow()
        dist_row.set_title("Distribuidor licenciado")
        dist_row.set_subtitle(self._spec.distributor.name)
        info.add(dist_row)

        size_row = Adw.ActionRow()
        size_row.set_title("Tamanho do download")
        size_row.set_subtitle(f"{self._spec.source.size_bytes / 1024 / 1024:.1f} MB")
        info.add(size_row)

        lic_row = Adw.ActionRow()
        lic_row.set_title("Licenca")
        lic_row.set_subtitle(self._spec.license.summary)
        info.add(lic_row)

        outer.append(info)

        # Status + barra de progresso (escondidos no inicio).
        self._status_label = Gtk.Label(label="")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.add_css_class("heading")
        self._status_label.set_visible(False)
        outer.append(self._status_label)

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_visible(False)
        outer.append(self._progress_bar)

        # Log inicia escondido, aparece durante installing.
        self._log_frame = Gtk.Frame()
        self._log_frame.set_visible(False)
        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_vexpand(True)
        log_scroll.set_min_content_height(120)
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
        self._log_frame.set_child(log_scroll)
        outer.append(self._log_frame)

        # Botoes.
        btn_box = Gtk.Box(spacing=10)
        btn_box.set_halign(Gtk.Align.END)

        self._cancel_btn = Gtk.Button(label="Cancelar")
        self._cancel_btn.connect("clicked", self._on_cancel)
        btn_box.append(self._cancel_btn)

        self._action_btn = Gtk.Button(label="Instalar")
        self._action_btn.add_css_class("suggested-action")
        self._action_btn.connect("clicked", self._on_install_clicked)
        btn_box.append(self._action_btn)

        outer.append(btn_box)
        toolbar.set_content(outer)
        self.set_child(toolbar)

    # ── Actions ─────────────────────────────────────────────────────

    def _on_install_clicked(self, _btn: Gtk.Button) -> None:
        self._action_btn.set_sensitive(False)
        self._status_label.set_visible(True)
        self._progress_bar.set_visible(True)
        threading.Thread(target=self._download_then_eula, daemon=True).start()

    def _download_then_eula(self) -> None:
        try:
            deb = self._installer.download(self._spec, self._on_progress_thread)
            eula = self._installer.extract_eula(self._spec, deb)
        except InterruptedError:
            GLib.idle_add(self._set_status, "Cancelado pelo usuario", False)
            return
        except Exception as exc:
            log.exception("Falha no download/extracao de EULA")
            GLib.idle_add(self._set_status, f"Falha: {exc}", False)
            return

        self._deb_path = deb
        self._eula_text = eula
        GLib.idle_add(self._open_eula_dialog)

    def _open_eula_dialog(self) -> bool:
        dialog = Adw.AlertDialog()
        dialog.set_heading("Licenca do fabricante")
        dialog.set_body(
            f"Voce esta prestes a instalar software proprietario de "
            f"{self._spec.vendor}. Leia a licenca abaixo e confirme se aceita "
            f"os termos para continuar."
        )

        # Conteudo extra: scrollable text view com o texto da EULA.
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(320)
        scroll.set_min_content_width(560)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)

        view = Gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_top_margin(8)
        view.set_bottom_margin(8)
        view.set_left_margin(8)
        view.set_right_margin(8)
        buf = view.get_buffer()
        buf.set_text(self._eula_text or "")
        scroll.set_child(view)

        dialog.set_extra_child(scroll)
        dialog.add_response("decline", "Recusar")
        dialog.add_response("accept", "Aceito a licenca")
        dialog.set_response_appearance("accept", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("decline")
        dialog.set_close_response("decline")
        dialog.connect("response", self._on_eula_response)
        dialog.present(self)
        return False

    def _on_eula_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response != "accept":
            self._set_status("Licenca recusada.", False)
            return
        self._log_frame.set_visible(True)
        threading.Thread(target=self._run_install, daemon=True).start()

    def _run_install(self) -> None:
        try:
            ok = self._installer.install(
                self._spec,
                self._deb_path,  # type: ignore[arg-type]
                self._on_progress_thread,
                self._on_log_thread,
            )
            self._success = ok
        except Exception as exc:
            log.exception("Erro na instalacao")
            GLib.idle_add(self._set_status, f"Falha: {exc}", False)
            return

        if ok:
            GLib.idle_add(self._mark_done)
        # mensagem de erro ja foi setada via on_progress

    # ── Thread → UI bridges ─────────────────────────────────────────

    def _on_progress_thread(self, p: InstallProgress) -> None:
        GLib.idle_add(self._apply_progress, p)

    def _apply_progress(self, p: InstallProgress) -> bool:
        self._status_label.set_text(p.message)
        if p.fraction < 0:
            self._progress_bar.pulse()
        else:
            self._progress_bar.set_fraction(p.fraction)
            self._progress_bar.set_text(f"{int(p.fraction * 100)}%")
            self._progress_bar.set_show_text(True)

        if p.stage == InstallStage.ERROR:
            self._set_status(p.message, False)
        return False

    def _on_log_thread(self, line: str) -> None:
        GLib.idle_add(self._append_log, line)

    def _append_log(self, line: str) -> bool:
        end = self._log_buffer.get_end_iter()
        self._log_buffer.insert(end, line + "\n")
        mark = self._log_buffer.get_insert()
        self._log_view.scroll_mark_onscreen(mark)
        return False

    # ── Finishing states ────────────────────────────────────────────

    def _set_status(self, msg: str, success: bool) -> bool:
        self._status_label.set_text(msg)
        self._progress_bar.set_visible(False)
        self._action_btn.set_visible(False)
        self._cancel_btn.set_label("Fechar")
        self._success = success
        return False

    def _mark_done(self) -> bool:
        self._status_label.set_text(f"{self._spec.product} instalado.")
        self._progress_bar.set_visible(False)
        self._action_btn.set_visible(False)
        self._cancel_btn.set_label("Fechar")
        self._cancel_btn.add_css_class("suggested-action")
        return False

    def _on_cancel(self, _btn: Gtk.Button) -> None:
        self._installer.cancel()
        if self._on_done_cb:
            self._on_done_cb(self._success)
        self.close()
