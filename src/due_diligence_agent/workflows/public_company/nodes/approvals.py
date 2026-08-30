from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict

from due_diligence_agent.domain.approvals.models import Approval, ContradictionDecision
from due_diligence_agent.domain.common import ContradictionStatus, FindingSeverity
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.domain.reports.models import ReportSnapshot
from due_diligence_agent.workflows.public_company.nodes.collect import AuditRecorder
from due_diligence_agent.workflows.public_company.state import PublicCaseState
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus


class InvalidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str
    data_revision: int
    approval: Approval
    invalidated_artifact_ids: tuple[UUID, ...] = ()
    invalidated_fact_ids: tuple[UUID, ...] = ()
    invalidated_calculation_ids: tuple[UUID, ...] = ()
    invalidated_finding_ids: tuple[UUID, ...] = ()
    invalidated_contradiction_ids: tuple[UUID, ...] = ()
    affected_report_snapshot_ids: tuple[UUID, ...] = ()
    report_snapshot_invalidated: bool = False


class Gate3DecisionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str
    status: ContradictionStatus
    data_revision: int
    contradiction_id: UUID
    approval: Approval
    forced_executive_summary_contradiction_ids: tuple[UUID, ...] = ()
    case_status: str | None = None
    severity: FindingSeverity | None = None


class FreezeDecisionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approved: bool
    final_pdf_allowed: bool
    json_artifact_ref: str
    html_artifact_ref: str | None
    pdf_artifact_ref: str | None
    data_revision: int
    approval: Approval | None = None
    reason: str | None = None


