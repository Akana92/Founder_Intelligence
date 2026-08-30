from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import UUID

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.application.services.startup_trace_query_service import (
    StartupTraceQueryService,
)
from due_diligence_agent.ports.tracing import AuditEvent
from due_diligence_agent.presentation.streamlit.components.audit import (
    AdminDashboardContext,
    _render_admin_console_theme,
    build_admin_observability_snapshot,
    build_startup_trace_admin_snapshot,
    render_admin_observability_dashboard,
)


ADMIN_AUDIT_EVENT_LIMIT = 200
ADMIN_AUDIT_FILE_LIMIT = 128
ADMIN_AUDIT_BYTE_LIMIT = 1_048_576
ADMIN_AUDIT_LINE_CHAR_LIMIT = 8192
_ADMIN_SAFE_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ADMIN_SAFE_LABEL_RE = re.compile(r"^[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9 .,&()+_-]{0,79}$")
_ADMIN_UNSAFE_LABEL_RE = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]+|api[_ -]?key|secret|prompt|[A-Za-z]:\\|/users/|\.pdf)"
)


def render_admin_console(
    *,
    container: Any | None = None,
    case_id: str | None = None,
    run_id: str | None = None,
    max_events: int = ADMIN_AUDIT_EVENT_LIMIT,
) -> None:
    import streamlit as st

    _render_admin_console_theme()

    active_container = container or st.session_state.get("app_container")
    if active_container is None:
        from due_diligence_agent.bootstrap.container import build_container
        from due_diligence_agent.config import Settings

        active_container = build_container(Settings(), use_fixture_adapters=True)
        st.session_state["app_container"] = active_container

    events = _read_admin_events(active_container)
    project_names = _admin_startup_project_names(active_container, events)

    selected_case_id = case_id or _safe_admin_query_trace_id(
        st.query_params,
        "caseId",
        "case_id",
        normalize_uuid=True,
    )
    selected_run_id = run_id or _safe_admin_query_trace_id(st.query_params, "runId", "run_id")

    if not selected_case_id or not selected_run_id:
        selected_case_id, selected_run_id = _selected_admin_startup_run(
            events,
            preferred_case_id=selected_case_id,
            preferred_run_id=selected_run_id,
            project_names=project_names,
        )

    if not selected_case_id or not selected_run_id:
        render_admin_observability_dashboard(
            build_admin_observability_snapshot(events),
            build_startup_trace_admin_snapshot(_empty_startup_trace_view()),
            context=_admin_dashboard_context(
                active_container,
                case_id=selected_case_id,
                project_names=project_names,
            ),
        )
        return

    try:
        view = _startup_trace_query_service(active_container, events).get_view(
            selected_case_id,
            selected_run_id,
            max_events=_clamp_admin_event_limit(max_events),
        )
    except ValueError:
        st.error("Startup trace filters are invalid.")
        return
    except Exception as exc:  # pragma: no cover - Streamlit rendering branch
        st.error("Startup trace is unavailable.")
        st.caption(type(exc).__name__)
        return
    render_admin_observability_dashboard(
        build_admin_observability_snapshot(events),
        build_startup_trace_admin_snapshot(view),
        context=_admin_dashboard_context(
            active_container,
            case_id=selected_case_id,
            project_names=project_names,
        ),
    )


def _empty_startup_trace_view() -> Any:
    from due_diligence_agent.application.services.startup_trace_query_service import (
        StartupTraceView,
    )

    return StartupTraceView()


def _startup_trace_query_service(container: Any, events: list[AuditEvent]) -> Any:
    service = getattr(container, "startup_trace_query_service", None)
    if service is not None:
        return service
    return StartupTraceQueryService(_InMemoryAuditSpool(events))


class _InMemoryAuditSpool:
    def __init__(self, events: list[AuditEvent]) -> None:
        self._events = events

    def read_bounded(
        self,
        *,
        max_events: int = 100,
        max_files: int = ADMIN_AUDIT_FILE_LIMIT,
        max_bytes: int = ADMIN_AUDIT_BYTE_LIMIT,
        max_line_chars: int = ADMIN_AUDIT_LINE_CHAR_LIMIT,
        newest_first: bool = False,
    ) -> list[AuditEvent]:
        return self._events[:max_events]


def _clamp_admin_event_limit(requested: int) -> int:
    if requested < 1:
        return 1
    return min(requested, ADMIN_AUDIT_EVENT_LIMIT)


def _selected_admin_startup_run(
    events: list[AuditEvent],
    *,
    preferred_case_id: str | None = None,
    preferred_run_id: str | None = None,
    project_names: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None]:
    import streamlit as st

    options = _admin_startup_run_options(events, project_names=project_names)
    if not options:
        return None, None

    labels = list(options)
    selected_index = _preferred_admin_startup_run_index(
        options,
        preferred_case_id=preferred_case_id,
        preferred_run_id=preferred_run_id,
    )
    selected_label = st.selectbox(
        "Выберите case/run из локального аудита",
        labels,
        index=selected_index,
        label_visibility="collapsed",
        help=(
            "Список построен только из безопасного имени проекта, case_id/run_id, времени и статуса. "
            "Raw PDF, текст документов, пути, имена файлов, промпты, PII и секреты не выводятся."
        ),
    )
    return options.get(str(selected_label), (None, None))


