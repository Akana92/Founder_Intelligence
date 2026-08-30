from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest

from due_diligence_agent.adapters.reports.html_renderer import HtmlRenderer
from due_diligence_agent.adapters.startup.frozen_market_research import (
    FrozenStartupMarketResearchAdapter,
)
from due_diligence_agent.application.services import startup_report_service
from due_diligence_agent.application.services.founder_report_presentation_service import (
    FounderStartupReportPresentationService,
)
from due_diligence_agent.application.services.report_service import (
    ReportService,
    ReportValidationError,
)
from due_diligence_agent.application.services.startup_readiness_service import (
    StartupReadinessService,
)
from due_diligence_agent.application.services.startup_report_service import (
    STARTUP_REPORT_SECTION_KEYS,
    StartupReportSnapshotBuilder,
    startup_canonical_snapshot_json,
)
from due_diligence_agent.domain.artifacts.models import SourceLocator
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
from due_diligence_agent.domain.evidence.startup_claims import (
    ClaimCategory,
    ClaimCriticality,
    StartupClaim,
)
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.startup.gtm import (
    StartupGtmDimension,
    StartupGtmDimensionName,
    StartupGtmDimensionStatus,
    StartupGtmExperimentCode,
    StartupGtmHorizon,
    StartupGtmLaunchPhase,
    StartupGtmSnapshot,
    StartupGtmStatus,
)
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupPublicBenchmarkCandidate,
    StartupResearchPlan,
    StartupResearchSourceMode,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.readiness import StartupReadinessSnapshot

AS_OF = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
CASE_ID = uuid5(NAMESPACE_URL, "startup-report-case")
OTHER_CASE_ID = uuid5(NAMESPACE_URL, "startup-report-other-case")
ARTIFACT_ID = uuid5(NAMESPACE_URL, "startup-report-artifact")
CLAIM_ID = uuid5(NAMESPACE_URL, "startup-report-claim-arr")
FACT_ID = uuid5(NAMESPACE_URL, "startup-report-fact-arr")
CALCULATION_ID = uuid5(NAMESPACE_URL, "startup-report-calculation-margin")
FINDING_ID = uuid5(NAMESPACE_URL, "startup-report-finding-risk")
CONTRADICTION_ID = uuid5(NAMESPACE_URL, "startup-report-contradiction-arr")
RAW_SENTINEL = "C:\\Users\\Akana\\secret\\pitch.pdf founder@example.com sk-live-secret"


def test_startup_snapshot_has_twelve_sections_and_explicit_missing_data() -> None:
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(_input())

    assert tuple(snapshot.sections)[:12] == STARTUP_REPORT_SECTION_KEYS
    assert set(STARTUP_REPORT_SECTION_KEYS) <= set(snapshot.sections)
    for key in STARTUP_REPORT_SECTION_KEYS:
        section = snapshot.sections[key]
        assert section["title"]
        assert section["summary"]
    assert snapshot.sections["market_size"]["status"] == "MISSING"
    assert "insufficient evidence" in snapshot.sections["market_size"]["summary"].lower()
    assert snapshot.sections["evidence_gaps"]["items"]
    assert snapshot.sections["action_plan"]["status"] == "MISSING"
    assert snapshot.sections["action_plan"]["rows"] == ()
    assert "without invented targets" in snapshot.sections["action_plan"]["items"][0]
    assert snapshot.sensitivity is SensitivityClass.CONFIDENTIAL


def test_startup_snapshot_identity_is_deterministic_and_sensitive_to_sources_and_revision() -> None:
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())
    baseline = builder.build(_input())
    same = builder.build(_input())
    changed_source = builder.build(
        replace(_input(), source_hashes={"pitch-deck": "sha256:" + "b" * 64})
    )
    changed_revision = builder.build(
        replace(
            _input(),
            case=_case(data_revision=2),
            startup_profile=_profile(data_revision=2),
        )
    )

    assert same.id == baseline.id
    assert same.report_hash == baseline.report_hash
    assert same.json_artifact_ref == baseline.json_artifact_ref
    assert changed_source.id != baseline.id
    assert changed_source.report_hash != baseline.report_hash
    assert changed_revision.id != baseline.id
    assert changed_revision.data_revision == 2


def test_founder_render_template_is_outside_canonical_snapshot_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_template = (
        Path("src/due_diligence_agent/adapters/reports/templates/startup_report.html.j2")
    )
    founder_template = canonical_template.with_name("startup_founder_report.html.j2")
    original_sha256_file = startup_report_service.sha256_file

    def stable_sha256_file(path: Path) -> str:
        if path.name == "uv.lock":
            return "0" * 64
        if path.resolve() == canonical_template.resolve():
            return _sha256_lf_normalized_file(path)
        return original_sha256_file(path)

    monkeypatch.setattr(
        startup_report_service,
        "current_git_commit",
        lambda _project_root: "task-7-baseline",
    )
    monkeypatch.setattr(
        startup_report_service.platform,
        "python_version",
        lambda: "3.13.0",
    )
    monkeypatch.setattr(
        startup_report_service,
        "package_versions",
        lambda _packages: {
            "pydantic": "fixed",
            "jinja2": "fixed",
            "weasyprint": "fixed",
            "reportlab": "fixed",
        },
    )
    monkeypatch.setattr(startup_report_service, "sha256_file", stable_sha256_file)

    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(_input())

    assert _sha256_lf_normalized_file(canonical_template) == (
        "4424cb5b1a4c11977609204d9bc5e568020b46eef18b4079a11e35a6bd25af97"
    )
    assert founder_template.is_file()
    assert str(snapshot.id) == "bfa8e9c5-38fe-5ab1-a393-d2bd16711998"
    assert snapshot.report_hash == (
        "sha256:be651ade13d8dc7398771ae9a2cd2604d6306a998f547e49e138e7c81306e044"
    )
    assert snapshot.reproducibility.adapter_versions["template"] == (
        "sha256:4424cb5b1a4c11977609204d9bc5e568020b46eef18b4079a11e35a6bd25af97"
    )


