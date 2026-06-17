"""Ponte GTK-free para certificados A1 (PFX) e A3 (token PKCS#11).

Reusa `src.certificate.*`. Imports pesados (`cryptography`, `PyKCS11`) são
lazy — o app carrega mesmo sem eles; só a operação correspondente exige.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# CertificateInfo é só dataclass + cryptography (lazy via parser); para type
# hints usamos string. Não importar no topo para não exigir cryptography.


def formatar_certificado(info) -> list[tuple[str, str, str]]:
    """Converte um CertificateInfo em linhas (rótulo, valor, nível)."""
    if info.is_expired:
        nivel_validade = "err"
    elif info.days_to_expire <= 30:
        nivel_validade = "warn"
    else:
        nivel_validade = "ok"

    validade = info.validity_status
    if info.not_after:
        validade += f" (até {info.not_after:%d/%m/%Y})"

    linhas = [
        ("Titular", info.holder_name or "—", "info"),
        ("CPF", info.cpf or "—", "info"),
        ("OAB", info.oab or "—", "info"),
        ("E-mail", info.email or "—", "info"),
        ("Emissor", info.issuer_cn or "—", "info"),
        ("Nº de série", info.serial_number or "—", "info"),
        ("Uso da chave", info.key_usage or "—", "info"),
        ("Validade", validade, nivel_validade),
    ]
    if info.cnpj:
        linhas.insert(3, ("CNPJ", info.cnpj, "info"))
    return linhas


# ─────────────────────────── A1 (PFX/P12) ───────────────────────────

def carregar_a1(caminho: str, senha: str):
    """Carrega e parseia um PFX/P12. Retorna (CertificateInfo|None, erro|None)."""
    path = Path(caminho).expanduser()
    if not path.is_file():
        return None, f"Arquivo não encontrado: {path}"
    try:
        from src.certificate.a1_manager import A1Manager
    except ImportError as exc:
        return None, f"Dependência ausente (cryptography): {exc}"

    try:
        info = A1Manager().load_pfx(str(path), senha)
    except Exception as exc:  # noqa: BLE001
        return None, f"Falha ao ler PFX: {exc}"
    if info is None:
        return None, "Senha inválida ou arquivo corrompido."
    return info, None


# ─────────────────────────── A3 (token) ───────────────────────────

class A3Service:
    """Mantém um A3Manager entre detecção e leitura (PIN uma vez)."""

    def __init__(self) -> None:
        self._mgr = None
        self._modulo: Optional[str] = None

    def disponivel(self) -> bool:
        try:
            import PyKCS11  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False

    def _manager(self):
        if self._mgr is None:
            from src.certificate.a3_manager import A3Manager
            from src.certificate.token_database import TokenDatabase
            self._mgr = A3Manager(TokenDatabase())
        return self._mgr

    def detectar(self):
        """Acha o módulo PKCS#11 e enumera slots. Retorna (modulo, slots, erro)."""
        if not self.disponivel():
            return None, [], "PyKCS11 não instalado (necessário para tokens A3)."
        try:
            modulo, slots = self._manager().try_all_modules()
        except Exception as exc:  # noqa: BLE001
            return None, [], f"Falha ao detectar token: {exc}"
        if not modulo:
            return None, [], "Nenhum token A3 com certificado encontrado."
        self._modulo = modulo
        return modulo, slots, None

    def ler(self, slot_id: int, pin: str):
        """Faz login e lista certificados do slot. Retorna (certs, erro)."""
        mgr = self._manager()
        if not mgr.login(slot_id, pin):
            return [], "Login falhou — PIN incorreto ou token bloqueado."
        try:
            certs = mgr.list_certificates(slot_id)
        except Exception as exc:  # noqa: BLE001
            return [], f"Falha ao ler certificados: {exc}"
        if not certs:
            return [], "Login OK, mas nenhum certificado foi encontrado no token."
        return certs, None

    def fechar(self) -> None:
        if self._mgr is not None:
            try:
                self._mgr.logout()
            except Exception:  # noqa: BLE001
                pass
