from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal, cast
from uuid import UUID, uuid5

from due_diligence_agent.application.services.startup_gtm_service import StartupGtmService
from due_diligence_agent.application.startup_cases import StartupGateConflict, StartupNotFound
from due_diligence_agent.domain.startup.assets import CaseAssetDraft
from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.gtm import (
    StartupGtmDimension,
    StartupGtmDimensionName,
    StartupGtmDimensionStatus,
)
from due_diligence_agent.domain.startup.scenario import (
    ScenarioInput,
    ScenarioKey,
    ScenarioMetric,
    StartupScenarioSet,
    StartupScenarioVariant,
)

CaseAssetType = Literal[
    "customer_interview_script",
    "pricing_experiment",
    "positioning_map",
    "weekly_funnel_template",
    "gtm_launch_pack",
]

_ASSET_NAMESPACE = UUID("b93e8e70-8a88-4434-88e6-4de27d2b9dd9")
_SUPPORTED_ASSETS: set[str] = {
    "customer_interview_script",
    "pricing_experiment",
    "positioning_map",
    "weekly_funnel_template",
    "gtm_launch_pack",
}


class CaseAssetService:
    def __init__(
        self,
        *,
        case_repository: Any,
        asset_repository: Any,
        scenario_repository: Any,
        scenario_service: Any | None = None,
        profile_repository: Any | None = None,
        gtm_query: Any | None = None,
        report_query: Any | None = None,
        report_repository: Any | None = None,
        event_sink: Any | None = None,
    ) -> None:
        self._cases = case_repository
        self._assets = asset_repository
        self._scenario_repository = scenario_repository
        self._scenario_service = scenario_service
        self._profiles = profile_repository
        self._gtm_query = gtm_query
        self._reports = report_query
        self._report_repository = report_repository
        self._event_sink = event_sink

    def generate(
        self,
        case_id: UUID,
        *,
        asset_type: CaseAssetType,
        selected_scenario_key: ScenarioKey,
        expected_case_revision: int,
        idempotency_key: str,
    ) -> CaseAssetDraft:
        if asset_type not in _SUPPORTED_ASSETS:
            raise StartupGateConflict("asset_type_unsupported")
        case = self._require_case(case_id)
        if case.data_revision != expected_case_revision:
            raise StartupGateConflict("case_revision_conflict")
        replay = _repo_get_by_idempotency(self._assets, case_id, idempotency_key)
        if replay is not None:
            if (
                replay.asset_key != asset_type
                or replay.selected_scenario_key != selected_scenario_key
                or replay.data_revision != expected_case_revision
            ):
                raise StartupGateConflict("idempotency_key_conflict")
            return replay
        scenario_set = self._scenario_set(case_id, expected_case_revision=expected_case_revision)
        if scenario_set.data_revision != expected_case_revision:
            raise StartupGateConflict("case_revision_conflict")
        if selected_scenario_key not in scenario_set.scenarios:
            raise StartupGateConflict("scenario_not_found")
        version = _next_version(self._assets.list_for_case(case_id), asset_type)
        body = _asset_markdown(
            case_name=str(getattr(case, "entity_name", case_id)),
            asset_type=asset_type,
            scenario_set=scenario_set,
            selected_scenario_key=selected_scenario_key,
            context=_asset_context(
                case_id=case_id,
                data_revision=expected_case_revision,
                profile_repository=self._profiles,
                gtm_query=self._gtm_query,
                report_query=self._reports,
                report_repository=self._report_repository,
            ),
        )
        draft = CaseAssetDraft(
            draft_id=_draft_id(
                case_id=case_id,
                data_revision=expected_case_revision,
                scenario_set_id=scenario_set.scenario_set_id,
                selected_scenario_key=selected_scenario_key,
                asset_key=asset_type,
                draft_version=version,
            ),
            case_id=case_id,
            data_revision=expected_case_revision,
            scenario_set_id=scenario_set.scenario_set_id,
            selected_scenario_key=selected_scenario_key,
            draft_version=version,
            asset_key=asset_type,
            status="draft",
            body_markdown=body,
            metadata={
                "scenario_set_id": str(scenario_set.scenario_set_id),
                "selected_scenario_key": selected_scenario_key,
                "asset_type": asset_type,
            },
            source_refs=_source_refs(scenario_set),
            dependency_refs=_dependency_refs(scenario_set),
        )
        try:
            saved = self._assets.save(
                draft,
                expected_revision=expected_case_revision,
                idempotency_key=idempotency_key,
            )
        except ValueError as exc:
            raise StartupGateConflict("case_revision_conflict") from exc
        self._append_success_event(saved)
        return cast(CaseAssetDraft, saved)

    def list(self, case_id: UUID) -> tuple[CaseAssetDraft, ...]:
        self._require_case(case_id)
        return tuple(self._assets.list_for_case(case_id))

    def data_revision(self, case_id: UUID) -> int:
        return int(self._require_case(case_id).data_revision)

    def get(self, case_id: UUID, asset_id: UUID) -> CaseAssetDraft:
        self._require_case(case_id)
        try:
            return cast(CaseAssetDraft, self._assets.get_for_case(case_id, asset_id))
        except KeyError as exc:
            raise StartupNotFound("asset_not_found") from exc

    def provenance_appendix(self, case_id: UUID, asset_id: UUID) -> str:
        draft = self.get(case_id, asset_id)
        return "\n".join(
            [
                "# Provenance appendix",
                "",
                f"- asset_key={draft.asset_key}",
                f"- status={draft.status}",
                f"- case_id={draft.case_id}",
                f"- data_revision={draft.data_revision}",
                f"- scenario_set_id={draft.scenario_set_id}",
                f"- selected_scenario_key={draft.selected_scenario_key}",
                f"- source_refs={','.join(str(item) for item in draft.source_refs) or 'none'}",
                f"- dependency_refs={','.join(str(item) for item in draft.dependency_refs) or 'none'}",
                "- validation=Draft asset only; validate against source facts before external use.",
            ]
        )

    def csv_content(self, case_id: UUID, asset_id: UUID) -> str | None:
        draft = self.get(case_id, asset_id)
        if draft.asset_key != "weekly_funnel_template":
            return None
        return _weekly_funnel_csv()

    def _scenario_set(self, case_id: UUID, *, expected_case_revision: int) -> StartupScenarioSet:
        try:
            current = cast(StartupScenarioSet, self._scenario_repository.get_current(case_id))
        except KeyError:
            if self._scenario_service is None:
                raise StartupGateConflict("scenario_set_missing")
            return cast(
                StartupScenarioSet,
                self._scenario_service.build(
                    case_id,
                    expected_case_revision=expected_case_revision,
                    idempotency_key=f"asset-scenario:{expected_case_revision}",
                ),
            )
        if current.data_revision == expected_case_revision:
            return current
        if self._scenario_service is None:
            raise StartupGateConflict("case_revision_conflict")
        return cast(
            StartupScenarioSet,
            self._scenario_service.build(
                case_id,
                expected_case_revision=expected_case_revision,
                idempotency_key=f"asset-scenario:{expected_case_revision}",
            ),
        )

    def _require_case(self, case_id: UUID) -> Any:
        try:
            return self._cases.get(case_id)
        except KeyError as exc:
            raise StartupNotFound("case_not_found") from exc

    def _append_success_event(self, draft: CaseAssetDraft) -> None:
        if self._event_sink is None:
            return
        append = getattr(self._event_sink, "append_case_asset_event", None)
        if callable(append):
            append(draft)


