from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from due_diligence_agent.adapters.local_storage.repositories import (
    LocalApprovalRepository,
    LocalCaseRepository,
)
from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.adapters.openai.gateway import OpenAIGateway
from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.application.policies.budget import BudgetGuard
from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
from due_diligence_agent.application.policies.data_egress import DataEgressDenied
from due_diligence_agent.application.policies.model_routing import ModelRoutingPolicy
from due_diligence_agent.application.services.startup_disclosure_service import (
    StartupDisclosureService,
)
from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.approvals.startup_disclosure import (
    ClassifiedDisclosureSnapshot,
    StartupDisclosureApproval,
)
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    CaseStatus,
    FindingSeverity,
    SensitivityClass,
)
from due_diligence_agent.ports.llm import LLMBudgetRequest, LLMContextFragment, LLMRoutingContext
from due_diligence_agent.ports.tracing import AuditEvent
from due_diligence_agent.ports.tracing import TraceContext


CASE_ID = UUID("00000000-0000-0000-0000-000000000801")
NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


class RecordingAuditSpool:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> str:
        self.events.append(event)
        if self.fail:
            raise OSError("disk full raw-secret")
        return "memory://audit"

    def read_batch(self, limit: int = 100) -> list[AuditEvent]:
        return self.events[:limit]

    def mark_flushed(self, event_ids: list[str]) -> None:
        return None


class RiskOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk: str
    evidence_ids: tuple[str, ...]


class ProviderSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return _Parsed(RiskOutput(risk="liquidity", evidence_ids=("fragment-1",)))


class _Parsed:
    def __init__(self, output: RiskOutput) -> None:
        self.output_parsed = output
        self.usage = {"total_tokens": 10, "input_tokens": 4, "output_tokens": 6}


def test_snapshot_and_approval_are_immutable_and_forbid_unsafe_fields() -> None:
    snapshot = _snapshot()

    with pytest.raises(ValidationError):
        ClassifiedDisclosureSnapshot(
            **snapshot.model_dump(mode="python"),
            raw_excerpt="secret@example.com",
        )
    with pytest.raises(ValidationError):
        snapshot.data_revision = 2  # type: ignore[misc]
    with pytest.raises(ValidationError):
        StartupDisclosureApproval.from_decision(
            snapshot,
            action="approved",
            actor="founder",
            destination="openai.responses",
            decided_at=NOW.replace(tzinfo=None),
        )
    with pytest.raises(ValidationError):
        StartupDisclosureApproval.from_decision(
            snapshot.model_copy(
                update={
                    "detected_classes": frozenset({SensitivityClass.RESTRICTED}),
                    "overall_class": SensitivityClass.RESTRICTED,
                }
            ),
            action="approved",
            actor="founder",
            destination="openai.responses",
            decided_at=NOW,
        )


def test_preview_contains_counts_but_no_raw_values_or_names() -> None:
    audit = RecordingAuditSpool()
    service = _service(_repo(), audit)
    snapshot = _snapshot(
        category_counts={"credential_like": 1, "customer_name": 2},
        artifact_counts={"pdf": 1},
        mime_counts={"application_pdf": 1},
    )

    preview = service.build_preview(snapshot)

    dumped = preview.model_dump_json()
    assert preview.category_counts["credential_like"] == 1
    assert preview.artifact_counts == {"pdf": 1}
    assert "sk-live-secret" not in dumped
    assert "Acme Bank" not in dumped
    assert [event.event_type for event in audit.events] == ["startup_disclosure.previewed"]


