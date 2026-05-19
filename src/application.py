"""Big Advogados — GtkApplication setup."""

from __future__ import annotations

import logging
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio  # noqa: E402

from src.window import MainWindow
from src.ui.password_settings import PasswordSettingsDialog

log = logging.getLogger(__name__)

APP_ID = "com.bigcertificados"
CURRENT_VERSION = "1.3.0"


class BigCertificadosApp(Adw.Application):
    """Main application class."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window: MainWindow | None = None

    def do_activate(self) -> None:
        if self._window is None:
            self._window = MainWindow(application=self)

        # Register icon search path for our custom icons
        src_root = os.path.dirname(os.path.dirname(__file__))
        icon_dir = os.path.join(src_root, "data", "icons")
        icon_theme = Gtk.IconTheme.get_for_display(self._window.get_display())
        icon_theme.add_search_path(icon_dir)

        # Ensure .desktop + icon are installed for Wayland app_id matching
        self._ensure_desktop_integration(src_root)

        self._window.present()

    # ------------------------------------------------------------------
    # Desktop integration (icon / .desktop file)
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_desktop_integration(src_root: str) -> None:
        """Install .desktop file and SVG icon into user-local XDG paths.

        Under Wayland the compositor resolves the window icon via
        app_id → .desktop file → Icon= key → icon theme lookup, so both
        the desktop entry and the icon must be discoverable.
        """
        xdg_data = os.environ.get(
            "XDG_DATA_HOME",
            os.path.join(os.path.expanduser("~"), ".local", "share"),
        )
        desktop_dir = os.path.join(xdg_data, "applications")
        icon_dir = os.path.join(
            xdg_data, "icons", "hicolor", "scalable", "apps",
        )

        desktop_src = os.path.join(
            src_root, "data", "com.bigcertificados.desktop",
        )
        icon_src = os.path.join(
            src_root, "data", "icons", "bigcertificados.svg",
        )

        pairs = [
            (desktop_src, os.path.join(desktop_dir, "com.bigcertificados.desktop")),
            (icon_src, os.path.join(icon_dir, "bigcertificados.svg")),
        ]

        for src, dst in pairs:
            if not os.path.exists(src):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            # Re-create symlink if target changed (e.g. repo moved)
            if os.path.islink(dst):
                if os.readlink(dst) == os.path.abspath(src):
                    continue
                os.remove(dst)
            elif os.path.exists(dst):
                continue  # real file installed by package manager — don't touch
            try:
                os.symlink(os.path.abspath(src), dst)
            except OSError:
                log.debug("Could not create symlink %s → %s", dst, src)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)

        # Use AdwStyleManager instead of deprecated GtkSettings dark theme
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

        self._setup_actions()

    def _setup_actions(self) -> None:
        # Setup browsers action
        action = Gio.SimpleAction.new("setup-browsers", None)
        action.connect("activate", self._on_setup_browsers)
        self.add_action(action)

        # Check dependencies action
        action = Gio.SimpleAction.new("check-deps", None)
        action.connect("activate", self._on_check_deps)
        self.add_action(action)

        # Password settings action
        action = Gio.SimpleAction.new("password-settings", None)
        action.connect("activate", self._on_password_settings)
        self.add_action(action)

        # About action
        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", self._on_about)
        self.add_action(action)

    def _on_setup_browsers(self, *_args: object) -> None:
        if self._window:
            self._window.setup_browsers()

    def _on_check_deps(self, *_args: object) -> None:
        from src.ui.deps_dialog import DependencyCheckDialog
        dialog = DependencyCheckDialog()
        if self._window:
            dialog.present(self._window)

    def _on_password_settings(self, *_args: object) -> None:
        dialog = PasswordSettingsDialog()
        if self._window:
            dialog.present(self._window)

    def _on_about(self, *_args: object) -> None:
        about = Adw.AboutDialog()
        about.set_application_name("Big Advogados")
        about.set_developer_name("BigLinux Team")
        about.set_version(CURRENT_VERSION)
        about.set_comments(
            "Stack jurídica completa para advogados brasileiros no GNU/Linux — "
            "certificados digitais, assinatura, WebSigner e acesso a tribunais.\n\n"
            "Recursos:\n"
            "• Assinatura no e-SAJ TJSP com token A3 ou certificado A1 (WebSigner nativo)\n"
            "• Certificados A3 via token USB (PKCS#11)\n"
            "• Certificados A1 (PFX/P12)\n"
            "• VidaaS Connect — certificado A3 na nuvem\n"
            "• Assinatura digital de PDFs (wizard guiado ICP-Brasil)\n"
            "• Dashboard com status de certificados e ações rápidas\n"
            "• Configuração automática de navegadores (Firefox, Chrome, Brave)\n"
            "• 39 sistemas judiciais organizados por estado\n"
            "• 68 drivers de tokens catalogados\n"
            "• Integração com PJe, e-SAJ, eProc, PROJUDI e PJeOffice Pro\n"
            "• Detecção automática de tokens USB via udev"
        )
        about.set_website("https://github.com/xathay/big-advogados")
        about.set_application_icon("bigcertificados")
        about.set_license_type(Gtk.License.MIT_X11)
        about.set_release_notes(
            "<p>Novidades na versão 1.3.0:</p>"
            "<ul>"
            "<li>WebSigner agora assina no e-SAJ com token A3 (PKCS#11), não só com A1 (.p12)</li>"
            "<li>Painel do WebSigner mostra se o token está conectado e qual modelo</li>"
            "<li>Diálogo de PIN do token via zenity/kdialog na hora da assinatura</li>"
            "<li>Textos do painel reescritos sem jargão — orientado a advogados leigos</li>"
            "<li>Removido link quebrado para extensão Web Signer da Mozilla AMO</li>"
            "</ul>"
            "<p>Versão 1.2.0:</p>"
            "<ul>"
            "<li>WebSigner nativo — conector PKI próprio compatível com o e-SAJ TJSP</li>"
            "<li>Diálogo de configuração e-SAJ com instalação automática da ponte WebPKI</li>"
            "<li>Importação de PFX direto pelo Web Signer (importPkcs12)</li>"
            "<li>Assinador de PDFs: carimbo visível redesenhado + página de certificação opcional</li>"
            "<li>Detecção automática de HiDPI para o PJeOffice Pro (Java Swing)</li>"
            "<li>Rebranding: BigCertificados → Big Advogados</li>"
            "</ul>"
            "<p>Versão 1.1.0:</p>"
            "<ul>"
            "<li>URLs de sistemas judiciais atualizados — 10 links quebrados corrigidos</li>"
            "<li>Migração para eProc (TRF2, TRF4, TJRS)</li>"
            "<li>Dashboard simplificado sem scroll desnecessário</li>"
            "<li>Certificados unificados com abas ViewStack (A3 + A1)</li>"
            "<li>Tema escuro respeita preferência do sistema por padrão</li>"
            "</ul>"
            "<p>Versão 1.0.0:</p>"
            "<ul>"
            "<li>Interface com sidebar categorizada (NavigationSplitView)</li>"
            "<li>Dashboard com visão geral dos certificados e ações rápidas</li>"
            "<li>Assinador de PDFs com wizard guiado de 4 passos</li>"
            "<li>Sistemas judiciais com sidebar colapsável (OverlaySplitView)</li>"
            "<li>VidaaS Connect — assinatura em nuvem via Valid Certificadora</li>"
            "<li>68 drivers de tokens catalogados com instalação automática</li>"
            "</ul>"
        )
        about.set_developers([
            "Leonardo Athayde <leoathayde@gmail.com>",
        ])
        about.set_copyright("© 2026 BigLinux Team")
        about.add_credit_section("Contribuidores", [
            "Rafael Ruscher <rruscher@gmail.com>",
        ])

        if self._window:
            about.present(self._window)
