from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.public_company.state import PublicCaseState
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus


def normalize_status(
    state: PublicCaseState,
    *,
    audit: Any | None,
    node_name: str = "normalize",
    final: bool = False,
) -> dict[str, object]:
    node_results = state.get("node_results", [])
    primary_failure = state.get("primary_failure")
    if primary_failure:
        status = "blocked"
    elif final or any(item.get("node_name") == "calculate" for item in node_results):
        status = "completed"
    else:
        status = "running"
    result: NodeResult[None] = NodeResult(
        status=NodeStatus.SUCCESS if status != "blocked" else NodeStatus.BLOCKED
    )
    if audit is not None:
        audit.record(node_name, result, dict(state))
    return {
        "status": status,
        "normalized_collection": True,
        "primary_failure": primary_failure,
    }


def should_continue_after_collection(state: PublicCaseState) -> str:
    if state.get("primary_failure") or state.get("status") == "blocked":
        return "end"
    return "retrieve"
