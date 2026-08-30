param(
  [Parameter(Mandatory = $true)]
  [string]$OutputDir,

  [string]$UvExecutable = 'uv'
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path

if ([System.IO.Path]::IsPathRooted($OutputDir)) {
  $resolvedOutputDir = [System.IO.Path]::GetFullPath($OutputDir)
} else {
  $resolvedOutputDir = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDir))
}

$env:OPENAI_API_KEY = ''
$env:OPENAI_STARTUP_API_KEY = ''
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:DDA_LANGSMITH_TRACING = 'false'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:UV_OFFLINE = 'true'

$exitCode = 0
Push-Location $repoRoot
try {
  & $UvExecutable run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev investment-dd run-gate-c --dataset startup_secure_ingest_v1 --output-dir $resolvedOutputDir
  if ($null -ne $LASTEXITCODE) {
    $exitCode = $LASTEXITCODE
  }
} finally {
  Pop-Location
}

exit $exitCode
