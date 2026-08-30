from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from due_diligence_agent.workflows.startup.graph import (
    StartupGraphDependencies,
    build_startup_graph,
    startup_checkpoint_state_hash,
)


class StartupAnalysisService:
    """Application facade for the resumable startup data-room workflow."""

    checkpoint_identity_required_for_resume = True

    def __init__(self, *, dependencies: StartupGraphDependencies, checkpoint_path: Path) -> None:
        self._dependencies = dependencies
        self._checkpoint_path = checkpoint_path

    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        with SqliteSaver.from_conn_string(str(self._checkpoint_path)) as saver:
            graph = build_startup_graph(self._dependencies, checkpointer=saver)
            return cast(dict[str, Any], graph.invoke(payload, _config(thread_id)))

    def resume(self, approval: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        with SqliteSaver.from_conn_string(str(self._checkpoint_path)) as saver:
            graph = build_startup_graph(self._dependencies, checkpointer=saver)
            return cast(
                dict[str, Any],
                graph.invoke(Command(resume=approval), _config(thread_id)),
            )

    def checkpoint_identity(self, *, thread_id: str) -> dict[str, Any] | None:
        with SqliteSaver.from_conn_string(str(self._checkpoint_path)) as saver:
            graph = build_startup_graph(self._dependencies, checkpointer=saver)
            snapshot = graph.get_state(_config(thread_id))
        values = snapshot.values if isinstance(snapshot.values, dict) else {}
        config = snapshot.config if isinstance(snapshot.config, dict) else {}
        configurable = config.get("configurable")
        if not isinstance(configurable, dict):
            return None
        checkpoint_id = configurable.get("checkpoint_id")
        snapshot_thread_id = configurable.get("thread_id")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            return None
        if not isinstance(snapshot_thread_id, str) or snapshot_thread_id != thread_id:
            return None
        data_revision = values.get("data_revision")
        if type(data_revision) is not int or data_revision < 1:
            return None
        return {
            "checkpoint_hash": startup_checkpoint_state_hash(values),
            "checkpoint_id": checkpoint_id,
            "data_revision": data_revision,
            "thread_id": thread_id,
        }


def _config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}
