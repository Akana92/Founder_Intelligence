from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import time
from typing import Any, MutableMapping, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pypdf import PdfReader
import pytest

from due_diligence_agent.adapters.reports.html_renderer import (
    HtmlRenderer,
    UnsafeReportTemplateError,
)
from due_diligence_agent.adapters.reports.pdf_renderer import WeasyPrintBackendError
from due_diligence_agent.adapters.reports.reportlab_renderer import ReportLabRenderer
from due_diligence_agent.application.services.report_service import (
    ReportBuilder,
    ReportFreezeRequired,
    ReportService,
    ReportValidationError,
)
from due_diligence_agent.application.services import report_service as report_service_module
from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    CaseStatus,
    ContradictionStatus,
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.reports.models import ReportSnapshot
from due_diligence_agent.ports.rendering import PdfRendererPort


AS_OF = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _uuid(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, value)


CASE_ID = _uuid("case:aapl")
ARTIFACT_ID = _uuid("artifact:10k")
FACT_REVENUE_ID = _uuid("fact:revenue")
CALC_GROWTH_ID = _uuid("calc:growth")
FINDING_ID = _uuid("finding:thesis")
CONTRADICTION_ID = _uuid("contradiction:risk")


def test_report_json_is_canonical_and_contains_required_sections(
    report_service: ReportService,
    approved_public_case: PublicReportCase,
) -> None:
    snapshot = report_service.build_public(approved_public_case)

    assert set(snapshot.sections) >= {
        "metadata",
        "executive_summary",
        "investment_thesis",
        "counter_thesis",
        "company_profile",
        "evidence_coverage",
        "financial_metrics",
        "risk_matrix",
        "contradictions",
        "missing_data",
        "next_steps",
        "methodology",
        "source_and_calculation_appendix",
        "disclaimer",
        "decision_owner",
        "filing_timeline",
        "financial_trends",
        "capital_structure",
        "valuation",
        "sec_risk_factor_changes",
        "corporate_events",
        "news_coverage",
    }
    assert snapshot.reproducibility.dependency_lock_hash.startswith("sha256:")
    assert snapshot.trace_ids == ("trace-public-1",)
    assert snapshot.json_artifact_ref.startswith("sha256:")
    assert snapshot.content_hashes["json"] == snapshot.json_artifact_ref
    assert "raw_source_text" not in snapshot.model_dump(mode="json")
    disclaimer = snapshot.sections["disclaimer"]["summary"]
    assert "not legal, tax, or personal investment advice" in disclaimer
    assert "does not execute or recommend a transaction" in disclaimer
    assert "requires a human decision owner" in disclaimer
    assert "limited by the listed sources, as-of date, and supported jurisdiction" in disclaimer


def test_news_coverage_marks_dropped_polarity_metadata(
    report_service: ReportService,
    approved_public_case: PublicReportCase,
) -> None:
    from due_diligence_agent.domain.artifacts.models import SourceLocator

    news_fact = EvidenceFact(
        id=_uuid("fact:news-missing-polarity"),
        artifact_id=ARTIFACT_ID,
        name="news_signal",
        value="Demand commentary remains constructive for Apple",
        value_type="text",
        unit=None,
        period=None,
        locator=SourceLocator(kind="news_metadata", value="https://example.com/news"),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.75"),
        extraction_method="news_metadata",
        supporting_text_hash="sha256:" + "d" * 64,
        source_freshness_at=AS_OF,
        retrieved_at=AS_OF,
    )

    snapshot = report_service.build_public(
        replace(approved_public_case, facts=(*approved_public_case.facts, news_fact))
    )

    rows = snapshot.sections["news_coverage"]["rows"]
    assert (
        "missing_polarity",
        "Demand commentary remains constructive for Apple",
        str(news_fact.id),
    ) in rows


