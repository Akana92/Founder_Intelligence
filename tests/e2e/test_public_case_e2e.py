from __future__ import annotations

from pathlib import Path

from due_diligence_agent.bootstrap.container import build_container
from due_diligence_agent.config import Settings


def test_ticker_to_approved_pdf_offline(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", langsmith_tracing=False)
    container = build_container(settings, use_fixture_adapters=True)
    try:
        case = container.case_service.create_public_case("AAPL", as_of="2026-06-30")
        state = container.public_analysis_service.run_with_approvals(case.id, approve_all=True)
        outputs = container.report_service.render_approved(state.report_snapshot_id, tmp_path)

        assert outputs.json.exists() and outputs.html.exists() and outputs.pdf.exists()
        assert state.status == "completed"
    finally:
        container.close()
