from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_cli_run_sellable_demo_freeze_dispatches_inputs_and_prints_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    captured_inputs: list[object] = []

    class PassingPacket:
        sellable_demo_passed = True

        def to_json_dict(self) -> dict[str, object]:
            return {
                "schema_version": "sellable_demo_freeze_packet@1",
                "sellable_demo_passed": True,
                "artifact_paths": {"packet": "sellable-demo-freeze-packet.json"},
            }

    def fake_build(inputs: object) -> PassingPacket:
        captured_inputs.append(inputs)
        return PassingPacket()

    monkeypatch.setattr(
        "due_diligence_agent.evals.sellable_demo_freeze.build_sellable_demo_freeze_packet",
        fake_build,
    )
    output_dir = tmp_path / "queue5-output"

    exit_code = cli.main(_cli_args(tmp_path, output_dir=output_dir))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert len(captured_inputs) == 1
    inputs = captured_inputs[0]
    assert getattr(inputs, "output_dir") == output_dir
    assert getattr(inputs, "gate_b_result_path") == tmp_path / "gate-b.json"
    assert getattr(inputs, "require_approved_report_lineage") is True
    payload = json.loads(captured.out)
    assert payload["schema_version"] == "sellable_demo_freeze_packet@1"
    assert payload["artifact_paths"]["packet"] == "sellable-demo-freeze-packet.json"


def test_cli_run_sellable_demo_freeze_allows_desktop_only_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import due_diligence_agent.presentation.cli as cli

    captured_inputs: list[object] = []

    class PassingPacket:
        sellable_demo_passed = True

        def to_json_dict(self) -> dict[str, object]:
            return {"sellable_demo_passed": True}

    monkeypatch.setattr(
        "due_diligence_agent.evals.sellable_demo_freeze.build_sellable_demo_freeze_packet",
        lambda inputs: captured_inputs.append(inputs) or PassingPacket(),
    )

    exit_code = cli.main(
        [
            item
            for item in _cli_args(tmp_path, output_dir=tmp_path / "desktop-only-output")
            if item not in {"--mobile-screenshot", str(tmp_path / "mobile.png")}
        ]
    )

    assert exit_code == 0
    assert len(captured_inputs) == 1
    assert getattr(captured_inputs[0], "mobile_screenshot_path") is None


def test_strict_freeze_builder_fails_closed_without_approved_report_lineage(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        SellableDemoFreezeInputs,
        build_sellable_demo_freeze_packet,
    )

    packet = build_sellable_demo_freeze_packet(
        SellableDemoFreezeInputs(
            output_dir=tmp_path / "strict-output",
            gate_b_result_path=tmp_path / "gate-b.json",
            gate_c_result_path=tmp_path / "gate-c.json",
            gate_d_first_result_path=tmp_path / "gate-d-first.json",
            gate_d_second_result_path=tmp_path / "gate-d-second.json",
            gate_e_result_path=tmp_path / "gate-e.json",
            browser_evidence_path=tmp_path / "browser-evidence.json",
            desktop_screenshot_path=tmp_path / "desktop.png",
            mobile_screenshot_path=tmp_path / "mobile.png",
            sample_pdf_path=tmp_path / "sample.pdf",
            demo_script_path=tmp_path / "demo.md",
            capstone_map_path=tmp_path / "capstone-map.md",
            require_approved_report_lineage=True,
        )
    )

    assert packet.sellable_demo_passed is False
    assert "report_approved_lineage_missing" in packet.fail_reasons
    assert packet.approved_report_lineage == {}


def test_strict_freeze_builder_fails_closed_for_invalid_approved_report_lineage(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        SellableDemoFreezeInputs,
        build_sellable_demo_freeze_packet,
    )

    browser_evidence = tmp_path / "browser-evidence.json"
    browser_evidence.write_text(
        json.dumps(
            {
                "admin_trace": {"case_id": "case-with-invalid-report-lineage"},
                "case_id": "case-with-invalid-report-lineage",
                "report_artifact_hashes": {},
            }
        ),
        encoding="utf-8",
    )

    packet = build_sellable_demo_freeze_packet(
        SellableDemoFreezeInputs(
            output_dir=tmp_path / "strict-invalid-output",
            gate_b_result_path=tmp_path / "gate-b.json",
            gate_c_result_path=tmp_path / "gate-c.json",
            gate_d_first_result_path=tmp_path / "gate-d-first.json",
            gate_d_second_result_path=tmp_path / "gate-d-second.json",
            gate_e_result_path=tmp_path / "gate-e.json",
            browser_evidence_path=browser_evidence,
            desktop_screenshot_path=tmp_path / "desktop.png",
            mobile_screenshot_path=tmp_path / "mobile.png",
            sample_pdf_path=tmp_path / "sample.pdf",
            demo_script_path=tmp_path / "demo.md",
            capstone_map_path=tmp_path / "capstone-map.md",
            require_approved_report_lineage=True,
        )
    )

    assert packet.sellable_demo_passed is False
    assert "report_approved_lineage_invalid" in packet.fail_reasons
    assert packet.approved_report_lineage == {}


