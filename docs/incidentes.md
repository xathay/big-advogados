# Registro de Incidentes

Histórico de bugs relatados em produção, com diagnóstico, causa-raiz e correção.
Serve como referência para investigar falhas semelhantes no futuro.

---

## INC-2026-001 — Token G&D StarSign CUT S não detectado (CachyOS)

| Campo | Valor |
|-------|-------|
| **Data do report** | 2026-05-18 |
| **Reportado por** | Filipe de Almeida (grupo Telegram Athayde Lab) |
| **Sistema operacional** | CachyOS (Arch-based) |
| **Versão do app** | 1.2.0 |
| **Hardware** | Giesecke & Devrient StarSign CUT S |
| **VID:PID real** | `1059:0019` |
| **Severidade** | Alta — bloqueio total de uso pra qualquer dono desse modelo |
| **Correção** | commit `f398728`, release `v1.2.1` |

### Sintomas

- Instalação via `makepkg -si` concluiu sem erro
- Tela de **Dependências** marcou tudo verde, `pcscd` ativo
- Tela **Certificados → Token USB (A3)** exibia "Nenhum token detectado"
- Botão "Buscar Dispositivos" não trazia nada mesmo com o token plugado
- Usuário tinha logout/login feito e estava no grupo `plugdev`

### Diagnóstico (passo a passo aplicado)

Pedido pro usuário rodar no terminal:

```bash
lsusb
pcsc_scan -n
pkcs11-tool --list-slots
```

Resultados:

- `lsusb` mostrou `ID 1059:0019 Giesecke & Devrient GmbH StarSign CUT S` → kernel
  reconhece o hardware
- `pcsc_scan` listou o leitor (`Reader 0: Giesecke & Devrient GmbH StarSign CUT S`),
  `Card inserted`, ATR válido → camada PC/SC funcional
- Ou seja: **stack de baixo nível 100% ok**, falha estava na camada do app

### Causa raiz

O scanner USB do app ([src/utils/udev_monitor.py:43-68](../src/utils/udev_monitor.py#L43-L68))
filtra dispositivos por **VID:PID presentes em `TokenDatabase.all_usb_ids()`**.
Apenas tokens cujo par `(vid, pid)` está catalogado em
[src/certificate/token_database.py](../src/certificate/token_database.py) aparecem na UI.

O catálogo tinha o modelo G&D StarSign CUT registrado com `04E6:5816`:

- `04E6` = vendor ID da **SCM Microsystems**, não da Giesecke & Devrient
- O VID oficial da G&D é **`1059`**, registrado na USB-IF
- A entrada provavelmente nasceu de um chute/copy-paste antigo e nunca foi
  validada com hardware real

Resultado: todo dono de um StarSign CUT S genuíno via o app falhar silenciosamente.

### Correção aplicada

**[src/certificate/token_database.py](../src/certificate/token_database.py)** — entrada "G&D" (linha 525):
- VID alterado de `0x04E6` → `0x1059`
- PID alterado de `0x5816` → `0x0019`
- Modelo renomeado para `"StarSign CUT S"` (era `"StarSign CUT Token"`)
- `search_paths` ampliados para incluir `/usr/lib64/` e `/usr/lib/pkcs11/`

**[data/udev/70-crypto-tokens.rules](../data/udev/70-crypto-tokens.rules)** — adicionada nova regra:
```
# ── Giesecke & Devrient ──
# StarSign CUT S (vendor oficial G&D, 1059:0019)
SUBSYSTEM=="usb", ATTR{idVendor}=="1059", ATTR{idProduct}=="0019", MODE="0660", GROUP="plugdev", TAG+="uaccess"
```

A entrada "GD Burti" antiga (`04E6:5816`) foi mantida — não temos certeza de qual
hardware ela representa e remover poderia quebrar outro usuário silenciosamente.

### Validação

Filipe atualizou via `git pull && makepkg -sif && udevadm reload`, replugou o
token, abriu o app e conseguiu autenticar em sistema judicial usando o
certificado A3 — fluxo completo, ponta a ponta, na primeira tentativa após o fix.

### Lições aprendidas

1. **Catálogo de VID:PID é a primeira camada de falha silenciosa.** Quando o
   stack baixo (kernel/pcscd) está ok mas o app não enxerga o token, suspeitar
   imediatamente do `token_database.py` antes de investigar driver/PKCS#11.

2. **Sempre confrontar o catálogo com `lsusb` real.** As entradas atuais que
   nunca foram testadas com hardware físico são suspeitas. Vale uma auditoria
   futura cruzando o catálogo com o repositório
   [usb.ids](http://www.linux-usb.org/usb.ids) — qualquer entrada onde o VID
   declarado não bate com o fabricante listado é forte candidata a estar errada.

3. **Padrão de diagnóstico para "token não detectado":**
   - `lsusb` → VID:PID real do hardware
   - `pcsc_scan -n` → PC/SC enxerga?
   - `pkcs11-tool --list-slots` → camada PKCS#11 enxerga?
   - Comparar VID:PID com entradas em `token_database.py` + udev rules
   - Se VID:PID ausente do catálogo → 2 linhas de patch resolvem

4. **Reports de usuário com `lsusb` valem ouro.** A linha do `lsusb` já contém
   VID:PID + fabricante + modelo — diagnóstico em segundos. Documentar isso no
   README ou em template de issue no GitHub.

---

<!-- Próximos incidentes seguem o mesmo template:
## INC-AAAA-NNN — Título curto
| Data | Reportado por | SO | Versão | Hardware | Severidade | Correção |
### Sintomas / Diagnóstico / Causa raiz / Correção / Validação / Lições
-->
