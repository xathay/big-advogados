"""Orquestracao da instalacao de drivers proprietarios.

Fluxo (cada etapa reporta progresso via callback):

    1. download  — baixa do canal oficial, cache em ~/.cache/big-certificados/drivers
    2. verifying — confere SHA-256
    3. eula      — extrai e devolve o texto da licenca (UI mostra ao usuario)
    4. installing — invoca helper privilegiado via pkexec, streamando logs
    5. done/error

A camada UI roda este orquestrador em uma thread e traduz callbacks
para GLib.idle_add.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
import threading
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from src.drivers._deb import extract_file_from_deb
from src.drivers.types import DriverSpec

log = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "big-certificados" / "drivers"

# Helper privilegiado: caminho instalado pelo pacote tem precedencia.
_HELPER_INSTALLED = Path("/usr/lib/big-certificados/scripts/big-drivers-install.py")
_HELPER_DEV = Path(__file__).resolve().parents[2] / "scripts" / "big-drivers-install.py"


class InstallStage(Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    EULA = "eula"
    INSTALLING = "installing"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class InstallProgress:
    stage: InstallStage
    message: str
    fraction: float  # 0.0 a 1.0; -1.0 = indeterminado


ProgressCb = Callable[[InstallProgress], None]
LogCb = Callable[[str], None]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_helper() -> Path:
    if _HELPER_INSTALLED.exists():
        return _HELPER_INSTALLED
    return _HELPER_DEV


class DriverInstaller:
    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._proc: Optional[subprocess.Popen] = None

    def cancel(self) -> None:
        self._cancelled.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def download(self, spec: DriverSpec, on_progress: ProgressCb) -> Path:
        """Baixa o source para CACHE_DIR e devolve o path local verificado.

        Se o arquivo ja existe e o SHA-256 bate, reusa sem rebaixar.
        Levanta ``ValueError`` em falha de integridade, ``InterruptedError``
        se cancelado e ``OSError``/``URLError`` em problemas de rede.
        """
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        target = CACHE_DIR / f"{spec.id}-{spec.version}.{spec.source.format}"

        if target.exists() and _sha256(target) == spec.source.sha256:
            on_progress(InstallProgress(
                InstallStage.VERIFYING,
                "Arquivo ja em cache, integridade confirmada.",
                1.0,
            ))
            return target

        on_progress(InstallProgress(
            InstallStage.DOWNLOADING,
            f"Baixando {spec.source.label}",
            0.0,
        ))

        tmp = target.with_suffix(target.suffix + ".part")
        tmp.unlink(missing_ok=True)

        with urllib.request.urlopen(spec.source.url, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0) or spec.source.size_bytes
            written = 0
            with tmp.open("wb") as f:
                while True:
                    if self._cancelled.is_set():
                        tmp.unlink(missing_ok=True)
                        raise InterruptedError("Download cancelado")
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    frac = (written / total) if total > 0 else -1.0
                    mb_done = written / 1024 / 1024
                    mb_total = total / 1024 / 1024 if total > 0 else 0
                    msg = (
                        f"Baixando {mb_done:.1f} MB de {mb_total:.1f} MB"
                        if total > 0 else f"Baixando {mb_done:.1f} MB"
                    )
                    on_progress(InstallProgress(InstallStage.DOWNLOADING, msg, frac))

        on_progress(InstallProgress(
            InstallStage.VERIFYING,
            "Verificando integridade (SHA-256)",
            -1.0,
        ))
        actual = _sha256(tmp)
        if actual != spec.source.sha256:
            tmp.unlink(missing_ok=True)
            raise ValueError(
                f"Integridade falhou: esperado {spec.source.sha256[:16]}..., "
                f"obtido {actual[:16]}..."
            )
        tmp.rename(target)
        return target

    def extract_eula(self, spec: DriverSpec, deb_path: Path) -> str:
        """Devolve o texto da licenca contida no .deb (UTF-8).

        Tenta primeiro o caminho preferido, depois o fallback. Levanta
        ``FileNotFoundError`` se nenhum dos dois existe.
        """
        candidates = [spec.license.file_in_archive]
        if spec.license.file_in_archive_fallback:
            candidates.append(spec.license.file_in_archive_fallback)

        for cand in candidates:
            try:
                raw = extract_file_from_deb(deb_path, cand)
            except (OSError, subprocess.SubprocessError) as exc:
                log.warning("Falha ao extrair %s de %s: %s", cand, deb_path, exc)
                continue
            if raw:
                return raw.decode("utf-8", errors="replace")

        raise FileNotFoundError(
            f"Nao foi possivel extrair a licenca de {deb_path.name}"
        )

    def install(
        self,
        spec: DriverSpec,
        deb_path: Path,
        on_progress: ProgressCb,
        on_log: LogCb,
    ) -> bool:
        """Invoca o helper privilegiado via pkexec; retorna True em sucesso.

        O helper le o catalogo de /usr/lib/big-certificados/data/drivers/
        e nunca confia no caller para definir caminhos de destino — so
        recebe o id do driver e o source local ja verificado.
        """
        helper = _resolve_helper()
        if not helper.exists():
            on_progress(InstallProgress(
                InstallStage.ERROR,
                f"Helper de instalacao nao encontrado: {helper}",
                0.0,
            ))
            return False

        on_progress(InstallProgress(
            InstallStage.INSTALLING,
            "Solicitando autorizacao administrativa",
            -1.0,
        ))

        cmd = [
            "pkexec",
            str(helper),
            "--driver", spec.id,
            "--source", str(deb_path),
            "--sha256", spec.source.sha256,
        ]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            on_progress(InstallProgress(
                InstallStage.ERROR,
                f"Falha ao iniciar helper: {exc}",
                0.0,
            ))
            return False

        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            if self._cancelled.is_set():
                self._proc.terminate()
                return False
            # Convencao do helper: linhas comecando com "PROGRESS: <msg>"
            # avancam o stage de instalacao na UI. Outras viram log line.
            if line.startswith("PROGRESS: "):
                on_progress(InstallProgress(
                    InstallStage.INSTALLING, line[10:], -1.0,
                ))
            else:
                on_log(line)

        rc = self._proc.wait()
        self._proc = None

        if rc == 0:
            on_progress(InstallProgress(
                InstallStage.DONE, "Driver instalado com sucesso.", 1.0,
            ))
            return True

        # pkexec exit codes: 126 = nao autorizado, 127 = nao achou helper
        if rc == 126:
            msg = "Autorizacao negada"
        elif rc == 127:
            msg = "Helper nao encontrado"
        else:
            msg = f"Falha na instalacao (codigo {rc})"
        on_progress(InstallProgress(InstallStage.ERROR, msg, 0.0))
        return False
