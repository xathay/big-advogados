"""Judicial systems quick-access view."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib  # noqa: E402

from src.utils.updater import (
    PJeOfficeUpdateInfo,
    check_pjeoffice_updates_async,
    get_installed_pjeoffice_version,
    is_pjeoffice_auto_update_enabled,
    set_pjeoffice_auto_update_enabled,
    should_check_pjeoffice_now,
)


# Brazilian electronic judicial systems organized by state/court level.
JUDICIAL_STATES = [
    {
        "name": "Tribunais Superiores",
        "subtitle": "STJ · TST · CNJ",
        "icon": "starred-symbolic",
        "systems": [
            {
                "name": "PJe — STJ",
                "url": "https://pje.stj.jus.br/pje/login.seam",
                "description": "Processo Judicial Eletrônico — Superior Tribunal de Justiça",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — STJ",
                "url": "https://processo.stj.jus.br/processo/pesquisa/",
                "description": "Pesquisa de processos no STJ",
                "icon": "system-search-symbolic",
            },
            {
                "name": "PJe — TST",
                "url": "https://pje.tst.jus.br",
                "description": "PJe — Tribunal Superior do Trabalho",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Portal PJe — CNJ",
                "url": "https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/",
                "description": "Portal PJe — Conselho Nacional de Justiça",
                "icon": "document-send-symbolic",
            },
        ],
    },
    {
        "name": "Bahia",
        "subtitle": "TJBA · TRF1 · TRT5",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PJe — TJBA 1ª Instância",
                "url": "https://pje.tjba.jus.br",
                "description": "Processo Judicial Eletrônico — Tribunal de Justiça da Bahia",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TJBA 2ª Instância",
                "url": "https://pje2g.tjba.jus.br",
                "description": "PJe 2º Grau — TJBA",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRF1 1ª Instância",
                "url": "https://pje1g.trf1.jus.br",
                "description": "PJe — Tribunal Regional Federal da 1ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRF1 2ª Instância",
                "url": "https://pje2g.trf1.jus.br",
                "description": "PJe 2º Grau — TRF1",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT5 (Bahia)",
                "url": "https://pje.trt5.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 5ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PROJUDI — TJBA",
                "url": "https://projudi.tjba.jus.br",
                "description": "Processo Judicial Digital — TJBA (sistema legado)",
                "icon": "document-properties-symbolic",
            },
            {
                "name": "e-SAJ — TJBA",
                "url": "https://esaj.tjba.jus.br",
                "description": "Sistema de Automação da Justiça — Consulta",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "São Paulo",
        "subtitle": "TJSP · eSAJ",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "eSAJ — TJSP 1ª Instância",
                "url": "https://esaj.tjsp.jus.br/cpopg/open.do",
                "description": "Consulta Processual 1º Grau — eSAJ / TJSP",
                "icon": "system-search-symbolic",
            },
            {
                "name": "eSAJ — TJSP 2ª Instância",
                "url": "https://esaj.tjsp.jus.br/cposg/open.do",
                "description": "Consulta Processual 2º Grau — eSAJ / TJSP",
                "icon": "system-search-symbolic",
            },
            {
                "name": "Portal eSAJ — TJSP",
                "url": "https://esaj.tjsp.jus.br/esaj/portal.do?servico=190090",
                "description": "Portal de serviços eSAJ — TJSP",
                "icon": "document-send-symbolic",
            },
            {
                "name": "PJe — TRT2 (São Paulo)",
                "url": "https://pje.trt2.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 2ª Região",
                "icon": "document-edit-symbolic",
            },
        ],
    },
    {
        "name": "Distrito Federal",
        "subtitle": "TJDFT · TRF1 · TRT10",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PJe — TJDFT 1ª Instância",
                "url": "https://pje.tjdft.jus.br",
                "description": "PJe — Tribunal de Justiça do Distrito Federal e Territórios",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TJDFT 2ª Instância",
                "url": "https://pje2i.tjdft.jus.br",
                "description": "PJe 2º Grau — TJDFT",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT10 (DF/TO)",
                "url": "https://pje.trt10.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 10ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — TJDFT",
                "url": "https://www.tjdft.jus.br/consultas",
                "description": "Portal de consultas processuais — TJDFT",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "Rio de Janeiro",
        "subtitle": "TJRJ · TRF2 · TRT1",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PJe — TJRJ 1ª Instância",
                "url": "https://pje.tjrj.jus.br",
                "description": "PJe — Tribunal de Justiça do Rio de Janeiro",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TJRJ 2ª Instância",
                "url": "https://pje2g.tjrj.jus.br",
                "description": "PJe 2º Grau — TJRJ",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRF2",
                "url": "https://pje.trf2.jus.br",
                "description": "PJe — Tribunal Regional Federal da 2ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT1 (Rio de Janeiro)",
                "url": "https://pje.trt1.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 1ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — TJRJ",
                "url": "https://www3.tjrj.jus.br/consultaprocessual/",
                "description": "Consulta de processos — TJRJ",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "Minas Gerais",
        "subtitle": "TJMG · TRF1 · TRT3",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PJe — TJMG 1ª Instância",
                "url": "https://pje.tjmg.jus.br",
                "description": "PJe — Tribunal de Justiça de Minas Gerais",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TJMG 2ª Instância",
                "url": "https://pje2g.tjmg.jus.br",
                "description": "PJe 2º Grau — TJMG",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT3 (Minas Gerais)",
                "url": "https://pje.trt3.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 3ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PROJUDI — TJMG",
                "url": "https://projudi.tjmg.jus.br",
                "description": "Processo Judicial Digital — TJMG (Juizados Especiais)",
                "icon": "document-properties-symbolic",
            },
            {
                "name": "Consulta Processual — TJMG",
                "url": "https://www4.tjmg.jus.br/juridico/sf/proc_movimentacoes.jsp",
                "description": "Consulta de processos — TJMG",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "Rio Grande do Sul",
        "subtitle": "TJRS · TRF4 · TRT4",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "eThemis — TJRS 1ª Instância",
                "url": "https://www.tjrs.jus.br/novo/servicos/e-themis-1o-grau/",
                "description": "Sistema eThemis — TJRS 1º Grau",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "eThemis — TJRS 2ª Instância",
                "url": "https://www.tjrs.jus.br/novo/servicos/e-themis-2o-grau/",
                "description": "Sistema eThemis — TJRS 2º Grau",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRF4",
                "url": "https://pje.trf4.jus.br",
                "description": "PJe — Tribunal Regional Federal da 4ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT4 (Rio Grande do Sul)",
                "url": "https://pje.trt4.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 4ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — TJRS",
                "url": "https://www.tjrs.jus.br/novo/busca/?tb=proc",
                "description": "Consulta de processos — TJRS",
                "icon": "system-search-symbolic",
            },
        ],
    },
    {
        "name": "Paraná",
        "subtitle": "TJPR · TRF4 · TRT9",
        "icon": "mark-location-symbolic",
        "systems": [
            {
                "name": "PROJUDI — TJPR",
                "url": "https://projudi.tjpr.jus.br",
                "description": "Processo Judicial Digital — TJPR",
                "icon": "document-properties-symbolic",
            },
            {
                "name": "PJe — TJPR 1ª Instância",
                "url": "https://pje.tjpr.jus.br",
                "description": "PJe — Tribunal de Justiça do Paraná",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TJPR 2ª Instância",
                "url": "https://pje2g.tjpr.jus.br",
                "description": "PJe 2º Grau — TJPR",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "PJe — TRT9 (Paraná)",
                "url": "https://pje.trt9.jus.br",
                "description": "PJe — Tribunal Regional do Trabalho 9ª Região",
                "icon": "document-edit-symbolic",
            },
            {
                "name": "Consulta Processual — TJPR",
                "url": "https://portal.tjpr.jus.br/jurisprudencia/",
                "description": "Consulta de processos e jurisprudência — TJPR",
                "icon": "system-search-symbolic",
            },
        ],
    },
]

# Flat list of all judicial systems for use by other modules (e.g. Brave config)
JUDICIAL_SYSTEMS: list[dict[str, str]] = [
    system
    for state in JUDICIAL_STATES
    for system in state["systems"]
]


class SystemsView(Adw.Bin):
    """Sidebar-navigated view with judicial systems, PJeOffice, drivers and browsers."""

    _SECTIONS = [
        ("judicial", "Sistemas Judiciais", "document-edit-symbolic"),
        ("pjeoffice", "PJeOffice Pro", "applications-office-symbolic"),
        ("drivers", "Drivers & Tokens", "dialog-password-symbolic"),
        ("browsers", "Navegadores", "web-browser-symbolic"),
    ]

    def __init__(self) -> None:
        super().__init__()

        # ── Sidebar ──
        self._sidebar = Gtk.ListBox()
        self._sidebar.add_css_class("navigation-sidebar")
        self._sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)

        for section_id, label_text, icon_name in self._SECTIONS:
            row = Gtk.ListBoxRow()
            row._section_id = section_id  # noqa: SLF001
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hbox.set_margin_top(6)
            hbox.set_margin_bottom(6)
            hbox.set_margin_start(8)
            hbox.set_margin_end(8)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            label = Gtk.Label(label=label_text)
            label.set_xalign(0)
            label.set_hexpand(True)
            hbox.append(icon)
            hbox.append(label)
            row.set_child(hbox)
            self._sidebar.append(row)

        self._sidebar.connect("row-selected", self._on_sidebar_selected)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_child(self._sidebar)
        sidebar_scroll.set_size_request(180, -1)

        # ── Content stack ──
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)

        self._stack.add_named(self._build_judicial_page(), "judicial")
        self._stack.add_named(self._build_pjeoffice_page(), "pjeoffice")
        self._stack.add_named(self._build_drivers_page(), "drivers")
        self._stack.add_named(self._build_browsers_page(), "browsers")

        # ── OverlaySplitView: sidebar collapses on narrow windows ──
        self._split = Adw.OverlaySplitView()
        self._split.set_sidebar(sidebar_scroll)
        self._split.set_content(self._stack)
        self._split.set_min_sidebar_width(180)
        self._split.set_max_sidebar_width(220)
        self._split.set_sidebar_position(Gtk.PackType.START)
        self.set_child(self._split)

        # Select first row
        first = self._sidebar.get_row_at_index(0)
        if first:
            self._sidebar.select_row(first)

        # Pending update info for install action
        self._pending_update: Optional[PJeOfficeUpdateInfo] = None

        # Auto-check on startup
        if is_pjeoffice_auto_update_enabled() and should_check_pjeoffice_now():
            if self._is_pjeoffice_installed():
                GLib.idle_add(self._auto_check_pjeoffice)

    # ── Sidebar callback ──

    def _on_sidebar_selected(
        self,
        _listbox: Gtk.ListBox,
        row: Optional[Gtk.ListBoxRow],
    ) -> None:
        if row:
            self._stack.set_visible_child_name(row._section_id)  # noqa: SLF001

    def select_section(self, section_id: str) -> None:
        """Select a sidebar section by ID (public API for navigation)."""
        for i in range(self._sidebar.observe_children().get_n_items()):
            row = self._sidebar.get_row_at_index(i)
            if row and getattr(row, "_section_id", None) == section_id:
                self._sidebar.select_row(row)
                return

    # ── Page helpers ──

    @staticmethod
    def _make_page(content: Gtk.Widget) -> Gtk.ScrolledWindow:
        """Wrap *content* in Clamp → ScrolledWindow."""
        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)
        clamp.set_child(content)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(clamp)
        return scroll

    @staticmethod
    def _page_box() -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        return box

    # ── Individual pages ──

    def _build_judicial_page(self) -> Gtk.Widget:
        content = self._page_box()

        group = Adw.PreferencesGroup()
        group.set_title("PJe — Processo Judicial Eletrônico")
        group.set_description(
            "Selecione o estado ou tribunal para acessar os sistemas disponíveis."
        )

        for state in JUDICIAL_STATES:
            expander = Adw.ExpanderRow()
            expander.set_title(state["name"])
            expander.set_subtitle(state["subtitle"])
            expander.set_icon_name(state["icon"])

            for system in state["systems"]:
                row = Adw.ActionRow()
                row.set_title(system["name"])
                row.set_subtitle(system["description"])
                row.set_icon_name(system["icon"])
                row.set_activatable(True)
                row.connect("activated", self._on_system_clicked, system["url"])

                arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
                row.add_suffix(arrow)
                expander.add_row(row)

            group.add(expander)

        content.append(group)
        return self._make_page(content)

    def _build_pjeoffice_page(self) -> Gtk.Widget:
        content = self._page_box()

        pjeoffice_group = Adw.PreferencesGroup()
        pjeoffice_group.set_title("PJeOffice Pro — Assinador Digital")
        pjeoffice_group.set_description(
            "Necessário para assinar documentos nos sistemas PJe."
        )

        self._pjeoffice_row = Adw.ActionRow()
        self._pjeoffice_row.set_icon_name("applications-office-symbolic")
        self._pjeoffice_status_icon: Optional[Gtk.Image] = None
        self._update_pjeoffice_status()
        pjeoffice_group.add(self._pjeoffice_row)

        self._update_row = Adw.ActionRow()
        self._update_row.set_icon_name("software-update-available-symbolic")
        self._update_row.set_visible(False)
        self._update_status_icon: Optional[Gtk.Image] = None
        pjeoffice_group.add(self._update_row)

        check_update_row = Adw.ActionRow()
        check_update_row.set_title("Verificar atualizações")
        check_update_row.set_subtitle("Consultar o site oficial do CNJ por novas versões")
        check_update_row.set_icon_name("view-refresh-symbolic")
        check_update_row.set_activatable(True)
        check_update_row.connect("activated", self._on_check_pjeoffice_update)

        self._check_spinner = Gtk.Spinner()
        check_update_row.add_suffix(self._check_spinner)
        arrow_upd = Gtk.Image.new_from_icon_name("go-next-symbolic")
        check_update_row.add_suffix(arrow_upd)
        pjeoffice_group.add(check_update_row)

        auto_check_row = Adw.SwitchRow()
        auto_check_row.set_title("Buscar atualizações automaticamente")
        auto_check_row.set_subtitle("Verifica a cada 24h ao abrir o aplicativo")
        auto_check_row.set_icon_name("preferences-system-time-symbolic")
        auto_check_row.set_active(is_pjeoffice_auto_update_enabled())
        auto_check_row.connect("notify::active", self._on_auto_check_toggled)
        pjeoffice_group.add(auto_check_row)

        self._install_row = Adw.ActionRow()
        self._install_row.set_title("Instalar PJeOffice Pro")
        self._install_row.set_subtitle(
            "Baixa do site oficial (CNJ/TRF3) e instala automaticamente"
        )
        self._install_row.set_icon_name("applications-office-symbolic")
        self._install_row.set_activatable(True)
        self._install_row.connect("activated", self._on_install_pjeoffice)
        arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
        self._install_row.add_suffix(arrow)
        self._install_row.set_visible(not self._is_pjeoffice_installed())
        pjeoffice_group.add(self._install_row)

        self._launch_row = Adw.ActionRow()
        self._launch_row.set_title("Abrir PJeOffice Pro")
        self._launch_row.set_subtitle("Iniciar o assinador digital")
        self._launch_row.set_icon_name("applications-office-symbolic")
        self._launch_row.set_activatable(True)
        self._launch_row.connect("activated", self._on_launch_pjeoffice)
        arrow2 = Gtk.Image.new_from_icon_name("go-next-symbolic")
        self._launch_row.add_suffix(arrow2)
        self._launch_row.set_visible(self._is_pjeoffice_installed())
        pjeoffice_group.add(self._launch_row)

        self._remove_row = Adw.ActionRow()
        self._remove_row.set_title("Remover PJeOffice Pro")
        self._remove_row.set_subtitle("Remove completamente do sistema")
        self._remove_row.set_icon_name("user-trash-symbolic")
        self._remove_row.set_activatable(True)
        self._remove_row.connect("activated", self._on_remove_pjeoffice)
        arrow_rm = Gtk.Image.new_from_icon_name("go-next-symbolic")
        self._remove_row.add_suffix(arrow_rm)
        self._remove_row.set_visible(self._is_pjeoffice_installed())
        pjeoffice_group.add(self._remove_row)

        content.append(pjeoffice_group)
        return self._make_page(content)

    def _build_drivers_page(self) -> Gtk.Widget:
        content = self._page_box()
        from src.ui.drivers_view import DriversSection
        self._drivers = DriversSection()
        self._drivers.build(content)
        return self._make_page(content)

    def _build_browsers_page(self) -> Gtk.Widget:
        content = self._page_box()
        self._build_browser_section(content)
        return self._make_page(content)

    @staticmethod
    def _is_pjeoffice_installed() -> bool:
        return (
            shutil.which("pjeoffice-pro") is not None
            or Path("/usr/share/pjeoffice-pro/pjeoffice-pro.jar").is_file()
        )

    def _update_pjeoffice_status(self) -> None:
        # Remove previous status icon before adding new one
        if self._pjeoffice_status_icon is not None:
            self._pjeoffice_row.remove(self._pjeoffice_status_icon)
            self._pjeoffice_status_icon = None

        if self._is_pjeoffice_installed():
            version = get_installed_pjeoffice_version() or "?"
            self._pjeoffice_row.set_title(f"PJeOffice Pro — Instalado (v{version})")
            self._pjeoffice_row.set_subtitle("Pronto para assinar documentos")

            icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            icon.add_css_class("success")
        else:
            self._pjeoffice_row.set_title("PJeOffice Pro — Não instalado")
            self._pjeoffice_row.set_subtitle(
                "Necessário para acessar os sistemas PJe com certificado digital"
            )

            icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            icon.add_css_class("warning")

        self._pjeoffice_status_icon = icon
        self._pjeoffice_row.add_suffix(icon)

    def _on_install_pjeoffice(self, _row: Adw.ActionRow) -> None:
        """Open the PJeOffice Pro installer dialog."""
        from src.ui.pjeoffice_installer import PJeOfficeInstallerDialog

        dialog = PJeOfficeInstallerDialog(on_installed=self._refresh_pjeoffice_status)
        window = self.get_root()
        dialog.present(window)

    def _on_remove_pjeoffice(self, _row: Adw.ActionRow) -> None:
        """Confirm and remove PJeOffice Pro."""
        window = self.get_root()

        confirm = Adw.AlertDialog()
        confirm.set_heading("Remover PJeOffice Pro?")
        confirm.set_body(
            "O PJeOffice Pro será removido completamente do sistema.\n"
            "Você poderá reinstalá-lo a qualquer momento pelo BigCertificados."
        )
        confirm.add_response("cancel", "Cancelar")
        confirm.add_response("remove", "Remover")
        confirm.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.set_default_response("cancel")
        confirm.set_close_response("cancel")
        confirm.connect("response", self._on_remove_confirmed)
        confirm.present(window)

    def _on_remove_confirmed(self, _dialog: Adw.AlertDialog, response: str) -> None:
        """Handle confirmation dialog response."""
        if response != "remove":
            return
        from src.ui.pjeoffice_installer import PJeOfficeUninstallerDialog

        dialog = PJeOfficeUninstallerDialog(on_removed=self._refresh_pjeoffice_status)
        window = self.get_root()
        dialog.present(window)

    def _refresh_pjeoffice_status(self) -> None:
        """Refresh the PJeOffice row after installation or removal."""
        self._update_pjeoffice_status()
        installed = self._is_pjeoffice_installed()
        self._install_row.set_visible(not installed)
        self._launch_row.set_visible(installed)
        self._remove_row.set_visible(installed)

    # ── PJeOffice update checking ──

    def _auto_check_pjeoffice(self) -> bool:
        """Auto-check for PJeOffice updates (called via GLib.idle_add)."""
        installed = get_installed_pjeoffice_version()
        if installed:
            check_pjeoffice_updates_async(installed, self._on_pjeoffice_update_result)
        return False

    def _on_check_pjeoffice_update(self, _row: Adw.ActionRow) -> None:
        """Manual check for PJeOffice Pro updates."""
        installed = get_installed_pjeoffice_version()
        version = installed or "0"

        self._check_spinner.start()
        self._update_row.set_visible(True)
        self._update_row.set_title("Verificando…")
        self._update_row.set_subtitle("Consultando site oficial do CNJ")

        # Remove previous update status icon
        if self._update_status_icon is not None:
            self._update_row.remove(self._update_status_icon)
            self._update_status_icon = None

        check_pjeoffice_updates_async(version, self._on_pjeoffice_update_result)

    def _on_pjeoffice_update_result(
        self,
        update_info: Optional[PJeOfficeUpdateInfo],
        error: Optional[str],
    ) -> bool:
        """Handle PJeOffice update check result."""
        self._check_spinner.stop()

        # Remove previous update status icon
        if self._update_status_icon is not None:
            self._update_row.remove(self._update_status_icon)
            self._update_status_icon = None

        if error:
            self._update_row.set_visible(True)
            self._update_row.set_title("Erro ao verificar atualizações")
            self._update_row.set_subtitle(error)
            icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
            icon.add_css_class("error")
        elif update_info:
            self._pending_update = update_info
            self._update_row.set_visible(True)
            self._update_row.set_title(
                f"Nova versão disponível: v{update_info.version}"
            )
            self._update_row.set_subtitle(
                "Clique em 'Instalar PJeOffice Pro' para atualizar"
            )
            icon = Gtk.Image.new_from_icon_name("software-update-available-symbolic")
            icon.add_css_class("accent")
        else:
            installed = get_installed_pjeoffice_version() or "?"
            self._update_row.set_visible(True)
            self._update_row.set_title("PJeOffice Pro está atualizado")
            self._update_row.set_subtitle(f"Versão instalada: v{installed}")
            icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            icon.add_css_class("success")

        self._update_status_icon = icon
        self._update_row.add_suffix(icon)

        return False

    def _on_auto_check_toggled(self, row: Adw.SwitchRow, *_args: object) -> None:
        """Toggle automatic PJeOffice update checking."""
        set_pjeoffice_auto_update_enabled(row.get_active())

    @staticmethod
    def _on_launch_pjeoffice(_row: Adw.ActionRow) -> None:
        """Launch PJeOffice Pro."""
        import subprocess
        path = shutil.which("pjeoffice-pro")
        if path:
            subprocess.Popen([path])

    @staticmethod
    def _on_system_clicked(_row: Adw.ActionRow, url: str) -> None:
        Gio.AppInfo.launch_default_for_uri(url, None)

    # ── Browser configuration ──

    # Map browser names to icon names (system theme or custom)
    _BROWSER_ICONS: dict[str, str] = {
        "Firefox": "firefox-symbolic",
        "Google Chrome": "google-chrome-symbolic",
        "Chromium": "chromium-browser-symbolic",
        "Brave": "web-browser-symbolic",
        "Vivaldi": "vivaldi-symbolic",
        "Microsoft Edge": "web-browser-symbolic",
        "Opera": "web-browser-symbolic",
    }

    def _build_browser_section(self, content: Gtk.Box) -> None:
        """Create the browser detection & configuration group."""
        from src.browser.browser_detect import find_all_profiles
        from src.browser.brave_config import is_brave_installed

        browser_group = Adw.PreferencesGroup()
        browser_group.set_title("Navegadores — Configuração para PJe")
        browser_group.set_description(
            "Registra o módulo PKCS#11 e importa o certificado do PJe Office "
            "nos navegadores detectados."
        )

        profiles = find_all_profiles()

        # Deduplicate by browser name (keep first)
        seen: dict[str, object] = {}
        for p in profiles:
            seen.setdefault(p.browser, p)

        if not seen:
            empty = Adw.ActionRow()
            empty.set_title("Nenhum navegador detectado")
            empty.set_icon_name("dialog-information-symbolic")
            browser_group.add(empty)
        else:
            for browser_name, profile in seen.items():
                row = Adw.ActionRow()
                row.set_title(browser_name)
                row.set_subtitle("Detectado")
                row.set_icon_name(
                    self._BROWSER_ICONS.get(browser_name, "web-browser-symbolic"),
                )

                icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                icon.add_css_class("success")
                row.add_suffix(icon)
                browser_group.add(row)

        # "Configure all" action row
        configure_row = Adw.ActionRow()
        configure_row.set_title("Configurar Navegadores para PJe Office")
        configure_row.set_subtitle(
            "Importa o certificado do PJe Office (localhost) em todos os navegadores"
        )
        configure_row.set_icon_name("emblem-system-symbolic")
        configure_row.set_activatable(True)
        self._browser_configure_row = configure_row
        configure_row.connect("activated", self._on_configure_all_browsers)

        self._browser_spinner = Gtk.Spinner()
        configure_row.add_suffix(self._browser_spinner)
        arrow_cfg = Gtk.Image.new_from_icon_name("go-next-symbolic")
        configure_row.add_suffix(arrow_cfg)
        browser_group.add(configure_row)

        # Brave Shields (only if Brave is installed)
        if is_brave_installed():
            self._brave_config_row = Adw.ActionRow()
            self._brave_config_row.set_title("Configurar Brave Shields para PJe")
            self._brave_config_row.set_subtitle(
                "Desativa Shields nos domínios judiciais para o PJe Office funcionar"
            )
            self._brave_config_row.set_icon_name("web-browser-symbolic")
            self._brave_config_row.set_activatable(True)
            self._brave_config_row.connect("activated", self._on_configure_brave)
            arrow_brave = Gtk.Image.new_from_icon_name("go-next-symbolic")
            self._brave_config_row.add_suffix(arrow_brave)
            browser_group.add(self._brave_config_row)

        # Status row (reused for both actions)
        self._browser_status_row = Adw.ActionRow()
        self._browser_status_row.set_visible(False)
        browser_group.add(self._browser_status_row)

        content.append(browser_group)

    # ── Browser action handlers ──

    def _on_configure_all_browsers(self, _row: Adw.ActionRow) -> None:
        """Import PJeOffice cert into all browsers' NSS databases."""
        import threading

        self._browser_configure_row.set_sensitive(False)
        self._browser_spinner.start()

        def work() -> None:
            from src.browser.brave_config import import_pjeoffice_cert_nss

            ok, msg = import_pjeoffice_cert_nss()
            GLib.idle_add(on_done, ok, msg)

        def on_done(success: bool, message: str) -> bool:
            self._browser_configure_row.set_sensitive(True)
            self._browser_spinner.stop()
            icon_name = "emblem-ok-symbolic" if success else "dialog-warning-symbolic"
            css_class = "success" if success else "warning"
            self._show_browser_status(message, icon_name, css_class)
            return False

        threading.Thread(target=work, daemon=True).start()

    def _on_configure_brave(self, _row: Adw.ActionRow) -> None:
        """Configure Brave Shields for PJe domains."""
        import threading
        from src.browser.brave_config import (
            configure_brave_shields,
            get_pje_domains,
            is_brave_running,
        )

        if is_brave_running():
            self._show_browser_status(
                "Feche o Brave completamente antes de configurar",
                "dialog-warning-symbolic",
                "warning",
            )
            return

        self._brave_config_row.set_sensitive(False)
        self._brave_config_row.set_subtitle("Configurando…")

        def configure_thread() -> None:
            domains = get_pje_domains()
            ok, msg = configure_brave_shields(domains)
            GLib.idle_add(on_done, ok, msg)

        def on_done(success: bool, message: str) -> bool:
            self._brave_config_row.set_sensitive(True)
            self._brave_config_row.set_subtitle(
                "Desativa Shields nos domínios judiciais para o PJe Office funcionar"
            )
            icon_name = "emblem-ok-symbolic" if success else "dialog-warning-symbolic"
            css_class = "success" if success else "warning"
            self._show_browser_status(message, icon_name, css_class)
            return False

        threading.Thread(target=configure_thread, daemon=True).start()

    def _show_browser_status(
        self, message: str, icon_name: str, css_class: str,
    ) -> None:
        """Show a status message in the browser config section."""
        self._browser_status_row.set_visible(True)
        self._browser_status_row.set_title(message)
        self._browser_status_row.set_icon_name(icon_name)

        for cls in ("success", "warning", "error", "accent"):
            self._browser_status_row.remove_css_class(cls)
        self._browser_status_row.add_css_class(css_class)
