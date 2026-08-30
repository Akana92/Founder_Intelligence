from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from due_diligence_agent.adapters.local_storage.case_copilot_repositories import (
    LocalCaseAssumptionRepository,
)
from due_diligence_agent.application.services.case_fact_intake_service import (
    CaseFactIntakeService,
    SaveFounderStatementCommand,
)
from due_diligence_agent.application.startup_cases import StartupGateConflict
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import AnalysisMode, CaseStatus, SensitivityClass
from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.case_intake import FounderStatement


CASE_ID = uuid5(NAMESPACE_URL, "case-fact-intake")
OTHER_CASE_ID = uuid5(NAMESPACE_URL, "case-fact-intake-other")
AS_OF = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def test_money_statement_returns_field_level_errors_without_mutation() -> None:
    case_repository = _CaseRepository()
    assumption_repository = _AssumptionRepository()
    service = _service(case_repository, assumption_repository)

    result = service.save_founder_statement(
        SaveFounderStatementCommand(
            case_id=CASE_ID,
            requirement_key="mrr",
            value="about twenty customers",
            expected_case_revision=1,
            idempotency_key="mrr-invalid",
        )
    )

    assert result.accepted is False
    assert result.old_revision == 1
    assert result.new_revision == 1
    assert result.changed_keys == ()
    assert result.original_draft == "about twenty customers"
    assert {error.field for error in result.validation_errors} == {
        "amount",
        "scale",
        "currency",
        "period",
        "declared_source",
    }
    assert case_repository.advance_calls == []
    assert assumption_repository.saved == []


def test_accepted_founder_statement_advances_once_and_invalidates_dependents() -> None:
    case_repository = _CaseRepository()
    assumption_repository = _AssumptionRepository()
    service = _service(case_repository, assumption_repository)

    result = service.save_founder_statement(
        SaveFounderStatementCommand(
            case_id=CASE_ID,
            requirement_key="mrr",
            value="27.9m",
            currency="KZT",
            scale="million",
            period="2026-06",
            declared_source="invoice register",
            expected_case_revision=1,
            idempotency_key="mrr-valid",
        )
    )

    assert result.accepted is True
    assert result.old_revision == 1
    assert result.new_revision == 2
    assert result.changed_keys == ("mrr",)
    assert result.stale_scenario_ids == (uuid5(CASE_ID, "scenario:mrr"),)
    assert result.stale_report_ids == (uuid5(CASE_ID, "report:mrr"),)
    assert result.metric_before == {"mrr": "missing"}
    assert result.metric_after == {"mrr": "founder_statement"}
    assert result.readiness_before == {"answered": 0}
    assert result.readiness_after == {"answered": 1}
    assert result.next_question is not None
    assert result.next_question.requirement_key == "buyer"
    assert case_repository.advance_calls == [(CASE_ID, 1, 2)]
    assert len(assumption_repository.saved) == 1
    saved = assumption_repository.saved[0]
    assert saved.field_key == "mrr"
    assert saved.provenance is CaseValueKind.FOUNDER_STATEMENT
    assert saved.data_revision == 2


def test_idempotent_replay_returns_original_delta_without_second_revision() -> None:
    service = _service(_CaseRepository(), _AssumptionRepository())
    command = SaveFounderStatementCommand(
        case_id=CASE_ID,
        requirement_key="buyer",
        value="FMCG distributor COO",
        declared_source="founder interview",
        expected_case_revision=1,
        idempotency_key="buyer-once",
    )

    first = service.save_founder_statement(command)
    second = service.save_founder_statement(command)

    assert second == first


def test_durable_idempotent_replay_survives_service_recreation(tmp_path: Path) -> None:
    case_repository = _CaseRepository()
    assumption_repository = LocalCaseAssumptionRepository(
        tmp_path,
        current_revision=lambda _case_id: case_repository.current.data_revision,
    )
    service_a = _service(case_repository, assumption_repository)
    command = SaveFounderStatementCommand(
        case_id=CASE_ID,
        requirement_key="buyer",
        value="FMCG distributor COO",
        declared_source="founder interview",
        expected_case_revision=1,
        idempotency_key="buyer-durable",
    )

    first = service_a.save_founder_statement(command)
    service_b = _service(case_repository, assumption_repository)
    second = service_b.save_founder_statement(command)

    assert second.accepted is True
    assert second.old_revision == first.old_revision
    assert second.new_revision == first.new_revision
    assert second.changed_keys == first.changed_keys
    assert case_repository.advance_calls == [(CASE_ID, 1, 2)]
    saved = assumption_repository.list_for_case(CASE_ID)
    assert len(saved) == 1
    assert saved[0].provenance is CaseValueKind.FOUNDER_STATEMENT


def test_durable_idempotent_replay_returns_original_delta_after_later_mutation(
    tmp_path: Path,
) -> None:
    case_repository = _CaseRepository()
    assumption_repository = LocalCaseAssumptionRepository(
        tmp_path,
        current_revision=lambda _case_id: case_repository.current.data_revision,
    )
    service_a = _service(case_repository, assumption_repository)
    original_command = SaveFounderStatementCommand(
        case_id=CASE_ID,
        requirement_key="buyer",
        value="FMCG distributor COO",
        declared_source="founder interview",
        expected_case_revision=1,
        idempotency_key="buyer-durable-original-delta",
    )
    first = service_a.save_founder_statement(original_command)
    second = service_a.save_founder_statement(
        SaveFounderStatementCommand(
            case_id=CASE_ID,
            requirement_key="channel",
            value="Founder-led outbound",
            declared_source="founder interview",
            expected_case_revision=2,
            idempotency_key="channel-later-mutation",
        )
    )
    assert second.new_revision == 3

    service_b = _service(case_repository, assumption_repository)
    replay = service_b.save_founder_statement(original_command)

    assert replay == first
    assert replay.readiness_after == {"answered": 1}
    assert case_repository.advance_calls == [(CASE_ID, 1, 2), (CASE_ID, 2, 3)]
    assert len(assumption_repository.list_for_case(CASE_ID)) == 2


