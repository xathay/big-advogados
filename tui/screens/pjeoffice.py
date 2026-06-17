"""PJeOffice Pro — status da instalação + verificação de atualização."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Label, Static

from tui.services.pjeoffice import status, url_download, verificar_atualizacao
from tui.services.sistemas import abrir_url


class PJeOffice(VerticalScroll):
    """Detecção de versão e checagem de atualização do PJeOffice Pro."""

    def compose(self) -> ComposeResult:
        yield Label("PJeOffice Pro", classes="title")
        yield Label(
            "Assinador oficial do CNJ para sistemas judiciais. Aqui você vê a "
            "versão instalada e verifica atualizações na fonte oficial.",
            classes="hint",
        )
        yield Static("Verificando instalação…", id="pje-status", classes="hint")
        with Horizontal(id="tr-actions"):
            yield Button("Verificar atualização", variant="primary", id="pje-check")
            yield Button("Abrir página de download", id="pje-download")
        yield Static("", id="pje-update")

    def on_mount(self) -> None:
        self._carregar_status()

    def ao_entrar(self) -> None:
        self._carregar_status()

    @work(thread=True, exclusive=True)
    def _carregar_status(self) -> None:
        st = status()
        self.app.call_from_thread(self._mostrar_status, st)

    def _mostrar_status(self, st) -> None:
        widget = self.query_one("#pje-status", Static)
        widget.remove_class("hint")
        if st.instalado:
            widget.update(
                f"[green]✓ Instalado[/] — versão [b]{st.versao_instalada}[/]  "
                f"[dim](canônica do app: {st.versao_canonica})[/]"
            )
        else:
            widget.update(
                f"[yellow]▲ Não instalado.[/] Versão canônica do app: "
                f"[b]{st.versao_canonica}[/]. Use 'Abrir página de download' ou "
                f"instale pelo app GTK."
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pje-check":
            self._verificar()
        elif event.button.id == "pje-download":
            ok, erro = abrir_url(url_download())
            out = self.query_one("#pje-update", Static)
            out.update(
                f"[green]✓ Abrindo página de download[/]" if ok
                else f"[red]Falha:[/] {erro}"
            )

    def _verificar(self) -> None:
        self.query_one("#pje-check", Button).disabled = True
        self.query_one("#pje-update", Static).update("[dim]Consultando fonte oficial…[/]")
        self._exec_check()

    @work(thread=True, exclusive=True)
    def _exec_check(self) -> None:
        st = status()
        info, erro = verificar_atualizacao(st.versao_instalada)
        self.app.call_from_thread(self._mostrar_update, info, erro)

    def _mostrar_update(self, info, erro) -> None:
        out = self.query_one("#pje-update", Static)
        self.query_one("#pje-check", Button).disabled = False
        if erro:
            out.update(f"[red]{erro}[/]")
            return
        if info is None:
            out.update("[green]✓ Você está na versão mais recente.[/]")
            return
        out.update(
            f"[yellow]▲ Atualização disponível:[/] [b]v{info.version}[/]\n"
            f"[dim]{info.download_url}[/]"
            + (f"\n[dim]SHA-256: {info.sha256}[/]" if info.sha256 else "")
        )
        self.app.bell()
