from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from due_diligence_agent.domain.findings.models import Finding
from due_diligence_agent.workflows.public_company.state import PublicCaseState


class ReflexionDecision(BaseModel):
    continue_loop: bool
    reason: Literal[
        "verified",
        "new_counter_evidence",
        "no_progress",
        "max_rounds",
        "insufficient_data",
    ]
    new_evidence_ids: list[str] = Field(default_factory=list)
    updated_finding_ids: list[str] = Field(default_factory=list)


class ReflexionReview(BaseModel):
    decision: ReflexionDecision
    replacement_findings: list[Finding] = Field(default_factory=list)


def should_continue_reflexion(state: PublicCaseState, *, max_rounds: int = 2) -> bool:
    round_count = int(state.get("reflexion_round_count", 0))
    if "reflexion_progress" in state:
        return round_count < max_rounds and bool(state.get("reflexion_progress"))
    return round_count < max_rounds and bool(
        state.get("new_evidence_ids") or state.get("updated_finding_ids")
    )