def _asset_markdown(
    *,
    case_name: str,
    asset_type: str,
    scenario_set: StartupScenarioSet,
    selected_scenario_key: ScenarioKey,
    context: dict[str, Any],
) -> str:
    selected = scenario_set.scenarios[selected_scenario_key]
    if asset_type != "gtm_launch_pack":
        return _base_asset_markdown(
            case_name=case_name,
            asset_type=asset_type,
            scenario_set=scenario_set,
            selected=selected,
        )
    sections = [
        ("Executive summary", _lineage(case_name, scenario_set, selected_scenario_key)),
        (
            "Problem / solution / ICP / buyer / purchase trigger",
            _profile_context_block(context),
        ),
        (
            "Value proposition and positioning",
            _positioning_context_block(context),
        ),
        (
            "Market, competitors, alternatives and citations",
            _market_context_block(context, scenario_set),
        ),
        (
            "Business model and public pricing",
            _business_model_context_block(context),
        ),
        ("Three-scenario unit economics", _scenario_comparison(scenario_set)),
        ("Experiments", _experiments_block()),
        (
            "Funnel and measurement",
            "Define visitor, signup, qualified conversation, pilot and paid conversion events before launch.",
        ),
        (
            "Strengths, weaknesses, risks and counter-thesis",
            _risk_context_block(context),
        ),
        ("7/30/60/90 actions", _launch_actions(context)),
        ("Validation backlog", _validation_backlog(selected, scenario_set)),
        (
            "Provenance, assumptions and limitations",
            "\n".join(
                _nonempty_lines(
                    _provenance_boundary(selected),
                    "",
                    _inputs_block(selected),
                    "",
                    _metrics_block(selected),
                    "",
                    _business_plan_context_appendix(context, selected),
                    "",
                    "Status: draft. This asset is not evidence and does not update source facts.",
                )
            ),
        ),
    ]
    return "\n\n".join(f"## {title}\n\n{body}" for title, body in sections)


