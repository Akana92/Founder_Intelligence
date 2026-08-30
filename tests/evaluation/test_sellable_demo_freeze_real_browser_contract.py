from hashlib import sha256
import json
from pathlib import Path

import pytest

from due_diligence_agent.evals import sellable_demo_freeze


def test_browser_evidence_accepts_canonical_desktop_14_state_contract(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "edge-14-state"
    state_root = evidence_root / "desktop-states"
    state_root.mkdir(parents=True)
    order = list(sellable_demo_freeze.EXPECTED_DESKTOP_STATE_ORDER)
    states: list[dict[str, object]] = []
    for index, file_name in enumerate(order, start=1):
        path = state_root / file_name
        _write_png(path, 1440, 1000)
        states.append(
            {
                "file": file_name,
                "index": index,
                "path": file_name,
                "overflow": {
                    "bodyScrollHeight": 1000,
                    "documentScrollHeight": 1000,
                    "tolerancePx": 1,
                    "verticalOverflowPx": 1 if file_name == "07-risks-questions.png" else 0,
                },
                "viewport": {"width": 1440, "height": 1000},
            }
        )
    (state_root / "desktop-state-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "founder_desktop_state_manifest@1",
                "order": order,
                "states": states,
                "viewport": {"width": 1440, "height": 1000},
            }
        ),
        encoding="utf-8",
    )
    browser = {
        "schema_version": "founder_browser_smoke_evidence@1",
        "offline": True,
        "network_external_calls": 0,
        "gate4_status": "approved",
        "screenshots": {
            "desktop_states": {
                "order": order,
                "path": "desktop-states",
                "viewport": {"width": 1440, "height": 1000},
            }
        },
    }
    fail_reasons: list[str] = []

    state_paths = sellable_demo_freeze._validate_browser_evidence(
        browser,
        visual_evidence_mode="desktop_14_state",
        screenshot_dimensions={"desktop": {"width": 1440, "height": 1000}},
        desktop_path=state_root / "04-overview-readiness.png",
        mobile_path=None,
        browser_evidence_path=evidence_root / "browser-evidence.json",
        fail_reasons=fail_reasons,
    )

    assert [path.name for path in state_paths] == order
    assert fail_reasons == []


def test_report_lineage_accepts_real_html_bound_to_canonical_report_id(
    tmp_path: Path,
) -> None:
    case_id = "1e9c11bb-7ac4-4aad-8d74-439521e9523e"
    report_id = "125465b8-0770-50bc-820f-8a216c62c018"
    report_json = tmp_path / "report.json"
    report_html = tmp_path / "report.html"
    report_pdf = tmp_path / "sample-report.pdf"
    report_json.write_text(json.dumps(_report_json(case_id, report_id)), encoding="utf-8")
    report_html.write_text(
        "<!doctype html><html><body>Snapshot " + report_id + "</body></html>",
        encoding="utf-8",
    )
    report_pdf.write_bytes(b"%PDF-1.4\n")
    fail_reasons: list[str] = []

    actual_case_id, lineage = sellable_demo_freeze._report_lineage(
        {
            "case_id": case_id,
            "report_json_path": report_json.name,
            "report_html_path": report_html.name,
            "report_pdf_path": report_pdf.name,
            "admin_trace": _admin_trace(case_id, report_id),
            "report_artifact_hashes": _artifact_hashes(
                json=report_json,
                html=report_html,
                pdf=report_pdf,
            ),
        },
        browser_evidence_path=tmp_path / "browser-evidence.json",
        sample_pdf_path=report_pdf,
        fail_reasons=fail_reasons,
    )

    assert actual_case_id == case_id
    assert lineage == {
        "case_id": case_id,
        "json": report_json.name,
        "html": report_html.name,
        "pdf": report_pdf.name,
    }
    assert fail_reasons == []
    approved = sellable_demo_freeze._approved_report_lineage(
        {
            "case_id": case_id,
            "report_json_path": report_json.name,
            "report_html_path": report_html.name,
            "report_pdf_path": report_pdf.name,
            "admin_trace": _admin_trace(case_id, report_id),
            "report_artifact_hashes": _artifact_hashes(
                json=report_json,
                html=report_html,
                pdf=report_pdf,
            ),
        },
        browser_evidence_path=tmp_path / "browser-evidence.json",
        fail_reasons=fail_reasons,
    )
    assert approved == {
        "report_checksum": "a" * 64,
        "report_html_hash": _hash_file(report_html),
        "report_id": report_id,
        "report_json_hash": _hash_file(report_json),
        "report_pdf_hash": _hash_file(report_pdf),
        "report_revision": "1",
    }


