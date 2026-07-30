# Script PowerShell para criar o ZIP do plugin ISTools v1.5.3
# Agora residindo em istools/scripts/ e garantindo a estrutura exigida pelo QGIS

$PLUGINNAME = "istools"
$VERSION = "1.5.3"
$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ISTOOLS_DIR = Split-Path -Parent $SCRIPT_DIR
$PROJECT_ROOT = Split-Path -Parent $ISTOOLS_DIR

$OUTPUT_ZIP = Join-Path $PROJECT_ROOT "$PLUGINNAME-v$VERSION.zip"
$TEMP_BASE = Join-Path $PROJECT_ROOT "temp_build_qgis"

Write-Host "Iniciando empacotamento do ISTools v$VERSION..." -ForegroundColor Cyan

# 1. Limpeza
if (Test-Path $TEMP_BASE) { Remove-Item $TEMP_BASE -Recurse -Force }
if (Test-Path $OUTPUT_ZIP) { Remove-Item $OUTPUT_ZIP -Force }

# 2. Criar estrutura: temp_build_qgis/istools/
$TEMP_PLUGIN_PATH = Join-Path $TEMP_BASE $PLUGINNAME
New-Item -ItemType Directory -Path $TEMP_PLUGIN_PATH -Force | Out-Null

Write-Host "Copiando arquivos da suite 1.5.3..." -ForegroundColor Yellow

# Exclusoes (caches, git, etc)
$exclude = @("*.pyc", "*.pyo", "__pycache__", ".git*", "temp_*", "test_*", "*.zip")

# Copia Recursiva
Copy-Item -Path "$ISTOOLS_DIR\*" -Destination $TEMP_PLUGIN_PATH -Recurse -Force -Exclude $exclude

# Copy-Item pode preservar diretórios __pycache__ vazios mesmo quando os
# arquivos .pyc são excluídos. Eles não fazem parte do pacote de runtime.
Get-ChildItem -Path $TEMP_PLUGIN_PATH -Directory -Recurse -Force |
    Where-Object { $_.Name -eq "__pycache__" } |
    Remove-Item -Recurse -Force

# 3. Limpeza pos-copia (remover scripts de build do pacote final)
Remove-Item -Path "$TEMP_PLUGIN_PATH\scripts\create_zip.ps1" -Force -ErrorAction SilentlyContinue
# Os scripts Python deste diretório são utilitários de desenvolvimento e
# referências standalone. O runtime do plugin utiliza apenas os dois scripts
# SQL oficiais abaixo; portanto, os utilitários não integram a distribuição.
Get-ChildItem -Path "$TEMP_PLUGIN_PATH\scripts" -Force |
    Where-Object { $_.Name -ne "sql_creator_database_edgv" } |
    Remove-Item -Recurse -Force
Remove-Item -Path "$TEMP_PLUGIN_PATH\tests" -Recurse -Force -ErrorAction SilentlyContinue
@(".gitignore", "Makefile", "pb_tool.cfg", "pylintrc", "RELEASE-GUIA.md") | ForEach-Object {
    Remove-Item -Path (Join-Path $TEMP_PLUGIN_PATH $_) -Force -ErrorAction SilentlyContinue
}

# 4. Criacao do ZIP com caminhos normalizados para o padrao do repositorio QGIS
Write-Host "Gerando arquivo ZIP: $OUTPUT_ZIP..." -ForegroundColor Green
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open(
    $OUTPUT_ZIP,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    Get-ChildItem -Path $TEMP_PLUGIN_PATH -File -Recurse | ForEach-Object {
        $entryName = $_.FullName.Substring($TEMP_BASE.Length + 1).Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $_.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $archive.Dispose()
}

# 5. Cleanup
# Tentar remover, mas ignorar se estiver travado (Windows as vezes trava threads de IO)
Remove-Item $TEMP_BASE -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "`n✅ Build concluído com sucesso!" -ForegroundColor Green
Write-Host "O arquivo $OUTPUT_ZIP está pronto para o QGIS." -ForegroundColor Yellow
