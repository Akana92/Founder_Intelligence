from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from due_diligence_agent.domain.common import (
    ContradictionStatus,
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.startup.market import StartupResearchSource


_CRITIC_ISSUE_NAMESPACE = UUID("0833c66e-7562-46e2-a9d0-c75759a430c4")
_ARBITER_CONTRADICTION_NAMESPACE = UUID("8f35f114-476c-4ec4-8991-380774e3d7bd")
_UNRESOLVED_STATUSES = {
    ContradictionStatus.OPEN,
    ContradictionStatus.AWAITING_EVIDENCE,
    ContradictionStatus.RECLASSIFIED,
    ContradictionStatus.UNRESOLVED,
}
_METRIC_CONFLICT_TYPES = {
    "metric_vs_claim",
    "source_fact_value_conflict",
}
_ASSERTED_FINDING_STATUSES = {
    FindingStatus.DRAFT,
    FindingStatus.VERIFIED,
    FindingStatus.REQUIRES_REVIEW,
}


class StartupCriticIssueCode(StrEnum):
    UNSUPPORTED_CONCLUSION = "unsupported_conclusion"
    COUNTER_EVIDENCE = "counter_evidence"
    METRIC_CONFLICT = "metric_conflict"
    UNRESOLVED_CONTRADICTION = "unresolved_contradiction"
    STALE_SOURCE = "stale_source"


_ISSUE_ORDER = {
    StartupCriticIssueCode.UNSUPPORTED_CONCLUSION: 0,
    StartupCriticIssueCode.COUNTER_EVIDENCE: 1,
    StartupCriticIssueCode.METRIC_CONFLICT: 2,
    StartupCriticIssueCode.UNRESOLVED_CONTRADICTION: 3,
    StartupCriticIssueCode.STALE_SOURCE: 4,
}


class StartupArbiterStatus(StrEnum):
    ACCEPTED = "accepted"
    REVISION_REQUIRED = "revision_required"
    UNRESOLVED = "unresolved"


class StartupCriticIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: UUID
    code: StartupCriticIssueCode
    severity: FindingSeverity
    finding_ids: tuple[UUID, ...] = ()
    contradiction_ids: tuple[UUID, ...] = ()
    evidence_fact_ids: tuple[UUID, ...] = ()
    source_ids: tuple[UUID, ...] = ()
    sensitivity: SensitivityClass
    observed_at: datetime


class StartupCriticReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    round_number: int = Field(ge=1, le=2)
    finding_ids: tuple[UUID, ...] = ()
    issues: tuple[StartupCriticIssue, ...] = ()


class StartupArbiterDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: StartupArbiterStatus
    issue_ids: tuple[UUID, ...] = ()
    accepted_finding_ids: tuple[UUID, ...] = ()
    contradiction_ids: tuple[UUID, ...] = ()
    new_contradiction_ids: tuple[UUID, ...] = ()
    progress: bool = False


class StartupCriticService:
    def review(
        self,
        *,
        case_id: UUID,
        round_number: int,
        findings: Iterable[Finding],
        contradictions: Iterable[Contradiction],
        market_sources: Iterable[StartupResearchSource],
    ) -> StartupCriticReview:
        if round_number not in {1, 2}:
            raise ValueError("startup_reflexion_round_out_of_bounds")
        selected_findings = tuple(
            sorted({item.id: item for item in findings}.values(), key=lambda item: str(item.id))
        )
        selected_contradictions = tuple(
            sorted(
                {item.id: item for item in contradictions}.values(),
                key=lambda item: str(item.id),
            )
        )
        selected_sources = tuple(
            sorted(
                {item.source_id: item for item in market_sources}.values(),
                key=lambda item: str(item.source_id),
            )
        )
        if any(item.case_id != case_id for item in selected_findings):
            raise ValueError("startup_reflexion_finding_case_mismatch")
        if any(item.case_id != case_id for item in selected_contradictions):
            raise ValueError("startup_reflexion_contradiction_case_mismatch")

        issues: list[StartupCriticIssue] = []
        for finding in selected_findings:
            if (
                finding.status in _ASSERTED_FINDING_STATUSES
                and not finding.evidence_fact_ids
                and not finding.calculation_ids
            ):
                issues.append(
                    _issue(
                        case_id=case_id,
                        code=StartupCriticIssueCode.UNSUPPORTED_CONCLUSION,
                        severity=finding.severity,
                        finding_ids=(finding.id,),
                        sensitivity=finding.sensitivity,
                        observed_at=finding.created_at,
                    )
                )
            if (
                finding.counter_evidence_fact_ids
                and finding.status in _ASSERTED_FINDING_STATUSES
            ):
                issues.append(
                    _issue(
                        case_id=case_id,
                        code=StartupCriticIssueCode.COUNTER_EVIDENCE,
                        severity=finding.severity,
                        finding_ids=(finding.id,),
                        evidence_fact_ids=tuple(sorted(finding.counter_evidence_fact_ids)),
                        sensitivity=finding.sensitivity,
                        observed_at=finding.created_at,
                    )
                )

        for contradiction in selected_contradictions:
            if contradiction.status not in _UNRESOLVED_STATUSES:
                continue
            if contradiction.conflict_type.startswith("critic_"):
                continue
            code = (
                StartupCriticIssueCode.METRIC_CONFLICT
                if _is_metric_conflict(contradiction)
                else StartupCriticIssueCode.UNRESOLVED_CONTRADICTION
            )
            issues.append(
                _issue(
                    case_id=case_id,
                    code=code,
                    severity=contradiction.severity,
                    finding_ids=tuple(sorted(contradiction.finding_ids)),
                    contradiction_ids=(contradiction.id,),
                    evidence_fact_ids=tuple(sorted(contradiction.fact_ids)),
                    sensitivity=contradiction.sensitivity,
                    observed_at=contradiction.detected_at,
                )
            )

        for source in selected_sources:
            if not source.stale:
                continue
            issues.append(
                _issue(
                    case_id=case_id,
                    code=StartupCriticIssueCode.STALE_SOURCE,
                    severity=FindingSeverity.MEDIUM,
                    source_ids=(source.source_id,),
                    sensitivity=SensitivityClass.PUBLIC,
                    observed_at=source.retrieved_at,
                )
            )

        return StartupCriticReview(
            case_id=case_id,
            round_number=round_number,
            finding_ids=tuple(item.id for item in selected_findings),
            issues=tuple(
                sorted(
                    issues,
                    key=lambda item: (_ISSUE_ORDER[item.code], str(item.issue_id)),
                )
            ),
        )


class StartupArbiterService:
    def __init__(self, *, contradiction_repository: object) -> None:
        self._contradiction_repository = contradiction_repository

    def decide(self, review: StartupCriticReview) -> StartupArbiterDecision:
        if not review.issues:
            return StartupArbiterDecision(
                status=StartupArbiterStatus.ACCEPTED,
                accepted_finding_ids=review.finding_ids,
            )

        existing = {
            item.id: item
            for item in self._list_for_case(review.case_id)
        }
        unresolved_ids: set[UUID] = {
            contradiction_id
            for issue in review.issues
            for contradiction_id in issue.contradiction_ids
        }
        new_ids: list[UUID] = []
        for issue in review.issues:
            if issue.contradiction_ids:
                continue
            contradiction = _contradiction_for_issue(review.case_id, issue)
            unresolved_ids.add(contradiction.id)
            existing_contradiction = existing.get(contradiction.id)
            if existing_contradiction is not None:
                if existing_contradiction != contradiction:
                    raise ValueError("startup_reflexion_contradiction_conflict")
                continue
            self._add(contradiction)
            existing[contradiction.id] = contradiction
            new_ids.append(contradiction.id)

        status = (
            StartupArbiterStatus.REVISION_REQUIRED
            if review.round_number < 2
            else StartupArbiterStatus.UNRESOLVED
        )
        return StartupArbiterDecision(
            status=status,
            issue_ids=tuple(issue.issue_id for issue in review.issues),
            contradiction_ids=tuple(sorted(unresolved_ids)),
            new_contradiction_ids=tuple(sorted(new_ids)),
            progress=bool(new_ids),
        )

    def _list_for_case(self, case_id: UUID) -> list[Contradiction]:
        method = getattr(self._contradiction_repository, "list_for_case", None)
        if not callable(method):
            raise ValueError("startup_reflexion_contradiction_repository_invalid")
        result = method(case_id)
        if not isinstance(result, list) or any(not isinstance(item, Contradiction) for item in result):
            raise ValueError("startup_reflexion_contradiction_repository_invalid")
        return result

    def _add(self, contradiction: Contradiction) -> None:
        method = getattr(self._contradiction_repository, "add", None)
        if not callable(method):
            raise ValueError("startup_reflexion_contradiction_repository_invalid")
        try:
            method(contradiction)
        except ValueError as exc:
            if str(exc) != "contradiction_already_exists":
                raise


def _issue(
    *,
    case_id: UUID,
    code: StartupCriticIssueCode,
    severity: FindingSeverity,
    sensitivity: SensitivityClass,
    observed_at: datetime,
    finding_ids: tuple[UUID, ...] = (),
    contradiction_ids: tuple[UUID, ...] = (),
    evidence_fact_ids: tuple[UUID, ...] = (),
    source_ids: tuple[UUID, ...] = (),
) -> StartupCriticIssue:
    canonical_finding_ids = tuple(sorted(finding_ids))
    canonical_contradiction_ids = tuple(sorted(contradiction_ids))
    canonical_evidence_ids = tuple(sorted(evidence_fact_ids))
    canonical_source_ids = tuple(sorted(source_ids))
    material = "\x1f".join(
        (
            str(case_id),
            code.value,
            ",".join(str(item) for item in canonical_finding_ids),
            ",".join(str(item) for item in canonical_contradiction_ids),
            ",".join(str(item) for item in canonical_evidence_ids),
            ",".join(str(item) for item in canonical_source_ids),
        )
    )
    return StartupCriticIssue(
        issue_id=uuid5(_CRITIC_ISSUE_NAMESPACE, material),
        code=code,
        severity=severity,
        finding_ids=canonical_finding_ids,
        contradiction_ids=canonical_contradiction_ids,
        evidence_fact_ids=canonical_evidence_ids,
        source_ids=canonical_source_ids,
        sensitivity=sensitivity,
        observed_at=observed_at,
    )


def _is_metric_conflict(contradiction: Contradiction) -> bool:
    conflict_type = contradiction.conflict_type.strip().casefold()
    return (
        conflict_type in _METRIC_CONFLICT_TYPES
        or conflict_type.startswith("startup_claim_")
        or "metric" in conflict_type
    )


def _contradiction_for_issue(case_id: UUID, issue: StartupCriticIssue) -> Contradiction:
    material = "\x1f".join((str(case_id), str(issue.issue_id), issue.code.value))
    explanation, recommendation = _arbiter_text(issue.code)
    return Contradiction(
        id=uuid5(_ARBITER_CONTRADICTION_NAMESPACE, material),
        case_id=case_id,
        conflict_type=f"critic_{issue.code.value}",
        fact_ids=issue.evidence_fact_ids,
        finding_ids=issue.finding_ids,
        explanation=explanation,
        severity=issue.severity,
        status=ContradictionStatus.UNRESOLVED,
        recommended_resolution=recommendation,
        resolved_by_approval_id=None,
        sensitivity=issue.sensitivity,
        detected_at=issue.observed_at,
    )


def _arbiter_text(code: StartupCriticIssueCode) -> tuple[str, str]:
    values = {
        StartupCriticIssueCode.UNSUPPORTED_CONCLUSION: (
            "A verified startup conclusion has no persisted supporting fact or calculation references.",
            "Downgrade the conclusion or attach persisted supporting evidence before acceptance.",
        ),
        StartupCriticIssueCode.COUNTER_EVIDENCE: (
            "A startup finding remains asserted despite linked counter-evidence.",
            "Revise the finding to address its counter-evidence or leave the conflict unresolved.",
        ),
        StartupCriticIssueCode.STALE_SOURCE: (
            "Startup market analysis relies on a source explicitly marked stale.",
            "Refresh the linked research source or label the conclusion as stale-source limited.",
        ),
    }
    try:
        return values[code]
    except KeyError as exc:
        raise ValueError("startup_reflexion_issue_not_materializable") from exc
