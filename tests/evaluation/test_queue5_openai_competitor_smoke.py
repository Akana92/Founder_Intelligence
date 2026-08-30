from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        FrozenCompetitorEvidence,
        Gate2Evidence,
        OpenAICompetitorRow,
        SanitizedStartupProfile,
    )


def test_openai_competitor_smoke_missing_key_skips_without_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import due_diligence_agent.evals.openai_competitor_smoke as smoke
    from due_diligence_agent.evals.openai_competitor_smoke import (
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setitem(smoke._OpenAICompetitorSettings.model_config, "env_file", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_STARTUP_API_KEY", raising=False)
    factory = ExplodingOpenAIClientFactory()

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "missing-key",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=_gate2(),
        execute_live=True,
        client_factory=factory,
    )

    assert evidence.schema_version == "openai_competitor_smoke_evidence@1"
    assert evidence.status == "skipped_missing_credential"
    assert evidence.credential_present is False
    assert evidence.execute_live_requested is True
    assert evidence.live_call_attempted is False
    assert evidence.live_call_succeeded is False
    assert evidence.call_count == 0
    assert evidence.inference_label == "live_inference"
    assert evidence.research_label == "not_live_web_research"
    assert evidence.gate2.status == "approved"
    assert evidence.gate2.destination == "openai.responses"
    assert evidence.budget["max_usd"] == "0.25"
    assert evidence.budget["worst_case_usd"] <= "0.25"
    assert evidence.lineage["source"] == "injected_test_evidence"
    assert evidence.source_summary_hashes
    assert evidence.privacy["privacy_leak_count"] == 0
    assert factory.created == 0
    persisted = json.loads(
        (tmp_path / "missing-key" / "openai-competitor-smoke-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["semantic_hash"] == evidence.semantic_hash
    assert not Path(persisted["artifact_paths"]["evidence"]).is_absolute()


def test_openai_competitor_smoke_gate2_guard_blocks_live_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        Gate2Evidence,
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "present-but-not-printed")
    factory = ExplodingOpenAIClientFactory()

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "gate2-blocked",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=Gate2Evidence(
            case_id=_CASE_ID,
            run_id=_RUN_ID,
            status="preview_ready",
            decision="pending",
            destination="openai.responses",
            profile_hash=_PROFILE_HASH,
        ),
        execute_live=True,
        client_factory=factory,
    )

    assert evidence.status == "blocked_gate2_not_approved"
    assert evidence.credential_present is True
    assert evidence.live_call_attempted is False
    assert evidence.live_call_succeeded is False
    assert evidence.fail_reasons == ("gate2_not_approved",)
    assert factory.created == 0
    serialized = json.dumps(evidence.to_json_dict(), sort_keys=True)
    assert "present-but-not-printed" not in serialized


def test_openai_competitor_smoke_fake_live_uses_one_sanitized_structured_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        OpenAICompetitorSynthesis,
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "present-for-fake-client")
    client = RecordingOpenAIClient(
        OpenAICompetitorSynthesis(
            competitors=[
                _row("direct", "workflow diligence suites"),
                _row("indirect", "spreadsheet analyst workflow"),
                _row("substitute", "consultant-led diligence"),
                _row("do_nothing", "manual memo process"),
                _row("potential_entrant", "CRM intelligence vendor"),
            ],
            summary="Structured live inference from sanitized frozen evidence only.",
            unknowns=["No live market freshness check was performed."],
        )
    )

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "fake-live",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=_gate2(),
        execute_live=True,
        client_factory=lambda **_: client,
    )

    assert evidence.status == "pass"
    assert evidence.credential_present is True
    assert evidence.live_call_attempted is True
    assert evidence.live_call_succeeded is True
    assert evidence.call_count == 1
    assert evidence.result is not None
    assert {row.category for row in evidence.result.competitors} == {
        "direct",
        "indirect",
        "substitute",
        "do_nothing",
        "potential_entrant",
    }
    assert client.parse_calls == 1
    request = client.requests[0]
    assert request["text_format"] is OpenAICompetitorSynthesis
    assert request["store"] is False
    assert request["max_output_tokens"] == 1200
    assert cast(dict[str, object], request["metadata"]) == {
        "case_id": _CASE_ID,
        "run_id": _RUN_ID,
        "schema_version": "openai_competitor_smoke_evidence@1",
        "inference_label": "live_inference",
        "research_label": "not_live_web_research",
    }
    payload = str(request["input"])
    assert "bounded sanitized StartupProfile" in str(request["instructions"])
    assert "%PDF" not in payload
    assert "pitch.pdf" not in payload
    assert str(tmp_path) not in payload
    assert "present-for-fake-client" not in payload
    assert "prompt" not in payload.lower()
    assert "raw_pdf" not in payload.lower()
    assert "document_text" not in payload.lower()
    assert evidence.privacy == {
        "request_payload_checked": True,
        "response_payload_checked": True,
        "unsafe_payload_rejected": True,
        "privacy_leak_count": 0,
    }
    assert evidence.lineage == {
        "source": "injected_test_evidence",
        "case_id": _CASE_ID,
        "run_id": _RUN_ID,
        "gate2_decision": "approved",
        "profile_hash": _PROFILE_HASH,
    }
    assert len(evidence.source_summary_hashes) == len(_competitor_evidence())
    assert all(value.startswith("sha256:") for value in evidence.source_summary_hashes)
    assert evidence.budget["max_usd"] == "0.25"
    assert Decimal(evidence.budget["worst_case_usd"]) <= Decimal("0.25")
    assert Decimal(evidence.budget["reserved_usd"]) <= Decimal("0.25")
    assert evidence.usage == {
        "input_tokens": 400,
        "output_tokens": 180,
        "total_tokens": 580,
    }
    assert evidence.cost_evidence == {
        "currency": "USD",
        "pricing_model": "gpt-5.6-luna",
        "calculation": "estimated_from_observed_usage",
        "input_usd_per_million_tokens": "1.00",
        "output_usd_per_million_tokens": "6.00",
        "actual_or_estimated_usd": "0.001480",
    }
    persisted = json.loads(
        (tmp_path / "fake-live" / "openai-competitor-smoke-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["cost_evidence"] == evidence.cost_evidence
    timeout = cast(float, request["timeout"])
    assert timeout <= 20.0
    assert evidence.transport == {"timeout_seconds": "20.0", "max_retries": "0"}


def test_openai_competitor_smoke_rejects_unsafe_payload_before_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        FrozenCompetitorEvidence,
        validate_openai_competitor_payload_privacy,
        run_queue5_openai_competitor_smoke,
    )

    unsafe = {
        "source_summary": "%PDF pitch.pdf C:\\secret\\founder@example.com raw document text",
        "prompt": "summarize this deck",
    }
    with pytest.raises(ValueError, match="^openai_competitor_payload_privacy_rejected$"):
        validate_openai_competitor_payload_privacy(unsafe)

    monkeypatch.setenv("OPENAI_API_KEY", "present")
    factory = ExplodingOpenAIClientFactory()
    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "unsafe",
        startup_profile=_profile(),
        competitor_evidence=(
            FrozenCompetitorEvidence(
                category="direct",
                label="Unsafe Inc",
                evidence_ref="fixture:unsafe",
                source_summary="%PDF pitch.pdf local path C:\\secret",
                confidence=Decimal("0.10"),
            ),
        ),
        gate2_evidence=_gate2(),
        execute_live=True,
        client_factory=factory,
    )

    assert evidence.status == "blocked_privacy_validation"
    assert evidence.live_call_attempted is False
    assert evidence.fail_reasons == ("privacy_validation_failed",)
    assert factory.created == 0


