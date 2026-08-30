from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any, cast

import pytest

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.evals import startup_frozen_runtime
from due_diligence_agent.evals.startup_frozen_runtime import (
    StartupFrozenRuntimeResult,
    run_startup_frozen_runtime_eval,
)


FIXTURE_ROOT = Path("tests/fixtures/startup_synthetic_v1")


@pytest.mark.parametrize(
    ("contract_break", "expected_error"),
    [
        ("case_sha256", "startup_fixture_sha256_mismatch"),
        ("expected_contracts_sha256", "startup_fixture_sha256_mismatch"),
        ("missing_case_file", "startup_fixture_file_missing"),
        ("declared_bytes", "startup_fixture_bytes_mismatch"),
        ("unlisted_case_file", "startup_fixture_case_inventory_mismatch"),
        ("nested_unlisted_case_file", "startup_fixture_case_inventory_mismatch"),
        ("expected_contracts_semantics", "startup_fixture_expected_contracts_invalid"),
        ("unsafe_case_name", "startup_fixture_case_name_invalid"),
        ("cross_case_path", "startup_fixture_case_path_invalid"),
        ("total_byte_cap_before_read", "startup_fixture_total_bytes_exceeded"),
        ("unsafe_path", "startup_fixture_path_unsafe"),
        ("network_policy", "startup_fixture_policy_invalid"),
        ("privacy_policy", "startup_fixture_policy_invalid"),
        ("total_byte_cap", "startup_fixture_total_bytes_exceeded"),
    ],
)
def test_startup_frozen_runtime_validates_fixture_contract_before_analysis_or_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contract_break: str,
    expected_error: str,
) -> None:
    fixture_root = tmp_path / "startup_synthetic_v1"
    shutil.copytree(FIXTURE_ROOT, fixture_root)
    _normalize_fixture_checkout_line_endings(fixture_root)
    unreadable_before_validation = _break_fixture_contract(fixture_root, contract_break)
    output_dir = tmp_path / "runtime-output"
    analysis_calls = 0

    def analysis_must_not_run(**_kwargs: object) -> tuple[()]:
        nonlocal analysis_calls
        analysis_calls += 1
        return ()

    monkeypatch.setattr(
        startup_frozen_runtime,
        "STARTUP_SYNTHETIC_FIXTURE_ROOT",
        fixture_root,
    )
    monkeypatch.setattr(startup_frozen_runtime, "_run_all_cases", analysis_must_not_run)
    if unreadable_before_validation is not None:
        original_open = Path.open
        guarded_path = unreadable_before_validation.resolve()

        def guarded_open(active_path: Path, *args: Any, **kwargs: Any) -> Any:
            if active_path.resolve() == guarded_path:
                raise AssertionError("fixture payload opened before stat/cap validation")
            return original_open(active_path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", guarded_open)

    with pytest.raises(ValueError) as exc_info:
        run_startup_frozen_runtime_eval(
            "startup_synthetic_v1",
            output_dir=output_dir,
            repeat_determinism=False,
        )

    assert str(exc_info.value) == expected_error
    assert analysis_calls == 0
    assert not output_dir.exists()


def _normalize_fixture_checkout_line_endings(fixture_root: Path) -> None:
    for path in fixture_root.rglob("*"):
        if path.is_file() and path.suffix in {".csv", ".json", ".txt"}:
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def _break_fixture_contract(fixture_root: Path, contract_break: str) -> Path | None:
    manifest_path = fixture_root / "manifest.json"
    manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    cases = cast(dict[str, Any], manifest["cases"])
    saas_files = cast(dict[str, Any], cases["saas"]["files"])
    case_entry = cast(dict[str, Any], saas_files["cases/saas/metrics.csv"])
    guarded_path: Path | None = None

    if contract_break == "case_sha256":
        case_path = fixture_root / str(case_entry["path"])
        payload = case_path.read_bytes()
        case_path.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    elif contract_break == "expected_contracts_sha256":
        expected_contracts = cast(dict[str, Any], manifest["expected_contracts"])
        expected_contracts["sha256"] = "0" * 64
    elif contract_break == "missing_case_file":
        (fixture_root / str(case_entry["path"])).unlink()
    elif contract_break == "declared_bytes":
        case_entry["bytes"] = int(case_entry["bytes"]) + 1
        guarded_path = fixture_root / str(case_entry["path"])
    elif contract_break == "unlisted_case_file":
        (fixture_root / "cases" / "saas" / "unlisted.txt").write_text(
            "synthetic unlisted input",
            encoding="utf-8",
        )
        guarded_path = None
    elif contract_break == "nested_unlisted_case_file":
        nested_path = fixture_root / "cases" / "saas" / "nested" / "unlisted.txt"
        nested_path.parent.mkdir()
        nested_path.write_text("synthetic nested input", encoding="utf-8")
        guarded_path = None
    elif contract_break == "expected_contracts_semantics":
        expected_entry = cast(dict[str, Any], manifest["expected_contracts"])
        expected_path = fixture_root / str(expected_entry["path"])
        expected_contracts = cast(
            dict[str, Any],
            json.loads(expected_path.read_text(encoding="utf-8")),
        )
        expected_cases = cast(dict[str, Any], expected_contracts["cases"])
        cast(dict[str, Any], expected_cases["saas"]).pop("expected_metric_pack")
        expected_payload = json.dumps(
            expected_contracts,
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8")
        expected_path.write_bytes(expected_payload)
        expected_entry["bytes"] = len(expected_payload)
        expected_entry["sha256"] = sha256(expected_payload).hexdigest()
        guarded_path = None
    elif contract_break == "unsafe_case_name":
        cases["../saas"] = cases.pop("saas")
        guarded_path = None
    elif contract_break == "cross_case_path":
        marketplace_path = fixture_root / "cases" / "marketplace" / "metrics.csv"
        marketplace_payload = marketplace_path.read_bytes()
        case_entry["path"] = "cases/marketplace/metrics.csv"
        case_entry["bytes"] = len(marketplace_payload)
        case_entry["sha256"] = sha256(marketplace_payload).hexdigest()
        guarded_path = None
    elif contract_break == "total_byte_cap_before_read":
        oversized_path = fixture_root / "cases" / "saas" / "oversized.bin"
        oversized_payload = b"x" * 100_001
        oversized_path.write_bytes(oversized_payload)
        saas_files["cases/saas/oversized.bin"] = {
            "path": "cases/saas/oversized.bin",
            "sha256": sha256(oversized_payload).hexdigest(),
            "bytes": len(oversized_payload),
            "format": "binary",
        }
        guarded_path = oversized_path
    elif contract_break == "unsafe_path":
        case_entry["path"] = "../outside.csv"
        guarded_path = None
    elif contract_break == "network_policy":
        manifest["network_policy"] = "external_network_allowed"
        guarded_path = None
    elif contract_break == "privacy_policy":
        manifest["privacy_policy"] = "may_contain_private_data"
        guarded_path = None
    elif contract_break == "total_byte_cap":
        manifest["max_total_fixture_bytes"] = 1
        guarded_path = None
    else:
        raise AssertionError(f"unknown fixture break: {contract_break}")

    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return guarded_path


def test_persisted_semantic_canonicalization_ignores_runtime_document_block_numbering() -> None:
    first = {
        "rows": [
            ["document_text_block_001", f"text_hash={'a' * 64}"],
            ["document_text_block_002", f"text_hash={'b' * 64}"],
        ]
    }
    repeated = {
        "rows": [
            ["document_text_block_001", f"text_hash={'b' * 64}"],
            ["document_text_block_002", f"text_hash={'a' * 64}"],
        ]
    }

    assert startup_frozen_runtime._canonicalize_persisted_semantics(
        first
    ) == startup_frozen_runtime._canonicalize_persisted_semantics(repeated)


def test_persisted_semantic_canonicalization_treats_disclosure_fragment_refs_as_a_set() -> None:
    first = {
        "disclosure_snapshot": {
            "destination": "openai.responses",
            "content_hash": "a" * 64,
            "minimized_fragment_refs": ["fragment-b", "fragment-a"],
        }
    }
    repeated = {
        "disclosure_snapshot": {
            "destination": "openai.responses",
            "content_hash": "b" * 64,
            "minimized_fragment_refs": ["fragment-a", "fragment-b"],
        }
    }

    assert startup_frozen_runtime._canonicalize_persisted_semantics(
        first
    ) == startup_frozen_runtime._canonicalize_persisted_semantics(repeated)


def test_startup_frozen_runtime_eval_executes_real_api_flow_for_every_synthetic_case(
    tmp_path: Path,
) -> None:
    result = run_startup_frozen_runtime_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path / "eval",
        repeat_determinism=True,
    )

    assert result.dataset == "startup_synthetic_v1"
    assert result.queue2_assertion_provenance == "runtime_api:startup_synthetic_v1"
    assert result.queue2_runtime_passed is True
    assert result.fail_reasons == ()
    assert result.case_count == 4
    assert result.privacy_leak_count == 0
    assert result.denied_gate2_external_calls == 0
    assert result.queue2_assertions["profile_determinism"] is True
    assert result.queue2_assertions["readiness_scored"] is True
    assert result.queue2_assertions["persisted_hash_determinism"] is True
    assert result.queue2_assertions["formula_source_coverage"] is True
    assert result.queue2_assertions["per_case_contradictions_and_unsupported"] is True
    assert result.queue2_assertions["competitor_sources_resolved"] is True
    assert result.queue2_assertions["privacy_scan_ok"] is True
    assert result.queue2_assertions["trace_sections_ok"] is True
    assert result.queue2_assertions["report_sections_ok"] is True
    max_questions = result.queue2_assertions["max_questions"]
    assert isinstance(max_questions, int)
    assert max_questions <= 3

    case_names = {case.case_name for case in result.cases}
    assert case_names == {"marketplace", "pre_revenue_service", "saas", "transactional"}
    for case in result.cases:
        assert case.fail_reasons == ()
        assert case.evidence_source == "runtime_api"
        assert case.uploaded_document_count >= 1
        assert case.report_json_status == 200
        assert case.report_html_status == 200
        assert case.report_pdf_status == 200
        assert case.gate4_status == "completed"
        assert case.runtime_trace_event_count >= 10
        assert case.semantic_fingerprint_match is True
        assert case.persisted_hash_fingerprint_match is True
        assert case.report_hash.startswith("sha256:")
        assert case.readiness_snapshot_hash.startswith("sha256:")
        assert case.market_research_snapshot_hash.startswith("sha256:")
        assert case.metric_pack_hash.startswith("sha256:")
        assert case.metric_formula_source_count >= 1
        assert case.contradiction_count >= 1
        assert case.unsupported_claim_count >= 1
        assert case.competitor_count >= 1
        assert case.source_appendix_hash_count >= case.competitor_source_ref_count
        assert case.competitor_sources_resolved is True
        assert case.competitor_sources_with_as_of == case.competitor_source_ref_count
        assert case.privacy_leak_count == 0

    artifact_path = Path(result.artifact_paths["runtime_evidence"])
    assert artifact_path.is_file()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["queue2_assertion_provenance"] == "runtime_api:startup_synthetic_v1"
    assert artifact["cases"][0]["evidence_source"] == "runtime_api"
    assert "expected_contracts.json" not in artifact_path.read_text(encoding="utf-8")


def test_startup_frozen_runtime_eval_fails_closed_when_trace_ids_are_missing(
    tmp_path: Path,
) -> None:
    result = run_startup_frozen_runtime_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path / "eval",
        repeat_determinism=False,
    )

    if any("report_trace_ids_missing" in reason for case in result.cases for reason in case.fail_reasons):
        assert result.queue2_runtime_passed is False
        assert result.queue2_assertions["trace_sections_ok"] is False
        assert "trace_sections_failed" in result.fail_reasons


