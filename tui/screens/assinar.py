"""Assinar PDF — assinatura digital PAdES com A1 (PFX) ou token A3."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Select, Static

from tui.screens.certificados import render_certificado
from tui.services.assinatura import (
    MOTIVO_PADRAO,
    assinar_a1,
    assinar_a3,
    dependencias_ok,
    saida_padrao,
)

MODOS = [("A1 — arquivo PFX/P12", "a1"), ("A3 — token USB (PIN)", "a3")]
VISUAIS_UI = [
    ("Carimbo no rodapé da última página", "rodape"),
    ("Carimbo no topo da última página", "topo"),
    ("Página de certificação ao final", "pagina"),
    ("Assinatura invisível (sem carimbo)", "invisivel"),
]


class Assinar(VerticalScroll):
    """Formulário de assinatura digital de PDF."""

    def compose(self) -> ComposeResult:
        yield Label("Assinar PDF", classes="title")
        yield Label(
            "Assinatura digital PAdES (endesive) com carimbo SHA-256 do "
            "documento. A senha/PIN não sai da máquina.",
            classes="hint",
        )
        with Vertical(id="tr-form"):
            yield Input(placeholder="Caminho do PDF", id="as-pdf")
            yield Select(MODOS, value="a1", allow_blank=False, id="as-modo")
            yield Input(placeholder="Caminho do .pfx / .p12", id="as-pfx")
            yield Input(placeholder="Senha do certificado", password=True, id="as-pwd")
            yield Input(placeholder="PIN do token", password=True, id="as-pin")
            yield Select(VISUAIS_UI, value="rodape", allow_blank=False, id="as-visual")
            yield Input(placeholder=f"Motivo (padrão: {MOTIVO_PADRAO})", id="as-motivo")
            yield Input(placeholder="Saída (padrão: <arquivo>_assinado.pdf)", id="as-saida")
            yield Button("Assinar", variant="primary", id="as-run")
        yield Static("", id="as-result")

    def on_mount(self) -> None:
        self.query_one("#as-pin", Input).display = False
        ok, erro = dependencias_ok()
        if not ok:
            self.query_one("#as-result", Static).update(f"[yellow]{erro}[/]")

    def ao_entrar(self) -> None:
        self.query_one("#as-pdf", Input).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "as-modo":
            return
        a1 = event.value == "a1"
        self.query_one("#as-pfx", Input).display = a1
        self.query_one("#as-pwd", Input).display = a1
        self.query_one("#as-pin", Input).display = not a1

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "as-run":
            self._assinar()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("as-pwd", "as-pin", "as-saida"):
            self._assinar()

    def _valor(self, sel: str) -> str:
        return self.query_one(sel, Input).value

    def _assinar(self) -> None:
        out = self.query_one("#as-result", Static)
        pdf = self._valor("#as-pdf").strip()
        if not pdf:
            out.update("[red]Informe o caminho do PDF.[/]")
            return
        modo = self.query_one("#as-modo", Select).value
        if modo == "a1" and not self._valor("#as-pfx").strip():
            out.update("[red]Informe o caminho do certificado PFX/P12.[/]")
            return
        if modo == "a3" and not self._valor("#as-pin"):
            out.update("[red]Informe o PIN do token.[/]")
            return
        out.update("[dim]Assinando…[/]")
        self.query_one("#as-run", Button).disabled = True
        visual = self.query_one("#as-visual", Select).value
        self._exec(
            modo, pdf,
            self._valor("#as-pfx").strip(), self._valor("#as-pwd"),
            self._valor("#as-pin"),
            self._valor("#as-saida"), self._valor("#as-motivo"), visual,
        )

    @work(thread=True, exclusive=True)
    def _exec(
        self, modo: str, pdf: str, pfx: str, senha: str,
        pin: str, saida: str, motivo: str, visual: str,
    ) -> None:
        if modo == "a1":
            res, erro = assinar_a1(pdf, pfx, senha, saida, motivo, visual)
        else:
            res, erro = assinar_a3(pdf, pin, saida, motivo, visual)
        self.app.call_from_thread(self._mostrar, res, erro)

    def _mostrar(self, res, erro) -> None:
        out = self.query_one("#as-result", Static)
        self.query_one("#as-run", Button).disabled = False
        if erro:
            out.update(f"[red]{erro}[/]")
            return
        linhas = [f"[green]✔ PDF assinado:[/] {res.output_path}"]
        if res.cert_info is not None:
            linhas += ["", render_certificado(res.cert_info)]
        out.update("\n".join(linhas))
