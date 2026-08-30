from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import sys
from types import ModuleType

from pytest import MonkeyPatch
from streamlit.testing.v1 import AppTest

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.application.services.startup_trace_query_service import (
    StartupLangSmithHealth,
    StartupTraceNodeRow,
    StartupTraceReportLineage,
    StartupTraceUsageSummary,
    StartupTraceView,
)
from due_diligence_agent.bootstrap import container as container_module
from due_diligence_agent.config import Settings
from due_diligence_agent.ports.tracing import AuditEvent
from due_diligence_agent.presentation.streamlit.components.audit import (
    _admin_dashboard_html,
    _render_admin_console_theme,
    build_admin_observability_snapshot,
    build_startup_trace_admin_snapshot,
)
from due_diligence_agent.presentation.streamlit.pages import admin as admin_page
from due_diligence_agent.presentation.streamlit.pages import public_case as public_case_page
from due_diligence_agent.presentation.streamlit.pages.admin import _read_admin_events


def test_admin_startup_run_options_include_safe_project_identity_and_correlatable_ids() -> None:
    event = AuditEvent(
        schema_version="audit_event@1",
        event_id="event-safe-1",
        timestamp_utc="2026-08-29T07:10:11Z",
        run_id="startup-api-11111111-2222-4333-8444-555555555555",
        correlation_id="corr-safe-1",
        span_name="startup.workflow",
        event_type="startup.workflow.completed",
        attributes={
            "case_id": "2dd8c3c7-69fb-4976-b148-2e96dc86bb40",
            "startup_name": "SMART UNIVERSITY",
            "status": "success",
            "unsafe_path": r"C:\Users\Akana\secret.pdf",
            "prompt": "never render this",
        },
    )

    options = admin_page._admin_startup_run_options(
        [event],
        project_names={"2dd8c3c7-69fb-4976-b148-2e96dc86bb40": "SMART UNIVERSITY"},
    )

    assert len(options) == 1
    label = next(iter(options))
    assert "SMART UNIVERSITY" in label
    assert "2dd8c3c7-69fb-4976-b" in label
    assert "2dd8c3c7-69fb-4976-b148-2e96dc86bb40" in label
    assert "startup-api-11111111" in label
    assert "2026-08-29 07:10:11 UTC" in label
    assert "success" in label
    assert "secret.pdf" not in label
    assert "prompt" not in label


def test_admin_startup_project_names_resolve_from_current_profile_without_raw_payload() -> None:
    case_id = "2dd8c3c7-69fb-4976-b148-2e96dc86bb40"

    class Field:
        values = ("SMART UNIVERSITY",)

    class Profile:
        fields = {"startup_name": Field()}

    class StartupProfileRepository:
        def get_current(self, requested_case_id):
            assert str(requested_case_id) == case_id
            return Profile()

    class Container:
        startup_profile_repository = StartupProfileRepository()

    event = AuditEvent(
        schema_version="audit_event@1",
        event_id="event-safe-1",
        timestamp_utc="2026-08-29T07:10:11Z",
        run_id="startup-api-profile",
        correlation_id="corr-safe-1",
        span_name="startup.workflow",
        event_type="startup.workflow.completed",
        attributes={"case_id": case_id, "status": "success"},
    )

    assert admin_page._admin_startup_project_names(Container(), [event]) == {
        case_id: "SMART UNIVERSITY"
    }