def test_cli_run_sellable_demo_freeze_returns_one_for_failed_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    class FailedPacket:
        sellable_demo_passed = False

        def to_json_dict(self) -> dict[str, object]:
            return {"sellable_demo_passed": False, "fail_reasons": ["gate_e_failed"]}

    monkeypatch.setattr(
        "due_diligence_agent.evals.sellable_demo_freeze.build_sellable_demo_freeze_packet",
        lambda _inputs: FailedPacket(),
    )

    exit_code = cli.main(_cli_args(tmp_path, output_dir=tmp_path / "failed-output"))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert json.loads(captured.out)["fail_reasons"] == ["gate_e_failed"]


def test_cli_run_sellable_demo_freeze_collision_returns_two_without_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    output_dir = tmp_path / "occupied-output"
    output_dir.mkdir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    calls: list[str] = []

    def fake_build(_inputs: object) -> object:
        calls.append("build")
        raise AssertionError("builder must not run for an output collision")

    monkeypatch.setattr(
        "due_diligence_agent.evals.sellable_demo_freeze.build_sellable_demo_freeze_packet",
        fake_build,
    )

    exit_code = cli.main(_cli_args(tmp_path, output_dir=output_dir))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "evaluation_output_dir_not_empty"
    assert calls == []
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_cli_run_sellable_demo_freeze_reservation_race_returns_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    monkeypatch.setattr(
        "due_diligence_agent.evals.sellable_demo_freeze.build_sellable_demo_freeze_packet",
        lambda _inputs: (_ for _ in ()).throw(ValueError("evaluation_output_dir_not_empty")),
    )

    exit_code = cli.main(_cli_args(tmp_path, output_dir=tmp_path / "race-output"))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "evaluation_output_dir_not_empty"


def test_queue5_freeze_script_forwards_offline_contract_and_child_exit(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the Queue 5 wrapper contract")

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "run_queue5_sellable_demo_freeze.ps1"
    capture_path = tmp_path / "captured.json"
    fake_uv = tmp_path / "fake-uv.ps1"
    fake_uv.write_text(
        "\n".join(
            [
                "function BlankValue($value) { if ($null -eq $value) { '' } else { $value } }",
                "$payload = @{",
                "  args = $args",
                "  env = @{",
                "    OPENAI_API_KEY = BlankValue $env:OPENAI_API_KEY",
                "    OPENAI_STARTUP_API_KEY = BlankValue $env:OPENAI_STARTUP_API_KEY",
                "    LANGSMITH_TRACING = $env:LANGSMITH_TRACING",
                "    LANGCHAIN_TRACING = $env:LANGCHAIN_TRACING",
                "    LANGCHAIN_TRACING_V2 = $env:LANGCHAIN_TRACING_V2",
                "    DDA_LANGSMITH_TRACING = $env:DDA_LANGSMITH_TRACING",
                "    HF_HUB_OFFLINE = $env:HF_HUB_OFFLINE",
                "    TRANSFORMERS_OFFLINE = $env:TRANSFORMERS_OFFLINE",
                "    UV_OFFLINE = $env:UV_OFFLINE",
                "  }",
                "}",
                f"$payload | ConvertTo-Json -Depth 4 | Set-Content -Path '{capture_path}' -Encoding UTF8",
                "exit 43",
                "",
            ]
        ),
        encoding="utf-8",
    )
    evidence = {name: tmp_path / name for name in _EVIDENCE_FILENAMES}
    output_dir = tmp_path / "freeze-output"
    process_env = os.environ.copy()
    process_env["OPENAI_API_KEY"] = "caller-openai-key"
    process_env["OPENAI_STARTUP_API_KEY"] = "caller-startup-key"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-OutputDir",
            str(output_dir),
            "-GateBResult",
            str(evidence["gate-b.json"]),
            "-GateCResult",
            str(evidence["gate-c.json"]),
            "-GateDFirstResult",
            str(evidence["gate-d-first.json"]),
            "-GateDSecondResult",
            str(evidence["gate-d-second.json"]),
            "-GateEResult",
            str(evidence["gate-e.json"]),
            "-BrowserEvidence",
            str(evidence["browser-evidence.json"]),
            "-DesktopScreenshot",
            str(evidence["desktop.png"]),
            "-MobileScreenshot",
            str(evidence["mobile.png"]),
            "-SamplePdf",
            str(evidence["sample.pdf"]),
            "-DemoScript",
            str(evidence["demo.md"]),
            "-CapstoneMap",
            str(evidence["capstone-map.md"]),
            "-UvExecutable",
            str(fake_uv),
        ],
        cwd=repo_root,
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 43, result.stderr
    captured = json.loads(capture_path.read_text(encoding="utf-8-sig"))
    args = captured["args"]
    assert args[:9] == [
        "run",
        "--offline",
        "--no-sync",
        "--no-default-groups",
        "--group",
        "stage1b",
        "--group",
        "founder-api",
        "--group",
    ]
    assert "run-sellable-demo-freeze" in args
    assert str(output_dir) in args
    assert str(evidence["browser-evidence.json"]) in args
    assert captured["env"] == {
        "OPENAI_API_KEY": "",
        "OPENAI_STARTUP_API_KEY": "",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
        "DDA_LANGSMITH_TRACING": "false",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "UV_OFFLINE": "true",
    }


