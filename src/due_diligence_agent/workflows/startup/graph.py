from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
import json
import re
from time import perf_counter
from typing import Any, Protocol, cast

from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus
from due_diligence_agent.workflows.startup.nodes.claims import claims
from due_diligence_agent.workflows.startup.nodes.critic import critic
from due_diligence_agent.workflows.startup.nodes.classify_redact import classify_redact
from due_diligence_agent.workflows.startup.nodes.disclosure import disclosure
from due_diligence_agent.workflows.startup.nodes.document_intelligence import (
    document_intelligence,
)
from due_diligence_agent.workflows.startup.nodes.evidence import evidence
from due_diligence_agent.workflows.startup.nodes.financial import financial_analysis
from due_diligence_agent.workflows.startup.nodes.ingest import ingest
from due_diligence_agent.workflows.startup.nodes.gtm import gtm
from due_diligence_agent.workflows.startup.nodes.gate4 import gate4
from due_diligence_agent.workflows.startup.nodes.market import market_analysis, market_research
from due_diligence_agent.workflows.startup.nodes.metrics import metrics
from due_diligence_agent.workflows.startup.nodes.parse import parse
from due_diligence_agent.workflows.startup.nodes.profile import primary_profile, profile_enrichment
from due_diligence_agent.workflows.startup.nodes.product_validation import product_validation
from due_diligence_agent.workflows.startup.nodes.arbiter import arbiter
from due_diligence_agent.workflows.startup.nodes.report import report
from due_diligence_agent.workflows.startup.nodes.risk import risk_analysis
from due_diligence_agent.workflows.startup.plan import STARTUP_PLAN_ID, default_startup_plan
from due_diligence_agent.workflows.startup.runtime import (
    ensure_runtime,
    runtime_for,
    save_runtime,
)
from due_diligence_agent.workflows.startup.state import CHECKPOINT_STATE_KEYS, StartupWorkflowState
from due_diligence_agent.workflows.startup.tracing import startup_agent_role


class StartupGraphDependencies(Protocol):
    data_room: Any
    parser: Any
    privacy: Any
    disclosure: Any
    evidence: Any
    lineage: Any
    claims: Any
    document_intelligence: Any
    profile: Any
    metrics: Any
    readiness: Any
    market_research: Any
    product_validation: Any
    gtm: Any
    provider: Any
    reflexion: Any
    report: Any
    gate3: Any
    audit: Any | None
    tracer: Any | None
    workflow_store: Any
    _startup_disclosure_scope: DisclosureScope | None


NodeCallable = Callable[..., dict[str, object]]

_LOCAL_PROVIDER_FALLBACKS = {
    "financial_analysis": "local_calculations",
    "risk_analysis": "local_evidence",
    "market_analysis": "cached_local_market_research",
}
_LOCAL_PROVIDER_FALLBACK_ERROR_CODES = frozenset(
    {
        "BUDGET_EXCEEDED",
        "STARTUP_PROVIDER_BRIDGE_TIMEOUT",
        "STARTUP_PROVIDER_CONTEXT_LIMIT",
        "provider_unavailable",
        "startup_provider_not_configured",
        "startup_provider_outage",
    }
)


