param(
  [Parameter(Mandatory = $true)]
  [string]$OutputDir,

  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[a-fA-F0-9]{40}$')]
  [string]$CommitId,

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
  'due_diligence_agent.evals.failure_matrix',
  '--output-dir', $resolvedOutputDir,
  '--commit-id', $CommitId
)

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
