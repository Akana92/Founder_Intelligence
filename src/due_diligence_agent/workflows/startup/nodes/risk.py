from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.nodes.financial import _llm_node
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def risk_analysis(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    return _llm_node("risk_analysis", state, dependencies)
