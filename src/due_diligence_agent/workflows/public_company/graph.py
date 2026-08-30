from __future__ import annotations

from typing import Any, Protocol

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph

from due_diligence_agent.workflows.public_company.nodes.collect import (
    async_collect_market,
    async_collect_news,
    async_collect_sec,
    collect_market,
    collect_news,
    collect_sec,
    compact_result,
    run_guarded,
)
from due_diligence_agent.workflows.public_company.nodes.approvals import (
    gate3_review,
    gate4_freeze,
    prepare_report_freeze,
)
from due_diligence_agent.workflows.public_company.nodes.financial_analysis import financial_analysis
from due_diligence_agent.workflows.public_company.nodes.market_analysis import market_analysis
from due_diligence_agent.workflows.public_company.nodes.metrics import calculate_metrics
from due_diligence_agent.workflows.public_company.nodes.normalize import (
    normalize_status,
    should_continue_after_collection,
)
from due_diligence_agent.workflows.public_company.nodes.reflexion import (
    reflexion,
    synthesize_readiness,
)
from due_diligence_agent.workflows.public_company.nodes.risk_analysis import risk_analysis
from due_diligence_agent.workflows.public_company.nodes.scope import request_scope, scope_gate
from due_diligence_agent.workflows.public_company.plan import default_public_plan
from due_diligence_agent.workflows.public_company.state import PublicCaseState
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus
from due_diligence_agent.workflows.shared.reflexion import should_continue_reflexion


class PublicGraphDependencies(Protocol):
    sec: Any
    market: Any
    news: Any
    artifact_repository: Any
    evidence_repository: Any
    artifact_store: Any
    retrieval: Any
    metric_service: Any
    guard: Any | None
    audit: Any | None
    async_sleeper: Any | None
    sync_sleeper: Any | None
    finding_repository: Any
    calculation_repository: Any
    contradiction_repository: Any
    report_repository: Any
    review_service: Any
    freeze_service: Any
    risk_analyzer: Any
    reflexion_reviewer: Any
    report_preparer: Any | None


