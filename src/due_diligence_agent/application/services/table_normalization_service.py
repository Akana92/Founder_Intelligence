from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import duckdb

from due_diligence_agent.domain.artifacts.models import Artifact
from due_diligence_agent.domain.documents.tabular import (
    NormalizedCell,
    NormalizedTable,
    SheetVisibility,
)
from due_diligence_agent.ports.repositories import ArtifactStore


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS normalized_table_snapshots (
    snapshot_hash VARCHAR PRIMARY KEY,
    artifact_id VARCHAR NOT NULL,
    table_name VARCHAR NOT NULL,
    storage_ref VARCHAR NOT NULL
)
"""
_INSERT_SQL = """
INSERT INTO normalized_table_snapshots (
    snapshot_hash, artifact_id, table_name, storage_ref
) VALUES (?, ?, ?, ?)
ON CONFLICT (snapshot_hash) DO NOTHING
"""


class TableNormalizationService:
    def __init__(self, *, artifact_store: ArtifactStore, database_path: Path) -> None:
        self._artifact_store = artifact_store
        self._database_path = database_path.resolve()
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def normalize_and_store(
        self,
        *,
        artifact: Artifact,
        name: str,
        cells: list[NormalizedCell],
        visibility: SheetVisibility,
        row_count: int,
        column_count: int,
    ) -> NormalizedTable:
        ordered_cells = sorted(cells, key=lambda cell: (cell.row, cell.column))
        snapshot = {
            "artifact_id": str(artifact.id),
            "cells": [_canonical_cell(cell) for cell in ordered_cells],
            "column_count": column_count,
            "name": name,
            "row_count": row_count,
            "visibility": visibility,
        }
        payload = json.dumps(
            snapshot,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        stored = self._artifact_store.put_bytes(
            payload,
            media_type="application/vnd.due-diligence.normalized-table+json",
            artifact_id=artifact.id,
            source_snapshot_hash=artifact.source_snapshot_hash,
            sensitivity=artifact.sensitivity,
        )
        self._record_snapshot(
            snapshot_hash=stored.content_hash,
            artifact_id=str(artifact.id),
            table_name=name,
            storage_ref=stored.content_hash,
        )
        return NormalizedTable(
            artifact_id=artifact.id,
            name=name,
            cells=ordered_cells,
            snapshot_hash=stored.content_hash,
            snapshot_ref=stored.content_hash,
            visibility=visibility,
            row_count=row_count,
            column_count=column_count,
        )

    def _initialize_schema(self) -> None:
        connection = duckdb.connect(str(self._database_path))
        try:
            connection.execute("BEGIN TRANSACTION")
            connection.execute(_SCHEMA_SQL)
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _record_snapshot(
        self,
        *,
        snapshot_hash: str,
        artifact_id: str,
        table_name: str,
        storage_ref: str,
    ) -> None:
        connection = duckdb.connect(str(self._database_path))
        try:
            connection.execute("BEGIN TRANSACTION")
            connection.execute(
                _INSERT_SQL,
                [snapshot_hash, artifact_id, table_name, storage_ref],
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


def _canonical_cell(cell: NormalizedCell) -> dict[str, object]:
    value: object
    value_type: str
    if cell.value is None:
        value = None
        value_type = "null"
    elif isinstance(cell.value, bool):
        value = cell.value
        value_type = "boolean"
    elif isinstance(cell.value, date):
        value = cell.value.isoformat()
        value_type = "date"
    elif isinstance(cell.value, Decimal):
        value = str(cell.value.normalize())
        value_type = "decimal"
    else:
        value = cell.value
        value_type = "text"
    return {
        "column": cell.column,
        "formula_cached": cell.formula_cached,
        "label": cell.label,
        "locator": cell.locator.model_dump(mode="json"),
        "period": cell.period,
        "row": cell.row,
        "status": cell.status,
        "unit": cell.unit,
        "value": value,
        "value_type": value_type,
    }
