import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  closeSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readdirSync,
  readFileSync,
  readSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const sleep = (milliseconds) =>
  new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
const MAX_SMOKE_PDF_BYTES = 5_000_000;
const BROWSER_EVIDENCE_SCHEMA_VERSION = "founder_browser_smoke_evidence@1";
const CASE_COPILOT_BROWSER_EVIDENCE_SCHEMA_VERSION = "case_copilot_browser_evidence@1";
const CANONICAL_DESKTOP_STATE_SCREENSHOTS = Object.freeze([
  "01-start-dashboard.png",
  "02-data-room.png",
  "03-analysis-progress-gate2.png",
  "04-overview-readiness.png",
  "11-ai-advisor-next-question.png",
  "12-ai-advisor-answer.png",
  "13-ai-advisor-updated-analysis.png",
  "14-ai-advisor-improved-plan.png",
  "05-metrics-finance.png",
  "06-market-competitors.png",
  "07-risks-questions.png",
  "08-ai-action-plan.png",
  "09-report-center.png",
  "10-admin-observability-v2.png",
]);
const DESKTOP_STATE_MANIFEST_SCHEMA_VERSION =
  "founder_desktop_state_manifest@1";
const DESKTOP_VERTICAL_OVERFLOW_TOLERANCE_PX = 1;
const SCRIPT_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(SCRIPT_DIRECTORY, "..");
const DEFAULT_ADVISOR_ANSWER =
  "Текущая выручка не подтверждена; пилот бесплатный. Модель цены требует проверки.";
const DEFAULT_INVALID_ADVISOR_ANSWER = "60%";
const REQUIRED_PDF_TRACE_NODES = new Set([
  "disclosure",
  "document_intelligence",
  "gtm",
  "market_analysis",
  "market_research",
  "metrics",
  "primary_profile",
  "product_validation",
  "profile_enrichment",
  "critic",
  "arbiter",
  "report",
]);
const SENSITIVE_ADMIN_TRACE_KEYS = new Set([
  "api_key",
  "attachment",
  "attachments",
  "document_path",
  "document_text",
  "file_name",
  "file_path",
  "filename",
  "input",
  "inputs",
  "local_path",
  "messages",
  "output",
  "outputs",
  "path",
  "pdf_bytes",
  "prompt",
  "prompts",
  "raw_pdf",
  "raw_text",
  "secret",
  "secrets",
]);
const FOUNDER_SAFE_REPORT_TOP_LEVEL_KEYS = new Set([
  "title_ru",
  "subtitle_ru",
  "as_of_ru",
  "data_revision",
  "main_sections",
  "metric_cards",
  "improvement_proposals",
  "technical_appendix",
  "analytics",
]);
const FOUNDER_SAFE_REPORT_SECTION_KEYS = Object.freeze([
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
]);
const FOUNDER_SAFE_REPORT_STATUSES = new Set([
  "confirmed",
  "partial",
  "needs_input",
  "contradiction",
]);
const FOUNDER_SAFE_IMPROVEMENT_AREAS = new Set([
  "positioning",
  "monetization",
  "metrics",
  "gtm",
  "risk_reduction",
  "investor_readiness",
]);
const FOUNDER_SAFE_ANALYTICS_POINT_STATUSES = new Set([
  "confirmed",
  "calculated",
  "estimated",
  "contradiction",
]);
const FOUNDER_SAFE_READINESS_STATUSES = new Set([
  "ready",
  "provisional",
  "blocked",
]);
const FOUNDER_SAFE_KEY_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;
const FOUNDER_SAFE_REPORT_PRIVATE_KEYS = new Set([
  "id",
  "case_id",
  "report_hash",
  "snapshot_hash",
  "case_snapshot_hash",
  "profile_hash",
  "profile_id",
  "source_hashes",
  "trace_id",
  "trace_ids",
  "prompt_version",
  "prompt_versions",
  "formula",
  "model",
  "repro",
  "source_appendix",
  "evidence_ref",
  "evidence_refs",
  "calculation_ref",
  "dimension_ref",
  "artifact_hash",
  "locator_hash",
  "document_text_block",
]);
const FOUNDER_SAFE_REPORT_PRIVATE_VALUE_PATTERN =
  /(?:\bMISSING\b|sha256:[0-9a-f]{64}|\b[0-9a-f]{64}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b|[A-Za-z]:[\\/]|file:\/\/|(?:^|\s)\/(?:Users|home|tmp|var|etc)\/|\b(?:document_text_block|prompt_versions?|trace_ids?|source_hashes|source_appendix|report_hash|snapshot_hash|profile_hash|profile_id|artifact_hash|locator_hash|evidence_refs?|calculation_ref|dimension_ref|chain[-_ ]?of[-_ ]?thought|reasoning_trace|system prompt|api token|secret|private key)\b|\bsk-[A-Za-z0-9_-]{8,}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})/iu;
const REPORT_METADATA_KEYS = new Set([
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
]);
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function safeObject(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function reportSection(report, key) {
  return (
    safeArray(safeObject(report).main_sections).find(
      (section) => safeObject(section).key === key,
    ) ?? {}
  );
}

function reportSectionItems(report, key, field) {
  return safeArray(safeObject(reportSection(report, key))[field]);
}

function reportSectionText(report, key) {
  const section = safeObject(reportSection(report, key));
  return [
    section.summary_ru,
    ...safeArray(section.known_facts_ru),
    ...safeArray(section.blockers_ru),
    ...safeArray(section.next_data_ru),
  ]
    .filter((item) => typeof item === "string")
    .join("\n");
}

export function buildDesktopSuitePublicApiPaths(caseId) {
  const normalizedCaseId = String(caseId ?? "").trim();
  if (!normalizedCaseId) {
    throw new Error("desktop_suite_public_api_case_missing");
  }
  const encodedCaseId = encodeURIComponent(normalizedCaseId);
  const caseRoot = `/api/startup/cases/${encodedCaseId}`;
  return {
    profile: `${caseRoot}/profile`,
    gtm: `${caseRoot}/gtm`,
    report: `${caseRoot}/report/json`,
  };
}

export function summarizeDesktopSuitePublicApiEvidence({
  profile,
  gtm,
  report,
}) {
  const profileFields = Object.keys(safeObject(safeObject(profile).fields)).length;
  const gtmDimensions = safeArray(safeObject(gtm).dimensions).length;
  const launchPlanItems = safeArray(safeObject(gtm).launch_plan).reduce(
    (total, step) => total + safeArray(safeObject(step).experiment_codes).length,
    0,
  );
  const reportAnalytics = safeObject(safeObject(report).analytics);
  const metricPoints = safeArray(reportAnalytics.metric_points);
  const marketPoints = safeArray(reportAnalytics.market_points);
  const readinessDimensions = safeArray(reportAnalytics.readiness_dimensions);
  const competitorFacts = reportSectionItems(report, "competitors", "known_facts_ru");
  const competitorText = reportSectionText(report, "competitors");
  const competitorCategories = [
    "direct",
    "indirect",
    "substitute",
    "do_nothing",
    "potential_entrant",
  ].filter((category) => competitorText.includes(category)).length;
  const actionPlanFacts = reportSectionItems(report, "action_plan", "known_facts_ru");
  const diligenceQuestions = reportSectionItems(
    report,
    "diligence_questions",
    "known_facts_ru",
  );
  const marketText = reportSectionText(report, "market_size");
  const hasMarketSourceRefs = safeArray(safeObject(gtm).dimensions).some(
    (dimension) => safeArray(safeObject(dimension).market_source_ids).length > 0,
  );

  return {
    actionPlanItems: actionPlanFacts.length || launchPlanItems,
    chartCards: [metricPoints, marketPoints, readinessDimensions].filter(
      (points) => points.length > 0,
    ).length,
    chartPoints:
      metricPoints.length + marketPoints.length + readinessDimensions.length,
    competitorCategories,
    competitorRows: competitorFacts.length,
    diligenceQuestions: diligenceQuestions.length,
    gtmDimensions,
    marketEvidenceFrozen:
      marketText.includes("source_mode=frozen") || hasMarketSourceRefs,
    marketUnknownsExplicit: /TAM|SAM|SOM/u.test(marketText),
    profileFields,
    readinessDimensions: readinessDimensions.length,
  };
}

function requireBoolean(value, key) {
  if (value !== true) {
    throw new Error(`case_copilot_scenario_journey_missing_${key}`);
  }
}

function requireNonEmptyArray(value, key) {
  if (!Array.isArray(value) || value.length < 1) {
    throw new Error(`case_copilot_scenario_journey_missing_${key}`);
  }
}

export function validateCaseCopilotScenarioJourneyEvidence(journey, fixtureSummary) {
  if (fixtureSummary?.mime_type !== "text/plain") {
    throw new Error("case_copilot_scenario_journey_requires_text_fixture");
  }
  const evidence = journey?.caseCopilotScenarioJourney;
  if (!evidence || typeof evidence !== "object") {
    throw new Error("case_copilot_scenario_journey_missing_structured_evidence");
  }
  const fixtures = evidence.fixtures;
  if (!Array.isArray(fixtures) || fixtures.length !== 2) {
    throw new Error("case_copilot_scenario_journey_requires_both_fixtures");
  }
  const fixtureNames = new Set(fixtures.map((fixture) => fixture?.fixture_name));
  if (!fixtureNames.has("idea_inventory") || !fixtureNames.has("idea_clinic")) {
    throw new Error("case_copilot_scenario_journey_fixture_set_invalid");
  }
  for (const fixture of fixtures) {
    if (!fixture?.case_id) throw new Error("case_copilot_scenario_journey_case_missing");
    requireNonEmptyArray(fixture.ui_interactions, "ui_interactions");
    const requiredUiInteractions = [
      "file_upload",
      "start_analysis",
      "gate2_approve",
      "unknown_answer",
      "public_research_consent",
      "scenario_select_base",
      "launch_pack_generate",
      "launch_pack_download",
    ];
    for (const interaction of requiredUiInteractions) {
      if (!fixture.ui_interactions.includes(interaction)) {
        throw new Error(`case_copilot_scenario_journey_missing_ui_${interaction}`);
      }
    }
    const visibleState = fixture.visible_state;
    requireBoolean(visibleState?.file_uploaded, "visible_file_uploaded");
    requireBoolean(visibleState?.question_card_visible, "visible_question_card");
    requireBoolean(visibleState?.research_status_visible, "visible_research_status");
    requireBoolean(visibleState?.scenario_metrics_visible, "visible_scenario_metrics");
    requireBoolean(visibleState?.launch_pack_visible, "visible_launch_pack");
    const finalScreenshotState = fixture.final_screenshot_state;
    requireBoolean(finalScreenshotState?.populated_same_case_ui, "final_screenshot_state");
    requireBoolean(finalScreenshotState?.case_copilot_panel_visible, "final_case_copilot_panel");
    requireBoolean(fixture.text_brief_uploaded, "text_brief_uploaded");
    requireBoolean(fixture.question_visible, "question_visible");
    requireBoolean(fixture.founder_statement_accepted, "founder_statement_accepted");
    requireBoolean(fixture.unknown_answer_recorded, "unknown_answer_recorded");
    const research = fixture.research;
    requireBoolean(research?.plan_prepared, "research_plan_prepared");
    requireBoolean(research?.provider_calls_zero_before_queue, "provider_boundary");
    requireBoolean(research?.explicit_consent, "research_consent");
    if (!["completed", "partial"].includes(research?.job_status)) {
      throw new Error("case_copilot_scenario_journey_job_status_invalid");
    }
    requireNonEmptyArray(research.citations, "research_citations");
    requireNonEmptyArray(research.source_refs, "research_source_refs");
    requireBoolean(research?.no_source_fact_promotion, "no_source_fact_promotion");

    const scenarios = fixture.scenarios;
    if (
      JSON.stringify(scenarios?.scenario_keys) !==
      JSON.stringify(["conservative", "base", "optimistic"])
    ) {
      throw new Error("case_copilot_scenario_journey_scenario_keys_invalid");
    }
    if (scenarios?.selected_key !== "base") {
      throw new Error("case_copilot_scenario_journey_base_selection_missing");
    }
    requireBoolean(scenarios?.metric_delta, "metric_delta");
    requireBoolean(scenarios?.readiness_delta, "readiness_delta");
    requireBoolean(scenarios?.risk_delta, "risk_delta");
    requireBoolean(scenarios?.action_delta, "action_delta");
    requireBoolean(scenarios?.metric_disclosure_complete, "metric_disclosure_complete");

    const launchPack = fixture.launch_pack;
    if (!launchPack?.asset_id) {
      throw new Error("case_copilot_scenario_journey_launch_pack_missing");
    }
    requireBoolean(launchPack.downloaded, "launch_pack_downloaded");
    requireBoolean(launchPack.versioned, "launch_pack_versioned");
    requireBoolean(launchPack.provenance_appendix, "launch_pack_provenance");

    const restart = fixture.restart;
    requireBoolean(restart?.process_restarted, "restart_process");
    requireBoolean(restart?.same_case_reloaded, "restart_same_case");
    requireBoolean(restart?.same_scenario_reloaded, "restart_same_scenario");
    requireBoolean(restart?.same_asset_reloaded, "restart_same_asset");
  }
  const crossFixture = evidence.cross_fixture;
  requireBoolean(crossFixture?.questions_differ, "cross_fixture_questions");
  requireBoolean(crossFixture?.benchmark_scopes_differ, "cross_fixture_scopes");
  requireBoolean(crossFixture?.base_inputs_differ, "cross_fixture_inputs");
  return evidence;
}

const SMART_UNIVERSITY_JOURNEY_SENSITIVE_PATTERN =
  /(?:^|[^A-Za-z])(?:[A-Za-z]:[\\/])|file:\/\/|OneDrive|Рабочий стол|Smart[_ -]?University[_ -]?Full|raw[_ -]?text|document[_ -]?text|pdf[_ -]?text|local[_ -]?path|owner[_ -]?path|sk-[A-Za-z0-9_-]{8,}/iu;

function assertNoSensitiveSmartUniversityJourneyValue(value, path = "root") {
  if (value === null || value === undefined) return;
  if (Array.isArray(value)) {
    value.forEach((item, index) =>
      assertNoSensitiveSmartUniversityJourneyValue(item, `${path}[${index}]`),
    );
    return;
  }
  if (typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (SMART_UNIVERSITY_JOURNEY_SENSITIVE_PATTERN.test(String(key))) {
        throw new Error(`smart_university_single_pdf_journey_sensitive_value path=${path}.${key}`);
      }
      assertNoSensitiveSmartUniversityJourneyValue(item, `${path}.${key}`);
    }
    return;
  }
  if (
    typeof value === "string" &&
    SMART_UNIVERSITY_JOURNEY_SENSITIVE_PATTERN.test(value)
  ) {
    throw new Error(`smart_university_single_pdf_journey_sensitive_value path=${path}`);
  }
}

function requireString(value, key) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`smart_university_single_pdf_journey_missing_${key}`);
  }
}

function requireSmartUniversityBoolean(value, key) {
  if (value !== true) {
    throw new Error(`smart_university_single_pdf_journey_missing_${key}`);
  }
}

function validateSmartUniversityPageEvidence(outputs, caseId) {
  const pageEvidence = outputs?.page_evidence ?? {};
  for (const pageKey of ["metrics", "market", "risks", "action_plan"]) {
    const page = pageEvidence[pageKey] ?? {};
    const invalidReasons = [];
    if (page.case_id !== caseId) invalidReasons.push("case_id");
    if (page.populated !== true) invalidReasons.push("populated");
    if (page.placeholder_only !== false) invalidReasons.push("placeholder_only");
    if (page.contract_satisfied !== true) invalidReasons.push("contract_satisfied");
    if (!Number.isInteger(page.rendered_text_chars) || page.rendered_text_chars < 120) {
      invalidReasons.push(`rendered_text_chars=${Number.isInteger(page.rendered_text_chars) ? page.rendered_text_chars : "invalid"}`);
    }
    if (!Number.isInteger(page.meaningful_item_count) || page.meaningful_item_count < 1) {
      invalidReasons.push(`meaningful_item_count=${Number.isInteger(page.meaningful_item_count) ? page.meaningful_item_count : "invalid"}`);
    }
    if (!Number.isInteger(page.source_signal_count) || page.source_signal_count < 1) {
      invalidReasons.push(`source_signal_count=${Number.isInteger(page.source_signal_count) ? page.source_signal_count : "invalid"}`);
    }
    if (
      page.case_id !== caseId ||
      page.populated !== true ||
      page.placeholder_only !== false ||
      page.contract_satisfied !== true ||
      !Number.isInteger(page.rendered_text_chars) ||
      page.rendered_text_chars < 120 ||
      !Number.isInteger(page.meaningful_item_count) ||
      page.meaningful_item_count < 1 ||
      !Number.isInteger(page.source_signal_count) ||
      page.source_signal_count < 1
    ) {
      throw new Error(
        `smart_university_single_pdf_journey_page_evidence_invalid page=${pageKey} reasons=${invalidReasons.join(",")}`,
      );
    }
  }
}

function validateSmartUniversityLangGraphCheckpoint(value) {
  const checkpoint = value ?? {};
  if (
    typeof checkpoint.thread_id !== "string" ||
    !checkpoint.thread_id.trim() ||
    typeof checkpoint.checkpoint_id !== "string" ||
    !/^[a-z0-9][a-z0-9_.:-]{5,127}$/iu.test(checkpoint.checkpoint_id) ||
    typeof checkpoint.checkpoint_hash !== "string" ||
    !/^[a-f0-9]{64}$/u.test(checkpoint.checkpoint_hash) ||
    !Number.isInteger(checkpoint.data_revision) ||
    checkpoint.data_revision < 1
  ) {
    throw new Error("smart_university_single_pdf_journey_langgraph_checkpoint_invalid");
  }
  return checkpoint;
}

function validateSmartUniversityRestartCheckpoint(identity, restart) {
  const checkpoint = validateSmartUniversityLangGraphCheckpoint(
    identity?.langgraph_checkpoint,
  );
  const reloaded = validateSmartUniversityLangGraphCheckpoint(
    restart?.langgraph_checkpoint,
  );
  for (const key of ["thread_id", "checkpoint_id", "checkpoint_hash", "data_revision"]) {
    if (reloaded[key] !== checkpoint[key]) {
      throw new Error("smart_university_single_pdf_journey_langgraph_checkpoint_mismatch");
    }
  }
  requireSmartUniversityBoolean(
    restart?.langgraph_checkpoint_reloaded,
    "restart_langgraph_checkpoint_reloaded",
  );
}

const SMART_UNIVERSITY_ONLINE_RESEARCH_TAB_LABELS = Object.freeze([
  "Онлайн-ресерч",
  "Live-поиск",
]);
const SMART_UNIVERSITY_PUBLIC_RESEARCH_ANSWER_TAB_LABEL = "Публичный поиск";
const SMART_UNIVERSITY_OFFLINE_RESEARCH_TAB_LABELS = Object.freeze([
  "Офлайн-демо",
]);
const SMART_UNIVERSITY_UNAVAILABLE_RESEARCH_TAB_LABELS = Object.freeze([
  "Без live-провайдера",
]);

export function selectSmartUniversityResearchTabLabel(labels, options = {}) {
  const visibleLabels = Array.isArray(labels) ? labels.map((label) => String(label)) : [];
  const requireLivePublicResearch = options?.requireLivePublicResearch === true;
  if (visibleLabels.includes(SMART_UNIVERSITY_PUBLIC_RESEARCH_ANSWER_TAB_LABEL)) {
    return SMART_UNIVERSITY_PUBLIC_RESEARCH_ANSWER_TAB_LABEL;
  }
  const onlineLabel = SMART_UNIVERSITY_ONLINE_RESEARCH_TAB_LABELS.find((label) =>
    visibleLabels.includes(label),
  );
  const offlineLabel = SMART_UNIVERSITY_OFFLINE_RESEARCH_TAB_LABELS.find((label) =>
    visibleLabels.includes(label),
  );
  const unavailableLabel = SMART_UNIVERSITY_UNAVAILABLE_RESEARCH_TAB_LABELS.find((label) =>
    visibleLabels.includes(label),
  );
  if (requireLivePublicResearch && !onlineLabel && (offlineLabel || unavailableLabel)) {
    throw new Error("smart_university_live_research_tab_unavailable");
  }
  if (requireLivePublicResearch) return onlineLabel ?? null;
  return onlineLabel ?? offlineLabel ?? unavailableLabel ?? null;
}

export function selectSmartUniversityLiveAcquisitionMode(controls) {
  const visibleControls = Array.isArray(controls)
    ? controls
        .map((control) => ({
          disabled: control?.disabled === true,
          label: String(control?.label ?? ""),
          mode: String(control?.mode ?? ""),
          visible: control?.visible === true,
        }))
        .filter((control) => control.visible)
    : [];
  if (visibleControls.length === 0) return null;
  const liveControl = visibleControls.find(
    (control) => control.mode === "live_public_research",
  );
  if (
    liveControl &&
    !liveControl.disabled &&
    SMART_UNIVERSITY_ONLINE_RESEARCH_TAB_LABELS.includes(liveControl.label)
  ) {
    return "live_public_research";
  }
  throw new Error("smart_university_live_research_mode_unavailable");
}

function validateSmartUniversityLiveResearchEvidence(research) {
  for (const key of [
    "requested_acquisition_mode",
    "selected_acquisition_mode",
    "acquisition_mode",
  ]) {
    if (research?.[key] !== "live_public_research") {
      throw new Error("smart_university_single_pdf_journey_live_research_mode_invalid");
    }
  }
  if (research.provider !== "openai") {
    throw new Error("smart_university_single_pdf_journey_live_provider_invalid");
  }
  if (!["web_search", "public_web_search", "openai_web_search"].includes(research.tool)) {
    throw new Error("smart_university_single_pdf_journey_live_tool_invalid");
  }
  if (research.tool_call_observed !== true) {
    throw new Error("smart_university_single_pdf_journey_live_tool_invalid");
  }
  if (!Number.isFinite(research.latency_ms) || research.latency_ms < 0) {
    throw new Error("smart_university_single_pdf_journey_live_latency_invalid");
  }
  if (!Number.isInteger(research.source_count) || research.source_count < 1) {
    throw new Error("smart_university_single_pdf_journey_live_sources_invalid");
  }
  if (!Array.isArray(research.sanitized_sources) || research.sanitized_sources.length < 1) {
    throw new Error("smart_university_single_pdf_journey_live_sources_invalid");
  }
  for (const source of research.sanitized_sources) {
    if (
      typeof source?.url !== "string" ||
      !/^https?:\/\//iu.test(source.url) ||
      source.source_mode !== "live" ||
      typeof (source.as_of ?? source.published_date) !== "string"
    ) {
      throw new Error("smart_university_single_pdf_journey_live_sources_invalid");
    }
  }
  const traceHealth = research.trace_health ?? {};
  const disabledTraceValues = new Set(["disabled", "tracing_disabled", "offline", ""]);
  const traceStatus = String(traceHealth.status ?? "");
  const langsmithStatus = String(traceHealth.langsmith_status ?? "");
  const auditStatus = String(traceHealth.audit_status ?? "");
  const healthyTraceValues = new Set(["ok", "exported", "healthy"]);
  const healthyTrace =
    healthyTraceValues.has(traceStatus) &&
    healthyTraceValues.has(langsmithStatus) &&
    healthyTraceValues.has(auditStatus);
  const degradedLangSmithWithLocalAudit =
    traceStatus === "degraded" &&
    langsmithStatus === "degraded" &&
    auditStatus === "ok" &&
    traceHealth.fallback_used === "local_audit" &&
    traceHealth.error_code === "external_export_failed";
  if (
    disabledTraceValues.has(traceStatus) ||
    disabledTraceValues.has(langsmithStatus) ||
    (!healthyTrace && !degradedLangSmithWithLocalAudit)
  ) {
    throw new Error("smart_university_single_pdf_journey_live_trace_invalid");
  }
  const tokenCostStatus = research.token_cost_status ?? {};
  if (
    typeof tokenCostStatus.status !== "string" ||
    !tokenCostStatus.status.trim() ||
    tokenCostStatus.raw_values_excluded !== true
  ) {
    throw new Error("smart_university_single_pdf_journey_live_usage_invalid");
  }
}

function validateSmartUniversityReportArtifacts(outputs, caseId) {
  if (outputs?.final_decision_accepted !== true) {
    throw new Error("smart_university_single_pdf_journey_report_artifacts_invalid");
  }
  const reportArtifacts = outputs.report_artifacts ?? {};
  const reportRoot = `/api/startup/cases/${encodeURIComponent(caseId)}/report`;
  const sha256Pattern = /^sha256:[a-f0-9]{64}$/u;
  if (
    reportArtifacts.case_id !== caseId ||
    reportArtifacts.json_path !== `${reportRoot}/json` ||
    reportArtifacts.html_path !== `${reportRoot}/html` ||
    reportArtifacts.pdf_path !== `${reportRoot}/pdf` ||
    reportArtifacts.pdf_bounded !== true ||
    reportArtifacts.pdf_magic !== "%PDF" ||
    typeof reportArtifacts.report_snapshot_id !== "string" ||
    !reportArtifacts.report_snapshot_id.trim() ||
    !sha256Pattern.test(String(reportArtifacts.json_sha256 ?? "")) ||
    !sha256Pattern.test(String(reportArtifacts.html_sha256 ?? "")) ||
    !sha256Pattern.test(String(reportArtifacts.pdf_sha256 ?? ""))
  ) {
    throw new Error("smart_university_single_pdf_journey_report_artifacts_invalid");
  }
  const formats = new Set(reportArtifacts.downloaded_formats ?? []);
  for (const format of ["JSON", "HTML", "PDF"]) {
    if (!formats.has(format)) {
      throw new Error("smart_university_single_pdf_journey_report_artifacts_invalid");
    }
  }
}

function validateSmartUniversityReportRestartArtifacts(outputs, restart) {
  const reportArtifacts = outputs?.report_artifacts ?? {};
  const reloadedArtifacts = restart?.report_artifacts ?? {};
  for (const key of [
    "report_snapshot_id",
    "json_sha256",
    "html_sha256",
    "pdf_sha256",
  ]) {
    if (
      typeof reportArtifacts[key] !== "string" ||
      !reportArtifacts[key].trim() ||
      reloadedArtifacts[key] !== reportArtifacts[key]
    ) {
      throw new Error("smart_university_single_pdf_journey_report_restart_mismatch");
    }
  }
}

export function validateSmartUniversitySinglePdfJourneyEvidence(
  journey,
  fixtureSummary,
  options = {},
) {
  if (fixtureSummary?.mime_type !== "application/pdf") {
    throw new Error("smart_university_single_pdf_journey_requires_pdf_fixture");
  }
  const evidence = journey?.smartUniversitySinglePdfJourney;
  if (!evidence || typeof evidence !== "object") {
    throw new Error("smart_university_single_pdf_journey_missing_structured_evidence");
  }
  assertNoSensitiveSmartUniversityJourneyValue(evidence);

  const identity = evidence.case_identity ?? {};
  requireString(identity.case_id, "case_id");
  requireString(identity.thread_id, "thread_id");
  requireString(identity.research_job_id, "research_job_id");
  requireString(identity.selected_scenario_key, "selected_scenario_key");
  if (identity.selected_scenario_key !== "base") {
    throw new Error("smart_university_single_pdf_journey_requires_base_scenario");
  }
  requireString(identity.asset_id, "asset_id");

  const upload = evidence.upload ?? {};
  requireSmartUniversityBoolean(upload.pdf_uploaded, "pdf_uploaded");
  requireSmartUniversityBoolean(upload.receipt_visible, "receipt_visible");
  requireSmartUniversityBoolean(upload.profile_source_grounded, "profile_source_grounded");
  requireSmartUniversityBoolean(upload.gate2_ready, "gate2_ready");

  const gapHandling = evidence.founder_gap_handling ?? {};
  requireSmartUniversityBoolean(gapHandling.question_visible, "question_visible");
  requireSmartUniversityBoolean(gapHandling.answered_or_skipped, "answered_or_skipped");
  requireSmartUniversityBoolean(
    gapHandling.private_metrics_manual_or_file_only,
    "private_metrics_manual_or_file_only",
  );

  const research = evidence.public_research ?? {};
  requireSmartUniversityBoolean(research.explicit_consent, "research_consent");
  if (!["completed", "partial"].includes(research.status)) {
    throw new Error("smart_university_single_pdf_journey_research_status_invalid");
  }
  requireNonEmptyArray(research.visible_sources, "research_visible_sources");
  requireSmartUniversityBoolean(research.scenario_delta_visible, "research_scenario_delta");
  const scenarioChangeEvidence = research.scenario_change_evidence ?? {};
  if (
    !Number.isInteger(scenarioChangeEvidence.rendered_comparison_count) ||
    scenarioChangeEvidence.rendered_comparison_count < 1 ||
    !Number.isInteger(scenarioChangeEvidence.rendered_change_count) ||
    scenarioChangeEvidence.rendered_change_count < 1
  ) {
    throw new Error("smart_university_single_pdf_journey_scenario_change_evidence_invalid");
  }
  requireSmartUniversityBoolean(
    research.source_fact_promotion_blocked,
    "research_source_fact_promotion_blocked",
  );
  const provenanceGuard = research.provenance_guard ?? {};
  for (const key of [
    "accepted_inputs_checked",
    "profile_fields_checked",
    "public_private_aliases_blocked",
  ]) {
    if (provenanceGuard[key] !== true) {
      throw new Error("smart_university_single_pdf_journey_public_research_provenance_guard_invalid");
    }
  }
  if (options?.requireLivePublicResearch === true) {
    validateSmartUniversityLiveResearchEvidence(research);
  }

  const scenarios = evidence.scenarios ?? {};
  if (
    JSON.stringify(scenarios.keys) !==
    JSON.stringify(["conservative", "base", "optimistic"])
  ) {
    throw new Error("smart_university_single_pdf_journey_scenario_keys_invalid");
  }
  if (scenarios.selected_key !== identity.selected_scenario_key) {
    throw new Error("smart_university_single_pdf_journey_selected_scenario_mismatch");
  }
  if (scenarios.selected_key !== "base") {
    throw new Error("smart_university_single_pdf_journey_requires_base_scenario");
  }
  requireSmartUniversityBoolean(scenarios.provenance_complete, "scenario_provenance_complete");

  const outputs = evidence.outputs ?? {};
  for (const key of [
    "market_reconstruction_visible",
    "metrics_visible",
    "risks_visible",
    "actions_visible",
    "plan_7_30_60_90_visible",
    "launch_pack_link_visible",
    "launch_pack_downloaded",
  ]) {
    requireSmartUniversityBoolean(outputs[key], key);
  }
  validateSmartUniversityPageEvidence(outputs, identity.case_id);
  const launchPackContract = outputs.launch_pack_contract ?? {};
  for (const key of [
    "platform_vs_housing_separated",
    "tariff_and_lead_economics_present",
    "forecast_2027_2031_clear",
    "rating_methodology_present",
    "housing_legal_fire_sanitary_gates_present",
    "tranche_plan_present",
    "provenance_appendix_present",
  ]) {
    if (launchPackContract[key] !== true) {
      throw new Error("smart_university_single_pdf_journey_launch_pack_contract_invalid");
    }
  }
  if (options?.requireLivePublicResearch === true) {
    validateSmartUniversityReportArtifacts(outputs, identity.case_id);
  }

  const restart = evidence.restart ?? {};
  for (const key of [
    "process_restarted",
    "same_case_ui_rehydrated",
    "same_case_reloaded",
    "same_thread_reloaded",
    "same_research_job_reloaded",
    "same_scenario_reloaded",
    "same_asset_reloaded",
  ]) {
    requireSmartUniversityBoolean(restart[key], `restart_${key}`);
  }
  if (options?.requireLivePublicResearch === true) {
    requireSmartUniversityBoolean(
      restart.same_final_decision_reloaded,
      "restart_same_final_decision_reloaded",
    );
    requireSmartUniversityBoolean(
      restart.same_report_artifacts_reloaded,
      "restart_same_report_artifacts_reloaded",
    );
    validateSmartUniversityRestartCheckpoint(identity, restart);
    validateSmartUniversityReportRestartArtifacts(outputs, restart);
  }
  return evidence;
}

function parseOptions(argv) {
  return Object.fromEntries(
    argv.map((entry) => {
      const separator = entry.indexOf("=");
      if (!entry.startsWith("--") || separator < 3) {
        throw new Error(`invalid_argument ${entry}`);
      }
      return [entry.slice(2, separator), entry.slice(separator + 1)];
    }),
  );
}

function required(options, name) {
  const value = options[name];
  if (!value) {
    throw new Error(`missing_argument --${name}`);
  }
  return value;
}

function evidenceRelativePath(evidencePath, artifactPath) {
  return relative(dirname(evidencePath), artifactPath).replaceAll("\\", "/");
}

function desktopStateRelativePath(manifestPath, artifactPath) {
  return relative(dirname(manifestPath), artifactPath).replaceAll("\\", "/");
}