def test_report_lineage_accepts_founder_safe_json_bound_by_report_metadata(
    tmp_path: Path,
) -> None:
    case_id = "1e9c11bb-7ac4-4aad-8d74-439521e9523e"
    report_id = "125465b8-0770-50bc-820f-8a216c62c018"
    report_json = tmp_path / "report.json"
    report_html = tmp_path / "report.html"
    report_pdf = tmp_path / "sample-report.pdf"
    report_json.write_text(
        json.dumps(_founder_safe_report_json(data_revision=3)),
        encoding="utf-8",
    )
    report_html.write_text(
        "<!doctype html><html><body>Founder-safe report</body></html>",
        encoding="utf-8",
    )
    report_pdf.write_bytes(b"%PDF-1.4\n")
    admin_trace = _admin_trace(case_id, report_id, report_revision=3)
    browser = {
        "case_id": case_id,
        "report_json_path": report_json.name,
        "report_html_path": report_html.name,
        "report_pdf_path": report_pdf.name,
        "report_metadata": _report_metadata(
            case_id,
            report_id,
            report_revision=3,
        ),
        "admin_trace": admin_trace,
        "report_artifact_hashes": _artifact_hashes(
            json=report_json,
            html=report_html,
            pdf=report_pdf,
        ),
    }
    fail_reasons: list[str] = []

    actual_case_id, lineage = sellable_demo_freeze._report_lineage(
        browser,
        browser_evidence_path=tmp_path / "browser-evidence.json",
        sample_pdf_path=report_pdf,
        fail_reasons=fail_reasons,
    )
    approved = sellable_demo_freeze._approved_report_lineage(
        browser,
        browser_evidence_path=tmp_path / "browser-evidence.json",
        fail_reasons=fail_reasons,
    )

    assert actual_case_id == case_id
    assert lineage == {
        "case_id": case_id,
        "json": report_json.name,
        "html": report_html.name,
        "pdf": report_pdf.name,
    }
    assert approved == {
        "report_checksum": "a" * 64,
        "report_html_hash": _hash_file(report_html),
        "report_id": report_id,
        "report_json_hash": _hash_file(report_json),
        "report_pdf_hash": _hash_file(report_pdf),
        "report_revision": "3",
    }
    assert fail_reasons == []


def test_approved_report_lineage_rejects_founder_safe_revision_mismatch(
    tmp_path: Path,
) -> None:
    case_id = "1e9c11bb-7ac4-4aad-8d74-439521e9523e"
    report_id = "125465b8-0770-50bc-820f-8a216c62c018"
    report_json = tmp_path / "report.json"
    report_html = tmp_path / "report.html"
    report_pdf = tmp_path / "sample-report.pdf"
    report_json.write_text(
        json.dumps(_founder_safe_report_json(data_revision=3)),
        encoding="utf-8",
    )
    report_html.write_text("<html>Founder-safe report</html>", encoding="utf-8")
    report_pdf.write_bytes(b"%PDF-1.4\n")
    fail_reasons: list[str] = []

    approved = sellable_demo_freeze._approved_report_lineage(
        {
            "case_id": case_id,
            "report_json_path": report_json.name,
            "report_html_path": report_html.name,
            "report_pdf_path": report_pdf.name,
            "report_metadata": _report_metadata(
                case_id,
                report_id,
                report_revision=3,
            ),
            "admin_trace": _admin_trace(case_id, report_id, report_revision=2),
            "report_artifact_hashes": _artifact_hashes(
                json=report_json,
                html=report_html,
                pdf=report_pdf,
            ),
        },
        browser_evidence_path=tmp_path / "browser-evidence.json",
        fail_reasons=fail_reasons,
    )

    assert approved == {}
    assert "report_admin_lineage_mismatch" in fail_reasons


@pytest.mark.parametrize(
    ("admin_report_id", "admin_checksum"),
    (
        ("33333333-3333-4333-8333-333333333333", "a" * 64),
        ("125465b8-0770-50bc-820f-8a216c62c018", "b" * 64),
    ),
)
def test_approved_report_lineage_rejects_founder_safe_snapshot_identity_mismatch(
    tmp_path: Path,
    admin_report_id: str,
    admin_checksum: str,
) -> None:
    case_id = "1e9c11bb-7ac4-4aad-8d74-439521e9523e"
    report_id = "125465b8-0770-50bc-820f-8a216c62c018"
    report_json = tmp_path / "report.json"
    report_html = tmp_path / "report.html"
    report_pdf = tmp_path / "sample-report.pdf"
    report_json.write_text(
        json.dumps(_founder_safe_report_json(data_revision=3)),
        encoding="utf-8",
    )
    report_html.write_text("<html>Founder-safe report</html>", encoding="utf-8")
    report_pdf.write_bytes(b"%PDF-1.4\n")
    admin_trace = _admin_trace(case_id, admin_report_id, report_revision=3)
    admin_trace["report_lineage"]["report_checksum"] = admin_checksum
    fail_reasons: list[str] = []

    approved = sellable_demo_freeze._approved_report_lineage(
        {
            "case_id": case_id,
            "report_json_path": report_json.name,
            "report_html_path": report_html.name,
            "report_pdf_path": report_pdf.name,
            "report_metadata": _report_metadata(
                case_id,
                report_id,
                report_revision=3,
            ),
            "admin_trace": admin_trace,
            "report_artifact_hashes": _artifact_hashes(
                json=report_json,
                html=report_html,
                pdf=report_pdf,
            ),
        },
        browser_evidence_path=tmp_path / "browser-evidence.json",
        fail_reasons=fail_reasons,
    )

    assert approved == {}
    assert "report_admin_lineage_mismatch" in fail_reasons


