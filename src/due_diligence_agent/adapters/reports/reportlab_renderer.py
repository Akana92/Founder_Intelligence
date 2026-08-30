from __future__ import annotations

from base64 import b64decode
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any


_FONT_REGULAR = "FounderReportDejaVuSans"
_FONT_BOLD = "FounderReportDejaVuSans-Bold"
_FONT_ITALIC = "FounderReportDejaVuSans-Oblique"
_FONT_BOLD_ITALIC = "FounderReportDejaVuSans-BoldOblique"


def _invariant_canvas(*args: Any, **kwargs: Any) -> Any:
    from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

    kwargs["invariant"] = 1
    return Canvas(*args, **kwargs)


def _table_column_widths(column_count: int, available_width: float) -> list[float]:
    if column_count <= 0:
        return []
    return [available_width / column_count] * column_count


def _register_unicode_fonts() -> None:
    from matplotlib import get_data_path
    from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
    from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]

    fonts_dir = Path(get_data_path()) / "fonts" / "ttf"
    font_files = {
        _FONT_REGULAR: fonts_dir / "DejaVuSans.ttf",
        _FONT_BOLD: fonts_dir / "DejaVuSans-Bold.ttf",
        _FONT_ITALIC: fonts_dir / "DejaVuSans-Oblique.ttf",
        _FONT_BOLD_ITALIC: fonts_dir / "DejaVuSans-BoldOblique.ttf",
    }
    for font_name, font_path in font_files.items():
        try:
            pdfmetrics.getFont(font_name)
        except KeyError:
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    pdfmetrics.registerFontFamily(
        _FONT_REGULAR,
        normal=_FONT_REGULAR,
        bold=_FONT_BOLD,
        italic=_FONT_ITALIC,
        boldItalic=_FONT_BOLD_ITALIC,
    )


def _safe_inline_markup(node: Any) -> str:
    from bs4.element import NavigableString, Tag

    if isinstance(node, NavigableString):
        return escape(str(node))
    if not isinstance(node, Tag):
        return ""

    name = str(node.name).lower()
    if name == "br":
        return "<br/>"

    inner = "".join(_safe_inline_markup(child) for child in node.children)
    if name in {"b", "strong"}:
        return f"<b>{inner}</b>"
    if name in {"em", "i"}:
        return f"<i>{inner}</i>"
    return inner


def _safe_block_markup(node: Any) -> str:
    return "".join(_safe_inline_markup(child) for child in node.children).strip()


class ReportLabRenderer:
    def render(self, html: str, output_path: Path) -> None:
        from bs4 import BeautifulSoup
        from reportlab.lib import colors  # type: ignore[import-untyped]
        from reportlab.lib.pagesizes import LETTER  # type: ignore[import-untyped]
        from reportlab.lib.styles import (  # type: ignore[import-untyped]
            ParagraphStyle,
            getSampleStyleSheet,
        )
        from reportlab.platypus import (  # type: ignore[import-untyped]
            Image,
            ListFlowable,
            ListItem,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        _register_unicode_fonts()
        styles = getSampleStyleSheet()
        styles["Title"].fontName = _FONT_BOLD
        styles["Heading2"].fontName = _FONT_BOLD
        styles["Heading3"].fontName = _FONT_BOLD
        styles["BodyText"].fontName = _FONT_REGULAR
        doc = SimpleDocTemplate(str(output_path), pagesize=LETTER)
        cell_style = ParagraphStyle(
            "ReportCompactCell",
            parent=styles["BodyText"],
            fontName=_FONT_REGULAR,
            fontSize=7,
            leading=8,
            alignment=0,
            wordWrap="CJK",
        )
        soup = BeautifulSoup(html, "html.parser")
        story: list[Any] = []
        title = soup.find("h1")
        if title is not None:
            story.append(Paragraph(_safe_block_markup(title), styles["Title"]))
            story.append(Spacer(1, 12))

        def append_table(table_node: Any) -> None:
            rows = [
                [
                    Paragraph(_safe_block_markup(cell), cell_style)
                    for cell in row.find_all(["td", "th"])
                ]
                for row in table_node.find_all("tr")
            ]
            if rows:
                column_count = max(len(row) for row in rows)
                widths = _table_column_widths(column_count, float(doc.width))
                table = Table(rows, colWidths=widths, repeatRows=0, hAlign="LEFT")
                table.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 3),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 8))

        def append_image(image_node: Any) -> None:
            source = str(image_node.get("src", ""))
            if source.startswith("data:image/png;base64,"):
                payload = b64decode(
                    source.removeprefix("data:image/png;base64,"), validate=True
                )
                story.append(
                    Image(BytesIO(payload), width=360, height=220, kind="proportional")
                )
                story.append(Spacer(1, 8))

        def append_list(list_node: Any) -> None:
            items = [
                ListItem(Paragraph(_safe_block_markup(item), styles["BodyText"]))
                for item in list_node.find_all("li", recursive=False)
                if _safe_block_markup(item)
            ]
            if items:
                story.append(
                    ListFlowable(items, bulletType="bullet", bulletFontName=_FONT_REGULAR)
                )
                story.append(Spacer(1, 6))

        def has_renderable_content(section_node: Any) -> bool:
            for candidate in section_node.find_all(
                ["h3", "h4", "p", "ul", "ol", "table", "img", "summary"]
            ):
                if candidate.name == "img":
                    if str(candidate.get("src", "")).startswith("data:image/png;base64,"):
                        return True
                elif _safe_block_markup(candidate):
                    return True
            return False

        for section in soup.find_all("section"):
            if not has_renderable_content(section):
                continue
            heading = section.find("h2", recursive=False)
            if heading is not None:
                story.append(Paragraph(_safe_block_markup(heading), styles["Heading2"]))
            for node in section.find_all(
                ["h3", "h4", "p", "ul", "ol", "table", "img", "summary"]
            ):
                if node.find_parent("table") is not None and node.name != "table":
                    continue
                if node.name in {"ul", "ol"}:
                    if node.find_parent(["ul", "ol"]) is None:
                        append_list(node)
                    continue
                if node.name == "table":
                    if node.find_parent("table") is None:
                        append_table(node)
                    continue
                if node.name == "img":
                    append_image(node)
                    continue

                text = _safe_block_markup(node)
                if text:
                    style = styles["Heading3"] if node.name in {"h3", "h4"} else styles["BodyText"]
                    story.append(Paragraph(text, style))
                    story.append(Spacer(1, 6))

        doc.build(story, canvasmaker=_invariant_canvas)