def test_startup_source_appendix_order_is_deterministic_across_input_mapping_order() -> None:
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())
    sources = {
        "market-source-b": "sha256:" + "b" * 64,
        "market-source-a": "sha256:" + "a" * 64,
    }
    baseline = builder.build(replace(_input(), source_hashes=sources))
    reordered = builder.build(replace(_input(), source_hashes=dict(reversed(tuple(sources.items())))))

    assert baseline.sections["source_appendix"]["rows"] == (
        ("market-source-a", "sha256:" + "a" * 64),
        ("market-source-b", "sha256:" + "b" * 64),
    )
    assert reordered.id == baseline.id
    assert reordered.report_hash == baseline.report_hash


def test_startup_snapshot_sections_are_grounded_in_the_canonical_profile() -> None:
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(_input())

    assert ("problem_statement", "source_fact", "Manual diligence takes weeks") in _profile_cells(
        snapshot.sections["problem_solution"]
    )
    assert ("solution", "source_fact", "Automated evidence-backed diligence") in _profile_cells(
        snapshot.sections["problem_solution"]
    )
    assert ("competitors", "source_fact", "Legacy advisory firms") in _profile_cells(
        snapshot.sections["competitors"]
    )
    assert ("strengths", "source_fact", "Deterministic evidence lineage") in _profile_cells(
        snapshot.sections["moat"]
    )
    assert ("weaknesses", "source_fact", "Early distribution") in _profile_cells(
        snapshot.sections["risks"]
    )
    assert ("assumptions", "source_fact", "Founder supplies primary evidence") in _profile_cells(
        snapshot.sections["financial_assumptions"]
    )
    assert "market_size_missing" in snapshot.sections["evidence_gaps"]["items"]
    assert snapshot.sections["evidence_gaps"]["status"] == "MISSING"


def test_startup_snapshot_identity_changes_with_profile_hash_and_revision() -> None:
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())
    baseline = builder.build(_input())
    changed_profile = _profile(
        fields={
            **_profile_fields(),
            StartupProfileFieldName.PROBLEM.value: _profile_field(
                StartupProfileFieldName.PROBLEM,
                "Evidence review has an avoidable manual bottleneck",
            ),
        }
    )
    changed_hash = builder.build(replace(_input(), startup_profile=changed_profile))
    changed_revision = builder.build(
        replace(
            _input(),
            case=_case(data_revision=2),
            startup_profile=_profile(data_revision=2),
        )
    )

    assert changed_profile.profile_hash != _input().startup_profile.profile_hash
    assert changed_hash.id != baseline.id
    assert changed_hash.report_hash != baseline.report_hash
    assert changed_revision.id != baseline.id
    assert changed_revision.report_hash != baseline.report_hash


def test_startup_snapshot_binds_readiness_and_research_identity_and_sections() -> None:
    profile = _profile()
    readiness = StartupReadinessService(clock=lambda: AS_OF).evaluate(
        profile,
        (),
        calculation_ids=(CALCULATION_ID,),
    )
    research = _market_research_snapshot(profile)
    report_input = replace(
        _input(),
        startup_readiness=readiness,
        startup_market_research=research,
    )

    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(report_input)

    methodology = str(snapshot.sections["methodology"])
    metrics = str(snapshot.sections["metrics"])
    competitors = str(snapshot.sections["competitors"])
    market_size = str(snapshot.sections["market_size"])
    assert str(readiness.snapshot_id) in methodology
    assert readiness.snapshot_hash in methodology
    assert str(research.snapshot_id) in methodology
    assert research.snapshot_hash in methodology
    assert readiness.metric_pack.pack_hash in metrics
    assert "blocked" in metrics
    assert "direct" in competitors
    assert "source_mode=frozen" in competitors
    assert "No cited numeric TAM/SAM/SOM inputs" in market_size
    assert "as_of=2026-07-20" in market_size


def test_startup_snapshot_identity_changes_with_readiness_or_research_identity() -> None:
    profile = _profile()
    baseline_readiness = StartupReadinessService(clock=lambda: AS_OF).evaluate(
        profile,
        (),
        calculation_ids=(CALCULATION_ID,),
    )
    changed_readiness = StartupReadinessService(
        clock=lambda: AS_OF + timedelta(seconds=1)
    ).evaluate(
        profile,
        (),
        calculation_ids=(CALCULATION_ID,),
    )
    research = _market_research_snapshot(profile)
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())

    baseline = builder.build(
        replace(
            _input(),
            startup_readiness=baseline_readiness,
            startup_market_research=research,
        )
    )
    changed = builder.build(
        replace(
            _input(),
            startup_readiness=changed_readiness,
            startup_market_research=research,
        )
    )

    assert changed_readiness.snapshot_hash != baseline_readiness.snapshot_hash
    assert changed.id != baseline.id
    assert changed.report_hash != baseline.report_hash


def test_startup_snapshot_binds_gtm_identity_and_changes_with_gtm_snapshot() -> None:
    profile = _profile()
    research = _market_research_snapshot(profile)
    baseline_gtm = _gtm_snapshot(profile, research)
    changed_gtm = _gtm_snapshot(
        profile,
        research,
        finding_ids=("finding-updated",),
    )
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())

    baseline = builder.build(
        replace(
            _input(),
            startup_market_research=research,
            startup_gtm=baseline_gtm,
        )
    )
    changed = builder.build(
        replace(
            _input(),
            startup_market_research=research,
            startup_gtm=changed_gtm,
        )
    )

    methodology = str(baseline.sections["methodology"])
    assert str(baseline_gtm.snapshot_id) in methodology
    assert baseline_gtm.snapshot_hash in methodology
    action_plan = baseline.sections["action_plan"]
    assert tuple(row[0] for row in action_plan["rows"]) == tuple(
        horizon.value for horizon in StartupGtmHorizon
    )
    assert all(
        f"gtm_snapshot_ref={baseline_gtm.snapshot_id}" in row
        and f"gtm_snapshot_hash={baseline_gtm.snapshot_hash}" in row
        and f"gtm_snapshot_revision={baseline_gtm.data_revision}" in row
        for row in action_plan["rows"]
    )
    founder_view = FounderStartupReportPresentationService().build(baseline)
    founder_action_plan = next(
        section for section in founder_view.main_sections if section.key == "action_plan"
    )
    assert tuple(item.split(" — ", 1)[0] for item in founder_action_plan.known_facts_ru) == (
        "7 дней",
        "30 дней",
        "60 дней",
        "90 дней",
    )
    founder_payload = founder_action_plan.model_dump_json()
    assert str(baseline_gtm.snapshot_id) not in founder_payload
    assert baseline_gtm.snapshot_hash not in founder_payload
    assert changed_gtm.snapshot_hash != baseline_gtm.snapshot_hash
    assert changed.id != baseline.id
    assert changed.report_hash != baseline.report_hash


