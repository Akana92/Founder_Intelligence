export const capabilityKeys = [
  "universal_upload",
  "primary_startup_analysis",
  "deep_startup_analysis",
  "public_comparable_analysis",
] as const;

export type CapabilityKey = (typeof capabilityKeys)[number];
export type LifecycleStatus = "available" | "planned" | "unavailable";

export type ProductCapability = Readonly<{
  key: CapabilityKey;
  label: string;
  lifecycle_status: LifecycleStatus;
  user_selectable: false;
}>;

export type ProductCapabilities = Readonly<{
  contract_version: "founder_capabilities.v1";
  delivery_profile: "sales_ready_hybrid";
  capabilities: readonly ProductCapability[];
  research_policy: "guarded_live_with_cached_fallback";
  surfaces: Readonly<{
    founder_workspace: "separate_web";
    admin_console: "streamlit";
  }>;
  upgrade_target: Readonly<{
    target: "full_platform";
    preserved_contracts: readonly string[];
  }>;
  user_selectable_modes: readonly [];
}>;

export class CapabilityContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CapabilityContractError";
  }
}

export class ApiContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiContractError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, field: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new CapabilityContractError(`${field} must be an object`);
  }
  return value;
}

function requireExact<T extends string>(
  value: unknown,
  expected: T,
  field: string,
): T {
  if (value !== expected) {
    throw new CapabilityContractError(`${field} must equal ${expected}`);
  }
  return expected;
}

function parseCapability(value: unknown, index: number): ProductCapability {
  const capability = requireRecord(value, `capabilities[${index}]`);
  const key = capability.key;
  const lifecycleStatus = capability.lifecycle_status;

  if (!capabilityKeys.includes(key as CapabilityKey)) {
    throw new CapabilityContractError(
      `capabilities[${index}].key is not part of founder_capabilities.v1`,
    );
  }
  if (
    lifecycleStatus !== "available" &&
    lifecycleStatus !== "planned" &&
    lifecycleStatus !== "unavailable"
  ) {
    throw new CapabilityContractError(
      `capabilities[${index}].lifecycle_status is invalid`,
    );
  }
  if (typeof capability.label !== "string" || capability.label.trim() === "") {
    throw new CapabilityContractError(
      `capabilities[${index}].label must be non-empty`,
    );
  }
  if (capability.user_selectable !== false) {
    throw new CapabilityContractError(
      `capabilities[${index}].user_selectable must be false`,
    );
  }

  return {
    key: key as CapabilityKey,
    label: capability.label,
    lifecycle_status: lifecycleStatus,
    user_selectable: false,
  };
}

export function parseProductCapabilities(value: unknown): ProductCapabilities {
  const contract = requireRecord(value, "capabilities contract");
  const rawCapabilities = contract.capabilities;
  const surfaces = requireRecord(contract.surfaces, "surfaces");
  const upgradeTarget = requireRecord(contract.upgrade_target, "upgrade_target");

  requireExact(
    contract.contract_version,
    "founder_capabilities.v1",
    "contract_version",
  );
  requireExact(
    contract.delivery_profile,
    "sales_ready_hybrid",
    "delivery_profile",
  );
  requireExact(
    contract.research_policy,
    "guarded_live_with_cached_fallback",
    "research_policy",
  );
  requireExact(
    surfaces.founder_workspace,
    "separate_web",
    "surfaces.founder_workspace",
  );
  requireExact(
    surfaces.admin_console,
    "streamlit",
    "surfaces.admin_console",
  );
  requireExact(upgradeTarget.target, "full_platform", "upgrade_target.target");

  if (!Array.isArray(rawCapabilities)) {
    throw new CapabilityContractError("capabilities must be an array");
  }
  const capabilities = rawCapabilities.map(parseCapability);
  const keys = capabilities.map((capability) => capability.key);
  if (
    capabilities.length !== capabilityKeys.length ||
    new Set(keys).size !== capabilityKeys.length ||
    capabilityKeys.some((key) => !keys.includes(key))
  ) {
    throw new CapabilityContractError(
      "capabilities must contain unique required capability keys",
    );
  }

  if (
    !Array.isArray(contract.user_selectable_modes) ||
    contract.user_selectable_modes.length !== 0
  ) {
    throw new CapabilityContractError("user_selectable_modes must be empty");
  }

  const preservedContracts = upgradeTarget.preserved_contracts;
  if (
    !Array.isArray(preservedContracts) ||
    !preservedContracts.every((item) => typeof item === "string") ||
    !preservedContracts.includes("analytics_core") ||
    !preservedContracts.includes("api_v1")
  ) {
    throw new CapabilityContractError(
      "upgrade_target.preserved_contracts must preserve analytics_core and api_v1",
    );
  }

  return {
    contract_version: "founder_capabilities.v1",
    delivery_profile: "sales_ready_hybrid",
    capabilities,
    research_policy: "guarded_live_with_cached_fallback",
    surfaces: {
      founder_workspace: "separate_web",
      admin_console: "streamlit",
    },
    upgrade_target: {
      target: "full_platform",
      preserved_contracts: [...preservedContracts],
    },
    user_selectable_modes: [],
  };
}

export function capabilityByKey(
  contract: ProductCapabilities,
  key: CapabilityKey,
): ProductCapability {
  const capability = contract.capabilities.find((item) => item.key === key);
  if (!capability) {
    throw new CapabilityContractError(`missing capability: ${key}`);
  }
  return capability;
}

export type ProviderStatus =
  | "deterministic_offline_fixture"
  | "unavailable"
  | "configured";
export type AnalysisStatus =
  | "awaiting_upload"
  | "awaiting_start"
  | "gate2_preview_ready"
  | "gate3_review_required"
  | "analysis_complete_report_pending"
  | "failed";
export type GateStatus = "not_ready" | "required" | "completed";
export type ReportStatus = "not_ready" | "pending" | "ready";
export type FreezeStatus = "not_ready" | "required" | "approved";
export type PdfStatus = "not_ready" | "freeze_required" | "ready";

export type StartupCreateRequest = Readonly<{
  fixture_mode: "live" | "deterministic_offline";
  auto_start?: boolean;
  company_name?: string | null;
  website?: string | null;
  as_of?: string | null;
  document_class_hint?: string | null;
}>;

export type StartupCreateResponse = Readonly<{
  case_id: string;
  case_status: "awaiting_upload";
  analysis_status: AnalysisStatus;
  provider_status: ProviderStatus;
  auto_start_triggered: boolean;
}>;

export type StartupCaseStatus = Readonly<{
  case_id: string;
  case_status: "awaiting_upload";
  analysis_status: AnalysisStatus;
  provider_status: ProviderStatus;
  data_revision: number;
  active_analysis_thread_id: string;
  langgraph_checkpoint: StartupLangGraphCheckpoint | null;
  gate2_status: GateStatus;
  gate3_status: GateStatus;
  gate4_status: GateStatus;
  report_status: ReportStatus;
  snapshot_hash: string | null;
  snapshot_revision: number | null;
}>;

export type StartupLangGraphCheckpoint = Readonly<{
  checkpoint_id: string;
  checkpoint_hash: string;
  data_revision: number;
  thread_id: string;
}>;

export type StartupUploadResponse = Readonly<{
  case_id: string;
  accepted_document_ids: readonly string[];
  analysis_status: AnalysisStatus;
  auto_start_triggered: boolean;
  next_poll_after_ms: number;
}>;

export type StartupGate2Preview = Readonly<{
  case_id: string;
  preview: Readonly<Record<string, unknown>>;
  resume_token: string;
  provider_mode: ProviderStatus;
}>;

export type StartupDecisionResult = Readonly<{
  case_id: string;
  analysis_status: AnalysisStatus;
  gate2_status: GateStatus;
  gate3_status: GateStatus;
  gate4_status: GateStatus;
  report_status: ReportStatus;
  snapshot_hash: string | null;
  snapshot_revision: number | null;
}>;

export type StartupCaseReport = Readonly<{
  case_id: string;
  report_status: "ready";
  snapshot_id: string;
  snapshot_hash: string;
  snapshot_revision: number;
  json_url: string;
  html_url: string;
  pdf_url: string;
  freeze_status: FreezeStatus;
  pdf_status: PdfStatus;
}>;

export const STARTUP_PROFILE_FIELD_NAMES = [
  "startup_name",
  "one_line_description",
  "problem",
  "solution",
  "icp",
  "users",
  "buyers",
  "geography",
  "stage",
  "business_model",
  "pricing_revenue_model",
  "traction",
  "channels_gtm",
  "competitors_mentioned",
  "assumptions",
  "strengths",
  "weaknesses",
  "metric_pack_candidates",
] as const;

export type StartupProfileFieldName =
  (typeof STARTUP_PROFILE_FIELD_NAMES)[number];
export type StartupProfileFieldStatus =
  | "source_fact"
  | "inference"
  | "insufficient_data"
  | "contradiction";
export type StartupProfileAnalysisStage = "primary" | "enriched";

export type StartupProfileEvidenceRefResponse = Readonly<{
  evidence_id: string;
  fragment_id: string | null;
  artifact_id: string;
  artifact_hash: string;
  locator_hash: string;
  page: number | null;
  table: string | null;
  cell: string | null;
  field_name: StartupProfileFieldName | null;
  confidence: string;
}>;

export type StartupProfileFieldResponse = Readonly<{
  status: StartupProfileFieldStatus;
  values: readonly string[];
  confidence: string;
  evidence_refs: readonly StartupProfileEvidenceRefResponse[];
  dependency_refs: readonly string[];
  reason_code: string | null;
  contradiction_ids: readonly string[];
}>;

export type StartupProfileParseInventoryResponse = Readonly<{
  source_hashes: Readonly<Record<string, string>>;
  parse_outcomes: Readonly<Record<string, string>>;
}>;

export type StartupProfileResponse = Readonly<{
  case_id: string;
  profile_id: string;
  profile_hash: string;
  data_revision: number;
  analysis_stage: StartupProfileAnalysisStage;
  parent_profile_id: string | null;
  fields: Readonly<Record<StartupProfileFieldName, StartupProfileFieldResponse>>;
  contradictions: readonly string[];
  gaps: readonly string[];
  parse_inventory: StartupProfileParseInventoryResponse;
}>;

export const STARTUP_REPORT_SECTION_KEYS = [
  "business_idea_summary",
  "problem_solution",
  "market_size",
  "competitors",
  "moat",
  "go_to_market",
  "metrics",
  "financial_assumptions",
  "risks",
  "evidence_gaps",
  "diligence_questions",
  "action_plan",
  "methodology",
  "source_appendix",
] as const;

export type StartupReportSectionKey =
  (typeof STARTUP_REPORT_SECTION_KEYS)[number];

export type FounderReportSectionStatus =
  | "confirmed"
  | "partial"
  | "needs_input"
  | "contradiction";

export type FounderReportSectionResponse = Readonly<{
  key: StartupReportSectionKey;
  title_ru: string;
  status: FounderReportSectionStatus;
  status_label_ru: string;
  summary_ru: string;
  content_heading_ru: string;
  known_facts_ru: readonly string[];
  blockers_ru: readonly string[];
  next_data_ru: readonly string[];
  unlocks_ru: readonly string[];
}>;

export type FounderReportMetricCardResponse = Readonly<{
  title_ru: string;
  summary_ru: string;
  status: FounderReportSectionStatus;
  why_it_matters_ru: string;
  next_unlock_ru: string;
}>;

export type FounderReportImprovementProposalResponse = Readonly<{
  target_area:
    | "positioning"
    | "monetization"
    | "metrics"
    | "gtm"
    | "risk_reduction"
    | "investor_readiness";
  title_ru: string;
  recommendation_ru: string;
  rationale_ru: string;
  expected_effect_ru: string;
  provenance: "ai_recommendation";
}>;

export type FounderReportTechnicalAppendixResponse = Readonly<{
  methodology_ru: readonly string[];
  sources_ru: readonly string[];
}>;

export type FounderReportAnalyticsPointStatus =
  | "confirmed"
  | "calculated"
  | "estimated"
  | "contradiction";
export type FounderReportReadinessStatus = "ready" | "provisional" | "blocked";

export type FounderReportAnalyticsPoint = Readonly<{
  key: string;
  label_ru: string;
  value: number;
  unit: string | null;
  period_ru: string | null;
  status: FounderReportAnalyticsPointStatus;
}>;

export type FounderReportReadinessDimensionResponse = Readonly<{
  key: string;
  label_ru: string;
  status: FounderReportReadinessStatus;
  status_label_ru: string;
  explanation_ru: string;
}>;

export type FounderReportAnalyticsResponse = Readonly<{
  metric_points: readonly FounderReportAnalyticsPoint[];
  market_points: readonly FounderReportAnalyticsPoint[];
  readiness_dimensions: readonly FounderReportReadinessDimensionResponse[];
}>;

export type StartupReportSnapshotResponse = Readonly<{
  title_ru: string;
  subtitle_ru: string;
  as_of_ru: string;
  data_revision: number;
  main_sections: readonly FounderReportSectionResponse[];
  metric_cards: Readonly<Record<string, FounderReportMetricCardResponse>>;
  improvement_proposals: readonly FounderReportImprovementProposalResponse[];
  technical_appendix: FounderReportTechnicalAppendixResponse;
  analytics: FounderReportAnalyticsResponse;
}>;

export type StartupGtmStatus =
  | "supported"
  | "partial"
  | "insufficient"
  | "contradicted";
export type StartupGtmDimensionName =
  | "audience"
  | "geography"
  | "channels"
  | "offer"
  | "market_context"
  | "product_proof"
  | "adoption_risk";
export type StartupGtmDimensionStatus =
  | "supported"
  | "partial"
  | "missing"
  | "contradicted";
export type StartupGtmLaunchHorizon =
  | "day_7"
  | "day_30"
  | "day_60"
  | "day_90";
export type StartupGtmExperimentCode =
  | "resolve_contradictions"
  | "clarify_audience"
  | "validate_geography"
  | "validate_channel"
  | "validate_offer"
  | "validate_product_proof"
  | "validate_market_positioning"
  | "validate_adoption_risk"
  | "measure_channel_signal"
  | "review_launch_evidence";

export type StartupGtmDimension = Readonly<{
  name: StartupGtmDimensionName;
  status: StartupGtmDimensionStatus;
  evidence_fact_ids: readonly string[];
  market_source_ids: readonly string[];
  contradiction_ids: readonly string[];
  reason_code: string;
  gap_code: string | null;
}>;

export type StartupGtmLaunchStep = Readonly<{
  horizon: StartupGtmLaunchHorizon;
  experiment_codes: readonly StartupGtmExperimentCode[];
}>;

export type StartupGtmResponse = Readonly<{
  case_id: string;
  schema_version: "startup_gtm@1";
  snapshot_id: string;
  snapshot_hash: string;
  snapshot_revision: number;
  status: StartupGtmStatus;
  profile_id: string;
  product_validation_snapshot_id: string;
  market_research_snapshot_id: string;
  dimensions: readonly StartupGtmDimension[];
  launch_plan: readonly StartupGtmLaunchStep[];
  finding_ids: readonly string[];
  built_at: string;
}>;

export type AdvisorAnswerType = "manual" | "file" | "public_research" | "skip";
export type AdvisorQuestionOrigin =
  | "static"
  | "document_gap"
  | "document_contradiction"
  | "answered_state";
export type AdvisorQuestionDto = Readonly<{
  question_id: string;
  field_key: string;
  question_ru: string;
  reason_ru: string;
  unlocks_ru: string;
  answer_modes: readonly AdvisorAnswerType[];
  origin: AdvisorQuestionOrigin;
  origin_label_ru: string;
  context_ru: string | null;
  answer_mode_labels_ru: Readonly<Record<AdvisorAnswerType, string>>;
}>;
export type AdvisorNextQuestionResponse = Readonly<{
  case_id: string;
  status: "active" | "complete";
  next_question: AdvisorQuestionDto | null;
  answered_count: number;
  total_count: number;
}>;
export type AdvisorResearchResult = Readonly<{
  status: "completed" | "partial" | "deferred" | "blocked";
  summary_ru: string;
  source_ids: readonly string[];
  fallback_used: boolean;
  fail_reason_ru: string | null;
}>;
export type AdvisorRecalculationDelta = Readonly<{
  previous_revision: number;
  new_revision: number;
  fields_changed: readonly string[];
  core_coverage_delta: number;
  conflicts_resolved: number;
  conflicts_remaining: number;
  calculations_recalculated: readonly string[];
  calculations_pending: readonly string[];
}>;
export type AdvisorAnswerResponse = Readonly<{
  case_id: string;
  question_id: string;
  field_key: string;
  answer_type: AdvisorAnswerType;
  status: "applied" | "blocked";
  confidence_delta: number;
  analysis_blocked: boolean;
  answered_count: number;
  total_count: number;
  research_result: AdvisorResearchResult | null;
  recalculation_status: "not_requested" | "started" | "deferred";
  recalculation_data_revision: number | null;
  recalculation_analysis_status: AnalysisStatus | null;
  recalculation_delta: AdvisorRecalculationDelta | null;
}>;
export type AdvisorImprovementProposal = Readonly<{
  proposal_id: string;
  target_area: string;
  recommendation_ru: string;
  rationale_ru: string;
  expected_effect_ru: string;
  evidence_kinds: readonly string[];
  confidence: number;
}>;
export type AdvisorImprovementsResponse = Readonly<{
  case_id: string;
  improvement_version: number;
  proposals: readonly AdvisorImprovementProposal[];
}>;
export type AdvisorImprovementDecisionResponse = Readonly<{
  case_id: string;
  proposal_id: string;
  decision: "accepted" | "rejected";
  previous_version: number;
  new_version: number;
  changed_fields: readonly string[];
  recalculation_status: "not_requested" | "started" | "deferred";
  recalculation_data_revision: number | null;
  recalculation_analysis_status: AnalysisStatus | null;
}>;

export type CaseValueKind =
  | "source_fact"
  | "founder_statement"
  | "public_benchmark"
  | "deterministic_calculation"
  | "ai_scenario"
  | "contradiction";
export type ScenarioKey = "conservative" | "base" | "optimistic";
export type ScenarioConfidence = "low" | "medium" | "high";
export type ScenarioAcceptance =
  | "proposed"
  | "accepted"
  | "rejected"
  | "needs_validation";
export type CopilotActionKey =
  | "open_fact_input"
  | "open_document_upload"
  | "prepare_public_research"
  | "explain_metric"
  | "navigate"
  | "prepare_asset"
  | "review_improvements";
export type CopilotActionStatus =
  | "available"
  | "requires_input"
  | "requires_consent"
  | "blocked";
export type CopilotPayloadValue = string | number | boolean | readonly string[];

export type ScenarioRangeResponse = Readonly<{
  lower: string;
  upper: string;
}>;

export type CopilotScenarioRangeResponse = Readonly<{
  conservative: string | null;
  base: string | null;
  optimistic: string | null;
}>;

export type ResearchRangeResponse = Readonly<{
  low: string | null;
  high: string | null;
}>;

export type CopilotFactProjection = Readonly<{
  field_key: string;
  value: string;
  source_type: CaseValueKind;
}>;

export type CopilotGapProjection = Readonly<{
  gap_code: string;
  field_key: string;
  privacy_class: string;
  allowed_action: string;
}>;

export type CopilotScenarioMetricProjection = Readonly<{
  metric_key: string;
  label: string;
  source_type: CaseValueKind;
  value: null;
  range: CopilotScenarioRangeResponse;
  formula: string;
  dependencies: readonly string[];
  unit: string;
  period: string;
  confidence: string;
  source_refs: readonly string[];
  what_would_confirm: string;
  validation_plan: string;
}>;

export type CopilotCoverageProjection = Readonly<{
  measure: string;
  status: string;
  source_fact_count: number | null;
  accepted_input_count: number | null;
}>;

