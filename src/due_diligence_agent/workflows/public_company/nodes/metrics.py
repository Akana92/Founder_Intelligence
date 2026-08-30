from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from due_diligence_agent.domain.metrics import MetricStatus
from due_diligence_agent.domain.metrics.definitions import PUBLIC_METRICS
from due_diligence_agent.workflows.public_company.nodes.collect import AuditRecorder
from due_diligence_agent.workflows.public_company.state import PublicCaseState
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus


class MetricService(Protocol):
    def calculate(
        self,
        case_id: UUID,
        metric_name: str,
        *,
        evidence_fact_ids: list[UUID],
        as_of: datetime | None = None,
    ) -> Any: ...


def calculate_metrics(
    state: PublicCaseState,
    *,
    metric_service: MetricService,
    audit: AuditRecorder | None,
) -> dict[str, object]:
    case_id = UUID(state["case_id"])
    fact_ids = _metric_fact_ids(
        metric_service,
        case_id=case_id,
        metric_name="gross_margin",
        evidence_fact_ids=[UUID(item) for item in state.get("evidence_fact_ids", [])],
    )
    result = metric_service.calculate(
        case_id,
        "gross_margin",
        evidence_fact_ids=fact_ids,
        as_of=datetime.fromisoformat(state["as_of"]),
    )
    if result.status is MetricStatus.CALCULATED and result.calculation_id is not None:
        node_result: NodeResult[None] = NodeResult(
            status=NodeStatus.SUCCESS, data_refs=[str(result.calculation_id)]
        )
        update: dict[str, object] = {"calculation_ids": [str(result.calculation_id)]}
    else:
        node_result = NodeResult(status=NodeStatus.PARTIAL, warnings=list(result.warnings))
        update = {"warnings": [f"calculate:{warning}" for warning in result.warnings]}
    if audit is not None:
        audit.record("calculate", node_result, dict(state))
    update["node_results"] = [
        {
            "node_name": "calculate",
            "status": node_result.status.value,
            "data_refs": node_result.data_refs,
            "warnings": node_result.warnings,
            "errors": node_result.errors,
        }
    ]
    return update


def _metric_fact_ids(
    metric_service: MetricService,
    *,
    case_id: UUID,
    metric_name: str,
    evidence_fact_ids: list[UUID],
) -> list[UUID]:
    repository = getattr(metric_service, "_evidence_repository", None)
    if repository is None:
        return evidence_fact_ids
    required = {slot.fact_name for slot in PUBLIC_METRICS[metric_name].slots}
    return [
        fact.id
        for fact in repository.list_for_case(case_id)
        if fact.id in set(evidence_fact_ids) and fact.name in required
    ]
