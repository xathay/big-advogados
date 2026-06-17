"""Big Advogados TUI — casca principal (Textual).

Navegação por sidebar + ContentSwitcher. Fase 1 entrega Dashboard e
Transcritor funcionais; as demais seções são placeholders das próximas fases.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import (
    ContentSwitcher,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Static,
)

from tui import __version__
from tui.screens.certificados import Certificados
from tui.screens.dashboard import Dashboard
from tui.screens.drivers import Drivers
from tui.screens.pjeoffice import PJeOffice
from tui.screens.sistemas import Sistemas
from tui.screens.token import TokenA3
from tui.screens.transcritor import Transcritor

# (id, tecla, rótulo, disponível?)
SECOES = [
    ("dashboard", "d", "Dashboard", True),
    ("transcritor", "x", "Transcritor", True),
    ("certificados", "c", "Certificados", True),
    ("token", "t", "Token A3", True),
    ("sistemas", "s", "Sistemas", True),
    ("pjeoffice", "p", "PJeOffice", True),
    ("drivers", "g", "Drivers", True),
    ("assinar", "a", "Assinar PDF", False),
]


class Placeholder(Static):
    """Seção ainda não implementada (fase futura)."""

    def __init__(self, titulo: str, fase: str, id: str) -> None:
        super().__init__(id=id)
        self._titulo = titulo
        self._fase = fase

    def compose(self) -> ComposeResult:
        yield Label(self._titulo, classes="title")
        yield Static(f"Em breve — {self._fase}.", classes="placeholder")


class BigAdvogadosTUI(App):
    """App principal."""

    CSS_PATH = "app.tcss"
    TITLE = "Big Advogados"

    # Temas que combinam com o visual do Omarchy/Ghostty.
    TEMAS = ("tokyo-night", "catppuccin-mocha", "gruvbox", "nord", "dracula")

    BINDINGS = [
        Binding("d", "ir('dashboard')", "Dashboard"),
        Binding("x", "ir('transcritor')", "Transcritor"),
        Binding("c", "ir('certificados')", "Certificados"),
        Binding("t", "ir('token')", "Token"),
        Binding("s", "ir('sistemas')", "Sistemas"),
        Binding("p", "ir('pjeoffice')", "PJeOffice"),
        Binding("g", "ir('drivers')", "Drivers"),
        Binding("a", "ir('assinar')", "Assinar"),
        Binding("r", "recarregar", "Recarregar"),
        Binding("escape", "focar_menu", "Menu", show=False),
        Binding("ctrl+t", "alterna_tema", "Tema"),
        Binding("q", "quit", "Sair"),
    ]

    def on_mount(self) -> None:
        # Tema padrão alinhado ao Omarchy (Hyprland/Ghostty).
        self.theme = "tokyo-night"

    def compose(self) -> ComposeResult:
        self.sub_title = f"v{__version__} · Omarchy/Hyprland"
        yield Header()
        with Horizontal(id="body"):
            with ListView(id="sidebar"):
                for sid, tecla, rotulo, ok in SECOES:
                    marca = "" if ok else " [dim](em breve)[/]"
                    item = ListItem(Label(f"[b]{tecla}[/]  {rotulo}{marca}"))
                    item.id = f"nav-{sid}"
                    yield item
            with ContentSwitcher(initial="dashboard", id="content"):
                yield Dashboard(id="dashboard")
                yield Transcritor(id="transcritor")
                yield Certificados(id="certificados")
                yield TokenA3(id="token")
                yield Sistemas(id="sistemas")
                yield PJeOffice(id="pjeoffice")
                yield Drivers(id="drivers")
                yield Placeholder("Assinar PDF", "fase 5 (sem preview visual)", id="assinar")

    def action_ir(self, secao: str) -> None:
        switcher = self.query_one("#content", ContentSwitcher)
        switcher.current = secao
        # Permite que a tela ative seu campo principal ao entrar (sem roubar
        # foco no boot, já que o ContentSwitcher monta todas as telas).
        try:
            ativa = switcher.get_child_by_id(secao)
        except Exception:  # noqa: BLE001
            ativa = None
        if ativa is not None and hasattr(ativa, "ao_entrar"):
            ativa.ao_entrar()

    def action_recarregar(self) -> None:
        switcher = self.query_one("#content", ContentSwitcher)
        if switcher.current == "dashboard":
            self.query_one(Dashboard).carregar()

    def action_focar_menu(self) -> None:
        """Escape: tira o foco de um campo e volta ao menu (teclas de letra voltam a navegar)."""
        self.query_one("#sidebar", ListView).focus()

    def action_alterna_tema(self) -> None:
        """Ctrl+T: cicla entre temas que combinam com o Omarchy."""
        try:
            atual = self.TEMAS.index(self.theme)
        except ValueError:
            atual = -1
        novo = self.TEMAS[(atual + 1) % len(self.TEMAS)]
        self.theme = novo
        self.notify(f"Tema: {novo}", timeout=2)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id and event.item.id.startswith("nav-"):
            self.action_ir(event.item.id[len("nav-"):])