export type CopilotAcceptedInputProjection = Readonly<{
  field_key: string;
  kind: CaseValueKind;
  status: string;
  value: string;
  period: string | null;
  rationale: string | null;
  validation_plan: string | null;
  declared_source: string | null;
  source_refs: readonly string[];
}>;

export type CopilotQuestionInputKind = "text" | "decimal" | "select" | "month";

export type CopilotQuestionInputField = Readonly<{
  field_key: string;
  label: string;
  input_kind: CopilotQuestionInputKind;
  required: boolean;
  placeholder: string | null;
}>;

export type CopilotQuestionInputSchema = Readonly<{
  kind: "text" | "money";
  fields: readonly CopilotQuestionInputField[];
}>;

export type CopilotQuestionDescriptor = Readonly<{
  question_id: string;
  field_key: string;
  question: string;
  label: string;
  description: string;
  why_needed: string;
  unlocks: readonly string[];
  unlocks_copy: string;
  example: string;
  validation_guidance: string;
  provenance: "founder_statement";
  input_schema: CopilotQuestionInputSchema;
}>;

export type CopilotActionAvailability = Readonly<{
  action_id: string;
  action: CopilotActionKey;
  status: CopilotActionStatus;
  handler: string | null;
  reason: string | null;
  effect_preview: string;
  payload: Readonly<Record<string, CopilotPayloadValue>>;
}>;

export type CopilotStateResponse = Readonly<{
  case_id: string;
  data_revision: number;
  stage: string;
  next_question: string | null;
  question_descriptor: CopilotQuestionDescriptor | null;
  suggested_action: string;
  selected_scenario_key: ScenarioKey;
  extracted_facts: readonly CopilotFactProjection[];
  prioritized_gaps: readonly CopilotGapProjection[];
  scenario_metrics: readonly CopilotScenarioMetricProjection[];
  fact_coverage: CopilotCoverageProjection;
  scenario_completeness: CopilotCoverageProjection;
  accepted_inputs: readonly CopilotAcceptedInputProjection[];
  actions: readonly CopilotActionAvailability[];
}>;

export type CopilotMessageRole = "system" | "system_event" | "user" | "assistant" | "tool";

export type CopilotMessageResponseItem = Readonly<{
  message_id: string;
  case_id: string;
  data_revision: number;
  role: CopilotMessageRole;
  content: string;
  page_context: string | null;
  current_section: string | null;
  idempotency_fingerprint: string | null;
  related_evidence_refs: readonly string[];
  question_refs: readonly string[];
  action_refs: readonly string[];
  action_snapshots: readonly CopilotActionAvailability[];
  action_result: Readonly<Record<string, CopilotPayloadValue>> | null;
}>;

export type CopilotThreadResponse = Readonly<{
  thread_id: string;
  case_id: string;
  data_revision: number;
  messages: readonly CopilotMessageResponseItem[];
}>;

export type CopilotTurnResponse = Readonly<{
  case_id: string;
  data_revision: number;
  thread_id: string;
  page_context: string;
  current_section: string;
  status: "accepted";
  message: string;
  available_actions: readonly CopilotActionAvailability[];
}>;

export type CaseMutationFieldError = Readonly<{
  field: string;
  message: string;
}>;

export type CaseMutationDeltaResponse = Readonly<{
  accepted: boolean;
  old_revision: number;
  new_revision: number;
  changed_keys: readonly string[];
  stale_scenario_ids: readonly string[];
  stale_report_ids: readonly string[];
  metric_before: Readonly<Record<string, string>>;
  metric_after: Readonly<Record<string, string>>;
  readiness_before: Readonly<Record<string, number>>;
  readiness_after: Readonly<Record<string, number>>;
  next_question: unknown;
  validation_errors: readonly CaseMutationFieldError[];
  original_draft: string | null;
}>;

export type FactMutationResponse = Readonly<{
  case_id: string;
  accepted: boolean;
  provenance: CaseValueKind;
  source_type: CaseValueKind;
  old_revision: number;
  new_revision: number;
  changed_keys: readonly string[];
  delta: CaseMutationDeltaResponse;
}>;

export type AssumptionOutcomeResponse = Readonly<{
  case_id: string;
  status: "accepted" | "blocked";
  provenance: CaseValueKind;
  reason: string | null;
  old_revision: number;
  new_revision: number;
  delta: CaseMutationDeltaResponse | null;
  accepted_input: CopilotAcceptedInputProjection | null;
}>;

export type StartupScenarioInput = Readonly<{
  input_id: string;
  case_id: string | null;
  data_revision: number | null;
  input_key: string;
  value_range: ScenarioRangeResponse;
  unit: string;
  period: string | null;
  provenance: CaseValueKind;
  source_refs: readonly string[];
  dependency_refs: readonly string[];
  confidence: ScenarioConfidence;
  rationale: string;
  validation_plan: string;
  what_would_confirm: string;
  acceptance: ScenarioAcceptance;
}>;

export type StartupScenarioMetric = Readonly<{
  metric_id: string;
  case_id: string;
  data_revision: number;
  metric_key: string;
  value_range: ScenarioRangeResponse | null;
  unit: string;
  period: string | null;
  provenance: CaseValueKind;
  source_refs: readonly string[];
  dependency_refs: readonly string[];
  formula_key: string;
  formula_description: string;
  confidence: ScenarioConfidence;
  rationale: string;
  validation_plan: string;
  what_would_confirm: string;
  acceptance: ScenarioAcceptance;
  gaps: readonly string[];
}>;

export type StartupScenarioVariant = Readonly<{
  scenario_key: ScenarioKey;
  inputs: Readonly<Record<string, StartupScenarioInput>>;
  metrics: Readonly<Record<string, StartupScenarioMetric>>;
  gaps: Readonly<Record<string, string>>;
}>;

export type ScenarioProjectionResponse = Readonly<{
  scenario_set_id: string;
  case_id: string;
  data_revision: number;
  selected_scenario_key: ScenarioKey;
  scenarios: Readonly<Record<ScenarioKey, StartupScenarioVariant>>;
  fact_coverage: CopilotCoverageProjection;
  scenario_completeness: CopilotCoverageProjection;
}>;

export type ScenarioSelectionResponse = Readonly<{
  case_id: string;
  data_revision: number;
  scenario_set_id: string;
  old_scenario_key: ScenarioKey;
  new_scenario_key: ScenarioKey;
  changed_keys: readonly string[];
}>;

export type LaunchPackMetadataResponse = Readonly<{
  case_id: string;
  data_revision: number;
  scenario_set_id: string;
  selected_scenario_key: ScenarioKey;
  asset_id: string;
  asset_key: string;
  asset_revision: number;
  status: "draft";
  markdown_url: string;
  csv_url: string | null;
  provenance_appendix_url: string;
  body_markdown: string;
}>;

export type CaseAssetListResponse = Readonly<{
  case_id: string;
  data_revision: number;
  assets: readonly LaunchPackMetadataResponse[];
}>;

export type ResearchPlanResponse = Readonly<{
  case_id: string;
  data_revision: number;
  status: "prepared";
  plan_id: string;
  plan_hash: string;
  focus: string;
  query_previews: readonly string[];
  manual_only_keys: readonly string[];
  consent_text: string;
  created_at: string;
  expires_at: string;
}>;

export type ResearchBenchmarkEntryProjection = Readonly<{
  entry_id: string;
  provenance: "public_benchmark";
  input_key: string;
  url: string;
  publisher: string;
  publication_date: string | null;
  retrieval_date: string;
  as_of: string;
  source_class: string;
  confidence: ScenarioConfidence;
  value: string | null;
  range: ResearchRangeResponse;
  unit: string;
  period: string;
  formula: string;
  dependencies: readonly string[];
  validation_plan: string;
  source_refs: readonly string[];
}>;

export type ResearchRejectedEntryProjection = Readonly<{
  rejected_id: string;
  reason_code: string;
  input_key: string | null;
  provenance: string | null;
  metadata: Readonly<Record<string, string>>;
}>;

export type ResearchAcquisitionMode =
  | "deterministic_offline_fixture"
  | "live_public_research"
  | "provider_unconfigured";
export type RequestedResearchAcquisitionMode = Exclude<
  ResearchAcquisitionMode,
  "provider_unconfigured"
>;

export type ResearchJobResponse = Readonly<{
  case_id: string;
  data_revision: number;
  job_id: string;
  plan_id: string | null;
  plan_hash: string | null;
  status: "queued" | "running" | "completed" | "partial" | "deferred" | "failed";
  acquisition_mode: ResearchAcquisitionMode;
  requested_acquisition_mode: ResearchAcquisitionMode;
  selected_acquisition_mode: ResearchAcquisitionMode;
  reason: string | null;
  accepted_entries: readonly ResearchBenchmarkEntryProjection[];
  rejected_entries: readonly ResearchRejectedEntryProjection[];
  citations: readonly string[];
  manual_only_keys: readonly string[];
  changed_blocks: readonly string[];
  stale_scenario_ids: readonly string[];
  old_revision: number | null;
  new_revision: number | null;
  source_refs: readonly string[];
  updated_at: string;
}>;

export type ApiErrorCode =
  | "api_unreachable"
  | "api_timeout"
  | "api_rejected"
  | "invalid_contract"
  | "unsafe_path"
  | "case_not_found"
  | "empty_upload"
  | "request_validation_error"
  | "invalid_fixture_mode"
  | "startup_document_intelligence_input_invalid"
  | "gate2_preview_not_ready"
  | "resume_token_invalid"
  | "gate2_resume_failed"
  | "invalid_gate2_decision"
  | "invalid_gate3_decision"
  | "invalid_gate3_exclusions"
  | "unknown_evidence_fact_id"
  | "startup_profile_not_ready"
  | "startup_profile_stale"
  | "startup_gtm_not_ready"
  | "startup_gtm_stale"
  | "startup_market_fixture_unavailable"
  | "startup_report_snapshot_stale"
  | "report_not_ready"
  | "gate_4_freeze_required"
  | "gate_4_snapshot_mismatch"
  | "invalid_gate4_decision"
  | "report_renderer_unavailable"
  | "advisor_question_cross_case"
  | "advisor_question_stale"
  | "advisor_answer_type_invalid"
  | "advisor_manual_answer_invalid"
  | "advisor_manual_answer_semantic_mismatch"
  | "advisor_answer_shape_invalid"
  | "advisor_document_not_in_case"
  | "advisor_answer_type_unavailable"
  | "advisor_improvements_not_ready"
  | "advisor_proposal_unknown"
  | "advisor_proposal_cross_case"
  | "advisor_proposal_stale"
  | "advisor_decision_conflict"
  | "advisor_progress_invalid"
  | "case_revision_conflict"
  | "stale_research_plan"
  | "private_public_research_rejected"
  | "public_research_consent_required"
  | "idempotency_key_conflict"
  | "research_plan_not_found"
  | "research_job_not_found"
  | "research_job_already_running"
  | "copilot_action_snapshot_corrupt"
  | "fact_validation_failed";

export type ApiError = Readonly<{
  code: ApiErrorCode;
  message: string;
  errors?: readonly ApiFieldError[];
}>;

export type ApiFieldError = Readonly<{
  field: string;
  message: string;
}>;

const providerStatuses = [
  "deterministic_offline_fixture",
  "unavailable",
  "configured",
] as const;
const analysisStatuses = [
  "awaiting_upload",
  "awaiting_start",
  "gate2_preview_ready",
  "gate3_review_required",
  "analysis_complete_report_pending",
  "failed",
] as const;
const gateStatuses = ["not_ready", "required", "completed"] as const;
const reportStatuses = ["not_ready", "pending", "ready"] as const;
const freezeStatuses = ["not_ready", "required", "approved"] as const;
const pdfStatuses = ["not_ready", "freeze_required", "ready"] as const;
const startupProfileFieldStatuses = [
  "source_fact",
  "inference",
  "insufficient_data",
  "contradiction",
] as const;
const startupProfileAnalysisStages = ["primary", "enriched"] as const;
const startupGtmStatuses = [
  "supported",
  "partial",
  "insufficient",
  "contradicted",
] as const;
const startupGtmDimensionNames = [
  "audience",
  "geography",
  "channels",
  "offer",
  "market_context",
  "product_proof",
  "adoption_risk",
] as const;
const startupGtmDimensionStatuses = [
  "supported",
  "partial",
  "missing",
  "contradicted",
] as const;
const startupGtmLaunchHorizons = [
  "day_7",
  "day_30",
  "day_60",
  "day_90",
] as const;
const startupGtmExperimentCodes = [
  "resolve_contradictions",
  "clarify_audience",
  "validate_geography",
  "validate_channel",
  "validate_offer",
  "validate_product_proof",
  "validate_market_positioning",
  "validate_adoption_risk",
  "measure_channel_signal",
  "review_launch_evidence",
] as const;
const apiErrorCodes = [
  "api_unreachable",
  "api_timeout",
  "api_rejected",
  "invalid_contract",
  "unsafe_path",
  "case_not_found",
  "empty_upload",
  "request_validation_error",
  "invalid_fixture_mode",
  "startup_document_intelligence_input_invalid",
  "gate2_preview_not_ready",
  "resume_token_invalid",
  "gate2_resume_failed",
  "invalid_gate2_decision",
  "invalid_gate3_decision",
  "invalid_gate3_exclusions",
  "unknown_evidence_fact_id",
  "startup_profile_not_ready",
  "startup_profile_stale",
  "startup_gtm_not_ready",
  "startup_gtm_stale",
  "startup_market_fixture_unavailable",
  "startup_report_snapshot_stale",
  "report_not_ready",
  "gate_4_freeze_required",
  "gate_4_snapshot_mismatch",
  "invalid_gate4_decision",
  "report_renderer_unavailable",
  "advisor_question_cross_case",
  "advisor_question_stale",
  "advisor_answer_type_invalid",
  "advisor_manual_answer_invalid",
  "advisor_manual_answer_semantic_mismatch",
  "advisor_answer_shape_invalid",
  "advisor_document_not_in_case",
  "advisor_answer_type_unavailable",
  "advisor_improvements_not_ready",
  "advisor_proposal_unknown",
  "advisor_proposal_cross_case",
  "advisor_proposal_stale",
  "advisor_decision_conflict",
  "advisor_progress_invalid",
  "case_revision_conflict",
  "stale_research_plan",
  "private_public_research_rejected",
  "public_research_consent_required",
  "idempotency_key_conflict",
  "research_plan_not_found",
  "research_job_not_found",
  "research_job_already_running",
  "copilot_action_snapshot_corrupt",
  "fact_validation_failed",
] as const;

function requireApiRecord(value: unknown, field: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new ApiContractError(`${field} must be an object`);
  }
  return value;
}

function requireApiExactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
  field: string,
): void {
  const expected = new Set(keys);
  for (const key of Object.keys(value)) {
    if (!expected.has(key)) {
      throw new ApiContractError(`${field}.${key} is not allowed`);
    }
  }
  for (const key of keys) {
    if (!(key in value)) {
      throw new ApiContractError(`${field}.${key} is required`);
    }
  }
}

function requireApiString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new ApiContractError(`${field} must be a non-empty string`);
  }
  return value;
}

function requireApiBoolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") {
    throw new ApiContractError(`${field} must be a boolean`);
  }
  return value;
}

function requireApiInteger(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new ApiContractError(`${field} must be an integer`);
  }
  return value;
}

function requireApiNullableString(value: unknown, field: string): string | null {
  if (value === null) {
    return null;
  }
  return requireApiString(value, field);
}

function requireApiNullableInteger(value: unknown, field: string): number | null {
  if (value === null) {
    return null;
  }
  return requireApiInteger(value, field);
}

function requireApiLiteral<T extends readonly string[]>(
  value: unknown,
  allowed: T,
  field: string,
): T[number] {
  if (!allowed.includes(value as T[number])) {
    throw new ApiContractError(`${field} is invalid`);
  }
  return value as T[number];
}

function requireApiStringArray(value: unknown, field: string): readonly string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new ApiContractError(`${field} must be a string array`);
  }
  return [...value];
}

const startupGtmSafeRefPattern = /^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$/;
const startupGtmSafeCodePattern = /^[a-z0-9][a-z0-9_.:@-]{0,119}$/;
const startupGtmSnapshotHashPattern = /^sha256:[0-9a-f]{64}$/;
const startupGtmMaxRefs = 512;
const startupProfileUuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const startupProfileConfidencePattern = /^(?:0(?:\.\d+)?|1(?:\.0+)?)$/;
const startupProfileMaxValues = 16;
const startupProfileMaxValueLength = 512;

function requireStartupGtmSafeRefs(
  value: unknown,
  field: string,
): readonly string[] {
  const refs = requireApiStringArray(value, field).map((item) => {
    const normalized = item.trim();
    if (!startupGtmSafeRefPattern.test(normalized)) {
      throw new ApiContractError(`${field} contains an unsafe reference`);
    }
    return normalized;
  });
  const normalized = [...new Set(refs)].sort();
  if (normalized.length > startupGtmMaxRefs) {
    throw new ApiContractError(`${field} contains too many references`);
  }
  return normalized;
}

function requireStartupGtmSafeCode(
  value: unknown,
  field: string,
): string {
  const normalized = requireApiString(value, field).trim().toLowerCase();
  if (!startupGtmSafeCodePattern.test(normalized)) {
    throw new ApiContractError(`${field} contains an unsafe code`);
  }
  return normalized;
}

function requireStartupGtmNullableSafeCode(
  value: unknown,
  field: string,
): string | null {
  if (value === null) {
    return null;
  }
  return requireStartupGtmSafeCode(value, field);
}

function requireStartupGtmSnapshotHash(value: unknown, field: string): string {
  const hash = requireApiString(value, field);
  if (!startupGtmSnapshotHashPattern.test(hash)) {
    throw new ApiContractError(`${field} must be sha256:<64 lowercase hex chars>`);
  }
  return hash;
}

function requireStartupGtmExperimentCodes(
  value: unknown,
  field: string,
): readonly StartupGtmExperimentCode[] {
  const codes = requireApiStringArray(value, field).map((item) =>
    requireApiLiteral(item, startupGtmExperimentCodes, field),
  );
  const uniqueCodes = new Set(codes);
  return startupGtmExperimentCodes.filter((code) => uniqueCodes.has(code));
}

export function parseStartupCreateResponse(value: unknown): StartupCreateResponse {
  const record = requireApiRecord(value, "startup_create");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "case_status",
      "analysis_status",
      "provider_status",
      "auto_start_triggered",
    ],
    "startup_create",
  );
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    case_status: requireApiLiteral(
      record.case_status,
      ["awaiting_upload"] as const,
      "case_status",
    ),
    analysis_status: requireApiLiteral(record.analysis_status, analysisStatuses, "analysis_status"),
    provider_status: requireApiLiteral(record.provider_status, providerStatuses, "provider_status"),
    auto_start_triggered: requireApiBoolean(
      record.auto_start_triggered,
      "auto_start_triggered",
    ),
  };
}

const startupStatusOpaqueIdPattern = /^[A-Za-z0-9_.:-]{6,128}$/;
const startupStatusCheckpointHashPattern = /^[0-9a-f]{64}$/;

function requireStartupStatusOpaqueId(value: unknown, field: string): string {
  const id = requireApiString(value, field).trim();
  if (!startupStatusOpaqueIdPattern.test(id)) {
    throw new ApiContractError(`${field} must be a safe opaque identifier`);
  }
  return id;
}

function requireStartupStatusDataRevision(value: unknown, field: string): number {
  const revision = requireApiInteger(value, field);
  if (revision < 0) {
    throw new ApiContractError(`${field} must be non-negative`);
  }
  return revision;
}

