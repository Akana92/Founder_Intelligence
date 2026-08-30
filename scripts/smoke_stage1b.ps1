[CmdletBinding()]
param(
  [switch]$Tesseract,
  [switch]$Presidio,
  [switch]$Docling
)

$ErrorActionPreference = 'Stop'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:PIP_NO_INDEX = '1'

function Invoke-Stage1bPython {
  param(
    [string[]]$Groups,
    [string]$Command
  )

  $uvArguments = @('run', '--offline', '--no-sync', '--no-default-groups')
  foreach ($group in $Groups) {
    $uvArguments += @('--group', $group)
  }
  $uvArguments += @('python', '-c', $Command)
  & uv @uvArguments
  if ($LASTEXITCODE -ne 0) {
    throw "Stage 1B no-network smoke failed (exit code $LASTEXITCODE)."
  }
}

$lightGroups = @('stage1b-light-ingest', 'stage1a-rag-local')
Invoke-Stage1bPython $lightGroups "import openpyxl,docx,fitz,pdfplumber; from PIL import Image; print('stage1b light ingest ok')"

if ($Tesseract) {
  $tesseractCommand = Get-Command tesseract -ErrorAction SilentlyContinue
  if (-not $tesseractCommand) {
    throw 'Tesseract adapter was selected, but tesseract is not available on PATH.'
  }
  & $tesseractCommand.Source --version
  if ($LASTEXITCODE -ne 0) {
    throw "Tesseract adapter smoke failed (exit code $LASTEXITCODE)."
  }
  Invoke-Stage1bPython ($lightGroups + 'stage1b-ocr-tesseract') "import pytesseract; print('stage1b tesseract adapter ok')"
}

if ($Presidio) {
  Invoke-Stage1bPython ($lightGroups + 'stage1b-redaction-presidio') "import presidio_analyzer,presidio_anonymizer; print('stage1b presidio adapter ok')"
}

if ($Docling) {
  Invoke-Stage1bPython ($lightGroups + 'stage1b-docling') "import docling; print('stage1b docling adapter ok')"
}

Write-Host 'stage1b staged no-network smoke ok'