def build_startup_graph(dependencies: StartupGraphDependencies, *, checkpointer: Any) -> Any:
    ensure_runtime(dependencies)
    graph = StateGraph(StartupWorkflowState)

    graph.add_node("initialize", lambda state: _initialize(state, dependencies))
    graph.add_node("ingest", _guarded("ingest", ingest, dependencies))  # type: ignore[arg-type]
    graph.add_node("parse", _guarded("parse", parse, dependencies))  # type: ignore[arg-type]
    graph.add_node("classify_redact", _guarded("classify_redact", classify_redact, dependencies))  # type: ignore[arg-type]
    graph.add_node("disclosure", _guarded("disclosure", disclosure, dependencies))  # type: ignore[arg-type]
    graph.add_node("plan", lambda state: _plan_node(state, dependencies))
    graph.add_node("evidence", _guarded("evidence", evidence, dependencies))  # type: ignore[arg-type]
    graph.add_node("claims", _guarded("claims", claims, dependencies))  # type: ignore[arg-type]
    graph.add_node("document_intelligence", _guarded("document_intelligence", document_intelligence, dependencies))  # type: ignore[arg-type]
    graph.add_node("primary_profile", _guarded("primary_profile", primary_profile, dependencies))  # type: ignore[arg-type]
    graph.add_node("profile_enrichment", _guarded("profile_enrichment", profile_enrichment, dependencies))  # type: ignore[arg-type]
    graph.add_node("product_validation", _guarded("product_validation", product_validation, dependencies))  # type: ignore[arg-type]
    graph.add_node("market_research", _guarded("market_research", market_research, dependencies))  # type: ignore[arg-type]
    graph.add_node("metrics", _guarded("metrics", metrics, dependencies))  # type: ignore[arg-type]
    graph.add_node("financial_analysis", _guarded("financial_analysis", financial_analysis, dependencies))  # type: ignore[arg-type]
    graph.add_node("risk_analysis", _guarded("risk_analysis", risk_analysis, dependencies))  # type: ignore[arg-type]
    graph.add_node("market_analysis", _guarded("market_analysis", market_analysis, dependencies))  # type: ignore[arg-type]
    graph.add_node("gtm", _guarded("gtm", gtm, dependencies))  # type: ignore[arg-type]
    graph.add_node("critic", _guarded("critic", critic, dependencies))  # type: ignore[arg-type]
    graph.add_node("arbiter", _guarded("arbiter", arbiter, dependencies))  # type: ignore[arg-type]
    graph.add_node("report", _guarded("report", report, dependencies))  # type: ignore[arg-type]
    graph.add_node("gate4", _guarded("gate4", gate4, dependencies))  # type: ignore[arg-type]

    graph.add_edge(START, "initialize")
    graph.add_conditional_edges(
        "initialize",
        lambda state: "end" if state.get("status") == "failed" else "ingest",
        {"ingest": "ingest", "end": END},
    )
    graph.add_conditional_edges(
        "ingest",
        _continue_or_end("parse"),
        {"parse": "parse", "end": END},
    )
    graph.add_conditional_edges(
        "parse",
        _continue_or_end("classify_redact"),
        {"classify_redact": "classify_redact", "end": END},
    )
    graph.add_conditional_edges(
        "classify_redact",
        _continue_or_end("evidence"),
        {"evidence": "evidence", "end": END},
    )
    graph.add_conditional_edges(
        "evidence",
        _continue_or_end("claims"),
        {"claims": "claims", "end": END},
    )
    graph.add_conditional_edges(
        "claims",
        _continue_or_end("document_intelligence"),
        {"document_intelligence": "document_intelligence", "end": END},
    )
    graph.add_conditional_edges(
        "document_intelligence",
        _continue_or_end("primary_profile"),
        {"primary_profile": "primary_profile", "end": END},
    )
    graph.add_conditional_edges(
        "primary_profile",
        _continue_or_end("disclosure"),
        {"disclosure": "disclosure", "end": END},
    )
    graph.add_conditional_edges(
        "disclosure",
        _continue_or_end("plan"),
        {"plan": "plan", "end": END},
    )
    graph.add_edge("plan", "profile_enrichment")
    graph.add_edge("profile_enrichment", "product_validation")
    graph.add_edge("product_validation", "metrics")
    graph.add_edge("product_validation", "market_research")
    graph.add_edge("metrics", "financial_analysis")
    graph.add_edge("financial_analysis", "risk_analysis")
    graph.add_edge(["risk_analysis", "market_research"], "market_analysis")
    graph.add_edge("market_analysis", "gtm")
    graph.add_edge("gtm", "critic")
    graph.add_edge("critic", "arbiter")
    graph.add_conditional_edges(
        "arbiter",
        lambda state: "critic"
        if _should_continue_reflexion(state, dependencies)
        else "report",
        {"critic": "critic", "report": "report"},
    )
    graph.add_conditional_edges(
        "report",
        _route_after_report(dependencies),
        {
            "product_validation": "product_validation",
            "metrics": "metrics",
            "market_research": "market_research",
            "financial_analysis": "financial_analysis",
            "risk_analysis": "risk_analysis",
            "market_analysis": "market_analysis",
            "gtm": "gtm",
            "critic": "critic",
            "report": "report",
            "gate4": "gate4",
            "end": END,
        },
    )
    graph.add_edge("gate4", END)
    return StartupGraph(graph.compile(checkpointer=checkpointer), dependencies=dependencies)


