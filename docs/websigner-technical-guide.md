# BigCertificados WebSigner — Guia Técnico Completo

> Como resolvemos a assinatura digital no e-SAJ e sistemas judiciais no GNU/Linux,
> substituindo o binário proprietário da Softplan por uma solução open-source em Python.

## O Problema

Advogados no GNU/Linux não conseguem protocolar petições no **e-SAJ** (TJSP, TJBA e
outros tribunais) porque o sistema exige o **Web Signer** — um componente nativo
proprietário da Softplan/Lacuna Software que:

1. O binário nativo para Linux (`/opt/softplan-websigner/websigner`, v2.12.1, agosto/2022)
   **não funciona** — retorna 0 bytes ao protocolo de native messaging
2. A extensão do Firefox (v2.15.4) tenta se comunicar com o binário, falha silenciosamente,
   e o e-SAJ mostra "Nenhum certificado encontrado"

## A Arquitetura do Web Signer

O Web Signer funciona em três camadas:

```
┌─────────────────────────────────────────────────────┐
│  Página e-SAJ (JavaScript)                          │
│  ↕ window.postMessage()                             │
├─────────────────────────────────────────────────────┤
│  Extensão Web Signer (content script + background)  │
│  ↕ browser.runtime.connectNative()                  │
├─────────────────────────────────────────────────────┤
│  Native Messaging Host (binário ou Python)          │
│  ↕ stdin/stdout com prefixo 4 bytes LE              │
└─────────────────────────────────────────────────────┘
```

### Protocolo de Native Messaging

Cada mensagem tem um prefixo de 4 bytes (little-endian) com o tamanho do JSON:

```
[4 bytes: tamanho] [JSON UTF-8]
```

### Comandos do protocolo

| Comando | Direção | Descrição |
|---------|---------|-----------|
| `getInfo` | → host | Retorna `{ os: "Linux", version: "2.15.4" }` |
| `authorizeCertificateAccess` | → host | Pede consentimento antes de expor certificados públicos ao domínio |
| `listCertificates` | → host | Lista certificados do banco NSS |
| `readCertificate` | → host | Lê conteúdo DER de um certificado (base64) |
| `authorizeSignatures` | → host | Autoriza assinatura — deve retornar `{ authorized: true, certificate: {...} }` |
| `signHash` | → host | Assina hash com chave privada do PFX |
| `signData` | → host | Assina dados brutos com chave privada |
| `signHashBatch` | → host | Assina múltiplos hashes em lote |

### Formato de resposta

```json
{
  "requestId": "uuid-matching-request",
  "success": true,
  "response": { /* dados específicos do comando */ }
}
```

## A Solução BigCertificados

### Componente 1: Native Messaging Host (`native_host.py`)

Substitui o binário `/opt/softplan-websigner/websigner` por um script Python que:

- **Lista certificados** do banco NSS do Firefox (`certutil -L`)
- **Assina dados** com a chave privada do PFX via biblioteca `cryptography`
- **Pede a senha** do certificado via dialog Zenity/KDialog
- **Registra logs** em `~/.local/state/big-certificados/websigner-host.log`

**Localização:** `src/websigner/native_host.py`

**Como funciona:**

```python
# Leitura de mensagem (stdin)
raw_length = sys.stdin.buffer.read(4)
length = struct.unpack("<I", raw_length)[0]
message = json.loads(sys.stdin.buffer.read(length))

# Envio de resposta (stdout)
data = json.dumps(response).encode("utf-8")
sys.stdout.buffer.write(struct.pack("<I", len(data)))
sys.stdout.buffer.write(data)
```

### Componente 2: Installer (`installer.py`)

Cria manifestos per-user que o Firefox lê para encontrar o native host:

**Firefox:** `~/.config/mozilla/native-messaging-hosts/br.com.softplan.webpki.json`