function parseStartupLangGraphCheckpoint(
  value: unknown,
  dataRevision: number,
  activeAnalysisThreadId: string,
): StartupLangGraphCheckpoint | null {
  if (value === null) {
    return null;
  }
  const record = requireApiRecord(value, "langgraph_checkpoint");
  requireApiExactKeys(
    record,
    ["checkpoint_id", "checkpoint_hash", "data_revision", "thread_id"],
    "langgraph_checkpoint",
  );
  const checkpointDataRevision = requirePositiveRevision(
    record.data_revision,
    "langgraph_checkpoint.data_revision",
  );
  if (checkpointDataRevision !== dataRevision) {
    throw new ApiContractError(
      "langgraph_checkpoint.data_revision must match startup_status.data_revision",
    );
  }
  const threadId = requireStartupStatusOpaqueId(
    record.thread_id,
    "langgraph_checkpoint.thread_id",
  );
  if (threadId !== activeAnalysisThreadId) {
    throw new ApiContractError(
      "langgraph_checkpoint.thread_id must match active_analysis_thread_id",
    );
  }
  const checkpointHash = requireApiString(
    record.checkpoint_hash,
    "langgraph_checkpoint.checkpoint_hash",
  );
  if (!startupStatusCheckpointHashPattern.test(checkpointHash)) {
    throw new ApiContractError("langgraph_checkpoint.checkpoint_hash must be lowercase sha256 hex");
  }
  return {
    checkpoint_id: requireStartupStatusOpaqueId(
      record.checkpoint_id,
      "langgraph_checkpoint.checkpoint_id",
    ),
    checkpoint_hash: checkpointHash,
    data_revision: checkpointDataRevision,
    thread_id: threadId,
  };
}

export function parseStartupCaseStatus(value: unknown): StartupCaseStatus {
  const record = requireApiRecord(value, "startup_status");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "case_status",
      "analysis_status",
      "provider_status",
      "data_revision",
      "active_analysis_thread_id",
      "langgraph_checkpoint",
      "gate2_status",
      "gate3_status",
      "gate4_status",
      "report_status",
      "snapshot_hash",
      "snapshot_revision",
    ],
    "startup_status",
  );
  const dataRevision = requireStartupStatusDataRevision(record.data_revision, "data_revision");
  const activeAnalysisThreadId = requireStartupStatusOpaqueId(
    record.active_analysis_thread_id,
    "active_analysis_thread_id",
  );
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    case_status: requireApiLiteral(
      record.case_status,
      ["awaiting_upload"] as const,
      "case_status",
    ),
    analysis_status: requireApiLiteral(record.analysis_status, analysisStatuses, "analysis_status"),
    provider_status: requireApiLiteral(record.provider_status, providerStatuses, "provider_status"),
    data_revision: dataRevision,
    active_analysis_thread_id: activeAnalysisThreadId,
    langgraph_checkpoint: parseStartupLangGraphCheckpoint(
      record.langgraph_checkpoint,
      dataRevision,
      activeAnalysisThreadId,
    ),
    gate2_status: requireApiLiteral(record.gate2_status, gateStatuses, "gate2_status"),
    gate3_status: requireApiLiteral(record.gate3_status, gateStatuses, "gate3_status"),
    gate4_status: requireApiLiteral(record.gate4_status, gateStatuses, "gate4_status"),
    report_status: requireApiLiteral(record.report_status, reportStatuses, "report_status"),
    snapshot_hash: requireApiNullableString(record.snapshot_hash, "snapshot_hash"),
    snapshot_revision: requireApiNullableInteger(record.snapshot_revision, "snapshot_revision"),
  };
}

export function parseStartupUploadResponse(value: unknown): StartupUploadResponse {
  const record = requireApiRecord(value, "startup_upload");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "accepted_document_ids",
      "analysis_status",
      "auto_start_triggered",
      "next_poll_after_ms",
    ],
    "startup_upload",
  );
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    accepted_document_ids: requireApiStringArray(
      record.accepted_document_ids,
      "accepted_document_ids",
    ),
    analysis_status: requireApiLiteral(record.analysis_status, analysisStatuses, "analysis_status"),
    auto_start_triggered: requireApiBoolean(
      record.auto_start_triggered,
      "auto_start_triggered",
    ),
    next_poll_after_ms: requireApiInteger(record.next_poll_after_ms, "next_poll_after_ms"),
  };
}

export function parseStartupAnalysis(value: unknown): StartupCaseStatus {
  return parseStartupCaseStatus(value);
}

export function parseStartupGate2Preview(value: unknown): StartupGate2Preview {
  const record = requireApiRecord(value, "startup_gate2_preview");
  requireApiExactKeys(
    record,
    ["case_id", "preview", "resume_token", "provider_mode"],
    "startup_gate2_preview",
  );
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    preview: requireApiRecord(record.preview, "preview"),
    resume_token: requireApiString(record.resume_token, "resume_token"),
    provider_mode: requireApiLiteral(record.provider_mode, providerStatuses, "provider_mode"),
  };
}

function parseStartupDecisionResult(value: unknown, field: string): StartupDecisionResult {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "case_id",
      "analysis_status",
      "gate2_status",
      "gate3_status",
      "gate4_status",
      "report_status",
      "snapshot_hash",
      "snapshot_revision",
    ],
    field,
  );
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    analysis_status: requireApiLiteral(record.analysis_status, analysisStatuses, "analysis_status"),
    gate2_status: requireApiLiteral(record.gate2_status, gateStatuses, "gate2_status"),
    gate3_status: requireApiLiteral(record.gate3_status, gateStatuses, "gate3_status"),
    gate4_status: requireApiLiteral(record.gate4_status, gateStatuses, "gate4_status"),
    report_status: requireApiLiteral(record.report_status, reportStatuses, "report_status"),
    snapshot_hash: requireApiNullableString(record.snapshot_hash, "snapshot_hash"),
    snapshot_revision: requireApiNullableInteger(record.snapshot_revision, "snapshot_revision"),
  };
}

export function parseStartupGate2DecisionResult(value: unknown): StartupDecisionResult {
  return parseStartupDecisionResult(value, "startup_gate2_decision");
}

export function parseStartupGate3DecisionResult(value: unknown): StartupDecisionResult {
  return parseStartupDecisionResult(value, "startup_gate3_decision");
}

export function parseStartupGate4DecisionResult(value: unknown): StartupDecisionResult {
  return parseStartupDecisionResult(value, "startup_gate4_decision");
}

export function parseStartupCaseReport(value: unknown): StartupCaseReport {
  const record = requireApiRecord(value, "startup_report");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "report_status",
      "snapshot_id",
      "snapshot_hash",
      "snapshot_revision",
      "json_url",
      "html_url",
      "pdf_url",
      "freeze_status",
      "pdf_status",
    ],
    "startup_report",
  );
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    report_status: requireApiLiteral(
      record.report_status,
      ["ready"] as const,
      "report_status",
    ),
    snapshot_id: requireApiString(record.snapshot_id, "snapshot_id"),
    snapshot_hash: requireApiString(record.snapshot_hash, "snapshot_hash"),
    snapshot_revision: requireApiInteger(record.snapshot_revision, "snapshot_revision"),
    json_url: requireApiString(record.json_url, "json_url"),
    html_url: requireApiString(record.html_url, "html_url"),
    pdf_url: requireApiString(record.pdf_url, "pdf_url"),
    freeze_status: requireApiLiteral(record.freeze_status, freezeStatuses, "freeze_status"),
    pdf_status: requireApiLiteral(record.pdf_status, pdfStatuses, "pdf_status"),
  };
}

function requireStartupProfileUuid(value: unknown, field: string): string {
  const normalized = requireApiString(value, field).trim().toLowerCase();
  if (!startupProfileUuidPattern.test(normalized)) {
    throw new ApiContractError(`${field} must be a UUID`);
  }
  return normalized;
}

function requireStartupProfileNullableUuid(
  value: unknown,
  field: string,
): string | null {
  if (value === null) return null;
  return requireStartupProfileUuid(value, field);
}

function requireStartupProfileConfidence(
  value: unknown,
  field: string,
): string {
  const normalized = requireApiString(value, field).trim();
  if (!startupProfileConfidencePattern.test(normalized)) {
    throw new ApiContractError(`${field} must be a decimal between 0 and 1`);
  }
  return normalized;
}

function requireStartupProfileValues(
  value: unknown,
  field: string,
): readonly string[] {
  const values = requireApiStringArray(value, field).map((item) => item.trim());
  if (
    values.length > startupProfileMaxValues ||
    values.some(
      (item) => item.length === 0 || item.length > startupProfileMaxValueLength,
    )
  ) {
    throw new ApiContractError(`${field} contains an invalid profile value`);
  }
  const seen = new Set<string>();
  for (const item of values) {
    const key = item.toLocaleLowerCase("en-US");
    if (seen.has(key)) {
      throw new ApiContractError(`${field} contains duplicate profile values`);
    }
    seen.add(key);
  }
  return values;
}

function requireStartupProfileSafeCode(
  value: unknown,
  field: string,
): string {
  return requireStartupGtmSafeCode(value, field);
}

function requireStartupProfileNullableSafeCode(
  value: unknown,
  field: string,
): string | null {
  if (value === null) return null;
  return requireStartupProfileSafeCode(value, field);
}

function requireStartupProfileUuidArray(
  value: unknown,
  field: string,
): readonly string[] {
  const refs = requireApiStringArray(value, field).map((item, index) =>
    requireStartupProfileUuid(item, `${field}[${index}]`),
  );
  return [...new Set(refs)].sort();
}

function requireStartupProfileSafeCodeArray(
  value: unknown,
  field: string,
): readonly string[] {
  const codes = requireApiStringArray(value, field).map((item, index) =>
    requireStartupProfileSafeCode(item, `${field}[${index}]`),
  );
  return [...new Set(codes)].sort();
}

function requireStartupProfileNullableFieldName(
  value: unknown,
  field: string,
): StartupProfileFieldName | null {
  if (value === null) return null;
  return requireApiLiteral(value, STARTUP_PROFILE_FIELD_NAMES, field);
}

function requireStartupProfileNullablePositiveInteger(
  value: unknown,
  field: string,
): number | null {
  if (value === null) return null;
  const integer = requireApiInteger(value, field);
  if (integer < 1) {
    throw new ApiContractError(`${field} must be a positive integer`);
  }
  return integer;
}

function parseStartupProfileEvidenceRef(
  value: unknown,
  field: string,
): StartupProfileEvidenceRefResponse {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "evidence_id",
      "fragment_id",
      "artifact_id",
      "artifact_hash",
      "locator_hash",
      "page",
      "table",
      "cell",
      "field_name",
      "confidence",
    ],
    field,
  );
  return {
    evidence_id: requireStartupProfileUuid(
      record.evidence_id,
      `${field}.evidence_id`,
    ),
    fragment_id: requireStartupProfileNullableUuid(
      record.fragment_id,
      `${field}.fragment_id`,
    ),
    artifact_id: requireStartupProfileUuid(
      record.artifact_id,
      `${field}.artifact_id`,
    ),
    artifact_hash: requireStartupGtmSnapshotHash(
      record.artifact_hash,
      `${field}.artifact_hash`,
    ),
    locator_hash: requireStartupGtmSnapshotHash(
      record.locator_hash,
      `${field}.locator_hash`,
    ),
    page: requireStartupProfileNullablePositiveInteger(
      record.page,
      `${field}.page`,
    ),
    table: requireStartupProfileNullableSafeCode(
      record.table,
      `${field}.table`,
    ),
    cell: requireStartupProfileNullableSafeCode(
      record.cell,
      `${field}.cell`,
    ),
    field_name: requireStartupProfileNullableFieldName(
      record.field_name,
      `${field}.field_name`,
    ),
    confidence: requireStartupProfileConfidence(
      record.confidence,
      `${field}.confidence`,
    ),
  };
}

function parseStartupProfileField(
  value: unknown,
  fieldName: StartupProfileFieldName,
): StartupProfileFieldResponse {
  const field = `fields.${fieldName}`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "status",
      "values",
      "confidence",
      "evidence_refs",
      "dependency_refs",
      "reason_code",
      "contradiction_ids",
    ],
    field,
  );
  const evidenceRefs = requireApiArray(
    record.evidence_refs,
    `${field}.evidence_refs`,
    (item, index) =>
      parseStartupProfileEvidenceRef(
        item,
        `${field}.evidence_refs[${index}]`,
      ),
  );
  if (
    evidenceRefs.some(
      (reference) =>
        reference.field_name !== null && reference.field_name !== fieldName,
    )
  ) {
    throw new ApiContractError(`${field}.evidence_refs field name mismatch`);
  }
  const parsed: StartupProfileFieldResponse = {
    status: requireApiLiteral(
      record.status,
      startupProfileFieldStatuses,
      `${field}.status`,
    ),
    values: requireStartupProfileValues(record.values, `${field}.values`),
    confidence: requireStartupProfileConfidence(
      record.confidence,
      `${field}.confidence`,
    ),
    evidence_refs: evidenceRefs,
    dependency_refs: requireStartupProfileUuidArray(
      record.dependency_refs,
      `${field}.dependency_refs`,
    ),
    reason_code: requireStartupProfileNullableSafeCode(
      record.reason_code,
      `${field}.reason_code`,
    ),
    contradiction_ids: requireStartupProfileUuidArray(
      record.contradiction_ids,
      `${field}.contradiction_ids`,
    ),
  };

  if (
    parsed.status === "source_fact" &&
    (parsed.values.length === 0 || parsed.evidence_refs.length === 0)
  ) {
    throw new ApiContractError(`${field} source_fact requires evidence refs and values`);
  }
  if (
    parsed.status === "inference" &&
    (parsed.values.length === 0 ||
      parsed.dependency_refs.length === 0 ||
      parsed.reason_code === null)
  ) {
    throw new ApiContractError(`${field} inference requires dependency refs, reason code, and values`);
  }
  if (parsed.status === "insufficient_data" && parsed.values.length > 0) {
    throw new ApiContractError(`${field} insufficient_data must not invent values`);
  }
  if (
    parsed.status === "contradiction" &&
    (parsed.values.length < 2 ||
      (parsed.evidence_refs.length < 2 &&
        parsed.contradiction_ids.length === 0) ||
      parsed.reason_code === null)
  ) {
    throw new ApiContractError(
      `${field} contradiction requires competing refs or contradiction ids, reason code, and values`,
    );
  }
  return parsed;
}

function parseStartupProfileFields(
  value: unknown,
): Readonly<Record<StartupProfileFieldName, StartupProfileFieldResponse>> {
  const record = requireApiRecord(value, "fields");
  const keys = Object.keys(record);
  if (
    keys.length !== STARTUP_PROFILE_FIELD_NAMES.length ||
    STARTUP_PROFILE_FIELD_NAMES.some((fieldName) => !(fieldName in record)) ||
    keys.some(
      (fieldName) =>
        !STARTUP_PROFILE_FIELD_NAMES.includes(
          fieldName as StartupProfileFieldName,
        ),
    )
  ) {
    throw new ApiContractError(
      "fields must contain each startup_profile@1 field exactly once",
    );
  }
  return Object.fromEntries(
    STARTUP_PROFILE_FIELD_NAMES.map((fieldName) => [
      fieldName,
      parseStartupProfileField(record[fieldName], fieldName),
    ]),
  ) as Record<StartupProfileFieldName, StartupProfileFieldResponse>;
}

function parseStartupProfileStringMap(
  value: unknown,
  field: string,
  valueParser: (item: unknown, itemField: string) => string,
): Readonly<Record<string, string>> {
  const record = requireApiRecord(value, field);
  return Object.fromEntries(
    Object.entries(record).map(([key, item]) => {
      const safeKey = requireStartupProfileSafeCode(key, `${field} key`);
      return [safeKey, valueParser(item, `${field}.${safeKey}`)];
    }),
  );
}

function parseStartupProfileInventory(
  value: unknown,
): StartupProfileParseInventoryResponse {
  const record = requireApiRecord(value, "parse_inventory");
  requireApiExactKeys(
    record,
    ["source_hashes", "parse_outcomes"],
    "parse_inventory",
  );
  const sourceHashes = parseStartupProfileStringMap(
    record.source_hashes,
    "parse_inventory.source_hashes",
    requireStartupGtmSnapshotHash,
  );
  const parseOutcomes = parseStartupProfileStringMap(
    record.parse_outcomes,
    "parse_inventory.parse_outcomes",
    requireStartupProfileSafeCode,
  );
  if (
    Object.keys(sourceHashes).length !== Object.keys(parseOutcomes).length ||
    Object.keys(sourceHashes).some((key) => !(key in parseOutcomes))
  ) {
    throw new ApiContractError(
      "parse_inventory source hashes and outcomes must describe the same sources",
    );
  }
  return { source_hashes: sourceHashes, parse_outcomes: parseOutcomes };
}

export function parseStartupProfileResponse(
  value: unknown,
): StartupProfileResponse {
  const record = requireApiRecord(value, "startup_profile");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "profile_id",
      "profile_hash",
      "data_revision",
      "analysis_stage",
      "parent_profile_id",
      "fields",
      "contradictions",
      "gaps",
      "parse_inventory",
    ],
    "startup_profile",
  );
  const analysisStage = requireApiLiteral(
    record.analysis_stage,
    startupProfileAnalysisStages,
    "analysis_stage",
  );
  const parentProfileId = requireStartupProfileNullableUuid(
    record.parent_profile_id,
    "parent_profile_id",
  );
  if (
    (analysisStage === "primary" && parentProfileId !== null) ||
    (analysisStage === "enriched" && parentProfileId === null)
  ) {
    throw new ApiContractError(
      "parent_profile_id must match the startup profile analysis stage",
    );
  }
  const dataRevision = requireApiInteger(record.data_revision, "data_revision");
  if (dataRevision < 1) {
    throw new ApiContractError("data_revision must be positive");
  }
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    profile_id: requireStartupProfileUuid(record.profile_id, "profile_id"),
    profile_hash: requireStartupGtmSnapshotHash(
      record.profile_hash,
      "profile_hash",
    ),
    data_revision: dataRevision,
    analysis_stage: analysisStage,
    parent_profile_id: parentProfileId,
    fields: parseStartupProfileFields(record.fields),
    contradictions: requireStartupProfileUuidArray(
      record.contradictions,
      "contradictions",
    ),
    gaps: requireStartupProfileSafeCodeArray(record.gaps, "gaps"),
    parse_inventory: parseStartupProfileInventory(record.parse_inventory),
  };
}

const founderSafeReportTopLevelKeys = [
  "title_ru",
  "subtitle_ru",
  "as_of_ru",
  "data_revision",
  "main_sections",
  "metric_cards",
  "improvement_proposals",
  "technical_appendix",
  "analytics",
] as const;
const founderReportSectionStatuses = [
  "confirmed",
  "partial",
  "needs_input",
  "contradiction",
] as const;
const founderReportImprovementAreas = [
  "positioning",
  "monetization",
  "metrics",
  "gtm",
  "risk_reduction",
  "investor_readiness",
] as const;
const founderReportAnalyticsPointStatuses = [
  "confirmed",
  "calculated",
  "estimated",
  "contradiction",
] as const;
const founderReportReadinessStatuses = ["ready", "provisional", "blocked"] as const;
const founderSafeReportKeyPattern = /^[a-z][a-z0-9_]{0,63}$/u;
const founderSafeReportUnsafePattern =
  /(?:\bMISSING\b|sha256:[0-9a-f]{64}|\b[0-9a-f]{64}\b|[A-Za-z]:[\\/]|file:\/\/|\b(?:document_text_block|prompt_versions|trace_ids?|source_hashes|source_appendix|report_hash|snapshot_hash|case_snapshot_hash|profile_hash|profile_id|artifact_hash|locator_hash|evidence_refs|calculation_ref|dimension_ref|chain[-_ ]?of[-_ ]?thought|reasoning_trace|system prompt|api token|secret|private key)\b|\bsk-[A-Za-z0-9_-]{8,})/iu;