def _base_asset_markdown(
    *,
    case_name: str,
    asset_type: str,
    scenario_set: StartupScenarioSet,
    selected: StartupScenarioVariant,
) -> str:
    template = _base_asset_body(asset_type, selected)
    return "\n\n".join(
        [
            f"## {asset_type.replace('_', ' ').title()}",
            f"Case: {case_name}",
            f"Scenario set: {scenario_set.scenario_set_id}",
            f"Selected scenario: {selected.scenario_key}",
            "Status: draft. This asset is not evidence.",
            "Validation plan: replace planning assumptions with confirmed source facts before external use.",
            template,
            "## Scenario metric provenance",
            _metrics_block(selected),
        ]
    )


def _base_asset_body(asset_type: str, selected: StartupScenarioVariant) -> str:
    metric_summary = _metrics_block(selected)
    if asset_type == "customer_interview_script":
        return (
            "## Pain validation interview script\n"
            "- Goal: validate pain frequency, current workaround, budget owner and purchase trigger.\n"
            "- Opening: confirm role, team size, current workflow and recent attempts to solve the problem.\n"
            "- Pain questions: When did this last happen? What did it cost? Who noticed? What breaks if nothing changes?\n"
            "- Solution questions: What would you try first? What evidence would make this worth a pilot?\n"
            "- Pricing signal: ask for current workaround cost, approval path and acceptable test budget.\n"
            "- Close: ask for one artifact or metric that can validate the claim.\n"
            "## Scenario metric anchor\n"
            f"{metric_summary}"
        )
    if asset_type == "pricing_experiment":
        return (
            "## Pricing hypothesis\n"
            "- Hypothesis: willingness-to-pay depends on measurable time saved, risk reduced or revenue protected.\n"
            "- Variants: free diagnostic, paid pilot, monthly team plan and usage-based add-on.\n"
            "- Segments: buyer, end user, budget owner and economic approver must be tracked separately.\n"
            "- Success criteria: qualified buyer accepts price range, pilot scope and next meeting.\n"
            "- Guardrails: do not use founder_statement, public_benchmark or ai_scenario as source_fact.\n"
            "- Stop rule: no price claim becomes evidence until validated by contract, invoice or explicit buyer confirmation.\n"
            "## Scenario metric anchor\n"
            f"{metric_summary}"
        )
    if asset_type == "positioning_map":
        return (
            "## Positioning comparison\n"
            "- Primary alternative: current manual/process workaround.\n"
            "- Direct alternatives: only list named competitors after source-backed confirmation.\n"
            "- Axes: time-to-value, workflow control, integration burden and buyer risk.\n"
            "- Claim discipline: mark unvalidated differentiation as draft hypothesis.\n"
            "- Validation: cite customer quote, public source or product evidence before external use.\n"
            "## Scenario metric anchor\n"
            f"{metric_summary}"
        )
    if asset_type == "weekly_funnel_template":
        return (
            "## Weekly funnel stages and definitions\n"
            "- Visitor: person or account exposed to the offer.\n"
            "- Signup: account that leaves contact details or starts onboarding.\n"
            "- Qualified conversation: buyer/user conversation matching ICP and pain trigger.\n"
            "- Pilot: scoped test with owner, timeline and success metric.\n"
            "- Paid conversion: signed, invoiced or otherwise source-backed payment signal.\n"
            "## Weekly input fields\n"
            "- week_start, visitors, signups, qualified_conversations, pilots_started, paid_conversions, notes, source_ref\n"
            "## Scenario metric anchor\n"
            f"{metric_summary}"
        )
    return "Unsupported base asset template."


