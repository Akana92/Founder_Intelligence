from __future__ import annotations

import socket
from pathlib import Path
from typing import Literal

import pytest
from starlette.testclient import TestClient

from due_diligence_agent.application.startup_cases import CanonicalReportSnapshot
from due_diligence_agent.application.startup_cases import StartupCaseCoordinator
from due_diligence_agent.presentation.api.app import create_app
from due_diligence_agent.presentation.api.dependencies import get_startup_case_coordinator
from due_diligence_agent.workflows.startup.runtime import InMemoryStartupWorkflowRuntimeStore


class OfflineFixtureAnalysis:
    def start(self, payload: dict[str, object], *, thread_id: str) -> dict[str, object]:
        assert payload["fixture_mode"] == "deterministic_offline"
        assert payload["execution_mode"] == "deterministic_offline_fixture"
        assert thread_id
        return {
            "status": "approval_required",
            "pending_gate": "startup_disclosure",
            "evidence_fact_ids": ["fixture-fact-arr", "fixture-fact-margin"],
        }

    def resume(self, approval: dict[str, object], *, thread_id: str) -> dict[str, object]:
        assert thread_id
        if approval.get("gate") == "startup_gate3_review":
            return {
                "status": "completed",
                "pending_gate": None,
                "report_snapshot_id": "fixture-snapshot-001",
                "report_snapshot_hash": "sha256:startup-founder-frozen-v1",
                "report_snapshot_revision": 1,
            }
        return {"status": "review_required", "pending_gate": "startup_gate3_review"}


class OfflineFixtureReport:
    def __init__(self) -> None:
        self.decision: str | None = None

    def current_snapshot(self, case_id: str) -> CanonicalReportSnapshot:
        del case_id

        return CanonicalReportSnapshot(
            "fixture-snapshot-001",
            "sha256:startup-founder-frozen-v1",
            1,
        )

    def canonical_json_bytes(self, case_id: str) -> bytes:
        del case_id
        return Path("tests/fixtures/startup_founder_frozen_v1/report_snapshot.json").read_bytes()

    def founder_json_bytes(self, case_id: str) -> bytes:
        del case_id
        return b'{"data_revision":1,"main_sections":[]}'

    def html(self, case_id: str) -> str:
        del case_id
        return "<main data-fixture='startup_founder_frozen_v1'>FounderCo report</main>"

    def pdf(self, case_id: str) -> bytes:
        del case_id
        if self.decision != "approved":
            from due_diligence_agent.application.startup_cases import StartupGateConflict

            raise StartupGateConflict("gate_4_freeze_required")
        return b"%PDF-1.4\n% startup founder frozen v1\n"

    def decide_gate4(
        self,
        case_id: str,
        *,
        decision: Literal["approved", "rejected"],
        snapshot_hash: str,
        snapshot_revision: int,
        reason: str | None = None,
    ) -> CanonicalReportSnapshot:
        del case_id, reason
        if snapshot_hash != "sha256:startup-founder-frozen-v1" or snapshot_revision != 1:
            from due_diligence_agent.application.startup_cases import StartupGateConflict

            raise StartupGateConflict("gate_4_snapshot_mismatch")
        self.decision = decision
        return self.current_snapshot("fixture")

    def freeze_status(self, case_id: str) -> Literal["required", "approved"]:
        del case_id
        return "approved" if self.decision == "approved" else "required"

    def pdf_status(self, case_id: str) -> Literal["freeze_required", "ready"]:
        del case_id
        return "ready" if self.decision == "approved" else "freeze_required"


def test_startup_offline_fixture_api_flow_makes_no_external_socket_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_socket_attempts: list[object] = []

    def block_socket_connect(self: socket.socket, address: object) -> None:
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            original_connect(self, address)
            return
        external_socket_attempts.append(address)
        raise AssertionError(f"unexpected external socket connection: {address!r}")

    original_connect = socket.socket.connect
    monkeypatch.setattr(socket.socket, "connect", block_socket_connect)
    report = OfflineFixtureReport()
    coordinator = StartupCaseCoordinator(
        analysis_service=OfflineFixtureAnalysis(),
        deterministic_analysis_service=OfflineFixtureAnalysis(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        deterministic_report_port=report,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)

    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    case_id = created.json()["case_id"]
    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true", "company_name": "FounderCo"},
        files=[
            ("files", ("founder_pitch.txt", b"ARR 1200000", "text/plain")),
            ("files", ("founder_metrics.txt", b"Gross margin 72", "text/plain")),
        ],
    )
    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    token = preview.json()["resume_token"]
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": token},
    )
    gate3 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate3/decision",
        json={"decision": "continue", "exclusions": []},
    )
    draft = client.get(f"/api/v1/startup/cases/{case_id}/report")
    pdf_before = client.get(f"/api/v1/startup/cases/{case_id}/report/pdf")
    gate4 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={
            "decision": "approved",
            "snapshot_hash": draft.json()["snapshot_hash"],
            "snapshot_revision": draft.json()["snapshot_revision"],
        },
    )
    pdf_after = client.get(f"/api/v1/startup/cases/{case_id}/report/pdf")

    assert created.json()["provider_status"] == "deterministic_offline_fixture"
    assert uploaded.json()["accepted_document_ids"] == ["doc-0001", "doc-0002"]
    assert preview.json()["provider_mode"] == "deterministic_offline_fixture"
    assert gate2.json()["analysis_status"] == "gate3_review_required"
    assert gate3.json()["report_status"] == "ready"
    assert draft.json()["freeze_status"] == "required"
    assert pdf_before.status_code == 409
    assert gate4.json()["gate4_status"] == "completed"
    assert pdf_after.status_code == 200
    assert pdf_after.content.startswith(b"%PDF-1.4")
    assert external_socket_attempts == []