def test_startup_frozen_runtime_allows_public_report_json_without_trace_ids_or_report_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_json = {
        "case_id": "case-public-json",
        "sections": {
            section_name: {"rows": []}
            for section_name in startup_frozen_runtime.REQUIRED_REPORT_SECTIONS
        },
    }
    report_json["sections"]["metrics"] = {
        "rows": [
            [
                "arr",
                "120000",
                "USD/year",
                "2026",
                "arr@1",
                "calculation_ref=calc-001",
            ]
        ]
    }
    report_json["sections"]["source_appendix"] = {
        "rows": [["source-1", "sha256:" + "f" * 64]]
    }
    snapshot_hash = "sha256:" + "a" * 64
    readiness_hash = "sha256:" + "b" * 64
    market_hash = "sha256:" + "c" * 64
    metric_pack_hash = "sha256:" + "d" * 64
    runtime = _minimal_runtime_payload(
        readiness_hash=readiness_hash,
        market_hash=market_hash,
        metric_pack_hash=metric_pack_hash,
    )

    monkeypatch.setattr(startup_frozen_runtime, "_multipart_files", lambda _case_dir: [])
    monkeypatch.setattr(startup_frozen_runtime, "_read_runtime_payload", lambda *_args: runtime)
    monkeypatch.setattr(startup_frozen_runtime, "_trace_event_count", lambda *_args: 1)
    monkeypatch.setattr(startup_frozen_runtime, "_audit_text", lambda *_args: "")

    case = startup_frozen_runtime._run_case(
        client=_PublicJsonClient(report_json=report_json, snapshot_hash=snapshot_hash),
        coordinator=object(),  # type: ignore[arg-type]
        fixture_root=tmp_path,
        runtime_root=tmp_path,
        case_name="saas",
    )

    assert "report_trace_ids_missing" not in case.fail_reasons
    assert "trace_to_report_lineage_missing" not in case.fail_reasons
    assert case.report_hash == snapshot_hash
    assert case.trace_to_report_lineage is True


