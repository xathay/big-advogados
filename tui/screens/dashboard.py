"""Dashboard — panorama do ambiente (config, whisper, pcscd, identidade)."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Label, Static

from tui.services.status import Probe, coletar_status

_ICON = {"ok": "✓", "warn": "▲", "err": "✗", "info": "•"}


class Dashboard(VerticalScroll):
    """Status do ambiente. Recarrega com a tecla 'r'."""

    def compose(self) -> ComposeResult:
        yield Label("Dashboard", classes="title")
        yield Static("Carregando status…", id="dash-status", classes="hint")

    def on_mount(self) -> None:
        self.carregar()

    @work(thread=True, exclusive=True)
    def carregar(self) -> None:
        """Coleta status em thread (subprocess/IO) e atualiza a UI."""
        probes = coletar_status()
        self.app.call_from_thread(self._mostrar_status, probes)

    def _mostrar_status(self, probes: list[Probe]) -> None:
        linhas = []
        for p in probes:
            icon = _ICON.get(p.level, "•")
            linhas.append(
                f"[b]{icon} {p.label}:[/] {p.value}"
            )
        widget = self.query_one("#dash-status", Static)
        widget.remove_class("hint")
        widget.update("\n".join(linhas))
