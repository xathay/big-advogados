"""Certificados A1 — carrega e exibe um PFX/P12."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Static

from tui.services.certificados import carregar_a1, formatar_certificado

_LVL = {"ok": "green", "warn": "yellow", "err": "red", "info": "white"}


def render_certificado(info) -> str:
    linhas = []
    for label, valor, nivel in formatar_certificado(info):
        cor = _LVL.get(nivel, "white")
        linhas.append(f"[b]{label}:[/] [{cor}]{valor}[/]")
    return "\n".join(linhas)


class Certificados(VerticalScroll):
    """Leitor de certificado A1 (arquivo .pfx/.p12)."""

    def compose(self) -> ComposeResult:
        yield Label("Certificados A1 (arquivo)", classes="title")
        yield Label(
            "Carrega um certificado PFX/P12 e mostra titular, CPF, OAB e validade.",
            classes="hint",
        )
        with Vertical(id="tr-form"):
            yield Input(placeholder="Caminho do .pfx / .p12", id="a1-path")
            yield Input(placeholder="Senha do certificado", password=True, id="a1-pwd")
            yield Button("Carregar", variant="primary", id="a1-load")
        yield Static("", id="a1-result")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "a1-load":
            self._carregar()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "a1-pwd":
            self._carregar()

    def _carregar(self) -> None:
        out = self.query_one("#a1-result", Static)
        caminho = self.query_one("#a1-path", Input).value.strip()
        if not caminho:
            out.update("[red]Informe o caminho do arquivo.[/]")
            return
        out.update("[dim]Carregando…[/]")
        senha = self.query_one("#a1-pwd", Input).value
        self.query_one("#a1-load", Button).disabled = True
        self._exec(Path(caminho), senha)

    @work(thread=True, exclusive=True)
    def _exec(self, caminho: Path, senha: str) -> None:
        info, erro = carregar_a1(str(caminho), senha)
        self.app.call_from_thread(self._mostrar, info, erro)

    def _mostrar(self, info, erro) -> None:
        out = self.query_one("#a1-result", Static)
        self.query_one("#a1-load", Button).disabled = False
        if erro:
            out.update(f"[red]{erro}[/]")
            return
        out.update(render_certificado(info))
