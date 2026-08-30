from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import platform
import re
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.application.services.report_canonical import (
    INTEGRITY_PREIMAGE_CONTRACT,
    STARTUP_REPORT_SCHEMA,
    STARTUP_REPORT_SECTION_KEYS,
    STARTUP_REPORT_TEMPLATE_VERSION,
    canonical_json,
    canonical_snapshot_report_json,
    current_git_commit,
    package_versions,
    sha256_file,
)
from due_diligence_agent.application.services.report_service import (
    ReportValidationError,
)
from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import AnalysisMode, ContradictionStatus, SensitivityClass
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import StartupClaim
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest
from due_diligence_agent.domain.startup.gtm import StartupGtmSnapshot
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupPublicBenchmarkCandidate,
    StartupResearchSourceStatus,
)
from due_diligence_agent.domain.startup.readiness import StartupReadinessSnapshot
from due_diligence_agent.ports.repositories import ApprovalRepository


_SAFE_SOURCE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,119}$")
_SAFE_UNIT_PATTERN = re.compile(r"^[A-Za-z0-9%._ -]{1,40}(?:/[A-Za-z0-9%._ -]{1,40})?$")


__all__ = [
    "STARTUP_REPORT_SECTION_KEYS",
    "STARTUP_REPORT_SCHEMA",
    "STARTUP_REPORT_TEMPLATE_VERSION",
    "StartupReportFreezeService",
    "StartupReportInput",
    "StartupReportProfileBindingError",
    "StartupReportSnapshotBuilder",
    "is_startup_report_snapshot",
    "startup_canonical_snapshot_json",
]


class StartupReportProfileBindingError(ReportValidationError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StartupReportInput(Protocol):
    @property
    def case(self) -> DueDiligenceCase: ...

    @property
    def startup_profile(self) -> StartupProfile: ...

    @property
    def startup_claims(self) -> Sequence[StartupClaim]: ...

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

    @property
    def startup_readiness(self) -> StartupReadinessSnapshot | None: ...

    @property
    def startup_market_research(self) -> StartupMarketResearchSnapshot | None: ...

    @property
    def startup_gtm(self) -> StartupGtmSnapshot | None: ...


class StartupReportSnapshotBuilder:
    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path.cwd()

    def build(self, report_input: StartupReportInput) -> ReportSnapshot:
        _validate_startup_input(report_input)
        case = report_input.case
        sections = _startup_sections(report_input)
        source_hashes = _safe_source_hashes(report_input.source_hashes)
        trace_ids = _safe_trace_ids(report_input.trace_ids)
        manifest = self._manifest(case)
        formula_versions = _formula_versions(report_input.calculations)
        preimage = canonical_json(
            {
                "schema": "startup_report_snapshot_integrity_preimage.v1",
                "case": case.model_dump(mode="json"),
                "case_snapshot_hash": _case_hash(case),
                "startup_profile": _startup_profile_identity(report_input.startup_profile),
                "startup_readiness": _startup_readiness_identity(
                    report_input.startup_readiness
                ),
                "startup_market_research": _startup_market_research_identity(
                    report_input.startup_market_research
                ),
                "startup_gtm": _startup_gtm_identity(report_input.startup_gtm),
                "source_hashes": source_hashes,
                "data_revision": case.data_revision,
                "as_of": case.as_of.isoformat(),
                "graph_version": case.workflow_version,
                "prompt_versions": {"report": STARTUP_REPORT_TEMPLATE_VERSION},
                "formula_versions": formula_versions,
                "model_versions": {"analysis": "offline"},
                "trace_ids": trace_ids,
                "reproducibility": manifest.model_dump(mode="json"),
                "sections": sections,
                "integrity_preimage_contract": INTEGRITY_PREIMAGE_CONTRACT,
            },
            sort_keys=False,
        )
        digest = sha256(preimage).hexdigest()
        snapshot_id = uuid5(NAMESPACE_URL, f"startup-report:{case.case_id}:{digest}")
        snapshot = ReportSnapshot(
            id=snapshot_id,
            case_id=case.case_id,
            report_hash=f"sha256:{digest}",
            case_snapshot_hash=_case_hash(case),
            source_hashes=source_hashes,
            as_of=case.as_of,
            graph_version=case.workflow_version,
            prompt_versions={"report": STARTUP_REPORT_TEMPLATE_VERSION},
            formula_versions=formula_versions,
            model_versions={"analysis": "offline"},
            trace_ids=trace_ids,
            sections=sections,
            data_revision=case.data_revision,
            json_artifact_ref="sha256:pending",
            html_artifact_ref=None,
            pdf_artifact_ref=None,
            content_hashes={},
            reproducibility=manifest,
            sensitivity=SensitivityClass.CONFIDENTIAL,
            created_at=case.as_of,
            version=1,
        )
        json_hash = sha256(startup_canonical_snapshot_json(snapshot)).hexdigest()
        return ReportSnapshot.model_validate(
            snapshot.model_dump(mode="json")
            | {
                "json_artifact_ref": f"sha256:{json_hash}",
                "content_hashes": {"json": f"sha256:{json_hash}"},
            }
        )

    def _manifest(self, case: DueDiligenceCase) -> ReproducibilityManifest:
        return ReproducibilityManifest(
            code_commit=current_git_commit(self._project_root),
            build_id="local-startup-report",
            dependency_lock_hash=f"sha256:{sha256_file(self._project_root / 'uv.lock')}",
            python_version=platform.python_version(),
            package_versions=package_versions(("pydantic", "jinja2", "weasyprint", "reportlab")),
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
                    / "startup_report.html.j2"
                ),
            },
            parser_versions={"report": "startup-report@1"},
            embedding_model_version="offline",
            index_version="none",
            redaction_policy_version=case.privacy_policy,
            locale="en-US",
            timezone="UTC",
            fx_source=case.base_currency,
            deterministic_seeds={"report": 1},
            configuration_hash=f"sha256:{sha256(case.model_dump_json().encode('utf-8')).hexdigest()}",
        )


