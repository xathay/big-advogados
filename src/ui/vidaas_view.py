"""VidaaS Connect setup and management view.

Modern guided UI with progressive disclosure: welcome → setup → connected states.
Follows GNOME HIG with libadwaita components for a clean, intuitive experience.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from src.certificate.a3_manager import A3Manager
from src.certificate.vidaas_manager import VidaaSManager, VidaaSState, VidaaSMode
from src.utils.vidaas_deps import (
    DependencyStatus,
    check_dependencies,
    ensure_pcscd_running,
    get_missing_packages,
    install_packages,
    run_pcsc_scan,
)
from src.browser.nss_config import (
    is_browser_running,
    register_vidaas_in_all_browsers,
)

log = logging.getLogger(__name__)

# View states for progressive disclosure
_STATE_WELCOME = 0
_STATE_SETUP = 1
_STATE_CONNECTED = 2


class VidaaSView(Gtk.ScrolledWindow):
    """VidaaS Connect cloud certificate view with guided UX flow."""

    def __init__(self, a3_manager: A3Manager) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._a3_manager = a3_manager
        self._vidaas_manager = VidaaSManager(a3_manager)
        self._view_state = _STATE_WELCOME
        self._deps_ok = False

        # Main stack for state management
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(300)
        self.set_child(self._stack)

        self._build_welcome_page()
        self._build_setup_page()
        self._build_connected_page()

        self._stack.set_visible_child_name("welcome")

        # Reset to welcome whenever this view becomes visible
        self.connect("map", self._on_mapped)

    def _on_mapped(self, _widget: Gtk.Widget) -> None:
        """Reset to welcome page each time the view is shown."""
        self._go_to_state(_STATE_WELCOME)

    @property
    def vidaas_manager(self) -> VidaaSManager:
        return self._vidaas_manager

    # ── Welcome Page ──────────────────────────────────────────────────

    def _build_welcome_page(self) -> None:
        """Inviting welcome with clear call-to-action."""
        page = Adw.StatusPage()
        page.set_icon_name("network-wireless-symbolic")
        page.set_title("VidaaS Connect")
        page.set_description(
            "Certificado digital na nuvem.\n"
            "Use seu certificado A3 diretamente pelo celular, "
            "sem precisar de token USB físico."
        )

        btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)

        start_btn = Gtk.Button(label="Configurar VidaaS Connect")
        start_btn.add_css_class("suggested-action")
        start_btn.add_css_class("pill")
        start_btn.connect("clicked", self._on_start_setup)
        btn_box.append(start_btn)

        hint = Gtk.Label(
            label="Requer o app VidaaS Connect instalado no celular"
        )
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        btn_box.append(hint)

        page.set_child(btn_box)
        self._stack.add_named(page, "welcome")

    # ── Setup Page ────────────────────────────────────────────────────

    def _build_setup_page(self) -> None:
        """Guided setup split into tabs: Dependencies, Connection, Diagnostics."""
        setup_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # ViewStack for tab content
        self._setup_view_stack = Adw.ViewStack()

        # ViewSwitcher at the top
        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self._setup_view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)

        switcher_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        switcher_bar.set_margin_top(12)
        switcher_bar.set_margin_bottom(4)
        switcher_bar.set_halign(Gtk.Align.CENTER)
        switcher_bar.append(switcher)
        setup_box.append(switcher_bar)

        # Banner (shared across tabs, sits above content)
        self._setup_banner = Adw.Banner()
        self._setup_banner.set_revealed(False)
        setup_box.append(self._setup_banner)

        setup_box.append(self._setup_view_stack)
        self._setup_view_stack.set_vexpand(True)

        # Build each tab
        self._build_deps_tab()
        self._build_connection_tab()
        self._build_diag_tab()

        self._stack.add_named(setup_box, "setup")

    def _build_deps_tab(self) -> None:
        """Tab 1: System dependency check."""
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        inner.set_margin_top(24)
        inner.set_margin_bottom(24)
        inner.set_margin_start(16)
        inner.set_margin_end(16)

        self._deps_group = Adw.PreferencesGroup()
        self._deps_group.set_title("Pré-requisitos do sistema")
        self._deps_group.set_description(
            "Componentes necessários para comunicação com o token virtual"
        )
        inner.append(self._deps_group)

        self._dep_rows: dict[str, Adw.ActionRow] = {}
        dep_items = [
            ("opensc", "OpenSC", "Módulo PKCS#11 para tokens virtuais",
             "application-x-addon-symbolic"),
            ("pcscd", "Serviço PC/SC", "Daemon de comunicação com smart cards",
             "system-run-symbolic"),
            ("ccid", "Drivers CCID", "Suporte a leitores de smart cards",
             "drive-removable-media-symbolic"),
            ("pcscd_running", "Serviço ativo", "pcscd em execução",
             "media-playback-start-symbolic"),
        ]
        for key, title, subtitle, icon in dep_items:
            row = Adw.ActionRow()
            row.set_title(title)
            row.set_subtitle(subtitle)
            row.set_icon_name(icon)

            spinner = Gtk.Spinner()
            spinner.set_spinning(True)
            spinner.set_valign(Gtk.Align.CENTER)
            row.add_suffix(spinner)
            row._check_spinner = spinner  # type: ignore[attr-defined]

            status_icon = Gtk.Image()
            status_icon.set_valign(Gtk.Align.CENTER)
            status_icon.set_visible(False)
            row.add_suffix(status_icon)
            row._status_icon = status_icon  # type: ignore[attr-defined]

            self._dep_rows[key] = row
            self._deps_group.add(row)

        # Action buttons
        self._dep_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._dep_actions.set_halign(Gtk.Align.CENTER)
        self._dep_actions.set_margin_top(4)
        self._dep_actions.set_visible(False)

        self._install_deps_btn = Gtk.Button(label="Instalar pacotes faltantes")
        self._install_deps_btn.add_css_class("suggested-action")
        self._install_deps_btn.add_css_class("pill")
        self._install_deps_btn.connect("clicked", self._on_install_deps_clicked)
        self._dep_actions.append(self._install_deps_btn)

        self._start_pcscd_btn = Gtk.Button(label="Iniciar serviço")
        self._start_pcscd_btn.add_css_class("pill")
        self._start_pcscd_btn.set_visible(False)
        self._start_pcscd_btn.connect("clicked", self._on_start_pcscd_clicked)
        self._dep_actions.append(self._start_pcscd_btn)

        inner.append(self._dep_actions)

        clamp.set_child(inner)
        scroll.set_child(clamp)
        page = self._setup_view_stack.add_titled(scroll, "deps", "Dependências")
        page.set_icon_name("application-x-addon-symbolic")

    def _build_connection_tab(self) -> None:
        """Tab 2: Token detection and connection."""
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        inner.set_margin_top(24)
        inner.set_margin_bottom(24)
        inner.set_margin_start(16)
        inner.set_margin_end(16)

        self._detect_group = Adw.PreferencesGroup()
        self._detect_group.set_title("Conectar ao VidaaS")
        self._detect_group.set_description(
            "Abra o app VidaaS no celular e toque em conectar"
        )
        self._detect_group.set_sensitive(False)
        inner.append(self._detect_group)

        self._token_row = Adw.ActionRow()
        self._token_row.set_title("Aguardando detecção")
        self._token_row.set_subtitle(
            "O token virtual será detectado automaticamente via OpenSC"
        )
        self._token_row.set_icon_name("network-wireless-acquiring-symbolic")
        self._detect_group.add(self._token_row)

        detect_btn_box = Gtk.Box(spacing=12)
        detect_btn_box.set_halign(Gtk.Align.CENTER)
        detect_btn_box.set_margin_top(4)

        self._detect_btn = Gtk.Button(label="Detectar token VidaaS")
        self._detect_btn.add_css_class("suggested-action")
        self._detect_btn.add_css_class("pill")
        self._detect_btn.set_sensitive(False)
        self._detect_btn.connect("clicked", self._on_detect_clicked)
        detect_btn_box.append(self._detect_btn)

        self._detect_spinner = Gtk.Spinner()
        self._detect_spinner.set_valign(Gtk.Align.CENTER)
        self._detect_spinner.set_visible(False)
        detect_btn_box.append(self._detect_spinner)

        inner.append(detect_btn_box)

        clamp.set_child(inner)
        scroll.set_child(clamp)
        page = self._setup_view_stack.add_titled(scroll, "connection", "Conexão")
        page.set_icon_name("network-wireless-symbolic")

    def _build_diag_tab(self) -> None:
        """Tab 3: Diagnostics and troubleshooting."""
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        inner.set_margin_top(24)
        inner.set_margin_bottom(24)
        inner.set_margin_start(16)
        inner.set_margin_end(16)

        diag_group = Adw.PreferencesGroup()
        diag_group.set_title("Diagnóstico avançado")
        diag_group.set_description("Ferramentas para solução de problemas")
        inner.append(diag_group)

        diag_scan_row = Adw.ActionRow()
        diag_scan_row.set_title("Escanear leitores PC/SC")
        diag_scan_row.set_subtitle("Executa pcsc_scan para listar dispositivos")
        diag_scan_row.set_icon_name("system-search-symbolic")
        diag_scan_row.set_activatable(True)
        diag_scan_row.connect("activated", self._on_diag_clicked)

        self._diag_scan_btn = Gtk.Button()
        self._diag_scan_btn.set_icon_name("media-playback-start-symbolic")
        self._diag_scan_btn.set_tooltip_text("Executar pcsc_scan")
        self._diag_scan_btn.set_valign(Gtk.Align.CENTER)
        self._diag_scan_btn.add_css_class("flat")
        self._diag_scan_btn.connect("clicked", self._on_diag_clicked)
        diag_scan_row.add_suffix(self._diag_scan_btn)
        diag_group.add(diag_scan_row)

        # Diagnostics output
        self._diag_frame = Gtk.Frame()
        self._diag_frame.set_visible(False)
        self._diag_frame.set_margin_top(8)
        self._diag_frame.add_css_class("card")

        diag_scroll = Gtk.ScrolledWindow()
        diag_scroll.set_min_content_height(120)
        diag_scroll.set_max_content_height(250)
        diag_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self._diag_text = Gtk.Label()
        self._diag_text.set_wrap(True)
        self._diag_text.set_selectable(True)
        self._diag_text.add_css_class("monospace")
        self._diag_text.add_css_class("dim-label")
        self._diag_text.set_halign(Gtk.Align.START)
        self._diag_text.set_valign(Gtk.Align.START)
        self._diag_text.set_margin_top(12)
        self._diag_text.set_margin_bottom(12)
        self._diag_text.set_margin_start(12)
        self._diag_text.set_margin_end(12)
        diag_scroll.set_child(self._diag_text)
        self._diag_frame.set_child(diag_scroll)
        inner.append(self._diag_frame)

        clamp.set_child(inner)
        scroll.set_child(clamp)
        page = self._setup_view_stack.add_titled(scroll, "diag", "Diagnóstico")
        page.set_icon_name("utilities-terminal-symbolic")

    # ── Connected Page ────────────────────────────────────────────────

    def _build_connected_page(self) -> None:
        """Success state showing certificates, browser config, and actions."""
        scroll_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        inner.set_margin_top(24)
        inner.set_margin_bottom(24)
        inner.set_margin_start(16)
        inner.set_margin_end(16)

        # ── Success header card ──
        self._success_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._success_card.add_css_class("card")
        self._success_card.set_margin_bottom(4)

        success_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        success_inner.set_margin_top(20)
        success_inner.set_margin_bottom(20)
        success_inner.set_margin_start(20)
        success_inner.set_margin_end(20)

        success_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        success_icon.set_pixel_size(48)
        success_icon.add_css_class("success")
        success_inner.append(success_icon)

        success_title = Gtk.Label(label="VidaaS conectado")
        success_title.add_css_class("title-2")
        success_inner.append(success_title)

        self._connected_subtitle = Gtk.Label()
        self._connected_subtitle.add_css_class("dim-label")
        self._connected_subtitle.set_wrap(True)
        self._connected_subtitle.set_justify(Gtk.Justification.CENTER)
        success_inner.append(self._connected_subtitle)

        self._success_card.append(success_inner)
        inner.append(self._success_card)

        # ── Banner for browser warnings ──
        self._connected_banner = Adw.Banner()
        self._connected_banner.set_revealed(False)
        inner.append(self._connected_banner)

        # ── Certificates group ──
        self._cert_group = Adw.PreferencesGroup()
        self._cert_group.set_title("Seus certificados na nuvem")
        self._cert_group.set_description(
            "Certificados disponíveis no token VidaaS"
        )
        inner.append(self._cert_group)

        # ── Browser registration group ──
        self._browser_group = Adw.PreferencesGroup()
        self._browser_group.set_title("Configurar navegadores")
        self._browser_group.set_description(
            "Registre o módulo PKCS#11 para usar o certificado nos sites dos tribunais"
        )
        inner.append(self._browser_group)

        self._register_btn = Gtk.Button(label="Configurar todos os navegadores")
        self._register_btn.add_css_class("suggested-action")
        self._register_btn.add_css_class("pill")
        self._register_btn.set_halign(Gtk.Align.CENTER)
        self._register_btn.connect("clicked", self._on_register_browsers_clicked)

        self._register_spinner = Gtk.Spinner()
        self._register_spinner.set_valign(Gtk.Align.CENTER)
        self._register_spinner.set_visible(False)

        reg_box = Gtk.Box(spacing=8)
        reg_box.set_halign(Gtk.Align.CENTER)
        reg_box.append(self._register_btn)
        reg_box.append(self._register_spinner)
        inner.append(reg_box)

        # ── Disconnect button ──
        self._disconnect_btn = Gtk.Button(label="Desconectar")
        self._disconnect_btn.add_css_class("pill")
        self._disconnect_btn.set_halign(Gtk.Align.CENTER)
        self._disconnect_btn.set_margin_top(8)
        self._disconnect_btn.connect("clicked", self._on_disconnect_clicked)
        inner.append(self._disconnect_btn)

        clamp.set_child(inner)
        scroll_content.append(clamp)
        self._stack.add_named(scroll_content, "connected")

    # ── Helpers ────────────────────────────────────────────────────────

    def _go_to_state(self, state: int) -> None:
        """Transition to a view state."""
        self._view_state = state
        if state == _STATE_WELCOME:
            self._stack.set_visible_child_name("welcome")
        elif state == _STATE_SETUP:
            self._stack.set_visible_child_name("setup")
            self._check_dependencies()
        elif state == _STATE_CONNECTED:
            self._stack.set_visible_child_name("connected")

    def _update_dep_row(self, key: str, ok: bool, detail: str) -> None:
        """Update a dependency row with result status."""
        row = self._dep_rows[key]
        row._check_spinner.set_spinning(False)  # type: ignore[attr-defined]
        row._check_spinner.set_visible(False)  # type: ignore[attr-defined]

        icon: Gtk.Image = row._status_icon  # type: ignore[attr-defined]
        icon.set_visible(True)
        if ok:
            icon.set_from_icon_name("emblem-ok-symbolic")
            icon.add_css_class("success")
            icon.remove_css_class("warning")
            icon.remove_css_class("error")
        else:
            icon.set_from_icon_name("dialog-warning-symbolic")
            icon.add_css_class("warning")
            icon.remove_css_class("success")
            icon.remove_css_class("error")
        row.set_subtitle(detail)

    def _reset_dep_spinners(self) -> None:
        """Reset all dep rows to loading state."""
        for row in self._dep_rows.values():
            row._check_spinner.set_spinning(True)  # type: ignore[attr-defined]
            row._check_spinner.set_visible(True)  # type: ignore[attr-defined]
            row._status_icon.set_visible(False)  # type: ignore[attr-defined]

    def _clear_group_children(self, group: Adw.PreferencesGroup) -> None:
        """Remove all children from a PreferencesGroup."""
        while True:
            child = group.get_first_child()
            if child is None:
                break
            # PreferencesGroup wraps children — walk to the actual row
            if hasattr(child, 'get_first_child'):
                inner = child.get_first_child()
                if inner and hasattr(inner, 'get_first_child'):
                    row = inner.get_first_child()
                    if row and isinstance(row, (Adw.ActionRow, Adw.ExpanderRow)):
                        group.remove(row)
                        continue
            group.remove(child)

    # ── Actions: Welcome ──────────────────────────────────────────────

    def _on_start_setup(self, _btn: Gtk.Button) -> None:
        self._go_to_state(_STATE_SETUP)

    # ── Actions: Dependency Check ─────────────────────────────────────

    def _check_dependencies(self) -> bool:
        """Run dependency check in background."""
        self._reset_dep_spinners()
        self._dep_actions.set_visible(False)
        self._setup_banner.set_revealed(False)

        def check_thread() -> None:
            status = check_dependencies()
            missing = get_missing_packages()
            GLib.idle_add(self._on_deps_checked, status, missing)

        threading.Thread(target=check_thread, daemon=True).start()
        return False

    def _on_deps_checked(
        self,
        status: DependencyStatus,
        missing: list[str],
    ) -> bool:
        """Update UI with dependency check results."""
        self._update_dep_row(
            "opensc", status.opensc_installed,
            "Instalado" if status.opensc_installed else "Não encontrado — necessário",
        )
        self._update_dep_row(
            "pcscd", status.pcscd_installed,
            "Instalado" if status.pcscd_installed else "Não encontrado — necessário",
        )
        self._update_dep_row(
            "ccid", status.ccid_installed,
            "Instalado" if status.ccid_installed else "Não encontrado — necessário",
        )
        self._update_dep_row(
            "pcscd_running", status.pcscd_running,
            "Em execução" if status.pcscd_running else "Serviço parado",
        )

        has_missing = len(missing) > 0
        needs_start = status.pcscd_installed and not status.pcscd_running

        self._install_deps_btn.set_visible(has_missing)
        self._start_pcscd_btn.set_visible(needs_start and not has_missing)
        self._dep_actions.set_visible(has_missing or needs_start)

        all_ok = (
            status.opensc_installed
            and status.pcscd_installed
            and status.ccid_installed
            and status.pcscd_running
        )
        self._deps_ok = all_ok

        # Enable connection tab when deps are OK
        self._detect_group.set_sensitive(all_ok)
        self._detect_btn.set_sensitive(all_ok)
        if all_ok:
            self._setup_view_stack.set_visible_child_name("connection")

        if has_missing:
            self._setup_banner.set_title(
                f"Pacotes faltando: {', '.join(missing)}"
            )
            self._setup_banner.set_revealed(True)
        elif needs_start:
            self._setup_banner.set_title(
                "Tudo instalado — inicie o serviço pcscd para continuar"
            )
            self._setup_banner.set_revealed(True)
        else:
            self._setup_banner.set_revealed(False)

        return False

    def _on_install_deps_clicked(self, _btn: Gtk.Button) -> None:
        """Install missing system packages."""
        missing = get_missing_packages()
        if not missing:
            return

        self._install_deps_btn.set_sensitive(False)
        self._install_deps_btn.set_label("Instalando…")

        def install_thread() -> None:
            success, msg = install_packages(missing)
            GLib.idle_add(on_done, success, msg)

        def on_done(success: bool, msg: str) -> bool:
            self._install_deps_btn.set_sensitive(True)
            if success:
                self._install_deps_btn.set_label("Instalado!")
                self._check_dependencies()
            else:
                self._install_deps_btn.set_label("Falha — tentar novamente")
                log.error("Package install failed: %s", msg)
            return False

        threading.Thread(target=install_thread, daemon=True).start()

    def _on_start_pcscd_clicked(self, _btn: Gtk.Button) -> None:
        """Start the pcscd service."""
        self._start_pcscd_btn.set_sensitive(False)
        self._start_pcscd_btn.set_label("Iniciando…")

        def start_thread() -> None:
            ok = ensure_pcscd_running()
            GLib.idle_add(on_done, ok)

        def on_done(ok: bool) -> bool:
            self._start_pcscd_btn.set_sensitive(True)
            self._start_pcscd_btn.set_label("Iniciar serviço")
            self._check_dependencies()
            return False

        threading.Thread(target=start_thread, daemon=True).start()

    # ── Actions: Token Detection ──────────────────────────────────────

    def _on_detect_clicked(self, _btn: Gtk.Button) -> None:
        """Detect VidaaS virtual token."""
        self._detect_btn.set_sensitive(False)
        self._detect_btn.set_label("Buscando…")
        self._detect_spinner.set_visible(True)
        self._detect_spinner.set_spinning(True)

        self._token_row.set_title("Buscando token VidaaS…")
        self._token_row.set_subtitle("Verificando slots PKCS#11 via OpenSC")
        self._token_row.set_icon_name("content-loading-symbolic")

        vidaas = self._vidaas_manager

        def detect_thread() -> None:
            status = vidaas.detect_vidaas_token()
            GLib.idle_add(on_done, status)

        def on_done(status) -> bool:  # type: ignore[no-untyped-def]
            self._detect_btn.set_sensitive(True)
            self._detect_btn.set_label("Detectar token VidaaS")
            self._detect_spinner.set_spinning(False)
            self._detect_spinner.set_visible(False)

            if status.state == VidaaSState.CONNECTED:
                self._populate_connected_page(status.slot_label)
                self._go_to_state(_STATE_CONNECTED)
            else:
                self._token_row.set_title("Token não encontrado")
                self._token_row.set_subtitle(
                    status.message or "Verifique se o app VidaaS está aberto no celular"
                )
                self._token_row.set_icon_name("dialog-warning-symbolic")
            return False

        threading.Thread(target=detect_thread, daemon=True).start()

    # ── Connected Page Logic ──────────────────────────────────────────

    def _populate_connected_page(self, slot_label: str = "") -> None:
        """Fill the connected page with certificates and status."""
        self._connected_subtitle.set_label(
            f"Token virtual conectado{' — ' + slot_label if slot_label else ''}"
        )
        self._show_certificates()

    def _show_certificates(self) -> None:
        """Show certificates from the connected VidaaS token."""
        certs = self._vidaas_manager.list_certificates()

        # Remove existing rows by iterating safely
        rows_to_remove: list[Gtk.Widget] = []
        child = self._cert_group.get_first_child()
        while child:
            # Walk the internal GtkListBox structure
            next_c = child.get_next_sibling()
            rows_to_remove.append(child)
            child = next_c
        for c in rows_to_remove:
            try:
                self._cert_group.remove(c)
            except Exception:
                pass

        if not certs:
            empty_row = Adw.ActionRow()
            empty_row.set_title("Nenhum certificado encontrado")
            empty_row.set_subtitle("O token pode estar vazio ou não autorizado")
            empty_row.set_icon_name("dialog-information-symbolic")
            self._cert_group.add(empty_row)
            return

        for cert in certs:
            expander = Adw.ExpanderRow()
            holder = cert.holder_name or cert.common_name or "Certificado"
            expander.set_title(holder)
            expander.set_show_enable_switch(False)

            # Subtitle with key info
            parts: list[str] = []
            if cert.cpf:
                parts.append(f"CPF: {cert.cpf}")
            if cert.oab:
                parts.append(f"OAB: {cert.oab}")
            expander.set_subtitle(" · ".join(parts) if parts else "")

            # Status icon based on validity
            if cert.is_expired:
                expander.set_icon_name("dialog-error-symbolic")
            elif cert.days_to_expire <= 30:
                expander.set_icon_name("dialog-warning-symbolic")
            else:
                expander.set_icon_name("application-certificate-symbolic")

            # Expanded details
            if cert.issuer_cn:
                ca_row = Adw.ActionRow()
                ca_row.set_title("Autoridade Certificadora")
                ca_row.set_subtitle(cert.issuer_cn)
                ca_row.set_icon_name("system-users-symbolic")
                expander.add_row(ca_row)

            if cert.not_after:
                valid_row = Adw.ActionRow()
                valid_row.set_title("Validade")
                expire_text = cert.not_after.strftime("%d/%m/%Y")
                if cert.is_expired:
                    valid_row.set_subtitle(f"Expirado em {expire_text}")
                    valid_row.set_icon_name("dialog-error-symbolic")
                elif cert.days_to_expire <= 30:
                    valid_row.set_subtitle(
                        f"Expira em {cert.days_to_expire} dias ({expire_text})"
                    )
                    valid_row.set_icon_name("dialog-warning-symbolic")
                else:
                    valid_row.set_subtitle(
                        f"Válido até {expire_text} "
                        f"({cert.days_to_expire} dias restantes)"
                    )
                    valid_row.set_icon_name("emblem-ok-symbolic")
                expander.add_row(valid_row)

            if cert.serial_number:
                sn_row = Adw.ActionRow()
                sn_row.set_title("Número de série")
                sn_row.set_subtitle(cert.serial_number)
                sn_row.set_icon_name("dialog-information-symbolic")
                expander.add_row(sn_row)

            if cert.email:
                email_row = Adw.ActionRow()
                email_row.set_title("E-mail")
                email_row.set_subtitle(cert.email)
                email_row.set_icon_name("mail-unread-symbolic")
                expander.add_row(email_row)

            self._cert_group.add(expander)

    def _on_register_browsers_clicked(self, _btn: Gtk.Button) -> None:
        """Register VidaaS PKCS#11 module in all browsers."""
        self._register_btn.set_sensitive(False)
        self._register_btn.set_label("Configurando…")
        self._register_spinner.set_visible(True)
        self._register_spinner.set_spinning(True)

        # Remove old result rows from browser group
        rows_to_remove: list[Gtk.Widget] = []
        child = self._browser_group.get_first_child()
        while child:
            next_c = child.get_next_sibling()
            rows_to_remove.append(child)
            child = next_c
        for c in rows_to_remove:
            try:
                self._browser_group.remove(c)
            except Exception:
                pass

        def register_thread() -> None:
            running: list[str] = []
            for name in ("Firefox", "Google Chrome", "Chromium",
                         "Brave", "Vivaldi", "Microsoft Edge"):
                if is_browser_running(name):
                    running.append(name)
            results = register_vidaas_in_all_browsers()
            GLib.idle_add(on_done, results, running)

        def on_done(
            results: dict[str, bool],
            running: list[str],
        ) -> bool:
            self._register_btn.set_sensitive(True)
            self._register_btn.set_label("Configurar todos os navegadores")
            self._register_spinner.set_spinning(False)
            self._register_spinner.set_visible(False)

            if running:
                self._connected_banner.set_title(
                    f"Feche antes: {', '.join(running)} — "
                    "pode ser necessário reconfigurar"
                )
                self._connected_banner.set_revealed(True)
            else:
                self._connected_banner.set_revealed(False)

            for label, success in results.items():
                row = Adw.ActionRow()
                row.set_title(label)
                if success:
                    row.set_icon_name("emblem-ok-symbolic")
                    row.set_subtitle("Módulo registrado")

                    ok_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                    ok_icon.add_css_class("success")
                    ok_icon.set_valign(Gtk.Align.CENTER)
                    row.add_suffix(ok_icon)
                else:
                    row.set_icon_name("dialog-error-symbolic")
                    row.set_subtitle("Falha no registro")

                    err_icon = Gtk.Image.new_from_icon_name("process-stop-symbolic")
                    err_icon.add_css_class("error")
                    err_icon.set_valign(Gtk.Align.CENTER)
                    row.add_suffix(err_icon)

                self._browser_group.add(row)
            return False

        threading.Thread(target=register_thread, daemon=True).start()

    def _on_disconnect_clicked(self, _btn: Gtk.Button) -> None:
        """Disconnect from VidaaS and return to setup."""
        self._vidaas_manager.disconnect()
        self._token_row.set_title("Aguardando detecção")
        self._token_row.set_subtitle(
            "O token virtual será detectado automaticamente via OpenSC"
        )
        self._token_row.set_icon_name("network-wireless-acquiring-symbolic")
        self._connected_banner.set_revealed(False)
        self._go_to_state(_STATE_SETUP)

    # ── Diagnostics ───────────────────────────────────────────────────

    def _on_diag_clicked(self, _widget: Gtk.Widget) -> None:
        """Run pcsc_scan diagnostics."""
        self._diag_frame.set_visible(True)
        self._diag_text.set_label("Executando pcsc_scan…")
        self._diag_scan_btn.set_sensitive(False)

        def diag_thread() -> None:
            output = run_pcsc_scan(timeout=5)
            GLib.idle_add(on_done, output)

        def on_done(output: str) -> bool:
            self._diag_text.set_label(output[:3000] if output else "Sem saída")
            self._diag_scan_btn.set_sensitive(True)
            return False

        threading.Thread(target=diag_thread, daemon=True).start()