def test_startup_frozen_runtime_eval_fails_closed_when_dataset_is_not_supported(
    tmp_path: Path,
) -> None:
    try:
        run_startup_frozen_runtime_eval("startup_founder_frozen_v1", output_dir=tmp_path / "eval")
    except ValueError as exc:
        assert str(exc) == "unsupported_dataset:startup_founder_frozen_v1"
    else:
        raise AssertionError("unsupported datasets must not produce fixture-derived evidence")


def test_runtime_evidence_artifact_does_not_persist_absolute_output_path(tmp_path: Path) -> None:
    artifact_path = tmp_path / "nested" / "runtime-evidence.json"
    artifact_path.parent.mkdir()
    result = StartupFrozenRuntimeResult(
        schema_version="startup_frozen_runtime_result@1",
        dataset="startup_synthetic_v1",
        queue2_runtime_passed=True,
        queue2_assertion_provenance="runtime_api:startup_synthetic_v1",
        case_count=0,
        privacy_leak_count=0,
        denied_gate2_external_calls=0,
        queue2_assertions={},
        artifact_paths={"runtime_evidence": str(artifact_path.resolve())},
    )

    startup_frozen_runtime._write_result(artifact_path, result)

    persisted = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert persisted["artifact_paths"] == {"runtime_evidence": "runtime-evidence.json"}
    assert startup_frozen_runtime._privacy_leak_count(artifact_path.read_text(encoding="utf-8")) == 0


