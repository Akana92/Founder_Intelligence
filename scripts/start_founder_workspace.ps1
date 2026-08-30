param(
    [string] $DataDir = ".tmp-founder-workspace",
    [string] $LogDir,
    [int] $ApiPort = 8000,
    [int] $WebPort = 3000,
    [int] $AdminPort = 8501,
    [ValidateSet("live", "deterministic_offline")]
    [string] $CaseMode = "live",
    [string] $EnvFile,
    [switch] $EnableLangSmithTracing,
    [switch] $ValidateOnly
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RunId = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
$StartedPids = New-Object System.Collections.Generic.List[int]

function Write-LaunchError([string] $Code, [string] $Detail) {
    [Console]::Error.WriteLine("$Code`: $Detail")
}

function Resolve-WorkspacePath([string] $Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        throw "workspace_path_required"
    }
    if ([System.IO.Path]::IsPathRooted($Candidate)) {
        return [System.IO.Path]::GetFullPath($Candidate)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Candidate))
}

function Resolve-ExplicitPath([string] $Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        throw "explicit_path_required"
    }
    if ([System.IO.Path]::IsPathRooted($Candidate)) {
        return [System.IO.Path]::GetFullPath($Candidate)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Candidate))
}

function Test-EnvValuePresent([string] $Name) {
    return -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name, "Process"))
}

function Format-Bool([bool] $Value) {
    if ($Value) {
        return "true"
    }
    return "false"
}

function Clear-AutomaticTracingEnv {
    foreach ($name in @(
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING",
        "LANGCHAIN_TRACING_V2",
        "LANGCHAIN_API_KEY"
    )) {
        [Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
}

function Import-LaunchEnvFile([string] $Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return $null
    }

    $resolved = Resolve-ExplicitPath $Candidate
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        Write-LaunchError "workspace_env_file_missing" "path=$resolved"
        exit 2
    }

    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $resolved -Encoding UTF8) {
        $lineNumber += 1
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed.StartsWith("export ")) {
            $trimmed = $trimmed.Substring(7).TrimStart()
        }

        $equalsIndex = $trimmed.IndexOf("=")
        if ($equalsIndex -lt 1) {
            Write-LaunchError "workspace_env_file_invalid" "path=$resolved line=$lineNumber"
            exit 2
        }

        $name = $trimmed.Substring(0, $equalsIndex).Trim()
        if ($name -notmatch "^[A-Za-z_][A-Za-z0-9_]*$") {
            Write-LaunchError "workspace_env_file_invalid" "path=$resolved line=$lineNumber"
            exit 2
        }

        $value = $trimmed.Substring($equalsIndex + 1).Trim()
        if (
            $value.Length -ge 2 -and (
                ($value.StartsWith("'") -and $value.EndsWith("'")) -or
                ($value.StartsWith('"') -and $value.EndsWith('"'))
            )
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }

    return $resolved
}

function Assert-PortNumber([string] $Name, [int] $Port) {
    if ($Port -lt 1 -or $Port -gt 65535) {
        Write-LaunchError "workspace_invalid_port" "$Name=$Port"
        exit 2
    }
}

function Assert-DistinctPorts {
    $seen = @{}
    foreach ($entry in @(
        @{ Name = "ApiPort"; Value = $ApiPort },
        @{ Name = "WebPort"; Value = $WebPort },
        @{ Name = "AdminPort"; Value = $AdminPort }
    )) {
        if ($seen.ContainsKey($entry.Value)) {
            Write-LaunchError "workspace_port_conflict" "$($entry.Name)=$($entry.Value)"
            exit 2
        }
        $seen[$entry.Value] = $entry.Name
    }
}

function Assert-PortFree([int] $Port) {
    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    if ($listeners.Port -contains $Port) {
        Write-LaunchError "workspace_port_in_use" "port=$Port"
        exit 3
    }
}

function Escape-PowerShellSingleQuotedString([string] $Value) {
    return $Value.Replace("'", "''")
}

