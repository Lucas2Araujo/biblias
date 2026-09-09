#!/usr/bin/env python3
"""Script para compressão de bancos SQLite e geração do manifest.json.

Converte arquivos .sqlite para .sqlite.gz com compresslevel=9, calcula tamanhos
em bytes e gera o arquivo manifest.json para o app cliente apontando para
as releases do GitHub em Lucas2Araujo/biblias.

Uso:
    python scripts/compress_and_manifest.py [--tag v1.0] [--input-dir inst/sql] [--output-dir dist]
"""

import argparse
import gzip
import json
import os
import shutil
import sys
from pathlib import Path

# Mapeamento interno de metadados e nomes amigáveis das versões bíblicas
# Mantido no próprio script para fins de documentação, leitura posterior e logs.
BIBLE_NAMES: dict[str, str] = {
    "ACF": "Almeida Corrigida e Fiel",
    "ALM1911": "Almeida 1911",
    "ARA": "Almeida Revista e Atualizada",
    "ARC": "Almeida Revista e Corrigida",
    "AS21": "Almeida Século 21",
    "BLIVRE": "Bíblia Livre",
    "JFAA": "Almeida Atualizada",
    "KJA": "King James Atualizada",
    "KJF": "King James Fiel",
    "MENS": "A Mensagem",
    "NAA": "Nova Almeida Atualizada",
    "NBV": "Nova Bíblia Viva",
    "NTLH": "Nova Tradução na Linguagem de Hoje",
    "NVI": "Nova Versão Internacional",
    "NVT": "Nova Versão Transformadora",
    "OL": "O Livro",
    "TB": "Tradução Brasileira",
    "VFL": "Versão Fácil de Ler",
}

DEFAULT_CANDIDATE_DIRS: tuple[str, ...] = (
    "inst/sql",
    "assets/biblias",
    "biblias",
    "data/sql",
    "dist",
    ".",
)

GITHUB_REPO = "Lucas2Araujo/biblias"


