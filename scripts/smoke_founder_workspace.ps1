param(
    [ValidateSet('offline-fixture','live-api')]
    [string] $Mode = "offline-fixture",
    [switch] $CaptureScreenshots,
    [switch] $ValidateOnly,
    [string] $BrowserCommand,
    [string] $BlockedBrowserInjectionOrigin,
    [string] $OfflineFixturePath,
    [string] $AdvisorAnswer = "Текущая выручка не подтверждена; пилот бесплатный. Модель цены требует проверки.",
    [string] $InvalidAdvisorAnswer = "60%",
    [string] $AdminTraceEvidencePath,
    [string] $FrontendRoot = "",
    [switch] $RequirePdfUploadJourney,
    [switch] $RequireCaseCopilotScenarioJourney,
    [switch] $RequireSmartUniversitySinglePdfJourney,
    [switch] $RequireSmartUniversityLivePublicResearch,
    [int] $ApiPort = 8000,
    [int] $WebPort = 3000,
    [int] $AdminPort = 8501,
    [string] $DataDir = ".tmp-founder-workspace-smoke",
    [string] $ScreenshotDir = "",
    [string] $BrowserEvidencePath = "",
    [string] $EnvFile,
    [switch] $EnableLangSmithTracing
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ArtifactDir = Join-Path $Root "artifacts/ui"
$ApiBaseUrl = "http://127.0.0.1:$ApiPort"
$WebBaseUrl = "http://127.0.0.1:$WebPort"
$AdminBaseUrl = "http://127.0.0.1:$AdminPort"
$DefaultBrowserReviewUrls = @(
    "http://127.0.0.1:3000/",
    "http://127.0.0.1:8501/",
    "http://127.0.0.1:3000/comparables",
    "http://127.0.0.1:8000/docs"
)
$BrowserReviewUrls = @(
    "$WebBaseUrl/",
    "$AdminBaseUrl/",
    "$WebBaseUrl/comparables",
    "$ApiBaseUrl/docs"
)
$FounderFixtureRoot = Join-Path $Root "tests/fixtures/startup_workspace_smoke_v1"
$FounderMetricsFixture = Join-Path $FounderFixtureRoot "documents/founder_metrics.csv"
$SmokeRunId = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds().ToString()
$StartedPids = New-Object System.Collections.Generic.List[int]

function Write-SmokeError([string] $Code, [string] $Detail) {
    [Console]::Error.WriteLine("$Code`: $Detail")
}

function Format-Bool([bool] $Value) {
    if ($Value) {
        return "true"
    }
    return "false"
}

function Test-EnvValuePresent([string] $Name) {
    return -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name, "Process"))
}

function Resolve-ExplicitSmokePath([string] $Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        throw "explicit_smoke_path_required"
    }
    if ([System.IO.Path]::IsPathRooted($Candidate)) {
        return [System.IO.Path]::GetFullPath($Candidate)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Candidate))
}

