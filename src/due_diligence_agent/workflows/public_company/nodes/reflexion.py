from __future__ import annotations

from typing import Any
from uuid import UUID

from due_diligence_agent.domain.common import FindingSeverity
from due_diligence_agent.workflows.public_company.nodes.collect import AuditRecorder
from due_diligence_agent.workflows.public_company.state import PublicCaseState
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus
from due_diligence_agent.workflows.shared.reflexion import ReflexionDecision, ReflexionReview


def reflexion(
    state: PublicCaseState,
    *,
    contradiction_repository: Any | None,
    finding_repository: Any | None = None,
    reviewer: Any | None = None,
    audit: AuditRecorder | None,
) -> dict[str, object]:
    case_id = UUID(state["case_id"])
    contradictions = (
        contradiction_repository.list_for_case(case_id)
        if contradiction_repository is not None
        else []
    )
    findings = finding_repository.list_for_case(case_id) if finding_repository is not None else []
    contradiction_ids = [str(contradiction.id) for contradiction in contradictions]
    forced_ids = [
        str(contradiction.id)
        for contradiction in contradictions
        if contradiction.severity is FindingSeverity.CRITICAL
    ]
    review = (
        reviewer.review(state, findings, contradictions)
        if reviewer is not None
        else ReflexionReview(
            decision=ReflexionDecision(
                continue_loop=False,
                reason="no_progress" if contradictions else "verified",
            )
        )
    )
    for replacement in review.replacement_findings:
        if finding_repository is not None:
            _add_once(finding_repository, replacement, "finding_already_exists")
    decision = review.decision
    progressed = bool(decision.new_evidence_ids or decision.updated_finding_ids)
    result: NodeResult[ReflexionDecision] = NodeResult(
        status=NodeStatus.SUCCESS, data=decision, data_refs=contradiction_ids
    )
    if audit is not None:
        audit.record("reflexion", result, dict(state))
    status = "awaiting_review" if contradiction_ids else "analysis_ready"
    return {
        "status": status,
        "contradiction_ids": contradiction_ids,
        "forced_executive_summary_contradiction_ids": forced_ids,
        "reflexion_round_count": int(state.get("reflexion_round_count", 0)) + 1,
        "reflexion_progress": progressed,
        "new_evidence_ids": decision.new_evidence_ids,
        "updated_finding_ids": decision.updated_finding_ids,
        "node_results": [
            {
                "node_name": "reflexion",
                "status": result.status.value,
                "data_refs": list(result.data_refs),
                "warnings": [],
                "errors": [],
            }
        ],
    }


def _add_once(repository: Any, item: Any, duplicate: str) -> None:
    try:
        repository.add(item)
    except ValueError as exc:
        if str(exc) != duplicate:
            raise


def synthesize_readiness(
    state: PublicCaseState, *, audit: AuditRecorder | None
) -> dict[str, object]:
    refs = list(state.get("finding_ids", [])) + list(state.get("contradiction_ids", []))
    result: NodeResult[None] = NodeResult(status=NodeStatus.SUCCESS, data_refs=refs)
    if audit is not None:
        audit.record("synthesize", result, dict(state))
    return {
        "status": "analysis_ready",
        "node_results": [
            {
                "node_name": "synthesize",
                "status": result.status.value,
                "data_refs": refs,
                "warnings": [],
                "errors": [],
            }
        ],
    }
