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


# Brazilian electronic judicial systems
JUDICIAL_SYSTEMS = [
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
    {
        "name": "PJe — TRT5 (Bahia)",
        "url": "https://pje.trt5.jus.br",
        "description": "PJe — Tribunal Regional do Trabalho 5ª Região",
        "icon": "document-edit-symbolic",
    },
    {
        "name": "PJe — TST",
        "url": "https://pje.tst.jus.br",
        "description": "PJe — Tribunal Superior do Trabalho",
        "icon": "document-edit-symbolic",
    },
    {
        "name": "PJe — CNJ",
        "url": "https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/",
        "description": "Portal PJe — Conselho Nacional de Justiça",
        "icon": "document-send-symbolic",
    },
]


class SystemsView(Gtk.ScrolledWindow):
    """Quick-access links to Brazilian electronic judicial systems."""

    def __init__(self) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        header = Gtk.Label(label="Sistemas Judiciais Eletrônicos")
        header.add_css_class("title-2")
        header.set_halign(Gtk.Align.START)
        content.append(header)

        desc = Gtk.Label(
            label="Acesse os sistemas com seu certificado digital configurado."
        )
        desc.set_halign(Gtk.Align.START)
        desc.add_css_class("dim-label")
        desc.set_wrap(True)
        content.append(desc)

        # Group: PJe Systems
        pje_group = Adw.PreferencesGroup()
        pje_group.set_title("PJe — Processo Judicial Eletrônico")

        other_group = Adw.PreferencesGroup()
        other_group.set_title("Outros Sistemas")

        for system in JUDICIAL_SYSTEMS:
            row = Adw.ActionRow()
            row.set_title(system["name"])
            row.set_subtitle(system["description"])
            row.set_icon_name(system["icon"])
            row.set_activatable(True)

            url = system["url"]
            row.connect("activated", self._on_system_clicked, url)

            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            row.add_suffix(arrow)

            if "PJe" in system["name"] or "PROJUDI" in system["name"]:
                pje_group.add(row)
            else:
                other_group.add(row)

        content.append(pje_group)
        content.append(other_group)

        # PJeOffice Pro section
        pjeoffice_group = Adw.PreferencesGroup()
        pjeoffice_group.set_title("PJeOffice Pro — Assinador Digital")
        pjeoffice_group.set_description(
            "Necessário para assinar documentos nos sistemas PJe."
        )

        self._pjeoffice_row = Adw.ActionRow()
        self._pjeoffice_row.set_icon_name("application-x-executable-symbolic")
        self._update_pjeoffice_status()
        pjeoffice_group.add(self._pjeoffice_row)

        # Update status row (hidden when no update available)
        self._update_row = Adw.ActionRow()
        self._update_row.set_icon_name("software-update-available-symbolic")
        self._update_row.set_visible(False)
        pjeoffice_group.add(self._update_row)

        # Check for updates button
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

        # Auto-check toggle
        auto_check_row = Adw.SwitchRow()
        auto_check_row.set_title("Buscar atualizações automaticamente")
        auto_check_row.set_subtitle("Verifica a cada 24h ao abrir o aplicativo")
        auto_check_row.set_icon_name("preferences-system-time-symbolic")
        auto_check_row.set_active(is_pjeoffice_auto_update_enabled())
        auto_check_row.connect("notify::active", self._on_auto_check_toggled)
        pjeoffice_group.add(auto_check_row)

        # Install button
        install_row = Adw.ActionRow()
        install_row.set_title("Instalar PJeOffice Pro")
        install_row.set_subtitle(
            "Baixa do site oficial (CNJ/TRF3) e instala automaticamente"
        )
        install_row.set_icon_name("folder-download-symbolic")
        install_row.set_activatable(True)
        install_row.connect("activated", self._on_install_pjeoffice)

        arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
        install_row.add_suffix(arrow)
        pjeoffice_group.add(install_row)

        # Launch button (if installed)
        self._launch_row = Adw.ActionRow()
        self._launch_row.set_title("Abrir PJeOffice Pro")
        self._launch_row.set_subtitle("Iniciar o assinador digital")
        self._launch_row.set_icon_name("media-playback-start-symbolic")
        self._launch_row.set_activatable(True)
        self._launch_row.connect("activated", self._on_launch_pjeoffice)
        arrow2 = Gtk.Image.new_from_icon_name("go-next-symbolic")
        self._launch_row.add_suffix(arrow2)
        self._launch_row.set_visible(self._is_pjeoffice_installed())
        pjeoffice_group.add(self._launch_row)

        content.append(pjeoffice_group)
        self.set_child(content)

        # Pending update info for install action
        self._pending_update: Optional[PJeOfficeUpdateInfo] = None

        # Auto-check on startup
        if is_pjeoffice_auto_update_enabled() and should_check_pjeoffice_now():
            if self._is_pjeoffice_installed():
                GLib.idle_add(self._auto_check_pjeoffice)

    @staticmethod
    def _is_pjeoffice_installed() -> bool:
        return (
            shutil.which("pjeoffice-pro") is not None
            or Path("/usr/share/pjeoffice-pro/pjeoffice-pro.jar").is_file()
        )

    def _update_pjeoffice_status(self) -> None:
        if self._is_pjeoffice_installed():
            version = get_installed_pjeoffice_version() or "?"
            self._pjeoffice_row.set_title(f"PJeOffice Pro — Instalado (v{version})")
            self._pjeoffice_row.set_subtitle("Pronto para assinar documentos")

            check = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            check.add_css_class("success")
            self._pjeoffice_row.add_suffix(check)
        else:
            self._pjeoffice_row.set_title("PJeOffice Pro — Não instalado")
            self._pjeoffice_row.set_subtitle(
                "Necessário para acessar os sistemas PJe com certificado digital"
            )

            warn = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            warn.add_css_class("warning")
            self._pjeoffice_row.add_suffix(warn)

    def _on_install_pjeoffice(self, _row: Adw.ActionRow) -> None:
        """Open the PJeOffice Pro installer dialog."""
        from src.ui.pjeoffice_installer import PJeOfficeInstallerDialog

        dialog = PJeOfficeInstallerDialog(on_installed=self._refresh_pjeoffice_status)
        window = self.get_root()
        dialog.present(window)

    def _refresh_pjeoffice_status(self) -> None:
        """Refresh the PJeOffice row after installation."""
        # Clear old suffixes
        child = self._pjeoffice_row.get_first_child()
        while child:
            next_c = child.get_next_sibling()
            if isinstance(child, Gtk.Image):
                self._pjeoffice_row.remove(child)
            child = next_c
        self._update_pjeoffice_status()
        self._launch_row.set_visible(self._is_pjeoffice_installed())

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

        # Clear old suffix icons
        child = self._update_row.get_first_child()
        while child:
            next_c = child.get_next_sibling()
            if isinstance(child, Gtk.Image):
                self._update_row.remove(child)
            child = next_c

        check_pjeoffice_updates_async(version, self._on_pjeoffice_update_result)

    def _on_pjeoffice_update_result(
        self,
        update_info: Optional[PJeOfficeUpdateInfo],
        error: Optional[str],
    ) -> bool:
        """Handle PJeOffice update check result."""
        self._check_spinner.stop()

        # Clear old suffix icons
        child = self._update_row.get_first_child()
        while child:
            next_c = child.get_next_sibling()
            if isinstance(child, Gtk.Image):
                self._update_row.remove(child)
            child = next_c

        if error:
            self._update_row.set_visible(True)
            self._update_row.set_title("Erro ao verificar atualizações")
            self._update_row.set_subtitle(error)
            icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
            icon.add_css_class("error")
            self._update_row.add_suffix(icon)
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
            self._update_row.add_suffix(icon)
        else:
            installed = get_installed_pjeoffice_version() or "?"
            self._update_row.set_visible(True)
            self._update_row.set_title("PJeOffice Pro está atualizado")
            self._update_row.set_subtitle(f"Versão instalada: v{installed}")
            icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            icon.add_css_class("success")
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