function buildDesktopStateManifest(desktopStatesPath, manifestPath, captures = []) {
  const capturesByFile = new Map(
    captures
      .filter((capture) => capture?.outputPath)
      .map((capture) => [basename(capture.outputPath), capture]),
  );
  const states = CANONICAL_DESKTOP_STATE_SCREENSHOTS.map((file, index) => {
    const artifactPath = join(desktopStatesPath, file);
    const capture = capturesByFile.get(file);
    return {
      file,
      index: index + 1,
      path: desktopStateRelativePath(manifestPath, artifactPath),
      overflow:
        capture?.verticalOverflowPx === undefined
          ? undefined
          : {
              bodyScrollHeight: capture.bodyScrollHeight,
              documentScrollHeight: capture.documentScrollHeight,
              tolerancePx: DESKTOP_VERTICAL_OVERFLOW_TOLERANCE_PX,
              verticalOverflowPx: capture.verticalOverflowPx,
            },
      viewport: { width: 1440, height: 1000 },
    };
  });
  return {
    schema_version: DESKTOP_STATE_MANIFEST_SCHEMA_VERSION,
    order: [...CANONICAL_DESKTOP_STATE_SCREENSHOTS],
    states,
    viewport: { width: 1440, height: 1000 },
  };
}

function writeDesktopStateManifest(desktopStatesPath, manifestPath, captures = []) {
  mkdirSync(dirname(manifestPath), { recursive: true });
  mkdirSync(desktopStatesPath, { recursive: true });
  writeFileSync(
    manifestPath,
    `${JSON.stringify(buildDesktopStateManifest(desktopStatesPath, manifestPath, captures), null, 2)}\n`,
    "utf8",
  );
  console.log(`founder_14_desktop_states_manifest_written path=${manifestPath}`);
}

function sha256Hash(buffer) {
  return `sha256:${createHash("sha256").update(buffer).digest("hex")}`;
}

function assertSameJourneyCase(desktop, mobile) {
  const desktopCaseId = desktop.journey?.caseId;
  const mobileCaseId = mobile.journey?.caseId;
  if (!desktopCaseId || !mobileCaseId || desktopCaseId !== mobileCaseId) {
    throw new Error(
      `browser_evidence_case_mismatch desktop=${desktopCaseId ?? "missing"} mobile=${mobileCaseId ?? "missing"}`,
    );
  }
}

const CAPTURE_EVIDENCE_FIELDS = Object.freeze([
  "blockedExternalRequests",
  "blockedParserInjections",
  "networkViolations",
  "observedRequests",
]);

function aggregateCaptureEvidence(captures) {
  if (!Array.isArray(captures) || captures.length === 0) {
    throw new Error("browser_evidence_capture_stats_invalid captures=empty");
  }
  const totals = Object.fromEntries(
    CAPTURE_EVIDENCE_FIELDS.map((field) => [field, 0]),
  );
  for (const [index, capture] of captures.entries()) {
    for (const field of CAPTURE_EVIDENCE_FIELDS) {
      const value = capture?.[field];
      if (!Number.isSafeInteger(value) || value < 0) {
        throw new Error(
          `browser_evidence_capture_stats_invalid index=${index} field=${field}`,
        );
      }
      totals[field] += value;
      if (!Number.isSafeInteger(totals[field])) {
        throw new Error(
          `browser_evidence_capture_stats_invalid aggregate_field=${field}`,
        );
      }
    }
  }
  return totals;
}

export function assertDesktopStateCaptureFitsViewport(stateFile, capture) {
  const innerHeight = capture?.innerHeight ?? capture?.height;
  const documentScrollHeight = capture?.documentScrollHeight;
  const bodyScrollHeight = capture?.bodyScrollHeight;
  const maxScrollHeight = Math.max(
    Number(documentScrollHeight ?? 0),
    Number(bodyScrollHeight ?? 0),
  );
  const verticalOverflowPx = Math.max(0, maxScrollHeight - Number(innerHeight ?? 0));
  if (
    !Number.isFinite(verticalOverflowPx) ||
    verticalOverflowPx > DESKTOP_VERTICAL_OVERFLOW_TOLERANCE_PX
  ) {
    throw new Error(
      `vertical_overflow state=${stateFile} viewportHeight=${innerHeight} documentScrollHeight=${documentScrollHeight} bodyScrollHeight=${bodyScrollHeight} overflowPx=${verticalOverflowPx} tolerancePx=${DESKTOP_VERTICAL_OVERFLOW_TOLERANCE_PX}`,
    );
  }
  return {
    bodyScrollHeight,
    documentScrollHeight,
    tolerancePx: DESKTOP_VERTICAL_OVERFLOW_TOLERANCE_PX,
    verticalOverflowPx,
  };
}

function safeFixtureSummary(fixturePath, requirePdfUploadJourney) {
  if (!fixturePath) return undefined;
  const resolvedFixture = resolve(fixturePath);
  if (!existsSync(resolvedFixture)) {
    throw new Error("browser_evidence_fixture_missing");
  }
  const bytes = statSync(resolvedFixture).size;
  if (bytes < 1 || bytes > MAX_SMOKE_PDF_BYTES) {
    throw new Error("browser_evidence_fixture_size_invalid");
  }
  const hash = createHash("sha256")
    .update(readFileSync(resolvedFixture))
    .digest("hex");
  const lowerFixture = resolvedFixture.toLowerCase();
  const mimeType = lowerFixture.endsWith(".pdf")
    ? "application/pdf"
    : lowerFixture.endsWith(".txt")
      ? "text/plain"
      : "application/octet-stream";
  if (requirePdfUploadJourney && mimeType !== "application/pdf") {
    throw new Error("browser_evidence_pdf_fixture_not_pdf");
  }
  return {
    bytes,
    mime_type: mimeType,
    pdf_upload_journey: Boolean(requirePdfUploadJourney),
    sha256: `sha256:${hash}`,
  };
}

function assertNoSensitiveAdminTraceValue(value) {
  if (value === null || value === undefined) return;
  if (Array.isArray(value)) {
    for (const item of value) assertNoSensitiveAdminTraceValue(item);
    return;
  }
  if (typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (SENSITIVE_ADMIN_TRACE_KEYS.has(key.toLowerCase())) {
        throw new Error("browser_evidence_admin_trace_privacy_violation");
      }
      assertNoSensitiveAdminTraceValue(item);
    }
    return;
  }
  if (typeof value !== "string") return;
  if (
    /(?:^|[\\/])[^\\/]+\.pdf\b/i.test(value) ||
    /[A-Z]:\\/i.test(value) ||
    /\b(?:prompt|secret|api[_ -]?key|sk-[A-Za-z0-9_-]+|[\w.+-]+@[\w.-]+\.[a-z]{2,})\b/i.test(
      value,
    )
  ) {
    throw new Error("browser_evidence_admin_trace_privacy_violation");
  }
}

function assertOnlyAllowedKeys(value, allowedKeys) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("browser_evidence_admin_trace_schema_invalid");
  }
  for (const key of Object.keys(value)) {
    if (!allowedKeys.has(key)) {
      throw new Error("browser_evidence_admin_trace_schema_invalid");
    }
  }
}

function assertExactObjectKeys(value, expectedKeys, errorCode) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(errorCode);
  }
  const actualKeys = Object.keys(value);
  if (
    actualKeys.length !== expectedKeys.size ||
    actualKeys.some((key) => !expectedKeys.has(key))
  ) {
    throw new Error(errorCode);
  }
}

function assertFounderSafeReportValue(value) {
  if (value === null || value === undefined) return;
  if (Array.isArray(value)) {
    for (const item of value) assertFounderSafeReportValue(item);
    return;
  }
  if (typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (FOUNDER_SAFE_REPORT_PRIVATE_KEYS.has(key.toLowerCase())) {
        throw new Error("browser_evidence_report_json_privacy_violation");
      }
      assertFounderSafeReportValue(item);
    }
    return;
  }
  if (
    typeof value === "string" &&
    FOUNDER_SAFE_REPORT_PRIVATE_VALUE_PATTERN.test(value)
  ) {
    throw new Error("browser_evidence_report_json_privacy_violation");
  }
}

function assertStringArray(value, errorCode) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(errorCode);
  }
}

export function validateFounderSafeReportPayload(payload) {
  assertExactObjectKeys(
    payload,
    FOUNDER_SAFE_REPORT_TOP_LEVEL_KEYS,
    "browser_evidence_report_json_schema_invalid",
  );
  assertFounderSafeReportValue(payload);
  if (
    typeof payload.title_ru !== "string" ||
    typeof payload.subtitle_ru !== "string" ||
    typeof payload.as_of_ru !== "string" ||
    !Number.isSafeInteger(payload.data_revision) ||
    payload.data_revision < 1
  ) {
    throw new Error("browser_evidence_report_json_schema_invalid");
  }
  if (
    !Array.isArray(payload.main_sections) ||
    payload.main_sections.length !== FOUNDER_SAFE_REPORT_SECTION_KEYS.length
  ) {
    throw new Error("browser_evidence_report_json_schema_invalid");
  }
  for (const [index, section] of payload.main_sections.entries()) {
    assertExactObjectKeys(
      section,
      new Set([
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
      ]),
      "browser_evidence_report_json_schema_invalid",
    );
    if (
      section.key !== FOUNDER_SAFE_REPORT_SECTION_KEYS[index] ||
      typeof section.title_ru !== "string" ||
      !FOUNDER_SAFE_REPORT_STATUSES.has(section.status) ||
      typeof section.status_label_ru !== "string" ||
      typeof section.summary_ru !== "string" ||
      typeof section.content_heading_ru !== "string"
    ) {
      throw new Error("browser_evidence_report_json_schema_invalid");
    }
    for (const key of [
      "known_facts_ru",
      "blockers_ru",
      "next_data_ru",
      "unlocks_ru",
    ]) {
      assertStringArray(
        section[key],
        "browser_evidence_report_json_schema_invalid",
      );
    }
  }
  if (
    !payload.metric_cards ||
    typeof payload.metric_cards !== "object" ||
    Array.isArray(payload.metric_cards) ||
    !Array.isArray(payload.improvement_proposals)
  ) {
    throw new Error("browser_evidence_report_json_schema_invalid");
  }
  for (const [cardKey, card] of Object.entries(payload.metric_cards)) {
    assertExactObjectKeys(
      card,
      new Set([
        "title_ru",
        "summary_ru",
        "status",
        "why_it_matters_ru",
        "next_unlock_ru",
      ]),
      "browser_evidence_report_json_schema_invalid",
    );
    if (
      !FOUNDER_SAFE_KEY_PATTERN.test(cardKey) ||
      typeof card.title_ru !== "string" ||
      typeof card.summary_ru !== "string" ||
      !FOUNDER_SAFE_REPORT_STATUSES.has(card.status) ||
      typeof card.why_it_matters_ru !== "string" ||
      typeof card.next_unlock_ru !== "string"
    ) {
      throw new Error("browser_evidence_report_json_schema_invalid");
    }
  }
  for (const proposal of payload.improvement_proposals) {
    assertExactObjectKeys(
      proposal,
      new Set([
        "target_area",
        "title_ru",
        "recommendation_ru",
        "rationale_ru",
        "expected_effect_ru",
        "provenance",
      ]),
      "browser_evidence_report_json_schema_invalid",
    );
    if (
      !FOUNDER_SAFE_IMPROVEMENT_AREAS.has(proposal.target_area) ||
      typeof proposal.title_ru !== "string" ||
      typeof proposal.recommendation_ru !== "string" ||
      typeof proposal.rationale_ru !== "string" ||
      typeof proposal.expected_effect_ru !== "string" ||
      proposal.provenance !== "ai_recommendation"
    ) {
      throw new Error("browser_evidence_report_json_schema_invalid");
    }
  }
  assertExactObjectKeys(
    payload.technical_appendix,
    new Set(["methodology_ru", "sources_ru"]),
    "browser_evidence_report_json_schema_invalid",
  );
  assertStringArray(
    payload.technical_appendix.methodology_ru,
    "browser_evidence_report_json_schema_invalid",
  );
  assertStringArray(
    payload.technical_appendix.sources_ru,
    "browser_evidence_report_json_schema_invalid",
  );
  assertExactObjectKeys(
    payload.analytics,
    new Set(["metric_points", "market_points", "readiness_dimensions"]),
    "browser_evidence_report_json_schema_invalid",
  );
  for (const key of ["metric_points", "market_points", "readiness_dimensions"]) {
    if (!Array.isArray(payload.analytics[key])) {
      throw new Error("browser_evidence_report_json_schema_invalid");
    }
  }
  for (const pointsKey of ["metric_points", "market_points"]) {
    for (const point of payload.analytics[pointsKey]) {
      assertExactObjectKeys(
        point,
        new Set(["key", "label_ru", "value", "unit", "period_ru", "status"]),
        "browser_evidence_report_json_schema_invalid",
      );
      if (
        typeof point.key !== "string" ||
        !FOUNDER_SAFE_KEY_PATTERN.test(point.key) ||
        typeof point.label_ru !== "string" ||
        typeof point.value !== "number" ||
        !Number.isFinite(point.value) ||
        point.value < 0 ||
        (point.unit !== null && typeof point.unit !== "string") ||
        (point.period_ru !== null && typeof point.period_ru !== "string") ||
        !FOUNDER_SAFE_ANALYTICS_POINT_STATUSES.has(point.status)
      ) {
        throw new Error("browser_evidence_report_json_schema_invalid");
      }
    }
  }
  for (const dimension of payload.analytics.readiness_dimensions) {
    assertExactObjectKeys(
      dimension,
      new Set(["key", "label_ru", "status", "status_label_ru", "explanation_ru"]),
      "browser_evidence_report_json_schema_invalid",
    );
    if (
      typeof dimension.key !== "string" ||
      !FOUNDER_SAFE_KEY_PATTERN.test(dimension.key) ||
      typeof dimension.label_ru !== "string" ||
      !FOUNDER_SAFE_READINESS_STATUSES.has(dimension.status) ||
      typeof dimension.status_label_ru !== "string" ||
      typeof dimension.explanation_ru !== "string"
    ) {
      throw new Error("browser_evidence_report_json_schema_invalid");
    }
  }
  return payload;
}

function assertReportArtifactPath(value, expectedCaseId, kind) {
  if (typeof value !== "string" || !value.startsWith("/api/")) {
    throw new Error("browser_evidence_report_metadata_schema_invalid");
  }
  const match = value.match(
    /^\/api\/(?:v1\/)?startup\/cases\/([^/]+)\/report\/(json|html|pdf)$/,
  );
  let decodedCaseId;
  try {
    decodedCaseId = match ? decodeURIComponent(match[1]) : undefined;
  } catch {
    decodedCaseId = undefined;
  }
  if (!match || decodedCaseId !== expectedCaseId || match[2] !== kind) {
    throw new Error("browser_evidence_report_metadata_schema_invalid");
  }
}

export function validateReportMetadata(payload, expectedCaseId, reportJson) {
  assertExactObjectKeys(
    payload,
    REPORT_METADATA_KEYS,
    "browser_evidence_report_metadata_schema_invalid",
  );
  if (
    payload.case_id !== expectedCaseId ||
    payload.report_status !== "ready" ||
    !UUID_PATTERN.test(String(payload.snapshot_id ?? "")) ||
    !/^sha256:[0-9a-f]{64}$/i.test(String(payload.snapshot_hash ?? "")) ||
    !Number.isSafeInteger(payload.snapshot_revision) ||
    payload.snapshot_revision < 1 ||
    !new Set(["not_ready", "required", "approved"]).has(
      payload.freeze_status,
    ) ||
    !new Set(["not_ready", "freeze_required", "ready"]).has(
      payload.pdf_status,
    )
  ) {
    throw new Error("browser_evidence_report_metadata_schema_invalid");
  }
  assertReportArtifactPath(payload.json_url, expectedCaseId, "json");
  assertReportArtifactPath(payload.html_url, expectedCaseId, "html");
  assertReportArtifactPath(payload.pdf_url, expectedCaseId, "pdf");
  if (reportJson && payload.snapshot_revision !== reportJson.data_revision) {
    throw new Error("browser_evidence_report_metadata_revision_mismatch");
  }
  return payload;
}

function validateAdminTracePayload(
  payload,
  expectedCaseId,
  reportJson,
  reportMetadata,
) {
  assertNoSensitiveAdminTraceValue(payload);
  assertOnlyAllowedKeys(
    payload,
    new Set([
      "schema_version",
      "case_id",
      "run_id",
      "node_rows",
      "usage_summary",
      "report_lineage",
      "exporter_health",
      "langsmith_health",
    ]),
  );
  if (payload?.schema_version !== "startup_trace_view@1") {
    throw new Error("browser_evidence_admin_trace_schema_invalid");
  }
  const expectedRunId = `startup-api-${expectedCaseId}`;
  if (payload.case_id !== expectedCaseId || payload.run_id !== expectedRunId) {
    throw new Error("browser_evidence_admin_trace_case_mismatch");
  }
  const nodeRows = Array.isArray(payload.node_rows) ? payload.node_rows : [];
  for (const row of nodeRows) {
    assertOnlyAllowedKeys(
      row,
      new Set([
        "case_id",
        "run_id",
        "node",
        "agent_role",
        "attempt",
        "retry_count",
        "status",
        "error_code",
        "duration_ms",
        "evidence_count",
        "fallback_used",
        "timeout_ms",
        "tool",
      ]),
    );
    if (row.case_id !== expectedCaseId || row.run_id !== expectedRunId) {
      throw new Error("browser_evidence_admin_trace_case_mismatch");
    }
  }
  const nodes = new Set(
    nodeRows
      .filter(
        (row) =>
          ["completed", "success"].includes(row?.status) ||
          (
            row?.status === "blocked" &&
            row?.error_code === "blocked_by_policy:startup_disclosure"
          ),
      )
      .map((row) => row?.node)
      .filter(Boolean),
  );
  if ([...REQUIRED_PDF_TRACE_NODES].some((node) => !nodes.has(node))) {
    throw new Error("browser_evidence_admin_trace_node_coverage_missing");
  }
  const lineage = payload.report_lineage ?? {};
  assertOnlyAllowedKeys(
    lineage,
    new Set([
      "decision",
      "gate4_status",
      "report_id",
      "report_revision",
      "report_checksum",
    ]),
  );
  if (
    lineage.decision !== "approved" ||
    lineage.gate4_status !== "completed" ||
    typeof lineage.report_id !== "string" ||
    !Number.isSafeInteger(lineage.report_revision) ||
    !/^[a-f0-9]{64}$/i.test(String(lineage.report_checksum ?? ""))
  ) {
    throw new Error("browser_evidence_admin_trace_lineage_invalid");
  }
  const langsmithHealth = payload.langsmith_health ?? {};
  assertOnlyAllowedKeys(
    langsmithHealth,
    new Set(["provider", "status", "error_code", "fallback_used"]),
  );
  if (
    langsmithHealth.provider !== "langsmith" ||
    langsmithHealth.status !== "disabled" ||
    langsmithHealth.error_code !== "tracing_disabled" ||
    langsmithHealth.fallback_used !== "local_audit"
  ) {
    throw new Error("browser_evidence_admin_trace_langsmith_health_invalid");
  }
  let exporterHealth = null;
  if (payload.exporter_health !== null && payload.exporter_health !== undefined) {
    assertOnlyAllowedKeys(
      payload.exporter_health,
      new Set(["status", "error_code", "fallback_used"]),
    );
    if (
      payload.exporter_health.status !== "degraded" ||
      payload.exporter_health.error_code !== "external_export_failed" ||
      payload.exporter_health.fallback_used !== "local_audit"
    ) {
      throw new Error("browser_evidence_admin_trace_exporter_health_invalid");
    }
    exporterHealth = {
      error_code: payload.exporter_health.error_code,
      fallback_used: payload.exporter_health.fallback_used,
      status: payload.exporter_health.status,
    };
  }
  const usage = payload.usage_summary ?? {};
  assertOnlyAllowedKeys(
    usage,
    new Set(["input_tokens", "output_tokens", "total_tokens", "cost_usd"]),
  );
  for (const key of ["input_tokens", "output_tokens", "total_tokens"]) {
    if (
      usage[key] !== null &&
      (!Number.isSafeInteger(usage[key]) || usage[key] < 0)
    ) {
      throw new Error("browser_evidence_admin_trace_usage_invalid");
    }
  }
  if (
    usage.cost_usd !== null &&
    !/^\d+(?:\.\d{1,8})?$/.test(String(usage.cost_usd))
  ) {
    throw new Error("browser_evidence_admin_trace_usage_invalid");
  }
  if (reportJson && lineage.report_revision !== reportJson.data_revision) {
    throw new Error("browser_evidence_admin_trace_report_mismatch");
  }
  if (reportMetadata) {
    const reportChecksum = reportMetadata.snapshot_hash.replace(/^sha256:/, "");
    if (
      lineage.report_id !== reportMetadata.snapshot_id ||
      lineage.report_revision !== reportMetadata.snapshot_revision ||
      lineage.report_checksum !== reportChecksum
    ) {
      throw new Error("browser_evidence_admin_trace_report_mismatch");
    }
  }
  return {
    case_id: payload.case_id,
    exporter_health: exporterHealth,
    langsmith_health: {
      error_code: langsmithHealth.error_code,
      fallback_used: langsmithHealth.fallback_used,
      provider: langsmithHealth.provider,
      status: langsmithHealth.status,
    },
    node_count: nodeRows.length,
    nodes: [...nodes].sort(),
    report_lineage: {
      decision: lineage.decision,
      gate4_status: lineage.gate4_status,
      report_checksum: lineage.report_checksum,
      report_id: lineage.report_id,
      report_revision: lineage.report_revision,
    },
    run_id: payload.run_id,
    usage_summary: {
      cost_usd: usage.cost_usd,
      input_tokens: usage.input_tokens,
      output_tokens: usage.output_tokens,
      total_tokens: usage.total_tokens,
    },
  };
}

function readAdminTraceEvidence(
  adminTracePath,
  expectedCaseId,
  reportJson,
  reportMetadata,
) {
  if (!adminTracePath) return undefined;
  const payload = JSON.parse(readFileSync(resolve(adminTracePath), "utf8"));
  return validateAdminTracePayload(
    payload,
    expectedCaseId,
    reportJson,
    reportMetadata,
  );
}

async function generateAdminTraceEvidence(
  auditSpoolRoot,
  caseId,
  outputPath,
) {
  if (!auditSpoolRoot || !existsSync(auditSpoolRoot)) {
    throw new Error("browser_evidence_admin_trace_audit_missing");
  }
  if (existsSync(outputPath)) {
    throw new Error("browser_evidence_admin_trace_output_exists");
  }
  const pythonPath =
    process.platform === "win32"
      ? join(REPO_ROOT, ".venv", "Scripts", "python.exe")
      : join(REPO_ROOT, ".venv", "bin", "python");
  if (!existsSync(pythonPath)) {
    throw new Error("browser_evidence_admin_trace_runtime_missing");
  }
  const runId = `startup-api-${caseId}`;
  const childEnvironment = {
    ...process.env,
    DDA_LANGSMITH_TRACING: "false",
    LANGCHAIN_API_KEY: "",
    LANGCHAIN_TRACING: "false",
    LANGCHAIN_TRACING_V2: "false",
    LANGSMITH_API_KEY: "",
    LANGSMITH_TRACING: "false",
    OPENAI_API_KEY: "",
    OPENAI_STARTUP_API_KEY: "",
  };
  await new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(
      pythonPath,
      [
        "-m",
        "due_diligence_agent.evals.startup_trace_sidecar",
        "--audit-spool-root",
        auditSpoolRoot,
        "--case-id",
        caseId,
        "--run-id",
        runId,
        "--output",
        outputPath,
      ],
      {
        cwd: REPO_ROOT,
        env: childEnvironment,
        stdio: "ignore",
        windowsHide: true,
      },
    );
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      rejectPromise(
        new Error("browser_evidence_admin_trace_generation_timeout"),
      );
    }, 30_000);
    child.once("error", () => {
      clearTimeout(timeout);
      rejectPromise(
        new Error("browser_evidence_admin_trace_generation_failed"),
      );
    });
    child.once("exit", (code) => {
      clearTimeout(timeout);
      if (code === 0 && existsSync(outputPath)) {
        resolvePromise();
        return;
      }
      rejectPromise(
        new Error("browser_evidence_admin_trace_generation_failed"),
      );
    });
  });
  return outputPath;
}

async function readBoundedLocalResponse(rawUrl, expectedContentType, artifactName) {
  if (!isAllowedBrowserRequest(rawUrl)) {
    throw new Error(`browser_evidence_artifact_url_invalid name=${artifactName}`);
  }
  const response = await fetch(rawUrl, { headers: { Accept: expectedContentType } });
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (!response.ok || !contentType.includes(expectedContentType)) {
    throw new Error(
      `browser_evidence_artifact_fetch_failed name=${artifactName} status=${response.status} content_type=${contentType}`,
    );
  }
  const contentLengthHeader = response.headers.get("content-length");
  const contentLength = contentLengthHeader === null ? null : Number(contentLengthHeader);
  if (
    contentLength !== null &&
    (!Number.isSafeInteger(contentLength) ||
      contentLength < 1 ||
      contentLength > MAX_SMOKE_PDF_BYTES)
  ) {
    throw new Error(
      `browser_evidence_artifact_size_invalid name=${artifactName} content_length=${contentLength}`,
    );
  }
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error(`browser_evidence_artifact_body_missing name=${artifactName}`);
  }
  const chunks = [];
  let totalBytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (!value) continue;
    totalBytes += value.byteLength;
    if (totalBytes > MAX_SMOKE_PDF_BYTES) {
      await reader.cancel();
      throw new Error(`browser_evidence_artifact_too_large name=${artifactName}`);
    }
    chunks.push(Buffer.from(value));
  }
  if (totalBytes < 1 || (contentLength !== null && totalBytes !== contentLength)) {
    throw new Error(
      `browser_evidence_artifact_truncated name=${artifactName} total=${totalBytes} content_length=${contentLength}`,
    );
  }
  return Buffer.concat(chunks, totalBytes);
}