def _admin_startup_run_options(
    events: list[AuditEvent],
    *,
    project_names: Mapping[str, str] | None = None,
) -> dict[str, tuple[str, str]]:
    options: dict[str, tuple[str, str]] = {}
    seen_runs: set[tuple[str, str]] = set()
    for event in events:
        case_id = event.attributes.get("case_id")
        if not isinstance(case_id, str) or not _is_safe_admin_trace_id(case_id):
            continue
        if not _is_safe_admin_trace_id(event.run_id):
            continue
        run_key = (case_id, event.run_id)
        if run_key in seen_runs:
            continue
        seen_runs.add(run_key)
        label = _admin_startup_run_label(
            event,
            case_id,
            project_name=(project_names or {}).get(case_id),
        )
        options[label] = run_key
    return options


def _preferred_admin_startup_run_index(
    options: dict[str, tuple[str, str]],
    *,
    preferred_case_id: str | None = None,
    preferred_run_id: str | None = None,
) -> int:
    if not options:
        return 0
    safe_case_id = preferred_case_id if preferred_case_id and _is_safe_admin_trace_id(preferred_case_id) else None
    safe_run_id = preferred_run_id if preferred_run_id and _is_safe_admin_trace_id(preferred_run_id) else None
    if safe_case_id is None and safe_run_id is None:
        return 0
    for index, (_, (case_id, run_id)) in enumerate(options.items()):
        if safe_case_id and case_id != safe_case_id:
            continue
        if safe_run_id and run_id != safe_run_id:
            continue
        return index
    return 0


def _admin_startup_run_label(
    event: AuditEvent,
    case_id: str,
    *,
    project_name: str | None = None,
) -> str:
    safe_project_name = _safe_admin_project_label(project_name) or "Проект без названия"
    status = _safe_admin_status_label(event.attributes.get("status")) or event.event_type
    safe_status = _safe_admin_status_label(status) or "status_unknown"
    timestamp = _safe_admin_timestamp_label(event.timestamp_utc)
    return (
        f"{safe_project_name} · case {_compact_admin_trace_id(case_id)} ({case_id}) · "
        f"run {_compact_admin_trace_id(event.run_id)} ({event.run_id}) · {timestamp} · {safe_status}"
    )


def _safe_admin_project_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().split())
    if _ADMIN_SAFE_LABEL_RE.fullmatch(normalized) and not _ADMIN_UNSAFE_LABEL_RE.search(normalized):
        return normalized
    return None


def _admin_startup_project_names(
    container: Any,
    events: list[AuditEvent],
) -> dict[str, str]:
    case_ids = _admin_startup_case_ids(events)
    if not case_ids:
        return {}

    names: dict[str, str] = {}
    repository = getattr(container, "startup_profile_repository", None)
    get_current = getattr(repository, "get_current", None)
    if callable(get_current):
        for case_id in case_ids:
            try:
                profile = get_current(UUID(case_id))
            except (KeyError, TypeError, ValueError):
                continue
            project_name = _admin_profile_project_name(profile)
            if project_name is not None:
                names[case_id] = project_name

    unresolved = tuple(case_id for case_id in case_ids if case_id not in names)
    if unresolved:
        names.update(_admin_project_names_from_profile_database(container, unresolved))
    return names


def _admin_startup_case_ids(events: list[AuditEvent]) -> tuple[str, ...]:
    case_ids: list[str] = []
    seen: set[str] = set()
    for event in events:
        case_id = event.attributes.get("case_id")
        if not isinstance(case_id, str) or not _is_safe_admin_trace_id(case_id):
            continue
        if case_id in seen:
            continue
        seen.add(case_id)
        case_ids.append(case_id)
    return tuple(case_ids)


def _admin_profile_project_name(profile: object) -> str | None:
    fields = getattr(profile, "fields", None)
    if not isinstance(fields, Mapping):
        return None
    startup_name = fields.get("startup_name")
    values = getattr(startup_name, "values", None)
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        return None
    for value in values:
        safe_value = _safe_admin_project_label(value)
        if safe_value is not None:
            return safe_value
    return None


