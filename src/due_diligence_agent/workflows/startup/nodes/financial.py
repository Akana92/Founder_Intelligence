from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import runtime_for
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def financial_analysis(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    return _llm_node("financial_analysis", state, dependencies)


def _llm_node(node_name: str, state: StartupWorkflowState, dependencies: Any) -> dict[str, object]:
    runtime = runtime_for(dependencies, state["case_id"])
    if runtime.get("gate3_recompute_started") and node_name not in set(
        runtime.get("gate3_affected_nodes", [])
    ):
        return {}
    scope = getattr(dependencies, "_startup_disclosure_scope", None) or runtime.get(
        "disclosure_scope"
    )
    if not runtime.get("external_llm_allowed") or scope is None:
        return {
            "_node_status": "blocked",
            "warnings": [f"{node_name}:blocked_by_policy"],
            "_node_errors": ["blocked_by_policy:startup_disclosure"],
        }
    invalidated_ids = [str(item) for item in runtime.get("invalidated_ids", [])]
    result = dependencies.provider.analyze(
        case_id=str(state["case_id"]),
        node_name=node_name,
        disclosure_scope=scope,
        remaining_evidence_fact_ids=[
            str(item)
            for item in state.get("evidence_fact_ids", [])
            if str(item) not in set(invalidated_ids)
        ],
        remaining_calculation_ids=[
            str(item)
            for item in state.get("calculation_ids", [])
            if str(item) not in set(invalidated_ids)
        ],
        invalidated_ids=invalidated_ids,
    )
    return {
        "finding_ids": [
            str(item)
            for item in result.get("finding_ids", [])
            if str(item) not in set(invalidated_ids)
        ]
    }