function Import-SmokeEnvFile([string] $Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return $null
    }

    $resolved = Resolve-ExplicitSmokePath $Candidate
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        Write-SmokeError "smoke_env_file_missing" "path=$resolved"
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
            Write-SmokeError "smoke_env_file_invalid" "path=$resolved line=$lineNumber"
            exit 2
        }

        $name = $trimmed.Substring(0, $equalsIndex).Trim()
        if ($name -notmatch "^[A-Za-z_][A-Za-z0-9_]*$") {
            Write-SmokeError "smoke_env_file_invalid" "path=$resolved line=$lineNumber"
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

function Clear-SmokeProviderEnv {
    foreach ($name in @(
        "OPENAI_API_KEY",
        "OPENAI_STARTUP_API_KEY",
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY"
    )) {
        [Environment]::SetEnvironmentVariable($name, "", "Process")
    }
    foreach ($name in @(
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING",
        "LANGCHAIN_TRACING_V2"
    )) {
        [Environment]::SetEnvironmentVariable($name, "false", "Process")
    }
    [Environment]::SetEnvironmentVariable("DDA_LANGSMITH_TRACING", "false", "Process")
}

function Clear-SmokeRawTracingEnv {
    foreach ($name in @(
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING",
        "LANGCHAIN_TRACING_V2",
        "LANGCHAIN_API_KEY"
    )) {
        [Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
}

function Assert-SmokeLaunchContract {
    if ($RequireSmartUniversityLivePublicResearch) {
        if ($Mode -ne "live-api") {
            Write-SmokeError "smart_university_live_research_requires_live_api" "Use -Mode live-api for Online research."
            exit 2
        }
        if ([string]::IsNullOrWhiteSpace($EnvFile)) {
            Write-SmokeError "smart_university_live_research_requires_env_file" "Online research must load credentials from the explicit env file."
            exit 2
        }
        if (-not $RequireSmartUniversitySinglePdfJourney) {
            Write-SmokeError "smart_university_live_research_requires_smart_university_journey" "Online research acceptance must run the Smart University PDF journey."
            exit 2
        }
        if (-not (Test-EnvValuePresent "OPENAI_API_KEY") -and -not (Test-EnvValuePresent "OPENAI_STARTUP_API_KEY")) {
            Write-SmokeError "smart_university_live_research_requires_openai_credential" "Configure OpenAI through the explicit env file."
            exit 3
        }
    }
    if ($Mode -eq "offline-fixture" -and -not [string]::IsNullOrWhiteSpace($EnvFile)) {
        Write-SmokeError "offline_fixture_rejects_env_file" "Offline fixture smoke clears provider credentials and does not read env files."
        exit 2
    }
}

function Resolve-ScreenshotDriver {
    if ($BrowserCommand) {
        if (Test-Path -LiteralPath $BrowserCommand) {
            return (Resolve-Path -LiteralPath $BrowserCommand).Path
        }
        Write-SmokeError "screenshot_capture_unavailable" "BrowserCommand was requested but does not exist: $BrowserCommand"
        exit 2
    }
    $edgeCommand = Get-Command "msedge.exe" -ErrorAction SilentlyContinue
    if ($edgeCommand) {
        return $edgeCommand.Source
    }
    $edgePath = Join-Path ${env:ProgramFiles(x86)} "Microsoft/Edge/Application/msedge.exe"
    if (Test-Path -LiteralPath $edgePath) {
        return (Resolve-Path -LiteralPath $edgePath).Path
    }
    Write-SmokeError "screenshot_capture_unavailable" "Provide an installed Microsoft Edge path with -BrowserCommand."
    exit 2
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

function Start-HiddenPowerShellProcess([string] $Name, [string] $Command, [string] $StdOut, [string] $StdErr) {
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

function Restart-FounderSmokeServicesForCaseCopilotEvidence(
    [string] $ApiCommand,
    [string] $AdminCommand,
    [string] $WebCommand
) {
    Write-Host "case_copilot_browser_evidence_reload_phase=restart_services"
    foreach ($pidValue in @($StartedPids)) {
        Stop-ProcessTree -ProcessId $pidValue
    }
    $StartedPids.Clear()
    Start-HiddenPowerShellProcess "founder-api-reload" $ApiCommand (Join-Path $ArtifactDir "founder-api.reload.stdout.log") (Join-Path $ArtifactDir "founder-api.reload.stderr.log") | Out-Null
    Start-HiddenPowerShellProcess "founder-admin-reload" $AdminCommand (Join-Path $ArtifactDir "founder-admin.reload.stdout.log") (Join-Path $ArtifactDir "founder-admin.reload.stderr.log") | Out-Null
    Start-HiddenPowerShellProcess "founder-web-reload" $WebCommand (Join-Path $ArtifactDir "founder-web.reload.stdout.log") (Join-Path $ArtifactDir "founder-web.reload.stderr.log") | Out-Null
    $apiReloadHealthUrl = "$ApiBaseUrl/health/live"
    $adminReloadUrl = "$AdminBaseUrl/"
    $webReloadUrl = "$WebBaseUrl/"
    Wait-HttpOk $apiReloadHealthUrl
    Wait-HttpOk $adminReloadUrl
    Wait-HttpOk $webReloadUrl
    Write-Host "case_copilot_browser_evidence_reload_phase=ready"
}

function Wait-FounderCaseCopilotRestartRequest(
    [string] $RequestPath,
    [object] $CaptureJob = $null,
    [int] $TimeoutSeconds = 900
) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $RequestPath -PathType Leaf) {
            return Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
        }
        if ($CaptureJob -and $CaptureJob.State -ne "Running") {
            $jobOutput = Receive-Job -Job $CaptureJob -Keep -ErrorAction SilentlyContinue 6>&1 | Out-String
            $jobErrors = $CaptureJob.ChildJobs[0].Error | Out-String
            throw "case_copilot_capture_exited_before_restart_request state=$($CaptureJob.State) output=$jobOutput errors=$jobErrors"
        }
        Start-Sleep -Milliseconds 250
    }
    throw "case_copilot_restart_request_timeout path=$RequestPath"
}

function Invoke-FounderScreenshotCaptureWithCaseCopilotRestart(
    [string[]] $CaptureArgs,
    [string] $RestartRequestPath,
    [string] $RestartReadyPath,
    [string] $ApiCommand,
    [string] $AdminCommand,
    [string] $WebCommand
) {
    $stdoutPath = Join-Path $ResolvedScreenshotRoot "case-copilot-capture.stdout.log"
    $stderrPath = Join-Path $ResolvedScreenshotRoot "case-copilot-capture.stderr.log"
    $captureJob = Start-Job -ScriptBlock {
        param([string[]] $NodeArgs)
        & node @NodeArgs
        [pscustomobject]@{
            capture_exit_code = [int] $LASTEXITCODE
        }
    } -ArgumentList (,$CaptureArgs)

    try {
        $restartRequest = Wait-FounderCaseCopilotRestartRequest $RestartRequestPath $captureJob
        Restart-FounderSmokeServicesForCaseCopilotEvidence $ApiCommand $AdminCommand $WebCommand
        $readyPayload = @{
            status = "ready"
            token = [string] $restartRequest.token
            ready_at = (Get-Date).ToUniversalTime().ToString("o")
            restarted_cases = $restartRequest.cases
        } | ConvertTo-Json -Depth 8
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($RestartReadyPath, "$readyPayload`n", $utf8NoBom)
        Wait-Job -Job $captureJob | Out-Null
        $jobOutput = @(Receive-Job -Job $captureJob -ErrorAction SilentlyContinue 6>&1)
        $jobErrors = $captureJob.ChildJobs[0].Error | Out-String
        $captureExitRecord = @(
            $jobOutput |
                Where-Object { $_.PSObject.Properties.Name -contains "capture_exit_code" } |
                Select-Object -Last 1
        )
        $captureExitCode = if ($captureExitRecord.Count -eq 1) {
            [int] $captureExitRecord[0].capture_exit_code
        } else {
            -1
        }
        $stdout = (
            $jobOutput |
                Where-Object { $_.PSObject.Properties.Name -notcontains "capture_exit_code" } |
                Out-String
        )
        Set-Content -LiteralPath $stdoutPath -Value $stdout -Encoding UTF8
        Set-Content -LiteralPath $stderrPath -Value $jobErrors -Encoding UTF8
        if (-not [string]::IsNullOrWhiteSpace($stdout)) { Write-Host $stdout.TrimEnd() }
        if ($captureJob.State -ne "Completed") {
            throw "screenshot_capture_failed cdp state=$($captureJob.State)"
        }
        if ($captureExitCode -ne 0) {
            throw "screenshot_capture_failed cdp exit_code=$captureExitCode"
        }
    } finally {
        if ($captureJob.State -ne "Running") {
            $remainingOutput = Receive-Job -Job $captureJob -Keep -ErrorAction SilentlyContinue 6>&1 | Out-String
            $remainingErrors = $captureJob.ChildJobs[0].Error | Out-String
            if (-not [string]::IsNullOrWhiteSpace($remainingOutput)) {
                Add-Content -LiteralPath $stdoutPath -Value $remainingOutput -Encoding UTF8
            }
            if (-not [string]::IsNullOrWhiteSpace($remainingErrors)) {
                Add-Content -LiteralPath $stderrPath -Value $remainingErrors -Encoding UTF8
            }
        }
        if ($captureJob.State -eq "Running") {
            Stop-Job -Job $captureJob
            $stoppedOutput = Receive-Job -Job $captureJob -ErrorAction SilentlyContinue 6>&1 | Out-String
            $stoppedErrors = $captureJob.ChildJobs[0].Error | Out-String
            if (-not [string]::IsNullOrWhiteSpace($stoppedOutput)) {
                Add-Content -LiteralPath $stdoutPath -Value $stoppedOutput -Encoding UTF8
            }
            if (-not [string]::IsNullOrWhiteSpace($stoppedErrors)) {
                Add-Content -LiteralPath $stderrPath -Value $stoppedErrors -Encoding UTF8
            }
        }
        Remove-Job -Job $captureJob -Force
    }
}

function Wait-HttpOk([string] $Url, [int] $Seconds = 60) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    $last = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        } catch {
            $last = $_.Exception.Message
            Start-Sleep -Milliseconds 500
        }
    }
    throw "health_timeout url=$Url last=$last"
}

