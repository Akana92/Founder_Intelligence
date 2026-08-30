from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def product_validation(
    state: StartupWorkflowState,
    *,
    dependencies: Any,
) -> dict[str, object]:
    runtime = runtime_for(dependencies, state["case_id"])
    recomputing = bool(runtime.get("gate3_recompute_started"))
    affected = {str(item) for item in runtime.get("gate3_affected_nodes", [])}
    if recomputing and "product_validation" not in affected:
        return {}
    if state.get("product_validation_snapshot_id") and not recomputing:
        return {}
    profile_id = state.get("profile_id") or runtime.get("profile_id")
    profile_hash = state.get("profile_hash") or runtime.get("profile_hash")
    profile_revision = state.get("profile_revision") or runtime.get("profile_revision")
    if not profile_id or not profile_hash or profile_revision is None:
        raise StartupProductValidationNodeError("startup_product_validation_profile_missing")
    invalidated_ids = {str(item) for item in runtime.get("invalidated_ids", [])}
    evidence_fact_ids = [
        str(item)
        for item in state.get("evidence_fact_ids", [])
        if str(item) not in invalidated_ids
    ]
    startup_claim_ids = [
        str(item)
        for item in state.get("startup_claim_ids", [])
        if str(item) not in invalidated_ids
    ]
    raw_statuses = runtime.get("claim_status_by_id", {})
    if not isinstance(raw_statuses, dict):
        raw_statuses = {}
    claim_status_by_id = {
        str(key): str(value)
        for key, value in raw_statuses.items()
        if str(key) in startup_claim_ids
    }
    if invalidated_ids:
        claim_status_by_id = {
            claim_id: "insufficient_data" for claim_id in startup_claim_ids
        }
    result = dependencies.product_validation.evaluate(
        case_id=state["case_id"],
        profile_id=str(profile_id),
        profile_hash=str(profile_hash),
        profile_revision=int(profile_revision),
        evidence_fact_ids=evidence_fact_ids,
        startup_claim_ids=startup_claim_ids,
        claim_status_by_id=claim_status_by_id,
        contradiction_ids=[
            str(item)
            for item in state.get("contradiction_ids", [])
            if str(item) not in invalidated_ids
        ],
    )
    update = {
        "product_validation_snapshot_id": str(
            result["product_validation_snapshot_id"]
        ),
        "product_validation_snapshot_hash": str(
            result["product_validation_snapshot_hash"]
        ),
        "product_validation_snapshot_revision": int(
            result["product_validation_snapshot_revision"]
        ),
    }
    save_runtime(dependencies, state["case_id"], update)
    return update


class StartupProductValidationNodeError(RuntimeError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