const startupReportPrivateValuePattern =
  /(?:[A-Za-z]:[\\/]|file:\/\/|(?:^|[\s("'=])\/(?:Users|home|tmp|var|etc)\/|\bsk-[A-Za-z0-9_-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\braw excerpt\b|\bsystem prompt\b|\bapi token\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})/iu;

function requireStartupReportSafeString(
  value: unknown,
  field: string,
  maxLength = 2_048,
): string {
  const text = requireApiString(value, field).trim();
  if (
    text.length > maxLength ||
    [...text].some((character) => character.charCodeAt(0) < 32) ||
    startupReportPrivateValuePattern.test(text)
  ) {
    throw new ApiContractError(`${field} contains unsafe report content`);
  }
  return text;
}

function requireStartupReportPositiveInteger(value: unknown, field: string): number {
  const integer = requireApiInteger(value, field);
  if (integer < 1) {
    throw new ApiContractError(`${field} must be positive`);
  }
  return integer;
}



export function parseStartupReportSnapshotResponse(
  value: unknown,
): StartupReportSnapshotResponse {
  return parseFounderSafeStartupReportResponse(value);
}

function parseFounderSafeStartupReportResponse(
  value: unknown,
): StartupReportSnapshotResponse {
  const record = requireApiRecord(value, "startup_report_snapshot");
  requireApiExactKeys(record, founderSafeReportTopLevelKeys, "startup_report_snapshot");
  return {
    title_ru: requireFounderSafeReportString(record.title_ru, "title_ru", 160),
    subtitle_ru: requireFounderSafeReportString(record.subtitle_ru, "subtitle_ru", 240),
    as_of_ru: requireFounderSafeReportString(record.as_of_ru, "as_of_ru", 64),
    data_revision: requireStartupReportPositiveInteger(
      record.data_revision,
      "data_revision",
    ),
    main_sections: parseFounderReportSections(record.main_sections),
    metric_cards: parseFounderReportMetricCards(record.metric_cards),
    improvement_proposals: parseFounderReportImprovementProposals(
      record.improvement_proposals,
    ),
    technical_appendix: parseFounderReportTechnicalAppendix(
      record.technical_appendix,
    ),
    analytics: parseFounderReportAnalytics(record.analytics),
  };
}

function requireFounderSafeReportString(
  value: unknown,
  field: string,
  maxLength = 2_048,
): string {
  const text = requireStartupReportSafeString(value, field, maxLength);
  if (founderSafeReportUnsafePattern.test(text)) {
    throw new ApiContractError(`${field} contains internal report content`);
  }
  return text;
}

function requireFounderSafeReportCode(value: unknown, field: string): string {
  const code = requireFounderSafeReportString(value, field, 80);
  if (!founderSafeReportKeyPattern.test(code)) {
    throw new ApiContractError(`${field} must be a safe report key`);
  }
  return code;
}

function requireFounderSafeReportStringArray(
  value: unknown,
  field: string,
  maxItems = 64,
): readonly string[] {
  const items = requireApiStringArray(value, field);
  if (items.length > maxItems) {
    throw new ApiContractError(`${field} must be bounded`);
  }
  return items.map((item, index) =>
    requireFounderSafeReportString(item, `${field}[${index}]`, 512),
  );
}

function parseFounderReportSections(
  value: unknown,
): readonly FounderReportSectionResponse[] {
  if (!Array.isArray(value) || value.length > 32) {
    throw new ApiContractError("main_sections must be a bounded array");
  }
  const seen = new Set<string>();
  return value.map((item, index) => {
    const field = `main_sections[${index}]`;
    const record = requireApiRecord(item, field);
    requireApiExactKeys(
      record,
      [
        "key",
        "title_ru",
        "status",
        "status_label_ru",
        "summary_ru",
        "content_heading_ru",
        "known_facts_ru",
        "blockers_ru",
        "next_data_ru",
        "unlocks_ru",
      ],
      field,
    );
    const key = requireApiLiteral(
      requireFounderSafeReportCode(record.key, `${field}.key`),
      STARTUP_REPORT_SECTION_KEYS.slice(0, 12),
      `${field}.key`,
    );
    if (seen.has(key)) {
      throw new ApiContractError(`${field}.key is duplicated`);
    }
    seen.add(key);
    return {
      key,
      title_ru: requireFounderSafeReportString(record.title_ru, `${field}.title_ru`, 160),
      status: requireApiLiteral(
        record.status,
        founderReportSectionStatuses,
        `${field}.status`,
      ),
      status_label_ru: requireFounderSafeReportString(
        record.status_label_ru,
        `${field}.status_label_ru`,
        80,
      ),
      summary_ru: requireFounderSafeReportString(
        record.summary_ru,
        `${field}.summary_ru`,
        512,
      ),
      content_heading_ru: requireFounderSafeReportString(
        record.content_heading_ru,
        `${field}.content_heading_ru`,
        120,
      ),
      known_facts_ru: requireFounderSafeReportStringArray(
        record.known_facts_ru,
        `${field}.known_facts_ru`,
      ),
      blockers_ru: requireFounderSafeReportStringArray(
        record.blockers_ru,
        `${field}.blockers_ru`,
      ),
      next_data_ru: requireFounderSafeReportStringArray(
        record.next_data_ru,
        `${field}.next_data_ru`,
      ),
      unlocks_ru: requireFounderSafeReportStringArray(
        record.unlocks_ru,
        `${field}.unlocks_ru`,
      ),
    };
  });
}

function parseFounderReportMetricCards(
  value: unknown,
): Readonly<Record<string, FounderReportMetricCardResponse>> {
  const record = requireApiRecord(value, "metric_cards");
  if (Object.keys(record).length > 32) {
    throw new ApiContractError("metric_cards must be bounded");
  }
  return Object.fromEntries(
    Object.entries(record).map(([key, item]) => {
      if (!founderSafeReportKeyPattern.test(key)) {
        throw new ApiContractError("metric_cards contains unsafe key");
      }
      const field = `metric_cards.${key}`;
      const card = requireApiRecord(item, field);
      requireApiExactKeys(
        card,
        ["title_ru", "summary_ru", "status", "why_it_matters_ru", "next_unlock_ru"],
        field,
      );
      return [
        key,
        {
          title_ru: requireFounderSafeReportString(card.title_ru, `${field}.title_ru`, 120),
          summary_ru: requireFounderSafeReportString(card.summary_ru, `${field}.summary_ru`, 512),
          status: requireApiLiteral(
            card.status,
            founderReportSectionStatuses,
            `${field}.status`,
          ),
          why_it_matters_ru: requireFounderSafeReportString(
            card.why_it_matters_ru,
            `${field}.why_it_matters_ru`,
            512,
          ),
          next_unlock_ru: requireFounderSafeReportString(
            card.next_unlock_ru,
            `${field}.next_unlock_ru`,
            512,
          ),
        },
      ];
    }),
  );
}

function parseFounderReportImprovementProposals(
  value: unknown,
): readonly FounderReportImprovementProposalResponse[] {
  if (!Array.isArray(value) || value.length > 24) {
    throw new ApiContractError("improvement_proposals must be a bounded array");
  }
  return value.map((item, index) => {
    const field = `improvement_proposals[${index}]`;
    const record = requireApiRecord(item, field);
    requireApiExactKeys(
      record,
      [
        "target_area",
        "title_ru",
        "recommendation_ru",
        "rationale_ru",
        "expected_effect_ru",
        "provenance",
      ],
      field,
    );
    return {
      target_area: requireApiLiteral(
        record.target_area,
        founderReportImprovementAreas,
        `${field}.target_area`,
      ),
      title_ru: requireFounderSafeReportString(record.title_ru, `${field}.title_ru`, 160),
      recommendation_ru: requireFounderSafeReportString(
        record.recommendation_ru,
        `${field}.recommendation_ru`,
        512,
      ),
      rationale_ru: requireFounderSafeReportString(record.rationale_ru, `${field}.rationale_ru`, 512),
      expected_effect_ru: requireFounderSafeReportString(
        record.expected_effect_ru,
        `${field}.expected_effect_ru`,
        512,
      ),
      provenance: requireApiLiteral(
        record.provenance,
        ["ai_recommendation"] as const,
        `${field}.provenance`,
      ),
    };
  });
}

function parseFounderReportTechnicalAppendix(
  value: unknown,
): FounderReportTechnicalAppendixResponse {
  const record = requireApiRecord(value, "technical_appendix");
  requireApiExactKeys(record, ["methodology_ru", "sources_ru"], "technical_appendix");
  return {
    methodology_ru: requireFounderSafeReportStringArray(
      record.methodology_ru,
      "technical_appendix.methodology_ru",
      16,
    ),
    sources_ru: requireFounderSafeReportStringArray(
      record.sources_ru,
      "technical_appendix.sources_ru",
      16,
    ),
  };
}

function parseFounderReportAnalytics(value: unknown): FounderReportAnalyticsResponse {
  const record = requireApiRecord(value, "analytics");
  requireApiExactKeys(
    record,
    ["metric_points", "market_points", "readiness_dimensions"],
    "analytics",
  );
  return {
    metric_points: parseFounderReportAnalyticsPoints(
      record.metric_points,
      "analytics.metric_points",
    ),
    market_points: parseFounderReportAnalyticsPoints(
      record.market_points,
      "analytics.market_points",
    ),
    readiness_dimensions: parseFounderReportReadinessDimensions(
      record.readiness_dimensions,
    ),
  };
}

function parseFounderReportAnalyticsPoints(
  value: unknown,
  field: string,
): readonly FounderReportAnalyticsPoint[] {
  if (!Array.isArray(value) || value.length > 64) {
    throw new ApiContractError(`${field} must be a bounded array`);
  }
  return value.map((item, index) => {
    const itemField = `${field}[${index}]`;
    const record = requireApiRecord(item, itemField);
    requireApiExactKeys(
      record,
      ["key", "label_ru", "value", "unit", "period_ru", "status"],
      itemField,
    );
    const pointValue = typeof record.value === "number" ? record.value : NaN;
    if (!Number.isFinite(pointValue) || pointValue < 0) {
      throw new ApiContractError(`${itemField}.value must be non-negative`);
    }
    return {
      key: requireFounderSafeReportCode(record.key, `${itemField}.key`),
      label_ru: requireFounderSafeReportString(record.label_ru, `${itemField}.label_ru`, 120),
      value: pointValue,
      unit:
        record.unit === null
          ? null
          : requireFounderSafeReportString(record.unit, `${itemField}.unit`, 40),
      period_ru:
        record.period_ru === null
          ? null
          : requireFounderSafeReportString(record.period_ru, `${itemField}.period_ru`, 80),
      status: requireApiLiteral(
        record.status,
        founderReportAnalyticsPointStatuses,
        `${itemField}.status`,
      ),
    };
  });
}

function parseFounderReportReadinessDimensions(
  value: unknown,
): readonly FounderReportReadinessDimensionResponse[] {
  if (!Array.isArray(value) || value.length > 64) {
    throw new ApiContractError("analytics.readiness_dimensions must be a bounded array");
  }
  return value.map((item, index) => {
    const field = `analytics.readiness_dimensions[${index}]`;
    const record = requireApiRecord(item, field);
    requireApiExactKeys(
      record,
      ["key", "label_ru", "status", "status_label_ru", "explanation_ru"],
      field,
    );
    return {
      key: requireFounderSafeReportCode(record.key, `${field}.key`),
      label_ru: requireFounderSafeReportString(record.label_ru, `${field}.label_ru`, 120),
      status: requireApiLiteral(
        record.status,
        founderReportReadinessStatuses,
        `${field}.status`,
      ),
      status_label_ru: requireFounderSafeReportString(
        record.status_label_ru,
        `${field}.status_label_ru`,
        80,
      ),
      explanation_ru: requireFounderSafeReportString(
        record.explanation_ru,
        `${field}.explanation_ru`,
        512,
      ),
    };
  });
}

function parseStartupGtmDimension(
  value: unknown,
  index: number,
): StartupGtmDimension {
  const field = `dimensions[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "name",
      "status",
      "evidence_fact_ids",
      "market_source_ids",
      "contradiction_ids",
      "reason_code",
      "gap_code",
    ],
    field,
  );
  const dimension = {
    name: requireApiLiteral(
      record.name,
      startupGtmDimensionNames,
      `${field}.name`,
    ),
    status: requireApiLiteral(
      record.status,
      startupGtmDimensionStatuses,
      `${field}.status`,
    ),
    evidence_fact_ids: requireStartupGtmSafeRefs(
      record.evidence_fact_ids,
      `${field}.evidence_fact_ids`,
    ),
    market_source_ids: requireStartupGtmSafeRefs(
      record.market_source_ids,
      `${field}.market_source_ids`,
    ),
    contradiction_ids: requireStartupGtmSafeRefs(
      record.contradiction_ids,
      `${field}.contradiction_ids`,
    ),
    reason_code: requireStartupGtmSafeCode(
      record.reason_code,
      `${field}.reason_code`,
    ),
    gap_code: requireStartupGtmNullableSafeCode(
      record.gap_code,
      `${field}.gap_code`,
    ),
  };
  if (dimension.status === "missing" && dimension.gap_code === null) {
    throw new ApiContractError(`${field}.gap_code is required for missing dimensions`);
  }
  if (dimension.status !== "missing" && dimension.gap_code !== null) {
    throw new ApiContractError(`${field}.gap_code is allowed only for missing dimensions`);
  }
  if (
    dimension.status === "supported" &&
    dimension.evidence_fact_ids.length === 0 &&
    dimension.market_source_ids.length === 0
  ) {
    throw new ApiContractError(
      `${field} supported dimension requires evidence references`,
    );
  }
  if (dimension.status === "contradicted" && dimension.contradiction_ids.length === 0) {
    throw new ApiContractError(
      `${field} contradicted dimension requires contradiction references`,
    );
  }
  return dimension;
}

function parseStartupGtmLaunchStep(
  value: unknown,
  index: number,
): StartupGtmLaunchStep {
  const field = `launch_plan[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(record, ["horizon", "experiment_codes"], field);
  return {
    horizon: requireApiLiteral(
      record.horizon,
      startupGtmLaunchHorizons,
      `${field}.horizon`,
    ),
    experiment_codes: requireStartupGtmExperimentCodes(
      record.experiment_codes,
      `${field}.experiment_codes`,
    ),
  };
}

function requireApiArray<T>(
  value: unknown,
  field: string,
  parser: (item: unknown, index: number) => T,
): readonly T[] {
  if (!Array.isArray(value)) {
    throw new ApiContractError(`${field} must be an array`);
  }
  return value.map(parser);
}

function requireCompleteStartupGtmDimensions(
  dimensions: readonly StartupGtmDimension[],
): void {
  const names = dimensions.map((dimension) => dimension.name);
  if (
    dimensions.length !== startupGtmDimensionNames.length ||
    new Set(names).size !== startupGtmDimensionNames.length ||
    startupGtmDimensionNames.some((name) => !names.includes(name))
  ) {
    throw new ApiContractError(
      "dimensions must contain each startup_gtm@1 dimension exactly once",
    );
  }
}

function requireCompleteStartupGtmLaunchPlan(
  launchPlan: readonly StartupGtmLaunchStep[],
): void {
  const horizons = launchPlan.map((step) => step.horizon);
  if (
    launchPlan.length !== startupGtmLaunchHorizons.length ||
    new Set(horizons).size !== startupGtmLaunchHorizons.length ||
    startupGtmLaunchHorizons.some((horizon) => !horizons.includes(horizon))
  ) {
    throw new ApiContractError(
      "launch_plan must contain each startup_gtm@1 horizon exactly once",
    );
  }
}

export function parseStartupGtmResponse(value: unknown): StartupGtmResponse {
  const record = requireApiRecord(value, "startup_gtm");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "schema_version",
      "snapshot_id",
      "snapshot_hash",
      "snapshot_revision",
      "status",
      "profile_id",
      "product_validation_snapshot_id",
      "market_research_snapshot_id",
      "dimensions",
      "launch_plan",
      "finding_ids",
      "built_at",
    ],
    "startup_gtm",
  );
  const dimensions = requireApiArray(
    record.dimensions,
    "dimensions",
    parseStartupGtmDimension,
  );
  const launchPlan = requireApiArray(
    record.launch_plan,
    "launch_plan",
    parseStartupGtmLaunchStep,
  );
  requireCompleteStartupGtmDimensions(dimensions);
  requireCompleteStartupGtmLaunchPlan(launchPlan);

  return {
    case_id: requireApiString(record.case_id, "case_id"),
    schema_version: requireApiLiteral(
      record.schema_version,
      ["startup_gtm@1"] as const,
      "schema_version",
    ),
    snapshot_id: requireApiString(record.snapshot_id, "snapshot_id"),
    snapshot_hash: requireStartupGtmSnapshotHash(record.snapshot_hash, "snapshot_hash"),
    snapshot_revision: requireApiInteger(
      record.snapshot_revision,
      "snapshot_revision",
    ),
    status: requireApiLiteral(record.status, startupGtmStatuses, "status"),
    profile_id: requireApiString(record.profile_id, "profile_id"),
    product_validation_snapshot_id: requireApiString(
      record.product_validation_snapshot_id,
      "product_validation_snapshot_id",
    ),
    market_research_snapshot_id: requireApiString(
      record.market_research_snapshot_id,
      "market_research_snapshot_id",
    ),
    dimensions,
    launch_plan: launchPlan,
    finding_ids: requireStartupGtmSafeRefs(record.finding_ids, "finding_ids"),
    built_at: requireApiString(record.built_at, "built_at"),
  };
}

const advisorAnswerTypes = ["manual", "file", "public_research", "skip"] as const;
const advisorQuestionOrigins = [
  "static",
  "document_gap",
  "document_contradiction",
  "answered_state",
] as const;
const advisorQuestionStatuses = ["active", "complete"] as const;
const advisorAnswerStatuses = ["applied", "blocked"] as const;
const advisorRecalculationStatuses = ["not_requested", "started", "deferred"] as const;
const advisorResearchStatuses = [
  "completed",
  "partial",
  "deferred",
  "blocked",
] as const;
const advisorImprovementDecisions = ["accepted", "rejected"] as const;
const advisorPrivateValuePattern =
  /(?:\bMISSING\b|sha256:[0-9a-f]{64}|[A-Za-z]:[\\/][^\s]+|\b[\w-]+\.(?:pdf|docx|xlsx|csv|png|jpg|jpeg|webp|zip)\b|\b(?:system prompt|prompt_versions|trace_ids|trace|token|secret|private key|sk-[A-Za-z0-9_-]{8,})\b)/iu;
const advisorPrivateCodeValuePattern =
  /(?:sha256:[0-9a-f]{64}|[A-Za-z]:[\\/][^\s]+|\b[\w-]+\.(?:pdf|docx|xlsx|csv|png|jpg|jpeg|webp|zip)\b|\b(?:system prompt|prompt_versions|trace_ids|trace|token|secret|private key|sk-[A-Za-z0-9_-]{8,})\b)/iu;
const advisorMissingSentinelCodePattern = /\bMISSING\b/u;
const advisorSafeCodePattern = /^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,119}$/;

function requireAdvisorSafeText(
  value: unknown,
  field: string,
  maxLength = 512,
): string {
  const text = requireApiString(value, field).trim();
  if (
    text.length > maxLength ||
    [...text].some((character) => character.charCodeAt(0) < 32) ||
    advisorPrivateValuePattern.test(text)
  ) {
    throw new ApiContractError(`${field} contains unsafe advisor content`);
  }
  return text;
}

function requireAdvisorSafeCode(value: unknown, field: string): string {
  const code = requireApiString(value, field).trim();
  if (
    !advisorSafeCodePattern.test(code) ||
    advisorMissingSentinelCodePattern.test(code) ||
    advisorPrivateCodeValuePattern.test(code)
  ) {
    throw new ApiContractError(`${field} contains unsafe advisor code`);
  }
  return code;
}

function requireAdvisorProgress(value: unknown, field: string): number {
  const progress = requireApiInteger(value, field);
  if (progress < 0 || progress > 20) {
    throw new ApiContractError(`${field} must be between 0 and 20`);
  }
  return progress;
}

function requireAdvisorTotalCount(value: unknown): number {
  const total = requireApiInteger(value, "total_count");
  if (total < 1 || total > 20) {
    throw new ApiContractError("total_count must be between 1 and 20");
  }
  return total;
}

function requireAdvisorVersion(value: unknown, field: string): number {
  const version = requireApiInteger(value, field);
  if (version < 1) {
    throw new ApiContractError(`${field} must be positive`);
  }
  return version;
}

function requireAdvisorConfidence(value: unknown, field: string): number {
  const numberValue =
    typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  if (
    typeof numberValue !== "number" ||
    !Number.isFinite(numberValue) ||
    numberValue < 0 ||
    numberValue > 1
  ) {
    throw new ApiContractError(`${field} must be a confidence between 0 and 1`);
  }
  return numberValue;
}

function parseAdvisorQuestion(value: unknown): AdvisorQuestionDto {
  const record = requireApiRecord(value, "next_question");
  requireApiExactKeys(
    record,
    [
      "question_id",
      "field_key",
      "question_ru",
      "reason_ru",
      "unlocks_ru",
      "answer_modes",
      "origin",
      "origin_label_ru",
      "context_ru",
      "answer_mode_labels_ru",
    ],
    "next_question",
  );
  if (!Array.isArray(record.answer_modes) || record.answer_modes.length === 0) {
    throw new ApiContractError("next_question.answer_modes must be non-empty");
  }
  const answerModes = record.answer_modes.map((mode, index) =>
    requireApiLiteral(mode, advisorAnswerTypes, `next_question.answer_modes[${index}]`),
  );
  if (new Set(answerModes).size !== answerModes.length) {
    throw new ApiContractError("next_question.answer_modes must be unique");
  }
  const rawLabels = requireApiRecord(
    record.answer_mode_labels_ru,
    "next_question.answer_mode_labels_ru",
  );
  const labels = Object.fromEntries(
    advisorAnswerTypes.map((mode) => [
      mode,
      requireAdvisorSafeText(
        rawLabels[mode],
        `next_question.answer_mode_labels_ru.${mode}`,
        80,
      ),
    ]),
  ) as Record<AdvisorAnswerType, string>;

  return {
    question_id: requireAdvisorSafeCode(record.question_id, "next_question.question_id"),
    field_key: requireAdvisorSafeCode(record.field_key, "next_question.field_key"),
    question_ru: requireAdvisorSafeText(record.question_ru, "next_question.question_ru"),
    reason_ru: requireAdvisorSafeText(record.reason_ru, "next_question.reason_ru"),
    unlocks_ru: requireAdvisorSafeText(record.unlocks_ru, "next_question.unlocks_ru"),
    answer_modes: answerModes,
    origin: requireApiLiteral(
      record.origin,
      advisorQuestionOrigins,
      "next_question.origin",
    ),
    origin_label_ru: requireAdvisorSafeText(
      record.origin_label_ru,
      "next_question.origin_label_ru",
      80,
    ),
    context_ru:
      record.context_ru === null
        ? null
        : requireAdvisorSafeText(record.context_ru, "next_question.context_ru", 240),
    answer_mode_labels_ru: labels,
  };
}

export function parseAdvisorNextQuestionResponse(
  value: unknown,
): AdvisorNextQuestionResponse {
  const record = requireApiRecord(value, "advisor_next_question");
  requireApiExactKeys(
    record,
    ["case_id", "status", "next_question", "answered_count", "total_count"],
    "advisor_next_question",
  );
  const status = requireApiLiteral(record.status, advisorQuestionStatuses, "status");
  const question =
    record.next_question === null ? null : parseAdvisorQuestion(record.next_question);
  if (status === "active" && question === null) {
    throw new ApiContractError("next_question is required when advisor is active");
  }
  const answeredCount = requireAdvisorProgress(record.answered_count, "answered_count");
  const totalCount = requireAdvisorTotalCount(record.total_count);
  if (answeredCount > totalCount) {
    throw new ApiContractError("answered_count must not exceed total_count");
  }
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    status,
    next_question: question,
    answered_count: answeredCount,
    total_count: totalCount,
  };
}

function parseAdvisorResearchResult(value: unknown): AdvisorResearchResult {
  const record = requireApiRecord(value, "research_result");
  requireApiExactKeys(
    record,
    ["status", "summary_ru", "source_ids", "fallback_used", "fail_reason_ru"],
    "research_result",
  );
  return {
    status: requireApiLiteral(record.status, advisorResearchStatuses, "research_result.status"),
    summary_ru: requireAdvisorSafeText(record.summary_ru, "research_result.summary_ru"),
    source_ids: requireApiStringArray(record.source_ids, "research_result.source_ids").map(
      (sourceId, index) => requireStartupProfileUuid(sourceId, `research_result.source_ids[${index}]`),
    ),
    fallback_used: requireApiBoolean(record.fallback_used, "research_result.fallback_used"),
    fail_reason_ru:
      record.fail_reason_ru === null
        ? null
        : requireAdvisorSafeText(record.fail_reason_ru, "research_result.fail_reason_ru"),
  };
}

function parseAdvisorSafeCodeArray(value: unknown, field: string): readonly string[] {
  return requireApiStringArray(value, field).map((item, index) =>
    requireAdvisorSafeCode(item, `${field}[${index}]`),
  );
}

function parseAdvisorRecalculationDelta(value: unknown): AdvisorRecalculationDelta {
  const record = requireApiRecord(value, "recalculation_delta");
  requireApiExactKeys(
    record,
    [
      "previous_revision",
      "new_revision",
      "fields_changed",
      "core_coverage_delta",
      "conflicts_resolved",
      "conflicts_remaining",
      "calculations_recalculated",
      "calculations_pending",
    ],
    "recalculation_delta",
  );
  const previousRevision = requireAdvisorVersion(
    record.previous_revision,
    "recalculation_delta.previous_revision",
  );
  const newRevision = requireAdvisorVersion(
    record.new_revision,
    "recalculation_delta.new_revision",
  );
  const coreCoverageDelta = requireApiInteger(
    record.core_coverage_delta,
    "recalculation_delta.core_coverage_delta",
  );
  if (coreCoverageDelta < -20 || coreCoverageDelta > 20) {
    throw new ApiContractError("recalculation_delta.core_coverage_delta must be bounded");
  }
  const conflictsResolved = requireApiInteger(
    record.conflicts_resolved,
    "recalculation_delta.conflicts_resolved",
  );
  const conflictsRemaining = requireApiInteger(
    record.conflicts_remaining,
    "recalculation_delta.conflicts_remaining",
  );
  if (conflictsResolved < 0 || conflictsRemaining < 0) {
    throw new ApiContractError("recalculation_delta conflict counts must be non-negative");
  }
  return {
    previous_revision: previousRevision,
    new_revision: newRevision,
    fields_changed: parseAdvisorSafeCodeArray(
      record.fields_changed,
      "recalculation_delta.fields_changed",
    ),
    core_coverage_delta: coreCoverageDelta,
    conflicts_resolved: conflictsResolved,
    conflicts_remaining: conflictsRemaining,
    calculations_recalculated: parseAdvisorSafeCodeArray(
      record.calculations_recalculated,
      "recalculation_delta.calculations_recalculated",
    ),
    calculations_pending: parseAdvisorSafeCodeArray(
      record.calculations_pending,
      "recalculation_delta.calculations_pending",
    ),
  };
}

export function parseAdvisorAnswerResponse(value: unknown): AdvisorAnswerResponse {
  const record = requireApiRecord(value, "advisor_answer");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "question_id",
      "field_key",
      "answer_type",
      "status",
      "confidence_delta",
      "analysis_blocked",
      "answered_count",
      "total_count",
      "research_result",
      "recalculation_status",
      "recalculation_data_revision",
      "recalculation_analysis_status",
      "recalculation_delta",
    ],
    "advisor_answer",
  );
  const delta = requireApiInteger(record.confidence_delta, "confidence_delta");
  if (delta < -100 || delta > 100) {
    throw new ApiContractError("confidence_delta must be bounded");
  }
  const answeredCount = requireAdvisorProgress(record.answered_count, "answered_count");
  const totalCount = requireAdvisorTotalCount(record.total_count);
  if (answeredCount > totalCount) {
    throw new ApiContractError("answered_count must not exceed total_count");
  }
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    question_id: requireAdvisorSafeCode(record.question_id, "question_id"),
    field_key: requireAdvisorSafeCode(record.field_key, "field_key"),
    answer_type: requireApiLiteral(record.answer_type, advisorAnswerTypes, "answer_type"),
    status: requireApiLiteral(record.status, advisorAnswerStatuses, "status"),
    confidence_delta: delta,
    analysis_blocked: requireApiBoolean(record.analysis_blocked, "analysis_blocked"),
    answered_count: answeredCount,
    total_count: totalCount,
    research_result:
      record.research_result === null
        ? null
        : parseAdvisorResearchResult(record.research_result),
    recalculation_status: requireApiLiteral(
      record.recalculation_status,
      advisorRecalculationStatuses,
      "recalculation_status",
    ),
    recalculation_data_revision:
      record.recalculation_data_revision === null
        ? null
        : requireAdvisorVersion(
            record.recalculation_data_revision,
            "recalculation_data_revision",
          ),
    recalculation_analysis_status:
      record.recalculation_analysis_status === null
        ? null
        : requireApiLiteral(
            record.recalculation_analysis_status,
            analysisStatuses,
            "recalculation_analysis_status",
          ),
    recalculation_delta:
      record.recalculation_delta === null
        ? null
        : parseAdvisorRecalculationDelta(record.recalculation_delta),
  };
}

