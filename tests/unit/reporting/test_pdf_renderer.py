from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest

from due_diligence_agent.adapters.reports.pdf_renderer import (
    PdfRenderer,
    WeasyPrintBackendError,
)


def test_weasyprint_internal_native_library_failures_become_typed_backend_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = Path(".tmp-task2-core-testdirs") / uuid4().hex
    output_dir.mkdir(parents=True, exist_ok=True)

    class BrokenHTML:
        def __init__(self, *, string: str, base_url: object) -> None:
            assert string
            assert base_url is None

        def write_pdf(self, output_path: str) -> None:
            raise NameError("Document is not defined")

    fake_weasyprint = ModuleType("weasyprint")
    fake_weasyprint.HTML = BrokenHTML
    monkeypatch.setitem(sys.modules, "weasyprint", fake_weasyprint)

    with pytest.raises(WeasyPrintBackendError, match="weasyprint_backend_error"):
        PdfRenderer().render("<html><body>report</body></html>", output_dir / "report.pdf")
