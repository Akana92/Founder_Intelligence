from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path("scripts/start_founder_workspace.ps1")


def _run_validate_only(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-ValidateOnly",
            *args,
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=20,
    )


def test_start_founder_workspace_script_parses_and_uses_one_safe_runtime_contract() -> None:
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
    assert "run_founder_api.ps1" in text
    assert "streamlit run" in text
    assert "src/due_diligence_agent/presentation/streamlit/app.py" in text
    assert "frontend/founder/node_modules/.bin/next.cmd" in text
    assert "$env:DDA_DATA_DIR" in text
    assert "$env:FOUNDER_API_BASE_URL" in text
    assert "$env:NEXT_PUBLIC_ADMIN_CONSOLE_URL" in text
    assert "$env:FOUNDER_CASE_FIXTURE_MODE" in text
    assert "$env:NEXT_TELEMETRY_DISABLED" in text
    assert "Start-Process" in text
    assert "GetActiveTcpListeners" in text
    assert "Get-NetTCPConnection" not in text
    assert "-WindowStyle Hidden" in text
    assert "-RedirectStandardOutput" in text
    assert "-RedirectStandardError" in text
    assert "Stop-Process -Name" not in text
    assert "taskkill" not in text.lower()
    assert "sk-proj-" not in text


def test_start_founder_workspace_uses_link_aware_next_dev_runtime_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "workspace_linked_node_modules_unsupported" not in text
    assert "Run npm ci in frontend/founder" not in text
    assert '$NextDevBundlerFlag = if ($NodeModules.LinkType) { "--webpack" } else { "--turbo" }' in text
    assert '$NextDistDir = ".next-owner-$RunId"' in text
    assert "node_modules_linked=$(Format-Bool ($null -ne $NodeModules.LinkType))" in text
    assert "next_dist_dir=$NextDistDir" in text
    assert "$env:FOUNDER_NEXT_DIST_DIR" in text
    assert "Push-Location '$SafeFrontendRoot'" in text
    assert "dev -H 127.0.0.1 -p $WebPort $NextDevBundlerFlag" in text


def test_founder_next_config_supports_linked_runtime_with_webpack_resolution() -> None:
    next_config = Path("frontend/founder/next.config.ts").read_text(encoding="utf-8")

    assert "webpack(config, { webpack })" in next_config
    assert "config.resolve.symlinks = false" in next_config
    assert "NormalModuleReplacementPlugin" in next_config
    assert r"/^\.\/([A-Za-z]:\/.*)$/" in next_config
    assert "resource.request = resource.request.slice(2)" in next_config


def test_start_founder_workspace_validate_only_accepts_absolute_data_dir(tmp_path: Path) -> None:
    data_dir = tmp_path / "shared-demo-data"

    result = _run_validate_only("-DataDir", str(data_dir))

    assert result.returncode == 0, result.stderr
    assert "startup_founder_workspace_launch_contract_valid" in result.stdout
    assert f"data_root={data_dir}" in result.stdout
    assert f"{Path.cwd()}{data_dir}" not in result.stdout
    assert "api_url=http://127.0.0.1:8000" in result.stdout
    assert "founder_url=http://127.0.0.1:3000" in result.stdout
    assert "admin_url=http://127.0.0.1:8501" in result.stdout


def test_start_founder_workspace_validate_only_accepts_relative_data_dir() -> None:
    result = _run_validate_only("-DataDir", ".tmp-launch-demo")

    assert result.returncode == 0, result.stderr
    assert "startup_founder_workspace_launch_contract_valid" in result.stdout
    assert f"data_root={Path.cwd() / '.tmp-launch-demo'}" in result.stdout


def test_start_founder_workspace_validate_only_rejects_conflicting_ports(tmp_path: Path) -> None:
    result = _run_validate_only(
        "-DataDir",
        str(tmp_path / "data"),
        "-ApiPort",
        "8000",
        "-WebPort",
        "8000",
    )

    assert result.returncode != 0
    assert "workspace_port_conflict" in (result.stderr + result.stdout)


