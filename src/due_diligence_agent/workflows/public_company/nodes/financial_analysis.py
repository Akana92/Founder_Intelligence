from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.domain.common import FindingSeverity, FindingStatus, SensitivityClass
from due_diligence_agent.domain.findings.models import Finding
from due_diligence_agent.workflows.public_company.nodes.collect import AuditRecorder
from due_diligence_agent.workflows.public_company.state import PublicCaseState
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus


def financial_analysis(
    state: PublicCaseState,
    *,
    calculation_repository: Any | None = None,
    evidence_repository: Any | None = None,
    finding_repository: Any | None = None,
    audit: AuditRecorder | None,
) -> dict[str, object]:
    case_id = UUID(state["case_id"])
    calculation_ids = list(state.get("calculation_ids", []))
    findings = []
    if calculation_repository is not None and finding_repository is not None:
        calculations = [
            calculation
            for calculation in calculation_repository.list_for_case(case_id)
            if str(calculation.id) in calculation_ids
        ]
        facts_by_id = (
            {fact.id: fact for fact in evidence_repository.list_for_case(case_id)}
            if evidence_repository is not None
            else {}
        )
        for calculation in calculations:
            if calculation.metric_name != "gross_margin":
                continue
            evidence_ids = tuple(
                fact_id for fact_id in calculation.input_fact_ids if fact_id in facts_by_id
            )
            finding = Finding(
                id=uuid5(
                    NAMESPACE_URL,
                    f"{case_id}:financial:{calculation.metric_name}:{calculation.id}:v{calculation.version}",
                ),
                case_id=case_id,
                category=f"financial:{calculation.metric_name}",
                severity=FindingSeverity.MEDIUM,
                claim=f"Gross margin is {calculation.value} {calculation.unit} for {calculation.period}.",
                evidence_fact_ids=evidence_ids,
                calculation_ids=(calculation.id,),
                confidence=Decimal("0.90"),
                status=FindingStatus.REQUIRES_REVIEW,
                author_node="financial_analysis",
                author_model=None,
                sensitivity=calculation.sensitivity
                if calculation.sensitivity is not None
                else SensitivityClass.PUBLIC,
                created_at=_as_of(state),
            )
            _add_once(finding_repository, finding, "finding_already_exists")
            findings.append(finding)
    data_refs = [*calculation_ids, *[str(finding.id) for finding in findings]]
    result: NodeResult[None] = NodeResult(status=NodeStatus.SUCCESS, data_refs=data_refs)
    if audit is not None:
        audit.record("financial_analysis", result, dict(state))
    return {
        "node_results": [_node_result("financial_analysis", result)],
        "finding_ids": [str(finding.id) for finding in findings],
        "updated_finding_ids": [str(finding.id) for finding in findings],
    }


def _node_result(node_name: str, result: NodeResult[Any]) -> dict[str, object]:
    return {
        "node_name": node_name,
        "status": result.status.value,
        "data_refs": list(result.data_refs),
        "warnings": list(result.warnings),
        "errors": list(result.errors),
    }


def _as_of(state: PublicCaseState) -> datetime:
    raw = state.get("as_of")
    if isinstance(raw, str):
        return datetime.fromisoformat(raw)
    return datetime.now(UTC)


def _add_once(repository: Any, item: Any, duplicate: str) -> None:
    try:
        repository.add(item)
    except ValueError as exc:
        if str(exc) != duplicate:
            raise