async function writeBrowserEvidence(
  evidencePath,
  pageUrl,
  desktop,
  mobile,
  fixtureSummary,
  adminTracePath,
) {
  if (mobile) {
    assertSameJourneyCase(desktop, mobile);
  }
  const evidenceTotals = aggregateCaptureEvidence(
    mobile ? [desktop, mobile] : [desktop],
  );
  const journey = desktop.journey;
  if (!journey?.caseId) {
    throw new Error("browser_evidence_desktop_journey_missing");
  }
  if (fixtureSummary?.pdf_upload_journey && !adminTracePath) {
    throw new Error("browser_evidence_admin_trace_required");
  }
  const reportUrls = Object.fromEntries(
    Object.entries(journey.reportPaths).map(([kind, artifactPath]) => [
      kind,
      new URL(artifactPath, pageUrl).href,
    ]),
  );
  const reportMetadataPath = String(journey.reportPaths.JSON ?? "").replace(
    /\/json$/,
    "",
  );
  if (!reportMetadataPath || reportMetadataPath === journey.reportPaths.JSON) {
    throw new Error("browser_evidence_report_metadata_url_invalid");
  }
  const reportMetadataBytes = await readBoundedLocalResponse(
    new URL(reportMetadataPath, pageUrl).href,
    "application/json",
    "report_metadata",
  );
  const reportJson = await readBoundedLocalResponse(
    reportUrls.JSON,
    "application/json",
    "report_json",
  );
  const reportHtml = await readBoundedLocalResponse(
    reportUrls.HTML,
    "text/html",
    "report_html",
  );
  const reportPdf = await readBoundedLocalResponse(
    reportUrls.PDF,
    "application/pdf",
    "report_pdf",
  );
  const reportArtifactHashes = {
    html: sha256Hash(reportHtml),
    json: sha256Hash(reportJson),
    pdf: sha256Hash(reportPdf),
  };
  const parsedJson = validateFounderSafeReportPayload(
    JSON.parse(reportJson.toString("utf8")),
  );
  const reportMetadata = validateReportMetadata(
    JSON.parse(reportMetadataBytes.toString("utf8")),
    journey.caseId,
    parsedJson,
  );
  const adminTrace = readAdminTraceEvidence(
    adminTracePath,
    journey.caseId,
    parsedJson,
    reportMetadata,
  );
  const reportHtmlText = reportHtml.toString("utf8");
  const reportChecksum = reportMetadata.snapshot_hash.replace(/^sha256:/, "");
  if (
    !reportHtmlText.includes('data-startup-charts') ||
    !reportHtmlText.includes('id="technical-appendix"') ||
    reportHtmlText.includes(journey.caseId) ||
    reportHtmlText.includes(reportMetadata.snapshot_id) ||
    reportHtmlText.includes(reportMetadata.snapshot_hash) ||
    reportHtmlText.includes(reportChecksum)
  ) {
    throw new Error(
      "browser_evidence_report_html_privacy_or_contract_mismatch",
    );
  }
  if (!reportPdf.subarray(0, 4).equals(Buffer.from("%PDF", "ascii"))) {
    throw new Error("browser_evidence_report_pdf_invalid");
  }

  const evidenceRoot = dirname(evidencePath);
  mkdirSync(evidenceRoot, { recursive: true });
  const reportJsonPath = join(evidenceRoot, "report.json");
  const reportHtmlPath = join(evidenceRoot, "report.html");
  const reportPdfPath = join(evidenceRoot, "sample-report.pdf");
  writeFileSync(reportJsonPath, reportJson);
  writeFileSync(reportHtmlPath, reportHtml);
  writeFileSync(reportPdfPath, reportPdf);

  const payload = {
    schema_version: BROWSER_EVIDENCE_SCHEMA_VERSION,
    base_url: new URL(pageUrl).origin,
    offline: true,
    network_external_calls: evidenceTotals.networkViolations,
    browser_requests: evidenceTotals.observedRequests,
    blocked_external_requests: evidenceTotals.blockedExternalRequests,
    blocked_parser_injections: evidenceTotals.blockedParserInjections,
    case_id: journey.caseId,
    gate4_status: "approved",
    admin_trace: adminTrace,
    live_provider_smoke: { status: "deferred_by_policy" },
    pdf_upload_journey: fixtureSummary?.pdf_upload_journey ?? false,
    intake_mode: journey.intakeEvidence.intake_mode,
    prompt_selection_used: journey.intakeEvidence.prompt_selection_used,
    industry_selection_used: journey.intakeEvidence.industry_selection_used,
    intake_observed_from_dom: journey.intakeEvidence.observed_from_dom,
    selected_file_count: journey.intakeEvidence.selected_file_count,
    selected_file_mime_types: journey.intakeEvidence.selected_file_mime_types,
    upload_bytes: fixtureSummary?.bytes ?? null,
    upload_mime_type: fixtureSummary?.mime_type ?? null,
    upload_sha256: fixtureSummary?.sha256 ?? null,
    report_json_path: evidenceRelativePath(evidencePath, reportJsonPath),
    report_html_path: evidenceRelativePath(evidencePath, reportHtmlPath),
    report_pdf_path: evidenceRelativePath(evidencePath, reportPdfPath),
    report_metadata: {
      case_id: reportMetadata.case_id,
      snapshot_id: reportMetadata.snapshot_id,
      snapshot_hash: reportMetadata.snapshot_hash,
      snapshot_revision: reportMetadata.snapshot_revision,
    },
    report_artifact_hashes: reportArtifactHashes,
    startup_profile_fields: journey.profileFields,
    gtm_dimensions: journey.gtmDimensions,
    readiness_dimensions: journey.readinessDimensions,
    action_plan_items: journey.actionPlanItems,
    competitor_categories: journey.competitorCategories,
    competitor_rows: journey.competitorRows,
    diligence_questions: journey.diligenceQuestions,
    market_evidence_frozen: journey.marketEvidenceFrozen,
    market_unknowns_explicit: journey.marketUnknownsExplicit,
    chart_cards: journey.chartCards,
    chart_points: journey.chartPoints,
    screenshots: mobile
      ? {
          desktop: {
            path: evidenceRelativePath(evidencePath, desktop.outputPath),
            width: desktop.width,
            height: desktop.height,
          },
          mobile: {
            path: evidenceRelativePath(evidencePath, mobile.outputPath),
            width: mobile.width,
            height: mobile.height,
          },
        }
      : {
          desktop_states: {
            order: [...CANONICAL_DESKTOP_STATE_SCREENSHOTS],
            path: evidenceRelativePath(evidencePath, desktop.outputPath),
            viewport: { width: desktop.width, height: desktop.height },
          },
        },
  };
  writeFileSync(evidencePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  console.log(
    `founder_browser_evidence_written path=${evidencePath} case_id=${journey.caseId}`,
  );
}

function resolveCaseCopilotFixturePaths(fixturePath) {
  const defaultRoot = join(
    REPO_ROOT,
    "tests",
    "fixtures",
    "startup_case_copilot_v1",
    "cases",
  );
  const candidate = fixturePath ? resolve(fixturePath) : undefined;
  const caseRoot =
    candidate && basename(candidate) === "brief.txt"
      ? dirname(dirname(candidate))
      : defaultRoot;
  const fixtures = {
    idea_clinic: join(caseRoot, "idea_clinic", "brief.txt"),
    idea_inventory: join(caseRoot, "idea_inventory", "brief.txt"),
  };
  for (const [fixtureName, path] of Object.entries(fixtures)) {
    if (!existsSync(path)) {
      throw new Error(
        `case_copilot_fixture_missing fixture=${fixtureName} path=${path}`,
      );
    }
  }
  return fixtures;
}

async function evaluateBrowserJson(client, sessionId, expression) {
  const result = await client.send(
    "Runtime.evaluate",
    {
      awaitPromise: true,
      expression,
      returnByValue: true,
    },
    sessionId,
    120_000,
  );
  if (result.exceptionDetails) {
    throw new Error(
      `browser_context_exception ${JSON.stringify(result.exceptionDetails)}`,
    );
  }
  return JSON.parse(result.result.value);
}

export function selectVisibleCurrentCaseCopilotPanel(panels, previousCaseId) {
  const previous = String(previousCaseId ?? "").trim();
  return (
    Array.from(panels ?? []).find((candidate) => {
      const caseId = candidate?.getAttribute?.("data-case-id")?.trim() ?? "";
      return (
        caseId &&
        caseId !== previous &&
        Number(candidate?.getClientRects?.().length ?? 0) > 0 &&
        Boolean(candidate?.querySelector?.("[data-case-question-card]"))
      );
    }) ?? null
  );
}

export function caseCopilotResearchJobMutationProofFromEvent(event, sequence = 0) {
  const method = String(event?.method ?? "").toUpperCase();
  const status = Number(event?.status);
  const url = String(event?.url ?? "");
  if (method !== "POST" || status < 200 || status >= 300) return null;
  const match = url.match(
    /\/api\/startup\/cases\/([^/?#]+)\/research\/jobs(?:[/?#]|$)/u,
  );
  if (!match) return null;
  const encodedCaseId = match[1];
  let caseId = encodedCaseId;
  try {
    caseId = decodeURIComponent(encodedCaseId);
  } catch {
    caseId = encodedCaseId;
  }
  return {
    caseId,
    method,
    path: `/api/startup/cases/${encodedCaseId}/research/jobs`,
    sequence: Number.isSafeInteger(sequence) ? sequence : 0,
    status,
  };
}

export function collectCaseCopilotResearchJobMutationProof(events) {
  return Array.from(events ?? []).flatMap((event, index) => {
    const proof = caseCopilotResearchJobMutationProofFromEvent(event, index + 1);
    return proof ? [proof] : [];
  });
}

export function assertNoPreQueueResearchJobMutations(proofRecords, caseId) {
  const currentCaseId = String(caseId ?? "").trim();
  if (!currentCaseId) throw new Error("case_copilot_current_case_id_missing");
  const matches = Array.from(proofRecords ?? []).filter(
    (record) => record?.caseId === currentCaseId,
  );
  if (matches.length > 0) {
    throw new Error(
      `case_copilot_pre_queue_research_jobs_observed count=${matches.length}`,
    );
  }
  return true;
}

async function armCaseCopilotFetchDiagnostics(client, sessionId) {
  const armed = await evaluateValue(
    client,
    sessionId,
    `(() => {
      globalThis.__caseCopilotFetchEvents = [];
      globalThis.__caseCopilotApiSnapshots = {};
      globalThis.__caseCopilotResearchJobMutationProof = [];
      globalThis.__caseCopilotResearchJobMutationSequence = 0;
      if (!globalThis.__caseCopilotFetchOriginal) {
        globalThis.__caseCopilotFetchOriginal = globalThis.fetch.bind(globalThis);
        const caseCopilotResearchJobMutationProofFromEvent = ${caseCopilotResearchJobMutationProofFromEvent.toString()};
        const reportArtifactSuffix = (value) => {
          const text = String(value ?? "");
          const match = text.match(/\\/report\\/(?:json|html|pdf)(?:\\?|$)/u);
          return match ? match[0].replace(/\\?.*$/u, "") : null;
        };
        const summarizeCaseCopilotApiPayload = (url, payload) => {
          if (!payload || typeof payload !== "object") return null;
          if (/\\/report\\/snapshot(?:\\?|$)/u.test(url)) {
            return {
              caseId: payload.case_id ?? null,
              dataRevision: payload.data_revision ?? null,
              sectionCount: Array.isArray(payload.sections) ? payload.sections.length : null,
            };
          }
          if (/\\/report(?:\\?|$)/u.test(url)) {
            return {
              caseId: payload.case_id ?? null,
              freezeStatus: payload.freeze_status ?? null,
              htmlUrlSuffix: reportArtifactSuffix(payload.html_url),
              jsonUrlSuffix: reportArtifactSuffix(payload.json_url),
              pdfStatus: payload.pdf_status ?? null,
              pdfUrlSuffix: reportArtifactSuffix(payload.pdf_url),
              reportStatus: payload.report_status ?? null,
              snapshotHashPresent: typeof payload.snapshot_hash === "string" && payload.snapshot_hash.length > 0,
              snapshotRevision: payload.snapshot_revision ?? null,
            };
          }
          if (/\\/gate2\\/preview(?:\\?|$)/u.test(url)) {
            return {
              caseId: payload.case_id ?? null,
              gate2ResumeTokenPresent: Boolean(payload.resume_token),
              previewFieldCount: Object.keys(payload.preview ?? {}).length,
            };
          }
          if (/\\/profile(?:\\?|$)/u.test(url)) {
            const fields = Object.values(payload.fields ?? {});
            const sourceFactFields = fields.filter((field) =>
              field &&
              typeof field === "object" &&
              field.status === "source_fact" &&
              Array.isArray(field.values) &&
              field.values.length > 0 &&
              Array.isArray(field.evidence_refs) &&
              field.evidence_refs.length > 0
            );
            return {
              caseId: payload.case_id ?? null,
              dataRevision: payload.data_revision ?? null,
              profileFieldCount: fields.length,
              profileSourceFactCount: sourceFactFields.length,
            };
          }
          if (/\\/startup\\/cases\\/[^/]+(?:\\?|$)/u.test(url)) {
            return {
              caseId: payload.case_id ?? null,
              analysisStatus: payload.analysis_status ?? null,
              gate2Status: payload.gate2_status ?? null,
              gate3Status: payload.gate3_status ?? null,
              gate4Status: payload.gate4_status ?? null,
              reportStatus: payload.report_status ?? null,
              snapshotHashPresent: typeof payload.snapshot_hash === "string" && payload.snapshot_hash.length > 0,
              snapshotRevision: payload.snapshot_revision ?? null,
              workflowStatus: payload.workflow_status ?? null,
            };
          }
          return null;
        };
        globalThis.fetch = async (...args) => {
          const startedAt = Date.now();
          const input = args[0];
          const init = args[1] ?? {};
          const url = String(input?.url ?? input ?? "");
          const method = String(init?.method ?? input?.method ?? "GET").toUpperCase();
          try {
            const response = await globalThis.__caseCopilotFetchOriginal(...args);
            if (url.includes("/api/") && response.ok) {
              try {
                const body = await response.clone().text();
                const payload = body ? JSON.parse(body) : null;
                const snapshot = summarizeCaseCopilotApiPayload(url, payload);
                if (snapshot) {
                  globalThis.__caseCopilotApiSnapshots[url] = {
                    ...snapshot,
                    elapsed_ms: Date.now() - startedAt,
                    method,
                    status: response.status,
                  };
                }
              } catch {
                // Snapshot diagnostics are best-effort and must not affect the UI journey.
              }
              if (method !== "GET") {
                globalThis.__caseCopilotResearchJobMutationSequence += 1;
                const researchJobProof = caseCopilotResearchJobMutationProofFromEvent(
                  { method, status: response.status, url },
                  globalThis.__caseCopilotResearchJobMutationSequence,
                );
                if (researchJobProof) {
                  globalThis.__caseCopilotResearchJobMutationProof.push(researchJobProof);
                }
                globalThis.__caseCopilotFetchEvents.push({
                  body: "",
                  elapsed_ms: Date.now() - startedAt,
                  method,
                  status: response.status,
                  statusText: response.statusText,
                  url,
                });
                globalThis.__caseCopilotFetchEvents =
                  globalThis.__caseCopilotFetchEvents.slice(-50);
              }
            }
            if (url.includes("/api/") && !response.ok) {
              globalThis.__caseCopilotFetchEvents.push({
                body: "",
                elapsed_ms: Date.now() - startedAt,
                method,
                status: response.status,
                statusText: response.statusText,
                url,
              });
              globalThis.__caseCopilotFetchEvents =
                globalThis.__caseCopilotFetchEvents.slice(-50);
            }
            return response;
          } catch (error) {
            if (url.includes("/api/")) {
              globalThis.__caseCopilotFetchEvents.push({
                body: "",
                elapsed_ms: Date.now() - startedAt,
                method,
                status: null,
                statusText: "fetch_exception",
                url,
              });
              globalThis.__caseCopilotFetchEvents =
                globalThis.__caseCopilotFetchEvents.slice(-50);
            }
            throw error;
          }
        };
      }
      return true;
    })()`,
  );
  if (!armed) throw new Error("case_copilot_fetch_diagnostics_not_armed");
}

async function collectCaseCopilotScenarioFixtureUiEvidence(
  client,
  sessionId,
  fixtureName,
  fixturePath,
) {
  await waitForExpression(
    client,
    sessionId,
    `Boolean(document.querySelector(".founder-dashboard-shell"))`,
    "case_copilot_ui_shell_ready",
    60_000,
  );

  await armCaseCopilotFetchDiagnostics(client, sessionId);

  async function buttonByText(label, waitLabel = `case_copilot_button_${label}`) {
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const expected = ${JSON.stringify(label)};
        const button = Array.from(document.querySelectorAll("button"))
          .find((candidate) => candidate.textContent?.replace(/\\s+/gu, " ").trim().includes(expected));
        return Boolean(button && !button.disabled && button.getClientRects().length > 0);
      })()`,
      waitLabel,
      120_000,
    );
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const expected = ${JSON.stringify(label)};
        const button = Array.from(document.querySelectorAll("button"))
          .find((candidate) => candidate.textContent?.replace(/\\s+/gu, " ").trim().includes(expected));
        if (!button || button.disabled) return false;
        button.click();
        return true;
      })()`,
    );
  }

  function caseCopilotPanelByCaseId(caseId) {
    return `Array.from(document.querySelectorAll("[data-case-copilot-panel][data-case-id]"))
      .find((panel) => panel?.getAttribute("data-case-id") === ${JSON.stringify(caseId)} &&
        panel.getClientRects().length > 0)`;
  }

  async function readVisibleCaseCopilotPanelCaseId() {
    return evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = Array.from(document.querySelectorAll("[data-case-copilot-panel][data-case-id]"))
          .find((candidate) => candidate.getClientRects().length > 0);
        return panel?.getAttribute("data-case-id")?.trim() ?? "";
      })()`,
    );
  }

  async function waitForCurrentCaseCopilotPanel(previousCaseId) {
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const previousCaseId = ${JSON.stringify(previousCaseId)};
        const selectVisibleCurrentCaseCopilotPanel = ${selectVisibleCurrentCaseCopilotPanel.toString()};
        const panel = selectVisibleCurrentCaseCopilotPanel(
          document.querySelectorAll("[data-case-copilot-panel][data-case-id]"),
          previousCaseId,
        );
        return Boolean(panel);
      })()`,
      "case_copilot_current_question_card_visible",
      120_000,
    );
  }

  async function readCurrentCaseCopilotPanelCaseId(previousCaseId) {
    return evaluateValue(
      client,
      sessionId,
      `(() => {
        const previousCaseId = ${JSON.stringify(previousCaseId)};
        const selectVisibleCurrentCaseCopilotPanel = ${selectVisibleCurrentCaseCopilotPanel.toString()};
        const panel = selectVisibleCurrentCaseCopilotPanel(
          document.querySelectorAll("[data-case-copilot-panel][data-case-id]"),
          previousCaseId,
        );
        return panel?.getAttribute("data-case-id")?.trim() ?? "";
      })()`,
    );
  }

  async function clickCaseCopilotAnswerTab(caseId, label) {
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const panel = ${caseCopilotPanelByCaseId(caseId)};
        const card = panel?.querySelector("[data-case-question-card]");
        const button = Array.from(card?.querySelectorAll("button") ?? [])
          .find((candidate) => candidate.textContent?.trim() === ${JSON.stringify(label)});
        return Boolean(button && !button.disabled && button.getClientRects().length > 0);
      })()`,
      `case_copilot_answer_tab_${label}`,
      120_000,
    );
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = ${caseCopilotPanelByCaseId(caseId)};
        const card = panel?.querySelector("[data-case-question-card]");
        const button = Array.from(card?.querySelectorAll("button") ?? [])
          .find((candidate) => candidate.textContent?.trim() === ${JSON.stringify(label)});
        button?.click();
        return true;
      })()`,
    );
  }

  async function setInputByLabel(caseId, label, value) {
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const panel = ${caseCopilotPanelByCaseId(caseId)};
        const expected = ${JSON.stringify(label)};
        const labels = Array.from(panel?.querySelectorAll("label") ?? []);
        const field = labels.find((candidate) => candidate.textContent?.includes(expected));
        return Boolean(field?.querySelector("input, select"));
      })()`,
      `case_copilot_input_${label}`,
      30_000,
    );
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = ${caseCopilotPanelByCaseId(caseId)};
        const expected = ${JSON.stringify(label)};
        const value = ${JSON.stringify(value)};
        const labels = Array.from(panel?.querySelectorAll("label") ?? []);
        const field = labels.find((candidate) => candidate.textContent?.includes(expected));
        const input = field?.querySelector("input, select");
        if (!input) return false;
        const prototype = input instanceof HTMLSelectElement
          ? HTMLSelectElement.prototype
          : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
        setter?.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      })()`,
    );
  }

  async function buttonByTextInCasePanel(caseId, label, waitLabel = `case_copilot_button_${label}`) {
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const panel = ${caseCopilotPanelByCaseId(caseId)};
        const expected = ${JSON.stringify(label)};
        const button = Array.from(panel?.querySelectorAll("button") ?? [])
          .find((candidate) => candidate.textContent?.replace(/\\s+/gu, " ").trim().includes(expected));
        return Boolean(button && !button.disabled && button.getClientRects().length > 0);
      })()`,
      waitLabel,
      120_000,
    );
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = ${caseCopilotPanelByCaseId(caseId)};
        const expected = ${JSON.stringify(label)};
        const button = Array.from(panel?.querySelectorAll("button") ?? [])
          .find((candidate) => candidate.textContent?.replace(/\\s+/gu, " ").trim().includes(expected));
        if (!button || button.disabled) return false;
        button.click();
        return true;
      })()`,
    );
  }

  async function requestCaseCopilotState(caseId) {
    if (!caseId) throw new Error("case_copilot_current_case_id_missing");
    return evaluateBrowserJson(
      client,
      sessionId,
      `(${async function readCaseCopilotState(caseId) {
        if (!caseId) throw new Error("case_copilot_current_case_id_missing");
        const response = await fetch(
          `/api/startup/cases/${encodeURIComponent(caseId)}/copilot/state`,
          {
            cache: "no-store",
            credentials: "same-origin",
            headers: { Accept: "application/json" },
          },
        );
        if (!response.ok) {
          throw new Error(
            `case_copilot_browser_request_failed path=copilot/state status=${response.status}`,
          );
        }
        return response.json();
      }} )(${JSON.stringify(caseId)}).then((value) => JSON.stringify(value))`,
    );
  }

  async function successfulCaseCopilotMutationEvents(caseId, pathFragment) {
    if (!caseId) throw new Error("case_copilot_current_case_id_missing");
    return evaluateBrowserJson(
      client,
      sessionId,
      `(() => {
        const caseId = ${JSON.stringify(caseId)};
        const pathFragment = ${JSON.stringify(pathFragment)};
        const proof = Array.from(globalThis.__caseCopilotResearchJobMutationProof ?? []);
        return JSON.stringify(proof
          .filter((event) =>
            event &&
            event.caseId === caseId &&
            String(event.path ?? "").includes(pathFragment)
          )
          .map((event) => ({
            caseId: event.caseId,
            method: event.method,
            path: event.path,
            sequence: event.sequence,
            status: event.status,
          })));
      })()`,
    );
  }

  const previousCaseId = await readVisibleCaseCopilotPanelCaseId();
  await buttonByText("Новый анализ", "case_copilot_open_data_room");
  await waitForExpression(
    client,
    sessionId,
    `Boolean(document.querySelector('[data-founder-view="data-room"] input[type="file"]'))`,
    "case_copilot_file_input_visible",
    30_000,
  );
  await client.send("DOM.enable", {}, sessionId);
  const { root } = await client.send("DOM.getDocument", {}, sessionId);
  const { nodeId } = await client.send(
    "DOM.querySelector",
    { nodeId: root.nodeId, selector: '[data-founder-view="data-room"] input[type="file"]' },
    sessionId,
  );
  if (!nodeId) throw new Error("case_copilot_file_input_missing");
  await client.send(
    "DOM.setFileInputFiles",
    { files: [resolve(fixturePath)], nodeId },
    sessionId,
  );
  await evaluateValue(
    client,
    sessionId,
    `(() => {
      const input = document.querySelector('[data-founder-view="data-room"] input[type="file"]')
        ?? document.querySelector('input[type="file"]');
      if (!input) return false;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return input.files?.length === 1;
    })()`,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const dataRoom = document.querySelector('[data-founder-view="data-room"]');
      const text = dataRoom?.textContent ?? "";
      return text.includes("файл(а) выбрано") && text.includes("brief.txt");
    })()`,
    "case_copilot_file_uploaded_visible",
    30_000,
  );
  await buttonByText("Начать анализ", "case_copilot_start_analysis");
  const caseCopilotGate2Action = "gate2-approve";
  await waitForExpression(
    client,
    sessionId,
    actionSelectorExpression(caseCopilotGate2Action, "ready"),
    "case_copilot_gate2_ready",
    300_000,
  );
  await evaluateValue(
    client,
    sessionId,
    actionSelectorExpression(caseCopilotGate2Action, "click"),
  );
  await waitForCurrentCaseCopilotPanel(previousCaseId);
  const currentCaseId = await readCurrentCaseCopilotPanelCaseId(previousCaseId);
  if (!currentCaseId) throw new Error("case_copilot_current_case_id_missing");
  await clickCaseCopilotAnswerTab(currentCaseId, "Manual");
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${caseCopilotPanelByCaseId(currentCaseId)};
      const card = panel?.querySelector("[data-case-question-card]");
      const manualFieldKey = card?.querySelector("[data-case-copilot-manual-field-key]");
      return Boolean(
        manualFieldKey?.textContent?.includes("Structured founder statement") &&
          manualFieldKey?.getAttribute("data-case-copilot-manual-field-key")?.trim()
      );
    })()`,
    "case_copilot_structured_founder_statement_visible",
    30_000,
  );
  await setInputByLabel(currentCaseId, "Amount", "1850000");
  await setInputByLabel(currentCaseId, "Scale", "ones");
  await setInputByLabel(currentCaseId, "Currency", "KZT");
  await setInputByLabel(currentCaseId, "Period month", "2026-07");
  await setInputByLabel(currentCaseId, "Declared source", "founder interview");
  await setInputByLabel(currentCaseId, "Rationale", "planning input");
  await setInputByLabel(currentCaseId, "Validation plan", "verify against CRM/finance");
  await buttonByTextInCasePanel(currentCaseId, "Save answer", "case_copilot_save_manual_answer");
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${caseCopilotPanelByCaseId(currentCaseId)};
      return Array.from(panel?.querySelectorAll("[data-role]") ?? []).some((message) =>
        message.textContent?.includes("Saved founder_statement")
      );
    })()`,
    "case_copilot_founder_statement_saved",
    120_000,
  );
  await clickCaseCopilotAnswerTab(currentCaseId, "Unknown");
  await buttonByTextInCasePanel(currentCaseId, "Reply unknown", "case_copilot_save_unknown");
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${caseCopilotPanelByCaseId(currentCaseId)};
      return Array.from(panel?.querySelectorAll("[data-role]") ?? []).some((message) =>
        message.textContent?.toLowerCase().includes("unknown")
      );
    })()`,
    "case_copilot_unknown_visible_in_thread",
    120_000,
  );
  await clickCaseCopilotAnswerTab(currentCaseId, "Public research");
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${caseCopilotPanelByCaseId(currentCaseId)};
      const checkbox = panel?.querySelector('[data-case-question-card] input[type="checkbox"]');
      return Boolean(checkbox && !checkbox.disabled);
    })()`,
    "case_copilot_public_research_consent_checkbox",
    120_000,
  );
  await evaluateValue(
    client,
    sessionId,
    `(() => {
      const panel = ${caseCopilotPanelByCaseId(currentCaseId)};
      const checkbox = panel?.querySelector('[data-case-question-card] input[type="checkbox"]');
      if (!checkbox) return false;
      checkbox.click();
      return checkbox.checked;
    })()`,
  );
  const preResearchState = await requestCaseCopilotState(currentCaseId);
  const preQueueResearchJobPosts = await successfulCaseCopilotMutationEvents(currentCaseId, "/research/jobs");
  const providerCallsZeroBeforeQueue = assertNoPreQueueResearchJobMutations(
    preQueueResearchJobPosts,
    currentCaseId,
  );
  await buttonByTextInCasePanel(currentCaseId, "Prepare research", "case_copilot_prepare_research");
  await waitForExpression(
    client,
    sessionId,
    `Boolean(${caseCopilotPanelByCaseId(currentCaseId)}?.querySelector('[data-case-copilot-research-status] [data-research-job-status]'))`,
    "case_copilot_research_status_visible",
    120_000,
  );
  const postQueueResearchJobPosts = await successfulCaseCopilotMutationEvents(currentCaseId, "/research/jobs");
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${caseCopilotPanelByCaseId(currentCaseId)};
      const metrics = panel?.querySelector("[data-founder-scenario-metrics]");
      return Boolean(metrics) &&
        Array.from(metrics.querySelectorAll("button"))
          .filter((button) => ["Conservative", "Base", "Optimistic"].includes(button.textContent?.trim() ?? "")).length === 3;
    })()`,
    "case_copilot_scenario_selector_visible",
    120_000,
  );
  await buttonByTextInCasePanel(currentCaseId, "Conservative", "case_copilot_select_conservative");
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${caseCopilotPanelByCaseId(currentCaseId)};
      const button = Array.from(panel?.querySelectorAll("[data-founder-scenario-metrics] button") ?? [])
        .find((candidate) => candidate.textContent?.trim() === "Conservative");
      return button?.getAttribute("aria-pressed") === "true";
    })()`,
    "case_copilot_conservative_selected",
    120_000,
  );
  await buttonByTextInCasePanel(currentCaseId, "Base", "case_copilot_select_base");
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${caseCopilotPanelByCaseId(currentCaseId)};
      const button = Array.from(panel?.querySelectorAll("[data-founder-scenario-metrics] button") ?? [])
        .find((candidate) => candidate.textContent?.trim() === "Base");
      return button?.getAttribute("aria-pressed") === "true";
    })()`,
    "case_copilot_base_selected",
    120_000,
  );
  await buttonByText("План действий", "case_copilot_open_action_plan");
  await buttonByText("Собрать рабочий пакет", "case_copilot_generate_launch_pack");
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const currentCaseAssetPrefix = ${JSON.stringify(`/api/startup/cases/${encodeURIComponent(currentCaseId)}/assets/`)};
      const links = Array.from(document.querySelectorAll('[data-founder-launch-pack="draft"] a[href]'));
      return Boolean(links.find((link) =>
        (link.getAttribute("href") ?? "").includes(currentCaseAssetPrefix) &&
        (link.getAttribute("href") ?? "").endsWith("/markdown")
      )) && Boolean(links.find((link) =>
        (link.getAttribute("href") ?? "").includes(currentCaseAssetPrefix) &&
        (link.getAttribute("href") ?? "").endsWith("/provenance")
      ));
    })()`,
    "case_copilot_launch_pack_visible",
    120_000,
  );

  const apiEvidence = await evaluateBrowserJson(
    client,
    sessionId,
    `(${async function collectCaseCopilotUiAssertions(args) {
      async function requestJson(path, init = {}) {
        const response = await fetch(path, {
          cache: "no-store",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            ...(init.headers ?? {}),
          },
          ...init,
        });
        if (!response.ok) {
          throw new Error(
            `case_copilot_browser_request_failed path=${path} status=${response.status}`,
          );
        }
        return response.json();
      }
      async function requestText(path) {
        const response = await fetch(path, {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(
            `case_copilot_browser_download_failed path=${path} status=${response.status}`,
          );
        }
        return {
          content_disposition: response.headers.get("content-disposition"),
          text: await response.text(),
        };
      }
      async function requestCaseCopilotState(caseId) {
        return requestJson(
          `/api/startup/cases/${encodeURIComponent(caseId)}/copilot/state`,
        );
      }
      function caseCopilotPanelByCaseId(caseId) {
        return Array.from(document.querySelectorAll("[data-case-copilot-panel][data-case-id]"))
          .find((panel) =>
            panel?.getAttribute("data-case-id") === caseId &&
            panel.getClientRects().length > 0
          );
      }
      function metricDisclosure(metric) {
        return Boolean(
          metric &&
            typeof metric.provenance === "string" &&
            ((metric.value_range && typeof metric.value_range === "object") ||
              (metric.value_range === null &&
                Array.isArray(metric.gaps) &&
                metric.gaps.length > 0)) &&
            typeof metric.formula_key === "string" &&
            typeof metric.formula_description === "string" &&
            Array.isArray(metric.dependency_refs) &&
            Array.isArray(metric.source_refs) &&
            typeof metric.validation_plan === "string" &&
            metric.validation_plan.trim(),
        );
      }
      function scenarioDisclosure(scenarios) {
        const variants = scenarios.scenarios ?? {};
        const allMetrics = Object.values(variants).flatMap((variant) =>
          Object.values(variant.metrics ?? {}),
        );
        const base = variants.base ?? {};
        const conservative = variants.conservative ?? {};
        const optimistic = variants.optimistic ?? {};
        const baseMetrics = JSON.stringify(base.metrics ?? {});
        const baseInputs = JSON.stringify(base.inputs ?? {});
        const conservativeInputs = JSON.stringify(conservative.inputs ?? {});
        const optimisticInputs = JSON.stringify(optimistic.inputs ?? {});
        const scenarioKeys = ["conservative", "base", "optimistic"];
        return {
          action_delta:
            baseInputs !== conservativeInputs || baseInputs !== optimisticInputs,
          metric_delta:
            baseMetrics !== JSON.stringify(conservative.metrics ?? {}) ||
            baseMetrics !== JSON.stringify(optimistic.metrics ?? {}),
          metric_disclosure_complete:
            allMetrics.length > 0 && allMetrics.every(metricDisclosure),
          readiness_delta:
            scenarioKeys.every((key) => variants[key]?.inputs && variants[key]?.metrics) &&
            (baseInputs !== conservativeInputs || baseMetrics !== JSON.stringify(optimistic.metrics ?? {})),
          risk_delta:
            scenarioKeys.every((key) => variants[key]?.gaps && typeof variants[key].gaps === "object"),
        };
      }

      const caseId = args.currentCaseId;
      if (!caseId) throw new Error("case_copilot_current_case_id_missing");
      const panel = caseCopilotPanelByCaseId(caseId);
      if (!panel) throw new Error("case_copilot_visible_ui_state_missing");
      const preResearchState = args.preResearchState ?? {};
      const stateAfterResearch = await requestCaseCopilotState(caseId);
      const researchStatus = panel.querySelector("[data-case-copilot-research-status]");
      const planId = researchStatus?.querySelector("[data-research-plan-id]")?.getAttribute("data-research-plan-id");
      const jobNode = researchStatus?.querySelector("[data-research-job-id]");
      const jobId = jobNode?.getAttribute("data-research-job-id");
      const jobStatus = jobNode?.getAttribute("data-research-job-status");
      if (!planId || !jobId || !jobStatus) throw new Error("case_copilot_research_status_not_visible");
      const job = await requestJson(
        `/api/startup/cases/${encodeURIComponent(caseId)}/research/jobs/${encodeURIComponent(jobId)}`,
      );
      const scenarios = await requestJson(
        `/api/startup/cases/${encodeURIComponent(caseId)}/scenarios`,
      );
      const scenarioKeys = ["conservative", "base", "optimistic"].filter(
        (key) => key in scenarios.scenarios,
      );
      const disclosure = scenarioDisclosure(scenarios);
      const selectedState = await requestJson(
        `/api/startup/cases/${encodeURIComponent(caseId)}/copilot/state`,
      );
      const selectedThread = await requestJson(
        `/api/startup/cases/${encodeURIComponent(caseId)}/copilot/thread`,
      );
      const currentProfile = await requestJson(
        `/api/startup/cases/${encodeURIComponent(caseId)}/profile`,
      );
      const currentProfileHasFounderStatementSourceFact = Object.values(
        currentProfile.fields ?? {},
      ).some(
        (field) =>
          field &&
          typeof field === "object" &&
          field.status === "source_fact" &&
          Array.isArray(field.values) &&
          field.values.some((value) => String(value).includes("1850000")),
      );
      const currentCaseAssetPrefix = `/api/startup/cases/${encodeURIComponent(caseId)}/assets/`;
      const launchPackLinks = Array.from(document.querySelectorAll('[data-founder-launch-pack="draft"] a[href]'));
      const markdownLink = launchPackLinks.find((link) => {
        const href = link.getAttribute("href") ?? "";
        return href.includes(currentCaseAssetPrefix) && href.endsWith("/markdown");
      });
      const provenanceLink = launchPackLinks.find((link) => {
        const href = link.getAttribute("href") ?? "";
        return href.includes(currentCaseAssetPrefix) && href.endsWith("/provenance");
      });
      const assetMatch = markdownLink?.getAttribute("href")?.match(/\/assets\/([^/]+)\/markdown$/u);
      const assetId = assetMatch?.[1] ?? "";
      if (!assetId || !provenanceLink) throw new Error("case_copilot_launch_pack_current_case_missing");
      const asset = await requestJson(
        `/api/startup/cases/${encodeURIComponent(caseId)}/assets/${encodeURIComponent(assetId)}`,
      );
      const markdown = await requestText(asset.markdown_url);
      const provenance = await requestText(asset.provenance_appendix_url);
      markdownLink?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));

      return {
        base_inputs_fingerprint: JSON.stringify(
          scenarios.scenarios.base?.metrics ?? {},
        ),
        case_id: caseId,
        fixture_name: args.fixtureName,
        founder_statement_accepted: selectedState.accepted_inputs.some(
          (item) =>
            item.kind === "founder_statement" &&
            String(item.value).includes("1850000") &&
            item.period === "2026-07" &&
            item.declared_source === "founder interview",
        ),
        final_screenshot_state: {
          case_copilot_panel_visible: Boolean(panel?.getClientRects().length),
          populated_same_case_ui:
            Boolean(panel?.getAttribute("data-case-id") === caseId) &&
            Boolean(assetId) &&
            scenarios.selected_scenario_key === "base" &&
            Boolean(panel.querySelector("[data-founder-scenario-metrics]")),
        },
        launch_pack: {
          asset_id: asset.asset_id,
          downloaded:
            markdown.content_disposition?.includes("attachment") === true &&
            markdown.text.length > 0,
          provenance_appendix:
            provenance.text.includes("validation=") &&
            provenance.text.includes("source_refs="),
          versioned: Number(asset.asset_revision) >= 1,
        },
        public_focus:
          job.accepted_entries?.[0]?.input_key ??
          stateAfterResearch.prioritized_gaps?.[0]?.field_key ??
          "public_benchmark",
        question_text: preResearchState.next_question,
        question_visible: Boolean(preResearchState.next_question),
        research: {
          citations: job.citations ?? [],
          explicit_consent: true,
          job_status: job.status,
          no_source_fact_promotion:
            selectedState.accepted_inputs.some((item) => item.kind === "founder_statement") &&
            !currentProfileHasFounderStatementSourceFact,
          plan_prepared: Boolean(planId),
          pre_research_state: {
            accepted_input_kinds: Array.isArray(preResearchState.accepted_inputs)
              ? preResearchState.accepted_inputs.map((item) => item?.kind ?? item?.provenance ?? null)
              : [],
            next_question: preResearchState.next_question ?? null,
            research_job_posts_before_queue: args.preQueueResearchJobPosts ?? [],
            stage: preResearchState.stage ?? null,
          },
          research_job_posts_after_queue: args.postQueueResearchJobPosts ?? [],
          provider_calls_zero_before_queue: args.providerCallsZeroBeforeQueue === true,
          source_refs:
            job.accepted_entries?.flatMap((entry) => entry.source_refs ?? []) ??
            [],
        },
        restart: {
          process_restarted: false,
          same_asset_reloaded: false,
          same_case_reloaded: false,
          same_scenario_reloaded: false,
        },
        scenarios: {
          ...disclosure,
          scenario_keys: scenarioKeys,
          selected_key: scenarios.selected_scenario_key,
        },
        text_brief_uploaded: true,
        ui_interactions: [
          "file_upload",
          "start_analysis",
          "gate2_approve",
          "manual_founder_statement",
          "unknown_answer",
          "public_research_consent",
          "scenario_select_base",
          "launch_pack_generate",
          "launch_pack_download",
        ],
        unknown_answer_recorded: selectedThread.messages.some(
          (message) =>
            message.role === "user" &&
            message.content?.toLowerCase() === "unknown",
        ),
        visible_state: {
          file_uploaded: true,
          launch_pack_visible: Boolean(assetId),
          question_card_visible: Boolean(panel.querySelector("[data-case-question-card]")),
          research_status_visible: Boolean(panel.querySelector("[data-case-copilot-research-status]")),
          scenario_metrics_visible: Boolean(panel.querySelector("[data-founder-scenario-metrics]")),
        },
      };
    }})( ${JSON.stringify({
      currentCaseId,
      fixtureName,
      postQueueResearchJobPosts,
      preQueueResearchJobPosts,
      preResearchState,
      providerCallsZeroBeforeQueue,
    })} ).then((value) => JSON.stringify(value))`,
  );
  if (!apiEvidence?.final_screenshot_state?.populated_same_case_ui) {
    throw new Error("case_copilot_visible_ui_state_missing");
  }
  return apiEvidence;
}

function caseCopilotRestartToken(fixtures) {
  return createHash("sha256")
    .update(fixtures.map((fixture) => `${fixture.fixture_name}:${fixture.case_id}:${fixture.launch_pack.asset_id}`).join("|"))
    .digest("hex")
    .slice(0, 16);
}

async function requestCaseCopilotServiceRestart(restartRequestPath, token, fixtures) {
  if (!restartRequestPath) {
    throw new Error("case_copilot_restart_request_path_missing");
  }
  mkdirSync(dirname(restartRequestPath), { recursive: true });
  writeFileSync(
    restartRequestPath,
    `${JSON.stringify({
      requested_at: new Date().toISOString(),
      token,
      cases: fixtures.map((fixture) => ({
        asset_id: fixture.launch_pack.asset_id,
        case_id: fixture.case_id,
        fixture_name: fixture.fixture_name,
        selected_scenario_key: fixture.scenarios.selected_key,
      })),
    }, null, 2)}\n`,
    "utf8",
  );
  console.log(`case_copilot_browser_restart_requested path=${restartRequestPath} token=${token}`);
}

export function parseCaseCopilotRestartReadyPayload(restartReadyPath) {
  const payload = readFileSync(restartReadyPath, "utf8");
  return JSON.parse(payload.startsWith("\uFEFF") ? payload.slice(1) : payload);
}

async function waitForCaseCopilotRestartReady(restartReadyPath, token) {
  if (!restartReadyPath) {
    throw new Error("case_copilot_restart_ready_path_missing");
  }
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    if (existsSync(restartReadyPath)) {
      const ready = parseCaseCopilotRestartReadyPayload(restartReadyPath);
      if (ready.token === token && ready.status === "ready") {
        console.log(`case_copilot_browser_restart_ready path=${restartReadyPath} token=${token}`);
        return ready;
      }
    }
    await sleep(250);
  }
  throw new Error(`case_copilot_restart_ready_timeout path=${restartReadyPath}`);
}

async function collectCaseCopilotPostRestartEvidence(client, sessionId, fixtures, restartReady) {
  const postRestart = await evaluateBrowserJson(
    client,
    sessionId,
    `(${async function collectPostRestart(args) {
      async function requestJson(path) {
        const response = await fetch(path, {
          cache: "no-store",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(
            `case_copilot_post_restart_request_failed path=${path} status=${response.status}`,
          );
        }
        return response.json();
      }
      const result = {};
      for (const fixture of args.fixtures) {
        const caseId = fixture.case_id;
        const [thread, scenarios, asset] = await Promise.all([
          requestJson(`/api/startup/cases/${encodeURIComponent(caseId)}/copilot/thread`),
          requestJson(`/api/startup/cases/${encodeURIComponent(caseId)}/scenarios`),
          requestJson(`/api/startup/cases/${encodeURIComponent(caseId)}/assets/${encodeURIComponent(fixture.launch_pack.asset_id)}`),
        ]);
        result[fixture.fixture_name] = {
          same_asset_reloaded: asset.asset_id === fixture.launch_pack.asset_id,
          same_case_reloaded: thread.case_id === caseId,
          same_scenario_reloaded: scenarios.selected_scenario_key === fixture.scenarios.selected_key,
        };
      }
      return result;
    }})( ${JSON.stringify({ fixtures })} ).then((value) => JSON.stringify(value))`,
  );
  return fixtures.map((fixture) => ({
    ...fixture,
    restart: {
      process_restarted: restartReady.status === "ready",
      ...(postRestart[fixture.fixture_name] ?? {}),
    },
    final_screenshot_state: {
      ...fixture.final_screenshot_state,
      populated_same_case_ui:
        fixture.final_screenshot_state.populated_same_case_ui &&
        postRestart[fixture.fixture_name]?.same_case_reloaded === true,
    },
  }));
}

function buildCaseCopilotScenarioJourney(fixtures) {
  const [inventory, clinic] = fixtures;
  return {
    caseCopilotScenarioJourney: {
      cross_fixture: {
        base_inputs_differ:
          inventory.base_inputs_fingerprint !== clinic.base_inputs_fingerprint,
        benchmark_scopes_differ: inventory.public_focus !== clinic.public_focus,
        questions_differ: inventory.question_text !== clinic.question_text,
      },
      fixtures: fixtures.map(
        ({
          base_inputs_fingerprint: _baseInputsFingerprint,
          public_focus: _publicFocus,
          question_text: _questionText,
          ...fixture
        }) => fixture,
      ),
    },
  };
}

async function driveCaseCopilotScenarioJourney(
  client,
  sessionId,
  fixturePath,
  caseCopilotRestartRequestPath,
  caseCopilotRestartReadyPath,
  captureCaseCopilotPreRestartScreenshot,
) {
  await waitForExpression(
    client,
    sessionId,
    "document.readyState === 'complete'",
    "case_copilot_browser_shell_ready",
    60_000,
  );
  const fixturePaths = resolveCaseCopilotFixturePaths(fixturePath);
  const fixtures = [];
  for (const fixtureName of ["idea_inventory", "idea_clinic"]) {
    fixtures.push(
      await collectCaseCopilotScenarioFixtureUiEvidence(
        client,
        sessionId,
        fixtureName,
        fixturePaths[fixtureName],
      ),
    );
  }
  await captureCaseCopilotPreRestartScreenshot(
    buildCaseCopilotScenarioJourney(fixtures),
  );
  const restartToken = caseCopilotRestartToken(fixtures);
  await requestCaseCopilotServiceRestart(
    caseCopilotRestartRequestPath,
    restartToken,
    fixtures,
  );
  const restartReady = await waitForCaseCopilotRestartReady(
    caseCopilotRestartReadyPath,
    restartToken,
  );
  const restartedFixtures = await collectCaseCopilotPostRestartEvidence(
    client,
    sessionId,
    fixtures,
    restartReady,
  );
  return buildCaseCopilotScenarioJourney(restartedFixtures);
}

function smartUniversityButtonExpression(labels, action) {
  const expectedLabels = JSON.stringify(Array.from(labels));
  return `(() => {
    const labels = ${expectedLabels};
    const button = Array.from(document.querySelectorAll("button"))
      .find((candidate) =>
        labels.some((label) =>
          candidate.textContent?.replace(/\\s+/gu, " ").trim().includes(label),
        ),
      );
    if (!button || button.disabled || button.getClientRects().length === 0) return false;
    ${action === "click" ? "button.click();" : ""}
    return true;
  })()`;
}

function materializeBrowserUploadPath(fixturePath) {
  const uploadDirectory = mkdtempSync(join(tmpdir(), "founder-browser-upload-"));
  const uploadPath = join(uploadDirectory, "owner-upload.pdf");
  copyFileSync(resolve(fixturePath), uploadPath);
  return {
    path: uploadPath,
    cleanup() {
      rmSync(uploadDirectory, { force: true, recursive: true });
    },
  };
}

function collectJsonlPaths(root, paths = []) {
  if (!root || !existsSync(root) || paths.length >= 80) return paths;
  let entries = [];
  try {
    entries = readdirSync(root, { withFileTypes: true });
  } catch {
    return paths;
  }
  for (const entry of entries) {
    if (paths.length >= 80) break;
    const entryPath = join(root, entry.name);
    if (entry.isDirectory()) {
      collectJsonlPaths(entryPath, paths);
    } else if (entry.isFile() && entry.name.endsWith(".jsonl")) {
      paths.push(entryPath);
    }
  }
  return paths;
}

function readJsonlTail(path, maxBytes = 1_000_000) {
  const stat = statSync(path);
  const bytesToRead = Math.min(stat.size, maxBytes);
  const buffer = Buffer.alloc(bytesToRead);
  const fd = openSync(path, "r");
  try {
    readSync(fd, buffer, 0, bytesToRead, Math.max(0, stat.size - bytesToRead));
  } finally {
    closeSync(fd);
  }
  const text = buffer.toString("utf8");
  if (bytesToRead >= stat.size) {
    return text;
  }
  const firstLineBreak = text.search(/\r?\n/u);
  return firstLineBreak >= 0 ? text.slice(firstLineBreak + 1) : text;
}

function founderSafeTraceMetadataValue(value) {
  const text = String(value ?? "");
  return /^[a-z0-9_.:-]{1,80}$/u.test(text) ? text : undefined;
}

export function collectSmartUniversityLiveAuditEvidence(
  auditSpoolRoot,
  caseId,
  researchJobId,
) {
  if (!auditSpoolRoot || !caseId || !researchJobId) return {};
  const paths = collectJsonlPaths(auditSpoolRoot)
    .map((path) => {
      try {
        return { path, mtimeMs: statSync(path).mtimeMs };
      } catch {
        return { path, mtimeMs: 0 };
      }
    })
    .sort((left, right) => right.mtimeMs - left.mtimeMs)
    .slice(0, 40)
    .map((entry) => entry.path);
  const events = [];
  for (const path of paths) {
    let text = "";
    try {
      text = readJsonlTail(path);
    } catch {
      continue;
    }
    for (const line of text.split(/\r?\n/u).slice(-200)) {
      if (!line.trim()) continue;
      try {
        const event = JSON.parse(line);
        const attributes = event?.attributes ?? {};
        const eventCaseId = String(attributes.case_id ?? event?.correlation_id ?? "");
        if (![String(caseId), `case-${String(caseId)}`].includes(eventCaseId)) continue;
        events.push(event);
      } catch {
        continue;
      }
    }
  }
  const newestMatchingEvent = (predicate) =>
    events
      .filter(predicate)
      .sort(
        (left, right) =>
          Date.parse(String(right?.timestamp_utc ?? "")) -
          Date.parse(String(left?.timestamp_utc ?? "")),
      )[0];
  const providerEvent = newestMatchingEvent(
    (event) =>
      event?.span_name === "startup.public_research" &&
      event?.attributes?.provider === "openai" &&
      String(event?.attributes?.request_id ?? "") === String(researchJobId) &&
      event?.attributes?.research_label === "live_public_research" &&
      event?.attributes?.tool_call_observed === true &&
      ["completed", "partial"].includes(String(event?.attributes?.status ?? "")),
  );
  if (!providerEvent) return {};
  const langsmithEvent = newestMatchingEvent(
    (event) =>
      event?.event_type === "observability.langsmith_status" &&
      event?.attributes?.exporter_provider === "langsmith",
  );
  const providerAttributes = providerEvent?.attributes ?? {};
  const latency = Number(providerAttributes.latency_ms);
  const sourceCount = Number(providerAttributes.source_count);
  const tool = providerAttributes.tool === "web_search" ? "web_search" : undefined;
  const toolCallObserved = providerAttributes.tool_call_observed === true;
  const usageObserved = ["input_tokens", "output_tokens", "total_tokens"].some((key) =>
    Number.isInteger(Number(providerAttributes[key])) && Number(providerAttributes[key]) > 0,
  );
  const langsmithStatus = String(langsmithEvent?.attributes?.status ?? "missing");
  const langsmithHasFailureMetadata = !["healthy", "ok", "exported"].includes(
    langsmithStatus,
  );
  const langsmithFallbackUsed = langsmithHasFailureMetadata
    ? founderSafeTraceMetadataValue(langsmithEvent?.attributes?.fallback_used)
    : undefined;
  const langsmithErrorCode = langsmithHasFailureMetadata
    ? founderSafeTraceMetadataValue(langsmithEvent?.attributes?.error_code)
    : undefined;
  const auditStatus =
    tool === "web_search" &&
    toolCallObserved &&
    Number.isFinite(latency) &&
    Number.isInteger(sourceCount) &&
    sourceCount > 0
      ? "ok"
      : "missing";
  return {
    latency_ms: Number.isFinite(latency) ? latency : undefined,
    provider: providerAttributes.provider,
    source_count: Number.isInteger(sourceCount) ? sourceCount : undefined,
    token_cost_status: {
      raw_values_excluded: true,
      status: usageObserved ? "usage_observed" : "usage_unavailable",
    },
    tool,
    tool_call_observed: toolCallObserved,
    trace_health: {
      audit_status: auditStatus,
      ...(langsmithErrorCode ? { error_code: langsmithErrorCode } : {}),
      ...(langsmithFallbackUsed ? { fallback_used: langsmithFallbackUsed } : {}),
      langsmith_status: langsmithStatus,
      status: langsmithStatus === "healthy" && auditStatus === "ok" ? "healthy" : langsmithStatus,
    },
  };
}

async function driveSmartUniversitySinglePdfJourney(
  client,
  sessionId,
  fixturePath,
  caseCopilotRestartRequestPath,
  caseCopilotRestartReadyPath,
  captureSmartUniversityPreRestartScreenshot,
  requireSmartUniversityLivePublicResearch = false,
  auditSpoolRoot,
) {
  await waitForExpression(
    client,
    sessionId,
    "document.readyState === 'complete'",
    "smart_university_browser_shell_ready",
    60_000,
  );
  await armCaseCopilotFetchDiagnostics(client, sessionId);

  async function clickSmartUniversityButton(labels, label, timeoutMilliseconds = 120_000) {
    await waitForExpression(
      client,
      sessionId,
      smartUniversityButtonExpression(labels, "ready"),
      label,
      timeoutMilliseconds,
    );
    const clicked = await evaluateValue(
      client,
      sessionId,
      smartUniversityButtonExpression(labels, "click"),
    );
    if (!clicked) throw new Error(`browser_click_failed label=${label}`);
  }

  async function readSmartUniversityCaseId() {
    return evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = Array.from(document.querySelectorAll("[data-case-copilot-panel][data-case-id]"))
          .find((candidate) => candidate.getClientRects().length > 0);
        return panel?.getAttribute("data-case-id")?.trim() ?? "";
      })()`,
    );
  }

  function smartUniversityPanelExpression(caseId) {
    return `Array.from(document.querySelectorAll("[data-case-copilot-panel][data-case-id]"))
      .find((panel) =>
        panel?.getAttribute("data-case-id") === ${JSON.stringify(caseId)} &&
        panel.getClientRects().length > 0
      )`;
  }

  async function clickCopilotTab(caseId, label) {
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const panel = ${smartUniversityPanelExpression(caseId)};
        const button = Array.from(panel?.querySelectorAll('[role="tablist"][aria-label="Способ ответа"] button') ?? [])
          .find((candidate) => candidate.textContent?.trim() === ${JSON.stringify(label)});
        return Boolean(button && !button.disabled && button.getClientRects().length > 0);
      })()`,
      `smart_university_copilot_tab_${label}`,
      120_000,
    );
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = ${smartUniversityPanelExpression(caseId)};
        const button = Array.from(panel?.querySelectorAll('[role="tablist"][aria-label="Способ ответа"] button') ?? [])
          .find((candidate) => candidate.textContent?.trim() === ${JSON.stringify(label)});
        button?.click();
        return true;
      })()`,
    );
  }

  async function activateControlledCheckboxWithTrustedPointer(caseId, selector, waitLabel) {
    await client.send("Page.bringToFront", {}, sessionId);
    const focusState = await evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = ${smartUniversityPanelExpression(caseId)};
        const checkbox = panel?.querySelector(${JSON.stringify(selector)});
        if (
          !(checkbox instanceof HTMLInputElement) ||
          checkbox.type !== "checkbox" ||
          checkbox.disabled ||
          checkbox.getClientRects().length === 0
        ) {
          return { available: false, checked: false, focused: false, x: null, y: null };
        }
        checkbox.scrollIntoView({ behavior: "instant", block: "center", inline: "center" });
        checkbox.focus({ preventScroll: true });
        const focused = document.activeElement === checkbox;
        const rect = checkbox.getBoundingClientRect();
        return {
          available: rect.width > 0 && rect.height > 0,
          checked: checkbox.checked,
          focused,
          x: rect.left + rect.width / 2,
          y: rect.top + rect.height / 2,
        };
      })()`,
    );
    if (
      !focusState?.available ||
      !focusState.focused ||
      !Number.isFinite(focusState.x) ||
      !Number.isFinite(focusState.y)
    ) {
      throw new Error(`${waitLabel}_target_unavailable`);
    }
    if (focusState.checked) return;
    // Match the verified owner interaction: dispatch a trusted pointer click at the measured
    // checkbox center, then require React's rendered checked/enabled postcondition below.
    await client.send(
      "Input.dispatchMouseEvent",
      {
        type: "mouseMoved",
        x: focusState.x,
        y: focusState.y,
      },
      sessionId,
    );
    await client.send(
      "Input.dispatchMouseEvent",
      {
        type: "mousePressed",
        x: focusState.x,
        y: focusState.y,
        button: "left",
        buttons: 1,
        clickCount: 1,
      },
      sessionId,
    );
    await client.send(
      "Input.dispatchMouseEvent",
      {
        type: "mouseReleased",
        x: focusState.x,
        y: focusState.y,
        button: "left",
        buttons: 0,
        clickCount: 1,
      },
      sessionId,
    );
    await sleep(250);
  }

  async function clickCopilotPanelButton(caseId, label, waitLabel) {
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const panel = ${smartUniversityPanelExpression(caseId)};
        const expected = ${JSON.stringify(label)};
        const button = Array.from(panel?.querySelectorAll("button") ?? [])
          .find((candidate) => candidate.textContent?.replace(/\\s+/gu, " ").trim().includes(expected));
        return Boolean(button && !button.disabled && button.getClientRects().length > 0);
      })()`,
      waitLabel,
      120_000,
    );
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = ${smartUniversityPanelExpression(caseId)};
        const expected = ${JSON.stringify(label)};
        const button = Array.from(panel?.querySelectorAll("button") ?? [])
          .find((candidate) => candidate.textContent?.replace(/\\s+/gu, " ").trim().includes(expected));
        button?.click();
        return true;
      })()`,
    );
  }

  async function readCopilotTabLabels(caseId) {
    return evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = ${smartUniversityPanelExpression(caseId)};
        return Array.from(panel?.querySelectorAll('[role="tablist"][aria-label="Способ ответа"] button') ?? [])
          .filter((button) => button.getClientRects().length > 0 && !button.disabled)
          .map((button) => button.textContent?.replace(/\\s+/gu, " ").trim() ?? "")
          .filter(Boolean);
      })()`,
    );
  }

  async function readCopilotUnknownAnswerCount(caseId) {
    return evaluateBrowserJson(
      client,
      sessionId,
      `(${async function readUnknownCount(caseId) {
        const response = await fetch(
          `/api/startup/cases/${encodeURIComponent(caseId)}/copilot/thread`,
          { cache: "no-store", credentials: "same-origin" },
        );
        if (!response.ok) {
          throw new Error(
            `smart_university_unknown_count_request_failed status=${response.status}`,
          );
        }
        const thread = await response.json();
        const count = Array.isArray(thread.messages)
          ? thread.messages.filter((message) =>
              message.role === "user" &&
              String(message.content ?? "").toLowerCase() === "unknown",
            ).length
          : 0;
        return JSON.stringify(count);
      }} )(${JSON.stringify(caseId)})`,
    );
  }

  async function waitForUnknownAnswerCount(caseId, expectedCount, label) {
    const deadline = Date.now() + 120_000;
    let lastCount = 0;
    while (Date.now() < deadline) {
      lastCount = await readCopilotUnknownAnswerCount(caseId);
      if (lastCount >= expectedCount) return lastCount;
      await sleep(200);
    }
    const diagnostic = await describeBrowserWaitState(client, sessionId);
    throw new Error(
      `browser_wait_timeout label=${label} expected=${expectedCount} actual=${lastCount} diagnostic=${JSON.stringify(diagnostic)}`,
    );
  }

  async function waitForSmartUniversityResearchTab(caseId) {
    const deadline = Date.now() + 120_000;
    let lastLabels = [];
    while (Date.now() < deadline) {
      lastLabels = await readCopilotTabLabels(caseId);
      const label = selectSmartUniversityResearchTabLabel(
        lastLabels,
        { requireLivePublicResearch: requireSmartUniversityLivePublicResearch },
      );
      if (label) return label;
      await sleep(200);
    }
    if (requireSmartUniversityLivePublicResearch) {
      throw new Error(
        `smart_university_live_research_tab_unavailable labels=${JSON.stringify(lastLabels)}`,
      );
    }
    throw new Error(
      "smart_university_public_research_tab_unavailable",
    );
  }

  async function readSmartUniversityResearchModeControls(caseId) {
    return evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = ${smartUniversityPanelExpression(caseId)};
        return Array.from(panel?.querySelectorAll("[data-case-question-research-mode]") ?? [])
          .map((button) => ({
            disabled: button.disabled === true,
            label: button.textContent?.replace(/\\s+/gu, " ").trim() ?? "",
            mode: button.getAttribute("data-case-question-research-mode") ?? "",
            visible: button.getClientRects().length > 0,
          }));
      })()`,
    );
  }

  async function waitForSmartUniversityLiveAcquisitionMode(caseId) {
    const deadline = Date.now() + 120_000;
    let lastControls = [];
    while (Date.now() < deadline) {
      lastControls = await readSmartUniversityResearchModeControls(caseId);
      const mode = selectSmartUniversityLiveAcquisitionMode(lastControls);
      if (mode) return mode;
      await sleep(200);
    }
    throw new Error(
      `smart_university_live_research_mode_unavailable controls=${JSON.stringify(lastControls)}`,
    );
  }

  async function clickSidebarView(label, selector) {
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const expected = ${JSON.stringify(label)};
        const button = Array.from(document.querySelectorAll("nav.founder-sidebar__nav button"))
          .find((candidate) => candidate.textContent?.trim().includes(expected));
        return Boolean(button && !button.disabled && button.getClientRects().length > 0);
      })()`,
      `smart_university_nav_${label}`,
      60_000,
    );
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const expected = ${JSON.stringify(label)};
        const button = Array.from(document.querySelectorAll("nav.founder-sidebar__nav button"))
          .find((candidate) => candidate.textContent?.trim().includes(expected));
        button?.click();
        return true;
      })()`,
    );
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const view = document.querySelector(${JSON.stringify(selector)});
        return Boolean(view && view.getClientRects().length > 0);
      })()`,
      `smart_university_view_${selector}`,
      60_000,
    );
  }

  async function collectVisibleSmartUniversityPageEvidence(
    viewName,
    requiredPatternSource,
    placeholderPatternSource,
    launchPackEvidence = null,
  ) {
    return evaluateValue(
      client,
      sessionId,
      `(() => {
        const args = ${JSON.stringify({
          caseId,
          launchPackEvidence,
          placeholderPatternSource,
          requiredPatternSource,
          viewName,
        })};
        const requiredPattern = new RegExp(args.requiredPatternSource, "iu");
        const placeholderPattern = new RegExp(args.placeholderPatternSource, "iu");
        const view = document.querySelector(\`[data-founder-view="\${args.viewName}"]\`);
        const text = view?.textContent?.replace(/\\s+/gu, " ").trim() ?? "";
        const structuredSelectorsByView = {
          "action-plan": [
            "[data-public-research-impact]",
            "[class*='priorityBasis'] small",
            "[class*='timelineStep']",
            "[data-founder-launch-pack='draft'] a[href$='/markdown']",
            "[data-founder-launch-pack='draft'] a[href$='/provenance']",
          ],
          market: [
            "[data-public-research-impact]",
            "[class*='opportunityBubble']",
            "[class*='marketSignalList'] [class*='factRow']",
            "[class*='competitorCard']:not([class*='placeholderCard']):not([class*='competitorUnlockCard'])",
          ],
          metrics: [
            "[data-metrics-research-summary]",
            "[data-scenario-chart-projection]",
            "[data-founder-scenario-metrics]",
            "a[href^='http']",
          ],
          risks: [
            "[data-public-research-impact]",
            "[data-risk-scale]",
            "[class*='questionRow']",
            "[class*='scenarioIssue']",
            "[data-scenario-only-disclosure]",
            "a[href^='http']",
          ],
        };
        const sourceSelectorsByView = {
          "action-plan": [
            "[data-public-research-impact]",
            "[data-founder-launch-pack='draft'] a[href$='/markdown']",
            "[data-founder-launch-pack='draft'] a[href$='/provenance']",
          ],
          market: [
            "[data-public-research-impact]",
            "[class*='marketSignalList'] [class*='factRow']",
            "[class*='competitorCard']:not([class*='placeholderCard']):not([class*='competitorUnlockCard'])",
            "a[href^='http']",
          ],
          metrics: [
            "[data-metrics-research-summary]",
            "[data-scenario-chart-projection]",
            "[data-founder-scenario-metrics]",
            "a[href^='http']",
          ],
          risks: [
            "[data-public-research-impact]",
            "[data-risk-scale]",
            "[class*='questionRow']",
            "[class*='scenarioIssue']",
            "[data-scenario-only-disclosure]",
            "a[href^='http']",
          ],
        };
        const structuredSelectors = structuredSelectorsByView[args.viewName] ?? [];
        const sourceSelectors = sourceSelectorsByView[args.viewName] ?? [];
        const cleanText = (node) => node?.textContent?.replace(/\\s+/gu, " ").trim() ?? "";
        const visibleNodes = (selector) =>
          Array.from(view?.querySelectorAll(selector) ?? []).filter((node) => node.getClientRects().length > 0);
        const isGroundedText = (value, extraPlaceholderPattern = null) => {
          if (!value || placeholderPattern.test(value)) {
            return false;
          }
          if (/(?:нужн(?:ы|о|ен|а)|после анализа|после данных|после проверки|нет данных|нет источников|пока нет|разблокирует|добавьте|требует проверки)/iu.test(value)) {
            return false;
          }
          if (extraPlaceholderPattern?.test(value)) {
            return false;
          }
          return requiredPattern.test(value);
        };
        const hasGroundedNode = (selector, predicate = (nodeText) => isGroundedText(nodeText)) =>
          visibleNodes(selector).some((node) => predicate(cleanText(node), node));
        const contractChecksByView = {
          "action-plan": () => {
            const hasResearchImpact = hasGroundedNode("[data-public-research-impact]", (nodeText) =>
              /(?:онлайн|источник|публичн|ориентир)/iu.test(nodeText),
            );
            const hasPriorityBasis = hasGroundedNode("[class*='priorityBasis'] small", (nodeText) =>
              /(?:отч[её]т|основан|данн|верси|research|gtm)/iu.test(nodeText) &&
              !/ИИ-гипотеза/iu.test(nodeText),
            );
            const timelineTexts = visibleNodes("[class*='timelineStep']").map(cleanText).filter((nodeText) =>
              /(?:7|30|60|90)/u.test(nodeText) &&
              !/ИИ-гипотеза/iu.test(nodeText),
            );
            const hasNonAiTimeline = ["7", "30", "60", "90"].every((marker) =>
              timelineTexts.some((nodeText) => nodeText.includes(marker)),
            );
            const draftLinks = visibleNodes("[data-founder-launch-pack='draft'] a[href]");
            const launchPackReady =
              args.launchPackEvidence?.link_visible === true &&
              typeof args.launchPackEvidence?.markdown_url === "string" &&
              typeof args.launchPackEvidence?.provenance_appendix_url === "string" &&
              draftLinks.some((link) => (link.getAttribute("href") ?? "") === args.launchPackEvidence.markdown_url) &&
              draftLinks.some((link) => (link.getAttribute("href") ?? "") === args.launchPackEvidence.provenance_appendix_url);
            return {
              draft_markdown_ready: launchPackReady,
              draft_provenance_ready: launchPackReady,
              non_ai_timeline: hasNonAiTimeline,
              priority_basis: hasPriorityBasis,
              public_research_impact: hasResearchImpact,
            };
          },
          market: () => {
            const hasResearchImpact = hasGroundedNode("[data-public-research-impact]", (nodeText) =>
              /(?:онлайн|источник|публичн|ориентир|рын|конкур|tam|sam|som)/iu.test(nodeText),
            );
            const hasOpportunity = hasGroundedNode("[class*='opportunityBubble']", (nodeText) =>
              /(?:tam|sam|som|₸|\\$|€|£|%|\\d|тыс|млн|млрд)/iu.test(nodeText) &&
              !/(?:нужен источник|после уточнения|нет данных|пока нет подтвержд)/iu.test(nodeText),
            );
            const hasSignal = hasGroundedNode("[class*='marketSignalList'] [class*='factRow']", (nodeText) =>
              /(?:аудит|географ|канал|рын|сегмент|сигнал|источник|source|benchmark|pricing|конкур|рост|категор)/iu.test(nodeText) &&
              !/(?:нужен источник|после уточнения|нет данных|пока нет подтвержд)/iu.test(nodeText),
            );
            const hasCompetitor = hasGroundedNode(
              "[class*='competitorCard']:not([class*='placeholderCard']):not([class*='competitorUnlockCard'])",
              (nodeText) =>
                /(?:конкур|альтернатив|риск|заменител|компан|источник|клиент)/iu.test(nodeText) &&
                !/(?:нужен источник|после уточнения|нет данных|пока нет подтвержд)/iu.test(nodeText),
            );
            return {
              non_placeholder_opportunity: hasOpportunity,
              public_research_impact: hasResearchImpact,
              real_competitor: hasCompetitor,
              real_signal: hasSignal,
            };
          },
          metrics: () => {
            const hasSummary = hasGroundedNode("[data-metrics-research-summary]", (nodeText) =>
              /(?:онлайн|публичн|источник|метрик|сценар)/iu.test(nodeText),
            );
            const hasSourceOrDelta =
              visibleNodes("[data-metrics-research-summary] a[href^='http']").length > 0 ||
              hasGroundedNode("[data-metrics-research-summary] [class*='metricsSourceList'] li", (nodeText) =>
                /(?:источник|публичн|source|benchmark|http)/iu.test(nodeText),
              ) ||
              hasGroundedNode("[data-metrics-research-summary] [class*='metricsDeltaList'] > div", (nodeText) =>
                /(?:до онлайн|после онлайн|обновл|метрик)/iu.test(nodeText),
              );
            const hasScenarioDetails = hasGroundedNode("[data-scenario-chart-projection], [data-founder-scenario-metrics]", (nodeText) =>
              /(?:сценарн|ARR|MRR|CAC|LTV|марж|выруч|расход|запас|runway)/iu.test(nodeText),
            );
            return {
              research_summary: hasSummary,
              scenario_details: hasScenarioDetails,
              source_or_delta: hasSourceOrDelta,
            };
          },
          risks: () => {
            const hasResearchImpact = hasGroundedNode("[data-public-research-impact]", (nodeText) =>
              /(?:онлайн|источник|публичн|ориентир|риск|вопрос)/iu.test(nodeText),
            );
            const hasScenarioIssue = hasGroundedNode("[class*='scenarioIssue'], [data-scenario-only-disclosure]", (nodeText) =>
              /(?:сценар|ARR|MRR|CAC|LTV|риск|проблем|провер)/iu.test(nodeText),
            );
            const hasRiskAssessment = hasGroundedNode("[class*='severity'], [class*='contradiction'], [data-risk-scale]", (nodeText) =>
              /(?:критич|высок|средн|под контрол|противореч|риск|вероятн|влияни)/iu.test(nodeText) &&
              !/(?:нужны данные|после ответа|после данных|после проверки|не выявлено)/iu.test(nodeText),
            );
            const hasActualQuestion = hasGroundedNode("[class*='questionRow']", (nodeText) =>
              /(?:\\?|как|какой|что|почему|сколько|когда|где|кто|уточн)/iu.test(nodeText) &&
              !/(?:разблокирует|добавьте|нужн|публичный поиск)/iu.test(nodeText),
            );
            return {
              actual_question: hasActualQuestion,
              public_research_impact: hasResearchImpact,
              risk_assessment: hasRiskAssessment,
              scenario_issue: hasScenarioIssue,
            };
          },
        };
        const contractChecks = contractChecksByView[args.viewName]?.() ?? {};
        const contractSatisfied = Object.values(contractChecks).every((value) => value === true);
        const meaningfulNodes = Array.from(
          structuredSelectors.length > 0 ? view?.querySelectorAll(structuredSelectors.join(",")) ?? [] : [],
        ).filter((node) => {
          const nodeText = node.textContent?.replace(/\\s+/gu, " ").trim() ?? "";
          if (args.viewName === "action-plan" && /ИИ-гипотеза/iu.test(nodeText)) {
            return false;
          }
          if (args.viewName === "market" && /(?:нужен источник|после уточнения|нет данных|пока нет подтвержд)/iu.test(nodeText)) {
            return false;
          }
          return node.getClientRects().length > 0 && requiredPattern.test(nodeText);
        });
        const sourceSignals = Array.from(
          sourceSelectors.length > 0 ? view?.querySelectorAll(sourceSelectors.join(",")) ?? [] : [],
        ).filter((node) => {
          const nodeText = node.textContent?.replace(/\\s+/gu, " ").trim() ?? "";
          return node.getClientRects().length > 0 && (requiredPattern.test(nodeText) || node instanceof HTMLAnchorElement);
        });
        const hasRequiredText = requiredPattern.test(text);
        const hasSourceSignal = sourceSignals.length > 0;
        const hasVisibleView = Boolean(view?.getClientRects().length);
        return {
          case_id: args.caseId,
          contract_checks: contractChecks,
          contract_satisfied: contractSatisfied,
          meaningful_item_count: meaningfulNodes.length,
          populated: hasVisibleView && hasRequiredText && contractSatisfied,
          placeholder_only:
            !hasRequiredText ||
            !contractSatisfied ||
            (placeholderPattern.test(text) && !hasSourceSignal),
          rendered_text_chars: text.length,
          source_signal_count: sourceSignals.length,
        };
      })()`,
    );
  }

  await clickSmartUniversityButton(
    ["Новый анализ", "Загрузить проект"],
    "smart_university_open_data_room",
    60_000,
  );
  await waitForExpression(
    client,
    sessionId,
    `Boolean(document.querySelector('[data-founder-view="data-room"] input[type="file"]'))`,
    "smart_university_file_input_visible",
    30_000,
  );
  await client.send("DOM.enable", {}, sessionId);
  const { root } = await client.send("DOM.getDocument", {}, sessionId);
  const { nodeId } = await client.send(
    "DOM.querySelector",
    {
      nodeId: root.nodeId,
      selector: '[data-founder-view="data-room"] input[type="file"]',
    },
    sessionId,
  );
  if (!nodeId) throw new Error("smart_university_file_input_missing");
  await armFounderIntakeObservation(client, sessionId);
  const browserUpload = materializeBrowserUploadPath(fixturePath);
  let smartUniversityUploadState;
  let intakeEvidence;
  const smartUniversityGate2Action = "gate2-approve";
  try {
    await client.send(
      "DOM.setFileInputFiles",
      { files: [browserUpload.path], nodeId },
      sessionId,
    );
    smartUniversityUploadState = JSON.parse(await evaluateValue(
      client,
      sessionId,
      `(() => {
        const observedIntake = globalThis.__queue5ObservedIntake;
        const input = document.querySelector('[data-founder-view="data-room"] input[type="file"]');
        const files = Array.from(input?.files ?? []);
        const fileCount = observedIntake?.fileCount ?? files.length;
        const fileTypes = observedIntake?.fileTypes ??
          files.map((file) => file.type || "application/octet-stream");
        const selectedPdf = fileCount === 1 &&
          fileTypes.every((fileType) => fileType === "application/pdf");
        if (!selectedPdf) {
          return JSON.stringify({ selectedPdf, fileCount, fileTypes });
        }
        if (!observedIntake && input) {
          globalThis.__queue5ObservedIntake = { fileCount, fileTypes };
          const reactPropsKey = Object.keys(input).find((key) => key.startsWith("__reactProps$"));
          const reactOnChange = reactPropsKey ? input[reactPropsKey]?.onChange : null;
          if (typeof reactOnChange === "function") {
            reactOnChange({ currentTarget: input, target: input });
          } else {
            const inputEvent = typeof InputEvent === "function"
              ? new InputEvent("input", { bubbles: true, composed: true })
              : new Event("input", { bubbles: true, composed: true });
            input.dispatchEvent(inputEvent);
            input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
          }
        }
        return JSON.stringify({ selectedPdf: true, fileCount, fileTypes });
      })()`,
    ));
    if (!smartUniversityUploadState.selectedPdf) {
      throw new Error(
        `smart_university_pdf_upload_not_selected file_count=${smartUniversityUploadState.fileCount} file_types=${smartUniversityUploadState.fileTypes.join(",")}`,
      );
    }
    intakeEvidence = await observeFounderIntakeEvidence(client, sessionId, true);
    await waitForExpression(
      client,
      sessionId,
      `(() => {
        const dataRoom = document.querySelector('[data-founder-view="data-room"]');
        const text = dataRoom?.textContent ?? "";
        return text.includes("1 файл") || text.includes("файл(а) выбрано");
      })()`,
      "smart_university_pdf_receipt_visible",
      30_000,
    );
    await clickSmartUniversityButton(
      ["Запустить анализ выбранных материалов", "Начать анализ"],
      "smart_university_start_analysis",
      60_000,
    );
    await waitForExpression(
      client,
      sessionId,
      actionSelectorExpression(smartUniversityGate2Action, "ready"),
      "smart_university_gate2_ready",
      300_000,
    );
  } finally {
    browserUpload.cleanup();
  }
  const gate2AcceptedReceiptVisible = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const gatePage = document.querySelector('[data-founder-analysis-page="progress-gate2"]');
      const pageText = gatePage?.textContent?.replace(/\\s+/gu, " ") ?? "";
      const receipt = Array.from(gatePage?.querySelectorAll('[role="status"]') ?? [])
        .find((candidate) => candidate.textContent?.includes("Документы приняты сервером"));
      const gateButton = gatePage?.querySelector('[data-founder-action="gate2-approve"]');
      const waitingMaterialsVisible =
        /Ожида(?:ем|ет) материалы|waiting materials|waiting-materials/iu.test(pageText);
      return Boolean(receipt && gateButton && !gateButton.disabled && !waitingMaterialsVisible);
    })()`,
  );
  if (!gate2AcceptedReceiptVisible) {
    throw new Error("smart_university_gate2_accepted_receipt_missing");
  }
  await evaluateValue(
    client,
    sessionId,
    actionSelectorExpression("gate2-approve", "click"),
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = Array.from(document.querySelectorAll("[data-case-copilot-panel][data-case-id]"))
        .find((candidate) => candidate.getClientRects().length > 0);
      return Boolean(panel?.querySelector("[data-case-question-card]"));
    })()`,
    "smart_university_case_copilot_ready",
    300_000,
  );
  const caseId = await readSmartUniversityCaseId();
  if (!caseId) throw new Error("smart_university_case_id_missing");
  const questionVisible = await evaluateValue(
    client,
    sessionId,
    `Boolean(${smartUniversityPanelExpression(caseId)}?.querySelector("[data-case-question-card]"))`,
  );

  const previousUnknownAnswerCount = await readCopilotUnknownAnswerCount(caseId);
  await clickCopilotTab(caseId, "Не знаю");
  await clickCopilotPanelButton(
    caseId,
    "Ответить «не знаю»",
    "smart_university_submit_unknown",
  );
  const unknownAnswerCount = await waitForUnknownAnswerCount(
    caseId,
    previousUnknownAnswerCount + 1,
    "smart_university_unknown_recorded",
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      return Boolean(
        panel &&
        panel.getAttribute("aria-busy") !== "true" &&
        !document.querySelector('.founder-global-busy[aria-busy="true"]')
      );
    })()`,
    "smart_university_unknown_ui_idle",
    120_000,
  );
  const publicResearchTabLabel = await waitForSmartUniversityResearchTab(caseId);
  const publicResearchPrep = {
    public_research_tab_label: publicResearchTabLabel,
    unknown_answer_count: unknownAnswerCount,
  };
  if (publicResearchTabLabel !== SMART_UNIVERSITY_PUBLIC_RESEARCH_ANSWER_TAB_LABEL) {
    throw new Error("smart_university_public_research_answer_tab_invalid");
  }
  await clickCopilotTab(caseId, "Публичный поиск");
  const publicResearchAcquisitionMode = await waitForSmartUniversityLiveAcquisitionMode(caseId);
  await evaluateValue(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const button = panel?.querySelector('[data-case-question-research-mode="live_public_research"]');
      if (!button || button.disabled || button.getClientRects().length === 0) return false;
      button.click();
      return true;
    })()`,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const button = panel?.querySelector('[data-case-question-research-mode="live_public_research"]');
      return Boolean(
        button &&
        button.getAttribute("aria-checked") === "true" &&
        button.getClientRects().length > 0
      );
    })()`,
    "smart_university_live_research_mode_selected",
    30_000,
  );
  publicResearchPrep.acquisition_mode = publicResearchAcquisitionMode;
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const checkbox = panel?.querySelector('[data-case-question-consent="public_research"]');
      return Boolean(checkbox && !checkbox.disabled && checkbox.getClientRects().length > 0);
    })()`,
    "smart_university_public_research_consent_visible",
    120_000,
  );
  await activateControlledCheckboxWithTrustedPointer(
    caseId,
    '[data-case-question-consent="public_research"]',
    "smart_university_public_research_consent_target",
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const checkbox = panel?.querySelector('[data-case-question-consent="public_research"]');
      const button = panel?.querySelector('[data-case-question-submit="public_research"]');
      return Boolean(
        checkbox?.checked &&
        button &&
        !button.disabled &&
        button.getClientRects().length > 0
      );
    })()`,
    "smart_university_public_research_consent_applied",
    30_000,
  );
  const researchStarted = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const button = panel?.querySelector('[data-case-question-submit="public_research"]');
      if (!button || button.disabled || button.getClientRects().length === 0) return false;
      button.click();
      return true;
    })()`,
  );
  if (!researchStarted) throw new Error("smart_university_start_public_research_unavailable");
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const job = panel?.querySelector("[data-case-copilot-research-status] [data-research-job-status]");
      const status = job?.getAttribute("data-research-job-status");
      return status === "completed" || status === "partial";
    })()`,
    "smart_university_public_research_done",
    180_000,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const comparison = panel?.querySelector("[data-research-metric-comparison]");
      return (
        panel?.getAttribute("aria-busy") !== "true" &&
        comparison &&
        comparison.getClientRects().length > 0
      );
    })()`,
    "smart_university_research_scenario_delta_ready",
    120_000,
  );
  await waitForExpression(
    client,
    sessionId,
    `(async () => {
      const statusResponse = await fetch("/api/startup/cases/${encodeURIComponent(caseId)}/analysis", {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!statusResponse.ok) return false;
      const status = await statusResponse.json();
      if (
        status?.analysis_status !== "gate3_review_required" ||
        status?.gate2_status !== "completed" ||
        status?.gate3_status !== "required"
      ) {
        return false;
      }
      const gtmResponse = await fetch("/api/startup/cases/${encodeURIComponent(caseId)}/gtm", {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!gtmResponse.ok) return false;
      const gtm = await gtmResponse.json();
      return gtm?.case_id === caseId && gtm?.data_revision === status?.data_revision;
    })()`,
    "smart_university_gate2_analysis_ready",
    180_000,
  );
  const scenarioDeltaVisible = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const renderedComparisonTexts = Array.from(
        panel?.querySelectorAll("[data-research-metric-comparison]") ?? [],
      )
        .map((node) => node.textContent?.replace(/\\s+/gu, " ").trim() ?? "")
        .filter(Boolean);
      const renderedChangeCount = renderedComparisonTexts.filter((text) =>
        /(?:→|->|[+\\-]\\s?\\d|delta|измен|рост|сниж|консерватив|оптимист)/iu.test(text),
      ).length;
      return {
        rendered_change_count: renderedChangeCount,
        rendered_comparison_count: renderedComparisonTexts.length,
        visible: renderedComparisonTexts.length > 0 && renderedChangeCount > 0,
      };
    })()`,
  );

  await waitForExpression(
    client,
    sessionId,
    `Boolean(${smartUniversityPanelExpression(caseId)}?.querySelector("[data-founder-scenario-metrics]"))`,
    "smart_university_scenarios_visible",
    120_000,
  );
  await evaluateValue(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const button = Array.from(panel?.querySelectorAll('[aria-label="Выбор сценария"] button') ?? [])
        .find((candidate) => candidate.textContent?.trim().includes("Базовый"));
      if (!button || button.disabled) return false;
      button.click();
      return true;
    })()`,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(caseId)};
      const button = Array.from(panel?.querySelectorAll('[aria-label="Выбор сценария"] button') ?? [])
        .find((candidate) => candidate.textContent?.trim().includes("Базовый"));
      return button?.getAttribute("aria-pressed") === "true";
    })()`,
    "smart_university_base_scenario_selected",
    120_000,
  );

  await clickSidebarView("Метрики", '[data-founder-view="metrics"]');
  const metricsVisible = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const view = document.querySelector('[data-founder-view="metrics"]');
      const text = view?.textContent?.replace(/\\s+/gu, " ").trim() ?? "";
      const visibleMetricNodes = Array.from(
        view?.querySelectorAll("[data-founder-scenario-metrics], article, section, details, [class*='metric']") ?? [],
      ).filter((node) => node.getClientRects().length > 0);
      return Boolean(
        view &&
        view.getClientRects().length > 0 &&
        text.length > 0 &&
        /(?:MRR|ARR|CAC|LTV|выруч|метрик|марж|расход|runway|запас)/iu.test(text) &&
        visibleMetricNodes.length > 0
      );
    })()`,
  );
  const metricsPageEvidence = await collectVisibleSmartUniversityPageEvidence(
    "metrics",
    "(?:MRR|ARR|CAC|LTV|марж|выруч|расход|runway|запас|сценар|источник)",
    "(?:не хватает данных|добавьте|нет документальных наблюдений)",
  );
  await clickSidebarView("Рынок", '[data-founder-view="market"]');
  const marketReconstructionVisible = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const text = document.querySelector('[data-founder-view="market"]')?.textContent ?? "";
      return text.trim().length > 0 && /(?:рын|market|tam|sam|som)/iu.test(text);
    })()`,
  );
  const marketPageEvidence = await collectVisibleSmartUniversityPageEvidence(
    "market",
    "(?:рын|market|tam|sam|som|конкур|сегмент|источник|source|pricing|benchmark)",
    "(?:нужен источник|после уточнения|нет данных|пока нет подтвержд)",
  );
  await clickSidebarView("Риски", '[data-founder-view="risks"]');
  const risksVisible = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const text = document.querySelector('[data-founder-view="risks"]')?.textContent ?? "";
      return text.trim().length > 0 && /(?:риск|risk)/iu.test(text);
    })()`,
  );
  const risksPageEvidence = await collectVisibleSmartUniversityPageEvidence(
    "risks",
    "(?:риск|risk|пробел|вопрос|противореч|провер|ARR|CAC|MRR|LTV)",
    "(?:нет источников|после ответа|не выявлено)",
  );
  await clickSidebarView("План действий", '[data-founder-view="action-plan"]');
  const actionsVisible = await evaluateValue(
    client,
    sessionId,
    `Boolean(document.querySelector('[data-founder-view="action-plan"]')?.textContent?.trim())`,
  );
  const planHorizonVisible = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const text = document.querySelector('[data-founder-view="action-plan"]')?.textContent ?? "";
      return ["7", "30", "60", "90"].every((marker) => text.includes(marker));
    })()`,
  );
  await clickSmartUniversityButton(
    ["Принять рекомендацию"],
    "smart_university_accept_final_decision",
    120_000,
  );
  await waitForExpression(
    client,
    sessionId,
    `(async () => {
      const response = await fetch("/api/startup/cases/${encodeURIComponent(caseId)}/analysis", {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return false;
      const status = await response.json();
      return status?.gate3_status === "completed" &&
        status?.report_status === "ready" &&
        typeof status?.snapshot_hash === "string" &&
        status.snapshot_hash.length > 0 &&
        Number.isInteger(status?.snapshot_revision);
    })()`,
    "smart_university_gate3_report_ready",
    180_000,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const view = document.querySelector('[data-founder-view="action-plan"]');
      const button = Array.from(view?.querySelectorAll("button") ?? [])
        .find((candidate) =>
          candidate.textContent?.replace(/\\s+/gu, " ").trim().includes("Собрать рабочий пакет"),
        );
      return Boolean(
        view &&
        view.getClientRects().length > 0 &&
        button &&
        !button.disabled &&
        button.getClientRects().length > 0
      );
    })()`,
    "smart_university_gate3_ui_ready",
    120_000,
  );
  await clickSmartUniversityButton(
    ["Собрать рабочий пакет"],
    "smart_university_build_launch_pack",
    120_000,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const draft = document.querySelector('[data-founder-launch-pack="draft"]');
      const links = Array.from(draft?.querySelectorAll("a[href]") ?? []);
      return links.some((link) => link.getAttribute("href")?.endsWith("/markdown")) &&
        links.some((link) => link.getAttribute("href")?.endsWith("/provenance"));
    })()`,
    "smart_university_launch_pack_visible",
    120_000,
  );
  const launchPackEvidence = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const caseId = ${JSON.stringify(caseId)};
      const assetPrefix = \`/api/startup/cases/\${encodeURIComponent(caseId)}/assets/\`;
      const draft = document.querySelector('[data-founder-launch-pack="draft"]');
      const links = Array.from(draft?.querySelectorAll("a[href]") ?? []);
      const markdownLink = links.find((link) => {
        const href = link.getAttribute("href") ?? "";
        return href.startsWith(assetPrefix) && href.endsWith("/markdown");
      });
      const provenanceLink = links.find((link) => {
        const href = link.getAttribute("href") ?? "";
        return href.startsWith(assetPrefix) && href.endsWith("/provenance");
      });
      const assetId = markdownLink?.getAttribute("href")?.match(/\\/assets\\/([^/]+)\\/markdown$/u)?.[1] ?? "";
      return {
        asset_id: assetId,
        link_visible: Boolean(
          assetId &&
          markdownLink &&
          provenanceLink &&
          markdownLink.getClientRects().length > 0 &&
          provenanceLink.getClientRects().length > 0
        ),
        markdown_url: markdownLink?.getAttribute("href") ?? "",
        provenance_appendix_url: provenanceLink?.getAttribute("href") ?? "",
      };
    })()`,
  );
  if (
    !launchPackEvidence?.asset_id ||
    launchPackEvidence.link_visible !== true ||
    !launchPackEvidence.markdown_url ||
    !launchPackEvidence.provenance_appendix_url
  ) {
    throw new Error("smart_university_launch_pack_visible_asset_missing");
  }
  const actionPlanPageEvidence = await collectVisibleSmartUniversityPageEvidence(
    "action-plan",
    "(?:7|30|60|90|план|действ|улучш|провер|launch|package|assets?)",
    "(?:ещё не сформирован|после анализа|нет данных|нужно|ИИ-гипотеза)",
    launchPackEvidence,
  );
  await clickSidebarView("Отчёты", '[data-founder-view="report-center"]');
  await clickSmartUniversityButton(
    ["Сформировать отчёт"],
    "smart_university_generate_report",
    180_000,
  );
  await waitForExpression(
    client,
    sessionId,
    `(async () => {
      const [statusResponse, reportResponse] = await Promise.all([
        fetch("/api/startup/cases/${encodeURIComponent(caseId)}/analysis", {
          cache: "no-store",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        }),
        fetch("/api/startup/cases/${encodeURIComponent(caseId)}/report", {
          cache: "no-store",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        }),
      ]);
      if (!statusResponse.ok || !reportResponse.ok) return false;
      const [status, report] = await Promise.all([
        statusResponse.json(),
        reportResponse.json(),
      ]);
      if (
        status?.case_id !== ${JSON.stringify(caseId)} ||
        report?.case_id !== ${JSON.stringify(caseId)} ||
        status?.gate4_status !== "completed" ||
        status?.report_status !== "ready" ||
        report?.freeze_status !== "approved" ||
        report?.pdf_status !== "ready" ||
        typeof status?.snapshot_hash !== "string" ||
        status.snapshot_hash.length === 0 ||
        !Number.isInteger(status?.snapshot_revision) ||
        report?.snapshot_hash !== status.snapshot_hash ||
        report?.snapshot_revision !== status.snapshot_revision
      ) {
        return false;
      }
      return ["json_url", "html_url", "pdf_url"].every((field) => {
        const format = field.replace("_url", "");
        return typeof report?.[field] === "string" &&
          report[field].endsWith("/report/" + format);
      });
    })()`,
    "smart_university_report_api_ready",
    180_000,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const view = document.querySelector('[data-founder-view="report-center"]');
      const formats = ["pdf", "html", "json"];
      return formats.every((format) => {
        return Array.from(view?.querySelectorAll("a[href]") ?? [])
          .some((candidate) =>
            candidate.getAttribute("href")?.endsWith("/report/" + format) &&
            candidate.getClientRects().length > 0 &&
            Boolean(candidate.querySelector('[data-ready="true"]')),
          );
      });
    })()`,
    "smart_university_report_formats_ready",
    180_000,
  );

  let preRestartEvidence = await evaluateBrowserJson(
    client,
    sessionId,
    `(${async function collectSmartUniversityEvidence(args) {
      async function requestJson(path) {
        const response = await fetch(path, {
          cache: "no-store",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
          if (!response.ok) {
            throw new Error(
            `smart_university_request_failed path=${path} status=${response.status}`,
            );
          }
        return response.json();
      }
      async function requestText(path) {
        const response = await fetch(path, {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(
            `smart_university_download_failed path=${path} status=${response.status}`,
          );
        }
        return {
          contentDisposition: response.headers.get("content-disposition") ?? "",
          text: await response.text(),
        };
      }
      async function sha256Bytes(bytes) {
        const digest = await crypto.subtle.digest("SHA-256", bytes);
        return `sha256:${Array.from(new Uint8Array(digest))
          .map((byte) => byte.toString(16).padStart(2, "0"))
          .join("")}`;
      }
      async function sha256Text(text) {
        return sha256Bytes(new TextEncoder().encode(text));
      }
      function reportSnapshotId(reportJson) {
        return String(
          reportJson?.snapshot_id ??
          reportJson?.snapshotId ??
          reportJson?.report_snapshot_id ??
          reportJson?.metadata?.snapshot_id ??
          "",
        ).trim();
      }
      async function requestPdfContract(path) {
        const response = await fetch(path, {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(
            `smart_university_pdf_download_failed path=${path} status=${response.status}`,
          );
        }
        const bytes = new Uint8Array(await response.arrayBuffer());
        const magic = String.fromCharCode(...bytes.slice(0, 4));
        return {
          byte_length: bytes.byteLength,
          sha256: await sha256Bytes(bytes),
          magic,
          bounded: bytes.byteLength > 4 && bytes.byteLength <= 5_000_000,
        };
      }
      function hasSourceFact(field) {
        return field &&
          typeof field === "object" &&
          field.status === "source_fact" &&
          Array.isArray(field.values) &&
          field.values.length > 0 &&
          Array.isArray(field.evidence_refs) &&
          field.evidence_refs.length > 0;
      }
      function scenarioMetricHasProvenance(metric) {
        return Boolean(
          metric &&
          typeof metric.provenance === "string" &&
          typeof metric.formula_key === "string" &&
          typeof metric.formula_description === "string" &&
          Array.isArray(metric.dependency_refs) &&
          Array.isArray(metric.source_refs) &&
          typeof metric.validation_plan === "string" &&
          metric.validation_plan.trim(),
        );
      }
      const caseId = args.caseId;
      const [analysisStatus, profile, state, thread, scenarios] = await Promise.all([
        requestJson(`/api/startup/cases/${encodeURIComponent(caseId)}/analysis`),
        requestJson(`/api/startup/cases/${encodeURIComponent(caseId)}/profile`),
        requestJson(`/api/startup/cases/${encodeURIComponent(caseId)}/copilot/state`),
        requestJson(`/api/startup/cases/${encodeURIComponent(caseId)}/copilot/thread`),
        requestJson(`/api/startup/cases/${encodeURIComponent(caseId)}/scenarios`),
      ]);
      const panel = Array.from(document.querySelectorAll("[data-case-copilot-panel][data-case-id]"))
        .find((candidate) =>
          candidate?.getAttribute("data-case-id") === caseId &&
          candidate.getClientRects().length > 0,
        );
      const researchStatus = panel?.querySelector("[data-case-copilot-research-status]");
      const jobNode = researchStatus?.querySelector("[data-research-job-id][data-research-job-status]");
      const jobId = jobNode?.getAttribute("data-research-job-id") ?? "";
      const jobStatus = jobNode?.getAttribute("data-research-job-status") ?? "";
      const job = await requestJson(
        `/api/startup/cases/${encodeURIComponent(caseId)}/research/jobs/${encodeURIComponent(jobId)}`,
      );
      const assetPrefix = `/api/startup/cases/${encodeURIComponent(caseId)}/assets/`;
      const launchPackEvidence = args.launchPackEvidence ?? {};
      if (
        launchPackEvidence.link_visible !== true ||
        typeof launchPackEvidence.asset_id !== "string" ||
        !launchPackEvidence.asset_id ||
        typeof launchPackEvidence.markdown_url !== "string" ||
        !launchPackEvidence.markdown_url.startsWith(assetPrefix) ||
        !launchPackEvidence.markdown_url.endsWith("/markdown") ||
        typeof launchPackEvidence.provenance_appendix_url !== "string" ||
        !launchPackEvidence.provenance_appendix_url.startsWith(assetPrefix) ||
        !launchPackEvidence.provenance_appendix_url.endsWith("/provenance")
      ) {
        throw new Error("smart_university_launch_pack_visible_asset_missing");
      }
      const asset = await requestJson(
        `/api/startup/cases/${encodeURIComponent(caseId)}/assets/${encodeURIComponent(launchPackEvidence.asset_id)}`,
      );
      if (
        asset?.asset_id !== launchPackEvidence.asset_id ||
        asset?.markdown_url !== launchPackEvidence.markdown_url ||
        asset?.provenance_appendix_url !== launchPackEvidence.provenance_appendix_url
      ) {
        throw new Error("smart_university_launch_pack_asset_mismatch");
      }
      const markdown = await requestText(asset.markdown_url);
      const provenance = await requestText(asset.provenance_appendix_url);
      const reportRoot = `/api/startup/cases/${encodeURIComponent(caseId)}/report`;
      const [reportJsonDownload, reportHtml, reportPdf] = await Promise.all([
        requestText(`${reportRoot}/json`),
        requestText(`${reportRoot}/html`),
        requestPdfContract(`${reportRoot}/pdf`),
      ]);
      const reportJson = JSON.parse(reportJsonDownload.text);
      const reportJsonSha256 = await sha256Text(reportJsonDownload.text);
      const reportHtmlSha256 = await sha256Text(reportHtml.text);
      const reportSnapshot = reportSnapshotId(reportJson);
      const profileFields = Object.values(profile.fields ?? {});
      const acceptedInputs = Array.isArray(state.accepted_inputs) ? state.accepted_inputs : [];
      const privateFieldPattern = /(?:revenue|mrr|arr|cash|burn|customer|client|contract|sales|invoice|invoices|invoice_register|bank|bank_data|выруч|кэш|деньг|сжиган|клиент|договор|контракт|сч[её]т|счета|инвойс|накладн|акт|банк|банков|касс|остат)/iu;
      const publicResearchPattern = /(?:founder_statement|public_benchmark|ai_scenario|market_research|public_research)/iu;
      const fieldIdentity = (entry) =>
        String(entry?.input_key ?? entry?.field_key ?? entry?.key ?? entry?.name ?? entry?.metric_key ?? "");
      const provenanceIdentity = (entry) =>
        String(entry?.kind ?? "") + " " +
        String(entry?.provenance ?? "") + " " +
        String(entry?.source_kind ?? "") + " " +
        String(entry?.source_type ?? "") + " " +
        String(entry?.origin ?? "");
      const isPublicResearchEntry = (entry) =>
        publicResearchPattern.test(provenanceIdentity(entry));
      const isPublicBenchmarkEntry = (entry) =>
        entry?.provenance === "public_benchmark" ||
        entry?.source_kind === "public_benchmark" ||
        entry?.source_type === "public_benchmark" ||
        entry?.origin === "public_benchmark";
      const isSourceFactEntry = (entry) =>
        entry?.kind === "source_fact" ||
        entry?.provenance === "source_fact" ||
        entry?.status === "source_fact";
      const publicAcceptedEntries = [
        ...(Array.isArray(job.accepted_entries) ? job.accepted_entries : []),
        ...acceptedInputs.filter((item) => isPublicBenchmarkEntry(item)),
      ];
      const guardedEntries = [
        ...publicAcceptedEntries,
        ...acceptedInputs,
        ...profileFields,
      ];
      const publicPrivateAliasPromotions = guardedEntries.filter((entry) =>
        isPublicResearchEntry(entry) && privateFieldPattern.test(fieldIdentity(entry)),
      );
      const publicSourceFactPromotions = guardedEntries.filter((entry) =>
        isPublicResearchEntry(entry) && isSourceFactEntry(entry),
      );
      const publicPrivateFillBlocked = publicPrivateAliasPromotions.length === 0;
      const noPublicSourceFactPromotion = publicSourceFactPromotions.length === 0;
      const scenarioKeys = ["conservative", "base", "optimistic"].filter(
        (key) => key in (scenarios.scenarios ?? {}),
      );
      const scenarioMetrics = Object.values(scenarios.scenarios ?? {})
        .flatMap((scenario) => Object.values(scenario?.metrics ?? {}));
      const renderedSourceTexts = Array.from(
        document.querySelectorAll('[data-research-source], [data-research-citation], [data-case-copilot-research-status] a[href]'),
      )
        .map((node) =>
          node.getAttribute("href") ||
          node.textContent?.replace(/\s+/gu, " ").trim() ||
          "",
        )
        .filter(Boolean);
      const visibleSources = renderedSourceTexts
        .map((item) => String(item ?? "").trim())
        .filter((item, index, items) =>
          item &&
          !/Smart[_ -]?University[_ -]?Full/iu.test(item) &&
          items.indexOf(item) === index,
        )
        .slice(0, 8);
      const launchPackText = `${markdown.text}\n${provenance.text}`;
      const launchPackContract = {
        forecast_2027_2031_clear:
          /(?:2027\s*[-–]\s*2031|2027[\s\S]*2028[\s\S]*2029[\s\S]*2030[\s\S]*2031)/u.test(launchPackText),
        housing_legal_fire_sanitary_gates_present:
          /(?:legal|юрид|правов|лиценз)/iu.test(launchPackText) &&
          /(?:fire|пожар)/iu.test(launchPackText) &&
          /(?:sanitary|санитар)/iu.test(launchPackText),
        platform_vs_housing_separated:
          /(?:platform|платформ)/iu.test(launchPackText) &&
          /(?:housing|общежит|жиль|проживан)/iu.test(launchPackText),
        provenance_appendix_present:
          provenance.text.length > 0 &&
          /(?:provenance|источник|founder_statement|public_benchmark|ai_scenario)/iu.test(provenance.text),
        rating_methodology_present: /(?:rating|рейтинг|methodology|методолог)/iu.test(launchPackText),
        tariff_and_lead_economics_present:
          /(?:tariff|тариф)/iu.test(launchPackText) &&
          /(?:lead|лид|conversion|конверс|CAC)/iu.test(launchPackText),
        tranche_plan_present: /(?:tranche|транш)/iu.test(launchPackText),
      };
      return {
        smartUniversitySinglePdfJourney: {
          case_identity: {
            asset_id: launchPackEvidence.asset_id,
            case_id: caseId,
            langgraph_checkpoint: analysisStatus.langgraph_checkpoint ?? {},
            research_job_id: jobId,
            selected_scenario_key: scenarios.selected_scenario_key,
            thread_id: thread.thread_id,
          },
          upload: {
            gate2_ready: args.gate2AcceptedReceiptVisible,
            pdf_uploaded:
              args.intakeEvidence?.selected_file_count === 1 &&
              args.intakeEvidence?.selected_file_mime_types?.every((type) => type === "application/pdf"),
            profile_source_grounded: profileFields.some(hasSourceFact),
            receipt_visible: args.gate2AcceptedReceiptVisible,
          },
          founder_gap_handling: {
            answered_or_skipped: thread.messages?.some((message) =>
              message.role === "user" &&
              String(message.content ?? "").toLowerCase() === "unknown",
            ) === true,
            unknown_answer_count: args.publicResearchPrep?.unknown_answer_count ?? 0,
            private_metrics_manual_or_file_only: publicPrivateFillBlocked,
            question_visible: args.questionVisible,
          },
          public_research: {
            acquisition_mode: job.acquisition_mode,
            explicit_consent: true,
            requested_acquisition_mode: job.requested_acquisition_mode,
            sanitized_sources: visibleSources.map((source) => ({
              as_of: String(job.updated_at ?? new Date().toISOString()).slice(0, 10),
              source_mode: job.acquisition_mode === "live_public_research" ? "live" : "offline",
              url: source,
            })),
            selected_acquisition_mode: job.selected_acquisition_mode,
            provenance_guard: {
              accepted_inputs_checked: Array.isArray(state.accepted_inputs),
              profile_fields_checked: profileFields.length > 0,
              public_private_aliases_blocked: publicPrivateFillBlocked,
            },
            scenario_change_evidence: {
              rendered_change_count: args.scenarioDeltaVisible?.rendered_change_count ?? 0,
              rendered_comparison_count: args.scenarioDeltaVisible?.rendered_comparison_count ?? 0,
            },
            scenario_delta_visible: args.scenarioDeltaVisible?.visible === true && scenarioKeys.length === 3,
            source_fact_promotion_blocked: publicPrivateFillBlocked && noPublicSourceFactPromotion,
            source_count: visibleSources.length,
            status: job.status || jobStatus,
            visible_sources: visibleSources,
          },
          scenarios: {
            keys: scenarioKeys,
            provenance_complete:
              scenarioMetrics.length > 0 &&
              scenarioMetrics.every(scenarioMetricHasProvenance),
            selected_key: scenarios.selected_scenario_key,
          },
          outputs: {
            actions_visible: args.actionsVisible,
            page_evidence: args.pageEvidence,
            launch_pack_downloaded:
              markdown.contentDisposition.includes("attachment") &&
              markdown.text.length > 0 &&
              provenance.text.length > 0,
            launch_pack_contract: launchPackContract,
            launch_pack_link_visible: Boolean(launchPackEvidence.link_visible && asset.asset_id === launchPackEvidence.asset_id),
            market_reconstruction_visible:
              args.marketReconstructionVisible &&
              (markdown.text.includes("## Market") ||
                markdown.text.includes("Market reconstruction") ||
                markdown.text.includes("рын") ||
                markdown.text.includes("Рын")),
            metrics_visible: args.metricsVisible,
            plan_7_30_60_90_visible:
              args.planHorizonVisible || /7[\s\S]*30[\s\S]*60[\s\S]*90/u.test(markdown.text),
            final_decision_accepted: Boolean(reportJson?.report_status || reportJson?.snapshot_id || reportHtml.text.length > 0),
            report_artifacts: {
              case_id: caseId,
              downloaded_formats: ["JSON", "HTML", "PDF"],
              html_path: `${reportRoot}/html`,
              html_sha256: reportHtmlSha256,
              json_path: `${reportRoot}/json`,
              json_sha256: reportJsonSha256,
              pdf_bounded: reportPdf.bounded,
              pdf_magic: reportPdf.magic,
              pdf_path: `${reportRoot}/pdf`,
              pdf_sha256: reportPdf.sha256,
              report_snapshot_id: reportSnapshot,
            },
            risks_visible: args.risksVisible,
          },
          restart: {
            process_restarted: false,
            same_case_ui_rehydrated: false,
            same_asset_reloaded: false,
            same_case_reloaded: false,
            same_research_job_reloaded: false,
            same_scenario_reloaded: false,
            same_thread_reloaded: false,
          },
        },
      };
    }})( ${JSON.stringify({
      actionsVisible,
      caseId,
      gate2AcceptedReceiptVisible,
      intakeEvidence,
      launchPackEvidence,
      marketReconstructionVisible,
      metricsVisible,
      pageEvidence: {
        action_plan: actionPlanPageEvidence,
        market: marketPageEvidence,
        metrics: metricsPageEvidence,
        risks: risksPageEvidence,
      },
      planHorizonVisible,
      publicResearchPrep,
      questionVisible,
      risksVisible,
      scenarioDeltaVisible,
    })} ).then((value) => JSON.stringify(value))`,
  );
  if (requireSmartUniversityLivePublicResearch) {
    const liveAuditEvidence = collectSmartUniversityLiveAuditEvidence(
      auditSpoolRoot,
      preRestartEvidence.smartUniversitySinglePdfJourney.case_identity.case_id,
      preRestartEvidence.smartUniversitySinglePdfJourney.case_identity.research_job_id,
    );
    preRestartEvidence = {
      smartUniversitySinglePdfJourney: {
        ...preRestartEvidence.smartUniversitySinglePdfJourney,
        case_identity: {
          ...preRestartEvidence.smartUniversitySinglePdfJourney.case_identity,
        },
        public_research: {
          ...preRestartEvidence.smartUniversitySinglePdfJourney.public_research,
          ...liveAuditEvidence,
        },
      },
    };
  }
  await captureSmartUniversityPreRestartScreenshot(preRestartEvidence);

  const journeyEvidence = preRestartEvidence.smartUniversitySinglePdfJourney;
  const restartFixture = {
    case_id: journeyEvidence.case_identity.case_id,
    fixture_name: "smart_university_single_pdf",
    launch_pack: {
      asset_id: journeyEvidence.case_identity.asset_id,
    },
    scenarios: {
      selected_key: journeyEvidence.case_identity.selected_scenario_key,
    },
  };
  const restartToken = caseCopilotRestartToken([restartFixture]);
  await requestCaseCopilotServiceRestart(
    caseCopilotRestartRequestPath,
    restartToken,
    [restartFixture],
  );
  const restartReady = await waitForCaseCopilotRestartReady(
    caseCopilotRestartReadyPath,
    restartToken,
  );
  await client.send("Page.reload", {}, sessionId);
  await waitForExpression(
    client,
    sessionId,
    "document.readyState === 'complete'",
    "smart_university_post_restart_page_ready",
    60_000,
  );
  await armCaseCopilotFetchDiagnostics(client, sessionId);
  await waitForExpression(
    client,
    sessionId,
    `Boolean(${smartUniversityPanelExpression(journeyEvidence.case_identity.case_id)})`,
    "smart_university_post_restart_same_case_ui",
    120_000,
  );
  const sameCaseUiRehydrated = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const panel = ${smartUniversityPanelExpression(journeyEvidence.case_identity.case_id)};
      return Boolean(
        panel?.querySelector("[data-case-copilot-research-status]") ||
        panel?.querySelector("[data-founder-scenario-metrics]") ||
        panel?.querySelector("[data-case-question-card]"),
      );
    })()`,
  );
  const postRestart = await evaluateBrowserJson(
    client,
    sessionId,
    `(${async function collectPostRestart(args) {
      async function requestJson(path) {
        const response = await fetch(path, {
          cache: "no-store",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
          if (!response.ok) {
            throw new Error(
            `smart_university_post_restart_request_failed path=${path} status=${response.status}`,
            );
        }
        return response.json();
      }
      async function requestText(path) {
        const response = await fetch(path, {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(
            `smart_university_post_restart_download_failed path=${path} status=${response.status}`,
          );
        }
        return response.text();
      }
      async function sha256Bytes(bytes) {
        const digest = await crypto.subtle.digest("SHA-256", bytes);
        return `sha256:${Array.from(new Uint8Array(digest))
          .map((byte) => byte.toString(16).padStart(2, "0"))
          .join("")}`;
      }
      async function sha256Text(text) {
        return sha256Bytes(new TextEncoder().encode(text));
      }
      function reportSnapshotId(reportJson) {
        return String(
          reportJson?.snapshot_id ??
          reportJson?.snapshotId ??
          reportJson?.report_snapshot_id ??
          reportJson?.metadata?.snapshot_id ??
          "",
        ).trim();
      }
      async function requestPdfContract(path) {
        const response = await fetch(path, {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(
            `smart_university_post_restart_pdf_download_failed path=${path} status=${response.status}`,
          );
        }
        const bytes = new Uint8Array(await response.arrayBuffer());
        return {
          magic: String.fromCharCode(...bytes.slice(0, 4)),
          sha256: await sha256Bytes(bytes),
        };
      }
      const [analysisStatus, thread, scenarios, job, asset, reportJsonDownload, reportHtml, reportPdf] = await Promise.all([
        requestJson(`/api/startup/cases/${encodeURIComponent(args.caseId)}/analysis`),
        requestJson(`/api/startup/cases/${encodeURIComponent(args.caseId)}/copilot/thread`),
        requestJson(`/api/startup/cases/${encodeURIComponent(args.caseId)}/scenarios`),
        requestJson(`/api/startup/cases/${encodeURIComponent(args.caseId)}/research/jobs/${encodeURIComponent(args.researchJobId)}`),
        requestJson(`/api/startup/cases/${encodeURIComponent(args.caseId)}/assets/${encodeURIComponent(args.assetId)}`),
        requestText(`/api/startup/cases/${encodeURIComponent(args.caseId)}/report/json`),
        requestText(`/api/startup/cases/${encodeURIComponent(args.caseId)}/report/html`),
        requestPdfContract(`/api/startup/cases/${encodeURIComponent(args.caseId)}/report/pdf`),
      ]);
      const reportJson = JSON.parse(reportJsonDownload);
      const reportArtifacts = {
        html_sha256: await sha256Text(reportHtml),
        json_sha256: await sha256Text(reportJsonDownload),
        pdf_sha256: reportPdf.sha256,
        report_snapshot_id: reportSnapshotId(reportJson),
      };
      const langgraphCheckpoint = analysisStatus.langgraph_checkpoint ?? {};
      return {
        process_restarted: args.restartReady?.status === "ready",
        same_case_ui_rehydrated: args.sameCaseUiRehydrated === true,
        same_asset_reloaded: asset.asset_id === args.assetId,
        same_case_reloaded: thread.case_id === args.caseId,
        same_research_job_reloaded: job.job_id === args.researchJobId,
        langgraph_checkpoint: langgraphCheckpoint,
        langgraph_checkpoint_reloaded:
          String(langgraphCheckpoint.thread_id ?? "") ===
            String(args.langgraphCheckpoint?.thread_id ?? "") &&
          String(langgraphCheckpoint.checkpoint_id ?? "") ===
            String(args.langgraphCheckpoint?.checkpoint_id ?? "") &&
          String(langgraphCheckpoint.checkpoint_hash ?? "") ===
            String(args.langgraphCheckpoint?.checkpoint_hash ?? "") &&
          Number(langgraphCheckpoint.data_revision) ===
            Number(args.langgraphCheckpoint?.data_revision),
        same_final_decision_reloaded: Boolean(
          reportJson?.report_status ||
          reportJson?.snapshot_id ||
          reportArtifacts.report_snapshot_id,
        ),
        same_report_artifacts_reloaded:
          reportPdf.magic === "%PDF" &&
          reportArtifacts.report_snapshot_id === args.reportArtifacts?.report_snapshot_id &&
          reportArtifacts.json_sha256 === args.reportArtifacts?.json_sha256 &&
          reportArtifacts.html_sha256 === args.reportArtifacts?.html_sha256 &&
          reportArtifacts.pdf_sha256 === args.reportArtifacts?.pdf_sha256,
        report_artifacts: reportArtifacts,
        same_scenario_reloaded: scenarios.selected_scenario_key === args.selectedScenarioKey,
        same_thread_reloaded: thread.thread_id === args.threadId,
      };
    }})( ${JSON.stringify({
      assetId: journeyEvidence.case_identity.asset_id,
      caseId: journeyEvidence.case_identity.case_id,
      langgraphCheckpoint: journeyEvidence.case_identity.langgraph_checkpoint,
      reportArtifacts: journeyEvidence.outputs.report_artifacts,
      researchJobId: journeyEvidence.case_identity.research_job_id,
      restartReady,
      sameCaseUiRehydrated,
      selectedScenarioKey: journeyEvidence.case_identity.selected_scenario_key,
      threadId: journeyEvidence.case_identity.thread_id,
    })} ).then((value) => JSON.stringify(value))`,
  );
  return {
    smartUniversitySinglePdfJourney: {
      ...journeyEvidence,
      restart: postRestart,
    },
  };
}

async function writeCaseCopilotBrowserEvidence(
  evidencePath,
  pageUrl,
  captureResult,
  fixtureSummary,
) {
  const scenarioJourney = validateCaseCopilotScenarioJourneyEvidence(
    captureResult.journey,
    fixtureSummary,
  );
  const evidenceRoot = dirname(evidencePath);
  mkdirSync(evidenceRoot, { recursive: true });
  const payload = {
    schema_version: CASE_COPILOT_BROWSER_EVIDENCE_SCHEMA_VERSION,
    base_url: new URL(pageUrl).origin,
    offline: true,
    caseCopilotScenarioJourney: scenarioJourney,
    network_external_calls: captureResult.networkViolations,
    browser_requests: captureResult.observedRequests,
    blocked_external_requests: captureResult.blockedExternalRequests,
    blocked_parser_injections: captureResult.blockedParserInjections,
    upload_bytes: fixtureSummary?.bytes ?? null,
    upload_mime_type: fixtureSummary?.mime_type ?? null,
    upload_sha256: fixtureSummary?.sha256 ?? null,
    screenshot: {
      path: evidenceRelativePath(evidencePath, captureResult.outputPath),
      width: captureResult.width,
      height: captureResult.height,
    },
  };
  writeFileSync(evidencePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  console.log(`case_copilot_browser_evidence_written path=${evidencePath}`);
}

async function writeSmartUniversitySinglePdfBrowserEvidence(
  evidencePath,
  pageUrl,
  captureResult,
  fixtureSummary,
  requireSmartUniversityLivePublicResearch = false,
) {
  const journey = validateSmartUniversitySinglePdfJourneyEvidence(
    captureResult.journey,
    fixtureSummary,
    { requireLivePublicResearch: requireSmartUniversityLivePublicResearch },
  );
  const evidenceRoot = dirname(evidencePath);
  mkdirSync(evidenceRoot, { recursive: true });
  const payload = {
    schema_version: "smart_university_single_pdf_browser_evidence@1",
    base_url: new URL(pageUrl).origin,
    offline: !requireSmartUniversityLivePublicResearch,
    smartUniversitySinglePdfJourney: journey,
    network_external_calls: captureResult.networkViolations,
    browser_requests: captureResult.observedRequests,
    blocked_external_requests: captureResult.blockedExternalRequests,
    blocked_parser_injections: captureResult.blockedParserInjections,
    upload_bytes: fixtureSummary?.bytes ?? null,
    upload_mime_type: fixtureSummary?.mime_type ?? null,
    upload_sha256: fixtureSummary?.sha256 ?? null,
    screenshot: {
      path: evidenceRelativePath(evidencePath, captureResult.outputPath),
      width: captureResult.width,
      height: captureResult.height,
    },
  };
  assertNoSensitiveSmartUniversityJourneyValue(payload);
  writeFileSync(evidencePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  console.log(`smart_university_single_pdf_browser_evidence_written path=${evidencePath}`);
}

class CdpClient {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    this.eventTasks = new Set();
    this.eventErrors = [];

    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        clearTimeout(pending.timer);
        if (message.error) {
          pending.reject(new Error(JSON.stringify(message.error)));
        } else {
          pending.resolve(message.result ?? {});
        }
        return;
      }
      if (message.method) {
        for (const listener of this.listeners.get(message.method) ?? []) {
          const task = Promise.resolve().then(() =>
            listener(message.params ?? {}, message.sessionId),
          );
          this.eventTasks.add(task);
          task
            .catch((error) => this.eventErrors.push(error))
            .finally(() => this.eventTasks.delete(task));
        }
      }
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  async drainEvents() {
    while (this.eventTasks.size > 0) {
      await Promise.allSettled([...this.eventTasks]);
    }
    if (this.eventErrors.length > 0) {
      throw new Error(`cdp_event_handler_failed count=${this.eventErrors.length}`);
    }
  }

  send(method, params = {}, sessionId, timeoutMilliseconds = 15_000) {
    const id = this.nextId++;
    return new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        rejectPromise(new Error(`cdp_command_timeout ${method}`));
      }, timeoutMilliseconds);
      this.pending.set(id, {
        reject: rejectPromise,
        resolve: resolvePromise,
        timer,
      });
      this.socket.send(
        JSON.stringify({
          id,
          method,
          params,
          ...(sessionId ? { sessionId } : {}),
        }),
      );
    });
  }

}

