from __future__ import annotations

from datetime import UTC
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from due_diligence_agent.adapters.reports.html_renderer import HtmlRenderer
from due_diligence_agent.adapters.reports.pdf_renderer import WeasyPrintBackendError
from due_diligence_agent.application.services.report_service import (
    ReportFreezeRequired,
    ReportRendererUnavailable,
    ReportService,
)
from due_diligence_agent.application.services.startup_report_service import (
    StartupReportFreezeService,
    StartupReportSnapshotBuilder,
)
from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.reports.models import ReportSnapshot
from tests.unit.reporting.test_startup_report_snapshot import AS_OF, _input


def test_gate4_exact_match_newest_rejection_and_stale_revision_block_pdf(
    local_tmp_path: Path,
) -> None:
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(_input())
    approvals = InMemoryApprovalRepository()
    freeze = StartupReportFreezeService(approvals, current_data_revision=lambda _case_id: 1)

    with pytest.raises(ReportFreezeRequired):
        _service(approvals).render_final_pdf(snapshot, local_tmp_path)
    with pytest.raises(ValueError, match="gate_4_snapshot_mismatch"):
        freeze.decide(
            snapshot,
            action="approved",
            snapshot_hash="sha256:" + "0" * 64,
            snapshot_revision=snapshot.data_revision,
        )

    freeze.decide(
        snapshot,
        action="approved",
        snapshot_hash=snapshot.report_hash,
        snapshot_revision=snapshot.data_revision,
    )
    assert freeze.is_approved(snapshot) is True
    assert freeze.latest_exact_decision(snapshot).action == "approved"
    _service(approvals).render_final_pdf(snapshot, local_tmp_path / "approved")

    freeze.decide(
        snapshot,
        action="rejected",
        snapshot_hash=snapshot.report_hash,
        snapshot_revision=snapshot.data_revision,
    )
    assert freeze.is_approved(snapshot) is False
    assert freeze.latest_exact_decision(snapshot).action == "rejected"
    with pytest.raises(ReportFreezeRequired):
        _service(approvals).render_final_pdf(snapshot, local_tmp_path / "rejected")

    stale_revision_service = ReportService(
        html_renderer=HtmlRenderer(),
        pdf_renderer=PdfProbe(),
        fallback_renderer=PdfProbe(),
        approval_repository=approvals,
        current_data_revision=lambda _case_id: 2,
    )
    with pytest.raises(ReportFreezeRequired):
        stale_revision_service.render_final_pdf(snapshot, local_tmp_path / "stale")


def test_renderer_unavailable_is_distinct_from_freeze_failure(local_tmp_path: Path) -> None:
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(_input())
    approvals = InMemoryApprovalRepository([_approval(snapshot, action="approved")])
    service = ReportService(
        html_renderer=HtmlRenderer(),
        pdf_renderer=FailingWeasyPrint(),
        fallback_renderer=FailingFallback(),
        approval_repository=approvals,
        current_data_revision=lambda _case_id: snapshot.data_revision,
    )

    with pytest.raises(ReportRendererUnavailable, match="report_renderer_unavailable"):
        service.render_final_pdf(snapshot, local_tmp_path)


class PdfProbe:
    def render(self, html: str, output_path: Path) -> None:
        output_path.write_bytes(b"%PDF-1.4\n% startup report\n")


class FailingWeasyPrint:
    def render(self, html: str, output_path: Path) -> None:
        raise WeasyPrintBackendError("native weasyprint backend unavailable")


class FailingFallback:
    def render(self, html: str, output_path: Path) -> None:
        raise RuntimeError("fallback renderer unavailable")


class InMemoryApprovalRepository:
    def __init__(self, approvals: list[Approval] | None = None) -> None:
        self.approvals = list(approvals or [])

    def add(self, approval: Approval) -> None:
        self.approvals.append(approval)

    def list_for_case(self, case_id):
        return [approval for approval in self.approvals if approval.case_id == case_id]


def _service(approvals: InMemoryApprovalRepository) -> ReportService:
    return ReportService(
        html_renderer=HtmlRenderer(),
        pdf_renderer=PdfProbe(),
        fallback_renderer=PdfProbe(),
        approval_repository=approvals,
        current_data_revision=lambda _case_id: 1,
    )


def _approval(snapshot: ReportSnapshot, *, action: str, sequence: int = 1) -> Approval:
    return Approval(
        id=uuid5(NAMESPACE_URL, f"startup-report-gate4:{snapshot.id}:{action}:{sequence}"),
        case_id=snapshot.case_id,
        gate="gate_4",
        action=action,
        actor="reviewer",
        decided_at=AS_OF.replace(second=sequence).astimezone(UTC),
        data_revision=snapshot.data_revision,
        subject_id=snapshot.id,
        subject_hash=snapshot.report_hash,
        subject_version=snapshot.version,
    )


@pytest.fixture
def local_tmp_path() -> Path:
    path = Path(".tmp-task2-core-testdirs") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path
