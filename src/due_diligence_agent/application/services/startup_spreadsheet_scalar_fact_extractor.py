from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
import re
from collections.abc import Iterable
from uuid import UUID, uuid5

from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.documents.tabular import NormalizedCell, NormalizedTable
from due_diligence_agent.domain.evidence.models import EvidenceFact


_FACT_NAMESPACE = UUID("a4e0f62a-fdf5-5d8f-9150-9d7cb3396463")
_PERIOD = re.compile(r"^(?:\d{4}|\d{4}-Q[1-4]|\d{4}-(?:0[1-9]|1[0-2]))$")
_SAFE_LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9 ]{0,63}$")
_SAFE_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DANGEROUS_PREFIXES = ("=", "+", "-", "@")
_PRIVATE_TERMS = frozenset(
    {
        "address",
        "bank",
        "card",
        "email",
        "passport",
        "password",
        "personal",
        "phone",
        "secret",
        "ssn",
        "token",
    }
)
_UNIT_ALIASES = {
    "count": "count",
    "number": "count",
    "usd": "USD",
    "usd thousands": "USD thousands",
    "usd millions": "USD millions",
    "eur": "EUR",
    "eur thousands": "EUR thousands",
    "eur millions": "EUR millions",
    "gbp": "GBP",
    "gbp thousands": "GBP thousands",
    "gbp millions": "GBP millions",
    "percent": "percent",
    "%": "percent",
    "months": "months",
    "days": "days",
}
_HEADER_ALIASES = {
    "metric": "metric",
    "metric name": "metric",
    "name": "metric",
    "kpi": "metric",
    "value": "value",
    "amount": "value",
    "actual": "value",
    "unit": "unit",
    "units": "unit",
    "period": "period",
    "month": "period",
    "quarter": "period",
    "year": "period",
}


class StartupSpreadsheetScalarFactExtractor:
    def extract(
        self,
        parsed_artifact: ParsedStartupArtifact,
        *,
        sensitivity: SensitivityClass,
        existing_facts: Iterable[EvidenceFact] = (),
    ) -> list[EvidenceFact]:
        spreadsheet = parsed_artifact.spreadsheet
        if parsed_artifact.kind != "spreadsheet" or spreadsheet is None:
            return []

        seen = {_canonical_key(fact) for fact in existing_facts}
        facts: list[EvidenceFact] = []
        for table in spreadsheet.tables:
            table_content_hash = _table_content_hash(table)
            for metric_cell, value_cell, unit, period in _long_form_rows(table):
                metric = _metric_slug(metric_cell.value)
                if (
                    metric is None
                    or not isinstance(value_cell.value, Decimal)
                    or value_cell.formula_cached is not None
                    or not _safe_sibling_text(unit)
                    or not _safe_sibling_text(period)
                ):
                    continue
                canonical_unit = _unit(unit)
                canonical_period = _period(period)
                if canonical_unit is None or canonical_period is None:
                    continue
                key = (
                    parsed_artifact.artifact_id,
                    metric,
                    canonical_period,
                    canonical_unit,
                )
                if key in seen:
                    continue
                seen.add(key)
                facts.append(
                    EvidenceFact(
                        id=uuid5(
                            _FACT_NAMESPACE,
                            "\x1f".join(
                                (
                                    str(parsed_artifact.case_id),
                                    str(parsed_artifact.artifact_id),
                                    table_content_hash,
                                    value_cell.locator.value,
                                    metric,
                                    canonical_period,
                                    canonical_unit,
                                )
                            ),
                        ),
                        artifact_id=parsed_artifact.artifact_id,
                        name=metric,
                        value=value_cell.value,
                        value_type="decimal",
                        unit=canonical_unit,
                        period=canonical_period,
                        locator=value_cell.locator,
                        sensitivity=sensitivity,
                        confidence=Decimal("0.70"),
                        extraction_method="startup_spreadsheet_scalar_fact_extractor",
                        supporting_text_hash=table_content_hash,
                        metadata={"table": table.name},
                    )
                )
        return facts


def _long_form_rows(table: NormalizedTable) -> Iterable[tuple[NormalizedCell, NormalizedCell, str, str]]:
    rows: dict[int, dict[int, NormalizedCell]] = {}
    for cell in table.cells:
        rows.setdefault(cell.row, {})[cell.column] = cell
    header = _header_columns(rows)
    if header is None:
        return ()
    metric_column, value_column, unit_column, period_column, header_row = header
    result: list[tuple[NormalizedCell, NormalizedCell, str, str]] = []
    for row_number in sorted(rows):
        if row_number <= header_row:
            continue
        row = rows[row_number]
        metric_cell = row.get(metric_column)
        value_cell = row.get(value_column)
        unit_cell = row.get(unit_column)
        period_cell = row.get(period_column)
        if (
            metric_cell is None
            or value_cell is None
            or unit_cell is None
            or period_cell is None
            or not isinstance(unit_cell.value, str)
            or not isinstance(period_cell.value, str)
        ):
            continue
        result.append((metric_cell, value_cell, unit_cell.value, period_cell.value))
    return result


def _header_columns(rows: dict[int, dict[int, NormalizedCell]]) -> tuple[int, int, int, int, int] | None:
    for row_number in sorted(rows):
        found: dict[str, int] = {}
        for column, cell in rows[row_number].items():
            if not isinstance(cell.value, str):
                continue
            header = _HEADER_ALIASES.get(_normalize_text(cell.value))
            if header is not None:
                found.setdefault(header, column)
        if {"metric", "value", "unit", "period"} <= found.keys():
            return found["metric"], found["value"], found["unit"], found["period"], row_number
    return None


def _metric_slug(value: object) -> str | None:
    if not isinstance(value, str) or not _safe_sibling_text(value):
        return None
    normalized = _normalize_text(value)
    if any(term in normalized.split() for term in _PRIVATE_TERMS):
        return None
    if not _SAFE_LABEL.fullmatch(value.strip()):
        return None
    slug = re.sub(r"\s+", "_", normalized)
    if not _SAFE_SLUG.fullmatch(slug):
        return None
    return slug


def _safe_sibling_text(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and not stripped.startswith(_DANGEROUS_PREFIXES)


def _unit(value: str) -> str | None:
    return _UNIT_ALIASES.get(_normalize_text(value))


def _period(value: str) -> str | None:
    stripped = value.strip()
    return stripped if _PERIOD.fullmatch(stripped) else None


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _table_content_hash(table: NormalizedTable) -> str:
    payload = [
        {
            "row": cell.row,
            "column": cell.column,
            "value": _stable_cell_value(cell.value),
            "formula_cached": cell.formula_cached is not None,
        }
        for cell in sorted(table.cells, key=lambda item: (item.row, item.column))
    ]
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _stable_cell_value(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def _canonical_key(fact: EvidenceFact) -> tuple[UUID, str, str | None, str | None]:
    return (fact.artifact_id, fact.name, fact.period, fact.unit)