def test_startup_snapshot_rejects_stale_or_mismatched_gtm_lineage() -> None:
    profile = _profile()
    research = _market_research_snapshot(profile)
    stale_gtm = _gtm_snapshot(profile, research, data_revision=2)
    mismatched_gtm = _gtm_snapshot(
        profile,
        research,
        profile_id=OTHER_CASE_ID,
    )
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())

    with pytest.raises(ReportValidationError, match="startup_report_gtm_stale"):
        builder.build(
            replace(
                _input(),
                startup_market_research=research,
                startup_gtm=stale_gtm,
            )
        )
    with pytest.raises(ReportValidationError, match="startup_report_gtm_profile_mismatch"):
        builder.build(
            replace(
                _input(),
                startup_market_research=research,
                startup_gtm=mismatched_gtm,
            )
        )


def test_startup_snapshot_rejects_mismatched_readiness_or_stale_research() -> None:
    profile = _profile()
    readiness = StartupReadinessService(clock=lambda: AS_OF).evaluate(
        _profile(case_id=OTHER_CASE_ID),
        (),
        calculation_ids=(),
    )
    research = _market_research_snapshot(profile)
    stale_research = StartupMarketResearchSnapshot.build(
        case_id=research.case_id,
        as_of=research.as_of,
        source_mode=research.source_mode,
        research_id=research.research_id,
        competitors=research.competitors,
        sources=research.sources,
        sentiment_signals=research.sentiment_signals,
        assumptions=research.assumptions,
        sizing=research.sizing,
        labels=research.labels,
        data_revision=2,
    )
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())

    with pytest.raises(ReportValidationError, match="startup_report_readiness_profile_mismatch"):
        builder.build(replace(_input(), startup_readiness=readiness))
    with pytest.raises(ReportValidationError, match="startup_report_market_research_stale"):
        builder.build(replace(_input(), startup_market_research=stale_research))


def test_startup_snapshot_rejects_cross_case_or_stale_profile() -> None:
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())

    with pytest.raises(ReportValidationError, match="cross_case_startup_profile_input"):
        builder.build(replace(_input(), startup_profile=_profile(case_id=OTHER_CASE_ID)))

    with pytest.raises(ReportValidationError, match="startup_report_profile_stale"):
        builder.build(replace(_input(), startup_profile=_profile(data_revision=2)))


def test_startup_snapshot_rejects_cross_case_inputs_and_excludes_private_raw_text() -> None:
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())
    mixed = replace(_input(), calculations=(_calculation(case_id=OTHER_CASE_ID),))

    with pytest.raises(ReportValidationError, match="cross_case_calculation_input"):
        builder.build(mixed)

    private_profile = _profile(
        fields={
            **_profile_fields(),
            StartupProfileFieldName.WEAKNESSES.value: _profile_field(
                StartupProfileFieldName.WEAKNESSES,
                RAW_SENTINEL,
            ),
        }
    )
    snapshot = builder.build(
        replace(
            _input(),
            startup_profile=private_profile,
            source_hashes={
                "private-path": "sha256:" + "a" * 64,
                RAW_SENTINEL: "sha256:" + "b" * 64,
            },
            trace_ids=("trace-startup-1", RAW_SENTINEL),
        )
    )

    serialized = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)
    assert RAW_SENTINEL not in serialized
    assert "pitch.pdf" not in serialized
    assert "founder@example.com" not in serialized
    assert "sk-live-secret" not in serialized


def test_startup_snapshot_preserves_safe_source_keys_and_redacts_unsafe_keys() -> None:
    market_source_id = uuid5(NAMESPACE_URL, "startup-report-market-source")
    safe_market_key = f"market-source-{market_source_id}"
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(
        replace(
            _input(),
            source_hashes={
                safe_market_key: "sha256:" + "a" * 64,
                "founder-notes": "sha256:" + "b" * 64,
                RAW_SENTINEL: "sha256:" + "c" * 64,
            },
        )
    )

    assert snapshot.source_hashes == {
        safe_market_key: "sha256:" + "a" * 64,
        "founder-notes": "sha256:" + "b" * 64,
        "source-redacted-8e028cfc2521baa7": "sha256:" + "c" * 64,
    }
    serialized = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)
    assert RAW_SENTINEL not in serialized
    assert "pitch.pdf" not in serialized
    assert "founder@example.com" not in serialized
    assert "sk-live-secret" not in serialized


def test_startup_snapshot_text_evidence_uses_hash_ref_not_raw_value() -> None:
    raw_text_fact = EvidenceFact(
        id=uuid5(NAMESPACE_URL, "startup-report-text-fact"),
        artifact_id=ARTIFACT_ID,
        name="founder_note",
        value=RAW_SENTINEL,
        value_type="text",
        unit=None,
        period=None,
        locator=SourceLocator(kind="startup_fact", value="founder_note", artifact_id=ARTIFACT_ID),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.80"),
        source_priority=2,
        extraction_method="startup-parser",
        supporting_text_hash="e" * 64,
        source_freshness_at=AS_OF,
        retrieved_at=AS_OF,
    )

    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(
        replace(_input(), facts=(_fact(), raw_text_fact))
    )

    metrics_text = str(snapshot.sections["metrics"])
    assert RAW_SENTINEL not in metrics_text
    assert "text_hash=" + "e" * 64 in metrics_text


def test_startup_snapshot_finding_claim_uses_refs_not_raw_value() -> None:
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(
        replace(_input(), findings=(_finding(claim=RAW_SENTINEL),))
    )

    serialized = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)
    assert str(FINDING_ID) in serialized
    assert "finding_ref=" in serialized
    assert "evidence_refs=" in serialized
    assert "calculation_refs=" in serialized
    assert RAW_SENTINEL not in serialized
    assert "pitch.pdf" not in serialized
    assert "founder@example.com" not in serialized
    assert "sk-live-secret" not in serialized


