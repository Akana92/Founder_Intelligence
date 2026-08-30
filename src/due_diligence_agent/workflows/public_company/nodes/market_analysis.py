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


def market_analysis(
    state: PublicCaseState,
    *,
    evidence_repository: Any | None = None,
    finding_repository: Any | None = None,
    audit: AuditRecorder | None,
) -> dict[str, object]:
    case_id = UUID(state["case_id"])
    fact_ids = list(state.get("evidence_fact_ids", []))
    findings = []
    if evidence_repository is not None and finding_repository is not None:
        market_facts = [
            fact
            for fact in evidence_repository.list_for_case(case_id)
            if str(fact.id) in fact_ids and fact.name in {"market_cap", "news_signal"}
        ]
        if market_facts:
            finding = Finding(
                id=uuid5(
                    NAMESPACE_URL,
                    f"{case_id}:market:secondary_source:{','.join(str(fact.id) for fact in market_facts)}",
                ),
                case_id=case_id,
                category="market:secondary_source",
                severity=FindingSeverity.LOW,
                claim="Secondary source market evidence is available for market and news context.",
                evidence_fact_ids=tuple(fact.id for fact in market_facts),
                calculation_ids=(),
                confidence=Decimal("0.70"),
                status=FindingStatus.REQUIRES_REVIEW,
                author_node="market_analysis",
                author_model=None,
                sensitivity=SensitivityClass.PUBLIC,
                created_at=_as_of(state),
            )
            _add_once(finding_repository, finding, "finding_already_exists")
            findings.append(finding)
    data_refs = [*fact_ids, *[str(finding.id) for finding in findings]]
    result: NodeResult[None] = NodeResult(status=NodeStatus.SUCCESS, data_refs=data_refs)
    if audit is not None:
        audit.record("market_analysis", result, dict(state))
    return {
        "node_results": [_node_result("market_analysis", result)],
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
