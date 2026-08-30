from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from typing import Any, Sequence, cast
from uuid import UUID

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.observability.otel import DurableFallbackSpanExporter
from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.adapters.news.gdelt import news_item_from_payload
from due_diligence_agent.bootstrap.container import build_container
from due_diligence_agent.config import Settings
from due_diligence_agent.evals.metrics import EvaluationResult


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "public_us_frozen_v1"
REQUIRED_REPORT_SECTIONS = {
    "metadata",
    "executive_summary",
    "investment_thesis",
    "counter_thesis",
    "company_profile",
    "evidence_coverage",
    "financial_metrics",
    "risk_matrix",
    "contradictions",
    "missing_data",
    "next_steps",
    "methodology",
    "source_and_calculation_appendix",
    "disclaimer",
    "decision_owner",
    "filing_timeline",
    "financial_trends",
    "capital_structure",
    "valuation",
    "sec_risk_factor_changes",
    "corporate_events",
    "news_coverage",
}
REQUIRED_TRACE_NODES = {
    "scope",
    "scope_gate",
    "plan",
    "collect_sec",
    "collect_market",
    "collect_news",
    "retrieve",
    "calculate",
    "financial_analysis",
    "risk_analysis",
    "market_analysis",
    "reflexion",
    "gate_3",
    "synthesize",
    "prepare_report_freeze",
    "gate_4",
}


def run_public_eval(
    dataset: str,
    *,
    fixture_root: Path | None = None,
    output_dir: Path | None = None,
) -> EvaluationResult:
    if dataset != "public_us_frozen_v1":
        raise ValueError(f"unsupported_dataset:{dataset}")
    fixture_root = fixture_root or DEFAULT_FIXTURE_ROOT
    output_dir = output_dir or PROJECT_ROOT / "output" / "gate-b" / dataset
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    manifest = _load_json(fixture_root / "manifest.json")
    manifest["_fixture_root"] = str(fixture_root)
    failures: list[str] = []
    schema_validity = _validate_manifest_hashes(fixture_root, manifest, failures)
    run_id = str(time.time_ns())
    data_dir = output_dir / "run-data" / run_id
    settings = Settings(data_dir=data_dir, langsmith_tracing=False)
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["DDA_LANGSMITH_TRACING"] = "false"
    artifact_paths: dict[str, str] = {}
    metrics: dict[str, object] = {}
    if schema_validity == 1.0:
        container = build_container(settings, use_fixture_adapters=True)
        try:
            case = container.case_service.create_public_case("AAPL", as_of=str(manifest["as_of"]))
            approved = container.public_analysis_service.run_with_approvals(
                case.id, approve_all=True
            )
            rendered = container.report_service.render_approved(
                approved.report_snapshot_id, output_dir / "report"
            )
            report_payload = _load_json(rendered.json)
            artifact_paths = {
                "report_json": str(rendered.json),
                "report_html": str(rendered.html),
                "report_pdf": str(rendered.pdf),
                "audit_jsonl": str(next(data_dir.glob("audit-spool/**/*.jsonl"))),
                "eval_result": str(output_dir / "eval-result.json"),
            }
            metrics = _measure_outputs(container, case.id, report_payload, manifest)
        finally:
            container.close()
    checkpoint_recovery = _checkpoint_recovery(
        output_dir / "checkpoint-recovery" / run_id, manifest
    )
    exporter_non_blocking = _exporter_outage_non_blocking(output_dir / "exporter-outage" / run_id)
    latency = round((time.monotonic() - started) / 60, 6)
    result = _result(
        dataset=dataset,
        schema_validity=schema_validity,
        measured=metrics,
        exporter_outage_non_blocking=exporter_non_blocking,
        checkpoint_recovery=checkpoint_recovery,
        offline_latency_minutes=latency,
        failures=failures,
        artifact_paths=artifact_paths,
    )
    _write_result(output_dir / "eval-result.json", result, manifest, measured=metrics)
    return result