function Assert-NoExternalNetwork {
    if ($Mode -ne "offline-fixture") {
        return
    }
    foreach ($pidValue in $StartedPids) {
        $tree = @($pidValue)
        $cursor = @($pidValue)
        while ($cursor.Count -gt 0) {
            $next = @()
            foreach ($parentPid in $cursor) {
                $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $parentPid" -ErrorAction SilentlyContinue
                foreach ($child in $children) {
                    $tree += [int] $child.ProcessId
                    $next += [int] $child.ProcessId
                }
            }
            $cursor = $next
        }
        foreach ($treePid in $tree) {
            $connections = Get-NetTCPConnection -OwningProcess $treePid -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.State -in @("Established", "SynSent") -and
                    $_.RemoteAddress -notin @("127.0.0.1", "::1", "0.0.0.0", "::")
                }
            if ($connections) {
                throw "offline_network_violation pid=$treePid"
            }
        }
    }
    Write-Host "offline_network_snapshot_clean"
}

function Invoke-FounderFixtureFlow([string] $FixturePath) {
    $create = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases" `
        -ContentType "application/json" `
        -Body (@{ fixture_mode = "deterministic_offline"; auto_start = $false; company_name = "FounderCo" } | ConvertTo-Json)
    $caseId = $create.case_id
    Invoke-MultipartUpload -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/documents" -Files @($FixturePath) | Out-Null
    $preview = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/gate2/preview"
    Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/gate2/decision" `
        -ContentType "application/json" `
        -Body (@{ decision = "approved"; resume_token = $preview.resume_token } | ConvertTo-Json) | Out-Null
    Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/gate3/decision" `
        -ContentType "application/json" `
        -Body (@{ decision = "continue"; exclusions = @() } | ConvertTo-Json) | Out-Null
    $profile = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/profile"
    $profileFields = @($profile.fields.PSObject.Properties)
    $invalidProfileFields = @(
        $profileFields | Where-Object {
            $_.Value.status -notin @("source_fact", "inference", "insufficient_data", "contradiction")
        }
    )
    $profileUuidPattern = '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    $profileLineageValid = (
        ($profile.analysis_stage -eq "primary" -and $null -eq $profile.parent_profile_id) -or
        ($profile.analysis_stage -eq "enriched" -and $profile.parent_profile_id -match $profileUuidPattern)
    )
    if (
        -not $profileLineageValid -or
        $profile.data_revision -lt 1 -or
        $profile.profile_id -notmatch $profileUuidPattern -or
        $profile.profile_hash -notmatch '^sha256:[0-9a-f]{64}$' -or
        $profileFields.Count -ne 18 -or
        $invalidProfileFields.Count -ne 0 -or
        @($profile.parse_inventory.source_hashes.PSObject.Properties).Count -lt 1
    ) {
        throw "smoke_profile_contract_mismatch"
    }
    $gtm = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/gtm"
    if (
        $gtm.schema_version -ne "startup_gtm@1" -or
        @($gtm.dimensions).Count -ne 7 -or
        @($gtm.launch_plan).Count -ne 4 -or
        $gtm.snapshot_hash -notmatch '^sha256:[0-9a-f]{64}$'
    ) {
        throw "smoke_gtm_contract_mismatch"
    }
    $report = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/report"
    $reportArtifact = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/report/json"
    $expectedReportSections = @(
        "business_idea_summary",
        "problem_solution",
        "market_size",
        "competitors",
        "moat",
        "go_to_market",
        "metrics",
        "financial_assumptions",
        "risks",
        "evidence_gaps",
        "diligence_questions",
        "action_plan"
    )
    $expectedFounderReportKeys = @(
        "title_ru",
        "subtitle_ru",
        "as_of_ru",
        "data_revision",
        "main_sections",
        "metric_cards",
        "improvement_proposals",
        "technical_appendix",
        "analytics"
    )
    $reportTopLevelKeys = @($reportArtifact.PSObject.Properties | ForEach-Object { $_.Name })
    $reportSections = @($reportArtifact.main_sections)
    $reportSectionKeys = @($reportSections | ForEach-Object { $_.key })
    if (
        $reportTopLevelKeys.Count -ne $expectedFounderReportKeys.Count -or
        (Compare-Object -ReferenceObject ($expectedFounderReportKeys | Sort-Object) -DifferenceObject ($reportTopLevelKeys | Sort-Object)) -or
        $reportArtifact.data_revision -lt 1 -or
        $reportArtifact.title_ru -isnot [string] -or
        $reportArtifact.subtitle_ru -isnot [string] -or
        $reportArtifact.as_of_ru -isnot [string] -or
        $reportSectionKeys.Count -ne $expectedReportSections.Count -or
        (Compare-Object -ReferenceObject $expectedReportSections -DifferenceObject $reportSectionKeys -SyncWindow 0) -or
        $null -eq $reportArtifact.metric_cards -or
        $null -eq $reportArtifact.improvement_proposals -or
        $null -eq $reportArtifact.technical_appendix -or
        $null -eq $reportArtifact.analytics -or
        $null -eq $reportArtifact.analytics.metric_points -or
        $null -eq $reportArtifact.analytics.market_points -or
        $null -eq $reportArtifact.analytics.readiness_dimensions
    ) {
        throw "smoke_report_contract_mismatch"
    }
    $escapedCaseId = [regex]::Escape($caseId)
    if (
        $report.case_id -ne $caseId -or
        $report.report_status -ne "ready" -or
        $report.snapshot_id -notmatch $profileUuidPattern -or
        $report.snapshot_hash -notmatch '^sha256:[0-9a-f]{64}$' -or
        $report.snapshot_revision -lt 1 -or
        $report.snapshot_revision -ne $reportArtifact.data_revision -or
        $report.json_url -notmatch "^/api/(?:v1/)?startup/cases/$escapedCaseId/report/json$" -or
        $report.html_url -notmatch "^/api/(?:v1/)?startup/cases/$escapedCaseId/report/html$" -or
        $report.pdf_url -notmatch "^/api/(?:v1/)?startup/cases/$escapedCaseId/report/pdf$"
    ) {
        throw "smoke_report_tuple_mismatch"
    }
    $invalidReportSections = @(
        $reportSections | Where-Object {
            $_.title_ru -isnot [string] -or
            $_.summary_ru -isnot [string] -or
            $_.status -notin @("confirmed", "partial", "needs_input", "contradiction") -or
            $null -eq $_.known_facts_ru -or
            $null -eq $_.blockers_ru -or
            $null -eq $_.next_data_ru -or
            $null -eq $_.unlocks_ru
        }
    )
    if ($invalidReportSections.Count -ne 0) {
        throw "smoke_report_section_contract_mismatch"
    }
    $metricsSection = @($reportSections | Where-Object { $_.key -eq "metrics" })
    if ($metricsSection.Count -ne 1 -or $metricsSection[0].status -eq "needs_input") {
        throw "smoke_report_metrics_missing"
    }
    $reportArtifactJson = ConvertTo-Json $reportArtifact -Depth 30 -Compress
    $forbiddenReportJsonPatterns = @(
        '"(?:case_id|id|report_hash|snapshot_hash|case_snapshot_hash|profile_hash|profile_id|source_hashes|trace_ids?|prompt_versions?|formula|model|repro|source_appendix|evidence_refs?|calculation_ref|dimension_ref|artifact_hash|locator_hash|document_text_block)"\s*:',
        '\bMISSING\b',
        'sha256:[0-9a-f]{64}',
        '\b[0-9a-f]{64}\b',
        '\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b',
        '[A-Za-z]:[\\/]',
        'file://',
        '\b(?:chain[-_ ]?of[-_ ]?thought|reasoning_trace|system prompt|api token|secret|private key)\b',
        '\bsk-[A-Za-z0-9_-]{8,}'
    )
    foreach ($pattern in $forbiddenReportJsonPatterns) {
        if ($reportArtifactJson -match $pattern) {
            throw "smoke_report_json_privacy_violation"
        }
    }
    $reportHtml = (Invoke-WebRequest -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/report/html" -UseBasicParsing).Content
    $expectedChartKeys = if ($RequirePdfUploadJourney) {
        @("readiness_coverage", "report_coverage")
    } else {
        @("confirmed_metrics", "readiness_coverage", "report_coverage")
    }
    foreach ($chartKey in $expectedChartKeys) {
        if ($reportHtml -notlike "*data-startup-chart=`"$chartKey`"*") {
            throw "smoke_report_html_charts_missing:$chartKey"
        }
    }
    $chartMarkerCount = ([regex]::Matches($reportHtml, 'data-startup-chart="')).Count
    $embeddedChartCount = ([regex]::Matches($reportHtml, '<img[^>]+src="data:image/png;base64,', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)).Count
    if ($chartMarkerCount -lt $expectedChartKeys.Count -or $embeddedChartCount -ne $chartMarkerCount) {
        throw "smoke_report_html_embedded_chart_count:markers=$chartMarkerCount embedded=$embeddedChartCount"
    }
    if ([regex]::IsMatch($reportHtml, '<img[^>]+src="https?://', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
        throw "smoke_report_html_external_image"
    }
    if ($reportArtifactJson -like "*chart_data_uri*") {
        throw "smoke_report_json_contains_render_only_charts"
    }
    Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/gate4/decision" `
        -ContentType "application/json" `
        -Body (@{
            decision = "approved"
            snapshot_hash = $report.snapshot_hash
            snapshot_revision = $report.snapshot_revision
        } | ConvertTo-Json) | Out-Null
    Invoke-WebRequest -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/report/pdf" -UseBasicParsing -OutFile (Join-Path $ArtifactDir "founder-report.pdf") | Out-Null
}

function Invoke-CaseCopilotScenarioFixtureFlow([string] $FixturePath) {
    $companyName = if ($FixturePath -like "*idea_clinic*") { "ClinicOps AI" } else { "InventoryPilot AI" }
    $create = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases" `
        -ContentType "application/json" `
        -Body (@{ fixture_mode = "deterministic_offline"; auto_start = $false; company_name = $companyName } | ConvertTo-Json)
    $caseId = $create.case_id
    $uploaded = Invoke-MultipartUploadWithoutAutoStart -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/documents" -Files @($FixturePath)
    if ($uploaded.analysis_status -ne "awaiting_start" -or $uploaded.auto_start_triggered -ne $false) {
        throw "case_copilot_upload_contract_mismatch"
    }
    $initialState = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/copilot/state"
    $publicGap = @($initialState.prioritized_gaps | Where-Object { $_.allowed_action -eq "prepare_public_research" } | Select-Object -First 1)
    if (-not $initialState.next_question -or -not $publicGap -or @($initialState.scenario_metrics).Count -lt 1) {
        throw "case_copilot_initial_state_incomplete"
    }
    $assumption = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/assumptions" `
        -ContentType "application/json" `
        -Body (@{
            requirement_key = "pricing_revenue_model"
            value = @{ kind = "text"; value = "Founder expects a paid pilot after interview validation." }
            period = @{ kind = "date"; value = "2027-04-01" }
            source = @{ kind = "founder_statement"; declared_source = "Task 11 smoke founder answer" }
            rationale = "Direct founder planning answer to the Copilot question."
            validation_plan = "Validate with signed pilot quotes and billing records."
            expected_case_revision = $initialState.data_revision
            idempotency_key = "task11-smoke-founder-pricing-statement"
        } | ConvertTo-Json -Depth 20)
    if ($assumption.provenance -ne "founder_statement" -or -not $assumption.accepted_input.validation_plan) {
        throw "case_copilot_founder_statement_contract_mismatch"
    }
    $stateAfterAssumption = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/copilot/state"
    $unknownTurn = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/copilot/messages" `
        -ContentType "application/json" `
        -Body (@{
            message = "unknown"
            page_context = "case-copilot"
            current_section = "scenario-question"
            focus_key = $publicGap.field_key
            expected_case_revision = $stateAfterAssumption.data_revision
            idempotency_key = "task11-smoke-unknown-market-answer"
        } | ConvertTo-Json -Depth 20)
    if ($unknownTurn.status -ne "accepted" -or @($unknownTurn.available_actions).Count -lt 1) {
        throw "case_copilot_unknown_answer_contract_mismatch"
    }
    $stateAfterUnknown = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/copilot/state"
    $plan = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/research/plans" `
        -ContentType "application/json" `
        -Body (@{
            focus = $publicGap.field_key
            intent = "Prepare cited public research for $($publicGap.field_key); exclude private metrics."
            expected_case_revision = $stateAfterUnknown.data_revision
        } | ConvertTo-Json -Depth 20)
    if ($plan.status -ne "prepared" -or -not $plan.plan_hash -or @($plan.query_previews).Count -lt 1 -or $plan.consent_text -notlike "*Consent*") {
        throw "case_copilot_research_plan_contract_mismatch"
    }
    $job = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/research/jobs" `
        -ContentType "application/json" `
        -Body (@{
            plan_id = $plan.plan_id
            plan_hash = $plan.plan_hash
            expected_case_revision = $plan.data_revision
            idempotency_key = "task11-smoke-public-research"
            consent_public_research = $true
        } | ConvertTo-Json -Depth 20)
    if ($job.status -ne "completed" -or @($job.accepted_entries).Count -lt 1 -or $job.accepted_entries[0].provenance -ne "public_benchmark" -or @($job.citations).Count -lt 1) {
        $jobSummary = $job | Select-Object status,reason,fail_reason,accepted_entries,changed_blocks,citations | ConvertTo-Json -Depth 10 -Compress
        throw "case_copilot_research_job_contract_mismatch:$jobSummary"
    }
    $scenarios = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/scenarios"
    $scenarioKeys = @($scenarios.scenarios.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
    if ((Compare-Object -ReferenceObject @("base", "conservative", "optimistic") -DifferenceObject $scenarioKeys) -or $scenarios.selected_scenario_key -ne "base") {
        throw "case_copilot_scenarios_contract_mismatch"
    }
    $baseScenario = $scenarios.scenarios.base
    $metricWithRange = @($baseScenario.metrics.PSObject.Properties | Where-Object { $null -ne $_.Value.value_range -and $_.Value.provenance -in @("ai_scenario", "public_benchmark", "deterministic_calculation", "founder_statement") } | Select-Object -First 1)
    if (-not $metricWithRange -or -not $metricWithRange.Value.formula_key -or -not $metricWithRange.Value.validation_plan -or $null -eq $metricWithRange.Value.dependency_refs -or $null -eq $metricWithRange.Value.source_refs) {
        throw "case_copilot_metric_provenance_contract_mismatch"
    }
    $selection = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/scenarios/selection" `
        -ContentType "application/json" `
        -Body (@{
            scenario_set_id = $scenarios.scenario_set_id
            scenario_key = "base"
            expected_case_revision = $scenarios.data_revision
            idempotency_key = "task11-smoke-select-base"
        } | ConvertTo-Json -Depth 20)
    if ($selection.new_scenario_key -ne "base") {
        throw "case_copilot_selection_contract_mismatch"
    }
    $selectedState = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/copilot/state"
    $asset = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/assets" `
        -ContentType "application/json" `
        -Body (@{
            asset_type = "gtm_launch_pack"
            selected_scenario_key = "base"
            expected_case_revision = $selectedState.data_revision
            idempotency_key = "task11-smoke-gtm-launch-pack"
        } | ConvertTo-Json -Depth 20)
    if ($asset.status -ne "draft" -or $asset.asset_key -ne "gtm_launch_pack" -or $asset.body_markdown -notlike "*provenance=ai_scenario*") {
        throw "case_copilot_asset_contract_mismatch"
    }
    $markdown = Invoke-WebRequest -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/assets/$($asset.asset_id)/markdown" -UseBasicParsing
    $provenance = Invoke-WebRequest -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/assets/$($asset.asset_id)/provenance" -UseBasicParsing
    if ($markdown.Headers["Content-Disposition"] -notlike "*attachment;*" -or $provenance.Content -notlike "*validation=*" -or $provenance.Content -notlike "*source_refs=*") {
        throw "case_copilot_asset_download_contract_mismatch"
    }
    $thread = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/copilot/thread"
    $reloadedScenarios = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/scenarios"
    $reloadedAsset = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/startup/cases/$caseId/assets/$($asset.asset_id)"
    $evidence = @{
        status = "verified"
        verification_mode = "deterministic_offline"
        case_id = $caseId
        fixture = [System.IO.Path]::GetFileName($FixturePath)
        upload_analysis_status = $uploaded.analysis_status
        next_question = $initialState.next_question
        founder_statement_provenance = $assumption.provenance
        research_focus = $publicGap.field_key
        research_job_status = $job.status
        citations = @($job.citations)
        scenario_keys = $scenarioKeys
        selected_scenario_key = $selection.new_scenario_key
        metric_key = $metricWithRange.Name
        metric_provenance = $metricWithRange.Value.provenance
        metric_range = $metricWithRange.Value.value_range
        metric_formula = $metricWithRange.Value.formula_key
        metric_dependencies = $metricWithRange.Value.dependency_refs
        metric_source_refs = $metricWithRange.Value.source_refs
        metric_validation_plan = $metricWithRange.Value.validation_plan
        asset_id = $asset.asset_id
        reload_thread_case_id = $thread.case_id
        reload_scenario_set_id = $reloadedScenarios.scenario_set_id
        reload_asset_id = $reloadedAsset.asset_id
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $ResolvedAdminTraceEvidencePath) -Force | Out-Null
    $evidence | ConvertTo-Json -Depth 30 | Set-Content -Path $ResolvedAdminTraceEvidencePath -Encoding utf8
    Write-Host "case_copilot_scenario_journey_verified case_id=$caseId asset_id=$($asset.asset_id) evidence=$ResolvedAdminTraceEvidencePath"
}

function Invoke-FounderLiveReadinessFlow {
    $create = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/startup/cases" `
        -ContentType "application/json" `
        -Body (@{ fixture_mode = "live"; auto_start = $false; company_name = "FounderCo" } | ConvertTo-Json)
    if ($create.provider_status -ne "configured") {
        Write-SmokeError "live_provider_unavailable" "Live provider is not configured; use -Mode offline-fixture for deterministic demo validation."
        exit 3
    }
    Write-Host "live_provider_configured case_id=$($create.case_id)"
}

function Get-FounderUploadMediaType([string] $FilePath) {
    $extension = [System.IO.Path]::GetExtension($FilePath).ToLowerInvariant()
    switch ($extension) {
        ".csv" { return "text/csv" }
        ".xlsx" { return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }
        ".txt" { return "text/plain" }
        ".pdf" { return "application/pdf" }
        ".docx" { return "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }
        ".png" { return "image/png" }
        ".jpg" { return "image/jpeg" }
        ".jpeg" { return "image/jpeg" }
        ".zip" { return "application/zip" }
        default { throw "unsupported_smoke_upload_type path=$FilePath" }
    }
}

function Resolve-FounderOfflineFixture([string] $Candidate) {
    $fixture = if ([string]::IsNullOrWhiteSpace($Candidate)) {
        $FounderMetricsFixture
    } elseif ([System.IO.Path]::IsPathRooted($Candidate)) {
        [System.IO.Path]::GetFullPath($Candidate)
    } else {
        [System.IO.Path]::GetFullPath((Join-Path $Root $Candidate))
    }
    if (-not (Test-Path -LiteralPath $fixture -PathType Leaf)) {
        Write-SmokeError "offline_fixture_missing" "Fixture does not exist."
        exit 2
    }
    $resolvedFixture = (Resolve-Path -LiteralPath $fixture).Path
    if (($RequirePdfUploadJourney -or $RequireSmartUniversitySinglePdfJourney) -and (Get-FounderUploadMediaType $resolvedFixture) -ne "application/pdf") {
        Write-SmokeError "pdf_required_fixture_not_pdf" "PDF-required mode accepts only PDF fixtures."
        exit 2
    }
    return $resolvedFixture
}

function Get-FounderFixtureSafeSummary([string] $FixturePath) {
    $mediaType = Get-FounderUploadMediaType $FixturePath
    $bytes = (Get-Item -LiteralPath $FixturePath).Length
    $stream = [System.IO.File]::OpenRead($FixturePath)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $hasher.ComputeHash($stream)
        $hash = ([System.BitConverter]::ToString($hashBytes)).Replace('-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
        $stream.Dispose()
    }
    return "fixture_mime=$mediaType fixture_bytes=$bytes fixture_sha256=sha256:$hash"
}

function Invoke-MultipartUpload([string] $Uri, [string[]] $Files) {
    return Invoke-MultipartUploadWithAutoStart `
        -Uri $Uri `
        -Files $Files `
        -AutoStart $true `
        -MediaTypeResolver ${function:Get-FounderUploadMediaType}
}

function Invoke-MultipartUploadWithoutAutoStart([string] $Uri, [string[]] $Files) {
    return Invoke-MultipartUploadWithAutoStart `
        -Uri $Uri `
        -Files $Files `
        -AutoStart $false `
        -MediaTypeResolver ${function:Get-FounderUploadMediaType}
}

function Invoke-MultipartUploadWithAutoStart(
    [string] $Uri,
    [string[]] $Files,
    [bool] $AutoStart,
    [scriptblock] $MediaTypeResolver
) {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $fileStreams = New-Object System.Collections.Generic.List[System.IO.FileStream]
    try {
        $content.Add((New-Object System.Net.Http.StringContent($AutoStart.ToString().ToLowerInvariant())), "auto_start")
        $content.Add((New-Object System.Net.Http.StringContent("FounderCo")), "company_name")
        foreach ($filePath in $Files) {
            $stream = [System.IO.File]::OpenRead($filePath)
            $fileStreams.Add($stream)
            $fileContent = New-Object System.Net.Http.StreamContent($stream)
            $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse((& $MediaTypeResolver $filePath))
            $content.Add($fileContent, "files", [System.IO.Path]::GetFileName($filePath))
        }
        $response = $client.PostAsync($Uri, $content).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "upload_failed status=$([int] $response.StatusCode) body=$body"
        }
        return $body | ConvertFrom-Json
    } finally {
        foreach ($stream in $fileStreams) {
            $stream.Dispose()
        }
        $content.Dispose()
        $client.Dispose()
    }
}

function Capture-FounderScreenshots(
    [string] $Driver,
    [string] $FixturePath = "",
    [string] $AuditSpoolRoot = ""
) {
    $desktopPath = if ($ScreenshotDir) {
        Join-Path $ResolvedScreenshotRoot "founder-desktop.png"
    } else {
        Join-Path $Root "artifacts/ui/founder-desktop.png"
    }
    $desktopStatesPath = if ($ScreenshotDir) {
        Join-Path $ResolvedScreenshotRoot "desktop-states"
    } else {
        Join-Path $Root "artifacts/ui/founder-desktop-states"
    }
    $driverName = (Split-Path -Leaf $Driver).ToLowerInvariant()
    if ($driverName -eq "msedge.exe") {
        $captureHelper = Join-Path $Root "scripts/capture_founder_screenshots.mjs"
        $captureArgs = @(
            $captureHelper,
            "--browser=$Driver",
            "--url=$WebBaseUrl/"
        )
        if ($FixturePath) {
            if ($RequireCaseCopilotScenarioJourney -or $RequireSmartUniversitySinglePdfJourney) {
                $captureArgs += "--desktop=$desktopPath"
            } else {
                $captureArgs += "--desktop-states=$desktopStatesPath"
                $captureArgs += "--require-desktop-state-suite=true"
            }
            $captureArgs += "--fixture=$FixturePath"
            $captureArgs += "--evidence=$ResolvedBrowserEvidencePath"
            $captureArgs += "--admin-url=$AdminBaseUrl/"
            $captureArgs += "--advisor-answer=$AdvisorAnswer"
            $captureArgs += "--invalid-advisor-answer=$InvalidAdvisorAnswer"
        } else {
            $captureArgs += "--desktop=$desktopPath"
        }
        if ($RequirePdfUploadJourney) {
            if ([string]::IsNullOrWhiteSpace($AuditSpoolRoot)) {
                throw "browser_evidence_admin_trace_audit_missing"
            }
            $captureArgs += "--require-pdf-upload-journey=true"
            $captureArgs += "--audit-spool-root=$AuditSpoolRoot"
        }
        if ($RequireCaseCopilotScenarioJourney) {
            $captureArgs += "--require-case-copilot-scenario-journey=true"
            $caseCopilotRestartId = "$SmokeRunId-$PID"
            $caseCopilotRestartRequestPath = Join-Path $ResolvedScreenshotRoot "case-copilot-restart-request-$caseCopilotRestartId.json"
            $caseCopilotRestartReadyPath = Join-Path $ResolvedScreenshotRoot "case-copilot-restart-ready-$caseCopilotRestartId.json"
            $captureArgs += "--case-copilot-restart-request=$caseCopilotRestartRequestPath"
            $captureArgs += "--case-copilot-restart-ready=$caseCopilotRestartReadyPath"
        }
        if ($RequireSmartUniversitySinglePdfJourney) {
            $captureArgs += "--require-smart-university-single-pdf-journey=true"
            if ($RequireSmartUniversityLivePublicResearch) {
                if ([string]::IsNullOrWhiteSpace($AuditSpoolRoot)) {
                    throw "smart_university_live_research_audit_missing"
                }
                $captureArgs += "--require-smart-university-live-public-research=true"
                $captureArgs += "--audit-spool-root=$AuditSpoolRoot"
            }
            $smartUniversityRestartId = "$SmokeRunId-$PID"
            $smartUniversityRestartRequestPath = Join-Path $ResolvedScreenshotRoot "smart-university-restart-request-$smartUniversityRestartId.json"
            $smartUniversityRestartReadyPath = Join-Path $ResolvedScreenshotRoot "smart-university-restart-ready-$smartUniversityRestartId.json"
            $captureArgs += "--case-copilot-restart-request=$smartUniversityRestartRequestPath"
            $captureArgs += "--case-copilot-restart-ready=$smartUniversityRestartReadyPath"
        }
        if ($ResolvedAdminTraceEvidencePath) {
            $captureArgs += "--admin-trace-json=$ResolvedAdminTraceEvidencePath"
        }
        if ($BlockedBrowserInjectionOrigin) {
            $normalizedOrigins = New-Object System.Collections.Generic.List[string]
            foreach ($rawOrigin in ($BlockedBrowserInjectionOrigin -split ",")) {
                $parsedOrigin = [System.Uri] $rawOrigin.Trim()
                if (
                    -not $parsedOrigin.IsAbsoluteUri -or
                    $parsedOrigin.Scheme -notin @("http", "https") -or
                    $parsedOrigin.UserInfo -or
                    $parsedOrigin.AbsolutePath -ne "/" -or
                    $parsedOrigin.Query -or
                    $parsedOrigin.Fragment
                ) {
                    throw "blocked_browser_injection_origin_invalid"
                }
                $normalizedOrigins.Add($parsedOrigin.GetLeftPart([System.UriPartial]::Authority)) | Out-Null
            }
            $captureArgs += "--allow-blocked-parser-script-origin=$($normalizedOrigins -join ',')"
        }
        if ($RequireCaseCopilotScenarioJourney -or $RequireSmartUniversitySinglePdfJourney) {
            $restartRequestPath = if ($RequireSmartUniversitySinglePdfJourney) { $smartUniversityRestartRequestPath } else { $caseCopilotRestartRequestPath }
            $restartReadyPath = if ($RequireSmartUniversitySinglePdfJourney) { $smartUniversityRestartReadyPath } else { $caseCopilotRestartReadyPath }
            Invoke-FounderScreenshotCaptureWithCaseCopilotRestart `
                $captureArgs `
                $restartRequestPath `
                $restartReadyPath `
                $apiCommand `
                $AdminCommand `
                $webCommand
        } else {
            & node @captureArgs
            if ($LASTEXITCODE -ne 0) { throw "screenshot_capture_failed cdp" }
        }
        if ($FixturePath -and -not (Test-Path -LiteralPath $ResolvedBrowserEvidencePath -PathType Leaf)) {
            throw "browser_evidence_missing path=$ResolvedBrowserEvidencePath"
        }
        return
    }
    if ($FixturePath) {
        throw "founder_gtm_journey_requires_cdp_browser driver=$Driver"
    }
    & $Driver screenshot --viewport-size=1440,1000 "$WebBaseUrl/" $desktopPath
    if ($LASTEXITCODE -ne 0) { throw "screenshot_capture_failed desktop" }
}

function Resolve-FounderDataRoot([string] $Candidate) {
    if ([System.IO.Path]::IsPathRooted($Candidate)) {
        return [System.IO.Path]::GetFullPath($Candidate)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Candidate))
}

function Resolve-FounderScreenshotRoot([string] $Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return $ArtifactDir
    }
    if ([System.IO.Path]::IsPathRooted($Candidate)) {
        return [System.IO.Path]::GetFullPath($Candidate)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Candidate))
}

function Resolve-FounderBrowserEvidencePath([string] $Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return [System.IO.Path]::GetFullPath((Join-Path $ResolvedScreenshotRoot "browser-evidence.json"))
    }
    if ([System.IO.Path]::IsPathRooted($Candidate)) {
        return [System.IO.Path]::GetFullPath($Candidate)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Candidate))
}

function Resolve-FounderAdminTraceEvidencePath([string] $Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($Candidate)) {
        return [System.IO.Path]::GetFullPath($Candidate)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $Candidate))
}

New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null

if ($Mode -eq "offline-fixture") {
    Clear-SmokeProviderEnv
    $ResolvedEnvFile = $null
} else {
    Clear-SmokeProviderEnv
    $ResolvedEnvFile = Import-SmokeEnvFile $EnvFile
    Clear-SmokeRawTracingEnv
    if ($EnableLangSmithTracing) {
        [Environment]::SetEnvironmentVariable("DDA_LANGSMITH_TRACING", "true", "Process")
    } else {
        [Environment]::SetEnvironmentVariable("DDA_LANGSMITH_TRACING", "false", "Process")
    }
}

Assert-SmokeLaunchContract

if ($CaptureScreenshots) {
    $ScreenshotDriver = Resolve-ScreenshotDriver
}

$ResolvedDataRoot = Resolve-FounderDataRoot $DataDir
$ResolvedScreenshotRoot = Resolve-FounderScreenshotRoot $ScreenshotDir
$ResolvedBrowserEvidencePath = Resolve-FounderBrowserEvidencePath $BrowserEvidencePath
$ResolvedAdminTraceEvidencePath = Resolve-FounderAdminTraceEvidencePath $AdminTraceEvidencePath
$ResolvedOfflineFixture = Resolve-FounderOfflineFixture $OfflineFixturePath
$ResolvedFrontendRoot = if ($FrontendRoot) {
    (Resolve-Path -LiteralPath $FrontendRoot).Path
} else {
    Join-Path $Root "frontend/founder"
}
New-Item -ItemType Directory -Path $ResolvedScreenshotRoot -Force | Out-Null

if ($ValidateOnly) {
    $fixtureSummary = Get-FounderFixtureSafeSummary $ResolvedOfflineFixture
    $pdfJourney = if ($RequirePdfUploadJourney) { "True" } else { "False" }
    $caseCopilotJourney = if ($RequireCaseCopilotScenarioJourney) { "True" } else { "False" }
    $smartUniversityJourney = if ($RequireSmartUniversitySinglePdfJourney) { "True" } else { "False" }
    $smartUniversityLiveResearch = if ($RequireSmartUniversityLivePublicResearch) { "True" } else { "False" }
    $captureAuditSpoolSummary = if ($Mode -eq "offline-fixture") {
        "startup-api/deterministic/startup-audit-spool"
    } else {
        "startup-api/startup-audit-spool"
    }
    Write-Host "startup_founder_smoke_contract_valid data_root=$ResolvedDataRoot browser_evidence=$ResolvedBrowserEvidencePath mode=$Mode pdf_upload_journey=$pdfJourney case_copilot_scenario_journey=$caseCopilotJourney smart_university_single_pdf_journey=$smartUniversityJourney smart_university_live_public_research=$smartUniversityLiveResearch env_file_loaded=$(Format-Bool ($null -ne $ResolvedEnvFile)) openai_credential_present=$(Format-Bool ((Test-EnvValuePresent 'OPENAI_API_KEY') -or (Test-EnvValuePresent 'OPENAI_STARTUP_API_KEY'))) langsmith_credential_present=$(Format-Bool (Test-EnvValuePresent 'LANGSMITH_API_KEY')) langsmith_tracing_enabled=$(Format-Bool ([Environment]::GetEnvironmentVariable('DDA_LANGSMITH_TRACING', 'Process') -eq 'true')) capture_audit_spool=$captureAuditSpoolSummary $fixtureSummary"
    exit 0
}

try {
    $apiDataDir = Join-Path $ResolvedDataRoot "$Mode-$SmokeRunId"
    $deterministicAuditSpoolRoot = Join-Path $apiDataDir "startup-api/deterministic/startup-audit-spool"
    $liveAuditSpoolRoot = Join-Path $apiDataDir "startup-api/startup-audit-spool"
    $captureAuditSpoolRoot = if ($Mode -eq "offline-fixture") { $deterministicAuditSpoolRoot } else { $liveAuditSpoolRoot }
    $safeRoot = Escape-PowerShellSingleQuotedString $Root
    $safeFrontendRoot = Escape-PowerShellSingleQuotedString $ResolvedFrontendRoot
    $safeApiDataDir = Escape-PowerShellSingleQuotedString $apiDataDir
    $SafeApiBaseUrl = Escape-PowerShellSingleQuotedString $ApiBaseUrl
    $SafeAdminBaseUrl = Escape-PowerShellSingleQuotedString $AdminBaseUrl
    $caseMode = if ($Mode -eq "offline-fixture") { "deterministic_offline" } else { "live" }
    $apiCommand = "& '$safeRoot/scripts/run_founder_api.ps1' -Port $ApiPort -DataDir '$safeApiDataDir' -CaseMode '$caseMode'"
    $nextCommand = Escape-PowerShellSingleQuotedString (Join-Path $ResolvedFrontendRoot "node_modules/.bin/next.cmd")
    $nodeModules = Get-Item -LiteralPath (Join-Path $ResolvedFrontendRoot "node_modules")
    $nextDevBundlerFlag = if ($nodeModules.LinkType) { "--webpack" } else { "--turbo" }
    $nextDistDir = ".next-smoke-$SmokeRunId"
    $StreamlitApp = Escape-PowerShellSingleQuotedString (Join-Path $Root "src/due_diligence_agent/presentation/streamlit/app.py")
    $AdminCommand = "`$env:DDA_DATA_DIR='$safeApiDataDir'; uv run --offline --no-sync --no-default-groups --group stage1a --group stage1a-ui-report --group stage1b-light-ingest --group founder-api --group dev streamlit run '$StreamlitApp' --server.address 127.0.0.1 --server.port $AdminPort --server.headless true --browser.gatherUsageStats false"
    $webCommand = "`$env:FOUNDER_API_BASE_URL='$SafeApiBaseUrl'; `$env:NEXT_PUBLIC_ADMIN_CONSOLE_URL='$SafeAdminBaseUrl'; `$env:FOUNDER_CASE_FIXTURE_MODE='$caseMode'; `$env:FOUNDER_NEXT_DIST_DIR='$nextDistDir'; `$env:NEXT_TELEMETRY_DISABLED='1'; Push-Location '$safeFrontendRoot'; & '$nextCommand' dev -H 127.0.0.1 -p $WebPort $nextDevBundlerFlag"
    Start-HiddenPowerShellProcess "founder-api" $apiCommand (Join-Path $ArtifactDir "founder-api.stdout.log") (Join-Path $ArtifactDir "founder-api.stderr.log") | Out-Null
    Start-HiddenPowerShellProcess "founder-admin" $AdminCommand (Join-Path $ArtifactDir "founder-admin.stdout.log") (Join-Path $ArtifactDir "founder-admin.stderr.log") | Out-Null
    Start-HiddenPowerShellProcess "founder-web" $webCommand (Join-Path $ArtifactDir "founder-web.stdout.log") (Join-Path $ArtifactDir "founder-web.stderr.log") | Out-Null
    Wait-HttpOk "$ApiBaseUrl/health/live"
    Wait-HttpOk "$AdminBaseUrl/"
    Wait-HttpOk "$WebBaseUrl/"
    Assert-NoExternalNetwork
    if ($Mode -eq "offline-fixture") {
        if ($RequireSmartUniversitySinglePdfJourney) {
            Write-Host "smart_university_browser_evidence_required path=$ResolvedBrowserEvidencePath"
        } elseif ($RequireCaseCopilotScenarioJourney) {
            Write-Host "case_copilot_browser_evidence_required path=$ResolvedBrowserEvidencePath"
        } else {
            Invoke-FounderFixtureFlow $ResolvedOfflineFixture
        }
    } else {
        Invoke-FounderLiveReadinessFlow
    }
    foreach ($reviewUrl in $BrowserReviewUrls) {
        Wait-HttpOk $reviewUrl
    }
    Assert-NoExternalNetwork
    if ($CaptureScreenshots) {
        $browserFixture = if ($CaptureScreenshots) { $ResolvedOfflineFixture } else { "" }
        Capture-FounderScreenshots $ScreenshotDriver $browserFixture $captureAuditSpoolRoot
    }
    Assert-NoExternalNetwork
    Write-Host "startup_founder_workspace_smoke_passed"
} finally {
    foreach ($pidValue in $StartedPids) {
        Stop-ProcessTree -ProcessId $pidValue
    }
}