def _weekly_funnel_csv() -> str:
    return "week_start,visitors,signups,qualified_conversations,pilots_started,paid_conversions,notes,source_ref\n,,,,,,,"


def _asset_context(
    *,
    case_id: UUID,
    data_revision: int,
    profile_repository: Any | None,
    gtm_query: Any | None,
    report_query: Any | None,
    report_repository: Any | None,
) -> dict[str, Any]:
    return {
        "profile": _current_projection(profile_repository, case_id, data_revision),
        "gtm": _current_projection(gtm_query, str(case_id), data_revision),
        "report": _current_report_projection(
            report_repository,
            report_query,
            case_id,
            data_revision,
        ),
    }


def _current_projection(
    repository: Any | None, case_id: UUID | str, data_revision: int
) -> Any | None:
    if repository is None:
        return None
    try:
        value = repository.get_current(case_id)
    except TypeError:
        try:
            value = repository.get_current(str(case_id))
        except (KeyError, AttributeError, TypeError):
            return None
    except (KeyError, AttributeError):
        current_snapshot = getattr(repository, "current_snapshot", None)
        if not callable(current_snapshot):
            return None
        try:
            value = current_snapshot(str(case_id))
        except (KeyError, TypeError):
            return None
    revision = getattr(value, "data_revision", data_revision)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision != data_revision:
        return None
    return value


def _current_report_projection(
    report_repository: Any | None,
    report_query: Any | None,
    case_id: UUID,
    data_revision: int,
) -> Any | None:
    if report_repository is not None:
        current_draft = getattr(report_repository, "get_current_draft", None)
        if callable(current_draft):
            try:
                value = current_draft(case_id)
            except (KeyError, TypeError, AttributeError):
                value = None
            if (
                value is not None
                and getattr(value, "data_revision", data_revision) == data_revision
            ):
                return value
        list_for_case = getattr(report_repository, "list_for_case", None)
        if callable(list_for_case):
            try:
                reports = tuple(list_for_case(case_id))
            except (KeyError, TypeError, AttributeError):
                reports = ()
            same_revision = [
                report
                for report in reports
                if getattr(report, "data_revision", None) == data_revision
            ]
            if same_revision:
                return max(
                    same_revision,
                    key=lambda report: getattr(report, "version", 0),
                )
    return _current_projection(report_query, str(case_id), data_revision)


