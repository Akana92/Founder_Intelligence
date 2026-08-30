from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import httpx


def test_founder_api_module_boots_on_localhost_and_exposes_contract() -> None:
    """Catches a missing module runner, unsafe bind default, or lost request ID header."""

    port = _unused_localhost_port()
    env = _offline_env()
    command = [
        sys.executable,
        "-m",
        "due_diligence_agent.presentation.api",
        "--port",
        str(port),
    ]
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).parents[2],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        _wait_for_live_health(base_url, process)

        response = httpx.get(f"{base_url}/api/v1/product/capabilities", timeout=2.0)

        assert response.status_code == 200
        assert UUID(response.headers["X-Request-ID"])
        payload = response.json()
        assert payload["contract_version"] == "founder_capabilities.v1"
        assert payload["delivery_profile"] == "sales_ready_hybrid"
        assert payload["surfaces"] == {
            "founder_workspace": "separate_web",
            "admin_console": "streamlit",
        }
    finally:
        _assert_clean_localhost_shutdown(process, port)


def _offline_env() -> dict[str, str]:
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = ""
    env["UV_OFFLINE"] = "true"
    env["DDA_NEWS_SOURCE"] = "fixture"
    env["DDA_SEC_SOURCE"] = "fixture"
    env["DDA_YFINANCE_SOURCE"] = "fixture"
    env["LANGSMITH_TRACING"] = "false"
    env["DDA_LANGSMITH_TRACING"] = "false"
    return env


def _unused_localhost_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_for_live_health(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 15
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(
                f"Founder API exited before health check. stdout={stdout!r} stderr={stderr!r}"
            )
        try:
            response = httpx.get(f"{base_url}/health/live", timeout=0.5)
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(0.2)
            continue
        if response.status_code == 200 and response.json() == {"status": "ok"}:
            assert UUID(response.headers["X-Request-ID"])
            return
        time.sleep(0.2)
    raise AssertionError(f"Founder API did not become healthy: {last_error!r}")


def _assert_clean_localhost_shutdown(process: subprocess.Popen[str], port: int) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    for _ in _short_poll_interval():
        if process.poll() is not None:
            _assert_localhost_bind_log(process, port)
            return
        time.sleep(0.1)
    process.kill()
    process.wait(timeout=5)
    raise AssertionError("Founder API did not terminate cleanly after SIGTERM")


def _assert_localhost_bind_log(process: subprocess.Popen[str], port: int) -> None:
    stdout, stderr = process.communicate(timeout=5)
    expected_bind = f"http://127.0.0.1:{port}"
    assert expected_bind in stderr, f"stdout={stdout!r} stderr={stderr!r}"


def _short_poll_interval() -> Iterator[None]:
    for _ in range(30):
        yield None