class StartupReportFreezeService:
    def __init__(
        self,
        approval_repository: ApprovalRepository,
        *,
        current_data_revision: Callable[[UUID], int],
        clock: Callable[[], Any] | None = None,
    ) -> None:
        self._approval_repository = approval_repository
        self._current_data_revision = current_data_revision
        self._clock = clock or (lambda: __import__("datetime").datetime.now(UTC))

    def decide(
        self,
        snapshot: ReportSnapshot,
        *,
        action: str,
        snapshot_hash: str,
        snapshot_revision: int,
        actor: str = "founder",
        comment: str | None = None,
    ) -> Approval:
        if action not in {"approved", "rejected"}:
            raise ValueError("invalid_gate4_decision")
        if (
            snapshot_hash != snapshot.report_hash
            or snapshot_revision != snapshot.data_revision
            or self._current_data_revision(snapshot.case_id) != snapshot.data_revision
        ):
            raise ValueError("gate_4_snapshot_mismatch")
        decided_at = self._clock()
        approval = Approval(
            id=uuid5(
                NAMESPACE_URL,
                "|".join(
                    (
                        "startup-gate4",
                        str(snapshot.id),
                        action,
                        str(snapshot.report_hash),
                        str(snapshot.version),
                        str(snapshot.data_revision),
                        decided_at.isoformat(),
                    )
                ),
            ),
            case_id=snapshot.case_id,
            gate="gate_4",
            action=action,
            actor=actor,
            comment=comment,
            decided_at=decided_at,
            data_revision=snapshot.data_revision,
            subject_id=snapshot.id,
            subject_hash=snapshot.report_hash,
            subject_version=snapshot.version,
        )
        self._approval_repository.add(approval)
        return approval

    def latest_exact_decision(self, snapshot: ReportSnapshot) -> Approval | None:
        approvals = [
            approval
            for approval in self._approval_repository.list_for_case(snapshot.case_id)
            if _matches_gate4_subject(approval, snapshot)
        ]
        if not approvals:
            return None
        return max(approvals, key=lambda approval: (approval.decided_at, str(approval.id)))

    def is_approved(self, snapshot: ReportSnapshot) -> bool:
        if self._current_data_revision(snapshot.case_id) != snapshot.data_revision:
            return False
        latest = self.latest_exact_decision(snapshot)
        return latest is not None and latest.action == "approved"


def startup_canonical_snapshot_json(snapshot: ReportSnapshot) -> bytes:
    return canonical_snapshot_report_json(snapshot, schema=STARTUP_REPORT_SCHEMA, sort_keys=False)


def is_startup_report_snapshot(snapshot: ReportSnapshot) -> bool:
    return dict(snapshot.prompt_versions).get("report") == STARTUP_REPORT_TEMPLATE_VERSION


