from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def disclosure(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    runtime = runtime_for(dependencies, state["case_id"])
    snapshot = runtime["disclosure_snapshot"]
    decision = interrupt(
        {
            "status": "approval_required",
            "pending_gate": "startup_disclosure",
            "case_id": state["case_id"],
            "sensitivity_summary_id": state.get("sensitivity_summary_id"),
        }
    )
    if not isinstance(decision, dict):
        decision = {"action": "denied", "actor": "founder", "destination": "openai.responses"}
    action = str(decision.get("action", "denied"))
    if action not in {"approved", "denied"}:
        raise StartupDisclosureNodeError("startup_disclosure_invalid_decision")
    if action == "denied" or SensitivityClass.RESTRICTED in snapshot.detected_classes:
        save_runtime(
            dependencies,
            state["case_id"],
            {
                "external_llm_allowed": False,
                "disclosure_scope": None,
                "approval_ids": [],
            },
        )
        return {
            "approval_ids": [],
            "pending_gate": None,
            "status": "running",
        }
    try:
        approval = dependencies.disclosure.decide(
            snapshot,
            action=action,
            actor=str(decision.get("actor", "founder")),
            destination=str(decision.get("destination", "openai.responses")),
        )
    except ValueError as exc:
        raise StartupDisclosureNodeError("startup_disclosure_decision_failed") from exc
    external_allowed = bool(getattr(approval, "external_llm_allowed", False))
    scope = dependencies.disclosure.resolve_scope(snapshot) if external_allowed else None
    external_allowed = scope is not None
    dependencies._startup_disclosure_scope = scope
    save_runtime(
        dependencies,
        state["case_id"],
        {
            "external_llm_allowed": external_allowed,
            "disclosure_scope": scope,
            "approval_ids": [str(getattr(approval, "id"))],
        },
    )
    return {
        "approval_ids": [str(getattr(approval, "id"))],
        "pending_gate": None,
        "status": "running",
    }


class StartupDisclosureNodeError(RuntimeError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
