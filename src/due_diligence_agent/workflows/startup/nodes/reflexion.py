from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import runtime_for
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def reflexion(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    runtime = runtime_for(dependencies, state["case_id"])
    if runtime.get("gate3_recompute_started") and "reflexion" not in set(
        runtime.get("gate3_affected_nodes", [])
    ):
        return {}
    contradiction_ids = [str(item) for item in state.get("contradiction_ids", [])]
    round_number = int(state.get("reflexion_round", 0)) + 1
    result = dependencies.reflexion.review(
        case_id=state["case_id"],
        round_number=round_number,
        finding_ids=[str(item) for item in state.get("finding_ids", [])],
        contradiction_ids=contradiction_ids,
    )
    return {
        "reflexion_round": min(round_number, 2),
        "contradiction_ids": [str(item) for item in result.get("contradiction_ids", [])],
        "critic_issue_ids": [str(item) for item in result.get("critic_issue_ids", [])],
        "critic_issue_codes": [str(item) for item in result.get("critic_issue_codes", [])],
        "arbiter_status": str(result.get("arbiter_status", "unresolved")),
        "pending_gate": "startup_gate3_review",
        "status": "review_required",
    }