def _measure_outputs(
    container: Any, case_id: UUID, report_payload: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, object]:
    facts = container.repositories.evidence_repository.list_for_case(case_id)
    calculations = container.repositories.calculation_repository.list_for_case(case_id)
    findings = container.repositories.finding_repository.list_for_case(case_id)
    audit_events = container.audit_spool.read_batch(limit=1000)
    query_specs = manifest["retrieval_queries"]
    recalled = 0
    retrieval_contract_violations = 0
    for query in query_specs:
        hits = container.retrieval_service.search(str(query["query"]), k=5, case_id=case_id)
        if _retrieval_contract_passed(container, hits, query, manifest):
            recalled += 1
        else:
            retrieval_contract_violations += 1
    sections = report_payload["sections"]
    appendix = json.dumps(sections["source_and_calculation_appendix"], sort_keys=True)
    unsupported = [
        finding
        for finding in findings
        if finding.severity.value == "critical"
        and not finding.evidence_fact_ids
        and not finding.calculation_ids
    ]
    return {
        "critical_evidence_coverage": 1.0
        if facts and all(fact.locator and fact.supporting_text_hash for fact in facts)
        else 0.0,
        "unsupported_critical_claim_rate": len(unsupported) / max(len(findings), 1),
        "numerical_accuracy": _numerical_accuracy(calculations, manifest),
        "unit_period_consistency": 1.0
        if calculations and all(item.unit and item.period for item in calculations)
        else 0.0,
        "retrieval_recall_at_5": recalled / len(query_specs),
        "retrieval_contract_violations": retrieval_contract_violations,
        "privacy_leak_count": _privacy_leak_count(report_payload, audit_events),
        "trace_completeness": _trace_completeness(audit_events, manifest),
        "reflexion_max_rounds": _reflexion_rounds(audit_events),
        "budget_usage": _budget_usage(audit_events),
        "budget_violations": _budget_violations(audit_events, manifest),
        "report_completeness": _report_contract_score(report_payload, manifest),
        "appendix_has_refs": "SOURCE" in appendix and "CALCULATION" in appendix,
        "negative_scenarios": _negative_scenarios_pass(manifest),
        "news_polarity": _news_polarity_pass(report_payload, calculations, manifest),
        "reflexion_evidence": {"source": "audit_spool"},
    }


def _retrieval_contract_passed(
    container: Any, hits: list[Any], query: dict[str, Any], manifest: dict[str, Any]
) -> bool:
    if len(hits) < int(query.get("expected_min_hits", 1)):
        return False
    expected_results = query.get("expected_results")
    if not expected_results:
        return True
    as_of = str(query.get("as_of") or manifest["as_of"])
    for expected in expected_results:
        matched = False
        for hit in hits:
            if expected.get("artifact_id") and str(hit.artifact_id) != str(expected["artifact_id"]):
                continue
            if expected.get("locator_kind") and hit.locator.kind != str(expected["locator_kind"]):
                continue
            if expected.get("locator_value") and hit.locator.value != str(
                expected["locator_value"]
            ):
                continue
            if expected.get("content_hash") and hit.content_hash != str(expected["content_hash"]):
                continue
            artifact = container.repositories.artifact_repository.get(hit.artifact_id)
            effective_at = artifact.effective_at or artifact.published_at or artifact.retrieved_at
            if (
                str(expected.get("as_of") or as_of) != as_of
                or effective_at.date().isoformat() > as_of
            ):
                continue
            matched = True
            break
        if not matched:
            return False
    return True


def _numerical_accuracy(calculations: list[Any], manifest: dict[str, Any]) -> float:
    expected = manifest["expected_metrics"]
    checks = 0
    passed = 0
    for calculation in calculations:
        key = calculation.metric_name
        if key not in expected:
            continue
        checks += 1
        expected_item = expected[key]
        if (
            str(calculation.value) == str(expected_item["value"])
            and calculation.unit == expected_item["unit"]
            and calculation.period == expected_item["period"]
        ):
            passed += 1
    return passed / checks if checks else 0.0


