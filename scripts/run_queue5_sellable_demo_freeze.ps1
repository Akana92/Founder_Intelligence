param(
  [Parameter(Mandatory = $true)]
  [string]$OutputDir,

  [Parameter(Mandatory = $true)]
  [string]$GateBResult,

  [Parameter(Mandatory = $true)]
  [string]$GateCResult,

  [Parameter(Mandatory = $true)]
  [string]$GateDFirstResult,

  [Parameter(Mandatory = $true)]
  [string]$GateDSecondResult,

  [Parameter(Mandatory = $true)]
  [string]$GateEResult,

  [Parameter(Mandatory = $true)]
  [string]$BrowserEvidence,

  [Parameter(Mandatory = $true)]
  [string]$DesktopScreenshot,

  [string]$MobileScreenshot = '',

  [Parameter(Mandatory = $true)]
  [string]$SamplePdf,

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

$resolvedGateBResult = Resolve-RepoPath $GateBResult
$resolvedGateCResult = Resolve-RepoPath $GateCResult
$resolvedGateDFirstResult = Resolve-RepoPath $GateDFirstResult
$resolvedGateDSecondResult = Resolve-RepoPath $GateDSecondResult
$resolvedGateEResult = Resolve-RepoPath $GateEResult
$resolvedBrowserEvidence = Resolve-RepoPath $BrowserEvidence
$resolvedDesktopScreenshot = Resolve-RepoPath $DesktopScreenshot
$resolvedMobileScreenshot = $null
if (-not [string]::IsNullOrWhiteSpace($MobileScreenshot)) {
  $resolvedMobileScreenshot = Resolve-RepoPath $MobileScreenshot
}
$resolvedSamplePdf = Resolve-RepoPath $SamplePdf
$resolvedDemoScript = Resolve-RepoPath $DemoScript
$resolvedCapstoneMap = Resolve-RepoPath $CapstoneMap

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
  'investment-dd',
  'run-sellable-demo-freeze',
  '--output-dir', $resolvedOutputDir,
  '--gate-b-result', $resolvedGateBResult,
  '--gate-c-result', $resolvedGateCResult,
  '--gate-d-first-result', $resolvedGateDFirstResult,
  '--gate-d-second-result', $resolvedGateDSecondResult,
  '--gate-e-result', $resolvedGateEResult,
  '--browser-evidence', $resolvedBrowserEvidence,
  '--desktop-screenshot', $resolvedDesktopScreenshot,
  '--sample-pdf', $resolvedSamplePdf,
  '--demo-script', $resolvedDemoScript,
  '--capstone-map', $resolvedCapstoneMap
)

if ($null -ne $resolvedMobileScreenshot) {
  $uvArgs += @('--mobile-screenshot', $resolvedMobileScreenshot)
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
