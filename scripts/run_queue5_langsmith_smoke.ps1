param(
  [Parameter(Mandatory = $true)]
  [string]$OutputDir,

  [switch]$ExecuteLive,

  [string]$RunId = ('queue5-langsmith-run-' + [Guid]::NewGuid().ToString('N')),

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

if ($RunId -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$') {
  [Console]::Error.WriteLine('RunId must be a safe 1-80 character identifier.')
  exit 2
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

$uvArgs = @(
  'run',
  '--offline',
  '--no-sync',
  '--no-default-groups',
  '--group', 'stage1b',
  '--group', 'founder-api',
  '--group', 'dev',
  'python',
  '-m',
  'due_diligence_agent.evals.langsmith_live_smoke',
  '--output-dir', $resolvedOutputDir,
  '--run-id', $RunId
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