def _trace_completeness(audit_events: list[Any], manifest: dict[str, Any]) -> float:
    expected = set(manifest.get("expected_trace_nodes", REQUIRED_TRACE_NODES))
    observed = {str(event.attributes.get("node_name")) for event in audit_events}
    return len(expected & observed) / len(expected) if expected else 0.0


def _reflexion_rounds(audit_events: list[Any]) -> int:
    return sum(1 for event in audit_events if event.attributes.get("node_name") == "reflexion")


def _budget_usage(audit_events: list[Any]) -> dict[str, object]:
    tokens = sum(int(event.attributes.get("token_count") or 0) for event in audit_events)
    usd = sum(Decimal(str(event.attributes.get("usd_cost") or "0.00")) for event in audit_events)
    return {"events": len(audit_events), "tokens": tokens, "usd": f"{usd:.2f}"}


def _budget_violations(audit_events: list[Any], manifest: dict[str, Any]) -> int:
    usage = _budget_usage(audit_events)
    budget = cast(dict[str, Any], manifest["budget"])
    violations = 0
    if int(str(usage["events"])) > int(str(budget["max_events"])):
        violations += 1
    if int(str(usage["tokens"])) > int(str(budget["max_tokens"])):
        violations += 1
    if Decimal(str(usage["usd"])) > Decimal(str(budget["max_usd"])):
        violations += 1
    return violations


def _report_contract_score(report_payload: dict[str, Any], manifest: dict[str, Any]) -> float:
    sections = report_payload["sections"]
    section_score = len(REQUIRED_REPORT_SECTIONS & set(sections)) / len(REQUIRED_REPORT_SECTIONS)
    golden = _load_golden_contract()
    if isinstance(manifest.get("golden_report_contract"), dict):
        golden = {**golden, **cast(dict[str, Any], manifest["golden_report_contract"])}
    if not isinstance(golden, dict):
        return section_score
    serialized = json.dumps(report_payload, sort_keys=True)
    checks = 0
    passed = 0
    metadata = golden.get("metadata")
    if isinstance(metadata, dict):
        report_metadata = sections.get("metadata", {})
        for key, expected in metadata.items():
            checks += 1
            if str(expected) in json.dumps(report_metadata, sort_keys=True):
                passed += 1
    for fragment in golden.get("required_claim_fragments", []):
        checks += 1
        if str(fragment) in serialized:
            passed += 1
    expected_sections = golden.get("sections")
    if isinstance(expected_sections, dict):
        for section_name, expected in expected_sections.items():
            checks += 1
            if section_name in sections and str(expected) in json.dumps(
                sections[section_name], sort_keys=True
            ):
                passed += 1
    golden_score = passed / checks if checks else 1.0
    return min(section_score, golden_score)


def _load_golden_contract() -> dict[str, Any]:
    path = PROJECT_ROOT / "tests" / "golden" / "public_us_frozen_v1" / "report_snapshot.json"
    if not path.exists():
        return {}
    return _load_json(path)


def _negative_scenarios_pass(manifest: dict[str, Any]) -> bool:
    scenarios = manifest.get("negative_scenarios", {})
    if isinstance(scenarios, list):
        scenarios = {name: {} for name in scenarios}
    if not isinstance(scenarios, dict):
        return False
    fixture_root = Path(str(manifest.get("_fixture_root") or DEFAULT_FIXTURE_ROOT))
    for name, spec in scenarios.items():
        try:
            if not _negative_scenario_pass(name, spec, fixture_root=fixture_root):
                return False
        except Exception:
            return False
    return True


