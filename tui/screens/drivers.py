"""Drivers & Tokens — lista com status, busca e instalação."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from tui.services.drivers import (
    DriverItem,
    buscar,
    instalar,
    listar_drivers,
    pcscd_status,
)


class Drivers(VerticalScroll):
    """68 drivers catalogados — status em tempo real + instalação."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._todos: list[DriverItem] = []
        self._filtrados: list[DriverItem] = []

    def compose(self) -> ComposeResult:
        yield Label("Drivers & Tokens", classes="title")
        yield Label(
            "Status via pacman. Enter/clique instala o driver (oficial via "
            "pkexec; AUR abre um terminal). Digite para filtrar.",
            classes="hint",
        )
        yield Static("", id="drv-pcscd")
        yield Input(placeholder="Filtrar driver… (ex.: 'etoken', 'safenet', 'yubikey')", id="drv-search")
        yield OptionList(id="drv-list")
        yield Static("", id="drv-status")

    def on_mount(self) -> None:
        self._recarregar()

    def ao_entrar(self) -> None:
        self.query_one("#drv-search", Input).focus()

    # ─── carregar / status ───

    @work(thread=True, exclusive=True)
    def _recarregar(self) -> None:
        itens = listar_drivers()
        ativo, habilitado = pcscd_status()
        self.app.call_from_thread(self._aplicar, itens, ativo, habilitado)

    def _aplicar(self, itens: list[DriverItem], pcscd_ativo: bool, pcscd_hab: bool) -> None:
        self._todos = itens
        consulta = self.query_one("#drv-search", Input).value
        self._filtrados = buscar(itens, consulta)
        self._popular(self._filtrados)
        inst = sum(1 for d in itens if d.instalado)
        estado = (
            "[green]ativo[/]" if pcscd_ativo else "[yellow]inativo[/]"
        ) + (" · habilitado" if pcscd_hab else " · não habilitado")
        self.query_one("#drv-pcscd", Static).update(
            f"[b]pcscd:[/] {estado}    [dim]{inst}/{len(itens)} drivers instalados[/]"
        )

    def _popular(self, itens: list[DriverItem]) -> None:
        lista = self.query_one("#drv-list", OptionList)
        lista.clear_options()
        for d in itens:
            marca = "[green]✓[/]" if d.instalado else "[dim]○[/]"
            fonte = "[blue]oficial[/]" if d.source == "official" else "[magenta]AUR[/]"
            lista.add_option(Option(
                f"{marca} [b]{d.nome}[/]  {fonte}  [dim]· {d.categoria_label}[/]"
            ))
        n = len(itens)
        self.query_one("#drv-status", Static).update(f"[dim]{n} driver(s)[/]")

    # ─── busca ───

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "drv-search":
            self._filtrados = buscar(self._todos, event.value)
            self._popular(self._filtrados)

    # ─── instalação ───

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if idx is None or not (0 <= idx < len(self._filtrados)):
            return
        self._instalar(self._filtrados[idx])

    def _instalar(self, item: DriverItem) -> None:
        status = self.query_one("#drv-status", Static)
        if item.instalado:
            pkgs = ", ".join(item.packages)
            status.update(f"[green]✓ {item.nome}[/] já instalado [dim]({pkgs})[/]")
            return
        status.update(f"[dim]Instalando {item.nome}…[/]")
        self._exec_instalar(item)

    @work(thread=True, exclusive=True)
    def _exec_instalar(self, item: DriverItem) -> None:
        ok, msg, terminal = instalar(item)
        self.app.call_from_thread(self._resultado_instalar, item, ok, msg, terminal)

    def _resultado_instalar(self, item: DriverItem, ok: bool, msg: str, terminal: bool) -> None:
        status = self.query_one("#drv-status", Static)
        if ok and not terminal:
            status.update(f"[green]✓ {item.nome}:[/] {msg}")
            self._recarregar()  # atualiza badges
        elif ok and terminal:
            status.update(f"[yellow]→ {item.nome}:[/] {msg} Reabra a seção p/ atualizar o status.")
        else:
            status.update(f"[red]Falha em {item.nome}:[/] {msg}")
            self.app.bell()
