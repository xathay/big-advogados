#!/usr/bin/env bash
# pjeoffice-install-helper.sh — Privileged installation helper for PJeOffice Pro
# Called via pkexec from the BigCertificados app
# Usage: pkexec bash /path/to/pjeoffice-install-helper.sh <extracted_dir>

set -euo pipefail

EXTRACTED_DIR="${1:?Uso: $0 <diretório_extraído>}"
INSTALL_DIR="/usr/share/pjeoffice-pro"

if [[ ! -d "${EXTRACTED_DIR}/pjeoffice-pro" ]]; then
    echo "ERRO: Diretório de extração inválido: ${EXTRACTED_DIR}/pjeoffice-pro"
    exit 1
fi

# Ensure Java 11 is available
if ! command -v /usr/lib/jvm/java-11-openjdk/bin/java &>/dev/null; then
    echo "LOG: Instalando jre11-openjdk..."
    pacman -S --noconfirm jre11-openjdk 2>&1
fi

echo "LOG: Removendo instalação anterior (se existir)..."
rm -rf "${INSTALL_DIR}"

echo "LOG: Copiando arquivos para ${INSTALL_DIR}..."
cp -a "${EXTRACTED_DIR}/pjeoffice-pro" "${INSTALL_DIR}"

# Remove bundled JRE
rm -rf "${INSTALL_DIR}/jre"
rm -f "${INSTALL_DIR}/LEIA-ME.TXT"
rm -f "${INSTALL_DIR}/.gitignore"

echo "LOG: Criando script de inicialização..."
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

echo "LOG: Criando link simbólico..."
ln -sf "${INSTALL_DIR}/pjeoffice-pro.sh" /usr/bin/pjeoffice-pro

echo "LOG: Extraindo ícone..."
if command -v unzip &>/dev/null; then
    mkdir -p /usr/share/icons/hicolor/512x512/apps
    unzip -p "${INSTALL_DIR}/pjeoffice-pro.jar" 'images/pje-icon-pje-feather.png' \
        > /usr/share/icons/hicolor/512x512/apps/pjeoffice.png 2>/dev/null || true
    gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
fi

echo "LOG: Criando entrada no menu..."
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

echo "OK: PJeOffice Pro instalado com sucesso!"