def _profile_context_block(context: dict[str, Any]) -> str:
    profile = context.get("profile")
    if profile is None:
        return "Missing current profile projection. Validate problem, solution, ICP, buyer and purchase trigger before use."
    return "\n".join(
        [
            f"- Problem: {_profile_field(profile, 'problem')}",
            f"- Solution: {_profile_field(profile, 'solution')}",
            f"- ICP: {_profile_field(profile, 'icp')}",
            f"- Buyer: {_profile_field(profile, 'buyers')}",
            "- Purchase trigger: Missing current profile field; validate with buyer interviews.",
        ]
    )


def _positioning_context_block(context: dict[str, Any]) -> str:
    profile = context.get("profile")
    if profile is None:
        return "Missing current profile projection. Positioning remains a draft hypothesis until supported."
    return "\n".join(
        [
            f"- Value proposition: {_profile_field(profile, 'solution')}",
            f"- Alternative: {_profile_field(profile, 'competitors_mentioned')}",
        ]
    )


def _market_context_block(context: dict[str, Any], scenario_set: StartupScenarioSet) -> str:
    report = context.get("report")
    source_block = _source_block(scenario_set)
    if report is None:
        return f"Missing current report projection.\n\n{source_block}"
    market = _report_section_text(report, "market_size") or "Missing current market summary."
    return f"Market: {market}\n\n{source_block}"


def _business_model_context_block(context: dict[str, Any]) -> str:
    profile = context.get("profile")
    if profile is None:
        return "Missing current profile projection. Use only public_benchmark inputs or founder statements with visible provenance; do not relabel either as source_fact."
    return (
        f"Business model: {_profile_field(profile, 'pricing_revenue_model')}. "
        "Use only public_benchmark inputs or founder statements with visible provenance; do not relabel either as source_fact."
    )


def _risk_context_block(context: dict[str, Any]) -> str:
    report = context.get("report")
    if report is None:
        return "Missing current report projection. Counter-thesis: acquisition cost, willingness-to-pay or operational adoption may invalidate the selected scenario."
    risks = getattr(report, "risks", ()) or ()
    if not risks:
        risk_text = _report_section_text(report, "risks")
        risks = (risk_text,) if risk_text else ()
    if not risks:
        return "Risk: Missing current report risk projection."
    return "\n".join(f"- Risk: {risk}" for risk in risks)


def _profile_field(profile: Any, field_key: str) -> str:
    fields = getattr(profile, "fields", {})
    field = fields.get(field_key) if isinstance(fields, Mapping) else None
    values = getattr(field, "values", ()) if field is not None else ()
    if values:
        return str(next(iter(values)))
    return f"Missing current profile field: {field_key}"


def _profile_field_text(profile: Any, field_key: str) -> str:
    fields = getattr(profile, "fields", {})
    field = fields.get(field_key) if isinstance(fields, Mapping) else None
    values = getattr(field, "values", ()) if field is not None else ()
    if values:
        return " | ".join(str(value) for value in values)
    return f"Missing current profile field: {field_key}"


