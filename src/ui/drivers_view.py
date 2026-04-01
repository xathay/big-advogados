"""Drivers & Tokens section for SystemsView.

Builds an Adw.PreferencesGroup that lets users see installed token
drivers and install missing ones.
"""

from __future__ import annotations

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from src.certificate.driver_database import (
    CATEGORY_META,
    CATEGORY_ORDER,
    TokenDriver,
    get_drivers_by_category,
    get_pcscd_status,
    install_official_packages,
    is_driver_installed,
    open_aur_install,
)


class DriversSection:
    """Builds and manages the 'Drivers & Tokens' UI section."""

    def __init__(self) -> None:
        self._rows: dict[str, tuple[Adw.ActionRow, Gtk.Image, Gtk.Button]] = {}

    # ── Public API ────────────────────────────────────────────────────

    def build(self, parent: Gtk.Box) -> None:
        """Create all driver groups and append to *parent*."""
        by_cat = get_drivers_by_category()

        group = Adw.PreferencesGroup()
        group.set_title("Drivers &amp; Tokens")
        group.set_description(
            "Instale os drivers e middleware necessários para seu token."
        )

        # Base packages (expanded by default)
        base_drivers = by_cat.get("base", [])
        if base_drivers:
            self._add_base_section(group, base_drivers)

        # Other categories as collapsed expanders
        for cat in CATEGORY_ORDER:
            if cat == "base":
                continue
            drivers = by_cat.get(cat, [])
            if not drivers:
                continue
            meta = CATEGORY_META.get(cat, (cat, "", "dialog-password-symbolic"))
            expander = Adw.ExpanderRow()
            expander.set_title(meta[0])
            expander.set_subtitle(meta[1])
            expander.set_icon_name(meta[2])
            for drv in drivers:
                row = self._make_driver_row(drv)
                expander.add_row(row)
            group.add(expander)

        # pcscd service status
        self._add_pcscd_row(group)

        parent.append(group)

        # Refresh installation status in background
        threading.Thread(target=self._refresh_all_status, daemon=True).start()

    # ── Internal: base section ────────────────────────────────────────

    def _add_base_section(
        self, group: Adw.PreferencesGroup, drivers: list[TokenDriver],
    ) -> None:
        meta = CATEGORY_META["base"]
        expander = Adw.ExpanderRow()
        expander.set_title(meta[0])
        expander.set_subtitle(meta[1])
        expander.set_icon_name(meta[2])
        expander.set_expanded(True)

        for drv in drivers:
            row = self._make_driver_row(drv)
            expander.add_row(row)

        # "Install all missing" action
        install_all_row = Adw.ActionRow()
        install_all_row.set_title("Instalar Pacotes Pendentes")
        install_all_row.set_subtitle(
            "Instala todos os pacotes base que ainda não estão no sistema"
        )
        install_all_row.set_icon_name("folder-download-symbolic")
        install_all_row.set_activatable(True)
        self._base_install_spinner = Gtk.Spinner()
        install_all_row.add_suffix(self._base_install_spinner)
        arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
        install_all_row.add_suffix(arrow)
        install_all_row.connect("activated", self._on_install_base, drivers)
        self._base_install_row = install_all_row
        expander.add_row(install_all_row)

        group.add(expander)

    def _on_install_base(
        self,
        _row: Adw.ActionRow,
        drivers: list[TokenDriver],
    ) -> None:
        missing: list[str] = []
        for drv in drivers:
            if drv.source == "official":
                for pkg in drv.packages:
                    missing.append(pkg)
        if not missing:
            return
        self._base_install_row.set_sensitive(False)
        self._base_install_spinner.start()

        def work() -> None:
            ok, msg = install_official_packages(missing)
            GLib.idle_add(on_done, ok, msg)

        def on_done(ok: bool, msg: str) -> bool:
            self._base_install_row.set_sensitive(True)
            self._base_install_spinner.stop()
            threading.Thread(
                target=self._refresh_all_status, daemon=True,
            ).start()
            return False

        threading.Thread(target=work, daemon=True).start()

    # ── Internal: pcscd row ───────────────────────────────────────────

    def _add_pcscd_row(self, group: Adw.PreferencesGroup) -> None:
        row = Adw.ActionRow()
        row.set_title("Serviço pcscd")
        row.set_icon_name("system-run-symbolic")
        self._pcscd_row = row

        self._pcscd_icon = Gtk.Image()
        row.add_suffix(self._pcscd_icon)

        restart_btn = Gtk.Button()
        restart_btn.set_icon_name("view-refresh-symbolic")
        restart_btn.set_valign(Gtk.Align.CENTER)
        restart_btn.set_tooltip_text("Reiniciar pcscd")
        restart_btn.add_css_class("flat")
        restart_btn.connect("clicked", self._on_restart_pcscd)
        row.add_suffix(restart_btn)

        group.add(row)
        self._update_pcscd_ui()

    def _update_pcscd_ui(self) -> None:
        active, enabled = get_pcscd_status()
        if active:
            self._pcscd_row.set_subtitle("Ativo e pronto para uso")
            self._pcscd_icon.set_from_icon_name("emblem-ok-symbolic")
            self._pcscd_icon.add_css_class("success")
        else:
            self._pcscd_row.set_subtitle("Inativo — inicie o serviço")
            self._pcscd_icon.set_from_icon_name("dialog-warning-symbolic")
            for cls in ("success",):
                self._pcscd_icon.remove_css_class(cls)
            self._pcscd_icon.add_css_class("warning")

    def _on_restart_pcscd(self, _btn: Gtk.Button) -> None:
        def work() -> None:
            import subprocess
            subprocess.run(
                ["pkexec", "systemctl", "enable", "--now", "pcscd.service"],
                capture_output=True, timeout=15,
            )
            GLib.idle_add(lambda: self._update_pcscd_ui() or False)

        threading.Thread(target=work, daemon=True).start()

    # ── Internal: driver row ──────────────────────────────────────────

    def _make_driver_row(self, drv: TokenDriver) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(drv.name)
        row.set_subtitle(drv.description)
        row.set_icon_name(drv.icon)

        # Status icon (updated later)
        status_icon = Gtk.Image.new_from_icon_name(
            "content-loading-symbolic",
        )
        row.add_suffix(status_icon)

        # Install button (hidden when installed)
        install_btn = Gtk.Button()
        install_btn.set_icon_name("folder-download-symbolic")
        install_btn.set_valign(Gtk.Align.CENTER)
        install_btn.set_tooltip_text(f"Instalar {', '.join(drv.packages)}")
        install_btn.add_css_class("flat")
        install_btn.connect("clicked", self._on_install_driver, drv)
        install_btn.set_visible(False)
        row.add_suffix(install_btn)

        key = "|".join(drv.packages)
        self._rows[key] = (row, status_icon, install_btn)
        return row

    def _set_driver_status(self, drv: TokenDriver, installed: bool) -> None:
        key = "|".join(drv.packages)
        entry = self._rows.get(key)
        if not entry:
            return
        _row, icon, btn = entry
        for cls in ("success", "warning", "dim-label"):
            icon.remove_css_class(cls)
        if installed:
            icon.set_from_icon_name("emblem-ok-symbolic")
            icon.add_css_class("success")
            btn.set_visible(False)
        else:
            icon.set_from_icon_name("software-update-available-symbolic")
            icon.add_css_class("dim-label")
            btn.set_visible(True)

    def _on_install_driver(
        self, _btn: Gtk.Button, drv: TokenDriver,
    ) -> None:
        if drv.source == "official":
            _btn.set_sensitive(False)

            def work() -> None:
                ok, _msg = install_official_packages(list(drv.packages))
                GLib.idle_add(on_done, ok)

            def on_done(ok: bool) -> bool:
                _btn.set_sensitive(True)
                installed = is_driver_installed(drv)
                self._set_driver_status(drv, installed)
                return False

            threading.Thread(target=work, daemon=True).start()
        else:
            for pkg in drv.packages:
                open_aur_install(pkg)

    # ── Internal: status refresh ──────────────────────────────────────

    def _refresh_all_status(self) -> None:
        from src.certificate.driver_database import get_installed_packages
        installed_pkgs = get_installed_packages()
        by_cat = get_drivers_by_category()
        for drivers in by_cat.values():
            for drv in drivers:
                installed = is_driver_installed(drv, installed_pkgs)
                GLib.idle_add(self._set_driver_status, drv, installed)
        GLib.idle_add(lambda: self._update_pcscd_ui() or False)