class StartupGraph:
    def __init__(self, graph: Any, *, dependencies: StartupGraphDependencies) -> None:
        self._graph = graph
        self._dependencies = dependencies

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> dict[str, Any]:
        safe_input = _prepare_safe_input(input, self._dependencies)
        result = self._graph.invoke(safe_input, config=config, **kwargs)
        if not isinstance(result, dict):
            return cast(dict[str, Any], result)
        return _with_runtime_result(result, self._dependencies)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> dict[str, Any]:
        safe_input = _prepare_safe_input(input, self._dependencies)
        result = await self._graph.ainvoke(safe_input, config=config, **kwargs)
        if not isinstance(result, dict):
            return cast(dict[str, Any], result)
        return _with_runtime_result(result, self._dependencies)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)


def _initialize(
    state: StartupWorkflowState,
    dependencies: StartupGraphDependencies,
) -> dict[str, object]:
    if state.get("status") is not None:
        return {}
    case_id = str(state["case_id"])
    dependencies._startup_disclosure_scope = None
    save_runtime(
        dependencies,
        case_id,
        {
            "node_results": [],
            "warnings": [],
            "invalidated_ids": [],
            "gate3_reviewed": False,
            "gate3_exclusions": [],
            "gate3_recompute_started": False,
            "gate3_report_finalized": False,
            "gate3_affected_nodes": [],
            "gate3_invalidation_chain": [],
            "last_reflexion_contradictions": [],
            "gate4_reviewed": False,
            "gate4_last_decision": None,
        },
    )
    _record_checkpoint_keys(dependencies)
    update: dict[str, object] = {
        "case_id": case_id,
        "run_id": str(state.get("run_id") or f"startup-{case_id}"),
        "correlation_id": str(state.get("correlation_id") or f"case-{case_id}"),
        "data_revision": int(state.get("data_revision") or 1),
        "plan_id": None,
        "inventory_id": None,
        "parsed_artifact_ids": [],
        "sensitivity_summary_id": None,
        "approval_ids": [],
        "evidence_fact_ids": [],
        "startup_claim_ids": [],
        "document_intelligence_snapshot_id": None,
        "document_intelligence_snapshot_hash": None,
        "document_intelligence_snapshot_revision": None,
        "primary_profile_id": None,
        "profile_id": None,
        "profile_hash": None,
        "profile_revision": None,
        "calculation_ids": [],
        "readiness_snapshot_id": None,
        "readiness_snapshot_hash": None,
        "readiness_snapshot_revision": None,
        "market_research_snapshot_id": None,
        "market_research_snapshot_hash": None,
        "market_research_snapshot_revision": None,
        "product_validation_snapshot_id": None,
        "product_validation_snapshot_hash": None,
        "product_validation_snapshot_revision": None,
        "gtm_snapshot_id": None,
        "gtm_snapshot_hash": None,
        "gtm_snapshot_revision": None,
        "finding_ids": [],
        "contradiction_ids": [],
        "critic_issue_ids": [],
        "critic_issue_codes": [],
        "arbiter_status": None,
        "gate4_decision": None,
        "report_snapshot_id": None,
        "report_snapshot_hash": None,
        "report_snapshot_revision": None,
        "reflexion_round": 0,
        "pending_gate": None,
        "status": "running",
        "error_code": None,
    }
    _record_node(
        "initialize",
        NodeResult[None](status=NodeStatus.SUCCESS),
        {**state, **update},
        dependencies,
        duration_ms=0,
        retry_count=0,
    )
    return update


