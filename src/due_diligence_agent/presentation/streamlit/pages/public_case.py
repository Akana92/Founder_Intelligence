from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as Date
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from due_diligence_agent.bootstrap.container import (
    AppContainer,
    build_container,
    public_us_frozen_fixture_manifest,
)
from due_diligence_agent.config import Settings
from due_diligence_agent.presentation.streamlit.components.evidence import render_evidence_ledger
from due_diligence_agent.presentation.streamlit.components.metrics import render_metrics
from due_diligence_agent.presentation.streamlit.components.risks import render_risk_matrix

PUBLIC_PAGE_SECTIONS = {
    "new_case",
    "source_inventory",
    "workflow_status",
    "evidence_ledger",
    "metrics",
    "risk_matrix",
    "hitl_inbox",
    "report_preview",
    "approved_download",
}


def render_public_case() -> None:
    import streamlit as st

    container = st.session_state.get("app_container")
    if container is None:
        container = build_container(Settings(), use_fixture_adapters=True)
        st.session_state["app_container"] = container

    st.title("Public Company Due Diligence")
    with st.form("new_public_case"):
        ticker = st.text_input("Ticker", value="AAPL")
        fixture_as_of = public_us_frozen_fixture_as_of()
        as_of = st.date_input(
            "As of",
            value=fixture_as_of,
            disabled=True,
            help="Derived from the public_us_frozen_v1 fixture manifest.",
        )
        fixture = st.checkbox(
            "Use public_us_frozen_v1 fixture",
            value=True,
            disabled=True,
            help="Live mode is unavailable in the Task 14 Streamlit shell.",
        )
        submitted = st.form_submit_button("Create Case")
    if submitted:
        st.session_state["public_case_state"] = create_public_case_state(
            container,
            ticker=ticker,
            as_of=fixture_as_of.isoformat() if fixture else as_of.isoformat(),
            fixture="public_us_frozen_v1" if fixture else None,
        )
    state = st.session_state.get("public_case_state", {})
    st.subheader("Source Inventory")
    st.dataframe(current_case_rows(container), width="stretch")
    st.subheader("Workflow Status")
    st.status(str(state.get("status", "No case started")), expanded=False)
    case_id = state.get("case_id")
    render_evidence_ledger(current_evidence_rows(container, str(case_id)) if case_id else [])
    render_metrics(current_metric_rows(container, str(case_id)) if case_id else [])
    render_risk_matrix(current_risk_rows(container, str(case_id)) if case_id else [])
    st.subheader("Contradictions / HITL Inbox")
    st.dataframe(current_contradiction_rows(container, str(case_id)) if case_id else [])
    if case_id:
        st.subheader("Workflow Classification")
        st.dataframe(public_workflow_badges(container, str(case_id)), width="stretch")
        if state.get("status") == "awaiting_scope_approval" and st.button(
            "Approve Scope", type="primary"
        ):
            st.session_state["public_case_state"] = approve_scope(container, state)
            state = st.session_state["public_case_state"]
        has_contradictions = bool(state.get("contradiction_ids"))
        if (
            state.get("status") in {"awaiting_review", "blocked"}
            and has_contradictions
            and st.button("Resolve Gate 3")
        ):
            st.session_state["public_case_state"] = resolve_gate3(container, state)
            state = st.session_state["public_case_state"]
        if state.get("status") in {
            "analysis_ready",
            "awaiting_review",
            "blocked",
        } and st.button("Prepare Report Freeze"):
            st.session_state["public_case_state"] = prepare_report_freeze(container, state)
            state = st.session_state["public_case_state"]
        if state.get("status") == "awaiting_report_freeze" and st.button(
            "Approve Gate 4", type="primary"
        ):
            st.session_state["public_case_state"] = approve_gate4(container, state)
            state = st.session_state["public_case_state"]
    st.subheader("Report Preview")
    st.json(state)
    downloads = (
        approved_report_downloads(
            container, state, container.settings.data_dir / "streamlit-exports"
        )
        if state.get("status") == "completed"
        else []
    )
    if not downloads:
        st.download_button("Approved Download", data=b"", file_name="report.pdf", disabled=True)
    for item in downloads:
        st.download_button(
            str(item["label"]),
            data=cast(bytes, item["bytes"]),
            file_name=str(item["file_name"]),
            mime=str(item["mime"]),
        )


def create_public_case_state(
    container: AppContainer, *, ticker: str, as_of: str, fixture: str | None
) -> dict[str, Any]:
    if fixture not in {None, "public_us_frozen_v1"}:
        raise ValueError(f"unsupported_fixture:{fixture}")
    if container.fixture_mode and fixture is None:
        raise ValueError("live_mode_unavailable:fixture_container_active")
    if not container.fixture_mode and fixture is not None:
        raise ValueError("fixture_mode_unavailable:live_container_active")
    as_of_datetime = datetime.fromisoformat(f"{as_of}T00:00:00+00:00").astimezone(UTC)
    case = container.case_service.create_public_case(
        ticker=ticker,
        entity_name=ticker.strip().upper(),
        as_of=as_of_datetime,
    )
    return container.public_analysis_service.start(
        ticker=case.entity_identifier,
        case_id=str(case.case_id),
        as_of=as_of_datetime.isoformat(),
    )


def public_us_frozen_fixture_as_of() -> Date:
    manifest = public_us_frozen_fixture_manifest()
    return Date.fromisoformat(str(manifest["as_of"]))