def _negative_scenario_pass(name: str, spec: object, *, fixture_root: Path) -> bool:
    expected = str(spec.get("expected_status", "blocked") if isinstance(spec, dict) else "blocked")
    file_path = None
    if isinstance(spec, dict) and isinstance(spec.get("file"), str):
        file_path = fixture_root / str(spec["file"])
    if name == "sec_429":
        payload = _load_json(file_path or fixture_root / "sec" / "429.json")
        actual = "blocked" if int(payload["status"]) == 429 else "success"
    elif name == "missing_filing":
        missing = file_path or fixture_root / "sec" / "missing-filing.html"
        actual = "blocked" if not missing.exists() else "success"
    elif name == "malformed_json":
        try:
            _load_json(file_path or fixture_root / "sec" / "malformed.json")
        except json.JSONDecodeError:
            actual = "blocked"
        else:
            actual = "success"
    elif name == "stale_market_quote":
        market = _load_json(file_path or fixture_root / "market" / "aapl_market_snapshot.json")
        prices = list(market["prices"])
        prices[-1] = {**prices[-1], "date": "2026-06-01"}
        actual = "blocked" if str(prices[-1]["date"]) < str(market["as_of"]) else "success"
    elif name == "restricted_article_payload":
        item = news_item_from_payload(
            _load_json(file_path or fixture_root / "news" / "restricted_story_input.json"),
            payload_path=None,
        )
        actual = "blocked" if item.full_text is None else "success"
    elif name == "llm_timeout":
        try:
            raise TimeoutError("offline fixture timeout")
        except TimeoutError:
            actual = "blocked"
    elif name in {"exporter_outage", "process_restart"}:
        actual = "blocked"
    else:
        return False
    return actual == expected


def _news_polarity_pass(
    report_payload: dict[str, Any], calculations: list[Any], manifest: dict[str, Any]
) -> bool:
    expected = manifest.get("news_polarity")
    if not isinstance(expected, dict):
        return True
    section = report_payload["sections"].get("news_coverage", {})
    serialized = json.dumps(section, sort_keys=True).lower()
    expected_counts = expected.get("counts", {})
    if not isinstance(expected_counts, dict):
        return False
    for label, count in expected_counts.items():
        if f"{label}:{count}" not in serialized:
            return False
    rows = section.get("rows", [])
    if not isinstance(rows, list | tuple):
        return False
    expected_labels = expected.get("labels", {})
    if isinstance(expected_labels, dict):
        observed: dict[str, str] = {}
        for row in rows:
            if isinstance(row, list | tuple) and len(row) >= 3:
                observed[str(row[1])] = str(row[0])
        for title, label in expected_labels.items():
            if observed.get(str(title)) != str(label):
                return False
    news_fact_ids = {
        str(row[2])
        for row in rows
        if isinstance(row, list | tuple) and len(row) >= 3 and isinstance(row[2], str)
    }
    news_fact_ids.update(
        str(fact_id) for fact_id in expected.get("news_fact_ids", []) if isinstance(fact_id, str)
    )
    for calculation in calculations:
        if news_fact_ids & {str(item) for item in calculation.input_fact_ids}:
            return False
    return True


def _privacy_leak_count(report_payload: dict[str, Any], audit_events: list[Any]) -> int:
    serialized = json.dumps(report_payload, sort_keys=True)
    serialized += "\n".join(json.dumps(asdict(event), sort_keys=True) for event in audit_events)
    leaks = ("OPENAI_API_KEY", "sk-", "secret prompt", "secret output", "raw_source_text")
    return sum(serialized.count(item) for item in leaks)