def test_canonical_report_json_is_full_snapshot_envelope(
    report_service: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    draft = report_service.render_draft(approved_snapshot, tmp_path)

    payload = json.loads(draft.json_path.read_text(encoding="utf-8"))

    assert payload["schema"] == "public_report_snapshot.v1"
    assert payload["integrity_preimage_contract"] == "report_hash excludes artifact hash fields"
    assert payload["id"] == str(approved_snapshot.id)
    assert payload["version"] == approved_snapshot.version
    assert payload["report_hash"] == approved_snapshot.report_hash
    assert payload["source_hashes"] == dict(approved_snapshot.source_hashes)
    assert payload["data_revision"] == approved_snapshot.data_revision
    assert payload["reproducibility"]["dependency_lock_hash"].startswith("sha256:")
    assert payload["sections"]["metadata"]["title"] == "Metadata"
    assert "mappingproxy" not in draft.json_path.read_text(encoding="utf-8")


def test_builder_json_hash_matches_rendered_canonical_json_bytes(
    report_service: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    draft = report_service.render_draft(approved_snapshot, tmp_path)

    assert approved_snapshot.json_artifact_ref == f"sha256:{_sha256_file(draft.json_path)}"
    assert approved_snapshot.content_hashes["json"] == approved_snapshot.json_artifact_ref
    assert draft.snapshot.json_artifact_ref == approved_snapshot.json_artifact_ref


def test_report_identity_changes_when_source_revision_or_manifest_inputs_change(
    report_service: ReportService,
    approved_public_case: PublicReportCase,
) -> None:
    baseline = report_service.build_public(approved_public_case)
    changed_source = report_service.build_public(
        approved_public_case.with_source_hashes({"10-k": "sha256:" + "d" * 64})
    )
    changed_revision = report_service.build_public(approved_public_case.with_data_revision(2))

    assert changed_source.id != baseline.id
    assert changed_source.report_hash != baseline.report_hash
    assert changed_revision.id != baseline.id
    assert changed_revision.report_hash != baseline.report_hash


def test_public_report_json_and_static_chart_are_deterministic(
    report_service: ReportService,
    approved_public_case: PublicReportCase,
) -> None:
    first = report_service.build_public(approved_public_case)
    second = report_service.build_public(approved_public_case)

    assert second.id == first.id
    assert second.report_hash == first.report_hash
    assert (
        second.sections["financial_trends"]["chart_data_uri"]
        == first.sections["financial_trends"]["chart_data_uri"]
    )


def test_unresolved_critical_contradictions_are_forced_into_executive_summary(
    report_service: ReportService,
    approved_public_case: PublicReportCase,
) -> None:
    critical_case = approved_public_case.with_contradictions(
        (_contradiction(severity=FindingSeverity.CRITICAL),)
    )

    snapshot = report_service.build_public(critical_case)

    executive_summary = snapshot.sections["executive_summary"]
    assert "Management notes demand uncertainty despite revenue growth." in str(executive_summary)


def test_report_snapshot_sections_are_deeply_immutable(
    report_service: ReportService,
    approved_public_case: PublicReportCase,
) -> None:
    snapshot = report_service.build_public(approved_public_case)

    with pytest.raises(TypeError):
        snapshot.sections["metadata"]["title"] = "mutated"
    with pytest.raises(TypeError):
        snapshot.sections["metadata"]["rows"][0][1] = "mutated"


def test_render_results_revalidate_snapshot_immutability(
    report_service_with_approval: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    draft = report_service_with_approval.render_draft(approved_snapshot, tmp_path / "draft")
    pdf = report_service_with_approval.render_final_pdf(draft.snapshot, tmp_path / "pdf")

    with pytest.raises(TypeError):
        draft.snapshot.sections["metadata"]["title"] = "mutated"
    with pytest.raises(TypeError):
        cast(MutableMapping[str, str], pdf.snapshot.content_hashes)["pdf"] = "sha256:mutated"


def test_draft_artifacts_are_server_owned_and_hash_bound(
    report_service: ReportService,
    approved_public_case: PublicReportCase,
    tmp_path: Path,
) -> None:
    snapshot = report_service.build_public(approved_public_case)

    draft = report_service.render_draft(snapshot, tmp_path)

    assert draft.snapshot.id == snapshot.id
    assert draft.json_path.read_text(encoding="utf-8").startswith("{")
    assert draft.html_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert draft.snapshot.content_hashes["json"] == f"sha256:{_sha256_file(draft.json_path)}"
    assert draft.snapshot.content_hashes["html"] == f"sha256:{_sha256_file(draft.html_path)}"
    assert "http://" not in draft.html_path.read_text(encoding="utf-8")
    assert "https://" not in draft.html_path.read_text(encoding="utf-8")


def test_draft_rerender_preserves_exact_json_and_html_hashes(
    report_service: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    first = report_service.render_draft(approved_snapshot, tmp_path / "first")
    second = report_service.render_draft(approved_snapshot, tmp_path / "second")

    assert second.json_path.read_bytes() == first.json_path.read_bytes()
    assert second.html_path.read_bytes() == first.html_path.read_bytes()
    assert second.snapshot.content_hashes == first.snapshot.content_hashes


def test_draft_publish_rolls_back_if_second_final_replace_fails(
    monkeypatch: pytest.MonkeyPatch,
    report_service: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "draft"
    first = report_service.render_draft(approved_snapshot, output_dir)
    original_html = first.html_path.read_bytes()
    original_json = first.json_path.read_bytes()
    service_os = cast(Any, report_service_module).os
    real_replace = service_os.replace
    failed_once = False

    def fail_second_replace(source: object, destination: object) -> None:
        nonlocal failed_once
        if Path(cast(str, destination)) == first.json_path and not failed_once:
            failed_once = True
            raise OSError("forced second publish failure")
        real_replace(source, destination)

    monkeypatch.setattr(service_os, "replace", fail_second_replace)
    sections = json.loads(json.dumps(approved_snapshot.model_dump(mode="json")["sections"]))
    sections["metadata"]["summary"] = "Changed staged draft should never be half-published."
    changed_snapshot = ReportSnapshot.model_validate(
        approved_snapshot.model_dump(mode="json") | {"sections": sections}
    )

    with pytest.raises(OSError, match="forced second publish failure"):
        report_service.render_draft(changed_snapshot, output_dir)

    assert first.html_path.read_bytes() == original_html
    assert first.json_path.read_bytes() == original_json
    assert not list(output_dir.glob("*.tmp"))
    assert not list(output_dir.glob("*.bak"))


def test_external_url_loading_in_report_html_is_rejected(
    report_service: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    sections = dict(approved_snapshot.sections)
    financial_trends = dict(sections["financial_trends"])
    financial_trends["chart_data_uri"] = "https://example.invalid/chart.png"
    sections["financial_trends"] = financial_trends
    unsafe_snapshot = approved_snapshot.model_copy(update={"sections": sections})

    with pytest.raises(UnsafeReportTemplateError):
        report_service.render_draft(unsafe_snapshot, tmp_path)


@pytest.mark.parametrize(
    "chart_uri",
    [
        "data:image/svg+xml;base64,PHN2Zy8+",
        "data:text/html;base64,PGgxPmJvb208L2gxPg==",
        "javascript:alert(1)",
        "file:///tmp/chart.png",
        "//example.invalid/chart.png",
        "chart.png",
        "/static/chart.png",
        "ftp://example.invalid/chart.png",
        "cid:chart-1",
        "blob:https://example.invalid/chart",
        "data:image/png;base64,not-valid-base64",
        "javascript%3Aalert(1)",
    ],
)
def test_only_valid_renderer_owned_png_data_uris_are_allowed(
    report_service: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
    chart_uri: str,
) -> None:
    sections = dict(approved_snapshot.sections)
    financial_trends = dict(sections["financial_trends"])
    financial_trends["chart_data_uri"] = chart_uri
    sections["financial_trends"] = financial_trends
    unsafe_snapshot = approved_snapshot.model_copy(update={"sections": sections})

    with pytest.raises(UnsafeReportTemplateError):
        report_service.render_draft(unsafe_snapshot, tmp_path)


@pytest.mark.parametrize(
    "href",
    ["https://example.invalid", "relative/page", "/absolute/path", "mailto:a@example.invalid"],
)
def test_report_html_hrefs_must_be_internal_fragments(tmp_path: Path, href: str) -> None:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "public_report.html.j2").write_text(
        '<!doctype html><html><body><a href="{{ href }}">link</a></body></html>',
        encoding="utf-8",
    )

    with pytest.raises(UnsafeReportTemplateError):
        HtmlRenderer(template_dir).render({"href": href})


def test_report_html_allows_internal_fragment_href(tmp_path: Path) -> None:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "public_report.html.j2").write_text(
        '<!doctype html><html><body><a href="#appendix">appendix</a></body></html>',
        encoding="utf-8",
    )

    assert "#appendix" in HtmlRenderer(template_dir).render({})


@pytest.mark.parametrize(
    "css",
    [
        r"background:u\72l(https://example.invalid/chart.png)",
        r"@imp\6frt url(https://example.invalid/chart.css)",
        "background:u&#x5c;72l(https://example.invalid/chart.png)",
        "@imp&#x5c;6frt url(https://example.invalid/chart.css)",
    ],
)
def test_report_html_rejects_escaped_css_resource_loads_in_style_attribute(
    tmp_path: Path, css: str
) -> None:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "public_report.html.j2").write_text(
        f'<!doctype html><html><body><section style="{css}">x</section></body></html>',
        encoding="utf-8",
    )

    with pytest.raises(UnsafeReportTemplateError):
        HtmlRenderer(template_dir).render({})


@pytest.mark.parametrize(
    "css",
    [
        r"body { background:u\72l(https://example.invalid/chart.png); }",
        r"@imp\6frt url(https://example.invalid/chart.css);",
        "body { background:u&#x5c;72l(https://example.invalid/chart.png); }",
        "@imp&#x5c;6frt url(https://example.invalid/chart.css);",
    ],
)
def test_report_html_rejects_escaped_css_resource_loads_in_style_block(
    tmp_path: Path, css: str
) -> None:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "public_report.html.j2").write_text(
        f"<!doctype html><html><head><style>{css}</style></head><body>x</body></html>",
        encoding="utf-8",
    )

    with pytest.raises(UnsafeReportTemplateError):
        HtmlRenderer(template_dir).render({})


def test_final_pdf_requires_freeze_approval(
    report_service: ReportService,
    draft_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    with pytest.raises(ReportFreezeRequired):
        report_service.render_final_pdf(draft_snapshot, tmp_path)


def test_forged_freeze_metadata_does_not_authorize_final_pdf(
    report_service: ReportService,
    draft_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    sections = dict(draft_snapshot.sections)
    metadata = dict(sections["metadata"])
    metadata["rows"] = (("freeze_approved", "true"),)
    sections["metadata"] = metadata
    forged = ReportSnapshot.model_validate(
        draft_snapshot.model_dump(mode="json") | {"sections": sections}
    )

    with pytest.raises(ReportFreezeRequired):
        report_service.render_final_pdf(forged, tmp_path)


def test_gate4_approval_must_match_snapshot_hash_and_current_revision(
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    repository = InMemoryApprovalRepository(
        [
            _gate4_approval(
                approved_snapshot,
                action="approved",
                subject_id=_uuid("other:snapshot"),
                subject_hash=approved_snapshot.report_hash,
            ),
            _gate4_approval(
                approved_snapshot,
                action="approved",
                subject_id=approved_snapshot.id,
                subject_hash="sha256:" + "e" * 64,
            ),
            _gate4_approval(
                approved_snapshot,
                action="approved",
                subject_id=approved_snapshot.id,
                subject_hash=approved_snapshot.report_hash,
                data_revision=0,
            ),
        ]
    )
    service = _service_with_approvals(repository, current_revision=approved_snapshot.data_revision)

    with pytest.raises(ReportFreezeRequired):
        service.render_final_pdf(approved_snapshot, tmp_path)


def test_latest_gate4_decision_wins_and_later_rejection_blocks_pdf(
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    repository = InMemoryApprovalRepository(
        [
            _gate4_approval(approved_snapshot, action="approved", sequence=1),
            _gate4_approval(approved_snapshot, action="rejected", sequence=2),
        ]
    )
    service = _service_with_approvals(repository, current_revision=approved_snapshot.data_revision)

    with pytest.raises(ReportFreezeRequired):
        service.render_final_pdf(approved_snapshot, tmp_path)


def test_reportlab_fallback_preserves_snapshot_identity(
    report_service_with_failing_weasyprint: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    result = report_service_with_failing_weasyprint.render_final_pdf(approved_snapshot, tmp_path)

    assert result.pdf_path.read_bytes().startswith(b"%PDF")
    assert result.snapshot_id == approved_snapshot.id
    assert result.snapshot.content_hashes["pdf"] == f"sha256:{_sha256_file(result.pdf_path)}"
    assert result.fallback_used == "reportlab"
    assert result.primary_error == "weasyprint_backend_error"


def test_reportlab_fallback_pdf_preserves_required_sections_and_disclaimer(
    report_service_with_failing_weasyprint: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    result = report_service_with_failing_weasyprint.render_final_pdf(approved_snapshot, tmp_path)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(result.pdf_path).pages)

    assert "Executive Summary" in text
    assert "Source and Calculation Appendix" in text
    assert "Mandatory Disclaimer" in text
    assert "This report is analytical support only" in text
    assert "Revenue growth supports the investment thesis." in text


def test_reportlab_fallback_pdf_embeds_unicode_font_for_cyrillic(tmp_path: Path) -> None:
    html = """
    <!doctype html>
    <html>
      <body>
        <h1>Отчёт о готовности стартапа</h1>
        <section>
          <h2>Главный <strong>вывод</strong></h2>
          <p>Система проверяет <strong>рынок</strong> и <em>метрики</em> после согласия основателя.</p>
          <ul>
            <li>Нужно подтвердить <strong>сегмент</strong> и <em>готовность платить</em>.</li>
          </ul>
          <table>
            <tr><th>Показатель</th><th>Значение</th></tr>
            <tr><td>Ежемесячная <em>выручка</em></td><td><strong>1850000 KZT</strong></td></tr>
          </table>
        </section>
      </body>
    </html>
    """
    pdf_path = tmp_path / "fallback-cyrillic.pdf"

    ReportLabRenderer().render(html, pdf_path)

    text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
    pdf_bytes = pdf_path.read_bytes()

    assert "Отчёт о готовности стартапа" in text
    assert "Главный вывод" in text
    assert "Система проверяет рынок и метрики после согласия основателя." in text
    assert "Нужно подтвердить сегмент и готовность платить." in text
    assert "Ежемесячная выручка" in text
    assert "■" not in text
    assert "�" not in text
    assert b"/FontFile2" in pdf_bytes
    assert b"/ToUnicode" in pdf_bytes
    assert b"DejaVuSans-Bold" in pdf_bytes
    assert b"DejaVuSans-Oblique" in pdf_bytes


def test_reportlab_fallback_pdf_is_byte_stable_for_cached_rebuilds(tmp_path: Path) -> None:
    html = """
    <!doctype html>
    <html><body><h1>Кешированный отчёт</h1><section><h2>Рынок</h2>
    <p>Kazent: публичный ориентир, не факт компании.</p></section></body></html>
    """
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"

    ReportLabRenderer().render(html, first)
    time.sleep(1.05)
    ReportLabRenderer().render(html, second)

    assert first.read_bytes() == second.read_bytes()


def test_reportlab_fallback_pdf_preserves_nested_report_content_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reportlab.platypus import Image as RealImage  # type: ignore[import-untyped]

    captured_images: list[Any] = []

    class CapturingImage(RealImage):  # type: ignore[misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured_images.append((args, kwargs))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("reportlab.platypus.Image", CapturingImage)
    png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMC"
        "AO+/p9sAAAAASUVORK5CYII="
    )
    html = f"""
    <!doctype html>
    <html>
      <body>
        <h1>Отчёт Smart University</h1>
        <section>
          <h2>План улучшений</h2>
          <article class="proposal">
            <h3>Сузить ICP</h3>
            <p><strong>Рекомендация:</strong> проверить цикл сделки.</p>
            <p><em>Обоснование:</em> рынок требует доказательства повторяемой боли.</p>
            <p>Эффект: меньше распыления команды.</p>
            <img src="data:image/png;base64,{png}" alt="chart">
          </article>
          <details>
            <summary>Методология и источники</summary>
            <p>Публичный benchmark остаётся публичным ориентиром, не фактом компании.</p>
          </details>
        </section>
        <section>
          <h2>Пустой технический раздел</h2>
        </section>
      </body>
    </html>
    """
    pdf_path = tmp_path / "nested-report.pdf"

    ReportLabRenderer().render(html, pdf_path)

    reader = PdfReader(pdf_path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert "Сузить ICP" in text
    assert "Рекомендация: проверить цикл сделки." in text
    assert "Обоснование: рынок требует доказательства повторяемой боли." in text
    assert "Эффект: меньше распыления команды." in text
    assert "Методология и источники" in text
    assert "Публичный benchmark остаётся публичным ориентиром, не фактом компании." in text
    assert "Пустой технический раздел" not in text
    assert "■" not in text
    assert "�" not in text
    assert len(captured_images) == 1
    assert len(reader.pages) == 1


def test_reportlab_fallback_tables_are_bounded_and_wrap_long_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reportlab.platypus import Paragraph, Table as RealTable

    captured_tables: list[Any] = []

    class CapturingTable(RealTable):  # type: ignore[misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.initial_rows = args[0]
            super().__init__(*args, **kwargs)
            captured_tables.append(self)

    monkeypatch.setattr("reportlab.platypus.Table", CapturingTable)
    long_hash = "sha256:" + "a" * 96
    long_uuid = "12345678-1234-5678-1234-567812345678"
    html = f"""
    <!doctype html>
    <html>
      <body>
        <h1>Public Due Diligence Report</h1>
        <section>
          <h2>Evidence Coverage</h2>
          <table>
            <tr><th>Locator</th><th>Supporting Hash</th><th>Artifact</th></tr>
            <tr><td>filing_section:Item 8</td><td>{long_hash}</td><td>{long_uuid}</td></tr>
          </table>
        </section>
      </body>
    </html>
    """

    ReportLabRenderer().render(html, tmp_path / "fallback.pdf")

    assert captured_tables
    for table in captured_tables:
        assert all(width is not None for width in table._argW)
        assert sum(float(width) for width in table._argW) <= 468
        cells = [cell for row in table.initial_rows for cell in row]
        assert all(isinstance(cell, Paragraph) for cell in cells)
        cell_text = "\n".join(cell.getPlainText() for cell in cells)
        assert long_hash in cell_text
        assert long_uuid in cell_text
        assert all(cell.style.wordWrap == "CJK" for cell in cells)


def test_appendix_contains_source_locator_calculation_and_claim_labels(
    report_service: ReportService,
    approved_snapshot: ReportSnapshot,
) -> None:
    appendix = approved_snapshot.sections["source_and_calculation_appendix"]
    appendix_text = str(appendix)

    assert "SOURCE" in appendix_text
    assert "CALCULATION" in appendix_text
    assert "INFERENCE" in appendix_text
    assert "filing_section" in appendix_text
    assert "Item 8" in appendix_text
    assert str(ARTIFACT_ID) in appendix_text
    assert "sha256:" + "c" * 64 in appendix_text
    assert str(CALC_GROWTH_ID) in appendix_text
    assert "public-metrics@1" in appendix_text
    assert str(FACT_REVENUE_ID) in appendix_text


def test_validation_errors_do_not_trigger_reportlab_fallback(
    report_service_with_failing_weasyprint: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    invalid_snapshot = approved_snapshot.model_copy(update={"sections": {}})

    with pytest.raises(ReportValidationError):
        report_service_with_failing_weasyprint.render_final_pdf(invalid_snapshot, tmp_path)


def test_public_builder_rejects_cross_case_inputs(report_service: ReportService) -> None:
    other_case = _uuid("case:other")
    mixed = PublicReportCase(
        case=_case(),
        facts=(_fact(FACT_REVENUE_ID, "revenue", Decimal("1000000000"), "USD", "FY2025"),),
        calculations=(
            _calculation(
                CALC_GROWTH_ID,
                "revenue_growth",
                Decimal("0.12"),
                "ratio",
                "FY2025",
                case_id=other_case,
            ),
        ),
        findings=(_finding(case_id=other_case),),
        contradictions=(_contradiction(case_id=other_case),),
        source_hashes={"10-k": "sha256:" + "a" * 64},
        trace_ids=("trace-public-1",),
    )

    with pytest.raises(ReportValidationError):
        report_service.build_public(mixed)


def test_draft_write_failure_leaves_no_success_artifact(
    report_service: ReportService,
    approved_snapshot: ReportSnapshot,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "draft"
    output_dir.mkdir()
    (output_dir / f"{approved_snapshot.id}.report.html").mkdir()

    with pytest.raises(OSError):
        report_service.render_draft(approved_snapshot, output_dir)

    assert not (output_dir / f"{approved_snapshot.id}.report.json").exists()


@pytest.fixture
def report_service() -> ReportService:
    return ReportService(
        builder=ReportBuilder(project_root=Path.cwd()), html_renderer=HtmlRenderer()
    )


@pytest.fixture
def report_service_with_approval(approved_snapshot: ReportSnapshot) -> ReportService:
    return _service_with_approvals(
        InMemoryApprovalRepository([_gate4_approval(approved_snapshot, action="approved")]),
        current_revision=approved_snapshot.data_revision,
    )


@pytest.fixture
def report_service_with_failing_weasyprint(approved_snapshot: ReportSnapshot) -> ReportService:
    return _service_with_approvals(
        InMemoryApprovalRepository([_gate4_approval(approved_snapshot, action="approved")]),
        current_revision=approved_snapshot.data_revision,
        pdf_renderer=FailingWeasyPrintRenderer(),
    )


@pytest.fixture
def approved_public_case() -> PublicReportCase:
    return PublicReportCase(
        case=_case(),
        facts=(_fact(FACT_REVENUE_ID, "revenue", Decimal("1000000000"), "USD", "FY2025"),),
        calculations=(
            _calculation(CALC_GROWTH_ID, "revenue_growth", Decimal("0.12"), "ratio", "FY2025"),
        ),
        findings=(_finding(),),
        contradictions=(_contradiction(),),
        source_hashes={"10-k": "sha256:" + "a" * 64, "market": "sha256:" + "b" * 64},
        trace_ids=("trace-public-1",),
    )


@pytest.fixture
def draft_snapshot(
    report_service: ReportService, approved_public_case: PublicReportCase
) -> ReportSnapshot:
    return report_service.build_public(approved_public_case)


@pytest.fixture
def approved_snapshot(
    report_service: ReportService, approved_public_case: PublicReportCase
) -> ReportSnapshot:
    return report_service.build_public(approved_public_case)


class FailingWeasyPrintRenderer:
    def render(self, html: str, output_path: Path) -> None:
        raise WeasyPrintBackendError("native weasyprint backend unavailable")


@dataclass(frozen=True)
class PublicReportCase:
    case: DueDiligenceCase
    facts: tuple[EvidenceFact, ...]
    calculations: tuple[Calculation, ...]
    findings: tuple[Finding, ...]
    contradictions: tuple[Contradiction, ...]
    source_hashes: dict[str, str]
    trace_ids: tuple[str, ...]

    def with_contradictions(self, contradictions: tuple[Contradiction, ...]) -> PublicReportCase:
        return replace(self, contradictions=contradictions)

    def with_source_hashes(self, source_hashes: dict[str, str]) -> PublicReportCase:
        return replace(self, source_hashes=source_hashes)

    def with_data_revision(self, data_revision: int) -> PublicReportCase:
        return replace(self, case=self.case.model_copy(update={"data_revision": data_revision}))


class InMemoryApprovalRepository:
    def __init__(self, approvals: list[Approval]) -> None:
        self._approvals = approvals

    def add(self, approval: Approval) -> None:
        self._approvals.append(approval)

    def list_for_case(self, case_id: UUID) -> list[Approval]:
        return [approval for approval in self._approvals if approval.case_id == case_id]


def _service_with_approvals(
    approvals: InMemoryApprovalRepository,
    *,
    current_revision: int,
    pdf_renderer: PdfRendererPort | None = None,
) -> ReportService:
    return ReportService(
        builder=ReportBuilder(project_root=Path.cwd()),
        html_renderer=HtmlRenderer(),
        pdf_renderer=pdf_renderer or FailingWeasyPrintRenderer(),
        fallback_renderer=ReportLabRenderer(),
        approval_repository=approvals,
        current_data_revision=lambda _case_id: current_revision,
    )


def _case() -> DueDiligenceCase:
    return DueDiligenceCase(
        case_id=CASE_ID,
        mode=AnalysisMode.PUBLIC_COMPANY,
        entity_name="Apple Inc.",
        entity_identifier="AAPL",
        jurisdiction="US",
        scope=("public_company_stage1a",),
        period_start="2025-01-01",
        period_end="2025-12-31",
        as_of=AS_OF,
        base_currency="USD",
        privacy_policy="public-egress@1",
        budget_policy="offline",
        status=CaseStatus.AWAITING_REVIEW,
        sensitivity=SensitivityClass.PUBLIC,
        created_at=AS_OF,
        updated_at=AS_OF,
        workflow_version="public-graph@1",
        data_revision=1,
    )


def _fact(
    fact_id: UUID,
    name: str,
    value: Decimal,
    unit: str,
    period: str,
) -> EvidenceFact:
    from due_diligence_agent.domain.artifacts.models import SourceLocator

    return EvidenceFact(
        id=fact_id,
        artifact_id=ARTIFACT_ID,
        name=name,
        value=value,
        value_type="decimal",
        unit=unit,
        period=period,
        locator=SourceLocator(
            kind="filing_section", value="Item 8", artifact_id=ARTIFACT_ID, page=12, table="Income"
        ),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.98"),
        source_priority=1,
        extraction_method="fixture",
        supporting_text_hash="sha256:" + "c" * 64,
        source_freshness_at=AS_OF,
        retrieved_at=AS_OF,
    )


def _calculation(
    calculation_id: UUID,
    metric_name: str,
    value: Decimal,
    unit: str,
    period: str,
    case_id: UUID = CASE_ID,
) -> Calculation:
    return Calculation(
        id=calculation_id,
        case_id=case_id,
        metric_name=metric_name,
        formula_version="public-metrics@1",
        input_fact_ids=(FACT_REVENUE_ID,),
        value=value,
        unit=unit,
        period=period,
        warnings=(),
        calculated_at=AS_OF,
        sensitivity=SensitivityClass.PUBLIC,
    )


def _finding(*, case_id: UUID = CASE_ID) -> Finding:
    return Finding(
        id=FINDING_ID,
        case_id=case_id,
        category="financial",
        severity=FindingSeverity.HIGH,
        claim="Revenue growth supports the investment thesis.",
        evidence_fact_ids=(FACT_REVENUE_ID,),
        calculation_ids=(CALC_GROWTH_ID,),
        confidence=Decimal("0.82"),
        status=FindingStatus.VERIFIED,
        author_node="financial_analysis",
        author_model="offline",
        sensitivity=SensitivityClass.PUBLIC,
        created_at=AS_OF,
    )


def _contradiction(
    *,
    severity: FindingSeverity = FindingSeverity.MEDIUM,
    case_id: UUID = CASE_ID,
) -> Contradiction:
    return Contradiction(
        id=CONTRADICTION_ID,
        case_id=case_id,
        conflict_type="risk_factor_change",
        fact_ids=(FACT_REVENUE_ID,),
        finding_ids=(FINDING_ID,),
        explanation="Management notes demand uncertainty despite revenue growth.",
        severity=severity,
        status=ContradictionStatus.UNRESOLVED,
        recommended_resolution="Carry forward into counter-thesis.",
        sensitivity=SensitivityClass.PUBLIC,
        detected_at=AS_OF,
    )


def _sha256_file(path: Path) -> str:
    from hashlib import sha256

    return sha256(path.read_bytes()).hexdigest()


def _gate4_approval(
    snapshot: ReportSnapshot,
    *,
    action: str,
    subject_id: UUID | None = None,
    subject_hash: str | None = None,
    data_revision: int | None = None,
    sequence: int = 1,
) -> Approval:
    return Approval(
        id=_uuid(f"approval:{snapshot.id}:{action}:{sequence}"),
        case_id=snapshot.case_id,
        gate="gate_4",
        action=action,
        actor="reviewer",
        decided_at=AS_OF.replace(second=sequence),
        data_revision=data_revision if data_revision is not None else snapshot.data_revision,
        subject_id=subject_id or snapshot.id,
        subject_hash=subject_hash or snapshot.report_hash,
        subject_version=snapshot.version,
    )