def test_startup_snapshot_rejects_non_canonical_source_hash_values() -> None:
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())

    with pytest.raises(ReportValidationError, match="invalid_source_hash"):
        builder.build(replace(_input(), source_hashes={"pitch-deck": RAW_SENTINEL}))


def test_startup_snapshot_redacts_unsafe_human_readable_report_labels() -> None:
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(
        replace(
            _input(),
            startup_claims=(_claim(normalized_name=RAW_SENTINEL, unit=RAW_SENTINEL),),
            facts=(_fact(name=RAW_SENTINEL, unit=RAW_SENTINEL, period=RAW_SENTINEL),),
            calculations=(
                _calculation(
                    metric_name=RAW_SENTINEL,
                    unit=RAW_SENTINEL,
                    period=RAW_SENTINEL,
                    formula_version=RAW_SENTINEL,
                ),
            ),
            findings=(_finding(category=RAW_SENTINEL),),
            contradictions=(
                _contradiction(
                    status=ContradictionStatus.OPEN,
                    explanation="safe explanation",
                    conflict_type=RAW_SENTINEL,
                ),
            ),
        )
    )
    service = ReportService(html_renderer=HtmlRenderer())
    output_dir = Path(".tmp-task2-core-testdirs") / uuid4().hex

    html = service.render_draft(snapshot, output_dir).html_path.read_text(encoding="utf-8")
    serialized = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)

    for rendered in (serialized, html):
        assert RAW_SENTINEL not in rendered
        assert "pitch.pdf" not in rendered
        assert "founder@example.com" not in rendered
        assert "sk-live-secret" not in rendered
    assert "redacted-label-sha256:" in serialized
    assert "redacted-label-sha256:" not in html


def test_founder_report_render_is_russian_actionable_and_keeps_canonical_snapshot(
    tmp_path: Path,
) -> None:
    document_block = EvidenceFact(
        id=uuid5(NAMESPACE_URL, "startup-report-document-block"),
        artifact_id=ARTIFACT_ID,
        name="document_text_block",
        value="raw extracted paragraph",
        value_type="text",
        unit=None,
        period=None,
        locator=SourceLocator(
            kind="startup_fact",
            value="document_text_block",
            artifact_id=ARTIFACT_ID,
        ),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.50"),
        source_priority=3,
        extraction_method="startup-parser",
        supporting_text_hash="f" * 64,
        source_freshness_at=AS_OF,
        retrieved_at=AS_OF,
    )
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(
        replace(_input(), facts=(_fact(), document_block))
    )
    canonical_before = startup_canonical_snapshot_json(snapshot)
    identity_before = (
        snapshot.case_id,
        snapshot.id,
        snapshot.report_hash,
        snapshot.data_revision,
    )

    draft = ReportService(html_renderer=HtmlRenderer()).render_draft(snapshot, tmp_path)
    html = draft.html_path.read_text(encoding="utf-8")

    assert '<html lang="ru">' in html
    assert "Отчёт для основателя" in html
    assert "Что уже известно" in html
    assert "Что добавить" in html
    assert "Что это откроет" in html
    assert "Предложения ИИ по улучшению" in html
    assert "Валовая маржа" in html
    assert "рекомендации, а не подтверждённые факты" in html.lower()
    assert "Техническая методология и источники" in html
    assert "<details" in html
    assert "MISSING" not in html
    assert "document_text_block" not in html
    assert "Provide primary support" not in html
    assert "evidence_refs=" not in html
    assert "calculation_ref=" not in html
    assert snapshot.report_hash not in html
    assert str(snapshot.id) not in html
    assert "sha256:" + "a" * 64 not in html
    assert RAW_SENTINEL not in html
    assert startup_canonical_snapshot_json(snapshot) == canonical_before
    assert (
        draft.snapshot.case_id,
        draft.snapshot.id,
        draft.snapshot.report_hash,
        draft.snapshot.data_revision,
    ) == identity_before


def test_founder_report_projection_reuses_advisor_cards_and_has_six_bounded_proposals() -> None:
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(_input())

    view = FounderStartupReportPresentationService().build(snapshot)

    assert tuple(section.key for section in view.main_sections) == STARTUP_REPORT_SECTION_KEYS[:12]
    assert view.data_revision == snapshot.data_revision
    assert view.metric_cards["gross_margin"].title_ru == "Валовая маржа"
    assert tuple(point.key for point in view.analytics.metric_points) == ("gross_margin",)
    assert view.analytics.metric_points[0].value == 0.72
    assert view.analytics.metric_points[0].unit == "ratio"
    assert tuple(proposal.target_area for proposal in view.improvement_proposals) == (
        "positioning",
        "monetization",
        "metrics",
        "gtm",
        "risk_reduction",
        "investor_readiness",
    )
    rendered_view = view.model_dump_json()
    assert "MISSING" not in rendered_view
    assert "document_text_block" not in rendered_view
    assert "sha256:" not in rendered_view
    assert str(snapshot.id) not in rendered_view
    assert snapshot.report_hash not in rendered_view


def test_founder_report_projection_surfaces_source_backed_direct_metric_facts() -> None:
    report_input = replace(
        _input(),
        calculations=(),
        facts=(
            _fact(name="monthly_recurring_revenue", value="27900000", unit="KZT", period="2026-07"),
            _fact(name="gross_margin", value="74", unit="percent", period="2026-Q2"),
            _fact(name="monthly_net_burn", value="22400000", unit="KZT/month", period="2026-07"),
            _fact(name="runway", value="7.8", unit="months", period="2026-07"),
        ),
    )
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(report_input)

    view = FounderStartupReportPresentationService().build(snapshot)

    assert tuple(view.metric_cards) == (
        "monthly_recurring_revenue",
        "gross_margin",
        "monthly_net_burn",
        "runway",
    )
    points = {point.key: point for point in view.analytics.metric_points}
    assert points["monthly_recurring_revenue"].value == 27900000.0
    assert points["monthly_recurring_revenue"].unit == "KZT"
    assert points["gross_margin"].value == 74.0
    assert points["gross_margin"].unit == "percent"
    assert points["monthly_net_burn"].value == 22400000.0
    assert points["monthly_net_burn"].unit == "KZT/month"
    assert points["runway"].value == 7.8
    assert points["runway"].unit == "months"
    rendered_view = view.model_dump_json()
    assert "evidence_ref=" not in rendered_view
    assert str(FACT_ID) not in rendered_view