function parseAdvisorImprovementProposal(
  value: unknown,
  index: number,
): AdvisorImprovementProposal {
  const field = `proposals[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "proposal_id",
      "target_area",
      "recommendation_ru",
      "rationale_ru",
      "expected_effect_ru",
      "evidence_kinds",
      "confidence",
    ],
    field,
  );
  return {
    proposal_id: requireStartupProfileUuid(record.proposal_id, `${field}.proposal_id`),
    target_area: requireAdvisorSafeCode(record.target_area, `${field}.target_area`),
    recommendation_ru: requireAdvisorSafeText(record.recommendation_ru, `${field}.recommendation_ru`),
    rationale_ru: requireAdvisorSafeText(record.rationale_ru, `${field}.rationale_ru`),
    expected_effect_ru: requireAdvisorSafeText(record.expected_effect_ru, `${field}.expected_effect_ru`),
    evidence_kinds: requireApiStringArray(record.evidence_kinds, `${field}.evidence_kinds`).map(
      (item, itemIndex) => requireAdvisorSafeCode(item, `${field}.evidence_kinds[${itemIndex}]`),
    ),
    confidence: requireAdvisorConfidence(record.confidence, `${field}.confidence`),
  };
}

export function parseAdvisorImprovementsResponse(
  value: unknown,
): AdvisorImprovementsResponse {
  const record = requireApiRecord(value, "advisor_improvements");
  requireApiExactKeys(
    record,
    ["case_id", "improvement_version", "proposals"],
    "advisor_improvements",
  );
  const proposals = requireApiArray(
    record.proposals,
    "proposals",
    parseAdvisorImprovementProposal,
  );
  if (proposals.length !== 6) {
    throw new ApiContractError("advisor improvements must contain six proposals");
  }
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    improvement_version: requireAdvisorVersion(
      record.improvement_version,
      "improvement_version",
    ),
    proposals,
  };
}

export function parseAdvisorImprovementDecisionResponse(
  value: unknown,
): AdvisorImprovementDecisionResponse {
  const record = requireApiRecord(value, "advisor_improvement_decision");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "proposal_id",
      "decision",
      "previous_version",
      "new_version",
      "changed_fields",
      "recalculation_status",
      "recalculation_data_revision",
      "recalculation_analysis_status",
    ],
    "advisor_improvement_decision",
  );
  const previousVersion = requireAdvisorVersion(record.previous_version, "previous_version");
  const newVersion = requireAdvisorVersion(record.new_version, "new_version");
  return {
    case_id: requireApiString(record.case_id, "case_id"),
    proposal_id: requireStartupProfileUuid(record.proposal_id, "proposal_id"),
    decision: requireApiLiteral(
      record.decision,
      advisorImprovementDecisions,
      "decision",
    ),
    previous_version: previousVersion,
    new_version: newVersion,
    changed_fields: requireApiStringArray(record.changed_fields, "changed_fields").map(
      (item, index) => requireAdvisorSafeCode(item, `changed_fields[${index}]`),
    ),
    recalculation_status: requireApiLiteral(
      record.recalculation_status,
      advisorRecalculationStatuses,
      "recalculation_status",
    ),
    recalculation_data_revision:
      record.recalculation_data_revision === null
        ? null
        : requireAdvisorVersion(
            record.recalculation_data_revision,
            "recalculation_data_revision",
          ),
    recalculation_analysis_status:
      record.recalculation_analysis_status === null
        ? null
        : requireApiLiteral(
            record.recalculation_analysis_status,
            analysisStatuses,
            "recalculation_analysis_status",
    ),
  };
}

const caseValueKinds = [
  "source_fact",
  "founder_statement",
  "public_benchmark",
  "deterministic_calculation",
  "ai_scenario",
  "contradiction",
] as const;
const scenarioKeys = ["conservative", "base", "optimistic"] as const;
const scenarioConfidences = ["low", "medium", "high"] as const;
const scenarioAcceptances = [
  "proposed",
  "accepted",
  "rejected",
  "needs_validation",
] as const;
const copilotActionKeys = [
  "open_fact_input",
  "open_document_upload",
  "prepare_public_research",
  "explain_metric",
  "navigate",
  "prepare_asset",
  "review_improvements",
] as const;
const copilotActionStatuses = [
  "available",
  "requires_input",
  "requires_consent",
  "blocked",
] as const;
const copilotMessageRoles = ["system", "system_event", "user", "assistant", "tool"] as const;
const researchPlanStatuses = ["prepared"] as const;
const researchJobStatuses = [
  "queued",
  "running",
  "completed",
  "partial",
  "deferred",
  "failed",
] as const;
const researchAcquisitionModes = [
  "deterministic_offline_fixture",
  "live_public_research",
  "provider_unconfigured",
] as const;
const publicResearchFocusKeys = [
  "market",
  "icp",
  "competitors",
  "alternatives",
  "channels",
  "public_pricing_analogs",
  "unit_economics_benchmarks",
  "regulatory_context",
] as const;
const privateFactInputKeys = [
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
] as const;

function requireCaseValueKind(value: unknown, field: string): CaseValueKind {
  return requireApiLiteral(value, caseValueKinds, field);
}

function requireScenarioKey(value: unknown, field: string): ScenarioKey {
  return requireApiLiteral(value, scenarioKeys, field);
}

function requirePositiveRevision(value: unknown, field: string): number {
  const revision = requireApiInteger(value, field);
  if (revision < 1) {
    throw new ApiContractError(`${field} must be positive`);
  }
  return revision;
}

function requireScenarioText(value: unknown, field: string): string {
  const text = requireApiString(value, field).trim();
  if (text.length > 1000) {
    throw new ApiContractError(`${field} is too long`);
  }
  return text;
}

function requireLaunchPackMarkdown(value: unknown, field: string): string {
  return requireApiString(value, field).trim();
}

function requireScenarioUuid(value: unknown, field: string): string {
  return requireStartupProfileUuid(value, field);
}

function requireScenarioUuidArray(value: unknown, field: string): readonly string[] {
  return requireApiStringArray(value, field).map((item, index) =>
    requireScenarioUuid(item, `${field}[${index}]`),
  );
}

function decimalRangeValue(value: string, field: string): number {
  if (!/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/u.test(value)) {
    throw new ApiContractError(`${field} must be a non-negative decimal string`);
  }
  return Number(value);
}

type ScenarioDecimalValue = Readonly<{
  digits: string;
  exponent: bigint;
}>;

function parseScenarioDecimalRangeValue(value: string, field: string): ScenarioDecimalValue {
  if (!/^(?:0|[1-9]\d*)(?:\.\d+)?(?:E[+-]?\d+)?$/u.test(value)) {
    throw new ApiContractError(`${field} must be a non-negative decimal string`);
  }
  const [coefficient = "", exponentText = "0"] = value.split("E", 2);
  const [integerPart = "", fractionalPart = ""] = coefficient.split(".", 2);
  const exponent = BigInt(exponentText);
  const effectiveDecimalPlaces =
    exponent >= BigInt(fractionalPart.length)
      ? BigInt(0)
      : BigInt(fractionalPart.length) - exponent;
  if (effectiveDecimalPlaces > BigInt(2)) {
    throw new ApiContractError(`${field} must have at most two decimal places`);
  }
  const rawDigits = `${integerPart}${fractionalPart}`;
  const withoutLeadingZeros = rawDigits.replace(/^0+/u, "");
  if (withoutLeadingZeros === "") {
    return { digits: "0", exponent: BigInt(0) };
  }
  const digits = withoutLeadingZeros.replace(/0+$/u, "");
  return {
    digits,
    exponent:
      exponent -
      BigInt(fractionalPart.length) +
      BigInt(withoutLeadingZeros.length - digits.length),
  };
}

function compareScenarioDecimalValues(
  left: ScenarioDecimalValue,
  right: ScenarioDecimalValue,
): number {
  if (left.digits === "0" || right.digits === "0") {
    if (left.digits === right.digits) {
      return 0;
    }
    return left.digits === "0" ? -1 : 1;
  }
  const leftMagnitude = BigInt(left.digits.length) + left.exponent;
  const rightMagnitude = BigInt(right.digits.length) + right.exponent;
  if (leftMagnitude !== rightMagnitude) {
    return leftMagnitude > rightMagnitude ? 1 : -1;
  }
  const commonExponent = left.exponent < right.exponent ? left.exponent : right.exponent;
  const normalizedLeft = left.digits.padEnd(
    left.digits.length + Number(left.exponent - commonExponent),
    "0",
  );
  const normalizedRight = right.digits.padEnd(
    right.digits.length + Number(right.exponent - commonExponent),
    "0",
  );
  if (normalizedLeft === normalizedRight) {
    return 0;
  }
  return normalizedLeft > normalizedRight ? 1 : -1;
}

function parseScenarioRange(value: unknown, field: string): ScenarioRangeResponse {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(record, ["lower", "upper"], field);
  const lower = requireApiString(record.lower, `${field}.lower`).trim();
  const upper = requireApiString(record.upper, `${field}.upper`).trim();
  if (
    compareScenarioDecimalValues(
      parseScenarioDecimalRangeValue(lower, `${field}.lower`),
      parseScenarioDecimalRangeValue(upper, `${field}.upper`),
    ) > 0
  ) {
    throw new ApiContractError(`${field} range requires lower <= upper`);
  }
  return { lower, upper };
}

function parseResearchRange(value: unknown, field: string): ResearchRangeResponse {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(record, ["low", "high"], field);
  const low = record.low === null ? null : requireApiString(record.low, `${field}.low`).trim();
  const high = record.high === null ? null : requireApiString(record.high, `${field}.high`).trim();
  if ((low === null) !== (high === null)) {
    throw new ApiContractError(`${field} requires both low and high or neither`);
  }
  if (low !== null && high !== null) {
    if (decimalRangeValue(low, `${field}.low`) > decimalRangeValue(high, `${field}.high`)) {
      throw new ApiContractError(`${field} range requires low <= high`);
    }
  }
  return { low, high };
}

type CopilotDecimalValue = Readonly<{
  digits: string;
  exponent: bigint;
}>;

function decimalCopilotRangeValue(value: string, field: string): CopilotDecimalValue {
  if (!/^(?:0|[1-9]\d*)(?:\.\d+)?(?:E[+-]?\d+)?$/u.test(value)) {
    throw new ApiContractError(`${field} must be a non-negative finite decimal string`);
  }
  const [coefficient = "", exponentText = "0"] = value.split("E", 2);
  const [integerPart = "", fractionalPart = ""] = coefficient.split(".", 2);
  const rawDigits = `${integerPart}${fractionalPart}`;
  const withoutLeadingZeros = rawDigits.replace(/^0+/u, "");
  if (withoutLeadingZeros === "") {
    return { digits: "0", exponent: BigInt(0) };
  }
  const digits = withoutLeadingZeros.replace(/0+$/u, "");
  return {
    digits,
    exponent: BigInt(exponentText) - BigInt(fractionalPart.length) + BigInt(withoutLeadingZeros.length - digits.length),
  };
}

function compareCopilotDecimalValues(left: CopilotDecimalValue, right: CopilotDecimalValue): number {
  if (left.digits === "0" || right.digits === "0") {
    if (left.digits === right.digits) {
      return 0;
    }
    return left.digits === "0" ? -1 : 1;
  }
  const leftMagnitude = BigInt(left.digits.length) + left.exponent;
  const rightMagnitude = BigInt(right.digits.length) + right.exponent;
  if (leftMagnitude !== rightMagnitude) {
    return leftMagnitude > rightMagnitude ? 1 : -1;
  }
  const commonExponent = left.exponent < right.exponent ? left.exponent : right.exponent;
  const normalizedLeft = left.digits.padEnd(
    left.digits.length + Number(left.exponent - commonExponent),
    "0",
  );
  const normalizedRight = right.digits.padEnd(
    right.digits.length + Number(right.exponent - commonExponent),
    "0",
  );
  if (normalizedLeft === normalizedRight) {
    return 0;
  }
  return normalizedLeft > normalizedRight ? 1 : -1;
}

function parseCopilotEncodedScenarioRangeValue(
  value: unknown,
  field: string,
): string | null {
  if (value === null) {
    return null;
  }
  const encoded = requireApiString(value, field);
  const parts = encoded.split(":");
  if (parts.length !== 2) {
    throw new ApiContractError(`${field} range requires exactly one lower:upper pair`);
  }
  const lower = decimalCopilotRangeValue(parts[0] ?? "", `${field}.lower`);
  const upper = decimalCopilotRangeValue(parts[1] ?? "", `${field}.upper`);
  if (compareCopilotDecimalValues(lower, upper) > 0) {
    throw new ApiContractError(`${field} range requires lower <= upper`);
  }
  return encoded;
}

function parseCopilotRange(value: unknown, field: string): CopilotScenarioRangeResponse {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(record, scenarioKeys, field);
  return {
    conservative: parseCopilotEncodedScenarioRangeValue(
      record.conservative,
      `${field}.conservative`,
    ),
    base: parseCopilotEncodedScenarioRangeValue(record.base, `${field}.base`),
    optimistic: parseCopilotEncodedScenarioRangeValue(
      record.optimistic,
      `${field}.optimistic`,
    ),
  };
}

function requireScenarioSourceRefs(
  provenance: CaseValueKind,
  sourceRefs: readonly string[],
  dependencyRefs: readonly string[],
  field: string,
  acceptance?: ScenarioAcceptance,
): void {
  if (provenance === "source_fact" && sourceRefs.length === 0) {
    throw new ApiContractError(`${field} source_fact requires source refs`);
  }
  if (provenance === "public_benchmark" && sourceRefs.length === 0) {
    throw new ApiContractError(`${field} public_benchmark requires source refs`);
  }
  if (provenance === "founder_statement" && sourceRefs.length === 0) {
    throw new ApiContractError(`${field} founder_statement requires source refs`);
  }
  if (provenance === "founder_statement" && acceptance !== undefined && acceptance !== "accepted") {
    throw new ApiContractError(`${field} founder_statement requires accepted acceptance`);
  }
  if (
    ["founder_statement", "public_benchmark", "ai_scenario"].includes(provenance) &&
    sourceRefs.some((sourceRef) => sourceRef.startsWith("source_fact:"))
  ) {
    throw new ApiContractError(`${field} non-source provenance cannot become source_fact`);
  }
  if (provenance === "deterministic_calculation" && dependencyRefs.length === 0) {
    throw new ApiContractError(`${field} deterministic calculation requires dependencies`);
  }
}

function requireMatchingUnitPeriod(unit: string, period: string | null, field: string): void {
  if (period === null || period.trim() === "") {
    throw new ApiContractError(`${field} period is required`);
  }
  if (unit.includes("/")) {
    const [currency, unitPeriod] = unit.split("/", 2);
    if (!currency?.trim() || !unitPeriod?.trim()) {
      throw new ApiContractError(`${field} unit requires currency/period`);
    }
    if (unitPeriod.trim() !== period) {
      throw new ApiContractError(`${field} unit and period must match`);
    }
  }
}

function parseFactProjection(value: unknown, index: number): CopilotFactProjection {
  const field = `extracted_facts[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(record, ["field_key", "value", "source_type"], field);
  return {
    field_key: requireAdvisorSafeCode(record.field_key, `${field}.field_key`),
    value: requireScenarioText(record.value, `${field}.value`),
    source_type: requireCaseValueKind(record.source_type, `${field}.source_type`),
  };
}

function parseGapProjection(value: unknown, index: number): CopilotGapProjection {
  const field = `prioritized_gaps[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    ["gap_code", "field_key", "privacy_class", "allowed_action"],
    field,
  );
  return {
    gap_code: requireAdvisorSafeCode(record.gap_code, `${field}.gap_code`),
    field_key: requireAdvisorSafeCode(record.field_key, `${field}.field_key`),
    privacy_class: requireAdvisorSafeCode(record.privacy_class, `${field}.privacy_class`),
    allowed_action: requireAdvisorSafeCode(record.allowed_action, `${field}.allowed_action`),
  };
}

function parseCopilotScenarioMetricProjection(
  value: unknown,
  index: number,
): CopilotScenarioMetricProjection {
  const field = `scenario_metrics[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "metric_key",
      "label",
      "source_type",
      "value",
      "range",
      "formula",
      "dependencies",
      "unit",
      "period",
      "confidence",
      "source_refs",
      "what_would_confirm",
      "validation_plan",
    ],
    field,
  );
  if (record.value !== null) {
    throw new ApiContractError(`${field}.value must be null`);
  }
  const sourceType = requireCaseValueKind(record.source_type, `${field}.source_type`);
  const sourceRefs = requireStartupGtmSafeRefs(record.source_refs, `${field}.source_refs`);
  const dependencies = requireStartupGtmSafeRefs(record.dependencies, `${field}.dependencies`);
  requireScenarioSourceRefs(sourceType, sourceRefs, dependencies, field);
  const unit = requireScenarioText(record.unit, `${field}.unit`);
  const period = requireScenarioText(record.period, `${field}.period`);
  requireMatchingUnitPeriod(unit, period, field);
  return {
    metric_key: requireAdvisorSafeCode(record.metric_key, `${field}.metric_key`),
    label: requireScenarioText(record.label, `${field}.label`),
    source_type: sourceType,
    value: null,
    range: parseCopilotRange(record.range, `${field}.range`),
    formula: requireScenarioText(record.formula, `${field}.formula`),
    dependencies,
    unit,
    period,
    confidence: requireScenarioText(record.confidence, `${field}.confidence`),
    source_refs: sourceRefs,
    what_would_confirm: requireScenarioText(
      record.what_would_confirm,
      `${field}.what_would_confirm`,
    ),
    validation_plan: requireScenarioText(record.validation_plan, `${field}.validation_plan`),
  };
}

