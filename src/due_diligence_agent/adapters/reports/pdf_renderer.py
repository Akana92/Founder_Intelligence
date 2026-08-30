from __future__ import annotations

from pathlib import Path


class WeasyPrintBackendError(RuntimeError):
    pass


class PdfRenderer:
    def render(self, html: str, output_path: Path) -> None:
        try:
            from weasyprint import HTML  # type: ignore[import-untyped]

            HTML(string=html, base_url=None).write_pdf(str(output_path))
        except Exception as exc:
            raise WeasyPrintBackendError("weasyprint_backend_error") from exc
