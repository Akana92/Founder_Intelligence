from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DATASET = "startup_founder_frozen_v1"


DOCUMENTS = {
    "founder_pitch.txt": "\n".join(
        [
            "FounderCo builds privacy-first diligence automation for seed-stage investors.",
            "ARR: 1200000 USD as of 2026-08-12.",
            "Gross margin: 72 percent.",
            "Pipeline: 18 active funds and 41 founder-led startups.",
        ]
    )
    + "\n",
    "founder_metrics.txt": "\n".join(
        [
            "Customers: 24 paying teams.",
            "Net revenue retention: 116 percent.",
            "Primary risk: sales cycle concentration in two accelerator channels.",
        ]
    )
    + "\n",
}


def build_bundle() -> dict[str, str]:
    manifest = {
        "dataset": DATASET,
        "schema": "startup_founder_fixture_manifest.v1",
        "as_of": "2026-08-12",
        "provider_status": "offline_fixture_active",
        "network_policy": "no_external_network",
        "documents": [
            {"path": "documents/founder_pitch.txt", "mime_type": "text/plain"},
            {"path": "documents/founder_metrics.txt", "mime_type": "text/plain"},
        ],
        "expected_flow": [
            "create_case",
            "upload_documents",
            "gate2_preview",
            "gate2_decision",
            "gate3_decision",
            "report_snapshot",
            "gate4_decision",
            "report_pdf",
        ],
        "artifacts": {
            "desktop_screenshot": "artifacts/ui/founder-desktop.png",
            "mobile_screenshot": "artifacts/ui/founder-mobile.png",
            "api_stdout_log": "artifacts/ui/founder-api.stdout.log",
            "api_stderr_log": "artifacts/ui/founder-api.stderr.log",
            "web_stdout_log": "artifacts/ui/founder-web.stdout.log",
            "web_stderr_log": "artifacts/ui/founder-web.stderr.log",
        },
    }
    expected_flow = {
        "create": {
            "fixture_mode": "deterministic_offline",
            "provider_status": "deterministic_offline_fixture",
            "case_status": "awaiting_upload",
            "analysis_status": "awaiting_upload",
        },
        "upload": {
            "accepted_document_ids": ["doc-0001", "doc-0002"],
            "auto_start_triggered": True,
            "analysis_status": "gate2_preview_ready",
        },
        "gate2_preview": {
            "provider_mode": "deterministic_offline_fixture",
            "required_keys": ["resume_token", "preview"],
        },
        "gate2": {
            "decision": "approved",
            "analysis_status": "gate3_review_required",
        },
        "gate3": {
            "decision": "continue",
            "report_status": "ready",
        },
        "report": {
            "snapshot_id": "fixture-snapshot-001",
            "snapshot_hash": "sha256:startup-founder-frozen-v1",
            "snapshot_revision": 1,
            "freeze_status": "required",
            "pdf_status": "freeze_required",
        },
        "gate4": {
            "decision": "approved",
            "freeze_status": "approved",
            "pdf_status": "ready",
        },
        "pdf": {"content_type": "application/pdf", "header": "%PDF-1.4"},
    }
    report_snapshot: dict[str, Any] = {
        "schema": "startup_report_snapshot.v1",
        "id": "fixture-snapshot-001",
        "report_hash": "sha256:startup-founder-frozen-v1",
        "data_revision": 1,
        "as_of": "2026-08-12",
        "company": {"name": "FounderCo", "website": "https://founderco.example"},
        "sections": [
            "business_idea_summary",
            "problem_solution",
            "market_size",
            "competitors",
            "moat",
            "gtm",
            "metrics",
            "financial_assumptions",
            "risks",
            "evidence_gaps",
            "diligence_questions",
            "action_plan",
        ],
        "provider_status": "offline_fixture_active",
        "evidence": {
            "arr_usd": 1200000,
            "gross_margin": 0.72,
            "customers": 24,
            "net_revenue_retention": 1.16,
        },
    }
    return {
        "manifest.json": _json(manifest),
        "expected_flow.json": _json(expected_flow),
        "report_snapshot.json": _json(report_snapshot),
        **{f"documents/{name}": text for name, text in DOCUMENTS.items()},
    }


def write_bundle(output: Path) -> None:
    for relative, content in build_bundle().items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/startup_founder_frozen_v1"),
    )
    args = parser.parse_args()
    write_bundle(args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