def _plan_node(
    state: StartupWorkflowState,
    dependencies: StartupGraphDependencies,
) -> dict[str, object]:
    plan = default_startup_plan()
    _record_node(
        "plan",
        NodeResult(status=NodeStatus.SUCCESS, data_refs=[step.task_id for step in plan.steps]),
        state,
        dependencies,
        duration_ms=0,
        retry_count=0,
    )
    return {"plan_id": STARTUP_PLAN_ID}


def _guarded(
    node_name: str,
    func: NodeCallable,
    dependencies: StartupGraphDependencies,
) -> Callable[[StartupWorkflowState], dict[str, object]]:
    def run(state: StartupWorkflowState) -> dict[str, object]:
        if state.get("status") == "failed":
            return {}
        attempts = 0
        while attempts < 3:
            attempts += 1
            started = perf_counter()
            try:
                update = func(state, dependencies=dependencies)
                duration_ms = int((perf_counter() - started) * 1000)
                update = _merge_accumulative_fields(state, update)
                status = NodeStatus(str(update.pop("_node_status", NodeStatus.SUCCESS.value)))
                raw_errors = update.pop("_node_errors", [])
                errors = [str(item) for item in raw_errors] if isinstance(raw_errors, list) else []
                raw_warnings = update.pop("_node_warnings", [])
                warnings = (
                    [str(item) for item in raw_warnings]
                    if isinstance(raw_warnings, list)
                    else []
                )
                raw_fallback = update.pop("_node_fallback_used", None)
                fallback_used = str(raw_fallback) if isinstance(raw_fallback, str) else None
                refs = _refs_from_update(update)
                result = NodeResult[None](
                    status=status,
                    data_refs=refs,
                    warnings=warnings,
                    errors=errors,
                    fallback_used=fallback_used,
                )
                _record_node(
                    node_name,
                    result,
                    {**state, **update},
                    dependencies,
                    duration_ms=duration_ms,
                    retry_count=attempts - 1,
                    attempt_count=attempts,
                )
                return update
            except Exception as exc:
                if isinstance(exc, GraphInterrupt):
                    raise
                if _is_retryable(exc) and attempts < 3:
                    result = NodeResult[None](
                        status=NodeStatus.RETRYABLE_ERROR,
                        errors=[_safe_error_code(exc)],
                    )
                    _record_node(
                        node_name,
                        result,
                        state,
                        dependencies,
                        duration_ms=int((perf_counter() - started) * 1000),
                        retry_count=attempts,
                        attempt_count=attempts,
                        durable=False,
                    )
                    continue
                code = _safe_error_code(exc)
                fallback_used = _local_provider_fallback(node_name, exc)
                if fallback_used is not None:
                    result = NodeResult[None](
                        status=NodeStatus.PARTIAL,
                        warnings=[f"{node_name}:replanned_to_local_evidence"],
                        errors=[code],
                        fallback_used=fallback_used,
                    )
                    update = {"finding_ids": []}
                    update = _merge_accumulative_fields(state, update)
                    _record_node(
                        node_name,
                        result,
                        {**state, **update},
                        dependencies,
                        duration_ms=int((perf_counter() - started) * 1000),
                        retry_count=attempts - 1,
                        attempt_count=attempts,
                    )
                    return update
                result = NodeResult[None](status=NodeStatus.FAILED, errors=[code])
                update = {
                    "status": "failed",
                    "error_code": code if not _is_unexpected(exc) else "workflow_unexpected",
                    "pending_gate": None,
                }
                _record_node(
                    node_name,
                    result,
                    {**state, **update},
                    dependencies,
                    duration_ms=int((perf_counter() - started) * 1000),
                    retry_count=attempts - 1,
                    attempt_count=attempts,
                )
                return update
        return {"status": "failed", "error_code": "retry_exhausted", "pending_gate": None}

    return run