async function waitForDevTools(profileDirectory, browserProcess) {
  const activePortFile = join(profileDirectory, "DevToolsActivePort");
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (existsSync(activePortFile)) {
      try {
        const [port, websocketPath] = readFileSync(activePortFile, "utf8")
          .trim()
          .split(/\r?\n/);
        if (port && websocketPath) {
          return `ws://127.0.0.1:${port}${websocketPath}`;
        }
      } catch (error) {
        // Edge can briefly lock or replace DevToolsActivePort while starting on Windows.
        // Retry only those transient file states within the existing deadline; fail closed otherwise.
        if (!["EBUSY", "ENOENT"].includes(error?.code)) {
          throw error;
        }
      }
    }
    if (browserProcess.exitCode !== null) {
      throw new Error(`browser_exited code=${browserProcess.exitCode}`);
    }
    await sleep(50);
  }
  throw new Error("devtools_start_timeout");
}

async function connect(websocketUrl) {
  const socket = new WebSocket(websocketUrl);
  await new Promise((resolvePromise, rejectPromise) => {
    socket.addEventListener("open", resolvePromise, { once: true });
    socket.addEventListener("error", rejectPromise, { once: true });
  });
  return socket;
}

async function waitForExit(browserProcess, timeoutMilliseconds) {
  if (browserProcess.exitCode !== null) return;
  await Promise.race([
    new Promise((resolvePromise) =>
      browserProcess.once("exit", resolvePromise),
    ),
    sleep(timeoutMilliseconds),
  ]);
}