class PublicReviewService:
    def __init__(self, repositories: Any, *, clock: Callable[[], datetime] | None = None) -> None:
        self._repositories = repositories
        self._clock = clock or (lambda: datetime.now(UTC))

    def exclude_artifact(
        self, artifact_id: UUID, *, actor: str, comment: str | None = None
    ) -> InvalidationResult:
        fact_ids = {fact.id for fact in self._repositories.list_facts_for_artifact(artifact_id)}
        calculations = self._repositories.list_calculations_for_facts(fact_ids)
        calculation_ids = {calculation.id for calculation in calculations}
        findings = self._repositories.list_findings_for_dependencies(fact_ids, calculation_ids)
        finding_ids = {finding.id for finding in findings}
        contradictions = self._repositories.list_contradictions_for_dependencies(
            fact_ids, finding_ids
        )
        contradiction_ids = {contradiction.id for contradiction in contradictions}
        case_id = _case_id_from_closure(findings, contradictions)
        if case_id is None and fact_ids:
            case_id = self._case_id_for_fact(next(iter(fact_ids)))
        snapshots = (
            self._repositories.list_report_snapshots_for_case(case_id)
            if case_id is not None
            else []
        )
        if case_id is None:
            raise KeyError(f"artifact_closure_case_not_found:{artifact_id}")
        revision = self._next_revision(case_id)
        approval = Approval(
            id=_stable_uuid(f"{case_id}:gate_3:exclude_artifact:{artifact_id}:{revision}"),
            case_id=case_id,
            gate="gate_3",
            action="exclude_artifact",
            actor=actor,
            comment=comment,
            decided_at=self._clock(),
            data_revision=revision,
        )
        _add_approval(self._repositories, approval)
        result = InvalidationResult(
            action="exclude_artifact",
            data_revision=revision,
            approval=approval,
            invalidated_artifact_ids=(artifact_id,),
            invalidated_fact_ids=tuple(sorted(fact_ids)),
            invalidated_calculation_ids=tuple(sorted(calculation_ids)),
            invalidated_finding_ids=tuple(sorted(finding_ids)),
            invalidated_contradiction_ids=tuple(sorted(contradiction_ids)),
            affected_report_snapshot_ids=tuple(snapshot.id for snapshot in snapshots),
            report_snapshot_invalidated=bool(snapshots),
        )
        self._add_decision(
            ContradictionDecision(
                id=_stable_uuid(f"{case_id}:gate_3:exclude_artifact:{artifact_id}:{revision}"),
                case_id=case_id,
                contradiction_id=next(iter(sorted(contradiction_ids))),
                approval_id=approval.id,
                action="exclude_artifact",
                status=ContradictionStatus.AWAITING_EVIDENCE,
                data_revision=revision,
                invalidated_artifact_ids=result.invalidated_artifact_ids,
                invalidated_fact_ids=result.invalidated_fact_ids,
                invalidated_calculation_ids=result.invalidated_calculation_ids,
                invalidated_finding_ids=result.invalidated_finding_ids,
                invalidated_contradiction_ids=result.invalidated_contradiction_ids,
                affected_report_snapshot_ids=result.affected_report_snapshot_ids,
                report_snapshot_invalidated=result.report_snapshot_invalidated,
                decided_at=approval.decided_at,
            )
        )
        self._record(
            gate="gate_3",
            action="exclude_artifact",
            actor=actor,
            data_revision=revision,
            comment=comment,
            result=result.model_dump(mode="json"),
        )
        return result

    def accept_source(
        self, contradiction_id: UUID, *, actor: str, comment: str | None = None
    ) -> Gate3DecisionResult:
        return self._gate3_decision(
            contradiction_id,
            actor=actor,
            action="accept_source",
            status=ContradictionStatus.ACCEPTED_SOURCE,
            comment=comment,
        )

    def request_evidence(
        self, contradiction_id: UUID, *, actor: str, comment: str | None = None
    ) -> Gate3DecisionResult:
        return self._gate3_decision(
            contradiction_id,
            actor=actor,
            action="request_evidence",
            status=ContradictionStatus.AWAITING_EVIDENCE,
            case_status="awaiting_evidence",
            comment=comment,
        )

    def reclassify(
        self,
        contradiction_id: UUID,
        *,
        actor: str,
        severity: FindingSeverity,
        comment: str | None = None,
    ) -> Gate3DecisionResult:
        return self._gate3_decision(
            contradiction_id,
            actor=actor,
            action="reclassify",
            status=ContradictionStatus.RECLASSIFIED,
            severity=severity,
            comment=comment,
        )

    def leave_unresolved(
        self, contradiction_id: UUID, *, actor: str, comment: str | None = None
    ) -> Gate3DecisionResult:
        contradiction = self._get_contradiction(contradiction_id)
        forced_ids = (
            (contradiction_id,) if contradiction.severity is FindingSeverity.CRITICAL else ()
        )
        return self._gate3_decision(
            contradiction_id,
            actor=actor,
            action="leave_unresolved",
            status=ContradictionStatus.UNRESOLVED,
            forced_ids=forced_ids,
            comment=comment,
        )

    def _gate3_decision(
        self,
        contradiction_id: UUID,
        *,
        actor: str,
        action: str,
        status: ContradictionStatus,
        comment: str | None = None,
        forced_ids: tuple[UUID, ...] = (),
        case_status: str | None = None,
        severity: FindingSeverity | None = None,
    ) -> Gate3DecisionResult:
        contradiction = self._get_contradiction(contradiction_id)
        revision = self._current_revision(contradiction.case_id)
        approval = Approval(
            id=_stable_uuid(
                f"{contradiction.case_id}:gate_3:{action}:{contradiction_id}:{revision}"
            ),
            case_id=contradiction.case_id,
            gate="gate_3",
            action=action,
            actor=actor,
            comment=comment,
            decided_at=self._clock(),
            data_revision=revision,
        )
        _add_approval(self._repositories, approval)
        result = Gate3DecisionResult(
            action=action,
            status=status,
            data_revision=revision,
            contradiction_id=contradiction_id,
            approval=approval,
            forced_executive_summary_contradiction_ids=forced_ids,
            case_status=case_status,
            severity=severity,
        )
        self._add_decision(
            ContradictionDecision(
                id=_stable_uuid(
                    f"{contradiction.case_id}:gate_3:{action}:{contradiction_id}:{revision}"
                ),
                case_id=contradiction.case_id,
                contradiction_id=contradiction_id,
                approval_id=approval.id,
                action=action,
                status=status,
                data_revision=revision,
                forced_executive_summary_contradiction_ids=forced_ids,
                target_severity=severity if action == "reclassify" else None,
                decided_at=approval.decided_at,
            )
        )
        self._record(
            gate="gate_3",
            action=action,
            actor=actor,
            data_revision=revision,
            comment=comment,
            result=result.model_dump(mode="json"),
        )
        return result

    def _get_contradiction(self, contradiction_id: UUID) -> Contradiction:
        if hasattr(self._repositories, "get_contradiction"):
            return cast(Contradiction, self._repositories.get_contradiction(contradiction_id))
        for contradiction in self._repositories.contradictions:
            if contradiction.id == contradiction_id:
                return cast(Contradiction, contradiction)
        raise KeyError(f"contradiction_not_found:{contradiction_id}")

    def _next_revision(self, case_id: UUID) -> int:
        if hasattr(self._repositories, "next_data_revision"):
            return int(self._repositories.next_data_revision(case_id))
        current = self._current_revision(case_id)
        next_revision = current + 1
        self._repositories.current_data_revision = next_revision
        return next_revision

    def _current_revision(self, case_id: UUID | None = None) -> int:
        if hasattr(self._repositories, "current_data_revision") and callable(
            self._repositories.current_data_revision
        ):
            return int(self._repositories.current_data_revision(case_id))
        return int(getattr(self._repositories, "current_data_revision", 1))

    def _record(self, **event: object) -> None:
        if hasattr(self._repositories, "record_audit"):
            self._repositories.record_audit(event)

    def _add_decision(self, decision: ContradictionDecision) -> None:
        if hasattr(self._repositories, "add_decision"):
            self._repositories.add_decision(decision)

    def _case_id_for_fact(self, fact_id: UUID) -> UUID | None:
        for fact in getattr(self._repositories, "facts", []):
            if fact.id == fact_id:
                artifact_id = fact.artifact_id
                for artifact in getattr(self._repositories, "artifacts", []):
                    if artifact.id == artifact_id:
                        return cast(UUID, artifact.case_id)
        return None


