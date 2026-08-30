from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_fixture_flow_uses_real_controls_and_downloads(tmp_path: Path) -> None:
    app_file = tmp_path / "task15_streamlit_app.py"
    data_dir = tmp_path / "streamlit-data"
    app_file.write_text(
        "\n".join(
            [
                "import os",
                f"os.environ['DDA_DATA_DIR'] = r'{data_dir}'",
                "os.environ['OPENAI_API_KEY'] = ''",
                "os.environ['LANGSMITH_TRACING'] = 'false'",
                "os.environ['DDA_LANGSMITH_TRACING'] = 'false'",
                "from due_diligence_agent.presentation.streamlit.pages.public_case import render_public_case",
                "render_public_case()",
            ]
        ),
        encoding="utf-8",
    )
    app = AppTest.from_file(str(app_file), default_timeout=30).run()

    manifest = json.loads(
        Path("tests/fixtures/public_us_frozen_v1/manifest.json").read_text(encoding="utf-8")
    )
    assert app.date_input[0].value.isoformat() == manifest["as_of"]
    assert app.date_input[0].disabled is True
    app.text_input[0].set_value("AAPL")
    app = _click_button(app, "Create Case")

    state = app.session_state["public_case_state"]
    assert state["status"] == "awaiting_scope_approval"
    app = _click_button(app, "Approve Scope")
    assert app.session_state["public_case_state"]["status"] in {
        "analysis_ready",
        "awaiting_review",
        "awaiting_report_freeze",
        "blocked",
    }

    if app.session_state["public_case_state"].get("contradiction_ids"):
        app = _click_button(app, "Resolve Gate 3")
    if app.session_state["public_case_state"]["status"] != "awaiting_report_freeze":
        app = _click_button(app, "Prepare Report Freeze")
    assert app.session_state["public_case_state"]["status"] == "awaiting_report_freeze"

    app = _click_button(app, "Approve Gate 4")
    final_state = app.session_state["public_case_state"]
    assert final_state["status"] == "completed"
    assert final_state["report_snapshot_id"]

    app = app.run()
    assert app.session_state["public_case_state"]["status"] == "completed"
    assert {button.label for button in app.download_button} >= {
        "Approved JSON",
        "Approved HTML",
        "Approved PDF",
    }
    rendered_tables = "\n".join(frame.value.to_string().lower() for frame in app.dataframe)
    assert "missing data" in rendered_tables
    assert "unsupported model inference" in rendered_tables


def _click_button(app: AppTest, label: str) -> AppTest:
    for button in app.button:
        if button.label == label:
            return button.click().run()
    available = [button.label for button in app.button]
    raise AssertionError(f"Button {label!r} not found; available buttons: {available!r}")
