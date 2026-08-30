from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def document_intelligence(
    state: StartupWorkflowState,
    *,
    dependencies: Any,
) -> dict[str, object]:
    if state.get("document_intelligence_snapshot_id"):
        return {}
    runtime = runtime_for(dependencies, state["case_id"])
    quarantine_reason_codes = [
        str(item.get("reason"))
        for item in runtime.get("quarantine", [])
        if isinstance(item, dict) and item.get("reason")
    ]
    result = dependencies.document_intelligence.analyze(
        case_id=state["case_id"],
        data_revision=int(state.get("data_revision") or runtime.get("data_revision") or 1),
        inventory_id=str(state.get("inventory_id") or ""),
        source_document_ids=[
            str(item) for item in runtime.get("source_document_ids", [])
        ],
        artifact_ids=[str(item) for item in runtime.get("artifact_ids", [])],
        parsed_artifact_ids=[
            str(item) for item in state.get("parsed_artifact_ids", [])
        ],
        evidence_fact_ids=[str(item) for item in state.get("evidence_fact_ids", [])],
        startup_claim_ids=[str(item) for item in state.get("startup_claim_ids", [])],
        quarantine_reason_codes=quarantine_reason_codes,
    )
    update = {
        "document_intelligence_snapshot_id": str(
            result["document_intelligence_snapshot_id"]
        ),
        "document_intelligence_snapshot_hash": str(
            result["document_intelligence_snapshot_hash"]
        ),
        "document_intelligence_snapshot_revision": int(
            result["document_intelligence_snapshot_revision"]
        ),
    }
    save_runtime(dependencies, state["case_id"], update)
    return update