def _continue_or_end(next_node: str) -> Callable[[StartupWorkflowState], str]:
    def route(state: StartupWorkflowState) -> str:
        return "end" if state.get("status") == "failed" else next_node

    return route


def _route_after_report(
    dependencies: StartupGraphDependencies,
) -> Callable[[StartupWorkflowState], str | list[str]]:
    def route(state: StartupWorkflowState) -> str | list[str]:
        runtime = runtime_for(dependencies, str(state.get("case_id", "")))
        if state.get("status") == "running" and runtime.get("gate3_recompute_started") and not runtime.get(
            "gate3_report_finalized"
        ):
            affected = set(runtime.get("gate3_affected_nodes", []))
            if "product_validation" in affected:
                return "product_validation"
            if "metrics" in affected:
                return ["metrics", "market_research"]
            if "financial_analysis" in affected:
                return ["financial_analysis", "market_research"]
            if "risk_analysis" in affected:
                return ["risk_analysis", "market_research"]
            if "market_research" in affected:
                return ["risk_analysis", "market_research"]
            for node_name in ("market_analysis", "gtm"):
                if node_name in affected:
                    return node_name
            if affected.intersection({"critic", "arbiter", "reflexion"}):
                return "critic"
            return "report"
        if (
            state.get("status") == "approval_required"
            and state.get("pending_gate") == "startup_gate4_freeze"
        ):
            return "gate4"
        return "end"

    return route


def _should_continue_reflexion(
    state: StartupWorkflowState,
    dependencies: StartupGraphDependencies,
) -> bool:
    if int(state.get("reflexion_round", 0)) >= 2:
        return False
    if not state.get("contradiction_ids"):
        return False
    runtime = runtime_for(dependencies, state["case_id"])
    previous = runtime.get("last_reflexion_contradictions")
    current = tuple(state.get("contradiction_ids", []))
    runtime["last_reflexion_contradictions"] = current
    save_runtime(dependencies, state["case_id"], {"last_reflexion_contradictions": current})
    return previous != current or int(state.get("reflexion_round", 0)) < 2


def _record_node(
    node_name: str,
    result: NodeResult[Any],
    state: StartupWorkflowState | dict[str, Any],
    dependencies: StartupGraphDependencies,
    *,
    duration_ms: int,
    retry_count: int,
    attempt_count: int = 1,
    durable: bool = True,
) -> None:
    case_id = str(state.get("case_id", "unknown"))
    runtime = runtime_for(dependencies, case_id)
    compact = {
        "node_name": node_name,
        "status": result.status.value,
        "data_refs": [str(item) for item in result.data_refs],
        "warnings": [str(item) for item in result.warnings],
        "errors": [str(item) for item in result.errors],
        "fallback_used": result.fallback_used,
        "attempt_count": attempt_count,
        "retry_count": retry_count,
    }
    if durable:
        retained = [
            item
            for item in runtime.get("node_results", [])
            if not (isinstance(item, dict) and item.get("node_name") == node_name)
        ]
        retained.append(compact)
        save_runtime(dependencies, case_id, {"node_results": retained})
    if result.errors:
        warnings = [*runtime.get("warnings", []), *result.errors]
        save_runtime(dependencies, case_id, {"warnings": warnings})
    checkpoint_id, checkpoint_hash = _checkpoint_identity(node_name, state)
    tool = _tool_name_for_node(node_name, dependencies)
    audit = getattr(dependencies, "audit", None)
    if audit is not None and durable:
        audit.record(
            node_name,
            result,
            dict(state),
            attempt_count=attempt_count,
            retry_count=retry_count,
            duration_ms=duration_ms,
            checkpoint_id=checkpoint_id,
            checkpoint_hash=checkpoint_hash,
            tool=tool,
        )
    tracer = getattr(dependencies, "tracer", None)
    if tracer is not None:
        trace_attributes: dict[str, Any] = {
            "node_name": node_name,
            "agent_role": startup_agent_role(node_name),
            "workflow_type": "startup",
            "status": result.status.value,
            "duration_ms": duration_ms,
            "latency_ms": duration_ms,
            "schema_version": "startup_node_span@1",
            "fallback_used": result.fallback_used,
            "case_id": case_id,
            "run_id": str(state.get("run_id", "unknown")),
            "correlation_id": str(state.get("correlation_id", "unknown")),
            "retry_count": retry_count,
            "attempt": attempt_count,
            "checkpoint_id": checkpoint_id,
            "checkpoint_hash": checkpoint_hash,
        }
        if bool(getattr(dependencies, "deterministic_trace_usage", False)):
            trace_attributes.update(
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                }
            )
        trace_attributes.update(_gate_trace_fields(node_name, state))
        trace_attributes.update(_report_trace_fields(node_name, state))
        if tool is not None:
            trace_attributes["tool"] = tool
        if result.errors:
            trace_attributes["error_code"] = str(result.errors[0])
        tracer.record(**trace_attributes)