def build_public_graph(dependencies: PublicGraphDependencies, *, checkpointer: Any) -> Any:
    graph = StateGraph(PublicCaseState)

    graph.add_node("scope", lambda state: _scope_node(state, dependencies))
    graph.add_node("scope_gate", lambda state: _scope_gate_node(state, dependencies))
    graph.add_node("plan", lambda state: _plan_node(state, dependencies))
    graph.add_node(
        "collect_sec",
        RunnableLambda(
            lambda state: collect_sec(state, dependencies=dependencies),
            lambda state: async_collect_sec(state, dependencies=dependencies),
        ),
    )
    graph.add_node(
        "collect_market",
        RunnableLambda(
            lambda state: collect_market(state, dependencies=dependencies),
            lambda state: async_collect_market(state, dependencies=dependencies),
        ),
    )
    graph.add_node(
        "collect_news",
        RunnableLambda(
            lambda state: collect_news(state, dependencies=dependencies),
            lambda state: async_collect_news(state, dependencies=dependencies),
        ),
    )
    graph.add_node(
        "normalize_collection",
        lambda state: normalize_status(
            state, audit=dependencies.audit, node_name="normalize_collection"
        ),
    )
    graph.add_node("retrieve", lambda state: _retrieve_node(state, dependencies))
    graph.add_node(
        "calculate",
        lambda state: calculate_metrics(
            state, metric_service=dependencies.metric_service, audit=dependencies.audit
        ),
    )
    graph.add_node(
        "financial_analysis",
        lambda state: financial_analysis(
            state,
            calculation_repository=getattr(dependencies, "calculation_repository", None),
            evidence_repository=getattr(dependencies, "evidence_repository", None),
            finding_repository=getattr(dependencies, "finding_repository", None),
            audit=dependencies.audit,
        ),
    )
    graph.add_node(
        "risk_analysis",
        lambda state: risk_analysis(
            state,
            finding_repository=getattr(dependencies, "finding_repository", None),
            evidence_repository=getattr(dependencies, "evidence_repository", None),
            calculation_repository=getattr(dependencies, "calculation_repository", None),
            risk_analyzer=getattr(dependencies, "risk_analyzer", None),
            audit=dependencies.audit,
        ),
    )
    graph.add_node(
        "market_analysis",
        lambda state: market_analysis(
            state,
            evidence_repository=getattr(dependencies, "evidence_repository", None),
            finding_repository=getattr(dependencies, "finding_repository", None),
            audit=dependencies.audit,
        ),
    )
    graph.add_node(
        "reflexion",
        lambda state: reflexion(
            state,
            contradiction_repository=getattr(dependencies, "contradiction_repository", None),
            finding_repository=getattr(dependencies, "finding_repository", None),
            reviewer=getattr(dependencies, "reflexion_reviewer", None),
            audit=dependencies.audit,
        ),
    )
    graph.add_node(
        "gate_3",
        lambda state: gate3_review(
            state,
            service=dependencies.review_service,
            audit=dependencies.audit,
        ),
    )
    graph.add_node(
        "synthesize",
        lambda state: synthesize_readiness(state, audit=dependencies.audit),
    )
    graph.add_node(
        "prepare_report_freeze",
        lambda state: prepare_report_freeze(
            state,
            report_repository=getattr(dependencies, "report_repository", None),
            report_preparer=getattr(dependencies, "report_preparer", None),
            audit=dependencies.audit,
        ),
    )
    graph.add_node(
        "gate_4",
        lambda state: gate4_freeze(
            state,
            service=dependencies.freeze_service,
            audit=dependencies.audit,
        ),
    )
    graph.add_node(
        "normalize",
        lambda state: normalize_status(state, audit=dependencies.audit, final=True),
    )

    graph.add_edge(START, "scope")
    graph.add_edge("scope", "scope_gate")
    graph.add_conditional_edges(
        "scope_gate",
        lambda state: "end" if state.get("status") == "blocked" else "plan",
        {"plan": "plan", "end": END},
    )
    graph.add_edge("plan", "collect_sec")
    graph.add_edge("plan", "collect_market")
    graph.add_edge("plan", "collect_news")
    collector_join = (("collect_sec", "collect_market", "collect_news"), "normalize_collection")
    graph.add_edge(list(collector_join[0]), collector_join[1])
    graph.add_conditional_edges(
        "normalize_collection",
        should_continue_after_collection,
        {"retrieve": "retrieve", "end": END},
    )
    graph.add_conditional_edges(
        "retrieve",
        lambda state: "end" if state.get("primary_failure") else "calculate",
        {"calculate": "calculate", "end": END},
    )
    graph.add_conditional_edges(
        "calculate",
        lambda state: "financial_analysis" if _task12_enabled(dependencies) else "normalize",
        {"financial_analysis": "financial_analysis", "normalize": "normalize"},
    )
    graph.add_edge("financial_analysis", "risk_analysis")
    graph.add_edge("risk_analysis", "market_analysis")
    graph.add_edge("market_analysis", "reflexion")
    graph.add_conditional_edges(
        "reflexion",
        lambda state: (
            "risk_analysis"
            if should_continue_reflexion(state, max_rounds=_max_reflexion_rounds(state))
            else "gate_3"
        ),
        {"risk_analysis": "risk_analysis", "gate_3": "gate_3"},
    )
    graph.add_conditional_edges(
        "gate_3",
        _after_gate3,
        {"synthesize": "synthesize", "end": END},
    )
    graph.add_edge("synthesize", "prepare_report_freeze")
    graph.add_edge("prepare_report_freeze", "gate_4")
    graph.add_edge("gate_4", END)
    graph.add_edge("normalize", END)
    return PublicGraph(
        graph.compile(checkpointer=checkpointer), task11_waiting_edges=(collector_join,)
    )


