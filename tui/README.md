# Big Advogados TUI

Frontend de **terminal** (TUI) do Big Advogados — companheiro do app GTK4,
pensado para **Omarchy / Hyprland** (teclado-first, roda bem no Ghostty).

Reusa **toda a lógica** de `src/` (transcritor, certificados, navegadores,
dados) sem dependência de GTK. Só a camada de view é nova (Textual).

## Status — Fases 1–5

| Seção | Tecla | Estado |
|---|---|---|
| Dashboard | `d` | ✅ status do ambiente (config, modelo, faster-whisper, pcscd, identidade) |
| Transcritor | `x` | ✅ transcrição forense (SHA-256 + faster-whisper → PDF/txt/md/json/csv) |
| Certificados | `c` | ✅ carrega A1 (PFX/P12) → titular, CPF, OAB, validade colorida |
| Token A3 | `t` | ✅ detecção USB com hotplug (asyncio) + leitura via PIN (PKCS#11) |
| Sistemas | `s` | ✅ palette de busca dos 39 tribunais → Enter abre no navegador |
| PJeOffice | `p` | ✅ instalar/reinstalar/remover (download + SHA-256 + `pkexec`) · versão instalada · verificação de atualização (fonte oficial) |
| Drivers | `g` | ✅ 68 drivers com status (pacman) + instalar (oficial pkexec / AUR terminal) |
| Assinar PDF | `a` | ✅ PAdES (endesive) com A1 (PFX) ou A3 (PIN) · carimbo rodapé/topo, página de certificação ou invisível · SHA-256 embutido |

Teclas globais: `r` recarrega o dashboard · `ctrl+t` cicla tema · `esc` volta
ao menu · `q` sai. As teclas de seção navegam quando o foco **não** está num
campo de texto; dentro de um campo, digitam normalmente (o Input consome a
tecla — por isso `esc` devolve o foco ao menu). A sidebar também navega por
clique e setas + Enter.

**Tema:** padrão `neon-mauve` (estética Blade Runner 2049 do Omarchy —
`#f2a6ff`/`#f04dff`/`#0a0612`); `ctrl+t` cicla por tokyo-night,
catppuccin-mocha, gruvbox, nord, dracula.

> **Deps de runtime por seção** (import lazy — o app abre sem elas):
> transcritor → `faster-whisper`; A1 → `cryptography`; A3 → `PyKCS11`;
> hotplug USB → `pyudev` (sem ele, a leitura por PIN ainda tenta os módulos).

## Rodar (desenvolvimento)

```bash
# venv com textual (fora da árvore do Nextcloud)
python -m venv ~/.cache/big-advogados-tui-venv
~/.cache/big-advogados-tui-venv/bin/pip install textual reportlab faster-whisper

# da raiz do repositório:
~/.cache/big-advogados-tui-venv/bin/python -m tui
```

Instalado via `pip install -e ".[tui]"`, há também o entry-point
`big-advogados-tui`.

> O transcritor exige `faster-whisper` em runtime (import lazy); o PDF exige
> `reportlab`. O resto do app carrega sem eles.

## Instalar no Omarchy (Arch)

O TUI é empacotado **junto** do app principal (`big-certificados`) — sem
duplicar `src/`. O `PKGBUILD` instala `python3 -m tui` como
`/usr/bin/big-advogados-tui` (dep `python-textual`) e um `.desktop` que abre
no terminal:

```bash
makepkg -si        # instala big-certificados (GUI + CLI + TUI)
big-advogados-tui  # roda a TUI
```

## Arquitetura

```
tui/
├── __main__.py        # python -m tui  (ajusta sys.path: src/ + tui/)
├── app.py             # casca: sidebar + ContentSwitcher + bindings
├── app.tcss           # tema
├── screens/
│   ├── dashboard.py    # status do ambiente (worker thread)
│   ├── transcritor.py  # formulário + execução com ProgressBar/RichLog
│   ├── certificados.py # leitor A1 (PFX) + render compartilhado de certificado
│   ├── token.py        # token A3: hotplug + leitura por PIN
│   ├── sistemas.py     # palette de busca dos tribunais (OptionList)
│   ├── pjeoffice.py    # status + verificação de atualização
│   ├── drivers.py      # 68 drivers: status + busca + instalação
│   └── assinar.py      # assinatura PAdES: A1/A3, carimbo e saída
└── services/           # GTK-free; ponte para src/
    ├── status.py        # sondas (pcscd, config, módulos)
    ├── transcricao.py   # orquestra o mesmo pipeline da CLI, com callbacks
    ├── certificados.py  # A1Manager / A3Manager (imports pesados lazy)
    ├── token_monitor.py # equivalente asyncio do udev_monitor (sem GLib)
    ├── sistemas.py      # achata judicial_systems + busca + xdg-open
    ├── pjeoffice.py     # reusa updater (sync), sem o caminho GLib
    ├── drivers.py       # reusa driver_database (pacman/pkexec/AUR)
    └── assinatura.py    # reusa pdf_signer (endesive) — A1 e A3 (login próprio)
```

> Telas dentro do `ContentSwitcher` são todas montadas no boot; para focar um
> campo só ao **entrar** numa seção, a tela expõe `ao_entrar()` (chamado por
> `action_ir`) — em vez de roubar foco em `on_mount`.

O trabalho pesado roda em `@work(thread=True)`; updates de UI voltam via
`App.call_from_thread`. Nada aqui importa GTK/GLib.
