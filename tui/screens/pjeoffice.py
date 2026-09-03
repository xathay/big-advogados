"""PJeOffice Pro — instalação, status e verificação de atualização."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Label, ProgressBar, RichLog, Static

from tui.services.pjeoffice import (
    desinstalar,
    instalar,
    status,
    url_download,
    verificar_atualizacao,
)
from tui.services.sistemas import abrir_url


class PJeOffice(VerticalScroll):
    """Instalação, detecção de versão e checagem de atualização do PJeOffice Pro."""

    def compose(self) -> ComposeResult:
        yield Label("PJeOffice Pro", classes="title")
        yield Label(
            "Assinador oficial do CNJ para sistemas judiciais. Instala da fonte "
            "oficial (TRF3/CNJ) com verificação SHA-256 e checa atualizações.",
            classes="hint",
        )
        yield Static("Verificando instalação…", id="pje-status", classes="hint")
        with Horizontal(id="pje-actions"):
            yield Button("Instalar", variant="primary", id="pje-install")
            yield Button("Reinstalar", id="pje-reinstall")
            yield Button("Remover", variant="error", id="pje-remove")
            yield Button("Verificar atualização", id="pje-check")
            yield Button("Abrir página de download", id="pje-download")
        yield Static("", id="pje-update")
        yield ProgressBar(id="pje-progress", total=100, show_eta=False)
        yield RichLog(id="pje-log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        # Barra/log só aparecem durante uma operação de instalação/remoção.
        self.query_one("#pje-progress", ProgressBar).display = False
        self.query_one("#pje-log", RichLog).display = False
        self._carregar_status()

    def ao_entrar(self) -> None:
        self._carregar_status()

    # --- status ----------------------------------------------------------- #

    @work(thread=True, exclusive=True)
    def _carregar_status(self) -> None:
        st = status()
        self.app.call_from_thread(self._mostrar_status, st)

    def _mostrar_status(self, st) -> None:
        widget = self.query_one("#pje-status", Static)
        widget.remove_class("hint")
        instalar_btn = self.query_one("#pje-install", Button)
        reinstalar_btn = self.query_one("#pje-reinstall", Button)
        remover_btn = self.query_one("#pje-remove", Button)
        if st.instalado:
            widget.update(
                f"[green]✓ Instalado[/] — versão [b]{st.versao_instalada}[/]  "
                f"[dim](canônica do app: {st.versao_canonica})[/]"
            )
            instalar_btn.display = False
            reinstalar_btn.display = True
            remover_btn.display = True
        else:
            widget.update(
                f"[yellow]▲ Não instalado.[/] Versão canônica do app: "
                f"[b]{st.versao_canonica}[/]. Clique em [b]Instalar[/]."
            )
            instalar_btn.display = True
            reinstalar_btn.display = False
            remover_btn.display = False

    # --- roteamento de botões -------------------------------------------- #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid in ("pje-install", "pje-reinstall"):
            self._instalar()
        elif bid == "pje-remove":
            self._remover()
        elif bid == "pje-check":
            self._verificar()
        elif bid == "pje-download":
            ok, erro = abrir_url(url_download())
            out = self.query_one("#pje-update", Static)
            out.update(
                "[green]✓ Abrindo página de download[/]" if ok
                else f"[red]Falha:[/] {erro}"
            )

    # --- helpers de UI para as operações --------------------------------- #

    def _set_acoes(self, *, disabled: bool) -> None:
        for btn in self.query("#pje-actions Button"):
            btn.disabled = disabled

    def _preparar_operacao(self, titulo: str) -> RichLog:
        self._set_acoes(disabled=True)
        self.query_one("#pje-update", Static).update("")
        pb = self.query_one("#pje-progress", ProgressBar)
        pb.display = True
        pb.update(total=100, progress=0)
        log = self.query_one("#pje-log", RichLog)
        log.display = True
        log.clear()
        log.write(f"[b]{titulo}[/]")
        return log

    def _ui_progress(self, frac: float, _label: str) -> None:
        self.query_one("#pje-progress", ProgressBar).update(progress=frac * 100)

    def _ui_log(self, msg: str) -> None:
        self.query_one("#pje-log", RichLog).write(msg)

    # --- instalar / reinstalar ------------------------------------------- #

    def _instalar(self) -> None:
        self._preparar_operacao("Instalando PJeOffice Pro…")
        self._exec_instalar()

    @work(thread=True, exclusive=True)
    def _exec_instalar(self) -> None:
        app = self.app

        def on_progress(frac: float, label: str) -> None:
            app.call_from_thread(self._ui_progress, frac, label)

        def on_log(msg: str) -> None:
            app.call_from_thread(self._ui_log, msg)

        ok, msg = instalar(on_progress, on_log)
        app.call_from_thread(self._concluir_operacao, ok, msg)

    # --- remover ---------------------------------------------------------- #

    def _remover(self) -> None:
        log = self._preparar_operacao("Removendo PJeOffice Pro…")
        # remoção não tem progresso granular; barra indeterminada-ish
        self.query_one("#pje-progress", ProgressBar).update(progress=30)
        self._exec_remover()

    @work(thread=True, exclusive=True)
    def _exec_remover(self) -> None:
        app = self.app

        def on_log(msg: str) -> None:
            app.call_from_thread(self._ui_log, msg)

        ok, msg = desinstalar(on_log)
        app.call_from_thread(self._concluir_operacao, ok, msg, True)

    def _concluir_operacao(self, ok: bool, msg: str, remocao: bool = False) -> None:
        if ok and not remocao:
            self.query_one("#pje-progress", ProgressBar).update(progress=100)
        log = self.query_one("#pje-log", RichLog)
        log.write(f"[green b]✓ {msg}[/]" if ok else f"[red b]✗ {msg}[/]")
        self._set_acoes(disabled=False)
        self.app.bell()
        self._carregar_status()  # reavalia botões instalar/remover

    # --- verificação de atualização -------------------------------------- #

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
