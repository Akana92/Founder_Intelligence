from __future__ import annotations

from collections.abc import Sequence
from operator import add
from typing import Annotated, Any, TypedDict


def extend_unique(left: Sequence[str], right: Sequence[str]) -> list[str]:
    result = list(left)
    for item in right:
        if item not in result:
            result.append(item)
    return result


CHECKPOINT_STATE_KEYS: tuple[str, ...] = (
    "case_id",
    "run_id",
    "correlation_id",
    "data_revision",
    "plan_id",
    "inventory_id",
    "parsed_artifact_ids",
    "sensitivity_summary_id",
    "approval_ids",
    "evidence_fact_ids",
    "startup_claim_ids",
    "document_intelligence_snapshot_id",
    "document_intelligence_snapshot_hash",
    "document_intelligence_snapshot_revision",
    "primary_profile_id",
    "profile_id",
    "profile_hash",
    "profile_revision",
    "calculation_ids",
    "readiness_snapshot_id",
    "readiness_snapshot_hash",
    "readiness_snapshot_revision",
    "market_research_snapshot_id",
    "market_research_snapshot_hash",
    "market_research_snapshot_revision",
    "product_validation_snapshot_id",
    "product_validation_snapshot_hash",
    "product_validation_snapshot_revision",
    "gtm_snapshot_id",
    "gtm_snapshot_hash",
    "gtm_snapshot_revision",
    "finding_ids",
    "contradiction_ids",
    "critic_issue_ids",
    "critic_issue_codes",
    "arbiter_status",
    "gate4_decision",
    "report_snapshot_id",
    "report_snapshot_hash",
    "report_snapshot_revision",
    "reflexion_round",
    "pending_gate",
    "status",
    "error_code",
)


class StartupWorkflowState(TypedDict, total=False):
    case_id: str
    run_id: str
    correlation_id: str
    data_revision: int
    plan_id: str | None
    inventory_id: str | None
    parsed_artifact_ids: Annotated[list[str], extend_unique]
    sensitivity_summary_id: str | None
    approval_ids: Annotated[list[str], extend_unique]
    evidence_fact_ids: Annotated[list[str], extend_unique]
    startup_claim_ids: Annotated[list[str], extend_unique]
    document_intelligence_snapshot_id: str | None
    document_intelligence_snapshot_hash: str | None
    document_intelligence_snapshot_revision: int | None
    primary_profile_id: str | None
    profile_id: str | None
    profile_hash: str | None
    profile_revision: int | None
    calculation_ids: list[str]
    readiness_snapshot_id: str | None
    readiness_snapshot_hash: str | None
    readiness_snapshot_revision: int | None
    market_research_snapshot_id: str | None
    market_research_snapshot_hash: str | None
    market_research_snapshot_revision: int | None
    product_validation_snapshot_id: str | None
    product_validation_snapshot_hash: str | None
    product_validation_snapshot_revision: int | None
    gtm_snapshot_id: str | None
    gtm_snapshot_hash: str | None
    gtm_snapshot_revision: int | None
    finding_ids: list[str]
    contradiction_ids: list[str]
    critic_issue_ids: list[str]
    critic_issue_codes: list[str]
    arbiter_status: str | None
    gate4_decision: str | None
    report_snapshot_id: str | None
    report_snapshot_hash: str | None
    report_snapshot_revision: int | None
    reflexion_round: int
    pending_gate: str | None
    status: str
    error_code: str | None
    node_results: Annotated[list[dict[str, Any]], add]