def _validate_startup_input(report_input: StartupReportInput) -> None:
    case = report_input.case
    if case.mode is not AnalysisMode.STARTUP:
        raise ReportValidationError("startup_mode_required")
    profile = report_input.startup_profile
    if profile.case_id != case.case_id:
        raise ReportValidationError("cross_case_startup_profile_input")
    if profile.data_revision != case.data_revision:
        raise ReportValidationError("startup_report_profile_stale")
    readiness = report_input.startup_readiness
    if readiness is not None and (
        readiness.profile_id != profile.profile_id
        or readiness.profile_hash != profile.profile_hash
        or readiness.profile_revision != profile.data_revision
    ):
        raise ReportValidationError("startup_report_readiness_profile_mismatch")
    research = report_input.startup_market_research
    if research is not None and research.case_id != case.case_id:
        raise ReportValidationError("startup_report_market_research_case_mismatch")
    if research is not None and research.data_revision != case.data_revision:
        raise ReportValidationError("startup_report_market_research_stale")
    gtm = report_input.startup_gtm
    if gtm is not None and gtm.case_id != case.case_id:
        raise ReportValidationError("startup_report_gtm_case_mismatch")
    if gtm is not None and gtm.data_revision != case.data_revision:
        raise ReportValidationError("startup_report_gtm_stale")
    if gtm is not None and gtm.profile_id != profile.profile_id:
        raise ReportValidationError("startup_report_gtm_profile_mismatch")
    if gtm is not None and research is None:
        raise ReportValidationError("startup_report_gtm_market_research_missing")
    if (
        gtm is not None
        and research is not None
        and gtm.market_research_snapshot_id != research.snapshot_id
    ):
        raise ReportValidationError("startup_report_gtm_market_research_mismatch")
    for claim in report_input.startup_claims:
        if claim.case_id != case.case_id:
            raise ReportValidationError("cross_case_startup_claim_input")
    for calculation in report_input.calculations:
        if calculation.case_id != case.case_id:
            raise ReportValidationError("cross_case_calculation_input")
    for finding in report_input.findings:
        if finding.case_id != case.case_id:
            raise ReportValidationError("cross_case_finding_input")
    for contradiction in report_input.contradictions:
        if contradiction.case_id != case.case_id:
            raise ReportValidationError("cross_case_contradiction_input")
    _safe_source_hashes(report_input.source_hashes)


