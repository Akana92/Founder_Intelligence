from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def ingest(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    if state.get("inventory_id"):
        return {}
    runtime = runtime_for(dependencies, state["case_id"])
    data_room = dependencies.data_room
    result = data_room.ingest(
        case_id=state["case_id"],
        source_refs=list(runtime.get("source_refs", [])),
        data_revision=int(state.get("data_revision") or runtime.get("data_revision") or 1),
    )
    if isinstance(result, dict):
        quarantine = [
            {
                "content_hash": str(item.get("content_hash", "")),
                "reason": str(item.get("reason", "")),
                "byte_size": int(item.get("byte_size", 0)),
            }
            for item in result.get("quarantine", [])
            if isinstance(item, dict)
        ]
        save_runtime(
            dependencies,
            state["case_id"],
            {
                "artifact_ids": [str(item) for item in result.get("artifact_ids", [])],
                "quarantine": quarantine,
            },
        )
        return {
            "inventory_id": str(result["inventory_id"]),
        }
    inventory_id = getattr(result, "inventory_id", "inventory")
    accepted = getattr(result, "accepted", ())
    artifact_ids = [str(getattr(item, "id", item)) for item in accepted]
    save_runtime(dependencies, state["case_id"], {"artifact_ids": artifact_ids})
    return {
        "inventory_id": str(inventory_id),
    }