async function terminateBrowser(browserProcess) {
  if (browserProcess.exitCode !== null) return;
  if (process.platform === "win32") {
    await new Promise((resolvePromise) => {
      const killer = spawn(
        "taskkill.exe",
        ["/PID", String(browserProcess.pid), "/T", "/F"],
        { stdio: "ignore", windowsHide: true },
      );
      killer.once("exit", resolvePromise);
      killer.once("error", resolvePromise);
    });
    return;
  }
  browserProcess.kill("SIGKILL");
}

export function cleanupProfileDirectory(profileDirectory, removeDirectory = rmSync) {
  const resolvedProfileDirectory = resolve(profileDirectory);
  const resolvedTempDirectory = resolve(tmpdir());
  if (
    dirname(resolvedProfileDirectory) !== resolvedTempDirectory ||
    !basename(resolvedProfileDirectory).startsWith("founder-screenshot-cdp-")
  ) {
    return { status: "skipped", error_code: "profile_path_not_allowed" };
  }
  try {
    removeDirectory(resolvedProfileDirectory, {
      force: true,
      maxRetries: 10,
      recursive: true,
      retryDelay: 100,
    });
    return { status: "removed", error_code: null };
  } catch (error) {
    const errorCode =
      error && typeof error === "object" && "code" in error
        ? String(error.code)
        : "profile_cleanup_failed";
    console.warn(`capture_profile_cleanup_deferred code=${errorCode}`);
    return { status: "deferred", error_code: errorCode };
  }
}