```json
{
  "name": "br.com.softplan.webpki",
  "description": "BigCertificados PKI Connector",
  "path": "/home/user/.local/share/big-certificados/bigcertificados-websigner",
  "type": "stdio",
  "allowed_extensions": ["websigner@softplan_com_br", "websigner@softplan.com.br"]
}
```

O manifesto per-user tem prioridade sobre o do sistema (`/usr/lib/mozilla/native-messaging-hosts/`),
então nosso host é usado em vez do binário morto da Softplan.

### Componente 3: Firefox Bridge Extension (`firefox-bridge/`)

A página de **login** do e-SAJ usa a biblioteca JavaScript da Softplan.
A página de **protocolo** usa a biblioteca **Lacuna Web PKI**.

São bibliotecas diferentes que procuram por extensões diferentes:

| Página | Biblioteca | Meta tag esperada | Event names |
|--------|-----------|-------------------|-------------|
| Login (`/sajcas/`) | Softplan | `websigner_softplan_com_br` | `br.com.softplan.WebPKI.*` |
| Protocolo (`/petpg/`) | Lacuna Web PKI | `webpki_lacunasoftware_com` | `com.lacunasoftware.WebPKI.*` |

A extensão Web Signer só injeta o meta tag da Softplan. A bridge:

1. **Injeta o meta tag Lacuna** (`webpki_lacunasoftware_com`) em `document_start`
2. **Traduz mensagens** entre os event names Lacuna ↔ Softplan via `window.postMessage`

```javascript
// Lacuna library → bridge → Softplan content script
if (event.data.port === 'com.lacunasoftware.WebPKI.RequestEvent') {
    window.postMessage({ port: 'br.com.softplan.WebPKI.RequestEvent', message: event.data.message }, '*');
}

// Softplan content script → bridge → Lacuna library
if (event.data.port === 'br.com.softplan.WebPKI.ResponseEvent') {
    window.postMessage({ port: 'com.lacunasoftware.WebPKI.ResponseEvent', message: event.data.message }, '*');
}
```

## Bugs encontrados e soluções

### Bug 1: OS case-sensitive (`"linux"` vs `"Linux"`)

A extensão verifica o OS retornado pelo native host (event-page.js, linha 1127):

```javascript
if (response.os !== 'Windows' && response.os !== 'Linux' && response.os !== 'Darwin') {
    errorCallback(createExceptionModel('Not supported OS: ' + response.os, 'os_not_supported'));
}
```

**Solução:** Retornar `"Linux"` com L maiúsculo.

### Bug 2: `authorizeSignatures` precisa de objeto, não boolean

A extensão espera (event-page.js, linha 2197):

```javascript
if (response.authorized) {
    if (response.dontAskAgain) {
        configManager.setSiteTrust(requestContext.page.domain, response.certificate);
    }
    callback(); // → prossegue para signData
}
```

Retornar apenas `true` faz `response.authorized === undefined` → nunca chama `signData`.

**Solução:** Retornar `{ authorized: true, dontAskAgain: true, certificate: {...} }`.

### Bug 3: Duas bibliotecas JavaScript diferentes

A página de login usa a lib Softplan. A página de protocolo usa a lib Lacuna.
Elas procuram por meta tags e event names diferentes.

**Solução:** Extensão ponte que injeta os meta tags Lacuna e traduz os event names.

### Bug 4: autorização de acesso aos certificados no Web Signer 2.18.3

A extensão 2.18.3 passou a chamar `authorizeCertificateAccess` antes de listar ou ler
certificados. Hosts antigos que não reconheciam o comando impediam o login, e o e-SAJ
voltava a exibir a janela de instalação do Web Signer.

**Solução:** o native host mostra um diálogo com o domínio solicitante e responde
`{ authorized, dontAskAgain }`. A autorização permite apenas ler os dados públicos do
certificado; senha e chave privada continuam protegidas pelo fluxo próprio de assinatura.

