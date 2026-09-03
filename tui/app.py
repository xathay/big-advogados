"""Big Advogados TUI — casca principal (Textual).

Navegação por sidebar + ContentSwitcher. Todas as seções funcionais.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.theme import Theme
from textual.widgets import (
    ContentSwitcher,
    Label,
    ListItem,
    ListView,
    Static,
)

from tui import __version__
from tui.screens.assinar import Assinar
from tui.screens.certificados import Certificados
from tui.screens.dashboard import Dashboard
from tui.screens.drivers import Drivers
from tui.screens.pjeoffice import PJeOffice
from tui.screens.sistemas import Sistemas
from tui.screens.token import TokenA3
from tui.screens.transcritor import Transcritor

# Tema próprio — estética neon-mauve Blade Runner 2049, paleta do big-perf:
# MAUVE #bb9af7 estrutura · NEON #f2a6ff destaque · PINK #f04dff · DIM #444b6a.
NEON_MAUVE = Theme(
    name="neon-mauve",
    primary="#f2a6ff",
    secondary="#bb9af7",
    accent="#f04dff",
    foreground="#a9b1d6",
    background="#0a0612",
    surface="#140a1f",
    panel="#1b0f2a",
    success="#9ece6a",
    warning="#e0af68",
    error="#f7768e",
    dark=True,
)

# (id, tecla, rótulo, disponível?)
SECOES = [
    ("dashboard", "d", "Dashboard", True),
    ("transcritor", "x", "Transcritor", True),
    ("certificados", "c", "Certificados", True),
    ("token", "t", "Token A3", True),
    ("sistemas", "s", "Sistemas", True),
    ("pjeoffice", "p", "PJeOffice", True),
    ("drivers", "g", "Drivers", True),
    ("assinar", "a", "Assinar PDF", True),
]


class BigAdvogadosTUI(App):
    """App principal."""

    CSS_PATH = "app.tcss"
    TITLE = "Big Advogados"

    # Temas que combinam com o visual do Omarchy/Ghostty.
    TEMAS = ("neon-mauve", "tokyo-night", "catppuccin-mocha", "gruvbox", "nord", "dracula")

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
        # Tema padrão alinhado ao Omarchy (neon-mauve / Blade Runner 2049).
        self.register_theme(NEON_MAUVE)
        self.theme = "neon-mauve"

    def compose(self) -> ComposeResult:
        # Banner no estilo big-perf: ◢ LOGO ◣ // subtítulo, régua dim abaixo.
        yield Static(
            f"[#f04dff]◢[/] [b #f2a6ff]BIG ADVOGADOS[/] [#444b6a]v{__version__}[/] "
            f"[#f04dff]◣[/] [#444b6a]// stack jurídica // omarchy · hyprland[/]",
            id="banner",
        )
        with Horizontal(id="body"):
            with ListView(id="sidebar"):
                for sid, tecla, rotulo, ok in SECOES:
                    marca = "" if ok else " [dim](em breve)[/]"
                    item = ListItem(Label(
                        f"[#bb9af7]\\[[/][b #f2a6ff]{tecla}[/][#bb9af7]][/] {rotulo}{marca}"
                    ))
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
                yield Assinar(id="assinar")
        yield Static("◣◢" * 200, id="footer-strip")

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
