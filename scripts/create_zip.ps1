# Script PowerShell para criar o ZIP do plugin ISTools v1.5.0
# Agora residindo em istools/scripts/ e garantindo a estrutura exigida pelo QGIS

$PLUGINNAME = "istools"
$VERSION = "1.5.0"

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

Write-Host "Copiando arquivos da suite 1.5.0..." -ForegroundColor Yellow

# Exclusoes (caches, git, etc)
$exclude = @("*.pyc", "*.pyo", "__pycache__", ".git*", "temp_*", "test_*", "*.zip")

# Copia Recursiva
Copy-Item -Path "$ISTOOLS_DIR\*" -Destination $TEMP_PLUGIN_PATH -Recurse -Force -Exclude $exclude

# 3. Limpeza pos-copia (remover scripts de build do pacote final)
Remove-Item -Path "$TEMP_PLUGIN_PATH\scripts\create_zip.ps1" -Force -ErrorAction SilentlyContinue

# 4. Criacao do ZIP (Compactando o CONTEUDO da temp_base, que eh a pasta istools)
Write-Host "Gerando arquivo ZIP: $OUTPUT_ZIP..." -ForegroundColor Green
# Usar a pasta do plugin como path direto garante que ela seja a raiz do ZIP no Windows
Compress-Archive -Path $TEMP_PLUGIN_PATH -DestinationPath $OUTPUT_ZIP -Force

# 5. Cleanup
# Tentar remover, mas ignorar se estiver travado (Windows as vezes trava threads de IO)
Remove-Item $TEMP_BASE -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "`n✅ Build concluído com sucesso!" -ForegroundColor Green
Write-Host "O arquivo $OUTPUT_ZIP está pronto para o QGIS." -ForegroundColor Yellow
