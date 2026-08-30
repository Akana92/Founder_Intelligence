param(
  [Parameter(Mandatory = $true)]
  [string]$OutputDir,

  [Parameter(Mandatory = $true)]
  [string]$FrozenPacket,

  [Parameter(Mandatory = $true)]
  [string]$PdfBrowserEvidence,

  [Parameter(Mandatory = $true)]
  [string]$LangSmithEvidence,

  [Parameter(Mandatory = $true)]
  [string]$OpenAICompetitorEvidence,

  [Parameter(Mandatory = $true)]
  [string]$FailureMatrix,

  [Parameter(Mandatory = $true)]
  [string]$DemoScript,

  [Parameter(Mandatory = $true)]
  [string]$CapstoneMap,

  [string]$UvExecutable = 'uv'
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path

function Resolve-RepoPath([string]$PathValue) {
  if ([System.IO.Path]::IsPathRooted($PathValue)) {
    return [System.IO.Path]::GetFullPath($PathValue)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PathValue))
}

$resolvedOutputDir = Resolve-RepoPath $OutputDir
if ($resolvedOutputDir -eq $repoRoot) {
  [Console]::Error.WriteLine('OutputDir must not be the repository root.')
  exit 2
}

$resolvedFrozenPacket = Resolve-RepoPath $FrozenPacket
$resolvedPdfBrowserEvidence = Resolve-RepoPath $PdfBrowserEvidence
$resolvedLangSmithEvidence = Resolve-RepoPath $LangSmithEvidence
$resolvedOpenAICompetitorEvidence = Resolve-RepoPath $OpenAICompetitorEvidence
$resolvedFailureMatrix = Resolve-RepoPath $FailureMatrix
$resolvedDemoScript = Resolve-RepoPath $DemoScript
$resolvedCapstoneMap = Resolve-RepoPath $CapstoneMap

$env:OPENAI_API_KEY = ''
$env:OPENAI_STARTUP_API_KEY = ''
$env:LANGSMITH_API_KEY = ''
$env:LANGCHAIN_API_KEY = ''
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
  'due_diligence_agent.evals.queue5_verification',
  '--output-dir', $resolvedOutputDir,
  '--frozen-packet', $resolvedFrozenPacket,
  '--pdf-browser-evidence', $resolvedPdfBrowserEvidence,
  '--langsmith-evidence', $resolvedLangSmithEvidence,
  '--openai-competitor-evidence', $resolvedOpenAICompetitorEvidence,
  '--failure-matrix', $resolvedFailureMatrix,
  '--demo-script', $resolvedDemoScript,
  '--capstone-map', $resolvedCapstoneMap
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