def _startup_sections(report_input: StartupReportInput) -> dict[str, dict[str, object]]:
    profile = report_input.startup_profile
    claims = tuple(report_input.startup_claims)
    facts = tuple(report_input.facts)
    calculations = tuple(report_input.calculations)
    findings = tuple(report_input.findings)
    contradictions = tuple(report_input.contradictions)
    claim_rows = tuple(
        (
            _safe_report_label(claim.normalized_name),
            claim.category.value,
            _safe_report_label(claim.period, missing="MISSING"),
            _safe_report_label(claim.unit, missing="MISSING"),
            f"claim_ref={claim.id}",
            f"text_hash={claim.text_hash}",
        )
        for claim in claims
    )
    fact_rows = _safe_fact_rows(facts, contradictions)
    calculation_rows = tuple(
        (
            _safe_report_label(calculation.metric_name),
            str(calculation.value),
            _safe_report_unit(calculation.unit),
            _safe_report_label(calculation.period),
            _safe_report_label(calculation.formula_version),
            f"calculation_ref={calculation.id}",
        )
        for calculation in calculations
    )
    finding_rows = tuple(
        (
            _safe_report_label(finding.category),
            finding.severity.value,
            finding.status.value,
            f"finding_ref={finding.id}",
            "evidence_refs=" + ",".join(str(item) for item in finding.evidence_fact_ids),
            "calculation_refs=" + ",".join(str(item) for item in finding.calculation_ids),
        )
        for finding in findings
    )
    contradiction_rows = _safe_contradiction_rows(contradictions)
    summary_fields = _profile_fields(
        profile,
        StartupProfileFieldName.STARTUP_NAME,
        StartupProfileFieldName.ONE_LINE_DESCRIPTION,
        StartupProfileFieldName.BUSINESS_MODEL,
    )
    problem_solution_fields = _profile_fields(
        profile,
        StartupProfileFieldName.PROBLEM,
        StartupProfileFieldName.SOLUTION,
    )
    competitor_fields = _profile_fields(profile, StartupProfileFieldName.COMPETITORS_MENTIONED)
    strength_fields = _profile_fields(profile, StartupProfileFieldName.STRENGTHS)
    assumption_fields = _profile_fields(profile, StartupProfileFieldName.ASSUMPTIONS)
    weakness_fields = _profile_fields(profile, StartupProfileFieldName.WEAKNESSES)
    gtm_fields = _profile_fields(
        profile,
        StartupProfileFieldName.ICP,
        StartupProfileFieldName.USERS,
        StartupProfileFieldName.BUYERS,
        StartupProfileFieldName.GEOGRAPHY,
        StartupProfileFieldName.CHANNELS_GTM,
    )
    metric_fields = _profile_fields(
        profile,
        StartupProfileFieldName.TRACTION,
        StartupProfileFieldName.PRICING_REVENUE_MODEL,
        StartupProfileFieldName.METRIC_PACK_CANDIDATES,
    )
    profile_gap_items = _profile_gap_items(profile)
    readiness = report_input.startup_readiness
    market_research = report_input.startup_market_research
    gtm = report_input.startup_gtm
    readiness_question_items = _readiness_question_items(readiness)
    readiness_gap_items = _readiness_gap_items(readiness)
    return {
        "business_idea_summary": _section(
            "Business Idea Summary",
            f"{report_input.case.entity_name} is summarized from the persisted canonical startup profile and claims.",
            rows=_profile_rows(summary_fields) + claim_rows,
            status=_profile_section_status(summary_fields),
        ),
        "problem_solution": _section(
            "Problem / Solution",
            "Problem and solution are bound to the exact persisted startup profile.",
            rows=_profile_rows(
                problem_solution_fields,
                labels={
                    StartupProfileFieldName.PROBLEM: "problem_statement",
                    StartupProfileFieldName.SOLUTION: "solution",
                },
            ),
            status=_profile_section_status(problem_solution_fields),
        ),
        "market_size": _section(
            "Market Size",
            _market_size_summary(market_research),
            status=_market_size_status(market_research),
            rows=_market_size_rows(market_research),
            items=_market_size_items(market_research),
        ),
        "competitors": _section(
            "Competitors",
            _competitor_summary(market_research),
            rows=_profile_rows(
                competitor_fields,
                labels={StartupProfileFieldName.COMPETITORS_MENTIONED: "competitors"},
            )
            + _competitor_rows(market_research)
            + _sentiment_rows(market_research),
            status=_competitor_status(competitor_fields, market_research),
        ),
        "moat": _section(
            "Moat",
            "Strengths are profile-backed; unsupported moat claims remain explicit gaps.",
            rows=_profile_rows(
                strength_fields,
                labels={StartupProfileFieldName.STRENGTHS: "strengths"},
            ),
            status=_profile_section_status(strength_fields),
        ),
        "go_to_market": _section(
            "Go To Market",
            "GTM fields are read from the canonical profile without inventing missing channels or audiences.",
            rows=_profile_rows(gtm_fields),
            status=_profile_section_status(gtm_fields),
        ),
        "metrics": _section(
            "Metrics",
            "Persisted profile candidates, evidence facts, calculations, and readiness diagnostics are the only metric sources.",
            rows=_profile_rows(metric_fields)
            + fact_rows
            + calculation_rows
            + _readiness_rows(readiness),
            status=_profile_section_status(metric_fields),
        ),
        "financial_assumptions": _section(
            "Financial Assumptions",
            "Assumptions remain explicitly qualified unless supported by profile evidence and calculations.",
            rows=_profile_rows(
                assumption_fields,
                labels={StartupProfileFieldName.ASSUMPTIONS: "assumptions"},
            )
            + calculation_rows,
            status=_profile_section_status(assumption_fields),
        ),
        "risks": _section(
            "Risks",
            "Weaknesses, findings, and contradictions are all persisted and referenceable.",
            rows=_profile_rows(
                weakness_fields,
                labels={StartupProfileFieldName.WEAKNESSES: "weaknesses"},
            )
            + finding_rows
            + contradiction_rows,
            status=_profile_section_status(weakness_fields),
        ),
        "evidence_gaps": _section(
            "Evidence Gaps",
            "Canonical profile gaps and contradictions remain explicit and are never replaced by examples.",
            items=profile_gap_items
            + readiness_gap_items
            + tuple(f"Resolve contradiction {contradiction.id}." for contradiction in contradictions),
            status="MISSING" if profile_gap_items or readiness_gap_items else "SUPPORTED",
        ),
        "diligence_questions": _section(
            "Diligence Questions",
            "Questions target unsupported report sections and conflicting evidence.",
            items=tuple(f"Provide primary support for {item}." for item in profile_gap_items)
            + readiness_question_items,
        ),
        "action_plan": _section(
            "Action Plan",
            _gtm_action_plan_summary(gtm),
            rows=_gtm_action_plan_rows(gtm),
            items=_gtm_action_plan_items(gtm),
            status=_gtm_action_plan_status(gtm),
        ),
        "methodology": _section(
            "Methodology",
            "Deterministic startup report built from persisted claims, facts, calculations, findings, readiness, market research, GTM lineage, hashes, revisions, and trace ids.",
            rows=tuple((key, str(value)) for key, value in _startup_profile_identity(profile).items())
            + tuple(
                (key, str(value))
                for key, value in _startup_readiness_identity(readiness).items()
            )
            + tuple(
                (key, str(value))
                for key, value in _startup_market_research_identity(market_research).items()
            )
            + tuple(
                (key, str(value))
                for key, value in _startup_gtm_identity(gtm).items()
            ),
        ),
        "source_appendix": _section(
            "Source Appendix",
            "Source hashes and normalized locators are included without raw uploaded text or private paths.",
            rows=tuple((key, value) for key, value in _safe_source_hashes(report_input.source_hashes).items()),
        ),
    }


