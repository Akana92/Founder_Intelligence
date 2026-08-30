from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf

from due_diligence_agent.evals.sellable_demo_freeze import (
    _privacy_leak_count,
    _read_bounded_privacy_bytes,
)


def test_pdf_privacy_scan_ignores_email_like_bytes_inside_pdf_stream(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "compressed-stream.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Filter /FlateDecode /Length 9 >>\nstream\n"
        b"so@j.aCkR\n"
        b"endstream\nendobj\n%%EOF\n"
    )
    fail_reasons: list[str] = []

    privacy_text = _read_bounded_privacy_bytes(
        pdf_path,
        "sample_pdf",
        fail_reasons,
    )

    assert fail_reasons == []
    assert _privacy_leak_count((privacy_text,)) == 0


def test_pdf_privacy_scan_handles_endstream_without_leading_newline(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "ascii85-stream.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Filter /ASCII85Decode /Length 11 >>\nstream\n"
        b"so@j.aCkR~>endstream\nendobj\n%%EOF\n"
    )
    fail_reasons: list[str] = []

    privacy_text = _read_bounded_privacy_bytes(
        pdf_path,
        "sample_pdf",
        fail_reasons,
    )

    assert fail_reasons == []
    assert _privacy_leak_count((privacy_text,)) == 0


def test_pdf_privacy_scan_ignores_path_like_bytes_inside_pdf_stream(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "path-like-stream.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Filter /FlateDecode /Length 16 >>\nstream\n"
        b"noise-D:/stream\n"
        b"endstream\nendobj\n%%EOF\n"
    )
    fail_reasons: list[str] = []

    privacy_text = _read_bounded_privacy_bytes(
        pdf_path,
        "sample_pdf",
        fail_reasons,
    )

    assert fail_reasons == []
    assert _privacy_leak_count((privacy_text,)) == 0


def test_pdf_privacy_scan_checks_extracted_visible_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "visible-email.pdf"
    open_pdf: Any = getattr(pymupdf, "open")
    document: Any = open_pdf()
    page = document.new_page()
    page.insert_text((72, 72), "founder@example.com")
    document.save(pdf_path)
    document.close()
    fail_reasons: list[str] = []

    privacy_text = _read_bounded_privacy_bytes(
        pdf_path,
        "sample_pdf",
        fail_reasons,
    )

    assert fail_reasons == []
    assert _privacy_leak_count((privacy_text,)) == 1


def test_pdf_privacy_scan_checks_extracted_visible_path(tmp_path: Path) -> None:
    pdf_path = tmp_path / "visible-path.pdf"
    open_pdf: Any = getattr(pymupdf, "open")
    document: Any = open_pdf()
    page = document.new_page()
    page.insert_text((72, 72), "D:/private/report.pdf")
    document.save(pdf_path)
    document.close()
    fail_reasons: list[str] = []

    privacy_text = _read_bounded_privacy_bytes(
        pdf_path,
        "sample_pdf",
        fail_reasons,
    )

    assert fail_reasons == []
    assert _privacy_leak_count((privacy_text,)) == 1


def test_pdf_privacy_scan_fails_closed_when_pdf_parser_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    pdf_path = tmp_path / "parser-failure.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Length 18 >>\nstream\n"
        b"hidden@example.io\n"
        b"endstream\nendobj\n%%EOF\n"
    )

    def raise_parser_error(path: Path) -> None:
        raise RuntimeError(f"cannot parse {path.name}")

    monkeypatch.setattr(pymupdf, "open", raise_parser_error)
    fail_reasons: list[str] = []

    privacy_text = _read_bounded_privacy_bytes(
        pdf_path,
        "sample_pdf",
        fail_reasons,
    )

    assert privacy_text.startswith("%PDF-1.4")
    assert fail_reasons == ["sample_pdf_privacy_parse_failed"]
