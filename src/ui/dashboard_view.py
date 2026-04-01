"""Dashboard / Home view — overview of certificate status and quick actions."""

from __future__ import annotations

from collections.abc import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: E402

# Navigation callback type: navigate_to(view_id, sidebar_id=None)
NavigateCallback = Callable[[str, str | None], None]


class DashboardView(Gtk.ScrolledWindow):
    """Home page with certificate status cards and quick actions."""

    def __init__(self, navigate_to: NavigateCallback) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._navigate = navigate_to

        # State
        self._token_count: int = 0
        self._a1_loaded: bool = False
        self._vidaas_connected: bool = False

        # Layout
        self._clamp = Adw.Clamp()
        self._clamp.set_maximum_size(700)
        self._clamp.set_tightening_threshold(500)

        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self._box.set_margin_top(24)
        self._box.set_margin_bottom(24)
        self._box.set_margin_start(16)
        self._box.set_margin_end(16)

        self._clamp.set_child(self._box)
        self.set_child(self._clamp)

        self._build_onboarding()
        self._build_status_cards()
        self._build_quick_actions()

        # Start with onboarding visible
        self._refresh()

    # ── Build sections ──

    def _build_onboarding(self) -> None:
        """Onboarding status page shown when no certificates are loaded."""
        self._onboarding = Adw.StatusPage()
        self._onboarding.set_icon_name("channel-secure-symbolic")
        self._onboarding.set_title("Bem-vindo ao BigCertificados")
        self._onboarding.set_description(
            "Comece conectando seu certificado digital."
        )

        btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        btn_box.set_halign(Gtk.Align.CENTER)

        token_btn = Gtk.Button()
        token_btn.set_child(self._icon_label("drive-removable-media-symbolic", "Conectar Token USB"))
        token_btn.add_css_class("suggested-action")
        token_btn.add_css_class("pill")
        token_btn.connect("clicked", lambda _b: self._navigate("certificates", None))
        btn_box.append(token_btn)

        a1_btn = Gtk.Button()
        a1_btn.set_child(self._icon_label("document-open-symbolic", "Importar Certificado A1"))
        a1_btn.add_css_class("pill")
        a1_btn.connect("clicked", lambda _b: self._navigate("certificates", None))
        btn_box.append(a1_btn)

        vidaas_btn = Gtk.Button()
        vidaas_btn.set_child(self._icon_label("network-wireless-symbolic", "Configurar VidaaS Connect"))
        vidaas_btn.add_css_class("pill")
        vidaas_btn.connect("clicked", lambda _b: self._navigate("vidaas", None))
        btn_box.append(vidaas_btn)

        self._onboarding.set_child(btn_box)
        self._box.append(self._onboarding)

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

        self._box.append(self._cards_group)

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

        self._box.append(self._actions_group)

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
        """Toggle onboarding vs status cards based on state."""
        has_anything = self._token_count > 0 or self._a1_loaded or self._vidaas_connected
        self._onboarding.set_visible(not has_anything)
        self._cards_group.set_visible(has_anything)
        self._actions_group.set_visible(True)

    @staticmethod
    def _icon_label(icon_name: str, text: str) -> Gtk.Box:
        """Build an icon + label box for button content."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_halign(Gtk.Align.CENTER)
        box.append(Gtk.Image.new_from_icon_name(icon_name))
        box.append(Gtk.Label(label=text))
        return box