def _startup_profile_identity(profile: StartupProfile) -> dict[str, object]:
    return {
        "profile_id": str(profile.profile_id),
        "profile_hash": profile.profile_hash,
        "data_revision": profile.data_revision,
        "analysis_stage": profile.analysis_stage.value,
        "parent_profile_id": str(profile.parent_profile_id) if profile.parent_profile_id else None,
    }


def _startup_readiness_identity(readiness: StartupReadinessSnapshot | None) -> dict[str, object]:
    if readiness is None:
        return {"readiness_snapshot_id": "MISSING", "readiness_snapshot_hash": "MISSING"}
    return {
        "readiness_snapshot_id": str(readiness.snapshot_id),
        "readiness_snapshot_hash": readiness.snapshot_hash,
        "readiness_snapshot_revision": readiness.profile_revision,
        "readiness_metric_pack_hash": readiness.metric_pack.pack_hash,
    }


def _startup_market_research_identity(
    market_research: StartupMarketResearchSnapshot | None,
) -> dict[str, object]:
    if market_research is None:
        return {
            "market_research_snapshot_id": "MISSING",
            "market_research_snapshot_hash": "MISSING",
        }
    return {
        "market_research_snapshot_id": str(market_research.snapshot_id),
        "market_research_snapshot_hash": market_research.snapshot_hash,
        "market_research_snapshot_revision": market_research.data_revision,
        "market_research_source_mode": market_research.source_mode.value,
        "market_research_as_of": market_research.as_of.date().isoformat(),
    }


def _startup_gtm_identity(gtm: StartupGtmSnapshot | None) -> dict[str, object]:
    if gtm is None:
        return {
            "gtm_snapshot_id": "MISSING",
            "gtm_snapshot_hash": "MISSING",
        }
    return {
        "gtm_snapshot_id": str(gtm.snapshot_id),
        "gtm_snapshot_hash": gtm.snapshot_hash,
        "gtm_snapshot_revision": gtm.data_revision,
        "gtm_schema_version": gtm.schema_version,
        "gtm_status": gtm.status.value,
        "gtm_profile_id": str(gtm.profile_id),
        "gtm_product_validation_snapshot_id": str(
            gtm.product_validation_snapshot_id
        ),
        "gtm_market_research_snapshot_id": str(gtm.market_research_snapshot_id),
    }


def _gtm_action_plan_summary(gtm: StartupGtmSnapshot | None) -> str:
    if gtm is None:
        return (
            "Add audience, channel, offer, product-proof, and market evidence to build "
            "a bounded 7/30/60/90-day launch plan."
        )
    return (
        "The 7/30/60/90-day plan is projected from the canonical GTM snapshot; "
        "experiment codes are validation work, not claimed outcomes."
    )


def _gtm_action_plan_rows(
    gtm: StartupGtmSnapshot | None,
) -> tuple[tuple[str, ...], ...]:
    if gtm is None:
        return ()
    return tuple(
        (
            phase.horizon.value,
            "experiment_codes="
            + ",".join(code.value for code in phase.experiment_codes),
            f"gtm_snapshot_ref={gtm.snapshot_id}",
            f"gtm_snapshot_hash={gtm.snapshot_hash}",
            f"gtm_snapshot_revision={gtm.data_revision}",
        )
        for phase in gtm.launch_plan
    )


def _gtm_action_plan_items(gtm: StartupGtmSnapshot | None) -> tuple[str, ...]:
    if gtm is None:
        return (
            "Provide GTM evidence to derive the four launch horizons without invented targets.",
        )
    return tuple(
        f"{phase.horizon.value}:"
        + (",".join(code.value for code in phase.experiment_codes) or "no_experiment_assigned")
        for phase in gtm.launch_plan
    )


def _gtm_action_plan_status(gtm: StartupGtmSnapshot | None) -> str:
    if gtm is None or gtm.status.value == "insufficient":
        return "MISSING"
    if gtm.status.value == "contradicted":
        return "CONTRADICTION"
    if gtm.status.value == "partial":
        return "PARTIAL"
    return "SUPPORTED"


def _readiness_rows(readiness: StartupReadinessSnapshot | None) -> tuple[tuple[str, ...], ...]:
    if readiness is None:
        return ()
    rows: list[tuple[str, ...]] = [
        (
            "readiness_metric_pack",
            readiness.metric_pack.pack_hash,
            f"snapshot_ref={readiness.snapshot_id}",
            f"snapshot_hash={readiness.snapshot_hash}",
        )
    ]
    rows.extend(
        (
            _safe_report_label(dimension.metric_id),
            dimension.status.value,
            _safe_report_label(dimension.reason_code),
            f"dimension_ref={dimension.dimension_id}",
        )
        for dimension in readiness.metric_pack.dimensions
    )
    return tuple(rows)