def test_openai_competitor_smoke_outage_returns_partial_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "present-for-failing-client")
    client = FailingOpenAIClient()

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "outage",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=_gate2(),
        execute_live=True,
        client_factory=lambda **_: client,
    )

    assert evidence.status == "partial_fallback"
    assert evidence.live_call_attempted is True
    assert evidence.live_call_succeeded is False
    assert evidence.call_count == 1
    assert evidence.result is None
    assert evidence.error_code == "provider_error"
    assert evidence.fail_reasons == ("provider_error",)
    assert client.parse_calls == 1
    assert "private exporter failure" not in json.dumps(evidence.to_json_dict())


def test_openai_competitor_smoke_truncated_structured_output_is_parse_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "present-for-truncated-json")
    client = TruncatedStructuredOutputClient()

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "truncated",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=_gate2(),
        execute_live=True,
        client_factory=lambda **_: client,
    )

    assert evidence.status == "partial_fallback"
    assert evidence.live_call_attempted is True
    assert evidence.error_code == "parse_error"
    assert evidence.fail_reasons == ("parse_error",)
    assert client.parse_calls == 1
    serialized = json.dumps(evidence.to_json_dict())
    assert "truncated-json" not in serialized


def test_openai_competitor_smoke_rejects_structured_output_missing_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "present-for-invalid-output")
    client = RecordingOpenAIClient(
        {
            "competitors": [
                _row("direct", "workflow diligence suites").model_dump(mode="json"),
                _row("indirect", "spreadsheet analyst workflow").model_dump(mode="json"),
                _row("substitute", "consultant-led diligence").model_dump(mode="json"),
                _row("do_nothing", "manual memo process").model_dump(mode="json"),
            ],
            "summary": "Missing a potential entrant category.",
            "unknowns": [],
        }
    )

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "missing-category",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=_gate2(),
        execute_live=True,
        client_factory=lambda **_: client,
    )

    assert evidence.status == "partial_fallback"
    assert evidence.result is None
    assert evidence.call_count == 1
    assert evidence.error_code == "parse_error"
    assert evidence.fail_reasons == ("parse_error",)


