from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

SCRIPT = Path("scripts/smoke_founder_workspace.ps1")
API_SCRIPT = Path("scripts/run_founder_api.ps1")


def test_founder_workspace_smoke_script_parses_and_exposes_safe_contract() -> None:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"$null = [scriptblock]::Create((Get-Content -Raw '{SCRIPT.as_posix()}'))",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[ValidateSet('offline-fixture','live-api')]" in text
    assert "[switch] $CaptureScreenshots" in text
    assert "Start-Process" in text
    assert "-WindowStyle Hidden" in text
    assert "Stop-ProcessTree" in text
    assert "Get-CimInstance Win32_Process" in text
    assert "taskkill" not in text.lower()
    assert "Stop-Process -Name" not in text
    assert "Get-Process |" not in text


def test_founder_workspace_smoke_starts_self_contained_admin_console() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "[int] $AdminPort = 8501" in text
    assert '$AdminBaseUrl = "http://127.0.0.1:$AdminPort"' in text
    assert '$StreamlitApp = ' in text
    assert "src/due_diligence_agent/presentation/streamlit/app.py" in text
    assert '$AdminCommand = ' in text
    assert "streamlit run '$StreamlitApp'" in text
    assert "--server.address 127.0.0.1" in text
    assert "--server.port $AdminPort" in text
    assert "NEXT_PUBLIC_ADMIN_CONSOLE_URL='$SafeAdminBaseUrl'" in text
    assert 'Start-HiddenPowerShellProcess "founder-admin" $AdminCommand' in text
    assert 'Wait-HttpOk "$AdminBaseUrl/"' in text

    admin_start = text.index('Start-HiddenPowerShellProcess "founder-admin" $AdminCommand')
    web_wait = text.index('Wait-HttpOk "$WebBaseUrl/"')
    admin_wait = text.index('Wait-HttpOk "$AdminBaseUrl/"')
    first_external_network_assert = text.index("Assert-NoExternalNetwork", admin_wait)
    assert admin_start < admin_wait < first_external_network_assert
    assert web_wait < first_external_network_assert