def test_queue5_freeze_script_omits_mobile_argument_when_not_provided(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the Queue 5 wrapper contract")

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "run_queue5_sellable_demo_freeze.ps1"
    capture_path = tmp_path / "captured-desktop-only.json"
    fake_uv = tmp_path / "fake-uv.ps1"
    fake_uv.write_text(
        "\n".join(
            [
                "$payload = @{ args = $args }",
                f"$payload | ConvertTo-Json -Depth 4 | Set-Content -Path '{capture_path}' -Encoding UTF8",
                "exit 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    evidence = {name: tmp_path / name for name in _EVIDENCE_FILENAMES}

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-OutputDir",
            str(tmp_path / "freeze-output"),
            "-GateBResult",
            str(evidence["gate-b.json"]),
            "-GateCResult",
            str(evidence["gate-c.json"]),
            "-GateDFirstResult",
            str(evidence["gate-d-first.json"]),
            "-GateDSecondResult",
            str(evidence["gate-d-second.json"]),
            "-GateEResult",
            str(evidence["gate-e.json"]),
            "-BrowserEvidence",
            str(evidence["browser-evidence.json"]),
            "-DesktopScreenshot",
            str(evidence["desktop.png"]),
            "-SamplePdf",
            str(evidence["sample.pdf"]),
            "-DemoScript",
            str(evidence["demo.md"]),
            "-CapstoneMap",
            str(evidence["capstone-map.md"]),
            "-UvExecutable",
            str(fake_uv),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    args = json.loads(capture_path.read_text(encoding="utf-8-sig"))["args"]
    assert "--desktop-screenshot" in args
    assert "--mobile-screenshot" not in args


def test_queue5_freeze_script_rejects_repository_root_with_exit_two(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the Queue 5 wrapper contract")

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "run_queue5_sellable_demo_freeze.ps1"
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-OutputDir",
        str(repo_root),
    ]
    for parameter in (
        "GateBResult",
        "GateCResult",
        "GateDFirstResult",
        "GateDSecondResult",
        "GateEResult",
        "BrowserEvidence",
        "DesktopScreenshot",
        "MobileScreenshot",
        "SamplePdf",
        "DemoScript",
        "CapstoneMap",
    ):
        command.extend((f"-{parameter}", str(tmp_path / f"{parameter}.artifact")))

    result = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "OutputDir must not be the repository root." in result.stderr


_EVIDENCE_FILENAMES = (
    "gate-b.json",
    "gate-c.json",
    "gate-d-first.json",
    "gate-d-second.json",
    "gate-e.json",
    "browser-evidence.json",
    "desktop.png",
    "mobile.png",
    "sample.pdf",
    "demo.md",
    "capstone-map.md",
)


def _cli_args(tmp_path: Path, *, output_dir: Path) -> list[str]:
    return [
        "run-sellable-demo-freeze",
        "--output-dir",
        str(output_dir),
        "--gate-b-result",
        str(tmp_path / "gate-b.json"),
        "--gate-c-result",
        str(tmp_path / "gate-c.json"),
        "--gate-d-first-result",
        str(tmp_path / "gate-d-first.json"),
        "--gate-d-second-result",
        str(tmp_path / "gate-d-second.json"),
        "--gate-e-result",
        str(tmp_path / "gate-e.json"),
        "--browser-evidence",
        str(tmp_path / "browser-evidence.json"),
        "--desktop-screenshot",
        str(tmp_path / "desktop.png"),
        "--mobile-screenshot",
        str(tmp_path / "mobile.png"),
        "--sample-pdf",
        str(tmp_path / "sample.pdf"),
        "--demo-script",
        str(tmp_path / "demo.md"),
        "--capstone-map",
        str(tmp_path / "capstone-map.md"),
    ]
