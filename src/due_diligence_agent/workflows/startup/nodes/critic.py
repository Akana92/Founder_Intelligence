from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def critic(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    round_number = int(state.get("reflexion_round", 0)) + 1
    result = dependencies.reflexion.review_critic(
        case_id=state["case_id"],
        round_number=round_number,
        finding_ids=[str(item) for item in state.get("finding_ids", [])],
        contradiction_ids=[str(item) for item in state.get("contradiction_ids", [])],
    )
    return {
        "critic_issue_ids": [str(item) for item in result.get("critic_issue_ids", [])],
        "critic_issue_codes": [str(item) for item in result.get("critic_issue_codes", [])],
        "pending_gate": None,
        "status": "running",
    }