def approve_fixture_workflow(container: AppContainer, state: dict[str, Any]) -> dict[str, Any]:
    case_id = UUID(str(state["case_id"]))
    approved = container.public_analysis_service.run_with_approvals(case_id, approve_all=True)
    return {
        **approved.state,
        "case_id": str(approved.case_id),
        "status": approved.status,
        "report_snapshot_id": str(approved.report_snapshot_id),
    }


def approve_scope(container: AppContainer, state: dict[str, Any]) -> dict[str, Any]:
    return container.public_analysis_service.approve_scope(UUID(str(state["case_id"])))


def resolve_gate3(container: AppContainer, state: dict[str, Any]) -> dict[str, Any]:
    return container.public_analysis_service.resolve_gate3(UUID(str(state["case_id"])))


def prepare_report_freeze(container: AppContainer, state: dict[str, Any]) -> dict[str, Any]:
    prepared = container.public_analysis_service.prepare_report_freeze(UUID(str(state["case_id"])))
    return {**state, **prepared}


def approve_gate4(container: AppContainer, state: dict[str, Any]) -> dict[str, Any]:
    approved = container.public_analysis_service.approve_gate4(
        UUID(str(state["case_id"])),
        snapshot_id=UUID(str(state["report_snapshot_id"])),
    )
    return {
        **approved,
        "case_id": str(state["case_id"]),
        "status": "completed" if approved.get("status") == "approved" else approved.get("status"),
        "report_snapshot_id": str(state["report_snapshot_id"]),
    }


def approved_report_downloads(
    container: AppContainer, state: dict[str, Any], output_dir: Path
) -> list[dict[str, object]]:
    snapshot_id = state.get("report_snapshot_id")
    if state.get("status") != "completed" or snapshot_id is None:
        return []
    rendered = container.report_service.render_approved(UUID(str(snapshot_id)), output_dir)
    paths = (
        ("json", "Approved JSON", rendered.json, "application/json"),
        ("html", "Approved HTML", rendered.html, "text/html"),
        ("pdf", "Approved PDF", rendered.pdf, "application/pdf"),
    )
    return [
        {
            "kind": kind,
            "label": label,
            "file_name": path.name,
            "mime": mime,
            "bytes": path.read_bytes(),
            "path": str(path),
        }
        for kind, label, path, mime in paths
    ]


def public_workflow_badges(container: AppContainer, case_id: str) -> list[dict[str, str]]:
    facts = current_evidence_rows(container, case_id)
    contradictions = current_contradiction_rows(container, case_id)
    findings = current_risk_rows(container, case_id)
    return [
        {"label": "missing data", "state": "distinct", "detail": "MISSING rows are shown"},
        {
            "label": "source error",
            "state": "distinct",
            "detail": "source errors remain separate from contradictions",
        },
        {
            "label": "low-confidence extraction",
            "state": "distinct",
            "detail": f"{len(facts)} extracted facts available for review",
        },
        {
            "label": "real contradiction",
            "state": "distinct",
            "detail": f"{len(contradictions)} contradictions",
        },
        {
            "label": "unsupported model inference",
            "state": "distinct",
            "detail": f"{len(findings)} findings require evidence refs or review",
        },
    ]


def current_case_rows(container: AppContainer) -> list[dict[str, object]]:
    rows = container.repositories.database.fetch_all("SELECT payload FROM cases ORDER BY id")
    return [
        {
            "case_id": payload["case_id"],
            "ticker": payload["entity_identifier"],
            "status": payload["status"],
            "as_of": payload["as_of"],
        }
        for payload in (_loads(str(row["payload"])) for row in rows)
    ]


def current_evidence_rows(container: AppContainer, case_id: str) -> list[dict[str, object]]:
    facts = container.repositories.evidence_repository.list_for_case(
        __import__("uuid").UUID(case_id)
    )
    return [
        {
            "name": fact.name,
            "value": str(fact.value),
            "period": fact.period,
            "unit": fact.unit,
            "locator": fact.locator.kind,
        }
        for fact in facts
    ]


def current_metric_rows(container: AppContainer, case_id: str) -> list[dict[str, object]]:
    calculations = container.repositories.calculation_repository.list_for_case(
        __import__("uuid").UUID(case_id)
    )
    return [
        {
            "metric": item.metric_name,
            "value": str(item.value),
            "period": item.period,
            "unit": item.unit,
        }
        for item in calculations
    ]


def current_risk_rows(container: AppContainer, case_id: str) -> list[dict[str, object]]:
    findings = container.repositories.finding_repository.list_for_case(
        __import__("uuid").UUID(case_id)
    )
    return [
        {
            "category": item.category,
            "severity": item.severity.value,
            "status": item.status.value,
            "claim": item.claim,
        }
        for item in findings
    ]


def current_contradiction_rows(container: AppContainer, case_id: str) -> list[dict[str, object]]:
    contradictions = container.repositories.contradiction_repository.list_for_case(
        __import__("uuid").UUID(case_id)
    )
    return [
        {
            "type": item.conflict_type,
            "severity": item.severity.value,
            "status": item.status.value,
            "explanation": item.explanation,
        }
        for item in contradictions
    ]


def _loads(payload: str) -> dict[str, Any]:
    import json

    return dict(json.loads(payload))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[5]
