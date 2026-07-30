"""Gera um ZIP do ISTools compatível com o repositório oficial do QGIS."""

from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile


PLUGIN_NAME = "istools"
VERSION = "1.5.3"

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = PLUGIN_DIR.parent
OUTPUT_ZIP = PROJECT_ROOT / f"{PLUGIN_NAME}-v{VERSION}-qgis.zip"
TEMP_ZIP = PROJECT_ROOT / f".{PLUGIN_NAME}-v{VERSION}-qgis.tmp"

EXCLUDED_TOP_LEVEL = {
    ".gitignore",
    "Makefile",
    "pb_tool.cfg",
    "pylintrc",
    "RELEASE-GUIA.md",
    "tests",
}
EXCLUDED_PARTS = {".git", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}
REQUIRED_ENTRIES = {
    "istools/__init__.py",
    "istools/istools.py",
    "istools/metadata.txt",
    "istools/resources.py",
    "istools/icons/icon_istools.png",
    "istools/icons/icon_tifftools.png",
    "istools/processing/provider.py",
    "istools/data/edgv_300_mapping.json",
    "istools/data/edgv_30_to_topo_145.json",
    "istools/scripts/sql_creator_database_edgv/edgv_300_topo_14.sql",
    "istools/scripts/sql_creator_database_edgv/edgv_300_topo_extension_14.sql",
}


def should_include(relative_path: Path) -> bool:
    """Informa se o arquivo pertence ao pacote de execução do plugin."""
    if relative_path.parts[0] in EXCLUDED_TOP_LEVEL:
        return False
    if any(part in EXCLUDED_PARTS for part in relative_path.parts):
        return False
    if relative_path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if relative_path.parts[0].startswith("temp_"):
        return False

    if relative_path.parts[0] == "scripts":
        return (
            len(relative_path.parts) >= 3
            and relative_path.parts[1] == "sql_creator_database_edgv"
        )
    return True


def build_archive() -> None:
    """Cria e valida um arquivo sem entradas de diretório ou barras invertidas."""
    source_files = sorted(
        path
        for path in PLUGIN_DIR.rglob("*")
        if path.is_file() and should_include(path.relative_to(PLUGIN_DIR))
    )

    if TEMP_ZIP.exists():
        TEMP_ZIP.unlink()

    with ZipFile(TEMP_ZIP, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for source_path in source_files:
            relative_path = source_path.relative_to(PLUGIN_DIR)
            archive_name = str(
                PurePosixPath(PLUGIN_NAME).joinpath(*relative_path.parts)
            )
            if "\\" in archive_name:
                raise RuntimeError(f"Caminho ZIP inválido: {archive_name}")
            archive.write(source_path, archive_name)

    with ZipFile(TEMP_ZIP, "r") as archive:
        entries = archive.infolist()
        names = {entry.filename for entry in entries}
        invalid_names = [
            entry.filename
            for entry in entries
            if "\\" in entry.filename or entry.is_dir()
        ]
        missing_entries = sorted(REQUIRED_ENTRIES - names)

        if invalid_names:
            raise RuntimeError(
                "O arquivo contém caminhos inválidos: " + ", ".join(invalid_names)
            )
        if missing_entries:
            raise RuntimeError(
                "Arquivos obrigatórios ausentes: " + ", ".join(missing_entries)
            )
        if archive.testzip() is not None:
            raise RuntimeError("A verificação CRC do arquivo ZIP falhou.")

    TEMP_ZIP.replace(OUTPUT_ZIP)
    print(f"ZIP QGIS criado: {OUTPUT_ZIP}")
    print(f"Arquivos: {len(source_files)}")


if __name__ == "__main__":
    build_archive()
