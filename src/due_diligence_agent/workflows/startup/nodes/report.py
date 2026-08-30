from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from due_diligence_agent.workflows.startup.runtime import runtime_for, save_runtime
from due_diligence_agent.workflows.startup.state import StartupWorkflowState


def report(state: StartupWorkflowState, *, dependencies: Any) -> dict[str, object]:
    runtime = runtime_for(dependencies, state["case_id"])
    if not runtime.get("gate3_reviewed"):
        decision = interrupt(
            {
                "status": "review_required",
                "pending_gate": "startup_gate3_review",
                "case_id": state["case_id"],
                "finding_ids": [str(item) for item in state.get("finding_ids", [])],
                "contradiction_ids": [
                    str(item) for item in state.get("contradiction_ids", [])
                ],
                "gate4_deferred_to": "startup_gate4_freeze",
            }
        )
        if not isinstance(decision, dict):
            decision = {"exclusions": []}
        save_runtime(
            dependencies,
            state["case_id"],
            {
                "gate3_reviewed": True,
                "gate3_exclusions": list(decision.get("exclusions", [])),
            },
        )
        runtime = runtime_for(dependencies, state["case_id"])
    gate3_exclusions = list(runtime.get("gate3_exclusions", []))
    invalidated_ids = list(runtime.get("invalidated_ids", []))
    startup_claim_ids = [str(item) for item in state.get("startup_claim_ids", [])]
    profile_id = state.get("profile_id") or runtime.get("profile_id")
    profile_hash = state.get("profile_hash") or runtime.get("profile_hash")
    profile_revision = state.get("profile_revision") or runtime.get("profile_revision")
    if not profile_id or not profile_hash or profile_revision is None:
        raise StartupReportProfileError("startup_report_profile_missing")
    readiness_snapshot_id = state.get("readiness_snapshot_id") or runtime.get(
        "readiness_snapshot_id"
    )
    readiness_snapshot_hash = state.get("readiness_snapshot_hash") or runtime.get(
        "readiness_snapshot_hash"
    )
    readiness_snapshot_revision = state.get("readiness_snapshot_revision") or runtime.get(
        "readiness_snapshot_revision"
    )
    market_research_snapshot_id = state.get("market_research_snapshot_id") or runtime.get(
        "market_research_snapshot_id"
    )
    market_research_snapshot_hash = state.get("market_research_snapshot_hash") or runtime.get(
        "market_research_snapshot_hash"
    )
    market_research_snapshot_revision = state.get(
        "market_research_snapshot_revision"
    ) or runtime.get("market_research_snapshot_revision")
    product_validation_snapshot_id = state.get(
        "product_validation_snapshot_id"
    ) or runtime.get("product_validation_snapshot_id")
    gtm_snapshot_id = state.get("gtm_snapshot_id") or runtime.get("gtm_snapshot_id")
    gtm_snapshot_hash = state.get("gtm_snapshot_hash") or runtime.get(
        "gtm_snapshot_hash"
    )
    gtm_snapshot_revision = state.get("gtm_snapshot_revision") or runtime.get(
        "gtm_snapshot_revision"
    )
    if (
        not readiness_snapshot_id
        or not readiness_snapshot_hash
        or readiness_snapshot_revision is None
    ):
        raise StartupReportProfileError("startup_report_readiness_missing")
    if (
        not market_research_snapshot_id
        or not market_research_snapshot_hash
        or market_research_snapshot_revision is None
    ):
        raise StartupReportProfileError("startup_report_market_research_missing")
    if not gtm_snapshot_id or not gtm_snapshot_hash or gtm_snapshot_revision is None:
        raise StartupReportProfileError("startup_report_gtm_missing")
    save_runtime(
        dependencies,
        state["case_id"],
        {
            "report_profile_id": str(profile_id),
            "report_profile_hash": str(profile_hash),
            "report_profile_revision": int(profile_revision),
            "report_readiness_snapshot_id": str(readiness_snapshot_id),
            "report_readiness_snapshot_hash": str(readiness_snapshot_hash),
            "report_readiness_snapshot_revision": int(readiness_snapshot_revision),
            "report_market_research_snapshot_id": str(market_research_snapshot_id),
            "report_market_research_snapshot_hash": str(market_research_snapshot_hash),
            "report_market_research_snapshot_revision": int(
                market_research_snapshot_revision
            ),
            "report_gtm_snapshot_id": str(gtm_snapshot_id),
            "report_gtm_snapshot_hash": str(gtm_snapshot_hash),
            "report_gtm_snapshot_revision": int(gtm_snapshot_revision),
        },
    )
    evidence_fact_ids = [str(item) for item in state.get("evidence_fact_ids", [])]
    calculation_ids = [str(item) for item in state.get("calculation_ids", [])]
    finding_ids = [str(item) for item in state.get("finding_ids", [])]
    contradiction_ids = [str(item) for item in state.get("contradiction_ids", [])]
    report_snapshot_id = state.get("report_snapshot_id")
    if gate3_exclusions and not runtime.get("gate3_recompute_started"):
        refreshed = dependencies.lineage.derive(
            case_id=state["case_id"],
            evidence_fact_ids=[str(item) for item in state.get("evidence_fact_ids", [])],
        )
        dependency_edges = {
            str(key): [str(item) for item in value]
            for key, value in refreshed.get("dependency_edges", {}).items()
        }
        dependency_node_edges = {
            str(key): [str(item) for item in value]
            for key, value in refreshed.get("dependency_node_edges", {}).items()
        }
        save_runtime(
            dependencies,
            state["case_id"],
            {
                "dependency_edges": dependency_edges,
                "dependency_node_edges": dependency_node_edges,
            },
        )
        invalidated_ids = _derive_invalidated_ids(
            exclusions=gate3_exclusions,
            dependency_edges=dependency_edges,
            report_snapshot_id=report_snapshot_id,
        )
        affected_nodes = _affected_nodes(
            invalidated_ids,
            dependency_node_edges,
        )
        if (
            "product_validation" in affected_nodes
            and product_validation_snapshot_id is not None
        ):
            invalidated_ids = _insert_before_report(
                invalidated_ids,
                str(product_validation_snapshot_id),
                report_snapshot_id=report_snapshot_id,
            )
        if "metrics" in affected_nodes and readiness_snapshot_id is not None:
            invalidated_ids = _insert_before_report(
                invalidated_ids,
                str(readiness_snapshot_id),
                report_snapshot_id=report_snapshot_id,
            )
        if "gtm" in affected_nodes and gtm_snapshot_id is not None:
            invalidated_ids = _insert_before_report(
                invalidated_ids,
                str(gtm_snapshot_id),
                report_snapshot_id=report_snapshot_id,
            )
        save_runtime(
            dependencies,
            state["case_id"],
            {
                "invalidated_ids": invalidated_ids,
                "gate3_affected_nodes": affected_nodes,
                "gate3_recompute_started": True,
                "gate3_invalidation_chain": invalidated_ids,
            },
        )
        update: dict[str, object] = {
            "calculation_ids": [
                item for item in calculation_ids if item not in set(invalidated_ids)
            ],
            "finding_ids": [item for item in finding_ids if item not in set(invalidated_ids)],
            "_replace_finding_ids": True,
            "contradiction_ids": [
                item for item in contradiction_ids if item not in set(invalidated_ids)
            ],
            "report_snapshot_id": None,
            "report_snapshot_hash": None,
            "report_snapshot_revision": None,
            "reflexion_round": 0,
            "critic_issue_ids": [],
            "critic_issue_codes": [],
            "arbiter_status": None,
            "readiness_snapshot_id": None,
            "readiness_snapshot_hash": None,
            "readiness_snapshot_revision": None,
            "pending_gate": None,
            "status": "running",
        }
        if "product_validation" in affected_nodes:
            update.update(
                {
                    "product_validation_snapshot_id": None,
                    "product_validation_snapshot_hash": None,
                    "product_validation_snapshot_revision": None,
                }
            )
        if "gtm" in affected_nodes:
            update.update(
                {
                    "gtm_snapshot_id": None,
                    "gtm_snapshot_hash": None,
                    "gtm_snapshot_revision": None,
                }
            )
        return update
    if runtime.get("gate3_recompute_started"):
        save_runtime(dependencies, state["case_id"], {"gate3_report_finalized": True})
    if not runtime.get("external_llm_allowed", True) and not finding_ids:
        finding_ids = ["local-finding-risk-gap"]
    result = dependencies.report.build(
        case_id=state["case_id"],
        profile_id=str(profile_id),
        profile_hash=str(profile_hash),
        profile_revision=int(profile_revision),
        readiness_snapshot_id=str(readiness_snapshot_id),
        readiness_snapshot_hash=str(readiness_snapshot_hash),
        readiness_snapshot_revision=int(readiness_snapshot_revision),
        market_research_snapshot_id=str(market_research_snapshot_id),
        market_research_snapshot_hash=str(market_research_snapshot_hash),
        market_research_snapshot_revision=int(market_research_snapshot_revision),
        gtm_snapshot_id=str(gtm_snapshot_id),
        gtm_snapshot_hash=str(gtm_snapshot_hash),
        gtm_snapshot_revision=int(gtm_snapshot_revision),
        startup_claim_ids=_without_invalidated(startup_claim_ids, invalidated_ids),
        evidence_fact_ids=_without_invalidated(evidence_fact_ids, invalidated_ids),
        calculation_ids=_without_invalidated(calculation_ids, invalidated_ids),
        finding_ids=_without_invalidated(finding_ids, invalidated_ids),
        contradiction_ids=_without_invalidated(contradiction_ids, invalidated_ids),
    )
    return {
        "calculation_ids": calculation_ids,
        "finding_ids": finding_ids,
        "_replace_finding_ids": True,
        "contradiction_ids": contradiction_ids,
        "invalidated_ids": invalidated_ids,
        "report_snapshot_id": str(result["report_snapshot_id"]),
        "report_snapshot_hash": str(result["report_snapshot_hash"]),
        "report_snapshot_revision": int(result["report_snapshot_revision"]),
        "pending_gate": "startup_gate4_freeze",
        "status": "approval_required",
    }


