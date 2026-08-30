from __future__ import annotations

from base64 import b64encode
from collections import Counter
from collections.abc import Mapping, Sequence
from functools import lru_cache
from html import escape
from pathlib import Path
import re
from typing import TypeAlias, TypedDict, cast

from due_diligence_agent.application.services.startup_trace_query_service import StartupTraceView
from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.ports.tracing import AuditEvent


AdminScalar: TypeAlias = str | int | float | bool | None
AdminRow: TypeAlias = dict[str, AdminScalar]


class TraceSummary(TypedDict):
    total_events: int
    status_counts: dict[str, int]


class CostLatencySummary(TypedDict):
    estimated_cost_usd: float | None
    latency_ms_total: float | None


class AdminSnapshot(TypedDict):
    trace_summary: TraceSummary
    privacy_redaction: list[AdminRow]
    evaluations: list[AdminRow]
    cost_latency: CostLatencySummary
    source_health: list[AdminRow]
    report_integrity: list[AdminRow]


class AdminDashboardContext(TypedDict, total=False):
    project_name: str
    case_id: str
    workflow_mode: str
    runtime_langsmith_status: str


class StartupTraceSummary(TypedDict):
    case_id: str
    run_id: str
    total_events: int
    status_counts: dict[str, int]


class StartupTraceAdminSnapshot(TypedDict):
    trace_summary: StartupTraceSummary
    exporter_health: AdminRow | None
    langsmith_health: AdminRow | None
    node_timeline: list[AdminRow]
    usage_summary: AdminRow
    report_lineage: AdminRow


_ADMIN_SAFE_ATTRIBUTE_KEYS = {
    "status",
    "error_code",
    "fallback_used",
    "latency_ms",
    "duration_ms",
    "estimated_cost_usd",
    "cost_usd",
    "evidence_count",
    "score",
    "redaction_policy_version",
    "adapter_version",
    "retrieval_index_version",
    "index_version",
    "http_status_code",
    "budget_usd",
    "bytes",
    "report_format",
    "artifact_hash",
    "evidence_hash",
}
_STARTUP_DISCLOSURE_SAFE_ATTRIBUTE_KEYS = {
    "case_id",
    "decision",
    "reason",
    "approval_id",
    "data_revision",
    "content_hash",
    "overall_class",
    "detected_class_count",
    "artifact_count",
    "fragment_count",
    "redaction_policy_version",
    "egress_policy_version",
    "destination",
}
_STARTUP_DISCLOSURE_COUNT_KEYS = {
    "data_revision",
    "detected_class_count",
    "artifact_count",
    "fragment_count",
}
_SOURCE_SPANS = {
    "sec.fetch",
    "document.ingest",
    "retrieval.search",
    "embedding.create",
    "chunk.create",
}
_REPORT_SOURCES = {"report", "report.generate"}
_STARTUP_DISCLOSURE_EVENT_TYPES = {
    "startup_disclosure.previewed",
    "startup_disclosure.approved",
    "startup_disclosure.denied",
    "startup_disclosure.invalidated",
}
_SAFE_STATUS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_SAFE_HASH_RE = re.compile(r"^[A-Fa-f0-9]{32,128}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DISPLAY_SANITIZER = StrictTraceSanitizer()
_ADMIN_GRAPH_NODES = (
    ("Document", "document"),
    ("Profile", "profile"),
    ("Gate 2", "hitl"),
    ("Product", "product"),
    ("Metrics", "metrics"),
    ("Market", "market"),
    ("Financial", "financial"),
    ("Risk", "risk"),
    ("Critic", "critic"),
    ("Gate 3", "hitl"),
    ("Arbiter", "arbiter"),
    ("GTM", "gtm"),
    ("Report Draft", "report"),
    ("Gate 4", "hitl"),
)
_ADMIN_GATE_NAMES = ("Gate B", "Gate C", "Gate D-A", "Gate D-B", "Gate E")
_ADMIN_STAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "document": (
        "document",
        "initialize",
        "ingest",
        "parse",
        "classify_redact",
        "evidence",
        "claims",
        "document_intelligence",
    ),
    "profile": ("profile", "primary_profile"),
    "gate2": ("gate_2", "gate2", "disclosure"),
    "product": ("product", "profile_enrichment", "product_validation"),
    "metrics": ("metrics",),
    "market_research": ("market_research",),
    "market_analysis": ("market", "market_analysis"),
    "financial": ("financial", "financial_analysis"),
    "risk": ("risk", "risk_analysis"),
    "critic": ("critic",),
    "gate3": ("gate_3", "gate3"),
    "arbiter": ("arbiter",),
    "gtm": ("gtm",),
    "report": ("report", "report_draft"),
    "gate4": ("gate_4", "gate4"),
}
_ADMIN_STATE_PRIORITY = (
    "error",
    "active",
    "hitl",
    "blocked",
    "retry",
    "partial",
    "skipped",
    "ok",
    "waiting",
)

# Lucide 1.31.0 paths. The Founder workspace already ships Lucide; the admin
# surface reuses the same icon family instead of glyphs or CSS placeholders.
_LUCIDE_ICON_MARKUP = {
    "layout-dashboard": (
        '<rect width="7" height="9" x="3" y="3" rx="1"/>'
        '<rect width="7" height="5" x="14" y="3" rx="1"/>'
        '<rect width="7" height="9" x="14" y="12" rx="1"/>'
        '<rect width="7" height="5" x="3" y="16" rx="1"/>'
    ),
    "workflow": (
        '<rect width="8" height="8" x="3" y="3" rx="2"/>'
        '<path d="M7 11v4a2 2 0 0 0 2 2h4"/>'
        '<rect width="8" height="8" x="13" y="13" rx="2"/>'
    ),
    "list-tree": (
        '<path d="M8 5h13"/><path d="M13 12h8"/><path d="M13 19h8"/>'
        '<path d="M3 10a2 2 0 0 0 2 2h3"/>'
        '<path d="M3 5v12a2 2 0 0 0 2 2h3"/>'
    ),
    "shield-check": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 '
        '20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 '
        '1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
        '<path d="m9 12 2 2 4-4"/>'
    ),
    "lock-keyhole": (
        '<circle cx="12" cy="16" r="1"/>'
        '<rect x="3" y="10" width="18" height="12" rx="2"/>'
        '<path d="M7 10V7a5 5 0 0 1 10 0v3"/>'
    ),
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6h4"/>',
    "circle-check": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="m9 12 2 2 4-4"/>'
    ),
    "circle-minus": '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>',
    "circle-pause": (
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="10" x2="10" y1="15" y2="9"/>'
        '<line x1="14" x2="14" y1="15" y2="9"/>'
    ),
    "circle-x": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="m15 9-6 6"/><path d="m9 9 6 6"/>'
    ),
    "loader-circle": '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
    "rotate-ccw": (
        '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>'
        '<path d="M3 3v5h5"/>'
    ),
    "file-check": (
        '<path d="M10.5 22H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 '
        '2.4 0 0 1 1.706.706l3.588 3.588A2.4 2.4 0 0 1 20 8v6"/>'
        '<path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="m14 20 2 2 4-4"/>'
    ),
    "panel-left": (
        '<rect width="18" height="18" x="3" y="3" rx="2"/>'
        '<path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>'
    ),
    "settings": (
        '<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 '
        '3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 '
        '3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 '
        '1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 '
        '2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 '
        '2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "cloud-upload": (
        '<path d="M12 13v8"/>'
        '<path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/>'
        '<path d="m8 17 4-4 4 4"/>'
    ),
    "database": (
        '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
        '<path d="M3 5V19A9 3 0 0 0 21 19V5"/>'
        '<path d="M3 12A9 3 0 0 0 21 12"/>'
    ),
    "bot": (
        '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/>'
        '<path d="M2 14h2"/><path d="M20 14h2"/>'
        '<path d="M15 13v2"/><path d="M9 13v2"/>'
    ),
    "circle-dollar": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/>'
        '<path d="M12 18V6"/>'
    ),
    "file-text": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 '
        '1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>'
        '<path d="M14 2v5a1 1 0 0 0 1 1h5"/>'
        '<path d="M16 13H8"/><path d="M16 17H8"/>'
    ),
    "user": '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    "box": (
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 '
        '0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 '
        '0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'
    ),
    "chart-bars": '<path d="M5 21v-6"/><path d="M12 21V9"/><path d="M19 21V3"/>',
    "chart-pie": (
        '<path d="M21 12c.552 0 1.005-.449.95-.998a10 10 0 0 0-8.953-8.951c-.55-.'
        '055-.998.398-.998.95v8a1 1 0 0 0 1 1z"/>'
        '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/>'
    ),
    "shield-alert": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 '
        '18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 '
        '1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
        '<path d="M12 8v4"/><path d="M12 16h.01"/>'
    ),
    "sparkles": (
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 '
        '1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 '
        '0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 '
        '0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 '
        '2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/><path d="M22 4h-4"/>'
    ),
    "scale": (
        '<path d="M12 3v18"/><path d="m19 8 3 8a5 5 0 0 1-6 0zV7"/>'
        '<path d="M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1"/>'
        '<path d="m5 8 3 8a5 5 0 0 1-6 0zV7"/><path d="M7 21h10"/>'
    ),
    "megaphone": (
        '<path d="M11 6a13 13 0 0 0 8.4-2.8A1 1 0 0 1 21 4v12a1 1 0 0 '
        '1-1.6.8A13 13 0 0 0 11 14H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z"/>'
        '<path d="M6 14a12 12 0 0 0 2.4 7.2 2 2 0 0 0 3.2-2.4A8 8 0 0 1 '
        '10 14"/><path d="M8 6v8"/>'
    ),
    "file-braces": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 '
        '1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>'
        '<path d="M14 2v5a1 1 0 0 0 1 1h5"/>'
        '<path d="M10 12a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1 1 1 0 0 1 1 1v1a1 1 '
        '0 0 0 1 1"/>'
        '<path d="M14 18a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1 1 1 0 0 1-1-1v-1a1 '
        '1 0 0 0-1-1"/>'
    ),
    "code-xml": (
        '<path d="m18 16 4-4-4-4"/><path d="m6 8-4 4 4 4"/>'
        '<path d="m14.5 4-5 16"/>'
    ),
    "file-down": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 '
        '1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>'
        '<path d="M14 2v5a1 1 0 0 0 1 1h5"/>'
        '<path d="M12 18v-6"/><path d="m9 15 3 3 3-3"/>'
    ),
    "circle-dashed": (
        '<path d="M10.1 2.182a10 10 0 0 1 3.8 0"/>'
        '<path d="M13.9 21.818a10 10 0 0 1-3.8 0"/>'
        '<path d="M17.609 3.721a10 10 0 0 1 2.69 2.7"/>'
        '<path d="M2.182 13.9a10 10 0 0 1 0-3.8"/>'
        '<path d="M20.279 17.609a10 10 0 0 1-2.7 2.69"/>'
        '<path d="M21.818 10.1a10 10 0 0 1 0 3.8"/>'
        '<path d="M3.721 6.391a10 10 0 0 1 2.7-2.69"/>'
        '<path d="M6.391 20.279a10 10 0 0 1-2.69-2.7"/>'
    ),
}
_ADMIN_ICON_ALIASES = {
    "overview": "layout-dashboard",
    "agents": "workflow",
    "traces": "list-tree",
    "gates": "shield-check",
    "privacy": "lock-keyhole",
    "cost": "circle-dollar",
    "time": "clock",
    "lineage": "file-check",
    "workspace": "panel-left",
    "langsmith": "cloud-upload",
    "audit": "database",
    "openai": "bot",
    "document": "file-text",
    "profile": "user",
    "product": "box",
    "metrics": "chart-bars",
    "market": "chart-pie",
    "financial": "circle-dollar",
    "risk": "shield-alert",
    "critic": "sparkles",
    "arbiter": "scale",
    "gtm": "megaphone",
    "report": "file-text",
    "snapshot": "file-check",
    "json": "file-braces",
    "html": "code-xml",
    "pdf": "file-down",
    "status": "circle-dashed",
}


def _admin_icon_svg(icon_key: str, *, class_name: str = "") -> str:
    resolved_key = _ADMIN_ICON_ALIASES.get(icon_key, icon_key)
    icon_markup = _LUCIDE_ICON_MARKUP.get(
        resolved_key,
        _LUCIDE_ICON_MARKUP["circle-dashed"],
    )
    class_attribute = f' class="{escape(class_name)}"' if class_name else ""
    return (
        f'<svg{class_attribute} data-icon="{escape(icon_key)}" aria-hidden="true" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        f'focusable="false">{icon_markup}</svg>'
    )