def _admin_project_names_from_profile_database(
    container: Any,
    case_ids: tuple[str, ...],
) -> dict[str, str]:
    settings = getattr(container, "settings", None)
    data_dir = getattr(settings, "data_dir", None)
    if not isinstance(data_dir, str | Path):
        return {}
    database_path = Path(data_dir) / "startup-api" / "startup-metadata.sqlite3"
    if not database_path.is_file():
        return {}

    from due_diligence_agent.domain.startup.profile import StartupProfile

    names: dict[str, str] = {}
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
        for case_id in case_ids:
            row = connection.execute(
                """
                SELECT payload FROM startup_profiles
                WHERE case_id = ?
                ORDER BY
                    data_revision DESC,
                    CASE analysis_stage WHEN 'enriched' THEN 0 WHEN 'primary' THEN 1 ELSE 2 END,
                    built_at DESC,
                    id DESC
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            if row is None:
                continue
            try:
                profile = StartupProfile.model_validate_json(str(row[0]))
            except (TypeError, ValueError):
                continue
            project_name = _admin_profile_project_name(profile)
            if project_name is not None:
                names[case_id] = project_name
    except sqlite3.Error:
        return names
    finally:
        if connection is not None:
            connection.close()
    return names


def _admin_dashboard_context(
    container: Any,
    *,
    case_id: str | None,
    project_names: Mapping[str, str],
) -> AdminDashboardContext:
    settings = getattr(container, "settings", None)
    langsmith_enabled = bool(getattr(settings, "langsmith_tracing", False))
    credential_present = bool(
        os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    )
    if not langsmith_enabled:
        runtime_langsmith_status = "disabled"
    elif credential_present:
        runtime_langsmith_status = "configured"
    else:
        runtime_langsmith_status = "blocked_missing_credential"

    fixture_mode = os.environ.get("FOUNDER_CASE_FIXTURE_MODE", "live").strip().lower()
    workflow_mode = "deterministic_offline" if fixture_mode == "deterministic_offline" else "live"
    return {
        "project_name": (
            _safe_admin_project_label(project_names.get(case_id or ""))
            or "Проект без названия"
        ),
        "case_id": case_id or "",
        "workflow_mode": workflow_mode,
        "runtime_langsmith_status": runtime_langsmith_status,
    }


def _safe_admin_status_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", normalized):
        return normalized
    return None


def _safe_admin_timestamp_label(value: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", value):
        return value.replace("T", " ").replace("Z", " UTC")
    return "time_unknown"


def _compact_admin_trace_id(value: str) -> str:
    if len(value) <= 18:
        return value
    return f"{value[:20]}…{value[-6:]}"


def _safe_admin_query_trace_id(
    query_params: Any,
    *names: str,
    normalize_uuid: bool = False,
) -> str | None:
    query_names = names or ("caseId", "case_id")
    for name in query_names:
        try:
            raw_value = query_params.get(name)
        except Exception:
            continue
        value = raw_value[0] if isinstance(raw_value, list | tuple) and raw_value else raw_value
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if not _is_safe_admin_trace_id(candidate):
            continue
        if normalize_uuid:
            try:
                return str(UUID(candidate))
            except ValueError:
                pass
        return candidate
    return None


def _is_safe_admin_trace_id(value: str) -> bool:
    return bool(_ADMIN_SAFE_TRACE_ID_RE.fullmatch(value))


def _read_admin_events(container: Any) -> list[AuditEvent]:
    import streamlit as st

    events: list[AuditEvent] = []
    failures: list[str] = []
    for spool in _admin_audit_spools(container):
        try:
            reader = getattr(spool, "read_bounded", None)
            if not callable(reader):
                raise TypeError("audit_spool.bounded_reader_unavailable")
            batch = reader(
                max_events=ADMIN_AUDIT_EVENT_LIMIT,
                max_files=ADMIN_AUDIT_FILE_LIMIT,
                max_bytes=ADMIN_AUDIT_BYTE_LIMIT,
                max_line_chars=ADMIN_AUDIT_LINE_CHAR_LIMIT,
                newest_first=True,
            )
        except Exception as exc:  # pragma: no cover - Streamlit rendering branch
            failures.append(type(exc).__name__)
            continue
        events.extend(event for event in batch if isinstance(event, AuditEvent))
    if failures:
        st.error("Audit spool is unavailable.")
        st.caption(", ".join(sorted(set(failures))))
    return sorted(events, key=_admin_event_sort_key, reverse=True)[
        :ADMIN_AUDIT_EVENT_LIMIT
    ]


def _admin_audit_spools(container: Any) -> list[Any]:
    spools = [container.audit_spool]
    settings = getattr(container, "settings", None)
    data_dir = getattr(settings, "data_dir", None)
    if not isinstance(data_dir, str | Path):
        return spools

    known_roots = {_spool_root(container.audit_spool)}
    startup_root = Path(data_dir) / "startup-api"
    for root in (
        startup_root / "startup-audit-spool",
        startup_root / "deterministic" / "startup-audit-spool",
    ):
        normalized_root = _normalized_path(root)
        if normalized_root in known_roots:
            continue
        spools.append(JsonlAuditSpool(root))
        known_roots.add(normalized_root)
    return spools


def _spool_root(spool: Any) -> Path | None:
    root = getattr(spool, "root", None)
    return _normalized_path(root) if isinstance(root, str | Path) else None


def _normalized_path(path: str | Path) -> Path:
    return Path(path).resolve()


def _admin_event_sort_key(event: AuditEvent) -> tuple[str, str, str, str]:
    return (
        event.timestamp_utc,
        event.event_id,
        event.run_id,
        event.correlation_id,
    )
