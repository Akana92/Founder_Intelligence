from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SENSITIVE_COMPOSE_ENV = (
    "OPENAI_API_KEY",
    "OPENAI_STARTUP_API_KEY",
    "LANGSMITH_API_KEY",
    "LANGCHAIN_API_KEY",
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _compose_config(
    *compose_args: str,
    compose_env: dict[str, str] | None = None,
) -> dict[str, object]:
    env = os.environ.copy()
    for key in SENSITIVE_COMPOSE_ENV:
        env[key] = ""
    env["DDA_LANGSMITH_TRACING"] = "false"
    env.pop("FOUNDER_CASE_FIXTURE_MODE", None)
    if compose_env:
        env.update(compose_env)
    completed = subprocess.run(
        [
            "docker",
            "compose",
            *compose_args,
            "-f",
            str(ROOT / "compose.yaml"),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_compose_declares_full_workspace_contract() -> None:
    config = _compose_config("--profile", "admin")
    services = config["services"]
    assert set(services) == {"admin", "api", "web"}
    assert services["admin"]["profiles"] == ["admin"]
    assert services["web"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert services["web"]["environment"]["FOUNDER_API_BASE_URL"] == "http://api:8000"
    assert services["api"]["image"] == services["admin"]["image"]
    assert services["api"]["volumes"][0]["target"] == "/app/data"
    assert services["admin"]["volumes"][0]["target"] == "/app/data"
    assert services["api"]["volumes"][0]["source"] == services["admin"]["volumes"][0]["source"]
    assert "healthcheck" in services["api"]
    assert "healthcheck" in services["web"]
    assert "healthcheck" in services["admin"]


def test_backend_image_is_reproducible_non_root_and_lean() -> None:
    dockerfile = _read("Dockerfile")
    pyproject = _read("pyproject.toml")
    assert "python:3.13-slim-bookworm" in dockerfile
    assert "ghcr.io/astral-sh/uv:0.11.22" in dockerfile
    assert "--group stage1b-light-ingest" in dockerfile
    assert "--group founder-api" in dockerfile
    assert "stage1a-rag-local" not in dockerfile
    assert "--group dev" not in dockerfile
    assert "USER app" in dockerfile
    assert '["investment-dd-api", "--all-interfaces", "--port", "8000"]' in dockerfile
    for resource in ("aapl-2026-10k.html", "aapl-2026-10q.html", "aapl-2026-xbrl.xml"):
        assert (
            f'"src/due_diligence_agent/fixtures/public_us_frozen_v1/sec/{resource}" = '
            f'"due_diligence_agent/fixtures/public_us_frozen_v1/sec/{resource}"'
        ) in pyproject


def test_backend_wheel_includes_startup_market_fixture_package_data() -> None:
    pyproject = tomllib.loads(_read("pyproject.toml"))
    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    assert force_include[
        "src/due_diligence_agent/fixtures/startup_market_research_v1/manifest.json"
    ] == "due_diligence_agent/fixtures/startup_market_research_v1/manifest.json"
    assert force_include[
        "src/due_diligence_agent/fixtures/startup_market_research_v1/sources/competitors.json"
    ] == "due_diligence_agent/fixtures/startup_market_research_v1/sources/competitors.json"
    assert force_include[
        "src/due_diligence_agent/fixtures/startup_market_research_v1/sources/news.json"
    ] == "due_diligence_agent/fixtures/startup_market_research_v1/sources/news.json"


def test_frontend_image_uses_locked_standalone_production_build() -> None:
    dockerfile = _read("frontend/founder/Dockerfile")
    next_config = _read("frontend/founder/next.config.ts")
    package_json = _read("frontend/founder/package.json")
    build_script = _read("frontend/founder/scripts/build-founder.mjs")
    inject_script = _read("frontend/founder/scripts/inject-direction-contract.mjs")
    verify_script = _read("frontend/founder/scripts/verify-direction-contract.mjs")
    assert "FROM node:22-alpine" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "npm exec -- next build" not in dockerfile
    assert ".next/standalone" in dockerfile
    assert ".next/server/app/index.html" not in dockerfile
    assert "USER nextjs" in dockerfile
    assert '["node", "server.js"]' in dockerfile
    assert "FOUNDER_NEXT_STANDALONE" in next_config
    assert 'undefined : "standalone"' in next_config
    assert "node scripts/build-founder.mjs" in package_json
    assert '"build", "--webpack"' in build_script
    assert 'readFile(tsconfigPath, "utf8")' in build_script
    assert "finally" in build_script
    assert 'writeFile(tsconfigPath, tsconfigBeforeBuild, "utf8")' in build_script
    assert "scripts/inject-direction-contract.mjs" in build_script
    assert "scripts/verify-direction-contract.mjs" in build_script
    assert "FOUNDER_NEXT_DIST_DIR" in inject_script
    assert '"standalone"' in inject_script
    assert "FOUNDER_NEXT_DIST_DIR" in verify_script
    assert '"standalone"' in verify_script
    assert "Built ${label} root page" in verify_script
    assert 'verifyOutput(standaloneOutputPath, "standalone")' in verify_script


def test_docker_contexts_and_git_ignore_exclude_local_weight() -> None:
    root_dockerignore = _read(".dockerignore")
    web_dockerignore = _read("frontend/founder/.dockerignore")
    gitignore = _read(".gitignore")
    assert root_dockerignore.lstrip().startswith("**")
    assert "!src/**" in root_dockerignore
    assert web_dockerignore.lstrip().startswith("**")
    assert "!app/**" in web_dockerignore
    for pattern in ("/.uv-cache/", "/pytest*/", "/.pytest*/", "/codex_tmp_pytest/", "/tmp/"):
        assert pattern in gitignore


def test_compose_defaults_to_live_research_runtime_when_mode_is_not_overridden() -> None:
    empty_env_file = ROOT / "tests" / "fixtures" / "empty-compose.env"
    config = _compose_config("--env-file", str(empty_env_file), "--profile", "admin")
    services = config["services"]

    for service_name in ("api", "admin", "web"):
        assert services[service_name]["environment"]["FOUNDER_CASE_FIXTURE_MODE"] == "live"


def test_compose_keeps_explicit_offline_fixture_override_available() -> None:
    config = _compose_config(
        "--profile",
        "admin",
        compose_env={"FOUNDER_CASE_FIXTURE_MODE": "deterministic_offline"},
    )
    services = config["services"]

    for service_name in ("api", "admin", "web"):
        assert (
            services[service_name]["environment"]["FOUNDER_CASE_FIXTURE_MODE"]
            == "deterministic_offline"
        )


def test_docker_example_documents_live_default_and_contains_no_secret() -> None:
    example = _read(".env.docker.example")
    values = {
        key: value
        for line in example.splitlines()
        if line and not line.startswith("#") and "=" in line
        for key, value in [line.split("=", 1)]
    }
    assert values["FOUNDER_CASE_FIXTURE_MODE"] == "live"
    assert values["OPENAI_API_KEY"] == ""
    assert values["OPENAI_STARTUP_API_KEY"] == ""
    readme = _read("README.md")
    assert "docker compose up --build" in readme
    assert "docker compose --profile admin up --build" in readme


def test_compose_enables_sanitized_langsmith_tracing_for_product_runtime() -> None:
    empty_env_file = ROOT / "tests" / "fixtures" / "empty-compose.env"
    config = _compose_config(
        "--env-file",
        str(empty_env_file),
        "--profile",
        "admin",
        compose_env={"DDA_LANGSMITH_TRACING": ""},
    )
    services = config["services"]
    for service_name in ("api", "admin"):
        environment = services[service_name]["environment"]
        assert environment["OPENAI_API_KEY"] == ""
        assert environment["LANGSMITH_API_KEY"] == ""
        assert environment["DDA_LANGSMITH_TRACING"] == "true"

    example = _read(".env.docker.example")
    values = {
        key: value
        for line in example.splitlines()
        if line and not line.startswith("#") and "=" in line
        for key, value in [line.split("=", 1)]
    }
    assert values["LANGSMITH_API_KEY"] == ""
    assert values["DDA_LANGSMITH_TRACING"] == "true"


def test_compose_keeps_explicit_langsmith_tracing_opt_out_available() -> None:
    config = _compose_config(
        "--profile",
        "admin",
        compose_env={"DDA_LANGSMITH_TRACING": "false"},
    )
    services = config["services"]

    for service_name in ("api", "admin"):
        assert services[service_name]["environment"]["DDA_LANGSMITH_TRACING"] == "false"


def test_compose_default_config_does_not_inherit_secret_key_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("OPENAI_API_KEY", "OPENAI_STARTUP_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.setenv(key, f"sentinel-parent-{key.lower()}")

    config = _compose_config("--profile", "admin")
    services = config["services"]
    for service_name in ("api", "admin"):
        environment = services[service_name]["environment"]
        assert environment["OPENAI_API_KEY"] == ""
        assert environment["OPENAI_STARTUP_API_KEY"] == ""
        assert environment["LANGSMITH_API_KEY"] == ""


def test_compose_explicit_key_env_reaches_api_and_admin_only() -> None:
    config = _compose_config(
        "--profile",
        "admin",
        compose_env={
            "OPENAI_API_KEY": "sentinel-openai-compose",
            "OPENAI_STARTUP_API_KEY": "sentinel-openai-startup-compose",
            "LANGSMITH_API_KEY": "sentinel-langsmith-compose",
        },
    )
    services = config["services"]
    for service_name in ("api", "admin"):
        environment = services[service_name]["environment"]
        assert environment["OPENAI_API_KEY"] == "sentinel-openai-compose"
        assert environment["OPENAI_STARTUP_API_KEY"] == "sentinel-openai-startup-compose"
        assert environment["LANGSMITH_API_KEY"] == "sentinel-langsmith-compose"

    web_environment = services["web"]["environment"]
    assert "OPENAI_API_KEY" not in web_environment
    assert "OPENAI_STARTUP_API_KEY" not in web_environment
    assert "LANGSMITH_API_KEY" not in web_environment
