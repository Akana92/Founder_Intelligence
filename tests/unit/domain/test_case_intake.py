from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from due_diligence_agent.domain.startup.case_intake import (
    CaseFactRequirement,
    CaseStage,
    CaseValueKind,
    FounderStatement,
)


def test_case_value_kind_keeps_source_founder_public_ai_and_contradiction_distinct() -> None:
    assert CaseValueKind.SOURCE_FACT.value == "source_fact"
    assert CaseValueKind.FOUNDER_STATEMENT.value == "founder_statement"
    assert CaseValueKind.PUBLIC_BENCHMARK.value == "public_benchmark"
    assert CaseValueKind.DETERMINISTIC_CALCULATION.value == "deterministic_calculation"
    assert CaseValueKind.AI_SCENARIO.value == "ai_scenario"
    assert CaseValueKind.CONTRADICTION.value == "contradiction"
    assert len({kind.value for kind in CaseValueKind}) == 6


def test_case_stage_uses_the_founder_launch_lifecycle_values() -> None:
    assert tuple(stage.value for stage in CaseStage) == (
        "idea",
        "first_sales",
        "growth",
    )


def test_founder_statement_is_case_revision_scoped_and_never_auto_promotes_to_source_fact() -> None:
    statement = FounderStatement(
        statement_id=uuid4(),
        case_id=uuid4(),
        data_revision=1,
        field_key="monthly_price",
        value="30000 KZT/month",
        confidence=Decimal("0.45"),
        source_refs=(),
        rationale="Founder interview answer",
    )

    assert statement.provenance is CaseValueKind.FOUNDER_STATEMENT

    with pytest.raises(ValidationError, match="founder statements cannot be source_fact"):
        FounderStatement(
            statement_id=uuid4(),
            case_id=statement.case_id,
            data_revision=1,
            field_key="monthly_price",
            value="30000 KZT/month",
            confidence=Decimal("0.45"),
            provenance=CaseValueKind.SOURCE_FACT,
            source_refs=(),
            rationale="Founder interview answer",
        )


def test_case_fact_requirement_is_immutable_and_requires_source_fact_or_public_benchmark_refs() -> None:
    requirement = CaseFactRequirement(
        requirement_id=uuid4(),
        case_id=uuid4(),
        data_revision=2,
        field_key="currency_period",
        required_kind=CaseValueKind.SOURCE_FACT,
        prompt="Upload billing export with currency and period",
        source_refs=(uuid4(),),
    )

    with pytest.raises(ValidationError, match="frozen_instance"):
        requirement.prompt = "mutated"  # type: ignore[misc]

    with pytest.raises(ValidationError, match="source refs"):
        CaseFactRequirement(
            requirement_id=uuid4(),
            case_id=requirement.case_id,
            data_revision=2,
            field_key="market_benchmark",
            required_kind=CaseValueKind.PUBLIC_BENCHMARK,
            prompt="Attach public benchmark source",
            source_refs=(),
        )
