from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.copilot import (
    CopilotActionKey,
    CopilotActionStatus,
    CopilotMessage,
    CopilotPayloadValue,
)
from due_diligence_agent.domain.startup.scenario import ScenarioKey, StartupScenarioVariant


class MoneyFactValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["money"]
    amount: Decimal | None = None
    scale: str | None = None
    currency: str | None = None


class TextFactValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"]
    value: str


TypedFactValue = Annotated[MoneyFactValue | TextFactValue, Field(discriminator="kind")]


class FactPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["month", "date", "range"]
    start: str | None = None
    end: str | None = None
    value: str | None = None


class FactSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CaseValueKind
    declared_source: str | None = None
    evidence_ref: UUID | None = None


class SaveFounderFactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_key: str
    value: TypedFactValue
    period: FactPeriod | None = None
    source: FactSource
    note: str | None = None
    resolves_contradiction_id: UUID | None = None
    expected_case_revision: StrictInt
    idempotency_key: str

    @field_validator("requirement_key", "idempotency_key", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("text value must be a string")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("text value must not be blank")
        return normalized


class SaveAssumptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_key: str
    value: TypedFactValue
    period: FactPeriod | None = None
    source: FactSource
    rationale: str
    validation_plan: str
    expected_case_revision: StrictInt
    idempotency_key: str


class PostCopilotMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    page_context: str = Field(min_length=1, max_length=120)
    current_section: str = Field(min_length=1, max_length=120)
    expected_case_revision: StrictInt
    focus_key: str | None = Field(default=None, min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=160)


class PrepareResearchPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: str = Field(min_length=1, max_length=160)
    intent: str = Field(min_length=1, max_length=1000)
    requested_private_value: str | None = Field(default=None, max_length=160)
    expected_case_revision: StrictInt


RequestedResearchAcquisitionMode = Literal[
    "deterministic_offline_fixture",
    "live_public_research",
]


class QueueResearchJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    plan_hash: str = Field(min_length=1, max_length=160)
    expected_case_revision: StrictInt
    idempotency_key: str = Field(min_length=1, max_length=160)
    consent_public_research: bool
    acquisition_mode: RequestedResearchAcquisitionMode | None = None
    retry_of_job_id: UUID | None = None


class SelectScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_set_id: UUID | None = None
    scenario_key: ScenarioKey
    expected_case_revision: StrictInt
    idempotency_key: str


class GenerateCaseAssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_type: Literal[
        "customer_interview_script",
        "pricing_experiment",
        "positioning_map",
        "weekly_funnel_template",
        "gtm_launch_pack",
    ]
    selected_scenario_key: ScenarioKey
    expected_case_revision: StrictInt
    idempotency_key: str = Field(min_length=1, max_length=160)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def normalize_idempotency_key(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("idempotency_key must be a string")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("idempotency_key must not be blank")
        return normalized


class FieldErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    message: str


class FactProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str
    value: str
    source_type: CaseValueKind


class GapProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_code: str
    field_key: str
    privacy_class: str
    allowed_action: str


class ScenarioMetricProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_key: str
    label: str
    source_type: CaseValueKind
    value: None = None
    range: dict[str, str | None]
    formula: str
    dependencies: list[str]
    unit: str
    period: str
    confidence: str
    source_refs: list[str]
    what_would_confirm: str
    validation_plan: str


class CoverageProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measure: str
    status: str
    source_fact_count: int | None = None
    accepted_input_count: int | None = None


class AcceptedInputProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str
    kind: CaseValueKind
    status: str
    value: str
    period: str | None = None
    rationale: str | None = None
    validation_plan: str | None = None
    declared_source: str | None = None
    source_refs: tuple[UUID, ...] = Field(default_factory=tuple)


class ActionAvailabilityProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: UUID
    action: CopilotActionKey
    status: CopilotActionStatus
    handler: str | None = None
    reason: str | None = None
    effect_preview: str
    payload: dict[str, CopilotPayloadValue] = Field(default_factory=dict)

    @field_validator("handler", "reason", "effect_preview", mode="before")
    @classmethod
    def normalize_optional_action_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("action text must be a string")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("action text must not be blank")
        return normalized

    @model_validator(mode="after")
    def enforce_action_contract(self) -> "ActionAvailabilityProjection":
        if self.status == "blocked":
            if self.handler is not None:
                raise ValueError("blocked actions must not expose a handler")
            if self.reason is None:
                raise ValueError("blocked actions require a reason")
        else:
            if self.handler is None:
                raise ValueError("executable actions require a handler")
            if self.status in {"requires_input", "requires_consent"} and self.reason is None:
                raise ValueError("gated actions require a reason")
        _validate_action_semantics(self)
        return self


class QuestionInputFieldProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str
    label: str
    input_kind: Literal["text", "decimal", "select", "month"]
    required: bool
    placeholder: str | None = None


class QuestionInputSchemaProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "money"]
    fields: tuple[QuestionInputFieldProjection, ...]


class CaseQuestionDescriptorProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: UUID
    field_key: str
    question: str
    label: str
    description: str
    why_needed: str
    unlocks: tuple[str, ...] = Field(default_factory=tuple)
    unlocks_copy: str
    example: str
    validation_guidance: str
    provenance: Literal[CaseValueKind.FOUNDER_STATEMENT]
    input_schema: QuestionInputSchemaProjection


_PUBLIC_RESEARCH_FOCUS_KEYS = {
    "market",
    "icp",
    "competitors",
    "alternatives",
    "channels",
    "public_pricing_analogs",
    "unit_economics_benchmarks",
    "regulatory_context",
}
_PRIVATE_FACT_INPUT_KEYS = {
    "problem",
    "solution",
    "icp",
    "buyer",
    "purchase_trigger",
    "pricing_revenue_model",
    "monthly_price",
    "launch_date",
    "team_capacity",
    "available_budget",
    "channel",
    "funnel",
    "revenue",
    "burn",
    "cogs",
    "gross_margin",
    "cac",
    "churn",
    "retention",
    "time_to_value",
    "monthly_recurring_revenue",
    "monthly_net_burn",
    "cash_balance",
    "customer_count",
    "mrr",
    "net_burn",
}


def _validate_action_semantics(action: ActionAvailabilityProjection) -> None:
    if action.action == "open_fact_input":
        _require_action_shape(
            action,
            status="requires_input",
            handler="openFactInput",
            payload_keys={"field_key", "provenance"},
        )
        field_key = _require_nonblank_string(action.payload.get("field_key"), "field_key")
        if field_key not in _PRIVATE_FACT_INPUT_KEYS:
            raise ValueError("open_fact_input field_key must be an approved private metric")
        if action.payload.get("provenance") != CaseValueKind.FOUNDER_STATEMENT.value:
            raise ValueError("open_fact_input provenance must be founder_statement")
    elif action.action == "open_document_upload":
        _require_action_shape(
            action,
            status="available",
            handler="openDocumentUpload",
            payload_keys={"case_id"},
        )
        case_id = _require_nonblank_string(action.payload.get("case_id"), "case_id")
        UUID(case_id)
    elif action.action == "prepare_public_research":
        _require_action_shape(
            action,
            status="requires_consent",
            handler="prepareResearchPlan",
            payload_keys={
                "focus",
                "expected_case_revision",
                "available_acquisition_modes",
                "unavailable_acquisition_modes",
                "default_acquisition_mode",
            },
        )
        focus = _require_nonblank_string(action.payload.get("focus"), "focus")
        if focus not in _PUBLIC_RESEARCH_FOCUS_KEYS:
            raise ValueError("prepare_public_research focus is not approved for public research")
        expected_revision = action.payload.get("expected_case_revision")
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("prepare_public_research expected_case_revision must be an int >= 1")
        available_modes = action.payload.get("available_acquisition_modes")
        unavailable_modes = action.payload.get("unavailable_acquisition_modes")
        default_mode = action.payload.get("default_acquisition_mode")
        if not isinstance(available_modes, tuple) or not all(
            mode in {"deterministic_offline_fixture", "live_public_research"}
            for mode in available_modes
        ):
            raise ValueError("prepare_public_research available_acquisition_modes are invalid")
        if not isinstance(unavailable_modes, tuple) or not all(
            mode in {"deterministic_offline_fixture", "live_public_research"}
            for mode in unavailable_modes
        ):
            raise ValueError("prepare_public_research unavailable_acquisition_modes are invalid")
        if set(available_modes).intersection(unavailable_modes):
            raise ValueError("prepare_public_research acquisition modes cannot overlap")
        if set(available_modes).union(unavailable_modes) != {
            "deterministic_offline_fixture",
            "live_public_research",
        }:
            raise ValueError("prepare_public_research acquisition modes must be exhaustive")
        if available_modes and default_mode not in available_modes:
            raise ValueError("prepare_public_research default_acquisition_mode must be available")
        if not available_modes and default_mode not in unavailable_modes:
            raise ValueError("prepare_public_research default_acquisition_mode must be declared")
    elif action.action == "explain_metric":
        _require_action_shape(
            action,
            status="available",
            handler="openMetricExplanation",
            payload_keys={"metric_key"},
        )
        _require_nonblank_string(action.payload.get("metric_key"), "metric_key")
    elif action.action == "navigate":
        _require_action_shape(
            action,
            status="available",
            handler="navigate",
            payload_keys={"target"},
        )
        if action.payload.get("target") != "scenarios":
            raise ValueError("navigate target must be scenarios")
    elif action.action == "prepare_asset":
        _require_action_shape(
            action,
            status="blocked",
            handler=None,
            payload_keys={"required_step"},
        )
        if action.payload.get("required_step") != "review_scenarios":
            raise ValueError("prepare_asset required_step must be review_scenarios")
    elif action.action == "review_improvements":
        _require_review_improvements_shape(action)


def _require_action_shape(
    action: ActionAvailabilityProjection,
    *,
    status: CopilotActionStatus,
    handler: str | None,
    payload_keys: set[str],
) -> None:
    if action.status != status:
        raise ValueError(f"{action.action} status must be {status}")
    if action.handler != handler:
        raise ValueError(f"{action.action} handler is invalid")
    if set(action.payload) != payload_keys:
        raise ValueError(f"{action.action} payload keys are invalid")


def _require_review_improvements_shape(action: ActionAvailabilityProjection) -> None:
    if set(action.payload) != {"same_case_fact_count"}:
        raise ValueError("review_improvements payload keys are invalid")
    fact_count = action.payload.get("same_case_fact_count")
    if type(fact_count) is not int or fact_count < 0:
        raise ValueError("review_improvements same_case_fact_count must be an int >= 0")
    if action.status == "available":
        if fact_count < 2:
            raise ValueError("review_improvements cannot be available below two same-case facts")
        if action.handler != "openImprovementReview":
            raise ValueError("review_improvements available handler is invalid")
        if action.reason is not None:
            raise ValueError("review_improvements available reason must be absent")
    elif action.status == "blocked":
        if fact_count >= 2:
            raise ValueError("review_improvements cannot be blocked with enough same-case facts")
        if action.handler is not None:
            raise ValueError("review_improvements blocked handler must be absent")
        if action.reason is None:
            raise ValueError("review_improvements blocked reason is required")
    else:
        raise ValueError("review_improvements status is invalid")


def _require_nonblank_string(value: CopilotPayloadValue | None, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    return normalized


class CopilotStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    data_revision: int
    stage: str
    next_question: str | None
    question_descriptor: CaseQuestionDescriptorProjection | None = None
    suggested_action: str
    selected_scenario_key: ScenarioKey
    extracted_facts: list[FactProjection]
    prioritized_gaps: list[GapProjection]
    scenario_metrics: list[ScenarioMetricProjection]
    fact_coverage: CoverageProjection
    scenario_completeness: CoverageProjection
    accepted_inputs: list[AcceptedInputProjection]
    actions: list[ActionAvailabilityProjection]


class CopilotThreadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: UUID
    case_id: UUID
    data_revision: int
    messages: tuple[CopilotMessage, ...]


class CopilotTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    data_revision: int
    thread_id: UUID
    page_context: str
    current_section: str
    status: Literal["accepted"]
    message: str
    available_actions: list[ActionAvailabilityProjection]


CopilotMessageResponse = CopilotTurnResponse


class CaseMutationDeltaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    old_revision: int
    new_revision: int
    changed_keys: tuple[str, ...]
    stale_scenario_ids: tuple[UUID, ...]
    stale_report_ids: tuple[UUID, ...]
    metric_before: dict[str, str]
    metric_after: dict[str, str]
    readiness_before: dict[str, int]
    readiness_after: dict[str, int]
    next_question: dict[str, Any] | str | None = None
    validation_errors: tuple[FieldErrorResponse, ...]
    original_draft: str | None = None


class FactMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    accepted: bool
    provenance: CaseValueKind
    source_type: CaseValueKind
    old_revision: int
    new_revision: int
    changed_keys: tuple[str, ...]
    delta: CaseMutationDeltaResponse


class AssumptionOutcomeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    status: Literal["accepted", "blocked"]
    provenance: CaseValueKind
    reason: str | None
    old_revision: int
    new_revision: int
    delta: CaseMutationDeltaResponse | None = None
    accepted_input: AcceptedInputProjection | None = None


class ScenarioProjectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_set_id: UUID
    case_id: UUID
    data_revision: int
    selected_scenario_key: ScenarioKey
    scenarios: dict[ScenarioKey, StartupScenarioVariant]
    fact_coverage: CoverageProjection
    scenario_completeness: CoverageProjection


class ScenarioSelectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    data_revision: int
    scenario_set_id: UUID
    old_scenario_key: ScenarioKey
    new_scenario_key: ScenarioKey
    changed_keys: tuple[str, ...]


class CaseAssetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    data_revision: int
    scenario_set_id: UUID
    selected_scenario_key: ScenarioKey
    asset_id: UUID
    asset_key: str
    asset_revision: int
    status: Literal["draft"]
    markdown_url: str
    csv_url: str | None = None
    provenance_appendix_url: str
    body_markdown: str


class CaseAssetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    data_revision: int
    assets: tuple[CaseAssetResponse, ...]


class ResearchPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    data_revision: int
    status: Literal["prepared"]
    plan_id: UUID
    plan_hash: str
    focus: str
    query_previews: tuple[str, ...]
    manual_only_keys: tuple[str, ...]
    consent_text: str
    created_at: datetime
    expires_at: datetime


class ResearchBenchmarkEntryProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: UUID
    provenance: Literal[CaseValueKind.PUBLIC_BENCHMARK]
    input_key: str
    url: str
    publisher: str
    publication_date: str | None
    retrieval_date: str
    as_of: str
    source_class: str
    confidence: Literal["low", "medium", "high"]
    value: str | None
    range: dict[str, str | None]
    unit: str
    period: str
    formula: str
    dependencies: list[str]
    validation_plan: str
    source_refs: list[str]


class ResearchRejectedEntryProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rejected_id: UUID
    reason_code: str
    input_key: str | None = None
    provenance: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


ResearchAcquisitionMode = Literal[
    "deterministic_offline_fixture",
    "live_public_research",
    "provider_unconfigured",
]


class ResearchJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    data_revision: int
    job_id: UUID
    plan_id: UUID | None
    plan_hash: str | None
    status: Literal["queued", "running", "completed", "partial", "deferred", "failed"]
    acquisition_mode: ResearchAcquisitionMode
    requested_acquisition_mode: ResearchAcquisitionMode
    selected_acquisition_mode: ResearchAcquisitionMode
    reason: str | None = None
    accepted_entries: tuple[ResearchBenchmarkEntryProjection, ...]
    rejected_entries: tuple[ResearchRejectedEntryProjection, ...]
    citations: tuple[str, ...] = Field(default_factory=tuple)
    manual_only_keys: tuple[str, ...] = Field(default_factory=tuple)
    changed_blocks: tuple[str, ...] = Field(default_factory=tuple)
    stale_scenario_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    old_revision: int | None = None
    new_revision: int | None = None
    source_refs: tuple[str, ...]
    updated_at: datetime


class DeferredBoundaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: UUID
    status: Literal["deferred"]
    reason: str
    owner: Literal["Task 6"]


__all__ = [
    "AcceptedInputProjection",
    "ActionAvailabilityProjection",
    "AssumptionOutcomeResponse",
    "CaseAssetListResponse",
    "CaseAssetResponse",
    "CaseMutationDeltaResponse",
    "CaseQuestionDescriptorProjection",
    "CopilotMessageResponse",
    "CopilotStateResponse",
    "CopilotThreadResponse",
    "CopilotTurnResponse",
    "DeferredBoundaryResponse",
    "FactMutationResponse",
    "FactPeriod",
    "FactProjection",
    "FactSource",
    "FieldErrorResponse",
    "GapProjection",
    "GenerateCaseAssetRequest",
    "MoneyFactValue",
    "PostCopilotMessageRequest",
    "PrepareResearchPlanRequest",
    "QuestionInputFieldProjection",
    "QuestionInputSchemaProjection",
    "QueueResearchJobRequest",
    "ResearchAcquisitionMode",
    "RequestedResearchAcquisitionMode",
    "ResearchBenchmarkEntryProjection",
    "ResearchJobResponse",
    "ResearchPlanResponse",
    "ResearchRejectedEntryProjection",
    "SaveAssumptionRequest",
    "SaveFounderFactRequest",
    "ScenarioMetricProjection",
    "ScenarioProjectionResponse",
    "ScenarioSelectionResponse",
    "SelectScenarioRequest",
    "TextFactValue",
    "TypedFactValue",
]