def test_metric_formula_source_coverage_counts_only_requested_metrics_with_valid_lineage() -> None:
    rows = [
        [
            "arr",
            "120000",
            "USD/year",
            "2026",
            "arr@1",
            "calculation_ref=calc-001",
        ],
        [
            "gross_margin",
            "blocked",
            "input.missing:revenue",
            "dimension_ref=dimension-001",
        ],
        [
            "unrequested_metric",
            "10",
            "ratio",
            "2026",
            "unrequested_metric@1",
            "evidence_ref=evidence-001",
        ],
        ["mrr", "blocked", "input.missing:monthly_recurring_revenue"],
    ]

    assert startup_frozen_runtime._metric_formula_source_count(
        rows,
        metric_ids=("arr", "gross_margin", "mrr"),
    ) == 2


def test_persisted_semantic_fingerprint_ignores_only_run_identity_not_material_content() -> None:
    fingerprint = getattr(
        startup_frozen_runtime,
        "_persisted_semantic_fingerprint",
        lambda **_kwargs: "missing",
    )
    first_report = {
        "case_id": "11111111-1111-4111-8111-111111111111",
        "report_id": "22222222-2222-4222-8222-222222222222",
        "report_hash": "sha256:" + "a" * 64,
        "as_of": "2026-08-13T12:00:00Z",
        "trace_ids": [
            "33333333-3333-4333-8333-333333333333",
            "startup-metrics-111aaa222bbb",
        ],
        "reproducibility": {"configuration_hash": "sha256:" + "9" * 64},
        "sections": {
            "metrics": {
                "status": "PARTIAL",
                "rows": [
                    [
                        "arr",
                        "120000",
                        "USD/year",
                        "2026",
                        "arr@1",
                        "calculation_ref=44444444-4444-4444-8444-444444444444",
                        "supporting_hash=sha256:" + "7" * 64,
                    ]
                ],
            },
            "methodology": {
                "rows": [
                    ["profile_hash", "sha256:" + "3" * 64],
                    ["readiness_metric_pack", "sha256:" + "4" * 64],
                ]
            },
            "source_appendix": {
                "rows": [["source_ref", "sha256:" + "9" * 64]]
            },
        },
    }
    repeated_report = {
        **first_report,
        "case_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "report_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "report_hash": "sha256:" + "b" * 64,
        "as_of": "2026-08-13T12:00:05Z",
        "trace_ids": [
            "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            "startup-metrics-999ccc888ddd",
        ],
        "reproducibility": {"configuration_hash": "sha256:" + "8" * 64},
        "sections": {
            "metrics": {
                "status": "PARTIAL",
                "rows": [
                    [
                        "arr",
                        "120000",
                        "USD/year",
                        "2026",
                        "arr@1",
                        "calculation_ref=dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                        "supporting_hash=" + "0" * 64,
                    ]
                ],
            },
            "methodology": {
                "rows": [
                    ["profile_hash", "sha256:" + "5" * 64],
                    ["readiness_metric_pack", "sha256:" + "6" * 64],
                ]
            },
            "source_appendix": {
                "rows": [["source_ref", "sha256:" + "1" * 64]]
            },
        },
    }
    first_runtime = {
        "profile_hash": "sha256:" + "c" * 64,
        "startup_readiness_artifact": {
            "snapshot": {
                "built_at": "2026-08-13T12:00:00Z",
                "snapshot_hash": "sha256:" + "d" * 64,
                "metric_pack": {
                    "pack_hash": "sha256:" + "e" * 64,
                    "metric_ids": ["arr"],
                    "dimensions": [
                        {
                            "dimension_id": "55555555-5555-4555-8555-555555555555",
                            "metric_id": "arr",
                            "status": "ready",
                            "reason_code": "calculation.available:arr",
                        }
                    ],
                },
            }
        },
        "node_results": [
            {
                "node_name": "metrics",
                "status": "success",
                "attempt_count": 1,
                "retry_count": 0,
                "data_refs": ["55555555-5555-4555-8555-555555555555"],
                "errors": [],
                "warnings": [],
            }
        ],
    }
    repeated_runtime = json.loads(json.dumps(first_runtime))
    repeated_runtime["profile_hash"] = "sha256:" + "f" * 64
    repeated_runtime["startup_readiness_artifact"]["snapshot"]["built_at"] = (
        "2026-08-13T12:00:05Z"
    )
    repeated_runtime["startup_readiness_artifact"]["snapshot"]["snapshot_hash"] = (
        "sha256:" + "1" * 64
    )
    repeated_runtime["startup_readiness_artifact"]["snapshot"]["metric_pack"]["pack_hash"] = (
        "sha256:" + "2" * 64
    )
    repeated_runtime["startup_readiness_artifact"]["snapshot"]["metric_pack"]["dimensions"][
        0
    ]["dimension_id"] = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    repeated_runtime["node_results"][0]["data_refs"] = [
        "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    ]
    changed_report = json.loads(json.dumps(repeated_report))
    changed_report["sections"]["metrics"]["rows"][0][4] = "arr@2"

    first = fingerprint(report_json=first_report, runtime=first_runtime)
    repeated = fingerprint(report_json=repeated_report, runtime=repeated_runtime)
    changed = fingerprint(report_json=changed_report, runtime=repeated_runtime)

    assert first == repeated
    assert first != changed


def test_persisted_semantic_fingerprint_ignores_independent_node_result_order_only() -> None:
    fingerprint = getattr(
        startup_frozen_runtime,
        "_persisted_semantic_fingerprint",
        lambda **_kwargs: "missing",
    )
    report = {"sections": {}, "as_of": "2026-08-13T12:00:00Z"}
    runtime = {
        "node_results": [
            {
                "node_name": "metrics",
                "status": "success",
                "attempt_count": 1,
                "retry_count": 0,
                "errors": [],
                "warnings": [],
            },
            {
                "node_name": "market_research",
                "status": "success",
                "attempt_count": 1,
                "retry_count": 0,
                "errors": [],
                "warnings": [],
            },
        ],
    }
    reordered_runtime = {
        **runtime,
        "node_results": list(reversed(runtime["node_results"])),
    }
    changed_runtime = json.loads(json.dumps(reordered_runtime))
    changed_runtime["node_results"][0]["status"] = "failed"
    changed_runtime["node_results"][0]["errors"] = ["tool_timeout"]

    assert fingerprint(report_json=report, runtime=runtime) == fingerprint(
        report_json=report,
        runtime=reordered_runtime,
    )
    assert fingerprint(report_json=report, runtime=runtime) != fingerprint(
        report_json=report,
        runtime=changed_runtime,
    )


def test_persisted_semantic_fingerprint_treats_disclosure_sets_as_order_independent() -> None:
    fingerprint = getattr(
        startup_frozen_runtime,
        "_persisted_semantic_fingerprint",
        lambda **_kwargs: "missing",
    )
    report = {"sections": {}, "as_of": "2026-08-13T12:00:00Z"}
    runtime = {
        "disclosure_scope": {
            "payload": {
                "allowed_classes": [
                    "metrics.revenue",
                    "market.positioning",
                    "product.workflow",
                ],
                "redaction_policy_versions": ["rules-redactor@1", "pii-redactor@2"],
            },
        },
        "disclosure_snapshot": {
            "payload": {
                "detected_classes": [
                    "product.workflow",
                    "market.positioning",
                    "metrics.revenue",
                ],
            },
        },
    }
    reordered_runtime = json.loads(json.dumps(runtime))
    reordered_runtime["disclosure_scope"]["payload"]["allowed_classes"] = list(
        reversed(runtime["disclosure_scope"]["payload"]["allowed_classes"])
    )
    reordered_runtime["disclosure_snapshot"]["payload"]["detected_classes"] = list(
        reversed(runtime["disclosure_snapshot"]["payload"]["detected_classes"])
    )
    reordered_runtime["disclosure_scope"]["payload"]["redaction_policy_versions"] = list(
        reversed(runtime["disclosure_scope"]["payload"]["redaction_policy_versions"])
    )
    changed_runtime = json.loads(json.dumps(reordered_runtime))
    changed_runtime["disclosure_snapshot"]["payload"]["detected_classes"] = [
        "product.workflow",
        "market.positioning",
        "metrics.cost",
    ]

    assert fingerprint(report_json=report, runtime=runtime) == fingerprint(
        report_json=report,
        runtime=reordered_runtime,
    )
    assert fingerprint(report_json=report, runtime=runtime) != fingerprint(
        report_json=report,
        runtime=changed_runtime,
    )


def test_privacy_scan_does_not_treat_local_risk_gap_as_an_api_key() -> None:
    assert startup_frozen_runtime._privacy_leak_count("local-finding-risk-gap") == 0
    assert startup_frozen_runtime._privacy_leak_count("token=sk-proj-" + "a" * 32) == 1


def test_runtime_eval_coordinator_uses_live_and_deterministic_audit_spools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CoordinatorProbe:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(
        startup_frozen_runtime,
        "StartupCaseCoordinator",
        CoordinatorProbe,
    )
    monkeypatch.setattr(
        getattr(startup_frozen_runtime, "container"),
        "build_startup_analysis_composer",
        lambda _data_dir: object(),
    )
    monkeypatch.setattr(
        getattr(startup_frozen_runtime, "container"),
        "build_deterministic_startup_analysis_composer",
        lambda _data_dir, *, inbox_root: object(),
    )
    monkeypatch.setattr(
        getattr(startup_frozen_runtime, "container"),
        "build_startup_report_port",
        lambda _data_dir: object(),
    )
    monkeypatch.setattr(
        getattr(startup_frozen_runtime, "container"),
        "build_startup_profile_query_port",
        lambda _data_dir: object(),
    )
    monkeypatch.setattr(
        getattr(startup_frozen_runtime, "container"),
        "build_startup_case_revision_port",
        lambda _data_dir: object(),
    )
    monkeypatch.setattr(
        startup_frozen_runtime,
        "SQLiteStartupWorkflowRuntimeStore",
        lambda _path: object(),
    )

    coordinator = startup_frozen_runtime._build_runtime_coordinator(
        Path("runtime-eval-coordinator-contract")
    )
    coordinator_kwargs = cast(Any, coordinator).kwargs

    assert isinstance(coordinator_kwargs["audit_spool"], JsonlAuditSpool)
    assert isinstance(coordinator_kwargs["deterministic_audit_spool"], JsonlAuditSpool)
    assert coordinator_kwargs["audit_spool"] is not coordinator_kwargs["deterministic_audit_spool"]


class _Response:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload, sort_keys=True)

    def json(self) -> dict[str, Any]:
        return self._payload


