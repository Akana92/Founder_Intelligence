from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import platform
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.adapters.reports.charts import (
    financial_trend_png_data_uri,
    startup_bar_chart_png_data_uri,
)
from due_diligence_agent.adapters.reports.html_renderer import HtmlRenderer
from due_diligence_agent.adapters.reports.pdf_renderer import PdfRenderer, WeasyPrintBackendError
from due_diligence_agent.adapters.reports.reportlab_renderer import ReportLabRenderer
from due_diligence_agent.application.services.report_canonical import (
    INTEGRITY_PREIMAGE_CONTRACT,
    PUBLIC_REPORT_SCHEMA,
    PUBLIC_REPORT_TEMPLATE_VERSION,
    STARTUP_REPORT_SCHEMA,
    STARTUP_REPORT_SECTION_KEYS,
    STARTUP_REPORT_TEMPLATE_VERSION,
    canonical_json,
    canonical_snapshot_report_json,
    current_git_commit,
    package_versions,
    sha256_bytes,
    sha256_file,
)
from due_diligence_agent.application.services.founder_report_presentation_service import (
    FounderStartupReportPresentationService,
)
from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import AnalysisMode, SensitivityClass
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest
from due_diligence_agent.ports.repositories import ApprovalRepository, ReportRepository
from due_diligence_agent.ports.rendering import HtmlRendererPort, PdfRendererPort


REQUIRED_PUBLIC_SECTIONS = (
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
)

DISCLAIMER = (
    "This report is analytical support only. It is not legal, tax, or personal "
    "investment advice, does not execute or recommend a transaction, requires a "
    "human decision owner, and is limited by the listed sources, as-of date, and "
    "supported jurisdiction."
)


class ReportFreezeRequired(RuntimeError):
    pass


class ReportRendererUnavailable(RuntimeError):
    pass


class ReportValidationError(ValueError):
    pass