def _report_section_text(report: Any, section_key: str) -> str:
    sections = getattr(report, "sections", {})
    if not isinstance(sections, Mapping):
        return ""
    section = sections.get(section_key)
    if isinstance(section, str):
        return section
    if isinstance(section, Mapping):
        for key in ("summary_ru", "summary", "content", "text"):
            value = section.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _business_plan_context_appendix(
    context: dict[str, Any],
    selected: StartupScenarioVariant,
) -> str:
    profile = context.get("profile")
    report = context.get("report")
    pricing_economics = _contextual_pricing_economics(profile, selected)
    lead_economics = _contextual_lead_economics(profile, report)
    context_text = " ".join(
        item
        for item in (
            _profile_field_text(profile, "solution") if profile is not None else "",
            _profile_field_text(profile, "icp") if profile is not None else "",
            _profile_field_text(profile, "buyers") if profile is not None else "",
            _profile_field_text(profile, "pricing_revenue_model") if profile is not None else "",
            _profile_field_text(profile, "metric_pack_candidates") if profile is not None else "",
            _profile_field_text(profile, "assumptions") if profile is not None else "",
            _profile_field_text(profile, "weaknesses") if profile is not None else "",
            _report_section_text(report, "market_size") if report is not None else "",
            _report_section_text(report, "risks") if report is not None else "",
        )
        if item
    )
    normalized = context_text.casefold()
    has_housing_gate = "housing" in normalized or "общежит" in normalized or "жиль" in normalized
    has_rating_method = "rating" in normalized or "рейтинг" in normalized
    has_platform_market = any(
        marker in normalized
        for marker in (
            "platform",
            "платформ",
            "program discovery",
            "university",
            "students",
            "абитуриент",
            "студент",
        )
    )
    has_funding_or_forecast = any(
        marker in normalized
        for marker in ("round", "раунд", "forecast", "прогноз", "2027", "2031")
    )
    has_pricing_model = bool(
        pricing_economics
        and not pricing_economics.startswith("Missing current profile field:")
    )
    if not (
        has_housing_gate
        and has_rating_method
        and has_platform_market
        and has_funding_or_forecast
        and has_pricing_model
        and lead_economics
    ):
        return ""
    market_formula = _contextual_market_reconstruction(profile, report)
    assumptions = _profile_field_text(profile, "assumptions") if profile is not None else ""
    weaknesses = _profile_field_text(profile, "weaknesses") if profile is not None else ""
    risk_register = _contextual_risk_register(report)
    return "\n".join(
        [
            "### Business-plan context appendix",
            "",
            f"- Platform thesis: {_profile_field_text(profile, 'solution')}",
            f"- Market reconstruction: {market_formula}",
            f"- Pricing/tariff economics: {pricing_economics}",
            f"- Lead/conversion economics: {lead_economics}",
            f"- Rating methodology: {assumptions}",
            f"- B2B pilot plan: validate {_profile_field_text(profile, 'icp')} with {_profile_field_text(profile, 'buyers')} before scaling paid channels.",
            f"- Housing decision tree: keep the Housing Management vertical separate until {weaknesses}",
            f"- Tranche plan: {assumptions}",
            f"- Risk register: {risk_register}",
            "- Forecast guardrail: 2027-2031 revenue and EBITDA are forecasts; the planning years 2027, 2028, 2029, 2030 and 2031 must not be presented as actual operating performance.",
            "- Provenance appendix: keep uploaded-document claims, founder statements, public benchmarks and AI scenarios visibly labeled; forecasts remain forecasts.",
        ]
    )


def _contextual_pricing_economics(
    profile: Any,
    selected: StartupScenarioVariant,
) -> str:
    profile_pricing = (
        _profile_field_text(profile, "pricing_revenue_model") if profile is not None else ""
    )
    if profile_pricing and not profile_pricing.startswith("Missing current profile field:"):
        return profile_pricing
    public_price = selected.inputs.get("monthly_price")
    if (
        public_price is not None
        and public_price.provenance is CaseValueKind.PUBLIC_BENCHMARK
        and public_price.source_refs
    ):
        return _input_line(public_price).removeprefix("- ")
    return ""


def _contextual_lead_economics(profile: Any, report: Any) -> str:
    candidates = (
        _report_section_text(report, "market_size") if report is not None else "",
        _profile_field_text(profile, "metric_pack_candidates") if profile is not None else "",
        _profile_field_text(profile, "assumptions") if profile is not None else "",
    )
    markers = ("lead", "лид", "conversion", "конверс", "cac")
    for candidate in candidates:
        normalized = candidate.casefold()
        if candidate and any(marker in normalized for marker in markers):
            return candidate
    return ""