function parseCoverageProjection(value: unknown, field: string): CopilotCoverageProjection {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    ["measure", "status", "source_fact_count", "accepted_input_count"],
    field,
  );
  const sourceFactCount = requireApiNullableInteger(
    record.source_fact_count,
    `${field}.source_fact_count`,
  );
  const acceptedInputCount = requireApiNullableInteger(
    record.accepted_input_count,
    `${field}.accepted_input_count`,
  );
  if (
    (sourceFactCount !== null && sourceFactCount < 0) ||
    (acceptedInputCount !== null && acceptedInputCount < 0)
  ) {
    throw new ApiContractError(`${field} counts must be non-negative`);
  }
  return {
    measure: requireAdvisorSafeCode(record.measure, `${field}.measure`),
    status: requireAdvisorSafeCode(record.status, `${field}.status`),
    source_fact_count: sourceFactCount,
    accepted_input_count: acceptedInputCount,
  };
}

function parseAcceptedInput(
  value: unknown,
  index: number,
): CopilotAcceptedInputProjection {
  const field = `accepted_inputs[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "field_key",
      "kind",
      "status",
      "value",
      "period",
      "rationale",
      "validation_plan",
      "declared_source",
      "source_refs",
    ],
    field,
  );
  const kind = requireCaseValueKind(record.kind, `${field}.kind`);
  const status = requireAdvisorSafeCode(record.status, `${field}.status`);
  const sourceRefs = requireScenarioUuidArray(record.source_refs, `${field}.source_refs`);
  if (isCopilotSourceStatusRow(kind, status, record.field_key)) {
    if (typeof record.value !== "string") {
      throw new ApiContractError(`${field}.value must be a string`);
    }
    const legendValue = record.value;
    if (legendValue !== "") {
      throw new ApiContractError(`${field} legend value must be empty`);
    }
    if (
      record.period !== null ||
      record.rationale !== null ||
      record.validation_plan !== null ||
      record.declared_source !== null ||
      sourceRefs.length !== 0
    ) {
      throw new ApiContractError(`${field} legend metadata must be empty`);
    }
    return {
      field_key: requireAdvisorSafeCode(record.field_key, `${field}.field_key`),
      kind,
      status,
      value: legendValue,
      period: null,
      rationale: null,
      validation_plan: null,
      declared_source: null,
      source_refs: sourceRefs,
    };
  }
  if (kind === "source_fact") {
    throw new ApiContractError(`${field}.kind must not auto-promote to source_fact`);
  }
  if (status !== "accepted") {
    throw new ApiContractError(`${field}.status must be accepted`);
  }
  if (["founder_statement", "public_benchmark"].includes(kind) && sourceRefs.length === 0) {
    throw new ApiContractError(`${field}.source_refs are required for ${kind}`);
  }
  return {
    field_key: requireAdvisorSafeCode(record.field_key, `${field}.field_key`),
    kind,
    status,
    value: requireScenarioText(record.value, `${field}.value`),
    period:
      record.period === null ? null : requireScenarioText(record.period, `${field}.period`),
    rationale:
      record.rationale === null
        ? null
        : requireScenarioText(record.rationale, `${field}.rationale`),
    validation_plan:
      record.validation_plan === null
        ? null
        : requireScenarioText(record.validation_plan, `${field}.validation_plan`),
    declared_source:
      record.declared_source === null
        ? null
        : requireScenarioText(record.declared_source, `${field}.declared_source`),
    source_refs: sourceRefs,
  };
}

function isCopilotSourceStatusRow(
  kind: CaseValueKind,
  status: string,
  rawFieldKey: unknown,
): boolean {
  const fieldKey = typeof rawFieldKey === "string" ? rawFieldKey : "";
  const expectedStatuses: Readonly<Record<CaseValueKind, string>> = {
    source_fact: "confirmed",
    founder_statement: "provisional",
    public_benchmark: "external_context",
    deterministic_calculation: "calculated",
    ai_scenario: "planning_assumption",
    contradiction: "conflict_open",
  };
  return fieldKey === kind && expectedStatuses[kind] === status;
}

function parseActionPayload(value: unknown, field: string): Record<string, CopilotPayloadValue> {
  const record = requireApiRecord(value, field);
  return Object.fromEntries(
    Object.entries(record).map(([key, item]) => {
      if (!startupGtmSafeRefPattern.test(key)) {
        throw new ApiContractError(`${field}.${key} is invalid`);
      }
      if (
        typeof item === "string" ||
        typeof item === "number" ||
        typeof item === "boolean"
      ) {
        return [key, item];
      }
      if (Array.isArray(item) && item.every((entry) => typeof entry === "string")) {
        return [key, [...item]];
      }
      throw new ApiContractError(`${field}.${key} has unsupported payload value`);
    }),
  );
}

function requireActionPayloadShape(
  action: CopilotActionAvailability,
  context: Readonly<{ caseId: string; dataRevision: number }> | null,
): void {
  if (action.status === "blocked") {
    if (action.handler !== null) {
      throw new ApiContractError("blocked action handler must be null");
    }
    if (action.reason === null) {
      throw new ApiContractError("blocked action reason is required");
    }
  } else {
    if (action.handler === null) {
      throw new ApiContractError("active action handler is required");
    }
    if (
      (action.status === "requires_input" || action.status === "requires_consent") &&
      action.reason === null
    ) {
      throw new ApiContractError(`${action.action} ${action.status} reason is required`);
    }
  }
  const keys = Object.keys(action.payload).sort();
  const expectKeys = (expected: readonly string[]) => {
    assertExactStringSet(keys, expected, `${action.action} payload`);
  };
  if (action.action === "open_fact_input") {
    expectKeys(["field_key", "provenance"]);
    if (action.status !== "requires_input" || action.handler !== "openFactInput") {
      throw new ApiContractError("open_fact_input action envelope is invalid");
    }
    if (!privateFactInputKeys.includes(action.payload.field_key as never)) {
      throw new ApiContractError("open_fact_input field_key is not approved");
    }
    if (action.payload.provenance !== "founder_statement") {
      throw new ApiContractError("open_fact_input provenance must be founder_statement");
    }
  } else if (action.action === "open_document_upload") {
    expectKeys(["case_id"]);
    if (action.status !== "available" || action.handler !== "openDocumentUpload") {
      throw new ApiContractError("open_document_upload action envelope is invalid");
    }
    const payloadCaseId = requireScenarioUuid(action.payload.case_id, "open_document_upload.payload.case_id");
    if (context && payloadCaseId !== context.caseId) {
      throw new ApiContractError("open_document_upload payload case_id must match active case");
    }
  } else if (action.action === "prepare_public_research") {
    expectKeys([
      "available_acquisition_modes",
      "default_acquisition_mode",
      "expected_case_revision",
      "focus",
      "unavailable_acquisition_modes",
    ]);
    if (action.status !== "requires_consent" || action.handler !== "prepareResearchPlan") {
      throw new ApiContractError("prepare_public_research action envelope is invalid");
    }
    if (
      typeof action.payload.focus !== "string" ||
      !publicResearchFocusKeys.includes(action.payload.focus as never)
    ) {
      throw new ApiContractError("prepare_public_research focus is not approved");
    }
    if (
      typeof action.payload.expected_case_revision !== "number" ||
      !Number.isInteger(action.payload.expected_case_revision) ||
      action.payload.expected_case_revision < 1
    ) {
      throw new ApiContractError("prepare_public_research expected revision is required");
    }
    if (
      context &&
      action.payload.expected_case_revision !== context.dataRevision
    ) {
      throw new ApiContractError("prepare_public_research expected revision must match active revision");
    }
    const availableModes = requireApiStringArray(
      action.payload.available_acquisition_modes,
      "prepare_public_research.available_acquisition_modes",
    );
    const unavailableModes = requireApiStringArray(
      action.payload.unavailable_acquisition_modes,
      "prepare_public_research.unavailable_acquisition_modes",
    );
    const selectableModes = [
      "deterministic_offline_fixture",
      "live_public_research",
    ] as const;
    for (const mode of [...availableModes, ...unavailableModes]) {
      requireApiLiteral(
        mode,
        selectableModes,
        "prepare_public_research acquisition mode",
      );
    }
    assertExactStringSet(
      [...new Set([...availableModes, ...unavailableModes])].sort(),
      [...selectableModes].sort(),
      "prepare_public_research acquisition modes",
    );
    const defaultMode = requireApiLiteral(
      action.payload.default_acquisition_mode,
      selectableModes,
      "prepare_public_research.default_acquisition_mode",
    );
    if (!availableModes.includes(defaultMode) && availableModes.length > 0) {
      throw new ApiContractError("prepare_public_research default acquisition mode must be available");
    }
  } else if (action.action === "explain_metric") {
    expectKeys(["metric_key"]);
    if (action.status !== "available" || action.handler !== "openMetricExplanation") {
      throw new ApiContractError("explain_metric action envelope is invalid");
    }
  } else if (action.action === "navigate") {
    expectKeys(["target"]);
    if (
      action.status !== "available" ||
      action.handler !== "navigate" ||
      action.payload.target !== "scenarios"
    ) {
      throw new ApiContractError("navigate action envelope is invalid");
    }
  } else if (action.action === "prepare_asset") {
    expectKeys(["required_step"]);
    if (
      action.status !== "blocked" ||
      action.handler !== null ||
      action.payload.required_step !== "review_scenarios"
    ) {
      throw new ApiContractError("prepare_asset action envelope is invalid");
    }
  } else {
    expectKeys(["same_case_fact_count"]);
    if (
      typeof action.payload.same_case_fact_count !== "number" ||
      !Number.isInteger(action.payload.same_case_fact_count) ||
      action.payload.same_case_fact_count < 0
    ) {
      throw new ApiContractError("review_improvements same_case_fact_count is invalid");
    }
    if (action.status === "available") {
      if (
        action.payload.same_case_fact_count < 2 ||
        action.handler !== "openImprovementReview" ||
        action.reason !== null
      ) {
        throw new ApiContractError("review_improvements available envelope is invalid");
      }
    } else if (action.status === "blocked") {
      if (
        action.payload.same_case_fact_count >= 2 ||
        action.handler !== null ||
        action.reason === null
      ) {
        throw new ApiContractError("review_improvements blocked envelope is invalid");
      }
    } else {
      throw new ApiContractError("review_improvements status is invalid");
    }
  }
}

function assertExactStringSet(
  actual: readonly string[],
  expected: readonly string[],
  field: string,
): void {
  if (
    actual.length !== expected.length ||
    expected.some((key) => !actual.includes(key))
  ) {
    throw new ApiContractError(`${field} keys are invalid`);
  }
}

function parseCopilotAction(
  value: unknown,
  index: number,
  context: Readonly<{ caseId: string; dataRevision: number }> | null = null,
): CopilotActionAvailability {
  const field = `actions[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    ["action_id", "action", "status", "handler", "reason", "effect_preview", "payload"],
    field,
  );
  const parsed: CopilotActionAvailability = {
    action_id: requireScenarioUuid(record.action_id, `${field}.action_id`),
    action: requireApiLiteral(record.action, copilotActionKeys, `${field}.action`),
    status: requireApiLiteral(record.status, copilotActionStatuses, `${field}.status`),
    handler:
      record.handler === null
        ? null
        : requireAdvisorSafeCode(record.handler, `${field}.handler`),
    reason:
      record.reason === null
        ? null
        : requireScenarioText(record.reason, `${field}.reason`),
    effect_preview: requireScenarioText(record.effect_preview, `${field}.effect_preview`),
    payload: parseActionPayload(record.payload, `${field}.payload`),
  };
  requireActionPayloadShape(parsed, context);
  return parsed;
}

const copilotQuestionInputKinds = ["text", "decimal", "select", "month"] as const;
const copilotQuestionInputSchemaKinds = ["text", "money"] as const;