def _readiness_gap_items(readiness: StartupReadinessSnapshot | None) -> tuple[str, ...]:
    if readiness is None:
        return ()
    return tuple(
        f"readiness:{dimension.metric_id}:{dimension.reason_code or dimension.status.value}"
        for dimension in readiness.metric_pack.dimensions
        if dimension.status.value != "ready"
    )


def _readiness_question_items(readiness: StartupReadinessSnapshot | None) -> tuple[str, ...]:
    if readiness is None:
        return ()
    return tuple(
        f"{question.question_code}: {_safe_report_value(question.text)}"
        for question in readiness.metric_pack.adaptive_questions
    )


def _market_size_summary(market_research: StartupMarketResearchSnapshot | None) -> str:
    if market_research is None:
        return "MISSING: insufficient evidence for market size; no TAM, SAM, or SOM is invented."
    if market_research.sizing is None:
        return (
            "No cited numeric TAM/SAM/SOM inputs; market sizing remains insufficient. "
            f"source_mode={market_research.source_mode.value}; as_of={_market_research_as_of(market_research)}."
        )
    return (
        "Market sizing is derived from bounded secondary research and explicit assumptions; "
        f"source_mode={market_research.source_mode.value}; as_of={_market_research_as_of(market_research)}."
    )


def _market_size_status(market_research: StartupMarketResearchSnapshot | None) -> str:
    if market_research is None or market_research.sizing is None:
        if market_research is not None and market_research.public_benchmark_candidates:
            return "PARTIAL"
        return "MISSING"
    estimates = (market_research.sizing.tam, market_research.sizing.sam, market_research.sizing.som)
    if all(estimate.level is StartupResearchSourceStatus.SOURCE_FACT for estimate in estimates):
        return "SUPPORTED"
    if any(estimate.value is not None for estimate in estimates):
        return "PARTIAL"
    return "MISSING"


def _market_size_rows(market_research: StartupMarketResearchSnapshot | None) -> tuple[tuple[str, ...], ...]:
    if market_research is None or market_research.sizing is None:
        return ()
    return tuple(
        (
            level_name,
            estimate.level.value,
            str(estimate.value) if estimate.value is not None else "MISSING",
            estimate.unit,
            estimate.currency,
            f"as_of={estimate.as_of.isoformat()}",
            f"source_mode={estimate.source_mode.value}",
            f"formula={estimate.formula_version}",
        )
        for level_name, estimate in (
            ("tam", market_research.sizing.tam),
            ("sam", market_research.sizing.sam),
            ("som", market_research.sizing.som),
        )
    )


def _market_size_items(market_research: StartupMarketResearchSnapshot | None) -> tuple[object, ...]:
    if market_research is None:
        return ("Ask founder for sourced TAM/SAM/SOM and bottom-up customer count support.",)
    public_benchmarks = _public_benchmark_items(market_research)
    items = tuple(
        f"assumption_ref={assumption.assumption_id}; status={assumption.status.value}; as_of={assumption.as_of.isoformat()}"
        for assumption in market_research.assumptions
    )
    if items or public_benchmarks:
        return items + public_benchmarks
    return (
        f"No cited numeric TAM/SAM/SOM inputs; source_mode={market_research.source_mode.value}; as_of={_market_research_as_of(market_research)}",
    )


def _public_benchmark_items(
    market_research: StartupMarketResearchSnapshot,
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        (
            "public_benchmark",
            _safe_report_label(candidate.input_key),
            _safe_report_label(candidate.publisher),
            _public_benchmark_value(candidate),
            _safe_report_unit(candidate.unit),
            _safe_report_label(candidate.period),
            f"as_of={candidate.as_of.isoformat()}",
            "status=inference",
        )
        for candidate in market_research.public_benchmark_candidates
    )


def _public_benchmark_value(candidate: StartupPublicBenchmarkCandidate) -> str:
    value = candidate.value
    if value is not None:
        return _safe_report_value(value)
    low = candidate.range_low
    high = candidate.range_high
    if low is None or high is None:
        return "MISSING"
    return f"{_safe_report_value(low)}..{_safe_report_value(high)}"


def _competitor_summary(market_research: StartupMarketResearchSnapshot | None) -> str:
    if market_research is None:
        return "Named competitors and alternatives come only from the canonical startup profile."
    return (
        "Competitors are grouped from bounded market research and canonical profile mentions; "
        f"source_mode={market_research.source_mode.value}; as_of={_market_research_as_of(market_research)}."
    )