function Stop-ProcessTree([int] $ProcessId) {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int] $child.ProcessId)
    }
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Start-HiddenPowerShellProcess(
    [string] $Name,
    [string] $Command,
    [string] $StdOut,
    [string] $StdErr
) {
    $process = Start-Process `
        -FilePath "powershell" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $Command) `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $StdOut `
        -RedirectStandardError $StdErr `
        -WorkingDirectory $Root
    $StartedPids.Add([int] $process.Id)
    Write-Host "$Name pid=$($process.Id)"
    return $process
}

function Wait-HttpReady([string] $Name, [string] $Url, [int] $Seconds = 90) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    $last = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "$Name ready url=$Url"
                return
            }
        } catch {
            $last = $_.Exception.Message
            Start-Sleep -Milliseconds 500
        }
    }
    throw "workspace_readiness_timeout name=$Name url=$Url last=$last"
}

Assert-PortNumber "ApiPort" $ApiPort
Assert-PortNumber "WebPort" $WebPort
Assert-PortNumber "AdminPort" $AdminPort
Assert-DistinctPorts

$ResolvedEnvFile = Import-LaunchEnvFile $EnvFile
Clear-AutomaticTracingEnv
if ($EnableLangSmithTracing) {
    [Environment]::SetEnvironmentVariable("DDA_LANGSMITH_TRACING", "true", "Process")
}

$ResolvedDataRoot = Resolve-WorkspacePath $DataDir
if ($LogDir) {
    $ResolvedLogRoot = Resolve-WorkspacePath $LogDir
} else {
    $ResolvedLogRoot = Join-Path $Root "artifacts/runtime/founder-workspace/$RunId"
}

$ApiUrl = "http://127.0.0.1:$ApiPort"
$FounderUrl = "http://127.0.0.1:$WebPort"
$AdminUrl = "http://127.0.0.1:$AdminPort"

$SafeRoot = Escape-PowerShellSingleQuotedString $Root
$SafeDataRoot = Escape-PowerShellSingleQuotedString $ResolvedDataRoot
$SafeApiUrl = Escape-PowerShellSingleQuotedString $ApiUrl
$SafeAdminUrl = Escape-PowerShellSingleQuotedString $AdminUrl
$SafeFrontendRoot = Escape-PowerShellSingleQuotedString (Join-Path $Root "frontend/founder")
$NextCommand = Escape-PowerShellSingleQuotedString (Join-Path $Root "frontend/founder/node_modules/.bin/next.cmd")
$StreamlitApp = Escape-PowerShellSingleQuotedString (Join-Path $Root "src/due_diligence_agent/presentation/streamlit/app.py")
$NodeModules = Get-Item -LiteralPath (Join-Path $Root "frontend/founder/node_modules")
$NextDevBundlerFlag = if ($NodeModules.LinkType) { "--webpack" } else { "--turbo" }
$NextDistDir = ".next-owner-$RunId"

$ApiCommand = "& '$SafeRoot/scripts/run_founder_api.ps1' -Port $ApiPort -DataDir '$SafeDataRoot' -CaseMode $CaseMode"

if ($ValidateOnly) {
    Write-Host "startup_founder_workspace_launch_contract_valid"
    Write-Host "data_root=$ResolvedDataRoot"
    Write-Host "log_root=$ResolvedLogRoot"
    Write-Host "api_url=$ApiUrl"
    Write-Host "founder_url=$FounderUrl"
    Write-Host "admin_url=$AdminUrl"
    Write-Host "case_mode=$CaseMode"
    Write-Host "api_case_mode=$CaseMode"
    if ($ResolvedEnvFile) {
        Write-Host "env_file=$ResolvedEnvFile"
    }
    Write-Host "env_file_loaded=$(Format-Bool ($null -ne $ResolvedEnvFile))"
    Write-Host "openai_credential_present=$(Format-Bool (Test-EnvValuePresent 'OPENAI_API_KEY'))"
    Write-Host "langsmith_credential_present=$(Format-Bool (Test-EnvValuePresent 'LANGSMITH_API_KEY'))"
    Write-Host "langsmith_tracing_enabled=$(Format-Bool ([Environment]::GetEnvironmentVariable('DDA_LANGSMITH_TRACING', 'Process') -eq 'true'))"
    Write-Host "raw_langsmith_tracing_present=$(Format-Bool (Test-EnvValuePresent 'LANGSMITH_TRACING'))"
    Write-Host "raw_langchain_tracing_present=$(Format-Bool (Test-EnvValuePresent 'LANGCHAIN_TRACING'))"
    Write-Host "raw_langchain_tracing_v2_present=$(Format-Bool (Test-EnvValuePresent 'LANGCHAIN_TRACING_V2'))"
    Write-Host "raw_langchain_api_key_present=$(Format-Bool (Test-EnvValuePresent 'LANGCHAIN_API_KEY'))"
    Write-Host "node_modules_linked=$(Format-Bool ($null -ne $NodeModules.LinkType))"
    Write-Host "next_dev_bundler=$NextDevBundlerFlag"
    Write-Host "next_dist_dir=$NextDistDir"
    Write-Host "api_command=$ApiCommand"
    exit 0
}

