from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.nodes.financial import _llm_node
from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def market_research(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    runtime = runtime_for(dependencies, state["case_id"])
    if runtime.get("gate3_recompute_started") and "market_research" not in set(
        runtime.get("gate3_affected_nodes", [])
    ):
        return {}
    result = dependencies.market_research.research(
        case_id=state["case_id"],
        profile_id=str(state.get("profile_id") or runtime.get("profile_id") or ""),
        profile_hash=str(state.get("profile_hash") or runtime.get("profile_hash") or ""),
        profile_revision=int(state.get("profile_revision") or runtime.get("profile_revision") or 0),
    )
    update = {
        "market_research_snapshot_id": str(result["market_research_snapshot_id"]),
        "market_research_snapshot_hash": str(result["market_research_snapshot_hash"]),
        "market_research_snapshot_revision": int(result["market_research_snapshot_revision"]),
    }
    save_runtime(dependencies, state["case_id"], update)
    return update


def market_analysis(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    runtime = runtime_for(dependencies, state["case_id"])
    if not (state.get("market_research_snapshot_id") or runtime.get("market_research_snapshot_id")):
        raise StartupMarketResearchNodeError("startup_market_research_missing")
    return _llm_node("market_analysis", state, dependencies)


class StartupMarketResearchNodeError(RuntimeError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
