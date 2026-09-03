"""Ponte GTK-free para assinatura digital de PDF (PAdES via endesive).

Reusa `src.certificate.pdf_signer` (A1 e A3). Imports pesados (`endesive`,
`cryptography`, `PyKCS11`) são lazy — o app carrega sem eles; só o ato de
assinar exige.
"""

from __future__ import annotations

from pathlib import Path

# Aparência do carimbo → (visible, signature_page, position)
VISUAIS = {
    "rodape": (True, "embed", "bottom"),
    "topo": (True, "embed", "top"),
    "pagina": (True, "append", "bottom"),
    "invisivel": (False, "embed", "bottom"),
}

MOTIVO_PADRAO = "Documento assinado digitalmente"


def dependencias_ok() -> tuple[bool, str]:
    """Verifica se endesive/pikepdf estão disponíveis para assinar."""
    try:
        import endesive  # type: ignore  # noqa: F401
        import pikepdf  # type: ignore  # noqa: F401
    except ImportError as exc:
        return False, f"Dependência ausente ({exc.name}) — instale python-endesive e python-pikepdf."
    return True, ""


def saida_padrao(pdf: str) -> str:
    """Caminho de saída padrão: mesmo diretório, sufixo `_assinado`."""
    p = Path(pdf).expanduser()
    return str(p.with_name(f"{p.stem}_assinado{p.suffix or '.pdf'}"))


def _opcoes(motivo: str, visual: str):
    from src.certificate.pdf_signer import SignatureOptions

    visible, page_mode, position = VISUAIS.get(visual, VISUAIS["rodape"])
    return SignatureOptions(
        reason=motivo.strip() or MOTIVO_PADRAO,
        visible=visible,
        signature_page=page_mode,
        position=position,
    )


def _validar_pdf(pdf: str) -> tuple[Path | None, str | None]:
    path = Path(pdf).expanduser()
    if not path.is_file():
        return None, f"PDF não encontrado: {path}"
    return path, None


def assinar_a1(pdf: str, pfx: str, senha: str, saida: str, motivo: str, visual: str):
    """Assina com certificado A1 (PFX/P12). Retorna (SignatureResult|None, erro|None)."""
    path, erro = _validar_pdf(pdf)
    if erro:
        return None, erro
    pfx_path = Path(pfx).expanduser()
    if not pfx_path.is_file():
        return None, f"Certificado não encontrado: {pfx_path}"
    ok, erro = dependencias_ok()
    if not ok:
        return None, erro

    from src.certificate.pdf_signer import sign_pdf

    destino = saida.strip() or saida_padrao(str(path))
    try:
        res = sign_pdf(str(path), str(pfx_path), senha, destino, _opcoes(motivo, visual))
    except Exception as exc:  # noqa: BLE001
        return None, f"Falha ao assinar: {exc}"
    if not res.success:
        return None, res.error or "Falha ao assinar."
    return res, None


def assinar_a3(pdf: str, pin: str, saida: str, motivo: str, visual: str):
    """Assina com token A3 (PKCS#11). Retorna (SignatureResult|None, erro|None).

    Fluxo autocontido: detecta o módulo, faz login no primeiro slot com token,
    extrai o certificado e assina — logout garantido ao final.
    """
    path, erro = _validar_pdf(pdf)
    if erro:
        return None, erro
    ok, erro = dependencias_ok()
    if not ok:
        return None, erro
    try:
        import PyKCS11  # type: ignore  # noqa: F401
    except ImportError:
        return None, "PyKCS11 não instalado (necessário para tokens A3)."

    from src.certificate.a3_manager import A3Manager
    from src.certificate.pdf_signer import sign_pdf_a3
    from src.certificate.token_database import TokenDatabase

    mgr = A3Manager(TokenDatabase())
    try:
        modulo, slots = mgr.try_all_modules()
        if not modulo or not slots:
            return None, "Nenhum token A3 encontrado — conecte o token e tente de novo."
        slot = slots[0].slot_id
        if not mgr.login(slot, pin):
            return None, "Login falhou — PIN incorreto ou token bloqueado."
        cert_der = mgr.get_certificate_der()
        if not cert_der:
            return None, "Login OK, mas nenhum certificado foi encontrado no token."
        destino = saida.strip() or saida_padrao(str(path))
        res = sign_pdf_a3(str(path), mgr, cert_der, destino, _opcoes(motivo, visual))
    except Exception as exc:  # noqa: BLE001
        return None, f"Falha ao assinar com o token: {exc}"
    finally:
        try:
            mgr.logout()
        except Exception:  # noqa: BLE001
            pass
    if not res.success:
        return None, res.error or "Falha ao assinar."
    return res, None
