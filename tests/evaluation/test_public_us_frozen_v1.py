from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from due_diligence_agent.application.services.public_analysis_service import PublicAnalysisService
from due_diligence_agent.evals import runner as eval_runner
from due_diligence_agent.evals.runner import run_public_eval


def test_public_us_frozen_v1_meets_blocking_thresholds(tmp_path: Path) -> None:
    result = run_public_eval("public_us_frozen_v1", output_dir=tmp_path)

    assert result.schema_validity == 1.0
    assert result.critical_evidence_coverage == 1.0
    assert result.unsupported_critical_claim_rate == 0.0
    assert result.numerical_accuracy == 1.0
    assert result.unit_period_consistency == 1.0
    assert result.retrieval_recall_at_5 >= 0.90
    assert result.privacy_leak_count == 0
    assert result.trace_completeness == 1.0
    assert result.reflexion_max_rounds <= 2
    assert result.budget_violations == 0
    assert result.offline_latency_minutes <= 15
    assert result.report_completeness == 1.0
    assert result.exporter_outage_non_blocking is True
    assert result.checkpoint_recovery is True

    payload = json.loads((tmp_path / "eval-result.json").read_text(encoding="utf-8"))
    assert payload["dataset"] == "public_us_frozen_v1"
    assert payload["gate_b_passed"] is True
    assert payload["artifact_paths"]["report_json"].endswith(".report.json")
    assert payload["artifact_paths"]["audit_jsonl"]
    assert payload["offline_no_key"]["openai_api_key_blank"] is True
    assert payload["offline_no_key"]["tracing_disabled"] is True
    assert payload["budget_usage"] == {"events": 16, "tokens": 0, "usd": "0.00"}
    assert payload["reflexion_evidence"]["source"] == "audit_spool"
    assert payload["environment"]["uv"]
    assert payload["environment"]["packages"]["langgraph"]


def test_public_us_frozen_v1_rejects_manifest_tampering(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    source = Path("tests/fixtures/public_us_frozen_v1")
    _copy_tree(source, fixture_root)
    manifest_path = fixture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sources"]["sec"]["files"]["companyfacts.json"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    result = run_public_eval("public_us_frozen_v1", fixture_root=fixture_root, output_dir=tmp_path)

    assert result.schema_validity == 0.0
    assert result.gate_b_passed is False
    assert any("hash_mismatch" in reason for reason in result.fail_reasons)


def test_gate_b_rejects_retrieval_locator_contract_mismatch(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    _copy_tree(Path("tests/fixtures/public_us_frozen_v1"), fixture_root)
    manifest_path = fixture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["retrieval_queries"][0]["expected_results"] = [
        {
            "artifact_id": "00000000-0000-4000-8000-000000000000",
            "locator_kind": "sec_filing",
            "content_hash": "0" * 64,
            "as_of": manifest["as_of"],
        }
    ]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    result = run_public_eval("public_us_frozen_v1", fixture_root=fixture_root, output_dir=tmp_path)

    assert result.gate_b_passed is False
    assert "retrieval_recall_at_5" in result.fail_reasons


def test_gate_b_rejects_golden_report_contract_mismatch(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    _copy_tree(Path("tests/fixtures/public_us_frozen_v1"), fixture_root)
    manifest_path = fixture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["golden_report_contract"] = {
        "metadata": {"entity_name": "Wrong Company"},
        "required_claim_fragments": ["Wrong Company"],
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    result = run_public_eval("public_us_frozen_v1", fixture_root=fixture_root, output_dir=tmp_path)

    assert result.gate_b_passed is False
    assert "report_completeness" in result.fail_reasons


def test_gate_b_executes_negative_scenario_assertions(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    _copy_tree(Path("tests/fixtures/public_us_frozen_v1"), fixture_root)
    manifest_path = fixture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["negative_scenarios"] = {
        "sec_429": {"file": "sec/429.json", "expected_status": "success"}
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    result = run_public_eval("public_us_frozen_v1", fixture_root=fixture_root, output_dir=tmp_path)

    assert result.gate_b_passed is False
    assert "negative_scenarios" in result.fail_reasons


def test_gate_b_rejects_unexpected_negative_scenario_exception(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    _copy_tree(Path("tests/fixtures/public_us_frozen_v1"), fixture_root)
    malformed = fixture_root / "sec" / "429.json"
    malformed.write_text("{not-json", encoding="utf-8")
    manifest_path = fixture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sources"]["sec"]["files"]["429.json"]["sha256"] = _sha256(malformed)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    result = run_public_eval("public_us_frozen_v1", fixture_root=fixture_root, output_dir=tmp_path)

    assert result.schema_validity == 1.0
    assert result.gate_b_passed is False
    assert "negative_scenarios" in result.fail_reasons


@pytest.mark.parametrize(
    "scenario",
    [
        "sec_429",
        "missing_filing",
        "malformed_json",
        "stale_market_quote",
        "restricted_article_payload",
        "llm_timeout",
    ],
)
def test_gate_b_accepts_each_explicit_negative_scenario_contract(
    tmp_path: Path, scenario: str
) -> None:
    fixture_root = tmp_path / "fixture"
    _copy_tree(Path("tests/fixtures/public_us_frozen_v1"), fixture_root)
    manifest_path = fixture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["negative_scenarios"] = {scenario: manifest["negative_scenarios"][scenario]}
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    result = run_public_eval("public_us_frozen_v1", fixture_root=fixture_root, output_dir=tmp_path)

    assert result.gate_b_passed is True


def test_gate_b_uses_fixture_news_polarity_when_title_heuristic_conflicts(
    tmp_path: Path,
) -> None:
    new_title = "Apple expands supplier program with positive momentum"

    result = run_public_eval("public_us_frozen_v1", output_dir=tmp_path)

    report = json.loads(Path(result.artifact_paths["report_json"]).read_text(encoding="utf-8"))
    rows = report["sections"]["news_coverage"]["rows"]
    matches = [row for row in rows if row[1] == new_title]
    assert matches
    assert matches[0][0] == "negative"
    assert result.gate_b_passed is True


def test_checkpoint_recovery_resumes_without_direct_freeze_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = json.loads(Path("tests/fixtures/public_us_frozen_v1/manifest.json").read_text())
    manifest["_fixture_root"] = str(Path("tests/fixtures/public_us_frozen_v1"))

    def fail_direct_prepare(self: PublicAnalysisService, case_id: object) -> dict[str, object]:
        raise AssertionError("direct prepare_report_freeze is forbidden in recovery")

    monkeypatch.setattr(PublicAnalysisService, "prepare_report_freeze", fail_direct_prepare)

    assert eval_runner._checkpoint_recovery(tmp_path, manifest) is True


def _copy_tree(source: Path, target: Path) -> None:
    import shutil

    shutil.copytree(source, target)


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