class PublicGraph:
    def __init__(
        self, graph: Any, *, task11_waiting_edges: tuple[tuple[tuple[str, ...], str], ...]
    ) -> None:
        self._graph = graph
        self.task11_waiting_edges = task11_waiting_edges

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return self._graph.invoke(input, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return await self._graph.ainvoke(input, config=config, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)


def _plan_node(state: PublicCaseState, dependencies: PublicGraphDependencies) -> dict[str, object]:
    plan = default_public_plan()
    result: NodeResult[None] = NodeResult(
        status=NodeStatus.SUCCESS, data_refs=[step.task_id for step in plan.steps]
    )
    if dependencies.audit is not None:
        dependencies.audit.record("plan", result, dict(state))
    return {"plan": plan}


def _task12_enabled(dependencies: PublicGraphDependencies) -> bool:
    return all(
        hasattr(dependencies, name)
        for name in ("review_service", "freeze_service", "report_repository")
    )


def _max_reflexion_rounds(state: PublicCaseState) -> int:
    plan = state.get("plan")
    configured = getattr(plan, "max_reflexion_rounds", 2)
    return min(int(configured), 2)


def _after_gate3(state: PublicCaseState) -> str:
    if state.get("primary_failure"):
        return "end"
    if state.get("status") in {"awaiting_evidence", "blocked", "failed"}:
        return "end"
    return "synthesize"


def _scope_node(state: PublicCaseState, dependencies: PublicGraphDependencies) -> dict[str, object]:
    update = request_scope(state)
    if dependencies.audit is not None:
        dependencies.audit.record(
            "scope",
            NodeResult(status=NodeStatus.SUCCESS, data_refs=[str(update["case_id"])]),
            dict(update),
        )
    return update


def _scope_gate_node(
    state: PublicCaseState, dependencies: PublicGraphDependencies
) -> dict[str, object]:
    update = scope_gate(state)
    status = NodeStatus.BLOCKED if update.get("status") == "blocked" else NodeStatus.SUCCESS
    errors = update.get("errors", [])
    error_items = errors if isinstance(errors, list) else []
    result: NodeResult[None] = NodeResult(
        status=status,
        errors=[str(item) for item in error_items],
        data_refs=[state["case_id"]],
    )
    if dependencies.audit is not None:
        dependencies.audit.record("scope_gate", result, dict(state))
    return update


def _retrieve_node(
    state: PublicCaseState, dependencies: PublicGraphDependencies
) -> dict[str, object]:
    result = run_guarded(
        node_name="retrieve",
        state=state,
        guard=getattr(dependencies, "guard", None),
        sleeper=getattr(dependencies, "sync_sleeper", None),
        call=lambda: _retrieve_once(state, dependencies),
    )
    compact = compact_result("retrieve", result)
    if dependencies.audit is not None:
        dependencies.audit.record("retrieve", compact, dict(state))
    update: dict[str, object] = {
        "node_results": [
            {
                "node_name": "retrieve",
                "status": compact.status.value,
                "data_refs": [str(item) for item in compact.data_refs],
                "warnings": list(compact.warnings),
                "errors": list(compact.errors),
            }
        ],
        "chunk_ids": [str(item) for item in compact.data_refs],
        "warnings": [f"retrieve:{warning}" for warning in compact.warnings],
    }
    if result.status in {NodeStatus.BLOCKED, NodeStatus.RETRYABLE_ERROR, NodeStatus.FAILED}:
        detail = result.errors[0] if result.errors else result.status.value
        update["primary_failure"] = f"retrieve:{detail}"
        update["status"] = "blocked"
        update["errors"] = [
            f"retrieve:{detail}",
            *[f"retrieve:{error}" for error in compact.errors[1:]],
        ]
    return update


def _retrieve_once(
    state: PublicCaseState, dependencies: PublicGraphDependencies
) -> NodeResult[None]:
    try:
        hits = dependencies.retrieval.search(
            "public company evidence",
            k=5,
            case_id=__import__("uuid").UUID(state["case_id"]),
        )
    except Exception as exc:
        result = getattr(exc, "result", None)
        if isinstance(result, NodeResult):
            return result.model_copy(update={"data": None})
        raise
    return NodeResult(status=NodeStatus.SUCCESS, data_refs=[str(hit.chunk_id) for hit in hits])
