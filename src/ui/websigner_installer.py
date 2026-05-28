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
        self.set_title("Configurar assinatura")
        self.set_content_width(620)
        self.set_content_height(740)

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

        title = Gtk.Label(label="Configurar assinatura nos tribunais")
        title.add_css_class("title-3")
        main_box.append(title)

        info = Gtk.Label(
            label=(
                "Prepara o navegador para assinar petições com seu certificado "
                "digital — token A3 (USB) ou A1 (arquivo .p12) — no e-SAJ (TJSP), "
                "eproc (TJMG e demais) e outros sistemas judiciais."
            )
        )
        info.add_css_class("dim-label")
        info.set_wrap(True)
        info.set_justify(Gtk.Justification.CENTER)
        main_box.append(info)

        # ── Explicação clara para o advogado: a peça que costuma faltar ──
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("card")
        card.set_margin_top(4)
        for w in ("set_margin_top", "set_margin_bottom", "set_margin_start", "set_margin_end"):
            getattr(card, w)(12)

        card_title = Gtk.Label(label="Sobre o navegador — leia antes")
        card_title.add_css_class("heading")
        card_title.set_halign(Gtk.Align.START)
        card.append(card_title)

        card_body = Gtk.Label(
            label=(
                "A assinatura só funciona se o navegador tiver a extensão de "
                "assinatura. Como cada navegador trata isso de um jeito:\n\n"
                "• Firefox ESR (recomendado): o Big Advogados instala a ponte "
                "automaticamente e ela continua valendo depois de reiniciar. "
                "Nada mais a fazer.\n"
                "• Firefox comum: por uma trava de segurança do próprio Firefox, "
                "a ponte automática não carrega. Use o Firefox ESR, ou instale "
                "a extensão oficial “Web Signer” pela loja de extensões.\n"
                "• Chrome / Brave / Edge: instale a extensão oficial "
                "“Web Signer” pela Chrome Web Store.\n\n"
                "Em todos os casos, a assinatura em si — com seu certificado e "
                "sua senha — é feita aqui pelo Big Advogados; a extensão é só a "
                "ponte entre o site do tribunal e o seu certificado."
            )
        )
        card_body.set_wrap(True)
        card_body.set_xalign(0.0)
        card_body.set_halign(Gtk.Align.START)
        card.append(card_body)
        main_box.append(card)

        self._status_label = Gtk.Label(label="Pronto para configurar")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.add_css_class("heading")
        self._status_label.set_margin_top(8)
        main_box.append(self._status_label)

        log_frame = Gtk.Frame()
        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_min_content_height(170)
        log_scroll.set_max_content_height(170)

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
        # Pre-fill with a hint so the empty box doesn't look orphaned.
        self._log_buffer.set_text(
            "Clique em 'Configurar' para registrar o Big Advogados como "
            "conector de assinatura nos navegadores instalados e instalar a "
            "ponte WebPKI nos perfis Firefox detectados.\n\n"
            "O progresso aparecerá aqui."
        )

        log_scroll.set_child(self._log_view)
        log_frame.set_child(log_scroll)
        main_box.append(log_frame)

        # Conteúdo rolável: nasce mostrando tudo na altura padrão, e se a
        # janela for encolhida o usuário rola em vez de ver o texto cortado.
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(main_box)
        toolbar.set_content(scroller)

        # Botões numa barra inferior fixa (padrão GNOME) — sempre visíveis,
        # não rolam junto com o conteúdo.
        btn_box = Gtk.Box(spacing=12, homogeneous=True)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)
        btn_box.set_margin_bottom(12)
        btn_box.set_margin_start(16)
        btn_box.set_margin_end(16)

        self._close_btn = Gtk.Button(label="Cancelar")
        self._close_btn.connect("clicked", lambda _: self.close())
        btn_box.append(self._close_btn)

        self._run_btn = Gtk.Button(label="Configurar")
        self._run_btn.add_css_class("suggested-action")
        self._run_btn.connect("clicked", self._on_run)
        btn_box.append(self._run_btn)

        toolbar.add_bottom_bar(btn_box)
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
        self._log_buffer.set_text("")  # Clear the pre-flight hint
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
            self._log_append("  Próximos passos:")
            self._log_append("  1. Plugue o token A3 (USB), se for usar")
            self._log_append("     — reconhecido automaticamente")
            self._log_append("  2. Ou configure o A1 (.p12) na seção")
            self._log_append("     'Certificados' do painel")
            self._log_append("  3. Abra o e-SAJ / eproc e faça login")
            self._log_append("")
            self._log_append("  Navegador:")
            self._log_append("  • Firefox ESR — pronto, nada a fazer.")
            self._log_append("  • Firefox comum / Chrome / Brave — instale a")
            self._log_append("    extensão oficial 'Web Signer' pela loja;")
            self._log_append("    o Big Advogados já é o conector por trás dela.")
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
