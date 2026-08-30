from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from due_diligence_agent.adapters.local_storage.repositories import (
    LocalCaseRepository,
    LocalContradictionRepository,
)
from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.application.services.source_fact_contradiction_service import (
    SourceFactContradictionService,
)
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    CaseStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import EvidenceFact


CASE_ID = UUID("00000000-0000-0000-0000-000000000771")
FIRST_ARTIFACT_ID = UUID("10000000-0000-0000-0000-000000000771")
SECOND_ARTIFACT_ID = UUID("10000000-0000-0000-0000-000000000772")
FIRST_FACT_ID = UUID("20000000-0000-0000-0000-000000000771")
SECOND_FACT_ID = UUID("20000000-0000-0000-0000-000000000772")
NOW = datetime(2026, 8, 14, tzinfo=UTC)


def test_materialize_persists_one_deterministic_cross_source_numeric_conflict_after_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "source-conflicts.sqlite3"
    database = SQLiteDatabase(database_path)
    LocalCaseRepository(database).add(_case())
    repository = LocalContradictionRepository(database)
    first = _fact(
        fact_id=FIRST_FACT_ID,
        artifact_id=FIRST_ARTIFACT_ID,
        name=" Orders ",
        value="720",
        unit="COUNT",
        period=" 2026-07 ",
        sensitivity=SensitivityClass.CONFIDENTIAL,
    )
    second = _fact(
        fact_id=SECOND_FACT_ID,
        artifact_id=SECOND_ARTIFACT_ID,
        name="orders",
        value="680",
        unit="count",
        period="2026-07",
        sensitivity=SensitivityClass.RESTRICTED,
    )

    created = SourceFactContradictionService(
        contradiction_repository=repository,
        clock=lambda: NOW,
    ).materialize(case_id=CASE_ID, evidence_facts=(second, first))
    reopened_repository = LocalContradictionRepository(SQLiteDatabase(database_path))
    repeated = SourceFactContradictionService(
        contradiction_repository=reopened_repository,
        clock=lambda: datetime(2030, 1, 1, tzinfo=UTC),
    ).materialize(case_id=CASE_ID, evidence_facts=(first, second))

    assert len(created) == 1
    assert repeated == created
    assert reopened_repository.list_for_case(CASE_ID) == list(created)
    contradiction = created[0]
    assert contradiction.conflict_type == "source_fact_value_conflict"
    assert contradiction.fact_ids == (FIRST_FACT_ID, SECOND_FACT_ID)
    assert contradiction.sensitivity is SensitivityClass.RESTRICTED
    assert contradiction.detected_at == NOW
    serialized = contradiction.model_dump_json()
    assert "orders" not in serialized
    assert "720" not in serialized
    assert "680" not in serialized


def test_materialize_ignores_non_cross_source_or_non_numeric_differences(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "ignored-source-conflicts.sqlite3")
    LocalCaseRepository(database).add(_case())
    repository = LocalContradictionRepository(database)
    service = SourceFactContradictionService(
        contradiction_repository=repository,
        clock=lambda: NOW,
    )
    facts = (
        _fact(
            fact_id=FIRST_FACT_ID,
            artifact_id=FIRST_ARTIFACT_ID,
            name="orders",
            value="720",
        ),
        _fact(
            fact_id=SECOND_FACT_ID,
            artifact_id=FIRST_ARTIFACT_ID,
            name="orders",
            value="680",
        ),
        _fact(
            fact_id=UUID("20000000-0000-0000-0000-000000000773"),
            artifact_id=SECOND_ARTIFACT_ID,
            name="same_value",
            value="5",
        ),
        _fact(
            fact_id=UUID("20000000-0000-0000-0000-000000000774"),
            artifact_id=FIRST_ARTIFACT_ID,
            name="same_value",
            value="5",
        ),
        _fact(
            fact_id=UUID("20000000-0000-0000-0000-000000000775"),
            artifact_id=FIRST_ARTIFACT_ID,
            name="narrative",
            value="first",
            value_type="text",
            unit=None,
            period=None,
        ),
        _fact(
            fact_id=UUID("20000000-0000-0000-0000-000000000776"),
            artifact_id=SECOND_ARTIFACT_ID,
            name="narrative",
            value="second",
            value_type="text",
            unit=None,
            period=None,
        ),
    )

    assert service.materialize(case_id=CASE_ID, evidence_facts=facts) == ()
    assert repository.list_for_case(CASE_ID) == []


def test_materialize_does_not_reopen_value_conflict_after_founder_accepts_one_source(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "accepted-founder-source.sqlite3")
    LocalCaseRepository(database).add(_case())
    repository = LocalContradictionRepository(database)
    crm = _fact(
        fact_id=FIRST_FACT_ID,
        artifact_id=FIRST_ARTIFACT_ID,
        name="monthly_recurring_revenue",
        value="28600000",
        unit="KZT",
        period="unknown",
    )
    invoices = _fact(
        fact_id=SECOND_FACT_ID,
        artifact_id=SECOND_ARTIFACT_ID,
        name="monthly_recurring_revenue",
        value="27900000",
        unit="KZT",
        period="unknown",
    )
    accepted = _fact(
        fact_id=UUID("20000000-0000-0000-0000-000000000777"),
        artifact_id=SECOND_ARTIFACT_ID,
        name="monthly_recurring_revenue",
        value="27900000",
        unit="KZT",
        period="unknown",
        metadata={"founder_clarification": "accepted_source"},
    )

    created = SourceFactContradictionService(
        contradiction_repository=repository,
        clock=lambda: NOW,
    ).materialize(case_id=CASE_ID, evidence_facts=(crm, invoices, accepted))

    assert created == ()
    assert repository.list_for_case(CASE_ID) == []


def _case() -> DueDiligenceCase:
    return DueDiligenceCase(
        case_id=CASE_ID,
        mode=AnalysisMode.STARTUP,
        entity_name="Startup data room",
        entity_identifier=str(CASE_ID),
        jurisdiction="local",
        scope=("uploaded_data_room",),
        period_start=None,
        period_end=None,
        as_of=NOW,
        base_currency="USD",
        privacy_policy="startup-local@1",
        budget_policy="startup-local@1",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=NOW,
        updated_at=NOW,
        workflow_version="startup-source-conflicts@1",
        data_revision=1,
    )


def _fact(
    *,
    fact_id: UUID,
    artifact_id: UUID,
    name: str,
    value: str,
    value_type: str = "decimal",
    unit: str | None = "count",
    period: str | None = "2026-07",
    sensitivity: SensitivityClass = SensitivityClass.CONFIDENTIAL,
    metadata: dict[str, str] | None = None,
) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id,
        artifact_id=artifact_id,
        name=name,
        value=Decimal(value) if value_type == "decimal" else value,
        value_type=value_type,
        unit=unit,
        period=period,
        locator=SourceLocator(
            kind="csv_cell",
            value=f"sheet!{fact_id}",
            artifact_id=artifact_id,
        ),
        sensitivity=sensitivity,
        confidence=Decimal("0.80"),
        source_priority=1,
        extraction_method="spreadsheet_parser",
        supporting_text_hash="a" * 64,
        metadata=metadata or {},
    )
