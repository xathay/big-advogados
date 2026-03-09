#!/usr/bin/env bash
# install-pjeoffice-pro.sh — Instala o PJeOffice Pro do site oficial (TRF3/CNJ)
# Uso: bash install-pjeoffice-pro.sh

set -euo pipefail

PJEOFFICE_VERSION="2.5.16u"
DOWNLOAD_URL="https://pje-office.pje.jus.br/pro/pjeoffice-pro-v${PJEOFFICE_VERSION}-linux_x64.zip"
SHA256="6087391759c7cba11fb5ef815fe8be91713b46a8607c12eb664a9d9a6882c4c7"
INSTALL_DIR="/usr/share/pjeoffice-pro"
TMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

echo "=== Instalação do PJeOffice Pro ${PJEOFFICE_VERSION} ==="
echo ""

# Check root
if [[ $EUID -ne 0 ]]; then
    echo "Erro: Execute este script com sudo."
    echo "  sudo bash $0"
    exit 1
fi

# Check Java 11
if ! command -v /usr/lib/jvm/java-11-openjdk/bin/java &>/dev/null; then
    echo "Java 11 não encontrado. Instalando jre11-openjdk..."
    pacman -S --noconfirm jre11-openjdk
fi

# Check unzip
if ! command -v unzip &>/dev/null; then
    echo "unzip não encontrado. Instalando..."
    pacman -S --noconfirm unzip
fi

# Download
echo "Baixando PJeOffice Pro v${PJEOFFICE_VERSION}..."
curl -L --progress-bar -o "${TMP_DIR}/pjeoffice-pro.zip" "${DOWNLOAD_URL}"

# Verify checksum
echo "Verificando integridade (SHA-256)..."
ACTUAL_SHA=$(sha256sum "${TMP_DIR}/pjeoffice-pro.zip" | cut -d' ' -f1)
if [[ "${ACTUAL_SHA}" != "${SHA256}" ]]; then
    echo "ERRO: Hash SHA-256 não confere!"
    echo "  Esperado: ${SHA256}"
    echo "  Obtido:   ${ACTUAL_SHA}"
    echo ""
    echo "O arquivo pode estar corrompido ou ter sido atualizado."
    echo "Verifique em: https://pjeoffice.trf3.jus.br"
    exit 1
fi
echo "Integridade verificada."

# Extract
echo "Extraindo..."
unzip -q "${TMP_DIR}/pjeoffice-pro.zip" -d "${TMP_DIR}"

# Remove bundled JRE (use system Java 11)
rm -rf "${TMP_DIR}/pjeoffice-pro/jre"
rm -f "${TMP_DIR}/pjeoffice-pro/LEIA-ME.TXT"
rm -f "${TMP_DIR}/pjeoffice-pro/.gitignore"

# Install
echo "Instalando em ${INSTALL_DIR}..."
rm -rf "${INSTALL_DIR}"
mv "${TMP_DIR}/pjeoffice-pro" "${INSTALL_DIR}"

# Create launch script
cat > "${INSTALL_DIR}/pjeoffice-pro.sh" << 'LAUNCHER'
#!/bin/bash
exec /usr/lib/jvm/java-11-openjdk/bin/java \
    -XX:+UseG1GC \
    -XX:MinHeapFreeRatio=3 \
    -XX:MaxHeapFreeRatio=3 \
    -Xms20m \
    -Xmx2048m \
    -Dpjeoffice_home="/usr/share/pjeoffice-pro/" \
    -Dffmpeg_home="/usr/share/pjeoffice-pro/" \
    -Dpjeoffice_looksandfeels="Metal" \
    -Dcutplayer4j_looksandfeels="Nimbus" \
    -jar /usr/share/pjeoffice-pro/pjeoffice-pro.jar
LAUNCHER
chmod 755 "${INSTALL_DIR}/pjeoffice-pro.sh"

# Create symlink
ln -sf "${INSTALL_DIR}/pjeoffice-pro.sh" /usr/bin/pjeoffice-pro

# Extract icon
unzip -p "${INSTALL_DIR}/pjeoffice-pro.jar" 'images/pje-icon-pje-feather.png' \
    > /usr/share/icons/hicolor/512x512/apps/pjeoffice.png 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

# Desktop entry
cat > /usr/share/applications/pje-office.desktop << 'DESKTOP'
[Desktop Entry]
Encoding=UTF-8
Name=PJeOffice Pro
GenericName=PJeOffice Pro - Assinador Digital
Exec=/usr/bin/pjeoffice-pro
Type=Application
Terminal=false
Categories=Office;
Comment=Assinador digital do CNJ para o PJe
Icon=pjeoffice
StartupWMClass=br-jus-cnj-pje-office-imp-PjeOfficeApp
DESKTOP

# Make ffmpeg executable if present
chmod +x "${INSTALL_DIR}/ffmpeg.exe" 2>/dev/null || true

echo ""
echo "=== PJeOffice Pro instalado com sucesso! ==="
echo ""
echo "Para iniciar:"
echo "  pjeoffice-pro"
echo ""
echo "Ou procure 'PJeOffice' no menu de aplicativos."
