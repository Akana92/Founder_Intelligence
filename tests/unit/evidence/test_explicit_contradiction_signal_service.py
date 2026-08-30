from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from due_diligence_agent.application.services.explicit_contradiction_signal_service import (
    ExplicitContradictionSignalService,
)
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import ContradictionStatus, SensitivityClass
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction


CASE_ID = UUID("50000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("50000000-0000-0000-0000-000000000002")
FACT_ID = UUID("50000000-0000-0000-0000-000000000003")
RAW_SENTINEL = "agencies versus enterprises ICP"


def test_materializes_generic_explicit_contradiction_signal_without_raw_text_leak() -> None:
    repository = _Repository()
    service = ExplicitContradictionSignalService(
        contradiction_repository=repository,
        clock=lambda: datetime(2026, 8, 13, tzinfo=UTC),
    )

    first = service.materialize_from_text(
        case_id=CASE_ID,
        text_fact=_text_fact(),
        text=f"Contradiction: {RAW_SENTINEL}.",
    )
    repeated = service.materialize_from_text(
        case_id=CASE_ID,
        text_fact=_text_fact(),
        text=f"Contradiction: {RAW_SENTINEL}.",
    )

    assert [item.id for item in repeated] == [item.id for item in first]
    assert len(repository.items) == 1
    contradiction = repository.items[0]
    assert contradiction.conflict_type == "explicit_source_conflict_signal"
    assert contradiction.fact_ids == (FACT_ID,)
    assert contradiction.status is ContradictionStatus.OPEN
    assert RAW_SENTINEL not in contradiction.model_dump_json()
    assert "source document explicitly flags" in contradiction.explanation


def test_materializes_bounded_icp_context_without_raw_phrase_leak() -> None:
    repository = _Repository()
    service = ExplicitContradictionSignalService(
        contradiction_repository=repository,
        clock=lambda: datetime(2026, 8, 13, tzinfo=UTC),
    )

    result = service.materialize_from_text(
        case_id=CASE_ID,
        text_fact=_text_fact(),
        text=f"Contradiction: {RAW_SENTINEL}.",
    )

    assert len(result) == 1
    contradiction = repository.items[0]
    dumped = contradiction.model_dump_json()
    assert RAW_SENTINEL not in dumped
    assert "field=icp" in contradiction.explanation
    assert "metric=ICP" in contradiction.explanation
    assert "agencies" in contradiction.explanation
    assert "enterprises" in contradiction.explanation


def test_materializes_bounded_metric_context_with_normalized_source_and_value_tokens() -> None:
    repository = _Repository()
    service = ExplicitContradictionSignalService(
        contradiction_repository=repository,
        clock=lambda: datetime(2026, 8, 13, tzinfo=UTC),
    )

    result = service.materialize_from_text(
        case_id=CASE_ID,
        text_fact=_text_fact(),
        text="MRR CONTRADICTION CRM 28,6 млн KZT; invoices 27,9 млн KZT; bank supports 27,9 млн KZT.",
    )

    assert len(result) == 1
    explanation = repository.items[0].explanation
    assert "field=revenue_pricing" in explanation
    assert "metric=MRR" in explanation
    assert "sources=crm|invoices|bank" in explanation
    assert "values=28.6m KZT|27.9m KZT" in explanation
    dumped = repository.items[0].model_dump_json()
    assert "28,6" not in dumped
    assert "27,9" not in dumped


def test_requires_both_explicit_marker_and_conflict_cue() -> None:
    repository = _Repository()
    service = ExplicitContradictionSignalService(contradiction_repository=repository)

    for text in (
        "The startup compares agencies versus enterprises.",
        "Contradiction: the customer profile needs review.",
        "The startup targets agencies and later expands to enterprise customers.",
    ):
        assert (
            service.materialize_from_text(
                case_id=CASE_ID,
                text_fact=_text_fact(),
                text=text,
            )
            == ()
        )
    assert repository.items == []


def test_ignores_negated_or_resolved_contradiction_markers_with_conflict_cues() -> None:
    repository = _Repository()
    service = ExplicitContradictionSignalService(contradiction_repository=repository)

    for text in (
        "No contradiction: supply count differs from CSV, because the CSV is stale.",
        "No contradiction MRR CRM 28; invoices 29.",
        "Not a contradiction: order count conflicts with receipt OCR only in archived data.",
        "Not a contradiction MRR CRM 28; invoices 29.",
        "Contradiction resolved: ARR differs between deck and metrics after currency normalization.",
        "Resolved contradiction: agencies versus enterprises ICP now share one segment definition.",
        "Resolved contradiction MRR CRM 28; invoices 29.",
    ):
        assert (
            service.materialize_from_text(
                case_id=CASE_ID,
                text_fact=_text_fact(),
                text=text,
            )
            == ()
        )
    assert repository.items == []


def test_materializes_fixture_phrase_shapes_without_case_specific_matching() -> None:
    repository = _Repository()
    service = ExplicitContradictionSignalService(
        contradiction_repository=repository,
        clock=lambda: datetime(2026, 8, 13, tzinfo=UTC),
    )

    for index, text in enumerate(
        (
            "Contradiction: supply count differs from CSV.",
            "Contradiction: agencies versus enterprises ICP.",
            "Contradiction: ARR differs between deck and metrics.",
            "Contradiction: order count conflicts with receipt OCR.",
        ),
        start=10,
    ):
        result = service.materialize_from_text(
            case_id=CASE_ID,
            text_fact=_text_fact(UUID(f"50000000-0000-0000-0000-0000000000{index}")),
            text=text,
        )
        assert len(result) == 1

    assert len(repository.items) == 4
    assert all(item.conflict_type == "explicit_source_conflict_signal" for item in repository.items)


def test_materializes_numeric_table_contradiction_row_without_raw_values() -> None:
    repository = _Repository()
    service = ExplicitContradictionSignalService(
        contradiction_repository=repository,
        clock=lambda: datetime(2026, 8, 13, tzinfo=UTC),
    )

    result = service.materialize_from_text(
        case_id=CASE_ID,
        text_fact=_text_fact(),
        text="MRR CONTRADICTION CRM 28,6 млн ₸; invoices 27,9 млн ₸",
    )

    assert len(result) == 1
    assert repository.items[0].status is ContradictionStatus.OPEN
    dumped = repository.items[0].model_dump_json()
    assert "28,6" not in dumped
    assert "27,9" not in dumped


def test_does_not_materialize_heading_only_contradiction_marker() -> None:
    repository = _Repository()
    service = ExplicitContradictionSignalService(contradiction_repository=repository)

    assert (
        service.materialize_from_text(
            case_id=CASE_ID,
            text_fact=_text_fact(),
            text="CONTRADICTION: MRR",
        )
        == ()
    )
    assert repository.items == []


def test_does_not_materialize_numeric_marker_without_competing_observation_context() -> None:
    repository = _Repository()
    service = ExplicitContradictionSignalService(contradiction_repository=repository)

    for text in (
        "Runway CONTRADICTION values 18 and 7 require normal planning review",
        "Runway CONTRADICTION values 18; 7 require normal planning review",
        "MRR CONTRADICTION values 28; 29 need review",
        "Runway CONTRADICTION values 18\n7 require normal planning review",
        "MRR CONTRADICTION values 28\n29 need review",
        "MRR CONTRADICTION check 28; todo 29",
        "Runway CONTRADICTION note 18; pending 7",
        "MRR CONTRADICTION CRM 28; CRM 29",
        "MRR CONTRADICTION invoice 28; invoice 29",
    ):
        assert (
            service.materialize_from_text(
                case_id=CASE_ID,
                text_fact=_text_fact(),
                text=text,
            )
            == ()
        )
    assert repository.items == []


class _Repository:
    def __init__(self) -> None:
        self.items: list[Contradiction] = []

    def add(self, contradiction: Contradiction) -> None:
        if any(item.id == contradiction.id for item in self.items):
            raise ValueError("contradiction_already_exists")
        self.items.append(contradiction)

    def list_for_case(self, case_id: UUID) -> list[Contradiction]:
        return [item for item in self.items if item.case_id == case_id]


def _text_fact(fact_id: UUID = FACT_ID) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id,
        artifact_id=ARTIFACT_ID,
        name="source_text_block",
        value="evidence_ref:abc123",
        value_type="text",
        unit=None,
        period=None,
        locator=SourceLocator(kind="paragraph", value="paragraph:1", artifact_id=ARTIFACT_ID),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.90"),
        extraction_method="startup_text_block",
        supporting_text_hash="a" * 64,
    )