class SnapshotFreezeService:
    def __init__(self, repositories: Any, *, clock: Callable[[], datetime] | None = None) -> None:
        self._repositories = repositories
        self._clock = clock or (lambda: datetime.now(UTC))

    def apply_freeze_decision(
        self,
        snapshot_id: UUID,
        *,
        approved: bool,
        actor: str,
        data_revision: int,
        comment: str | None = None,
    ) -> FreezeDecisionOutcome:
        snapshot = self._repositories.get_snapshot(snapshot_id)
        current_revision = _current_revision(self._repositories, snapshot.case_id)
        if data_revision != current_revision:
            return FreezeDecisionOutcome(
                approved=False,
                final_pdf_allowed=False,
                json_artifact_ref=snapshot.json_artifact_ref,
                html_artifact_ref=snapshot.html_artifact_ref,
                pdf_artifact_ref=snapshot.pdf_artifact_ref,
                data_revision=current_revision,
                reason="stale_data_revision",
            )
        approval = Approval(
            id=_stable_uuid(
                f"{snapshot.case_id}:gate_4:{approved}:{snapshot_id}:{current_revision}"
            ),
            case_id=snapshot.case_id,
            gate="gate_4",
            action="approved" if approved else "rejected",
            actor=actor,
            comment=comment,
            decided_at=self._clock(),
            data_revision=current_revision,
            subject_id=snapshot.id,
            subject_hash=snapshot.report_hash,
            subject_version=snapshot.version,
        )
        _add_approval(self._repositories, approval)
        outcome = FreezeDecisionOutcome(
            approved=approved,
            final_pdf_allowed=approved,
            json_artifact_ref=snapshot.json_artifact_ref,
            html_artifact_ref=snapshot.html_artifact_ref,
            pdf_artifact_ref=None,
            data_revision=current_revision,
            approval=approval,
        )
        if hasattr(self._repositories, "record_audit"):
            self._repositories.record_audit(
                {
                    "gate": "gate_4",
                    "action": approval.action,
                    "actor": actor,
                    "data_revision": current_revision,
                    "result": outcome.model_dump(mode="json"),
                }
            )
        return outcome


def gate3_review(
    state: PublicCaseState, *, service: PublicReviewService, audit: AuditRecorder | None
) -> dict[str, object]:
    if not state.get("contradiction_ids"):
        return {"status": "analysis_ready"}
    decision = interrupt(
        {
            "status": "awaiting_review",
            "gate": "gate_3",
            "contradiction_ids": state.get("contradiction_ids", []),
            "forced_executive_summary_contradiction_ids": state.get(
                "forced_executive_summary_contradiction_ids", []
            ),
        }
    )
    if not isinstance(decision, dict):
        decision = {"action": "leave_unresolved"}
    action = str(decision.get("action", "leave_unresolved"))
    actor = str(decision.get("actor", "reviewer"))
    contradiction_id = UUID(str(decision.get("contradiction_id", state["contradiction_ids"][0])))
    if action == "accept_source":
        result = service.accept_source(contradiction_id, actor=actor)
    elif action == "request_evidence":
        result = service.request_evidence(contradiction_id, actor=actor)
    elif action == "reclassify":
        severity = FindingSeverity(str(decision.get("severity", FindingSeverity.MEDIUM.value)))
        result = service.reclassify(contradiction_id, actor=actor, severity=severity)
    elif action == "exclude_artifact":
        artifact_id = UUID(str(decision["artifact_id"]))
        invalidation = service.exclude_artifact(artifact_id, actor=actor)
        return {
            "status": "awaiting_evidence",
            "data_revision": invalidation.data_revision,
            "report_snapshot_id": None,
            "node_results": [
                _compact(
                    "gate_3", [str(item) for item in invalidation.invalidated_contradiction_ids]
                )
            ],
        }
    else:
        result = service.leave_unresolved(contradiction_id, actor=actor)
    node_result = NodeResult[None](status=NodeStatus.SUCCESS, data_refs=[str(contradiction_id)])
    if audit is not None:
        audit.record("gate_3", node_result, dict(state))
    update: dict[str, object] = {
        "status": result.case_status or "review_resolved",
        "approvals": [result.approval.model_dump(mode="json")],
        "data_revision": result.data_revision,
        "node_results": [_compact("gate_3", [str(contradiction_id)])],
    }
    if result.forced_executive_summary_contradiction_ids:
        update["forced_executive_summary_contradiction_ids"] = [
            str(item) for item in result.forced_executive_summary_contradiction_ids
        ]
    return update


