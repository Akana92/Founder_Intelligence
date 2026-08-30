from pathlib import Path
from typing import Protocol


class HtmlRendererPort(Protocol):
    def render(self, context: dict[str, object]) -> str: ...


class PdfRendererPort(Protocol):
    def render(self, html: str, output_path: Path) -> None: ...