def test_openai_competitor_smoke_rejects_output_evidence_refs_outside_frozen_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        OpenAICompetitorSynthesis,
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "present-for-rogue-ref")
    client = RecordingOpenAIClient(
        OpenAICompetitorSynthesis(
            competitors=[
                _row("direct", "workflow diligence suites"),
                _row("indirect", "spreadsheet analyst workflow"),
                _row("substitute", "consultant-led diligence"),
                _row("do_nothing", "manual memo process"),
                _row("potential_entrant", "CRM intelligence vendor", evidence_ref="live:web"),
            ],
            summary="Structured live inference from sanitized frozen evidence only.",
            unknowns=[],
        )
    )

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "rogue-ref",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=_gate2(),
        execute_live=True,
        client_factory=lambda **_: client,
    )

    assert evidence.status == "partial_fallback"
    assert evidence.result is None
    assert evidence.call_count == 1
    assert evidence.error_code == "response_validation_error"
    assert evidence.fail_reasons == ("response_validation_error",)


def test_openai_competitor_smoke_client_init_failure_makes_zero_sdk_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "present-for-client-init-failure")

    def fail_client_init(**_: object) -> object:
        raise RuntimeError("private client init failure C:\\secret\\pitch.pdf")

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "client-init-failure",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=_gate2(),
        execute_live=True,
        client_factory=fail_client_init,
    )

    assert evidence.status == "partial_fallback"
    assert evidence.live_call_attempted is False
    assert evidence.call_count == 0
    assert evidence.error_code == "client_init_error"
    assert evidence.fail_reasons == ("client_init_error",)
    assert "private client init failure" not in json.dumps(evidence.to_json_dict())


def test_openai_competitor_smoke_output_privacy_failure_is_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        OpenAICompetitorSynthesis,
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "present-for-output-privacy")
    client = RecordingOpenAIClient(
        OpenAICompetitorSynthesis(
            competitors=[
                _row("direct", "workflow diligence suites"),
                _row("indirect", "spreadsheet analyst workflow"),
                _row("substitute", "consultant-led diligence"),
                _row("do_nothing", "manual memo process"),
                _row("potential_entrant", "CRM intelligence vendor"),
            ],
            summary="Unsafe prompt text must not enter evidence.",
            unknowns=[],
        )
    )

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "output-privacy",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=_gate2(),
        execute_live=True,
        client_factory=lambda **_: client,
    )

    assert evidence.status == "partial_fallback"
    assert evidence.live_call_attempted is True
    assert evidence.call_count == 1
    assert evidence.error_code == "output_privacy_rejected"
    assert evidence.fail_reasons == ("output_privacy_rejected",)
    assert "Unsafe prompt" not in json.dumps(evidence.to_json_dict())


def test_openai_competitor_smoke_key_without_execute_is_armed_no_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "present-but-armed-only")
    factory = ExplodingOpenAIClientFactory()

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "armed",
        startup_profile=_profile(),
        competitor_evidence=_competitor_evidence(),
        gate2_evidence=_gate2(),
        execute_live=False,
        client_factory=factory,
    )

    assert evidence.status == "armed_not_executed"
    assert evidence.credential_present is True
    assert evidence.live_call_attempted is False
    assert evidence.call_count == 0
    assert factory.created == 0