foreach ($port in @($ApiPort, $WebPort, $AdminPort)) {
    Assert-PortFree $port
}

New-Item -ItemType Directory -Path $ResolvedDataRoot -Force | Out-Null
New-Item -ItemType Directory -Path $ResolvedLogRoot -Force | Out-Null

$AdminCommand = "`$env:DDA_DATA_DIR='$SafeDataRoot'; uv run --offline --no-sync --no-default-groups --group stage1a --group stage1a-ui-report --group stage1b-light-ingest --group founder-api --group dev streamlit run '$StreamlitApp' --server.address 127.0.0.1 --server.port $AdminPort --server.headless true --browser.gatherUsageStats false"
$WebCommand = "`$env:DDA_DATA_DIR='$SafeDataRoot'; `$env:FOUNDER_API_BASE_URL='$SafeApiUrl'; `$env:NEXT_PUBLIC_ADMIN_CONSOLE_URL='$SafeAdminUrl'; `$env:FOUNDER_CASE_FIXTURE_MODE='$CaseMode'; `$env:FOUNDER_NEXT_DIST_DIR='$NextDistDir'; `$env:NEXT_TELEMETRY_DISABLED='1'; Push-Location '$SafeFrontendRoot'; & '$NextCommand' dev -H 127.0.0.1 -p $WebPort $NextDevBundlerFlag"

try {
    Start-HiddenPowerShellProcess "founder-api" $ApiCommand (Join-Path $ResolvedLogRoot "founder-api.stdout.log") (Join-Path $ResolvedLogRoot "founder-api.stderr.log") | Out-Null
    Start-HiddenPowerShellProcess "founder-admin" $AdminCommand (Join-Path $ResolvedLogRoot "founder-admin.stdout.log") (Join-Path $ResolvedLogRoot "founder-admin.stderr.log") | Out-Null
    Start-HiddenPowerShellProcess "founder-web" $WebCommand (Join-Path $ResolvedLogRoot "founder-web.stdout.log") (Join-Path $ResolvedLogRoot "founder-web.stderr.log") | Out-Null

    Wait-HttpReady "founder-api" "$ApiUrl/health/live"
    Wait-HttpReady "founder-admin" $AdminUrl
    Wait-HttpReady "founder-web" $FounderUrl

    Write-Host "startup_founder_workspace_started"
    Write-Host "data_root=$ResolvedDataRoot"
    Write-Host "log_root=$ResolvedLogRoot"
    Write-Host "api_url=$ApiUrl"
    Write-Host "founder_url=$FounderUrl"
    Write-Host "admin_url=$AdminUrl"
    Write-Host "case_mode=$CaseMode"
    Write-Host "stop_instruction=Close this PowerShell process with Ctrl+C to stop child processes."

    while ($true) {
        Start-Sleep -Seconds 5
        foreach ($pidValue in $StartedPids) {
            if (-not (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
                throw "workspace_child_process_exited pid=$pidValue"
            }
        }
    }
} finally {
    foreach ($pidValue in $StartedPids) {
        Stop-ProcessTree -ProcessId $pidValue
    }
}
