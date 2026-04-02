"""Dashboard / Home view — overview of certificate status and quick actions."""

from __future__ import annotations

from collections.abc import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: E402

# Navigation callback type: navigate_to(view_id, sidebar_id=None)
NavigateCallback = Callable[[str, str | None], None]


class DashboardView(Adw.Bin):
    """Home page with certificate status cards and quick actions."""

    def __init__(self, navigate_to: NavigateCallback) -> None:
        super().__init__()

        self._navigate = navigate_to

        # State
        self._token_count: int = 0
        self._a1_loaded: bool = False
        self._vidaas_connected: bool = False

        # Main StatusPage — no scroll, fills available space
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("channel-secure-symbolic")
        self._status_page.set_title("BigCertificados")
        self._status_page.set_description(
            "Selecione uma opção na barra lateral para começar."
        )
        self.set_child(self._status_page)

        # Content box inside status page (for cards + actions)
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        self._build_status_cards()
        self._build_quick_actions()

        self._status_page.set_child(self._content_box)

        # Start with onboarding visible
        self._refresh()

    # ── Build sections ──

    def _build_status_cards(self) -> None:
        """Certificate status cards group."""
        self._cards_group = Adw.PreferencesGroup()
        self._cards_group.set_title("Status dos Certificados")

        # Token A3 card
        self._token_card = Adw.ActionRow()
        self._token_card.set_icon_name("drive-removable-media-symbolic")
        self._token_card.set_title("Tokens USB (A3)")
        self._token_card.set_subtitle("Nenhum token detectado")
        self._token_card.set_activatable(True)
        self._token_card.connect("activated", lambda _r: self._navigate("certificates", None))
        arrow1 = Gtk.Image.new_from_icon_name("go-next-symbolic")
        self._token_card.add_suffix(arrow1)
        self._cards_group.add(self._token_card)

        # A1 card
        self._a1_card = Adw.ActionRow()
        self._a1_card.set_icon_name("document-open-symbolic")
        self._a1_card.set_title("Certificado A1 (PFX)")
        self._a1_card.set_subtitle("Nenhum certificado carregado")
        self._a1_card.set_activatable(True)
        self._a1_card.connect("activated", lambda _r: self._navigate("certificates", None))
        arrow2 = Gtk.Image.new_from_icon_name("go-next-symbolic")
        self._a1_card.add_suffix(arrow2)
        self._cards_group.add(self._a1_card)

        # VidaaS card
        self._vidaas_card = Adw.ActionRow()
        self._vidaas_card.set_icon_name("network-wireless-symbolic")
        self._vidaas_card.set_title("VidaaS Connect")
        self._vidaas_card.set_subtitle("Não configurado")
        self._vidaas_card.set_activatable(True)
        self._vidaas_card.connect("activated", lambda _r: self._navigate("vidaas", None))
        arrow3 = Gtk.Image.new_from_icon_name("go-next-symbolic")
        self._vidaas_card.add_suffix(arrow3)
        self._cards_group.add(self._vidaas_card)

        self._content_box.append(self._cards_group)

    def _build_quick_actions(self) -> None:
        """Quick action buttons."""
        self._actions_group = Adw.PreferencesGroup()
        self._actions_group.set_title("Ações Rápidas")

        sign_row = Adw.ActionRow()
        sign_row.set_icon_name("document-edit-symbolic")
        sign_row.set_title("Assinar PDF")
        sign_row.set_subtitle("Assinatura digital de documentos")
        sign_row.set_activatable(True)
        sign_row.connect("activated", lambda _r: self._navigate("signer", None))
        sign_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self._actions_group.add(sign_row)

        systems_row = Adw.ActionRow()
        systems_row.set_icon_name("preferences-system-network-symbolic")
        systems_row.set_title("Sistemas Judiciais")
        systems_row.set_subtitle("Acessar PJe, e-SAJ, PROJUDI e outros")
        systems_row.set_activatable(True)
        systems_row.connect("activated", lambda _r: self._navigate("systems", None))
        systems_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self._actions_group.add(systems_row)

        deps_row = Adw.ActionRow()
        deps_row.set_icon_name("dialog-information-symbolic")
        deps_row.set_title("Verificar Dependências")
        deps_row.set_subtitle("Pacotes, módulos e serviços do sistema")
        deps_row.set_activatable(True)
        deps_row.connect("activated", lambda _r: self._navigate("deps", None))
        deps_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self._actions_group.add(deps_row)

        self._content_box.append(self._actions_group)

    # ── Public API ──

    def update_token_status(self, count: int) -> None:
        """Update token card with current count."""
        self._token_count = count
        if count > 0:
            self._token_card.set_subtitle(f"{count} dispositivo(s) conectado(s)")
        else:
            self._token_card.set_subtitle("Nenhum token detectado")
        self._refresh()

    def update_a1_status(self, loaded: bool, holder_name: str = "", validity: str = "") -> None:
        """Update A1 card."""
        self._a1_loaded = loaded
        if loaded:
            sub = holder_name
            if validity:
                sub += f" — {validity}"
            self._a1_card.set_subtitle(sub)
        else:
            self._a1_card.set_subtitle("Nenhum certificado carregado")
        self._refresh()

    def update_vidaas_status(self, connected: bool) -> None:
        """Update VidaaS card."""
        self._vidaas_connected = connected
        if connected:
            self._vidaas_card.set_subtitle("Conectado")
        else:
            self._vidaas_card.set_subtitle("Não configurado")
        self._refresh()

    # ── Internal ──

    def _refresh(self) -> None:
        """Toggle description vs status cards based on state."""
        has_anything = self._token_count > 0 or self._a1_loaded or self._vidaas_connected

        if has_anything:
            self._status_page.set_description("")
        else:
            self._status_page.set_description(
                "Selecione uma opção na barra lateral para começar."
            )

        self._cards_group.set_visible(has_anything)
        self._actions_group.set_visible(True)