def _competitor_rows(market_research: StartupMarketResearchSnapshot | None) -> tuple[tuple[str, ...], ...]:
    if market_research is None:
        return ()
    return tuple(
        (
            _safe_report_label(competitor.name),
            competitor.category.value,
            competitor.status.value,
            f"confidence={competitor.confidence}",
            f"source_mode={market_research.source_mode.value}",
            "source_refs=" + ",".join(str(source_id) for source_id in competitor.source_ids),
        )
        for competitor in market_research.competitors
    )


def _sentiment_rows(
    market_research: StartupMarketResearchSnapshot | None,
) -> tuple[tuple[str, ...], ...]:
    if market_research is None:
        return ()
    return tuple(
        (
            "sentiment",
            _safe_report_label(signal.subject),
            signal.sentiment.value,
            f"confidence={signal.polarity_confidence}",
            f"as_of={signal.as_of.date().isoformat()}",
            f"source_ref={signal.source_id}",
            f"source_mode={signal.source_mode.value}",
        )
        for signal in market_research.sentiment_signals
    )


def _competitor_status(
    fields: Sequence[StartupProfileField],
    market_research: StartupMarketResearchSnapshot | None,
) -> str:
    if market_research is not None and market_research.competitors:
        return "SUPPORTED"
    return _profile_section_status(fields)


def _market_research_as_of(market_research: StartupMarketResearchSnapshot) -> str:
    if market_research.sources:
        return max(source.as_of for source in market_research.sources).isoformat()
    return market_research.as_of.date().isoformat()


def _profile_fields(
    profile: StartupProfile,
    *names: StartupProfileFieldName,
) -> tuple[StartupProfileField, ...]:
    return tuple(profile.fields[name.value] for name in names)


def _profile_rows(
    fields: Sequence[StartupProfileField],
    *,
    labels: Mapping[StartupProfileFieldName, str] | None = None,
) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    safe_labels = labels or {}
    for field in fields:
        label = safe_labels.get(field.name, field.name.value)
        values = field.values or ("MISSING",)
        evidence_refs = ",".join(str(ref.evidence_id) for ref in field.evidence_refs) or "MISSING"
        contradiction_refs = ",".join(str(item) for item in field.contradiction_ids) or "MISSING"
        for value in values:
            rows.append(
                (
                    label,
                    field.status.value,
                    _safe_report_value(value),
                    f"confidence={field.confidence}",
                    f"evidence_refs={evidence_refs}",
                    f"reason_code={field.reason_code or 'MISSING'}",
                    f"contradiction_refs={contradiction_refs}",
                )
            )
    return tuple(rows)


def _profile_section_status(fields: Sequence[StartupProfileField]) -> str:
    statuses = {field.status for field in fields}
    if not statuses or statuses == {StartupProfileFieldStatus.INSUFFICIENT_DATA}:
        return "MISSING"
    if StartupProfileFieldStatus.CONTRADICTION in statuses:
        return "CONTRADICTION"
    if StartupProfileFieldStatus.INSUFFICIENT_DATA in statuses:
        return "PARTIAL"
    return "SUPPORTED"


def _profile_gap_items(profile: StartupProfile) -> tuple[str, ...]:
    explicit = tuple(_safe_report_label(code) for code in profile.gap_codes)
    missing_fields = tuple(
        f"{field.name.value}:{_safe_report_label(field.reason_code)}"
        for field in profile.fields.values()
        if field.status is StartupProfileFieldStatus.INSUFFICIENT_DATA
        and field.name.value not in profile.gap_codes
    )
    contradictions = tuple(f"profile_contradiction:{item}" for item in profile.contradiction_ids)
    return explicit + missing_fields + contradictions


def _section(
    title: str,
    summary: str,
    *,
    rows: Sequence[Sequence[object]] = (),
    items: Sequence[object] = (),
    status: str = "SUPPORTED",
) -> dict[str, object]:
    return {
        "title": title,
        "summary": summary,
        "status": status,
        "rows": tuple(tuple(str(cell) for cell in row) for row in rows),
        "items": tuple(items),
    }