def _gate_trace_fields(
    node_name: str,
    state: StartupWorkflowState | dict[str, Any],
) -> dict[str, str]:
    if node_name == "disclosure":
        if state.get("approval_ids"):
            return {"gate": "gate2", "gate_status": "approved"}
        return {"gate": "gate2", "gate_status": "local_only"}
    if node_name == "report":
        if state.get("report_snapshot_id"):
            return {"gate": "gate3", "gate_status": "approved"}
    if node_name == "gate4":
        decision = state.get("gate4_decision")
        if decision in {"approved", "rejected"}:
            return {"gate": "gate4", "gate_status": str(decision)}
    return {}


def _report_trace_fields(
    node_name: str,
    state: StartupWorkflowState | dict[str, Any],
) -> dict[str, str | int]:
    if node_name not in {"report", "gate4"}:
        return {}
    report_id = state.get("report_snapshot_id")
    report_revision = state.get("report_snapshot_revision")
    raw_checksum = state.get("report_snapshot_hash")
    if (
        not isinstance(report_id, str)
        or not report_id
        or isinstance(report_revision, bool)
        or not isinstance(report_revision, int)
        or not isinstance(raw_checksum, str)
    ):
        return {}
    checksum = raw_checksum.removeprefix("sha256:")
    if re.fullmatch(r"[A-Fa-f0-9]{32,128}", checksum) is None:
        return {}
    return {
        "report_id": report_id,
        "report_revision": report_revision,
        "report_checksum": checksum,
    }


def _with_runtime_result(
    result: dict[str, Any],
    dependencies: StartupGraphDependencies,
) -> dict[str, Any]:
    case_id = str(result.get("case_id", ""))
    runtime = runtime_for(dependencies, case_id)
    merged = dict(result)
    interrupt_payload = _interrupt_payload(result.get("__interrupt__"))
    if interrupt_payload is not None:
        merged.update(interrupt_payload)
    merged["node_results"] = list(runtime.get("node_results", []))
    if runtime.get("warnings"):
        merged["warnings"] = list(runtime.get("warnings", []))
    if runtime.get("invalidated_ids"):
        merged["invalidated_ids"] = list(runtime.get("invalidated_ids", []))
    return merged


def _interrupt_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    payload = getattr(first, "value", None)
    if isinstance(payload, dict):
        return dict(payload)
    return None


