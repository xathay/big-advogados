# Maintainer: Leonardo Athayde <leoathayde@gmail.com>
pkgname=big-certificados
pkgver=0.1.0
pkgrel=1
pkgdesc="Gerenciador de certificados digitais para advogados brasileiros"
arch=('any')
url="https://github.com/xathay/big-advogados"
license=('MIT')
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
)
source=()
sha256sums=()

package() {
    local _appdir="${pkgdir}/usr/lib/${pkgname}"

    # Install Python sources
    install -dm755 "${_appdir}"
    cp -a "${srcdir}/../src" "${_appdir}/src"

    # Remove __pycache__
    find "${_appdir}" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

    # Launcher script
    install -dm755 "${pkgdir}/usr/bin"
    cat > "${pkgdir}/usr/bin/${pkgname}" << 'EOF'
#!/usr/bin/env bash
cd /usr/lib/big-certificados
exec python3 -m src.main "$@"
EOF
    chmod 755 "${pkgdir}/usr/bin/${pkgname}"

    # Desktop entry
    install -Dm644 "${srcdir}/../data/com.bigcertificados.desktop" \
        "${pkgdir}/usr/share/applications/com.bigcertificados.desktop"

    # Icons
    install -Dm644 "${srcdir}/../data/icons/bigcertificados.svg" \
        "${pkgdir}/usr/share/icons/hicolor/scalable/apps/bigcertificados.svg"
    install -Dm644 "${srcdir}/../data/icons/bigcertificados-symbolic.svg" \
        "${pkgdir}/usr/share/icons/hicolor/symbolic/apps/bigcertificados-symbolic.svg"

    # Udev rules
    install -Dm644 "${srcdir}/../data/udev/70-crypto-tokens.rules" \
        "${pkgdir}/usr/lib/udev/rules.d/70-crypto-tokens.rules"

    # Helper scripts
    install -Dm755 "${srcdir}/../scripts/install-pjeoffice-pro.sh" \
        "${_appdir}/scripts/install-pjeoffice-pro.sh"
    install -Dm755 "${srcdir}/../scripts/pjeoffice-install-helper.sh" \
        "${_appdir}/scripts/pjeoffice-install-helper.sh"

    # License
    install -Dm644 "${srcdir}/../LICENSE" \
        "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE" 2>/dev/null || true
}
