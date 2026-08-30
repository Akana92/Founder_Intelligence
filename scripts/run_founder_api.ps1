param(
    [int] $Port = 8000,
    [string] $HostAddress = "127.0.0.1",
    [string] $DataDir,
    [ValidateSet("live", "deterministic_offline")]
    [string] $CaseMode = "live",
    [switch] $AllInterfaces,
    [switch] $ValidateOnly
)

$ErrorActionPreference = "Stop"

if ($DataDir) {
    $env:DDA_DATA_DIR = [System.IO.Path]::GetFullPath($DataDir)
}
$env:FOUNDER_CASE_FIXTURE_MODE = $CaseMode

$argsList = @(
    "--offline",
    "--no-sync",
    "--no-default-groups",
    "--group",
    "stage1a",
    "--group",
    "stage1b-light-ingest",
    "--group",
    "founder-api",
    "--group",
    "dev",
    "investment-dd-api",
    "--port",
    $Port.ToString()
)

if ($AllInterfaces) {
    $argsList += "--all-interfaces"
} else {
    $argsList += @("--host", $HostAddress)
}

if ($ValidateOnly) {
    $hostContract = if ($AllInterfaces) { "0.0.0.0" } else { $HostAddress }
    Write-Host "startup_founder_api_launch_contract_valid"
    Write-Host "data_root=$env:DDA_DATA_DIR"
    Write-Host "host=$hostContract"
    Write-Host "port=$Port"
    Write-Host "case_mode=$CaseMode"
    Write-Host "fixture_mode_env=$env:FOUNDER_CASE_FIXTURE_MODE"
    exit 0
}

uv run @argsList
