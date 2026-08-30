from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


FIXTURE_ROOT = Path("tests/fixtures/startup_founder_frozen_v1")


def test_startup_founder_fixture_bundle_is_deterministic() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["dataset"] == "startup_founder_frozen_v1"
    assert manifest["provider_status"] == "offline_fixture_active"
    assert manifest["network_policy"] == "no_external_network"
    assert manifest["expected_flow"] == [
        "create_case",
        "upload_documents",
        "gate2_preview",
        "gate2_decision",
        "gate3_decision",
        "report_snapshot",
        "gate4_decision",
        "report_pdf",
    ]
    assert manifest["artifacts"]["desktop_screenshot"] == "artifacts/ui/founder-desktop.png"
    assert manifest["artifacts"]["mobile_screenshot"] == "artifacts/ui/founder-mobile.png"

    expected = json.loads((FIXTURE_ROOT / "expected_flow.json").read_text(encoding="utf-8"))
    assert expected["create"]["fixture_mode"] == "deterministic_offline"
    assert expected["create"]["provider_status"] == "deterministic_offline_fixture"
    assert expected["upload"]["accepted_document_ids"] == ["doc-0001", "doc-0002"]
    assert expected["gate2_preview"]["provider_mode"] == "deterministic_offline_fixture"
    assert expected["report"]["freeze_status"] == "required"
    assert expected["gate4"]["freeze_status"] == "approved"
    assert expected["pdf"]["content_type"] == "application/pdf"


def test_refresh_startup_fixture_reproduces_frozen_bundle(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/refresh_startup_fixture.py",
            "--output",
            str(tmp_path / "startup_founder_frozen_v1"),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    for name in ("manifest.json", "expected_flow.json", "documents/founder_pitch.txt"):
        expected = (FIXTURE_ROOT / name).read_bytes()
        actual = (tmp_path / "startup_founder_frozen_v1" / name).read_bytes()
        assert actual == expected, name