function isAllowedBrowserRequest(rawUrl) {
  if (
    rawUrl.startsWith("about:") ||
    rawUrl.startsWith("blob:") ||
    rawUrl.startsWith("data:")
  ) {
    return true;
  }
  try {
    const parsed = new URL(rawUrl);
    return (
      ["http:", "https:", "ws:", "wss:"].includes(parsed.protocol) &&
      ["127.0.0.1", "::1", "localhost"].includes(parsed.hostname)
    );
  } catch {
    return false;
  }
}

function safeRequestOrigin(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return "invalid-url";
  }
}

function normalizeParserInjectionOrigin(rawOrigin) {
  if (!rawOrigin) throw new Error("blocked_parser_script_origin_invalid");
  try {
    const parsed = new URL(rawOrigin.trim());
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    ) {
      throw new Error("invalid");
    }
    return parsed.origin;
  } catch {
    throw new Error("blocked_parser_script_origin_invalid");
  }
}

export function normalizeOptionalOrigins(rawOrigins) {
  if (!rawOrigins) return undefined;
  const origins = String(rawOrigins)
    .split(",")
    .map((entry) => normalizeParserInjectionOrigin(entry))
    .filter(Boolean);
  return origins.length > 0 ? new Set(origins) : undefined;
}

async function assertServedMarkupHasNoExternalScripts(pageUrl) {
  if (!isAllowedBrowserRequest(pageUrl)) {
    throw new Error(`served_html_url_rejected origin=${safeRequestOrigin(pageUrl)}`);
  }
  const response = await fetch(pageUrl, {
    redirect: "error",
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) {
    throw new Error(`served_html_http_error status=${response.status}`);
  }
  const declaredBytes = Number(response.headers.get("content-length") ?? "0");
  if (declaredBytes > 2_000_000) {
    throw new Error(`served_html_too_large bytes=${declaredBytes}`);
  }
  const markup = await response.text();
  if (Buffer.byteLength(markup, "utf8") > 2_000_000) {
    throw new Error("served_html_too_large bytes=streamed");
  }
  const externalOrigins = [];
  const scriptSourcePattern = /<script\b[^>]*\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/giu;
  for (const match of markup.matchAll(scriptSourcePattern)) {
    const source = match[1] ?? match[2] ?? match[3] ?? "";
    const resolvedSource = new URL(source, pageUrl).toString();
    if (!isAllowedBrowserRequest(resolvedSource)) {
      externalOrigins.push(safeRequestOrigin(resolvedSource));
    }
  }
  if (externalOrigins.length > 0) {
    throw new Error(
      `served_html_external_script count=${externalOrigins.length} origins=${[...new Set(externalOrigins)].join(",")}`,
    );
  }
}

function isExplicitlyQuarantinedParserInjection(
  params,
  allowedBlockedParserScriptOrigins,
) {
  if (!allowedBlockedParserScriptOrigins) return false;
  const requestUrl = params.request?.url ?? "";
  return (
    allowedBlockedParserScriptOrigins.has(safeRequestOrigin(requestUrl)) &&
    params.type === "Script" &&
    params.initiator?.type === "parser" &&
    isAllowedBrowserRequest(params.documentURL ?? "") &&
    !params.redirectResponse
  );
}

async function evaluateValue(client, sessionId, expression) {
  const result = await client.send(
    "Runtime.evaluate",
    { awaitPromise: true, expression, returnByValue: true },
    sessionId,
  );
  return result.result.value;
}

async function describeBrowserWaitState(client, sessionId) {
  try {
    return await evaluateValue(
      client,
      sessionId,
      `(() => {
        const sanitizeBrowserDiagnosticText = (value) => String(value ?? "")
          .replace(/\\s+/gu, " ")
          .replace(
            /(?:sha256:[0-9a-f]{64}|\\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\\b|[A-Za-z]:[\\\\/][^\\s]+|\\bsk-[A-Za-z0-9_-]{8,}|[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,})/giu,
            "[redacted]",
          )
          .trim()
          .slice(0, 240);
        return ({
        activeView: document
          .querySelector("[data-founder-active-view]")
          ?.getAttribute("data-founder-active-view") ?? null,
        renderedViews: Array.from(document.querySelectorAll("[data-founder-view]"))
          .map((candidate) => ({
            view: candidate.getAttribute("data-founder-view"),
            visible: candidate.getClientRects().length > 0,
          })),
        actions: Array.from(document.querySelectorAll("[data-founder-action]"))
          .map((candidate) => ({
            action: candidate.getAttribute("data-founder-action"),
            disabled: Boolean(candidate.disabled),
            visible: candidate.getClientRects().length > 0,
            text: candidate.textContent?.replace(/\\s+/gu, " ").trim().slice(0, 120) ?? "",
          })),
        visibleAlerts: Array.from(document.querySelectorAll("[role=alert]"))
          .filter((candidate) => candidate.getClientRects().length > 0)
          .map((candidate) => sanitizeBrowserDiagnosticText(candidate.textContent))
          .filter(Boolean)
          .slice(0, 6),
        reportCenter: (() => {
          const view = document.querySelector('[data-founder-view="report-center"]');
          if (!view) return null;
          const reportSuffix = (value) => {
            const text = String(value ?? "");
            const match = text.match(/\\/report\\/(?:json|html|pdf)(?:\\?|$)/u);
            return match ? match[0].replace(/\\?.*$/u, "") : null;
          };
          return {
            text: sanitizeBrowserDiagnosticText(view.textContent),
            links: Array.from(view.querySelectorAll("a[href]"))
              .map((link) => ({
                hrefSuffix: reportSuffix(link.getAttribute("href")),
                ready: Boolean(link.querySelector('[data-ready="true"]')),
                text: sanitizeBrowserDiagnosticText(link.textContent),
                visible: link.getClientRects().length > 0,
              }))
              .slice(0, 12),
            readyMarkers: Array.from(view.querySelectorAll("[data-ready]"))
              .map((marker) => ({
                ready: marker.getAttribute("data-ready"),
                text: sanitizeBrowserDiagnosticText(marker.textContent),
                visible: marker.getClientRects().length > 0,
              }))
              .slice(0, 12),
          };
        })(),
        apiSnapshots: globalThis.__caseCopilotApiSnapshots ?? {},
        fetchEvents: Array.from(globalThis.__caseCopilotFetchEvents ?? [])
          .map((event) => ({
            body: event.body,
            elapsed_ms: event.elapsed_ms,
            method: event.method,
            status: event.status,
            statusText: event.statusText,
            url: event.url,
          })),
        });
      })()`,
    );
  } catch (error) {
    return { diagnosticError: error instanceof Error ? error.message : String(error) };
  }
}

async function waitForExpression(
  client,
  sessionId,
  expression,
  label,
  timeoutMilliseconds = 180_000,
) {
  const deadline = Date.now() + timeoutMilliseconds;
  let lastValue;
  while (Date.now() < deadline) {
    lastValue = await evaluateValue(client, sessionId, expression);
    if (lastValue) return lastValue;
    await sleep(200);
  }
  const diagnostic = await describeBrowserWaitState(client, sessionId);
  throw new Error(
    `browser_wait_timeout label=${label} last=${String(lastValue)} diagnostic=${JSON.stringify(diagnostic)}`,
  );
}

function buttonExpression(label, action) {
  const expected = JSON.stringify(label);
  return `(() => {
    const button = Array.from(document.querySelectorAll("button"))
      .find((candidate) => candidate.textContent?.includes(${expected}));
    if (!button || button.disabled) return false;
    ${action === "click" ? "button.click();" : ""}
    return true;
  })()`;
}

function actionSelectorExpression(actionName, action) {
  const selector = JSON.stringify(`[data-founder-action="${actionName}"]`);
  return `(() => {
    const button = document.querySelector(${selector});
    if (!button || button.disabled) return false;
    ${action === "click" ? "button.click();" : ""}
    return true;
  })()`;
}

async function armFounderIntakeObservation(client, sessionId) {
  const armed = await evaluateValue(
    client,
    sessionId,
    `(() => {
      const fileInput = document.querySelector('input[type="file"]');
      if (!fileInput) return false;
      globalThis.__queue5ObservedIntake = null;
      fileInput.addEventListener("change", (event) => {
        const files = event.currentTarget?.files
          ? Array.from(event.currentTarget.files)
          : [];
        globalThis.__queue5ObservedIntake = {
          fileCount: files.length,
          fileTypes: files.map((file) => file.type || "application/octet-stream")
        };
      }, { capture: true, once: true });
      return true;
    })()`,
  );
  if (!armed) throw new Error("founder_file_input_observer_missing");
}

async function observeFounderIntakeEvidence(client, sessionId, pdfUploadJourney) {
  const evidence = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const fileInput = document.querySelector('input[type="file"]');
        const files = fileInput ? Array.from(fileInput.files) : [];
        const observedIntake = globalThis.__queue5ObservedIntake;
        const selectedControls = Array.from(
          document.querySelectorAll("select, textarea, input:not([type='file'])"),
        ).filter((control) => {
          if (control.disabled) return false;
          const type = String(control.getAttribute("type") ?? "").toLowerCase();
          if (["button", "hidden", "submit", "reset"].includes(type)) return false;
          if (["checkbox", "radio"].includes(type)) return Boolean(control.checked);
          return Boolean(String(control.value ?? "").trim());
        });
        const names = selectedControls.map((control) =>
          [
            control.getAttribute("name"),
            control.getAttribute("id"),
            control.getAttribute("aria-label"),
            control.getAttribute("data-testid"),
            control.getAttribute("data-field"),
          ].filter(Boolean).join(" ").toLowerCase(),
        );
        delete globalThis.__queue5ObservedIntake;
        return JSON.stringify({
          fileCount: observedIntake?.fileCount ?? files.length,
          fileTypes: observedIntake?.fileTypes ?? files.map((file) => file.type || "application/octet-stream"),
          promptSelectionUsed: names.some((name) => name.includes("prompt")),
          industrySelectionUsed: names.some((name) => name.includes("industry")),
          selectedControlCount: selectedControls.length
        });
      })()`,
    ),
  );
  if (pdfUploadJourney) {
    const observedPdfUpload =
      evidence.fileCount === 1 &&
      evidence.fileTypes.every((type) => type === "application/pdf");
    if (!observedPdfUpload) {
      throw new Error(
        `browser_evidence_pdf_upload_not_observed file_count=${evidence.fileCount} file_types=${evidence.fileTypes.join(",")}`,
      );
    }
    if (
      evidence.promptSelectionUsed ||
      evidence.industrySelectionUsed ||
      evidence.selectedControlCount > 0
    ) {
      throw new Error(
        `browser_evidence_guided_selection_observed prompt=${evidence.promptSelectionUsed} industry=${evidence.industrySelectionUsed} controls=${evidence.selectedControlCount}`,
      );
    }
  }
  return {
    intake_mode: pdfUploadJourney ? "pdf_upload_only" : "fixture_upload",
    industry_selection_used: Boolean(evidence.industrySelectionUsed),
    observed_from_dom: true,
    prompt_selection_used: Boolean(evidence.promptSelectionUsed),
    selected_file_count: evidence.fileCount,
    selected_file_mime_types: evidence.fileTypes,
  };
}

async function driveFounderGtmJourney(
  client,
  sessionId,
  fixturePath,
  pdfUploadJourney = false,
) {
  await client.send("DOM.enable", {}, sessionId);
  const { root } = await client.send("DOM.getDocument", {}, sessionId);
  const { nodeId } = await client.send(
    "DOM.querySelector",
    { nodeId: root.nodeId, selector: 'input[type="file"]' },
    sessionId,
  );
  if (!nodeId) throw new Error("founder_file_input_missing");

  await armFounderIntakeObservation(client, sessionId);
  await client.send(
    "DOM.setFileInputFiles",
    { files: [resolve(fixturePath)], nodeId },
    sessionId,
  );
  await evaluateValue(
    client,
    sessionId,
    `(() => {
      const input = document.querySelector('input[type="file"]');
      if (!input) return false;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    })()`,
  );
  const intakeEvidence = await observeFounderIntakeEvidence(
    client,
    sessionId,
    pdfUploadJourney,
  );
  await waitForExpression(
    client,
    sessionId,
    buttonExpression("Начать анализ", "ready"),
    "founder_start_button",
  );
  await evaluateValue(
    client,
    sessionId,
    buttonExpression("Начать анализ", "click"),
  );
  await waitForExpression(
    client,
    sessionId,
    buttonExpression("Подтвердить и углубить", "ready"),
    "founder_gate2_button",
  );
  await evaluateValue(
    client,
    sessionId,
    buttonExpression("Подтвердить и углубить", "click"),
  );
  const requiredChartKeys = pdfUploadJourney
    ? ["readiness_coverage", "report_coverage"]
    : ["confirmed_metrics", "readiness_coverage", "report_coverage"];
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = document.getElementById("startup-gtm-title")?.closest("section");
      return Boolean(panel && !document.querySelector(".workflow-action-panel--error"));
    })()`,
    "startup_gtm_panel",
  );

  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = document.getElementById("startup-profile-title")?.closest("section");
      const fields = panel?.querySelectorAll(".startup-profile__grid .profile-field").length ?? 0;
      return Boolean(panel && fields === 18 && !document.querySelector(".workflow-action-panel--error"));
    })()`,
    "startup_profile_panel",
  );

  const profileContract = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `JSON.stringify({
        title: document.getElementById("startup-profile-title")?.textContent?.trim() ?? "",
        fields: document.querySelectorAll(".startup-profile__grid .profile-field").length,
        fieldNames: Array.from(document.querySelectorAll(".startup-profile__grid .profile-field"),
          (field) => field.getAttribute("data-profile-field") ?? ""),
        evidenceFields: document.querySelectorAll(".profile-field__references").length,
        statusFields: document.querySelectorAll('[class*="profile-field--"]').length
      })`,
    ),
  );
  const requiredProfileFields = [
    "startup_name",
    "problem",
    "icp",
    "traction",
    "metric_pack_candidates",
  ];
  if (
    profileContract.title !== "Что система знает, выводит и ещё уточняет" ||
    profileContract.fields !== 18 ||
    profileContract.statusFields !== 18 ||
    new Set(profileContract.fieldNames).size !== 18 ||
    profileContract.evidenceFields < 1 ||
    requiredProfileFields.some((field) => !profileContract.fieldNames.includes(field))
  ) {
    throw new Error(
      `profile_panel_contract_mismatch title=${profileContract.title} fields=${profileContract.fields} evidence=${profileContract.evidenceFields}`,
    );
  }
  console.log(
    `founder_profile_panel_visible fields=${profileContract.fields} evidence_fields=${profileContract.evidenceFields}`,
  );

  const contract = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `JSON.stringify({
        dimensions: document.querySelectorAll(".startup-gtm__dimensions .gtm-dimension").length,
        horizons: document.querySelectorAll(".gtm-launch-grid > article").length,
        title: document.getElementById("startup-gtm-title")?.textContent?.trim() ?? ""
      })`,
    ),
  );
  if (
    contract.title !== "План выхода на рынок" ||
    contract.dimensions !== 7 ||
    contract.horizons !== 4
  ) {
    throw new Error(
      `gtm_panel_contract_mismatch title=${contract.title} dimensions=${contract.dimensions} horizons=${contract.horizons}`,
    );
  }
  await evaluateValue(
    client,
    sessionId,
    `document.getElementById("startup-gtm-title")?.closest("section")
      ?.scrollIntoView({ block: "start" }); true`,
  );
  console.log(
    `founder_gtm_panel_visible dimensions=${contract.dimensions} horizons=${contract.horizons}`,
  );

  await waitForExpression(
    client,
    sessionId,
    buttonExpression("Сформировать отчёт", "ready"),
    "founder_gate3_button",
  );
  await evaluateValue(
    client,
    sessionId,
    buttonExpression("Сформировать отчёт", "click"),
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = document.getElementById("founder-report-title")?.closest("section");
      const sections = panel?.querySelectorAll("[data-report-section]").length ?? 0;
      return Boolean(panel && sections === 12 && !document.querySelector(".workflow-action-panel--error"));
    })()`,
    "founder_report_panel",
  );

  const reportContract = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `JSON.stringify({
        title: document.getElementById("founder-report-title")?.textContent?.trim() ?? "",
        sectionKeys: Array.from(document.querySelectorAll("[data-report-section]"),
          (section) => section.getAttribute("data-report-section") ?? ""),
        statuses: Array.from(document.querySelectorAll("[data-report-status]"),
          (section) => section.getAttribute("data-report-status") ?? ""),
        lineage: Boolean(document.querySelector("[data-report-lineage]"))
      })`,
    ),
  );
  const expectedReportSections = [
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
  ];
  const allowedReportStatuses = new Set([
    "SUPPORTED",
    "PARTIAL",
    "MISSING",
    "CONTRADICTION",
  ]);
  if (
    reportContract.title !== "Выводы, пробелы и следующие проверки" ||
    reportContract.sectionKeys.length !== 12 ||
    reportContract.statuses.length !== 12 ||
    new Set(reportContract.sectionKeys).size !== 12 ||
    expectedReportSections.some(
      (key, index) => reportContract.sectionKeys[index] !== key,
    ) ||
    reportContract.statuses.some((status) => !allowedReportStatuses.has(status)) ||
    !reportContract.lineage
  ) {
    throw new Error(
      `report_panel_contract_mismatch title=${reportContract.title} sections=${reportContract.sectionKeys.length} statuses=${reportContract.statuses.length} lineage=${reportContract.lineage}`,
    );
  }
  const frozenResearchContract = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const market = document.querySelector('[data-report-section="market_size"]');
        const competitors = document.querySelector('[data-report-section="competitors"]');
        const diligence = document.querySelector('[data-report-section="diligence_questions"]');
        const actionPlan = document.querySelector('[data-report-section="action_plan"]');
        const competitorText = competitors?.textContent ?? "";
        const categories = ["direct", "indirect", "substitute", "do_nothing", "potential_entrant"];
        return JSON.stringify({
          actionItems: actionPlan?.querySelectorAll("li").length ?? 0,
          competitorCategories: categories.filter((category) => competitorText.includes(category)),
          competitorFrozen: competitorText.includes("source_mode=frozen"),
          competitorRows: competitors?.querySelectorAll("tbody tr").length ?? 0,
          competitorSourceRefs: competitorText.includes("source_refs="),
          contradictionSummary: Array.from(
            document.querySelectorAll(".startup-profile__counts dt"),
          ).some((item) => item.textContent?.trim() === "Противоречия"),
          diligenceItems: diligence?.querySelectorAll("li").length ?? 0,
          marketFrozen: (market?.textContent ?? "").includes("source_mode=frozen"),
          marketUnknowns: (market?.textContent ?? "").includes("TAM/SAM/SOM")
        });
      })()`,
    ),
  );
  if (
    !frozenResearchContract.marketFrozen ||
    !frozenResearchContract.marketUnknowns ||
    frozenResearchContract.competitorRows < 5 ||
    !frozenResearchContract.competitorFrozen ||
    !frozenResearchContract.competitorSourceRefs ||
    frozenResearchContract.competitorCategories.length !== 5 ||
    !frozenResearchContract.contradictionSummary ||
    frozenResearchContract.diligenceItems < 1 ||
    frozenResearchContract.actionItems < 1
  ) {
    throw new Error(
      `frozen_research_contract_mismatch market_frozen=${frozenResearchContract.marketFrozen} market_unknowns=${frozenResearchContract.marketUnknowns} competitor_rows=${frozenResearchContract.competitorRows} competitor_categories=${frozenResearchContract.competitorCategories.length} diligence=${frozenResearchContract.diligenceItems} actions=${frozenResearchContract.actionItems}`,
    );
  }
  console.log(
    `founder_frozen_research_visible competitors=${frozenResearchContract.competitorRows} categories=${frozenResearchContract.competitorCategories.length} diligence=${frozenResearchContract.diligenceItems} actions=${frozenResearchContract.actionItems}`,
  );
  await evaluateValue(
    client,
    sessionId,
    `document.getElementById("founder-report-title")?.closest("section")
      ?.scrollIntoView({ block: "start" }); true`,
  );
  console.log(
    `founder_report_panel_visible sections=12 statuses=${reportContract.statuses.length} lineage=${reportContract.lineage}`,
  );

  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = document.getElementById("founder-readiness-title")?.closest("section");
      const stages = panel?.querySelectorAll("[data-analysis-stage]").length ?? 0;
      const dimensions = panel?.querySelectorAll("[data-readiness-dimension]").length ?? 0;
      const deepSections = panel?.querySelectorAll("[data-deep-section]").length ?? 0;
      return Boolean(panel && stages === 2 && dimensions > 0 && deepSections === 4 && !document.querySelector(".workflow-action-panel--error"));
    })()`,
    "founder_readiness_panel",
  );

  const readinessContract = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `JSON.stringify({
        title: document.getElementById("founder-readiness-title")?.textContent?.trim() ?? "",
        stageKeys: Array.from(document.querySelectorAll("[data-analysis-stage]"),
          (stage) => stage.getAttribute("data-analysis-stage") ?? ""),
        stageStatuses: Array.from(document.querySelectorAll("[data-analysis-status]"),
          (stage) => stage.getAttribute("data-analysis-status") ?? ""),
        readinessDimensions: document.querySelectorAll("[data-readiness-dimension]").length,
        deepSectionKeys: Array.from(document.querySelectorAll("[data-deep-section]"),
          (section) => section.getAttribute("data-deep-section") ?? ""),
        questions: document.getElementById("founder-readiness-questions-title")
          ?.closest("section")?.querySelectorAll("ol > li").length ?? 0,
        lineage: Boolean(document.querySelector(".founder-readiness__snapshot")),
        warning: Boolean(document.querySelector(".founder-readiness__warning"))
      })`,
    ),
  );
  const expectedReadinessStages = ["primary", "deep"];
  const expectedDeepSections = [
    "market_size",
    "competitors",
    "risks",
    "action_plan",
  ];
  if (
    readinessContract.title !== "Что подтверждено, что блокирует решение и что спросить дальше" ||
    readinessContract.stageKeys.length !== 2 ||
    expectedReadinessStages.some(
      (key, index) => readinessContract.stageKeys[index] !== key,
    ) ||
    readinessContract.stageStatuses.some((status) => status !== "available") ||
    readinessContract.readinessDimensions < 1 ||
    readinessContract.deepSectionKeys.length !== 4 ||
    expectedDeepSections.some(
      (key, index) => readinessContract.deepSectionKeys[index] !== key,
    ) ||
    readinessContract.questions > 3 ||
    !readinessContract.lineage ||
    readinessContract.warning
  ) {
    throw new Error(
      `readiness_panel_contract_mismatch title=${readinessContract.title} stages=${readinessContract.stageKeys.length} dimensions=${readinessContract.readinessDimensions} deep=${readinessContract.deepSectionKeys.length} questions=${readinessContract.questions} lineage=${readinessContract.lineage} warning=${readinessContract.warning}`,
    );
  }
  await evaluateValue(
    client,
    sessionId,
    `document.getElementById("founder-readiness-title")?.closest("section")
      ?.scrollIntoView({ block: "start" }); true`,
  );
  console.log(
    `founder_readiness_panel_visible stages=2 dimensions=${readinessContract.readinessDimensions} deep_sections=4 questions=${readinessContract.questions} lineage=${readinessContract.lineage}`,
  );

  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = document.getElementById("founder-charts-title")?.closest("section");
      const charts = Array.from(
        panel?.querySelectorAll("[data-founder-chart][data-chart-key]") ?? [],
      );
      const keys = charts.map((chart) => chart.getAttribute("data-chart-key") ?? "");
      const required = ${JSON.stringify(requiredChartKeys)};
      const points = panel?.querySelectorAll("[data-chart-point]").length ?? 0;
      const lineage = panel?.querySelectorAll("[data-chart-lineage]").length ?? 0;
      return Boolean(
        panel &&
          charts.length >= required.length &&
          points >= 6 &&
          lineage === charts.length &&
          required.every((key) => keys.includes(key)) &&
          !document.querySelector(".workflow-action-panel--error")
      );
    })()`,
    "founder_charts_panel",
  );
  const chartsContract = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = document.getElementById("founder-charts-title")?.closest("section");
        return JSON.stringify({
          keys: Array.from(panel?.querySelectorAll("[data-founder-chart][data-chart-key]") ?? [],
            (chart) => chart.getAttribute("data-chart-key") ?? ""),
          lineage: panel?.querySelectorAll("[data-chart-lineage]").length ?? 0,
          points: panel?.querySelectorAll("[data-chart-point]").length ?? 0,
          title: document.getElementById("founder-charts-title")?.textContent?.trim() ?? ""
        });
      })()`,
    ),
  );
  if (
    chartsContract.keys.length < requiredChartKeys.length ||
    chartsContract.points < 6 ||
    chartsContract.lineage !== chartsContract.keys.length ||
    requiredChartKeys.some((key) => !chartsContract.keys.includes(key))
  ) {
    throw new Error(
      `charts_panel_contract_mismatch title=${chartsContract.title} charts=${chartsContract.keys.length} points=${chartsContract.points} lineage=${chartsContract.lineage}`,
    );
  }
  await evaluateValue(
    client,
    sessionId,
    `document.getElementById("founder-charts-title")?.closest("section")
      ?.scrollIntoView({ block: "start" }); true`,
  );
  console.log(
    `founder_charts_panel_visible charts=${chartsContract.keys.length} points=${chartsContract.points} lineage=${chartsContract.lineage}`,
  );

  await waitForExpression(
    client,
    sessionId,
    buttonExpression("Зафиксировать версию", "ready"),
    "founder_gate4_button",
  );
  const draftArtifacts = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const nav = document.querySelector("nav.workflow-artifacts");
        const links = Object.fromEntries(
          Array.from(nav?.querySelectorAll("a") ?? [], (link) => [
            link.textContent?.trim() ?? "",
            link.getAttribute("href") ?? "",
          ]),
        );
        return JSON.stringify({
          disabledPdf: Array.from(nav?.querySelectorAll('span[aria-disabled="true"]') ?? [])
            .some((item) => item.textContent?.trim() === "PDF после фиксации"),
          html: links.HTML ?? "",
          json: links.JSON ?? "",
          pdf: links.PDF ?? ""
        });
      })()`,
    ),
  );
  const draftCaseMatch = draftArtifacts.json.match(
    /^\/api\/startup\/cases\/([^/]+)\/report\/json$/,
  );
  if (
    !draftCaseMatch ||
    draftArtifacts.html !==
      `/api/startup/cases/${draftCaseMatch[1]}/report/html` ||
    draftArtifacts.pdf ||
    !draftArtifacts.disabledPdf
  ) {
    throw new Error(
      `gate4_artifact_contract_mismatch phase=draft json=${draftArtifacts.json} html=${draftArtifacts.html} pdf=${draftArtifacts.pdf} disabled=${draftArtifacts.disabledPdf}`,
    );
  }
  const draftCaseId = draftCaseMatch[1];

  await evaluateValue(
    client,
    sessionId,
    buttonExpression("Зафиксировать версию", "click"),
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = document.querySelector(".workflow-action-panel--report_pdf_ready");
      const pdf = Array.from(document.querySelectorAll("nav.workflow-artifacts a"))
        .find((link) => link.textContent?.trim() === "PDF");
      return Boolean(panel && pdf && !document.querySelector(".workflow-action-panel--error"));
    })()`,
    "founder_gate4_pdf",
  );

  const approvedArtifacts = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const nav = document.querySelector("nav.workflow-artifacts");
        const links = Object.fromEntries(
          Array.from(nav?.querySelectorAll("a") ?? [], (link) => [
            link.textContent?.trim() ?? "",
            {
              href: link.getAttribute("href") ?? "",
              origin: new URL(link.href, window.location.href).origin
            },
          ]),
        );
        return JSON.stringify({ links, origin: window.location.origin });
      })()`,
    ),
  );
  const approvedCaseMatch = approvedArtifacts.links.JSON?.href.match(
    /^\/api\/startup\/cases\/([^/]+)\/report\/json$/,
  );
  const approvedCaseId = approvedCaseMatch?.[1] ?? "";
  const expectedApprovedPaths = {
    HTML: `/api/startup/cases/${approvedCaseId}/report/html`,
    JSON: `/api/startup/cases/${approvedCaseId}/report/json`,
    PDF: `/api/startup/cases/${approvedCaseId}/report/pdf`,
  };
  if (
    !approvedCaseMatch ||
    approvedCaseId !== draftCaseId ||
    Object.entries(expectedApprovedPaths).some(
      ([name, path]) =>
        approvedArtifacts.links[name]?.href !== path ||
        approvedArtifacts.links[name]?.origin !== approvedArtifacts.origin,
    )
  ) {
    throw new Error(
      `gate4_artifact_contract_mismatch phase=approved draft_case=${draftCaseId} approved_case=${approvedCaseId} links=${JSON.stringify(approvedArtifacts.links)}`,
    );
  }

  const pdfResult = await client.send(
    "Runtime.evaluate",
    {
      awaitPromise: true,
      expression: `(async () => {
        const response = await fetch(${JSON.stringify(expectedApprovedPaths.PDF)}, {
          headers: { Accept: "application/pdf" }
        });
        const contentLengthHeader = response.headers.get("content-length");
        const contentLength = contentLengthHeader === null
          ? null
          : Number(contentLengthHeader);
        if (
          contentLength !== null &&
          (!Number.isSafeInteger(contentLength) ||
            contentLength < 4 ||
            contentLength > ${MAX_SMOKE_PDF_BYTES})
        ) {
          return JSON.stringify({
            bounded: false,
            contentLength,
            contentType: response.headers.get("content-type") ?? "",
            firstBytes: [],
            ok: response.ok,
            status: response.status,
            totalBytes: 0
          });
        }
        const reader = response.body?.getReader();
        if (!reader) {
          return JSON.stringify({
            bounded: false,
            contentLength,
            contentType: response.headers.get("content-type") ?? "",
            firstBytes: [],
            ok: response.ok,
            status: response.status,
            totalBytes: 0
          });
        }
        const firstBytes = [];
        let totalBytes = 0;
        let exceededLimit = false;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (!value) continue;
          totalBytes += value.byteLength;
          for (const byte of value) {
            if (firstBytes.length === 4) break;
            firstBytes.push(byte);
          }
          if (totalBytes > ${MAX_SMOKE_PDF_BYTES}) {
            exceededLimit = true;
            await reader.cancel();
            break;
          }
        }
        return JSON.stringify({
          bounded:
            !exceededLimit &&
            totalBytes >= 4 &&
            (contentLength === null || totalBytes === contentLength),
          contentLength,
          contentType: response.headers.get("content-type") ?? "",
          firstBytes,
          ok: response.ok,
          status: response.status,
          totalBytes
        });
      })()`,
      returnByValue: true,
    },
    sessionId,
  );
  const pdfContract = JSON.parse(pdfResult.result.value);
  const expectedPdfMagic = [37, 80, 68, 70];
  if (
    !pdfContract.ok ||
    !pdfContract.bounded ||
    !pdfContract.contentType.toLowerCase().includes("application/pdf") ||
    pdfContract.firstBytes.length !== expectedPdfMagic.length ||
    pdfContract.firstBytes.some(
      (value, index) => value !== expectedPdfMagic[index],
    )
  ) {
    throw new Error(
      `gate4_artifact_contract_mismatch phase=pdf status=${pdfContract.status} bounded=${pdfContract.bounded} content_length=${pdfContract.contentLength} total_bytes=${pdfContract.totalBytes} content_type=${pdfContract.contentType} magic=${pdfContract.firstBytes.join(",")}`,
    );
  }
  const gate4ScrollContract = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        document.documentElement.style.scrollBehavior = "auto";
        const panel = document.querySelector(".workflow-action-panel--report_pdf_ready");
        if (!panel) return JSON.stringify({ found: false });
        const targetTop = panel.getBoundingClientRect().top + window.scrollY;
        window.scrollTo(0, Math.max(0, targetTop - 16));
        const rect = panel.getBoundingClientRect();
        return JSON.stringify({
          bottom: rect.bottom,
          found: true,
          innerHeight: window.innerHeight,
          scrollY: window.scrollY,
          targetTop,
          top: rect.top
        });
      })()`,
    ),
  );
  console.log(
    `founder_gate4_scroll found=${gate4ScrollContract.found} top=${gate4ScrollContract.top} bottom=${gate4ScrollContract.bottom} viewport=${gate4ScrollContract.innerHeight} scroll_y=${gate4ScrollContract.scrollY} target=${gate4ScrollContract.targetTop}`,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = document.querySelector(".workflow-action-panel--report_pdf_ready");
      const rect = panel?.getBoundingClientRect();
      return Boolean(rect && rect.top >= 0 && rect.top < window.innerHeight && rect.bottom > 0);
    })()`,
    "founder_gate4_panel_in_view",
    5_000,
  );
  console.log(
    `founder_gate4_pdf_ready json=true html=true pdf=true bytes=${pdfContract.totalBytes}`,
  );

  const chartsScrollContract = JSON.parse(
    await evaluateValue(
      client,
      sessionId,
      `(() => {
        const panel = document.getElementById("founder-charts-title")?.closest("section");
        if (!panel) return JSON.stringify({ found: false });
        const targetTop = panel.getBoundingClientRect().top + window.scrollY;
        window.scrollTo(0, Math.max(0, targetTop - 16));
        const rect = panel.getBoundingClientRect();
        return JSON.stringify({
          bottom: rect.bottom,
          found: true,
          innerHeight: window.innerHeight,
          scrollY: window.scrollY,
          targetTop,
          top: rect.top
        });
      })()`,
    ),
  );
  console.log(
    `founder_charts_scroll found=${chartsScrollContract.found} top=${chartsScrollContract.top} bottom=${chartsScrollContract.bottom} viewport=${chartsScrollContract.innerHeight} scroll_y=${chartsScrollContract.scrollY} target=${chartsScrollContract.targetTop}`,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const panel = document.getElementById("founder-charts-title")?.closest("section");
      const rect = panel?.getBoundingClientRect();
      return Boolean(rect && rect.top >= 0 && rect.top < window.innerHeight && rect.bottom > 0);
    })()`,
    "founder_charts_panel_in_view",
    5_000,
  );
  await waitForExpression(
    client,
    sessionId,
    `(() => {
      const point = document.getElementById("founder-charts-title")
        ?.closest("section")
        ?.querySelector("[data-chart-point]");
      const rect = point?.getBoundingClientRect();
      return Boolean(rect && rect.top < window.innerHeight && rect.bottom > 0);
    })()`,
    "founder_chart_point_in_view",
    5_000,
  );
  return {
    caseId: approvedCaseId,
    intakeEvidence,
    reportPaths: expectedApprovedPaths,
    profileFields: profileContract.fields,
    gtmDimensions: contract.dimensions,
    readinessDimensions: readinessContract.readinessDimensions,
    chartCards: chartsContract.keys.length,
    chartPoints: chartsContract.points,
    competitorCategories: frozenResearchContract.competitorCategories.length,
    competitorRows: frozenResearchContract.competitorRows,
    diligenceQuestions: frozenResearchContract.diligenceItems,
    actionPlanItems: frozenResearchContract.actionItems,
    marketEvidenceFrozen: frozenResearchContract.marketFrozen,
    marketUnknownsExplicit: frozenResearchContract.marketUnknowns,
  };
}

