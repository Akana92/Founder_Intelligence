from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.approvals.startup_disclosure import (
    STARTUP_DISCLOSURE_GATE,
    ClassifiedDisclosureSnapshot,
    DisclosurePreviewSafe,
    StartupDisclosureApproval,
    is_comment_safe_for_storage,
)
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.ports.repositories import ApprovalRepository
from due_diligence_agent.ports.tracing import AuditEvent, AuditSpool


class StartupDisclosureService:
    def __init__(
        self,
        *,
        approval_repository: ApprovalRepository,
        audit_spool: AuditSpool,
        clock: Callable[[], datetime] | None = None,
        run_id: str = "startup-gate2",
        correlation_id: str = "startup-gate2",
    ) -> None:
        self._approval_repository = approval_repository
        self._audit_spool = audit_spool
        self._clock = clock or (lambda: datetime.now(UTC))
        self._run_id = run_id
        self._correlation_id = correlation_id
        self.last_invalidation_reason: str | None = None
        self.last_gate_reason: str | None = None

    def build_preview(self, snapshot: ClassifiedDisclosureSnapshot) -> DisclosurePreviewSafe:
        preview = DisclosurePreviewSafe(
            case_id=snapshot.case_id,
            overall_class=snapshot.overall_class,
            detected_classes=tuple(sorted(snapshot.detected_classes, key=lambda item: item.value)),
            artifact_counts=dict(sorted(snapshot.artifact_counts.items())),
            mime_counts=dict(sorted(snapshot.mime_counts.items())),
            category_counts=dict(sorted(snapshot.category_counts.items())),
            fragment_count=len(snapshot.redacted_fragment_ids),
            redaction_policy_version=snapshot.redaction_policy_version,
            egress_policy_version=snapshot.egress_policy_version,
            data_revision=snapshot.data_revision,
            content_hash=snapshot.content_hash,
            destination=snapshot.destination,
            policy_explanation=(
                "Only redacted minimized metadata may leave the local runtime after explicit approval."
            ),
        )
        self._append_audit(snapshot, decision="previewed")
        return preview

    def decide(
        self,
        snapshot: ClassifiedDisclosureSnapshot,
        *,
        action: Literal["approved", "denied"],
        actor: str,
        destination: str,
        decided_at: datetime | None = None,
        human_comment: str | None = None,
    ) -> StartupDisclosureApproval:
        if not is_comment_safe_for_storage(human_comment):
            raise ValueError("unsafe_comment")
        approval = StartupDisclosureApproval.from_decision(
            snapshot,
            action=action,
            actor=actor,
            destination=destination,
            decided_at=decided_at or self._clock(),
        )
        self._append_audit(snapshot, decision=action)
        try:
            self._approval_repository.add(approval.as_base_approval())
        except ValueError as exc:
            if str(exc) != "approval_already_exists":
                raise
        return approval

    def resolve_scope(self, snapshot: ClassifiedDisclosureSnapshot) -> DisclosureScope | None:
        self.last_invalidation_reason = None
        self.last_gate_reason = None

        approvals, invalid_approval_id = self._startup_approvals(snapshot.case_id)
        if invalid_approval_id is not None:
            self.last_invalidation_reason = "approval_scope_invalid"
            self.last_gate_reason = "approval_required"
            self._append_audit(
                snapshot,
                decision="invalidated",
                reason="approval_scope_invalid",
                approval_id=invalid_approval_id,
            )
            return None
        if not approvals:
            self.last_gate_reason = "approval_required"
            return None

        latest = max(approvals, key=lambda item: (item.data_revision, item.decided_at, str(item.id)))
        if latest.action == "denied":
            self.last_gate_reason = "local_deterministic_only"
            return None

        reason = self._invalidation_reason(latest, snapshot)
        if reason is not None:
            self.last_invalidation_reason = reason
            self.last_gate_reason = "approval_required"
            self._append_audit(
                snapshot,
                decision="invalidated",
                reason=reason,
                approval_id=latest.id,
            )
            return None

        self.last_gate_reason = "approved_external"
        return DisclosureScope(
            approval_id=latest.id,
            allowed_classes=latest.allowed_classes,
            destination=latest.destination,
            egress_policy_version=latest.approved_egress_policy_version,
            redaction_policy_versions=frozenset({latest.approved_redaction_policy_version}),
        )

    def _startup_approvals(self, case_id: UUID) -> tuple[list[StartupDisclosureApproval], UUID | None]:
        parsed: list[StartupDisclosureApproval] = []
        invalid_approval_id: UUID | None = None
        for approval in self._approval_repository.list_for_case(case_id):
            if not isinstance(approval, Approval) or approval.gate != STARTUP_DISCLOSURE_GATE:
                continue
            try:
                parsed.append(StartupDisclosureApproval.from_base_approval(approval))
            except (ValueError, TypeError, KeyError):
                invalid_approval_id = invalid_approval_id or approval.id
        return parsed, invalid_approval_id

    def _invalidation_reason(
        self,
        approval: StartupDisclosureApproval,
        snapshot: ClassifiedDisclosureSnapshot,
    ) -> str | None:
        if SensitivityClass.RESTRICTED in snapshot.detected_classes:
            return "restricted_data"
        if approval.case_id != snapshot.case_id:
            return "case_changed"
        if approval.data_revision != snapshot.data_revision:
            return "data_revision_changed"
        if approval.content_hash != snapshot.content_hash:
            return "content_hash_changed"
        if approval.destination != snapshot.destination:
            return "destination_changed"
        if approval.approved_redaction_policy_version != snapshot.redaction_policy_version:
            return "redaction_policy_changed"
        if approval.approved_egress_policy_version != snapshot.egress_policy_version:
            return "egress_policy_changed"
        if approval.allowed_classes != snapshot.detected_classes:
            return "sensitivity_scope_changed"
        return None

    def _append_audit(
        self,
        snapshot: ClassifiedDisclosureSnapshot,
        *,
        decision: str,
        reason: str | None = None,
        approval_id: UUID | None = None,
    ) -> None:
        timestamp = self._clock()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        timestamp_utc = timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
        attributes: dict[str, str | int | bool | None] = {
            "case_id": str(snapshot.case_id),
            "decision": decision,
            "reason": reason,
            "approval_id": str(approval_id) if approval_id is not None else None,
            "data_revision": snapshot.data_revision,
            "content_hash": snapshot.content_hash,
            "overall_class": snapshot.overall_class.value,
            "detected_class_count": len(snapshot.detected_classes),
            "artifact_count": sum(snapshot.artifact_counts.values()),
            "fragment_count": len(snapshot.redacted_fragment_ids),
            "redaction_policy_version": snapshot.redaction_policy_version,
            "egress_policy_version": snapshot.egress_policy_version,
            "destination": snapshot.destination,
        }
        self._audit_spool.append(
            AuditEvent(
                schema_version="audit_event@1",
                event_id=str(uuid4()),
                timestamp_utc=timestamp_utc,
                run_id=self._run_id,
                correlation_id=self._correlation_id,
                span_name="startup.disclosure_gate",
                event_type=f"{STARTUP_DISCLOSURE_GATE}.{decision}",
                attributes=attributes,
            )
        )