class _PublicJsonClient:
    def __init__(self, *, report_json: dict[str, Any], snapshot_hash: str) -> None:
        self.report_json = report_json
        self.snapshot_hash = snapshot_hash
        self.case_id = "case-public-json"

    def post(self, url: str, **_kwargs: object) -> _Response:
        if url == "/api/v1/startup/cases":
            return _Response(201, {"case_id": self.case_id})
        if url.endswith("/documents"):
            return _Response(200, {"accepted_document_ids": ["doc-0001"]})
        if url.endswith("/gate2/decision"):
            return _Response(200, {})
        if url.endswith("/gate3/decision"):
            return _Response(
                200,
                {"snapshot_hash": self.snapshot_hash, "snapshot_revision": 1},
            )
        if url.endswith("/gate4/decision"):
            return _Response(200, {"gate4_status": "completed"})
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url: str, **_kwargs: object) -> _Response:
        if url.endswith("/gate2/preview"):
            return _Response(200, {"resume_token": "resume-token"})
        if url.endswith("/report/json"):
            return _Response(200, self.report_json)
        if url.endswith("/report/html"):
            return _Response(200, {"html": "<main>public founder report</main>"})
        if url.endswith("/report/pdf"):
            return _Response(200, {"pdf": "%PDF-1.4"})
        if url.endswith(f"/cases/{self.case_id}"):
            return _Response(
                200,
                {
                    "provider_status": "available",
                    "gate2_status": "approved",
                    "gate3_status": "approved",
                    "gate4_status": "completed",
                    "report_status": "approved",
                    "snapshot_hash": self.snapshot_hash,
                },
            )
        raise AssertionError(f"unexpected GET {url}")


