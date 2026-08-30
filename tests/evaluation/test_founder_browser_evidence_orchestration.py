from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REQUIRED_PDF_TRACE_NODES = (
    "disclosure",
    "document_intelligence",
    "gtm",
    "market_analysis",
    "market_research",
    "metrics",
    "primary_profile",
    "product_validation",
    "profile_enrichment",
    "critic",
    "arbiter",
    "report",
)
REPORT_SNAPSHOT_ID = "11111111-1111-4111-8111-111111111111"

CANONICAL_DESKTOP_STATE_SCREENSHOTS = (
    "01-start-dashboard.png",
    "02-data-room.png",
    "03-analysis-progress-gate2.png",
    "04-overview-readiness.png",
    "11-ai-advisor-next-question.png",
    "12-ai-advisor-answer.png",
    "13-ai-advisor-updated-analysis.png",
    "14-ai-advisor-improved-plan.png",
    "05-metrics-finance.png",
    "06-market-competitors.png",
    "07-risks-questions.png",
    "08-ai-action-plan.png",
    "09-report-center.png",
    "10-admin-observability-v2.png",
)


def _write_contract_fixture(path: Path) -> Path:
    path.write_bytes(b"fixture")
    return path


def test_cdp_capture_validate_only_accepts_canonical_desktop_14_state_suite(
    tmp_path: Path,
) -> None:
    """Regression: owner QA is the ordered 14-screen desktop journey, never mobile."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "capture_founder_screenshots.mjs"
    fixture = _write_contract_fixture(tmp_path / "founder.csv")
    result = subprocess.run(
        [
            node,
            str(script),
            "--validate-only=true",
            f"--browser={tmp_path / 'browser.exe'}",
            "--url=http://127.0.0.1:3000/",
            f"--desktop-states={tmp_path / 'desktop-states'}",
            f"--fixture={fixture}",
            f"--evidence={tmp_path / 'browser-evidence.json'}",
            "--require-desktop-state-suite=true",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "founder_14_desktop_states_contract_valid" in result.stdout
    assert "mobile" not in result.stdout.lower()
    assert ",".join(CANONICAL_DESKTOP_STATE_SCREENSHOTS) in result.stdout


def test_cdp_capture_validate_only_writes_desktop_14_state_manifest(
    tmp_path: Path,
) -> None:
    """Regression: visual QA consumes a desktop-only state manifest, not ad hoc files."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "capture_founder_screenshots.mjs"
    states_dir = tmp_path / "desktop-states"
    manifest_path = tmp_path / "desktop-state-manifest.json"
    fixture = _write_contract_fixture(tmp_path / "founder.csv")
    result = subprocess.run(
        [
            node,
            str(script),
            "--validate-only=true",
            f"--browser={tmp_path / 'browser.exe'}",
            "--url=http://127.0.0.1:3000/",
            f"--desktop-states={states_dir}",
            f"--desktop-state-manifest={manifest_path}",
            f"--fixture={fixture}",
            f"--evidence={tmp_path / 'browser-evidence.json'}",
            "--require-desktop-state-suite=true",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "founder_desktop_state_manifest@1"
    assert payload["viewport"] == {"width": 1440, "height": 1000}
    assert payload["order"] == list(CANONICAL_DESKTOP_STATE_SCREENSHOTS)
    assert [state["file"] for state in payload["states"]] == list(
        CANONICAL_DESKTOP_STATE_SCREENSHOTS
    )
    assert all(state["path"].startswith("desktop-states/") for state in payload["states"])
    assert "mobile" not in payload
    assert "founder_14_desktop_states_manifest_written" in result.stdout


@pytest.mark.skipif(
    os.name != "nt", reason="Windows file locks reproduce Crashpad cleanup failures"
)
def test_cdp_capture_profile_cleanup_preserves_primary_capture_error() -> None:
    """Regression: profile cleanup is best-effort and cannot mask capture failures."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    temp_root = repo_root / "artifacts" / "tmp" / "capture-cleanup-contract"
    temp_root.mkdir(parents=True, exist_ok=True)
    profile_dir = temp_root / "founder-screenshot-cdp-synthetic"
    child_env = {
        **os.environ,
        "TEMP": str(temp_root),
        "TMP": str(temp_root),
        "TMPDIR": str(temp_root),
    }
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ cleanupProfileDirectory }} from "{script}";'
                "try { throw new Error('primary_capture_failure'); } "
                "finally { cleanupProfileDirectory(process.argv[1], () => { "
                "const error = new Error('cleanup' + '_failed'); "
                "error.code = 'ENOTEMPTY'; "
                "throw error; "
                "}); }"
            ),
            str(profile_dir),
        ],
        cwd=repo_root,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "primary_capture_failure" in result.stderr
    assert "cleanup_failed" not in result.stderr


def test_cdp_capture_desktop_state_suite_uses_real_streamlit_admin_url() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    assert 'options["admin-url"] ?? "http://127.0.0.1:8501/"' in text
    assert "desktopStateSuiteAdminUrl" in text
    assert 'Page.navigate", { url: desktopStateSuiteAdminUrl }' in text
    assert re.search(
        r"const desktopSuiteCapture = await capture\([\s\S]*?desktopStatesPath,\s*adminUrl,",
        text,
    )
    assert 'new URL("/admin", url).href' not in text


def test_cdp_capture_desktop_state_suite_preserves_same_case_browser_evidence() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    assert "const desktopSuiteCapture = await capture(" in text
    assert "collectDesktopSuiteReportJourneyEvidence" in text
    assert "desktopSuiteCapture.journey.caseId" in text
    assert (
        "await writeBrowserEvidence(\n        evidencePath,\n        url,\n        desktopSuiteCapture,\n        undefined,"
        in text
    )
    assert "desktop_states" in text
    assert "CANONICAL_DESKTOP_STATE_SCREENSHOTS" in text


def test_cdp_capture_desktop_state_suite_summarizes_same_case_public_api() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    public_payload = {
        "profile": {
            "fields": {
                "startup_name": {"status": "source_fact", "values": ["NomadFlow AI"]},
                "traction": {"status": "contradiction", "values": ["29", "31"]},
            }
        },
        "gtm": {
            "dimensions": [
                {"key": "market_context", "market_source_ids": ["source-1"]},
                {"key": "sales_motion", "market_source_ids": []},
            ],
            "launch_plan": [
                {"experiment_codes": ["pricing", "channel"]},
                {"experiment_codes": ["retention"]},
            ],
        },
        "report": {
            "analytics": {
                "metric_points": [{"key": "mrr"}, {"key": "gross_margin"}],
                "market_points": [{"key": "sam"}],
                "readiness_dimensions": [
                    {"key": "metrics"},
                    {"key": "gtm"},
                ],
            },
            "main_sections": [
                {
                    "key": "market_size",
                    "summary_ru": "TAM / SAM / SOM требуют сверки.",
                    "known_facts_ru": [],
                    "blockers_ru": [],
                    "next_data_ru": [],
                },
                {
                    "key": "competitors",
                    "summary_ru": "direct indirect substitute",
                    "known_facts_ru": ["Конкурент A", "Конкурент B"],
                    "blockers_ru": [],
                    "next_data_ru": [],
                },
                {
                    "key": "diligence_questions",
                    "summary_ru": "",
                    "known_facts_ru": ["Вопрос 1", "Вопрос 2"],
                    "blockers_ru": [],
                    "next_data_ru": [],
                },
                {
                    "key": "action_plan",
                    "summary_ru": "",
                    "known_facts_ru": [],
                    "blockers_ru": [],
                    "next_data_ru": [],
                },
            ],
        },
    }
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                "import { buildDesktopSuitePublicApiPaths, "
                f'summarizeDesktopSuitePublicApiEvidence }} from "{script}";'
                f"const payload = {json.dumps(public_payload)};"
                "console.log(JSON.stringify({"
                "paths: buildDesktopSuitePublicApiPaths('case / 42'),"
                "summary: summarizeDesktopSuitePublicApiEvidence(payload)"
                "}));"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["paths"] == {
        "profile": "/api/startup/cases/case%20%2F%2042/profile",
        "gtm": "/api/startup/cases/case%20%2F%2042/gtm",
        "report": "/api/startup/cases/case%20%2F%2042/report/json",
    }
    assert observed["summary"] == {
        "actionPlanItems": 3,
        "chartCards": 3,
        "chartPoints": 5,
        "competitorCategories": 3,
        "competitorRows": 2,
        "diligenceQuestions": 2,
        "gtmDimensions": 2,
        "marketEvidenceFrozen": True,
        "marketUnknownsExplicit": True,
        "profileFields": 2,
        "readinessDimensions": 2,
    }


def test_cdp_capture_accepts_all_public_metric_provenance_statuses() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    report = _safe_founder_report()
    report["analytics"]["metric_points"] = [
        {
            "key": "monthly_recurring_revenue",
            "label_ru": "MRR",
            "value": 27_900_000,
            "unit": "KZT",
            "period_ru": "2026-06",
            "status": "calculated",
        },
        {
            "key": "gross_margin",
            "label_ru": "Валовая маржа",
            "value": 74,
            "unit": "%",
            "period_ru": None,
            "status": "contradiction",
        },
    ]
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ validateFounderSafeReportPayload }} from "{script}";'
                f"validateFounderSafeReportPayload({json.dumps(report)});"
                "console.log('valid');"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "valid"


def test_desktop_suite_aggregates_numeric_network_evidence_across_captures() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    assert "function aggregateCaptureEvidence(captures)" in text
    assert "browser_evidence_capture_stats_invalid" in text
    assert re.search(
        r"return \{\s*\.\.\.aggregateCaptureEvidence\(captures\),\s*captures,",
        text,
    )
    assert "const evidenceTotals = aggregateCaptureEvidence(" in text
    assert "network_external_calls: evidenceTotals.networkViolations" in text
    assert "browser_requests: evidenceTotals.observedRequests" in text
    assert "blocked_external_requests: evidenceTotals.blockedExternalRequests" in text
    assert "blocked_parser_injections: evidenceTotals.blockedParserInjections" in text


def test_desktop_suite_rejects_captured_state_vertical_overflow_with_diagnostics() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ assertDesktopStateCaptureFitsViewport }} from "{script}";'
                "try {"
                "assertDesktopStateCaptureFitsViewport('05-metrics-finance.png', {"
                "width: 1440, height: 1000, documentScrollHeight: 1003,"
                "bodyScrollHeight: 1002, documentScrollWidth: 1440,"
                "bodyScrollWidth: 1440, innerWidth: 1440, innerHeight: 1000"
                "});"
                "} catch (error) { console.error(error.message); process.exit(13); }"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 13
    assert "vertical_overflow" in result.stderr
    assert "state=05-metrics-finance.png" in result.stderr
    assert "documentScrollHeight=1003" in result.stderr
    assert "bodyScrollHeight=1002" in result.stderr


def test_desktop_suite_records_per_state_vertical_overflow_diagnostics() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    capture_state = text[text.index("async function captureDesktopState") :]

    assert "assertDesktopStateCaptureFitsViewport(file," in capture_state
    assert "documentScrollHeight" in capture_state
    assert "bodyScrollHeight" in capture_state
    assert "verticalOverflowPx" in capture_state
    assert "desktop_state_viewport_fits" in text


def test_cdp_capture_validate_only_accepts_browser_evidence_contract(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "capture_founder_screenshots.mjs"
    fixture = _write_contract_fixture(tmp_path / "founder.csv")
    result = subprocess.run(
        [
            node,
            str(script),
            "--validate-only=true",
            f"--browser={tmp_path / 'browser.exe'}",
            "--url=http://127.0.0.1:3000/",
            f"--desktop-states={tmp_path / 'desktop-states'}",
            f"--fixture={fixture}",
            f"--evidence={tmp_path / 'browser-evidence.json'}",
            "--require-desktop-state-suite=true",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "founder_browser_evidence_contract_valid" in result.stdout


def test_cdp_capture_validate_only_rejects_admin_trace_without_case_id(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "capture_founder_screenshots.mjs"
    admin_trace = tmp_path / "admin-trace.json"
    admin_trace.write_text(json.dumps(_safe_admin_trace()), encoding="utf-8")
    fixture = (
        repo_root / "tests" / "fixtures" / "startup_synthetic_v1" / "cases" / "saas" / "pitch.pdf"
    )
    result = subprocess.run(
        [
            node,
            str(script),
            "--validate-only=true",
            f"--browser={tmp_path / 'browser.exe'}",
            "--url=http://127.0.0.1:3000/",
            f"--desktop-states={tmp_path / 'desktop-states'}",
            f"--fixture={fixture}",
            f"--evidence={tmp_path / 'browser-evidence.json'}",
            "--require-desktop-state-suite=true",
            "--require-pdf-upload-journey=true",
            f"--admin-trace-json={admin_trace}",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "browser_evidence_admin_trace_case_required" in result.stderr


def test_cdp_capture_validate_only_accepts_pdf_journey_admin_trace_contract(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    admin_trace = tmp_path / "admin-trace.json"
    admin_trace.write_text(json.dumps(_safe_admin_trace()), encoding="utf-8")
    report_json = tmp_path / "report.json"
    report_json.write_text(
        json.dumps(_safe_founder_report()),
        encoding="utf-8",
    )
    report_metadata = tmp_path / "report-metadata.json"
    report_metadata.write_text(json.dumps(_safe_report_metadata()), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "capture_founder_screenshots.mjs"
    fixture = (
        repo_root / "tests" / "fixtures" / "startup_synthetic_v1" / "cases" / "saas" / "pitch.pdf"
    )
    result = subprocess.run(
        [
            node,
            str(script),
            "--validate-only=true",
            f"--browser={tmp_path / 'browser.exe'}",
            "--url=http://127.0.0.1:3000/",
            f"--desktop-states={tmp_path / 'desktop-states'}",
            f"--fixture={fixture}",
            f"--evidence={tmp_path / 'browser-evidence.json'}",
            "--require-desktop-state-suite=true",
            "--require-pdf-upload-journey=true",
            f"--admin-trace-json={admin_trace}",
            f"--report-json={report_json}",
            f"--report-metadata={report_metadata}",
            "--desktop-case-id=case-123",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "founder_browser_evidence_contract_valid" in result.stdout
    assert "admin_trace_contract_valid" in result.stdout
    assert "pitch.pdf" not in result.stdout
    assert str(fixture) not in result.stdout


def test_cdp_capture_validate_only_rejects_admin_trace_sensitive_key(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    admin_trace = tmp_path / "admin-trace.json"
    payload = _safe_admin_trace()
    payload["prompt"] = "redacted"
    admin_trace.write_text(json.dumps(payload), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "capture_founder_screenshots.mjs"
    fixture = (
        repo_root / "tests" / "fixtures" / "startup_synthetic_v1" / "cases" / "saas" / "pitch.pdf"
    )
    result = subprocess.run(
        [
            node,
            str(script),
            "--validate-only=true",
            f"--browser={tmp_path / 'browser.exe'}",
            "--url=http://127.0.0.1:3000/",
            f"--desktop-states={tmp_path / 'desktop-states'}",
            f"--fixture={fixture}",
            f"--evidence={tmp_path / 'browser-evidence.json'}",
            "--require-desktop-state-suite=true",
            "--require-pdf-upload-journey=true",
            f"--admin-trace-json={admin_trace}",
            "--desktop-case-id=case-123",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "browser_evidence_admin_trace_privacy_violation" in result.stderr
    assert "pitch.pdf" not in result.stderr
    assert str(fixture) not in result.stderr


def test_cdp_capture_validate_only_rejects_incomplete_admin_trace_coverage(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    payload = _safe_admin_trace()
    payload["node_rows"] = [payload["node_rows"][-1]]
    admin_trace = tmp_path / "admin-trace.json"
    admin_trace.write_text(json.dumps(payload), encoding="utf-8")
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "capture_founder_screenshots.mjs"
    fixture = (
        repo_root / "tests" / "fixtures" / "startup_synthetic_v1" / "cases" / "saas" / "pitch.pdf"
    )
    result = subprocess.run(
        [
            node,
            str(script),
            "--validate-only=true",
            f"--browser={tmp_path / 'browser.exe'}",
            "--url=http://127.0.0.1:3000/",
            f"--desktop-states={tmp_path / 'desktop-states'}",
            f"--fixture={fixture}",
            f"--evidence={tmp_path / 'browser-evidence.json'}",
            "--require-desktop-state-suite=true",
            "--require-pdf-upload-journey=true",
            f"--admin-trace-json={admin_trace}",
            "--desktop-case-id=case-123",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "browser_evidence_admin_trace_node_coverage_missing" in result.stderr


def test_cdp_capture_validate_only_rejects_stale_admin_report_lineage(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    admin_trace = tmp_path / "admin-trace.json"
    admin_trace.write_text(json.dumps(_safe_admin_trace()), encoding="utf-8")
    report_json = tmp_path / "report.json"
    report_json.write_text(
        json.dumps(_safe_founder_report(data_revision=2)),
        encoding="utf-8",
    )
    report_metadata = tmp_path / "report-metadata.json"
    report_metadata.write_text(
        json.dumps(
            _safe_report_metadata(
                data_revision=2,
                snapshot_id="22222222-2222-4222-8222-222222222222",
                hash_character="b",
            )
        ),
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "capture_founder_screenshots.mjs"
    fixture = (
        repo_root / "tests" / "fixtures" / "startup_synthetic_v1" / "cases" / "saas" / "pitch.pdf"
    )
    result = subprocess.run(
        [
            node,
            str(script),
            "--validate-only=true",
            f"--browser={tmp_path / 'browser.exe'}",
            "--url=http://127.0.0.1:3000/",
            f"--desktop-states={tmp_path / 'desktop-states'}",
            f"--fixture={fixture}",
            f"--evidence={tmp_path / 'browser-evidence.json'}",
            "--require-desktop-state-suite=true",
            "--require-pdf-upload-journey=true",
            f"--admin-trace-json={admin_trace}",
            f"--report-json={report_json}",
            f"--report-metadata={report_metadata}",
            "--desktop-case-id=case-123",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "browser_evidence_admin_trace_report_mismatch" in result.stderr


def test_cdp_capture_production_path_generates_same_case_admin_trace() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    assert "generateAdminTraceEvidence" in text
    assert "due_diligence_agent.evals.startup_trace_sidecar" in text
    assert 'required(options, "audit-spool-root")' in text
    assert "startup-api-${caseId}" in text
    assert "mkdirSync(dirname(generatedAdminTracePath), { recursive: true })" in text


def test_cdp_capture_validates_founder_safe_html_without_internal_lineage_ids() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    assert "reportHtmlText.includes('data-startup-charts')" in text
    assert "reportHtmlText.includes('id=\"technical-appendix\"')" in text
    assert "reportHtmlText.includes(reportMetadata.snapshot_id)" in text
    assert "reportHtmlText.includes(reportMetadata.snapshot_hash)" in text
    assert "reportHtmlText.includes(journey.caseId)" in text
    assert "reportHtmlText.includes(parsedJson.id)" not in text
    assert "validateFounderSafeReportPayload" in text
    assert "validateReportMetadata" in text
    assert "report_metadata: {" in text
    assert "snapshot_id: reportMetadata.snapshot_id" in text
    assert "snapshot_hash: reportMetadata.snapshot_hash" in text
    assert "snapshot_revision: reportMetadata.snapshot_revision" in text
    assert "browser_evidence_report_html_privacy_or_contract_mismatch" in text


def test_desktop_suite_captures_updated_analysis_after_recalculation() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    recalculation_ready = text.index('"desktop_suite_recalculation_report_ready"')
    updated_analysis_capture = text.index(
        'captureDesktopState("13-ai-advisor-updated-analysis.png")'
    )
    improved_plan_capture = text.index('captureDesktopState("14-ai-advisor-improved-plan.png")')

    assert recalculation_ready < updated_analysis_capture < improved_plan_capture


def test_desktop_suite_waits_for_rendered_admin_dashboard_before_capture() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    assert 'text.includes("Обзор системы")' in text
    assert 'text.includes("Граф агентов (LangGraph)")' in text
    assert '"desktop_suite_admin_dashboard_ready"' in text


def test_cdp_capture_records_pdf_intake_from_observed_dom_actions() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    assert "armFounderIntakeObservation" in text
    assert "observeFounderIntakeEvidence" in text
    assert "__queue5ObservedIntake" in text
    assert 'addEventListener("change"' in text
    assert "capture: true" in text
    assert "intake_mode: journey.intakeEvidence.intake_mode" in text
    assert "prompt_selection_used: journey.intakeEvidence.prompt_selection_used" in text
    assert "industry_selection_used: journey.intakeEvidence.industry_selection_used" in text
    assert "prompt_selection_used: false" not in text
    assert "industry_selection_used: false" not in text
    assert "intake_mode: fixtureSummary?.pdf_upload_journey" not in text


def test_cdp_capture_dispatches_file_input_events_after_setting_files() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    set_files_index = text.index('"DOM.setFileInputFiles"')
    start_button_index = text.index('"Начать анализ"')
    dispatch_slice = text[set_files_index:start_button_index]

    assert "querySelector('input[type=\"file\"]')" in dispatch_slice
    assert 'dispatchEvent(new Event("input", { bubbles: true }))' in dispatch_slice
    assert 'dispatchEvent(new Event("change", { bubbles: true }))' in dispatch_slice
    assert 'clickButton(\n        "Начать анализ",' in text


def test_desktop_suite_clicks_buttons_atomically_when_they_become_ready() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    helper_start = text.index("async function clickButton(")
    helper_end = text.index("async function clickSidebar", helper_start)
    helper = text[helper_start:helper_end]

    assert 'buttonExpression(label, "click")' in helper
    assert 'buttonExpression(label, "ready")' not in helper
    assert "await evaluateValue" not in helper
    assert "timeoutMilliseconds = 30_000" in helper
    assert "waitLabel = `desktop_suite_button_${label}`" in helper

    recalculation_start = text.index('"Продолжить обновление"')
    recalculation_end = text.index('"desktop_suite_recalculation_report_ready"')
    recalculation_slice = text[recalculation_start:recalculation_end]
    assert '"desktop_suite_recalculation_gate2_ready"' in recalculation_slice
    assert 'buttonExpression("Подтвердить и продолжить", "ready")' not in recalculation_slice

    improvement_start = text.index('"desktop_suite_improvement_recalculation_started"')
    improvement_end = text.index('"desktop_suite_improvement_report_ready"')
    improvement_slice = text[improvement_start:improvement_end]
    assert '"desktop_suite_improvement_gate2_ready"' in improvement_slice
    assert 'buttonExpression("Подтвердить и продолжить", "ready")' not in improvement_slice


def test_cdp_wait_timeout_reports_active_view_and_action_state() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    helper_start = text.index("async function describeBrowserWaitState(")
    helper_end = text.index("async function waitForExpression(", helper_start)
    helper = text[helper_start:helper_end]

    assert 'getAttribute("data-founder-active-view")' in helper
    assert 'querySelectorAll("[data-founder-view]")' in helper
    assert 'querySelectorAll("[data-founder-action]")' in helper
    assert "candidate.disabled" in helper
    assert "candidate.getClientRects().length > 0" in helper
    assert "describeBrowserWaitState(client, sessionId)" in text
    assert "diagnostic=${JSON.stringify(diagnostic)}" in text


def test_desktop_suite_uses_stable_gate2_action_selector() -> None:
    script = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    page = Path("frontend/founder/components/founder-analysis-pages.tsx").read_text(
        encoding="utf-8"
    )

    assert "data-founder-action={action}" in page
    assert 'action="gate2-approve"' in page
    assert "actionSelectorExpression" in script

    desktop_suite_start = script.index("if (desktopStateSuitePath) {")
    first_gate2_start = script.index(
        'actionSelectorExpression("gate2-approve", "ready")', desktop_suite_start
    )
    first_gate2_end = script.index('captureDesktopState("03-analysis-progress-gate2.png")')
    first_gate2_slice = script[first_gate2_start:first_gate2_end]

    assert 'actionSelectorExpression("gate2-approve", "ready")' in first_gate2_slice
    assert "buttonExpression" not in first_gate2_slice


def test_cdp_capture_prepares_same_case_report_before_improved_plan() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    overview_capture_index = text.index('captureDesktopState("04-overview-readiness.png")')
    gate3_action_index = text.index('clickButton(\n        "Принять рекомендацию",')
    advisor_capture_index = text.index('captureDesktopState("11-ai-advisor-next-question.png")')

    assert overview_capture_index < gate3_action_index < advisor_capture_index
    assert 'buttonExpression("Сформировать отчёт", "ready")' in text
    assert '"Принять направление"' not in text
    assert '"Подтвердить и сформировать PDF"' not in text


def test_cdp_capture_uses_report_sidebar_after_action_plan_state() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    action_plan_capture_index = text.index('captureDesktopState("08-ai-action-plan.png")')
    report_sidebar_index = text.index(
        'clickSidebar("Отчёты", \'[data-founder-view="report-center"]\')'
    )
    report_capture_index = text.index('captureDesktopState("09-report-center.png")')
    report_slice = text[action_plan_capture_index:report_capture_index]

    assert action_plan_capture_index < report_sidebar_index < report_capture_index
    assert '"Собрать итоговый отчёт"' not in report_slice
    assert '"Подтвердить и сформировать PDF"' not in report_slice


def test_cdp_capture_waits_for_advisor_answer_settle_before_save() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    answer_input_index = text.index('"desktop_suite_advisor_manual_input"')
    answer_submit_index = text.index('"Сохранить и пересчитать"')
    answer_slice = text[answer_input_index:answer_submit_index]

    assert 'textarea[aria-label="Ручной ответ советнику"]' in answer_slice
    assert "HTMLTextAreaElement.prototype" in answer_slice
    assert "desktop_suite_advisor_answer_settle" in answer_slice
    assert "requestAnimationFrame" in answer_slice
    assert 'buttonExpression("Запустить анализ выбранных материалов"' not in text


def test_desktop_suite_accepts_real_improvement_and_rebuilds_same_case_before_screen_14() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    updated_capture_index = text.index('captureDesktopState("13-ai-advisor-updated-analysis.png")')
    improved_plan_index = text.index('"Перейти к улучшенному плану"', updated_capture_index)
    accept_index = text.index('clickButton(\n        "Принять",', improved_plan_index)
    accepted_recalculation_index = text.index(
        '"desktop_suite_improvement_recalculation_started"', accept_index
    )
    improvement_gate2_index = text.index(
        '"desktop_suite_improvement_gate2_ready"', accepted_recalculation_index
    )
    improvement_report_index = text.index(
        '"desktop_suite_improvement_report_ready"', improvement_gate2_index
    )
    accepted_version_index = text.index(
        '"desktop_suite_improvement_version_ready"', improvement_report_index
    )
    improved_capture_index = text.index('captureDesktopState("14-ai-advisor-improved-plan.png")')

    assert updated_capture_index < improved_plan_index < accept_index
    assert accept_index < accepted_recalculation_index < improvement_gate2_index
    assert improvement_gate2_index < improvement_report_index
    assert improvement_report_index < accepted_version_index < improved_capture_index


def test_cdp_capture_waits_for_requested_founder_shell_before_first_desktop_state() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    shell_wait_index = text.index('"desktop_suite_initial_founder_shell"')
    first_capture_index = text.index('captureDesktopState("01-start-dashboard.png")')

    assert shell_wait_index < first_capture_index
    assert "location.href === expectedInitialUrl" in text
    assert 'document.querySelector(".founder-dashboard-shell")' in text
    assert 'document.querySelector("nav.founder-sidebar__nav")' in text


def test_desktop_suite_browser_evidence_uses_same_case_public_api_not_legacy_dom() -> None:
    text = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    collector = text[
        text.index("async function collectDesktopSuitePublicApiEvidence"):
        text.index("async function collectDesktopSuiteReportJourneyEvidence")
    ]

    assert "collectDesktopSuitePublicApiEvidence(approvedCaseId)" in text
    assert "summarizeDesktopSuitePublicApiEvidence" in text
    assert "buildDesktopSuitePublicApiPaths" in text
    assert "collectDesktopSuiteOverviewEvidence" not in text
    assert "collectDesktopSuiteMetricsDomEvidence" not in text
    assert "collectDesktopSuiteReportDomEvidence" not in text
    assert ".startup-profile__grid .profile-field" not in collector
    assert "[data-report-section=" not in collector


def test_cdp_capture_allows_multiple_quarantined_parser_injection_origins() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ normalizeOptionalOrigins }} from "{script}";'
                "const origins = [...normalizeOptionalOrigins("
                "'http://gc.kis.v2.scr.kaspersky-labs.com,"
                "http://me.kis.v2.scr.kaspersky-labs.com/'"
                ")];"
                "console.log(JSON.stringify(origins));"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        "http://gc.kis.v2.scr.kaspersky-labs.com",
        "http://me.kis.v2.scr.kaspersky-labs.com",
    ]


def test_founder_smoke_validate_only_resolves_browser_evidence_path(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "smoke_founder_workspace.ps1"
    evidence_path = tmp_path / "browser-evidence.json"
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ValidateOnly",
            "-DataDir",
            str(tmp_path / "data"),
            "-ScreenshotDir",
            str(tmp_path / "screenshots"),
            "-BrowserEvidencePath",
            str(evidence_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"browser_evidence={evidence_path}" in result.stdout


def test_founder_smoke_validate_only_accepts_case_copilot_text_fixture_contract(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "smoke_founder_workspace.ps1"
    text_fixture = (
        repo_root
        / "tests"
        / "fixtures"
        / "startup_case_copilot_v1"
        / "cases"
        / "idea_inventory"
        / "brief.txt"
    )
    evidence_path = tmp_path / "case-copilot-browser-evidence.json"
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ValidateOnly",
            "-RequireCaseCopilotScenarioJourney",
            "-OfflineFixturePath",
            str(text_fixture),
            "-DataDir",
            str(tmp_path / "data"),
            "-ScreenshotDir",
            str(tmp_path / "screenshots"),
            "-BrowserEvidencePath",
            str(evidence_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "case_copilot_scenario_journey=True" in result.stdout
    assert "fixture_mime=text/plain" in result.stdout


def test_founder_smoke_requires_explicit_cdp_case_copilot_journey_not_screenshot_fallback() -> None:
    script = Path("scripts/smoke_founder_workspace.ps1").read_text(encoding="utf-8")
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    assert "[switch] $RequireCaseCopilotScenarioJourney" in script
    assert "--require-case-copilot-scenario-journey=true" in script
    assert "case_copilot_scenario_journey" in script
    assert 'options["require-case-copilot-scenario-journey"] === "true"' in capture
    assert "case_copilot_scenario_journey_required" in capture
    assert "case_copilot_scenario_journey_verified" in capture
    assert "validateCaseCopilotScenarioJourneyEvidence(" in capture
    assert "caseCopilotScenarioJourney" in capture
    assert "case_copilot_scenario_journey_requires_both_fixtures" in capture


def test_founder_smoke_supports_restart_aware_smart_university_single_pdf_journey() -> None:
    script = Path("scripts/smoke_founder_workspace.ps1").read_text(encoding="utf-8")

    assert "[switch] $RequireSmartUniversitySinglePdfJourney" in script
    assert "--require-smart-university-single-pdf-journey=true" in script
    assert "smart_university_single_pdf_journey" in script
    assert "smart_university_browser_evidence_required" in script
    assert "$RequireSmartUniversitySinglePdfJourney) {" in script
    assert "$captureArgs += \"--desktop=$desktopPath\"" in script
    assert "$captureArgs += \"--desktop-states=$desktopStatesPath\"" in script
    assert '"--require-desktop-state-suite=true"' in script
    assert script.index("$RequireSmartUniversitySinglePdfJourney) {") < script.index(
        '$captureArgs += "--fixture=$FixturePath"',
    )
    assert "smart-university-restart-request-" in script
    assert "smart-university-restart-ready-" in script
    assert "--case-copilot-restart-request=$smartUniversityRestartRequestPath" in script
    assert "--case-copilot-restart-ready=$smartUniversityRestartReadyPath" in script
    assert (
        "$RequireCaseCopilotScenarioJourney -or $RequireSmartUniversitySinglePdfJourney"
        in script
    )
    assert "Invoke-FounderScreenshotCaptureWithCaseCopilotRestart" in script


def test_cdp_case_copilot_journey_uses_dedicated_non_validate_browser_driver() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")

    assert 'const CASE_COPILOT_BROWSER_EVIDENCE_SCHEMA_VERSION = "case_copilot_browser_evidence@1"' in capture
    assert "async function driveCaseCopilotScenarioJourney(" in capture
    assert "async function writeCaseCopilotBrowserEvidence(" in capture
    assert "collectCaseCopilotScenarioFixtureUiEvidence" in capture
    assert "driveFounderGtmJourney(client, sessionId, fixturePath, pdfUploadJourney)" in capture
    assert "driveCaseCopilotScenarioJourney(" in capture
    assert "caseCopilotRestartRequestPath" in capture
    assert "caseCopilotRestartReadyPath" in capture


def test_cdp_case_copilot_journey_posts_both_text_fixtures_through_same_origin_proxy() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    driver = capture[
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence("):
        capture.index("function smartUniversityButtonExpression(")
    ]

    assert 'input[type="file"]' in driver
    assert "DOM.setFileInputFiles" in driver
    assert 'data-case-question-card' in driver
    assert '"Structured founder statement"' in driver
    assert "data-case-copilot-manual-field-key" in driver
    assert "manualFieldKey" in driver
    assert '"Amount"' in driver
    assert '"Scale"' in driver
    assert '"Currency"' in driver
    assert '"Period month"' in driver
    assert '"Declared source"' in driver
    assert '"Rationale"' in driver
    assert '"Validation plan"' in driver
    assert '"1850000"' in driver
    assert '"ones"' in driver
    assert '"KZT"' in driver
    assert '"2026-07"' in driver
    assert '"founder interview"' in driver
    assert '"planning input"' in driver
    assert '"verify against CRM/finance"' in driver
    assert '"Unknown"' in driver
    assert '"Public research"' in driver
    assert 'input[type="checkbox"]' in driver
    assert '"Prepare research"' in driver
    assert 'data-case-copilot-research-status' in driver
    assert '"Base"' in driver
    assert '"Собрать рабочий пакет"' in driver or '"Launch pack"' in driver or '"Build workpack"' in driver
    assert '"idea_inventory"' in driver
    assert '"idea_clinic"' in driver
    assert '"Runtime.evaluate"' in capture


def test_cdp_case_copilot_captures_pre_queue_research_baseline_before_prepare() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    driver = capture[
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence("):
        capture.index("async function collectCaseCopilotPostRestartEvidence(")
    ]

    public_research_index = driver.index('clickCaseCopilotAnswerTab(currentCaseId, "Public research")')
    consent_index = driver.index("checkbox.click()", public_research_index)
    pre_research_index = driver.index("const preResearchState = await requestCaseCopilotState(currentCaseId)", consent_index)
    provider_boundary_index = driver.index("const providerCallsZeroBeforeQueue =", pre_research_index)
    prepare_research_index = driver.index(
        'buttonByTextInCasePanel(currentCaseId, "Prepare research"',
        provider_boundary_index,
    )
    post_research_index = driver.index("const stateAfterResearch = await requestCaseCopilotState(caseId)", prepare_research_index)

    assert consent_index < pre_research_index < provider_boundary_index
    assert provider_boundary_index < prepare_research_index < post_research_index
    assert "pre_research_state:" in driver
    assert "provider_calls_zero_before_queue: args.providerCallsZeroBeforeQueue" in driver
    assert "successfulCaseCopilotMutationEvents(currentCaseId, \"/research/jobs\")" in driver
    assert "assertNoPreQueueResearchJobMutations(" in driver
    assert "__caseCopilotResearchJobMutationProof" in driver
    assert "__caseCopilotResearchJobMutationProof.slice" not in driver
    assert "accepted public benchmarks" not in driver
    assert 'item?.kind === "public_benchmark"' not in driver
    assert "initialState = await requestJson" not in driver


def test_cdp_case_copilot_current_panel_helper_rejects_stale_or_unchanged_case() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ selectVisibleCurrentCaseCopilotPanel }} from "{script}";'
                "const panel = (caseId, visible = true, hasQuestion = true) => ({"
                "getAttribute: (name) => name === 'data-case-id' ? caseId : null,"
                "getClientRects: () => visible ? [{}] : [],"
                "querySelector: (selector) => hasQuestion && selector === '[data-case-question-card]' ? {} : null,"
                "});"
                "const selected = selectVisibleCurrentCaseCopilotPanel(["
                "panel('previous'), panel('current')"
                "], 'previous');"
                "if (selected?.getAttribute('data-case-id') !== 'current') throw new Error('current_not_selected');"
                "if (selectVisibleCurrentCaseCopilotPanel([panel('previous')], 'previous') !== null) throw new Error('unchanged_selected');"
                "if (selectVisibleCurrentCaseCopilotPanel([panel('current', false), panel('other', true, false)], 'previous') !== null) throw new Error('invalid_selected');"
                "console.log('panel-helper-ok');"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "panel-helper-ok"


def test_cdp_case_copilot_research_job_proof_is_non_evicting_and_fail_closed() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                "import { collectCaseCopilotResearchJobMutationProof, "
                f'assertNoPreQueueResearchJobMutations }} from "{script}";'
                "const events = [{"
                "method: 'POST', status: 201,"
                "url: '/api/startup/cases/current-case/research/jobs'"
                "}];"
                "for (let index = 0; index < 60; index += 1) {"
                "events.push({method: 'POST', status: 200, url: `/api/startup/cases/noisy-${index}/profile`});"
                "}"
                "const proof = collectCaseCopilotResearchJobMutationProof(events);"
                "if (proof.length !== 1) throw new Error(`proof_count=${proof.length}`);"
                "let failedClosed = false;"
                "try { assertNoPreQueueResearchJobMutations(proof, 'current-case'); }"
                "catch (error) { failedClosed = String(error.message).includes('case_copilot_pre_queue_research_jobs_observed'); }"
                "if (!failedClosed) throw new Error('forbidden_research_job_not_detected');"
                "const acceptedInputs = [];"
                "if (acceptedInputs.some((item) => item?.kind === 'public_benchmark')) throw new Error('bad_fixture');"
                "if (!assertNoPreQueueResearchJobMutations(proof, 'different-case')) throw new Error('other_case_failed');"
                "console.log('research-proof-ok');"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "research-proof-ok"


def test_cdp_case_copilot_successful_mutation_expression_returns_json_string() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "capture_founder_screenshots.mjs"
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                "import { readFileSync } from 'node:fs';"
                f"const source = readFileSync({json.dumps(str(script_path))}, 'utf8');"
                "const normalizedSource = source.replaceAll('\\r\\n', '\\n');"
                "const start = normalizedSource.indexOf('async function successfulCaseCopilotMutationEvents(');"
                "if (start < 0) throw new Error('helper_missing');"
                "const templateStart = normalizedSource.indexOf('`(() => {', start);"
                "const templateEnd = normalizedSource.indexOf('`,\\n    );', templateStart);"
                "if (templateStart < 0 || templateEnd < 0) throw new Error('expression_missing');"
                "let expression = normalizedSource.slice(templateStart + 1, templateEnd);"
                "expression = expression"
                ".replace('${JSON.stringify(caseId)}', JSON.stringify('current-case'))"
                ".replace('${JSON.stringify(pathFragment)}', JSON.stringify('/research/jobs'));"
                "globalThis.__caseCopilotResearchJobMutationProof = [{"
                "caseId: 'current-case', method: 'POST',"
                "path: '/api/startup/cases/current-case/research/jobs',"
                "sequence: 1, status: 201"
                "}];"
                "const browserValue = eval(expression);"
                "const parsed = JSON.parse(browserValue);"
                "if (!Array.isArray(parsed) || parsed[0]?.caseId !== 'current-case') {"
                "throw new Error('parsed_payload_invalid');"
                "}"
                "console.log('json-expression-ok');"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "json-expression-ok"


def test_cdp_case_copilot_journey_scopes_state_and_interactions_to_current_case_panel() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    driver = capture[
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence("):
        capture.index("async function writeCaseCopilotBrowserEvidence(")
    ]

    previous_case_index = driver.index("const previousCaseId = await readVisibleCaseCopilotPanelCaseId()")
    new_analysis_index = driver.index('buttonByText("Новый анализ"', previous_case_index)
    wait_current_index = driver.index(
        "await waitForCurrentCaseCopilotPanel(previousCaseId)",
        new_analysis_index,
    )
    current_case_index = driver.index(
        "const currentCaseId = await readCurrentCaseCopilotPanelCaseId(previousCaseId)",
        wait_current_index,
    )

    assert previous_case_index < new_analysis_index < wait_current_index < current_case_index
    assert "function caseCopilotPanelByCaseId(caseId)" in driver
    assert "panel?.getAttribute(\"data-case-id\") === caseId" in driver
    assert "async function requestCaseCopilotState(caseId)" in driver
    assert "if (!caseId) throw new Error(\"case_copilot_current_case_id_missing\")" in driver
    assert 'clickCaseCopilotAnswerTab(currentCaseId, "Manual")' in driver
    assert 'clickCaseCopilotAnswerTab(currentCaseId, "Unknown")' in driver
    assert 'clickCaseCopilotAnswerTab(currentCaseId, "Public research")' in driver
    assert 'setInputByLabel(currentCaseId, "Amount", "1850000")' in driver
    assert 'buttonByTextInCasePanel(currentCaseId, "Save answer"' in driver
    assert 'buttonByTextInCasePanel(currentCaseId, "Reply unknown"' in driver
    assert 'buttonByTextInCasePanel(currentCaseId, "Prepare research"' in driver
    assert 'panel?.querySelectorAll("[data-role]")' in driver
    assert 'panel?.querySelector("[data-founder-scenario-metrics]")' in driver
    assert 'buttonByTextInCasePanel(currentCaseId, "Conservative"' in driver
    assert 'buttonByTextInCasePanel(currentCaseId, "Base"' in driver
    assert "currentCaseAssetPrefix" in driver
    assert "href.includes(currentCaseAssetPrefix)" in driver
    assert "caseCopilotPanelByCaseId(currentCaseId)" in driver
    assert "[data-case-copilot-research-status]" in driver
    assert 'document.querySelector("[data-case-question-card]")' not in driver
    assert "document.querySelector('[data-case-question-card] input[type=\"checkbox\"]')" not in driver


def test_cdp_case_copilot_global_navigation_actions_keep_current_case_asset_proof() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    driver = capture[
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence("):
        capture.index("async function writeCaseCopilotBrowserEvidence(")
    ]

    assert 'buttonByTextInCasePanel(currentCaseId, "План действий"' not in driver
    assert 'buttonByTextInCasePanel(currentCaseId, "Собрать рабочий пакет"' not in driver
    assert 'buttonByText("План действий", "case_copilot_open_action_plan")' in driver
    assert 'buttonByText("Собрать рабочий пакет", "case_copilot_generate_launch_pack")' in driver
    assert "currentCaseAssetPrefix" in driver
    assert "href.includes(currentCaseAssetPrefix)" in driver
    assert "case_copilot_launch_pack_current_case_missing" in driver


def test_cdp_case_copilot_journey_saves_manual_statement_before_unknown_reply() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    driver = capture[
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence("):
        capture.index("async function writeCaseCopilotBrowserEvidence(")
    ]

    manual_tab_index = driver.index('clickCaseCopilotAnswerTab(currentCaseId, "Manual")')
    manual_input_index = driver.index('"Structured founder statement"', manual_tab_index)
    amount_index = driver.index('"Amount"', manual_input_index)
    period_index = driver.index('"Period month"', amount_index)
    validation_plan_index = driver.index('"Validation plan"', period_index)
    save_answer_index = driver.index(
        'buttonByTextInCasePanel(currentCaseId, "Save answer"',
        validation_plan_index,
    )
    unknown_tab_index = driver.index(
        'clickCaseCopilotAnswerTab(currentCaseId, "Unknown")',
        save_answer_index,
    )
    reply_unknown_index = driver.index(
        'buttonByTextInCasePanel(currentCaseId, "Reply unknown"',
        unknown_tab_index,
    )
    public_research_index = driver.index('clickCaseCopilotAnswerTab(currentCaseId, "Public research")')
    prepare_research_index = driver.index(
        'buttonByTextInCasePanel(currentCaseId, "Prepare research"',
        public_research_index,
    )

    assert manual_tab_index < manual_input_index < amount_index < period_index
    assert period_index < validation_plan_index < save_answer_index
    assert save_answer_index < unknown_tab_index < reply_unknown_index
    assert reply_unknown_index < public_research_index < prepare_research_index


def test_cdp_case_copilot_evidence_separates_founder_statement_from_unknown_reply() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    collector = capture[
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence("):
        capture.index("async function writeCaseCopilotBrowserEvidence(")
    ]

    founder_statement_slice = collector[
        collector.index("founder_statement_accepted:"):
        collector.index("final_screenshot_state:")
    ]
    unknown_answer_slice = collector[
        collector.index("unknown_answer_recorded:"):
        collector.index("visible_state:")
    ]

    assert "1850000" in founder_statement_slice
    assert "2026-07" in founder_statement_slice
    assert "founder interview" in founder_statement_slice
    assert 'item.kind === "founder_statement"' in founder_statement_slice
    assert ".includes(\"unknown\")" not in founder_statement_slice
    assert 'message.content?.toLowerCase() === "unknown"' in unknown_answer_slice
    assert "accepted_inputs.some" not in unknown_answer_slice


def test_cdp_case_copilot_no_source_fact_promotion_checks_current_profile_fields() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    collector = capture[
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence("):
        capture.index("async function writeCaseCopilotBrowserEvidence(")
    ]
    no_promotion_slice = collector[
        collector.index("no_source_fact_promotion:"):
        collector.index("plan_prepared:")
    ]
    profile_source_fact_slice = collector[
        collector.index("currentProfileHasFounderStatementSourceFact"):
        collector.index("const markdownLink")
    ]

    assert (
        "`/api/startup/cases/${encodeURIComponent(caseId)}/profile`"
        in collector
    )
    assert "currentProfile.fields ?? {}" in collector
    assert 'field.status === "source_fact"' in collector
    assert "Array.isArray(field.values)" in collector
    assert "field.values.some" in profile_source_fact_slice
    assert 'String(value).includes("1850000")' in profile_source_fact_slice
    assert '"1850000"' in profile_source_fact_slice
    assert "!currentProfileHasFounderStatementSourceFact" in no_promotion_slice
    assert "selectedState.accepted_inputs.some" in no_promotion_slice


def test_cdp_case_copilot_journey_uses_visible_ui_not_fetch_only_orchestration() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    driver = capture[
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence("):
        capture.index("async function writeCaseCopilotBrowserEvidence(")
    ]

    assert "collectCaseCopilotScenarioFixtureEvidence" not in capture
    assert "ui_interactions" in driver
    assert "visible_state" in driver
    assert "final_screenshot_state" in capture
    assert "case_copilot_visible_ui_state_missing" in capture
    assert "buttonByText(" in driver
    assert "setInputByLabel(" in driver
    assert "setTextareaByLabel(" not in driver
    assert "clickCaseCopilotAnswerTab(" in driver
    assert "requestJson(" in driver
    assert driver.index("DOM.setFileInputFiles") < driver.index("requestJson(")


def test_cdp_case_copilot_wait_diagnostics_include_same_origin_fetch_failures() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    driver = capture[
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence("):
        capture.index("async function writeCaseCopilotBrowserEvidence(")
    ]
    fetch_diagnostics = capture[
        capture.index("async function armCaseCopilotFetchDiagnostics("):
        capture.index("async function collectCaseCopilotScenarioFixtureUiEvidence(")
    ]
    diagnostics = capture[
        capture.index("async function describeBrowserWaitState("):
        capture.index("async function waitForExpression(")
    ]

    assert "armCaseCopilotFetchDiagnostics" in capture
    assert "await armCaseCopilotFetchDiagnostics(client, sessionId)" in driver
    assert "__caseCopilotFetchEvents" in fetch_diagnostics
    assert "__caseCopilotApiSnapshots" in fetch_diagnostics
    assert "response.clone().text()" in fetch_diagnostics
    assert "summarizeCaseCopilotApiPayload" in fetch_diagnostics
    assert "profileSourceFactCount" in fetch_diagnostics
    assert "gate2ResumeTokenPresent" in fetch_diagnostics
    assert "fetchEvents" in diagnostics
    assert "apiSnapshots: globalThis.__caseCopilotApiSnapshots ?? {}" in diagnostics
    assert 'querySelectorAll("[role=alert]")' in diagnostics
    assert "visibleAlerts" in diagnostics
    assert "sanitizeBrowserDiagnosticText" in diagnostics
    assert "status: event.status" in diagnostics
    assert "body: event.body" in diagnostics


def test_cdp_case_copilot_restart_validation_happens_after_real_smoke_restart() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    script = Path("scripts/smoke_founder_workspace.ps1").read_text(encoding="utf-8")

    assert "process_restarted: true" not in capture
    assert "reloadedThread = await requestJson" not in capture
    assert "caseCopilotRestartRequestPath" in capture
    assert "caseCopilotRestartReadyPath" in capture
    assert "await requestCaseCopilotServiceRestart(" in capture
    assert "await waitForCaseCopilotRestartReady(" in capture
    drive = capture[
        capture.index("async function driveCaseCopilotScenarioJourney("):
        capture.index("async function writeCaseCopilotBrowserEvidence(")
    ]
    assert "collectCaseCopilotPostRestartEvidence" in drive
    assert drive.index("await waitForCaseCopilotRestartReady(") < drive.index(
        "collectCaseCopilotPostRestartEvidence",
    )
    assert "--case-copilot-restart-request=" in script
    assert "--case-copilot-restart-ready=" in script
    assert "Wait-FounderCaseCopilotRestartRequest" in script
    assert "System.Text.UTF8Encoding($false)" in script
    assert "System.IO.File]::WriteAllText($RestartReadyPath" in script
    assert "Set-Content -LiteralPath $RestartReadyPath" not in script


def test_cdp_case_copilot_captures_populated_ui_before_restart_request() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    drive = capture[
        capture.index("async function driveCaseCopilotScenarioJourney("):
        capture.index("async function writeCaseCopilotBrowserEvidence(")
    ]

    assert "captureCaseCopilotPreRestartScreenshot" in drive
    assert drive.index("await captureCaseCopilotPreRestartScreenshot(") < drive.index(
        "await requestCaseCopilotServiceRestart(",
    )
    assert drive.index("await requestCaseCopilotServiceRestart(") < drive.index(
        "await waitForCaseCopilotRestartReady(",
    )


def test_cdp_case_copilot_post_restart_collector_is_api_only() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    collector = capture[
        capture.index("async function collectCaseCopilotPostRestartEvidence("):
        capture.index("async function driveCaseCopilotScenarioJourney(")
    ]

    assert "fetch(path" in collector
    assert "/copilot/thread" in collector
    assert "/scenarios" in collector
    assert "/assets/" in collector
    assert "buttonByTextPostRestart" not in capture
    assert "waitForExpression(" not in collector
    assert "querySelector" not in collector
    assert "document." not in collector


def test_cdp_case_copilot_returns_pre_restart_screenshot_with_final_journey_and_network_stats() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    branch = capture[
        capture.index("if (requireCaseCopilotScenarioJourney) {"):
        capture.index("if (desktopStateSuitePath) {")
    ]

    assert "let caseCopilotPreRestartCapture;" in branch
    assert "caseCopilotPreRestartCapture = await captureViewportArtifact(outputPath, viewport)" in branch
    assert "await accumulateCaptureEvidenceStats(caseCopilotPreRestartCapture" in branch
    assert "caseCopilotPreRestartCapture.journey = journey" in branch
    assert "return caseCopilotPreRestartCapture" in branch
    assert "return await captureViewportArtifact(outputPath, viewport)" not in branch


def test_cdp_case_copilot_restart_ready_parser_accepts_utf8_bom(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    ready_path = tmp_path / "restart-ready.json"
    ready_path.write_bytes(
        b'\xef\xbb\xbf{"status":"ready","token":"restart-token","ready_at":"2026-08-23T00:00:00Z"}\n',
    )
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ parseCaseCopilotRestartReadyPayload }} from "{script}";'
                "const ready = parseCaseCopilotRestartReadyPayload("
                f"{json.dumps(str(ready_path))}, 'restart-token'"
                ");"
                "console.log(`${ready.status}:${ready.token}`);"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ready:restart-token"


def test_cdp_case_copilot_evidence_writer_is_separate_from_legacy_report_payload() -> None:
    capture = Path("scripts/capture_founder_screenshots.mjs").read_text(encoding="utf-8")
    writer = capture[
        capture.index("async function writeCaseCopilotBrowserEvidence("):
        capture.index("class CdpClient")
    ]

    assert "CASE_COPILOT_BROWSER_EVIDENCE_SCHEMA_VERSION" in writer
    assert "caseCopilotScenarioJourney" in writer
    assert "report_json_path" not in writer
    assert "report_pdf_path" not in writer
    assert "validateFounderSafeReportPayload" not in writer


def test_founder_smoke_restarts_services_for_case_copilot_browser_evidence() -> None:
    script = Path("scripts/smoke_founder_workspace.ps1").read_text(encoding="utf-8")

    assert "case_copilot_browser_evidence_required" in script
    assert "case_copilot_browser_evidence_reload_phase" in script
    assert "Restart-FounderSmokeServicesForCaseCopilotEvidence" in script
    assert "Capture-FounderScreenshots $ScreenshotDriver $browserFixture $captureAuditSpoolRoot" in script


def test_founder_smoke_restart_capture_propagates_node_exit_code() -> None:
    script = Path("scripts/smoke_founder_workspace.ps1").read_text(encoding="utf-8")

    assert "capture_exit_code = [int] $LASTEXITCODE" in script
    assert "$captureExitCode -ne 0" in script
    assert "screenshot_capture_failed cdp exit_code=$captureExitCode" in script


def test_cdp_case_copilot_journey_rejects_legacy_or_single_fixture_evidence(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ validateCaseCopilotScenarioJourneyEvidence }} from "{script}";'
                "const fixture = {mime_type: 'text/plain'};"
                "try {"
                "validateCaseCopilotScenarioJourneyEvidence({caseId: 'legacy', actionPlanItems: 1, readinessDimensions: 1}, fixture);"
                "} catch (error) { console.log(error.message); }"
                "try {"
                "validateCaseCopilotScenarioJourneyEvidence({caseCopilotScenarioJourney: {fixtures: [{fixture_name: 'idea_inventory'}]}}, fixture);"
                "} catch (error) { console.log(error.message); }"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "case_copilot_scenario_journey_missing_structured_evidence" in result.stdout
    assert "case_copilot_scenario_journey_requires_both_fixtures" in result.stdout


def _case_copilot_fixture_journey(
    *,
    fixture_name: str,
    case_id: str,
    job_status: str = "completed",
    citations: list[str] | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "fixture_name": fixture_name,
        "ui_interactions": [
            "file_upload",
            "start_analysis",
            "gate2_approve",
            "unknown_answer",
            "public_research_consent",
            "scenario_select_base",
            "launch_pack_generate",
            "launch_pack_download",
        ],
        "visible_state": {
            "file_uploaded": True,
            "question_card_visible": True,
            "research_status_visible": True,
            "scenario_metrics_visible": True,
            "launch_pack_visible": True,
        },
        "final_screenshot_state": {
            "populated_same_case_ui": True,
            "case_copilot_panel_visible": True,
        },
        "text_brief_uploaded": True,
        "question_visible": True,
        "founder_statement_accepted": True,
        "unknown_answer_recorded": True,
        "research": {
            "plan_prepared": True,
            "provider_calls_zero_before_queue": True,
            "explicit_consent": True,
            "job_status": job_status,
            "citations": citations if citations is not None else ["https://example.com/source"],
            "source_refs": source_refs if source_refs is not None else ["source-1"],
            "no_source_fact_promotion": True,
        },
        "scenarios": {
            "scenario_keys": ["conservative", "base", "optimistic"],
            "selected_key": "base",
            "metric_delta": True,
            "readiness_delta": True,
            "risk_delta": True,
            "action_delta": True,
            "metric_disclosure_complete": True,
        },
        "launch_pack": {
            "asset_id": f"asset-{case_id}",
            "downloaded": True,
            "versioned": True,
            "provenance_appendix": True,
        },
        "restart": {
            "process_restarted": True,
            "same_case_reloaded": True,
            "same_scenario_reloaded": True,
            "same_asset_reloaded": True,
        },
    }


def test_cdp_case_copilot_journey_rejects_deferred_research_without_sources(
    tmp_path: Path,
) -> None:
    """Strict browser evidence requires completed or partial public research."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    journey_path = tmp_path / "deferred-journey.json"
    journey_path.write_text(
        json.dumps(
            {
                "caseCopilotScenarioJourney": {
                    "fixtures": [
                        _case_copilot_fixture_journey(
                            fixture_name="idea_inventory",
                            case_id="idea-inventory",
                            job_status="deferred",
                            citations=[],
                            source_refs=[],
                        ),
                        _case_copilot_fixture_journey(
                            fixture_name="idea_clinic",
                            case_id="idea-clinic",
                        ),
                    ],
                    "cross_fixture": {
                        "questions_differ": True,
                        "benchmark_scopes_differ": True,
                        "base_inputs_differ": True,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                "import { readFileSync } from 'node:fs';"
                f'import {{ validateCaseCopilotScenarioJourneyEvidence }} from "{script}";'
                "const fixture = {mime_type: 'text/plain'};"
                "const journey = JSON.parse(readFileSync(process.argv[1], 'utf8'));"
                "try {"
                "validateCaseCopilotScenarioJourneyEvidence(journey, fixture);"
                "console.log('deferred_without_citations_passed');"
                "process.exit(1);"
                "} catch (error) { console.log(error.message); }"
            ),
            str(journey_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "deferred_without_citations_passed" not in result.stdout
    assert "case_copilot_scenario_journey_job_status_invalid" in result.stdout


def test_smart_university_live_required_rejects_offline_or_unproved_research() -> None:
    """Live-required Smart University evidence must fail closed instead of accepting offline demo."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    journey_json = json.dumps(_safe_smart_university_single_pdf_journey())

    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ validateSmartUniversitySinglePdfJourneyEvidence }} from "{script}";'
                "const journey = JSON.parse(process.argv[1]);"
                "try {"
                "validateSmartUniversitySinglePdfJourneyEvidence(journey, {mime_type: 'application/pdf'}, {requireLivePublicResearch: true});"
                "console.log('offline_live_acceptance_passed');"
                "process.exit(1);"
                "} catch (error) { console.log(error.message); }"
            ),
            journey_json,
        ],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "offline_live_acceptance_passed" not in result.stdout
    assert "smart_university_single_pdf_journey_live_research_mode_invalid" in result.stdout


def test_smart_university_live_required_accepts_openai_web_search_report_and_restart_evidence() -> None:
    """Live-required evidence records requested live mode, actual OpenAI web search, final reports, and restart survival."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    public_research = _safe_smart_university_public_research(
        acquisition_mode="live_public_research",
        provider="openai",
        tool="web_search",
        tool_call_observed=True,
        trace_health={
            "status": "ok",
            "langsmith_status": "exported",
            "audit_status": "ok",
        },
    )
    journey = _safe_smart_university_single_pdf_journey(
        public_research=public_research,
        outputs=_safe_smart_university_outputs(final_decision_accepted=True),
        restart=_safe_smart_university_restart(
            same_final_decision_reloaded=True,
            same_report_artifacts_reloaded=True,
        ),
    )

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    journey_json = json.dumps(journey)

    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ validateSmartUniversitySinglePdfJourneyEvidence }} from "{script}";'
                "const journey = JSON.parse(process.argv[1]);"
                "validateSmartUniversitySinglePdfJourneyEvidence(journey, {mime_type: 'application/pdf'}, {requireLivePublicResearch: true});"
                "const research = journey.smartUniversitySinglePdfJourney.public_research;"
                "console.log(`${research.provider}:${research.tool}`);"
            ),
            journey_json,
        ],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "openai:web_search" in result.stdout


def test_smart_university_live_required_rejects_disabled_langsmith_trace() -> None:
    """Live-required mode cannot pass with tracing disabled in the owner-visible evidence."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    public_research = _safe_smart_university_public_research(
        acquisition_mode="live_public_research",
        provider="openai",
        tool="web_search",
        tool_call_observed=True,
        trace_health={
            "status": "disabled",
            "langsmith_status": "tracing_disabled",
            "audit_status": "ok",
        },
    )
    journey = _safe_smart_university_single_pdf_journey(
        public_research=public_research,
        outputs=_safe_smart_university_outputs(final_decision_accepted=True),
        restart=_safe_smart_university_restart(
            same_final_decision_reloaded=True,
            same_report_artifacts_reloaded=True,
        ),
    )

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    journey_json = json.dumps(journey)

    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ validateSmartUniversitySinglePdfJourneyEvidence }} from "{script}";'
                "const journey = JSON.parse(process.argv[1]);"
                "try {"
                "validateSmartUniversitySinglePdfJourneyEvidence(journey, {mime_type: 'application/pdf'}, {requireLivePublicResearch: true});"
                "console.log('disabled_trace_live_acceptance_passed');"
                "process.exit(1);"
                "} catch (error) { console.log(error.message); }"
            ),
            journey_json,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "disabled_trace_live_acceptance_passed" not in result.stdout
    assert "smart_university_single_pdf_journey_live_trace_invalid" in result.stdout


def test_smart_university_live_audit_uses_provider_event_as_canonical_tool_proof(
    tmp_path: Path,
) -> None:
    """The durable OpenAI span proves web_search without a legacy advisor span."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    case_id = "11111111-2222-4333-8444-555555555555"
    research_job_id = "66666666-7777-4888-8999-aaaaaaaaaaaa"
    spool_root = tmp_path / "audit-spool"
    spool_root.mkdir()
    events = [
        {
            "timestamp_utc": "2026-08-27T10:00:02Z",
            "correlation_id": f"different-{case_id}",
            "span_name": "startup.public_research",
            "event_type": "span",
            "attributes": {
                "provider": "openai",
                "research_label": "live_public_research",
                "status": "completed",
                "tool": "not_web_search",
                "latency_ms": 9999,
                "source_count": 99,
                "total_tokens": 999,
            },
        },
        {
            "schema_version": "audit_event@1",
            "event_id": "provider-completed",
            "timestamp_utc": "2026-08-27T10:00:00Z",
            "run_id": f"startup-public-research-{case_id}",
            "correlation_id": f"case-{case_id}",
            "span_name": "startup.public_research",
            "event_type": "span",
            "attributes": {
                "case_id": case_id,
                "provider": "openai",
                "request_id": research_job_id,
                "research_label": "live_public_research",
                "status": "completed",
                "tool": "web_search",
                "tool_call_observed": True,
                "latency_ms": 1234.5,
                "source_count": 3,
                "input_tokens": 321,
                "output_tokens": 123,
                "total_tokens": 444,
            },
        },
        {
            "schema_version": "audit_event@1",
            "event_id": "langsmith-healthy",
            "timestamp_utc": "2026-08-27T10:00:01Z",
            "run_id": f"startup-api-{case_id}",
            "correlation_id": case_id,
            "span_name": "analysis.module",
            "event_type": "observability.langsmith_status",
            "attributes": {
                "case_id": case_id,
                "status": "healthy",
                "error_code": "none",
                "fallback_used": "local_audit",
                "exporter_provider": "langsmith",
            },
        },
    ]
    (spool_root / "events.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ collectSmartUniversityLiveAuditEvidence }} from "{script}";'
                "console.log(JSON.stringify(collectSmartUniversityLiveAuditEvidence(process.argv[1], process.argv[2], process.argv[3])));"
            ),
            str(spool_root),
            case_id,
            research_job_id,
        ],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["provider"] == "openai"
    assert evidence["tool"] == "web_search"
    assert evidence["tool_call_observed"] is True
    assert evidence["latency_ms"] == 1234.5
    assert evidence["source_count"] == 3
    assert evidence["token_cost_status"] == {
        "status": "usage_observed",
        "raw_values_excluded": True,
    }
    assert evidence["trace_health"] == {
        "status": "healthy",
        "langsmith_status": "healthy",
        "audit_status": "ok",
    }


def test_smart_university_live_audit_prefers_latest_langsmith_failure(
    tmp_path: Path,
) -> None:
    """A later exporter failure cannot be hidden by an earlier healthy marker."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    case_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    research_job_id = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
    spool_root = tmp_path / "audit-spool"
    spool_root.mkdir()
    events = [
        {
            "timestamp_utc": "2026-08-27T10:00:00Z",
            "correlation_id": f"case-{case_id}",
            "span_name": "startup.public_research",
            "event_type": "span",
            "attributes": {
                "case_id": case_id,
                "provider": "openai",
                "request_id": research_job_id,
                "research_label": "live_public_research",
                "status": "completed",
                "tool": "web_search",
                "tool_call_observed": True,
                "latency_ms": 100,
                "source_count": 1,
                "total_tokens": 0,
            },
        },
        {
            "timestamp_utc": "2026-08-27T10:00:01Z",
            "correlation_id": case_id,
            "span_name": "analysis.module",
            "event_type": "observability.langsmith_status",
            "attributes": {
                "case_id": case_id,
                "status": "healthy",
                "exporter_provider": "langsmith",
            },
        },
        {
            "timestamp_utc": "2026-08-27T10:00:02Z",
            "correlation_id": case_id,
            "span_name": "analysis.module",
            "event_type": "observability.langsmith_status",
            "attributes": {
                "case_id": case_id,
                "status": "degraded",
                "exporter_provider": "langsmith",
            },
        },
    ]
    (spool_root / "events.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ collectSmartUniversityLiveAuditEvidence }} from "{script}";'
                "const evidence = collectSmartUniversityLiveAuditEvidence(process.argv[1], process.argv[2], process.argv[3]);"
                "console.log(JSON.stringify(evidence));"
            ),
            str(spool_root),
            case_id,
            research_job_id,
        ],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["trace_health"]["langsmith_status"] == "degraded"
    assert evidence["token_cost_status"] == {
        "status": "usage_unavailable",
        "raw_values_excluded": True,
    }


def test_smart_university_live_audit_rejects_stale_same_case_tool_proof(
    tmp_path: Path,
) -> None:
    """Only the current research job may satisfy the OpenAI web-search proof."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    case_id = "cccccccc-dddd-4eee-8fff-000000000000"
    stale_job_id = "11111111-1111-4111-8111-111111111111"
    current_job_id = "22222222-2222-4222-8222-222222222222"
    spool_root = tmp_path / "audit-spool"
    spool_root.mkdir()
    events = [
        {
            "timestamp_utc": "2026-08-27T10:00:00Z",
            "correlation_id": f"research-job-{stale_job_id}",
            "span_name": "startup.public_research",
            "event_type": "span",
            "attributes": {
                "case_id": case_id,
                "request_id": stale_job_id,
                "provider": "openai",
                "research_label": "live_public_research",
                "status": "completed",
                "tool": "web_search",
                "tool_call_observed": True,
                "latency_ms": 100,
                "source_count": 2,
                "total_tokens": 100,
            },
        },
        {
            "timestamp_utc": "2026-08-27T10:00:01Z",
            "correlation_id": f"research-job-{current_job_id}",
            "span_name": "startup.public_research",
            "event_type": "span",
            "attributes": {
                "case_id": case_id,
                "request_id": current_job_id,
                "provider": "openai",
                "research_label": "live_public_research",
                "status": "completed",
                "tool": "web_search",
                "tool_call_observed": False,
                "latency_ms": 90,
                "source_count": 2,
                "total_tokens": 100,
            },
        },
    ]
    (spool_root / "events.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ collectSmartUniversityLiveAuditEvidence }} from "{script}";'
                "console.log(JSON.stringify(collectSmartUniversityLiveAuditEvidence(process.argv[1], process.argv[2], process.argv[3])));"
            ),
            str(spool_root),
            case_id,
            current_job_id,
        ],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {}


