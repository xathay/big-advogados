# BigCertificados

Gerenciador de certificados digitais para advogados e profissionais do Direito
no GNU/Linux — certificados A1 (PFX/P12) e A3 (token USB) em uma interface nativa
moderna.

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![GTK 4.0](https://img.shields.io/badge/GTK-4.0-4A86CF?logo=gnome&logoColor=white)
![Platform: GNU/Linux](https://img.shields.io/badge/Platform-GNU%2FLinux-FCC624?logo=linux&logoColor=black)
![Status: Em Desenvolvimento](https://img.shields.io/badge/Status-Em%20Desenvolvimento-orange?logo=git&logoColor=white)

> ⚠️ **Este projeto está em fase de desenvolvimento e testes.**
> Ainda não está pronto para uso em produção. Use por sua conta e risco.

---

## Visão Geral

BigCertificados é um aplicativo GTK4/Adwaita criado para o ecossistema do [BigLinux](https://biglinux.com.br) e do [BigCommunity](https://communitybig.org/) e distribuições Arch-based (EndeavourOS, CachyOS, Manjaro, Garuda Linux e outros). Ele simplifica o uso de certificados digitais no GNU/Linux — uma tarefa
historicamente complexa para quem precisa acessar sistemas judiciais eletrônicos
como PJe, PROJUDI e e-SAJ.

O aplicativo detecta automaticamente tokens USB, carrega certificados A1 em
formato PFX/P12, instala os certificados nos navegadores (Firefox, Chrome,
Chromium, Brave, Edge, Opera) via NSS, e oferece acesso rápido aos principais
sistemas judiciais eletrônicos do Brasil.

## Screenshots

| Detecção de Tokens USB | Certificado A1 |
|:---:|:---:|
| ![Tokens](docs/screenshots/tokens.png) | ![Certificado A1](docs/screenshots/certificado-a1.png) |

| Certificados Instalados | Sistemas Judiciais |
|:---:|:---:|
| ![Certificados](docs/screenshots/certificados.png) | ![Sistemas](docs/screenshots/sistemas.png) |

## Funcionalidades

### Certificados A3 (Token USB)

- **Detecção automática** de tokens USB via udev — conecte e o dispositivo
  aparece instantaneamente
- **Banco de dados** com 40+ modelos de tokens (Gemalto, SafeNet, Aladdin,
  Feitian, Watchdata, G&D)
- **Identificação do módulo PKCS#11** — verifica automaticamente se o driver
  correto está instalado
- **Leitura de certificados** via PIN — exibe titular, CPF, OAB, validade,
  emissor e uso do certificado
- **Hotplug** — monitora conexão e desconexão de dispositivos em tempo real

### Certificados A1 (PFX/P12)

- **Carregamento de arquivos** PFX e P12 com solicitação segura de senha
- **Visualização completa** — titular, CPF, OAB, validade, emissor, número de
  série, algoritmo de assinatura
- **Indicador de validade** — banner visual mostrando se o certificado está
  válido, próximo do vencimento ou expirado
- **Instalação nos navegadores** via NSS/certutil com um clique

### Integração com Navegadores

- Detecção automática de perfis Firefox, Chrome, Chromium, Brave, Edge e Opera
- Instalação de certificados A1 e módulos PKCS#11 (A3) em todos os perfis
  simultaneamente
- Utiliza `certutil` (libnss3-tools) para manipulação segura do banco NSS

### Sistemas Judiciais Eletrônicos

Acesso rápido com um clique aos principais sistemas:

| Sistema | Descrição |
|---------|-----------|
| PJe — TJBA | 1ª e 2ª Instância — Tribunal de Justiça da Bahia |
| PJe — TRF1 | 1ª e 2ª Instância — Tribunal Regional Federal |
| PJe — TRT5 | Tribunal Regional do Trabalho 5ª Região (Bahia) |
| PJe — TST | Tribunal Superior do Trabalho |
| PJe — CNJ | Portal do Conselho Nacional de Justiça |
| PROJUDI — TJBA | Processo Judicial Digital (sistema legado) |
| e-SAJ — TJBA | Sistema de Automação da Justiça — Consulta |

> 🔜 **Novos sistemas em breve!** Outros tribunais e sistemas processuais
> eletrônicos serão adicionados nas próximas versões.

### Assinador Digital de PDF

- **Assinatura digital** com certificado A1 (PFX/P12) em conformidade com
  ICP-Brasil
- **Padrão Adobe** — Adobe.PPKLite / adbe.pkcs7.detached / SHA-256, compatível
  com Adobe Acrobat, Foxit, Okular e validadores do gov.br
- **Carimbo visual** — selo de assinatura personalizado no rodapé do documento
  com dados do signatário (nome, CPF, OAB, Autoridade Certificadora e data)
- **Assinatura em lote** — assine múltiplos PDFs de uma só vez com barra de
  progresso
- **Opções de posicionamento** — carimbo na última página, primeira página ou
  em todas as páginas
- **Motivo e localidade** — campos personalizáveis para identificar o contexto
  da assinatura

### PJeOffice Pro

- **Detecção de instalação** com exibição da versão instalada
- **Instalador integrado** — baixa e instala diretamente do site oficial
  (CNJ/TRF3) com progresso visual e log em tempo real
- **Verificação de atualizações** — manual e automática (a cada 24h)
- **Acesso rápido** para abrir o PJeOffice Pro

### Brave — Configuração Automática para PJe Office

> 🆕 **Solução inédita desenvolvida pelo time BigLinux / BigCommunity.**
> Até então, não existia documentação ou solução pública para usar o PJe
> Office com o navegador Brave no GNU/Linux.

O Brave bloqueia, por padrão, a comunicação entre os sites dos tribunais e o
PJe Office (servidor local na porta 8801). Isso acontece porque o **Brave
Shields** impede requisições cross-origin para `localhost` com certificado
auto-assinado.

O BigCertificados resolve isso automaticamente com um clique:

1. **Desativa o Shields** nos domínios judiciais conhecidos (PJe, PROJUDI,
   e-SAJ, TST, TRT, TRF, CNJ)
2. **Importa o certificado** do PJe Office no banco NSS do navegador
3. O PJe Office passa a ser detectado normalmente pelo Brave

**Configuração manual (sem o BigCertificados):**

Se preferir configurar manualmente:

1. Abra o Brave e acesse `https://127.0.0.1:8801` — aceite o aviso de
   certificado
2. No site do PJe, clique no **ícone do Brave Shields** (leão) na barra de
   endereço → **Desative** o Shields
3. Recarregue a página — o PJe Office será detectado

### Segurança

- **Proteção por senha** — bloqueio opcional do aplicativo com senha definida
  pelo usuário
- **PBKDF2-HMAC-SHA256** com 600.000 iterações para hash de senha (padrão
  OWASP)
- **Limite de tentativas** — 3 tentativas antes de bloquear o acesso
- **Permissões restritas** — arquivo de senha com chmod 0600
- **Nenhum segredo em código** — senhas nunca são armazenadas em texto plano

### Interface

- **GTK4 + Libadwaita** — interface nativa que respeita o tema do sistema
  (claro/escuro)
- **5 abas organizadas** — Tokens, Certificado A1, Certificados, Sistemas e Assinador
- **Redimensionável** — funciona em telas pequenas (mínimo 360×400) até
  monitores widescreen
- **Rolagem inteligente** — todo o conteúdo é rolável quando a janela é
  reduzida

## Tokens Suportados

O BigCertificados reconhece automaticamente os seguintes modelos:

| Fabricante | Modelos |
|------------|---------|
| SafeNet (Thales) | eToken 5110, 5300, 7300, PRO 72K, PRO Java |
| Gemalto (Thales) | IDBridge CT40/CT710/K30/K50, IDPrime MD |
| Watchdata | ProxKey, GD e-Pass |
| Feitian | ePass 2003/3003, BioPass, Rockey, FIDO-NFC |
| Taglio | DinKey |
| GD Burti | StarSign CUT S |
| Oberthur (IDEMIA) | IDOne Cosmo V7 |
| Bit4id | miniLector EVO, Digital-DNA Key |
| Athena | ASEDrive IIIe, ASECard Crypto |
| ACS | ACR38U, ACR39U |
| Cherry | ST-2000, SmartTerminal |
| SCM Microsystems | SCR 3310, SCR 3500 |
| HID Global | OMNIKEY 3021, 5021 CL |
| Yubico | YubiKey 5 NFC, 5C, 5Ci |
| Kryptus | kNET HSM Token |
| AET Europe | SafeSign Token |

Certificadoras brasileiras compatíveis:
**Certisign, Serasa Experian, Soluti, Valid Certificadora, Safeweb, AC OAB**

### Drivers PKCS#11 (Bibliotecas de Token)

O BigCertificados **não instala** drivers proprietários automaticamente. Ele
apenas detecta se o driver correto já está instalado no sistema e, caso
contrário, sugere o pacote AUR adequado para o modelo de token detectado.

**Fluxo de funcionamento:**

1. O token USB é conectado e identificado pelo `vendor_id`/`product_id`
2. O app consulta o banco de dados interno (~48 modelos) para identificar o
   driver PKCS#11 necessário (ex: `libeToken.so`, `libaetpkcs11.so`)
3. Verifica se o arquivo `.so` existe nos caminhos conhecidos do sistema
4. Se não encontrar, sugere o pacote AUR correspondente para instalação

**Pacotes de drivers disponíveis no AUR:**

| Driver | Pacote | Origem | Tokens |
|--------|--------|--------|--------|
| SafeNet Authentication Client | `sac-core` | AUR | eToken 5110/5300/7300, IDPrime MD |
| SafeSign Identity Client | `safesignidentityclient` | AUR | Tokens AET Europe, G&D StarSign |
| WatchData ProxKey | `watchdata-proxkey` | AUR | ProxKey, GD e-Pass |
| OpenSC (genérico) | `opensc` | pacman | Feitian, Athena, Bit4id, Cherry, ACS, HID, Yubico |

> **Nota:** O pacote `opensc` (disponível no pacman) cobre a maioria dos tokens
> genéricos. Instale com `sudo pacman -S opensc`. Para tokens SafeNet e
> Gemalto/Thales, use `yay -S sac-core`.

## Arquitetura

```
comm-lawyers/
├── src/                          # Código-fonte principal
│   ├── main.py                   # Ponto de entrada
│   ├── application.py            # Adw.Application (instância única)
│   ├── window.py                 # Janela principal (Adw.ApplicationWindow)
│   │
│   ├── ui/                       # Interface GTK4/Adwaita
│   │   ├── token_detect_view.py  # Detecção de tokens USB
│   │   ├── a1_view.py            # Carregamento de certificados A1
│   │   ├── certificate_view.py   # Visualização detalhada de certificados
│   │   ├── signer_view.py        # Assinador digital de PDFs
│   │   ├── systems_view.py       # Sistemas judiciais e PJeOffice Pro
│   │   ├── pin_dialog.py         # Diálogo de PIN para tokens A3
│   │   ├── lock_screen.py        # Tela de bloqueio por senha
│   │   ├── password_settings.py  # Configuração de senha do app
│   │   └── pjeoffice_installer.py # Instalador do PJeOffice Pro
│   │
│   ├── certificate/              # Lógica de certificados (sem imports de UI)
│   │   ├── a1_manager.py         # Gerenciamento de certificados A1 (PFX)
│   │   ├── a3_manager.py         # Gerenciamento de certificados A3 (PKCS#11)
│   │   ├── parser.py             # Parser X.509 (cryptography)
│   │   ├── pdf_signer.py         # Assinatura digital de PDFs (endesive)
│   │   ├── stamp.py              # Gerador de carimbo visual (Pillow)
│   │   └── token_database.py     # Banco de dados de tokens USB
│   │
│   ├── browser/                  # Integração com navegadores
│   │   ├── browser_detect.py     # Detecção de navegadores e perfis
│   │   └── nss_config.py         # Configuração NSS via certutil
│   │
│   └── utils/                    # Utilitários
│       ├── app_lock.py           # Hash e verificação de senha (PBKDF2)
│       ├── udev_monitor.py       # Monitoramento USB via pyudev
│       ├── updater.py            # Verificação de atualizações PJeOffice
│       └── xdg.py                # Diretórios XDG
│
├── data/
│   ├── icons/                    # Ícones do aplicativo (SVG)
│   ├── udev/                     # Regras udev para tokens
│   └── com.bigcertificados.desktop  # Entrada no menu do sistema
│
├── scripts/                      # Scripts auxiliares
│   ├── install-pjeoffice-pro.sh  # Instalador PJeOffice Pro
│   └── pjeoffice-install-helper.sh
│
├── docs/
│   └── manual-usuario.md         # Manual do usuário
│
└── requirements.txt              # Dependências Python
```

## Requisitos

| Componente | Versão | Uso |
|------------|--------|-----|
| Python | ≥ 3.10 | Runtime |
| GTK | 4.0 | Toolkit de interface |
| libadwaita | ≥ 1.0 | Widgets Adwaita |
| PyGObject | ≥ 3.46 | Bindings GObject para Python |
| PyKCS11 | ≥ 1.5.11 | Comunicação PKCS#11 com tokens |
| pyudev | ≥ 0.24.1 | Monitoramento USB via udev |
| cryptography | ≥ 41.0 | Parsing X.509 e PFX |
| endesive | ≥ 2.17 | Assinatura digital de PDFs |
| pikepdf | ≥ 8.0 | Manipulação de PDFs |
| Pillow | ≥ 10.0 | Geração de carimbo visual |
| libnss3-tools | — | certutil para navegadores |
| pcsclite / ccid | — | Serviço de smart card para tokens A3 |

## Instalação

### Arch Linux / BigLinux (recomendado)

```bash
# Instale as dependências do sistema
sudo pacman -S python python-gobject gtk4 libadwaita python-pykcs11 \
  python-pyudev python-cryptography python-pikepdf python-reportlab \
  python-pillow python-asn1crypto python-oscrypto nss pcsclite ccid opensc

# Instale o endesive (assinador de PDFs)
pip install --user endesive

# Habilite o serviço de smart card
sudo systemctl enable --now pcscd.service

# Clone o repositório
git clone https://github.com/xathay/big-advogados.git
cd big-advogados

# Execute
python -m src.main
```

### Regras udev (acesso ao token sem sudo)

```bash
sudo cp data/udev/70-crypto-tokens.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

O usuário deve estar no grupo `plugdev`:

```bash
sudo usermod -aG plugdev $USER
```

Faça logout e login para aplicar.

## Configuração

BigCertificados armazena seus dados seguindo a especificação XDG Base Directory:

| Caminho | Descrição |
|---------|-----------|
| `~/.config/bigcertificados/settings.json` | Preferências do usuário |
| `~/.config/bigcertificados/applock.json` | Hash da senha de proteção (chmod 0600) |

## Uso

Inicie pelo menu de aplicativos ou via terminal:

```bash
python -m src.main
```

1. **Tokens USB** — conecte seu token e ele será detectado automaticamente.
   Clique no dispositivo para inserir o PIN e visualizar os certificados.
2. **Certificados A1** — clique em "Selecionar Arquivo PFX" para carregar um
   certificado A1. Insira a senha e visualize os detalhes.
3. **Navegadores** — use o menu → "Configurar Navegadores" para instalar
   certificados nos navegadores detectados.
4. **Sistemas** — acesse os sistemas judiciais com um clique na aba Sistemas.
5. **Assinador** — selecione PDFs, escolha o certificado A1 e assine com
   carimbo visual no rodapé do documento.
6. **Proteção** — ative a proteção por senha em menu → "Proteção por Senha".

---

## Contribuindo

Contribuições são bem-vindas! Abra uma issue ou envie um pull request.

1. Faça um fork do repositório
2. Crie sua branch (`git checkout -b feature/minha-feature`)
3. Faça commit das alterações (`git commit -m 'Adiciona minha feature'`)
4. Envie para a branch (`git push origin feature/minha-feature`)
5. Abra um Pull Request

## Licença

Este projeto está licenciado sob a Licença MIT — veja o arquivo
[LICENSE](LICENSE) para detalhes.

## Créditos

Desenvolvido para a comunidade [BigCommunity](https://communitybig.org/) e
[BigLinux](https://www.biglinux.com.br/).

Feito com cuidado para a comunidade jurídica brasileira no GNU/Linux
