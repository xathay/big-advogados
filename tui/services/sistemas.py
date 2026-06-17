"""Sistemas judiciais — lista achatada, busca e abertura no navegador.

Reusa `src/data/judicial_systems.py` (dados puros). Abre URLs com
`xdg-open` (respeita o navegador padrão do Omarchy/Hyprland), com fallback
para o módulo `webbrowser`.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

from src.data.judicial_systems import JUDICIAL_STATES


@dataclass(frozen=True)
class Sistema:
    nome: str
    url: str
    descricao: str
    regiao: str
    _blob: str = field(default="", repr=False, compare=False)


def listar_sistemas() -> list[Sistema]:
    """Achata JUDICIAL_STATES numa lista única e pesquisável."""
    out: list[Sistema] = []
    for estado in JUDICIAL_STATES:
        regiao = estado.get("name", "")
        for s in estado.get("systems", []):
            nome = s.get("name", "")
            url = s.get("url", "")
            desc = s.get("description", "")
            blob = " ".join((nome, regiao, desc, url)).lower()
            out.append(Sistema(nome=nome, url=url, descricao=desc, regiao=regiao, _blob=blob))
    return out


def buscar(sistemas: list[Sistema], consulta: str) -> list[Sistema]:
    """Filtra e ordena por relevância. Tokens AND; ranqueia por onde casa."""
    q = consulta.strip().lower()
    if not q:
        return sistemas
    tokens = q.split()

    def score(s: Sistema) -> int:
        if not all(t in s._blob for t in tokens):
            return -1
        nl = s.nome.lower()
        if nl.startswith(q):
            return 100
        if q in nl:
            return 80
        if q in s.regiao.lower():
            return 60
        return 40

    ranqueados = [(score(s), s) for s in sistemas]
    ranqueados = [(sc, s) for sc, s in ranqueados if sc >= 0]
    ranqueados.sort(key=lambda par: (-par[0], par[1].nome))
    return [s for _, s in ranqueados]


def abrir_url(url: str) -> tuple[bool, str | None]:
    """Abre a URL no navegador padrão. Retorna (ok, erro)."""
    if not url:
        return False, "URL vazia."
    exe = shutil.which("xdg-open")
    if exe:
        try:
            subprocess.Popen(
                [exe, url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True, None
        except OSError as exc:
            return False, f"xdg-open falhou: {exc}"
    try:
        import webbrowser
        if webbrowser.open(url):
            return True, None
        return False, "Nenhum navegador disponível."
    except Exception as exc:  # noqa: BLE001
        return False, f"Falha ao abrir: {exc}"