def test_metric_fact_rows_carry_safe_status_confidence_and_no_private_lineage() -> None:
    mrr_fact_id = uuid5(NAMESPACE_URL, "startup-report-mrr-bank")
    text_fact_id = uuid5(NAMESPACE_URL, "startup-report-mrr-text")
    locator_value = RAW_SENTINEL
    report_input = replace(
        _input(),
        calculations=(),
        facts=(
            _fact(
                fact_id=mrr_fact_id,
                name="mrr",
                value="27900000",
                unit="KZT/month",
                period="2026-06",
                locator_value=locator_value,
                confidence=Decimal("0.91"),
            ),
            _fact(
                fact_id=text_fact_id,
                name="document_text_block",
                value=RAW_SENTINEL,
                value_type="text",
                unit=None,
                period=None,
                locator_value=locator_value,
                confidence=Decimal("0.60"),
            ),
        ),
        contradictions=(
            _contradiction(
                status=ContradictionStatus.OPEN,
                explanation=RAW_SENTINEL,
                fact_ids=(text_fact_id,),
            ),
        ),
    )

    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(report_input)

    metric_row = next(row for row in snapshot.sections["metrics"]["rows"] if row[0] == "mrr")
    assert "confidence=0.91" in metric_row
    assert "status=contradiction" in metric_row
    serialized = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)
    assert locator_value not in serialized
    assert "founder@example.com" not in serialized
    assert "sk-live-secret" not in serialized


def test_founder_report_projection_selects_direct_metrics_by_confidence_and_status() -> None:
    report_input = replace(
        _input(),
        calculations=(
            _calculation(metric_name="net_burn", unit="KZT/month", period="2026-06"),
        ),
        facts=(
            _fact(
                fact_id=uuid5(NAMESPACE_URL, "startup-report-mrr-crm"),
                name="mrr",
                value="28600000",
                unit="KZT/month",
                period="2026-06",
                confidence=Decimal("0.82"),
            ),
            _fact(
                fact_id=uuid5(NAMESPACE_URL, "startup-report-mrr-bank"),
                name="mrr",
                value="27900000",
                unit="KZT/month",
                period="2026-06",
                confidence=Decimal("0.91"),
            ),
            _fact(
                fact_id=uuid5(NAMESPACE_URL, "startup-report-margin-operational"),
                name="gross_margin",
                value="74",
                unit="percent",
                period="2026-Q2",
                confidence=Decimal("0.88"),
            ),
            _fact(
                fact_id=uuid5(NAMESPACE_URL, "startup-report-margin-loaded"),
                name="gross_margin",
                value="70",
                unit="percent",
                period="2026-Q2",
                confidence=Decimal("0.88"),
            ),
            _fact(
                fact_id=uuid5(NAMESPACE_URL, "startup-report-burn"),
                name="burn",
                value="22400000",
                unit="KZT/month",
                period="unknown",
                confidence=Decimal("0.80"),
            ),
            _fact(
                fact_id=uuid5(NAMESPACE_URL, "startup-report-runway"),
                name="runway",
                value="7.8",
                unit="months",
                period="2026-07",
                confidence=Decimal("0.84"),
            ),
        ),
        contradictions=(
            _contradiction(
                status=ContradictionStatus.OPEN,
                explanation="CRM and bank MRR differ.",
                fact_ids=(
                    uuid5(NAMESPACE_URL, "startup-report-mrr-crm"),
                    uuid5(NAMESPACE_URL, "startup-report-mrr-bank"),
                ),
            ),
        ),
    )
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(report_input)

    view = FounderStartupReportPresentationService().build(snapshot)

    points = {point.key: point for point in view.analytics.metric_points}
    assert points["mrr"].value == 27900000.0
    assert points["mrr"].status == "contradiction"
    assert "gross_margin" not in points
    assert points["burn"].value == 22400000.0
    assert points["burn"].period_ru is None
    assert points["burn"].status == "confirmed"
    assert points["runway"].value == 7.8
    assert points["runway"].status == "confirmed"
    assert points["net_burn"].status == "calculated"
    rendered_view = view.model_dump_json()
    assert "evidence_ref=" not in rendered_view
    assert "locator" not in rendered_view.lower()


def test_founder_report_projection_drops_bare_identifiers_from_allowlisted_profile_fields() -> None:
    raw_uuid = str(uuid5(NAMESPACE_URL, "startup-report-hostile-profile-id"))
    raw_hash = "f" * 64
    fields = _profile_fields()
    fields[StartupProfileFieldName.PROBLEM.value] = _profile_field(
        StartupProfileFieldName.PROBLEM,
        raw_uuid,
    )
    fields[StartupProfileFieldName.SOLUTION.value] = _profile_field(
        StartupProfileFieldName.SOLUTION,
        raw_hash,
    )
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(
        replace(_input(), startup_profile=_profile(fields=fields))
    )

    rendered_view = FounderStartupReportPresentationService().build(snapshot).model_dump_json()
    html = ReportService(html_renderer=HtmlRenderer()).render_html(snapshot)

    for rendered in (rendered_view, html):
        assert raw_uuid not in rendered
        assert raw_hash not in rendered


