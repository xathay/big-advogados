"""Main application window."""

from __future__ import annotations

import logging
import threading
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, GObject  # noqa: E402

from src.certificate.a3_manager import A3Manager
from src.certificate.token_database import TokenDatabase
from src.ui.dashboard_view import DashboardView
from src.ui.unified_certificates_view import UnifiedCertificatesView
from src.ui.systems_view import SystemsView
from src.ui.signer_view import SignerView
from src.ui.vidaas_view import VidaaSView
from src.ui.pin_dialog import PinDialog
from src.ui.lock_screen import LockDialog
from src.utils.udev_monitor import UdevMonitor
from src.utils.app_lock import is_lock_enabled
from src.browser.nss_config import register_in_all_browsers, is_nss_tools_available

log = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """Main application window with navigation between views."""

    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application)

        self.set_title("BigCertificados")
        self.set_default_size(800, 600)
        self.set_size_request(360, 400)

        # Core objects
        self._token_db = TokenDatabase()
        self._a3_manager = A3Manager(self._token_db)
        self._udev_monitor = UdevMonitor(self._token_db)

        self._unlocked = False

        # Build UI
        self._build_ui()

        # Connect udev events
        self._udev_monitor.connect(self._on_usb_event)

        # If lock is enabled, show lock screen first; otherwise unlock immediately
        if is_lock_enabled():
            self._show_lock()
        else:
            self._unlock()

    # ── Sidebar navigation definition ──
    _SIDEBAR_ITEMS: list[tuple[str, str, str, str | None]] = [
        # (view_id, label, icon, category_header_or_None)
        ("home", "Início", "go-home-symbolic", None),
        ("certificates", "Certificados", "application-certificate-symbolic", "Certificados"),
        ("vidaas", "VidaaS Connect", "network-wireless-symbolic", None),
        ("signer", "Assinador de PDFs", "document-edit-symbolic", "Ferramentas"),
        ("systems", "Sistemas Judiciais", "preferences-system-network-symbolic", None),
        ("deps", "Dependências", "dialog-information-symbolic", "Configuração"),
        ("browsers", "Navegadores", "web-browser-symbolic", None),
    ]

    def _build_ui(self) -> None:
        # ── Main layout: ToolbarView → NavigationSplitView ──
        toolbar_view = Adw.ToolbarView()

        # Header bar
        header = Adw.HeaderBar()

        # Title (updated on sidebar selection)
        self._header_title = Adw.WindowTitle()
        self._header_title.set_title("BigCertificados")
        header.set_title_widget(self._header_title)

        # Sidebar toggle button (visible only when collapsed)
        self._sidebar_button = Gtk.ToggleButton()
        self._sidebar_button.set_icon_name("sidebar-show-symbolic")
        self._sidebar_button.set_tooltip_text("Barra lateral")
        self._sidebar_button.set_visible(False)
        header.pack_start(self._sidebar_button)

        # Search button
        self._search_button = Gtk.ToggleButton()
        self._search_button.set_icon_name("system-search-symbolic")
        self._search_button.set_tooltip_text("Buscar (Ctrl+F)")
        header.pack_start(self._search_button)

        # Menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text("Menu")

        menu = Gio.Menu()
        menu.append("Proteção por Senha", "app.password-settings")
        menu.append("Sobre", "app.about")

        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

        toolbar_view.add_top_bar(header)

        # ── Search bar ──
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_hexpand(True)
        self._search_entry.set_placeholder_text("Buscar em todo o aplicativo…")

        self._search_bar = Gtk.SearchBar()
        self._search_bar.set_child(self._search_entry)
        self._search_bar.connect_entry(self._search_entry)
        self._search_bar.set_key_capture_widget(None)

        self._search_button.bind_property(
            "active", self._search_bar, "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )

        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_entry.connect("stop-search", self._on_stop_search)

        toolbar_view.add_top_bar(self._search_bar)

        # ── Search results view ──
        self._search_results_list = Gtk.ListBox()
        self._search_results_list.add_css_class("boxed-list")
        self._search_results_list.set_selection_mode(Gtk.SelectionMode.NONE)

        search_clamp = Adw.Clamp()
        search_clamp.set_maximum_size(600)
        search_clamp.set_tightening_threshold(400)

        search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        search_box.set_margin_top(12)
        search_box.set_margin_bottom(12)
        search_box.set_margin_start(12)
        search_box.set_margin_end(12)
        search_box.append(self._search_results_list)
        search_clamp.set_child(search_box)

        search_scroll = Gtk.ScrolledWindow()
        search_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        search_scroll.set_child(search_clamp)

        # ── Views ──
        self._dashboard = DashboardView(navigate_to=self._navigate_to)

        self._certs_view = UnifiedCertificatesView(self._token_db)
        self._certs_view.token_view.emit_scan_request = self._do_scan

        self._systems_view = SystemsView()
        self._signer_view = SignerView(a3_manager=self._a3_manager)
        self._vidaas_view = VidaaSView(self._a3_manager)

        # Config pages (promoted from menu to sidebar)
        self._deps_page = self._build_deps_page()
        self._browsers_page = self._build_browsers_page()

        # ── View stack (internal navigation) ──
        self._view_stack = Gtk.Stack()
        self._view_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._view_stack.set_transition_duration(200)
        self._view_stack.set_hexpand(True)
        self._view_stack.set_vexpand(True)

        self._view_stack.add_named(self._dashboard, "home")
        self._view_stack.add_named(self._certs_view, "certificates")
        self._view_stack.add_named(self._vidaas_view, "vidaas")
        self._view_stack.add_named(self._signer_view, "signer")
        self._view_stack.add_named(self._systems_view, "systems")
        self._view_stack.add_named(self._deps_page, "deps")
        self._view_stack.add_named(self._browsers_page, "browsers")

        # ── Content stack: views vs search ──
        self._content_stack = Gtk.Stack()
        self._content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._content_stack.add_named(self._view_stack, "views")
        self._content_stack.add_named(search_scroll, "search")

        # ── Sidebar (categorized ListBox) ──
        self._sidebar_list = Gtk.ListBox()
        self._sidebar_list.add_css_class("navigation-sidebar")
        self._sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._sidebar_rows: dict[str, Gtk.ListBoxRow] = {}

        current_category: str | None = None
        for view_id, label, icon_name, category in self._SIDEBAR_ITEMS:
            if category and category != current_category:
                current_category = category
                sep_row = Gtk.ListBoxRow()
                sep_row.set_selectable(False)
                sep_row.set_activatable(False)
                sep_label = Gtk.Label(label=category)
                sep_label.add_css_class("caption-heading")
                sep_label.add_css_class("dim-label")
                sep_label.set_xalign(0)
                sep_label.set_margin_start(12)
                sep_label.set_margin_top(12 if view_id != "certificates" else 4)
                sep_label.set_margin_bottom(4)
                sep_row.set_child(sep_label)
                self._sidebar_list.append(sep_row)

            row = Gtk.ListBoxRow()
            row._view_id = view_id  # noqa: SLF001
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_margin_top(6)
            hbox.set_margin_bottom(6)
            hbox.set_margin_start(10)
            hbox.set_margin_end(10)
            hbox.append(Gtk.Image.new_from_icon_name(icon_name))
            lbl = Gtk.Label(label=label)
            lbl.set_xalign(0)
            lbl.set_hexpand(True)
            hbox.append(lbl)
            row.set_child(hbox)
            self._sidebar_list.append(row)
            self._sidebar_rows[view_id] = row

        self._sidebar_list.connect("row-selected", self._on_sidebar_selected)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_child(self._sidebar_list)
        sidebar_scroll.set_size_request(200, -1)

        # ── NavigationSplitView ──
        sidebar_page = Adw.NavigationPage.new(sidebar_scroll, "Navegação")
        content_page = Adw.NavigationPage.new(self._content_stack, "Conteúdo")

        self._split_view = Adw.NavigationSplitView()
        self._split_view.set_sidebar(sidebar_page)
        self._split_view.set_content(content_page)
        self._split_view.set_min_sidebar_width(200)
        self._split_view.set_max_sidebar_width(260)

        self._split_view.connect("notify::collapsed", self._on_split_collapsed)
        self._sidebar_button.connect("toggled", self._on_sidebar_toggle)

        # Toast overlay
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self._split_view)
        toolbar_view.set_content(self._toast_overlay)

        self.set_content(toolbar_view)

        self._search_bar.set_key_capture_widget(self)

        # Select home row initially
        first_row = self._sidebar_rows.get("home")
        if first_row:
            self._sidebar_list.select_row(first_row)

        # Wire up token row activation
        for row in self._certs_view.token_view._token_rows.values():
            row.connect("activated", self._on_token_row_activated)

    # ── Sidebar callbacks ──

    def _on_sidebar_selected(
        self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None,
    ) -> None:
        if not row or not hasattr(row, "_view_id"):
            return
        view_id: str = row._view_id  # noqa: SLF001

        self._view_stack.set_visible_child_name(view_id)
        self._content_stack.set_visible_child_name("views")

        for vid, label, _icon, _cat in self._SIDEBAR_ITEMS:
            if vid == view_id:
                self._header_title.set_title(label)
                break

        if self._split_view.get_collapsed():
            self._split_view.set_show_content(True)

    def _on_split_collapsed(
        self, split_view: Adw.NavigationSplitView, _pspec: object,
    ) -> None:
        collapsed = split_view.get_collapsed()
        self._sidebar_button.set_visible(collapsed)
        if not collapsed:
            self._sidebar_button.set_active(False)

    def _on_sidebar_toggle(self, button: Gtk.ToggleButton) -> None:
        if self._split_view.get_collapsed():
            self._split_view.set_show_content(not button.get_active())

    # ── Promoted config pages ──

    def _build_deps_page(self) -> Gtk.ScrolledWindow:
        """Dependências page — triggers the existing check-deps action."""
        status = Adw.StatusPage()
        status.set_icon_name("dialog-information-symbolic")
        status.set_title("Dependências do Sistema")
        status.set_description(
            "Verifique e instale os pacotes, módulos Python e serviços "
            "necessários para o funcionamento completo do BigCertificados."
        )
        btn = Gtk.Button(label="Verificar Dependências")
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect(
            "clicked",
            lambda _b: self.get_application().activate_action("check-deps", None),
        )
        status.set_child(btn)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(status)
        return scroll

    def _build_browsers_page(self) -> Gtk.ScrolledWindow:
        """Navegadores page — triggers the existing setup-browsers action."""
        status = Adw.StatusPage()
        status.set_icon_name("web-browser-symbolic")
        status.set_title("Configuração de Navegadores")
        status.set_description(
            "Registre o módulo PKCS#11 nos navegadores detectados "
            "para que reconheçam seu certificado digital automaticamente."
        )
        btn = Gtk.Button(label="Configurar Navegadores")
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect(
            "clicked",
            lambda _b: self.get_application().activate_action("setup-browsers", None),
        )
        status.set_child(btn)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(status)
        return scroll

    # ── Search ──

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        text = entry.get_text().strip().lower()
        if not text:
            self._content_stack.set_visible_child_name("views")
            return

        self._content_stack.set_visible_child_name("search")
        self._populate_search_results(text)

    def _on_stop_search(self, _entry: Gtk.SearchEntry) -> None:
        self._search_button.set_active(False)
        self._content_stack.set_visible_child_name("views")

    def _navigate_to(self, tab_id: str, sidebar_id: str | None = None) -> None:
        """Close search and navigate to *tab_id*, optionally selecting a sidebar item."""
        self._search_button.set_active(False)
        self._content_stack.set_visible_child_name("views")

        # Select the sidebar row (which triggers _on_sidebar_selected)
        row = self._sidebar_rows.get(tab_id)
        if row:
            self._sidebar_list.select_row(row)

        if sidebar_id and tab_id == "systems":
            self._systems_view.select_section(sidebar_id)

    def _add_result(
        self, title: str, subtitle: str, icon: str,
        *, tab: str | None = None, sidebar: str | None = None,
        url: str | None = None, action: str | None = None,
    ) -> None:
        """Append one search result row."""
        row = Adw.ActionRow()
        row.set_title(title)
        row.set_subtitle(subtitle)
        row.set_icon_name(icon)
        row.set_activatable(True)
        arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
        row.add_suffix(arrow)

        if url:
            row.connect(
                "activated",
                lambda _r, u=url: Gio.AppInfo.launch_default_for_uri(u, None),
            )
        elif action:
            row.connect(
                "activated",
                lambda _r, a=action: self.get_application().activate_action(
                    a.removeprefix("app."), None),
            )
        elif tab:
            row.connect(
                "activated",
                lambda _r, t=tab, s=sidebar: self._navigate_to(t, s),
            )

        self._search_results_list.append(row)

    def _populate_search_results(self, text: str) -> None:
        # Clear previous results
        while True:
            child = self._search_results_list.get_first_child()
            if child is None:
                break
            self._search_results_list.remove(child)

        def _match(*haystack: str) -> bool:
            return any(text in h.lower() for h in haystack)

        # ── 1. Navigation & quick actions ──
        nav = [
            ("Início", "Painel de visão geral e ações rápidas",
             "go-home-symbolic",
             "início home dashboard painel visão geral",
             "home", None, None),
            ("Certificados A1 e A3", "Gerenciar certificados digitais",
             "application-certificate-symbolic",
             "certificado a1 a3 token pfx importar gerenciar",
             "certificates", None, None),
            ("Assinador de PDF", "Assinar documentos digitalmente",
             "document-edit-symbolic",
             "assinar assinador pdf documento assinatura digital",
             "signer", None, None),
            ("VidaaS Connect", "Certificado digital em nuvem",
             "network-wireless-symbolic",
             "vidaas nuvem cloud connect certificado",
             "vidaas", None, None),
            ("PJeOffice Pro", "Instalar, remover ou atualizar o PJeOffice",
             "applications-office-symbolic",
             "pjeoffice pje assinador instalar atualizar cnj",
             "systems", "pjeoffice", None),
            ("Drivers &amp; Tokens", "Drivers para tokens criptográficos",
             "dialog-password-symbolic",
             "driver token pkcs11 middleware smartcard leitora",
             "systems", "drivers", None),
            ("Navegadores", "Configurar navegadores para PJe Office",
             "web-browser-symbolic",
             "navegador browser firefox chrome brave edge nss configurar",
             "systems", "browsers", None),
        ]
        for title, sub, icon, kw, tab, sidebar, _ in nav:
            if _match(title, sub, kw):
                self._add_result(title, sub, icon, tab=tab, sidebar=sidebar)

        # Menu actions
        actions = [
            ("Proteção por Senha", "Configurar senha de acesso ao aplicativo",
             "dialog-password-symbolic", "senha password proteção segurança lock",
             "app.password-settings"),
            ("Configurar Navegadores", "Registrar módulo PKCS#11 nos navegadores",
             "emblem-system-symbolic", "configurar navegador browser pkcs11 nss",
             "app.setup-browsers"),
            ("Verificar Dependências", "Checar pacotes necessários",
             "dialog-information-symbolic", "dependência pacote verificar checar",
             "app.check-deps"),
            ("Sobre o BigCertificados", "Versão e informações do aplicativo",
             "help-about-symbolic", "sobre versão about informação big",
             "app.about"),
        ]
        for title, sub, icon, kw, act in actions:
            if _match(title, sub, kw):
                self._add_result(title, sub, icon, action=act)

        # ── 2. Judicial systems ──
        from src.ui.systems_view import JUDICIAL_STATES

        for state in JUDICIAL_STATES:
            for system in state["systems"]:
                if _match(system["name"], system.get("description", ""),
                          state["name"]):
                    self._add_result(
                        system["name"],
                        f"Sistemas Judiciais — {state['name']}",
                        system.get("icon", "document-edit-symbolic"),
                        url=system["url"],
                    )

        # ── 3. Drivers ──
        from src.certificate.driver_database import get_drivers_by_category, CATEGORY_META

        for cat, drivers in get_drivers_by_category().items():
            cat_label = CATEGORY_META.get(cat, (cat,))[0]
            for drv in drivers:
                if _match(drv.name, drv.description, " ".join(drv.packages)):
                    self._add_result(
                        drv.name,
                        f"Drivers — {cat_label}",
                        drv.icon or "dialog-password-symbolic",
                        tab="systems", sidebar="drivers",
                    )

        # ── 4. Detected browsers ──
        try:
            if not hasattr(self, "_cached_profiles"):
                from src.browser.browser_detect import find_all_profiles
                self._cached_profiles = find_all_profiles()

            seen: set[str] = set()
            for p in self._cached_profiles:
                if p.browser not in seen and _match(p.browser):
                    seen.add(p.browser)
                    self._add_result(
                        p.browser, "Navegador detectado",
                        "web-browser-symbolic",
                        tab="systems", sidebar="browsers",
                    )
        except Exception:
            pass

        # "No results" placeholder
        if self._search_results_list.get_first_child() is None:
            row = Adw.ActionRow()
            row.set_title("Nenhum resultado encontrado")
            row.set_icon_name("dialog-information-symbolic")
            self._search_results_list.append(row)

    def _show_lock(self) -> None:
        """Show the lock dialog as a modal."""
        dialog = LockDialog(on_unlocked=self._unlock)
        dialog.present(self)

    def _unlock(self) -> None:
        """Unlock the app — start scanning."""
        self._unlocked = True
        GLib.idle_add(self._initial_scan)

    def _initial_scan(self) -> bool:
        """Run initial USB scan on startup."""
        self._do_scan()
        self._udev_monitor.start()
        return False  # Don't repeat

    def _do_scan(self) -> None:
        self._set_status("Buscando dispositivos USB...")
        self._certs_view.token_view.clear()

        def scan_thread() -> None:
            found = self._udev_monitor.scan_existing()
            GLib.idle_add(self._on_scan_result, found)

        threading.Thread(target=scan_thread, daemon=True).start()

    def _on_scan_result(self, found: list[tuple[int, int, str]]) -> bool:
        for vid, pid, devnode in found:
            self._certs_view.token_view.add_token(vid, pid, devnode)

            # Wire up the new row
            key = f"{vid:04x}:{pid:04x}"
            row = self._certs_view.token_view._token_rows.get(key)
            if row:
                row.connect(
                    "activated",
                    self._on_token_row_activated,
                    vid, pid,
                )

        if found:
            self._set_status(f"{len(found)} dispositivo(s) encontrado(s)")
            self._dashboard.update_token_status(len(found))
        else:
            self._set_status("Nenhum token detectado")
            self._dashboard.update_token_status(0)
            # Try loading any available module
            self._try_auto_detect()

        return False

    def _try_auto_detect(self) -> None:
        """Try to find tokens via PKCS#11 module probing."""
        if not self._a3_manager.is_available:
            return

        def probe_thread() -> None:
            module = self._a3_manager.try_all_modules()
            if module:
                GLib.idle_add(self._on_module_found, module)

        threading.Thread(target=probe_thread, daemon=True).start()

    def _on_module_found(self, module_path: str) -> bool:
        self._set_status(f"Módulo encontrado: {module_path}")
        slots = self._a3_manager.get_slots()
        if slots:
            self._prompt_pin(slots[0])
        return False

    def _on_usb_event(
        self, action: str, vid: int, pid: int, devnode: str,
    ) -> bool:
        if action == "add":
            self._certs_view.token_view.add_token(vid, pid, devnode)
            self._set_status(f"Token conectado: {vid:04x}:{pid:04x}")

            key = f"{vid:04x}:{pid:04x}"
            row = self._certs_view.token_view._token_rows.get(key)
            if row:
                row.connect(
                    "activated",
                    self._on_token_row_activated,
                    vid, pid,
                )

            token_count = len(self._certs_view.token_view._token_rows)
            self._dashboard.update_token_status(token_count)

        elif action == "remove":
            self._certs_view.token_view.remove_token(vid, pid)
            self._set_status(f"Token removido: {vid:04x}:{pid:04x}")
            self._certs_view.reset_a3_view()

            token_count = len(self._certs_view.token_view._token_rows)
            self._dashboard.update_token_status(token_count)

        return False

    def _on_token_row_activated(
        self, row: Adw.ActionRow, vid: int = 0, pid: int = 0,
    ) -> None:
        # Load PKCS#11 module
        if vid and pid:
            success = self._a3_manager.load_module_for_device(vid, pid)
            if not success:
                self._set_status("Módulo PKCS#11 não encontrado para este dispositivo")
                return

        slots = self._a3_manager.get_slots()
        if slots:
            self._prompt_pin(slots[0])
        else:
            self._set_status("Nenhum slot de token disponível")

    def _prompt_pin(self, slot_info: object) -> None:
        from src.certificate.a3_manager import TokenSlotInfo
        if not isinstance(slot_info, TokenSlotInfo):
            return

        dialog = PinDialog(token_label=slot_info.label)
        dialog.connect("closed", self._on_pin_dialog_closed, slot_info)
        dialog.present(self)

    def _on_pin_dialog_closed(
        self, dialog: PinDialog, slot_info: object,
    ) -> None:
        from src.certificate.a3_manager import TokenSlotInfo
        if not isinstance(slot_info, TokenSlotInfo):
            return

        if not dialog.confirmed or not dialog.pin:
            return

        self._set_status("Autenticando...")
        pin = dialog.pin

        def login_thread() -> None:
            success = self._a3_manager.login(slot_info.slot_id, pin)
            if success:
                certs = self._a3_manager.list_certificates()
                GLib.idle_add(self._on_certificates_loaded, certs)
            else:
                GLib.idle_add(self._on_login_failed)

        threading.Thread(target=login_thread, daemon=True).start()

    def _on_certificates_loaded(self, certs: list) -> bool:
        self._certs_view.show_a3_certificates(certs)
        self._navigate_to("certificates")
        self._set_status(f"{len(certs)} certificado(s) encontrado(s)")
        return False

    def _on_login_failed(self) -> bool:
        self._set_status("Falha na autenticação — PIN incorreto?")
        self._certs_view.reset_a3_view()
        return False

    def _set_status(self, text: str) -> None:
        toast = Adw.Toast(title=text)
        toast.set_timeout(3)
        self._toast_overlay.add_toast(toast)

    def setup_browsers(self) -> None:
        """Register PKCS#11 module in all detected browsers."""
        module = self._a3_manager.current_module
        if not module:
            self._set_status("Nenhum módulo PKCS#11 carregado")
            return

        if not is_nss_tools_available():
            self._set_status("nss-tools não instalado (pacman -S nss)")
            return

        self._set_status("Configurando navegadores...")

        def setup_thread() -> None:
            results = register_in_all_browsers(module)
            summary = ", ".join(
                f"{name}: {'OK' if ok else 'FALHA'}"
                for name, ok in results.items()
            )
            GLib.idle_add(self._set_status, f"Navegadores: {summary}")

        threading.Thread(target=setup_thread, daemon=True).start()
