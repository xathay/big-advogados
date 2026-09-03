#!/usr/bin/env python3
"""big-drivers-install — helper privilegiado para instalar drivers PKCS#11.

Invocado via pkexec a partir do big-advogados. Le o catalogo do disco
(em /usr/lib/big-certificados/data/drivers/) — nao confia no caller
para definir destinos. Re-verifica SHA-256 antes de escrever nada.

Argumentos:
    --driver <id>     Id do driver no catalogo (ex.: safesign)
    --source <path>   Arquivo local ja baixado (.deb)
    --sha256 <hash>   Hash informado pela UI (deve coincidir com o catalogo)

Saida (linhas):
    PROGRESS: <msg>   Estagio atual (UI traduz para spinner/barra)
    LOG: <msg>        Detalhe verboso (UI mostra na area de log)
    ERROR: <msg>      Falha; precede sys.exit(!=0)
"""
import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

CATALOG_DIR = Path("/usr/lib/big-certificados/data/drivers")

# Prefix base permitido — qualquer install.prefix do catalogo deve ficar
# dentro dele. Bloqueia uma entrada de catalogo maliciosa que tente
# escrever em /usr/lib/, /etc/, etc.
PREFIX_BASE = Path("/usr/local/lib/big-drivers")

# Whitelist de paths "shared" (fora do prefix) que aceitamos como destino.
# /usr/share/* cobre data files que bibliotecas proprietarias procuram
# em locais hardcoded (ex.: libaetpkss.so abre /usr/share/safesign/...).
SHARED_PATH_WHITELIST = (
    Path("/usr/share"),
    Path("/etc"),
    Path("/var/lib/big-drivers"),
)


def progress(msg: str) -> None:
    print(f"PROGRESS: {msg}", flush=True)


def log_line(msg: str) -> None:
    print(f"LOG: {msg}", flush=True)


