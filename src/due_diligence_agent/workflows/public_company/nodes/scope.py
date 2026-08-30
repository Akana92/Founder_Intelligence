from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from langgraph.types import interrupt

from due_diligence_agent.workflows.public_company.state import PublicCaseState


def request_scope(state: PublicCaseState) -> dict[str, object]:
    as_of = state.get("as_of") or datetime.now(UTC).isoformat()
    case_id = str(state["case_id"])
    return {
        "case_id": case_id,
        "ticker": str(state["ticker"]).strip().upper(),
        "as_of": as_of,
        "status": "awaiting_scope_approval",
        "artifact_ids": [],
        "evidence_fact_ids": [],
        "chunk_ids": [],
        "calculation_ids": [],
        "finding_ids": [],
        "contradiction_ids": [],
        "warnings": [],
        "errors": [],
        "approvals": [],
        "node_results": [],
        "reflexion_round_count": 0,
        "new_evidence_ids": [],
        "updated_finding_ids": [],
        "forced_executive_summary_contradiction_ids": [],
        "data_revision": 1,
        "final_pdf_allowed": False,
        "draft_json_artifact_ref": None,
        "draft_html_artifact_ref": None,
        "report_snapshot_id": None,
        "correlation_id": state.get("correlation_id") or str(uuid4()),
        "trace_id": state.get("trace_id") or str(uuid4()),
        "primary_failure": None,
        "normalized_collection": False,
    }


def scope_gate(state: PublicCaseState) -> dict[str, object]:
    decision = interrupt(
        {
            "status": "awaiting_scope_approval",
            "case_id": state["case_id"],
            "ticker": state["ticker"],
        }
    )
    if not isinstance(decision, dict) or decision.get("approved") is not True:
        return {
            "status": "blocked",
            "errors": ["scope:approval_denied"],
            "primary_failure": "scope:approval_denied",
        }
    return {
        "status": "running",
        "approvals": [{"gate": "scope", "approved": True}],
    }