def test_repeated_previews_emit_unique_events_that_real_spool_flushes_independently(tmp_path) -> None:
    audit = JsonlAuditSpool(tmp_path, max_mb=1)
    service = StartupDisclosureService(
        approval_repository=_repo(),
        audit_spool=audit,
        clock=lambda: NOW,
        run_id="run-gate2",
        correlation_id="corr-gate2",
    )
    snapshot = _snapshot()

    service.build_preview(snapshot)
    service.build_preview(snapshot)

    events = audit.read_batch(limit=10)
    assert [event.event_type for event in events] == [
        "startup_disclosure.previewed",
        "startup_disclosure.previewed",
    ]
    assert events[0].event_id != events[1].event_id

    audit.mark_flushed([events[0].event_id])

    remaining = audit.read_batch(limit=10)
    assert [event.event_id for event in remaining] == [events[1].event_id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approved_first", "changed", "want_reason"),
    [
        (False, {}, "approval_required"),
        (True, {"content_hash": "b" * 64}, "approval_required"),
        (
            True,
            {
                "detected_classes": frozenset({SensitivityClass.RESTRICTED}),
                "overall_class": SensitivityClass.RESTRICTED,
            },
            "restricted_data",
        ),
    ],
)
async def test_missing_stale_and_restricted_scopes_deny_before_provider_call(
    approved_first: bool,
    changed: dict[str, object],
    want_reason: str,
) -> None:
    audit = RecordingAuditSpool()
    service = _service(_repo(), audit)
    provider = ProviderSpy()
    snapshot = _snapshot()
    if approved_first:
        service.decide(
            snapshot,
            action="approved",
            actor="founder",
            destination="openai.responses",
        )
    current = snapshot.model_copy(update=changed)

    scope = service.resolve_scope(current)

    with pytest.raises(DataEgressDenied) as excinfo:
        await _gateway(provider).complete_structured(
            task="startup_risk",
            fragments=[_fragment(current.overall_class, redaction_policy_version=current.redaction_policy_version)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(current.overall_class),
            trace_context=_trace(current.redaction_policy_version),
            disclosure_scope=scope,
        )

    assert excinfo.value.decision.reason == want_reason
    assert provider.calls == []


@pytest.mark.asyncio
async def test_denied_approval_returns_no_scope_and_denies_before_provider_call() -> None:
    audit = RecordingAuditSpool()
    service = _service(_repo(), audit)
    provider = ProviderSpy()
    snapshot = _snapshot()
    denied = service.decide(
        snapshot,
        action="denied",
        actor="founder",
        destination="openai.responses",
        human_comment="Do not send this outside",
    )

    assert denied.action == "denied"
    scope = service.resolve_scope(snapshot)
    with pytest.raises(DataEgressDenied) as excinfo:
        await _gateway(provider).complete_structured(
            task="startup_risk",
            fragments=[_fragment(SensitivityClass.CONFIDENTIAL)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.CONFIDENTIAL),
            trace_context=_trace(snapshot.redaction_policy_version),
            disclosure_scope=scope,
        )

    assert excinfo.value.decision.reason == "approval_required"
    assert service.last_gate_reason == "local_deterministic_only"
    assert provider.calls == []
    assert [event.event_type for event in audit.events] == ["startup_disclosure.denied"]
    assert "Do not send this outside" not in json.dumps(
        [event.__dict__ for event in audit.events],
        default=str,
    )


def test_valid_approval_returns_disclosure_scope_and_round_trips_through_sqlite() -> None:
    db_path = Path(".tmp-task8-sqlite") / f"gate2-{uuid4()}.sqlite3"
    db = SQLiteDatabase(db_path)
    try:
        LocalCaseRepository(db).add(_case())
        repo = LocalApprovalRepository(db)
        service = _service(repo, RecordingAuditSpool())
        snapshot = _snapshot()

        approval = service.decide(
            snapshot,
            action="approved",
            actor="founder",
            destination="openai.responses",
            human_comment="Founder approved safe summary",
        )
    finally:
        db.close()

    reopened_db = SQLiteDatabase(db_path)
    try:
        reopened = LocalApprovalRepository(reopened_db)
        restarted = _service(reopened, RecordingAuditSpool())
        base_approval = reopened.list_for_case(CASE_ID)[0]
        scope = restarted.resolve_scope(snapshot)
    finally:
        reopened_db.close()

    typed = StartupDisclosureApproval.from_base_approval(base_approval)
    assert base_approval.comment == approval.as_base_approval().comment
    assert "Founder approved safe summary" not in (base_approval.comment or "")
    assert typed.allowed_classes == approval.allowed_classes
    assert scope is not None
    assert scope.approval_id == approval.id
    assert scope.allowed_classes == frozenset(
        {SensitivityClass.PUBLIC, SensitivityClass.INTERNAL, SensitivityClass.CONFIDENTIAL}
    )
    assert scope.destination == "openai.responses"
    assert scope.egress_policy_version == DataEgressPolicy.version


@pytest.mark.parametrize(
    "tamper",
    [
        {"case_id": UUID("00000000-0000-0000-0000-000000000802")},
        {"data_revision": 2},
        {"action": "denied"},
        {"subject_version": 2},
        {"id": UUID("00000000-0000-0000-0000-000000000803")},
    ],
)
def test_base_approval_tampering_rejects_scope_without_trusting_comment(
    tamper: dict[str, object],
) -> None:
    approval = StartupDisclosureApproval.from_decision(
        _snapshot(),
        action="approved",
        actor="founder",
        destination="openai.responses",
        decided_at=NOW,
    ).as_base_approval()
    tampered = Approval(**{**approval.model_dump(mode="python"), **tamper})

    with pytest.raises(ValueError, match="approval_scope_invalid"):
        StartupDisclosureApproval.from_base_approval(tampered)


def test_corrupted_base_approval_invalidates_with_sanitized_audit() -> None:
    repo = _repo()
    audit = RecordingAuditSpool()
    service = _service(repo, audit)
    approval = StartupDisclosureApproval.from_decision(
        _snapshot(),
        action="approved",
        actor="founder",
        destination="openai.responses",
        decided_at=NOW,
    ).as_base_approval()
    repo.add(
        Approval(
            **{
                **approval.model_dump(mode="python"),
                "comment": "startup_disclosure_scope@1:not-json-raw-secret",
                "subject_hash": "b" * 64,
            }
        )
    )

    assert service.resolve_scope(_snapshot()) is None
    assert service.last_invalidation_reason == "approval_scope_invalid"
    assert audit.events[-1].event_type == "startup_disclosure.invalidated"
    assert audit.events[-1].attributes["reason"] == "approval_scope_invalid"
    serialized = json.dumps([event.__dict__ for event in audit.events], default=str)
    assert "not-json-raw-secret" not in serialized
    assert "raw-secret" not in serialized


@pytest.mark.parametrize(
    ("changed", "reason"),
    [
        ({"data_revision": 2}, "data_revision_changed"),
        ({"content_hash": "b" * 64}, "content_hash_changed"),
        ({"detected_classes": frozenset({SensitivityClass.CONFIDENTIAL})}, "sensitivity_scope_changed"),
        ({"redaction_policy_version": "redact@2"}, "redaction_policy_changed"),
        ({"egress_policy_version": "egress@2"}, "egress_policy_changed"),
        ({"destination": "langsmith"}, "destination_changed"),
        (
            {
                "detected_classes": frozenset({SensitivityClass.RESTRICTED}),
                "overall_class": SensitivityClass.RESTRICTED,
            },
            "restricted_data",
        ),
    ],
)
def test_scope_invalidates_on_every_material_snapshot_dimension(
    changed: dict[str, object],
    reason: str,
) -> None:
    audit = RecordingAuditSpool()
    repo = _repo()
    service = _service(repo, audit)
    original = _snapshot()
    service.decide(
        original,
        action="approved",
        actor="founder",
        destination="openai.responses",
    )

    mutated = original.model_copy(update=changed)

    assert service.resolve_scope(mutated) is None
    assert service.last_invalidation_reason == reason
    assert audit.events[-1].event_type == "startup_disclosure.invalidated"
    assert audit.events[-1].attributes["reason"] == reason


def test_latest_approval_is_chosen_deterministically() -> None:
    repo = _repo()
    service = _service(repo, RecordingAuditSpool())
    snapshot_v1 = _snapshot(data_revision=1)
    snapshot_v2 = _snapshot(data_revision=2)
    service.decide(
        snapshot_v1,
        action="approved",
        actor="founder",
        destination="openai.responses",
        decided_at=NOW,
    )
    latest = service.decide(
        snapshot_v2,
        action="approved",
        actor="founder",
        destination="openai.responses",
        decided_at=NOW + timedelta(minutes=1),
    )

    scope = service.resolve_scope(snapshot_v2)

    assert scope is not None
    assert scope.approval_id == latest.id


def test_audit_failure_fails_closed_before_authorization_is_persisted() -> None:
    repo = _repo()
    audit = RecordingAuditSpool(fail=True)
    service = _service(repo, audit)

    with pytest.raises(OSError, match="disk full"):
        service.decide(
            _snapshot(),
            action="approved",
            actor="founder",
            destination="openai.responses",
        )

    assert repo.list_for_case(CASE_ID) == []
    serialized = json.dumps([event.__dict__ for event in audit.events], default=str)
    assert "raw-secret" not in serialized


def test_unsafe_human_comment_is_rejected_and_never_serialized() -> None:
    service = _service(_repo(), RecordingAuditSpool())

    with pytest.raises(ValueError, match="unsafe_comment"):
        service.decide(
            _snapshot(),
            action="approved",
            actor="founder",
            destination="openai.responses",
            human_comment="email founder@example.com token sk-live-secret",
        )


def _service(
    repo: LocalApprovalRepository | "_MemoryApprovalRepository",
    audit: RecordingAuditSpool,
) -> StartupDisclosureService:
    return StartupDisclosureService(
        approval_repository=repo,
        audit_spool=audit,
        clock=lambda: NOW,
        run_id="run-gate2",
        correlation_id="corr-gate2",
    )


def _repo() -> "_MemoryApprovalRepository":
    return _MemoryApprovalRepository()


def _gateway(provider: ProviderSpy) -> OpenAIGateway:
    return OpenAIGateway(
        responses_client=provider,
        egress_policy=DataEgressPolicy(),
        routing_policy=ModelRoutingPolicy(),
        budget_guard=BudgetGuard(
            default_token_limit=10_000,
            default_usd_limit=Decimal("1.00"),
        ),
        audit_spool=RecordingAuditSpool(),
    )


def _fragment(
    sensitivity: SensitivityClass,
    *,
    redaction_policy_version: str = "redact@1",
) -> LLMContextFragment:
    return LLMContextFragment(
        id=uuid4(),
        minimized_text="[REDACTED:confidential_source:1]",
        sensitivity=sensitivity,
        redacted=True,
        minimized=True,
        redaction_policy_version=redaction_policy_version,
    )


def _budget() -> LLMBudgetRequest:
    return LLMBudgetRequest(
        case_id=CASE_ID,
        worst_case_tokens=100,
        worst_case_usd_cost=Decimal("0.01"),
    )


def _routing(sensitivity: SensitivityClass) -> LLMRoutingContext:
    return LLMRoutingContext(
        task_complexity="medium",
        latency_budget_ms=1000,
        schema_validation_failed=False,
        potential_finding_severity=FindingSeverity.MEDIUM,
        sensitivity=sensitivity,
    )


def _trace(redaction_policy_version: str) -> TraceContext:
    return TraceContext(
        request_id="req-gate2",
        run_id="run-gate2",
        case_id=str(CASE_ID),
        correlation_id="corr-gate2",
        workflow_type="startup",
        app_version="test",
        graph_version="test",
        redaction_policy_version=redaction_policy_version,
    )


class _MemoryApprovalRepository:
    def __init__(self) -> None:
        self.items: list[object] = []

    def add(self, approval: object) -> None:
        self.items.append(approval)

    def list_for_case(self, case_id: UUID) -> list[object]:
        return [
            item.as_base_approval() if hasattr(item, "as_base_approval") else item
            for item in self.items
            if getattr(item, "case_id") == case_id
        ]


def _snapshot(**overrides: object) -> ClassifiedDisclosureSnapshot:
    data = {
        "case_id": CASE_ID,
        "detected_classes": frozenset(
            {
                SensitivityClass.PUBLIC,
                SensitivityClass.INTERNAL,
                SensitivityClass.CONFIDENTIAL,
            }
        ),
        "overall_class": SensitivityClass.CONFIDENTIAL,
        "redaction_policy_version": "redact@1",
        "egress_policy_version": DataEgressPolicy.version,
        "data_revision": 1,
        "content_hash": "a" * 64,
        "artifact_counts": {"pdf": 1},
        "mime_counts": {"application_pdf": 1},
        "category_counts": {"credential_like": 1},
        "redacted_fragment_ids": (uuid4(),),
        "minimized_fragment_refs": ("c" * 64,),
        "destination": "openai.responses",
    }
    data.update(overrides)
    return ClassifiedDisclosureSnapshot(**data)


def _case() -> DueDiligenceCase:
    return DueDiligenceCase(
        case_id=CASE_ID,
        mode=AnalysisMode.STARTUP,
        entity_name="Startup",
        entity_identifier="startup-801",
        jurisdiction="GLOBAL",
        scope=("startup",),
        period_start=None,
        period_end=None,
        as_of=NOW,
        base_currency="USD",
        privacy_policy="startup-local@1",
        budget_policy="stage1b-local@1",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=NOW,
        updated_at=NOW,
        workflow_version="startup-local@1",
        data_revision=1,
    )
