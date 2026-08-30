param(
  [Parameter(Mandatory = $true)]
  [string]$OutputDir,

  [switch]$ExecuteLive,

  [string]$UvExecutable = 'uv'
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path
$resolvedOutputDir = if ([System.IO.Path]::IsPathRooted($OutputDir)) {
  [System.IO.Path]::GetFullPath($OutputDir)
} else {
  [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDir))
}

if ($resolvedOutputDir -eq $repoRoot) {
  [Console]::Error.WriteLine('OutputDir must not be the repository root.')
  exit 2
}

$env:OPENAI_STARTUP_API_KEY = ''
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:DDA_LANGSMITH_TRACING = 'false'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:UV_OFFLINE = 'true'

$uvArgs = @(
  'run',
  '--offline',
  '--no-sync',
  '--no-default-groups',
  '--group', 'stage1b',
  '--group', 'founder-api',
  '--group', 'llm-openai',
  '--group', 'dev',
  'python',
  '-m',
  'due_diligence_agent.evals.openai_competitor_smoke',
  '--output-dir', $resolvedOutputDir
)

if ($ExecuteLive) {
  $uvArgs += '--execute-live'
}

$exitCode = 0
Push-Location $repoRoot
try {
  & $UvExecutable @uvArgs
  if ($null -ne $LASTEXITCODE) {
    $exitCode = $LASTEXITCODE
  }
} finally {
  Pop-Location
}

exit $exitCode
