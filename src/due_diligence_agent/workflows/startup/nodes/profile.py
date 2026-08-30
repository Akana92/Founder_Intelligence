from __future__ import annotations

from typing import Any
from uuid import UUID

from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def primary_profile(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    if state.get("primary_profile_id"):
        return {}
    profile = dependencies.profile.build_primary(case_id=UUID(str(state["case_id"])))
    update = _profile_update(profile, primary_profile_id=True)
    save_runtime(
        dependencies,
        str(state["case_id"]),
        {
            "primary_profile_id": update["primary_profile_id"],
            "profile_id": update["profile_id"],
            "profile_hash": update["profile_hash"],
            "profile_revision": update["profile_revision"],
        },
    )
    return update


def profile_enrichment(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    runtime = runtime_for(dependencies, str(state["case_id"]))
    primary_profile_id = state.get("primary_profile_id") or runtime.get("primary_profile_id")
    if not primary_profile_id:
        raise StartupProfileNodeError("startup_profile_primary_missing")
    scope = getattr(dependencies, "_startup_disclosure_scope", None) or runtime.get(
        "disclosure_scope"
    )
    if not runtime.get("external_llm_allowed") or scope is None:
        return {}
    profile = dependencies.profile.enrich(
        case_id=UUID(str(state["case_id"])),
        primary_profile_id=UUID(str(primary_profile_id)),
        disclosure_scope=scope,
    )
    update = _profile_update(profile, primary_profile_id=False)
    save_runtime(
        dependencies,
        str(state["case_id"]),
        {
            "profile_id": update["profile_id"],
            "profile_hash": update["profile_hash"],
            "profile_revision": update["profile_revision"],
        },
    )
    return update


class StartupProfileNodeError(RuntimeError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _profile_update(profile: Any, *, primary_profile_id: bool) -> dict[str, object]:
    profile_id = str(_value(profile, "profile_id"))
    update: dict[str, object] = {
        "profile_id": profile_id,
        "profile_hash": str(_value(profile, "profile_hash")),
        "profile_revision": int(str(_value(profile, "data_revision"))),
    }
    if primary_profile_id:
        update["primary_profile_id"] = profile_id
    return update


def _value(profile: Any, name: str) -> object:
    if isinstance(profile, dict):
        return profile[name]
    return getattr(profile, name)
