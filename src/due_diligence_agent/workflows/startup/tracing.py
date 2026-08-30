from __future__ import annotations

from typing import Any, Final, Protocol


class StartupNodeTracer(Protocol):
    def record(self, **attributes: Any) -> None: ...


STARTUP_NODE_AGENT_ROLES: Final[dict[str, str]] = {
    "initialize": "orchestration",
    "ingest": "data_room",
    "parse": "document",
    "classify_redact": "privacy",
    "disclosure": "privacy",
    "plan": "orchestration",
    "evidence": "evidence",
    "claims": "evidence",
    "document_intelligence": "document",
    "primary_profile": "profile",
    "profile_enrichment": "profile",
    "product_validation": "product",
    "market_research": "market",
    "metrics": "metrics",
    "financial_analysis": "finance",
    "risk_analysis": "risk",
    "market_analysis": "market",
    "gtm": "gtm",
    "critic": "critic",
    "arbiter": "arbiter",
    "report": "report",
    "gate4": "report",
}


def startup_agent_role(node_name: str) -> str:
    return STARTUP_NODE_AGENT_ROLES.get(node_name, "orchestration")


class CompositeNodeTracer:
    def __init__(self, *tracers: StartupNodeTracer | None) -> None:
        self._tracers = tuple(tracer for tracer in tracers if tracer is not None)

    def record(self, **attributes: Any) -> None:
        for tracer in self._tracers:
            tracer.record(**attributes)

    def record_checkpoint_keys(self, keys: set[str]) -> None:
        for tracer in self._tracers:
            method = getattr(tracer, "record_checkpoint_keys", None)
            if callable(method):
                method(set(keys))

    def flush(self) -> None:
        for tracer in self._tracers:
            method = getattr(tracer, "flush", None)
            if callable(method):
                method()
