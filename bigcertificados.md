# BigCertificados — Planejamento de Construção

## 1. Visão Geral

Gerenciador de certificados digitais para advogados brasileiros, com foco em:
- **Certificados A3** (tokens USB / smartcards) — detecção automática, leitura de certificados
- **Certificados A1** (arquivos PFX/P12) — importação e visualização (fase 2)
- **Integração com navegadores** — Firefox e Chromium/Chrome
- **Acesso a sistemas judiciais** — PJE TJBA (1ª e 2ª instância), PJE TRF1, PROJUDI

## 2. Stack Tecnológica

| Componente          | Tecnologia                          |
|---------------------|-------------------------------------|
| Linguagem           | Python 3.11+                        |
| UI Framework        | GTK4 + libadwaita                   |
| PKCS#11             | PyKCS11                             |
| Certificados X.509  | cryptography (pyca)                 |
| Detecção USB        | pyudev                              |
| PC/SC               | pcscd + ccid                        |
| NSS (browsers)      | certutil / modutil (nss-tools)      |
| Empacotamento       | pacman (PKGBUILD para Arch/BigLinux)|

## 3. Fases de Desenvolvimento

### Fase 1 — Detecção de Tokens e Visualização de Certificados A3 (ATUAL)

1. **Base de dados de tokens** — mapeamento USB vendor:product → módulo PKCS#11
2. **Monitor udev** — detecção automática de inserção/remoção de token
3. **Gerenciador PKCS#11** — comunicação com token, listagem de certificados
4. **Parser X.509** — extração de dados (nome, CPF, OAB, validade, CA emissora)
5. **Interface GTK4** — janela principal com detecção de token e visualização
6. **Regras udev** — permissões automáticas sem sudo
7. **Configuração NSS** — registro automático do módulo PKCS#11 no Firefox e Chrome

### Fase 2 — Certificados A1 (PFX)

1. Importação de arquivo PFX/P12
2. Visualização de detalhes do certificado
3. Verificação de validade e cadeia de confiança
4. Instalação no NSS database do navegador

### Fase 3 — Integração com Sistemas Judiciais

1. Links rápidos para PJE TJBA 1ª instância, 2ª instância, TRF1
2. Verificação de compatibilidade do certificado com cada sistema
3. Diagnóstico de problemas comuns (Java, PJeOffice, etc.)

### Fase 4 — Polimento e Distribuição

1. PKGBUILD para Arch Linux / BigLinux / Manjaro
2. Ícones e .desktop file
3. Flatpak (opcional)
4. Documentação do usuário

## 4. Estrutura do Projeto

```
certificateManager/
├── src/
│   ├── main.py                    # Entry point, GtkApplication
│   ├── application.py             # Classe GtkApplication
│   ├── window.py                  # Janela principal (AdwApplicationWindow)
│   ├── certificate/
│   │   ├── __init__.py
│   │   ├── a3_manager.py          # Gerenciamento PKCS#11 tokens
│   │   ├── a1_manager.py          # Gerenciamento PFX/P12 (Fase 2)
│   │   ├── parser.py              # Parse de certificados X.509
│   │   └── token_database.py      # Base de tokens USB → módulo PKCS#11
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── nss_config.py          # Configuração NSS (Firefox + Chrome)
│   │   └── browser_detect.py      # Detecção de navegadores instalados
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── certificate_view.py    # Painel de detalhes do certificado
│   │   ├── token_detect_view.py   # Tela de detecção/status do token
│   │   └── systems_view.py        # Links para sistemas judiciais
│   └── utils/
│       ├── __init__.py
│       ├── udev_monitor.py        # Monitor de dispositivos USB
│       └── xdg.py                 # Paths XDG
├── data/
│   ├── icons/
│   │   └── cert-manager.svg
│   ├── udev/
│   │   └── 70-crypto-tokens.rules # Regras udev para tokens
│   └── com.bigcertificados.desktop
├── requirements.txt
├── bigcertificados.md             # Este arquivo
└── README.md
```

## 5. Base de Tokens Brasileiros

### Tokens USB (lista extensiva)

