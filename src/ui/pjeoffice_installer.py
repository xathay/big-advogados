"""PJeOffice Pro installer dialog — downloads and installs within the GTK4 UI."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango  # noqa: E402

log = logging.getLogger(__name__)

PJEOFFICE_VERSION = "2.5.16u"
DOWNLOAD_URL = (
    f"https://pje-office.pje.jus.br/pro/"
    f"pjeoffice-pro-v{PJEOFFICE_VERSION}-linux_x64.zip"
)
EXPECTED_SHA256 = "6087391759c7cba11fb5ef815fe8be91713b46a8607c12eb664a9d9a6882c4c7"


class PJeOfficeInstallerDialog(Adw.Dialog):
    """Dialog that downloads and installs PJeOffice Pro with full progress."""

    def __init__(self, on_installed: Optional[Callable[[], None]] = None) -> None:
        super().__init__()
        self.set_title("Instalar PJeOffice Pro")
        self.set_content_width(600)
        self.set_content_height(500)

        self._tmp_dir: Optional[str] = None
        self._cancelled = False
        self._on_installed = on_installed

        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()

        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)

        # Title
        title = Gtk.Label(label="PJeOffice Pro — Assinador Digital do CNJ")
        title.add_css_class("title-3")
        main_box.append(title)

        info = Gtk.Label(
            label=(
                f"Versão {PJEOFFICE_VERSION} — Download oficial do site do TRF3/CNJ.\n"
                "Necessário para assinatura digital nos sistemas PJe."
            )
        )
        info.add_css_class("dim-label")
        info.set_wrap(True)
        info.set_justify(Gtk.Justification.CENTER)
        main_box.append(info)

        # Progress section
        progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        progress_box.set_margin_top(8)

        self._status_label = Gtk.Label(label="Pronto para iniciar")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.add_css_class("heading")
        progress_box.append(self._status_label)

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)
        self._progress_bar.set_text("0%")
        progress_box.append(self._progress_bar)

        self._size_label = Gtk.Label(label="")
        self._size_label.set_halign(Gtk.Align.END)
        self._size_label.add_css_class("dim-label")
        self._size_label.add_css_class("caption")
        progress_box.append(self._size_label)

        main_box.append(progress_box)

        # Log view
        log_frame = Gtk.Frame()
        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_vexpand(True)
        log_scroll.set_min_content_height(200)

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

        # Buttons
        btn_box = Gtk.Box(spacing=12, homogeneous=True)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        self._cancel_btn = Gtk.Button(label="Cancelar")
        self._cancel_btn.connect("clicked", self._on_cancel)
        btn_box.append(self._cancel_btn)

        self._install_btn = Gtk.Button(label="Iniciar Instalação")
        self._install_btn.add_css_class("suggested-action")
        self._install_btn.connect("clicked", self._on_install)
        btn_box.append(self._install_btn)

        main_box.append(btn_box)

        toolbar.set_content(main_box)
        self.set_child(toolbar)

    def _log_append(self, text: str) -> None:
        """Thread-safe log append."""
        GLib.idle_add(self._log_append_ui, text)

    def _log_append_ui(self, text: str) -> bool:
        end_iter = self._log_buffer.get_end_iter()
        self._log_buffer.insert(end_iter, text + "\n")
        # Auto-scroll
        mark = self._log_buffer.get_insert()
        self._log_view.scroll_mark_onscreen(mark)
        return False

    def _set_progress(self, fraction: float, text: str) -> None:
        GLib.idle_add(self._set_progress_ui, fraction, text)

    def _set_progress_ui(self, fraction: float, text: str) -> bool:
        self._progress_bar.set_fraction(fraction)
        self._progress_bar.set_text(text)
        return False

    def _set_status(self, text: str) -> None:
        GLib.idle_add(self._set_status_ui, text)

    def _set_status_ui(self, text: str) -> bool:
        self._status_label.set_label(text)
        return False

    def _set_size_label(self, text: str) -> None:
        GLib.idle_add(self._set_size_label_ui, text)

    def _set_size_label_ui(self, text: str) -> bool:
        self._size_label.set_label(text)
        return False

    def _on_cancel(self, _btn: Gtk.Button) -> None:
        self._cancelled = True
        self.close()

    def _on_install(self, _btn: Gtk.Button) -> None:
        self._install_btn.set_sensitive(False)
        self._install_btn.set_label("Instalando...")
        threading.Thread(target=self._install_thread, daemon=True).start()

    def _install_thread(self) -> None:
        """Full installation in background thread."""
        try:
            self._tmp_dir = tempfile.mkdtemp(prefix="pjeoffice_")
            zip_path = os.path.join(self._tmp_dir, "pjeoffice-pro.zip")

            # Step 1: Download
            self._set_status("Baixando PJeOffice Pro...")
            self._log_append(f"URL: {DOWNLOAD_URL}")
            self._log_append(f"Versão: {PJEOFFICE_VERSION}")
            self._log_append("")

            if not self._download_file(DOWNLOAD_URL, zip_path):
                return

            if self._cancelled:
                return

            # Step 2: Verify SHA-256
            self._set_status("Verificando integridade...")
            self._set_progress(0.0, "Verificando SHA-256...")
            self._log_append("Calculando hash SHA-256...")

            sha = self._calculate_sha256(zip_path)
            self._log_append(f"  Esperado: {EXPECTED_SHA256}")
            self._log_append(f"  Obtido:   {sha}")

            if sha != EXPECTED_SHA256:
                self._log_append("")
                self._log_append("ERRO: Hash não confere! Arquivo corrompido.")
                self._set_status("Falha — Arquivo corrompido")
                self._set_progress(0.0, "Erro")
                GLib.idle_add(self._on_install_failed)
                return

            self._log_append("  ✓ Integridade verificada")
            self._log_append("")

            # Step 3: Extract
            self._set_status("Extraindo arquivos...")
            self._set_progress(0.7, "Extraindo...")
            self._log_append("Extraindo arquivo ZIP...")

            result = subprocess.run(
                ["unzip", "-q", "-o", zip_path, "-d", self._tmp_dir],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                self._log_append(f"ERRO ao extrair: {result.stderr}")
                self._set_status("Falha na extração")
                GLib.idle_add(self._on_install_failed)
                return

            self._log_append("  ✓ Extração concluída")
            self._log_append("")

            # Step 4: Install with pkexec
            self._set_status("Instalando (autenticação necessária)...")
            self._set_progress(0.85, "Instalando...")
            self._log_append("Executando instalação com privilégios elevados (pkexec)...")
            self._log_append("Uma janela de autenticação será exibida.")
            self._log_append("")

            helper_script = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "scripts", "pjeoffice-install-helper.sh",
            )

            if not os.path.isfile(helper_script):
                self._log_append(f"ERRO: Script auxiliar não encontrado: {helper_script}")
                self._set_status("Falha — Script não encontrado")
                GLib.idle_add(self._on_install_failed)
                return

            result = subprocess.run(
                ["pkexec", "bash", helper_script, self._tmp_dir],
                capture_output=True, text=True, timeout=120,
            )

            # Show all output
            for line in result.stdout.splitlines():
                if line.startswith("LOG: "):
                    self._log_append(f"  {line[5:]}")
                elif line.startswith("OK: "):
                    self._log_append(f"  ✓ {line[4:]}")
                else:
                    self._log_append(f"  {line}")

            if result.stderr:
                for line in result.stderr.splitlines():
                    self._log_append(f"  [stderr] {line}")

            if result.returncode != 0:
                self._log_append("")
                self._log_append(f"ERRO: pkexec retornou código {result.returncode}")
                if result.returncode == 126:
                    self._log_append("(Autenticação cancelada pelo usuário)")
                self._set_status("Instalação cancelada ou falhou")
                GLib.idle_add(self._on_install_failed)
                return

            # Step 5: Done
            self._set_progress(1.0, "100% — Concluído!")
            self._set_status("Instalação concluída!")
            self._log_append("")
            self._log_append("═══════════════════════════════════════════")
            self._log_append("  PJeOffice Pro instalado com sucesso!")
            self._log_append("  Execute: pjeoffice-pro")
            self._log_append("═══════════════════════════════════════════")
            GLib.idle_add(self._on_install_success)

        except subprocess.TimeoutExpired:
            self._log_append("ERRO: Operação expirou (timeout)")
            self._set_status("Falha — Timeout")
            GLib.idle_add(self._on_install_failed)
        except Exception as exc:
            self._log_append(f"ERRO: {exc}")
            self._set_status("Falha na instalação")
            GLib.idle_add(self._on_install_failed)
        finally:
            if self._tmp_dir and os.path.isdir(self._tmp_dir):
                shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _download_file(self, url: str, dest: str) -> bool:
        """Download with progress reporting."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BigCertificados/1.0"})
            response = urllib.request.urlopen(req, timeout=60)
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 65536

            if total_size > 0:
                total_mb = total_size / (1024 * 1024)
                self._log_append(f"Tamanho: {total_mb:.1f} MB")
            else:
                self._log_append("Tamanho: desconhecido")

            self._log_append("Iniciando download...")

            with open(dest, "wb") as f:
                while True:
                    if self._cancelled:
                        self._log_append("Download cancelado pelo usuário.")
                        return False

                    chunk = response.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        fraction = downloaded / total_size
                        pct = fraction * 100
                        dl_mb = downloaded / (1024 * 1024)
                        self._set_progress(
                            fraction * 0.65, f"{pct:.0f}%"
                        )
                        self._set_size_label(
                            f"{dl_mb:.1f} / {total_mb:.1f} MB"
                        )
                    else:
                        dl_mb = downloaded / (1024 * 1024)
                        self._set_size_label(f"{dl_mb:.1f} MB baixados")
                        self._progress_bar.props.fraction = -1

            self._set_progress(0.65, "Download concluído")
            self._log_append(f"  ✓ Download concluído ({downloaded / (1024*1024):.1f} MB)")
            self._log_append("")
            return True

        except Exception as exc:
            self._log_append(f"ERRO no download: {exc}")
            self._set_status("Falha no download")
            GLib.idle_add(self._on_install_failed)
            return False

    @staticmethod
    def _calculate_sha256(path: str) -> str:
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha.update(data)
        return sha.hexdigest()

    def _on_install_success(self) -> bool:
        self._install_btn.set_label("Concluído ✓")
        self._install_btn.add_css_class("success")
        self._cancel_btn.set_label("Fechar")
        if self._on_installed:
            self._on_installed()
        return False

    def _on_install_failed(self) -> bool:
        self._install_btn.set_label("Tentar Novamente")
        self._install_btn.set_sensitive(True)
        self._install_btn.remove_css_class("suggested-action")
        self._install_btn.add_css_class("destructive-action")
        return False
