"""Dashboard — panorama do ambiente (config, whisper, pcscd, identidade)."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label, Static

from tui.services.status import Probe, coletar_status

_ICON = {"ok": "●", "warn": "▲", "err": "○", "info": "·"}


class Dashboard(VerticalScroll):
    """Status do ambiente. Recarrega com a tecla 'r'."""

    def compose(self) -> ComposeResult:
        yield Label("Dashboard", classes="title")
        yield Vertical(Static("Carregando status…", classes="hint"), id="dash-status")

    def on_mount(self) -> None:
        self.carregar()

    @work(thread=True, exclusive=True)
    def carregar(self) -> None:
        """Coleta status em thread (subprocess/IO) e atualiza a UI."""
        probes = coletar_status()
        self.app.call_from_thread(self._mostrar_status, probes)

    def _mostrar_status(self, probes: list[Probe]) -> None:
        cont = self.query_one("#dash-status", Vertical)
        cont.remove_children()
        for p in probes:
            icon = _ICON.get(p.level, "•")
            cont.mount(Static(
                f"[b]{icon} {p.label}:[/] {p.value}",
                classes=f"probe-row lvl-{p.level}",
            ))