def _contextual_market_reconstruction(profile: Any, report: Any) -> str:
    profile_formula = (
        _profile_field_text(profile, "metric_pack_candidates") if profile is not None else ""
    )
    if profile_formula and not profile_formula.startswith("Missing current profile field:"):
        return profile_formula
    report_market = _report_section_text(report, "market_size") if report is not None else ""
    if report_market:
        return report_market
    return "Missing current profile field: metric_pack_candidates"


def _contextual_risk_register(report: Any) -> str:
    if report is not None:
        risk_text = _report_section_text(report, "risks")
        if risk_text:
            return risk_text
        risks = getattr(report, "risks", ()) or ()
        if risks:
            return "; ".join(str(risk) for risk in risks)
    return (
        "commercial traction, data freshness/SLA, rating anti-fraud and appeals, "
        "privacy/legal/tax, and housing legal/fire/sanitary gates."
    )


def _nonempty_lines(*lines: str) -> list[str]:
    result: list[str] = []
    for line in lines:
        if line or (result and result[-1]):
            result.append(line)
    while result and result[-1] == "":
        result.pop()
    return result


def _lineage(
    case_name: str, scenario_set: StartupScenarioSet, selected_scenario_key: ScenarioKey
) -> str:
    return "\n".join(
        [
            f"- case={case_name}",
            f"- case_id={scenario_set.case_id}",
            f"- data_revision={scenario_set.data_revision}",
            f"- scenario_set_id={scenario_set.scenario_set_id}",
            f"- selected_scenario_key={selected_scenario_key}",
        ]
    )


