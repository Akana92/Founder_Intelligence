from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from due_diligence_agent.application.services.claim_evidence_service import ClaimEvidenceService
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import ClaimEvidenceMatrix, StartupClaim
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus
from due_diligence_agent.workflows.startup.runtime import save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


class StartupClaimsNodeInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    claims: tuple[StartupClaim, ...]
    evidence_facts: tuple[EvidenceFact, ...] = ()
    calculations: tuple[Calculation, ...] = ()


def build_claim_matrix_node(
    payload: StartupClaimsNodeInput,
    *,
    service: ClaimEvidenceService | None = None,
) -> NodeResult[ClaimEvidenceMatrix]:
    matrix = (service or ClaimEvidenceService()).build(
        case_id=payload.case_id,
        claims=payload.claims,
        evidence_facts=payload.evidence_facts,
        calculations=payload.calculations,
    )
    warnings = [
        "unsupported_critical_claims_present"
        for row in matrix.rows
        if not row.executive_summary_eligible
    ]
    return NodeResult(
        status=NodeStatus.SUCCESS,
        data=matrix,
        warnings=warnings[:1],
    )


def claims(state: StartupWorkflowState, *, dependencies: object) -> dict[str, object]:
    service = getattr(dependencies, "claims")
    result = service.extract(
        case_id=state["case_id"],
        evidence_fact_ids=[str(item) for item in state.get("evidence_fact_ids", [])],
    )
    contradiction_ids = list(
        dict.fromkeys(
            (
                *(str(item) for item in state.get("contradiction_ids", [])),
                *(str(item) for item in result.get("contradiction_ids", [])),
            )
        )
    )
    save_runtime(
        dependencies,
        state["case_id"],
        {
            "claim_status_by_id": result.get("claim_status_by_id", {}),
            "claim_matrix_summary": result.get("claim_matrix_summary", []),
            "contradiction_ids": contradiction_ids,
            "has_contradictions": bool(contradiction_ids),
        },
    )
    return {
        "startup_claim_ids": [str(item) for item in result.get("startup_claim_ids", [])],
        "contradiction_ids": contradiction_ids,
    }
