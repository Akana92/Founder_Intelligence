from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def parse(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    if state.get("parsed_artifact_ids"):
        return {}
    parser = dependencies.parser
    runtime = runtime_for(dependencies, state["case_id"])
    artifact_ids = [str(item) for item in runtime.get("artifact_ids", [])]
    parsed_ids: list[str] = []
    if hasattr(dependencies, "artifact_repository"):
        for artifact_id in artifact_ids:
            artifact = dependencies.artifact_repository.get(artifact_id)
            parsed = parser.parse(artifact)
            parsed_ids.append(str(getattr(parsed, "artifact_id", artifact_id)))
    else:
        result = parser.parse(
            case_id=state["case_id"],
            inventory_id=str(state["inventory_id"]),
            artifact_ids=artifact_ids,
        )
        parsed_ids = [str(item) for item in result.get("parsed_artifact_ids", [])]
    save_runtime(dependencies, state["case_id"], {"parsed_artifact_ids": parsed_ids})
    return {"parsed_artifact_ids": parsed_ids}