def test_openai_competitor_smoke_default_anchors_gate2_to_real_frozen_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import due_diligence_agent.evals.openai_competitor_smoke as smoke
    from due_diligence_agent.evals.openai_competitor_smoke import (
        run_queue5_openai_competitor_smoke,
    )

    monkeypatch.setitem(smoke._OpenAICompetitorSettings.model_config, "env_file", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_STARTUP_API_KEY", raising=False)

    evidence = run_queue5_openai_competitor_smoke(
        tmp_path / "default-real-workflow",
        execute_live=False,
        client_factory=ExplodingOpenAIClientFactory(),
    )

    assert evidence.status == "skipped_missing_credential"
    assert evidence.gate2.status == "approved"
    assert evidence.gate2.decision == "approved"
    assert evidence.lineage["source"] == "deterministic_startup_composer"
    assert evidence.lineage["fixture_case"] == "startup_synthetic_v1/saas"
    assert evidence.lineage["profile_hash"] == evidence.gate2.profile_hash
    assert evidence.lineage["market_source_mode"] == "frozen"
    assert evidence.lineage["market_snapshot_hash"].startswith("sha256:")
    assert evidence.lineage["market_competitor_categories"] == (
        "direct,do_nothing,indirect,potential_entrant,substitute"
    )
    assert evidence.startup_profile.startup_name == "MISSING"
    assert (
        evidence.startup_profile.one_line_description
        == "SaaS case: backlog automation for finance teams."
    )
    assert evidence.source_summary_hashes
    serialized = json.dumps(evidence.to_json_dict(), sort_keys=True)
    assert "%PDF" not in serialized
    assert "pitch.pdf" not in serialized
    assert "DiligenceFlow" not in serialized
    assert str(tmp_path) not in serialized


def test_openai_competitor_smoke_rejects_output_collision_before_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.openai_competitor_smoke import (
        run_queue5_openai_competitor_smoke,
    )

    output_dir = tmp_path / "occupied"
    output_dir.mkdir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    factory = ExplodingOpenAIClientFactory()

    with pytest.raises(ValueError, match="^evaluation_output_dir_not_empty$"):
        run_queue5_openai_competitor_smoke(
            output_dir,
            startup_profile=_profile(),
            competitor_evidence=_competitor_evidence(),
            gate2_evidence=_gate2(),
            execute_live=True,
            client_factory=factory,
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert factory.created == 0


def test_openai_competitor_smoke_script_defaults_safe_and_forwards_live_switch(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the OpenAI smoke contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_queue5_openai_competitor_smoke.ps1"
    capture_path = tmp_path / "capture.json"
    fake_uv = tmp_path / "fake-uv.ps1"
    fake_uv.write_text(
        "\n".join(
            [
                "$payload = @{ args = $args; env = @{",
                "  LANGSMITH_TRACING = $env:LANGSMITH_TRACING",
                "  OPENAI_API_KEY_PRESENT = [bool]$env:OPENAI_API_KEY",
                "  OPENAI_STARTUP_API_KEY_PRESENT = [bool]$env:OPENAI_STARTUP_API_KEY",
                "  UV_OFFLINE = $env:UV_OFFLINE",
                "} }",
                f"$payload | ConvertTo-Json -Depth 4 | Set-Content -Path '{capture_path}' -Encoding UTF8",
                "exit 43",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "openai-output"
    process_env = os.environ.copy()
    process_env["OPENAI_API_KEY"] = "must-not-be-printed"
    process_env["LANGSMITH_API_KEY"] = "caller-langsmith-key"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OutputDir",
            str(output_dir),
            "-ExecuteLive",
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
    assert "must-not-be-printed" not in result.stdout
    assert "must-not-be-printed" not in result.stderr
    assert "caller-langsmith-key" not in result.stdout
    assert "caller-langsmith-key" not in result.stderr
    captured = json.loads(capture_path.read_text(encoding="utf-8-sig"))
    assert captured["args"][-6:] == [
        "python",
        "-m",
        "due_diligence_agent.evals.openai_competitor_smoke",
        "--output-dir",
        str(output_dir),
        "--execute-live",
    ]
    assert captured["env"] == {
        "LANGSMITH_TRACING": "false",
        "OPENAI_API_KEY_PRESENT": True,
        "OPENAI_STARTUP_API_KEY_PRESENT": False,
        "UV_OFFLINE": "true",
    }


_CASE_ID = "00000000-0000-0000-0000-000000000951"
_RUN_ID = "queue5-openai-competitor-run-951"
_PROFILE_HASH = "sha256:" + "a" * 64


def _profile() -> SanitizedStartupProfile:
    from due_diligence_agent.evals.openai_competitor_smoke import SanitizedStartupProfile

    return SanitizedStartupProfile(
        startup_name="DiligenceFlow",
        one_line_description="AI-assisted investment due diligence workspace",
        problem="Investment teams lose time reconciling startup evidence.",
        solution="A controlled workflow converts approved evidence into diligence reports.",
        business_model="B2B SaaS",
        icp="Seed and Series A investment teams",
        geography="United States",
        stage="pilot-ready",
        profile_hash=_PROFILE_HASH,
    )


def _gate2() -> Gate2Evidence:
    from due_diligence_agent.evals.openai_competitor_smoke import Gate2Evidence

    return Gate2Evidence(
        case_id=_CASE_ID,
        run_id=_RUN_ID,
        status="approved",
        decision="approved",
        destination="openai.responses",
        profile_hash=_PROFILE_HASH,
    )


def _competitor_evidence() -> tuple[FrozenCompetitorEvidence, ...]:
    from due_diligence_agent.evals.openai_competitor_smoke import FrozenCompetitorEvidence

    return (
        FrozenCompetitorEvidence(
            category="direct",
            label="Workflow diligence suites",
            evidence_ref="fixture:market:direct",
            source_summary="Frozen source summary names workflow tools for diligence teams.",
            confidence=Decimal("0.71"),
        ),
        FrozenCompetitorEvidence(
            category="indirect",
            label="Spreadsheet analyst workflow",
            evidence_ref="fixture:market:indirect",
            source_summary="Frozen source summary describes spreadsheet-led analyst process.",
            confidence=Decimal("0.62"),
        ),
        FrozenCompetitorEvidence(
            category="substitute",
            label="Consultant-led diligence",
            evidence_ref="fixture:market:substitute",
            source_summary="Frozen source summary describes outsourced diligence projects.",
            confidence=Decimal("0.58"),
        ),
        FrozenCompetitorEvidence(
            category="do_nothing",
            label="Manual memo process",
            evidence_ref="fixture:market:do_nothing",
            source_summary="Frozen source summary describes not adopting new tooling.",
            confidence=Decimal("0.53"),
        ),
        FrozenCompetitorEvidence(
            category="potential_entrant",
            label="CRM intelligence vendor",
            evidence_ref="fixture:market:potential_entrant",
            source_summary="Frozen source summary describes adjacent CRM intelligence products.",
            confidence=Decimal("0.49"),
        ),
    )


def _row(
    category: str,
    name: str,
    *,
    evidence_ref: str | None = None,
) -> OpenAICompetitorRow:
    from due_diligence_agent.evals.openai_competitor_smoke import OpenAICompetitorRow

    return OpenAICompetitorRow.model_validate(
        {
            "category": category,
            "name": name,
            "icp_overlap": "medium",
            "differentiation": "Different workflow depth and evidence controls.",
            "risk": "May compete for analyst attention.",
            "confidence": 0.6,
            "evidence_refs": [evidence_ref or f"fixture:market:{category}"],
            "unknowns": ["Current live positioning was not checked."],
        }
    )


class ExplodingOpenAIClientFactory:
    def __init__(self) -> None:
        self.created = 0

    def __call__(self, **_: object) -> object:
        self.created += 1
        raise AssertionError("OpenAI client must not be constructed")


class RecordingOpenAIClient:
    def __init__(self, parsed: object) -> None:
        self.responses = self
        self.parsed = parsed
        self.requests: list[dict[str, object]] = []
        self.parse_calls = 0

    def parse(self, **kwargs: object) -> object:
        self.parse_calls += 1
        self.requests.append(kwargs)
        return _FakeOpenAIResponse(self.parsed)


class FailingOpenAIClient:
    def __init__(self) -> None:
        self.responses = self
        self.parse_calls = 0

    def parse(self, **kwargs: object) -> object:
        del kwargs
        self.parse_calls += 1
        raise RuntimeError("private exporter failure C:\\secret\\pitch.pdf")


class TruncatedStructuredOutputClient:
    def __init__(self) -> None:
        self.responses = self
        self.parse_calls = 0

    def parse(self, **kwargs: object) -> object:
        from due_diligence_agent.evals.openai_competitor_smoke import OpenAICompetitorSynthesis

        del kwargs
        self.parse_calls += 1
        return OpenAICompetitorSynthesis.model_validate_json('{"competitors": "')


class _FakeOpenAIResponse:
    def __init__(self, parsed: object) -> None:
        self.output_parsed = parsed
        self.usage = _FakeOpenAIUsage()


class _FakeOpenAIUsage:
    input_tokens = 400
    output_tokens = 180
    total_tokens = 580