| Fabricante          | Modelo                    | USB VID:PID   | Módulo PKCS#11                          |
|---------------------|---------------------------|---------------|-----------------------------------------|
| SafeNet (Thales)    | eToken 5110               | 0529:0620     | libeToken.so                            |
| SafeNet (Thales)    | eToken 5110+ FIPS         | 0529:0620     | libeToken.so                            |
| SafeNet (Thales)    | eToken 5300               | 0529:0621     | libeToken.so                            |
| SafeNet (Thales)    | eToken 5300-C             | 0529:0621     | libeToken.so                            |
| SafeNet (Thales)    | eToken 7300               | 0529:0622     | libeToken.so                            |
| SafeNet (Thales)    | eToken PRO 72K            | 0529:0600     | libeTPkcs11.so                          |
| SafeNet (Thales)    | eToken PRO (Java)         | 0529:0514     | libeTPkcs11.so                          |
| Gemalto (Thales)    | IDBridge CT40             | 08e6:3437     | libIDPrimePKCS11.so                     |
| Gemalto (Thales)    | IDBridge CT710            | 08e6:3438     | libIDPrimePKCS11.so                     |
| Gemalto (Thales)    | IDBridge K30              | 08e6:34ec     | libIDPrimePKCS11.so                     |
| Gemalto (Thales)    | IDBridge K50              | 08e6:3479     | libIDPrimePKCS11.so                     |
| Gemalto (Thales)    | IDPrime MD 830            | 08e6:3438     | libIDPrimePKCS11.so                     |
| Gemalto (Thales)    | IDPrime MD 840            | 08e6:3438     | libIDPrimePKCS11.so                     |
| Watchdata           | ProxKey                   | 058f:9540     | libwdpkcs.so                            |
| Watchdata           | GD e-Pass                 | 058f:9520     | libwdpkcs.so                            |
| Feitian             | ePass 2003                | 096e:0807     | libepsng_p11.so                         |
| Feitian             | ePass 3003 Auto           | 096e:0808     | libepsng_p11.so                         |
| Feitian             | BioPass FIDO              | 096e:060b     | libepsng_p11.so                         |
| Feitian             | Rockey 200                | 096e:0305     | libepsng_p11.so                         |
| Feitian             | ePass FIDO-NFC            | 096e:0854     | libepsng_p11.so                         |
| Taglio              | DinKey                    | 04b9:0300     | libneloersen.so                         |
| GD Burti            | StarSign CUT S            | 04e6:5816     | libgdpkcs11.so                          |
| GD Burti            | StarSign CUT S 3.5        | 04e6:5816     | libgdpkcs11.so                          |
| Oberthur (IDEMIA)   | IDOne Cosmo V7            | 08e6:34ec     | libOcsCryptoki.so                       |
| AET Europe          | SafeSign (smartcard)      | —             | libaetpkcs11.so                         |
| Pronova             | eToken Pronova            | 0529:0620     | libeToken.so (rebranded SafeNet)        |
| Bit4id              | miniLector EVO            | 25dd:3111     | libbit4ipki.so                          |
| Bit4id              | Digital-DNA Key           | 25dd:3111     | libbit4xpki.so                          |
| Athena              | ASEDrive IIIe             | 0dc3:0802     | libASEP11.so                            |
| Athena              | ASECard Crypto            | 0dc3:1004     | libASEP11.so                            |
| Kryptus             | kNET                      | —             | libkNET_pkcs11.so                       |
| ACS                 | ACR38U                    | 072f:90cc     | opensc-pkcs11.so (via OpenSC)           |
| ACS                 | ACR39U                    | 072f:2200     | opensc-pkcs11.so (via OpenSC)           |
| Cherry              | ST-2000                   | 046a:003e     | opensc-pkcs11.so (via OpenSC)           |
| Cherry              | SmartTerminal             | 046a:0070     | opensc-pkcs11.so (via OpenSC)           |
| Alcor Micro         | AU9540                    | 058f:9540     | opensc-pkcs11.so (via OpenSC)           |
| SCM Microsystems    | SCR 3310                  | 04e6:5116     | opensc-pkcs11.so (via OpenSC)           |
| SCM Microsystems    | SCR 3500                  | 04e6:5410     | opensc-pkcs11.so (via OpenSC)           |
| Broadcom            | 5880                      | 0a5c:5800     | opensc-pkcs11.so (via OpenSC)           |
| C3PO                | LTC31                     | 0783:0003     | opensc-pkcs11.so (via OpenSC)           |
| HID Global          | OMNIKEY 3021              | 076b:3021     | opensc-pkcs11.so (via OpenSC)           |
| HID Global          | OMNIKEY 5021              | 076b:5321     | opensc-pkcs11.so (via OpenSC)           |
| Yubico              | YubiKey 5 NFC             | 1050:0407     | opensc-pkcs11.so / yubico-piv-tool      |
| Yubico              | YubiKey 5C                | 1050:0407     | opensc-pkcs11.so / yubico-piv-tool      |