def err(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", flush=True)
    sys.exit(code)


def copy_verified_source(source: Path, destination: Path) -> tuple[str, int]:
    """Copy from one opened descriptor while hashing, avoiding path races."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(source, flags)
    except OSError as exc:
        err(f"Nao foi possivel abrir o arquivo de origem com seguranca: {exc}")

    digest = hashlib.sha256()
    size = 0
    with os.fdopen(source_fd, "rb") as src, destination.open("xb") as dst:
        source_stat = os.fstat(src.fileno())
        if not stat.S_ISREG(source_stat.st_mode):
            err("Arquivo de origem nao e um arquivo regular")
        for chunk in iter(lambda: src.read(1 << 16), b""):
            digest.update(chunk)
            dst.write(chunk)
            size += len(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    destination.chmod(0o600)
    return digest.hexdigest(), size


def safe_join(base: Path, rel: str) -> Path:
    """Junta `rel` a `base` e verifica que o resultado nao escapa."""
    base_resolved = base.resolve()
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        err(f"Path escapa do prefixo: {rel}")
    return candidate


def assert_shared_allowed(target: Path) -> None:
    resolved = target.resolve() if target.exists() else target
    for allowed in SHARED_PATH_WHITELIST:
        try:
            resolved.relative_to(allowed)
            return
        except ValueError:
            continue
    err(f"Path shared nao permitido: {target}")


def detect_data_member(deb_path: Path) -> str:
    result = subprocess.run(
        ["ar", "t", str(deb_path)],
        capture_output=True, text=True, check=True,
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("data.tar"):
            return line
    err(f"{deb_path.name}: arquivo data.tar nao encontrado")


def tar_decompress_flag(member: str) -> list[str]:
    if member.endswith(".zst"):
        return ["--zstd"]
    if member.endswith(".xz"):
        return ["--xz"]
    if member.endswith(".gz"):
        return ["-z"]
    return []


def extract_deb(deb_path: Path, target_dir: Path) -> None:
    member = detect_data_member(deb_path)
    ar_proc = subprocess.Popen(
        ["ar", "p", str(deb_path), member],
        stdout=subprocess.PIPE,
    )
    tar_proc = subprocess.Popen(
        ["tar", *tar_decompress_flag(member), "-xf", "-", "-C", str(target_dir)],
        stdin=ar_proc.stdout,
    )
    if ar_proc.stdout is not None:
        ar_proc.stdout.close()
    tar_proc.communicate()
    ar_proc.wait()
    if tar_proc.returncode != 0:
        err(f"Falha ao extrair {deb_path.name}")


def validate_staging_tree(staging_dir: Path) -> None:
    """Reject special files and links escaping the root-owned staging tree."""
    staging_root = staging_dir.resolve()
    for root, dirnames, filenames in os.walk(staging_root, followlinks=False):
        root_path = Path(root)
        for name in [*dirnames, *filenames]:
            entry = root_path / name
            mode = entry.lstat().st_mode
            if stat.S_ISLNK(mode):
                link_target = os.readlink(entry)
                if Path(link_target).is_absolute():
                    err(f"Link absoluto recusado no pacote: {entry.name}")
                resolved = (entry.parent / link_target).resolve(strict=False)
                try:
                    resolved.relative_to(staging_root)
                except ValueError:
                    err(f"Link escapa da area de extracao: {entry.name}")
            elif not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                err(f"Tipo de arquivo especial recusado no pacote: {entry.name}")


def copy_tree(src: Path, dst: Path) -> None:
    """Copia src/. para dst preservando symlinks/perms/owners (root)."""
    dst.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-a", f"{src}/.", str(dst)], check=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--driver", required=True, help="id do driver no catalogo")
    p.add_argument("--source", required=True, help="arquivo local .deb")
    p.add_argument("--sha256", required=True, help="SHA-256 esperado")
    args = p.parse_args()

    if os.geteuid() != 0:
        err("Precisa ser executado como root (via pkexec)")

    source = Path(args.source)
    if not source.is_file():
        err(f"Source nao encontrado: {source}")
    # Recusa symlink para evitar TOCTOU (caller poderia trocar o alvo).
    if source.is_symlink():
        err("Source e symlink — recusado por seguranca")

    # Driver id: so caracteres seguros, evita path traversal no catalogo.
    if not args.driver.replace("-", "").replace("_", "").isalnum():
        err(f"Id de driver invalido: {args.driver}")

    catalog_path = CATALOG_DIR / f"{args.driver}.toml"
    if not catalog_path.is_file():
        err(f"Catalogo nao encontrado: {catalog_path}")

    progress("Lendo catalogo")
    with catalog_path.open("rb") as f:
        catalog = tomllib.load(f)
    if catalog.get("driver", {}).get("id") != args.driver:
        err("Id do driver nao coincide com o catalogo instalado")
    expected_hash = str(catalog.get("source", {}).get("sha256", "")).lower()
    if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
        err("SHA-256 invalido no catalogo instalado")
    if args.sha256.lower() != expected_hash:
        err("Hash informado pela interface nao coincide com o catalogo instalado")

    inst = catalog["install"]
    prefix = Path(inst["prefix"])

    # Confina o prefix dentro de PREFIX_BASE
    try:
        prefix.resolve().relative_to(PREFIX_BASE)
    except ValueError:
        err(f"Prefix {prefix} fora da base permitida {PREFIX_BASE}")

    # Conflitos: se shared_dirs ja existem e nao estao vazios, aborta.
    for entry in inst.get("shared_dirs", []):
        target = Path(entry["to"])
        assert_shared_allowed(target)
        if target.exists() and any(target.iterdir()):
            err(
                f"Conflito: {target} ja existe com conteudo. Remova outra "
                f"instalacao deste driver (ex.: 'pacman -R safesignidentityclient') "
                f"e tente novamente."
            )

    with tempfile.TemporaryDirectory(prefix="big-drivers-") as staging:
        staging_path = Path(staging)
        verified_source = staging_path / "source.deb"

        progress("Verificando integridade do arquivo de origem")
        actual, actual_size = copy_verified_source(source, verified_source)
        if actual != expected_hash:
            err(
                "SHA-256 nao coincide com o catalogo instalado "
                f"(esperado {expected_hash[:16]}..., obtido {actual[:16]}...)"
            )
        expected_size = catalog.get("source", {}).get("size_bytes")
        if isinstance(expected_size, int) and actual_size != expected_size:
            err(
                "Tamanho nao coincide com o catalogo instalado "
                f"(esperado {expected_size}, obtido {actual_size})"
            )

        progress("Extraindo arquivo de origem")
        extract_deb(verified_source, staging_path)
        validate_staging_tree(staging_path)

        progress(f"Instalando em {prefix}")
        prefix.mkdir(parents=True, exist_ok=True)

        for entry in inst.get("dirs", []):
            src_dir = safe_join(staging_path, entry["from"])
            target = safe_join(prefix, entry["to"])
            if not src_dir.is_dir():
                log_line(f"pulando {entry['from']} (nao existe no .deb)")
                continue
            log_line(f"copiando {entry['from']} -> {target}")
            copy_tree(src_dir, target)

        for entry in inst.get("shared_dirs", []):
            src_dir = safe_join(staging_path, entry["from"])
            target = Path(entry["to"])
            if not src_dir.is_dir():
                log_line(f"pulando {entry['from']} (nao existe no .deb)")
                continue
            log_line(f"copiando {entry['from']} -> {target}")
            copy_tree(src_dir, target)

    progress("Atualizando cache do linker")
    subprocess.run(["ldconfig"], check=False)

    progress("Concluido")
    log_line(f"Driver '{args.driver}' instalado em {prefix}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        err("Cancelado", code=130)
    except SystemExit:
        raise
    except Exception as exc:
        err(f"Erro inesperado: {exc}", code=1)
