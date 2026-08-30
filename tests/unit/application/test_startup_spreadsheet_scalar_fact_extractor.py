from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from due_diligence_agent.application.services.startup_spreadsheet_scalar_fact_extractor import (
    StartupSpreadsheetScalarFactExtractor,
)
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.documents.tabular import (
    NormalizedCell,
    NormalizedTable,
    SpreadsheetParseResult,
)


CASE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_A = UUID("11111111-1111-1111-1111-111111111111")
ARTIFACT_B = UUID("22222222-2222-2222-2222-222222222222")
SNAPSHOT_A = "a" * 64
SNAPSHOT_B = "b" * 64
CellValue = bool | Decimal | str | None


def test_extracts_long_form_startup_scalar_rows_from_multiple_artifacts() -> None:
    extractor = StartupSpreadsheetScalarFactExtractor()
    first = _parsed_artifact(
        artifact_id=ARTIFACT_A,
        snapshot_hash=SNAPSHOT_A,
        rows=[
            ("Orders", Decimal("720"), "count", "2026-Q1"),
            ("Active Suppliers", Decimal("18"), "count", "2026-06"),
        ],
    )
    second = _parsed_artifact(
        artifact_id=ARTIFACT_B,
        snapshot_hash=SNAPSHOT_B,
        rows=[("Orders", Decimal("680"), "count", "2026-Q2")],
    )

    facts = [
        *extractor.extract(first, sensitivity=SensitivityClass.CONFIDENTIAL),
        *extractor.extract(second, sensitivity=SensitivityClass.CONFIDENTIAL),
    ]

    assert [(fact.name, fact.value, fact.unit, fact.period) for fact in facts] == [
        ("orders", Decimal("720"), "count", "2026-Q1"),
        ("active_suppliers", Decimal("18"), "count", "2026-06"),
        ("orders", Decimal("680"), "count", "2026-Q2"),
    ]
    assert [fact.artifact_id for fact in facts] == [ARTIFACT_A, ARTIFACT_A, ARTIFACT_B]
    assert [fact.sensitivity for fact in facts] == [SensitivityClass.CONFIDENTIAL] * 3
    assert facts[0].supporting_text_hash == facts[1].supporting_text_hash
    assert facts[2].supporting_text_hash != SNAPSHOT_B
    assert all(
        fact.supporting_text_hash is not None
        and len(fact.supporting_text_hash) == 64
        and set(fact.supporting_text_hash) <= set("0123456789abcdef")
        for fact in facts
    )
    assert [fact.locator.value for fact in facts] == ["R2C2", "R3C2", "R2C2"]


def test_ids_are_deterministic_and_existing_canonical_facts_are_not_duplicated() -> None:
    extractor = StartupSpreadsheetScalarFactExtractor()
    parsed = _parsed_artifact(
        artifact_id=ARTIFACT_A,
        snapshot_hash=SNAPSHOT_A,
        rows=[("Orders", Decimal("720"), "count", "2026-Q1")],
    )

    facts = extractor.extract(parsed, sensitivity=SensitivityClass.RESTRICTED)
    repeated = extractor.extract(
        parsed,
        sensitivity=SensitivityClass.RESTRICTED,
        existing_facts=facts,
    )

    assert [fact.id for fact in extractor.extract(parsed, sensitivity=SensitivityClass.RESTRICTED)] == [
        facts[0].id
    ]
    assert repeated == []


def test_rejects_formulas_private_labels_unsafe_formats_and_missing_context() -> None:
    parsed = _parsed_artifact(
        artifact_id=ARTIFACT_A,
        snapshot_hash=SNAPSHOT_A,
        rows=[
            ("=Orders", Decimal("720"), "count", "2026-Q1"),
            ("Founder personal phone", Decimal("5551234"), "count", "2026-Q1"),
            ("Very / Unsafe Metric", Decimal("5"), "count", "2026-Q1"),
            ("Orders", Decimal("11"), "widgets", "2026-Q1"),
            ("Orders", Decimal("12"), "count", "FY2026"),
            ("Orders", Decimal("13"), "count", "2026-13"),
            ("Orders", "720", "count", "2026-Q1"),
            ("Orders", Decimal("14"), "count", "2026-Q1", True),
        ],
    )

    assert (
        StartupSpreadsheetScalarFactExtractor().extract(
            parsed,
            sensitivity=SensitivityClass.RESTRICTED,
        )
        == []
    )


def _parsed_artifact(
    *,
    artifact_id: UUID,
    snapshot_hash: str,
    rows: list[tuple[str, CellValue, str, str] | tuple[str, CellValue, str, str, bool]],
) -> ParsedStartupArtifact:
    table = NormalizedTable(
        artifact_id=artifact_id,
        name="metrics",
        cells=_cells(artifact_id, rows),
        snapshot_hash=snapshot_hash,
        snapshot_ref=snapshot_hash,
        row_count=len(rows) + 1,
        column_count=4,
    )
    return ParsedStartupArtifact.from_spreadsheet(
        SpreadsheetParseResult(
            artifact_id=artifact_id,
            tables=[table],
            status="parsed",
        ),
        case_id=CASE_ID,
        detected_mime_type="text/csv",
        parser_name="test",
        parser_version="1",
    )


def _cells(
    artifact_id: UUID,
    rows: list[tuple[str, CellValue, str, str] | tuple[str, CellValue, str, str, bool]],
) -> list[NormalizedCell]:
    headers = ["Metric", "Value", "Unit", "Period"]
    cells = [
        _cell(artifact_id, row=1, column=column, value=header)
        for column, header in enumerate(headers, start=1)
    ]
    for row_index, row in enumerate(rows, start=2):
        metric, value, unit, period = row[:4]
        formula_cached = row[4] if len(row) == 5 else None
        cells.extend(
            [
                _cell(artifact_id, row=row_index, column=1, value=metric),
                _cell(
                    artifact_id,
                    row=row_index,
                    column=2,
                    value=value,
                    formula_cached=formula_cached,
                ),
                _cell(artifact_id, row=row_index, column=3, value=unit),
                _cell(artifact_id, row=row_index, column=4, value=period),
            ]
        )
    return cells


def _cell(
    artifact_id: UUID,
    *,
    row: int,
    column: int,
    value: CellValue,
    formula_cached: bool | None = None,
) -> NormalizedCell:
    return NormalizedCell(
        row=row,
        column=column,
        value=value,
        locator=SourceLocator(
            kind="csv_cell",
            value=f"R{row}C{column}",
            artifact_id=artifact_id,
            table="metrics",
            cell=f"R{row}C{column}",
        ),
        status="insufficient_data",
        formula_cached=formula_cached,
    )
