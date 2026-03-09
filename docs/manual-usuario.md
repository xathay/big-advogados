# BigCertificados — Manual do Usuário

## Índice

1. [Introdução](#1-introdução)
2. [Requisitos do Sistema](#2-requisitos-do-sistema)
3. [Instalação](#3-instalação)
4. [Primeiro Uso](#4-primeiro-uso)
5. [Certificado A3 (Token USB)](#5-certificado-a3-token-usb)
6. [Certificado A1 (Arquivo PFX)](#6-certificado-a1-arquivo-pfx)
7. [Configuração dos Navegadores](#7-configuração-dos-navegadores)
8. [Sistemas Judiciais Eletrônicos](#8-sistemas-judiciais-eletrônicos)
9. [Verificação de Dependências](#9-verificação-de-dependências)
10. [Perguntas Frequentes](#10-perguntas-frequentes)
11. [Solução de Problemas](#11-solução-de-problemas)

---

## 1. Introdução

O **BigCertificados** é um gerenciador de certificados digitais desenvolvido especificamente para **advogados brasileiros** que utilizam os sistemas processuais eletrônicos da Justiça, como PJe, PROJUDI e e-SAJ.

O aplicativo suporta dois tipos de certificados digitais ICP-Brasil:

| Tipo | Descrição | Mídia |
|------|-----------|-------|
| **A1** | Certificado em arquivo (PFX/P12) | Arquivo digital armazenado no computador |
| **A3** | Certificado em dispositivo criptográfico | Token USB ou smartcard |

### O que o BigCertificados faz

- **Detecta automaticamente** tokens USB de certificado digital
- **Exibe os dados** do certificado: nome, CPF, OAB, e-mail, validade
- **Configura automaticamente** os navegadores Firefox e Chrome/Chromium
- **Oferece acesso rápido** aos sistemas judiciais eletrônicos
- **Verifica dependências** e diagnostica problemas de configuração

---

## 2. Requisitos do Sistema

### Sistema Operacional
- Arch Linux, BigLinux, Manjaro ou derivados
- Ambientes de desktop: KDE Plasma ou GNOME

### Pacotes Necessários

Instale os pacotes com o seguinte comando no terminal:

```bash
sudo pacman -S python python-gobject python-cryptography python-pyudev python-pykcs11 gtk4 libadwaita pcsclite ccid opensc nss
```

### Serviço pcscd

O serviço PC/SC é necessário para a comunicação com tokens e smartcards:

```bash
sudo systemctl enable --now pcscd.service
```

Verifique se está ativo:

```bash
sudo systemctl status pcscd
```

---

## 3. Instalação

### 3.1 Regras udev (acesso ao token sem sudo)

Copie o arquivo de regras para o sistema:

```bash
sudo cp data/udev/70-crypto-tokens.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 3.2 Grupo plugdev

Adicione seu usuário ao grupo `plugdev` para acessar dispositivos USB:

```bash
sudo usermod -aG plugdev $USER
```

> **Importante:** Após adicionar ao grupo, faça logout e login novamente para que a alteração tenha efeito.

### 3.3 Driver do Token

Cada fabricante de token possui um driver (módulo PKCS#11) específico. Os mais comuns no Brasil:

| Token | Pacote / Driver |
|-------|----------------|
| SafeNet eToken 5110 | SafeNet Authentication Client (SAC) |
| Watchdata ProxKey | WatchKey middleware |
| Feitian ePass 2003 | ePass2003 middleware |
| Gemalto/Thales | SafeNet Authentication Client |

Normalmente, o driver é fornecido pela certificadora que emitiu seu certificado (Certisign, Serasa, Soluti, Valid, etc.).

---

## 4. Primeiro Uso

### 4.1 Iniciando o Aplicativo

Abra o terminal e navegue até a pasta do projeto:

```bash
cd certificateManager
python3 -m src.main
```

### 4.2 Visão Geral da Interface

A janela principal possui **quatro abas** no topo:

| Aba | Ícone | Função |
|-----|-------|--------|
| **Tokens** | 🔌 | Detecção e gerenciamento de tokens USB (A3) |
| **Certificado A1** | 📄 | Importação e visualização de certificados PFX |
| **Certificados** | 🔒 | Detalhes do certificado selecionado |
| **Sistemas** | 📋 | Links para sistemas judiciais eletrônicos |

Na parte inferior, há uma **barra de status** que mostra mensagens sobre as operações em andamento.

No canto superior direito, o **menu** (ícone ☰) oferece:
- **Configurar Navegadores** — registra o módulo PKCS#11 nos navegadores
- **Verificar Dependências** — diagnóstico do sistema
- **Sobre** — informações do aplicativo

---

## 5. Certificado A3 (Token USB)

### 5.1 Conectando o Token

1. **Conecte o token USB** ao computador
2. O BigCertificados detecta o dispositivo **automaticamente**
3. Na aba **Tokens**, aparecerá o modelo reconhecido com o status do módulo PKCS#11

Se o token não for detectado automaticamente, clique no botão **"Buscar Dispositivos"**.

### 5.2 Acessando os Certificados

1. Clique na linha do token detectado
2. Uma janela pedirá o **PIN do certificado**
3. Digite o PIN e clique em **"Entrar"**
4. O aplicativo listará os certificados armazenados no token

### 5.3 Visualizando os Detalhes

Após o login com PIN, a aba **Certificados** exibirá:

- **Titular**: Nome completo do advogado
- **CPF**: Número formatado (XXX.XXX.XXX-XX)
- **OAB**: Número da inscrição na Ordem dos Advogados
- **E-mail**: Endereço eletrônico cadastrado
- **Emissora (CA)**: Autoridade Certificadora que emitiu o certificado
- **Validade**: Datas de início e expiração
- **Status**: VÁLIDO, EXPIRA EM X DIAS, ou EXPIRADO

### 5.4 Indicadores de Validade

| Cor | Significado |
|-----|-------------|
| 🟢 Verde | Certificado válido |
| 🟡 Amarelo | Expira em menos de 30 dias |
| 🔴 Vermelho | Certificado expirado |

---

## 6. Certificado A1 (Arquivo PFX)

### 6.1 O que é um Certificado A1

O certificado A1 é um arquivo digital com extensão `.pfx` ou `.p12` que contém o certificado e a chave privada protegidos por senha. Diferente do A3, **não requer dispositivo físico**.

### 6.2 Carregando o Certificado

1. Vá para a aba **"Certificado A1"**
2. Clique no botão **"Selecionar Arquivo PFX"**
3. Navegue até o arquivo `.pfx` ou `.p12` no seu computador
4. Digite a **senha do certificado** quando solicitado
5. O certificado será carregado e seus dados exibidos

### 6.3 Dados Exibidos

Os mesmos dados do certificado A3 serão apresentados:
- Nome, CPF, OAB, e-mail, CA emissora, validade e status.

### 6.4 Instalando no Navegador

Após carregar o certificado A1, você pode instalá-lo diretamente no navegador clicando em **"Instalar no Navegador"**. O certificado será adicionado à base NSS do Firefox e/ou Chrome.

> **Atenção:** O certificado A1 possui validade de **1 ano**. Ao expirar, será necessário adquirir um novo com sua certificadora.

---

## 7. Configuração dos Navegadores

### 7.1 Firefox

O BigCertificados registra automaticamente o módulo PKCS#11 no banco de dados NSS do Firefox. Isso permite que o navegador acesse o certificado do token para autenticação nos sistemas judiciais.

**Para configurar:**
1. Certifique-se de que o token está conectado e o módulo foi carregado
2. Vá ao menu **☰ → Configurar Navegadores**
3. O app encontrará todos os perfis do Firefox e registrará o módulo

**Verificação manual no Firefox:**
1. Abra o Firefox
2. Acesse: `about:preferences#privacy`
3. Role até "Certificados" → clique em "Dispositivos de Segurança"
4. Deve aparecer o módulo "BigCertificados_Token"

### 7.2 Chrome / Chromium / Brave / Edge

Esses navegadores compartilham o banco NSS em `~/.pki/nssdb/`. O BigCertificados configura todos automaticamente.

**Para configurar:**
1. Vá ao menu **☰ → Configurar Navegadores**
2. O app detectará os navegadores Chromium-based instalados
3. O módulo será registrado no NSS compartilhado

---

## 8. Sistemas Judiciais Eletrônicos

A aba **Sistemas** oferece acesso rápido aos principais sistemas da Justiça:

### Sistemas Disponíveis

| Sistema | Instância | Descrição |
|---------|-----------|-----------|
| PJe TJBA | 1ª Instância | Varas da Justiça Estadual da Bahia |
| PJe TJBA | 2ª Instância | Tribunal de Justiça da Bahia |
| PJe TRF1 | 1ª Instância | Varas Federais (BA, MG, GO, etc.) |
| PJe TRF1 | 2ª Instância | Tribunal Regional Federal 1ª Região |
| PROJUDI TJBA | — | Sistema legado (em migração para PJe) |
| e-SAJ TJBA | — | Consulta processual |
| PJe TRT5 | — | Justiça do Trabalho (Bahia) |
| PJe TST | — | Tribunal Superior do Trabalho |

### Como Acessar

1. Clique no sistema desejado
2. O navegador padrão abrirá a URL do sistema
3. O certificado digital configurado será usado para autenticação

> **Dica:** Antes de acessar o sistema, certifique-se de que:
> - O token está conectado (A3) ou o certificado está instalado (A1)
> - O módulo PKCS#11 está registrado no navegador
> - O PJeOffice está instalado, se exigido pelo sistema

---

## 9. Verificação de Dependências

Acesse **☰ → Verificar Dependências** para diagnosticar o sistema:

### Dependências Verificadas

| Item | Pacote | Função |
|------|--------|--------|
| pcscd | pcsclite | Comunicação com smartcards |
| modutil | nss | Configuração de navegadores |
| opensc-tool | opensc | Middleware de smartcard |
| pcscd (serviço) | — | Status do daemon PC/SC |
| PyKCS11 | python-pykcs11 | Biblioteca Python para PKCS#11 |
| pyudev | python-pyudev | Detecção de dispositivos USB |
| cryptography | python-cryptography | Parsing de certificados |

Se algum item estiver marcado como "Não encontrado" ou "Não instalado", instale o pacote correspondente com `sudo pacman -S <pacote>`.

---

## 10. Perguntas Frequentes

### O token foi detectado mas diz "Módulo não encontrado"

Isso significa que o driver (biblioteca PKCS#11) do seu token não está instalado. Você precisa instalar o middleware do fabricante do token. Consulte a seção [3.3 Driver do Token](#33-driver-do-token).

### O PIN está correto mas a autenticação falha

Verifique se:
- O serviço `pcscd` está ativo: `sudo systemctl status pcscd`
- O token está sendo reconhecido pelo sistema: `pcsc_scan`
- O driver PKCS#11 está no caminho correto

### O navegador não reconhece o certificado

1. Verifique se o módulo foi registrado: menu **☰ → Configurar Navegadores**
2. No Firefox, vá em `about:preferences#privacy` → Dispositivos de Segurança
3. Reinicie o navegador após a configuração

### Qual a diferença entre A1 e A3?

| Aspecto | A1 | A3 |
|---------|----|----|
| Mídia | Arquivo digital (.pfx) | Token USB / Smartcard |
| Validade | 1 ano | 1 a 3 anos |
| Portabilidade | Pode ser copiado | Vinculado ao dispositivo |
| Segurança | Menor (arquivo pode vazar) | Maior (chave no hardware) |
| Preço | Mais barato | Mais caro |

### Posso usar o BigCertificados com o PJeOffice?

Sim. O BigCertificados configura o módulo PKCS#11 no navegador, e o PJeOffice utiliza o mesmo mecanismo. Ambos podem coexistir.

---

## 11. Solução de Problemas

### 11.1 Token não detectado

```bash
# Verifique se o dispositivo é reconhecido pelo kernel
lsusb | grep -i "token\|smart\|safe\|feitian\|watch"

# Verifique permissões
ls -la /dev/bus/usb/*/*

# Recarregue regras udev
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 11.2 Serviço pcscd

```bash
# Iniciar o serviço
sudo systemctl start pcscd

# Habilitar na inicialização
sudo systemctl enable pcscd

# Ver logs
journalctl -u pcscd -f
```

### 11.3 Testar comunicação com o token

```bash
# Listar leitores/tokens
opensc-tool -l

# Listar certificados no token
pkcs11-tool --module /usr/lib/libeToken.so -O

# Testar com pcsc_scan
pcsc_scan
```

### 11.4 Logs do BigCertificados

O aplicativo gera logs no terminal com informações de debug. Execute o app pelo terminal para visualizar:

```bash
python3 -m src.main
```

Os logs mostram:
- Dispositivos detectados e seus USB IDs
- Módulos PKCS#11 carregados
- Resultados de login/autenticação
- Erros de configuração

---

## Suporte

- **Repositório**: https://github.com/biglinux/bigcertificados
- **Licença**: GPL-3.0