def test_founder_report_projection_shows_live_market_research_as_public_benchmarks() -> None:
    baseline = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(_input())
    sections = dict(baseline.sections)
    sections["competitors"] = {
        "title": "Competitors",
        "status": "SUPPORTED",
        "summary": "Competitors from live public research.",
        "rows": (
            (
                "Kazent",
                "direct",
                "inference",
                "confidence=0.82",
                "source_mode=live",
                "source_refs=live-source-1",
            ),
            (
                "Sigma Center",
                "indirect",
                "inference",
                "confidence=0.76",
                "source_mode=live",
                "source_refs=live-source-2",
            ),
            (
                "EDTECH.KZ",
                "category",
                "inference",
                "confidence=0.71",
                "source_mode=live",
                "source_refs=live-source-3",
            ),
        ),
        "items": (),
    }
    sections["market_size"] = {
        "title": "Market Size",
        "status": "PARTIAL",
        "summary": "Market context from live public research.",
        "rows": (
            (
                "tam",
                "inference",
                "250000",
                "students",
                "units",
                "as_of=2026-08-28",
                "source_mode=live",
                "formula=public-research-v1",
            ),
        ),
        "items": (),
    }
    snapshot = baseline.model_copy(update={"sections": sections})

    view_json = FounderStartupReportPresentationService().build(snapshot).model_dump_json()
    assert "Kazent" in view_json
    assert "Sigma Center" in view_json
    assert "EDTECH.KZ" in view_json
    assert "TAM: 250000 students" in view_json
    assert "Публичный ориентир" in view_json
    assert "Публичная гипотеза" in view_json
    assert "source_refs=" not in view_json
    assert "live-source-" not in view_json
    assert "source_mode=live" not in view_json
    assert "source_fact" not in view_json
    assert "HubSpot" not in view_json
    assert "Salesforce" not in view_json


def test_startup_snapshot_retains_public_benchmark_candidates_without_source_fact_promotion() -> None:
    profile = _profile()
    market_research = _live_market_research_with_public_benchmarks(profile)

    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(
        replace(_input(), startup_profile=profile, startup_market_research=market_research)
    )

    market_size = snapshot.sections["market_size"]
    serialized = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)
    founder_view = FounderStartupReportPresentationService().build(snapshot).model_dump_json()

    assert market_size["status"] == "PARTIAL"
    assert (
        "public_benchmark",
        "monthly_price",
        "Kazent",
        "37000..45000",
        "KZT",
        "month",
        "as_of=2026-08-28",
        "status=inference",
    ) in market_size["items"]
    assert (
        "public_benchmark",
        "monthly_price",
        "Sigma Center",
        "20000..52000",
        "KZT",
        "month",
        "as_of=2026-08-28",
        "status=inference",
    ) in market_size["items"]
    assert "provenance=source_fact" not in serialized
    assert "Kazent" in founder_view
    assert "Sigma Center" in founder_view
    assert "37,000..45,000 KZT/month" in founder_view
    assert "20,000..52,000 KZT/month" in founder_view
    assert "source_ref" not in founder_view
    assert "monthly_recurring_revenue" not in serialized
    assert "cash_balance" not in serialized
    assert "burn" not in serialized.casefold()
    assert "customers" not in serialized.casefold()
    assert "contracts" not in serialized.casefold()


def test_startup_snapshot_identity_includes_privacy_safe_contradictions() -> None:
    builder = StartupReportSnapshotBuilder(project_root=Path.cwd())
    baseline = builder.build(_input())
    open_contradiction = builder.build(
        replace(
            _input(),
            contradictions=(
                _contradiction(status=ContradictionStatus.OPEN, explanation=RAW_SENTINEL),
            ),
        )
    )
    accepted_contradiction = builder.build(
        replace(
            _input(),
            contradictions=(
                _contradiction(
                    status=ContradictionStatus.ACCEPTED_SOURCE,
                    explanation=RAW_SENTINEL,
                ),
            ),
        )
    )

    assert open_contradiction.id != baseline.id
    assert accepted_contradiction.id != open_contradiction.id
    assert accepted_contradiction.report_hash != open_contradiction.report_hash
    serialized = json.dumps(open_contradiction.model_dump(mode="json"), sort_keys=True)
    assert str(CONTRADICTION_ID) in serialized
    assert "contradiction_ref=" in serialized
    assert "metric_vs_claim" in serialized
    assert "open" in serialized
    assert RAW_SENTINEL not in serialized
    assert "pitch.pdf" not in serialized
    assert "founder@example.com" not in serialized
    assert "sk-live-secret" not in serialized


def test_founder_report_metric_points_distinguish_source_calculation_and_contradiction() -> None:
    direct_fact_id = uuid5(NAMESPACE_URL, "startup-report-fact-mrr-direct")
    conflicting_fact_id = uuid5(NAMESPACE_URL, "startup-report-fact-mrr-conflict")
    snapshot = StartupReportSnapshotBuilder(project_root=Path.cwd()).build(
        replace(
            _input(),
            facts=(
                _fact(
                    fact_id=direct_fact_id,
                    name="monthly_recurring_revenue",
                    value="27900000",
                    unit="KZT",
                    period="June 2026",
                    locator_value="mrr-bank-invoices",
                    confidence=Decimal("0.88"),
                ),
                _fact(
                    fact_id=conflicting_fact_id,
                    name="monthly_recurring_revenue",
                    value="28600000",
                    unit="KZT",
                    period="June 2026",
                    locator_value="mrr-crm",
                    confidence=Decimal("0.72"),
                ),
                _fact(
                    fact_id=uuid5(NAMESPACE_URL, "startup-report-fact-burn-direct"),
                    name="monthly_net_burn",
                    value="22400000",
                    unit="KZT/month",
                    period="June 2026",
                    locator_value="net-burn",
                    confidence=Decimal("0.82"),
                ),
            ),
            calculations=(
                _calculation(metric_name="gross_margin", unit="ratio", period="June 2026"),
            ),
            contradictions=(
                _contradiction(
                    status=ContradictionStatus.OPEN,
                    explanation="MRR CRM 28.6m conflicts with bank/invoices 27.9m.",
                    conflict_type="explicit_source_conflict_signal",
                    fact_ids=(direct_fact_id, conflicting_fact_id),
                ),
            ),
        )
    )

    view = FounderStartupReportPresentationService().build(snapshot)
    points = {point.key: point for point in view.analytics.metric_points}

    assert points["monthly_recurring_revenue"].status == "contradiction"
    assert points["monthly_recurring_revenue"].value == 27900000
    assert points["monthly_net_burn"].status == "confirmed"
    assert points["monthly_net_burn"].value == 22400000
    assert points["gross_margin"].status == "calculated"