def gate4_freeze(
    state: PublicCaseState, *, service: SnapshotFreezeService, audit: AuditRecorder | None
) -> dict[str, object]:
    decision = interrupt(
        {
            "status": "awaiting_report_freeze",
            "gate": "gate_4",
            "report_snapshot_id": state.get("report_snapshot_id"),
            "data_revision": state.get("data_revision", 1),
        }
    )
    if not isinstance(decision, dict):
        decision = {"approved": False}
    snapshot_id = UUID(str(decision.get("snapshot_id", state["report_snapshot_id"])))
    outcome = service.apply_freeze_decision(
        snapshot_id,
        approved=decision.get("approved") is True,
        actor=str(decision.get("actor", "reviewer")),
        data_revision=int(state.get("data_revision", 1)),
    )
    node_result = NodeResult[None](status=NodeStatus.SUCCESS, data_refs=[str(snapshot_id)])
    if audit is not None:
        audit.record("gate_4", node_result, dict(state))
    update: dict[str, object] = {
        "status": "approved" if outcome.approved else "draft_rejected",
        "final_pdf_allowed": outcome.final_pdf_allowed,
        "draft_json_artifact_ref": outcome.json_artifact_ref,
        "draft_html_artifact_ref": outcome.html_artifact_ref,
        "data_revision": outcome.data_revision,
        "node_results": [_compact("gate_4", [str(snapshot_id)])],
    }
    if outcome.approval is not None:
        update["approvals"] = [outcome.approval.model_dump(mode="json")]
    if outcome.reason is not None:
        update["primary_failure"] = f"gate_4:{outcome.reason}"
    return update


def prepare_report_freeze(
    state: PublicCaseState,
    *,
    report_repository: Any | None,
    report_preparer: Callable[[UUID], ReportSnapshot] | None = None,
    audit: AuditRecorder | None,
) -> dict[str, object]:
    snapshot_id = state.get("report_snapshot_id")
    if snapshot_id is None and report_repository is not None:
        getter = getattr(report_repository, "get_current_draft", None)
        snapshot = getter(UUID(state["case_id"])) if callable(getter) else None
        if isinstance(snapshot, ReportSnapshot):
            snapshot_id = str(snapshot.id)
    if snapshot_id is None and report_preparer is not None:
        snapshot = report_preparer(UUID(state["case_id"]))
        snapshot_id = str(snapshot.id)
    result = NodeResult[None](
        status=NodeStatus.SUCCESS if snapshot_id else NodeStatus.BLOCKED,
        data_refs=[snapshot_id] if snapshot_id else [],
        errors=[] if snapshot_id else ["report_snapshot_required"],
    )
    if audit is not None:
        audit.record("prepare_report_freeze", result, dict(state))
    if snapshot_id is None:
        return {
            "status": "blocked",
            "primary_failure": "gate_4:report_snapshot_required",
            "errors": ["gate_4:report_snapshot_required"],
        }
    return {
        "status": "awaiting_report_freeze",
        "report_snapshot_id": snapshot_id,
        "data_revision": int(state.get("data_revision", 1)),
        "node_results": [_compact("prepare_report_freeze", [snapshot_id])],
    }


def _case_id_from_closure(findings: list[Any], contradictions: list[Any]) -> UUID | None:
    for item in [*findings, *contradictions]:
        case_id = getattr(item, "case_id", None)
        if isinstance(case_id, UUID):
            return case_id
    return None


def _add_approval(repositories: Any, approval: Approval) -> None:
    if hasattr(repositories, "add_approval"):
        repositories.add_approval(approval)
    elif hasattr(repositories, "approval_repository"):
        try:
            repositories.approval_repository.add(approval)
        except ValueError as exc:
            if str(exc) != "approval_already_exists":
                raise


def _current_revision(repositories: Any, case_id: UUID) -> int:
    value = getattr(repositories, "current_data_revision", 1)
    if callable(value):
        return int(value(case_id))
    return int(value)


def _stable_uuid(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, value)


def _compact(node_name: str, refs: list[str]) -> dict[str, object]:
    return {
        "node_name": node_name,
        "status": "success",
        "data_refs": refs,
        "warnings": [],
        "errors": [],
    }
