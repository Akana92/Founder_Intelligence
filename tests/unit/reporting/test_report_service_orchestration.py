from __future__ import annotations

import ast
from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4

import pytest

from due_diligence_agent.adapters.reports.html_renderer import HtmlRenderer
from due_diligence_agent.application.services.report_service import ReportService
from due_diligence_agent.application.services.startup_report_service import (
    STARTUP_REPORT_SECTION_KEYS,
    StartupReportSnapshotBuilder,
)
from due_diligence_agent.application.services.startup_readiness_service import (
    StartupReadinessService,
)
from tests.unit.reporting.test_startup_report_snapshot import AS_OF
from tests.unit.reporting.test_startup_report_snapshot import _input


def test_startup_json_and_html_are_derived_from_same_snapshot_and_template(
    local_tmp_path: Path,
) -> None:
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(_input())
    service = ReportService(html_renderer=HtmlRenderer())

    draft = service.render_draft(snapshot, local_tmp_path)

    payload = json.loads(draft.json_path.read_text(encoding="utf-8"))
    html = draft.html_path.read_text(encoding="utf-8")
    assert payload["schema"] == "startup_report_snapshot.v1"
    assert payload["id"] == str(snapshot.id)
    assert payload["report_hash"] == snapshot.report_hash
    assert tuple(payload["sections"])[:12] == STARTUP_REPORT_SECTION_KEYS
    assert "Отчёт для основателя" in html
    assert "Каноническая схема: startup_report_snapshot.v1" in html
    assert str(snapshot.id) not in html
    assert snapshot.report_hash not in html
    assert "Public Due Diligence Report" not in html
    assert draft.snapshot.json_artifact_ref == f"sha256:{_sha256_file(draft.json_path)}"
    assert draft.snapshot.html_artifact_ref == f"sha256:{_sha256_file(draft.html_path)}"


def test_startup_html_gets_render_only_charts_without_mutating_canonical_json(
    local_tmp_path: Path,
) -> None:
    base_input = _input()
    readiness = StartupReadinessService(clock=lambda: AS_OF).evaluate(
        base_input.startup_profile,
        (),
        calculation_ids=tuple(calculation.id for calculation in base_input.calculations),
    )
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(
        replace(base_input, startup_readiness=readiness)
    )
    service = ReportService(html_renderer=HtmlRenderer())

    draft = service.render_draft(snapshot, local_tmp_path)

    payload = json.loads(draft.json_path.read_text(encoding="utf-8"))
    html = draft.html_path.read_text(encoding="utf-8")
    assert "chart_data_uri" not in json.dumps(payload, sort_keys=True)
    assert "data:image/png;base64," in html
    assert html.count('class="chart"') == 3
    assert 'alt="Диаграмма покрытия отчёта"' in html
    assert 'alt="Диаграмма подтверждённых метрик"' in html
    assert 'alt="Диаграмма готовности метрик"' in html
    assert 'id="technical-appendix"' in html
    technical_appendix_html = html.split('id="technical-appendix"', 1)[1]
    assert "data:image/png;base64," not in technical_appendix_html
    assert draft.snapshot.id == snapshot.id
    assert draft.snapshot.report_hash == snapshot.report_hash


def test_report_services_do_not_import_private_helpers_from_each_other() -> None:
    startup_tree = ast.parse(
        Path("src/due_diligence_agent/application/services/startup_report_service.py").read_text(
            encoding="utf-8"
        )
    )
    report_tree = ast.parse(
        Path("src/due_diligence_agent/application/services/report_service.py").read_text(
            encoding="utf-8"
        )
    )

    startup_private_report_imports = _imported_names_from(
        startup_tree,
        "due_diligence_agent.application.services.report_service",
    )
    report_private_startup_imports = _imported_names_from(
        report_tree,
        "due_diligence_agent.application.services.startup_report_service",
    )

    assert not [name for name in startup_private_report_imports if name.startswith("_")]
    assert not [name for name in report_private_startup_imports if name.startswith("_")]


def _sha256_file(path: Path) -> str:
    from hashlib import sha256

    return sha256(path.read_bytes()).hexdigest()


def _imported_names_from(tree: ast.AST, module: str) -> tuple[str, ...]:
    return tuple(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == module
        for alias in node.names
    )


@pytest.fixture
def local_tmp_path() -> Path:
    path = Path(".tmp-task2-core-testdirs") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path
