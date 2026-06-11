# Big Advogados — Manual de Uso

> Versão: **1.3.0** · Plataforma alvo: **CachyOS / Arch Linux + GNOME**
>
> Este manual é orientado ao uso prático. Para detalhes técnicos de
> arquitetura, ver `README.md`. Para incidentes de campo, ver
> `docs/incidentes.md`. Para o protocolo WebSigner em profundidade, ver
> `docs/websigner-technical-guide.md`.

---

## Índice

1. [O que é o Big Advogados](#1-o-que-é-o-big-advogados)
2. [Glossário rápido](#2-glossário-rápido)
3. [Instalação](#3-instalação)
4. [Tour pelo painel principal](#4-tour-pelo-painel-principal)
5. [Fluxo completo: protocolar no e-SAJ TJSP com token A3](#5-fluxo-completo-protocolar-no-e-saj-tjsp-com-token-a3)
6. [Fluxo alternativo: protocolar com certificado A1 (.p12)](#6-fluxo-alternativo-protocolar-com-certificado-a1-p12)
7. [Assinar um PDF avulso](#7-assinar-um-pdf-avulso)
8. [VidaaS Connect — certificado em nuvem](#8-vidaas-connect--certificado-em-nuvem)
9. [PJeOffice Pro — quando e como](#9-pjeoffice-pro--quando-e-como)
10. [Diagnóstico: quando algo não funciona](#10-diagnóstico-quando-algo-não-funciona)
11. [Perguntas frequentes](#11-perguntas-frequentes)

---

## 1. O que é o Big Advogados

O **Big Advogados** é uma "estação de trabalho jurídica" para advogados que
atuam no Brasil e usam Linux. Em uma única janela, ele resolve:

- **Reconhecer** seu certificado digital (token A3 USB, arquivo A1 .p12 ou nuvem
  VidaaS) sem você precisar instalar drivers manualmente
- **Configurar o Firefox** para assinar peças no **e-SAJ TJSP** e outros sistemas
  que usam Web Signer — sem precisar de extensão proprietária da Softplan/Lacuna
- **Assinar PDFs** com carimbo visível e página de certificação opcional, no
  padrão ICP-Brasil
- **Acessar os tribunais** (PJe, e-SAJ, eProc, PROJUDI) com 1 clique
- **Diagnosticar problemas** quando o token não aparece, o navegador não enxerga
  o certificado, o serviço pcscd parou, etc.

A motivação principal: hoje, no Linux, **o componente oficial do Web Signer
(binário da Softplan) não funciona**. O Big Advogados é a única forma estável
de protocolar no e-SAJ TJSP usando Linux.

---

## 2. Glossário rápido

| Termo | O que significa, na prática |
|-------|------------------------------|
| **A1** | Certificado digital em arquivo `.p12` ou `.pfx`. Tem senha. Funciona sem token. |
| **A3** | Certificado digital em token USB físico (ex.: G&D StarSign, SafeNet eToken, GemSafe). Tem PIN. |
| **ICP-Brasil** | Infraestrutura nacional de chaves públicas. Todo certificado válido para o Judiciário brasileiro é ICP-Brasil. |
| **AC** | Autoridade Certificadora — quem emitiu seu certificado (Serasa, Soluti, AC-Certisign, etc.) |
| **e-SAJ** | Sistema eletrônico do TJSP, TJBA e outros tribunais estaduais |
| **PJe** | Sistema do CNJ, usado por TJMG, TRTs, TST, TJDFT, entre outros |
| **eProc** | Sistema usado por TRF2, TRF4, TJRS — substituiu o PJe nesses tribunais |
| **PROJUDI** | Sistema do TJPR principalmente |
| **Web Signer** | Componente que o navegador usa para falar com o certificado. O Big Advogados implementa um Web Signer próprio, sem precisar do binário da Softplan. |
| **Ponte WebPKI** | Extensão Firefox que o Big Advogados instala para o e-SAJ enxergar o Web Signer |
| **Firefox ESR** | Versão "Extended Support Release" do Firefox. Aceita extensões não-assinadas em modo permanente. |
| **VidaaS** | Certificado A3 emitido pela Valid Certificadora, usado por celular (app VidaaS) sem token físico |

---

## 3. Instalação

### Pré-requisitos (CachyOS / Arch)

```bash
# Componentes do sistema (oficiais)
sudo pacman -S --needed \
  python-pykcs11 python-pyudev python-cryptography \
  python-pikepdf python-reportlab python-asn1crypto \
  python-oscrypto python-qrcode \
  pcsclite ccid opensc nss zenity

# Componente do AUR
paru -S --needed python-endesive
```

### Compilar e instalar

```bash
git clone https://github.com/xathay/big-advogados.git
cd big-advogados
makepkg -f
sudo pacman -U big-certificados-1.3.0-1-any.pkg.tar.zst
sudo udevadm control --reload && sudo udevadm trigger
sudo systemctl enable --now pcscd.socket
```

> ✅ **Confirmação rápida**: rode `big-certificados` no terminal — a janela do app
> deve abrir. Ou procure por **"Big Advogados"** no menu de aplicações do GNOME.

### O que foi instalado onde

| Local | O que tem |
|-------|-----------|
| `/usr/lib/big-certificados/src/` | Código Python da aplicação |
| `/usr/bin/big-certificados` | Atalho de linha de comando |
| `/usr/share/applications/com.bigcertificados.desktop` | Entrada do menu GNOME |
| `/usr/lib/udev/rules.d/70-crypto-tokens.rules` | Regras para acesso ao token sem sudo |
| `~/.local/share/big-certificados/` | Configuração do WebSigner (`websigner.json`) |
| `~/.local/state/big-certificados/websigner-host.log` | Log do native host (útil para diagnóstico) |
| `~/Certificados/` (configurável via `save_dir` no `websigner.json`) | Cópia dos `.p12` importados pelo Web Signer |

---

## 4. Tour pelo painel principal

Ao abrir o Big Advogados, você vê uma **sidebar** à esquerda com as áreas
principais:

```
┌─────────────────────────────────────────────────────────┐
│ Big Advogados                                           │
├──────────────────┬──────────────────────────────────────┤
│ ▸ Início         │  [Conteúdo da seção selecionada]     │
│                  │                                      │
│ Certificados     │                                      │
│ ▸ Certificados   │                                      │
│ ▸ VidaaS Connect │                                      │
│                  │                                      │
│ Ferramentas      │                                      │
│ ▸ Assinador      │                                      │
│ ▸ Sistemas Jud.  │                                      │
│                  │                                      │
│ Configuração     │                                      │
│ ▸ Dependências   │                                      │
│ ▸ Navegadores    │                                      │
└──────────────────┴──────────────────────────────────────┘
```

**O que cada área faz:**

- **Início** — dashboard com resumo de certificados detectados e atalhos rápidos
- **Certificados** — lista unificada de todos os certificados detectados (A1 + A3)
  com validade, CPF, OAB e emissor
- **VidaaS Connect** — assistente para conectar com o certificado em nuvem da Valid
- **Assinador de PDFs** — wizard de 4 passos para assinar PDFs avulsos
- **Sistemas Judiciais** — atalhos para tribunais + **configuração do WebSigner**
  (aqui é onde mora o e-SAJ TJSP) + PJeOffice Pro + drivers de tokens + navegadores
- **Dependências** — diagnóstico das bibliotecas e serviços necessários
- **Navegadores** — onde cada navegador detectado está instalado e em que perfil

---

## 5. Fluxo completo: protocolar no e-SAJ TJSP com token A3

Este é o fluxo mais comum. Acompanhe **uma única vez** para deixar tudo
configurado; nas próximas vezes, você pula direto para o passo 5.4.

### 5.1 Plugar o token A3

Pluge o token USB. No painel **Sistemas → WebSigner — e-SAJ**, a 3ª linha de
status (ícone de pendrive) deve mostrar:

> ✅ **Token A3 detectado: [vendor] [modelo]**
> Pronto para assinar — o e-SAJ vai pedir o PIN ao confirmar

Se mostrar **"Nenhum token A3 conectado"**, vá para [§10.1](#101-token-não-aparece).

### 5.2 Configurar o WebSigner (primeira vez)

No mesmo painel **WebSigner — e-SAJ**, clique em **Configurar / Reinstalar**.

Vai aparecer um diálogo "Configurar e-SAJ — TJSP". Clique em **Configurar**.
O log à direita mostra duas etapas:

1. **Etapa 1/2 — Native messaging host**: registra o Big Advogados como
   "conector de assinatura" nos navegadores instalados (Firefox, Chrome,
   Chromium, Brave). Você vai ver `✓ /home/.../.mozilla/native-messaging-hosts`,
   `✓ /home/.../.config/google-chrome/...`, etc.

2. **Etapa 2/2 — Bridge extension (Firefox profiles)**: instala uma extensão
   leve no Firefox que se faz passar pela extensão Web Signer (que não existe
   mais no Mozilla AMO). Você vai ver os nomes dos seus perfis Firefox
   (ex.: `vdox86rc.default`, `j7nfd8ui.default-release`).

No fim, aparece o checklist "Próximos passos". Pode fechar.

> ⚠️ **Atenção sobre o Firefox**: se você usa o **Firefox normal** (versão
> "release"), a extensão da ponte é instalada como **temporária** e some
> quando você reinicia o Firefox. Soluções:
>
> - **Recomendado**: usar **Firefox ESR** (`paru -S firefox-esr`) — aceita a
>   ponte permanente
> - **Alternativo**: cada vez que reiniciar o Firefox, voltar aqui e clicar
>   "Configurar / Reinstalar" antes de abrir o e-SAJ

### 5.3 Abrir o e-SAJ e fazer login

No mesmo painel, clique em **"Abrir e-SAJ TJSP (login)"**. Isso abre o Firefox
na página `esaj.tjsp.jus.br/sajcas/login`.

Na página de login, clique em **"Certificado digital"**. A página mostra um
dropdown com os certificados disponíveis. Você deve ver o seu (CN do
certificado, ex.: "FULANO DE TAL:00000000000").

Escolha o certificado e clique em **Confirmar**.

### 5.4 Quando o PIN é solicitado

Ao confirmar o login (ou ao assinar uma peça depois), aparece um **diálogo
zenity** com a mensagem:

> 🔐 **Big Advogados — PIN do Token A3**
> Digite o PIN do token:
> [Nome do token]

Digite o PIN do seu token (o mesmo que você usava no Windows com o Safenet/
SAC-CORE). Clique em **OK**.

Importante:
- O PIN é solicitado **apenas uma vez por sessão do Firefox**. Você não vai ter
  que digitar de novo a cada assinatura na mesma sessão.
- Se você digitar errado, o token bloqueia após N tentativas (geralmente 3).
  Em caso de bloqueio, só o desbloqueio com a senha PUK resolve.
- A sessão do token é fechada automaticamente quando o Firefox encerra a
  comunicação com o Big Advogados.

### 5.5 Protocolar a peça

A partir daqui é o e-SAJ normal:
- Menu **"Peticionamento Eletrônico"** → **"Petição Inicial / Intermediária"**
- Preencha os campos do processo
- Anexe o PDF da peça (já assinado ou não — o e-SAJ assina antes de protocolar
  se necessário)
- Clique em **Protocolar**

Se aparecer o pedido de assinatura no momento de protocolar, é o mesmo
diálogo de PIN da seção anterior — mas como o PIN já foi cacheado, geralmente
nem aparece de novo.

> ✅ **Sinal de sucesso**: o e-SAJ exibe o **protocolo gerado** e o **recibo**
> em PDF para download. Salve esse recibo!

---

## 6. Fluxo alternativo: protocolar com certificado A1 (.p12)

Se você não usa token (A3) — só tem o arquivo `.p12` — o fluxo é parecido:

### 6.1 Configurar o A1 no painel

**Sistemas → WebSigner — e-SAJ** → clique em **"Certificado A1 (.p12) — opcional"** →
um diálogo de seleção de arquivo aparece. Aponte para o seu `.p12` ou `.pfx`.

> O caminho do arquivo é salvo em `~/.local/share/big-certificados/websigner.json`.

### 6.2 Login no e-SAJ

Mesmo procedimento da [§5.3](#53-abrir-o-e-saj-e-fazer-login). A diferença é que,
ao escolher o certificado e confirmar, **o diálogo pede a senha do arquivo .p12**
(não um PIN de token):

> 🔐 **Big Advogados — Senha do Certificado**
> Digite a senha do certificado:
> [nome-do-arquivo.p12]

Digite a senha. Pronto.

> 💡 **Dica**: se você tem **A1 e A3 ao mesmo tempo**, ambos aparecem no
> dropdown do e-SAJ. Escolha conforme a peça. Trocar é só selecionar o outro
> no dropdown.

---

## 7. Assinar um PDF avulso

Quando você precisa assinar um PDF **fora do navegador** (ex.: um anexo, uma
declaração, um documento que será juntado depois), use o **Assinador de PDFs**.

### 7.1 Wizard de 4 passos

**Sidebar → Assinador de PDFs**:

1. **PDF de entrada** — clique e selecione o arquivo
2. **Certificado** — escolha entre A1 (escolhe `.p12` + senha), A3 (escolhe o
   token) ou VidaaS (se já estiver conectado)
3. **Carimbo visível** — opcional. Configure posição (canto inferior direito é
   o padrão), texto e tamanho. Pode adicionar uma página de certificação extra
   ao fim do documento listando emissor, CPF, OAB e validade
4. **Assinar** — escolha onde salvar o PDF assinado e clique em **Assinar**

### 7.2 Validação no Papers / Adobe Reader

O **GNOME Papers** (visualizador padrão do GNOME) valida as assinaturas se
você importar a cadeia ICP-Brasil. No wizard, há um botão **"Configurar
Papers"** que faz a importação.

No **Adobe Acrobat Reader** (Windows/Mac) a validação é automática — a
cadeia ICP-Brasil já vem instalada por padrão.

---

## 8. VidaaS Connect — certificado em nuvem

A **Valid Certificadora** emite certificados A3 que não precisam de token
físico: você instala o app **VidaaS** no celular e o certificado vive no
celular. A comunicação acontece por leitura QR + push notification.

### 8.1 Pré-requisitos

Na primeira vez, o painel **VidaaS Connect** verifica e instala os
pré-requisitos automaticamente (OpenSC para comunicação, pcscd ativo, etc.).

### 8.2 Fluxo de conexão

1. Abra o app VidaaS no celular
2. No Big Advogados, clique em **"Buscar token VidaaS"**
3. Aparece um QR code → leia com o app VidaaS no celular
4. Confirme no celular
5. O Big Advogados detecta o token virtual e mostra os dados do certificado

A partir daqui, o VidaaS aparece junto dos outros certificados no e-SAJ e no
Assinador de PDFs.

---

## 9. PJeOffice Pro — quando e como

O **PJeOffice Pro** é o componente do CNJ para assinar peças no **PJe**
(diferente do e-SAJ). Roda em Java Swing. O Big Advogados:

- Detecta se ele já está instalado
- Oferece instalação automática se não estiver
- **Resolve o problema de HiDPI** em monitores de alta resolução — sem isso,
  a janela do PJeOffice aparece minúscula em telas 4K ou em escala fracionária
  (1.25x, 1.333x, 1.5x). O launcher detecta automaticamente o DPI correto via
  3 métodos (Xft.dpi, Mutter DBus, EDID físico)

**Quando você precisa do PJeOffice e não do WebSigner?** Sempre que o tribunal
usa **PJe (do CNJ)** — TJMG, TRTs, TST, TJDFT, alguns TRFs antigos. O e-SAJ
(TJSP, TJBA, etc.) usa **WebSigner**, não PJeOffice.

---

## 10. Diagnóstico: quando algo não funciona

### 10.1 Token não aparece

**Sintoma**: na linha "Token A3", aparece "Nenhum token A3 conectado" mesmo
com o token plugado.

**Diagnóstico**:

```bash
# 1. O sistema vê o USB?
lsusb | grep -E "1059|0529|096e|0bda|076b|072f"

# 2. O pcscd está rodando?
systemctl status pcscd.socket pcscd.service

# 3. O pcsc_scan enxerga o token? (precisa do pacote pcsc-tools)
pcsc_scan -n
```

**Soluções**:

- Se `lsusb` mostra o token mas o painel não — pode ser USB ID novo. Veja
  `docs/incidentes.md` para o caso INC-2026-001 (G&D StarSign CUT S).
  Solução: adicionar o VID:PID em `token_database.py` e em
  `data/udev/70-crypto-tokens.rules`, depois reinstalar.
- Se `lsusb` não mostra o token — problema de USB físico. Trocar de porta,
  testar em outra máquina.
- Se `pcscd` não está ativo — `sudo systemctl enable --now pcscd.socket`

### 10.2 PIN é rejeitado

**Sintoma**: o diálogo de PIN aceita a digitação, mas o e-SAJ acusa erro de
assinatura logo depois.

**Diagnóstico**: ver o log:

```bash
tail -50 ~/.local/state/big-certificados/websigner-host.log | grep -E "A3:|login|sign"
```

Linhas relevantes:
- `A3: login failed (wrong PIN or token locked?)` — PIN errado **OU** token
  bloqueado por excesso de tentativas
- `A3: sign failed: ...` — PIN correto, mas a assinatura falhou (driver
  incompatível com mecanismo PKCS#11)

**Solução**:
- PIN errado: tente de novo (CUIDADO com o limite de tentativas — 3 ou 5
  dependendo do token)
- Token bloqueado: desbloqueio com PUK (use o utilitário do fabricante)

### 10.3 e-SAJ diz "WebSigner não instalado"

**Sintoma**: a página do e-SAJ exibe um banner pedindo para instalar o
"componente Web Signer".

**Causas comuns**:

1. **Você abriu o e-SAJ antes de rodar "Configurar / Reinstalar"** — vá no
   painel, configure e recarregue a página
2. **Você reiniciou o Firefox (versão normal)** — a ponte sumiu. Rode
   "Configurar / Reinstalar" outra vez ou use Firefox ESR
3. **O Firefox não detectou a extensão da ponte** — confira em
   `about:debugging#/runtime/this-firefox` se aparece **"Big Advogados WebSigner Bridge"**
4. **O native messaging host não foi registrado** — confira em
   `~/.mozilla/native-messaging-hosts/` ou `~/.config/mozilla/native-messaging-hosts/`
   se existe o arquivo `*.json` apontando para o Big Advogados

### 10.4 Firefox foi reiniciado e a extensão sumiu

Comportamento esperado em Firefox release (não-ESR). Soluções:

- **Curto prazo**: voltar no painel e clicar "Configurar / Reinstalar"
- **Longo prazo**: instalar `firefox-esr` e usar ele

### 10.5 Onde estão os logs

| O que loga | Arquivo |
|-----------|---------|
| Native messaging host (WebSigner) | `~/.local/state/big-certificados/websigner-host.log` |
| App principal (GTK) | terminal onde você rodou `big-certificados`, ou `journalctl --user -t big-certificados` |
| pcscd | `journalctl -u pcscd` |
| Firefox | `~/.mozilla/firefox/[profile]/serviceworker.log` ou `about:debugging` |

Para enviar um relato de erro, copie pelo menos as últimas 50 linhas do log
do native host:

```bash
tail -50 ~/.local/state/big-certificados/websigner-host.log
```

---

## 11. Perguntas frequentes

**P: Preciso desinstalar o Web Signer oficial da Softplan?**
R: Não. Se você tem o `.deb` da Softplan baixado mas não instalado, pode
   apagar. Se já está instalado (ex.: em outra distro), o Big Advogados vai
   prevalecer porque registra o native messaging host com prioridade.

**P: Funciona com qualquer token?**
R: Atualmente o `token_database.py` cataloga ~70 modelos (SafeNet, Gemalto,
   Watchdata, G&D, Feitian, etc.). Se seu token não está catalogado, ele
   ainda pode funcionar via fallback OpenSC — basta o `pcsc_scan` reconhecer.
   Se nem por fallback funciona, abra issue no GitHub com saída de `lsusb` e
   modelo exato.

**P: Posso ter A1 e A3 ao mesmo tempo?**
R: Sim. O e-SAJ lista os dois no dropdown. O Big Advogados despacha a
   assinatura para o caminho certo conforme o thumbprint do certificado
   escolhido.

**P: Por que o PIN aparece em zenity e não no Firefox?**
R: O native messaging host roda fora do navegador (é um processo Python
   separado). Ele precisa de uma janela própria para o PIN, e o zenity é o
   padrão do GNOME. Em KDE, fallback para kdialog.

**P: O PIN fica salvo em algum lugar?**
R: Não em disco. Só na memória do processo do native host, enquanto o
   Firefox estiver aberto. Quando você fecha o Firefox, o native host
   encerra (`C_Logout` + `C_CloseSession`) e o PIN é descartado.

**P: O Big Advogados manda dados para algum servidor?**
R: Não. Toda assinatura é local. As únicas conexões de rede são:
   - O navegador acessando o site do tribunal (normal)
   - O VidaaS Connect comunicando com `certificado.vidaas.com.br` (só se você
     usar o VidaaS)
   - Verificação de atualização do PJeOffice contra o site oficial do CNJ
     (opcional, pode desligar)

**P: Como atualizo o Big Advogados?**
R: `cd big-advogados && git pull && makepkg -f && sudo pacman -U
   big-certificados-*.pkg.tar.zst`

**P: Posso usar em Ubuntu/Debian?**
R: O `PKGBUILD` é específico de Arch. Em Ubuntu/Debian, você precisaria
   instalar as dependências via apt + rodar `python3 -m src.main` direto do
   código (modo desenvolvimento). Não tem pacote `.deb` oficial.

**P: O que fazer se o e-SAJ atualizar e quebrar a integração?**
R: O protocolo Web Signer é estável há anos, mas se mudar:
   1. Logar via `tail -f ~/.local/state/big-certificados/websigner-host.log`
   2. Tentar a operação no e-SAJ
   3. Ver qual comando novo apareceu no log (linha `Command: ...`)
   4. Abrir issue no GitHub com o log

---

## Links úteis

- **Repositório**: https://github.com/xathay/big-advogados
- **Issues / suporte**: https://github.com/xathay/big-advogados/issues
- **e-SAJ TJSP**: https://esaj.tjsp.jus.br
- **PJe (CNJ)**: https://www.pje.jus.br
- **VidaaS / Valid**: https://www.valid.com/pt/produtos-e-solucoes/identidade-digital-valid/vidaas/
- **Detalhes técnicos do WebSigner**: `docs/websigner-technical-guide.md`
- **Incidentes registrados**: `docs/incidentes.md`