def _prepare_safe_input(
    input: Any,
    dependencies: StartupGraphDependencies,
) -> Any:
    if isinstance(input, Command) or not isinstance(input, dict):
        return input
    if "sources" in input:
        raise StartupSafeInputError("startup_raw_sources_forbidden")
    case_id = str(input["case_id"])
    data_revision = _safe_data_revision(input.get("data_revision", 1))
    source_refs = _safe_source_refs(input)
    save_runtime(
        dependencies,
        case_id,
        {
            "data_revision": data_revision,
            "source_document_ids": [str(item["document_id"]) for item in source_refs],
            "source_refs": source_refs,
        },
    )
    safe_input = {
        key: input[key]
        for key in ("case_id", "run_id", "correlation_id")
        if key in input
    }
    safe_input["data_revision"] = data_revision
    return safe_input


def _safe_source_refs(input: dict[str, Any]) -> list[dict[str, str]]:
    raw_refs = input.get("source_refs")
    if not isinstance(raw_refs, list) or not raw_refs:
        raise StartupSafeInputError("startup_source_refs_required")
    refs = [_coerce_source_ref(item, index=index) for index, item in enumerate(raw_refs, start=1)]
    if len({item["document_id"] for item in refs}) != len(refs):
        raise StartupSafeInputError("startup_source_ref_duplicate")
    if len({item["private_name"] for item in refs}) != len(refs):
        raise StartupSafeInputError("startup_source_ref_duplicate")
    if len({item["content_sha256"] for item in refs}) != len(refs):
        raise StartupSafeInputError("startup_source_ref_duplicate")
    return refs


