from __future__ import annotations

from typing import Any

from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def metrics(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    runtime = runtime_for(dependencies, state["case_id"])
    if runtime.get("gate3_recompute_started") and "metrics" not in set(
        runtime.get("gate3_affected_nodes", [])
    ):
        return {}
    result = dependencies.metrics.calculate(
        case_id=state["case_id"],
        evidence_fact_ids=[
            str(item)
            for item in state.get("evidence_fact_ids", [])
            if item not in set(runtime.get("invalidated_ids", []))
        ],
    )
    save_runtime(
        dependencies,
        state["case_id"],
        {"metric_diagnostics": result.get("metric_diagnostics", [])},
    )
    calculation_ids = [str(item) for item in result.get("calculation_ids", [])]
    readiness = dependencies.readiness.evaluate(
        case_id=state["case_id"],
        profile_id=str(state.get("profile_id") or runtime.get("profile_id") or ""),
        profile_hash=str(state.get("profile_hash") or runtime.get("profile_hash") or ""),
        profile_revision=int(state.get("profile_revision") or runtime.get("profile_revision") or 0),
        metric_diagnostics=[
            dict(item)
            for item in result.get("metric_diagnostics", [])
            if isinstance(item, dict)
        ],
        calculation_ids=calculation_ids,
    )
    save_runtime(dependencies, state["case_id"], dict(readiness))
    return {
        "calculation_ids": calculation_ids,
        "readiness_snapshot_id": str(readiness["readiness_snapshot_id"]),
        "readiness_snapshot_hash": str(readiness["readiness_snapshot_hash"]),
        "readiness_snapshot_revision": int(readiness["readiness_snapshot_revision"]),
    }