async function capture(
  browserPath,
  url,
  outputPath,
  viewport,
  fixturePath,
  allowedBlockedParserScriptOrigin,
  additionalCapture,
  pdfUploadJourney = false,
  desktopStateSuitePath,
  desktopStateSuiteAdminUrl = "http://127.0.0.1:8501/",
  advisorAnswer = DEFAULT_ADVISOR_ANSWER,
  invalidAdvisorAnswer = DEFAULT_INVALID_ADVISOR_ANSWER,
  requireCaseCopilotScenarioJourney = false,
  caseCopilotRestartRequestPath,
  caseCopilotRestartReadyPath,
  requireSmartUniversitySinglePdfJourney = false,
  requireSmartUniversityLivePublicResearch = false,
  auditSpoolRoot,
) {
  await assertServedMarkupHasNoExternalScripts(url);
  const profileDirectory = mkdtempSync(
    join(tmpdir(), "founder-screenshot-cdp-"),
  );
  const browserProcess = spawn(
    browserPath,
    [
      "--headless=new",
      "--disable-gpu",
      "--disable-background-networking",
      "--disable-extensions",
      "--disable-sync",
      "--disable-component-update",
      "--metrics-recording-only",
      "--no-first-run",
      "--no-default-browser-check",
      "--remote-debugging-port=0",
      `--user-data-dir=${profileDirectory}`,
      "about:blank",
    ],
    { stdio: "ignore", windowsHide: true },
  );

  let client;
  let socket;
  let journey;
  try {
    console.log(`capture_started label=${viewport.label}`);
    const websocketUrl = await waitForDevTools(
      profileDirectory,
      browserProcess,
    );
    socket = await connect(websocketUrl);
    client = new CdpClient(socket);

    const { targetId } = await client.send("Target.createTarget", {
      url: "about:blank",
    });
    const { sessionId } = await client.send("Target.attachToTarget", {
      flatten: true,
      targetId,
    });
    await client.send("Page.enable", {}, sessionId);
    await client.send("Runtime.enable", {}, sessionId);
    const browserNetworkViolations = [];
    const browserNetworkInjections = [];
    const classifiedExternalRequestIds = new Set();
    const blockedExternalNetworkIds = new Set();
    const validatedBlockedExternalNetworkIds = new Set();
    let blockedExternalRequests = 0;
    let observedBrowserRequests = 0;
    client.on("Network.requestWillBeSent", (params, eventSessionId) => {
      if (eventSessionId !== sessionId) return;
      observedBrowserRequests += 1;
      const requestUrl = params.request?.url ?? "";
      if (!isAllowedBrowserRequest(requestUrl)) {
        classifiedExternalRequestIds.add(params.requestId);
        const requestEvidence = `${safeRequestOrigin(requestUrl)}:${params.type ?? "unknown"}:${params.initiator?.type ?? "unknown"}`;
        if (
          isExplicitlyQuarantinedParserInjection(
            params,
            allowedBlockedParserScriptOrigin,
          )
        ) {
          browserNetworkInjections.push(requestEvidence);
        } else {
          browserNetworkViolations.push(requestEvidence);
        }
      }
    });
    client.on("Fetch.requestPaused", async (params, eventSessionId) => {
      if (eventSessionId !== sessionId) return;
      const requestUrl = params.request?.url ?? "";
      if (isAllowedBrowserRequest(requestUrl)) {
        await client.send(
          "Fetch.continueRequest",
          { requestId: params.requestId },
          sessionId,
        );
        return;
      }
      blockedExternalRequests += 1;
      if (params.networkId) {
        blockedExternalNetworkIds.add(params.networkId);
      } else {
        browserNetworkViolations.push(
          `${safeRequestOrigin(requestUrl)}:unattributed:fetch`,
        );
      }
      await client.send(
        "Fetch.failRequest",
        { errorReason: "BlockedByClient", requestId: params.requestId },
        sessionId,
      );
    });
    await client.send("Network.enable", {}, sessionId);
    await client.send(
      "Network.setUserAgentOverride",
      { userAgent: "FounderOfflineSmoke/1.0" },
      sessionId,
    );
    await client.send(
      "Fetch.enable",
      { patterns: [{ requestStage: "Request", urlPattern: "*" }] },
      sessionId,
    );
    async function applyViewport(targetViewport) {
      await client.send(
        "Emulation.setDeviceMetricsOverride",
        {
          deviceScaleFactor: 1,
          height: targetViewport.height,
          mobile: targetViewport.mobile,
          screenHeight: targetViewport.height,
          screenOrientation: {
            angle: 0,
            type: targetViewport.mobile ? "portraitPrimary" : "landscapePrimary",
          },
          screenWidth: targetViewport.width,
          width: targetViewport.width,
        },
        sessionId,
      );
    }

    let lastEvidenceStats = {
      blockedExternalRequests: 0,
      blockedParserInjections: 0,
      networkViolations: 0,
      observedRequests: 0,
    };

    async function collectCaptureEvidenceStats(targetViewport) {
      await client.drainEvents();
      for (const networkId of blockedExternalNetworkIds) {
        if (
          !validatedBlockedExternalNetworkIds.has(networkId) &&
          !classifiedExternalRequestIds.has(networkId)
        ) {
          browserNetworkViolations.push("unknown-origin:unclassified:fetch");
        }
        validatedBlockedExternalNetworkIds.add(networkId);
      }
      if (browserNetworkViolations.length > 0) {
        throw new Error(
          `browser_network_violation count=${browserNetworkViolations.length} origins=${[...new Set(browserNetworkViolations)].join(",")}`,
        );
      }
      if (
        browserNetworkInjections.length > lastEvidenceStats.blockedParserInjections
      ) {
        console.log(
          `browser_network_injection_blocked label=${targetViewport.label} count=${browserNetworkInjections.length - lastEvidenceStats.blockedParserInjections} origins=${[...new Set(browserNetworkInjections.map((entry) => entry.replace(/:[^:]+:[^:]+$/, "")))].join(",")}`,
        );
      }
      console.log(
        `browser_network_no_egress label=${targetViewport.label} requests=${observedBrowserRequests - lastEvidenceStats.observedRequests} blocked_external=${blockedExternalRequests - lastEvidenceStats.blockedExternalRequests}`,
      );
      const evidenceStats = {
        blockedExternalRequests:
          blockedExternalRequests - lastEvidenceStats.blockedExternalRequests,
        blockedParserInjections:
          browserNetworkInjections.length -
          lastEvidenceStats.blockedParserInjections,
        networkViolations:
          browserNetworkViolations.length - lastEvidenceStats.networkViolations,
        observedRequests: observedBrowserRequests - lastEvidenceStats.observedRequests,
      };
      lastEvidenceStats = {
        blockedExternalRequests,
        blockedParserInjections: browserNetworkInjections.length,
        networkViolations: browserNetworkViolations.length,
        observedRequests: observedBrowserRequests,
      };
      return evidenceStats;
    }

    async function accumulateCaptureEvidenceStats(captureResult, targetViewport) {
      const evidenceStats = await collectCaptureEvidenceStats(targetViewport);
      for (const field of CAPTURE_EVIDENCE_FIELDS) {
        captureResult[field] += evidenceStats[field];
      }
      return captureResult;
    }

    async function captureViewportArtifact(targetOutputPath, targetViewport) {
      const evidenceStats = await collectCaptureEvidenceStats(targetViewport);
      const geometryResult = await client.send(
        "Runtime.evaluate",
        {
          expression: `JSON.stringify({
            bodyScrollHeight: document.body.scrollHeight,
            bodyScrollWidth: document.body.scrollWidth,
            clientHeight: document.documentElement.clientHeight,
            clientWidth: document.documentElement.clientWidth,
            documentScrollHeight: document.documentElement.scrollHeight,
            innerHeight: window.innerHeight,
            innerWidth: window.innerWidth,
            scrollX: window.scrollX,
            scrollY: window.scrollY,
            scrollWidth: document.documentElement.scrollWidth
          })`,
          returnByValue: true,
        },
        sessionId,
      );
      const geometry = JSON.parse(geometryResult.result.value);
      if (geometry.innerWidth !== targetViewport.width) {
        throw new Error(
          `viewport_mismatch expected=${targetViewport.width} actual=${geometry.innerWidth}`,
        );
      }
      if (
        geometry.scrollWidth > geometry.innerWidth ||
        geometry.bodyScrollWidth > geometry.innerWidth
      ) {
        throw new Error(
          `horizontal_overflow viewport=${geometry.innerWidth} document=${geometry.scrollWidth} body=${geometry.bodyScrollWidth}`,
        );
      }

      const screenshot = await client.send(
        "Page.captureScreenshot",
        {
          captureBeyondViewport: false,
          clip: {
            height: targetViewport.height,
            scale: 1,
            width: targetViewport.width,
            x: geometry.scrollX,
            y: geometry.scrollY,
          },
          format: "png",
          fromSurface: true,
        },
        sessionId,
      );
      mkdirSync(dirname(targetOutputPath), { recursive: true });
      writeFileSync(targetOutputPath, Buffer.from(screenshot.data, "base64"));
      console.log(
        `viewport_geometry label=${targetViewport.label} inner=${geometry.innerWidth}x${geometry.innerHeight} scroll=${geometry.scrollWidth}x${geometry.documentScrollHeight} body=${geometry.bodyScrollWidth}x${geometry.bodyScrollHeight}`,
      );
      const result = {
        bodyScrollHeight: geometry.bodyScrollHeight,
        bodyScrollWidth: geometry.bodyScrollWidth,
        blockedExternalRequests: evidenceStats.blockedExternalRequests,
        blockedParserInjections: evidenceStats.blockedParserInjections,
        documentScrollHeight: geometry.documentScrollHeight,
        documentScrollWidth: geometry.scrollWidth,
        height: targetViewport.height,
        innerHeight: geometry.innerHeight,
        innerWidth: geometry.innerWidth,
        journey,
        networkViolations: evidenceStats.networkViolations,
        observedRequests: evidenceStats.observedRequests,
        outputPath: targetOutputPath,
        width: targetViewport.width,
      };
      return result;
    }

    async function captureDesktopState(file) {
      await client.send(
        "Runtime.evaluate",
        {
          awaitPromise: true,
          expression:
            "new Promise((resolve) => { window.scrollTo({ top: 0, left: 0, behavior: 'instant' }); requestAnimationFrame(() => requestAnimationFrame(resolve)); })",
        },
        sessionId,
      );
      const captured = await captureViewportArtifact(
        join(desktopStateSuitePath, file),
        viewport,
      );
      const overflow = assertDesktopStateCaptureFitsViewport(file, captured);
      captured.verticalOverflowPx = overflow.verticalOverflowPx;
      console.log(
        `desktop_state_viewport_fits state=${file} viewportHeight=${captured.innerHeight} documentScrollHeight=${captured.documentScrollHeight} bodyScrollHeight=${captured.bodyScrollHeight} verticalOverflowPx=${captured.verticalOverflowPx}`,
      );
      return captured;
    }

    async function clickButton(
      label,
      waitSelector,
      timeoutMilliseconds = 30_000,
      waitLabel = `desktop_suite_button_${label}`,
    ) {
      await waitForExpression(
        client,
        sessionId,
        buttonExpression(label, "click"),
        waitLabel,
        timeoutMilliseconds,
      );
      if (waitSelector) {
        await waitForExpression(
          client,
          sessionId,
          `Boolean(document.querySelector(${JSON.stringify(waitSelector)}))`,
          `desktop_suite_view_${waitSelector}`,
          30_000,
        );
      }
    }

    async function clickAction(
      actionName,
      waitSelector,
      timeoutMilliseconds = 30_000,
      waitLabel = `desktop_suite_action_${actionName}`,
    ) {
      await waitForExpression(
        client,
        sessionId,
        actionSelectorExpression(actionName, "click"),
        waitLabel,
        timeoutMilliseconds,
      );
      if (waitSelector) {
        await waitForExpression(
          client,
          sessionId,
          `Boolean(document.querySelector(${JSON.stringify(waitSelector)}))`,
          `desktop_suite_view_${waitSelector}`,
          30_000,
        );
      }
    }

    async function clickSidebar(label, waitSelector) {
      const expected = JSON.stringify(label);
      await waitForExpression(
        client,
        sessionId,
        `(() => {
          const button = Array.from(document.querySelectorAll("nav.founder-sidebar__nav button"))
            .find((candidate) => candidate.textContent?.trim().includes(${expected}));
          return Boolean(button && !button.disabled);
        })()`,
        `desktop_suite_nav_${label}`,
        30_000,
      );
      await evaluateValue(
        client,
        sessionId,
        `(() => {
          const button = Array.from(document.querySelectorAll("nav.founder-sidebar__nav button"))
            .find((candidate) => candidate.textContent?.trim().includes(${expected}));
          button?.click();
          return true;
        })()`,
      );
      await waitForExpression(
        client,
        sessionId,
        `Boolean(document.querySelector(${JSON.stringify(waitSelector)}))`,
        `desktop_suite_view_${waitSelector}`,
        30_000,
      );
    }

    async function setManualAdvisorAnswer(answer) {
      await waitForExpression(
        client,
        sessionId,
        `Boolean(document.querySelector('textarea[aria-label="Ручной ответ советнику"]'))`,
        "desktop_suite_advisor_manual_input",
        10_000,
      );
      await evaluateValue(
        client,
        sessionId,
        `(() => {
          const input = document.querySelector('textarea[aria-label="Ручной ответ советнику"]');
          if (!input) return false;
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
          setter?.call(input, ${JSON.stringify(answer)});
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()`,
      );
      await waitForExpression(
        client,
        sessionId,
        `new Promise((resolve) => {
          requestAnimationFrame(() => {
            requestAnimationFrame(() => setTimeout(() => resolve(true), 1_000));
          });
        })`,
        "desktop_suite_advisor_answer_settle",
        5_000,
      );
    }

    async function assertManualAdvisorAnswerRejected() {
      await waitForExpression(
        client,
        sessionId,
        `(() => {
          const page = document.querySelector('[data-founder-advisor-page="advisor-answer"]');
          const input = page?.querySelector('textarea[aria-label="Ручной ответ советнику"]');
          return Boolean(
            page &&
            input?.getAttribute("aria-invalid") === "true" &&
            page.querySelector('[role="alert"]')?.textContent?.includes("Ответ не подходит к текущему вопросу")
          );
        })()`,
        "desktop_suite_advisor_invalid_answer_inline_feedback",
        30_000,
      );
      console.log("founder_advisor_invalid_answer_rejected_inline");
    }

    async function collectDesktopSuitePublicApiEvidence(caseId) {
      const apiPaths = buildDesktopSuitePublicApiPaths(caseId);
      const result = await client.send(
        "Runtime.evaluate",
        {
          awaitPromise: true,
          expression: `(async () => {
            const paths = ${JSON.stringify(apiPaths)};
            const entries = await Promise.all(
              Object.entries(paths).map(async ([key, path]) => {
                const response = await window.fetch(path, {
                  headers: { Accept: "application/json" }
                });
                if (!response.ok) {
                  throw new Error(\`desktop_suite_public_api_http_error key=\${key} status=\${response.status}\`);
                }
                return [key, await response.json()];
              })
            );
            return JSON.stringify(Object.fromEntries(entries));
          })()`,
          returnByValue: true,
        },
        sessionId,
      );
      if (result.exceptionDetails || typeof result.result?.value !== "string") {
        throw new Error("desktop_suite_public_api_collection_failed");
      }
      const publicPayload = JSON.parse(result.result.value);
      return summarizeDesktopSuitePublicApiEvidence({
        profile: publicPayload.profile,
        gtm: publicPayload.gtm,
        report: validateFounderSafeReportPayload(publicPayload.report),
      });
    }

    async function collectDesktopSuiteReportJourneyEvidence() {
      await waitForExpression(
        client,
        sessionId,
        buttonExpression("Сформировать отчёт", "ready"),
        "desktop_suite_gate4_button",
        120_000,
      );
      await evaluateValue(
        client,
        sessionId,
        buttonExpression("Сформировать отчёт", "click"),
      );
      await waitForExpression(
        client,
        sessionId,
        `(() => {
          const links = Array.from(document.querySelectorAll("a"));
          const pdf = links.find((link) =>
            link.textContent?.trim().includes("PDF") &&
            link.getAttribute("href")?.includes("/report/pdf")
          );
          const html = links.find((link) =>
            link.textContent?.trim().includes("HTML") &&
            link.getAttribute("href")?.includes("/report/html")
          );
          const json = links.find((link) =>
            link.textContent?.trim().includes("JSON") &&
            link.getAttribute("href")?.includes("/report/json")
          );
          return Boolean(pdf && html && json && !document.querySelector(".workflow-action-panel--error"));
        })()`,
        "desktop_suite_gate4_pdf",
        120_000,
      );
      const approvedArtifacts = JSON.parse(
        await evaluateValue(
          client,
          sessionId,
          `(() => {
            const artifactLinks = Array.from(document.querySelectorAll("a"))
              .filter((link) => link.getAttribute("href")?.includes("/report/"));
            const links = Object.fromEntries(
              artifactLinks.map((link) => [
                (link.textContent?.trim().match(/PDF|HTML|JSON/) ?? [""])[0],
                {
                  href: link.getAttribute("href") ?? "",
                  origin: new URL(link.href, window.location.href).origin
                },
              ]).filter(([name]) => name),
            );
            return JSON.stringify({ links, origin: window.location.origin });
          })()`,
        ),
      );
      const approvedCaseMatch = approvedArtifacts.links.JSON?.href.match(
        /^\/api\/startup\/cases\/([^/]+)\/report\/json$/,
      );
      const approvedCaseId = approvedCaseMatch?.[1] ?? "";
      const expectedApprovedPaths = {
        HTML: `/api/startup/cases/${approvedCaseId}/report/html`,
        JSON: `/api/startup/cases/${approvedCaseId}/report/json`,
        PDF: `/api/startup/cases/${approvedCaseId}/report/pdf`,
      };
      if (
        !approvedCaseMatch ||
        Object.entries(expectedApprovedPaths).some(
          ([name, path]) =>
            approvedArtifacts.links[name]?.href !== path ||
            approvedArtifacts.links[name]?.origin !== approvedArtifacts.origin,
        )
      ) {
        throw new Error(
          `desktop_suite_gate4_artifact_contract_mismatch case=${approvedCaseId} links=${JSON.stringify(approvedArtifacts.links)}`,
        );
      }
      const publicApiEvidence = await collectDesktopSuitePublicApiEvidence(approvedCaseId);
      return {
        ...publicApiEvidence,
        caseId: approvedCaseId,
        reportPaths: expectedApprovedPaths,
      };
    }

    await applyViewport(viewport);

    await client.send("Page.navigate", { url }, sessionId);
    const pageDeadline = Date.now() + 15_000;
    while (Date.now() < pageDeadline) {
      const ready = await client.send(
        "Runtime.evaluate",
        { expression: "document.readyState", returnByValue: true },
        sessionId,
      );
      if (ready.result.value === "complete") break;
      await sleep(100);
    }
    const ready = await client.send(
      "Runtime.evaluate",
      { expression: "document.readyState", returnByValue: true },
      sessionId,
    );
    if (ready.result.value !== "complete") {
      throw new Error(`page_load_timeout state=${ready.result.value}`);
    }
    await client.send(
      "Runtime.evaluate",
      {
        awaitPromise: true,
        expression: `new Promise(async (resolve) => {
          if (document.fonts) await document.fonts.ready;
          setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(resolve)), 500);
        })`,
      },
      sessionId,
    );
    if (requireCaseCopilotScenarioJourney) {
      if (!fixturePath) {
        throw new Error("case_copilot_scenario_journey_requires_fixture");
      }
      let caseCopilotPreRestartCapture;
      journey = await driveCaseCopilotScenarioJourney(
        client,
        sessionId,
        fixturePath,
        caseCopilotRestartRequestPath,
        caseCopilotRestartReadyPath,
        async (preRestartJourney) => {
          journey = preRestartJourney;
          caseCopilotPreRestartCapture = await captureViewportArtifact(outputPath, viewport);
          return caseCopilotPreRestartCapture;
        },
      );
      await client.send(
        "Runtime.evaluate",
        {
          awaitPromise: true,
          expression: "new Promise((resolve) => setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(resolve)), 300))",
        },
        sessionId,
      );
      if (!caseCopilotPreRestartCapture) {
        throw new Error("case_copilot_pre_restart_screenshot_missing");
      }
      await accumulateCaptureEvidenceStats(caseCopilotPreRestartCapture, {
        ...viewport,
        label: `${viewport.label}-post-restart`,
      });
      caseCopilotPreRestartCapture.journey = journey;
      return caseCopilotPreRestartCapture;
    }
    if (requireSmartUniversitySinglePdfJourney) {
      if (!fixturePath) {
        throw new Error("smart_university_single_pdf_journey_requires_fixture");
      }
      let smartUniversityPreRestartCapture;
      journey = await driveSmartUniversitySinglePdfJourney(
        client,
        sessionId,
        fixturePath,
        caseCopilotRestartRequestPath,
        caseCopilotRestartReadyPath,
        async (preRestartJourney) => {
          journey = preRestartJourney;
          smartUniversityPreRestartCapture = await captureViewportArtifact(outputPath, viewport);
          return smartUniversityPreRestartCapture;
        },
        requireSmartUniversityLivePublicResearch,
        auditSpoolRoot,
      );
      await client.send(
        "Runtime.evaluate",
        {
          awaitPromise: true,
          expression: "new Promise((resolve) => setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(resolve)), 300))",
        },
        sessionId,
      );
      if (!smartUniversityPreRestartCapture) {
        throw new Error("smart_university_pre_restart_screenshot_missing");
      }
      await accumulateCaptureEvidenceStats(smartUniversityPreRestartCapture, {
        ...viewport,
        label: `${viewport.label}-post-restart`,
      });
      smartUniversityPreRestartCapture.journey = journey;
      return smartUniversityPreRestartCapture;
    }
    if (desktopStateSuitePath) {
      if (!fixturePath) {
        throw new Error("desktop_state_suite_requires_fixture");
      }
      await waitForExpression(
        client,
        sessionId,
        `(() => {
          const expectedInitialUrl = ${JSON.stringify(url)};
          return location.href === expectedInitialUrl &&
            Boolean(document.querySelector(".founder-dashboard-shell")) &&
            Boolean(document.querySelector("nav.founder-sidebar__nav"));
        })()`,
        "desktop_suite_initial_founder_shell",
        120_000,
      );
      mkdirSync(desktopStateSuitePath, { recursive: true });
      const captures = [];
      captures.push(await captureDesktopState("01-start-dashboard.png"));
      await clickSidebar("Новый анализ", '[data-founder-view="data-room"]');
      captures.push(await captureDesktopState("02-data-room.png"));

      await client.send("DOM.enable", {}, sessionId);
      const { root } = await client.send("DOM.getDocument", {}, sessionId);
      const { nodeId } = await client.send(
        "DOM.querySelector",
        { nodeId: root.nodeId, selector: 'input[type="file"]' },
        sessionId,
      );
      if (!nodeId) throw new Error("founder_file_input_missing");
      await armFounderIntakeObservation(client, sessionId);
      await client.send(
        "DOM.setFileInputFiles",
        { files: [resolve(fixturePath)], nodeId },
        sessionId,
      );
      await evaluateValue(
        client,
        sessionId,
        `(() => {
          const input = document.querySelector('input[type="file"]');
          if (!input) return false;
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()`,
      );
      journey = { intakeEvidence: await observeFounderIntakeEvidence(
        client,
        sessionId,
        pdfUploadJourney,
      ) };
      await clickButton(
        "Начать анализ",
        '[data-founder-view="progress-gate2"]',
      );
      await waitForExpression(
        client,
        sessionId,
        actionSelectorExpression("gate2-approve", "ready"),
        "desktop_suite_gate2_ready",
        120_000,
      );
      captures.push(await captureDesktopState("03-analysis-progress-gate2.png"));
      await clickAction(
        "gate2-approve",
        '[data-founder-view="overview"]',
      );
      captures.push(await captureDesktopState("04-overview-readiness.png"));

      await clickSidebar("План действий", '[data-founder-view="action-plan"]');
      await clickButton(
        "Принять рекомендацию",
        '[data-founder-view="report-center"]',
      );
      await waitForExpression(
        client,
        sessionId,
        buttonExpression("Сформировать отчёт", "ready"),
        "desktop_suite_report_ready_before_advisor",
        120_000,
      );
      await clickSidebar("Обзор", '[data-founder-view="overview"]');

      await clickButton(
        "Спросить AI-советника о проекте",
        '[data-founder-view="advisor-next-question"]',
      );
      captures.push(await captureDesktopState("11-ai-advisor-next-question.png"));
      await clickButton(
        "Ответить на вопрос",
        '[data-founder-view="advisor-answer"]',
      );
      await setManualAdvisorAnswer(invalidAdvisorAnswer);
      await clickButton(
        "Сохранить и пересчитать",
        null,
      );
      await assertManualAdvisorAnswerRejected();
      captures.push(await captureDesktopState("12-ai-advisor-answer.png"));
      await setManualAdvisorAnswer(advisorAnswer);
      await clickButton(
        "Сохранить и пересчитать",
        '[data-founder-view="advisor-updated-analysis"]',
      );
      await clickButton(
        "Продолжить обновление",
        '[data-founder-view="progress-gate2"]',
      );
      await clickAction(
        "gate2-approve",
        '[data-founder-view="overview"]',
        120_000,
        "desktop_suite_recalculation_gate2_ready",
      );
      await clickSidebar("План действий", '[data-founder-view="action-plan"]');
      await clickButton(
        "Принять рекомендацию",
        '[data-founder-view="report-center"]',
      );
      await waitForExpression(
        client,
        sessionId,
        buttonExpression("Сформировать отчёт", "ready"),
        "desktop_suite_recalculation_report_ready",
        120_000,
      );
      await clickSidebar("Обзор", '[data-founder-view="overview"]');
      await clickButton(
        "Спросить AI-советника о проекте",
        '[data-founder-view="advisor-next-question"]',
      );
      await clickButton(
        "Ответить на вопрос",
        '[data-founder-view="advisor-updated-analysis"]',
      );
      captures.push(await captureDesktopState("13-ai-advisor-updated-analysis.png"));
      await clickButton(
        "Перейти к улучшенному плану",
        '[data-founder-view="advisor-improved-plan"]',
      );
      await clickButton(
        "Принять",
        null,
      );
      await waitForExpression(
        client,
        sessionId,
        `(() => {
          const page = document.querySelector('[data-founder-advisor-page="advisor-improved-plan"]');
          return Boolean(page?.textContent?.includes("Улучшенный план ещё не сформирован"));
        })()`,
        "desktop_suite_improvement_recalculation_started",
        120_000,
      );
      await clickSidebar("Новый анализ", '[data-founder-view="progress-gate2"]');
      await clickAction(
        "gate2-approve",
        '[data-founder-view="overview"]',
        120_000,
        "desktop_suite_improvement_gate2_ready",
      );
      await clickSidebar("План действий", '[data-founder-view="action-plan"]');
      await clickButton(
        "Принять рекомендацию",
        '[data-founder-view="report-center"]',
      );
      await waitForExpression(
        client,
        sessionId,
        buttonExpression("Сформировать отчёт", "ready"),
        "desktop_suite_improvement_report_ready",
        120_000,
      );
      await clickSidebar("Обзор", '[data-founder-view="overview"]');
      await clickButton(
        "Спросить AI-советника о проекте",
        '[data-founder-view="advisor-next-question"]',
      );
      await clickButton(
        "Ответить на вопрос",
        '[data-founder-view="advisor-updated-analysis"]',
      );
      await clickButton(
        "Перейти к улучшенному плану",
        '[data-founder-view="advisor-improved-plan"]',
      );
      await waitForExpression(
        client,
        sessionId,
        `(() => {
          const page = document.querySelector('[data-founder-advisor-page="advisor-improved-plan"]');
          return Boolean(page?.textContent?.includes("Проект улучшен — версия 2"));
        })()`,
        "desktop_suite_improvement_version_ready",
        120_000,
      );
      captures.push(await captureDesktopState("14-ai-advisor-improved-plan.png"));

      await clickSidebar("Метрики", '[data-founder-view="metrics"]');
      captures.push(await captureDesktopState("05-metrics-finance.png"));
      await clickSidebar("Рынок", '[data-founder-view="market"]');
      captures.push(await captureDesktopState("06-market-competitors.png"));
      await clickSidebar("Риски", '[data-founder-view="risks"]');
      captures.push(await captureDesktopState("07-risks-questions.png"));
      await clickSidebar("План действий", '[data-founder-view="action-plan"]');
      captures.push(await captureDesktopState("08-ai-action-plan.png"));
      await clickSidebar("Отчёты", '[data-founder-view="report-center"]');
      captures.push(await captureDesktopState("09-report-center.png"));
      journey = {
        ...journey,
        ...(await collectDesktopSuiteReportJourneyEvidence()),
      };

      await client.send("Page.navigate", { url: desktopStateSuiteAdminUrl }, sessionId);
      await waitForExpression(
        client,
        sessionId,
        "document.readyState === 'complete'",
        "desktop_suite_admin_ready",
        30_000,
      );
      await waitForExpression(
        client,
        sessionId,
        `(() => {
          const text = document.body?.innerText ?? "";
          return text.includes("Обзор системы") &&
            text.includes("Граф агентов (LangGraph)");
        })()`,
        "desktop_suite_admin_dashboard_ready",
        120_000,
      );
      captures.push(await captureDesktopState("10-admin-observability-v2.png"));
      return {
        ...aggregateCaptureEvidence(captures),
        captures,
        height: viewport.height,
        journey,
        outputPath: desktopStateSuitePath,
        width: viewport.width,
      };
    }
    if (fixturePath) {
      journey = await driveFounderGtmJourney(client, sessionId, fixturePath, pdfUploadJourney);
      await client.send(
        "Runtime.evaluate",
        {
          awaitPromise: true,
          expression: "new Promise((resolve) => setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(resolve)), 300))",
        },
        sessionId,
      );
    } else {
      await client.send(
        "Runtime.evaluate",
        { expression: "window.scrollTo(0, 0)" },
        sessionId,
      );
    }
    const primaryCapture = await captureViewportArtifact(outputPath, viewport);
    if (!additionalCapture) {
      return primaryCapture;
    }
    await applyViewport(additionalCapture.viewport);
    await client.send(
      "Runtime.evaluate",
      {
        awaitPromise: true,
        expression: "new Promise((resolve) => setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(resolve)), 300))",
      },
      sessionId,
    );
    return {
      additionalCapture: await captureViewportArtifact(
        additionalCapture.outputPath,
        additionalCapture.viewport,
      ),
      primaryCapture,
    };
  } finally {
    socket?.close();
    await terminateBrowser(browserProcess);
    await waitForExit(browserProcess, 2_000);
    cleanupProfileDirectory(profileDirectory);
  }
}

