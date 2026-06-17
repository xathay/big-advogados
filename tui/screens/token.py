"""Token A3 — detecção USB com hotplug + leitura de certificado via PIN."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Static

from tui.screens.certificados import render_certificado
from tui.services.certificados import A3Service
from tui.services.token_monitor import (
    TokenHotplug,
    pyudev_disponivel,
    scan_tokens,
)


class TokenA3(VerticalScroll):
    """Lista tokens conectados (hotplug) e lê o certificado A3."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._a3 = A3Service()
        self._hotplug = TokenHotplug()

    def compose(self) -> ComposeResult:
        yield Label("Token A3 (PKCS#11)", classes="title")
        yield Label(
            "Conecte o token — ele aparece automaticamente. Leitura do "
            "certificado exige PIN; o áudio do PIN nunca sai da máquina.",
            classes="hint",
        )
        yield Static("Procurando tokens…", id="tk-list", classes="hint")
        with Vertical(id="tr-form"):
            yield Input(placeholder="PIN do token", password=True, id="tk-pin")
            with Horizontal(id="tr-actions"):
                yield Button("Ler certificado", variant="primary", id="tk-read")
                yield Button("Reescanear", id="tk-rescan")
        yield Static("", id="tk-result")

    def on_mount(self) -> None:
        if not pyudev_disponivel():
            self.query_one("#tk-list", Static).update(
                "[yellow]pyudev ausente — detecção USB desativada. "
                "A leitura por PIN ainda tenta os módulos PKCS#11.[/]"
            )
        else:
            self._escanear()
            self._hotplug.start(self._on_hotplug)

    def on_unmount(self) -> None:
        self._hotplug.stop()

    # ─── scan / hotplug ───

    @work(thread=True, exclusive=True)
    def _escanear(self) -> None:
        tokens = scan_tokens()
        self.app.call_from_thread(self._mostrar_lista, tokens)

    def _mostrar_lista(self, tokens) -> None:
        widget = self.query_one("#tk-list", Static)
        widget.remove_class("hint")
        if not tokens:
            widget.update("[dim]Nenhum token conhecido conectado.[/]")
            return
        linhas = ["[b]Tokens conectados:[/]"]
        for t in tokens:
            dev = f"  [dim]{t.devnode}[/]" if t.devnode else ""
            linhas.append(f"  [green]✓[/] {t.nome}{dev}")
        widget.update("\n".join(linhas))

    def _on_hotplug(self, action: str, vid: int, pid: int, devnode: str) -> None:
        # roda na thread do monitor → marshalla p/ a UI e re-escaneia
        self.app.call_from_thread(self._escanear)

    # ─── leitura do certificado ───

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "tk-read":
            self._ler()
        elif event.button.id == "tk-rescan":
            self._escanear()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "tk-pin":
            self._ler()

    def _ler(self) -> None:
        pin = self.query_one("#tk-pin", Input).value
        if not pin:
            self.query_one("#tk-result", Static).update("[red]Informe o PIN.[/]")
            return
        self.query_one("#tk-read", Button).disabled = True
        self.query_one("#tk-result", Static).update("[dim]Detectando módulo e lendo…[/]")
        self._exec_ler(pin)

    @work(thread=True, exclusive=True)
    def _exec_ler(self, pin: str) -> None:
        modulo, slots, erro = self._a3.detectar()
        if erro:
            self.app.call_from_thread(self._mostrar_certs, [], erro)
            return
        certs, erro = self._a3.ler(slots[0].slot_id, pin)
        self.app.call_from_thread(self._mostrar_certs, certs, erro, modulo)

    def _mostrar_certs(self, certs, erro, modulo: str | None = None) -> None:
        out = self.query_one("#tk-result", Static)
        self.query_one("#tk-read", Button).disabled = False
        # limpa o PIN da UI após o uso
        self.query_one("#tk-pin", Input).value = ""
        if erro:
            out.update(f"[red]{erro}[/]")
            self.app.bell()
            return
        blocos = []
        if modulo:
            blocos.append(f"[dim]Módulo: {modulo}[/]\n")
        for i, info in enumerate(certs, 1):
            cabec = f"[b u]Certificado {i}[/]" if len(certs) > 1 else ""
            blocos.append((cabec + "\n" if cabec else "") + render_certificado(info))
        out.update("\n\n".join(blocos))
        self.app.bell()
