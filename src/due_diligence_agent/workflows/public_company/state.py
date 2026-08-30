from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from operator import add
from typing import Annotated, Any, TypedDict

from due_diligence_agent.workflows.shared.plan import AnalysisPlan


def extend_unique(left: Sequence[str], right: Sequence[str]) -> list[str]:
    result = list(left)
    for item in right:
        if item not in result:
            result.append(item)
    return result


class PublicCaseState(TypedDict, total=False):
    case_id: str
    ticker: str
    as_of: str
    status: str
    plan: AnalysisPlan
    artifact_ids: Annotated[list[str], extend_unique]
    evidence_fact_ids: Annotated[list[str], extend_unique]
    chunk_ids: Annotated[list[str], extend_unique]
    calculation_ids: Annotated[list[str], extend_unique]
    finding_ids: Annotated[list[str], extend_unique]
    contradiction_ids: Annotated[list[str], extend_unique]
    warnings: Annotated[list[str], extend_unique]
    errors: Annotated[list[str], extend_unique]
    approvals: Annotated[list[dict[str, Any]], add]
    node_results: Annotated[list[dict[str, Any]], add]
    reflexion_round_count: int
    reflexion_progress: bool
    new_evidence_ids: Annotated[list[str], extend_unique]
    updated_finding_ids: Annotated[list[str], extend_unique]
    forced_executive_summary_contradiction_ids: Annotated[list[str], extend_unique]
    data_revision: int
    final_pdf_allowed: bool
    draft_json_artifact_ref: str | None
    draft_html_artifact_ref: str | None
    report_snapshot_id: str | None
    correlation_id: str
    trace_id: str
    primary_failure: str | None
    normalized_collection: bool
    generated_at: datetime
