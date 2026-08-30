from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def gate4(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    snapshot_id = _required_text(state.get("report_snapshot_id"), "gate_4_report_missing")
    snapshot_hash = _required_text(state.get("report_snapshot_hash"), "gate_4_report_missing")
    snapshot_revision = state.get("report_snapshot_revision")
    if isinstance(snapshot_revision, bool) or not isinstance(snapshot_revision, int):
        raise StartupGate4DecisionError("gate_4_report_missing")

    decision = interrupt(
        {
            "status": "approval_required",
            "pending_gate": "startup_gate4_freeze",
            "case_id": state["case_id"],
            "report_snapshot_id": snapshot_id,
            "report_snapshot_hash": snapshot_hash,
            "report_snapshot_revision": snapshot_revision,
        }
    )
    if not isinstance(decision, dict):
        raise StartupGate4DecisionError("invalid_gate4_decision")
    action = str(decision.get("action") or "")
    actor = str(decision.get("actor") or "founder")
    requested_id = str(decision.get("report_snapshot_id") or "")
    requested_hash = str(decision.get("report_snapshot_hash") or "")
    requested_revision = decision.get("report_snapshot_revision")
    if action not in {"approved", "rejected"}:
        raise StartupGate4DecisionError("invalid_gate4_decision")
    if actor != "founder":
        raise StartupGate4DecisionError("invalid_gate4_actor")
    if (
        requested_id != snapshot_id
        or requested_hash != snapshot_hash
        or isinstance(requested_revision, bool)
        or requested_revision != snapshot_revision
    ):
        raise StartupGate4DecisionError("gate_4_snapshot_mismatch")

    dependencies.report.decide_gate4(
        state["case_id"],
        decision=action,
        snapshot_hash=snapshot_hash,
        snapshot_revision=snapshot_revision,
        reason=_safe_reason(decision.get("reason")),
    )
    save_runtime(
        dependencies,
        state["case_id"],
        {
            "gate4_reviewed": True,
            "gate4_last_decision": action,
        },
    )
    runtime = runtime_for(dependencies, state["case_id"])
    status = (
        "completed"
        if runtime.get("external_llm_allowed", True)
        else "completed_with_policy_blocks"
    )
    return {
        "gate4_decision": action,
        "pending_gate": None,
        "status": status,
    }


def _required_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise StartupGate4DecisionError(code)
    return value


def _safe_reason(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    safe = "".join(char if char.isalnum() or char in " _-" else " " for char in value)
    return " ".join(safe.split())[:200] or None


class StartupGate4DecisionError(RuntimeError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
