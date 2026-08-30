from __future__ import annotations

from base64 import b64decode
from collections.abc import Mapping
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

from jinja2 import Environment, FileSystemLoader, select_autoescape


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_CHART_BYTES = 2_000_000


class UnsafeReportTemplateError(ValueError):
    pass


class HtmlRenderer:
    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = template_dir or Path(__file__).with_name("templates")
        self._environment = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        )

    def render(self, context: dict[str, object]) -> str:
        _validate_renderer_owned_charts(context)
        template_name = _template_name(context)
        template = self._environment.get_template(template_name)
        html = template.render(**context)
        _validate_rendered_html(html)
        return html


def _template_name(context: dict[str, object]) -> str:
    requested = context.get("template")
    if requested is None:
        return "public_report.html.j2"
    if requested == "public_report.html.j2":
        return "public_report.html.j2"
    if requested == "startup_report.html.j2":
        return "startup_report.html.j2"
    if requested == "startup_founder_report.html.j2":
        return "startup_founder_report.html.j2"
    raise UnsafeReportTemplateError("report_template_not_allowed")


def _validate_renderer_owned_charts(context: dict[str, object]) -> None:
    sections = context.get("sections", {})
    if not isinstance(sections, Mapping):
        sections = {}
    for section in sections.values():
        _validate_chart_mapping(section)
    startup_charts = context.get("startup_charts", ())
    if not isinstance(startup_charts, (list, tuple)):
        raise UnsafeReportTemplateError("startup_charts_must_be_a_sequence")
    for chart in startup_charts:
        if not isinstance(chart, Mapping) or not chart.get("chart_data_uri"):
            raise UnsafeReportTemplateError("startup_chart_payload_invalid")
        _decode_png_data_uri(str(chart["chart_data_uri"]))


def _validate_chart_mapping(value: object) -> None:
    if isinstance(value, Mapping) and value.get("chart_data_uri"):
        _decode_png_data_uri(str(value["chart_data_uri"]))


def _validate_rendered_html(html: str) -> None:
    parser = _ReportHtmlSafetyParser()
    parser.feed(html)
    parser.close()


class _ReportHtmlSafetyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._in_style = tag.lower() == "style"
        for name, value in attrs:
            attr = name.lower()
            normalized = _normalize_attr(value or "")
            normalized_scheme = normalized.lower()
            if attr == "srcset":
                raise UnsafeReportTemplateError("srcset_forbidden")
            if attr == "style" and _css_loads_url(normalized_scheme):
                raise UnsafeReportTemplateError("css_url_loading_forbidden")
            if attr == "src" and normalized:
                if not normalized_scheme.startswith("data:image/png;base64,"):
                    raise UnsafeReportTemplateError("src_must_be_valid_png_data_uri")
                _decode_png_data_uri(normalized)
            if attr == "href" and normalized and not normalized.startswith("#"):
                raise UnsafeReportTemplateError("href_must_be_internal_fragment")

    def handle_data(self, data: str) -> None:
        if self._in_style and _css_loads_url(_normalize_attr(data).lower()):
            raise UnsafeReportTemplateError("css_url_loading_forbidden")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style":
            self._in_style = False


def _normalize_attr(value: str) -> str:
    normalized = value.strip()
    for _ in range(3):
        decoded = unquote(unescape(normalized)).strip()
        if decoded == normalized:
            break
        normalized = decoded
    return normalized


def _css_loads_url(value: str) -> bool:
    return "\\" in value or "url(" in value or "@import" in value


def _decode_png_data_uri(value: str) -> bytes:
    prefix = "data:image/png;base64,"
    if not value.lower().startswith(prefix):
        raise UnsafeReportTemplateError("only_png_data_uri_charts_allowed")
    try:
        payload = b64decode(value[len(prefix) :], validate=True)
    except ValueError as exc:
        raise UnsafeReportTemplateError("invalid_png_chart_data") from exc
    if not payload.startswith(PNG_SIGNATURE):
        raise UnsafeReportTemplateError("invalid_png_chart_signature")
    if not payload or len(payload) > MAX_CHART_BYTES:
        raise UnsafeReportTemplateError("invalid_png_chart_size")
    return payload