def _minimal_runtime_payload(
    *,
    readiness_hash: str,
    market_hash: str,
    metric_pack_hash: str,
) -> dict[str, Any]:
    return {
        "provider_status": "available",
        "profile_hash": "sha256:" + "e" * 64,
        "report_readiness_snapshot_hash": readiness_hash,
        "report_market_research_snapshot_hash": market_hash,
        "startup_readiness_artifact": {
            "snapshot": {
                "snapshot_hash": readiness_hash,
                "metric_pack": {
                    "pack_hash": metric_pack_hash,
                    "metric_ids": ["arr"],
                    "adaptive_questions": [{"question_code": "pricing"}],
                },
            }
        },
        "startup_market_research_artifact": {
            "snapshot": {
                "snapshot_hash": market_hash,
                "competitors": [{"category": "direct", "source_ids": ["source-1"]}],
                "sources": [
                    {
                        "source_id": "source-1",
                        "source_hash": "sha256:" + "f" * 64,
                        "as_of": "2026-08-13",
                    }
                ],
            }
        },
        "contradiction_ids": ["contradiction-1"],
        "claim_status_by_id": {"claim-1": "unsupported"},
        "node_results": [
            {
                "node_name": node_name,
                "status": "success",
                "attempt_count": 1,
                "retry_count": 0,
                "errors": [],
                "warnings": [],
            }
            for node_name in startup_frozen_runtime.REQUIRED_RUNTIME_NODES
        ],
    }