### Caminhos comuns dos módulos PKCS#11 no Arch Linux

| Módulo                  | Caminhos possíveis                                             |
|-------------------------|----------------------------------------------------------------|
| libeToken.so            | /usr/lib/libeToken.so, /usr/lib64/libeToken.so                 |
| libeTPkcs11.so          | /usr/lib/libeTPkcs11.so                                        |
| libIDPrimePKCS11.so     | /usr/lib/libIDPrimePKCS11.so, /usr/lib/x86_64-linux-gnu/      |
| libwdpkcs.so            | /usr/lib/libwdpkcs.so, /usr/lib/watchdata/lib/                 |
| libepsng_p11.so         | /usr/lib/libepsng_p11.so, /opt/ePass2003/                      |
| libneloersen.so         | /usr/lib/libneloersen.so                                       |
| libgdpkcs11.so          | /usr/lib/libgdpkcs11.so                                        |
| libOcsCryptoki.so       | /usr/lib/libOcsCryptoki.so                                     |
| libaetpkcs11.so         | /usr/lib/libaetpkcs11.so                                       |
| libbit4ipki.so          | /usr/lib/libbit4ipki.so, /usr/lib/bit4id/                      |
| libASEP11.so            | /usr/lib/libASEP11.so                                          |
| opensc-pkcs11.so        | /usr/lib/opensc-pkcs11.so, /usr/lib/pkcs11/opensc-pkcs11.so   |

## 6. Sistemas Judiciais Eletrônicos

| Sistema     | URL                                              | Observação              |
|-------------|--------------------------------------------------|-------------------------|
| PJE TJBA 1ª | https://pje.tjba.jus.br                          | 1ª Instância            |
| PJE TJBA 2ª | https://pje2g.tjba.jus.br                        | 2ª Instância            |
| PJE TRF1    | https://pje1g.trf1.jus.br                        | Justiça Federal 1ª Reg. |
| PJE TRF1 2ª | https://pje2g.trf1.jus.br                        | TRF1 2ª Instância       |
| PROJUDI     | https://projudi.tjba.jus.br                      | Sistema legado          |
| e-SAJ       | https://esaj.tjba.jus.br                         | Consulta processual     |

## 7. Dependências do Sistema (Arch Linux)

```bash
# Pacotes oficiais
sudo pacman -S python python-gobject gtk4 libadwaita
sudo pacman -S pcsclite ccid opensc nss

# Pacotes Python (pip/venv)
pip install PyKCS11 pyudev cryptography

# Serviço pcscd
sudo systemctl enable --now pcscd.service
```

## 8. Fluxo do Usuário

```
1. Instala o app
2. Conecta o token USB
3. App detecta o token automaticamente
4. App identifica o modelo e localiza o módulo PKCS#11
5. Solicita o PIN ao usuário
6. Lista os certificados no token
7. Exibe detalhes: nome, CPF, OAB, validade, AC emissora
8. Opção: registrar módulo no Firefox/Chrome automaticamente
9. Opção: abrir sistema judicial diretamente
```

## 9. Notas Técnicas

- O `pcscd` (PC/SC daemon) é requisito para comunicação com tokens/smartcards
- O driver `ccid` cobre a maioria dos leitores USB CCID-compliant
- O OpenSC fornece um módulo PKCS#11 genérico que suporta muitos cartões
- Tokens SafeNet/Thales requerem driver proprietário (SAC / SafeNet Authentication Client)
- Tokens Feitian requerem o ePass2003 middleware
- Tokens Watchdata requerem o WatchKey middleware
- A configuração do NSS database é por perfil do navegador (Firefox: ~/.mozilla/firefox/*.default/)
- Chrome/Chromium usa o NSS database em ~/.pki/nssdb/