Comandos futuros desconhecidos devem responder com o código `command_unknown`, grafia
esperada pela extensão para acionar sua compatibilidade com hosts anteriores.

### Bug 5: Python do `mise` sem as dependências do pacote

O native host era iniciado com `python3`, resolvido pelo `PATH` herdado do navegador.
Quando `mise` ou `pyenv` tinha precedência, o host usava um ambiente diferente do Python
do sistema e falhava ao importar `cryptography`, embora `python-cryptography` estivesse
corretamente instalado pelo pacman.

**Solução:** wrappers e launchers do pacote usam explicitamente `/usr/bin/python3`, o
mesmo interpretador para o qual as dependências do `PKGBUILD` são instaladas.

## Fluxo completo de assinatura

```
1. Usuário acessa e-SAJ → página carrega lib Lacuna Web PKI
2. Bridge injeta meta tag webpki_lacunasoftware_com
3. Lib Lacuna detecta "extensão instalada"
4. Lib Lacuna envia mensagem via postMessage (event: Lacuna)
5. Bridge traduz event name Lacuna → Softplan
6. Content script Web Signer recebe e encaminha ao background
7. Background chama native host (BigCertificados) via stdio
8. Native host:
   a. getInfo → { os: "Linux", version: "2.15.4" }
   b. listCertificates → lê NSS database do Firefox via certutil
   c. authorizeSignatures → { authorized: true, certificate: {...} }
   d. signHash → pede senha PFX via Zenity → assina com cryptography
9. Assinatura retorna pela cadeia inversa até a página
10. e-SAJ valida a assinatura no servidor → protocolo realizado
```

## Arquivos do projeto

```
src/websigner/
├── __init__.py
├── native_host.py          # Native messaging host (stdio)
├── installer.py             # Deploy de manifestos per-user
└── firefox-bridge/
    ├── manifest.json        # WebExtension manifest (temporária)
    └── bridge.js            # Ponte Lacuna ↔ Softplan
```

## Configuração

```
~/.local/share/big-certificados/
├── websigner.json           # { "pfx_path": "/path/to/cert.p12" }
└── bigcertificados-websigner # Wrapper script que chama native_host.py

~/.config/mozilla/native-messaging-hosts/
└── br.com.softplan.webpki.json  # Manifesto per-user (prioridade sobre /usr/lib)

~/.local/state/big-certificados/
└── websigner-host.log       # Log de debug
```

## Instalação

### 1. Native Messaging Host

```python
from src.websigner.installer import install_native_host, configure_pfx_path

# Instala manifestos para Firefox, Chrome e Brave
install_native_host()

# Configura caminho do certificado PFX
configure_pfx_path("/caminho/para/certificado.p12")
```

### 2. Bridge Extension (temporária)

1. Firefox → `about:debugging` → Este Firefox
2. Carregar extensão temporária → selecionar `src/websigner/firefox-bridge/manifest.json`

### 3. Bridge Extension (permanente — futuro)

A bridge será empacotada como XPI assinada e instalada automaticamente
pelo BigCertificados, eliminando a necessidade de `about:debugging`.

## Compatibilidade

| Sistema | Login | Protocolo | Assinatura |
|---------|-------|-----------|-----------|
| e-SAJ TJSP | ✅ | ✅ | ✅ |
| e-SAJ (outros TJs) | ✅ (esperado) | ✅ (esperado) | ✅ (esperado) |
| PJe | ✅ (via PJeOffice) | ✅ (via PJeOffice) | ✅ (via PJeOffice) |
| Qualquer sistema Web Signer/Lacuna | ✅ | ✅ | ✅ |

## Dependências

- Python 3.10+ com `cryptography` (já dependência do BigCertificados)
- `certutil` do pacote `nss` (para listar certificados NSS)
- `zenity` ou `kdialog` (para dialog de senha)
- Extensão Web Signer instalada no Firefox (do e-SAJ)
