from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import due_diligence_agent.application.services.report_service as report_service_module

from due_diligence_agent.adapters.reports.html_renderer import (
    HtmlRenderer,
    UnsafeReportTemplateError,
)
from due_diligence_agent.application.services.report_service import ReportService
from due_diligence_agent.application.services.startup_report_service import (
    StartupReportSnapshotBuilder,
)
from due_diligence_agent.domain.reports.models import ReportSnapshot
from tests.unit.reporting.test_startup_report_snapshot import _input


def test_startup_html_embeds_unit_safe_snapshot_derived_charts_without_mutating_json(
    local_tmp_path: Path,
) -> None:
    snapshot = _chart_ready_snapshot()
    service = ReportService(html_renderer=HtmlRenderer())

    draft = service.render_draft(snapshot, local_tmp_path)

    payload = json.loads(draft.json_path.read_text(encoding="utf-8"))
    html = draft.html_path.read_text(encoding="utf-8")
    assert html.count('data:image/png;base64,') == 5
    for chart_key in (
        "market_sizing",
        "confirmed_metrics",
        "readiness_coverage",
        "report_coverage",
    ):
        assert f'data-startup-chart="{chart_key}"' in html
    assert html.count('data-startup-chart="confirmed_metrics"') == 2
    assert "chart_data_uri" not in json.dumps(payload, sort_keys=True)
    assert "startup_charts" not in payload
    assert payload["report_hash"] == snapshot.report_hash


def test_startup_renderer_rejects_non_embedded_chart_sources() -> None:
    with pytest.raises(UnsafeReportTemplateError):
        HtmlRenderer().render(
            {
                "template": "startup_report.html.j2",
                "title": "Founder Startup Due Diligence Report",
                "snapshot_id": "snapshot-1",
                "as_of": "2026-08-15T00:00:00Z",
                "sections": {},
                "startup_charts": (
                    {
                        "key": "report_coverage",
                        "title": "Report coverage",
                        "summary": "Canonical section status counts.",
                        "chart_data_uri": "https://example.invalid/chart.png",
                    },
                ),
            }
        )


def test_startup_chart_projection_filters_rows_and_preserves_native_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, tuple[tuple[str, Decimal], ...]]] = []

    def capture_chart(
        title: str,
        points: tuple[tuple[str, Decimal], ...],
    ) -> str:
        captured.append((title, tuple(points)))
        return "data:image/png;base64,iVBORw0KGgo="

    monkeypatch.setattr(
        report_service_module,
        "startup_bar_chart_png_data_uri",
        capture_chart,
    )

    report_service_module._startup_chart_context(_chart_ready_snapshot())

    assert (
        "Market sizing",
        (
            ("TAM (USD customers)", Decimal("1200000000")),
            ("SAM (USD customers)", Decimal("260000000")),
            ("SOM (USD customers)", Decimal("18000000")),
        ),
    ) in captured
    assert ("Confirmed metrics", (("arr (USD)", Decimal("1200000")),)) in captured
    assert (
        "Confirmed metrics",
        (("gross_margin (ratio)", Decimal("0.72")),),
    ) in captured


@pytest.mark.parametrize("startup_charts", ["invalid", {"chart_data_uri": "invalid"}])
def test_startup_renderer_rejects_non_sequence_chart_context(startup_charts: object) -> None:
    with pytest.raises(UnsafeReportTemplateError):
        HtmlRenderer().render(
            {
                "template": "startup_report.html.j2",
                "title": "Founder Startup Due Diligence Report",
                "snapshot_id": "snapshot-1",
                "as_of": "2026-08-15T00:00:00Z",
                "sections": {},
                "startup_charts": startup_charts,
            }
        )


def _chart_ready_snapshot() -> ReportSnapshot:
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(_input())
    payload = snapshot.model_dump(mode="json")
    sections = payload["sections"]
    sections["market_size"] = {
        "title": "Market Size",
        "summary": "Frozen sourced TAM, SAM, and SOM.",
        "status": "SUPPORTED",
        "rows": (
            ("narrative", "source_fact", "999", "customers", "USD", "as_of=2026-08-15"),
            ("tam", "source_fact", "1200000000", "customers", "USD", "as_of=2026-08-15"),
            ("sam", "source_fact", "260000000", "customers", "USD", "as_of=2026-08-15"),
            ("som", "source_fact", "18000000", "customers", "USD", "as_of=2026-08-15"),
        ),
        "items": (),
    }
    sections["metrics"] = {
        "title": "Metrics",
        "summary": "Confirmed calculations and readiness diagnostics.",
        "status": "PARTIAL",
        "rows": (
            ("malformed", "1,2", "USD", "Q2 2026", "bad@1", "calculation_ref=bad"),
            ("arr", "1200000", "USD", "Q2 2026", "arr@1", "calculation_ref=calc-arr"),
            (
                "gross_margin",
                "0.72",
                "ratio",
                "Q2 2026",
                "gross-margin@1",
                "calculation_ref=calc-margin",
            ),
            ("activation", "ready", "evidence_complete", "dimension_ref=activation"),
            ("retention", "provisional", "partial_evidence", "dimension_ref=retention"),
            ("cac", "blocked", "missing_costs", "dimension_ref=cac"),
        ),
        "items": (),
    }
    sections["risks"] = {
        **sections["risks"],
        "status": "CONTRADICTION",
    }
    return ReportSnapshot.model_validate(payload)


@pytest.fixture
def local_tmp_path() -> Path:
    path = Path(".tmp-task2-core-testdirs") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path
