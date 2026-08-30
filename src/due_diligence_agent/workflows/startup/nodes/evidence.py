from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def evidence(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    result = dependencies.evidence.extract(
        case_id=state["case_id"],
        parsed_artifact_ids=[str(item) for item in state.get("parsed_artifact_ids", [])],
    )
    evidence_fact_ids = [str(item) for item in result.get("evidence_fact_ids", [])]
    contradiction_ids = list(
        dict.fromkeys(str(item) for item in result.get("contradiction_ids", []))
    )
    lineage = dependencies.lineage.derive(
        case_id=state["case_id"],
        evidence_fact_ids=evidence_fact_ids,
    )
    edges = {
        str(key): [str(item) for item in value]
        for key, value in lineage.get("dependency_edges", {}).items()
    }
    node_edges = {
        str(key): [str(item) for item in value]
        for key, value in lineage.get("dependency_node_edges", {}).items()
    }
    save_runtime(
        dependencies,
        state["case_id"],
        {"dependency_edges": edges, "dependency_node_edges": node_edges},
    )
    return {
        "evidence_fact_ids": evidence_fact_ids,
        "contradiction_ids": contradiction_ids,
    }
