"""CLI do Big Advogados — entry-point ``big-advogados``.

Comando principal: ``big-advogados transcrever <arquivo>...``

Modos:
- **Modo simples** — sem flag ``--processo``, gera um PDF por áudio com
  layout enxuto.
- **Modo formal (declaração técnica)** — com ``--processo`` e demais flags
  de caso, gera **um único PDF** agregando todos os áudios passados, no
  formato do Anexo 12 do projeto-piloto.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import typer
    _HAS_TYPER = True
except ImportError:
    typer = None  # type: ignore[assignment]
    _HAS_TYPER = False

from src.transcritor import config as cfg_module
from src.transcritor.engine import transcribe
from src.transcritor.metadata import compute_metadata, get_environment_metadata
from src.transcritor.pdf_builder import (
    AudioEntry,
    CoSubscritor,
    DadosCaso,
    build_pdf,
    build_pdf_formal,
)
from src.transcritor.writers import (
    write_markdown,
    write_metadata_json,
    write_segments_csv,
    write_txt,
)

log = logging.getLogger("big-advogados.cli")

SAIDAS_VALIDAS = {"txt", "md", "pdf", "json", "csv", "todos"}


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _detectar_data_no_nome(nome: str) -> str:
    """Tenta extrair data 'DD/MM/AAAA — HHhMM' do nome do arquivo no padrão
    'AUDIO-2026-04-17-16-17-06.m4a' → '01/01/2026 — 00h00'."""
    # Padrão: AAAA-MM-DD-HH-MM-SS
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})(?:-(\d{2}))?", nome)
    if m:
        ano, mes, dia, h, mi = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        return f"{dia}/{mes}/{ano} — {h}h{mi}"
    return ""


def _aplicar_overrides(
    cfg: cfg_module.TranscritorConfig,
    modelo: Optional[str],
    idioma: Optional[str],
) -> cfg_module.TranscritorConfig:
    """Aplica overrides de CLI sobre a config carregada."""
    if modelo:
        cfg = cfg_module.TranscritorConfig(
            modelo=cfg_module.ModeloConfig(
                nome=modelo,
                device=cfg.modelo.device,
                compute_type=cfg.modelo.compute_type,
            ),
            transcricao=cfg.transcricao,
            identidade_visual=cfg.identidade_visual,
            advogado=cfg.advogado,
        )
    if idioma:
        cfg = cfg_module.TranscritorConfig(
            modelo=cfg.modelo,
            transcricao=cfg_module.TranscricaoConfig(
                idioma=idioma,
                beam_size=cfg.transcricao.beam_size,
                temperature=cfg.transcricao.temperature,
                vad_filter=cfg.transcricao.vad_filter,
                word_timestamps=cfg.transcricao.word_timestamps,
                condition_on_previous_text=cfg.transcricao.condition_on_previous_text,
            ),
            identidade_visual=cfg.identidade_visual,
            advogado=cfg.advogado,
        )
    return cfg


def _parse_destaques(specs: list[str], n_audios: int) -> dict[int, list[int]]:
    """Parse '--destacar-segmento N:M' → dict[audio_idx (1-based)] → [seg_idx, ...].

    Aceita também o formato simplificado 'M' (sem ':') quando há apenas 1 áudio,
    interpretando como audio 1, segmento M.
    """
    destaques: dict[int, list[int]] = {}
    for spec in specs:
        s = spec.strip()
        if not s:
            continue
        if ":" in s:
            audio_str, seg_str = s.split(":", 1)
        elif n_audios == 1:
            audio_str, seg_str = "1", s
        else:
            log.warning("--destacar-segmento '%s' ignorado (formato esperado: AUDIO:SEG)", s)
            continue
        try:
            audio_idx = int(audio_str)
            seg_idx = int(seg_str)
        except ValueError:
            log.warning("--destacar-segmento '%s' ignorado (não numérico)", s)
            continue
        if audio_idx < 1 or audio_idx > n_audios:
            log.warning("--destacar-segmento '%s': áudio %d fora do range (1..%d)",
                        s, audio_idx, n_audios)
            continue
        destaques.setdefault(audio_idx, []).append(seg_idx)
    return destaques


def _parse_co_subscritor(spec: Optional[str]) -> Optional[CoSubscritor]:
    """Parse '--co-subscritor "Nome — OAB/UF Número"'."""
    if not spec:
        return None
    if "—" in spec:
        partes = spec.split("—", 1)
    elif "-" in spec and " " in spec:
        # último hífen separando OAB
        partes = spec.rsplit("-", 1)
    else:
        return CoSubscritor(nome=spec.strip(), oab="")
    nome = partes[0].strip()
    oab = partes[1].strip()
    return CoSubscritor(nome=nome, oab=oab)


def run_transcrever(
    arquivos: list[Path],
    modelo: Optional[str],
    idioma: Optional[str],
    saidas: set[str],
    config_path: Optional[Path],
    verbose: bool,
    # ─── flags do modo formal ───
    processo: Optional[str] = None,
    cliente: Optional[str] = None,
    contraparte: Optional[str] = None,
    documento: Optional[str] = None,
    juizo: Optional[str] = None,
    posicao_cliente: str = "Agravada",
    posicao_contraparte: str = "Agravante",
    data_declaracao: Optional[str] = None,
    local: str = "Salvador/BA",
    remetente_nome: Optional[str] = None,
    remetente_oab: Optional[str] = None,
    co_subscritor: Optional[str] = None,
    saida_formal: Optional[Path] = None,
    destacar_segmentos: Optional[list[str]] = None,
) -> int:
    """Implementação do subcomando `transcrever`."""
    _setup_logging(verbose)

    cfg = cfg_module.load_config(config_path or cfg_module.CONFIG_FILE)
    cfg = _aplicar_overrides(cfg, modelo, idioma)

    if "todos" in saidas:
        saidas = {"txt", "md", "pdf", "json", "csv"}

    # Modo formal exige --processo
    modo_formal = bool(processo)

    if modo_formal:
        return _executar_modo_formal(
            arquivos, cfg, saidas,
            processo=processo or "",
            cliente=cliente or "",
            contraparte=contraparte or "",
            documento=documento or "",
            juizo=juizo or "",
            posicao_cliente=posicao_cliente,
            posicao_contraparte=posicao_contraparte,
            data_declaracao=data_declaracao or "",
            local=local,
            remetente_nome=remetente_nome or "",
            remetente_oab=remetente_oab or "",
            co_subscritor_spec=co_subscritor,
            saida_formal=saida_formal,
            destaque_specs=destacar_segmentos or [],
        )

    # Modo simples (1 PDF por áudio)
    erros = 0
    for arquivo in arquivos:
        try:
            _processar_modo_simples(arquivo, cfg, saidas)
        except FileNotFoundError as exc:
            log.error("%s", exc)
            erros += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao processar %s: %s", arquivo, exc)
            erros += 1

    return 1 if erros else 0


def _processar_modo_simples(
    arquivo: Path,
    cfg: cfg_module.TranscritorConfig,
    saidas: set[str],
) -> None:
    log.info("=" * 60)
    log.info("Arquivo: %s", arquivo)

    audio = compute_metadata(arquivo)
    log.info("SHA-256: %s", audio.sha256)
    if audio.duracao_segundos:
        log.info("Duração: %.2fs", audio.duracao_segundos)

    env = get_environment_metadata()
    result = transcribe(arquivo, cfg)
    log.info(
        "Transcrição concluída: %d segmentos, idioma=%s (prob=%.3f)",
        len(result.segments), result.idioma_detectado, result.probabilidade_idioma,
    )

    base = arquivo.with_suffix("")
    if "txt" in saidas:
        out = base.parent / f"{base.name}.transcricao.txt"
        write_txt(out, result)
        log.info("Escrito: %s", out)
    if "md" in saidas:
        out = base.parent / f"{base.name}.transcricao.md"
        write_markdown(out, audio, env, result)
        log.info("Escrito: %s", out)
    if "pdf" in saidas:
        out = base.parent / f"{base.name}.transcricao.pdf"
        build_pdf(out, audio, env, result, cfg.identidade_visual, cfg.advogado)
        log.info("Escrito: %s", out)
    if "json" in saidas:
        out = base.parent / f"{base.name}.metadata.json"
        write_metadata_json(out, audio, env, result)
        log.info("Escrito: %s", out)
    if "csv" in saidas:
        out = base.parent / f"{base.name}.segments.csv"
        write_segments_csv(out, result)
        log.info("Escrito: %s", out)


def _executar_modo_formal(
    arquivos: list[Path],
    cfg: cfg_module.TranscritorConfig,
    saidas: set[str],
    *,
    processo: str,
    cliente: str,
    contraparte: str,
    documento: str,
    juizo: str,
    posicao_cliente: str,
    posicao_contraparte: str,
    data_declaracao: str,
    local: str,
    remetente_nome: str,
    remetente_oab: str,
    co_subscritor_spec: Optional[str],
    saida_formal: Optional[Path],
    destaque_specs: list[str],
) -> int:
    log.info("=" * 60)
    log.info("Modo formal — Declaração técnica (%d áudios)", len(arquivos))
    destaques = _parse_destaques(destaque_specs, len(arquivos))
    if destaques:
        log.info("Destaques: %s", destaques)
    log.info("Processo: %s", processo)
    if cliente and contraparte:
        log.info("Caso: %s x %s", cliente, contraparte)

    env = get_environment_metadata()
    entries: list[AudioEntry] = []

    for arquivo in arquivos:
        try:
            log.info("─ Processando %s", arquivo.name)
            audio_meta = compute_metadata(arquivo)
            log.info("  SHA-256: %s", audio_meta.sha256)
            result = transcribe(arquivo, cfg)
            log.info("  %d segmentos, idioma=%s",
                     len(result.segments), result.idioma_detectado)

            data_rec = _detectar_data_no_nome(arquivo.name)
            idx_audio = len(entries) + 1  # 1-based
            entries.append(AudioEntry(
                metadata=audio_meta,
                transcription=result,
                data_recebimento=data_rec,
                segmentos_destacados=tuple(destaques.get(idx_audio, [])),
            ))

            # Saídas individuais (txt/md/json/csv) por áudio — útil pra
            # ter os arquivos separados como backup
            base = arquivo.with_suffix("")
            if "txt" in saidas:
                write_txt(base.parent / f"{base.name}.transcricao.txt", result)
            if "md" in saidas:
                write_markdown(base.parent / f"{base.name}.transcricao.md",
                               audio_meta, env, result)
            if "json" in saidas:
                write_metadata_json(base.parent / f"{base.name}.metadata.json",
                                    audio_meta, env, result)
            if "csv" in saidas:
                write_segments_csv(base.parent / f"{base.name}.segments.csv", result)

        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao processar %s: %s", arquivo, exc)
            return 1

    # PDF formal: 1 só, agregando todos os áudios
    caso = DadosCaso(
        processo=processo,
        cliente=cliente,
        contraparte=contraparte,
        documento=documento,
        juizo=juizo,
        posicao_cliente=posicao_cliente,
        posicao_contraparte=posicao_contraparte,
        data_declaracao=data_declaracao,
        local=local,
        remetente_nome=remetente_nome,
        remetente_oab=remetente_oab,
    )
    co_sub = _parse_co_subscritor(co_subscritor_spec)

    # Decide nome de saída
    if saida_formal is None:
        primeiro = arquivos[0]
        saida_formal = primeiro.parent / f"Declaracao-tecnica-{processo.split('-')[0] or 'transcricoes'}.pdf"

    if "pdf" in saidas:
        build_pdf_formal(saida_formal, entries, env,
                        cfg.identidade_visual, cfg.advogado, caso, co_sub)
        log.info("PDF formal: %s", saida_formal)

    return 0


# ─────────────────────────── typer wiring ───────────────────────────

if _HAS_TYPER:
    app = typer.Typer(
        name="big-advogados",
        help="Stack jurídica do Big Advogados — comandos para advogados Linux.",
        no_args_is_help=True,
        rich_markup_mode="rich",
    )

    @app.callback()
    def _root() -> None:
        """Força typer a tratar como multi-command mesmo com um único comando."""

    @app.command(help="Transcreve áudio com cadeia de custódia (SHA-256 + PDF formal).")
    def transcrever(
        arquivos: list[Path] = typer.Argument(
            ..., exists=True, dir_okay=False, readable=True,
            help="Um ou mais arquivos de áudio (M4A, MP3, OPUS, OGG, WAV, FLAC).",
        ),
        modelo: Optional[str] = typer.Option(
            None, "--modelo", "-m",
            help="Override do modelo: tiny, base, small, medium, large-v3.",
        ),
        idioma: Optional[str] = typer.Option(
            None, "--idioma", "-i",
            help="Código ISO do idioma (pt, en, es, ...). Default: pt.",
        ),
        saida: list[str] = typer.Option(
            ["todos"], "--saida", "-s",
            help="Formatos a gerar: txt, md, pdf, json, csv, todos.",
        ),
        config: Optional[Path] = typer.Option(
            None, "--config", "-c",
            help="Override do path da config.",
        ),
        verbose: bool = typer.Option(False, "--verbose", "-v"),
        # ─── modo formal ───
        processo: Optional[str] = typer.Option(
            None, "--processo",
            help="[MODO FORMAL] Número do processo (ativa template de declaração técnica).",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        cliente: Optional[str] = typer.Option(
            None, "--cliente",
            help="Nome da parte que você representa.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        contraparte: Optional[str] = typer.Option(
            None, "--contraparte",
            help="Nome da parte adversa.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        documento: Optional[str] = typer.Option(
            None, "--documento",
            help="Descrição do documento ao qual se anexa.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        juizo: Optional[str] = typer.Option(
            None, "--juizo",
            help="Órgão julgador (ex.: 'Câmara Cível do Tribunal de Justiça').",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        posicao_cliente: str = typer.Option(
            "Agravada", "--posicao-cliente",
            help="Polo processual do cliente (Agravada, Autora, Ré, etc.).",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        posicao_contraparte: str = typer.Option(
            "Agravante", "--posicao-contraparte",
            help="Polo processual da contraparte.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        data_declaracao: Optional[str] = typer.Option(
            None, "--data-declaracao",
            help="Data por extenso (default: hoje).",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        local: str = typer.Option(
            "Salvador/BA", "--local",
            help="Cidade onde a declaração é firmada.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        remetente_nome: Optional[str] = typer.Option(
            None, "--remetente-nome",
            help="Nome do advogado que enviou os áudios.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        remetente_oab: Optional[str] = typer.Option(
            None, "--remetente-oab",
            help="OAB do remetente.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        co_subscritor: Optional[str] = typer.Option(
            None, "--co-subscritor",
            help="Segundo advogado: 'Nome — OAB/UF Número'.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        saida_formal: Optional[Path] = typer.Option(
            None, "--saida-formal",
            help="Path do PDF formal agregado. Default: 'Declaracao-tecnica-<processo>.pdf' na pasta do primeiro áudio.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
        destacar_segmento: list[str] = typer.Option(
            [], "--destacar-segmento", "-d",
            help="Destaca segmentos específicos na tabela: 'AUDIO:SEG' (ex.: '1:4' = áudio 1, segmento 4). Para áudio único, basta 'SEG'. Pode repetir a flag.",
            rich_help_panel="Modo formal (declaração técnica)",
        ),
    ) -> None:
        invalidas = set(saida) - SAIDAS_VALIDAS
        if invalidas:
            typer.secho(
                f"Saídas inválidas: {', '.join(invalidas)}. "
                f"Válidas: {', '.join(sorted(SAIDAS_VALIDAS))}",
                fg=typer.colors.RED, err=True,
            )
            raise typer.Exit(code=2)

        code = run_transcrever(
            arquivos=arquivos,
            modelo=modelo,
            idioma=idioma,
            saidas=set(saida),
            config_path=config,
            verbose=verbose,
            processo=processo,
            cliente=cliente,
            contraparte=contraparte,
            documento=documento,
            juizo=juizo,
            posicao_cliente=posicao_cliente,
            posicao_contraparte=posicao_contraparte,
            data_declaracao=data_declaracao,
            local=local,
            remetente_nome=remetente_nome,
            remetente_oab=remetente_oab,
            co_subscritor=co_subscritor,
            saida_formal=saida_formal,
            destacar_segmentos=destacar_segmento,
        )
        raise typer.Exit(code=code)

else:
    def app() -> None:  # type: ignore[no-redef]
        import argparse
        parser = argparse.ArgumentParser(prog="big-advogados")
        sub = parser.add_subparsers(dest="cmd", required=True)
        tr = sub.add_parser("transcrever")
        tr.add_argument("arquivos", nargs="+", type=Path)
        tr.add_argument("--modelo", "-m")
        tr.add_argument("--idioma", "-i")
        tr.add_argument("--saida", "-s", action="append")
        tr.add_argument("--verbose", "-v", action="store_true")
        args = parser.parse_args()
        sys.exit(run_transcrever(
            arquivos=args.arquivos,
            modelo=args.modelo,
            idioma=args.idioma,
            saidas=set(args.saida or ["todos"]),
            config_path=None,
            verbose=args.verbose,
        ))


def main() -> None:
    if _HAS_TYPER:
        app()
    else:
        app()  # type: ignore[misc]


if __name__ == "__main__":
    main()