def test_founder_workspace_smoke_validate_only_accepts_absolute_data_dir(tmp_path: Path) -> None:
    data_dir = tmp_path / "absolute-smoke-data"

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "offline-fixture",
            "-ValidateOnly",
            "-DataDir",
            str(data_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "startup_founder_smoke_contract_valid" in result.stdout
    assert f"data_root={data_dir}" in result.stdout
    assert f"{Path.cwd()}{data_dir}" not in result.stdout


def test_founder_workspace_smoke_validate_only_accepts_explicit_pdf_required_mode(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "founder-smoke-fixture.pdf"
    fixture.write_bytes(b"%PDF-1.4\n% deterministic founder smoke fixture\n%%EOF\n")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "offline-fixture",
            "-ValidateOnly",
            "-DataDir",
            str(tmp_path / "data"),
            "-OfflineFixturePath",
            str(fixture),
            "-RequirePdfUploadJourney",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "pdf_upload_journey=True" in result.stdout
    assert "fixture_mime=application/pdf" in result.stdout
    assert "nomadflow_ai_startup_test_business_plan_ru.pdf" not in result.stdout
    assert str(fixture) not in result.stdout


def test_founder_workspace_smoke_validate_only_accepts_second_pdf_required_mode(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/startup_synthetic_v1/cases/pre_revenue_service/concept.pdf")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "offline-fixture",
            "-ValidateOnly",
            "-DataDir",
            str(tmp_path / "data"),
            "-OfflineFixturePath",
            str(fixture),
            "-RequirePdfUploadJourney",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "pdf_upload_journey=True" in result.stdout
    assert "fixture_mime=application/pdf" in result.stdout
    assert "concept.pdf" not in result.stdout
    assert str(fixture) not in result.stdout


def test_founder_workspace_smoke_validate_only_rejects_csv_when_pdf_required(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/startup_workspace_smoke_v1/documents/founder_metrics.csv")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "offline-fixture",
            "-ValidateOnly",
            "-DataDir",
            str(tmp_path / "data"),
            "-OfflineFixturePath",
            str(fixture),
            "-RequirePdfUploadJourney",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "pdf_required_fixture_not_pdf" in result.stderr
    assert "founder_metrics.csv" not in result.stderr
    assert str(fixture) not in result.stderr


def test_run_founder_api_defaults_to_localhost_and_accepts_data_dir() -> None:
    text = Path("scripts/run_founder_api.ps1").read_text(encoding="utf-8")

    assert '[string] $HostAddress = "127.0.0.1"' in text
    assert "[string] $DataDir" in text
    assert '"--no-sync"' in text
    assert "--host" in text
    assert "DDA_DATA_DIR" in text


def test_founder_workspace_smoke_forwards_resolved_case_mode_to_api_launcher() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert (
        "run_founder_api.ps1' -Port $ApiPort -DataDir '$safeApiDataDir' "
        "-CaseMode '$caseMode'"
    ) in text


def test_run_founder_api_validate_only_reports_default_live_contract() -> None:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(API_SCRIPT),
            "-ValidateOnly",
            "-DataDir",
            ".tmp-task1-api-data",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "startup_founder_api_launch_contract_valid" in result.stdout
    assert "case_mode=live" in result.stdout
    assert "fixture_mode_env=live" in result.stdout
    assert f"data_root={Path.cwd() / '.tmp-task1-api-data'}" in result.stdout
    assert "host=127.0.0.1" in result.stdout
    assert "port=8000" in result.stdout


def test_run_founder_api_validate_only_reports_deterministic_case_mode() -> None:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(API_SCRIPT),
            "-ValidateOnly",
            "-DataDir",
            ".tmp-task1-api-data",
            "-CaseMode",
            "deterministic_offline",
            "-Port",
            "8100",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "case_mode=deterministic_offline" in result.stdout
    assert "fixture_mode_env=deterministic_offline" in result.stdout
    assert "host=127.0.0.1" in result.stdout
    assert "port=8100" in result.stdout


def test_run_founder_api_rejects_unknown_case_mode() -> None:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(API_SCRIPT),
            "-ValidateOnly",
            "-DataDir",
            ".tmp-task1-api-data",
            "-CaseMode",
            "demo",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "ValidateSet" in (result.stderr + result.stdout)


def test_founder_smoke_isolates_next_dev_cache_from_an_existing_workspace() -> None:
    smoke = SCRIPT.read_text(encoding="utf-8")
    next_config = Path("frontend/founder/next.config.ts").read_text(encoding="utf-8")

    assert "$env:FOUNDER_NEXT_DIST_DIR" in smoke
    assert '.next-smoke-$SmokeRunId' in smoke
    assert '.next/smoke-$SmokeRunId' not in smoke
    assert "process.env.FOUNDER_NEXT_DIST_DIR" in next_config
    assert "distDir:" in next_config


def test_live_founder_screenshot_capture_uploads_the_explicit_fixture() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert (
        '$browserFixture = if ($CaptureScreenshots) { $ResolvedOfflineFixture } else { "" }'
        in text
    )
    assert "Capture-FounderScreenshots $ScreenshotDriver $browserFixture" in text
    assert '$browserFixture = if ($Mode -eq "offline-fixture")' not in text


def test_founder_smoke_uses_the_matching_audit_spool_for_each_runtime_mode() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '$liveAuditSpoolRoot = Join-Path $apiDataDir "startup-api/startup-audit-spool"' in text
    assert (
        '$captureAuditSpoolRoot = if ($Mode -eq "offline-fixture") '
        '{ $deterministicAuditSpoolRoot } else { $liveAuditSpoolRoot }'
        in text
    )
    assert "Capture-FounderScreenshots $ScreenshotDriver $browserFixture $captureAuditSpoolRoot" in text


def test_founder_smoke_live_smart_university_forwards_online_research_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "[switch] $RequireSmartUniversityLivePublicResearch" in text
    assert '"--require-smart-university-live-public-research=true"' in text
    assert "Assert-SmokeLaunchContract" in text
    assert "smart_university_live_research_requires_live_api" in text
    assert "smart_university_live_research_requires_smart_university_journey" in text
    assert "smart_university_live_research_requires_openai_credential" in text


def test_founder_smoke_live_validate_only_loads_env_without_leaking_values(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "live.env"
    openai_secret = "sk-" + "proj-smoke-live-secret"
    langsmith_secret = "lsv2-smoke-live-secret"
    fixture = tmp_path / "smart-university.pdf"
    env_file.write_text(
        f"OPENAI_API_KEY={openai_secret}\nLANGSMITH_API_KEY={langsmith_secret}\n",
        encoding="utf-8",
    )
    fixture.write_bytes(b"%PDF-1.4\n% smart university smoke\n%%EOF\n")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "live-api",
            "-ValidateOnly",
            "-DataDir",
            str(tmp_path / "data"),
            "-OfflineFixturePath",
            str(fixture),
            "-EnvFile",
            str(env_file),
            "-EnableLangSmithTracing",
            "-RequireSmartUniversitySinglePdfJourney",
            "-RequireSmartUniversityLivePublicResearch",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, result.stderr
    assert "mode=live-api" in result.stdout
    assert "env_file_loaded=true" in result.stdout
    assert "openai_credential_present=true" in result.stdout
    assert "langsmith_credential_present=true" in result.stdout
    assert "langsmith_tracing_enabled=true" in result.stdout
    assert "smart_university_live_public_research=True" in result.stdout
    assert "capture_audit_spool=startup-api/startup-audit-spool" in result.stdout
    assert openai_secret not in combined_output
    assert langsmith_secret not in combined_output
    assert str(fixture) not in combined_output


def test_founder_smoke_rejects_live_smart_university_research_without_openai(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "live.env"
    fixture = tmp_path / "smart-university.pdf"
    env_file.write_text("LANGSMITH_API_KEY=lsv2-no-openai-secret\n", encoding="utf-8")
    fixture.write_bytes(b"%PDF-1.4\n% smart university smoke\n%%EOF\n")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "live-api",
            "-ValidateOnly",
            "-DataDir",
            str(tmp_path / "data"),
            "-OfflineFixturePath",
            str(fixture),
            "-EnvFile",
            str(env_file),
            "-RequireSmartUniversitySinglePdfJourney",
            "-RequireSmartUniversityLivePublicResearch",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "smart_university_live_research_requires_openai_credential" in (
        result.stderr + result.stdout
    )


def test_founder_smoke_rejects_online_research_without_explicit_env_file_even_with_ambient_credentials(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "smart-university.pdf"
    fixture.write_bytes(b"%PDF-1.4\n% smart university smoke\n%%EOF\n")
    ambient_openai = "sk-" + "proj-ambient-openai-secret"
    ambient_langsmith = "lsv2-ambient-langsmith-secret"
    env = os.environ.copy()
    env.update(
        {
            "OPENAI_API_KEY": ambient_openai,
            "OPENAI_STARTUP_API_KEY": "sk-" + "proj-ambient-startup-secret",
            "LANGSMITH_API_KEY": ambient_langsmith,
        }
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "live-api",
            "-ValidateOnly",
            "-DataDir",
            str(tmp_path / "data"),
            "-OfflineFixturePath",
            str(fixture),
            "-RequireSmartUniversitySinglePdfJourney",
            "-RequireSmartUniversityLivePublicResearch",
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=20,
    )

    combined_output = result.stderr + result.stdout
    assert result.returncode != 0
    assert "smart_university_live_research_requires_env_file" in combined_output
    assert ambient_openai not in combined_output
    assert ambient_langsmith not in combined_output


def test_founder_smoke_live_clears_ambient_provider_credentials_before_env_import(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "live.env"
    startup_secret = "sk-" + "proj-explicit-startup-secret"
    ambient_openai = "sk-" + "proj-ambient-openai-secret"
    ambient_langsmith = "lsv2-ambient-langsmith-secret"
    fixture = tmp_path / "smart-university.pdf"
    env_file.write_text(f"OPENAI_STARTUP_API_KEY={startup_secret}\n", encoding="utf-8")
    fixture.write_bytes(b"%PDF-1.4\n% smart university smoke\n%%EOF\n")
    env = os.environ.copy()
    env.update(
        {
            "OPENAI_API_KEY": ambient_openai,
            "LANGSMITH_API_KEY": ambient_langsmith,
        }
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "live-api",
            "-ValidateOnly",
            "-DataDir",
            str(tmp_path / "data"),
            "-OfflineFixturePath",
            str(fixture),
            "-EnvFile",
            str(env_file),
            "-EnableLangSmithTracing",
            "-RequireSmartUniversitySinglePdfJourney",
            "-RequireSmartUniversityLivePublicResearch",
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=20,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, result.stderr
    assert "openai_credential_present=true" in result.stdout
    assert "langsmith_credential_present=false" in result.stdout
    assert "env_file_loaded=true" in result.stdout
    assert startup_secret not in combined_output
    assert ambient_openai not in combined_output
    assert ambient_langsmith not in combined_output


def test_founder_smoke_rejects_online_research_in_offline_mode(tmp_path: Path) -> None:
    fixture = tmp_path / "smart-university.pdf"
    fixture.write_bytes(b"%PDF-1.4\n% smart university smoke\n%%EOF\n")

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "offline-fixture",
            "-ValidateOnly",
            "-DataDir",
            str(tmp_path / "data"),
            "-OfflineFixturePath",
            str(fixture),
            "-RequireSmartUniversitySinglePdfJourney",
            "-RequireSmartUniversityLivePublicResearch",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "smart_university_live_research_requires_live_api" in (
        result.stderr + result.stdout
    )


def test_offline_founder_flow_uploads_supported_fixture_media_types() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    fixture_root = Path("tests/fixtures/startup_workspace_smoke_v1/documents")

    for fixture_name in ("founder_metrics.csv",):
        assert (fixture_root / fixture_name).is_file()
        assert f'"documents/{fixture_name}"' in text

    fixture_flow_start = text.index("function Invoke-FounderFixtureFlow")
    fixture_flow_end = text.index(
        "\nfunction Invoke-FounderLiveReadinessFlow",
        fixture_flow_start,
    )
    fixture_flow_body = text[fixture_flow_start:fixture_flow_end]
    assert "startup_founder_frozen_v1" not in fixture_flow_body
    assert ".txt" not in fixture_flow_body

    multipart_upload = re.search(
        r"function Invoke-MultipartUpload\(\[string\] \$Uri, \[string\[\]\] \$Files\) \{(?P<body>.*?)\n\}",
        text,
        flags=re.DOTALL,
    )
    assert multipart_upload is not None
    assert '::Parse("text/plain")' not in multipart_upload.group("body")
    assert "Get-FounderUploadMediaType" in multipart_upload.group("body")
    assert '".csv"' in text
    assert '"text/csv"' in text
    assert '".zip"' in text
    assert '"application/zip"' in text
    assert '".xlsm"' not in text
    assert '/gtm"' in fixture_flow_body
    assert "smoke_gtm_contract_mismatch" in fixture_flow_body
    assert '/profile"' in fixture_flow_body
    assert "smoke_profile_contract_mismatch" in fixture_flow_body
    assert '/report/json"' in fixture_flow_body
    assert '"main_sections"' in fixture_flow_body
    assert '"technical_appendix"' in fixture_flow_body
    assert '"analytics"' in fixture_flow_body
    assert "startup_report_snapshot.v1" not in fixture_flow_body
    assert "smoke_report_contract_mismatch" in fixture_flow_body
    assert "smoke_report_tuple_mismatch" in fixture_flow_body
    assert "smoke_report_section_contract_mismatch" in fixture_flow_body
    assert "smoke_report_metrics_missing" in fixture_flow_body
    assert "smoke_report_json_privacy_violation" in fixture_flow_body