class PublicReportCaseInput(Protocol):
    @property
    def case(self) -> DueDiligenceCase: ...

    @property
    def facts(self) -> Sequence[EvidenceFact]: ...

    @property
    def calculations(self) -> Sequence[Calculation]: ...

    @property
    def findings(self) -> Sequence[Finding]: ...

    @property
    def contradictions(self) -> Sequence[Contradiction]: ...

    @property
    def source_hashes(self) -> Mapping[str, str]: ...

    @property
    def trace_ids(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class DraftRenderResult:
    snapshot: ReportSnapshot
    json_path: Path
    html_path: Path


@dataclass(frozen=True)
class PdfRenderResult:
    snapshot: ReportSnapshot
    snapshot_id: object
    pdf_path: Path
    fallback_used: str | None = None
    primary_error: str | None = None


@dataclass(frozen=True)
class ApprovedRenderResult:
    json: Path
    html: Path
    pdf: Path
    snapshot: ReportSnapshot
    fallback_used: str | None = None


class ReportBuilder:
    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path.cwd()

    def build_public(self, report_case: PublicReportCaseInput) -> ReportSnapshot:
        case = report_case.case
        _validate_case_input(report_case)
        sections = _required_public_sections(report_case)
        manifest = self._manifest(case)
        preimage = _canonical_integrity_preimage(
            case=case,
            source_hashes=report_case.source_hashes,
            sections=sections,
            manifest=manifest,
            trace_ids=report_case.trace_ids,
            data_revision=case.data_revision,
            formula_versions=_formula_versions(report_case.calculations),
        )
        json_hash = sha256_bytes(preimage)
        snapshot_id = uuid5(NAMESPACE_URL, f"{case.case_id}:{json_hash}")
        snapshot = ReportSnapshot(
            id=snapshot_id,
            case_id=case.case_id,
            report_hash=f"sha256:{json_hash}",
            case_snapshot_hash=f"sha256:{sha256_bytes(canonical_json(case.model_dump(mode='json')))}",
            source_hashes=dict(report_case.source_hashes),
            as_of=case.as_of,
            graph_version=case.workflow_version,
            prompt_versions={"report": PUBLIC_REPORT_TEMPLATE_VERSION},
            formula_versions=_formula_versions(report_case.calculations),
            model_versions={"analysis": "offline"},
            trace_ids=report_case.trace_ids,
            sections=sections,
            data_revision=case.data_revision,
            json_artifact_ref=f"sha256:{json_hash}",
            html_artifact_ref=None,
            pdf_artifact_ref=None,
            content_hashes={"json": f"sha256:{json_hash}"},
            reproducibility=manifest,
            sensitivity=SensitivityClass.PUBLIC,
            created_at=case.as_of,
            version=1,
        )
        return _with_canonical_json_refs(snapshot)

    def _manifest(self, case: DueDiligenceCase) -> ReproducibilityManifest:
        return ReproducibilityManifest(
            code_commit=current_git_commit(self._project_root),
            build_id="local-stage1a",
            dependency_lock_hash=f"sha256:{sha256_file(self._project_root / 'uv.lock')}",
            python_version=platform.python_version(),
            package_versions=package_versions(
                ("pydantic", "jinja2", "matplotlib", "weasyprint", "reportlab")
            ),
            provider_model_id="offline",
            model_alias_snapshot="offline",
            reasoning_parameters={"effort": "none", "network": "disabled"},
            adapter_versions={
                "html": "jinja-server-owned@1",
                "pdf": "weasyprint@1",
                "fallback_pdf": "reportlab@1",
                "template": "sha256:"
                + sha256_file(
                    Path(__file__).parents[2]
                    / "adapters"
                    / "reports"
                    / "templates"
                    / "public_report.html.j2"
                ),
            },
            parser_versions={"report": "public-report@1"},
            embedding_model_version="offline",
            index_version="none",
            redaction_policy_version="egress@1",
            locale="en-US",
            timezone="UTC",
            fx_source=case.base_currency,
            deterministic_seeds={"report": 1, "matplotlib": 1},
            configuration_hash=f"sha256:{sha256_bytes(case.model_dump_json().encode('utf-8'))}",
        )


class ReportService:
    def __init__(
        self,
        *,
        builder: ReportBuilder | None = None,
        html_renderer: HtmlRendererPort | None = None,
        pdf_renderer: PdfRendererPort | None = None,
        fallback_renderer: PdfRendererPort | None = None,
        approval_repository: ApprovalRepository | None = None,
        current_data_revision: Callable[[UUID], int] | None = None,
        report_repository: ReportRepository | None = None,
    ) -> None:
        self._builder = builder or ReportBuilder()
        self._html_renderer = html_renderer or HtmlRenderer()
        self._pdf_renderer = pdf_renderer or PdfRenderer()
        self._fallback_renderer = fallback_renderer or ReportLabRenderer()
        self._approval_repository = approval_repository
        self._current_data_revision = current_data_revision
        self._report_repository = report_repository

    def build_public(self, report_case: PublicReportCaseInput) -> ReportSnapshot:
        return self._builder.build_public(report_case)

    def render_html(self, snapshot: ReportSnapshot) -> str:
        """Render HTML without mutating artifact lineage or persisted metadata."""
        _validate_snapshot(snapshot)
        return self._render_html(snapshot)

    def render_draft(self, snapshot: ReportSnapshot, output_dir: Path) -> DraftRenderResult:
        _validate_snapshot(snapshot)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_bytes = _canonical_snapshot_report_json(snapshot)
        json_hash = sha256_bytes(json_bytes)
        html = self._render_html(snapshot)
        html_bytes = html.encode("utf-8")
        html_hash = sha256_bytes(html_bytes)
        json_path = output_dir / f"{snapshot.id}.report.json"
        html_path = output_dir / f"{snapshot.id}.report.html"
        _write_pair_atomic(
            first_path=html_path,
            first_payload=html_bytes,
            second_path=json_path,
            second_payload=json_bytes,
        )
        updated = _revalidated_snapshot(
            snapshot,
            {
                "json_artifact_ref": f"sha256:{json_hash}",
                "html_artifact_ref": f"sha256:{html_hash}",
                "content_hashes": {
                    **dict(snapshot.content_hashes),
                    "json": f"sha256:{json_hash}",
                    "html": f"sha256:{html_hash}",
                },
            },
        )
        self._persist_rendered_draft(updated)
        return DraftRenderResult(snapshot=updated, json_path=json_path, html_path=html_path)

    def render_final_pdf(self, snapshot: ReportSnapshot, output_dir: Path) -> PdfRenderResult:
        _validate_snapshot(snapshot)
        if not self._freeze_approved(snapshot):
            raise ReportFreezeRequired("gate_4_freeze_required")
        output_dir.mkdir(parents=True, exist_ok=True)
        html = self._render_html(snapshot)
        pdf_path = output_dir / f"{snapshot.id}.report.pdf"
        pdf_tmp_path = pdf_path.with_name(f"{pdf_path.name}.tmp")
        if pdf_tmp_path.exists() and pdf_tmp_path.is_file():
            pdf_tmp_path.unlink()
        try:
            self._pdf_renderer.render(html, pdf_tmp_path)
            fallback_used = None
            primary_error = None
        except WeasyPrintBackendError:
            if pdf_tmp_path.exists() and pdf_tmp_path.is_file():
                pdf_tmp_path.unlink()
            try:
                self._fallback_renderer.render(html, pdf_tmp_path)
            except Exception as exc:
                if pdf_tmp_path.exists() and pdf_tmp_path.is_file():
                    pdf_tmp_path.unlink()
                raise ReportRendererUnavailable("report_renderer_unavailable") from exc
            fallback_used = "reportlab"
            primary_error = "weasyprint_backend_error"
        os.replace(pdf_tmp_path, pdf_path)
        pdf_hash = sha256_file(pdf_path)
        updated = _revalidated_snapshot(
            snapshot,
            {
                "pdf_artifact_ref": f"sha256:{pdf_hash}",
                "content_hashes": {**dict(snapshot.content_hashes), "pdf": f"sha256:{pdf_hash}"},
            },
        )
        return PdfRenderResult(
            snapshot=updated,
            snapshot_id=snapshot.id,
            pdf_path=pdf_path,
            fallback_used=fallback_used,
            primary_error=primary_error,
        )

    def render_approved(self, snapshot_id: UUID, output_dir: Path) -> ApprovedRenderResult:
        if self._report_repository is None:
            raise RuntimeError("report_repository_required")
        snapshot = self._report_repository.get_snapshot(snapshot_id)
        renderer = ReportService(
            builder=self._builder,
            html_renderer=self._html_renderer,
            pdf_renderer=self._pdf_renderer,
            fallback_renderer=self._fallback_renderer,
            approval_repository=self._approval_repository,
            current_data_revision=self._current_data_revision,
            report_repository=None,
        )
        draft = renderer.render_draft(snapshot, output_dir)
        pdf = renderer.render_final_pdf(draft.snapshot, output_dir)
        return ApprovedRenderResult(
            json=draft.json_path,
            html=draft.html_path,
            pdf=pdf.pdf_path,
            snapshot=pdf.snapshot,
            fallback_used=pdf.fallback_used,
        )

    def _render_html(self, snapshot: ReportSnapshot) -> str:
        if _is_startup_snapshot(snapshot):
            founder_view = FounderStartupReportPresentationService().build(snapshot)
            return self._html_renderer.render(
                {
                    "template": "startup_founder_report.html.j2",
                    "founder_view": founder_view,
                    "startup_charts": _startup_chart_context(snapshot),
                }
            )
        return self._html_renderer.render(
            {
                "title": "Public Due Diligence Report",
                "snapshot_id": str(snapshot.id),
                "as_of": snapshot.as_of.isoformat(),
                "sections": dict(snapshot.sections),
            }
        )

    def _freeze_approved(self, snapshot: ReportSnapshot) -> bool:
        if self._approval_repository is None:
            return False
        current_revision = (
            self._current_data_revision(snapshot.case_id)
            if self._current_data_revision is not None
            else snapshot.data_revision
        )
        if current_revision != snapshot.data_revision:
            return False
        approvals = [
            approval
            for approval in self._approval_repository.list_for_case(snapshot.case_id)
            if _matches_gate4_subject(approval, snapshot)
        ]
        if not approvals:
            return False
        latest = max(approvals, key=lambda approval: (approval.decided_at, str(approval.id)))
        return latest.action == "approved"

    def _persist_rendered_draft(self, snapshot: ReportSnapshot) -> None:
        if self._report_repository is None:
            return
        try:
            self._report_repository.add_snapshot(snapshot)
        except ValueError as exc:
            if str(exc) != "report_snapshot_already_exists":
                raise
            existing = self._report_repository.get_snapshot(snapshot.id)
            if existing.model_dump(mode="json") != snapshot.model_dump(mode="json"):
                raise ValueError("report_snapshot_conflict") from exc


def _required_public_sections(report_case: PublicReportCaseInput) -> dict[str, dict[str, object]]:
    case = report_case.case
    facts = tuple(report_case.facts)
    calculations = tuple(report_case.calculations)
    findings = tuple(report_case.findings)
    contradictions = tuple(report_case.contradictions)
    financial_rows: list[tuple[object, ...]] = [
        (calculation.metric_name, str(calculation.value), calculation.unit, calculation.period)
        for calculation in calculations
    ]
    evidence_rows: list[tuple[object, ...]] = [
        (
            "SOURCE",
            fact.name,
            str(fact.value),
            fact.unit or "",
            fact.period or "",
            f"locator_kind={fact.locator.kind}",
            f"locator_value={fact.locator.value}",
            f"page={fact.locator.page or 'MISSING'}",
            f"table={fact.locator.table or 'MISSING'}",
            str(fact.locator.artifact_id),
            fact.supporting_text_hash,
        )
        for fact in facts
    ]
    calculation_rows: list[tuple[object, ...]] = [
        (
            "CALCULATION",
            str(calculation.id),
            calculation.metric_name,
            str(calculation.value),
            calculation.unit,
            calculation.period,
            calculation.formula_version,
            ",".join(str(fact_id) for fact_id in calculation.input_fact_ids),
        )
        for calculation in calculations
    ]
    finding_rows: list[tuple[object, ...]] = [
        (
            "INFERENCE",
            str(finding.id),
            finding.category,
            finding.severity.value,
            finding.status.value,
            finding.claim,
            f"evidence_refs={','.join(str(item) for item in finding.evidence_fact_ids)}",
            f"calculation_refs={','.join(str(item) for item in finding.calculation_ids)}",
        )
        for finding in findings
    ]
    chart_points = [
        (calculation.period, calculation.value)
        for calculation in calculations
        if calculation.metric_name == "revenue_growth"
    ] or [("current", Decimal("0"))]
    return {
        "metadata": _section(
            "Metadata",
            f"{case.entity_name} ({case.entity_identifier}) as of {case.as_of.date().isoformat()}",
            rows=(
                ("case_id", str(case.case_id)),
                ("trace_ids", ", ".join(report_case.trace_ids)),
                ("data_revision", str(case.data_revision)),
                ("report_mode", case.mode.value),
            ),
        ),
        "executive_summary": _section(
            "Executive Summary",
            _claims_summary(findings, contradictions),
            items=tuple(
                contradiction.explanation
                for contradiction in contradictions
                if contradiction.severity.value == "critical"
                and contradiction.status.value == "unresolved"
            ),
        ),
        "investment_thesis": _section(
            "Investment Thesis",
            "Verified findings support the investable thesis where evidence coverage is complete.",
            items=tuple(
                f"{finding.claim} [INFERENCE appendix_ref={finding.id}]"
                for finding in findings
                if finding.status.value == "verified"
            ),
        ),
        "counter_thesis": _section(
            "Counter-Thesis",
            "Open contradictions and insufficient-data findings remain decision inputs.",
            items=tuple(contradiction.explanation for contradiction in contradictions),
        ),
        "company_profile": _section(
            "Company Profile",
            f"{case.entity_name} is evaluated as a supported SEC-reporting issuer.",
            rows=(("jurisdiction", case.jurisdiction), ("base_currency", case.base_currency)),
        ),
        "evidence_coverage": _section(
            "Evidence Coverage",
            f"{len(facts)} facts and {len(calculations)} calculations are linked to the report.",
            rows=evidence_rows,
        ),
        "financial_metrics": _section(
            "Financial Metrics", "Deterministic metric outputs.", rows=financial_rows
        ),
        "risk_matrix": _section(
            "Risk Matrix",
            "Risk severity is derived from evidence, confidence, impact, and open status.",
            rows=tuple(
                (
                    finding.category,
                    f"probability_confidence={finding.confidence}",
                    f"impact_severity={finding.severity.value}",
                    finding.status.value,
                    f"evidence_refs={','.join(str(item) for item in finding.evidence_fact_ids)}",
                )
                for finding in findings
            ),
        ),
        "contradictions": _section(
            "Contradictions",
            "Contradictions are carried forward until resolved by HITL.",
            rows=tuple(
                (item.conflict_type, item.severity.value, item.status.value, item.explanation)
                for item in contradictions
            ),
        ),
        "missing_data": _section(
            "Missing Data",
            "MISSING items are explicitly labelled; no raw source document text is embedded.",
            rows=(("MISSING", "raw_source_documents", "privacy_boundary"),),
        ),
        "next_steps": _section(
            "Next Steps",
            "Human reviewer should resolve open contradictions and approve or reject freeze.",
        ),
        "methodology": _section(
            "Methodology",
            "Evidence-backed deterministic calculations, bounded review gates, and immutable snapshots.",
        ),
        "source_and_calculation_appendix": _section(
            "Source and Calculation Appendix",
            "Every report claim references source locators, calculations, or insufficient-data status.",
            rows=evidence_rows
            + calculation_rows
            + finding_rows
            + [("MISSING", "uncited_claims", "none")],
        ),
        "disclaimer": _section("Mandatory Disclaimer", DISCLAIMER),
        "decision_owner": _section(
            "Decision Owner",
            "The report does not make a decision; a human decision owner must approve any action.",
        ),
        "filing_timeline": _section(
            "Filing Timeline",
            "Frozen SEC fixture timeline as of the report date; MISSING where filings are unavailable.",
        ),
        "financial_trends": _section(
            "Financial Trends",
            "Static deterministic chart rendering for PDF output.",
            chart_data_uri=financial_trend_png_data_uri(chart_points),
        ),
        "capital_structure": _section(
            "Capital Structure",
            "Capital structure is summarized from public filings or marked MISSING.",
        ),
        "valuation": _section(
            "Valuation", "Valuation is analytical support and not a transaction recommendation."
        ),
        "sec_risk_factor_changes": _section(
            "SEC Risk Factor Changes",
            "Risk factor changes are summarized from cited filing evidence or marked MISSING.",
        ),
        "corporate_events": _section(
            "Corporate Events",
            "Corporate events are secondary context; unavailable events are MISSING.",
        ),
        "news_coverage": _news_coverage_section(facts),
    }


def _section(
    title: str,
    summary: str,
    *,
    rows: Sequence[Sequence[object]] = (),
    items: Sequence[str] = (),
    chart_data_uri: str | None = None,
) -> dict[str, object]:
    section: dict[str, object] = {
        "title": title,
        "summary": summary,
        "rows": tuple(tuple(str(cell) for cell in row) for row in rows),
        "items": tuple(items),
    }
    if chart_data_uri is not None:
        section["chart_data_uri"] = chart_data_uri
    return section


def _news_coverage_section(facts: Sequence[EvidenceFact]) -> dict[str, object]:
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    rows: list[tuple[str, str, str]] = []
    for fact in facts:
        if fact.name != "news_signal":
            continue
        title = str(fact.value)
        polarity = str(fact.metadata.get("polarity") or "")
        if polarity not in counts:
            rows.append(("missing_polarity", title, str(fact.id)))
            continue
        counts[polarity] += 1
        rows.append((polarity, title, str(fact.id)))
    summary = (
        "News polarity is deterministic metadata-only context "
        f"(positive:{counts['positive']} neutral:{counts['neutral']} negative:{counts['negative']}); "
        "news is not evidence for primary financial facts."
    )
    return _section("News Coverage", summary, rows=rows)


def _claims_summary(findings: Sequence[Finding], contradictions: Sequence[Contradiction]) -> str:
    return (
        f"{len(findings)} findings and {len(contradictions)} contradictions were synthesized "
        "from approved public-company evidence."
    )


def _validate_case_input(report_case: PublicReportCaseInput) -> None:
    case = report_case.case
    if case.mode is not AnalysisMode.PUBLIC_COMPANY:
        raise ReportValidationError("public_company_mode_required")
    for calculation in report_case.calculations:
        if calculation.case_id != case.case_id:
            raise ReportValidationError("cross_case_calculation_input")
    for finding in report_case.findings:
        if finding.case_id != case.case_id:
            raise ReportValidationError("cross_case_finding_input")
    for contradiction in report_case.contradictions:
        if contradiction.case_id != case.case_id:
            raise ReportValidationError("cross_case_contradiction_input")


def _validate_snapshot(snapshot: ReportSnapshot) -> None:
    if _is_startup_snapshot(snapshot):
        _validate_startup_snapshot(snapshot)
        return
    missing = set(REQUIRED_PUBLIC_SECTIONS) - set(snapshot.sections)
    if missing:
        raise ReportValidationError(f"missing_report_sections:{','.join(sorted(missing))}")
    for key in REQUIRED_PUBLIC_SECTIONS:
        section = snapshot.sections[key]
        if not isinstance(section, Mapping):
            raise ReportValidationError(f"invalid_report_section:{key}")
        if not str(section.get("title", "")).strip() or not str(section.get("summary", "")).strip():
            raise ReportValidationError(f"empty_report_section:{key}")
    disclaimer = snapshot.sections["disclaimer"]
    if not isinstance(disclaimer, Mapping) or DISCLAIMER not in str(disclaimer.get("summary", "")):
        raise ReportValidationError("mandatory_disclaimer_missing")


def _formula_versions(calculations: Sequence[Calculation]) -> dict[str, str]:
    versions = {
        calculation.metric_name: calculation.formula_version for calculation in calculations
    }
    return versions or {"none": "none"}


def _matches_gate4_subject(approval: Approval, snapshot: ReportSnapshot) -> bool:
    return (
        approval.gate == "gate_4"
        and approval.action in {"approved", "rejected"}
        and approval.case_id == snapshot.case_id
        and approval.subject_id == snapshot.id
        and approval.subject_hash == snapshot.report_hash
        and approval.subject_version == snapshot.version
        and approval.data_revision == snapshot.data_revision
    )


def _revalidated_snapshot(snapshot: ReportSnapshot, update: Mapping[str, object]) -> ReportSnapshot:
    payload = snapshot.model_dump(mode="json")
    payload.update(update)
    return ReportSnapshot.model_validate(payload)


def _with_canonical_json_refs(snapshot: ReportSnapshot) -> ReportSnapshot:
    json_hash = sha256_bytes(_canonical_snapshot_report_json(snapshot))
    return _revalidated_snapshot(
        snapshot,
        {
            "json_artifact_ref": f"sha256:{json_hash}",
            "content_hashes": {**dict(snapshot.content_hashes), "json": f"sha256:{json_hash}"},
        },
    )


def _write_pair_atomic(
    *,
    first_path: Path,
    first_payload: bytes,
    second_path: Path,
    second_payload: bytes,
) -> None:
    first_tmp = first_path.with_name(f"{first_path.name}.tmp")
    second_tmp = second_path.with_name(f"{second_path.name}.tmp")
    first_backup = first_path.with_name(f"{first_path.name}.bak")
    second_backup = second_path.with_name(f"{second_path.name}.bak")
    for final_path in (first_path, second_path):
        if final_path.exists() and not final_path.is_file():
            raise OSError(f"artifact_destination_not_file:{final_path}")
    for scratch_path in (first_tmp, second_tmp, first_backup, second_backup):
        if scratch_path.exists():
            if not scratch_path.is_file():
                raise OSError(f"artifact_scratch_not_file:{scratch_path}")
            scratch_path.unlink()
    first_existed = first_path.exists()
    second_existed = second_path.exists()
    first_published = False
    second_published = False
    try:
        first_tmp.write_bytes(first_payload)
        second_tmp.write_bytes(second_payload)
        if first_existed:
            os.replace(first_path, first_backup)
        if second_existed:
            os.replace(second_path, second_backup)
        os.replace(first_tmp, first_path)
        first_published = True
        os.replace(second_tmp, second_path)
        second_published = True
    except OSError:
        _rollback_pair_publish(
            first_path=first_path,
            second_path=second_path,
            first_backup=first_backup,
            second_backup=second_backup,
            first_existed=first_existed,
            second_existed=second_existed,
            first_published=first_published,
            second_published=second_published,
        )
        for scratch_path in (first_tmp, second_tmp, first_backup, second_backup):
            if scratch_path.exists() and scratch_path.is_file():
                scratch_path.unlink()
        raise
    for backup_path in (first_backup, second_backup):
        if backup_path.exists() and backup_path.is_file():
            backup_path.unlink()


def _rollback_pair_publish(
    *,
    first_path: Path,
    second_path: Path,
    first_backup: Path,
    second_backup: Path,
    first_existed: bool,
    second_existed: bool,
    first_published: bool,
    second_published: bool,
) -> None:
    if first_published and first_path.exists() and first_path.is_file():
        first_path.unlink()
    if second_published and second_path.exists() and second_path.is_file():
        second_path.unlink()
    if first_existed and first_backup.exists() and first_backup.is_file():
        os.replace(first_backup, first_path)
    if second_existed and second_backup.exists() and second_backup.is_file():
        os.replace(second_backup, second_path)


def _canonical_snapshot_report_json(snapshot: ReportSnapshot) -> bytes:
    if _is_startup_snapshot(snapshot):
        return canonical_snapshot_report_json(snapshot, schema=STARTUP_REPORT_SCHEMA, sort_keys=False)
    return canonical_snapshot_report_json(snapshot, schema=PUBLIC_REPORT_SCHEMA)


def _startup_chart_context(snapshot: ReportSnapshot) -> tuple[dict[str, str], ...]:
    sections = dict(snapshot.sections)
    charts: list[dict[str, str]] = []
    market_points = _startup_market_chart_points(sections)
    if market_points:
        charts.append(
            _startup_chart_item(
                "market_sizing",
                "Market sizing",
                "TAM / SAM / SOM from cited startup report rows only.",
                market_points,
            )
        )
    for metric_unit, metric_points in _startup_confirmed_metric_groups(sections):
        charts.append(
            _startup_chart_item(
                "confirmed_metrics",
                "Confirmed metrics",
                f"Calculated business metrics on the {metric_unit} native-unit scale; "
                "profile candidates are excluded.",
                metric_points,
            )
        )
    readiness_points = _startup_readiness_points(sections)
    if readiness_points:
        charts.append(
            _startup_chart_item(
                "readiness_coverage",
                "Readiness coverage",
                "Metric-pack readiness dimensions grouped by deterministic status.",
                readiness_points,
            )
        )
    charts.append(
        _startup_chart_item(
            "report_coverage",
            "Report coverage",
            "Coverage status across the 12 founder-facing report sections.",
            _startup_report_coverage_points(sections),
        )
    )
    return tuple(chart for chart in charts if chart["chart_data_uri"])


def _startup_chart_item(
    key: str,
    title: str,
    summary: str,
    points: Sequence[tuple[str, Decimal]],
) -> dict[str, str]:
    return {
        "key": key,
        "title": title,
        "summary": summary,
        "chart_data_uri": startup_bar_chart_png_data_uri(title, points) or "",
    }


def _startup_market_chart_points(
    sections: Mapping[str, object],
) -> tuple[tuple[str, Decimal], ...]:
    section = sections.get("market_size")
    if not isinstance(section, Mapping):
        return ()
    allowed_levels = {"tam", "sam", "som"}
    points: list[tuple[str, Decimal]] = []
    for row in _section_rows(section):
        if len(row) < 3:
            continue
        level = row[0].casefold()
        if level not in allowed_levels:
            continue
        value = _positive_decimal(row[2])
        if value is None:
            continue
        unit = row[3] if len(row) > 3 else "unit"
        currency = row[4] if len(row) > 4 else ""
        label = f"{level.upper()} ({currency} {unit})".replace("( ", "(")
        points.append((label[:80], value))
        if len(points) >= 3:
            break
    return tuple(points)


def _startup_confirmed_metric_groups(
    sections: Mapping[str, object],
) -> tuple[tuple[str, tuple[tuple[str, Decimal], ...]], ...]:
    section = sections.get("metrics")
    if not isinstance(section, Mapping):
        return ()
    grouped: dict[str, list[tuple[str, Decimal]]] = {}
    point_count = 0
    for row in _section_rows(section):
        if len(row) < 2 or not any(cell.startswith("calculation_ref=") for cell in row):
            continue
        value = _positive_decimal(row[1])
        if value is None:
            continue
        unit = (row[2].strip() if len(row) > 2 else "") or "unit"
        bounded_unit = unit[:40]
        grouped.setdefault(bounded_unit, []).append((f"{row[0]} ({bounded_unit})"[:80], value))
        point_count += 1
        if point_count >= 8:
            break
    return tuple((unit, tuple(points)) for unit, points in grouped.items())


def _startup_readiness_points(
    sections: Mapping[str, object],
) -> tuple[tuple[str, Decimal], ...]:
    section = sections.get("metrics")
    if not isinstance(section, Mapping):
        return ()
    counts = {"ready": 0, "provisional": 0, "blocked": 0}
    for row in _section_rows(section):
        if len(row) < 2 or not any(cell.startswith("dimension_ref=") for cell in row):
            continue
        status = row[1]
        if status in counts:
            counts[status] += 1
    if not any(counts.values()):
        return ()
    return tuple((label, Decimal(count)) for label, count in counts.items())


def _startup_report_coverage_points(
    sections: Mapping[str, object],
) -> tuple[tuple[str, Decimal], ...]:
    counts = {"SUPPORTED": 0, "PARTIAL": 0, "MISSING": 0, "CONTRADICTION": 0}
    for key in STARTUP_REPORT_SECTION_KEYS[:12]:
        section = sections.get(key)
        if not isinstance(section, Mapping):
            continue
        status = str(section.get("status", ""))
        if status in counts:
            counts[status] += 1
    return tuple((label, Decimal(count)) for label, count in counts.items())


def _section_rows(section: Mapping[str, object]) -> tuple[tuple[str, ...], ...]:
    rows = section.get("rows", ())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return ()
    normalized: list[tuple[str, ...]] = []
    for row in rows:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
            continue
        normalized.append(tuple(str(cell) for cell in row))
    return tuple(normalized)


def _positive_decimal(value: str) -> Decimal | None:
    if value == "MISSING":
        return None
    if not value.replace(".", "", 1).isdigit():
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _canonical_integrity_preimage(
    *,
    case: DueDiligenceCase,
    source_hashes: Mapping[str, str],
    sections: Mapping[str, object],
    manifest: ReproducibilityManifest,
    trace_ids: Sequence[str],
    data_revision: int,
    formula_versions: Mapping[str, str],
) -> bytes:
    return canonical_json(
        {
            "schema": "public_report_snapshot_integrity_preimage.v1",
            "case": case.model_dump(mode="json"),
            "case_snapshot_hash": f"sha256:{sha256_bytes(case.model_dump_json().encode('utf-8'))}",
            "source_hashes": dict(source_hashes),
            "data_revision": data_revision,
            "as_of": case.as_of.isoformat(),
            "graph_version": case.workflow_version,
            "prompt_versions": {"report": PUBLIC_REPORT_TEMPLATE_VERSION},
            "formula_versions": dict(formula_versions),
            "model_versions": {"analysis": "offline"},
            "trace_ids": tuple(trace_ids),
            "reproducibility": manifest.model_dump(mode="json"),
            "sections": sections,
            "integrity_preimage_contract": INTEGRITY_PREIMAGE_CONTRACT,
        }
    )


def _canonical_json(payload: object) -> bytes:
    return canonical_json(payload)


def _is_startup_snapshot(snapshot: ReportSnapshot) -> bool:
    return dict(snapshot.prompt_versions).get("report") == STARTUP_REPORT_TEMPLATE_VERSION


def _validate_startup_snapshot(snapshot: ReportSnapshot) -> None:
    missing = set(STARTUP_REPORT_SECTION_KEYS) - set(snapshot.sections)
    if missing:
        raise ReportValidationError(f"missing_startup_report_sections:{','.join(sorted(missing))}")
    for key in STARTUP_REPORT_SECTION_KEYS:
        section = snapshot.sections[key]
        if not isinstance(section, Mapping):
            raise ReportValidationError(f"invalid_startup_report_section:{key}")
        if not str(section.get("title", "")).strip() or not str(section.get("summary", "")).strip():
            raise ReportValidationError(f"empty_startup_report_section:{key}")