def _scenario_comparison(scenario_set: StartupScenarioSet) -> str:
    rows = ["| scenario | mrr | net_burn | runway |", "| --- | --- | --- | --- |"]
    for key in ("conservative", "base", "optimistic"):
        variant = scenario_set.scenarios[key]
        rows.append(
            "| "
            + " | ".join(
                [
                    key,
                    _metric_range(variant.metrics.get("mrr")),
                    _metric_range(variant.metrics.get("net_burn")),
                    _metric_range(variant.metrics.get("runway")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _metrics_block(variant: StartupScenarioVariant) -> str:
    return "\n".join(_metric_line(metric) for metric in variant.metrics.values())


def _metric_line(metric: ScenarioMetric) -> str:
    return (
        f"- {metric.metric_key}: range={_metric_range(metric)}; "
        f"provenance={metric.provenance.value}; formula={metric.formula_description}; "
        f"dependencies={_refs(metric.dependency_refs)}; source_refs={_refs(metric.source_refs)}; "
        f"validation_plan={metric.validation_plan}; what_would_confirm={metric.what_would_confirm}"
    )


def _inputs_block(variant: StartupScenarioVariant) -> str:
    return "\n".join(_input_line(item) for item in variant.inputs.values())


def _input_line(item: ScenarioInput) -> str:
    return (
        f"- {item.input_key}: range={item.value_range.lower}-{item.value_range.upper} {item.unit}/{item.period}; "
        f"provenance={item.provenance.value}; source_refs={_refs(item.source_refs)}; "
        f"dependencies={_refs(item.dependency_refs)}; validation_plan={item.validation_plan}"
    )


def _provenance_boundary(variant: StartupScenarioVariant) -> str:
    provenances = sorted({item.provenance.value for item in variant.inputs.values()})
    return (
        "Founder statements, public benchmarks, deterministic calculations and AI scenarios remain labeled as such. "
        f"Current selected-scenario input provenances: {', '.join(provenances)}."
    )


def _source_block(scenario_set: StartupScenarioSet) -> str:
    refs = _source_refs(scenario_set)
    if not refs:
        return "No source facts or cited public benchmarks are attached to this draft."
    return "\n".join(f"- {ref}" for ref in refs)


def _experiments_block() -> str:
    return (
        "- Interview the primary buyer and user separately.\n"
        "- Run a pricing analog desk-check before paid traffic.\n"
        "- Measure channel signal before scaling acquisition spend."
    )


def _launch_actions(context: dict[str, Any]) -> str:
    gtm = context.get("gtm")
    phases = tuple(getattr(gtm, "launch_plan", ()) or ()) if gtm is not None else ()
    prefix = "" if gtm is not None else "Missing current GTM projection.\n"
    if not phases:
        dimensions = tuple(
            StartupGtmDimension(
                name=name,
                status=StartupGtmDimensionStatus.MISSING,
                reason_code=f"missing_{name.value}",
                gap_code=f"gtm.missing:{name.value}",
            )
            for name in StartupGtmDimensionName
        )
        phases = StartupGtmService._launch_plan(dimensions)
    return "\n".join(
        [
            *([prefix.strip()] if prefix else []),
            *[
                f"- {phase.horizon.value}: {', '.join(code.value for code in phase.experiment_codes) or 'no_action'}"
                for phase in phases
            ],
        ]
    )


def _validation_backlog(selected: StartupScenarioVariant, scenario_set: StartupScenarioSet) -> str:
    lines = [
        f"- Scenario set validation: {scenario_set.validation_plan}",
        "- Regenerate after case revision, scenario selection, accepted public benchmark, or source-fact changes.",
    ]
    lines.extend(
        f"- {metric.metric_key}: {metric.validation_plan}" for metric in selected.metrics.values()
    )
    return "\n".join(lines)


def _metric_range(metric: ScenarioMetric | None) -> str:
    if metric is None or metric.value_range is None:
        return "missing"
    return f"{metric.value_range.lower}-{metric.value_range.upper} {metric.unit}/{metric.period}"


def _source_refs(scenario_set: StartupScenarioSet) -> tuple[UUID, ...]:
    return _unique_refs(
        [
            *[
                ref
                for scenario in scenario_set.scenarios.values()
                for item in scenario.inputs.values()
                for ref in item.source_refs
            ],
            *[
                ref
                for scenario in scenario_set.scenarios.values()
                for metric in scenario.metrics.values()
                for ref in metric.source_refs
            ],
        ]
    )


def _dependency_refs(scenario_set: StartupScenarioSet) -> tuple[UUID, ...]:
    return _unique_refs(
        [
            *[
                ref
                for scenario in scenario_set.scenarios.values()
                for item in scenario.inputs.values()
                for ref in item.dependency_refs
            ],
            *[
                ref
                for scenario in scenario_set.scenarios.values()
                for metric in scenario.metrics.values()
                for ref in metric.dependency_refs
            ],
        ]
    )


def _unique_refs(values: Iterable[UUID]) -> tuple[UUID, ...]:
    return tuple(sorted(set(values), key=str))


def _refs(values: tuple[UUID, ...]) -> str:
    return ",".join(str(item) for item in values) or "none"


def _next_version(existing: tuple[CaseAssetDraft, ...], asset_key: str) -> int:
    versions = [item.draft_version for item in existing if item.asset_key == asset_key]
    return max(versions, default=0) + 1


def _repo_get_by_idempotency(
    repository: Any, case_id: UUID, idempotency_key: str
) -> CaseAssetDraft | None:
    getter = getattr(repository, "get_by_idempotency", None)
    if getter is None:
        return None
    existing = getter(case_id, idempotency_key)
    if existing is None:
        return None
    return cast(CaseAssetDraft, existing)


def _draft_id(
    *,
    case_id: UUID,
    data_revision: int,
    scenario_set_id: UUID,
    selected_scenario_key: ScenarioKey,
    asset_key: str,
    draft_version: int,
) -> UUID:
    return uuid5(
        _ASSET_NAMESPACE,
        ":".join(
            [
                "asset-draft",
                str(case_id),
                str(data_revision),
                str(scenario_set_id),
                selected_scenario_key,
                asset_key,
                str(draft_version),
            ]
        ),
    )


__all__ = ["CaseAssetService", "CaseAssetType"]