def _derive_invalidated_ids(
    *,
    exclusions: list[Any],
    dependency_edges: dict[str, Any],
    report_snapshot_id: object | None,
) -> list[str]:
    roots = [
        str(item.get("evidence_fact_id"))
        for item in exclusions
        if isinstance(item, dict) and item.get("evidence_fact_id")
    ]
    invalidated: list[str] = []
    queue = list(roots)
    while queue:
        current = queue.pop(0)
        if current in invalidated:
            continue
        invalidated.append(current)
        queue.extend(str(item) for item in dependency_edges.get(current, []))
    if report_snapshot_id is not None and str(report_snapshot_id) not in invalidated:
        invalidated.append(str(report_snapshot_id))
    return invalidated


def _affected_nodes(
    invalidated_ids: list[str],
    dependency_node_edges: dict[str, Any],
) -> list[str]:
    nodes: list[str] = []
    for item in invalidated_ids:
        for node in dependency_node_edges.get(item, []):
            node_name = str(node)
            if node_name not in nodes:
                nodes.append(node_name)
    return nodes


def _without_invalidated(ids: list[str], invalidated_ids: list[str]) -> list[str]:
    invalidated = set(invalidated_ids)
    return [item for item in ids if item not in invalidated]


def _insert_before_report(
    invalidated_ids: list[str],
    artifact_id: str,
    *,
    report_snapshot_id: object | None,
) -> list[str]:
    if artifact_id in invalidated_ids:
        return invalidated_ids
    result = list(invalidated_ids)
    if report_snapshot_id is None or str(report_snapshot_id) not in result:
        result.append(artifact_id)
        return result
    result.insert(result.index(str(report_snapshot_id)), artifact_id)
    return result


class StartupReportProfileError(RuntimeError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
