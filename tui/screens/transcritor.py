"""Transcritor — transcrição forense de um áudio com cadeia de custódia.

Reusa o pipeline determinístico de src.transcritor; roda em worker thread
e reporta progresso/log na UI.
"""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
)

from src.transcritor import config as cfg_module
from tui.services.transcricao import transcrever_arquivo

_MODELOS = ["tiny", "base", "small", "medium", "large-v3"]
_SAIDAS = ["pdf", "txt", "md", "json", "csv"]


class Transcritor(VerticalScroll):
    """Formulário + execução da transcrição."""

    def compose(self) -> ComposeResult:
        yield Label("Transcritor forense", classes="title")
        yield Label(
            "SHA-256 + transcrição local (faster-whisper) → PDF/txt/md/json/csv. "
            "O áudio nunca sai da máquina.",
            classes="hint",
        )
        with Vertical(id="tr-form"):
            yield Input(
                placeholder="Caminho do áudio (.m4a .opus .mp3 .ogg .wav .flac)",
                id="tr-path",
            )
            yield Label("Modelo:")
            yield Select(
                [(m, m) for m in _MODELOS],
                prompt="(usar config)",
                allow_blank=True,
                id="tr-modelo",
            )
            yield Label("Saídas:")
            with Horizontal(id="tr-saidas"):
                for fmt in _SAIDAS:
                    yield Checkbox(fmt, value=(fmt == "pdf"), id=f"saida-{fmt}")
            with Horizontal(id="tr-actions"):
                yield Button("Transcrever", variant="primary", id="tr-run")
        yield ProgressBar(id="tr-progress", total=100, show_eta=False)
        yield RichLog(id="tr-log", highlight=True, markup=True, wrap=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "tr-run":
            self._iniciar()

    def _saidas_escolhidas(self) -> set[str]:
        return {
            fmt for fmt in _SAIDAS
            if self.query_one(f"#saida-{fmt}", Checkbox).value
        }

    def _iniciar(self) -> None:
        log = self.query_one("#tr-log", RichLog)
        caminho = self.query_one("#tr-path", Input).value.strip()
        if not caminho:
            log.write("[red]Informe o caminho do áudio.[/]")
            return
        arquivo = Path(caminho).expanduser()
        if not arquivo.is_file():
            log.write(f"[red]Arquivo não encontrado:[/] {arquivo}")
            return

        saidas = self._saidas_escolhidas()
        if not saidas:
            log.write("[red]Selecione ao menos uma saída.[/]")
            return

        modelo_sel = self.query_one("#tr-modelo", Select).value
        modelo = None if modelo_sel is Select.BLANK else str(modelo_sel)

        self.query_one("#tr-run", Button).disabled = True
        self.query_one("#tr-progress", ProgressBar).update(total=100, progress=0)
        log.clear()
        log.write(f"[b]Iniciando:[/] {arquivo.name}")
        self._executar(arquivo, saidas, modelo)

    @work(thread=True, exclusive=True)
    def _executar(self, arquivo: Path, saidas: set[str], modelo: str | None) -> None:
        app = self.app

        def progress(frac: float) -> None:
            app.call_from_thread(
                self.query_one("#tr-progress", ProgressBar).update,
                progress=frac * 100,
            )

        def escreve_log(msg: str) -> None:
            app.call_from_thread(self.query_one("#tr-log", RichLog).write, msg)

        try:
            cfg = cfg_module.load_config()
            if modelo:
                cfg = cfg_module.TranscritorConfig(
                    modelo=cfg_module.ModeloConfig(
                        nome=modelo,
                        device=cfg.modelo.device,
                        compute_type=cfg.modelo.compute_type,
                    ),
                    transcricao=cfg.transcricao,
                    identidade_visual=cfg.identidade_visual,
                    advogado=cfg.advogado,
                )
            resultado = transcrever_arquivo(
                arquivo, cfg, saidas,
                on_progress=progress, on_log=escreve_log,
            )
            app.call_from_thread(self._concluir, resultado, None)
        except Exception as exc:  # noqa: BLE001
            app.call_from_thread(self._concluir, None, exc)

    def _concluir(self, resultado, erro) -> None:
        log = self.query_one("#tr-log", RichLog)
        self.query_one("#tr-run", Button).disabled = False
        if erro is not None:
            log.write(f"[red]Falha:[/] {erro}")
            self.app.bell()
            return
        log.write(
            f"[green b]✓ Pronto[/] — {resultado.n_segmentos} segmentos. "
            f"Saídas: {', '.join(s.path.name for s in resultado.saidas)}"
        )
        self.app.bell()