def test_smart_university_live_required_chooses_online_research_fail_closed() -> None:
    """The browser driver selects the owner-visible online option and never falls back to offline in live mode."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    offline_tabs = json.dumps(["Офлайн-демо"], ensure_ascii=True)
    live_tabs = json.dumps(["Офлайн-демо", "Онлайн-ресерч"], ensure_ascii=True)
    unavailable_tabs = json.dumps(
        ["Офлайн-демо", "Без live-провайдера"],
        ensure_ascii=True,
    )
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ selectSmartUniversityResearchTabLabel }} from "{script}";'
                f"console.log(selectSmartUniversityResearchTabLabel({offline_tabs}));"
                f"console.log(selectSmartUniversityResearchTabLabel({live_tabs}, "
                "{requireLivePublicResearch: true}));"
                "try {"
                f"selectSmartUniversityResearchTabLabel({unavailable_tabs}, "
                "{requireLivePublicResearch: true});"
                "console.log('offline_required_selection_passed');"
                "process.exit(1);"
                "} catch (error) { console.log(error.message); }"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    stdout_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert stdout_lines[:2] == ["Офлайн-демо", "Онлайн-ресерч"]
    assert "offline_required_selection_passed" not in result.stdout
    assert "smart_university_live_research_tab_unavailable" in result.stdout


def test_smart_university_journey_rejects_missing_metrics_page_evidence() -> None:
    """Smart University same-case journey must prove the real metrics page was populated."""

    journey = _safe_smart_university_single_pdf_journey()
    journey["smartUniversitySinglePdfJourney"]["outputs"].pop("metrics_visible", None)

    result = _run_smart_university_validation(journey, require_live=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "smart_university_validation_passed" not in result.stdout
    assert "smart_university_single_pdf_journey_missing_metrics_visible" in result.stdout


def test_smart_university_live_required_rejects_changed_report_snapshot_after_restart() -> None:
    """Restart evidence must preserve the exact frozen report snapshot ID."""

    journey = _safe_smart_university_live_report_journey()
    journey["smartUniversitySinglePdfJourney"]["restart"]["report_artifacts"][
        "report_snapshot_id"
    ] = "snapshot-after-restart"

    result = _run_smart_university_validation(journey, require_live=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "smart_university_validation_passed" not in result.stdout
    assert "smart_university_single_pdf_journey_report_restart_mismatch" in result.stdout


def test_smart_university_live_required_rejects_changed_report_json_hash_after_restart() -> None:
    """Restart evidence must preserve the exact JSON report artifact hash."""

    journey = _safe_smart_university_live_report_journey()
    journey["smartUniversitySinglePdfJourney"]["restart"]["report_artifacts"][
        "json_sha256"
    ] = f"sha256:{'b' * 64}"

    result = _run_smart_university_validation(journey, require_live=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "smart_university_validation_passed" not in result.stdout
    assert "smart_university_single_pdf_journey_report_restart_mismatch" in result.stdout


def test_smart_university_live_required_rejects_changed_report_pdf_hash_after_restart() -> None:
    """Restart evidence must preserve the exact PDF report artifact hash."""

    journey = _safe_smart_university_live_report_journey()
    journey["smartUniversitySinglePdfJourney"]["restart"]["report_artifacts"][
        "pdf_sha256"
    ] = f"sha256:{'c' * 64}"

    result = _run_smart_university_validation(journey, require_live=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "smart_university_validation_passed" not in result.stdout
    assert "smart_university_single_pdf_journey_report_restart_mismatch" in result.stdout


def _run_smart_university_validation(
    journey: dict[str, Any],
    *,
    require_live: bool,
) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser evidence contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "capture_founder_screenshots.mjs").as_uri()
    return subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            (
                f'import {{ validateSmartUniversitySinglePdfJourneyEvidence }} from "{script}";'
                "const journey = JSON.parse(process.argv[1]);"
                "const requireLivePublicResearch = process.argv[2] === 'true';"
                "try {"
                "validateSmartUniversitySinglePdfJourneyEvidence(journey, {mime_type: 'application/pdf'}, {requireLivePublicResearch});"
                "console.log('smart_university_validation_passed');"
                "process.exit(1);"
                "} catch (error) { console.log(error.message); }"
            ),
            json.dumps(journey),
            "true" if require_live else "false",
        ],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        text=True,
        check=False,
    )


def _safe_smart_university_public_research(
    *,
    acquisition_mode: str = "offline_demo",
    provider: str | None = None,
    tool: str | None = None,
    tool_call_observed: bool = False,
    trace_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "explicit_consent": True,
        "requested_acquisition_mode": acquisition_mode,
        "selected_acquisition_mode": acquisition_mode,
        "acquisition_mode": acquisition_mode,
        "provider": provider,
        "tool": tool,
        "tool_call_observed": tool_call_observed,
        "status": "completed",
        "visible_sources": ["https://example.com/public-smart-university-source"],
        "source_count": 1,
        "sanitized_sources": [
            {
                "url": "https://example.com/public-smart-university-source",
                "as_of": "2026-08-27",
                "source_mode": "live" if acquisition_mode == "live_public_research" else "offline",
            }
        ],
        "latency_ms": 1250,
        "trace_health": trace_health
        if trace_health is not None
        else {
            "status": "offline",
            "langsmith_status": "tracing_disabled",
            "audit_status": "offline_fixture",
        },
        "token_cost_status": {
            "status": "observed",
            "raw_values_excluded": True,
        },
        "scenario_delta_visible": True,
        "scenario_change_evidence": {
            "rendered_comparison_count": 1,
            "rendered_change_count": 1,
        },
        "source_fact_promotion_blocked": True,
        "provenance_guard": {
            "accepted_inputs_checked": True,
            "profile_fields_checked": True,
            "public_private_aliases_blocked": True,
        },
    }


def _safe_smart_university_outputs(
    *,
    final_decision_accepted: bool = False,
) -> dict[str, Any]:
    case_id = "smart-university-case"
    report_root = f"/api/startup/cases/{case_id}/report"
    report_snapshot_id = "snapshot-before-restart"
    json_sha256 = f"sha256:{'1' * 64}"
    html_sha256 = f"sha256:{'2' * 64}"
    pdf_sha256 = f"sha256:{'3' * 64}"
    return {
        "metrics_visible": True,
        "market_reconstruction_visible": True,
        "risks_visible": True,
        "actions_visible": True,
        "page_evidence": _safe_smart_university_page_evidence(case_id),
        "plan_7_30_60_90_visible": True,
        "launch_pack_link_visible": True,
        "launch_pack_generated": True,
        "launch_pack_downloaded": True,
        "launch_pack_contract": {
            "platform_vs_housing_separated": True,
            "tariff_and_lead_economics_present": True,
            "forecast_2027_2031_clear": True,
            "rating_methodology_present": True,
            "housing_legal_fire_sanitary_gates_present": True,
            "tranche_plan_present": True,
            "provenance_appendix_present": True,
        },
        "final_decision_accepted": final_decision_accepted,
        "report_artifacts": {
            "case_id": case_id,
            "json_path": f"{report_root}/json",
            "html_path": f"{report_root}/html",
            "pdf_path": f"{report_root}/pdf",
            "downloaded_formats": ["JSON", "HTML", "PDF"],
            "pdf_bounded": True,
            "pdf_magic": "%PDF",
            "report_snapshot_id": report_snapshot_id,
            "json_sha256": json_sha256,
            "html_sha256": html_sha256,
            "pdf_sha256": pdf_sha256,
        },
    }


def _safe_smart_university_page_evidence(case_id: str) -> dict[str, Any]:
    return {
        "metrics": {
            "case_id": case_id,
            "contract_satisfied": True,
            "meaningful_item_count": 3,
            "populated": True,
            "placeholder_only": False,
            "rendered_text_chars": 320,
            "source_signal_count": 2,
        },
        "market": {
            "case_id": case_id,
            "contract_satisfied": True,
            "meaningful_item_count": 3,
            "populated": True,
            "placeholder_only": False,
            "rendered_text_chars": 340,
            "source_signal_count": 2,
        },
        "risks": {
            "case_id": case_id,
            "contract_satisfied": True,
            "meaningful_item_count": 2,
            "populated": True,
            "placeholder_only": False,
            "rendered_text_chars": 280,
            "source_signal_count": 1,
        },
        "action_plan": {
            "case_id": case_id,
            "contract_satisfied": True,
            "meaningful_item_count": 3,
            "populated": True,
            "placeholder_only": False,
            "rendered_text_chars": 360,
            "source_signal_count": 1,
        },
    }


def _safe_smart_university_langgraph_checkpoint() -> dict[str, Any]:
    return {
        "checkpoint_hash": "d" * 64,
        "checkpoint_id": "1f1a1fb3-c02e-6bb0-8008-d92ea1be1c4a",
        "data_revision": 2,
        "thread_id": "smart-university-case:r2",
    }


def _safe_smart_university_restart(
    *,
    same_final_decision_reloaded: bool = False,
    same_report_artifacts_reloaded: bool = False,
) -> dict[str, Any]:
    report_snapshot_id = "snapshot-before-restart"
    json_sha256 = f"sha256:{'1' * 64}"
    html_sha256 = f"sha256:{'2' * 64}"
    pdf_sha256 = f"sha256:{'3' * 64}"
    return {
        "process_restarted": True,
        "same_case_ui_rehydrated": True,
        "same_case_reloaded": True,
        "same_thread_reloaded": True,
        "same_research_job_reloaded": True,
        "same_scenario_reloaded": True,
        "same_asset_reloaded": True,
        "langgraph_checkpoint": _safe_smart_university_langgraph_checkpoint(),
        "langgraph_checkpoint_reloaded": True,
        "same_final_decision_reloaded": same_final_decision_reloaded,
        "same_report_artifacts_reloaded": same_report_artifacts_reloaded,
        "report_artifacts": {
            "report_snapshot_id": report_snapshot_id,
            "json_sha256": json_sha256,
            "html_sha256": html_sha256,
            "pdf_sha256": pdf_sha256,
        },
    }


def _safe_smart_university_single_pdf_journey(
    *,
    public_research: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    restart: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "smartUniversitySinglePdfJourney": {
            "case_identity": {
                "case_id": "smart-university-case",
                "thread_id": "thread-smart-university-case",
                "research_job_id": "research-smart-university-case",
                "selected_scenario_key": "base",
                "asset_id": "asset-smart-university-case",
                "langgraph_checkpoint": _safe_smart_university_langgraph_checkpoint(),
            },
            "upload": {
                "pdf_uploaded": True,
                "receipt_visible": True,
                "profile_source_grounded": True,
                "gate2_ready": True,
            },
            "founder_gap_handling": {
                "question_visible": True,
                "answered_or_skipped": True,
                "private_metrics_manual_or_file_only": True,
            },
            "public_research": public_research
            if public_research is not None
            else _safe_smart_university_public_research(),
            "scenarios": {
                "keys": ["conservative", "base", "optimistic"],
                "selected_key": "base",
                "provenance_complete": True,
            },
            "outputs": outputs if outputs is not None else _safe_smart_university_outputs(),
            "restart": restart if restart is not None else _safe_smart_university_restart(),
        }
    }


def _safe_smart_university_live_report_journey() -> dict[str, Any]:
    public_research = _safe_smart_university_public_research(
        acquisition_mode="live_public_research",
        provider="openai",
        tool="web_search",
        tool_call_observed=True,
        trace_health={
            "status": "ok",
            "langsmith_status": "exported",
            "audit_status": "ok",
        },
    )
    return _safe_smart_university_single_pdf_journey(
        public_research=public_research,
        outputs=_safe_smart_university_outputs(final_decision_accepted=True),
        restart=_safe_smart_university_restart(
            same_final_decision_reloaded=True,
            same_report_artifacts_reloaded=True,
        ),
    )


def _safe_founder_report(*, data_revision: int = 1) -> dict[str, Any]:
    section_keys = (
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
        "action_plan",
    )
    return {
        "title_ru": "Отчёт для основателя",
        "subtitle_ru": "Краткий разбор проекта, блокеры и следующие шаги",
        "as_of_ru": "2026-08-21",
        "data_revision": data_revision,
        "main_sections": [
            {
                "key": key,
                "title_ru": f"Раздел {index}",
                "status": "partial",
                "status_label_ru": "Частично подтверждено",
                "summary_ru": "Доступна безопасная сводка.",
                "content_heading_ru": "Что уже известно",
                "known_facts_ru": [],
                "blockers_ru": [],
                "next_data_ru": [],
                "unlocks_ru": [],
            }
            for index, key in enumerate(section_keys, start=1)
        ],
        "metric_cards": {},
        "improvement_proposals": [],
        "technical_appendix": {
            "methodology_ru": ["Детерминированная сборка отчёта."],
            "sources_ru": ["Использованы материалы текущего кейса."],
        },
        "analytics": {
            "metric_points": [],
            "market_points": [],
            "readiness_dimensions": [],
        },
    }


def _safe_report_metadata(
    *,
    data_revision: int = 1,
    snapshot_id: str = REPORT_SNAPSHOT_ID,
    hash_character: str = "a",
) -> dict[str, Any]:
    report_root = "/api/v1/startup/cases/case-123/report"
    return {
        "case_id": "case-123",
        "report_status": "ready",
        "snapshot_id": snapshot_id,
        "snapshot_hash": f"sha256:{hash_character * 64}",
        "snapshot_revision": data_revision,
        "json_url": f"{report_root}/json",
        "html_url": f"{report_root}/html",
        "pdf_url": f"{report_root}/pdf",
        "freeze_status": "approved",
        "pdf_status": "ready",
    }


def _safe_admin_trace() -> dict[str, Any]:
    run_id = "startup-api-case-123"
    return {
        "schema_version": "startup_trace_view@1",
        "case_id": "case-123",
        "run_id": run_id,
        "node_rows": [
            {
                "case_id": "case-123",
                "run_id": run_id,
                "node": node,
                "agent_role": "orchestration",
                "attempt": 1,
                "retry_count": 0,
                "status": "success",
                "error_code": None,
                "duration_ms": 1.0,
            }
            for node in REQUIRED_PDF_TRACE_NODES
        ],
        "report_lineage": {
            "decision": "approved",
            "gate4_status": "completed",
            "report_id": REPORT_SNAPSHOT_ID,
            "report_revision": 1,
            "report_checksum": "a" * 64,
        },
        "usage_summary": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost_usd": "0",
        },
        "exporter_health": None,
        "langsmith_health": {
            "provider": "langsmith",
            "status": "disabled",
            "error_code": "tracing_disabled",
            "fallback_used": "local_audit",
        },
    }