def test_report_lineage_rejects_html_bound_to_another_report_id(tmp_path: Path) -> None:
    case_id = "1e9c11bb-7ac4-4aad-8d74-439521e9523e"
    report_json = tmp_path / "report.json"
    report_html = tmp_path / "report.html"
    report_pdf = tmp_path / "sample-report.pdf"
    report_id = "125465b8-0770-50bc-820f-8a216c62c018"
    report_json.write_text(json.dumps(_report_json(case_id, report_id)), encoding="utf-8")
    report_html.write_text(
        "<!doctype html><html><body>Snapshot stale-report-id</body></html>",
        encoding="utf-8",
    )
    report_pdf.write_bytes(b"%PDF-1.4\n")
    fail_reasons: list[str] = []

    sellable_demo_freeze._report_lineage(
        {
            "case_id": case_id,
            "report_json_path": report_json.name,
            "report_html_path": report_html.name,
            "report_pdf_path": report_pdf.name,
            "admin_trace": _admin_trace(case_id, report_id),
            "report_artifact_hashes": _artifact_hashes(
                json=report_json,
                html=report_html,
                pdf=report_pdf,
            ),
        },
        sample_pdf_path=report_pdf,
        browser_evidence_path=tmp_path / "browser-evidence.json",
        fail_reasons=fail_reasons,
    )

    assert "report_lineage_case_mismatch" in fail_reasons


def test_report_lineage_rejects_ambiguous_non_uuid_report_id(tmp_path: Path) -> None:
    case_id = "1e9c11bb-7ac4-4aad-8d74-439521e9523e"
    report_json = tmp_path / "report.json"
    report_html = tmp_path / "report.html"
    report_pdf = tmp_path / "sample-report.pdf"
    report_json.write_text(json.dumps(_report_json(case_id, "report")), encoding="utf-8")
    report_html.write_text(
        "<!doctype html><html><body>Canonical report</body></html>",
        encoding="utf-8",
    )
    report_pdf.write_bytes(b"%PDF-1.4\n")
    fail_reasons: list[str] = []

    sellable_demo_freeze._approved_report_lineage(
        {
            "case_id": case_id,
            "report_json_path": report_json.name,
            "report_html_path": report_html.name,
            "report_pdf_path": report_pdf.name,
            "admin_trace": _admin_trace(case_id, "report"),
            "report_artifact_hashes": _artifact_hashes(
                json=report_json,
                html=report_html,
                pdf=report_pdf,
            ),
        },
        browser_evidence_path=tmp_path / "browser-evidence.json",
        fail_reasons=fail_reasons,
    )

    assert "report_admin_lineage_mismatch" in fail_reasons


def test_report_lineage_rejects_report_paths_outside_browser_evidence_root(
    tmp_path: Path,
) -> None:
    case_id = "1e9c11bb-7ac4-4aad-8d74-439521e9523e"
    report_id = "125465b8-0770-50bc-820f-8a216c62c018"
    evidence_root = tmp_path / "evidence"
    outside_root = tmp_path / "outside"
    evidence_root.mkdir()
    outside_root.mkdir()
    outside_json = outside_root / "report.json"
    report_html = evidence_root / "report.html"
    report_pdf = evidence_root / "sample-report.pdf"
    outside_json.write_text(json.dumps(_report_json(case_id, report_id)), encoding="utf-8")
    report_html.write_text("<html>" + report_id + "</html>", encoding="utf-8")
    report_pdf.write_bytes(b"%PDF-1.4\n")
    fail_reasons: list[str] = []

    sellable_demo_freeze._approved_report_lineage(
        {
            "case_id": case_id,
            "report_json_path": "../outside/report.json",
            "report_html_path": report_html.name,
            "report_pdf_path": report_pdf.name,
            "admin_trace": _admin_trace(case_id, report_id),
            "report_artifact_hashes": {
                "json": _hash_file(outside_json),
                "html": _hash_file(report_html),
                "pdf": _hash_file(report_pdf),
            },
        },
        browser_evidence_path=evidence_root / "browser-evidence.json",
        fail_reasons=fail_reasons,
    )

    assert "report_json_path_outside_evidence_dir" in fail_reasons