def format_size(num_bytes: int) -> str:
    """Formata tamanho em bytes para representação legível (B, KB, MB)."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.2f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TB"


def resolve_input_dir(explicit_dir: str | None) -> Path:
    """Resolve o diretório de entrada com arquivos .sqlite."""
    if explicit_dir:
        path = Path(explicit_dir)
        if not path.is_dir():
            raise FileNotFoundError(f"Diretório de entrada especificado não existe: {path}")
        return path

    env_dir = os.environ.get("SQLITE_DIR")
    if env_dir:
        path = Path(env_dir)
        if path.is_dir():
            return path

    for candidate in DEFAULT_CANDIDATE_DIRS:
        path = Path(candidate)
        if path.is_dir() and any(path.glob("*.sqlite")):
            return path

    raise FileNotFoundError(
        f"Nenhum arquivo .sqlite encontrado nos diretórios padrão: {DEFAULT_CANDIDATE_DIRS}. "
        "Use --input-dir ou a variável de ambiente SQLITE_DIR."
    )


def determine_manifest_version(output_dir: Path, requested_version: int | None) -> int:
    """Determina a versão do manifesto (incremental se já existir)."""
    if requested_version is not None:
        return requested_version

    env_version = os.environ.get("MANIFEST_VERSION")
    if env_version and env_version.isdigit():
        return int(env_version)

    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data.get("version"), int):
                    return data["version"] + 1
        except Exception:
            pass

    return 1


def compress_sqlite(source_file: Path, target_file: Path) -> tuple[int, int]:
    """Comprime o arquivo .sqlite para .sqlite.gz com compresslevel=9.
    
    Retorna (tamanho_original, tamanho_comprimido) em bytes.
    """
    orig_size = source_file.stat().st_size
    with open(source_file, "rb") as f_in:
        with gzip.open(target_file, "wb", compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out, length=128 * 1024)
    comp_size = target_file.stat().st_size
    return orig_size, comp_size


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comprime bancos .sqlite em gzip (nível 9) e gera manifest.json."
    )
    parser.add_argument(
        "-i", "--input-dir",
        help="Diretório contendo os arquivos .sqlite (padrão: auto-detecção em inst/sql, assets/biblias, etc.)"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=os.environ.get("OUTPUT_DIR", "dist"),
        help="Diretório de saída para os arquivos .sqlite.gz e manifest.json (padrão: dist)"
    )
    parser.add_argument(
        "-t", "--tag",
        default=os.environ.get("RELEASE_TAG", "v1.0"),
        help="Tag da release do GitHub para as URLs de download (padrão: v1.0 ou $RELEASE_TAG)"
    )
    parser.add_argument(
        "-v", "--manifest-version",
        type=int,
        help="Versão inteira do manifesto (padrão: incremental baseado no manifest.json existente, ou 1)"
    )

    args = parser.parse_args()

    try:
        input_dir = resolve_input_dir(args.input_dir)
    except FileNotFoundError as err:
        print(f"[ERRO] {err}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    release_tag = args.tag.strip() if args.tag else "v1.0"
    if not release_tag:
        release_tag = "v1.0"

    sqlite_files = sorted(input_dir.glob("*.sqlite"))
    if not sqlite_files:
        print(f"[ERRO] Nenhum arquivo .sqlite encontrado em {input_dir}", file=sys.stderr)
        return 1

    print("=" * 80)
    print("COMPRESSÃO E GERAÇÃO DE MANIFESTO DE BÍBLIAS")
    print(f"Diretório de entrada: {input_dir.resolve()}")
    print(f"Diretório de saída:   {output_dir.resolve()}")
    print(f"Tag da Release:       {release_tag}")
    print(f"Total de bancos:      {len(sqlite_files)}")
    print("=" * 80)

    modules = []
    total_orig_bytes = 0
    total_comp_bytes = 0

    for idx, sqlite_file in enumerate(sqlite_files, 1):
        module_id = sqlite_file.stem
        friendly_name = BIBLE_NAMES.get(module_id, module_id)
        gz_filename = f"{module_id}.sqlite.gz"
        gz_path = output_dir / gz_filename

        orig_bytes, comp_bytes = compress_sqlite(sqlite_file, gz_path)
        total_orig_bytes += orig_bytes
        total_comp_bytes += comp_bytes

        ratio = (1.0 - (comp_bytes / orig_bytes)) * 100.0 if orig_bytes > 0 else 0.0

        download_url = (
            f"https://github.com/{GITHUB_REPO}/releases/download/{release_tag}/{gz_filename}"
        )

        modules.append({
            "id": module_id,
            "file": gz_filename,
            "size_bytes": comp_bytes,
            "url": download_url,
        })

        print(
            f"[{idx:2d}/{len(sqlite_files):2d}] {module_id:<7} ({friendly_name})\n"
            f"       Original:   {orig_bytes:>10,d} B ({format_size(orig_bytes)})\n"
            f"       Compactado: {comp_bytes:>10,d} B ({format_size(comp_bytes)})\n"
            f"       Redução:    {ratio:>6.2f}%\n"
            f"       Arquivo:    {gz_filename}"
        )

    manifest_version = determine_manifest_version(output_dir, args.manifest_version)

    manifest_data = {
        "version": manifest_version,
        "modules": modules,
    }

    manifest_file = output_dir / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    overall_ratio = (
        (1.0 - (total_comp_bytes / total_orig_bytes)) * 100.0
        if total_orig_bytes > 0
        else 0.0
    )

    print("-" * 80)
    print("[SUCESSO] Processamento concluído com sucesso!")
    print(f"Manifesto:             {manifest_file.resolve()}")
    print(f"Versão do manifesto:   {manifest_version}")
    print(f"Módulos registrados:   {len(modules)}")
    print(f"Tamanho total bruto:   {total_orig_bytes:,d} B ({format_size(total_orig_bytes)})")
    print(f"Tamanho total gzip:    {total_comp_bytes:,d} B ({format_size(total_comp_bytes)})")
    print(f"Redução média geral:   {overall_ratio:.2f}%")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())