def test_admin_query_case_id_prefers_matching_run_over_newer_history() -> None:
    target_case_id = "2dd8c3c7-69fb-4976-b148-2e96dc86bb40"
    target_run_id = "startup-api-target"
    options = admin_page._admin_startup_run_options(
        [
            AuditEvent(
                schema_version="audit_event@1",
                event_id="newer-other",
                timestamp_utc="2026-08-29T08:00:00Z",
                run_id="startup-api-other",
                correlation_id="corr-other",
                span_name="startup.workflow",
                event_type="startup.workflow.failed",
                attributes={"case_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "status": "failed"},
            ),
            AuditEvent(
                schema_version="audit_event@1",
                event_id="older-target",
                timestamp_utc="2026-08-29T07:00:00Z",
                run_id=target_run_id,
                correlation_id="corr-target",
                span_name="startup.workflow",
                event_type="startup.workflow.completed",
                attributes={"case_id": target_case_id, "status": "success"},
            ),
        ]
    )

    assert (
        admin_page._safe_admin_query_trace_id(
            {"caseId": target_case_id.upper()},
            normalize_uuid=True,
        )
        == target_case_id
    )
    selected_index = admin_page._preferred_admin_startup_run_index(
        options,
        preferred_case_id=target_case_id,
        preferred_run_id=None,
    )
    assert list(options.values())[selected_index] == (target_case_id, target_run_id)


def test_admin_query_run_id_preserves_safe_mixed_case_identity() -> None:
    assert (
        admin_page._safe_admin_query_trace_id(
            {"runId": "Run-MixedCase-01"},
            "runId",
            "run_id",
        )
        == "Run-MixedCase-01"
    )


def test_admin_dashboard_separates_current_runtime_from_selected_trace_history() -> None:
    snapshot = build_admin_observability_snapshot([])
    startup_snapshot = build_startup_trace_admin_snapshot(
        StartupTraceView(
            case_id="case-alpha",
            run_id="startup-workflow",
            langsmith_health=StartupLangSmithHealth(
                provider="langsmith",
                status="disabled",
                error_code="tracing_disabled",
                fallback_used="false",
            ),
        )
    )

    html = _admin_dashboard_html(
        snapshot,
        startup_snapshot,
        context={
            "project_name": "SMART UNIVERSITY",
            "case_id": "case-alpha",
            "workflow_mode": "live",
            "runtime_langsmith_status": "configured",
        },
    )

    assert "LangSmith runtime" in html
    assert "configured" in html
    assert "Selected trace" in html
    assert "selected run: tracing disabled" in html
    assert "LangSmith trace: tracing disabled" not in html
    assert '<span class="admin-case-id">case-alpha</span>' in html


def test_admin_theme_stacks_wide_header_controls_before_they_overflow(
    monkeypatch: MonkeyPatch,
) -> None:
    rendered: list[str] = []
    streamlit_module = ModuleType("streamlit")
    streamlit_module.markdown = (  # type: ignore[attr-defined]
        lambda body, **_kwargs: rendered.append(str(body))
    )
    monkeypatch.setitem(sys.modules, "streamlit", streamlit_module)

    _render_admin_console_theme()

    css = rendered[0]
    assert "@media (max-width: 1420px)" in css
    assert ".admin-console-hero { grid-template-columns: 1fr; }" in css


def test_admin_console_reads_deterministic_startup_api_audit_spool(tmp_path: Path) -> None:
    event = AuditEvent(
        schema_version="audit_event@1",
        event_id="startup-disclosure-approved-1",
        timestamp_utc=datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        run_id="startup-run-1",
        correlation_id="startup-correlation-1",
        span_name="startup.disclosure_gate",
        event_type="startup_disclosure.approved",
        attributes={
            "case_id": "startup-case-1",
            "decision": "approved",
            "reason": "human_approved",
            "approval_id": "approval-1",
            "data_revision": 2,
            "content_hash": "a" * 64,
            "overall_class": "confidential",
            "detected_class_count": 1,
            "artifact_count": 2,
            "fragment_count": 3,
            "redaction_policy_version": "startup-redaction@1",
            "egress_policy_version": "startup-egress@1",
            "destination": "provider.api",
        },
    )
    startup_spool = JsonlAuditSpool(
        tmp_path / "startup-api" / "deterministic" / "startup-audit-spool"
    )
    startup_spool.append(event)

    class Container:
        settings = Settings(data_dir=tmp_path)
        audit_spool = JsonlAuditSpool(tmp_path / "audit-spool")

    assert _read_admin_events(Container()) == [event]


def test_packaged_streamlit_fixture_surfaces_do_not_depend_on_project_tests_root(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    fake_installed_root = tmp_path / ".venv" / "lib" / "python3.13"
    monkeypatch.setattr(container_module, "_project_root", lambda: fake_installed_root)
    monkeypatch.setattr(public_case_page, "_project_root", lambda: fake_installed_root)

    fixture_as_of = public_case_page.public_us_frozen_fixture_as_of()
    active_container = container_module.build_container(
        Settings(data_dir=tmp_path / "data"),
        use_fixture_adapters=True,
    )
    try:
        assert fixture_as_of.isoformat() == "2026-06-30"
        assert active_container.fixture_mode is True
        assert active_container.public_sources.sec.fixture_dir.name == "sec"
    finally:
        active_container.close()


def test_admin_console_applies_one_global_event_limit_after_merging_spools(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    public_event = _span_event("public-1", minute=0)
    live_event = _span_event("startup-live-1", minute=1)
    deterministic_event = _span_event("startup-deterministic-1", minute=2)
    public_spool = JsonlAuditSpool(tmp_path / "audit-spool")
    live_spool = JsonlAuditSpool(tmp_path / "startup-api" / "startup-audit-spool")
    deterministic_spool = JsonlAuditSpool(
        tmp_path / "startup-api" / "deterministic" / "startup-audit-spool"
    )
    public_spool.append(public_event)
    live_spool.append(live_event)
    deterministic_spool.append(deterministic_event)
    monkeypatch.setattr(admin_page, "ADMIN_AUDIT_EVENT_LIMIT", 2)

    class Container:
        settings = Settings(data_dir=tmp_path)
        audit_spool = public_spool

    assert _read_admin_events(Container()) == [deterministic_event, live_event]


def test_admin_console_keeps_the_newest_run_inside_its_bounded_event_window(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    old_event = _span_event("a-old", minute=0)
    middle_event = _span_event("b-middle", minute=1)
    current_event = _span_event("z-current", minute=2)
    spool = JsonlAuditSpool(tmp_path / "audit-spool")
    for event in (old_event, middle_event, current_event):
        spool.append(event)
    monkeypatch.setattr(admin_page, "ADMIN_AUDIT_EVENT_LIMIT", 2)

    class Container:
        settings = Settings(data_dir=tmp_path)
        audit_spool = spool

    assert _read_admin_events(Container()) == [current_event, middle_event]


def _span_event(event_id: str, *, minute: int) -> AuditEvent:
    timestamp = datetime(2026, 8, 13, 12, minute, tzinfo=UTC)
    return AuditEvent(
        schema_version="audit_event@1",
        event_id=event_id,
        timestamp_utc=timestamp.isoformat().replace("+00:00", "Z"),
        run_id=f"run-{event_id}",
        correlation_id=f"correlation-{event_id}",
        span_name="analysis.module",
        event_type="span",
        attributes={"status": "success", "evidence_count": 1},
    )


def test_admin_console_preserves_general_observability_and_adds_startup_trace_service(
    tmp_path: Path,
) -> None:
    app_file = tmp_path / "task4_streamlit_admin.py"
    app_file.write_text(
        "\n".join(
            [
                "from datetime import UTC, datetime",
                "import streamlit as st",
                "from due_diligence_agent.ports.tracing import AuditEvent",
                "from due_diligence_agent.presentation.streamlit.pages.admin import render_admin_console",
                "class FakeSpool:",
                "    def __init__(self):",
                "        self.bounds = None",
                "    def read_batch(self, limit=100):",
                "        raise AssertionError('admin console must use bounded reader')",
                "    def read_bounded(self, **kwargs):",
                "        self.bounds = kwargs",
                "        return [AuditEvent(",
                "            schema_version='audit_event@1',",
                "            event_id='event-1',",
                "            timestamp_utc=datetime(2026, 8, 13, 12, 0, tzinfo=UTC).isoformat().replace('+00:00', 'Z'),",
                "            run_id='run-1',",
                "            correlation_id='corr-1',",
                "            span_name='llm.call',",
                "            event_type='span',",
                "            attributes={'case_id': 'case-1', 'status': 'success', 'latency_ms': 25, 'estimated_cost_usd': 0.01, 'input_tokens': 999},",
                "        )]",
                "class FakeContainer:",
                "    def __init__(self):",
                "        self.audit_spool = FakeSpool()",
                "container = FakeContainer()",
                "st.session_state['app_container'] = container",
                "render_admin_console(container=container, case_id='case-1', run_id='run-1')",
                "st.session_state['audit_bounds'] = container.audit_spool.bounds",
            ]
        ),
        encoding="utf-8",
    )

    app = AppTest.from_file(str(app_file), default_timeout=30).run()

    text = "\n".join(
        str(item.value)
        for collection in (app.title, app.header, app.subheader, app.caption, app.markdown)
        for item in collection
    )
    assert "Founder Intelligence" in text
    assert "ADMIN CONSOLE" in text
    assert "Workflow" in text
    assert "Privacy &amp; Egress" in text
    assert "Evaluation Gates" in text
    assert "Cost &amp; Latency" in text
    assert "Report Lineage" in text
    assert "Sanitized LangSmith trace" in text
    assert app.session_state["audit_bounds"]["max_events"] == 200
    assert app.session_state["audit_bounds"]["max_files"] == 128
    assert app.session_state["audit_bounds"]["max_line_chars"] == 8192
    rendered = text.lower() + "\n".join(frame.value.to_string().lower() for frame in app.dataframe)
    assert "<dt>input:</dt>" in rendered
    assert "999" in rendered
    assert "event-1" not in rendered


def test_admin_console_renders_startup_trace_dto_without_rereading_raw_audit_events(
    tmp_path: Path,
) -> None:
    app_file = tmp_path / "startup_trace_admin.py"
    app_file.write_text(
        "\n".join(
            [
                "from decimal import Decimal",
                "import streamlit as st",
                "from due_diligence_agent.application.services.startup_trace_query_service import (",
                "    StartupTraceNodeRow,",
                "    StartupTraceReportLineage,",
                "    StartupTraceUsageSummary,",
                "    StartupTraceView,",
                ")",
                "from due_diligence_agent.ports.tracing import AuditEvent",
                "from due_diligence_agent.presentation.streamlit.pages.admin import render_admin_console",
                "class RawSpool:",
                "    def __init__(self):",
                "        self.read_count = 0",
                "    def read_bounded(self, **kwargs):",
                "        self.read_count += 1",
                "        return [AuditEvent(",
                "            schema_version='audit_event@1',",
                "            event_id='general-event-1',",
                "            timestamp_utc='2026-08-13T12:00:00Z',",
                "            run_id='general-run',",
                "            correlation_id='general-corr',",
                "            span_name='llm.call',",
                "            event_type='span',",
                "            attributes={'status': 'success', 'latency_ms': 25},",
                "        )]",
                "class FakeTraceQueryService:",
                "    def __init__(self):",
                "        self.calls = []",
                "    def get_view(self, case_id, run_id, *, max_events=200):",
                "        self.calls.append((case_id, run_id, max_events))",
                "        return StartupTraceView(",
                "            case_id=case_id,",
                "            run_id=run_id,",
                "            node_rows=(",
                "                StartupTraceNodeRow(",
                "                    case_id=case_id, run_id=run_id, node='market_sizing',",
                "                    attempt=2, retry_count=1, status='success', error_code=None,",
                "                    checkpoint_id='checkpoint-002', tool='python_interpreter',",
                "                    latency_ms=120.5, event_id='event-private-id',",
                "                    timestamp_utc='2026-08-13T12:00:01Z',",
                "                ),",
                "            ),",
                "            usage_summary=StartupTraceUsageSummary(",
                "                input_tokens=100, output_tokens=40, total_tokens=140,",
                "                cost_usd=Decimal('0.0125'),",
                "            ),",
                "            report_lineage=StartupTraceReportLineage(",
                "                decision='approved', gate4_status='completed',",
                "                report_id='report-001', report_revision=7, report_checksum='a' * 64,",
                "            ),",
                "        )",
                "class FakeContainer:",
                "    def __init__(self):",
                "        self.audit_spool = RawSpool()",
                "        self.startup_trace_query_service = FakeTraceQueryService()",
                "container = FakeContainer()",
                "render_admin_console(container=container, case_id='case-alpha', run_id='run-alpha')",
                "st.session_state['trace_calls'] = container.startup_trace_query_service.calls",
                "st.session_state['raw_read_count'] = container.audit_spool.read_count",
            ]
        ),
        encoding="utf-8",
    )

    app = AppTest.from_file(str(app_file), default_timeout=30).run()

    text = "\n".join(
        str(item.value)
        for collection in (app.title, app.header, app.subheader, app.caption, app.metric, app.markdown)
        for item in collection
    )
    rendered = text.lower() + "\n".join(frame.value.to_string().lower() for frame in app.dataframe)
    assert app.session_state["trace_calls"] == [("case-alpha", "run-alpha", 200)]
    assert app.session_state["raw_read_count"] == 1
    assert "sanitized langsmith trace" in rendered
    assert "граф агентов" in rendered
    assert "market_sizing" in rendered
    assert "python_interpreter" in rendered
    assert "<dt>input:</dt>" in rendered
    assert "0.0125" in rendered
    assert "report-001" in rendered
    assert "event-private-id" not in rendered


def test_admin_console_renders_safe_startup_run_selector_without_raw_payload(
    tmp_path: Path,
) -> None:
    app_file = tmp_path / "startup_trace_selector_admin.py"
    app_file.write_text(
        "\n".join(
            [
                "import streamlit as st",
                "from due_diligence_agent.ports.tracing import AuditEvent",
                "from due_diligence_agent.application.services.startup_trace_query_service import StartupTraceView",
                "from due_diligence_agent.presentation.streamlit.pages.admin import render_admin_console",
                "class RawSpool:",
                "    def read_bounded(self, **kwargs):",
                "        return [AuditEvent(",
                "            schema_version='audit_event@1',",
                "            event_id='private-event-id-must-not-render',",
                "            timestamp_utc='2026-08-13T12:00:00Z',",
                "            run_id='run-safe-1',",
                "            correlation_id='corr-safe-1',",
                "            span_name='startup.workflow',",
                "            event_type='span',",
                "            attributes={",
                "                'case_id': 'case-safe-1',",
                "                'status': 'success',",
                "                'prompt': 'raw prompt must not render',",
                "                'local_path': 'D:/private/source.pdf',",
                "                'filename': 'source.pdf',",
                "                'secret': 'sk-test-secret',",
                "            },",
                "        )]",
                "class FakeTraceQueryService:",
                "    def __init__(self):",
                "        self.calls = []",
                "    def get_view(self, case_id, run_id, *, max_events=200):",
                "        self.calls.append((case_id, run_id, max_events))",
                "        return StartupTraceView(case_id=case_id, run_id=run_id)",
                "class FakeContainer:",
                "    def __init__(self):",
                "        self.audit_spool = RawSpool()",
                "        self.startup_trace_query_service = FakeTraceQueryService()",
                "container = FakeContainer()",
                "render_admin_console(container=container)",
                "st.session_state['trace_calls'] = container.startup_trace_query_service.calls",
            ]
        ),
        encoding="utf-8",
    )

    app = AppTest.from_file(str(app_file), default_timeout=30).run()

    text = "\n".join(
        str(item.value)
        for collection in (app.caption, app.markdown, app.selectbox)
        for item in collection
    )
    rendered = text.lower()
    assert app.session_state["trace_calls"] == [("case-safe-1", "run-safe-1", 200)]
    assert len(app.selectbox) == 1
    assert app.selectbox[0].label == "Выберите case/run из локального аудита"
    assert "проверенный запуск" not in rendered
    assert "проверенные startup-запуски" not in rendered
    assert "case-safe-1" in rendered
    assert "run-safe-1" in rendered
    assert "private-event-id-must-not-render" not in rendered
    assert "raw prompt must not render" not in rendered
    assert "d:/private/source.pdf" not in rendered
    assert "source.pdf" not in rendered
    assert "sk-test-secret" not in rendered


def test_public_case_page_does_not_import_or_render_trace_summary() -> None:
    public_case_source = Path(
        "src/due_diligence_agent/presentation/streamlit/pages/public_case.py"
    ).read_text(encoding="utf-8")

    assert "render_trace_summary" not in public_case_source
    assert "audit_spool.read_batch" not in public_case_source


def test_streamlit_entry_exposes_admin_console_as_separate_operator_surface() -> None:
    app_source = Path("src/due_diligence_agent/presentation/streamlit/app.py").read_text(
        encoding="utf-8"
    )

    assert "Admin Console" in app_source
    assert "render_admin_console" in app_source
    assert "Public Case" in app_source


def test_streamlit_admin_console_keeps_approved_desktop_design_and_no_fake_pass() -> None:
    audit_source = Path(
        "src/due_diligence_agent/presentation/streamlit/components/audit.py"
    ).read_text(encoding="utf-8")
    admin_source = Path(
        "src/due_diligence_agent/presentation/streamlit/pages/admin.py"
    ).read_text(encoding="utf-8")
    source = audit_source + admin_source

    assert "founder-admin-console" in source
    assert "admin-shell" in source
    assert "admin-sidebar" in source
    assert "admin-observability-grid" in source
    assert "admin-trace-map" in source
    assert "admin-gate-row" in source
    assert "Founder Intelligence" in source
    assert "ADMIN CONSOLE" in source
    assert "Founder Workspace" in source
    assert "Evaluation Gates" in source
    assert "Privacy & Egress" in source
    assert "Cost & Latency" in source
    assert "Report Lineage" in source
    assert "grid-template-columns: 228px minmax(0, 1fr)" in audit_source
    assert "white-space: nowrap" in audit_source
    assert "grid-template-columns: repeat(7, minmax(0, 1fr))" in audit_source
    assert "grid-template-columns: minmax(0, 1fr) minmax(420px, .72fr)" in audit_source
    assert "grid-template-columns: minmax(0, .95fr) minmax(0, .68fr) minmax(520px, 1fr)" in audit_source
    assert '[data-testid="stSidebar"]' in audit_source
    assert '[data-testid="stSidebarNav"]' in audit_source
    assert '[data-testid="stSidebarCollapsedControl"]' in audit_source
    assert '[data-testid="stAppViewContainer"]' in audit_source
    assert "margin-left: 0" in audit_source
    assert "Founder Intelligence" in source
    assert "Workflow" in source
    assert "Sanitized LangSmith trace" in source
    assert "LangSmith exporter" in source
    assert "LangSmith trace:" in source
    assert "Открыть в LangSmith" not in source
    assert "admin-langsmith-link" not in source
    assert "Local audit" in source
    assert "Privacy leaks" in source
    assert "Утечки приватных данных" not in source
    assert "OpenAI calls" in source
    assert "Проверки качества" in source
    assert "Privacy & Egress" in source
    assert "LangSmith exporter" in source
    assert "Ожидает" in source
    assert "Без текста документов, путей, имён файлов, промптов, PII и секретов" in source
    assert "PASS" not in audit_source
    assert "st.title(" not in admin_source
    assert "st.header(" not in audit_source
    assert "st.text_input(" not in admin_source


def test_admin_dashboard_markup_contract_stays_close_to_approved_mockup() -> None:
    snapshot = build_admin_observability_snapshot(
        [
            AuditEvent(
                schema_version="audit_event@1",
                event_id="event-1",
                timestamp_utc="2026-08-13T12:00:00Z",
                run_id="run-alpha",
                correlation_id="corr-alpha",
                span_name="report.generate",
                event_type="span",
                attributes={
                    "status": "success",
                    "latency_ms": 125.0,
                    "estimated_cost_usd": 0.01,
                    "report_format": "pdf",
                    "artifact_hash": "a" * 64,
                    "evidence_hash": "b" * 64,
                },
            )
        ]
    )
    startup_snapshot = build_startup_trace_admin_snapshot(
        admin_page._empty_startup_trace_view()
    )
    audit_source = Path(
        "src/due_diligence_agent/presentation/streamlit/components/audit.py"
    ).read_text(encoding="utf-8")

    assert snapshot["trace_summary"]["total_events"] == 1
    assert startup_snapshot["trace_summary"]["total_events"] == 0
    assert "def render_admin_observability_dashboard" in audit_source
    assert "grid-template-columns: 228px minmax(0, 1fr)" in audit_source
    assert " is-active" in audit_source
    assert "FlowPilot" not in audit_source
    assert "Выполняется" in audit_source
    assert "Ошибка" in audit_source
    assert "HITL пройден" in audit_source


def test_admin_dashboard_renders_approved_observability_layout_contract() -> None:
    snapshot = build_admin_observability_snapshot(
        [
            AuditEvent(
                schema_version="audit_event@1",
                event_id="privacy-1",
                timestamp_utc="2026-08-13T12:00:00Z",
                run_id="run-alpha",
                correlation_id="corr-alpha",
                span_name="startup.disclosure_gate",
                event_type="startup_disclosure.approved",
                attributes={
                    "case_id": "case-alpha",
                    "decision": "approved",
                    "reason": "human_approved",
                    "redaction_policy_version": "startup-redaction@1",
                    "egress_policy_version": "startup-egress@1",
                    "destination": "provider.api",
                    "artifact_count": 1,
                    "fragment_count": 2,
                },
            ),
            AuditEvent(
                schema_version="audit_event@1",
                event_id="source-1",
                timestamp_utc="2026-08-13T12:00:01Z",
                run_id="run-alpha",
                correlation_id="corr-alpha",
                span_name="retrieval.search",
                event_type="span",
                attributes={"status": "success", "latency_ms": 50.0},
            ),
            AuditEvent(
                schema_version="audit_event@1",
                event_id="report-1",
                timestamp_utc="2026-08-13T12:00:02Z",
                run_id="run-alpha",
                correlation_id="corr-alpha",
                span_name="report.generate",
                event_type="span",
                attributes={
                    "status": "success",
                    "report_format": "pdf",
                    "artifact_hash": "a" * 64,
                    "evidence_hash": "b" * 64,
                },
            ),
        ]
    )
    startup_snapshot = build_startup_trace_admin_snapshot(
        StartupTraceView(
            case_id="case-alpha",
            run_id="startup-workflow",
            node_rows=(
                _startup_node("Document", 1.2),
                _startup_node("Profile", 1.1),
                _startup_node("Gate 2", 0.2),
                _startup_node("Market", 1.4, retry_count=1),
                _startup_node("Gate 4", 0.2),
            ),
            usage_summary=StartupTraceUsageSummary(
                input_tokens=4200,
                output_tokens=2220,
                total_tokens=6420,
                cost_usd=Decimal("0.08"),
            ),
            report_lineage=StartupTraceReportLineage(
                decision="approved",
                gate4_status="completed",
                report_id="report-alpha",
                report_revision=6,
                report_checksum="c" * 64,
            ),
            langsmith_health=StartupLangSmithHealth(
                provider="langsmith",
                status="exported",
                error_code="none",
                fallback_used="false",
            ),
        )
    )

    html = _admin_dashboard_html(snapshot, startup_snapshot)

    assert html.count('class="admin-card"') == 7
    assert html.count('data-icon="circle-check"') >= 7
    assert html.count('class="admin-flow-link"') >= 10
    assert 'class="admin-workflow-row"' in html
    assert 'class="admin-parallel-stage"' in html
    assert 'class="admin-bottom-grid"' in html
    assert html.index('class="admin-trace-map"') < html.index('Sanitized LangSmith trace')
    bottom_html = html[html.index('class="admin-bottom-grid"') :]
    assert (
        bottom_html.index("Privacy &amp; Egress")
        < bottom_html.index("Reliability")
        < bottom_html.index("Report Lineage")
    )
    assert html.count('class="admin-legend-mark"') == 7
    assert "case-alpha" in html
    assert "startup-workflow" in html
    assert "6420" in html
    assert "0.08" in html
    assert "Gate B" in html
    assert "Gate C" in html
    assert "Gate D-A" in html
    assert "Gate D-B" in html
    assert "Gate E" in html
    assert "LangSmith smoke" in html
    assert "Reliability" in html
    assert "Privacy &amp; Egress" in html
    assert "Report Lineage" in html
    assert "Snapshot v6" in html
    assert "JSON" in html
    assert "HTML" in html
    assert "PDF" in html
    assert "Raw-экспорт" in html
    assert "Без текста документов, путей, имён файлов, промптов, PII и секретов" in html
    forbidden_payload_markers = ("event_id", "event-private-id", "prompt", "C:\\", "D:\\")
    assert not any(marker in html for marker in forbidden_payload_markers)


def test_admin_graph_marks_report_formats_linked_from_approved_canonical_lineage() -> None:
    snapshot = build_admin_observability_snapshot([])
    startup_snapshot = build_startup_trace_admin_snapshot(
        StartupTraceView(
            case_id="case-alpha",
            run_id="startup-workflow",
            node_rows=(
                _startup_node("document_intelligence", 0.1),
                _startup_node("primary_profile", 0.1),
                _startup_node("disclosure", 0.1),
                _startup_node("product_validation", 0.1),
                _startup_node("report", 0.1),
            ),
            usage_summary=StartupTraceUsageSummary(
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                cost_usd=None,
            ),
            report_lineage=StartupTraceReportLineage(
                decision="approved",
                gate4_status="completed",
                report_id="report-alpha",
                report_revision=6,
                report_checksum="c" * 64,
            ),
        )
    )

    html = _admin_dashboard_html(snapshot, startup_snapshot)

    assert 'data-stage="gate4" data-state="ok"' in html
    assert 'data-stage="snapshot" data-state="ok"' in html
    assert 'data-stage="json" data-state="ok"' in html
    assert 'data-stage="html" data-state="ok"' in html
    assert 'data-stage="pdf" data-state="ok"' in html
    assert "Snapshot v6" in html
    assert "JSON linked" in html
    assert "HTML linked" in html
    assert "PDF linked" in html


def test_admin_graph_does_not_treat_disclosure_approval_as_gate4_completion() -> None:
    snapshot = build_admin_observability_snapshot([])
    startup_snapshot = build_startup_trace_admin_snapshot(
        StartupTraceView(
            case_id="case-alpha",
            run_id="startup-workflow",
            node_rows=(_startup_node("report", 0.1),),
            usage_summary=StartupTraceUsageSummary(
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                cost_usd=None,
            ),
            report_lineage=StartupTraceReportLineage(
                decision="approved",
                gate4_status=None,
                report_id=None,
                report_revision=None,
                report_checksum=None,
            ),
        )
    )

    html = _admin_dashboard_html(snapshot, startup_snapshot)

    assert 'data-stage="gate4" data-state="hitl"' in html
    assert 'data-stage="snapshot" data-state="waiting"' in html
    assert 'data-stage="json" data-state="waiting"' in html
    assert 'data-stage="html" data-state="waiting"' in html
    assert 'data-stage="pdf" data-state="waiting"' in html


def test_admin_dashboard_exposes_dense_screen10_state_classes_without_fake_links() -> None:
    snapshot = build_admin_observability_snapshot(
        [
            AuditEvent(
                schema_version="audit_event@1",
                event_id="source-1",
                timestamp_utc="2026-08-13T12:00:01Z",
                run_id="run-alpha",
                correlation_id="corr-alpha",
                span_name="retrieval.search",
                event_type="span",
                attributes={"status": "success", "latency_ms": 50.0},
            ),
        ]
    )
    startup_snapshot = build_startup_trace_admin_snapshot(
        StartupTraceView(
            case_id="case-alpha",
            run_id="startup-workflow",
            node_rows=(
                _startup_node("Document", 1.2),
                _startup_node("Gate 2", 0.2),
                _startup_node("Market", 1.4, retry_count=1),
                _startup_node("Risk", 1.1, status="deferred"),
                _startup_node("Gate 4", 0.2),
            ),
            usage_summary=StartupTraceUsageSummary(
                input_tokens=4200,
                output_tokens=2220,
                total_tokens=6420,
                cost_usd=Decimal("0.08"),
            ),
            report_lineage=StartupTraceReportLineage(
                decision="approved",
                gate4_status="completed",
                report_id="report-alpha",
                report_revision=6,
                report_checksum="c" * 64,
            ),
            langsmith_health=StartupLangSmithHealth(
                provider="langsmith",
                status="blocked_missing_credential",
                error_code="missing_key",
                fallback_used="true",
            ),
        )
    )

    html = _admin_dashboard_html(snapshot, startup_snapshot)

    assert 'class="admin-trace-panel"' in html
    assert 'class="admin-trace-metrics"' in html
    assert 'class="admin-langsmith-action is-disabled"' in html
    assert 'class="admin-select"' not in html
    assert 'class="admin-select-spacer"' in html
    assert 'data-icon="workflow"' in html
    assert 'data-icon="langsmith"' in html
    assert 'data-icon="audit"' in html
    assert 'data-icon="privacy"' in html
    assert 'data-icon="openai"' in html
    assert 'data-icon="cost"' in html
    assert 'data-icon="time"' in html
    assert html.count('data-icon="circle-check"') >= 7
    assert 'data-icon="document"' in html
    assert 'data-icon="market"' in html
    assert 'class="admin-node-icon"' in html
    assert "LangSmith link недоступен" in html
    assert 'href=' not in html
    assert 'data-state="ok"' in html
    assert 'data-state="hitl"' in html
    assert 'data-state="retry"' in html
    assert 'data-state="skipped"' in html
    assert 'class="admin-node-duration"' in html
    assert 'class="admin-node-status"' in html
    assert 'class="admin-gate-panel"' in html
    assert 'class="admin-lineage-flow"' in html
    assert 'data-format="pdf"' in html
    assert "blocked_missing_credential" in html
    assert "report-alpha" in html
    assert "event_id" not in html
    assert "source-1" not in html


def test_admin_workflow_projects_real_node_aliases_routes_and_semantic_states() -> None:
    snapshot = build_admin_observability_snapshot([])
    startup_snapshot = build_startup_trace_admin_snapshot(
        StartupTraceView(
            case_id="case-alpha",
            run_id="startup-workflow",
            node_rows=(
                _startup_node("ingest", 0.1),
                _startup_node("parse", 0.2),
                _startup_node("document_intelligence", 0.3),
                _startup_node("primary_profile", 0.1),
                _startup_node("disclosure", 0.1),
                _startup_node("product_validation", 0.2, status="partial"),
                _startup_node("metrics", 0.4, status="running"),
                _startup_node("market_research", 0.3),
                _startup_node(
                    "market_analysis",
                    0.0,
                    status="blocked",
                    error_code="blocked_by_policy",
                ),
                _startup_node(
                    "financial_analysis",
                    0.5,
                    retry_count=1,
                    status="retryable_error",
                    error_code="provider_unavailable",
                ),
                _startup_node(
                    "risk_analysis",
                    0.2,
                    status="failed",
                    error_code="provider_unavailable",
                ),
                _startup_node("critic", 0.2),
                _startup_node("arbiter", 0.1),
            ),
            usage_summary=StartupTraceUsageSummary(
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                cost_usd=None,
            ),
            report_lineage=StartupTraceReportLineage(
                decision=None,
                gate4_status=None,
                report_id=None,
                report_revision=None,
                report_checksum=None,
            ),
        )
    )

    html = _admin_dashboard_html(snapshot, startup_snapshot)

    assert 'data-stage="document" data-state="ok"' in html
    assert 'data-stage="profile" data-state="ok"' in html
    assert 'data-stage="gate2" data-state="ok"' in html
    assert 'data-stage="product" data-state="partial"' in html
    assert 'data-stage="metrics" data-state="active"' in html
    assert 'data-stage="market_research" data-state="ok"' in html
    assert 'data-stage="market_analysis" data-state="blocked"' in html
    assert 'data-stage="financial" data-state="retry"' in html
    assert 'data-stage="risk" data-state="error"' in html
    assert 'data-stage="gate3" data-state="hitl"' in html
    assert 'data-stage="gate4" data-state="waiting"' in html
    assert "HITL пройден" in html
    assert "Ожидает решения" in html
    assert "Выполняется" in html
    assert "Заблокирован" in html
    assert "Повтор 1" in html
    assert "Ошибка" in html
    assert html.count('class="admin-parallel-route"') == 2
    assert (
        'class="admin-parallel-route" data-source="product" '
        'data-target="market_research" data-state="ok"'
    ) in html
    assert (
        'class="admin-parallel-route" data-source="product" '
        'data-target="metrics" data-state="active"'
    ) in html
    assert 'data-edge="metrics-financial" data-state="retry"' in html
    assert 'data-edge="financial-risk" data-state="error"' in html
    assert (
        'class="admin-join-path" data-source="market_research" '
        'data-target="market_analysis" data-state="blocked"'
    ) in html
    assert (
        'class="admin-join-path" data-source="risk" '
        'data-target="market_analysis" data-state="blocked"'
    ) in html
    assert 'data-edge="market_analysis-gtm"' in html
    assert 'data-edge="gtm-critic"' in html
    assert 'data-edge="critic-arbiter"' in html
    assert 'data-edge="arbiter-critic" data-loop-limit="2"' in html
    assert 'data-edge="arbiter-gate3"' in html
    assert 'data-edge="gate3-report"' in html
    assert 'data-edge="report-gate4"' in html
    assert html.index('data-stage="gtm"') < html.index('data-stage="critic"')
    assert html.index('data-stage="critic"') < html.index('data-stage="arbiter"')
    assert html.index('data-stage="arbiter"') < html.index('data-stage="gate3"')
    assert html.index('data-stage="gate3"') < html.index('data-stage="report"')
    for state in ("ok", "active", "error", "hitl", "retry", "skipped", "waiting"):
        assert f'class="admin-legend-mark" data-state="{state}"' in html


def test_admin_summary_cards_and_lineage_do_not_fake_success() -> None:
    snapshot = build_admin_observability_snapshot([])
    startup_snapshot = build_startup_trace_admin_snapshot(
        StartupTraceView(
            case_id="case-alpha",
            run_id="startup-workflow",
            node_rows=(
                _startup_node("metrics", 0.1),
                _startup_node(
                    "financial_analysis",
                    0.0,
                    status="blocked",
                    error_code="blocked_by_policy",
                ),
            ),
            usage_summary=StartupTraceUsageSummary(
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                cost_usd=None,
            ),
            report_lineage=StartupTraceReportLineage(
                decision=None,
                gate4_status="required",
                report_id=None,
                report_revision=None,
                report_checksum=None,
            ),
            langsmith_health=StartupLangSmithHealth(
                provider="langsmith",
                status="disabled",
                error_code="tracing_disabled",
                fallback_used="local_audit",
            ),
        )
    )

    html = _admin_dashboard_html(snapshot, startup_snapshot)

    assert 'data-card="workflow" data-state="blocked"' in html
    assert "1 блокировка" in html
    assert "Запуск • 1 блокировка" in html
    assert 'data-card="langsmith-exporter" data-state="skipped"' in html
    assert 'data-card="local-audit" data-state="waiting"' in html
    assert 'data-card="openai-calls" data-state="waiting"' in html
    assert 'data-card="стоимость" data-state="waiting"' in html
    assert 'data-format="snapshot" data-state="waiting"' in html
    assert html.count('class="admin-gate-card" data-state="waiting"') >= 5


def test_admin_dashboard_screen10_density_selector_and_long_id_contract() -> None:
    audit_source = Path(
        "src/due_diligence_agent/presentation/streamlit/components/audit.py"
    ).read_text(encoding="utf-8")
    admin_source = Path(
        "src/due_diligence_agent/presentation/streamlit/pages/admin.py"
    ).read_text(encoding="utf-8")
    long_case_id = "case-" + ("alpha-" * 18)
    long_run_id = "run-" + ("startup-workflow-" * 8)
    startup_snapshot = build_startup_trace_admin_snapshot(
        StartupTraceView(
            case_id=long_case_id,
            run_id=long_run_id,
            node_rows=(
                _startup_node("Document", 1.2),
                _startup_node("Gate 2", 0.2),
                _startup_node("Market", 1.4, retry_count=1),
                _startup_node("Gate 4", 0.2),
            ),
            usage_summary=StartupTraceUsageSummary(
                input_tokens=4200,
                output_tokens=2220,
                total_tokens=6420,
                cost_usd=None,
            ),
            report_lineage=StartupTraceReportLineage(
                decision="approved",
                gate4_status="completed",
                report_id="report-alpha",
                report_revision=6,
                report_checksum="c" * 64,
            ),
        )
    )
    snapshot = build_admin_observability_snapshot([])

    html = _admin_dashboard_html(snapshot, startup_snapshot)

    assert '[data-testid="stSelectbox"]' in audit_source
    assert "position: fixed !important" in audit_source
    assert "right: 422px !important" in audit_source
    assert "background: transparent !important" in audit_source
    assert "height: 84px" in audit_source
    assert ".admin-select-spacer" in audit_source
    assert "grid-template-columns: 111px 280px 180px 222px" in audit_source
    assert "margin-left: 132px" not in audit_source
    assert "max-width: 180px" in audit_source
    assert 'class="admin-card-value"' in audit_source
    assert '.admin-card[data-state="blocked"]::before' in audit_source
    assert (
        '.admin-graph-node[data-state="blocked"] .admin-node-status'
        in audit_source
    )
    assert 'label_visibility="collapsed"' in admin_source
    assert "[data-testid=\"stSelectbox\"] > div" in audit_source
    assert '[data-testid="stSelectbox"] .react-aria-ComboBox' in audit_source
    assert '[data-testid="stSelectbox"] .react-aria-ComboBox input' in audit_source
    assert '[data-testid="stSelectbox"] .react-aria-ComboBox button' in audit_source
    assert "margin-bottom: 0 !important" in audit_source
    assert "max-width: 1440px !important" in audit_source
    assert '.block-container > [data-testid="stVerticalBlock"]' in audit_source
    assert "gap: 0 !important" in audit_source
    assert '.founder-admin-console [data-testid="stHeadingWithActionElements"]' in audit_source
    assert "height: auto !important" in audit_source
    assert '.founder-admin-console [data-testid="stHeaderActionElements"]' in audit_source
    assert "padding: 22px 0 0" in audit_source
    assert "margin-bottom: 40px" in audit_source
    assert "min-height: 512px" in audit_source
    assert "grid-template-rows: minmax(0, 1.42fr) minmax(0, 1fr)" in audit_source
    assert ".admin-bottom-grid .admin-panel" in audit_source
    assert "min-height: 210px" in audit_source
    assert ".admin-graph-node strong" in audit_source
    assert ".admin-graph-node.is-diamond .admin-node-title strong" in audit_source
    assert ".admin-graph-node.is-diamond .admin-node-duration" in audit_source
    assert "min-height: 54px" in audit_source
    assert "min-width: 96px" in audit_source
    assert "flex: 0 0 18px" in audit_source
    assert "align-items: start" in audit_source
    assert "min-height: 42px" in audit_source
    assert "min-height: 48px" in audit_source
    assert "overflow-wrap: anywhere" in audit_source
    assert "grid-template-columns: 52px minmax(0, 1fr)" in audit_source
    assert ".admin-trace-metrics dd" in audit_source
    assert "text-overflow: ellipsis" in audit_source
    assert "white-space: nowrap" in audit_source
    assert "Raw-экспорт" in html
    assert "Внешние вызовы" in html
    assert "span-события" not in html
    assert "инструменты" not in html
    assert "токены всего" not in html
    assert "цепочка отчёта" not in html
    assert "spans" in html
    assert "tools" in html
    assert "tokens" in html
    assert "lineage" in html
    assert long_case_id not in html
    assert long_run_id not in html
    assert "…" in html
    assert "report-alpha" in html


def _startup_node(
    node: str,
    latency_seconds: float,
    *,
    retry_count: int = 0,
    status: str = "success",
    error_code: str | None = None,
) -> StartupTraceNodeRow:
    return StartupTraceNodeRow(
        case_id="case-alpha",
        run_id="startup-workflow",
        node=node,
        attempt=1 + retry_count,
        retry_count=retry_count,
        status=status,
        error_code=error_code,
        checkpoint_id=f"checkpoint-{node.lower().replace(' ', '-')}",
        tool="startup_agent",
        latency_ms=latency_seconds * 1000,
        event_id=f"event-{node.lower().replace(' ', '-')}",
        timestamp_utc="2026-08-13T12:00:00Z",
    )