def test_start_founder_workspace_validate_only_prints_custom_urls_and_logs(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"

    result = _run_validate_only(
        "-DataDir",
        str(data_dir),
        "-LogDir",
        str(log_dir),
        "-ApiPort",
        "8100",
        "-WebPort",
        "3100",
        "-AdminPort",
        "8601",
    )

    assert result.returncode == 0, result.stderr
    assert f"data_root={data_dir}" in result.stdout
    assert f"log_root={log_dir}" in result.stdout
    assert "api_url=http://127.0.0.1:8100" in result.stdout
    assert "founder_url=http://127.0.0.1:3100" in result.stdout
    assert "admin_url=http://127.0.0.1:8601" in result.stdout


def test_start_founder_workspace_validate_only_exposes_explicit_case_mode(
    tmp_path: Path,
) -> None:
    result = _run_validate_only(
        "-DataDir",
        str(tmp_path / "data"),
        "-CaseMode",
        "deterministic_offline",
    )

    assert result.returncode == 0, result.stderr
    assert "case_mode=deterministic_offline" in result.stdout


def test_start_founder_workspace_validate_only_passes_case_mode_to_api_launcher() -> None:
    result = _run_validate_only(
        "-DataDir",
        ".tmp-task1-start-data",
        "-CaseMode",
        "deterministic_offline",
    )

    assert result.returncode == 0, result.stderr
    assert "case_mode=deterministic_offline" in result.stdout
    assert "api_case_mode=deterministic_offline" in result.stdout
    assert "-CaseMode deterministic_offline" in result.stdout


def test_start_founder_workspace_rejects_unknown_case_mode(tmp_path: Path) -> None:
    result = _run_validate_only(
        "-DataDir",
        str(tmp_path / "data"),
        "-CaseMode",
        "demo",
    )

    assert result.returncode != 0
    assert "ParameterArgumentValidationError" in (result.stderr + result.stdout)


def test_start_founder_workspace_validate_only_loads_env_file_without_leaking_values(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "launch.env"
    openai_secret = "sk-" + "proj-test-secret-value"
    langsmith_secret = "lsv2-test-secret-value"
    env_file.write_text(
        "\n".join(
            [
                "# fake test credentials",
                f"OPENAI_API_KEY={openai_secret}",
                f"LANGSMITH_API_KEY='{langsmith_secret}'",
                "DDA_TEST_SAFE_FLAG=enabled",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_validate_only(
        "-DataDir",
        str(tmp_path / "data"),
        "-EnvFile",
        str(env_file),
        "-EnableLangSmithTracing",
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, result.stderr
    assert f"env_file={env_file}" in result.stdout
    assert "env_file_loaded=true" in result.stdout
    assert "openai_credential_present=true" in result.stdout
    assert "langsmith_credential_present=true" in result.stdout
    assert "langsmith_tracing_enabled=true" in result.stdout
    assert openai_secret not in combined_output
    assert langsmith_secret not in combined_output
    assert "DDA_TEST_SAFE_FLAG=enabled" not in combined_output


def test_start_founder_workspace_validate_only_clears_raw_tracing_from_env_file(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "launch.env"
    raw_tracing_secret = "raw-langchain-secret-value"
    langsmith_secret = "lsv2-test-secret-value"
    env_file.write_text(
        "\n".join(
            [
                "LANGSMITH_TRACING=true",
                "LANGCHAIN_TRACING=true",
                "LANGCHAIN_TRACING_V2=true",
                f"LANGCHAIN_API_KEY={raw_tracing_secret}",
                f"LANGSMITH_API_KEY={langsmith_secret}",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_validate_only(
        "-DataDir",
        str(tmp_path / "data"),
        "-EnvFile",
        str(env_file),
        "-EnableLangSmithTracing",
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, result.stderr
    assert "raw_langsmith_tracing_present=false" in result.stdout
    assert "raw_langchain_tracing_present=false" in result.stdout
    assert "raw_langchain_tracing_v2_present=false" in result.stdout
    assert "raw_langchain_api_key_present=false" in result.stdout
    assert "langsmith_credential_present=true" in result.stdout
    assert "langsmith_tracing_enabled=true" in result.stdout
    assert raw_tracing_secret not in combined_output
    assert langsmith_secret not in combined_output


def test_start_founder_workspace_validate_only_clears_inherited_raw_tracing(
    tmp_path: Path,
) -> None:
    inherited_env = os.environ.copy()
    inherited_env.update(
        {
            "LANGSMITH_TRACING": "true",
            "LANGCHAIN_TRACING": "true",
            "LANGCHAIN_TRACING_V2": "true",
            "LANGCHAIN_API_KEY": "raw-inherited-secret-value",
            "LANGSMITH_API_KEY": "lsv2-inherited-secret-value",
        }
    )

    result = _run_validate_only(
        "-DataDir",
        str(tmp_path / "data"),
        "-EnableLangSmithTracing",
        env=inherited_env,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, result.stderr
    assert "raw_langsmith_tracing_present=false" in result.stdout
    assert "raw_langchain_tracing_present=false" in result.stdout
    assert "raw_langchain_tracing_v2_present=false" in result.stdout
    assert "raw_langchain_api_key_present=false" in result.stdout
    assert "langsmith_credential_present=true" in result.stdout
    assert "langsmith_tracing_enabled=true" in result.stdout
    assert "raw-inherited-secret-value" not in combined_output
    assert "lsv2-inherited-secret-value" not in combined_output


def test_start_founder_workspace_validate_only_rejects_missing_env_file(
    tmp_path: Path,
) -> None:
    missing_env_file = tmp_path / "missing.env"

    result = _run_validate_only(
        "-DataDir",
        str(tmp_path / "data"),
        "-EnvFile",
        str(missing_env_file),
    )

    assert result.returncode != 0
    assert "workspace_env_file_missing" in (result.stderr + result.stdout)
    assert str(missing_env_file) in (result.stderr + result.stdout)


def test_start_founder_workspace_validate_only_rejects_invalid_env_file_line(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "invalid.env"
    env_file.write_text(
        "OPENAI_API_KEY=" + "sk-" + "proj-test-secret-value\nnot a dotenv line\n",
        encoding="utf-8",
    )

    result = _run_validate_only(
        "-DataDir",
        str(tmp_path / "data"),
        "-EnvFile",
        str(env_file),
    )

    combined_output = result.stderr + result.stdout
    assert result.returncode != 0
    assert "workspace_env_file_invalid" in combined_output
    assert "sk-" + "proj-test-secret-value" not in combined_output
