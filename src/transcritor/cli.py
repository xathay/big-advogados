"""CLI do Big Advogados — entry-point ``big-advogados``.

Comandos:
  big-advogados transcrever <arquivo> [--modelo X] [--idioma pt] [--saida fmt]

A CLI é fina: parsing → carrega config → chama pipeline → escreve saídas.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

# typer é dep nova; cair pra argparse se não estiver disponível
try:
    import typer
    _HAS_TYPER = True
except ImportError:
    typer = None  # type: ignore[assignment]
    _HAS_TYPER = False

from src.transcritor import config as cfg_module
from src.transcritor.engine import transcribe
from src.transcritor.metadata import compute_metadata, get_environment_metadata
from src.transcritor.pdf_builder import build_pdf
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


def run_transcrever(
    arquivos: list[Path],
    modelo: Optional[str],
    idioma: Optional[str],
    saidas: set[str],
    config_path: Optional[Path],
    verbose: bool,
) -> int:
    """Implementação do subcomando `transcrever` — sem dep de typer."""
    _setup_logging(verbose)

    cfg = cfg_module.load_config(config_path or cfg_module.CONFIG_FILE)

    # Overrides via flag
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

    if "todos" in saidas:
        saidas = {"txt", "md", "pdf", "json", "csv"}

    erros = 0
    for arquivo in arquivos:
        try:
            _processar_um_arquivo(arquivo, cfg, saidas)
        except FileNotFoundError as exc:
            log.error("%s", exc)
            erros += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao processar %s: %s", arquivo, exc)
            erros += 1

    return 1 if erros else 0


def _processar_um_arquivo(
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


# ─────────────────────────── typer entry-points ───────────────────────────

if _HAS_TYPER:
    app = typer.Typer(
        name="big-advogados",
        help="Stack jurídica do Big Advogados — comandos para advogados Linux.",
        no_args_is_help=True,
        rich_markup_mode="rich",
    )

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
            help="Formatos a gerar: txt, md, pdf, json, csv, todos. Pode repetir a flag.",
        ),
        config: Optional[Path] = typer.Option(
            None, "--config", "-c",
            help="Override do path da config (default: ~/.config/big-advogados/transcritor.toml).",
        ),
        verbose: bool = typer.Option(False, "--verbose", "-v"),
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
        )
        raise typer.Exit(code=code)

else:
    # Fallback argparse — funciona sem instalar typer
    def app() -> None:  # type: ignore[no-redef]
        import argparse

        parser = argparse.ArgumentParser(
            prog="big-advogados",
            description="Stack jurídica do Big Advogados.",
        )
        sub = parser.add_subparsers(dest="cmd", required=True)

        tr = sub.add_parser("transcrever", help="Transcreve áudio com cadeia de custódia.")
        tr.add_argument("arquivos", nargs="+", type=Path)
        tr.add_argument("--modelo", "-m", default=None)
        tr.add_argument("--idioma", "-i", default=None)
        tr.add_argument("--saida", "-s", action="append", default=None)
        tr.add_argument("--config", "-c", type=Path, default=None)
        tr.add_argument("--verbose", "-v", action="store_true")

        args = parser.parse_args()

        if args.cmd == "transcrever":
            saidas = set(args.saida or ["todos"])
            invalidas = saidas - SAIDAS_VALIDAS
            if invalidas:
                print(
                    f"Saídas inválidas: {', '.join(invalidas)}. "
                    f"Válidas: {', '.join(sorted(SAIDAS_VALIDAS))}",
                    file=sys.stderr,
                )
                sys.exit(2)

            code = run_transcrever(
                arquivos=args.arquivos,
                modelo=args.modelo,
                idioma=args.idioma,
                saidas=saidas,
                config_path=args.config,
                verbose=args.verbose,
            )
            sys.exit(code)


def main() -> None:
    """Entry-point chamado pelo console_scripts ou /usr/bin/big-advogados."""
    if _HAS_TYPER:
        app()
    else:
        app()  # type: ignore[misc]


if __name__ == "__main__":
    main()