@dataclass(frozen=True)
class _StartupReportFixtureInput:
    case: DueDiligenceCase
    startup_profile: StartupProfile
    startup_claims: tuple[StartupClaim, ...]
    facts: tuple[EvidenceFact, ...]
    calculations: tuple[Calculation, ...]
    findings: tuple[Finding, ...]
    contradictions: tuple[Contradiction, ...]
    source_hashes: dict[str, str]
    trace_ids: tuple[str, ...]
    startup_readiness: StartupReadinessSnapshot | None = None
    startup_market_research: StartupMarketResearchSnapshot | None = None
    startup_gtm: StartupGtmSnapshot | None = None


def _input() -> _StartupReportFixtureInput:
    return _StartupReportFixtureInput(
        case=_case(),
        startup_profile=_profile(),
        startup_claims=(_claim(),),
        facts=(_fact(),),
        calculations=(_calculation(),),
        findings=(_finding(),),
        contradictions=(),
        source_hashes={"pitch-deck": "sha256:" + "a" * 64},
        trace_ids=("trace-startup-1",),
    )


def _sha256_lf_normalized_file(path: Path) -> str:
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _market_research_snapshot(profile: StartupProfile) -> StartupMarketResearchSnapshot:
    adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(
        Path("tests/fixtures/startup_market_research_v1")
    )
    collected = adapter.collect(
        StartupResearchPlan(
            case_id=profile.case_id,
            source_mode=StartupResearchSourceMode.FROZEN,
            queries=("founder diligence market competitors",),
        )
    )
    return StartupMarketResearchSnapshot.build(
        case_id=collected.case_id,
        as_of=collected.as_of,
        source_mode=collected.source_mode,
        research_id=collected.research_id,
        competitors=collected.competitors,
        sources=collected.sources,
        sentiment_signals=collected.sentiment_signals,
        assumptions=collected.assumptions,
        sizing=collected.sizing,
        labels=collected.labels,
        data_revision=profile.data_revision,
    )


def _live_market_research_with_public_benchmarks(
    profile: StartupProfile,
) -> StartupMarketResearchSnapshot:
    collected = _market_research_snapshot(profile)
    source_ref = collected.sources[0].source_id
    source_url = str(collected.sources[0].source_url).rstrip("/")
    return StartupMarketResearchSnapshot.build(
        case_id=profile.case_id,
        as_of=datetime(2026, 8, 28, tzinfo=UTC),
        source_mode=StartupResearchSourceMode.LIVE,
        research_id=uuid5(NAMESPACE_URL, "startup-report-live-public-benchmarks"),
        competitors=collected.competitors,
        sources=collected.sources,
        sentiment_signals=collected.sentiment_signals,
        assumptions=collected.assumptions,
        sizing=None,
        labels=collected.labels,
        data_revision=profile.data_revision,
        public_benchmark_candidates=(
            StartupPublicBenchmarkCandidate(
                input_key="monthly_price",
                source_url=source_url,
                publisher="Kazent",
                publication_date=None,
                retrieval_date=datetime(2026, 8, 28, tzinfo=UTC).date(),
                as_of=datetime(2026, 8, 28, tzinfo=UTC).date(),
                source_class="public_price_page",
                confidence="medium",
                range_low=Decimal("37000"),
                range_high=Decimal("45000"),
                unit="KZT",
                period="month",
                formula="public price range",
                dependencies=("public landing page",),
                validation_plan="Confirm current public pricing before final use.",
                source_ref=source_ref,
                rationale="Public price benchmark, not private company revenue.",
            ),
            StartupPublicBenchmarkCandidate(
                input_key="monthly_price",
                source_url=source_url,
                publisher="Sigma Center",
                publication_date=None,
                retrieval_date=datetime(2026, 8, 28, tzinfo=UTC).date(),
                as_of=datetime(2026, 8, 28, tzinfo=UTC).date(),
                source_class="public_price_page",
                confidence="medium",
                range_low=Decimal("20000"),
                range_high=Decimal("52000"),
                unit="KZT",
                period="month",
                formula="public price range",
                dependencies=("public landing page",),
                validation_plan="Confirm current public pricing before final use.",
                source_ref=source_ref,
                rationale="Public price benchmark, not private company revenue.",
            ),
        ),
    )


def _gtm_snapshot(
    profile: StartupProfile,
    research: StartupMarketResearchSnapshot,
    *,
    data_revision: int | None = None,
    profile_id: UUID | None = None,
    finding_ids: tuple[str, ...] = (),
) -> StartupGtmSnapshot:
    return StartupGtmSnapshot.build(
        case_id=profile.case_id,
        profile_id=profile_id or profile.profile_id,
        product_validation_snapshot_id=uuid5(
            NAMESPACE_URL,
            "startup-report-product-validation",
        ),
        market_research_snapshot_id=research.snapshot_id,
        data_revision=data_revision or profile.data_revision,
        status=StartupGtmStatus.INSUFFICIENT,
        dimensions=tuple(
            StartupGtmDimension(
                name=name,
                status=StartupGtmDimensionStatus.MISSING,
                reason_code="evidence_missing",
                gap_code=f"{name.value}_missing",
            )
            for name in StartupGtmDimensionName
        ),
        launch_plan=(
            StartupGtmLaunchPhase(
                horizon=StartupGtmHorizon.DAY_7,
                experiment_codes=(StartupGtmExperimentCode.CLARIFY_AUDIENCE,),
            ),
            StartupGtmLaunchPhase(
                horizon=StartupGtmHorizon.DAY_30,
                experiment_codes=(StartupGtmExperimentCode.VALIDATE_CHANNEL,),
            ),
            StartupGtmLaunchPhase(
                horizon=StartupGtmHorizon.DAY_60,
                experiment_codes=(StartupGtmExperimentCode.VALIDATE_OFFER,),
            ),
            StartupGtmLaunchPhase(
                horizon=StartupGtmHorizon.DAY_90,
                experiment_codes=(StartupGtmExperimentCode.REVIEW_LAUNCH_EVIDENCE,),
            ),
        ),
        finding_ids=finding_ids,
        built_at=AS_OF,
    )


