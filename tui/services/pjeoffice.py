"""PJeOffice Pro — status, verificação de atualização e instalação (GTK-free).

Reusa `src/utils/updater.py` (versão/URL/SHA canônicos) e os mesmos helpers
privilegiados que a GUI GTK chama (`scripts/pjeoffice-*-helper.sh`). O módulo
só toca GLib dentro de `check_pjeoffice_updates_async`, que NÃO importamos —
usamos as funções síncronas num worker thread do Textual.

`instalar` espelha o fluxo de `src/ui/pjeoffice_installer.py` sem GTK:
download → verificação SHA-256 → extração → `pkexec` do helper.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from src.utils import updater

# Callbacks reportados ao worker da UI (frações 0..1; mensagens com markup Rich).
ProgressCB = Callable[[float, str], None]
LogCB = Callable[[str], None]

_BLOCK = 65536


@dataclass(frozen=True)
class PJeStatus:
    instalado: bool
    versao_instalada: Optional[str]
    versao_canonica: str


def status() -> PJeStatus:
    instalada = updater.get_installed_pjeoffice_version()
    return PJeStatus(
        instalado=instalada is not None,
        versao_instalada=instalada,
        versao_canonica=updater.PJEOFFICE_VERSION,
    )


def verificar_atualizacao(versao_instalada: Optional[str]):
    """Consulta a página oficial. Retorna (info|None, erro|None). Bloqueante."""
    base = versao_instalada or updater.PJEOFFICE_VERSION
    try:
        info = updater.check_pjeoffice_updates(base)
    except Exception as exc:  # noqa: BLE001
        return None, f"Falha ao consultar atualização: {exc}"
    return info, None


def url_download() -> str:
    return updater.PJEOFFICE_BASE_URL


# --------------------------------------------------------------------------- #
# Instalação / remoção (mesmos helpers privilegiados da GUI, via pkexec)
# --------------------------------------------------------------------------- #

def _scripts_dir() -> Path:
    """Diretório dos helpers — árvore do repo em dev, /usr/lib quando instalado."""
    repo_scripts = Path(__file__).resolve().parents[2] / "scripts"
    if repo_scripts.is_dir():
        return repo_scripts
    return Path("/usr/lib/big-certificados/scripts")


def _helper(name: str) -> Path:
    return _scripts_dir() / name


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_BLOCK), b""):
            h.update(chunk)
    return h.hexdigest()


def _baixar(url: str, dest: str, on_progress: ProgressCB, on_log: LogCB) -> bool:
    """Download com progresso (0..0.6 da barra). Retorna True em sucesso."""
    req = urllib.request.Request(url, headers={"User-Agent": "BigAdvogados-TUI/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        total = int(resp.headers.get("Content-Length", 0))
        total_mb = total / (1024 * 1024)
        on_log(f"Tamanho: {total_mb:.1f} MB" if total else "Tamanho: desconhecido")
        baixado = 0
        while True:
            chunk = resp.read(_BLOCK)
            if not chunk:
                break
            f.write(chunk)
            baixado += len(chunk)
            mb = baixado / (1024 * 1024)
            if total:
                on_progress(baixado / total * 0.6, f"Baixando {mb:.0f}/{total_mb:.0f} MB")
            else:
                on_progress(0.3, f"Baixando {mb:.0f} MB")
    on_log(f"[green]✓[/] Download concluído ({baixado / (1024 * 1024):.1f} MB)")
    return True


def _emit_helper_output(result: subprocess.CompletedProcess, on_log: LogCB) -> None:
    """Espelha o protocolo LOG:/OK: dos helpers no RichLog."""
    for line in result.stdout.splitlines():
        if line.startswith("LOG: "):
            on_log(f"  {line[5:]}")
        elif line.startswith("OK: "):
            on_log(f"  [green]✓[/] {line[4:]}")
        elif line.strip():
            on_log(f"  {line}")
    for line in result.stderr.splitlines():
        if line.strip():
            on_log(f"  [red][stderr][/] {line}")


def _erro_pkexec(returncode: int) -> str:
    if returncode == 126:
        return "Autenticação cancelada."
    if returncode == 127:
        return "pkexec indisponível ou política ausente."
    return f"Falha (pkexec retornou {returncode})."


def instalar(on_progress: ProgressCB, on_log: LogCB) -> tuple[bool, str]:
    """Baixa, verifica SHA-256, extrai e instala via pkexec. Bloqueante.

    Roda num worker thread; reporta progresso/log pelos callbacks. Retorna
    (ok, mensagem). Reinstala por cima de uma versão existente (o helper
    remove a anterior antes de copiar).
    """
    helper = _helper("pjeoffice-install-helper.sh")
    if not helper.is_file():
        return False, f"Helper não encontrado: {helper}"

    tmp = tempfile.mkdtemp(prefix="pjeoffice_")
    try:
        zip_path = os.path.join(tmp, "pjeoffice-pro.zip")
        on_log(f"[dim]URL:[/] {updater.PJEOFFICE_DOWNLOAD_URL}")
        on_log(f"[dim]Versão:[/] {updater.PJEOFFICE_VERSION}")

        on_progress(0.0, "Baixando…")
        if not _baixar(updater.PJEOFFICE_DOWNLOAD_URL, zip_path, on_progress, on_log):
            return False, "Falha no download."

        on_progress(0.64, "Verificando SHA-256…")
        sha = _sha256(zip_path)
        if sha != updater.PJEOFFICE_SHA256:
            on_log(f"[red]SHA-256 não confere.[/] obtido: {sha}")
            return False, "Arquivo corrompido (SHA-256 não confere)."
        on_log("[green]✓[/] Integridade verificada")

        on_progress(0.72, "Extraindo…")
        unzip = subprocess.run(
            ["unzip", "-q", "-o", zip_path, "-d", tmp],
            capture_output=True, text=True, timeout=120,
        )
        if unzip.returncode != 0:
            on_log(f"[red]Falha ao extrair:[/] {unzip.stderr.strip()}")
            return False, "Falha na extração do zip."
        on_log("[green]✓[/] Extração concluída")

        on_progress(0.85, "Instalando (autenticação)…")
        on_log("[yellow]Autenticação via pkexec — confirme no diálogo do sistema.[/]")
        inst = subprocess.run(
            ["pkexec", "bash", str(helper), tmp],
            capture_output=True, text=True, timeout=180,
        )
        _emit_helper_output(inst, on_log)
        if inst.returncode != 0:
            return False, _erro_pkexec(inst.returncode)

        on_progress(1.0, "Concluído")
        return True, f"PJeOffice Pro {updater.PJEOFFICE_VERSION} instalado."
    except subprocess.TimeoutExpired:
        return False, "Operação expirou (timeout)."
    except Exception as exc:  # noqa: BLE001
        return False, f"Erro: {exc}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def desinstalar(on_log: LogCB) -> tuple[bool, str]:
    """Remove o PJeOffice Pro via pkexec. Bloqueante. Retorna (ok, mensagem)."""
    helper = _helper("pjeoffice-uninstall-helper.sh")
    if not helper.is_file():
        return False, f"Helper não encontrado: {helper}"
    on_log("[yellow]Autenticação via pkexec — confirme no diálogo do sistema.[/]")
    try:
        rem = subprocess.run(
            ["pkexec", "bash", str(helper)],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "Operação expirou (timeout)."
    _emit_helper_output(rem, on_log)
    if rem.returncode != 0:
        return False, _erro_pkexec(rem.returncode)
    return True, "PJeOffice Pro removido."