def _safe_data_revision(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StartupSafeInputError("startup_data_revision_invalid")
    return value


def _coerce_source_ref(item: Any, *, index: int) -> dict[str, str]:
    if not isinstance(item, dict):
        raise StartupSafeInputError("startup_source_ref_invalid")
    document_id = item.get("document_id")
    private_name = item.get("private_name")
    content_sha256 = item.get("content_sha256")
    expected_document_id = f"doc-{index:04d}"
    if document_id != expected_document_id:
        raise StartupSafeInputError("startup_source_ref_document_id_invalid")
    if not isinstance(private_name, str) or not re.fullmatch(
        rf"{expected_document_id}\.(pdf|docx|png|jpg|jpeg|csv|xlsx|txt|zip|bin)",
        private_name,
    ):
        raise StartupSafeInputError("startup_source_ref_private_name_invalid")
    if not isinstance(content_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
        raise StartupSafeInputError("startup_source_ref_content_sha256_invalid")
    return {
        "document_id": document_id,
        "private_name": private_name,
        "content_sha256": content_sha256,
    }


class StartupSafeInputError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _refs_from_update(update: dict[str, object]) -> list[str]:
    refs: list[str] = []
    for key in (
        "inventory_id",
        "parsed_artifact_ids",
        "sensitivity_summary_id",
        "approval_ids",
        "evidence_fact_ids",
        "startup_claim_ids",
        "document_intelligence_snapshot_id",
        "document_intelligence_snapshot_hash",
        "document_intelligence_snapshot_revision",
        "primary_profile_id",
        "profile_id",
        "profile_hash",
        "profile_revision",
        "calculation_ids",
        "readiness_snapshot_id",
        "readiness_snapshot_hash",
        "readiness_snapshot_revision",
        "market_research_snapshot_id",
        "market_research_snapshot_hash",
        "market_research_snapshot_revision",
        "product_validation_snapshot_id",
        "product_validation_snapshot_hash",
        "product_validation_snapshot_revision",
        "gtm_snapshot_id",
        "gtm_snapshot_hash",
        "gtm_snapshot_revision",
        "finding_ids",
        "contradiction_ids",
        "report_snapshot_id",
        "report_snapshot_hash",
        "report_snapshot_revision",
    ):
        value = update.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            refs.extend(str(item) for item in value)
        else:
            refs.append(str(value))
    return refs


def _safe_error_code(exc: Exception) -> str:
    return _declared_error_code(exc) or "workflow_unexpected"


def _is_retryable(exc: Exception) -> bool:
    return getattr(exc, "retryable", False) is True


def _local_provider_fallback(node_name: str, exc: Exception) -> str | None:
    if _declared_error_code(exc) not in _LOCAL_PROVIDER_FALLBACK_ERROR_CODES:
        return None
    return _LOCAL_PROVIDER_FALLBACKS.get(node_name)


def _is_unexpected(exc: Exception) -> bool:
    return _declared_error_code(exc) is None


def _declared_error_code(exc: Exception) -> str | None:
    for attribute in ("code", "stable_error_code"):
        code = getattr(exc, attribute, None)
        if isinstance(code, str) and code:
            return code
    return None


def _runtime(dependencies: StartupGraphDependencies) -> dict[str, dict[str, Any]]:
    ensure_runtime(dependencies)
    return cast(dict[str, dict[str, Any]], getattr(dependencies, "_startup_runtime"))


def _record_checkpoint_keys(dependencies: StartupGraphDependencies) -> None:
    tracer = getattr(dependencies, "tracer", None)
    if tracer is not None and hasattr(tracer, "record_checkpoint_keys"):
        tracer.record_checkpoint_keys(set(CHECKPOINT_STATE_KEYS))


def _checkpoint_identity(node_name: str, state: StartupWorkflowState | dict[str, Any]) -> tuple[str, str]:
    digest = startup_checkpoint_state_hash(state)
    run_id = str(state.get("run_id", "unknown"))
    return f"startup-{_safe_trace_slug(node_name)}-{sha256(run_id.encode('utf-8')).hexdigest()[:12]}", digest


def startup_checkpoint_state_hash(state: StartupWorkflowState | dict[str, Any]) -> str:
    projection: dict[str, str | int | list[str]] = {}
    for key in CHECKPOINT_STATE_KEYS:
        if key not in state:
            continue
        safe_value = _checkpoint_safe_value(state.get(key))
        if safe_value is not None:
            projection[key] = safe_value
    payload = json.dumps(projection, allow_nan=False, separators=(",", ":"), sort_keys=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def _checkpoint_safe_value(value: Any) -> str | int | list[str] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [str(item) for item in value]
    return None


def _tool_name_for_node(node_name: str, dependencies: StartupGraphDependencies) -> str | None:
    if node_name in {"critic", "arbiter"}:
        dependency = getattr(dependencies, "reflexion", None)
        raw_tool_name = getattr(dependency, f"{node_name}_trace_tool_name", None)
        if not isinstance(raw_tool_name, str):
            return None
        safe_tool_name = _safe_trace_slug(raw_tool_name)
        return safe_tool_name or None
    dependency_name = {
        "ingest": "data_room",
        "parse": "parser",
        "classify_redact": "privacy",
        "disclosure": "disclosure",
        "evidence": "evidence",
        "claims": "claims",
        "document_intelligence": "document_intelligence",
        "primary_profile": "profile",
        "profile_enrichment": "profile",
        "metrics": "metrics",
        "market_research": "market_research",
        "product_validation": "product_validation",
        "financial_analysis": "provider",
        "risk_analysis": "provider",
        "market_analysis": "provider",
        "gtm": "gtm",
        "report": "report",
        "gate4": "report",
    }.get(node_name)
    if dependency_name is None:
        return None
    dependency = getattr(dependencies, dependency_name, None)
    raw_tool_name = getattr(dependency, "trace_tool_name", None)
    if not isinstance(raw_tool_name, str):
        return None
    safe_tool_name = _safe_trace_slug(raw_tool_name)
    return safe_tool_name or None


def _safe_trace_slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return normalized.strip("._-")[:64]


def _merge_accumulative_fields(
    state: StartupWorkflowState,
    update: dict[str, object],
) -> dict[str, object]:
    if "finding_ids" in update and not update.get("_replace_finding_ids"):
        existing = [str(item) for item in state.get("finding_ids", [])]
        raw_incoming = update.get("finding_ids", [])
        incoming = [str(item) for item in raw_incoming] if isinstance(raw_incoming, list) else []
        update["finding_ids"] = _unique(existing + incoming)
    update.pop("_replace_finding_ids", None)
    return update


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
