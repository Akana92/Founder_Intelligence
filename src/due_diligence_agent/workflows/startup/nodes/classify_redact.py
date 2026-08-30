from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def classify_redact(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    if state.get("sensitivity_summary_id"):
        return {}
    result = dependencies.privacy.classify_redact(
        case_id=state["case_id"],
        data_revision=int(state["data_revision"]),
        parsed_artifact_ids=[str(item) for item in state.get("parsed_artifact_ids", [])],
        raw_payload=None,
    )
    snapshot = result.get("snapshot")
    if snapshot is not None:
        dependencies.disclosure.build_preview(snapshot)
        runtime_update = {"disclosure_snapshot": snapshot}
        if result.get("privacy_fail_closed_code"):
            runtime_update["privacy_fail_closed_code"] = str(result["privacy_fail_closed_code"])
            runtime_update["privacy_fail_closed_reason"] = str(
                result.get("privacy_fail_closed_reason", "unknown")
            )
        save_runtime(dependencies, state["case_id"], runtime_update)
    return {
        "sensitivity_summary_id": str(result["sensitivity_summary_id"]),
        "status": "running",
        "pending_gate": None,
    }
