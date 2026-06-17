"""Sondas de status do ambiente — todas GTK-free e baratas.

Usadas pelo Dashboard. Nada aqui importa GTK/GLib; subprocessos usam
arrays (sem shell=True) e degradam graciosamente quando o binário falta.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.transcritor import config as cfg_module


@dataclass(frozen=True)
class Probe:
    """Um item de status: rótulo, valor legível e nível (ok/warn/err/info)."""

    label: str
    value: str
    level: str = "info"  # ok | warn | err | info


def _systemctl_active(unit: str) -> bool:
    exe = shutil.which("systemctl")
    if not exe:
        return False
    try:
        out = subprocess.run(
            [exe, "is-active", unit],
            capture_output=True, text=True, timeout=3,
        )
        return out.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def _module_installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def coletar_status() -> list[Probe]:
    """Reúne o panorama do ambiente para o Dashboard."""
    probes: list[Probe] = []

    cfg = cfg_module.load_config()
    adv = cfg.advogado
    if adv.preenchido:
        oab = f" — OAB {adv.oab}" if adv.oab else ""
        probes.append(Probe("Advogado", f"{adv.nome}{oab}", "ok"))
    else:
        probes.append(Probe(
            "Advogado",
            "não configurado (edite transcritor.toml p/ emitir declaração)",
            "warn",
        ))

    probes.append(Probe(
        "Modelo Whisper",
        f"{cfg.modelo.nome} (device={cfg.modelo.device})",
        "info",
    ))

    iv = cfg.identidade_visual
    probes.append(Probe(
        "Identidade visual",
        "logo + rodapé presentes" if (iv.logo_existe and iv.footer_bar_existe)
        else "logo/rodapé ausentes (PDF usa layout sem imagens)",
        "ok" if (iv.logo_existe and iv.footer_bar_existe) else "warn",
    ))

    probes.append(Probe(
        "faster-whisper",
        "instalado" if _module_installed("faster_whisper")
        else "ausente — instale para transcrever (pip install faster-whisper)",
        "ok" if _module_installed("faster_whisper") else "err",
    ))

    probes.append(Probe(
        "Serviço pcscd (tokens A3)",
        "ativo" if _systemctl_active("pcscd.service")
        else "inativo (sudo systemctl enable --now pcscd)",
        "ok" if _systemctl_active("pcscd.service") else "warn",
    ))

    probes.append(Probe("Config", str(cfg_module.CONFIG_FILE), "info"))

    return probes