function parseCopilotQuestionInputField(
  value: unknown,
  index: number,
): CopilotQuestionInputField {
  const field = `question_descriptor.input_schema.fields[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    ["field_key", "label", "input_kind", "required", "placeholder"],
    field,
  );
  if (typeof record.required !== "boolean") {
    throw new ApiContractError(`${field}.required must be boolean`);
  }
  return {
    field_key: requireAdvisorSafeCode(record.field_key, `${field}.field_key`),
    label: requireScenarioText(record.label, `${field}.label`),
    input_kind: requireApiLiteral(
      record.input_kind,
      copilotQuestionInputKinds,
      `${field}.input_kind`,
    ),
    required: record.required,
    placeholder:
      record.placeholder === null
        ? null
        : requireScenarioText(record.placeholder, `${field}.placeholder`),
  };
}

function parseCopilotQuestionInputSchema(
  value: unknown,
): CopilotQuestionInputSchema {
  const record = requireApiRecord(value, "question_descriptor.input_schema");
  requireApiExactKeys(record, ["kind", "fields"], "question_descriptor.input_schema");
  const kind = requireApiLiteral(
    record.kind,
    copilotQuestionInputSchemaKinds,
    "question_descriptor.input_schema.kind",
  );
  const fields = requireApiArray(
    record.fields,
    "question_descriptor.input_schema.fields",
    parseCopilotQuestionInputField,
  );
  const fieldKeys = fields.map((field) => field.field_key);
  if (new Set(fieldKeys).size !== fieldKeys.length) {
    throw new ApiContractError("question_descriptor.input_schema.fields must not contain duplicates");
  }
  const allowed = kind === "money"
    ? ["amount", "scale", "currency", "period", "declared_source", "rationale", "validation_plan"]
    : ["value", "declared_source", "rationale", "validation_plan"];
  if (fieldKeys.some((fieldKey) => !allowed.includes(fieldKey))) {
    throw new ApiContractError("question_descriptor.input_schema.fields contains unsupported field");
  }
  const requiredBaseFields = kind === "money"
    ? ["amount", "scale", "currency", "declared_source", "rationale", "validation_plan"]
    : ["value", "declared_source", "rationale", "validation_plan"];
  for (const requiredField of requiredBaseFields) {
    const field = fields.find((candidate) => candidate.field_key === requiredField) ?? null;
    if (field === null || !field.required) {
      throw new ApiContractError("question_descriptor.input_schema.fields missing required base field");
    }
  }
  return { kind, fields };
}

function parseCopilotQuestionDescriptor(
  value: unknown,
  legacyQuestion: string | null,
): CopilotQuestionDescriptor {
  const record = requireApiRecord(value, "question_descriptor");
  requireApiExactKeys(
    record,
    [
      "question_id",
      "field_key",
      "question",
      "label",
      "description",
      "why_needed",
      "unlocks",
      "unlocks_copy",
      "example",
      "validation_guidance",
      "provenance",
      "input_schema",
    ],
    "question_descriptor",
  );
  const question = requireScenarioText(record.question, "question_descriptor.question");
  if (legacyQuestion !== null && legacyQuestion !== question) {
    throw new ApiContractError("question_descriptor.question must match next_question");
  }
  const fieldKey = requireAdvisorSafeCode(record.field_key, "question_descriptor.field_key");
  if (!privateFactInputKeys.includes(fieldKey as never)) {
    throw new ApiContractError("question_descriptor field_key is not approved");
  }
  return {
    question_id: requireScenarioUuid(record.question_id, "question_descriptor.question_id"),
    field_key: fieldKey,
    question,
    label: requireScenarioText(record.label, "question_descriptor.label"),
    description: requireScenarioText(
      record.description,
      "question_descriptor.description",
    ),
    why_needed: requireScenarioText(record.why_needed, "question_descriptor.why_needed"),
    unlocks: parseAdvisorSafeCodeArray(record.unlocks, "question_descriptor.unlocks"),
    unlocks_copy: requireScenarioText(record.unlocks_copy, "question_descriptor.unlocks_copy"),
    example: requireScenarioText(record.example, "question_descriptor.example"),
    validation_guidance: requireScenarioText(
      record.validation_guidance,
      "question_descriptor.validation_guidance",
    ),
    provenance: requireApiLiteral(
      record.provenance,
      ["founder_statement"] as const,
      "question_descriptor.provenance",
    ),
    input_schema: parseCopilotQuestionInputSchema(record.input_schema),
  };
}

export function parseCopilotStateResponse(value: unknown): CopilotStateResponse {
  const record = requireApiRecord(value, "copilot_state");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "data_revision",
      "stage",
      "next_question",
      "question_descriptor",
      "suggested_action",
      "selected_scenario_key",
      "extracted_facts",
      "prioritized_gaps",
      "scenario_metrics",
      "fact_coverage",
      "scenario_completeness",
      "accepted_inputs",
      "actions",
    ],
    "copilot_state",
  );
  const caseId = requireScenarioUuid(record.case_id, "case_id");
  const dataRevision = requirePositiveRevision(record.data_revision, "data_revision");
  const nextQuestion =
    record.next_question === null
      ? null
      : requireScenarioText(record.next_question, "next_question");
  const questionDescriptor =
    record.question_descriptor === null
      ? null
      : parseCopilotQuestionDescriptor(record.question_descriptor, nextQuestion);
  const actions = requireApiArray(record.actions, "actions", (item, index) =>
    parseCopilotAction(item, index, { caseId, dataRevision }),
  );
  if (questionDescriptor !== null) {
    const openFactInput = actions.find((action) => action.action === "open_fact_input") ?? null;
    if (
      openFactInput === null ||
      openFactInput.payload.field_key !== questionDescriptor.field_key
    ) {
      throw new ApiContractError("question_descriptor must match open_fact_input field_key");
    }
    if (openFactInput.payload.provenance !== questionDescriptor.provenance) {
      throw new ApiContractError("question_descriptor must match open_fact_input provenance");
    }
  }
  return {
    case_id: caseId,
    data_revision: dataRevision,
    stage: requireAdvisorSafeCode(record.stage, "stage"),
    next_question: nextQuestion,
    question_descriptor: questionDescriptor,
    suggested_action: requireAdvisorSafeCode(record.suggested_action, "suggested_action"),
    selected_scenario_key: requireScenarioKey(
      record.selected_scenario_key,
      "selected_scenario_key",
    ),
    extracted_facts: requireApiArray(
      record.extracted_facts,
      "extracted_facts",
      parseFactProjection,
    ),
    prioritized_gaps: requireApiArray(
      record.prioritized_gaps,
      "prioritized_gaps",
      parseGapProjection,
    ),
    scenario_metrics: requireApiArray(
      record.scenario_metrics,
      "scenario_metrics",
      parseCopilotScenarioMetricProjection,
    ),
    fact_coverage: parseCoverageProjection(record.fact_coverage, "fact_coverage"),
    scenario_completeness: parseCoverageProjection(
      record.scenario_completeness,
      "scenario_completeness",
    ),
    accepted_inputs: requireApiArray(
      record.accepted_inputs,
      "accepted_inputs",
      parseAcceptedInput,
    ),
    actions,
  };
}

function parseCopilotMessage(
  value: unknown,
  index: number,
  threadCaseId: string,
  threadRevision: number,
): CopilotMessageResponseItem {
  const field = `messages[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "message_id",
      "case_id",
      "data_revision",
      "role",
      "content",
      "page_context",
      "current_section",
      "idempotency_fingerprint",
      "related_evidence_refs",
      "question_refs",
      "action_refs",
      "action_snapshots",
      "action_result",
    ],
    field,
  );
  const caseId = requireScenarioUuid(record.case_id, `${field}.case_id`);
  const revision = requirePositiveRevision(record.data_revision, `${field}.data_revision`);
  if (caseId !== threadCaseId) {
    throw new ApiContractError(`${field}.case_id does not match thread case_id`);
  }
  if (revision > threadRevision) {
    throw new ApiContractError(`${field}.data_revision cannot reference a future revision`);
  }
  const actionRefs = requireScenarioUuidArray(record.action_refs, `${field}.action_refs`);
  const actionSnapshots = requireApiArray(
    record.action_snapshots,
    `${field}.action_snapshots`,
    (item, actionIndex) => parseCopilotAction(item, actionIndex, { caseId, dataRevision: revision }),
  );
  const uniqueSnapshotIds = new Set(actionSnapshots.map((action) => action.action_id));
  if (uniqueSnapshotIds.size !== actionSnapshots.length) {
    throw new ApiContractError(`${field}.action_snapshots action_id values must be unique`);
  }
  assertExactStringSet(
    [...actionRefs].sort(),
    [...uniqueSnapshotIds].sort(),
    `${field}.action_refs`,
  );
  return {
    message_id: requireScenarioUuid(record.message_id, `${field}.message_id`),
    case_id: caseId,
    data_revision: revision,
    role: requireApiLiteral(record.role, copilotMessageRoles, `${field}.role`),
    content: requireScenarioText(record.content, `${field}.content`),
    page_context:
      record.page_context === null
        ? null
        : requireScenarioText(record.page_context, `${field}.page_context`),
    current_section:
      record.current_section === null
        ? null
        : requireScenarioText(record.current_section, `${field}.current_section`),
    idempotency_fingerprint:
      record.idempotency_fingerprint === null
        ? null
        : requireScenarioText(
            record.idempotency_fingerprint,
            `${field}.idempotency_fingerprint`,
          ),
    related_evidence_refs: requireScenarioUuidArray(
      record.related_evidence_refs,
      `${field}.related_evidence_refs`,
    ),
    question_refs: requireScenarioUuidArray(record.question_refs, `${field}.question_refs`),
    action_refs: actionRefs,
    action_snapshots: actionSnapshots,
    action_result:
      record.action_result === null
        ? null
        : parseActionPayload(record.action_result, `${field}.action_result`),
  };
}

export function parseCopilotThreadResponse(value: unknown): CopilotThreadResponse {
  const record = requireApiRecord(value, "copilot_thread");
  requireApiExactKeys(record, ["thread_id", "case_id", "data_revision", "messages"], "copilot_thread");
  const caseId = requireScenarioUuid(record.case_id, "case_id");
  const dataRevision = requirePositiveRevision(record.data_revision, "data_revision");
  return {
    thread_id: requireScenarioUuid(record.thread_id, "thread_id"),
    case_id: caseId,
    data_revision: dataRevision,
    messages: requireApiArray(record.messages, "messages", (item, index) =>
      parseCopilotMessage(item, index, caseId, dataRevision),
    ),
  };
}

export function parseCopilotTurnResponse(value: unknown): CopilotTurnResponse {
  const record = requireApiRecord(value, "copilot_turn");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "data_revision",
      "thread_id",
      "page_context",
      "current_section",
      "status",
      "message",
      "available_actions",
    ],
    "copilot_turn",
  );
  const caseId = requireScenarioUuid(record.case_id, "case_id");
  const dataRevision = requirePositiveRevision(record.data_revision, "data_revision");
  return {
    case_id: caseId,
    data_revision: dataRevision,
    thread_id: requireScenarioUuid(record.thread_id, "thread_id"),
    page_context: requireScenarioText(record.page_context, "page_context"),
    current_section: requireScenarioText(record.current_section, "current_section"),
    status: requireApiLiteral(record.status, ["accepted"] as const, "status"),
    message: requireScenarioText(record.message, "message"),
    available_actions: requireApiArray(
      record.available_actions,
      "available_actions",
      (item, index) => parseCopilotAction(item, index, { caseId, dataRevision }),
    ),
  };
}

function parseStringRecord(value: unknown, field: string): Readonly<Record<string, string>> {
  const record = requireApiRecord(value, field);
  return Object.fromEntries(
    Object.entries(record).map(([key, item]) => [
      requireAdvisorSafeCode(key, `${field} key`),
      requireScenarioText(item, `${field}.${key}`),
    ]),
  );
}

function parseNumberRecord(value: unknown, field: string): Readonly<Record<string, number>> {
  const record = requireApiRecord(value, field);
  return Object.fromEntries(
    Object.entries(record).map(([key, item]) => [
      requireAdvisorSafeCode(key, `${field} key`),
      requireApiInteger(item, `${field}.${key}`),
    ]),
  );
}