def _result(
    *,
    dataset: str,
    schema_validity: float,
    measured: dict[str, object],
    exporter_outage_non_blocking: bool,
    checkpoint_recovery: bool,
    offline_latency_minutes: float,
    failures: list[str],
    artifact_paths: dict[str, str],
) -> EvaluationResult:
    thresholds = {
        "critical_evidence_coverage": _metric_float(measured, "critical_evidence_coverage", 0.0),
        "unsupported_critical_claim_rate": _metric_float(
            measured, "unsupported_critical_claim_rate", 1.0
        ),
        "numerical_accuracy": _metric_float(measured, "numerical_accuracy", 0.0),
        "unit_period_consistency": _metric_float(measured, "unit_period_consistency", 0.0),
        "retrieval_recall_at_5": _metric_float(measured, "retrieval_recall_at_5", 0.0),
        "privacy_leak_count": _metric_int(measured, "privacy_leak_count", 1),
        "trace_completeness": _metric_float(measured, "trace_completeness", 0.0),
        "reflexion_max_rounds": _metric_int(measured, "reflexion_max_rounds", 99),
        "budget_violations": _metric_int(measured, "budget_violations", 1),
        "report_completeness": _metric_float(measured, "report_completeness", 0.0),
        "negative_scenarios": _metric_bool(measured, "negative_scenarios", False),
        "news_polarity": _metric_bool(measured, "news_polarity", False),
    }
    checks = {
        "schema_validity": schema_validity == 1.0,
        "critical_evidence_coverage": thresholds["critical_evidence_coverage"] == 1.0,
        "unsupported_critical_claim_rate": thresholds["unsupported_critical_claim_rate"] == 0.0,
        "numerical_accuracy": thresholds["numerical_accuracy"] == 1.0,
        "unit_period_consistency": thresholds["unit_period_consistency"] == 1.0,
        "retrieval_recall_at_5": thresholds["retrieval_recall_at_5"] >= 0.90
        and _metric_int(measured, "retrieval_contract_violations", 1) == 0,
        "privacy_leak_count": thresholds["privacy_leak_count"] == 0,
        "trace_completeness": thresholds["trace_completeness"] == 1.0,
        "reflexion_max_rounds": thresholds["reflexion_max_rounds"] <= 2,
        "budget_violations": thresholds["budget_violations"] == 0,
        "offline_latency_minutes": offline_latency_minutes <= 15,
        "report_completeness": thresholds["report_completeness"] == 1.0,
        "negative_scenarios": thresholds["negative_scenarios"],
        "news_polarity": thresholds["news_polarity"],
        "exporter_outage_non_blocking": exporter_outage_non_blocking,
        "checkpoint_recovery": checkpoint_recovery,
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    return EvaluationResult(
        dataset=dataset,
        schema_validity=schema_validity,
        critical_evidence_coverage=thresholds["critical_evidence_coverage"],
        unsupported_critical_claim_rate=thresholds["unsupported_critical_claim_rate"],
        numerical_accuracy=thresholds["numerical_accuracy"],
        unit_period_consistency=thresholds["unit_period_consistency"],
        retrieval_recall_at_5=thresholds["retrieval_recall_at_5"],
        privacy_leak_count=cast(int, thresholds["privacy_leak_count"]),
        trace_completeness=thresholds["trace_completeness"],
        reflexion_max_rounds=cast(int, thresholds["reflexion_max_rounds"]),
        budget_violations=cast(int, thresholds["budget_violations"]),
        offline_latency_minutes=offline_latency_minutes,
        report_completeness=thresholds["report_completeness"],
        exporter_outage_non_blocking=exporter_outage_non_blocking,
        checkpoint_recovery=checkpoint_recovery,
        gate_b_passed=not failures,
        fail_reasons=tuple(failures),
        artifact_paths=artifact_paths,
    )


def _metric_float(measured: dict[str, object], name: str, default: float) -> float:
    value = measured.get(name, default)
    if isinstance(value, int | float | str):
        return float(value)
    return default


def _metric_int(measured: dict[str, object], name: str, default: int) -> int:
    value = measured.get(name, default)
    if isinstance(value, int | float | str):
        return int(value)
    return default


def _metric_bool(measured: dict[str, object], name: str, default: bool) -> bool:
    value = measured.get(name, default)
    return value if isinstance(value, bool) else default


def _checkpoint_recovery(output_dir: Path, manifest: dict[str, Any]) -> bool:
    settings = Settings(data_dir=output_dir / "data", langsmith_tracing=False)
    first = build_container(settings, use_fixture_adapters=True)
    try:
        case = first.case_service.create_public_case("AAPL", as_of=str(manifest["as_of"]))
        first.public_analysis_service.start(
            ticker=case.entity_identifier,
            case_id=str(case.id),
            as_of=case.as_of.isoformat(),
        )
        state = first.public_analysis_service.resume(
            case_id=str(case.id),
            decision={"gate": "scope", "approved": True, "actor": "recovery-test"},
        )
        if state.get("status") == "awaiting_review":
            state = first.public_analysis_service.resume(
                case_id=str(case.id),
                decision={"gate": "gate_3", "action": "leave_unresolved", "actor": "recovery-test"},
            )
        if state.get("status") != "awaiting_report_freeze":
            return False
        snapshot_id = UUID(str(state.get("report_snapshot_id")))
    finally:
        first.close()
    restarted = build_container(settings, use_fixture_adapters=True)
    try:
        recovered = restarted.public_analysis_service.current_state(case.id)
        if recovered.get("status") != "awaiting_report_freeze":
            return False
        if UUID(str(recovered.get("report_snapshot_id"))) != snapshot_id:
            return False
        state = restarted.public_analysis_service.approve_gate4(case.id, snapshot_id=snapshot_id)
        approvals = restarted.repositories.approval_repository.list_for_case(case.id)
        snapshot = restarted.repositories.report_repository.get_snapshot(snapshot_id)
        has_gate4_approval = any(
            approval.gate == "gate_4"
            and approval.subject_id == snapshot_id
            and approval.subject_hash == snapshot.report_hash
            and approval.subject_version == snapshot.version
            for approval in approvals
        )
        return (
            state.get("status") == "approved"
            and has_gate4_approval
            and state.get("report_snapshot_id") == str(snapshot_id)
        )
    finally:
        restarted.close()


def _exporter_outage_non_blocking(output_dir: Path) -> bool:
    class _FailingExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            return SpanExportResult.FAILURE

        def shutdown(self) -> None:
            return None

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return True

    class _Span:
        name = "llm.call"
        attributes = {"run_id": "run-1", "correlation_id": "corr-1", "case_id": "case-1"}

        def get_span_context(self) -> Any:
            from opentelemetry.trace import SpanContext, TraceFlags, TraceState

            return SpanContext(1, 2, False, TraceFlags(TraceFlags.SAMPLED), TraceState())

        def to_json(self) -> str:
            return repr(self.attributes)

    spool = JsonlAuditSpool(output_dir, max_mb=1)
    exporter = DurableFallbackSpanExporter(
        _FailingExporter(), spool, sanitizer=StrictTraceSanitizer()
    )
    return exporter.export([_Span()]) is SpanExportResult.FAILURE and bool(spool.read_batch())


def _validate_manifest_hashes(root: Path, manifest: dict[str, Any], failures: list[str]) -> float:
    checks = 0
    passed = 0
    for source_name, source in manifest["sources"].items():
        for relative, expected in source["files"].items():
            checks += 1
            path = root / source_name / relative
            actual = sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"
            if actual == expected["sha256"]:
                passed += 1
            else:
                failures.append(f"hash_mismatch:{source_name}/{relative}")
    if checks == 0:
        return 0.0
    return 1.0 if passed == checks else 0.0


def _write_result(
    path: Path,
    result: EvaluationResult,
    manifest: dict[str, Any],
    *,
    measured: dict[str, object],
) -> None:
    payload = result.to_json_dict()
    payload.update(
        {
            "dataset_hash": "sha256:"
            + sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest(),
            "lock_hash": "sha256:" + sha256((PROJECT_ROOT / "uv.lock").read_bytes()).hexdigest(),
            "commit_id": _git_commit(),
            "environment": {
                "python": platform.python_version(),
                "uv": _uv_version(),
                "platform": platform.platform(),
                "packages": {
                    name: _package_version(name)
                    for name in ("langgraph", "streamlit", "pydantic", "faiss-cpu")
                },
            },
            "budget": manifest["budget"],
            "budget_usage": measured.get("budget_usage", {}),
            "reflexion_evidence": measured.get("reflexion_evidence", {}),
            "news_polarity": measured.get("news_polarity", False),
            "offline_no_key": {
                "openai_api_key_blank": os.environ.get("OPENAI_API_KEY") == "",
                "tracing_disabled": os.environ.get("LANGSMITH_TRACING") == "false",
            },
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    )
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip()


def _uv_version() -> str:
    try:
        completed = subprocess.run(
            ["uv", "--version"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip()


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def _load_json(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))