def _case(*, data_revision: int = 1) -> DueDiligenceCase:
    return DueDiligenceCase(
        case_id=CASE_ID,
        mode=AnalysisMode.STARTUP,
        entity_name="FounderCo",
        entity_identifier="founderco",
        jurisdiction="US",
        scope=("startup",),
        as_of=AS_OF,
        base_currency="USD",
        privacy_policy="startup-local@1",
        budget_policy="offline",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
        updated_at=AS_OF,
        workflow_version="startup-graph@1",
        data_revision=data_revision,
    )


def _claim(
    *,
    normalized_name: str = "arr",
    period: str | None = "Q2 2026",
    unit: str | None = "USD",
) -> StartupClaim:
    return StartupClaim(
        id=CLAIM_ID,
        case_id=CASE_ID,
        text_ref="c" * 64,
        text_hash="c" * 64,
        category=ClaimCategory.ARR,
        source_artifact_id=ARTIFACT_ID,
        locator=SourceLocator(kind="startup_claim", value="arr", artifact_id=ARTIFACT_ID),
        criticality=ClaimCriticality.CRITICAL,
        evidence_query="arr q2 2026",
        normalized_name=normalized_name,
        normalized_value=Decimal("1200000"),
        unit=unit,
        period=period,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.82"),
        extracted_at=AS_OF,
    )


def _fact(
    *,
    fact_id: UUID = FACT_ID,
    name: str = "arr",
    value: str = "1200000",
    value_type: str = "decimal",
    unit: str | None = "USD",
    period: str | None = "Q2 2026",
    locator_value: str = "arr",
    confidence: Decimal = Decimal("0.82"),
) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id,
        artifact_id=ARTIFACT_ID,
        name=name,
        value=Decimal(value) if value_type in {"decimal", "integer"} else value,
        value_type=value_type,
        unit=unit,
        period=period,
        locator=SourceLocator(kind="startup_fact", value=locator_value, artifact_id=ARTIFACT_ID),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=confidence,
        source_priority=1,
        extraction_method="startup-parser",
        supporting_text_hash="d" * 64,
        source_freshness_at=AS_OF,
        retrieved_at=AS_OF,
        metadata={"startup_claim_id": str(CLAIM_ID)},
    )


def _calculation(
    *,
    case_id: UUID = CASE_ID,
    metric_name: str = "gross_margin",
    unit: str = "ratio",
    period: str = "Q2 2026",
    formula_version: str = "startup-gross-margin@1",
) -> Calculation:
    return Calculation(
        id=CALCULATION_ID,
        case_id=case_id,
        metric_name=metric_name,
        formula_version=formula_version,
        input_fact_ids=(FACT_ID,),
        value=Decimal("0.72"),
        unit=unit,
        period=period,
        warnings=(),
        calculated_at=AS_OF,
        sensitivity=SensitivityClass.CONFIDENTIAL,
    )


def _finding(
    *,
    category: str = "risk",
    claim: str = "Revenue concentration remains unverified.",
) -> Finding:
    return Finding(
        id=FINDING_ID,
        case_id=CASE_ID,
        category=category,
        severity=FindingSeverity.MEDIUM,
        claim=claim,
        evidence_fact_ids=(FACT_ID,),
        calculation_ids=(CALCULATION_ID,),
        confidence=Decimal("0.55"),
        status=FindingStatus.REQUIRES_REVIEW,
        author_node="risk_analysis",
        author_model="startup-provider@fixture",
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
    )


def _contradiction(
    *,
    status: ContradictionStatus,
    explanation: str,
    conflict_type: str = "metric_vs_claim",
    fact_ids: tuple[UUID, ...] = (FACT_ID,),
) -> Contradiction:
    return Contradiction(
        id=CONTRADICTION_ID,
        case_id=CASE_ID,
        conflict_type=conflict_type,
        fact_ids=fact_ids,
        finding_ids=(FINDING_ID,),
        explanation=explanation,
        severity=FindingSeverity.HIGH,
        status=status,
        recommended_resolution=RAW_SENTINEL,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        detected_at=AS_OF,
    )


def _profile(
    *,
    case_id: UUID = CASE_ID,
    data_revision: int = 1,
    fields: dict[str, StartupProfileField] | None = None,
) -> StartupProfile:
    return StartupProfile.build(
        case_id=case_id,
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="deterministic-profile@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=data_revision,
        source_hashes={"pitch-deck": "sha256:" + "a" * 64},
        parse_outcomes={"pitch-deck": "parsed"},
        fields=fields or _profile_fields(),
        gap_codes=("market_size_missing",),
        contradiction_ids=(),
        case_revision_at=AS_OF,
    )


def _profile_fields() -> dict[str, StartupProfileField]:
    values = {
        StartupProfileFieldName.PROBLEM: "Manual diligence takes weeks",
        StartupProfileFieldName.SOLUTION: "Automated evidence-backed diligence",
        StartupProfileFieldName.COMPETITORS_MENTIONED: "Legacy advisory firms",
        StartupProfileFieldName.STRENGTHS: "Deterministic evidence lineage",
        StartupProfileFieldName.WEAKNESSES: "Early distribution",
        StartupProfileFieldName.ASSUMPTIONS: "Founder supplies primary evidence",
    }
    return {
        name.value: (
            _profile_field(name, values[name])
            if name in values
            else StartupProfileField(
                name=name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                values=(),
                confidence=Decimal("0"),
                reason_code=f"{name.value}_missing",
            )
        )
        for name in StartupProfileFieldName
    }


def _profile_field(name: StartupProfileFieldName, value: str) -> StartupProfileField:
    return StartupProfileField(
        name=name,
        status=StartupProfileFieldStatus.SOURCE_FACT,
        values=(value,),
        confidence=Decimal("0.91"),
        evidence_refs=(
            StartupProfileEvidenceRef(
                evidence_id=uuid5(NAMESPACE_URL, f"startup-report-profile-evidence:{name.value}"),
                artifact_id=ARTIFACT_ID,
                artifact_hash="sha256:" + "a" * 64,
                locator_hash="sha256:" + "f" * 64,
                field_name=name,
                confidence=Decimal("0.91"),
            ),
        ),
    )


def _profile_cells(section: object) -> set[tuple[str, str, str]]:
    assert isinstance(section, Mapping)
    rows = section["rows"]
    assert isinstance(rows, tuple)
    return {(str(row[0]), str(row[1]), str(row[2])) for row in rows}