function parseCaseMutationFieldError(
  value: unknown,
  index: number,
): CaseMutationFieldError {
  const field = `validation_errors[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(record, ["field", "message"], field);
  return {
    field: requireScenarioText(record.field, `${field}.field`),
    message: requireScenarioText(record.message, `${field}.message`),
  };
}

function parseCaseMutationDelta(value: unknown, field: string): CaseMutationDeltaResponse {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "accepted",
      "old_revision",
      "new_revision",
      "changed_keys",
      "stale_scenario_ids",
      "stale_report_ids",
      "metric_before",
      "metric_after",
      "readiness_before",
      "readiness_after",
      "next_question",
      "validation_errors",
      "original_draft",
    ],
    field,
  );
  const oldRevision = requirePositiveRevision(record.old_revision, `${field}.old_revision`);
  const newRevision = requirePositiveRevision(record.new_revision, `${field}.new_revision`);
  if (newRevision < oldRevision) {
    throw new ApiContractError(`${field}.new_revision must not regress`);
  }
  if (
    record.next_question !== null &&
    typeof record.next_question !== "string" &&
    !isRecord(record.next_question)
  ) {
    throw new ApiContractError(`${field}.next_question is invalid`);
  }
  return {
    accepted: requireApiBoolean(record.accepted, `${field}.accepted`),
    old_revision: oldRevision,
    new_revision: newRevision,
    changed_keys: parseAdvisorSafeCodeArray(record.changed_keys, `${field}.changed_keys`),
    stale_scenario_ids: requireScenarioUuidArray(
      record.stale_scenario_ids,
      `${field}.stale_scenario_ids`,
    ),
    stale_report_ids: requireScenarioUuidArray(record.stale_report_ids, `${field}.stale_report_ids`),
    metric_before: parseStringRecord(record.metric_before, `${field}.metric_before`),
    metric_after: parseStringRecord(record.metric_after, `${field}.metric_after`),
    readiness_before: parseNumberRecord(record.readiness_before, `${field}.readiness_before`),
    readiness_after: parseNumberRecord(record.readiness_after, `${field}.readiness_after`),
    next_question: record.next_question,
    validation_errors: requireApiArray(
      record.validation_errors,
      `${field}.validation_errors`,
      parseCaseMutationFieldError,
    ),
    original_draft:
      record.original_draft === null
        ? null
        : requireScenarioText(record.original_draft, `${field}.original_draft`),
  };
}

export function parseFactMutationResponse(value: unknown): FactMutationResponse {
  const record = requireApiRecord(value, "fact_mutation");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "accepted",
      "provenance",
      "source_type",
      "old_revision",
      "new_revision",
      "changed_keys",
      "delta",
    ],
    "fact_mutation",
  );
  const provenance = requireCaseValueKind(record.provenance, "provenance");
  const sourceType = requireCaseValueKind(record.source_type, "source_type");
  if (["founder_statement", "public_benchmark", "ai_scenario"].includes(provenance) && sourceType === "source_fact") {
    throw new ApiContractError("non-source provenance must not return source_fact");
  }
  return {
    case_id: requireScenarioUuid(record.case_id, "case_id"),
    accepted: requireApiBoolean(record.accepted, "accepted"),
    provenance,
    source_type: sourceType,
    old_revision: requirePositiveRevision(record.old_revision, "old_revision"),
    new_revision: requirePositiveRevision(record.new_revision, "new_revision"),
    changed_keys: parseAdvisorSafeCodeArray(record.changed_keys, "changed_keys"),
    delta: parseCaseMutationDelta(record.delta, "delta"),
  };
}

export function parseAssumptionOutcomeResponse(value: unknown): AssumptionOutcomeResponse {
  const record = requireApiRecord(value, "assumption_outcome");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "status",
      "provenance",
      "reason",
      "old_revision",
      "new_revision",
      "delta",
      "accepted_input",
    ],
    "assumption_outcome",
  );
  const provenance = requireCaseValueKind(record.provenance, "provenance");
  if (provenance === "source_fact") {
    throw new ApiContractError("assumption provenance must not be source_fact");
  }
  const status = requireApiLiteral(record.status, ["accepted", "blocked"] as const, "status");
  return {
    case_id: requireScenarioUuid(record.case_id, "case_id"),
    status,
    provenance,
    reason: record.reason === null ? null : requireScenarioText(record.reason, "reason"),
    old_revision: requirePositiveRevision(record.old_revision, "old_revision"),
    new_revision: requirePositiveRevision(record.new_revision, "new_revision"),
    delta: record.delta === null ? null : parseCaseMutationDelta(record.delta, "delta"),
    accepted_input:
      record.accepted_input === null
        ? null
        : parseAcceptedInput(record.accepted_input, 0),
  };
}

function parseScenarioNullableRange(
  value: unknown,
  field: string,
): ScenarioRangeResponse | null {
  return value === null ? null : parseScenarioRange(value, field);
}

export function parseStartupScenarioInput(
  value: unknown,
  caseId: string,
  dataRevision: number,
  field: string,
): StartupScenarioInput {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "input_id",
      "case_id",
      "data_revision",
      "input_key",
      "value_range",
      "unit",
      "period",
      "provenance",
      "source_refs",
      "dependency_refs",
      "confidence",
      "rationale",
      "validation_plan",
      "what_would_confirm",
      "acceptance",
    ],
    field,
  );
  const inputCaseId =
    record.case_id === null ? null : requireScenarioUuid(record.case_id, `${field}.case_id`);
  const inputRevision =
    record.data_revision === null
      ? null
      : requirePositiveRevision(record.data_revision, `${field}.data_revision`);
  if (inputCaseId !== null && inputCaseId !== caseId) {
    throw new ApiContractError(`${field}.case_id does not match scenario case_id`);
  }
  if (inputRevision !== null && inputRevision !== dataRevision) {
    throw new ApiContractError(`${field}.data_revision does not match scenario revision`);
  }
  const provenance = requireCaseValueKind(record.provenance, `${field}.provenance`);
  const sourceRefs = requireScenarioUuidArray(record.source_refs, `${field}.source_refs`);
  const dependencyRefs = requireScenarioUuidArray(
    record.dependency_refs,
    `${field}.dependency_refs`,
  );
  const acceptance = requireApiLiteral(
    record.acceptance,
    scenarioAcceptances,
    `${field}.acceptance`,
  );
  requireScenarioSourceRefs(provenance, sourceRefs, dependencyRefs, field, acceptance);
  const unit = requireScenarioText(record.unit, `${field}.unit`);
  const period =
    record.period === null ? null : requireScenarioText(record.period, `${field}.period`);
  requireMatchingUnitPeriod(unit, period, field);
  return {
    input_id: requireScenarioUuid(record.input_id, `${field}.input_id`),
    case_id: inputCaseId,
    data_revision: inputRevision,
    input_key: requireAdvisorSafeCode(record.input_key, `${field}.input_key`),
    value_range: parseScenarioRange(record.value_range, `${field}.value_range`),
    unit,
    period,
    provenance,
    source_refs: sourceRefs,
    dependency_refs: dependencyRefs,
    confidence: requireApiLiteral(
      record.confidence,
      scenarioConfidences,
      `${field}.confidence`,
    ),
    rationale: requireScenarioText(record.rationale, `${field}.rationale`),
    validation_plan: requireScenarioText(
      record.validation_plan,
      `${field}.validation_plan`,
    ),
    what_would_confirm: requireScenarioText(
      record.what_would_confirm,
      `${field}.what_would_confirm`,
    ),
    acceptance,
  };
}

export function parseStartupScenarioMetric(
  value: unknown,
  caseId: string,
  dataRevision: number,
  field: string,
): StartupScenarioMetric {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "metric_id",
      "case_id",
      "data_revision",
      "metric_key",
      "value_range",
      "unit",
      "period",
      "provenance",
      "source_refs",
      "dependency_refs",
      "formula_key",
      "formula_description",
      "confidence",
      "rationale",
      "validation_plan",
      "what_would_confirm",
      "acceptance",
      "gaps",
    ],
    field,
  );
  const metricCaseId = requireScenarioUuid(record.case_id, `${field}.case_id`);
  const metricRevision = requirePositiveRevision(
    record.data_revision,
    `${field}.data_revision`,
  );
  if (metricCaseId !== caseId) {
    throw new ApiContractError(`${field}.case_id does not match scenario case_id`);
  }
  if (metricRevision !== dataRevision) {
    throw new ApiContractError(`${field}.data_revision does not match scenario revision`);
  }
  const provenance = requireCaseValueKind(record.provenance, `${field}.provenance`);
  const sourceRefs = requireScenarioUuidArray(record.source_refs, `${field}.source_refs`);
  const dependencyRefs = requireScenarioUuidArray(
    record.dependency_refs,
    `${field}.dependency_refs`,
  );
  const acceptance = requireApiLiteral(
    record.acceptance,
    scenarioAcceptances,
    `${field}.acceptance`,
  );
  requireScenarioSourceRefs(provenance, sourceRefs, dependencyRefs, field, acceptance);
  const unit = requireScenarioText(record.unit, `${field}.unit`);
  const period =
    record.period === null ? null : requireScenarioText(record.period, `${field}.period`);
  requireMatchingUnitPeriod(unit, period, field);
  return {
    metric_id: requireScenarioUuid(record.metric_id, `${field}.metric_id`),
    case_id: metricCaseId,
    data_revision: metricRevision,
    metric_key: requireAdvisorSafeCode(record.metric_key, `${field}.metric_key`),
    value_range: parseScenarioNullableRange(record.value_range, `${field}.value_range`),
    unit,
    period,
    provenance,
    source_refs: sourceRefs,
    dependency_refs: dependencyRefs,
    formula_key: requireAdvisorSafeCode(record.formula_key, `${field}.formula_key`),
    formula_description: requireScenarioText(
      record.formula_description,
      `${field}.formula_description`,
    ),
    confidence: requireApiLiteral(
      record.confidence,
      scenarioConfidences,
      `${field}.confidence`,
    ),
    rationale: requireScenarioText(record.rationale, `${field}.rationale`),
    validation_plan: requireScenarioText(
      record.validation_plan,
      `${field}.validation_plan`,
    ),
    what_would_confirm: requireScenarioText(
      record.what_would_confirm,
      `${field}.what_would_confirm`,
    ),
    acceptance,
    gaps: parseAdvisorSafeCodeArray(record.gaps, `${field}.gaps`),
  };
}

function parseScenarioRecord<T>(
  value: unknown,
  field: string,
  parser: (item: unknown, key: string) => T,
): Readonly<Record<string, T>> {
  const record = requireApiRecord(value, field);
  return Object.fromEntries(
    Object.entries(record).map(([key, item]) => [key, parser(item, key)]),
  );
}

function parseStartupScenarioVariant(
  value: unknown,
  scenarioKey: ScenarioKey,
  caseId: string,
  dataRevision: number,
): StartupScenarioVariant {
  const field = `scenarios.${scenarioKey}`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(record, ["scenario_key", "inputs", "metrics", "gaps"], field);
  const parsedScenarioKey = requireScenarioKey(record.scenario_key, `${field}.scenario_key`);
  if (parsedScenarioKey !== scenarioKey) {
    throw new ApiContractError(`${field}.scenario_key must match its map key`);
  }
  const inputs = parseScenarioRecord(record.inputs, `${field}.inputs`, (item, key) => {
    const input = parseStartupScenarioInput(
      item,
      caseId,
      dataRevision,
      `${field}.inputs.${key}`,
    );
    if (input.input_key !== key) {
      throw new ApiContractError(`${field}.inputs.${key} input_key mismatch`);
    }
    return input;
  });
  const metrics = parseScenarioRecord(record.metrics, `${field}.metrics`, (item, key) => {
    const metric = parseStartupScenarioMetric(
      item,
      caseId,
      dataRevision,
      `${field}.metrics.${key}`,
    );
    if (metric.metric_key !== key) {
      throw new ApiContractError(`${field}.metrics.${key} metric_key mismatch`);
    }
    return metric;
  });
  const gaps = Object.fromEntries(
    Object.entries(requireApiRecord(record.gaps, `${field}.gaps`)).map(([key, item]) => [
      requireAdvisorSafeCode(key, `${field}.gaps key`),
      requireScenarioText(item, `${field}.gaps.${key}`),
    ]),
  );
  return { scenario_key: scenarioKey, inputs, metrics, gaps };
}

export function parseScenarioProjectionResponse(
  value: unknown,
): ScenarioProjectionResponse {
  const record = requireApiRecord(value, "scenarios");
  requireApiExactKeys(
    record,
    [
      "scenario_set_id",
      "case_id",
      "data_revision",
      "selected_scenario_key",
      "scenarios",
      "fact_coverage",
      "scenario_completeness",
    ],
    "scenarios",
  );
  const caseId = requireScenarioUuid(record.case_id, "case_id");
  const dataRevision = requirePositiveRevision(record.data_revision, "data_revision");
  const scenariosRecord = requireApiRecord(record.scenarios, "scenarios.scenarios");
  assertExactStringSet(Object.keys(scenariosRecord).sort(), [...scenarioKeys].sort(), "scenarios");
  return {
    scenario_set_id: requireScenarioUuid(record.scenario_set_id, "scenario_set_id"),
    case_id: caseId,
    data_revision: dataRevision,
    selected_scenario_key: requireScenarioKey(
      record.selected_scenario_key,
      "selected_scenario_key",
    ),
    scenarios: {
      conservative: parseStartupScenarioVariant(
        scenariosRecord.conservative,
        "conservative",
        caseId,
        dataRevision,
      ),
      base: parseStartupScenarioVariant(
        scenariosRecord.base,
        "base",
        caseId,
        dataRevision,
      ),
      optimistic: parseStartupScenarioVariant(
        scenariosRecord.optimistic,
        "optimistic",
        caseId,
        dataRevision,
      ),
    },
    fact_coverage: parseCoverageProjection(record.fact_coverage, "fact_coverage"),
    scenario_completeness: parseCoverageProjection(
      record.scenario_completeness,
      "scenario_completeness",
    ),
  };
}

export function parseScenarioSelectionResponse(
  value: unknown,
): ScenarioSelectionResponse {
  const record = requireApiRecord(value, "scenario_selection");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "data_revision",
      "scenario_set_id",
      "old_scenario_key",
      "new_scenario_key",
      "changed_keys",
    ],
    "scenario_selection",
  );
  return {
    case_id: requireScenarioUuid(record.case_id, "case_id"),
    data_revision: requirePositiveRevision(record.data_revision, "data_revision"),
    scenario_set_id: requireScenarioUuid(record.scenario_set_id, "scenario_set_id"),
    old_scenario_key: requireScenarioKey(record.old_scenario_key, "old_scenario_key"),
    new_scenario_key: requireScenarioKey(record.new_scenario_key, "new_scenario_key"),
    changed_keys: parseAdvisorSafeCodeArray(record.changed_keys, "changed_keys"),
  };
}

export function parseLaunchPackMetadataResponse(
  value: unknown,
): LaunchPackMetadataResponse {
  const record = requireApiRecord(value, "launch_pack");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "data_revision",
      "scenario_set_id",
      "selected_scenario_key",
      "asset_id",
      "asset_key",
      "asset_revision",
      "status",
      "markdown_url",
      "csv_url",
      "provenance_appendix_url",
      "body_markdown",
    ],
    "launch_pack",
  );
  const status = requireAdvisorSafeCode(record.status, "status");
  if (status !== "draft") {
    throw new ApiContractError("launch_pack status is invalid");
  }
  return {
    case_id: requireScenarioUuid(record.case_id, "case_id"),
    data_revision: requirePositiveRevision(record.data_revision, "data_revision"),
    scenario_set_id: requireScenarioUuid(record.scenario_set_id, "scenario_set_id"),
    selected_scenario_key: requireScenarioKey(
      record.selected_scenario_key,
      "selected_scenario_key",
    ),
    asset_id: requireScenarioUuid(record.asset_id, "asset_id"),
    asset_key: requireAdvisorSafeCode(record.asset_key, "asset_key"),
    asset_revision: requirePositiveRevision(record.asset_revision, "asset_revision"),
    status,
    markdown_url: requireScenarioText(record.markdown_url, "markdown_url"),
    csv_url:
      record.csv_url === null
        ? null
        : requireScenarioText(record.csv_url, "csv_url"),
    provenance_appendix_url: requireScenarioText(
      record.provenance_appendix_url,
      "provenance_appendix_url",
    ),
    body_markdown: requireLaunchPackMarkdown(record.body_markdown, "body_markdown"),
  };
}

export function parseCaseAssetListResponse(value: unknown): CaseAssetListResponse {
  const record = requireApiRecord(value, "case_asset_list");
  requireApiExactKeys(record, ["case_id", "data_revision", "assets"], "case_asset_list");
  const caseId = requireScenarioUuid(record.case_id, "case_id");
  const dataRevision = requirePositiveRevision(record.data_revision, "data_revision");
  const assets = requireApiArray(record.assets, "assets", (asset, index) => {
    const parsed = parseLaunchPackMetadataResponse(asset);
    if (parsed.case_id !== caseId || parsed.data_revision !== dataRevision) {
      throw new ApiContractError(`case_asset_list assets[${index}] lineage mismatch`);
    }
    return parsed;
  });
  return {
    case_id: caseId,
    data_revision: dataRevision,
    assets,
  };
}

export function parseResearchPlanResponse(value: unknown): ResearchPlanResponse {
  const record = requireApiRecord(value, "research_plan");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "data_revision",
      "status",
      "plan_id",
      "plan_hash",
      "focus",
      "query_previews",
      "manual_only_keys",
      "consent_text",
      "created_at",
      "expires_at",
    ],
    "research_plan",
  );
  return {
    case_id: requireScenarioUuid(record.case_id, "case_id"),
    data_revision: requirePositiveRevision(record.data_revision, "data_revision"),
    status: requireApiLiteral(record.status, researchPlanStatuses, "status"),
    plan_id: requireScenarioUuid(record.plan_id, "plan_id"),
    plan_hash: requireScenarioText(record.plan_hash, "plan_hash"),
    focus: requireScenarioText(record.focus, "focus"),
    query_previews: requireApiStringArray(record.query_previews, "query_previews").map(
      (item, index) => requireScenarioText(item, `query_previews[${index}]`),
    ),
    manual_only_keys: parseAdvisorSafeCodeArray(record.manual_only_keys, "manual_only_keys"),
    consent_text: requireScenarioText(record.consent_text, "consent_text"),
    created_at: requireScenarioText(record.created_at, "created_at"),
    expires_at: requireScenarioText(record.expires_at, "expires_at"),
  };
}

function parseResearchBenchmarkEntry(
  value: unknown,
  index: number,
): ResearchBenchmarkEntryProjection {
  const field = `accepted_entries[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(
    record,
    [
      "entry_id",
      "provenance",
      "input_key",
      "url",
      "publisher",
      "publication_date",
      "retrieval_date",
      "as_of",
      "source_class",
      "confidence",
      "value",
      "range",
      "unit",
      "period",
      "formula",
      "dependencies",
      "validation_plan",
      "source_refs",
    ],
    field,
  );
  const sourceRefs = requireScenarioUuidArray(record.source_refs, `${field}.source_refs`);
  if (sourceRefs.length === 0) {
    throw new ApiContractError(`${field}.source_refs are required`);
  }
  const acceptedValue =
    record.value === null ? null : requireScenarioText(record.value, `${field}.value`);
  const range = parseResearchRange(record.range, `${field}.range`);
  if (acceptedValue !== null) {
    decimalRangeValue(acceptedValue, `${field}.value`);
  }
  if (acceptedValue === null && (range.low === null || range.high === null)) {
    throw new ApiContractError(`${field}.range is required when value is null`);
  }
  if (acceptedValue !== null && (range.low !== null || range.high !== null)) {
    throw new ApiContractError(`${field}.value and range are mutually exclusive`);
  }
  return {
    entry_id: requireScenarioUuid(record.entry_id, `${field}.entry_id`),
    provenance: requireApiLiteral(
      record.provenance,
      ["public_benchmark"] as const,
      `${field}.provenance`,
    ),
    input_key: requireAdvisorSafeCode(record.input_key, `${field}.input_key`),
    url: requireScenarioText(record.url, `${field}.url`),
    publisher: requireScenarioText(record.publisher, `${field}.publisher`),
    publication_date:
      record.publication_date === null
        ? null
        : requireScenarioText(record.publication_date, `${field}.publication_date`),
    retrieval_date: requireScenarioText(record.retrieval_date, `${field}.retrieval_date`),
    as_of: requireScenarioText(record.as_of, `${field}.as_of`),
    source_class: requireAdvisorSafeText(record.source_class, `${field}.source_class`, 240),
    confidence: requireApiLiteral(record.confidence, scenarioConfidences, `${field}.confidence`),
    value: acceptedValue,
    range,
    unit: requireScenarioText(record.unit, `${field}.unit`),
    period: requireScenarioText(record.period, `${field}.period`),
    formula: requireScenarioText(record.formula, `${field}.formula`),
    dependencies: requireApiStringArray(record.dependencies, `${field}.dependencies`).map(
      (item, dependencyIndex) => {
        const dependency = requireScenarioText(item, `${field}.dependencies[${dependencyIndex}]`);
        if (dependency.length === 0) {
          throw new ApiContractError(`${field}.dependencies[${dependencyIndex}] is required`);
        }
        return dependency;
      },
    ),
    validation_plan: requireScenarioText(record.validation_plan, `${field}.validation_plan`),
    source_refs: sourceRefs,
  };
}

function parseResearchRejectedEntry(
  value: unknown,
  index: number,
): ResearchRejectedEntryProjection {
  const field = `rejected_entries[${index}]`;
  const record = requireApiRecord(value, field);
  requireApiExactKeys(record, ["rejected_id", "reason_code", "input_key", "provenance", "metadata"], field);
  return {
    rejected_id: requireScenarioUuid(record.rejected_id, `${field}.rejected_id`),
    reason_code: requireAdvisorSafeCode(record.reason_code, `${field}.reason_code`),
    input_key:
      record.input_key === null ? null : requireAdvisorSafeCode(record.input_key, `${field}.input_key`),
    provenance:
      record.provenance === null
        ? null
        : requireScenarioText(record.provenance, `${field}.provenance`),
    metadata: parseStringRecord(record.metadata, `${field}.metadata`),
  };
}

export function parseResearchJobResponse(value: unknown): ResearchJobResponse {
  const record = requireApiRecord(value, "research_job");
  requireApiExactKeys(
    record,
    [
      "case_id",
      "data_revision",
      "job_id",
      "plan_id",
      "plan_hash",
      "status",
      "acquisition_mode",
      "requested_acquisition_mode",
      "selected_acquisition_mode",
      "reason",
      "accepted_entries",
      "rejected_entries",
      "citations",
      "manual_only_keys",
      "changed_blocks",
      "stale_scenario_ids",
      "old_revision",
      "new_revision",
      "source_refs",
      "updated_at",
    ],
    "research_job",
  );
  return {
    case_id: requireScenarioUuid(record.case_id, "case_id"),
    data_revision: requirePositiveRevision(record.data_revision, "data_revision"),
    job_id: requireScenarioUuid(record.job_id, "job_id"),
    plan_id: record.plan_id === null ? null : requireScenarioUuid(record.plan_id, "plan_id"),
    plan_hash: record.plan_hash === null ? null : requireScenarioText(record.plan_hash, "plan_hash"),
    status: requireApiLiteral(record.status, researchJobStatuses, "status"),
    acquisition_mode: requireApiLiteral(
      record.acquisition_mode,
      researchAcquisitionModes,
      "acquisition_mode",
    ),
    requested_acquisition_mode: requireApiLiteral(
      record.requested_acquisition_mode,
      researchAcquisitionModes,
      "requested_acquisition_mode",
    ),
    selected_acquisition_mode: requireApiLiteral(
      record.selected_acquisition_mode,
      researchAcquisitionModes,
      "selected_acquisition_mode",
    ),
    reason: record.reason === null ? null : requireScenarioText(record.reason, "reason"),
    accepted_entries: requireApiArray(
      record.accepted_entries,
      "accepted_entries",
      parseResearchBenchmarkEntry,
    ),
    rejected_entries: requireApiArray(
      record.rejected_entries,
      "rejected_entries",
      parseResearchRejectedEntry,
    ),
    citations: requireApiStringArray(record.citations, "citations").map((item, index) =>
      requireScenarioText(item, `citations[${index}]`),
    ),
    manual_only_keys: parseAdvisorSafeCodeArray(record.manual_only_keys, "manual_only_keys"),
    changed_blocks: parseAdvisorSafeCodeArray(record.changed_blocks, "changed_blocks"),
    stale_scenario_ids: requireScenarioUuidArray(record.stale_scenario_ids, "stale_scenario_ids"),
    old_revision:
      record.old_revision === null ? null : requirePositiveRevision(record.old_revision, "old_revision"),
    new_revision:
      record.new_revision === null ? null : requirePositiveRevision(record.new_revision, "new_revision"),
    source_refs: requireApiStringArray(record.source_refs, "source_refs").map((item, index) =>
      requireScenarioText(item, `source_refs[${index}]`),
    ),
    updated_at: requireScenarioText(record.updated_at, "updated_at"),
  };
}

export function parseApiError(value: unknown): ApiError {
  const record = requireApiRecord(value, "api_error");
  const keys = Object.keys(record).sort();
  const allowedKeys = ["code", "message"];
  const allowedWithErrors = ["code", "errors", "message"];
  const isSafeErrorShape =
    (keys.length === allowedKeys.length &&
      keys.every((key, index) => key === allowedKeys[index])) ||
    (keys.length === allowedWithErrors.length &&
      keys.every((key, index) => key === allowedWithErrors[index]));
  if (!isSafeErrorShape) {
    throw new ApiContractError("api_error keys are invalid");
  }
  const code = requireApiLiteral(record.code, apiErrorCodes, "code");
  if ("errors" in record && code !== "fact_validation_failed") {
    throw new ApiContractError("api_error.errors is only allowed for fact_validation_failed");
  }
  return {
    code,
    message: requireApiString(record.message, "message"),
    errors: "errors" in record ? parseApiFieldErrors(record.errors, "errors") : [],
  };
}

const apiFieldErrorFieldPattern = /^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,7}$/u;
const apiFieldErrorMessagePattern = /^[A-Za-z0-9][A-Za-z0-9 .,:;_()'%-]{0,159}$/iu;

function parseApiFieldErrors(value: unknown, field: string): readonly ApiFieldError[] {
  if (!Array.isArray(value)) {
    throw new ApiContractError(`${field} must be an array`);
  }
  const records = value;
  if (records.length === 0) {
    throw new ApiContractError(`${field} must include at least one field error`);
  }
  return records.map((item, index) => parseApiFieldError(item, `${field}[${index}]`));
}

function parseApiFieldError(value: unknown, field: string): ApiFieldError {
  const record = requireApiRecord(value, field);
  requireApiExactKeys(record, ["field", "message"], field);
  const errorField = requireApiString(record.field, `${field}.field`);
  if (!apiFieldErrorFieldPattern.test(errorField)) {
    throw new ApiContractError(`${field}.field is not founder-safe`);
  }
  const message = requireApiString(record.message, `${field}.message`);
  if (
    !apiFieldErrorMessagePattern.test(message) ||
    /\b(?:secret|token|stack|trace)\b/iu.test(message)
  ) {
    throw new ApiContractError(`${field}.message is not founder-safe`);
  }
  return { field: errorField, message };
}