@lru_cache(maxsize=1)
def _admin_brand_mark_data_uri() -> str | None:
    asset_path = (
        Path(__file__).resolve().parents[5]
        / "frontend"
        / "founder"
        / "components"
        / "founder-intelligence-mark.png"
    )
    try:
        encoded = b64encode(asset_path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:image/png;base64,{encoded}"


def render_trace_summary(events: Sequence[object]) -> None:
    import streamlit as st

    st.subheader("Sanitized Trace Summary")
    if events:
        st.dataframe(events, width="stretch")
    else:
        st.caption("No sanitized audit events loaded yet.")


def build_admin_observability_snapshot(events: Sequence[AuditEvent]) -> AdminSnapshot:
    safe_events = [_safe_event_row(event) for event in events]
    status_counts: Counter[str] = Counter(
        str(row["status"]) for row in safe_events if isinstance(row.get("status"), str)
    )
    latency_values = [_preferred_numeric(row, "latency_ms", "duration_ms") for row in safe_events]
    cost_values = [_preferred_numeric(row, "estimated_cost_usd", "cost_usd") for row in safe_events]
    observed_latency = [value for value in latency_values if value is not None]
    observed_cost = [value for value in cost_values if value is not None]
    return {
        "trace_summary": {
            "total_events": len(events),
            "status_counts": dict(status_counts),
        },
        "privacy_redaction": [
            _pick(
                row,
                (
                    "event_type",
                    "decision",
                    "reason",
                    "data_revision",
                    "overall_class",
                    "detected_class_count",
                    "artifact_count",
                    "fragment_count",
                    "redaction_policy_version",
                    "egress_policy_version",
                    "destination",
                    "status",
                    "error_code",
                ),
            )
            for row in safe_events
            if _is_privacy_row(row)
        ],
        "evaluations": [
            _pick(row, ("span_name", "status", "score", "evidence_count"))
            for row in safe_events
            if _is_evaluation_row(row)
        ],
        "cost_latency": {
            "estimated_cost_usd": round(sum(observed_cost), 6) if observed_cost else None,
            "latency_ms_total": round(sum(observed_latency), 3) if observed_latency else None,
        },
        "source_health": [
            _pick(row, ("source", "status", "error_code", "http_status_code", "fallback_used"))
            for row in safe_events
            if _is_source_health_row(row)
        ],
        "report_integrity": [
            _pick(row, ("status", "report_format", "artifact_hash", "evidence_hash"))
            for row in safe_events
            if _is_report_integrity_row(row)
        ],
    }


def build_startup_trace_admin_snapshot(view: StartupTraceView) -> StartupTraceAdminSnapshot:
    status_counts: Counter[str] = Counter(
        row.status for row in view.node_rows if row.status is not None
    )
    return {
        "trace_summary": {
            "case_id": view.case_id,
            "run_id": view.run_id,
            "total_events": len(view.node_rows),
            "status_counts": dict(status_counts),
        },
        "exporter_health": (
            {
                "status": view.exporter_health.status,
                "error_code": view.exporter_health.error_code,
                "fallback_used": view.exporter_health.fallback_used,
            }
            if view.exporter_health is not None
            else None
        ),
        "langsmith_health": (
            {
                "provider": view.langsmith_health.provider,
                "status": view.langsmith_health.status,
                "error_code": view.langsmith_health.error_code,
                "fallback_used": view.langsmith_health.fallback_used,
            }
            if view.langsmith_health is not None
            else None
        ),
        "node_timeline": [
            _drop_none(
                {
                    "timestamp_utc": row.timestamp_utc,
                    "node": row.node,
                    "attempt": row.attempt,
                    "retry_count": row.retry_count,
                    "status": row.status,
                    "error_code": row.error_code,
                    "checkpoint_id": row.checkpoint_id,
                    "tool": row.tool,
                    "latency_ms": row.latency_ms,
                    "timeout_ms": row.timeout_ms,
                    "evidence_count": row.evidence_count,
                    "fallback_used": row.fallback_used,
                }
            )
            for row in view.node_rows
        ],
        "usage_summary": _drop_none(
            {
                "input_tokens": view.usage_summary.input_tokens,
                "output_tokens": view.usage_summary.output_tokens,
                "total_tokens": view.usage_summary.total_tokens,
                "cost_usd": str(view.usage_summary.cost_usd)
                if view.usage_summary.cost_usd is not None
                else None,
            }
        ),
        "report_lineage": _drop_none(
            {
                "decision": view.report_lineage.decision,
                "gate4_status": view.report_lineage.gate4_status,
                "report_id": view.report_lineage.report_id,
                "report_revision": view.report_lineage.report_revision,
                "report_checksum": view.report_lineage.report_checksum,
            }
        ),
    }


def render_startup_trace_admin_snapshot(snapshot: StartupTraceAdminSnapshot) -> None:
    import streamlit as st

    _render_admin_console_theme()
    st.markdown(_render_startup_trace_design(snapshot), unsafe_allow_html=True)


def render_admin_observability_snapshot(snapshot: AdminSnapshot) -> None:
    import streamlit as st

    _render_admin_console_theme()
    st.markdown(_render_admin_overview_design(snapshot), unsafe_allow_html=True)


def render_admin_observability_dashboard(
    snapshot: AdminSnapshot,
    startup_snapshot: StartupTraceAdminSnapshot,
    *,
    context: AdminDashboardContext | None = None,
) -> None:
    import streamlit as st

    _render_admin_console_theme()
    st.markdown(
        _admin_dashboard_html(snapshot, startup_snapshot, context=context),
        unsafe_allow_html=True,
    )


def _render_admin_console_theme() -> None:
    import streamlit as st

    st.markdown(
        """
        <style>
          .founder-admin-console {
            --admin-panel: rgba(12, 14, 15, 0.84);
            --admin-line: rgba(255,255,255,0.16);
            --admin-text: #fbf7f9;
            --admin-muted: #b8b0b5;
            --admin-pink: #f5a1cf;
            --admin-green: #8bd98c;
            --admin-gold: #ecc257;
            --admin-red: #f0848f;
            --admin-blue: #8eb4ff;
            background:
              radial-gradient(circle at 72% 0%, rgba(245,161,207,.13), transparent 30%),
              linear-gradient(120deg, #040606 0%, #0b0d0e 58%, #120d10 100%);
            border: 1px solid var(--admin-line);
            border-radius: 22px;
            color: var(--admin-text);
            font-family: "Segoe UI Variable", "Aptos", "Segoe UI", sans-serif;
            padding: 14px 16px;
            text-rendering: optimizeLegibility;
          }
          .stApp {
            background: #050606;
          }
          [data-testid="stHeader"],
          [data-testid="stToolbar"],
          [data-testid="stDecoration"],
          [data-testid="stSidebar"],
          [data-testid="stSidebarNav"],
          [data-testid="stSidebarCollapsedControl"],
          [data-testid="collapsedControl"],
          [data-testid="stDeployButton"] {
            display: none !important;
            visibility: hidden !important;
          }
          [data-testid="stAppViewContainer"],
          [data-testid="stAppViewContainer"] > .main,
          [data-testid="stMain"],
          [data-testid="stMainBlockContainer"] {
            margin-left: 0 !important;
            padding-left: 0 !important;
            width: 100vw !important;
            max-width: 100vw !important;
          }
          .block-container {
            max-width: 1440px !important;
            padding: 2px 3px 10px !important;
          }
          .block-container > [data-testid="stVerticalBlock"] {
            gap: 0 !important;
          }
          [data-testid="stSelectbox"] {
            max-width: 280px !important;
            position: fixed !important;
            right: 422px !important;
            top: 34px !important;
            width: 280px !important;
            z-index: 50 !important;
          }
          [data-testid="stSelectbox"] > div {
            height: 36px !important;
            margin-bottom: 0 !important;
          }
          [data-testid="stSelectbox"] label,
          [data-testid="stSelectbox"] [data-testid="stWidgetLabel"] {
            display: none !important;
          }
          [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            background: rgba(9, 11, 12, .78) !important;
            border: 1px solid rgba(255,255,255,.22) !important;
            border-radius: 9px !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.08), 0 14px 42px rgba(0,0,0,.28) !important;
            min-height: 38px !important;
          }
          [data-testid="stSelectbox"] .react-aria-ComboBox {
            height: 36px !important;
            min-height: 36px !important;
          }
          [data-testid="stSelectbox"] .react-aria-ComboBox input,
          [data-testid="stSelectbox"] .react-aria-ComboBox button {
            color: #fbf7f9 !important;
          }
          [data-testid="stSelectbox"] [data-baseweb="select"] * {
            color: #fbf7f9 !important;
            font-size: 13px !important;
          }
          [data-testid="stSelectbox"] .react-aria-ComboBox,
          [data-testid="stSelectbox"] .react-aria-ComboBox [role="group"] {
            min-width: 0 !important;
            position: relative !important;
            width: 100% !important;
          }
          [data-testid="stSelectbox"] .react-aria-ComboBox [role="group"] {
            background: transparent !important;
            border: 0 !important;
            border-radius: 10px !important;
            box-shadow: none !important;
            height: 36px !important;
            min-height: 36px !important;
            overflow: visible !important;
          }
          [data-testid="stSelectbox"] .react-aria-ComboBox input {
            background: rgba(9, 11, 12, .94) !important;
            border: 1px solid rgba(255,255,255,.22) !important;
            border-radius: 10px !important;
            box-shadow:
              inset 0 1px 0 rgba(255,255,255,.08),
              0 14px 42px rgba(0,0,0,.28) !important;
            color: #fbf7f9 !important;
            font-family: "Segoe UI Variable", "Aptos", "Segoe UI", sans-serif !important;
            font-size: 13px !important;
            height: 36px !important;
            min-width: 0 !important;
            overflow: hidden !important;
            padding: 0 34px 0 13px !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
            width: 100% !important;
          }
          [data-testid="stSelectbox"] .react-aria-ComboBox button {
            align-items: center !important;
            background: transparent !important;
            border: 0 !important;
            color: rgba(251,247,249,.76) !important;
            display: inline-flex !important;
            height: 34px !important;
            justify-content: center !important;
            padding: 0 !important;
            position: absolute !important;
            right: 2px !important;
            top: 1px !important;
            width: 32px !important;
          }
          .founder-admin-console * { box-sizing: border-box; }
          .founder-admin-console [data-testid="stHeadingWithActionElements"] {
            height: auto !important;
            margin: 0 !important;
            min-height: 0 !important;
            padding: 0 !important;
          }
          .founder-admin-console [data-testid="stHeaderActionElements"] {
            display: none !important;
          }
          .admin-shell {
            display: grid;
            gap: 20px;
            grid-template-columns: 228px minmax(0, 1fr);
            min-height: 0;
            padding: 22px 0 0;
          }
          .admin-sidebar {
            background: rgba(10, 11, 12, .84);
            border: 1px solid rgba(255,255,255,.16);
            border-radius: 18px;
            display: flex;
            flex-direction: column;
            min-height: 948px;
            padding: 26px 22px;
          }
          .admin-brand {
            align-items: center;
            display: grid;
            gap: 14px;
            grid-template-columns: 34px 1fr;
            margin-bottom: 26px;
          }
          .admin-brand-mark {
            align-items: center;
            display: inline-flex;
            height: 42px;
            justify-content: center;
            overflow: hidden;
            width: 42px;
          }
          .admin-brand-mark img {
            height: 38px;
            object-fit: contain;
            transform: scale(2.05);
            width: 38px;
          }
          .admin-brand-mark svg {
            color: var(--admin-pink);
            height: 30px;
            width: 30px;
          }
          .admin-brand strong {
            display: block;
            font-size: 20px;
            font-weight: 600;
            line-height: 1.12;
          }
          .admin-sidebar-label {
            color: var(--admin-pink);
            font-size: 13px;
            margin-bottom: 22px;
            text-transform: uppercase;
          }
          .admin-nav {
            display: grid;
            gap: 10px;
          }
          .admin-nav-item {
            align-items: center;
            border: 1px solid transparent;
            border-radius: 14px;
            color: var(--admin-text);
            display: grid;
            font-size: 16px;
            gap: 14px;
            grid-template-columns: 26px 1fr;
            min-height: 49px;
            padding: 0 14px;
            white-space: nowrap;
          }
          .admin-nav-item.is-active {
            background: linear-gradient(90deg, rgba(245,161,207,.22), rgba(245,161,207,.06));
            border-color: rgba(245,161,207,.32);
            box-shadow: inset 3px 0 0 var(--admin-pink);
          }
          .admin-nav-icon {
            align-items: center;
            color: rgba(255,255,255,.78);
            display: inline-flex;
            justify-content: center;
            height: 22px;
            width: 22px;
          }
          .admin-nav-icon svg {
            height: 20px;
            width: 20px;
          }
          .admin-sidebar-footer {
            border-top: 1px solid var(--admin-line);
            display: grid;
            gap: 12px;
            margin-top: auto;
            padding-top: 22px;
          }
          .admin-content {
            min-width: 0;
            padding: 0 0 10px;
          }
          .admin-console-hero {
            align-items: center;
            display: grid;
            gap: 16px;
            grid-template-columns: minmax(320px, 1fr) auto;
            margin-bottom: 40px;
          }
          .admin-console-hero h1 {
            font-size: 27px;
            font-weight: 600;
            line-height: 1.08;
            margin: 0 0 6px;
            padding: 0 !important;
          }
          .admin-console-hero p,
          .admin-card p,
          .admin-safe-note,
          .admin-graph-node span {
            color: var(--admin-muted);
            margin: 0;
          }
          .admin-console-hero p {
            font-size: 14px;
            line-height: 1.35;
          }
          .admin-active-case {
            align-items: baseline;
            display: flex;
            flex-wrap: wrap;
            gap: 6px 10px;
            margin-top: 10px;
          }
          .admin-active-case strong {
            color: var(--admin-pink);
            font-size: 14px;
          }
          .admin-active-case span {
            color: var(--admin-muted);
            font-size: 12px;
          }
          .admin-case-id {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--admin-line);
            border-radius: 6px;
            color: var(--admin-text) !important;
            display: inline-block;
            font-family: "Cascadia Mono", "Consolas", monospace;
            font-size: 12px;
            overflow-wrap: anywhere;
            padding: 3px 7px;
          }
          .admin-top-controls {
            align-items: center;
            display: grid;
            gap: 8px;
            grid-template-columns: 111px 280px 180px 222px;
            min-width: 0;
          }
          .admin-pill,
          .admin-select,
          .admin-status-pill,
          .admin-langsmith-status {
            border: 1px solid var(--admin-line);
            border-radius: 999px;
            color: var(--admin-text);
            display: inline-flex;
            align-items: center;
            font-size: 13px;
            min-height: 36px;
            padding: 0 15px;
          }
          .admin-select,
          .admin-status-pill,
          .admin-langsmith-status {
            max-width: 240px;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .admin-select-spacer {
            display: inline-flex;
            visibility: hidden;
            width: 280px;
          }
          .admin-status-pill {
            font-size: 11px;
            justify-content: center;
            max-width: 180px;
            padding: 0 8px;
          }
          .admin-pill,
          .admin-langsmith-status {
            border-color: rgba(245,161,207,.52);
            color: var(--admin-pink);
          }
          .admin-observability-grid {
            display: grid;
            gap: 9px;
            grid-template-columns: repeat(7, minmax(0, 1fr));
            margin-bottom: 12px;
          }
          .admin-card,
          .admin-trace-map,
          .admin-panel,
          .admin-trace-panel,
          .admin-gate-panel {
            background:
              linear-gradient(145deg, rgba(255,255,255,.075), rgba(255,255,255,.018)),
              radial-gradient(circle at 90% 0%, rgba(245,161,207,.075), transparent 38%);
            border: 1px solid var(--admin-line);
            border-radius: 10px;
            box-shadow:
              inset 0 1px 0 rgba(255,255,255,.08),
              0 20px 72px rgba(0,0,0,.38);
            padding: 12px 14px;
          }
          .admin-card strong,
          .admin-graph-node strong,
          .admin-gate-card strong {
            display: block;
            font-weight: 600;
          }
          .admin-card strong {
            font-size: 13px;
            line-height: 1.15;
          }
          .admin-card span,
          .admin-gate-card span {
            color: var(--admin-muted);
            font-size: 12px;
          }
          .admin-card p {
            font-size: 11px;
            line-height: 1.2;
          }
          .admin-card {
            align-items: center;
            display: grid;
            gap: 6px 10px;
            grid-template-columns: 36px minmax(0, 1fr);
            height: 84px;
            min-height: 84px;
            overflow: hidden;
            padding: 9px 10px;
            position: relative;
          }
          .admin-card::before {
            background: rgba(255,255,255,.22);
            border-radius: 999px;
            bottom: 9px;
            content: "";
            left: 0;
            position: absolute;
            top: 9px;
            width: 3px;
          }
          .admin-card[data-state="ok"]::before { background: var(--admin-green); }
          .admin-card[data-state="active"]::before,
          .admin-card[data-state="hitl"]::before { background: var(--admin-pink); }
          .admin-card[data-state="retry"]::before { background: var(--admin-gold); }
          .admin-card[data-state="error"]::before,
          .admin-card[data-state="blocked"]::before {
            background: var(--admin-red);
            box-shadow: 0 0 18px rgba(240,132,143,.34);
          }
          .admin-card[data-state="partial"]::before { background: var(--admin-blue); }
          .admin-card[data-state="waiting"]::before,
          .admin-card[data-state="skipped"]::before { background: rgba(255,255,255,.24); }
          .admin-card-icon {
            align-items: center;
            background: linear-gradient(145deg, rgba(245,161,207,.16), rgba(245,161,207,.035));
            border: 1px solid rgba(245,161,207,.44);
            border-radius: 999px;
            color: var(--admin-pink);
            display: inline-flex;
            justify-content: center;
            height: 36px;
            width: 36px;
          }
          .admin-card-icon svg {
            height: 20px;
            width: 20px;
          }
          .admin-card-body {
            display: grid;
            gap: 1px;
            min-width: 0;
          }
          .admin-card-body strong {
            display: -webkit-box;
            overflow: hidden;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 2;
          }
          .admin-card-body > span,
          .admin-card-body > p {
            overflow: hidden;
            padding-right: 18px;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .admin-card-body > .admin-card-value {
            font-size: 11px;
            letter-spacing: -.01em;
            padding-right: 2px;
          }
          .admin-card-status {
            align-items: center;
            bottom: 9px;
            color: var(--admin-green);
            display: inline-flex;
            height: 16px;
            justify-content: center;
            position: absolute;
            right: 9px;
            width: 16px;
          }
          .admin-card-status svg {
            height: 16px;
            width: 16px;
          }
          .admin-card[data-state="ok"] .admin-card-body > span,
          .admin-card[data-state="ok"] .admin-card-status,
          .admin-gate-card[data-state="ok"] span { color: var(--admin-green); }
          .admin-card[data-state="active"] .admin-card-body > span,
          .admin-card[data-state="active"] .admin-card-status,
          .admin-card[data-state="hitl"] .admin-card-body > span,
          .admin-card[data-state="hitl"] .admin-card-status,
          .admin-gate-card[data-state="active"] span,
          .admin-gate-card[data-state="hitl"] span { color: var(--admin-pink); }
          .admin-card[data-state="retry"] .admin-card-body > span,
          .admin-card[data-state="retry"] .admin-card-status,
          .admin-gate-card[data-state="retry"] span { color: var(--admin-gold); }
          .admin-card[data-state="error"] .admin-card-body > span,
          .admin-card[data-state="error"] .admin-card-status,
          .admin-card[data-state="blocked"] .admin-card-body > span,
          .admin-card[data-state="blocked"] .admin-card-status,
          .admin-gate-card[data-state="error"] span,
          .admin-gate-card[data-state="blocked"] span { color: var(--admin-red); }
          .admin-card[data-state="partial"] .admin-card-body > span,
          .admin-card[data-state="partial"] .admin-card-status,
          .admin-gate-card[data-state="partial"] span { color: var(--admin-blue); }
          .admin-card[data-state="waiting"] .admin-card-status,
          .admin-card[data-state="skipped"] .admin-card-status { color: rgba(255,255,255,.42); }
          .admin-main-grid {
            display: grid;
            gap: 12px;
            grid-template-columns: minmax(0, 1fr) minmax(420px, .72fr);
            align-items: start;
            margin-bottom: 18px;
            min-height: 512px;
          }
          .admin-trace-map {
            min-height: 512px;
          }
          .admin-section-head {
            align-items: center;
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
            min-width: 0;
          }
          .admin-section-head h2 {
            font-size: 17px;
            font-weight: 600;
            line-height: 1.18;
            margin: 0;
            padding: 0 !important;
          }
          .admin-node-row {
            align-content: space-between;
            display: grid;
            gap: 4px;
            min-height: 440px;
          }
          .admin-workflow-row {
            align-items: center;
            display: flex;
            gap: 6px;
            min-height: 48px;
            min-width: 0;
          }
          .admin-parallel-stage {
            background: rgba(255,255,255,.025);
            border: 1px solid rgba(255,255,255,.11);
            border-radius: 10px;
            padding: 7px 9px 8px;
          }
          .admin-parallel-head {
            align-items: center;
            color: var(--admin-muted);
            display: flex;
            font-size: 10px;
            gap: 7px;
            margin-bottom: 5px;
          }
          .admin-parallel-head span {
            background: rgba(245,161,207,.10);
            border: 1px solid rgba(245,161,207,.24);
            border-radius: 999px;
            color: var(--admin-pink);
            padding: 2px 7px;
          }
          .admin-parallel-head strong {
            color: rgba(255,255,255,.80);
            font-weight: 600;
          }
          .admin-parallel-body {
            display: grid;
            gap: 6px;
            padding-right: 116px;
            position: relative;
          }
          .admin-parallel-lane {
            align-items: center;
            display: flex;
            gap: 5px;
            min-height: 54px;
            min-width: 0;
          }
          .admin-parallel-lane .admin-graph-node {
            flex: 0 0 96px;
            min-width: 96px;
          }
          .admin-lane-label {
            align-items: center;
            color: rgba(255,255,255,.58);
            display: inline-flex;
            flex: 0 0 52px;
            font-size: 9px;
            font-weight: 600;
            letter-spacing: .06em;
            text-transform: uppercase;
          }
          .admin-parallel-route,
          .admin-join-path,
          .admin-join-trunk {
            background: rgba(255,255,255,.28);
            color: rgba(255,255,255,.28);
            height: 2px;
            position: relative;
          }
          .admin-parallel-route {
            flex: 0 0 16px;
          }
          .admin-join-path {
            flex: 1 1 18px;
            min-width: 10px;
          }
          .admin-parallel-route::after,
          .admin-join-trunk::after {
            border-bottom: 4px solid transparent;
            border-left: 6px solid currentColor;
            border-top: 4px solid transparent;
            content: "";
            position: absolute;
            right: -1px;
            top: -3px;
          }
          .admin-join-trunk {
            position: absolute;
            right: 105px;
            top: 50%;
            width: 12px;
          }
          .admin-join-trunk::before {
            background: currentColor;
            bottom: -30px;
            content: "";
            position: absolute;
            right: 11px;
            top: -30px;
            width: 2px;
          }
          .admin-parallel-body > .admin-graph-node {
            min-width: 104px;
            position: absolute;
            right: 0;
            top: 50%;
            transform: translateY(-50%);
            width: 104px;
          }
          .admin-parallel-route[data-state="ok"],
          .admin-join-path[data-state="ok"],
          .admin-join-trunk[data-state="ok"] { background: var(--admin-green); color: var(--admin-green); }
          .admin-parallel-route[data-state="active"],
          .admin-join-path[data-state="active"],
          .admin-join-trunk[data-state="active"] { background: var(--admin-pink); color: var(--admin-pink); }
          .admin-parallel-route[data-state="retry"],
          .admin-join-path[data-state="retry"],
          .admin-join-trunk[data-state="retry"] { background: var(--admin-gold); color: var(--admin-gold); }
          .admin-parallel-route[data-state="error"],
          .admin-parallel-route[data-state="blocked"],
          .admin-join-path[data-state="error"],
          .admin-join-path[data-state="blocked"],
          .admin-join-trunk[data-state="error"],
          .admin-join-trunk[data-state="blocked"] { background: var(--admin-red); color: var(--admin-red); }
          .admin-parallel-route[data-state="partial"],
          .admin-join-path[data-state="partial"],
          .admin-join-trunk[data-state="partial"] { background: var(--admin-blue); color: var(--admin-blue); }
          .admin-parallel-route[data-state="skipped"],
          .admin-parallel-route[data-state="waiting"],
          .admin-join-path[data-state="skipped"],
          .admin-join-path[data-state="waiting"],
          .admin-join-trunk[data-state="skipped"],
          .admin-join-trunk[data-state="waiting"] {
            background: repeating-linear-gradient(to right, rgba(255,255,255,.26) 0 4px, transparent 4px 7px);
            color: rgba(255,255,255,.30);
          }
          .admin-stage-handoff {
            align-items: center;
            color: rgba(255,255,255,.44);
            display: flex;
            font-size: 9px;
            gap: 7px;
            justify-content: center;
            min-height: 14px;
          }
          .admin-stage-handoff .admin-handoff-line {
            background: currentColor;
            height: 2px;
            position: relative;
            width: 32px;
          }
          .admin-stage-handoff .admin-handoff-line::after {
            border-bottom: 4px solid transparent;
            border-left: 6px solid currentColor;
            border-top: 4px solid transparent;
            content: "";
            position: absolute;
            right: -1px;
            top: -3px;
          }
          .admin-stage-handoff[data-state="ok"] { color: var(--admin-green); }
          .admin-stage-handoff[data-state="active"],
          .admin-stage-handoff[data-state="hitl"] { color: var(--admin-pink); }
          .admin-stage-handoff[data-state="retry"] { color: var(--admin-gold); }
          .admin-stage-handoff[data-state="blocked"],
          .admin-stage-handoff[data-state="error"] { color: var(--admin-red); }
          .admin-stage-handoff[data-state="partial"] { color: var(--admin-blue); }
          .admin-reflexion-loop {
            align-items: center;
            border: 1px solid currentColor;
            border-radius: 999px;
            color: rgba(255,255,255,.44);
            display: inline-flex;
            font-size: 9px;
            gap: 5px;
            justify-self: center;
            line-height: 1;
            padding: 3px 9px;
          }
          .admin-reflexion-loop svg { height: 11px; width: 11px; }
          .admin-reflexion-loop[data-state="ok"] { color: var(--admin-green); }
          .admin-reflexion-loop[data-state="active"],
          .admin-reflexion-loop[data-state="hitl"] { color: var(--admin-pink); }
          .admin-reflexion-loop[data-state="retry"] { color: var(--admin-gold); }
          .admin-reflexion-loop[data-state="blocked"],
          .admin-reflexion-loop[data-state="error"] { color: var(--admin-red); }
          .admin-graph-node {
            align-items: center;
            background: rgba(255,255,255,.035);
            border: 1px solid rgba(255,255,255,.20);
            border-radius: 8px;
            display: grid;
            gap: 2px;
            justify-items: center;
            min-height: 54px;
            min-width: 96px;
            padding: 6px 9px;
            text-align: center;
          }
          .admin-node-title {
            align-items: center;
            display: inline-flex;
            gap: 5px;
            justify-content: center;
            min-width: 0;
          }
          .admin-node-icon {
            align-items: center;
            color: rgba(255,255,255,.72);
            display: inline-flex;
            flex: 0 0 18px;
            height: 18px;
            justify-content: center;
            width: 18px;
          }
          .admin-node-icon svg {
            height: 18px;
            width: 18px;
          }
          .admin-graph-node strong {
            font-size: 12px;
            line-height: 1.12;
            white-space: nowrap;
          }
          .admin-graph-node[data-state="ok"] {
            background: rgba(139,217,140,.10);
            border-color: rgba(139,217,140,.48);
          }
          .admin-graph-node[data-state="ok"] .admin-node-icon,
          .admin-graph-node[data-state="ok"] .admin-node-status { color: var(--admin-green); }
          .admin-graph-node[data-state="active"] {
            background: rgba(245,161,207,.13);
            border-color: rgba(245,161,207,.72);
            box-shadow: 0 0 0 1px rgba(245,161,207,.10), 0 10px 30px rgba(245,161,207,.12);
          }
          .admin-graph-node[data-state="active"] .admin-node-icon,
          .admin-graph-node[data-state="active"] .admin-node-status { color: var(--admin-pink); }
          .admin-graph-node[data-state="retry"] {
            background: rgba(236,194,87,.10);
            border-color: rgba(236,194,87,.58);
          }
          .admin-graph-node[data-state="retry"] .admin-node-icon,
          .admin-graph-node[data-state="retry"] .admin-node-status { color: var(--admin-gold); }
          .admin-graph-node[data-state="skipped"],
          .admin-graph-node[data-state="waiting"] {
            background: rgba(255,255,255,.035);
            border-color: rgba(255,255,255,.32);
            border-style: dashed;
          }
          .admin-graph-node[data-state="skipped"] { opacity: .72; }
          .admin-graph-node[data-state="error"] {
            background: rgba(240,132,143,.13);
            border-color: rgba(240,132,143,.74);
          }
          .admin-graph-node[data-state="error"] .admin-node-icon,
          .admin-graph-node[data-state="error"] .admin-node-status,
          .admin-graph-node[data-state="blocked"] .admin-node-icon,
          .admin-graph-node[data-state="blocked"] .admin-node-status {
            color: var(--admin-red);
          }
          .admin-graph-node[data-state="blocked"] {
            background: rgba(240,132,143,.07);
            border-color: rgba(240,132,143,.48);
            border-style: dashed;
          }
          .admin-graph-node[data-state="hitl"] {
            background: rgba(245,161,207,.10);
            border-color: rgba(245,161,207,.55);
          }
          .admin-graph-node[data-state="hitl"] .admin-node-icon,
          .admin-graph-node[data-state="hitl"] .admin-node-status { color: var(--admin-pink); }
          .admin-graph-node[data-state="partial"] {
            background: rgba(142,180,255,.09);
            border-color: rgba(142,180,255,.52);
          }
          .admin-graph-node[data-state="partial"] .admin-node-icon,
          .admin-graph-node[data-state="partial"] .admin-node-status { color: var(--admin-blue); }
          .admin-node-state-icon {
            align-items: center;
            display: inline-flex;
            flex: 0 0 11px;
            height: 11px;
            justify-content: center;
            width: 11px;
          }
          .admin-node-state-icon svg {
            height: 11px;
            width: 11px;
          }
          .admin-graph-node.is-diamond {
            align-items: center;
            background: transparent;
            border: 0;
            display: grid;
            height: auto;
            justify-items: center;
            min-height: 64px;
            min-width: 68px;
            padding: 0;
            position: relative;
            width: 68px;
          }
          .admin-graph-node.is-diamond .admin-node-title {
            align-items: center;
            border: 1px solid rgba(245,161,207,.62);
            display: grid;
            height: 40px;
            justify-items: center;
            position: relative;
            transform: rotate(45deg);
            width: 40px;
          }
          .admin-graph-node.is-diamond .admin-node-title strong {
            font-size: 10px;
            transform: rotate(-45deg);
          }
          .admin-graph-node.is-diamond[data-state="ok"] .admin-node-title { border-color: rgba(139,217,140,.62); }
          .admin-graph-node.is-diamond[data-state="error"] .admin-node-title,
          .admin-graph-node.is-diamond[data-state="blocked"] .admin-node-title { border-color: rgba(240,132,143,.72); }
          .admin-graph-node.is-diamond[data-state="waiting"] .admin-node-title { border-color: rgba(255,255,255,.28); border-style: dashed; }
          .admin-graph-node.is-diamond .admin-node-duration {
            display: none;
          }
          .admin-node-status,
          .admin-node-duration {
            align-items: center;
            display: block;
            font-size: 10px;
            line-height: 1.25;
          }
          .admin-node-status {
            background: rgba(255,255,255,.045);
            border: 1px solid rgba(255,255,255,.13);
            border-radius: 999px;
            display: inline-flex;
            gap: 4px;
            justify-content: center;
            max-width: 136px;
            overflow: hidden;
            padding: 1px 5px;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .admin-graph-node[data-state="ok"] .admin-node-status {
            background: rgba(139,217,140,.11);
            border-color: rgba(139,217,140,.30);
          }
          .admin-graph-node[data-state="active"] .admin-node-status,
          .admin-graph-node[data-state="hitl"] .admin-node-status {
            background: rgba(245,161,207,.13);
            border-color: rgba(245,161,207,.36);
          }
          .admin-graph-node[data-state="retry"] .admin-node-status {
            background: rgba(236,194,87,.12);
            border-color: rgba(236,194,87,.34);
          }
          .admin-graph-node[data-state="error"] .admin-node-status,
          .admin-graph-node[data-state="blocked"] .admin-node-status {
            background: rgba(240,132,143,.13);
            border-color: rgba(240,132,143,.38);
          }
          .admin-graph-node[data-state="partial"] .admin-node-status {
            background: rgba(142,180,255,.11);
            border-color: rgba(142,180,255,.32);
          }
          .admin-graph-node[data-state="waiting"] .admin-node-status,
          .admin-graph-node[data-state="skipped"] .admin-node-status {
            background: rgba(255,255,255,.035);
            border-color: rgba(255,255,255,.16);
            color: rgba(255,255,255,.58);
          }
          .admin-flow-link {
            background: rgba(255,255,255,.28);
            color: rgba(255,255,255,.28);
            flex: 1 1 26px;
            height: 2px;
            max-width: 30px;
            min-width: 16px;
            position: relative;
          }
          .admin-flow-link::after {
            border-bottom: 5px solid transparent;
            border-left: 7px solid currentColor;
            border-top: 5px solid transparent;
            content: "";
            position: absolute;
            right: -1px;
            top: -4px;
          }
          .admin-flow-link[data-state="ok"] { background: var(--admin-green); color: var(--admin-green); }
          .admin-flow-link[data-state="active"],
          .admin-flow-link[data-state="hitl"] { background: var(--admin-pink); color: var(--admin-pink); }
          .admin-flow-link[data-state="retry"] { background: var(--admin-gold); color: var(--admin-gold); }
          .admin-flow-link[data-state="error"],
          .admin-flow-link[data-state="blocked"] { background: var(--admin-red); color: var(--admin-red); }
          .admin-flow-link[data-state="partial"] { background: var(--admin-blue); color: var(--admin-blue); }
          .admin-flow-link[data-state="skipped"],
          .admin-flow-link[data-state="waiting"] {
            background: repeating-linear-gradient(to right, rgba(255,255,255,.26) 0 4px, transparent 4px 7px);
            color: rgba(255,255,255,.30);
          }
          .admin-graph-legend {
            align-items: center;
            color: var(--admin-muted);
            display: flex;
            flex-wrap: wrap;
            font-size: 12px;
            gap: 7px 13px;
            margin-top: 3px;
          }
          .admin-legend-item {
            align-items: center;
            display: inline-flex;
            gap: 8px;
          }
          .admin-legend-mark {
            align-items: center;
            border: 1px solid currentColor;
            border-radius: 999px;
            color: var(--admin-muted);
            display: inline-flex;
            height: 17px;
            justify-content: center;
            width: 17px;
          }
          .admin-legend-mark svg { height: 11px; width: 11px; }
          .admin-legend-mark[data-state="ok"] { color: var(--admin-green); }
          .admin-legend-mark[data-state="active"],
          .admin-legend-mark[data-state="hitl"] { color: var(--admin-pink); }
          .admin-legend-mark[data-state="retry"] { color: var(--admin-gold); }
          .admin-legend-mark[data-state="error"] { color: var(--admin-red); }
          .admin-legend-mark[data-state="skipped"],
          .admin-legend-mark[data-state="waiting"] { color: rgba(255,255,255,.48); }
          @keyframes admin-status-spin { to { transform: rotate(360deg); } }
          .admin-graph-node[data-state="active"] .admin-node-state-icon svg,
          .admin-legend-mark[data-state="active"] svg {
            animation: admin-status-spin 1.2s linear infinite;
          }
          @media (prefers-reduced-motion: reduce) {
            .admin-graph-node[data-state="active"] .admin-node-state-icon svg,
            .admin-legend-mark[data-state="active"] svg { animation: none; }
          }
          .admin-right-rail,
          .admin-bottom-grid {
            display: grid;
            gap: 8px;
            min-width: 0;
          }
          .admin-right-rail {
            grid-template-rows: minmax(0, 1.42fr) minmax(0, 1fr);
            min-height: 512px;
          }
          .admin-bottom-grid {
            grid-template-columns: minmax(0, .95fr) minmax(0, .68fr) minmax(520px, 1fr);
          }
          .admin-bottom-grid .admin-panel {
            min-height: 210px;
          }
          .admin-kv-grid {
            display: grid;
            gap: 5px 10px;
            grid-template-columns: 108px minmax(0, 1fr);
          }
          .admin-bottom-grid .admin-kv-grid {
            font-size: 13px;
            gap: 4px 8px;
            grid-template-columns: minmax(0, 1fr) auto;
            line-height: 1.22;
          }
          .admin-bottom-grid .admin-kv-grid dt {
            white-space: nowrap;
          }
          .admin-kv-grid dt {
            color: var(--admin-muted);
          }
          .admin-kv-grid dd {
            margin: 0;
          }
          .admin-trace-panel .admin-kv-grid,
          .admin-trace-metrics {
            display: grid;
            gap: 4px 10px;
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
          .admin-trace-metrics dl,
          .admin-trace-panel dl {
            display: grid;
            font-size: 12px;
            gap: 4px;
            grid-template-columns: 52px minmax(0, 1fr);
            line-height: 1.2;
            min-width: 0;
            margin: 0;
          }
          .admin-trace-metrics dt,
          .admin-trace-metrics dd,
          .admin-kv-grid dt,
          .admin-kv-grid dd {
            min-width: 0;
            overflow-wrap: anywhere;
          }
          .admin-trace-metrics dd {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .admin-trace-panel .admin-kv-grid dt,
          .admin-trace-panel .admin-kv-grid dd {
            display: inline;
          }
          .admin-langsmith-action {
            border: 1px solid rgba(245,161,207,.58);
            border-radius: 10px;
            color: var(--admin-pink);
            display: inline-flex;
            font-size: 13px;
            justify-content: center;
            margin-top: 8px;
            min-height: 34px;
            padding: 7px 12px;
            width: 100%;
          }
          .admin-langsmith-action.is-disabled {
            cursor: not-allowed;
            opacity: .72;
          }
          .admin-gate-row,
          .admin-lineage-cards {
            display: grid;
            gap: 10px;
            grid-template-columns: repeat(5, minmax(0, 1fr));
          }
          .admin-lineage-cards {
            grid-template-columns: repeat(4, minmax(0, 1fr));
          }
          .admin-gate-card {
            background: rgba(255,255,255,.035);
            border: 1px solid var(--admin-line);
            border-radius: 9px;
            min-height: 42px;
            padding: 6px;
            text-align: center;
          }
          .admin-lineage-flow {
            align-items: center;
            display: grid;
            gap: 8px;
            grid-template-columns: repeat(4, minmax(0, 1fr));
          }
          .admin-safe-note {
            border: 1px solid var(--admin-line);
            border-radius: 10px;
            font-size: 12px;
            line-height: 1.28;
            margin-top: 6px;
            padding: 6px;
          }
          @media (max-width: 1420px) {
            .admin-console-hero { grid-template-columns: 1fr; }
            .admin-top-controls {
              grid-template-columns: 111px 180px 222px;
              justify-content: start;
            }
            .admin-select-spacer { display: none; }
          }
          @media (max-width: 1180px) {
            .admin-observability-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .admin-console-hero,
            .admin-shell,
            .admin-main-grid,
            .admin-bottom-grid { grid-template-columns: 1fr; }
            .admin-sidebar { min-height: auto; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _admin_dashboard_html(
    snapshot: AdminSnapshot,
    startup_snapshot: StartupTraceAdminSnapshot,
    *,
    context: AdminDashboardContext | None = None,
) -> str:
    dashboard_context = context or {}
    trace_summary = snapshot["trace_summary"]
    startup_trace = startup_snapshot["trace_summary"]
    total_events = trace_summary.get("total_events", 0)
    rows = startup_snapshot["node_timeline"]
    usage = startup_snapshot["usage_summary"]
    lineage = startup_snapshot["report_lineage"]
    report_rows = snapshot["report_integrity"]
    privacy_rows = snapshot["privacy_redaction"]
    source_rows = snapshot["source_health"]
    evaluations = snapshot["evaluations"]
    cost_latency = snapshot["cost_latency"]
    cost = usage.get("cost_usd") or cost_latency.get("estimated_cost_usd")
    latency = cost_latency.get("latency_ms_total")
    workflow_state = _workflow_summary_state(rows)
    langsmith_state = _status_card_state(_health_value(startup_snapshot["langsmith_health"]))
    local_audit_state = "ok" if total_events > 0 else "waiting"
    privacy_value = _privacy_denials(privacy_rows)
    privacy_state = "ok" if privacy_value == "0" else "error"
    usage_state = "ok" if usage.get("total_tokens") is not None else "waiting"
    cost_state = "ok" if cost is not None else "waiting"
    latency_state = "ok" if isinstance(latency, int | float) else "waiting"
    case_label = _compact_admin_label(startup_trace["case_id"] or "ожидает кейс")
    run_label = _compact_admin_label(startup_trace["run_id"] or "ожидает run")
    project_name = str(dashboard_context.get("project_name") or "Проект без названия")
    full_case_id = _compact_admin_label(
        dashboard_context.get("case_id") or startup_trace["case_id"] or "—",
        max_chars=64,
    )
    workflow_mode_label = _admin_workflow_mode_label(dashboard_context)
    runtime_langsmith_status = _runtime_langsmith_status_label(dashboard_context)
    last_run_state = (
        _last_run_result(rows)
        if startup_trace["total_events"] or total_events
        else "ожидает"
    )
    cards = (
        (
            "Workflow",
            _workflow_result(rows),
            f"{startup_trace['total_events'] or total_events} events",
            workflow_state,
        ),
        (
            "LangSmith exporter",
            _health_value(startup_snapshot["langsmith_health"]),
            "selected trace history",
            langsmith_state,
        ),
        (
            "Local audit",
            _status_or_waiting(total_events > 0),
            "source of truth",
            local_audit_state,
        ),
        (
            "Privacy leaks",
            privacy_value,
            "denials",
            privacy_state,
        ),
        (
            "OpenAI calls",
            "1" if usage.get("total_tokens") is not None else "—",
            "usage DTO",
            usage_state,
        ),
        ("Стоимость", str(cost or "Ожидает"), "USD", cost_state),
        ("Время", _format_optional_number(latency, "ms"), "latency", latency_state),
    )
    return "\n".join(
        (
            '<section class="founder-admin-console admin-shell">',
            _admin_sidebar_html(),
            '<main class="admin-content">',
            '<div class="admin-console-hero">',
            "<div>",
            "<h1>Обзор системы</h1>",
            "<p>Наблюдаемость и доказательства работы реального startup workflow</p>",
            (
                '<div class="admin-active-case" aria-label="Текущий проект и Case ID">'
                f'<strong>{escape(project_name)}</strong><span>Case ID</span>'
                f'<span class="admin-case-id">{escape(full_case_id)}</span></div>'
            ),
            "</div>",
            '<div class="admin-top-controls">',
            f'<span class="admin-pill">{escape(workflow_mode_label)}</span>',
            '<span class="admin-select-spacer" aria-hidden="true"></span>',
            f'<span class="admin-status-pill">Запуск • {last_run_state}</span>',
            (
                '<span class="admin-langsmith-status">LangSmith runtime: '
                f'{escape(runtime_langsmith_status)}</span>'
            ),
            "</div>",
            "</div>",
            '<div class="admin-observability-grid">',
            *(_admin_card(title, value, note, state) for title, value, note, state in cards),
            "</div>",
            '<div class="admin-main-grid">',
            _startup_graph_html(rows, lineage=lineage, report_rows=report_rows),
            _admin_trace_panel_html(
                {
                    "case": case_label,
                    "run": run_label,
                    "spans": str(startup_trace["total_events"] or total_events),
                    "nodes": _timeline_text(rows, "node"),
                    "tools": _timeline_text(rows, "tool"),
                    "retries": _timeline_value(rows, "retry_count"),
                    "errors": _timeline_errors(rows),
                    "input": str(usage.get("input_tokens", "Ожидает")),
                    "tokens": str(usage.get("total_tokens", "Ожидает")),
                    "cost": str(cost or "Ожидает"),
                    "lineage": _lineage_status(lineage),
                },
                status=_selected_trace_status_label(startup_snapshot["langsmith_health"]),
            ),
            "</div>",
            '<div class="admin-bottom-grid">',
            _admin_small_panel_html(
                "Privacy & Egress",
                (
                    ("Внешние вызовы", str(len(source_rows))),
                    ("Raw-экспорт", "0 наблюдается"),
                    ("Отклонено", _privacy_denials(privacy_rows)),
                    ("Redaction", _status_or_waiting(bool(privacy_rows))),
                ),
            ),
            _admin_small_panel_html(
                "Reliability",
                (
                    ("Повторы", _timeline_value(rows, "retry_count")),
                    ("Ошибки инструментов", _timeline_errors(rows)),
                    ("Проверки качества", str(len(evaluations))),
                    ("Итог графа", _workflow_result(rows)),
                ),
            ),
            _admin_lineage_panel_html([lineage] if lineage else report_rows),
            "</div>",
            "</main>",
            "</section>",
        )
    )


def _admin_sidebar_html() -> str:
    nav_items = (
        ("Обзор системы", "overview", True),
        ("Граф агентов", "agents", False),
        ("Трейсы", "traces", False),
        ("Evaluation Gates", "gates", False),
        ("Privacy & Egress", "privacy", False),
        ("Cost & Latency", "cost", False),
        ("Report Lineage", "lineage", False),
    )
    nav = "".join(
        (
            f'<div class="admin-nav-item{" is-active" if active else ""}">'
            f'<span class="admin-nav-icon">{_admin_icon_svg(icon_key)}</span>'
            f"<span>{escape(label)}</span>"
            "</div>"
        )
        for label, icon_key, active in nav_items
    )
    mark_source = _admin_brand_mark_data_uri()
    mark_html = (
        f'<img src="{mark_source}" alt="" />'
        if mark_source is not None
        else _admin_icon_svg("workflow", class_name="admin-brand-fallback")
    )
    return (
        '<aside class="admin-sidebar">'
        f'<div class="admin-brand"><span class="admin-brand-mark" data-icon="brand">{mark_html}</span>'
        "<strong>Founder Intelligence</strong></div>"
        '<div class="admin-sidebar-label">ADMIN CONSOLE</div>'
        f'<nav class="admin-nav">{nav}</nav>'
        '<div class="admin-sidebar-footer">'
        '<div class="admin-nav-item"><span class="admin-nav-icon">'
        f'{_admin_icon_svg("workspace")}</span><span>Founder Workspace</span></div>'
        '<div class="admin-nav-item"><span class="admin-nav-icon">'
        f'{_admin_icon_svg("settings")}</span><span>Настройки</span></div>'
        "</div>"
        "</aside>"
    )


def _render_admin_overview_design(snapshot: AdminSnapshot) -> str:
    trace_summary = snapshot["trace_summary"]
    total_events = (
        trace_summary.get("total_events", 0)
        if isinstance(trace_summary, Mapping)
        else 0
    )
    cost_latency = snapshot["cost_latency"]
    cost = cost_latency.get("estimated_cost_usd") if isinstance(cost_latency, Mapping) else None
    latency = cost_latency.get("latency_ms_total") if isinstance(cost_latency, Mapping) else None
    privacy_rows = snapshot["privacy_redaction"]
    report_rows = snapshot["report_integrity"]
    source_rows = snapshot["source_health"]
    cards = (
        (
            "Workflow",
            _status_or_waiting(total_events > 0),
            f"{total_events} events",
            "ok" if total_events > 0 else "waiting",
        ),
        ("LangSmith exporter", "Ожидает", "нужно выбрать запуск", "waiting"),
        (
            "Local audit",
            _status_or_waiting(total_events > 0),
            "source of truth",
            "ok" if total_events > 0 else "waiting",
        ),
        (
            "Privacy leaks",
            _privacy_denials(privacy_rows),
            "denials",
            "ok",
        ),
        (
            "OpenAI calls",
            "1" if cost is not None else "—",
            "по usage/cost audit",
            "ok" if cost is not None else "waiting",
        ),
        (
            "Стоимость",
            _format_optional_number(cost, "$"),
            "USD",
            "ok" if cost is not None else "waiting",
        ),
        (
            "Время",
            _format_optional_number(latency, "ms"),
            "latency",
            "ok" if latency is not None else "waiting",
        ),
    )
    return "\n".join(
            (
                '<section class="founder-admin-console">',
                '<div class="admin-console-hero">',
                "<div>",
                "<h1>Обзор системы</h1>",
                "<p>Консоль контроля · Наблюдаемость и доказательства работы реального startup workflow</p>",
                "</div>",
                '<div class="admin-top-controls">',
                '<span class="admin-pill">LOCAL AUDIT</span>',
                '<span class="admin-select">Кейс выбирается фильтром</span>',
                '<span class="admin-status-pill">Последний запуск — по audit spool</span>',
                '<span class="admin-langsmith-status">LangSmith trace: ожидает выбор case/run</span>',
                "</div>",
                "</div>",
                '<div class="admin-observability-grid">',
                *(_admin_card(title, value, note, state) for title, value, note, state in cards),
                "</div>",
                '<div class="admin-main-grid">',
                _admin_graph_html("Ожидает"),
                _admin_trace_panel_html(
                    {
                        "case": "выберите Case ID",
                        "run": "выберите Run ID",
                        "spans": str(total_events),
                        "retries": "ожидает startup trace",
                        "errors": _observed_source_errors(source_rows),
                        "tokens": "ожидает выбранный запуск",
                        "cost": _format_optional_number(cost, "$"),
                        "lineage": f"{len(report_rows)} строк",
                    }
                ),
                "</div>",
                '<div class="admin-bottom-grid">',
                _admin_gate_panel_html("Ожидает"),
                _admin_small_panel_html(
                    "Privacy & Egress",
                    (
                        ("Внешние вызовы", str(len(source_rows))),
                        ("Raw-экспорт", "0 наблюдается"),
                        ("Redaction", _status_or_waiting(bool(privacy_rows))),
                    ),
                ),
                _admin_lineage_panel_html(report_rows),
                "</div>",
                "</section>",
            )
    )


def _render_startup_trace_design(snapshot: StartupTraceAdminSnapshot) -> str:
    trace_summary = snapshot["trace_summary"]
    usage = snapshot["usage_summary"]
    lineage = snapshot["report_lineage"]
    rows = snapshot["node_timeline"]
    return "\n".join(
            (
                '<section class="founder-admin-console">',
                '<div class="admin-console-hero">',
                "<div>",
                "<h1>Безопасный след LangSmith</h1>",
                "<p>Startup Trace · реальные DTO выбранного startup workflow без raw payload</p>",
                "</div>",
                '<div class="admin-top-controls">',
                f'<span class="admin-pill">case {escape(trace_summary["case_id"] or "Ожидает")}</span>',
                f'<span class="admin-select">run {escape(trace_summary["run_id"] or "Ожидает")}</span>',
                "</div>",
                "</div>",
                '<div class="admin-main-grid">',
                _startup_graph_html(rows),
                _admin_trace_panel_html(
                    {
                        "case": trace_summary["case_id"] or "Ожидает",
                        "run": trace_summary["run_id"] or "Ожидает",
                        "spans": str(trace_summary["total_events"]),
                        "nodes": _timeline_text(rows, "node"),
                        "tools": _timeline_text(rows, "tool"),
                        "retries": _timeline_value(rows, "retry_count"),
                        "errors": _timeline_errors(rows),
                        "input": str(usage.get("input_tokens", "Ожидает")),
                        "tokens": str(usage.get("total_tokens", "Ожидает")),
                        "cost": str(usage.get("cost_usd", "Ожидает")),
                        "lineage": _lineage_status(lineage),
                    }
                ),
                "</div>",
                '<div class="admin-bottom-grid">',
                _admin_gate_panel_html("По DTO"),
                _admin_small_panel_html(
                    "Reliability",
                    (
                        ("Повторы", _timeline_value(rows, "retry_count")),
                        ("Ошибки инструментов", _timeline_errors(rows)),
                        ("Итог графа", _workflow_result(rows)),
                    ),
                ),
                _admin_lineage_panel_html([lineage] if lineage else []),
                "</div>",
                "</section>",
            )
    )


def _admin_card(title: str, value: object, note: object, state: str) -> str:
    icon_key = _admin_card_icon_key(title)
    card_key = "-".join(title.casefold().split())
    status_icon = _workflow_state_icon(state)
    return (
        f'<article class="admin-card" data-card="{escape(card_key)}" data-state="{escape(state)}">'
        f'<span class="admin-card-icon">{_admin_icon_svg(icon_key)}</span>'
        '<div class="admin-card-body">'
        f"<strong>{escape(str(title))}</strong>"
        f'<span class="admin-card-value">{escape(str(value))}</span>'
        f"<p>{escape(str(note))}</p>"
        "</div>"
        f'<span class="admin-card-status" aria-label="{escape(_summary_state_label(state))}">'
        f'{_admin_icon_svg(status_icon)}</span>'
        "</article>"
    )


def _admin_card_icon_key(title: str) -> str:
    normalized = title.lower()
    if "workflow" in normalized:
        return "workflow"
    if "langsmith" in normalized:
        return "langsmith"
    if "audit" in normalized:
        return "audit"
    if "privacy" in normalized:
        return "privacy"
    if "openai" in normalized:
        return "openai"
    if "стоимость" in normalized:
        return "cost"
    if "время" in normalized:
        return "time"
    return "status"


def _admin_graph_html(status: str) -> str:
    return (
        '<section class="admin-trace-map">'
        '<div class="admin-section-head"><h2>Граф агентов (LangGraph)</h2></div>'
        f'{_workflow_map_html({}, default_status=status)}'
        "</section>"
    )


def _startup_graph_html(
    rows: Sequence[Mapping[str, AdminScalar]],
    *,
    lineage: Mapping[str, AdminScalar] | None = None,
    report_rows: Sequence[Mapping[str, AdminScalar]] = (),
) -> str:
    stage_rows = _workflow_stage_rows(rows, lineage=lineage, report_rows=report_rows)
    return (
        '<section class="admin-trace-map">'
        '<div class="admin-section-head"><h2>Граф агентов (LangGraph)</h2></div>'
        f'{_workflow_map_html(stage_rows, default_status="waiting")}'
        "</section>"
    )


def _workflow_map_html(
    stage_rows: Mapping[str, Mapping[str, AdminScalar]],
    *,
    default_status: str,
) -> str:
    row_one = (
        ("Document", "document", "document"),
        ("Profile", "profile", "profile"),
        ("Gate 2", "gate2", "hitl"),
        ("Product", "product", "product"),
    )
    row_two = (
        ("GTM", "gtm", "gtm"),
        ("Critic", "critic", "critic"),
        ("Arbiter", "arbiter", "arbiter"),
    )
    row_three = (
        ("Gate 3", "gate3", "hitl"),
        ("Report Draft", "report", "report"),
        ("Gate 4", "gate4", "hitl"),
    )
    row_four = (
        (_workflow_stage_label(stage_rows, "snapshot", "Snapshot"), "snapshot", "snapshot"),
        (_workflow_stage_label(stage_rows, "json", "JSON"), "json", "json"),
        (_workflow_stage_label(stage_rows, "html", "HTML"), "html", "html"),
        (_workflow_stage_label(stage_rows, "pdf", "PDF"), "pdf", "pdf"),
    )
    return (
        '<div class="admin-node-row">'
        f'{_workflow_row_html(row_one, stage_rows, default_status=default_status)}'
        f'{_workflow_parallel_html(stage_rows, default_status=default_status)}'
        f'{_workflow_handoff_html("market_analysis", "gtm", "Сведение веток → GTM", stage_rows, default_status=default_status)}'
        f'{_workflow_row_html(row_two, stage_rows, default_status=default_status)}'
        f'{_workflow_reflexion_html(stage_rows, default_status=default_status)}'
        f'{_workflow_handoff_html("arbiter", "gate3", "Решение Arbiter → Gate 3", stage_rows, default_status=default_status)}'
        f'{_workflow_row_html(row_three, stage_rows, default_status=default_status)}'
        f'{_workflow_handoff_html("gate4", "snapshot", "Gate 4 → артефакты", stage_rows, default_status=default_status)}'
        f'{_workflow_row_html(row_four, stage_rows, default_status=default_status, compact=True)}'
        f'{_workflow_legend_html()}'
        "</div>"
    )


def _workflow_row_html(
    nodes: Sequence[tuple[str, str, str]],
    stage_rows: Mapping[str, Mapping[str, AdminScalar]],
    *,
    default_status: str,
    compact: bool = False,
) -> str:
    cells: list[str] = []
    for index, (name, stage, kind) in enumerate(nodes):
        row = stage_rows.get(stage)
        cells.append(
            _workflow_node_html(
                name,
                stage,
                kind,
                row,
                default_status=default_status,
            )
        )
        if index < len(nodes) - 1:
            next_stage = nodes[index + 1][1]
            link_state = _workflow_link_state(row, stage_rows.get(next_stage), default_status)
            cells.append(
                f'<span class="admin-flow-link" data-edge="{escape(stage)}-{escape(next_stage)}" '
                f'data-state="{escape(link_state)}" '
                'aria-hidden="true"></span>'
            )
    modifier = " is-compact" if compact else ""
    return f'<div class="admin-workflow-row{modifier}">{"".join(cells)}</div>'


def _workflow_parallel_html(
    stage_rows: Mapping[str, Mapping[str, AdminScalar]],
    *,
    default_status: str,
) -> str:
    product = stage_rows.get("product")
    market_research = stage_rows.get("market_research")
    metrics = stage_rows.get("metrics")
    financial = stage_rows.get("financial")
    risk = stage_rows.get("risk")
    market_analysis = stage_rows.get("market_analysis")
    product_market_state = _workflow_link_state(product, market_research, default_status)
    product_metrics_state = _workflow_link_state(product, metrics, default_status)
    metrics_financial_state = _workflow_link_state(metrics, financial, default_status)
    financial_risk_state = _workflow_link_state(financial, risk, default_status)
    market_join_state = _workflow_link_state(
        market_research,
        market_analysis,
        default_status,
    )
    risk_join_state = _workflow_link_state(risk, market_analysis, default_status)
    analysis_state = _state_from_stage_row(market_analysis, default_status)
    return (
        '<section class="admin-parallel-stage" aria-label="Параллельные ветки после Product">'
        '<div class="admin-parallel-head">'
        '<span>После Product</span><strong>две параллельные ветки</strong>'
        "</div>"
        '<div class="admin-parallel-body">'
        '<div class="admin-parallel-lane" data-lane="market">'
        '<span class="admin-lane-label">Рынок</span>'
        f'<span class="admin-parallel-route" data-source="product" data-target="market_research" data-state="{escape(product_market_state)}"></span>'
        f'{_workflow_node_html("Market Research", "market_research", "market", market_research, default_status=default_status)}'
        f'<span class="admin-join-path" data-source="market_research" data-target="market_analysis" data-state="{escape(market_join_state)}"></span>'
        "</div>"
        '<div class="admin-parallel-lane" data-lane="finance">'
        '<span class="admin-lane-label">Расчёты</span>'
        f'<span class="admin-parallel-route" data-source="product" data-target="metrics" data-state="{escape(product_metrics_state)}"></span>'
        f'{_workflow_node_html("Metrics", "metrics", "metrics", metrics, default_status=default_status)}'
        f'<span class="admin-flow-link" data-edge="metrics-financial" data-state="{escape(metrics_financial_state)}" aria-hidden="true"></span>'
        f'{_workflow_node_html("Financial", "financial", "financial", financial, default_status=default_status)}'
        f'<span class="admin-flow-link" data-edge="financial-risk" data-state="{escape(financial_risk_state)}" aria-hidden="true"></span>'
        f'{_workflow_node_html("Risk", "risk", "risk", risk, default_status=default_status)}'
        f'<span class="admin-join-path" data-source="risk" data-target="market_analysis" data-state="{escape(risk_join_state)}"></span>'
        "</div>"
        f'<span class="admin-join-trunk" data-state="{escape(analysis_state)}" aria-hidden="true"></span>'
        f'{_workflow_node_html("Market Analysis", "market_analysis", "market", market_analysis, default_status=default_status)}'
        "</div>"
        "</section>"
    )


def _workflow_handoff_html(
    source_stage: str,
    target_stage: str,
    label: str,
    stage_rows: Mapping[str, Mapping[str, AdminScalar]],
    *,
    default_status: str,
) -> str:
    state = _workflow_link_state(
        stage_rows.get(source_stage),
        stage_rows.get(target_stage),
        default_status,
    )
    return (
        f'<div class="admin-stage-handoff" data-edge="{escape(source_stage)}-{escape(target_stage)}" '
        f'data-state="{escape(state)}" aria-label="{escape(label)}">'
        '<span class="admin-handoff-line" aria-hidden="true"></span>'
        f'<span>{escape(label)}</span>'
        "</div>"
    )


def _workflow_reflexion_html(
    stage_rows: Mapping[str, Mapping[str, AdminScalar]],
    *,
    default_status: str,
) -> str:
    state = _workflow_link_state(
        stage_rows.get("arbiter"),
        stage_rows.get("critic"),
        default_status,
    )
    return (
        f'<div class="admin-reflexion-loop" data-edge="arbiter-critic" data-loop-limit="2" '
        f'data-state="{escape(state)}" aria-label="Bounded Reflexion: Arbiter возвращает задачу Critic, максимум две итерации">'
        f'{_admin_icon_svg("rotate-ccw")}'
        '<span>Reflexion: Arbiter ↺ Critic · максимум 2 итерации</span>'
        "</div>"
    )


def _workflow_node_html(
    name: str,
    stage: str,
    kind: str,
    row: Mapping[str, AdminScalar] | None,
    *,
    default_status: str,
) -> str:
    status = str(row.get("status", default_status)) if row is not None else default_status
    duration = _node_duration(row)
    state = _state_from_stage_row(row, default_status)
    status_label = _stage_status_label(stage, state, row, status)
    meta_label, meta_title = _node_meta(row, duration)
    diamond_class = " is-diamond" if name.startswith("Gate ") else ""
    icon_key = _admin_node_icon_key(name, kind)
    icon_html = "" if name.startswith("Gate ") else (
        f'<span class="admin-node-icon">{_admin_icon_svg(icon_key)}</span>'
    )
    status_icon = _admin_icon_svg(_workflow_state_icon(state))
    aria_label = f"{name}: {status_label}"
    return (
        f'<article class="admin-graph-node{diamond_class}" data-node="{escape(kind)}" '
        f'data-stage="{escape(stage)}" data-state="{escape(state)}" '
        f'aria-label="{escape(aria_label)}">'
        f'<span class="admin-node-title">{icon_html}<strong>{escape(name)}</strong></span>'
        '<span class="admin-node-status">'
        f'<span class="admin-node-state-icon">{status_icon}</span>{escape(status_label)}'
        "</span>"
        f'<span class="admin-node-duration" title="{escape(meta_title)}">{escape(meta_label)}</span>'
        "</article>"
    )


def _admin_node_icon_key(name: str, kind: str) -> str:
    normalized = name.lower()
    if normalized.startswith("snapshot"):
        return "snapshot"
    if normalized.startswith("json"):
        return "json"
    if normalized.startswith("html"):
        return "html"
    if normalized.startswith("pdf"):
        return "pdf"
    return kind


def _workflow_node_state(
    name: str,
    status: str,
    row: Mapping[str, AdminScalar] | None,
) -> str:
    del name
    normalized = status.strip().casefold().replace("-", "_").replace(" ", "_")
    if row is not None:
        retry_count = row.get("retry_count")
        if isinstance(retry_count, int | float) and not isinstance(retry_count, bool) and retry_count > 0:
            return "retry"
    if normalized in {"running", "in_progress", "executing", "processing"}:
        return "active"
    if normalized in {"approval_required", "review_required", "paused", "interrupted", "hitl"}:
        return "hitl"
    if normalized in {"skipped", "deferred"}:
        return "skipped"
    if normalized in {"failed", "error", "fatal"}:
        return "error"
    if normalized in {"blocked", "policy_blocked"}:
        return "blocked"
    if normalized in {"retry", "retrying", "retryable_error"}:
        return "retry"
    if normalized in {"partial", "fallback", "degraded"}:
        return "partial"
    if normalized in {"success", "completed", "exported", "approved", "linked", "canonical"}:
        return "ok"
    return "waiting"


def _observed_node_rows(
    rows: Sequence[Mapping[str, AdminScalar]],
) -> dict[str, Mapping[str, AdminScalar]]:
    observed: dict[str, Mapping[str, AdminScalar]] = {}
    for row in rows:
        node = row.get("node")
        if isinstance(node, str) and node:
            observed[_normalize_workflow_name(node)] = row
    return observed


def _workflow_stage_rows(
    rows: Sequence[Mapping[str, AdminScalar]],
    *,
    lineage: Mapping[str, AdminScalar] | None,
    report_rows: Sequence[Mapping[str, AdminScalar]],
) -> dict[str, Mapping[str, AdminScalar]]:
    observed = _observed_node_rows(rows)
    stages: dict[str, Mapping[str, AdminScalar]] = {}
    for stage, aliases in _ADMIN_STAGE_ALIASES.items():
        matched = [observed[alias] for alias in aliases if alias in observed]
        if matched:
            stages[stage] = _summarize_stage_rows(matched)

    gate2 = stages.get("gate2")
    if gate2 is not None and _state_from_stage_row(gate2, "waiting") in {"ok", "partial", "retry"}:
        stages["gate2"] = {**gate2, "ui_status": "HITL пройден"}

    if "gate3" not in stages:
        arbiter = stages.get("arbiter")
        report = stages.get("report")
        if report is not None and _state_from_stage_row(report, "waiting") in {"ok", "partial", "retry"}:
            stages["gate3"] = {"status": "completed", "ui_state": "ok", "ui_status": "HITL пройден"}
        elif arbiter is not None:
            arbiter_state = _state_from_stage_row(arbiter, "waiting")
            if arbiter_state in {"error", "blocked"}:
                stages["gate3"] = {**arbiter, "ui_state": arbiter_state}
            elif arbiter_state == "active":
                stages["gate3"] = {**arbiter, "ui_state": "active", "ui_status": "Проверяет"}
            else:
                stages["gate3"] = {"status": "review_required", "ui_state": "hitl", "ui_status": "Ожидает решения"}

    lineage_row = lineage or {}
    if "gate4" not in stages:
        gate4_status = str(lineage_row.get("gate4_status", "")).casefold()
        report_id = lineage_row.get("report_id")
        report_revision = lineage_row.get("report_revision")
        report_checksum = lineage_row.get("report_checksum")
        has_canonical_identity = (
            isinstance(report_id, str)
            and bool(report_id)
            and isinstance(report_revision, int)
            and not isinstance(report_revision, bool)
            and isinstance(report_checksum, str)
            and bool(report_checksum)
        )
        if gate4_status in {"completed", "approved"} and has_canonical_identity:
            stages["gate4"] = {"status": "completed", "ui_state": "ok", "ui_status": "HITL пройден"}
        elif stages.get("report") is not None:
            stages["gate4"] = {"status": "approval_required", "ui_state": "hitl", "ui_status": "Ожидает решения"}

    _append_output_stages(stages, lineage=lineage_row, report_rows=report_rows)
    return stages


def _summarize_stage_rows(
    rows: Sequence[Mapping[str, AdminScalar]],
) -> Mapping[str, AdminScalar]:
    states = [
        _workflow_node_state("", str(row.get("status", "waiting")), row)
        for row in rows
    ]
    state = next(
        (candidate for candidate in _ADMIN_STATE_PRIORITY if candidate in states),
        "waiting",
    )
    selected_index = states.index(state) if state in states else len(rows) - 1
    selected = rows[selected_index]
    latencies = [
        value
        for row in rows
        if isinstance((value := row.get("latency_ms")), int | float)
        and not isinstance(value, bool)
        and value >= 0
    ]
    retry_counts = [
        value
        for row in rows
        if isinstance((value := row.get("retry_count")), int | float)
        and not isinstance(value, bool)
        and value > 0
    ]
    return _drop_none(
        {
            "status": selected.get("status"),
            "ui_state": state,
            "latency_ms": sum(latencies) if latencies else None,
            "retry_count": int(sum(retry_counts)) if retry_counts else 0,
            "error_code": selected.get("error_code"),
            "fallback_used": selected.get("fallback_used"),
            "observed_count": len(rows),
            "successful_count": sum(item in {"ok", "retry"} for item in states),
        }
    )


def _append_output_stages(
    stages: dict[str, Mapping[str, AdminScalar]],
    *,
    lineage: Mapping[str, AdminScalar],
    report_rows: Sequence[Mapping[str, AdminScalar]],
) -> None:
    report_id = lineage.get("report_id")
    revision = lineage.get("report_revision")
    checksum = lineage.get("report_checksum")
    gate4_state = _state_from_stage_row(stages.get("gate4"), "waiting")
    if isinstance(report_id, str) and report_id and isinstance(checksum, str) and checksum:
        revision_label = f" v{revision}" if isinstance(revision, int) and not isinstance(revision, bool) else ""
        snapshot_state = "ok" if gate4_state == "ok" else "partial"
        stages["snapshot"] = {
            "status": "completed" if snapshot_state == "ok" else "partial",
            "ui_state": snapshot_state,
            "ui_status": "Одобрен" if snapshot_state == "ok" else "Черновик",
            "label": f"Snapshot{revision_label}",
        }
        if snapshot_state == "ok":
            for stage in ("json", "html", "pdf"):
                stages[stage] = {
                    "status": "linked",
                    "ui_state": "ok",
                    "label": f"{stage.upper()} linked",
                }
    for report_row in report_rows:
        report_format = report_row.get("report_format")
        if not isinstance(report_format, str):
            continue
        stage = report_format.casefold()
        if stage not in {"json", "html", "pdf"}:
            continue
        state = _workflow_node_state("", str(report_row.get("status", "waiting")), report_row)
        label = f"{stage.upper()} linked" if state == "ok" else stage.upper()
        stages[stage] = {**report_row, "ui_state": state, "label": label}


def _normalize_workflow_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _workflow_stage_label(
    stage_rows: Mapping[str, Mapping[str, AdminScalar]],
    stage: str,
    default: str,
) -> str:
    row = stage_rows.get(stage)
    label = row.get("label") if row is not None else None
    return str(label) if isinstance(label, str) and label else default


def _state_from_stage_row(
    row: Mapping[str, AdminScalar] | None,
    default_status: str,
) -> str:
    if row is None:
        return _workflow_node_state("", default_status, None)
    ui_state = row.get("ui_state")
    if isinstance(ui_state, str) and ui_state in _ADMIN_STATE_PRIORITY:
        return ui_state
    return _workflow_node_state("", str(row.get("status", default_status)), row)


def _workflow_link_state(
    source: Mapping[str, AdminScalar] | None,
    target: Mapping[str, AdminScalar] | None,
    default_status: str,
) -> str:
    source_state = _state_from_stage_row(source, default_status)
    target_state = _state_from_stage_row(target, default_status)
    if source_state in {"waiting", "skipped"}:
        return source_state
    return target_state


def _workflow_state_icon(state: str) -> str:
    return {
        "ok": "circle-check",
        "active": "loader-circle",
        "error": "circle-x",
        "hitl": "circle-pause",
        "retry": "rotate-ccw",
        "blocked": "circle-pause",
        "partial": "circle-minus",
        "skipped": "circle-minus",
        "waiting": "circle-dashed",
    }.get(state, "circle-dashed")


def _stage_status_label(
    stage: str,
    state: str,
    row: Mapping[str, AdminScalar] | None,
    status: str,
) -> str:
    del stage
    if row is not None:
        ui_status = row.get("ui_status")
        if isinstance(ui_status, str) and ui_status:
            return ui_status
    if state == "ok":
        count = row.get("observed_count") if row is not None else None
        return f"Успешно · {count} узл." if isinstance(count, int) and count > 1 else "Успешно"
    if state == "active":
        return "Выполняется"
    if state == "error":
        return "Ошибка"
    if state == "hitl":
        return "Ожидает решения"
    if state == "retry":
        retry_count = row.get("retry_count") if row is not None else None
        return f"Повтор {int(retry_count)}" if isinstance(retry_count, int | float) and retry_count > 0 else "Повтор"
    if state == "blocked":
        return "Заблокирован"
    if state == "partial":
        return "Частично / fallback" if row is not None and row.get("fallback_used") else "Частично"
    if state == "skipped":
        return "Пропущено"
    return _human_status(status)


def _node_meta(
    row: Mapping[str, AdminScalar] | None,
    duration: str,
) -> tuple[str, str]:
    if row is None:
        return duration, duration
    for key in ("error_code", "fallback_used"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return _compact_admin_label(value, max_chars=20), value
    return duration, duration


def _node_duration(row: Mapping[str, AdminScalar] | None) -> str:
    if row is None:
        return "—"
    latency = row.get("latency_ms")
    if isinstance(latency, bool) or not isinstance(latency, int | float):
        return "—"
    return f"{latency / 1000:.1f}s"


def _human_status(status: str) -> str:
    normalized = status.strip().casefold().replace("-", "_").replace(" ", "_")
    if normalized in {"success", "completed", "exported", "approved", "linked"}:
        return "Успешно"
    if normalized in {"failed", "error", "fatal"}:
        return "Ошибка"
    if normalized in {"skipped", "deferred"}:
        return "Пропущено"
    if normalized in {"running", "in_progress", "executing", "processing"}:
        return "Выполняется"
    if normalized in {"approval_required", "review_required", "paused", "interrupted", "hitl"}:
        return "Ожидает решения"
    if normalized in {"blocked", "policy_blocked"}:
        return "Заблокирован"
    if normalized in {"partial", "fallback", "degraded"}:
        return "Частично"
    if normalized in {"retry", "retrying", "retryable_error"}:
        return "Повтор"
    return "Ожидает"


def _workflow_legend_html() -> str:
    entries = (
        ("ok", "Успешно"),
        ("active", "Выполняется"),
        ("error", "Ошибка"),
        ("hitl", "HITL"),
        ("retry", "Повтор"),
        ("skipped", "Пропущено"),
        ("waiting", "Ожидает"),
    )
    items = "".join(
        (
            '<span class="admin-legend-item">'
            f'<span class="admin-legend-mark" data-state="{escape(state)}">'
            f'{_admin_icon_svg(_workflow_state_icon(state))}</span>{escape(label)}</span>'
        )
        for state, label in entries
    )
    return f'<div class="admin-graph-legend" aria-label="Легенда статусов">{items}</div>'


def _admin_trace_panel_html(values: Mapping[str, object], *, status: str = "Ожидает") -> str:
    rows = "".join(_trace_metric_html(key, value) for key, value in values.items())
    return (
        '<aside class="admin-right-rail">'
        '<section class="admin-trace-panel">'
        '<div class="admin-section-head"><h2>Selected trace · Sanitized LangSmith trace</h2>'
        f'<span class="admin-status-pill">{escape(status)}</span></div>'
        f'<div class="admin-trace-metrics">{rows}</div>'
        '<p class="admin-safe-note">Без текста документов, путей, имён файлов, промптов, PII и секретов.</p>'
        '<span class="admin-langsmith-action is-disabled" aria-disabled="true">'
        "LangSmith link недоступен"
        "</span>"
        "</section>"
        '<section class="admin-gate-panel">'
        '<div class="admin-section-head"><h2>Проверки качества</h2>'
        f'<span>Выбранный запуск • {escape(status)}</span></div>'
        f'{_gate_cards_html("Ожидает")}'
        '<p class="admin-safe-note">LangSmith smoke — ожидает безопасное live-доказательство.</p>'
        "</section>"
        "</aside>"
    )


def _trace_metric_html(key: str, value: object) -> str:
    return (
        "<dl>"
        f"<dt>{escape(str(key))}:</dt>"
        f"<dd>{escape(str(value))}</dd>"
        "</dl>"
    )


def _admin_gate_panel_html(status: str) -> str:
    return (
        '<section class="admin-gate-panel">'
        '<div class="admin-section-head"><h2>Проверки качества</h2></div>'
        f'{_gate_cards_html(status)}'
        "</section>"
    )


def _gate_cards_html(status: str) -> str:
    state = _status_card_state(status)
    cards = "".join(
        (
            f'<article class="admin-gate-card" data-state="{escape(state)}">'
            f"<strong>{escape(gate)}</strong><span>{escape(status)}</span>"
            "</article>"
        )
        for gate in _ADMIN_GATE_NAMES
    )
    return f'<div class="admin-gate-row">{cards}</div>'


def _admin_small_panel_html(title: str, rows: Sequence[tuple[str, object]]) -> str:
    body = "".join(
        f"<dt>{escape(label)}:</dt><dd>{escape(str(value))}</dd>" for label, value in rows
    )
    return (
        '<section class="admin-panel">'
        f'<div class="admin-section-head"><h2>{escape(title)}</h2></div>'
        f'<dl class="admin-kv-grid">{body}</dl>'
        "</section>"
    )


def _admin_lineage_panel_html(rows: Sequence[Mapping[str, AdminScalar]]) -> str:
    linked = any(_lineage_status(row) == "Связано" for row in rows)
    status = "Связано" if linked else "Ожидает связь"
    state = "ok" if linked else "waiting"
    lineage_details = _lineage_details(rows)
    snapshot_label = _snapshot_label(rows)
    cards = "".join(
        (
            f'<article class="admin-gate-card" data-format="{escape(_lineage_format_key(format_name))}" '
            f'data-state="{escape(state)}">'
            f"<strong>{escape(format_name)}</strong><span>{escape(status)}</span>"
            "</article>"
        )
        for format_name in (snapshot_label, "JSON", "HTML", "PDF")
    )
    return (
        '<section class="admin-panel">'
        '<div class="admin-section-head"><h2>Report Lineage</h2>'
        "<span>Один кейс • одна одобренная версия</span></div>"
        f'<div class="admin-lineage-flow">{cards}</div>'
        f'<p class="admin-safe-note">{escape(lineage_details)}</p>'
        "</section>"
    )


def _lineage_format_key(label: str) -> str:
    if label.upper() in {"JSON", "HTML", "PDF"}:
        return label.lower()
    return "snapshot"


def _snapshot_label(rows: Sequence[Mapping[str, AdminScalar]]) -> str:
    if not rows:
        return "Snapshot"
    revision = rows[0].get("report_revision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        return "Snapshot"
    return f"Snapshot v{revision}"


def _status_or_waiting(observed: bool) -> str:
    return "Наблюдается" if observed else "Ожидает"


def _format_optional_number(value: object, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "Ожидает"
    if label == "$":
        return f"${value:.4f}"
    if label == "ms":
        return f"{value:.0f}ms"
    return str(value)


def _observed_source_errors(rows: Sequence[Mapping[str, AdminScalar]]) -> str:
    errors = [row.get("error_code") for row in rows if row.get("error_code") is not None]
    return str(len(errors))


def _timeline_value(rows: Sequence[Mapping[str, AdminScalar]], key: str) -> str:
    values = [row.get(key) for row in rows if isinstance(row.get(key), int | float)]
    if not values:
        return "Ожидает"
    return str(sum(cast(Sequence[int | float], values)))


def _timeline_errors(rows: Sequence[Mapping[str, AdminScalar]]) -> str:
    errors = [row for row in rows if row.get("error_code") is not None]
    return str(len(errors))


def _timeline_text(rows: Sequence[Mapping[str, AdminScalar]], key: str) -> str:
    values = [str(row[key]) for row in rows if isinstance(row.get(key), str)]
    if not values:
        return "Ожидает"
    return _compact_admin_label(", ".join(sorted(set(values))[:4]), max_chars=64)


def _workflow_result(rows: Sequence[Mapping[str, AdminScalar]]) -> str:
    state = _workflow_summary_state(rows)
    state_count = sum(
        _workflow_node_state("", str(row.get("status", "waiting")), row) == state
        for row in rows
    )
    if state == "blocked":
        return _russian_count(state_count, "блокировка", "блокировки", "блокировок")
    if state == "error":
        return _russian_count(state_count, "ошибка", "ошибки", "ошибок")
    return {
        "ok": "Сохранено",
        "active": "Выполняется",
        "hitl": "Ожидает решения",
        "retry": "Повторяется",
        "partial": "Частично завершён",
        "skipped": "Есть пропуски",
        "waiting": "Ожидает",
    }[state]


def _last_run_result(rows: Sequence[Mapping[str, AdminScalar]]) -> str:
    state = _workflow_summary_state(rows)
    if state == "ok":
        return "сохранён"
    if state == "partial":
        return "частично завершён"
    return _workflow_result(rows).casefold()


def _russian_count(value: int, one: str, few: str, many: str) -> str:
    absolute = abs(value)
    tail = absolute % 100
    if 11 <= tail <= 14:
        word = many
    elif absolute % 10 == 1:
        word = one
    elif absolute % 10 in {2, 3, 4}:
        word = few
    else:
        word = many
    return f"{value} {word}"


def _workflow_summary_state(rows: Sequence[Mapping[str, AdminScalar]]) -> str:
    states = {
        _workflow_node_state("", str(row.get("status", "waiting")), row)
        for row in rows
    }
    return next(
        (candidate for candidate in _ADMIN_STATE_PRIORITY if candidate in states),
        "waiting",
    )


def _status_card_state(status: str) -> str:
    normalized = status.strip().casefold().replace("-", "_").replace(" ", "_")
    if normalized in {"healthy", "exported", "success", "completed", "linked"}:
        return "ok"
    if normalized in {"running", "in_progress", "exporting"}:
        return "active"
    if normalized in {"disabled", "blocked_missing_credential", "skipped", "deferred"}:
        return "skipped"
    if normalized in {"degraded", "fallback", "partial"}:
        return "partial"
    if normalized in {"failed", "error", "outage", "unavailable"}:
        return "error"
    return "waiting"


def _summary_state_label(state: str) -> str:
    return {
        "ok": "Успешно",
        "active": "Выполняется",
        "error": "Ошибка",
        "hitl": "Ожидает решения",
        "blocked": "Заблокировано",
        "retry": "Повтор",
        "partial": "Частично",
        "skipped": "Пропущено",
        "waiting": "Ожидает",
    }.get(state, "Ожидает")


def _lineage_status(lineage: Mapping[str, AdminScalar]) -> str:
    if lineage.get("report_checksum") is not None or lineage.get("report_id") is not None:
        return "Связано"
    return "Ожидает"


def _lineage_details(rows: Sequence[Mapping[str, AdminScalar]]) -> str:
    if not rows:
        return "Связь артефактов ожидает approved snapshot."
    row = rows[0]
    if _lineage_status(row) != "Связано":
        return "Связь артефактов ожидает approved snapshot."
    details = [
        f"{key}={_compact_admin_label(row[key])}"
        for key in ("report_id", "report_revision", "report_checksum", "report_format")
        if row.get(key) is not None
    ]
    if not details:
        return "Связь артефактов подтверждается локальным аудитом."
    return " • ".join(str(value) for value in details)


def _compact_admin_label(value: object, *, max_chars: int = 48) -> str:
    text = str(value)
    if len(text) <= max_chars:
        return text
    head = max(8, max_chars - 10)
    return f"{text[:head]}…{text[-6:]}"


def _health_value(row: Mapping[str, AdminScalar] | None) -> str:
    if row is None:
        return "Ожидает"
    status = row.get("status")
    if isinstance(status, str) and status:
        return status
    return "Ожидает"


def _langsmith_trace_status(row: Mapping[str, AdminScalar] | None) -> str:
    status = _health_value(row)
    if status in {"healthy", "exported"}:
        return "exported"
    if status == "disabled":
        return "tracing disabled"
    if status == "blocked_missing_credential":
        return "ожидает ключ"
    if status == "degraded":
        return "exporter degraded; local audit сохранён"
    return "ожидает safe live trace"


def _selected_trace_status_label(row: Mapping[str, AdminScalar] | None) -> str:
    return f"selected run: {_langsmith_trace_status(row)}"


def _admin_workflow_mode_label(context: Mapping[str, object]) -> str:
    mode = str(context.get("workflow_mode") or "").strip().lower()
    if mode == "live":
        return "LIVE WORKFLOW"
    if mode == "deterministic_offline":
        return "OFFLINE FIXTURE"
    return "AUDIT VIEW"


def _runtime_langsmith_status_label(context: Mapping[str, object]) -> str:
    status = str(context.get("runtime_langsmith_status") or "unknown").strip().lower()
    return {
        "configured": "configured",
        "disabled": "disabled",
        "blocked_missing_credential": "ожидает ключ",
    }.get(status, "unknown")


def _privacy_denials(rows: Sequence[Mapping[str, AdminScalar]]) -> str:
    denied = [
        row
        for row in rows
        if row.get("decision") == "denied" or row.get("error_code") in {"policy_denied", "budget_denied"}
    ]
    return str(len(denied))


def _safe_event_row(event: AuditEvent) -> AdminRow:
    row: AdminRow = {}
    event_type = _safe_event_type(event.event_type)
    if event_type is not _SKIP:
        row["event_type"] = cast(AdminScalar, event_type)
    span_name = _safe_identifier(event.span_name)
    if span_name is not _SKIP:
        row["span_name"] = cast(AdminScalar, span_name)
    if event.span_name in _SOURCE_SPANS:
        row["source"] = event.span_name
    elif event.span_name == "analysis.module":
        node_name = _sanitize_trace_attribute("node_name", event.attributes.get("node_name"))
        if isinstance(node_name, str):
            row["source"] = node_name
    for key, value in event.attributes.items():
        safe_value = _safe_attribute(event, key, value)
        if safe_value is not _SKIP:
            row[key] = cast(AdminScalar, safe_value)
    return row


_SKIP = object()


def _preferred_numeric(row: Mapping[str, AdminScalar], primary: str, secondary: str) -> float | None:
    primary_value = _numeric_or_none(row.get(primary))
    if primary_value is not None:
        return primary_value
    return _numeric_or_none(row.get(secondary))


def _numeric_or_none(value: AdminScalar) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _is_privacy_row(row: Mapping[str, AdminScalar]) -> bool:
    event_type = row.get("event_type")
    return (
        isinstance(event_type, str)
        and ("disclosure" in event_type or event_type.startswith("privacy"))
    ) or "redaction_policy_version" in row or row.get("error_code") in {
        "policy_denied",
        "budget_denied",
    }


def _is_source_health_row(row: Mapping[str, AdminScalar]) -> bool:
    source = row.get("source")
    if source in _SOURCE_SPANS:
        return True
    return row.get("span_name") == "analysis.module" and source not in _REPORT_SOURCES


def _is_report_integrity_row(row: Mapping[str, AdminScalar]) -> bool:
    return row.get("span_name") == "report.generate" or row.get("source") in _REPORT_SOURCES


def _is_evaluation_row(row: Mapping[str, AdminScalar]) -> bool:
    span_name = row.get("span_name")
    return isinstance(span_name, str) and ("eval" in span_name or "evaluation" in span_name)


def _pick(row: Mapping[str, AdminScalar], keys: Sequence[str]) -> AdminRow:
    return {key: row[key] for key in keys if key in row}


def _count_rows(counts: object) -> list[dict[str, object]]:
    if not isinstance(counts, Mapping):
        return []
    return [{"status": key, "count": value} for key, value in counts.items()]


def _render_rows(rows: object, empty_caption: str) -> None:
    import streamlit as st

    if isinstance(rows, list) and rows:
        st.dataframe(rows, width="stretch")
        return
    st.caption(empty_caption)


def _drop_none(row: Mapping[str, AdminScalar]) -> AdminRow:
    return {key: value for key, value in row.items() if value is not None}


def _safe_attribute(event: AuditEvent, key: str, value: object) -> AdminScalar | object:
    if event.event_type.startswith("startup_disclosure."):
        return _sanitize_startup_disclosure_attribute(key, value)
    if key not in _ADMIN_SAFE_ATTRIBUTE_KEYS:
        return _SKIP
    return _sanitize_trace_attribute(key, value)


def _sanitize_trace_attribute(key: str, value: object) -> AdminScalar | object:
    try:
        return _DISPLAY_SANITIZER.sanitize_attributes({key: value})[key]
    except ValueError:
        return _SKIP


def _sanitize_startup_disclosure_attribute(key: str, value: object) -> AdminScalar | object:
    if key not in _STARTUP_DISCLOSURE_SAFE_ATTRIBUTE_KEYS:
        return _SKIP
    if value is None:
        return None
    if key in _STARTUP_DISCLOSURE_COUNT_KEYS:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return _SKIP
        return value
    if not isinstance(value, str):
        return _SKIP
    if _sanitize_trace_attribute("provider", value) is _SKIP:
        return _SKIP
    if key in {"case_id", "approval_id"}:
        return value if _SAFE_ID_RE.fullmatch(value) else _SKIP
    if key == "content_hash":
        return value if _SAFE_HASH_RE.fullmatch(value) else _SKIP
    if key in {"decision", "reason", "overall_class"}:
        return value if _SAFE_STATUS_RE.fullmatch(value) else _SKIP
    if key in {"redaction_policy_version", "egress_policy_version", "destination"}:
        return value if _SAFE_TOKEN_RE.fullmatch(value) else _SKIP
    return _SKIP


def _safe_event_type(value: str) -> str | object:
    if value.startswith("startup_disclosure.") and value not in _STARTUP_DISCLOSURE_EVENT_TYPES:
        return _SKIP
    return _safe_identifier(value)


def _safe_identifier(value: str) -> str | object:
    if _sanitize_trace_attribute("status", value) is not _SKIP and _SAFE_TOKEN_RE.fullmatch(value):
        return value
    return _SKIP
