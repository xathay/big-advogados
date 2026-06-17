"""Sistemas judiciais — palette de busca (digite → Enter abre no navegador)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from tui.services.sistemas import Sistema, abrir_url, buscar, listar_sistemas


class Sistemas(VerticalScroll):
    """Busca incremental sobre os 39 sistemas judiciais."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._todos: list[Sistema] = listar_sistemas()
        self._filtrados: list[Sistema] = list(self._todos)

    def compose(self) -> ComposeResult:
        yield Label("Sistemas judiciais", classes="title")
        yield Label(
            "Digite tribunal/estado (ex.: 'TJBA', 'pje trt5', 'esaj sp') · "
            "Enter abre o 1º resultado · ↑↓ navega · clique abre.",
            classes="hint",
        )
        yield Input(placeholder="Buscar sistema…", id="sis-search")
        yield OptionList(id="sis-list")
        yield Static("", id="sis-status")

    def on_mount(self) -> None:
        self._popular(self._todos)

    def ao_entrar(self) -> None:
        """Chamado ao navegar para esta seção: foca a busca."""
        self.query_one("#sis-search", Input).focus()

    # ─── busca ───

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "sis-search":
            self._filtrados = buscar(self._todos, event.value)
            self._popular(self._filtrados)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "sis-search" and self._filtrados:
            self._abrir(self._filtrados[0])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index is not None and 0 <= event.option_index < len(self._filtrados):
            self._abrir(self._filtrados[event.option_index])

    # ─── render / ação ───

    def _popular(self, sistemas: list[Sistema]) -> None:
        lista = self.query_one("#sis-list", OptionList)
        lista.clear_options()
        for s in sistemas:
            regiao = f"  [dim]· {s.regiao}[/]" if s.regiao else ""
            lista.add_option(Option(f"[b]{s.nome}[/]{regiao}"))
        status = self.query_one("#sis-status", Static)
        n = len(sistemas)
        status.update(f"[dim]{n} sistema{'s' if n != 1 else ''}[/]")

    def _abrir(self, s: Sistema) -> None:
        ok, erro = abrir_url(s.url)
        status = self.query_one("#sis-status", Static)
        if ok:
            status.update(f"[green]✓ Abrindo[/] {s.nome} → [dim]{s.url}[/]")
        else:
            status.update(f"[red]Falha:[/] {erro}")
            self.app.bell()