def _safe_source_hashes(source_hashes: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in sorted(source_hashes.items(), key=lambda item: str(item[0]).casefold()):
        hash_ref = str(value)
        if not _is_sha256_ref(hash_ref):
            raise ReportValidationError("invalid_source_hash")
        source_key = str(key).strip().casefold()
        if not _SAFE_SOURCE_KEY_PATTERN.fullmatch(source_key):
            key_hash = sha256(str(key).encode("utf-8")).hexdigest()[:16]
            source_key = f"source-redacted-{key_hash}"
        result[source_key] = hash_ref
    return result or {"source-001": "sha256:" + "0" * 64}


def _safe_trace_ids(trace_ids: Sequence[str]) -> tuple[str, ...]:
    safe: list[str] = []
    for index, trace_id in enumerate(trace_ids, start=1):
        text = str(trace_id)
        if _looks_private(text):
            safe.append(f"trace-redacted-{index:03d}")
        else:
            safe.append(text)
    return tuple(safe)


def _looks_private(value: str) -> bool:
    lowered = value.casefold()
    return (
        "\\" in value
        or "/" in value
        or "@" in value
        or ".pdf" in lowered
        or "token" in lowered
        or "sk-" in lowered
    )


def _is_sha256_ref(value: str) -> bool:
    if not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def _formula_versions(calculations: Sequence[Calculation]) -> dict[str, str]:
    versions = {
        _safe_report_label(calculation.metric_name): _safe_report_label(calculation.formula_version)
        for calculation in calculations
    }
    return versions or {"none": "none"}


def _safe_fact_value(fact: EvidenceFact) -> str:
    if fact.value_type == "text":
        return f"text_hash={fact.supporting_text_hash or 'MISSING'}"
    return _safe_report_value(fact.value)


def _safe_fact_rows(
    facts: Sequence[EvidenceFact],
    contradictions: Sequence[Contradiction],
) -> tuple[tuple[str, ...], ...]:
    contradiction_fact_ids = _open_contradiction_fact_ids(contradictions)
    contradicted_text_locators = {
        locator_key
        for fact in facts
        if fact.value_type == "text" and fact.id in contradiction_fact_ids
        for locator_key in (_fact_locator_key(fact),)
        if locator_key is not None
    }
    rows: list[tuple[str, ...]] = []
    for fact in facts:
        locator_key = _fact_locator_key(fact)
        is_contradiction = fact.id in contradiction_fact_ids or (
            fact.value_type in {"decimal", "integer"} and locator_key in contradicted_text_locators
        )
        rows.append(
            (
                _safe_report_label(fact.name),
                _safe_fact_value(fact),
                _safe_report_unit(fact.unit),
                _safe_report_label(fact.period, missing="MISSING"),
                f"status={'contradiction' if is_contradiction else 'source_fact'}",
                f"confidence={_safe_confidence(fact.confidence)}",
                f"evidence_ref={fact.id}",
                f"supporting_hash={fact.supporting_text_hash or 'MISSING'}",
            )
        )
    return tuple(rows)


def _open_contradiction_fact_ids(contradictions: Sequence[Contradiction]) -> frozenset[UUID]:
    open_statuses = {
        ContradictionStatus.OPEN,
        ContradictionStatus.AWAITING_EVIDENCE,
        ContradictionStatus.UNRESOLVED,
    }
    return frozenset(
        fact_id
        for contradiction in contradictions
        if contradiction.status in open_statuses
        for fact_id in contradiction.fact_ids
    )


def _fact_locator_key(fact: EvidenceFact) -> tuple[str, str, str] | None:
    locator = fact.locator
    if not locator.kind or not locator.value:
        return None
    return (str(locator.kind), str(locator.value), str(locator.artifact_id))


def _safe_contradiction_rows(contradictions: Sequence[Contradiction]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        (
            _safe_report_label(contradiction.conflict_type),
            contradiction.severity.value,
            contradiction.status.value,
            f"contradiction_ref={contradiction.id}",
            "fact_refs=" + ",".join(str(fact_id) for fact_id in contradiction.fact_ids),
            "finding_refs=" + ",".join(str(finding_id) for finding_id in contradiction.finding_ids),
            f"resolved_by_approval_ref={contradiction.resolved_by_approval_id or 'MISSING'}",
        )
        for contradiction in contradictions
    )


def _safe_report_label(value: object | None, *, missing: str = "MISSING") -> str:
    if value is None:
        return missing
    text = str(value).strip()
    if not text:
        return missing
    if _looks_private(text) or len(text) > 80 or any(ord(character) < 32 for character in text):
        return f"redacted-label-sha256:{sha256(text.encode('utf-8')).hexdigest()[:16]}"
    return text


def _safe_report_value(value: object | None) -> str:
    if value is None:
        return "MISSING"
    text = str(value)
    if _looks_private(text) or len(text) > 160 or any(ord(character) < 32 for character in text):
        return f"redacted-value-sha256:{sha256(text.encode('utf-8')).hexdigest()[:16]}"
    return text


def _safe_report_unit(value: object | None) -> str:
    if value is None:
        return "MISSING"
    text = str(value).strip()
    if not text:
        return "MISSING"
    if _SAFE_UNIT_PATTERN.fullmatch(text):
        return text
    return _safe_report_label(value, missing="MISSING")


def _safe_confidence(value: Decimal) -> str:
    bounded = min(Decimal("1"), max(Decimal("0"), value))
    return format(bounded.normalize(), "f")


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


def _case_hash(case: DueDiligenceCase) -> str:
    return f"sha256:{sha256(case.model_dump_json().encode('utf-8')).hexdigest()}"