def test_gate_d_runtime_path_rejects_absolute_path_outside_gate_result_root(
    tmp_path: Path,
) -> None:
    gate_root = tmp_path / "gate-d-a"
    outside_root = tmp_path / "outside"
    gate_root.mkdir()
    outside_root.mkdir()
    runtime_path = outside_root / "runtime-evidence.json"
    runtime_path.write_text("{}", encoding="utf-8")
    fail_reasons: list[str] = []

    resolved = sellable_demo_freeze._gate_d_runtime_path(
        gate_root / "eval-result.json",
        {"artifact_paths": {"runtime_runtime_evidence": str(runtime_path)}},
        "gate_d_first",
        fail_reasons,
    )

    assert resolved is None
    assert fail_reasons == ["gate_d_first_runtime_evidence_path_invalid"]


def test_gate_d_runtime_path_accepts_existing_repo_relative_path_inside_gate_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    gate_root = repo_root / ".local" / "run" / "gate-d-a"
    runtime_path = gate_root / "runtime" / "runtime-evidence.json"
    runtime_path.parent.mkdir(parents=True)
    runtime_path.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(repo_root)
    fail_reasons: list[str] = []

    resolved = sellable_demo_freeze._gate_d_runtime_path(
        gate_root / "eval-result.json",
        {
            "artifact_paths": {
                "runtime_runtime_evidence": runtime_path.relative_to(repo_root).as_posix()
            }
        },
        "gate_d_first",
        fail_reasons,
    )

    assert resolved == runtime_path.resolve()
    assert fail_reasons == []


def test_report_lineage_rejects_pdf_tamper_even_when_replacement_is_valid_pdf(
    tmp_path: Path,
) -> None:
    case_id = "1e9c11bb-7ac4-4aad-8d74-439521e9523e"
    report_id = "125465b8-0770-50bc-820f-8a216c62c018"
    report_json = tmp_path / "report.json"
    report_html = tmp_path / "report.html"
    report_pdf = tmp_path / "sample-report.pdf"
    report_json.write_text(json.dumps(_report_json(case_id, report_id)), encoding="utf-8")
    report_html.write_text("<html>" + report_id + "</html>", encoding="utf-8")
    report_pdf.write_bytes(b"%PDF-1.4\n% canonical\n")
    recorded_hashes = _artifact_hashes(json=report_json, html=report_html, pdf=report_pdf)
    report_pdf.write_bytes(b"%PDF-1.4\n% different valid pdf\n")
    fail_reasons: list[str] = []

    sellable_demo_freeze._approved_report_lineage(
        {
            "case_id": case_id,
            "report_json_path": report_json.name,
            "report_html_path": report_html.name,
            "report_pdf_path": report_pdf.name,
            "admin_trace": _admin_trace(case_id, report_id),
            "report_artifact_hashes": recorded_hashes,
        },
        browser_evidence_path=tmp_path / "browser-evidence.json",
        fail_reasons=fail_reasons,
    )

    assert "report_pdf_hash_mismatch" in fail_reasons


def _admin_trace(
    case_id: str,
    report_id: str,
    *,
    report_revision: int = 1,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "report_lineage": {
            "decision": "approved",
            "gate4_status": "completed",
            "report_checksum": "a" * 64,
            "report_id": report_id,
            "report_revision": report_revision,
        },
    }


def _report_json(case_id: str, report_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "data_revision": 1,
        "id": report_id,
        "report_hash": "sha256:" + "a" * 64,
    }


def _founder_safe_report_json(*, data_revision: int) -> dict[str, object]:
    return {
        "title_ru": "Отчёт для основателя",
        "subtitle_ru": "Краткий разбор проекта",
        "as_of_ru": "Данные на 21.08.2026",
        "data_revision": data_revision,
        "main_sections": [],
        "metric_cards": {},
        "improvement_proposals": [],
        "technical_appendix": {
            "methodology_ru": [],
            "sources_ru": [],
        },
        "analytics": {
            "metric_points": [],
            "market_points": [],
            "readiness_dimensions": [],
        },
    }


def _report_metadata(
    case_id: str,
    report_id: str,
    *,
    report_revision: int,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "snapshot_id": report_id,
        "snapshot_hash": "sha256:" + "a" * 64,
        "snapshot_revision": report_revision,
    }


def _artifact_hashes(*, json: Path, html: Path, pdf: Path) -> dict[str, str]:
    return {
        "json": _hash_file(json),
        "html": _hash_file(html),
        "pdf": _hash_file(pdf),
    }


def _hash_file(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _write_png(path: Path, width: int, height: int) -> None:
    ihdr_payload = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + len(ihdr_payload).to_bytes(4, "big")
        + b"IHDR"
        + ihdr_payload
        + b"\x00\x00\x00\x00"
    )