async function main() {
const options = parseOptions(process.argv.slice(2));
const validateOnly = options["validate-only"] === "true";
const browserPath = resolve(required(options, "browser"));
const url = required(options, "url");
const adminUrl = options["admin-url"] ?? "http://127.0.0.1:8501/";
const fixturePath = options.fixture ? resolve(options.fixture) : undefined;
const requireDesktopStateSuite =
  options["require-desktop-state-suite"] === "true";
const requireCaseCopilotScenarioJourney =
  options["require-case-copilot-scenario-journey"] === "true";
const requireSmartUniversitySinglePdfJourney =
  options["require-smart-university-single-pdf-journey"] === "true";
const requireSmartUniversityLivePublicResearch =
  options["require-smart-university-live-public-research"] === "true";
const desktopStatesPath = requireDesktopStateSuite
  ? resolve(required(options, "desktop-states"))
  : undefined;
const desktopStateManifestPath = options["desktop-state-manifest"]
  ? resolve(options["desktop-state-manifest"])
  : desktopStatesPath
    ? join(desktopStatesPath, "desktop-state-manifest.json")
    : undefined;
const desktopPath = requireDesktopStateSuite
  ? undefined
  : validateOnly && requireSmartUniversitySinglePdfJourney
    ? undefined
    : resolve(required(options, "desktop"));
const mobilePath = requireDesktopStateSuite ||
  requireCaseCopilotScenarioJourney ||
  requireSmartUniversitySinglePdfJourney
  ? undefined
  : resolve(required(options, "mobile"));
const evidencePath = options.evidence ? resolve(options.evidence) : undefined;
const configuredAdminTracePath = options["admin-trace-json"]
  ? resolve(options["admin-trace-json"])
  : undefined;
const smartUniversityAuditSpoolRoot = options["audit-spool-root"]
  ? resolve(options["audit-spool-root"])
  : undefined;
const requirePdfUploadJourney = options["require-pdf-upload-journey"] === "true";
const advisorAnswer = options["advisor-answer"] ?? DEFAULT_ADVISOR_ANSWER;
const invalidAdvisorAnswer =
  options["invalid-advisor-answer"] ?? DEFAULT_INVALID_ADVISOR_ANSWER;
const allowedBlockedParserScriptOrigin = normalizeOptionalOrigins(
  options["allow-blocked-parser-script-origin"],
);
const caseCopilotRestartRequestPath = options["case-copilot-restart-request"]
  ? resolve(options["case-copilot-restart-request"])
  : undefined;
const caseCopilotRestartReadyPath = options["case-copilot-restart-ready"]
  ? resolve(options["case-copilot-restart-ready"])
  : undefined;
const fixtureSummary = safeFixtureSummary(
  fixturePath,
  requirePdfUploadJourney || requireSmartUniversitySinglePdfJourney,
);

if (validateOnly) {
  required(options, "fixture");
  required(options, "evidence");
  if (!isAllowedBrowserRequest(url)) {
    throw new Error("browser_evidence_url_must_be_local");
  }
  if (!isAllowedBrowserRequest(adminUrl)) {
    throw new Error("browser_evidence_admin_url_must_be_local");
  }
  if (!requireDesktopStateSuite && (options["desktop-case-id"] || options["mobile-case-id"])) {
    assertSameJourneyCase(
      { journey: { caseId: options["desktop-case-id"] } },
      { journey: { caseId: options["mobile-case-id"] } },
    );
  }
  if (requirePdfUploadJourney) {
    if (!configuredAdminTracePath) {
      throw new Error("browser_evidence_admin_trace_required");
    }
    const expectedCaseId = options["desktop-case-id"];
    if (!expectedCaseId) {
      throw new Error("browser_evidence_admin_trace_case_required");
    }
    const reportJsonPath = options["report-json"]
      ? resolve(options["report-json"])
      : undefined;
    const reportJson = reportJsonPath
      ? validateFounderSafeReportPayload(
          JSON.parse(readFileSync(reportJsonPath, "utf8")),
        )
      : undefined;
    const reportMetadataPath = options["report-metadata"]
      ? resolve(options["report-metadata"])
      : undefined;
    const reportMetadata = reportMetadataPath
      ? validateReportMetadata(
          JSON.parse(readFileSync(reportMetadataPath, "utf8")),
          expectedCaseId,
          reportJson,
        )
      : undefined;
    readAdminTraceEvidence(
      configuredAdminTracePath,
      expectedCaseId,
      reportJson,
      reportMetadata,
    );
    if (!reportJson) {
      throw new Error("browser_evidence_report_json_required");
    }
    if (!reportMetadata) {
      throw new Error("browser_evidence_report_metadata_required");
    }
    console.log("admin_trace_contract_valid");
  }
  if (requireDesktopStateSuite) {
    if (!desktopStatesPath) {
      throw new Error("browser_evidence_desktop_states_required");
    }
    writeDesktopStateManifest(desktopStatesPath, desktopStateManifestPath);
    console.log(
      `founder_14_desktop_states_contract_valid ${CANONICAL_DESKTOP_STATE_SCREENSHOTS.join(",")}`,
    );
  }
  if (requireCaseCopilotScenarioJourney) {
    validateCaseCopilotScenarioJourneyEvidence(
      { caseCopilotScenarioJourney: {
        cross_fixture: {
          base_inputs_differ: true,
          benchmark_scopes_differ: true,
          questions_differ: true,
        },
        fixtures: [
          {
            case_id: "validate-only-idea-inventory",
            fixture_name: "idea_inventory",
            ui_interactions: [
              "file_upload",
              "start_analysis",
              "gate2_approve",
              "unknown_answer",
              "public_research_consent",
              "scenario_select_base",
              "launch_pack_generate",
              "launch_pack_download",
            ],
            visible_state: {
              file_uploaded: true,
              launch_pack_visible: true,
              question_card_visible: true,
              research_status_visible: true,
              scenario_metrics_visible: true,
            },
            final_screenshot_state: {
              case_copilot_panel_visible: true,
              populated_same_case_ui: true,
            },
            founder_statement_accepted: true,
            launch_pack: {
              asset_id: "validate-only-asset-inventory",
              downloaded: true,
              provenance_appendix: true,
              versioned: true,
            },
            question_visible: true,
            research: {
              citations: ["https://example.com/validate-only"],
              explicit_consent: true,
              job_status: "completed",
              no_source_fact_promotion: true,
              plan_prepared: true,
              provider_calls_zero_before_queue: true,
              source_refs: ["validate-only-source-inventory"],
            },
            restart: {
              process_restarted: Boolean("validate-only-restart"),
              same_asset_reloaded: true,
              same_case_reloaded: true,
              same_scenario_reloaded: true,
            },
            scenarios: {
              action_delta: true,
              metric_delta: true,
              metric_disclosure_complete: true,
              readiness_delta: true,
              risk_delta: true,
              scenario_keys: ["conservative", "base", "optimistic"],
              selected_key: "base",
            },
            text_brief_uploaded: true,
            unknown_answer_recorded: true,
          },
          {
            case_id: "validate-only-idea-clinic",
            fixture_name: "idea_clinic",
            ui_interactions: [
              "file_upload",
              "start_analysis",
              "gate2_approve",
              "unknown_answer",
              "public_research_consent",
              "scenario_select_base",
              "launch_pack_generate",
              "launch_pack_download",
            ],
            visible_state: {
              file_uploaded: true,
              launch_pack_visible: true,
              question_card_visible: true,
              research_status_visible: true,
              scenario_metrics_visible: true,
            },
            final_screenshot_state: {
              case_copilot_panel_visible: true,
              populated_same_case_ui: true,
            },
            founder_statement_accepted: true,
            launch_pack: {
              asset_id: "validate-only-asset-clinic",
              downloaded: true,
              provenance_appendix: true,
              versioned: true,
            },
            question_visible: true,
            research: {
              citations: ["https://example.com/validate-only"],
              explicit_consent: true,
              job_status: "completed",
              no_source_fact_promotion: true,
              plan_prepared: true,
              provider_calls_zero_before_queue: true,
              source_refs: ["validate-only-source-clinic"],
            },
            restart: {
              process_restarted: Boolean("validate-only-restart"),
              same_asset_reloaded: true,
              same_case_reloaded: true,
              same_scenario_reloaded: true,
            },
            scenarios: {
              action_delta: true,
              metric_delta: true,
              metric_disclosure_complete: true,
              readiness_delta: true,
              risk_delta: true,
              scenario_keys: ["conservative", "base", "optimistic"],
              selected_key: "base",
            },
            text_brief_uploaded: true,
            unknown_answer_recorded: true,
          },
        ],
      } },
      fixtureSummary,
    );
    console.log("case_copilot_scenario_journey_required");
  }
  if (requireSmartUniversitySinglePdfJourney) {
    const evidence = JSON.parse(readFileSync(evidencePath, "utf8"));
    validateSmartUniversitySinglePdfJourneyEvidence(evidence, fixtureSummary, {
      requireLivePublicResearch: requireSmartUniversityLivePublicResearch,
    });
    console.log("smart_university_single_pdf_journey_required");
  }
  console.log("founder_browser_evidence_contract_valid");
} else {
  if (requireDesktopStateSuite) {
    const desktopSuiteCapture = await capture(
      browserPath,
      url,
      desktopStatesPath,
      {
        height: 1000,
        label: "desktop-state-suite",
        mobile: false,
        width: 1440,
      },
      fixturePath,
      allowedBlockedParserScriptOrigin,
      undefined,
      requirePdfUploadJourney,
      desktopStatesPath,
      adminUrl,
      advisorAnswer,
      invalidAdvisorAnswer,
    );
    writeDesktopStateManifest(
      desktopStatesPath,
      desktopStateManifestPath,
      desktopSuiteCapture.captures,
    );
    if (evidencePath) {
      let generatedAdminTracePath = configuredAdminTracePath;
      if (requirePdfUploadJourney) {
        const auditSpoolRoot = resolve(required(options, "audit-spool-root"));
        generatedAdminTracePath =
          generatedAdminTracePath ??
          join(dirname(evidencePath), "admin-trace.json");
        mkdirSync(dirname(generatedAdminTracePath), { recursive: true });
        await generateAdminTraceEvidence(
          auditSpoolRoot,
          desktopSuiteCapture.journey.caseId,
          generatedAdminTracePath,
        );
      }
      if (requireCaseCopilotScenarioJourney) {
        validateCaseCopilotScenarioJourneyEvidence(
          desktopSuiteCapture.journey,
          fixtureSummary,
        );
        console.log("case_copilot_scenario_journey_verified");
      }
      await writeBrowserEvidence(
        evidencePath,
        url,
        desktopSuiteCapture,
        undefined,
        fixtureSummary,
        generatedAdminTracePath,
      );
    }
    console.log(
      `founder_14_desktop_states_written ${CANONICAL_DESKTOP_STATE_SCREENSHOTS.join(",")}`,
    );
    process.exit(0);
  }
  if (evidencePath) {
    if (!fixturePath) {
      throw new Error("browser_evidence_requires_fixture");
    }
    if (requireSmartUniversityLivePublicResearch && !smartUniversityAuditSpoolRoot) {
      throw new Error("smart_university_live_research_requires_audit_spool_root");
    }
    const evidenceCapture = await capture(
      browserPath,
      url,
      desktopPath,
      {
        height: 1000,
        label: "desktop",
        mobile: false,
        width: 1440,
      },
      fixturePath,
      allowedBlockedParserScriptOrigin,
      requireCaseCopilotScenarioJourney || requireSmartUniversitySinglePdfJourney
        ? undefined
        : {
            outputPath: mobilePath,
            viewport: {
              height: 844,
              label: "mobile",
              mobile: true,
              width: 390,
            },
          },
      requirePdfUploadJourney,
      undefined,
      "http://127.0.0.1:8501/",
      advisorAnswer,
      invalidAdvisorAnswer,
      requireCaseCopilotScenarioJourney,
      caseCopilotRestartRequestPath,
      caseCopilotRestartReadyPath,
      requireSmartUniversitySinglePdfJourney,
      requireSmartUniversityLivePublicResearch,
      smartUniversityAuditSpoolRoot,
    );
    if (requireCaseCopilotScenarioJourney) {
      await writeCaseCopilotBrowserEvidence(
        evidencePath,
        url,
        evidenceCapture.primaryCapture ?? evidenceCapture,
        fixtureSummary,
      );
      process.exit(0);
    }
    if (requireSmartUniversitySinglePdfJourney) {
      await writeSmartUniversitySinglePdfBrowserEvidence(
        evidencePath,
        url,
        evidenceCapture.primaryCapture ?? evidenceCapture,
        fixtureSummary,
        requireSmartUniversityLivePublicResearch,
      );
      process.exit(0);
    }
    let generatedAdminTracePath = configuredAdminTracePath;
    if (requirePdfUploadJourney) {
      const auditSpoolRoot = resolve(required(options, "audit-spool-root"));
      generatedAdminTracePath =
        generatedAdminTracePath ??
        join(dirname(evidencePath), "admin-trace.json");
      mkdirSync(dirname(generatedAdminTracePath), { recursive: true });
      await generateAdminTraceEvidence(
        auditSpoolRoot,
        evidenceCapture.primaryCapture.journey.caseId,
        generatedAdminTracePath,
      );
    }
    await writeBrowserEvidence(
      evidencePath,
      url,
      evidenceCapture.primaryCapture,
      evidenceCapture.additionalCapture,
      fixtureSummary,
      generatedAdminTracePath,
    );
  } else {
    await capture(
      browserPath,
      url,
      desktopPath,
      {
        height: 1000,
        label: "desktop",
        mobile: false,
        width: 1440,
      },
      fixturePath,
      allowedBlockedParserScriptOrigin,
      undefined,
      false,
      undefined,
      "http://127.0.0.1:8501/",
      advisorAnswer,
      invalidAdvisorAnswer,
    );
    await capture(
      browserPath,
      url,
      mobilePath,
      {
        height: 844,
        label: "mobile",
        mobile: false,
        width: 390,
      },
      fixturePath,
      allowedBlockedParserScriptOrigin,
    );
  }
}
}

function isCliEntrypoint() {
  const entrypoint = process.argv[1];
  return Boolean(entrypoint) && import.meta.url === pathToFileURL(resolve(entrypoint)).href;
}

if (isCliEntrypoint()) {
  await main();
}
