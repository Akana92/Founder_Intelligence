from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


_GTM_UPSTREAM_NODES = {
    "product_validation",
    "market_research",
    "financial_analysis",
    "risk_analysis",
    "market_analysis",
}


def gtm(
    state: StartupWorkflowState,
    *,
    dependencies: Any,
) -> dict[str, object]:
    runtime = runtime_for(dependencies, state["case_id"])
    recomputing = bool(runtime.get("gate3_recompute_started"))
    affected = {str(item) for item in runtime.get("gate3_affected_nodes", [])}
    if recomputing and "gtm" not in affected and not (_GTM_UPSTREAM_NODES & affected):
        return {}
    if state.get("gtm_snapshot_id") and not recomputing:
        return {}

    profile_id = state.get("profile_id") or runtime.get("profile_id")
    profile_hash = state.get("profile_hash") or runtime.get("profile_hash")
    profile_revision = state.get("profile_revision") or runtime.get("profile_revision")
    product_snapshot_id = state.get("product_validation_snapshot_id") or runtime.get(
        "product_validation_snapshot_id"
    )
    product_snapshot_hash = state.get("product_validation_snapshot_hash") or runtime.get(
        "product_validation_snapshot_hash"
    )
    product_snapshot_revision = state.get(
        "product_validation_snapshot_revision"
    ) or runtime.get("product_validation_snapshot_revision")
    market_snapshot_id = state.get("market_research_snapshot_id") or runtime.get(
        "market_research_snapshot_id"
    )
    market_snapshot_hash = state.get("market_research_snapshot_hash") or runtime.get(
        "market_research_snapshot_hash"
    )
    market_snapshot_revision = state.get("market_research_snapshot_revision") or runtime.get(
        "market_research_snapshot_revision"
    )
    if not profile_id or not profile_hash or profile_revision is None:
        raise StartupGtmNodeError("startup_gtm_profile_missing")
    if (
        not product_snapshot_id
        or not product_snapshot_hash
        or product_snapshot_revision is None
    ):
        raise StartupGtmNodeError("startup_gtm_product_validation_missing")
    if not market_snapshot_id or not market_snapshot_hash or market_snapshot_revision is None:
        raise StartupGtmNodeError("startup_gtm_market_research_missing")

    invalidated_ids = {str(item) for item in runtime.get("invalidated_ids", [])}
    result = dependencies.gtm.evaluate(
        case_id=state["case_id"],
        profile_id=str(profile_id),
        profile_hash=str(profile_hash),
        profile_revision=int(profile_revision),
        product_validation_snapshot_id=str(product_snapshot_id),
        product_validation_snapshot_hash=str(product_snapshot_hash),
        product_validation_snapshot_revision=int(product_snapshot_revision),
        market_research_snapshot_id=str(market_snapshot_id),
        market_research_snapshot_hash=str(market_snapshot_hash),
        market_research_snapshot_revision=int(market_snapshot_revision),
        evidence_fact_ids=[
            str(item)
            for item in state.get("evidence_fact_ids", [])
            if str(item) not in invalidated_ids
        ],
        finding_ids=[
            str(item)
            for item in state.get("finding_ids", [])
            if str(item) not in invalidated_ids
        ],
        contradiction_ids=[
            str(item)
            for item in state.get("contradiction_ids", [])
            if str(item) not in invalidated_ids
        ],
    )
    update = {
        "gtm_snapshot_id": str(result["gtm_snapshot_id"]),
        "gtm_snapshot_hash": str(result["gtm_snapshot_hash"]),
        "gtm_snapshot_revision": int(result["gtm_snapshot_revision"]),
    }
    save_runtime(dependencies, state["case_id"], update)
    return update


class StartupGtmNodeError(RuntimeError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