def test_durable_idempotency_rejects_same_key_different_payload_without_mutation(
    tmp_path: Path,
) -> None:
    case_repository = _CaseRepository()
    assumption_repository = LocalCaseAssumptionRepository(
        tmp_path,
        current_revision=lambda _case_id: case_repository.current.data_revision,
    )
    service_a = _service(case_repository, assumption_repository)
    service_a.save_founder_statement(
        SaveFounderStatementCommand(
            case_id=CASE_ID,
            requirement_key="buyer",
            value="FMCG distributor COO",
            declared_source="founder interview",
            expected_case_revision=1,
            idempotency_key="buyer-durable-conflict",
        )
    )
    service_b = _service(case_repository, assumption_repository)

    with pytest.raises(StartupGateConflict, match="idempotency_key_conflict"):
        service_b.save_founder_statement(
            SaveFounderStatementCommand(
                case_id=CASE_ID,
                requirement_key="buyer",
                value="Enterprise CFO",
                declared_source="founder interview",
                expected_case_revision=1,
                idempotency_key="buyer-durable-conflict",
            )
        )

    assert case_repository.advance_calls == [(CASE_ID, 1, 2)]
    assert len(assumption_repository.list_for_case(CASE_ID)) == 1


def test_stale_and_cross_case_input_fail_closed_before_mutation() -> None:
    case_repository = _CaseRepository()
    assumption_repository = _AssumptionRepository()
    service = _service(case_repository, assumption_repository)

    with pytest.raises(StartupGateConflict, match="case_revision_conflict"):
        service.save_founder_statement(
            SaveFounderStatementCommand(
                case_id=CASE_ID,
                requirement_key="buyer",
                value="FMCG distributor COO",
                declared_source="founder interview",
                expected_case_revision=0,
                idempotency_key="stale",
            )
        )
    with pytest.raises(StartupGateConflict, match="case_scope_mismatch"):
        service.save_founder_statement(
            SaveFounderStatementCommand(
                case_id=OTHER_CASE_ID,
                requirement_key="buyer",
                value="FMCG distributor COO",
                declared_source="founder interview",
                expected_case_revision=1,
                idempotency_key="cross-case",
            )
        )
    assert case_repository.advance_calls == []
    assert assumption_repository.saved == []


def test_external_provenance_is_never_promoted_to_source_fact() -> None:
    case_repository = _CaseRepository()
    assumption_repository = _AssumptionRepository()
    service = _service(case_repository, assumption_repository)

    for kind in ("founder_statement", "public_benchmark", "ai_scenario"):
        result = service.save_founder_statement(
            SaveFounderStatementCommand(
                case_id=CASE_ID,
                requirement_key="monthly_price",
                value="50000",
                currency="KZT",
                scale="ones",
                period="month",
                declared_source=f"{kind} planning note",
                supporting_evidence_refs=(uuid5(CASE_ID, kind),),
                expected_case_revision=case_repository.current.data_revision,
                idempotency_key=f"provenance-{kind}",
            )
        )
        assert result.accepted is True
        assert assumption_repository.saved[-1].provenance is CaseValueKind.FOUNDER_STATEMENT


def _service(
    case_repository: _CaseRepository,
    assumption_repository: _AssumptionRepository,
) -> CaseFactIntakeService:
    return CaseFactIntakeService(
        case_repository=case_repository,
        assumption_repository=assumption_repository,
        question_service_factory=lambda answers: _NextQuestionService(),
    )


class _CaseRepository:
    def __init__(self) -> None:
        self.current = _case(1)
        self.advance_calls: list[tuple[UUID, int, int]] = []

    def get(self, case_id: UUID) -> DueDiligenceCase:
        if case_id != CASE_ID:
            raise KeyError(f"case_not_found:{case_id}")
        return self.current

    def advance_data_revision(
        self,
        case_id: UUID,
        *,
        expected_revision: int,
        updated_case: DueDiligenceCase,
    ) -> DueDiligenceCase:
        self.advance_calls.append((case_id, expected_revision, updated_case.data_revision))
        if self.current.data_revision != expected_revision:
            raise ValueError("case_data_revision_conflict")
        self.current = updated_case
        return self.current


class _AssumptionRepository:
    def __init__(self) -> None:
        self.saved: list[FounderStatement] = []

    def save(
        self,
        value: FounderStatement,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> FounderStatement:
        del idempotency_key
        assert getattr(value, "data_revision") == expected_revision
        self.saved.append(value)
        return value

    def get_current(self, case_id: UUID) -> tuple[FounderStatement, ...]:
        assert case_id == CASE_ID
        return tuple(self.saved)


class _NextQuestionService:
    def next_question(self, case_id: UUID, *, page_context: str, focus_key: str | None) -> object:
        del page_context, focus_key
        assert case_id == CASE_ID
        return _Question(requirement_key="buyer")


@dataclass(frozen=True)
class _Question:
    requirement_key: str


def _case(data_revision: int) -> DueDiligenceCase:
    return DueDiligenceCase(
        case_id=CASE_ID,
        mode=AnalysisMode.STARTUP,
        entity_name="FounderCo",
        entity_identifier=str(CASE_ID),
        jurisdiction="KZ",
        scope=("startup",),
        as_of=AS_OF,
        base_currency="KZT",
        privacy_policy="startup-local@1",
        budget_policy="offline",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
        updated_at=AS_OF,
        workflow_version="startup-graph@1",
        data_revision=data_revision,
    )
