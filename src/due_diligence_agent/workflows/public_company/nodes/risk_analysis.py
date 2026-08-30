from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.domain.findings.risk import RiskFinding
from due_diligence_agent.workflows.public_company.nodes.collect import AuditRecorder
from due_diligence_agent.workflows.public_company.state import PublicCaseState
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus


def risk_analysis(
    state: PublicCaseState,
    *,
    finding_repository: Any | None,
    evidence_repository: Any | None = None,
    calculation_repository: Any | None = None,
    risk_analyzer: Any | None = None,
    audit: AuditRecorder | None,
) -> dict[str, object]:
    case_id = UUID(state["case_id"])
    if finding_repository is not None and risk_analyzer is not None:
        facts = (
            evidence_repository.list_for_case(case_id) if evidence_repository is not None else []
        )
        calculations = (
            calculation_repository.list_for_case(case_id)
            if calculation_repository is not None
            else []
        )
        for proposal in risk_analyzer.propose(state, facts, calculations):
            if not isinstance(proposal, RiskFinding):
                continue
            finding = proposal.to_finding(
                finding_id=uuid5(
                    NAMESPACE_URL,
                    ":".join(
                        [
                            str(case_id),
                            "risk",
                            proposal.category,
                            ",".join(str(item) for item in proposal.evidence_fact_ids),
                            ",".join(str(item) for item in proposal.calculation_ids),
                            str(proposal.version),
                        ]
                    ),
                )
            )
            _add_once(finding_repository, finding, "finding_already_exists")
    findings = finding_repository.list_for_case(case_id) if finding_repository is not None else []
    finding_ids = [str(finding.id) for finding in findings]
    result: NodeResult[None] = NodeResult(status=NodeStatus.SUCCESS, data_refs=finding_ids)
    if audit is not None:
        audit.record("risk_analysis", result, dict(state))
    return {
        "finding_ids": finding_ids,
        "node_results": [_node_result("risk_analysis", result)],
    }


def _node_result(node_name: str, result: NodeResult[Any]) -> dict[str, object]:
    return {
        "node_name": node_name,
        "status": result.status.value,
        "data_refs": list(result.data_refs),
        "warnings": list(result.warnings),
        "errors": list(result.errors),
    }


def _add_once(repository: Any, item: Any, duplicate: str) -> None:
    try:
        repository.add(item)
    except ValueError as exc:
        if str(exc) != duplicate:
            raise
