# Maintainer: Leonardo Athayde <leoathayde@gmail.com>
pkgname=big-certificados
pkgver=1.4.3
pkgrel=1
pkgdesc="Stack jurídica para advogados brasileiros — certificados digitais, assinatura, WebSigner e acesso a tribunais"
arch=('any')
url="https://github.com/xathay/big-advogados"
license=('MIT')
install="${pkgname}.install"
depends=(
    'python'
    'python-gobject'
    'gtk4'
    'libadwaita'
    'python-pykcs11'
    'python-pyudev'
    'python-cryptography'
    'pcsclite'
    'ccid'
    'opensc'
    'nss'
    'python-pikepdf'
    'python-reportlab'
    'python-pillow'
    'python-asn1crypto'
    'python-oscrypto'
    'python-endesive'
    'python-certifi'
    'python-qrcode'
    'binutils'  # ar — extrai .deb no instalador de drivers (big-drivers)
    'tar'       # data.tar.zst dentro do .deb (big-drivers)
    'polkit'    # autorização do helper big-drivers-install
    'python-typer'  # CLI do transcritor (big-advogados transcrever ...)
    'zenity'    # diálogo de senha (A1) e PIN (A3) do WebSigner — sem ele a assinatura falha
)
optdepends=(
    'pcsc-tools: Diagnóstico de leitores PC/SC (pcsc_scan)'
    'kdialog: Diálogo de senha/PIN do WebSigner em ambientes KDE (alternativa ao zenity)'
    'firefox-esr-bin: Navegador que aceita a ponte WebPKI embutida sem instalar extensão da loja'
    'python-faster-whisper: Transcritor de áudio (modelo Whisper local, ~3GB no primeiro uso)'
    'ffmpeg: Extração de duração/formato dos áudios no transcritor'
    'ttf-ubuntu-font-family: Tipografia padrão dos PDFs do transcritor'
)
source=()
sha256sums=()

package() {
    local _appdir="${pkgdir}/usr/lib/${pkgname}"

    # Install Python sources
    install -dm755 "${_appdir}"
    cp -a "${startdir}/src" "${_appdir}/src"

    # Remove __pycache__
    find "${_appdir}" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

    # Launcher script (GUI)
    install -dm755 "${pkgdir}/usr/bin"
    cat > "${pkgdir}/usr/bin/${pkgname}" << 'EOF'
#!/usr/bin/env bash
cd /usr/lib/big-certificados
exec python3 -m src.main "$@"
EOF
    chmod 755 "${pkgdir}/usr/bin/${pkgname}"

    # Launcher script (CLI — transcritor e futuros subcomandos)
    cat > "${pkgdir}/usr/bin/big-advogados" << 'EOF'
#!/usr/bin/env bash
cd /usr/lib/big-certificados
exec python3 -m src.transcritor.cli "$@"
EOF
    chmod 755 "${pkgdir}/usr/bin/big-advogados"

    # File-manager action para "Transcrever áudio com BIG"
    install -Dm644 "${startdir}/data/file-manager-actions/transcrever-audio.desktop" \
        "${pkgdir}/usr/share/file-manager/actions/transcrever-audio.desktop"

    # Desktop entry
    install -Dm644 "${startdir}/data/com.bigcertificados.desktop" \
        "${pkgdir}/usr/share/applications/com.bigcertificados.desktop"

    # Icons
    install -Dm644 "${startdir}/data/icons/bigcertificados.svg" \
        "${pkgdir}/usr/share/icons/hicolor/scalable/apps/bigcertificados.svg"
    install -Dm644 "${startdir}/data/icons/bigcertificados-symbolic.svg" \
        "${pkgdir}/usr/share/icons/hicolor/symbolic/apps/bigcertificados-symbolic.svg"

    # Udev rules
    install -Dm644 "${startdir}/data/udev/70-crypto-tokens.rules" \
        "${pkgdir}/usr/lib/udev/rules.d/70-crypto-tokens.rules"

    # Helper scripts
    install -Dm755 "${startdir}/scripts/install-pjeoffice-pro.sh" \
        "${_appdir}/scripts/install-pjeoffice-pro.sh"
    install -Dm755 "${startdir}/scripts/pjeoffice-install-helper.sh" \
        "${_appdir}/scripts/pjeoffice-install-helper.sh"
    install -Dm755 "${startdir}/scripts/pjeoffice-uninstall-helper.sh" \
        "${_appdir}/scripts/pjeoffice-uninstall-helper.sh"
    install -Dm755 "${startdir}/scripts/pjeoffice-detect-uiscale.py" \
        "${_appdir}/scripts/pjeoffice-detect-uiscale.py"

    # big-drivers — helper privilegiado e catálogo de drivers proprietários
    install -Dm755 "${startdir}/scripts/big-drivers-install.py" \
        "${_appdir}/scripts/big-drivers-install.py"
    install -dm755 "${_appdir}/data/drivers"
    install -m644 "${startdir}/data/drivers/"*.toml "${_appdir}/data/drivers/"
    install -Dm644 "${startdir}/data/polkit/org.bigcommunity.drivers.policy" \
        "${pkgdir}/usr/share/polkit-1/actions/org.bigcommunity.drivers.policy"

    # Web Signer (e-SAJ) — força a instalação da extensão oficial da Chrome
    # Web Store nos navegadores Chromium, pro advogado não instalar à mão.
    # Firefox fica de fora: a extensão foi blocklistada pela Mozilla — lá o
    # caminho é a ponte WebPKI embutida (Firefox ESR/Developer).
    for _poldir in \
        "etc/opt/chrome/policies/managed" \
        "etc/chromium/policies/managed" \
        "etc/brave/policies/managed"; do
        install -Dm644 "${startdir}/data/browser-policies/big-websigner.json" \
            "${pkgdir}/${_poldir}/big-websigner.json"
    done

    # License
    install -Dm644 "${startdir}/LICENSE" \
        "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE" 2>/dev/null || true
}
