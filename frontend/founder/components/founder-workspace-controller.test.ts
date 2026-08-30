import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type {
  StartupProfileFieldName,
  StartupProfileFieldResponse,
  StartupProfileResponse,
  StartupCaseReport,
  StartupCaseStatus,
  StartupCreateResponse,
  StartupDecisionResult,
  StartupGate2Preview,
  StartupGtmResponse,
  StartupReportSnapshotResponse,
  StartupUploadResponse,
  AdvisorAnswerResponse,
  AdvisorImprovementDecisionResponse,
  AdvisorImprovementsResponse,
  AdvisorNextQuestionResponse,
  AssumptionOutcomeResponse,
  CopilotActionAvailability,
  CopilotThreadResponse,
  CopilotTurnResponse,
  CopilotStateResponse,
  FactMutationResponse,
  LaunchPackMetadataResponse,
  ResearchJobResponse,
  ResearchPlanResponse,
  ScenarioProjectionResponse,
} from "../lib/contracts.ts";
import {
  parseStartupProfileResponse,
  STARTUP_PROFILE_FIELD_NAMES,
} from "../lib/contracts.ts";
import {
  FounderApiClientError,
  type StartupGate2Decision,
} from "../lib/founder-api-client.ts";
import {
  buildCaseCopilotManualAssumptionRequest,
  deriveCaseCopilotResearchConsentScope,
  buildCaseCopilotSubmitPayload,
  caseCopilotSubmitFailureMessage,
  deriveCaseCopilotAnswerModes,
  selectCaseCopilotAnswerType,
} from "../lib/case-copilot-presentation.ts";
import {
  createFounderWorkspaceOrchestrator,
  founderErrorMessage,
  founderShellStage,
  normalizeFounderCaseFixtureMode,
  type FounderWorkspaceApi,
  type FounderWorkspaceSnapshot,
} from "./founder-workspace-orchestrator.ts";
import { startFounderWorkspaceAnalysis } from "./founder-workspace-analysis-start.ts";

const caseId = "case-founder-001";

const caseCopilotPanelComponent = readFileSync(
  new URL("./case-copilot-panel.tsx", import.meta.url),
  "utf8",
);
const caseQuestionCardComponent = readFileSync(
  new URL("./case-question-card.tsx", import.meta.url),
  "utf8",
);
const founderScenarioMetricsComponent = readFileSync(
  new URL("./founder-scenario-metrics.tsx", import.meta.url),
  "utf8",
);

test("renders Case Copilot contracts as readable Russian without exposing raw identifiers", () => {
  for (const copy of [
    "Помощник по кейсу",
    "Публичное исследование",
    "Диалог",
    "Что нужно сделать",
    "Как читать источники",
  ]) {
    assert.match(caseCopilotPanelComponent, new RegExp(copy, "u"));
  }
  for (const copy of [
    "Один главный вопрос",
    "Значение",
    "Масштаб",
    "Валюта",
    "Месяц",
    "Откуда значение",
    "Почему это важно",
    "Как проверить",
    "Сохранить ответ",
  ]) {
    assert.match(caseQuestionCardComponent, new RegExp(copy, "u"));
  }

  assert.match(caseCopilotPanelComponent, /formatCopilotAction\(action\.action\)/u);
  assert.match(caseCopilotPanelComponent, /formatCopilotActionStatus\(action\.status\)/u);
  assert.match(caseCopilotPanelComponent, /formatCopilotRole\(message\.role\)/u);
  assert.match(
    caseCopilotPanelComponent,
    /formatCopilotThreadMessage\(message\.role, message\.content\)/u,
  );
  assert.match(caseCopilotPanelComponent, /formatProvenance\(kind\)/u);
  assert.match(caseQuestionCardComponent, /formatCopilotQuestion\(question\)/u);
  assert.match(caseQuestionCardComponent, /formatDependency\(error\.field\)/u);
  assert.match(founderScenarioMetricsComponent, /formatCoverage\(factCoverage\)/u);
  assert.match(founderScenarioMetricsComponent, /formatScenario\(scenarioKey\)/u);
  assert.match(founderScenarioMetricsComponent, /presentScenarioMetric\(metric\)/u);
  assert.match(founderScenarioMetricsComponent, /<summary>Как рассчитано и проверить<\/summary>/u);
  assert.match(founderScenarioMetricsComponent, /presentation\.dependencies\.map/u);
  assert.match(founderScenarioMetricsComponent, /presentation\.sourceReferences\.map/u);
  assert.match(founderScenarioMetricsComponent, /presentation\.validationPlan/u);
  assert.match(founderScenarioMetricsComponent, /presentation\.confirmationGuidance/u);
  assert.doesNotMatch(founderScenarioMetricsComponent, /disclosure\.whatWouldConfirm/u);

  assert.doesNotMatch(caseCopilotPanelComponent, />\{action\.action\}</u);
  assert.doesNotMatch(caseCopilotPanelComponent, />\{message\.role\}</u);
  assert.match(caseCopilotPanelComponent, /сценарии ИИ/u);
  assert.doesNotMatch(caseCopilotPanelComponent, /сценарии AI/u);
  assert.doesNotMatch(caseQuestionCardComponent, /`\$\{error\.field\}: \$\{error\.message\}`/u);
  assert.doesNotMatch(founderScenarioMetricsComponent, /scenarioLabels|provenanceLabels|metricLabels|coverageLabel/u);
  assert.doesNotMatch(founderScenarioMetricsComponent, /disclosure\.dependencies\.length|disclosure\.sourceRefs\.length/u);
});

const created: StartupCreateResponse = {
  case_id: caseId,
  case_status: "awaiting_upload",
  analysis_status: "awaiting_upload",
  provider_status: "configured",
  auto_start_triggered: false,
};

const uploaded: StartupUploadResponse = {
  case_id: caseId,
  accepted_document_ids: ["doc-0001"],
  analysis_status: "gate2_preview_ready",
  auto_start_triggered: true,
  next_poll_after_ms: 0,
};

const gate2Status: StartupCaseStatus = {
  case_id: caseId,
  case_status: "awaiting_upload",
  analysis_status: "gate2_preview_ready",
  provider_status: "configured",
  data_revision: 1,
  active_analysis_thread_id: caseId,
  langgraph_checkpoint: null,
  gate2_status: "required",
  gate3_status: "not_ready",
  gate4_status: "not_ready",
  report_status: "not_ready",
  snapshot_hash: null,
  snapshot_revision: null,
};

const gate2Preview: StartupGate2Preview = {
  case_id: caseId,
  preview: {
    document_count: 1,
    detected_company: "FounderCo",
  },
  resume_token: "resume-token-001",
  provider_mode: "configured",
};

const gate3Status: StartupCaseStatus = {
  ...gate2Status,
  analysis_status: "gate3_review_required",
  gate2_status: "completed",
  gate3_status: "required",
};

const reportStatus: StartupCaseStatus = {
  ...gate3Status,
  analysis_status: "analysis_complete_report_pending",
  gate3_status: "completed",
  report_status: "ready",
  snapshot_hash: "sha256:canonical-report",
  snapshot_revision: 4,
};

const report: StartupCaseReport = {
  case_id: caseId,
  report_status: "ready",
  snapshot_id: "snapshot-004",
  snapshot_hash: "sha256:canonical-report",
  snapshot_revision: 4,
  json_url: `/api/startup/cases/${caseId}/report/json`,
  html_url: `/api/startup/cases/${caseId}/report/html`,
  pdf_url: `/api/startup/cases/${caseId}/report/pdf`,
  freeze_status: "required",
  pdf_status: "freeze_required",
};

const startupGtm: StartupGtmResponse = {
  case_id: caseId,
  schema_version: "startup_gtm@1",
  snapshot_id: "gtm-snapshot-004",
  snapshot_hash:
    "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  snapshot_revision: 4,
  status: "partial",
  profile_id: "profile-founder-001",
  product_validation_snapshot_id: "product-validation-snapshot-001",
  market_research_snapshot_id: "market-research-snapshot-001",
  dimensions: [
    {
      name: "audience",
      status: "supported",
      evidence_fact_ids: ["fact-audience-001"],
      market_source_ids: [],
      contradiction_ids: [],
      reason_code: "gtm_audience_supported",
      gap_code: null,
    },
    {
      name: "geography",
      status: "partial",
      evidence_fact_ids: ["fact-geography-001"],
      market_source_ids: ["market-source-geography-001"],
      contradiction_ids: [],
      reason_code: "gtm_geography_partial",
      gap_code: "gtm_geography_gap",
    },
    {
      name: "channels",
      status: "missing",
      evidence_fact_ids: [],
      market_source_ids: [],
      contradiction_ids: [],
      reason_code: "gtm_channels_missing",
      gap_code: "gtm_channels_gap",
    },
    {
      name: "offer",
      status: "supported",
      evidence_fact_ids: ["fact-offer-001"],
      market_source_ids: [],
      contradiction_ids: [],
      reason_code: "gtm_offer_supported",
      gap_code: null,
    },
    {
      name: "market_context",
      status: "supported",
      evidence_fact_ids: [],
      market_source_ids: ["market-source-context-001"],
      contradiction_ids: [],
      reason_code: "gtm_market_context_supported",
      gap_code: null,
    },
    {
      name: "product_proof",
      status: "contradicted",
      evidence_fact_ids: ["fact-product-proof-001"],
      market_source_ids: [],
      contradiction_ids: ["contradiction-product-proof-001"],
      reason_code: "gtm_product_proof_contradicted",
      gap_code: "gtm_product_proof_gap",
    },
    {
      name: "adoption_risk",
      status: "partial",
      evidence_fact_ids: ["fact-adoption-risk-001"],
      market_source_ids: ["market-source-risk-001"],
      contradiction_ids: [],
      reason_code: "gtm_adoption_risk_partial",
      gap_code: "gtm_adoption_risk_gap",
    },
  ],
  launch_plan: [
    {
      horizon: "day_7",
      experiment_codes: ["clarify_audience", "resolve_contradictions"],
    },
    {
      horizon: "day_30",
      experiment_codes: ["validate_geography", "validate_channel"],
    },
    {
      horizon: "day_60",
      experiment_codes: ["validate_offer", "validate_product_proof"],
    },
    {
      horizon: "day_90",
      experiment_codes: ["measure_channel_signal", "review_launch_evidence"],
    },
  ],
  finding_ids: ["gtm-finding-001", "gtm-finding-002"],
  built_at: "2026-08-15T00:00:00.000Z",
};

type FounderWorkspaceGtmSnapshot = FounderWorkspaceSnapshot &
  Readonly<{ gtm: StartupGtmResponse | null }>;

type FounderWorkspaceGtmApi = FounderWorkspaceApi &
  Readonly<{
    getStartupGtm: (
      caseId: string,
      options?: Readonly<{ signal?: AbortSignal }>,
    ) => Promise<StartupGtmResponse>;
  }>;

type FounderWorkspaceProfileSnapshot = FounderWorkspaceSnapshot &
  Readonly<{ profile: StartupProfileResponse | null }>;

type FounderWorkspaceProfileApi = FounderWorkspaceApi &
  Readonly<{
    getStartupProfile: (
      caseId: string,
      options?: Readonly<{ signal?: AbortSignal }>,
    ) => Promise<StartupProfileResponse>;
  }>;

type FounderWorkspaceReportSnapshot = FounderWorkspaceSnapshot &
  Readonly<{ reportSnapshot: StartupReportSnapshotResponse | null }>;

type FounderWorkspaceReportSnapshotApi = FounderWorkspaceApi &
  Readonly<{
    getStartupReportSnapshot: (
      caseId: string,
      options?: Readonly<{ signal?: AbortSignal }>,
    ) => Promise<StartupReportSnapshotResponse>;
  }>;

type FounderWorkspaceAdvisorSnapshot = FounderWorkspaceSnapshot &
  Readonly<{
    advisorQuestion: AdvisorNextQuestionResponse | null;
    advisorAnswer: AdvisorAnswerResponse | null;
    advisorImprovements: AdvisorImprovementsResponse | null;
    advisorDecision: AdvisorImprovementDecisionResponse | null;
    advisorError: Error | null;
  }>;

type FounderWorkspaceCopilotSnapshot = FounderWorkspaceSnapshot &
  Readonly<{ copilotThread: CopilotThreadResponse | null }>;

function snapshotGtm(
  snapshot: FounderWorkspaceSnapshot,
): StartupGtmResponse | null | undefined {
  return (snapshot as Partial<FounderWorkspaceGtmSnapshot>).gtm;
}

function snapshotProfile(
  snapshot: FounderWorkspaceSnapshot,
): StartupProfileResponse | null | undefined {
  return (snapshot as Partial<FounderWorkspaceProfileSnapshot>).profile;
}

function snapshotReport(
  snapshot: FounderWorkspaceSnapshot,
): StartupReportSnapshotResponse | null | undefined {
  return (snapshot as Partial<FounderWorkspaceReportSnapshot>).reportSnapshot;
}

function snapshotAdvisor(
  snapshot: FounderWorkspaceSnapshot,
): Partial<FounderWorkspaceAdvisorSnapshot> {
  return snapshot as Partial<FounderWorkspaceAdvisorSnapshot>;
}

function snapshotCopilot(
  snapshot: FounderWorkspaceSnapshot,
): Partial<FounderWorkspaceCopilotSnapshot> {
  return snapshot as Partial<FounderWorkspaceCopilotSnapshot>;
}

function startupProfileField(
  overrides: Partial<StartupProfileFieldResponse> = {},
): StartupProfileFieldResponse {
  return {
    status: "insufficient_data",
    values: [],
    confidence: "0",
    evidence_refs: [],
    dependency_refs: [],
    reason_code: "missing_source_fact",
    contradiction_ids: [],
    ...overrides,
  };
}

function startupProfileFields(): Readonly<
  Record<StartupProfileFieldName, StartupProfileFieldResponse>
> {
  return Object.fromEntries(
    STARTUP_PROFILE_FIELD_NAMES.map((fieldName) => [
      fieldName,
      startupProfileField(),
    ]),
  ) as Record<StartupProfileFieldName, StartupProfileFieldResponse>;
}

const primaryProfileId = "00000000-0000-4000-8000-000000000101";
const enrichedProfileId = "00000000-0000-4000-8000-000000000102";
const startupNameEvidenceId = "00000000-0000-4000-8000-000000000201";
const canonicalReportSnapshotHash =
  "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";
const canonicalReportSnapshotId = "00000000-0000-4000-8000-000000000401";
function founderReportSection(
  key: StartupReportSnapshotResponse["main_sections"][number]["key"],
  title: string,
  status: StartupReportSnapshotResponse["main_sections"][number]["status"] = "confirmed",
): StartupReportSnapshotResponse["main_sections"][number] {
  return {
    key,
    title_ru: title,
    status,
    status_label_ru: status === "confirmed" ? "Подтверждено" : "Нужно уточнить",
    summary_ru: `${title} построен из безопасной версии отчета.`,
    content_heading_ru: "Что уже известно",
    known_facts_ru: status === "confirmed" ? ["FounderCo обслуживает финансовые команды."] : [],
    blockers_ru: status === "contradiction" ? ["Есть противоречие в данных."] : [],
    next_data_ru: status === "needs_input" ? ["Добавьте подтверждающий источник."] : [],
    unlocks_ru: status === "confirmed" ? [] : ["Это уточнит следующую версию отчета."],
  };
}

const startupProfile: StartupProfileResponse = parseStartupProfileResponse({
  case_id: caseId,
  profile_id: primaryProfileId,
  profile_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  data_revision: 1,
  analysis_stage: "primary",
  parent_profile_id: null,
  fields: {
    ...startupProfileFields(),
    startup_name: startupProfileField({
      status: "source_fact",
      values: ["FounderCo"],
      confidence: "0.95",
      evidence_refs: [
        {
          evidence_id: startupNameEvidenceId,
          fragment_id: null,
          artifact_id: "00000000-0000-4000-8000-000000000301",
          artifact_hash:
            "sha256:1111111111111111111111111111111111111111111111111111111111111111",
          locator_hash:
            "sha256:2222222222222222222222222222222222222222222222222222222222222222",
          page: 1,
          table: null,
          cell: null,
          field_name: "startup_name",
          confidence: "0.95",
        },
      ],
      dependency_refs: [],
      reason_code: null,
      contradiction_ids: [],
    }),
    icp: startupProfileField({
      status: "insufficient_data",
      reason_code: "missing_icp",
    }),
  },
  gaps: ["icp"],
  contradictions: [],
  parse_inventory: {
    source_hashes: {
      "doc-0001":
        "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    },
    parse_outcomes: { "doc-0001": "parsed" },
  },
});

const canonicalReportSnapshot: StartupReportSnapshotResponse = {
  title_ru: "Отчёт для основателя",
  subtitle_ru: "Краткий разбор проекта",
  as_of_ru: "2026-08-15",
  data_revision: 4,
  main_sections: [
    founderReportSection("business_idea_summary", "Кратко о проекте"),
    founderReportSection("problem_solution", "Проблема и решение"),
    founderReportSection("market_size", "Размер рынка", "needs_input"),
    founderReportSection("competitors", "Конкуренты"),
    founderReportSection("moat", "Защитимость"),
    founderReportSection("go_to_market", "Выход на рынок"),
    founderReportSection("metrics", "Ключевые метрики"),
    founderReportSection("financial_assumptions", "Финансовые допущения"),
    founderReportSection("risks", "Риски", "contradiction"),
    founderReportSection("evidence_gaps", "Пробелы в подтверждениях", "needs_input"),
    founderReportSection("diligence_questions", "Вопросы для уточнения"),
    founderReportSection("action_plan", "План действий"),
  ],
  metric_cards: {},
  improvement_proposals: [],
  technical_appendix: {
    methodology_ru: ["Отчёт построен из безопасной версии."],
    sources_ru: ["Внутренние идентификаторы скрыты."],
  },
  analytics: {
    metric_points: [],
    market_points: [],
    readiness_dimensions: [],
  },
};

const advisorQuestion: AdvisorNextQuestionResponse = {
  case_id: caseId,
  status: "active",
  next_question: {
    question_id: `${caseId}:icp`,
    field_key: "icp",
    question_ru: "Кто платит за продукт и почему именно сейчас?",
    reason_ru: "Это уточнит ICP и приоритет канала продаж.",
    unlocks_ru: "После ответа можно пересчитать риск продаж.",
    answer_modes: ["manual", "file", "public_research", "skip"],
    origin: "document_gap",
    origin_label_ru: "Пробел в документе",
    context_ru: "Документ не подтверждает ICP.",
    answer_mode_labels_ru: {
      manual: "Ответить вручную",
      file: "Прикрепить файл",
      public_research: "Разрешить публичный поиск",
      skip: "Пропустить",
    },
  },
  answered_count: 1,
  total_count: 5,
};

const advisorAnswer: AdvisorAnswerResponse = {
  case_id: caseId,
  question_id: `${caseId}:icp`,
  field_key: "icp",
  answer_type: "manual",
  status: "applied",
  confidence_delta: 7,
  analysis_blocked: false,
  answered_count: 2,
  total_count: 5,
  research_result: null,
  recalculation_status: "started",
  recalculation_data_revision: 2,
  recalculation_analysis_status: "gate2_preview_ready",
  recalculation_delta: {
    previous_revision: 1,
    new_revision: 2,
    fields_changed: ["icp"],
    core_coverage_delta: 1,
    conflicts_resolved: 0,
    conflicts_remaining: 0,
    calculations_recalculated: [],
    calculations_pending: ["report"],
  },
};

const advisorImprovementTargets = [
  "POSITIONING",
  "MONETIZATION",
  "METRICS",
  "GTM",
  "RISK_REDUCTION",
  "INVESTOR_READINESS",
] as const;

const advisorImprovements: AdvisorImprovementsResponse = {
  case_id: caseId,
  improvement_version: 6,
  proposals: advisorImprovementTargets.map((targetArea, index) => ({
    proposal_id: `00000000-0000-4000-8000-00000000050${index}`,
    target_area: targetArea,
    recommendation_ru: `Улучшить область ${index + 1}.`,
    rationale_ru: `Бизнес-логика ${index + 1}.`,
    expected_effect_ru: `Эффект для отчёта ${index + 1}.`,
    evidence_kinds: ["live_inference"],
    confidence: 0.7,
  })),
};

function decision(status: StartupCaseStatus): StartupDecisionResult {
  return {
    case_id: status.case_id,
    analysis_status: status.analysis_status,
    gate2_status: status.gate2_status,
    gate3_status: status.gate3_status,
    gate4_status: status.gate4_status,
    report_status: status.report_status,
    snapshot_hash: status.snapshot_hash,
    snapshot_revision: status.snapshot_revision,
  };
}

function api(overrides: Partial<FounderWorkspaceApi> = {}): FounderWorkspaceApi {
  return {
    createCase: async () => created,
    uploadDocuments: async () => uploaded,
    getCase: async () => gate2Status,
    getGate2Preview: async () => gate2Preview,
    getStartupProfile: async () => startupProfile,
    getStartupGtm: async () => startupGtm,
    decideGate2: async () => decision(gate3Status),
    decideGate3: async () => decision(reportStatus),
    decideGate4: async (_id, request) =>
      decision({
        ...reportStatus,
        gate4_status: "completed",
        snapshot_hash: request.snapshot_hash,
        snapshot_revision: request.snapshot_revision,
    }),
    getReport: async () => report,
    getStartupReportSnapshot: async () => ({
      ...canonicalReportSnapshot,
      snapshot_id: report.snapshot_id,
      snapshot_hash: report.snapshot_hash,
      snapshot_revision: report.snapshot_revision,
    }),
    downloadReportArtifact: async () => new Response("%PDF-1.4"),
    reportArtifactUrl: (id, artifact) =>
      `/api/startup/cases/${id}/report/${artifact}`,
    getAdvisorNextQuestion: async () => advisorQuestion,
    submitAdvisorAnswer: async () => advisorAnswer,
    getAdvisorImprovements: async () => advisorImprovements,
    decideAdvisorImprovement: async (_id, proposalId, decisionValue) => ({
      case_id: caseId,
      proposal_id: proposalId,
      decision: decisionValue,
      previous_version: 6,
      new_version: decisionValue === "accepted" ? 7 : 6,
      changed_fields: decisionValue === "accepted" ? ["positioning"] : [],
      recalculation_status: decisionValue === "accepted" ? "started" : "not_requested",
      recalculation_data_revision: decisionValue === "accepted" ? 2 : null,
      recalculation_analysis_status:
        decisionValue === "accepted" ? "gate2_preview_ready" : null,
    }),
    ...overrides,
  };
}

function latest(snapshots: FounderWorkspaceSnapshot[]): FounderWorkspaceSnapshot {
  const snapshot = snapshots.at(-1);
  assert.ok(snapshot);
  return snapshot;
}

test("exposes canonical GTM when Gate 3 review becomes required", async () => {
  const calls: string[] = [];
  const snapshots: FounderWorkspaceSnapshot[] = [];
  const workspaceApi: FounderWorkspaceGtmApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupGtm: async (id) => {
      calls.push(id);
      return startupGtm;
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: (snapshot) => snapshots.push(snapshot),
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.deepEqual(calls, [caseId]);
  assert.deepEqual(snapshotGtm(latest(snapshots)), startupGtm);
});

test("does not fetch canonical GTM before deep analysis is ready", async () => {
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceGtmApi = {
    ...api({
      getCase: async () => gate2Status,
    }),
    getStartupGtm: async (id) => {
      calls.push(id);
      return startupGtm;
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.deepEqual(calls, []);
  assert.equal(snapshotGtm(orchestrator.getSnapshot()), null);
});

test("clears canonical GTM when starting a fresh case", async () => {
  const secondCaseId = "case-founder-002";
  const statuses = [
    gate3Status,
    {
      ...gate2Status,
      case_id: secondCaseId,
      analysis_status: "awaiting_upload",
      gate2_status: "not_ready",
    } satisfies StartupCaseStatus,
  ];
  const workspaceApi: FounderWorkspaceGtmApi = {
    ...api({
      createCase: async () => created,
      getCase: async () => statuses.shift() ?? gate2Status,
      uploadDocuments: async () => uploaded,
    }),
    getStartupGtm: async () => startupGtm,
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["first"], "first.pdf")]);
  assert.deepEqual(snapshotGtm(orchestrator.getSnapshot()), startupGtm);

  await orchestrator.start([new File(["second"], "second.pdf")]);

  assert.equal(snapshotGtm(orchestrator.getSnapshot()), null);
});

test("removes a cached GTM snapshot when the backend reports it stale", async () => {
  let gtmReads = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupGtm: async () => {
        gtmReads += 1;
        if (gtmReads === 1) return startupGtm;
        throw new FounderApiClientError(
          "startup_gtm_stale",
          409,
          "GTM snapshot no longer matches the case revision",
        );
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["first"], "first.pdf")]);
  assert.deepEqual(snapshotGtm(orchestrator.getSnapshot()), startupGtm);

  await orchestrator.refresh();

  assert.equal(snapshotGtm(orchestrator.getSnapshot()), null);
  assert.equal(
    (orchestrator.getSnapshot().error as FounderApiClientError | null)?.code,
    "startup_gtm_stale",
  );
});

test("fails closed when Gate 3 is visible before its GTM snapshot is readable", async () => {
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupGtm: async () => {
        throw new FounderApiClientError(
          "startup_gtm_not_ready",
          404,
          "GTM snapshot is not ready",
        );
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  const snapshot = orchestrator.getSnapshot();
  assert.equal(snapshot.gtm, null);
  assert.equal(snapshot.display.stage, "error");
  assert.equal(
    founderErrorMessage(snapshot.error),
    "План выхода на рынок ещё не готов. Обновите кейс после завершения глубинного анализа.",
  );
});

test("fetches the canonical startup profile when primary preview becomes ready", async () => {
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceProfileApi = {
    ...api({
      getCase: async () => gate2Status,
    }),
    getStartupProfile: async (id) => {
      calls.push(id);
      return startupProfile;
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.deepEqual(calls, [caseId]);
  assert.deepEqual(snapshotProfile(orchestrator.getSnapshot()), startupProfile);
});

test("emits an actionable Gate 2 preview before optional Copilot hydration completes", async () => {
  let releaseCopilotLoad!: () => void;
  let resolveCopilotLoad!: (response: CopilotStateResponse) => void;
  const copilotLoadEntered = new Promise<void>((resolve) => {
    releaseCopilotLoad = resolve;
  });
  const pendingCopilotLoad = new Promise<CopilotStateResponse>((resolve) => {
    resolveCopilotLoad = resolve;
  });
  const gate2Decisions: StartupGate2Decision[] = [];
  let gate2Approved = false;
  const snapshots: FounderWorkspaceSnapshot[] = [];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => (gate2Approved ? gate3Status : gate2Status),
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: 4,
      }),
      getCopilotState: async () => {
        releaseCopilotLoad();
        return pendingCopilotLoad;
      },
      decideGate2: async (_activeCaseId, request) => {
        gate2Decisions.push(request);
        gate2Approved = true;
        return decision(gate3Status);
      },
    }),
    onChange: (snapshot) => snapshots.push(snapshot),
  });

  const startPromise = orchestrator.start([new File(["deck"], "deck.pdf")]);
  await copilotLoadEntered;

  const snapshot = latest(snapshots);
  assert.equal(snapshot.display.stage, "gate2_preview_ready");
  assert.equal(snapshot.gate2Preview?.resume_token, "resume-token-001");
  assert.equal(snapshot.profile?.fields.startup_name.status, "source_fact");
  assert.equal(snapshot.profile?.fields.startup_name.values.length, 1);
  assert.equal(snapshot.profile?.fields.startup_name.evidence_refs.length, 1);
  assert.equal(snapshot.busy, false);

  const decisionPromise = orchestrator.decideGate2("approved");
  resolveCopilotLoad(copilotState());
  await decisionPromise;
  await startPromise;

  assert.deepEqual(gate2Decisions, [
    {
      decision: "approved",
      resume_token: "resume-token-001",
    },
  ]);
  assert.equal(orchestrator.getSnapshot().display.stage, "gate3_review_required");
});

function copilotState(
  overrides: Partial<CopilotStateResponse> = {},
): CopilotStateResponse {
  return {
    case_id: caseId,
    data_revision: 4,
    stage: "idea",
    next_question: "What is current MRR?",
    question_descriptor: null,
    suggested_action: "open_fact_input",
    selected_scenario_key: "base",
    extracted_facts: [
      { field_key: "startup_name", value: "FounderCo", source_type: "source_fact" },
    ],
    prioritized_gaps: [],
    scenario_metrics: [
      {
        metric_key: "mrr",
        label: "MRR",
        source_type: "deterministic_calculation",
        value: null,
        range: {
          conservative: "7.2E+6:1.47E+7",
          base: "3.6E+4:86666.67",
          optimistic: null,
        },
        formula: "mrr",
        dependencies: ["monthly_price", "paying_customers"],
        unit: "KZT/month",
        period: "month",
        confidence: "medium",
        source_refs: [],
        what_would_confirm: "Billing export.",
        validation_plan: "Validate billing export.",
      },
    ],
    fact_coverage: {
      measure: "fact_coverage",
      status: "partial",
      source_fact_count: 1,
      accepted_input_count: 2,
    },
    scenario_completeness: {
      measure: "scenario_completeness",
      status: "partial",
      source_fact_count: 1,
      accepted_input_count: 2,
    },
    accepted_inputs: [
      {
        field_key: "monthly_price",
        kind: "founder_statement",
        status: "accepted",
        value: "35000-40000",
        period: "month",
        rationale: "Founder statement.",
        validation_plan: "Validate invoice data.",
        declared_source: "founder",
        source_refs: [],
      },
      {
        field_key: "paying_customers",
        kind: "public_benchmark",
        status: "accepted",
        value: "40-50",
        period: "month",
        rationale: "Benchmark.",
        validation_plan: "Validate public source.",
        declared_source: "benchmark",
        source_refs: ["11111111-1111-4111-8111-111111111111"],
      },
    ],
    actions: [],
    ...overrides,
  };
}

function copilotAction(
  action: CopilotActionAvailability["action"],
  status: CopilotActionAvailability["status"],
  payload: CopilotActionAvailability["payload"],
  reason = "Need a founder statement or source fact.",
): CopilotActionAvailability {
  return {
    action_id: `action:${action}`,
    action,
    status,
    handler: status === "blocked" ? null : action,
    reason: status === "available" ? null : reason,
    effect_preview: `${action} preview`,
    payload,
  };
}

function copilotSourceStatusRows(): CopilotStateResponse["accepted_inputs"] {
  return [
    {
      field_key: "source_fact",
      kind: "source_fact",
      status: "confirmed",
      value: "Evidence-backed fact",
      period: null,
      rationale: null,
      validation_plan: null,
      declared_source: null,
      source_refs: [],
    },
    {
      field_key: "founder_statement",
      kind: "founder_statement",
      status: "provisional",
      value: "Founder statement",
      period: null,
      rationale: null,
      validation_plan: null,
      declared_source: null,
      source_refs: [],
    },
    {
      field_key: "public_benchmark",
      kind: "public_benchmark",
      status: "external_context",
      value: "Public benchmark",
      period: null,
      rationale: null,
      validation_plan: null,
      declared_source: null,
      source_refs: [],
    },
    {
      field_key: "ai_scenario",
      kind: "ai_scenario",
      status: "planning_assumption",
      value: "AI scenario",
      period: null,
      rationale: null,
      validation_plan: null,
      declared_source: null,
      source_refs: [],
    },
  ];
}

function copilotThread(
  overrides: Partial<CopilotThreadResponse> = {},
): CopilotThreadResponse {
  return {
    thread_id: "99999999-9999-4999-8999-999999999999",
    case_id: caseId,
    data_revision: 4,
    messages: [
      {
        message_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        case_id: caseId,
        data_revision: 4,
        role: "system",
        content: "Case Copilot is attached to this case revision.",
        page_context: "overview",
        current_section: "case_copilot",
        idempotency_fingerprint: null,
        related_evidence_refs: [],
        question_refs: [],
        action_refs: [],
        action_snapshots: [],
        action_result: null,
      },
      {
        message_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        case_id: caseId,
        data_revision: 4,
        role: "assistant",
        content: "What is current MRR?",
        page_context: "overview",
        current_section: "next_question",
        idempotency_fingerprint: null,
        related_evidence_refs: [],
        question_refs: ["question:mrr"],
        action_refs: ["action:open_fact_input"],
        action_snapshots: [
          {
            action_id: "action:open_fact_input",
            action: "open_fact_input",
            status: "requires_input",
            handler: "case_fact_input",
            reason: "Need a founder statement or source fact.",
            effect_preview: "Adds a founder statement without promoting it to source_fact.",
            payload: { field_key: "mrr", expected_case_revision: 4 },
          },
        ],
        action_result: null,
      },
    ],
    ...overrides,
  };
}

function scenarioProjection(
  overrides: Partial<ScenarioProjectionResponse> = {},
): ScenarioProjectionResponse {
  const metric = {
    metric_id: "44444444-4444-4444-8444-444444444444",
    case_id: caseId,
    data_revision: 4,
    metric_key: "mrr",
    value_range: { lower: "1400000", upper: "2000000" },
    unit: "KZT/month",
    period: "month",
    provenance: "deterministic_calculation",
    source_refs: [],
    dependency_refs: [
      "55555555-5555-4555-8555-555555555555",
      "66666666-6666-4666-8666-666666666666",
    ],
    formula_key: "mrr",
    formula_description: "monthly_price * paying_customers",
    confidence: "medium",
    rationale: "Derived from accepted inputs.",
    validation_plan: "Validate billing export.",
    what_would_confirm: "Billing export.",
    acceptance: "needs_validation",
    gaps: [],
  } as const;
  const variant = (scenarioKey: "conservative" | "base" | "optimistic") => ({
    scenario_key: scenarioKey,
    inputs: {},
    metrics: { mrr: metric },
    gaps: {},
  });
  return {
    scenario_set_id: "88888888-8888-4888-8888-888888888888",
    case_id: caseId,
    data_revision: 4,
    selected_scenario_key: "base",
    scenarios: {
      conservative: variant("conservative"),
      base: variant("base"),
      optimistic: variant("optimistic"),
    },
    fact_coverage: {
      measure: "fact_coverage",
      status: "partial",
      source_fact_count: 1,
      accepted_input_count: 2,
    },
    scenario_completeness: {
      measure: "scenario_completeness",
      status: "partial",
      source_fact_count: 1,
      accepted_input_count: 2,
    },
    ...overrides,
  };
}

function scenarioProjectionWithMrrRange(
  revision: number,
  range: Readonly<{ lower: string; upper: string }> | null,
): ScenarioProjectionResponse {
  const projection = scenarioProjection({ data_revision: revision });
  const mrr = {
    ...projection.scenarios.base.metrics.mrr,
    data_revision: revision,
    value_range: range,
    gaps: range ? [] : ["missing:monthly_price"],
  };
  const base = {
    ...projection.scenarios.base,
    metrics: {
      ...projection.scenarios.base.metrics,
      mrr,
    },
  };
  return {
    ...projection,
    scenarios: {
      ...projection.scenarios,
      base,
    },
  };
}

function researchPlanResponse(
  overrides: Partial<ResearchPlanResponse> = {},
): ResearchPlanResponse {
  return {
    case_id: caseId,
    data_revision: 4,
    status: "prepared",
    plan_id: "12121212-1212-4121-8121-121212121212",
    plan_hash: "sha256:task11-plan",
    focus: "public_pricing_analogs",
    query_previews: ["public pricing analogs for comparable startup products"],
    manual_only_keys: ["monthly_recurring_revenue"],
    consent_text: "Consent required for public-only benchmark research.",
    created_at: "2026-08-23T00:00:00Z",
    expires_at: "2026-08-23T00:30:00Z",
    ...overrides,
  };
}

function researchJobResponse(
  overrides: Partial<ResearchJobResponse> = {},
): ResearchJobResponse {
  return {
    case_id: caseId,
    data_revision: 4,
    job_id: "34343434-3434-4343-8343-343434343434",
    plan_id: "12121212-1212-4121-8121-121212121212",
    plan_hash: "sha256:task11-plan",
    status: "completed",
    reason: null,
    acquisition_mode: "live_public_research",
    requested_acquisition_mode: "live_public_research",
    selected_acquisition_mode: "live_public_research",
    accepted_entries: [
      {
        entry_id: "56565656-5656-4656-8656-565656565656",
        provenance: "public_benchmark",
        input_key: "monthly_price",
        url: "https://example.com/public-benchmark",
        publisher: "Example Research",
        publication_date: "2026-08-01",
        retrieval_date: "2026-08-23",
        as_of: "2026-08-01",
        source_class: "industry_report",
        confidence: "medium",
        value: null,
        range: { low: "1000", high: "2000" },
        unit: "USD/month",
        period: "month",
        formula: "public benchmark range",
        dependencies: ["public comparable companies"],
        validation_plan: "Use as external context until founder evidence exists.",
        source_refs: ["78787878-7878-4787-8787-787878787878"],
      },
    ],
    rejected_entries: [],
    citations: ["https://example.com/public-benchmark"],
    manual_only_keys: ["monthly_recurring_revenue"],
    changed_blocks: ["public_benchmarks", "scenarios"],
    stale_scenario_ids: [],
    old_revision: 4,
    new_revision: 5,
    source_refs: ["78787878-7878-4787-8787-787878787878"],
    updated_at: "2026-08-23T00:00:10Z",
    ...overrides,
  };
}

function launchPackResponse(
  overrides: Partial<LaunchPackMetadataResponse> = {},
): LaunchPackMetadataResponse {
  return {
    case_id: caseId,
    data_revision: 4,
    scenario_set_id: "88888888-8888-4888-8888-888888888888",
    selected_scenario_key: "base",
    asset_id: "77777777-7777-4777-8777-777777777777",
    asset_key: "gtm_launch_pack",
    asset_revision: 1,
    status: "draft",
    markdown_url:
      `/api/startup/cases/${caseId}/assets/77777777-7777-4777-8777-777777777777/markdown`,
    csv_url: null,
    provenance_appendix_url:
      `/api/startup/cases/${caseId}/assets/77777777-7777-4777-8777-777777777777/provenance`,
    body_markdown: "## Executive summary\n\nDraft GTM launch pack.",
    ...overrides,
  };
}

test("loads Copilot after profile and scenarios only on same case revision inputs", async () => {
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => {
      calls.push("profile");
      return { ...startupProfile, case_id: caseId, data_revision: 4 };
    },
    getCopilotState: async () => {
      calls.push("copilot");
      return copilotState();
    },
    getScenarios: async () => {
      calls.push("scenarios");
      return scenarioProjection();
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const snapshot = orchestrator.getSnapshot();

  assert.deepEqual(calls, ["profile", "copilot", "scenarios"]);
  assert.equal(snapshot.copilotState?.case_id, caseId);
  assert.equal(snapshot.assumptions?.length, 2);
  assert.equal(snapshot.scenarios?.data_revision, 4);
  assert.equal(snapshot.selectedScenario?.scenario_key, "base");
  assert.equal(snapshot.scenarioCompleteness?.measure, "scenario_completeness");
  assert.equal(snapshot.launchPack, null);
});

test("eager-loads the canonical Copilot thread after same-revision state before scenarios", async () => {
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => {
      calls.push("profile");
      return { ...startupProfile, case_id: caseId, data_revision: 4 };
    },
    getCopilotState: async () => {
      calls.push("copilot");
      return copilotState();
    },
    getCopilotThread: async (id, threadId) => {
      calls.push(`thread:${id}:${threadId ?? "default"}`);
      return copilotThread();
    },
    getScenarios: async () => {
      calls.push("scenarios");
      return scenarioProjection();
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const snapshot = orchestrator.getSnapshot();

  assert.deepEqual(calls, ["profile", "copilot", `thread:${caseId}:default`, "scenarios"]);
  assert.equal(snapshotCopilot(snapshot).copilotThread?.thread_id, "99999999-9999-4999-8999-999999999999");
  assert.equal(snapshotCopilot(snapshot).copilotThread?.data_revision, 4);
});

test("loads scenarios from founder-only accepted inputs without requiring public benchmarks", async () => {
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () =>
      copilotState({
        accepted_inputs: [
          {
            field_key: "monthly_price",
            kind: "founder_statement",
            status: "accepted",
            value: "35000-40000",
            period: "month",
            rationale: "Founder statement.",
            validation_plan: "Validate invoice data.",
            declared_source: "founder",
            source_refs: [],
          },
        ],
      }),
    getScenarios: async () => {
      calls.push("scenarios");
      return scenarioProjection();
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.deepEqual(calls, ["scenarios"]);
  assert.equal(orchestrator.getSnapshot().selectedScenario?.scenario_key, "base");
});

test("does not load scenarios from backend source status legend rows alone", async () => {
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () =>
      copilotState({
        accepted_inputs: copilotSourceStatusRows(),
        scenario_metrics: [],
      }),
    getScenarios: async () => {
      calls.push("scenarios");
      return scenarioProjection();
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.deepEqual(calls, []);
  assert.equal(orchestrator.getSnapshot().scenarios, null);
  assert.equal(orchestrator.getSnapshot().selectedScenario, null);
});

test("loads scenarios from backend source status rows when scenario metrics are materialized", async () => {
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () =>
      copilotState({
        accepted_inputs: copilotSourceStatusRows(),
      }),
    getScenarios: async () => {
      calls.push("scenarios");
      return scenarioProjection();
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.deepEqual(calls, ["scenarios"]);
  assert.equal(orchestrator.getSnapshot().selectedScenario?.scenario_key, "base");
});

test("refetches one stale Copilot state revision before loading scenarios", async () => {
  const copilotRevisions = [3, 4];
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () => {
      calls.push("copilot");
      return copilotState({ data_revision: copilotRevisions.shift() ?? 4 });
    },
    getScenarios: async () => {
      calls.push("scenarios");
      return scenarioProjection();
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const snapshot = orchestrator.getSnapshot();

  assert.deepEqual(calls, ["copilot", "copilot", "scenarios"]);
  assert.equal(snapshot.error, null);
  assert.equal(snapshot.copilotState?.data_revision, 4);
  assert.equal(snapshot.scenarios?.data_revision, 4);
});

test("refetches one stale scenario projection before accepting a same-revision response", async () => {
  const revisions = [5, 4];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () => copilotState(),
    getScenarios: async () =>
      scenarioProjection({ data_revision: revisions.shift() ?? 4 }),
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const snapshot = orchestrator.getSnapshot();

  assert.equal(snapshot.error, null);
  assert.equal(snapshot.scenarios?.data_revision, 4);
  assert.equal(snapshot.selectedScenario?.scenario_key, "base");
});

test("discards stale scenario projections instead of merging them into the workspace", async () => {
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () => copilotState(),
    getScenarios: async () => scenarioProjection({ data_revision: 5 }),
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const snapshot = orchestrator.getSnapshot();

  assert.equal(snapshot.selectedScenario, null);
  assert.equal(snapshot.scenarios, null);
  assert.ok(snapshot.error);
  assert.match(snapshot.error.message, /lineage mismatch/);
});

test("generates a launch pack only for the active case revision and selected scenario", async () => {
  const calls: { caseId: string; request: unknown }[] = [];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () => copilotState(),
    getScenarios: async () => scenarioProjection(),
    generateLaunchPack: async (activeCaseId, request) => {
      calls.push({ caseId: activeCaseId, request });
      return launchPackResponse();
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.generateLaunchPack();
  const snapshot = orchestrator.getSnapshot();

  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.caseId, caseId);
  assert.deepEqual(calls[0]?.request, {
    asset_type: "gtm_launch_pack",
    selected_scenario_key: "base",
    expected_case_revision: 4,
    idempotency_key: (calls[0]?.request as { idempotency_key: string }).idempotency_key,
  });
  assert.match(
    (calls[0]?.request as { idempotency_key: string }).idempotency_key,
    /[0-9a-f-]{36}/iu,
  );
  assert.equal(snapshot.launchPack?.asset_key, "gtm_launch_pack");
  assert.equal(snapshot.launchPack?.status, "draft");
  assert.equal(snapshot.launchPack?.selected_scenario_key, "base");
  assert.equal(snapshot.error, null);
});

test("ignores stale queued polling callbacks while generating a launch pack", async () => {
  let caseReads = 0;
  let queuedPoll: (() => void) | null = null;
  let activeLaunchPackSignal: AbortSignal | undefined;
  let resolveLaunchPack!: (response: LaunchPackMetadataResponse) => void;
  const launchPackRequest = new Promise<LaunchPackMetadataResponse>((resolve) => {
    resolveLaunchPack = resolve;
  });
  const runningStatus: StartupCaseStatus = {
    ...gate2Status,
    analysis_status: "awaiting_start",
    gate2_status: "completed",
  };
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => {
        caseReads += 1;
        if (caseReads === 1) return runningStatus;
        return gate3Status;
      },
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () => copilotState(),
    getScenarios: async () => scenarioProjection(),
    generateLaunchPack: async (_activeCaseId, _request, options) => {
      activeLaunchPackSignal = options?.signal;
      return launchPackRequest;
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
    schedule: (callback) => {
      queuedPoll = callback;
      return () => {
        queuedPoll = null;
      };
    },
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const staleQueuedPoll = queuedPoll as (() => void) | null;
  assert.ok(staleQueuedPoll);

  await orchestrator.refresh();
  const launchPack = orchestrator.generateLaunchPack();
  await Promise.resolve();

  staleQueuedPoll();
  await Promise.resolve();

  assert.equal(activeLaunchPackSignal?.aborted, false);
  resolveLaunchPack(launchPackResponse());
  await launchPack;

  const snapshot = orchestrator.getSnapshot();
  assert.equal(snapshot.busy, false);
  assert.equal(snapshot.launchPack?.asset_key, "gtm_launch_pack");
  assert.equal(snapshot.launchPack?.status, "draft");
  assert.equal(snapshot.error, null);
});

test("shows specific busy activities for scenario and launch-pack generation", async () => {
  const snapshots: FounderWorkspaceSnapshot[] = [];
  let scenarioSelectCalls = 0;
  let assetCalls = 0;
  let releaseScenario!: () => void;
  let releaseAsset!: () => void;
  const pendingScenario = new Promise<void>((resolve) => {
    releaseScenario = resolve;
  });
  const pendingAsset = new Promise<void>((resolve) => {
    releaseAsset = resolve;
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: 4,
      }),
      getCopilotState: async () => copilotState(),
      getScenarios: async () => scenarioProjection(),
      selectScenario: async (_activeCaseId, request) => {
        scenarioSelectCalls += 1;
        await pendingScenario;
        return {
          case_id: caseId,
          data_revision: request.expected_case_revision,
          scenario_set_id: request.scenario_set_id ?? "scenario-set-case-founder-001",
          old_scenario_key: "base",
          new_scenario_key: request.scenario_key,
          changed_keys: ["selected_scenario_key"],
        };
      },
      generateLaunchPack: async (_activeCaseId, request) => {
        assetCalls += 1;
        await pendingAsset;
        return launchPackResponse({ asset_key: request.asset_type });
      },
    }),
    onChange: (snapshot) => snapshots.push(snapshot),
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  const selectScenario = orchestrator.selectScenario("optimistic");
  await Promise.resolve();
  await orchestrator.selectScenario("optimistic");
  assert.equal(scenarioSelectCalls, 1);
  assert.equal(latest(snapshots).activity, "scenario_selecting");
  assert.equal(latest(snapshots).display.stage, "gate3_review_required");
  releaseScenario();
  await selectScenario;

  const generateAsset = orchestrator.generateAsset("pricing_experiment");
  await Promise.resolve();
  await orchestrator.generateAsset("pricing_experiment");
  assert.equal(assetCalls, 1);
  assert.equal(latest(snapshots).activity, "asset_generating");
  assert.equal(latest(snapshots).display.stage, "gate3_review_required");
  releaseAsset();
  await generateAsset;

  let releaseLaunchPack!: () => void;
  const pendingLaunchPack = new Promise<void>((resolve) => {
    releaseLaunchPack = resolve;
  });
  const launchPackOrchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: 4,
      }),
      getCopilotState: async () => copilotState(),
      getScenarios: async () => scenarioProjection(),
      generateLaunchPack: async (_activeCaseId, request) => {
        assetCalls += 1;
        await pendingLaunchPack;
        return launchPackResponse({ asset_key: request.asset_type });
      },
    }),
    onChange: (snapshot) => snapshots.push(snapshot),
  });
  await launchPackOrchestrator.start([new File(["deck"], "deck.pdf")]);
  const generateLaunchPack = launchPackOrchestrator.generateLaunchPack();
  await Promise.resolve();
  assert.equal(latest(snapshots).activity, "launch_pack_generating");
  assert.equal(latest(snapshots).display.stage, "gate3_review_required");
  releaseLaunchPack();
  await generateLaunchPack;
});

test("hydrates only GTM launch pack after restart when newer base assets exist", async () => {
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () => copilotState(),
    getScenarios: async () => scenarioProjection(),
    listCaseAssets: async () => ({
      case_id: caseId,
      data_revision: 4,
      assets: [
        launchPackResponse({
          asset_key: "weekly_funnel_template",
          asset_revision: 3,
          csv_url:
            `/api/startup/cases/${caseId}/assets/77777777-7777-4777-8777-777777777777/csv`,
          body_markdown: "## Weekly funnel template\n\nDraft base asset.",
        }),
        launchPackResponse({
          asset_key: "gtm_launch_pack",
          asset_revision: 1,
          body_markdown: "## Executive summary\n\nDraft GTM launch pack.",
        }),
      ],
    }),
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const snapshot = orchestrator.getSnapshot();

  assert.equal(snapshot.launchPack?.asset_key, "gtm_launch_pack");
  assert.equal(snapshot.launchPack?.asset_revision, 1);
  assert.match(snapshot.launchPack?.body_markdown ?? "", /Executive summary/u);
});

test("resumes an existing case by hydrating same-lineage profile Copilot scenarios and launch pack", async () => {
  const resumedCaseId = "11111111-1111-4111-8111-111111111111";
  const calls: string[] = [];
  const resumedScenarios = scenarioProjection({ case_id: resumedCaseId });
  const resumedLaunchPack = launchPackResponse({
    case_id: resumedCaseId,
    asset_revision: 3,
    scenario_set_id: resumedScenarios.scenario_set_id,
  });
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      createCase: async () => {
        throw new Error("resume must not create a case");
      },
      uploadDocuments: async () => {
        throw new Error("resume must not upload documents");
      },
      getCase: async (activeCaseId) => {
        calls.push(`case:${activeCaseId}`);
        return { ...gate3Status, case_id: activeCaseId };
      },
    }),
    getStartupProfile: async (activeCaseId) => {
      calls.push(`profile:${activeCaseId}`);
      return { ...startupProfile, case_id: activeCaseId, data_revision: 4 };
    },
    getCopilotState: async (activeCaseId) => {
      calls.push(`copilot:${activeCaseId}`);
      return copilotState({ case_id: activeCaseId });
    },
    getCopilotThread: async (activeCaseId) => {
      calls.push(`thread:${activeCaseId}`);
      return copilotThread({ case_id: activeCaseId });
    },
    getScenarios: async (activeCaseId) => {
      calls.push(`scenarios:${activeCaseId}`);
      return { ...resumedScenarios, case_id: activeCaseId };
    },
    listCaseAssets: async (activeCaseId) => {
      calls.push(`assets:${activeCaseId}`);
      return {
        case_id: activeCaseId,
        data_revision: 4,
        assets: [{ ...resumedLaunchPack, case_id: activeCaseId }],
      };
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  const resumed = await orchestrator.resumeCase(resumedCaseId);
  const snapshot = orchestrator.getSnapshot();

  assert.equal(resumed, "resumed");
  assert.deepEqual(calls, [
    `case:${resumedCaseId}`,
    `profile:${resumedCaseId}`,
    `copilot:${resumedCaseId}`,
    `thread:${resumedCaseId}`,
    `scenarios:${resumedCaseId}`,
    `assets:${resumedCaseId}`,
  ]);
  assert.equal(snapshot.caseId, resumedCaseId);
  assert.equal(snapshot.uploadAccepted, true);
  assert.equal(snapshot.profile?.case_id, resumedCaseId);
  assert.equal(snapshot.copilotThread?.case_id, resumedCaseId);
  assert.equal(snapshot.selectedScenario?.scenario_key, "base");
  assert.equal(snapshot.launchPack?.case_id, resumedCaseId);
  assert.equal(snapshot.launchPack?.asset_revision, 3);
  assert.equal(snapshot.error, null);
});

test("resumeCase retries a transient hydration failure and preserves the active case", async () => {
  const resumedCaseId = "11111111-1111-4111-8111-111111111111";
  const calls: string[] = [];
  const retryDelays: number[] = [];
  const scheduledRetries: (() => void)[] = [];
  let createCalls = 0;
  let uploadCalls = 0;
  let caseAttempts = 0;
  let profileAttempts = 0;
  let copilotAttempts = 0;
  let threadAttempts = 0;
  let scenarioAttempts = 0;
  let assetAttempts = 0;
  const resumedScenarios = scenarioProjection({ case_id: resumedCaseId });
  const resumedLaunchPack = launchPackResponse({
    case_id: resumedCaseId,
    asset_revision: 3,
    scenario_set_id: resumedScenarios.scenario_set_id,
  });
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      createCase: async () => {
        createCalls += 1;
        throw new Error("resume must not create a case");
      },
      uploadDocuments: async () => {
        uploadCalls += 1;
        throw new Error("resume must not upload documents");
      },
      getCase: async (activeCaseId) => {
        caseAttempts += 1;
        calls.push(`case:${activeCaseId}`);
        return { ...gate3Status, case_id: activeCaseId };
      },
      getStartupGtm: async (activeCaseId) => ({
        ...startupGtm,
        case_id: activeCaseId,
      }),
    }),
    getStartupProfile: async (activeCaseId) => {
      profileAttempts += 1;
      calls.push(`profile:${activeCaseId}`);
      if (profileAttempts === 1) {
        throw new FounderApiClientError(
          "api_timeout",
          503,
          "Transient profile hydration timeout after service restart",
        );
      }
      return { ...startupProfile, case_id: activeCaseId, data_revision: 4 };
    },
    getCopilotState: async (activeCaseId) => {
      copilotAttempts += 1;
      calls.push(`copilot:${activeCaseId}`);
      return copilotState({ case_id: activeCaseId });
    },
    getCopilotThread: async (activeCaseId) => {
      threadAttempts += 1;
      calls.push(`thread:${activeCaseId}`);
      return copilotThread({ case_id: activeCaseId });
    },
    getScenarios: async (activeCaseId) => {
      scenarioAttempts += 1;
      calls.push(`scenarios:${activeCaseId}`);
      return { ...resumedScenarios, case_id: activeCaseId };
    },
    listCaseAssets: async (activeCaseId) => {
      assetAttempts += 1;
      calls.push(`assets:${activeCaseId}`);
      return {
        case_id: activeCaseId,
        data_revision: 4,
        assets: [{ ...resumedLaunchPack, case_id: activeCaseId }],
      };
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
    schedule: (callback, delayMs) => {
      retryDelays.push(delayMs);
      scheduledRetries.push(callback);
      return () => {
        const index = scheduledRetries.indexOf(callback);
        if (index >= 0) scheduledRetries.splice(index, 1);
      };
    },
  });

  const resumedPromise = orchestrator.resumeCase(resumedCaseId);
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(scheduledRetries.length, 1);
  scheduledRetries.shift()?.();
  await new Promise((resolve) => setTimeout(resolve, 0));

  const resumed = await resumedPromise;
  const snapshot = orchestrator.getSnapshot();

  assert.equal(resumed, "resumed");
  assert.deepEqual(calls, [
    `case:${resumedCaseId}`,
    `profile:${resumedCaseId}`,
    `case:${resumedCaseId}`,
    `profile:${resumedCaseId}`,
    `copilot:${resumedCaseId}`,
    `thread:${resumedCaseId}`,
    `scenarios:${resumedCaseId}`,
    `assets:${resumedCaseId}`,
  ]);
  assert.deepEqual(
    {
      createCalls,
      uploadCalls,
      caseAttempts,
      profileAttempts,
      copilotAttempts,
      threadAttempts,
      scenarioAttempts,
      assetAttempts,
      scheduledRetries: retryDelays.length,
    },
    {
      createCalls: 0,
      uploadCalls: 0,
      caseAttempts: 2,
      profileAttempts: 2,
      copilotAttempts: 1,
      threadAttempts: 1,
      scenarioAttempts: 1,
      assetAttempts: 1,
      scheduledRetries: 1,
    },
  );
  assert.equal(snapshot.caseId, resumedCaseId);
  assert.equal(snapshot.uploadAccepted, true);
  assert.equal(snapshot.profile?.case_id, resumedCaseId);
  assert.equal(snapshot.copilotState?.case_id, resumedCaseId);
  assert.equal(snapshot.copilotThread?.case_id, resumedCaseId);
  assert.equal(snapshot.scenarios?.case_id, resumedCaseId);
  assert.equal(snapshot.selectedScenario?.scenario_key, "base");
  assert.equal(snapshot.launchPack?.case_id, resumedCaseId);
  assert.equal(snapshot.launchPack?.asset_revision, 3);
  assert.equal(snapshot.error, null);
});

test("resumeCase clears a typed 404 missing case without retrying", async () => {
  const resumedCaseId = "11111111-1111-4111-8111-111111111111";
  let getCaseAttempts = 0;
  let scheduledRetries = 0;
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      createCase: async () => {
        throw new Error("resume must not create a case");
      },
      uploadDocuments: async () => {
        throw new Error("resume must not upload documents");
      },
      getCase: async () => {
        getCaseAttempts += 1;
        throw new FounderApiClientError(
          "case_not_found",
          404,
          "Case does not exist after restart",
        );
      },
    }),
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
    schedule: () => {
      scheduledRetries += 1;
      return () => undefined;
    },
  });

  const resumed = await orchestrator.resumeCase(resumedCaseId);
  const snapshot = orchestrator.getSnapshot();

  assert.equal(resumed, "missing");
  assert.equal(getCaseAttempts, 1);
  assert.equal(scheduledRetries, 0);
  assert.equal(snapshot.caseId, null);
  assert.equal(snapshot.uploadAccepted, false);
  assert.equal(snapshot.error, null);
});

test("resumeCase exhausts transient hydration retries without clearing the case", async () => {
  const resumedCaseId = "11111111-1111-4111-8111-111111111111";
  const retryDelays: number[] = [];
  const scheduledRetries: (() => void)[] = [];
  let getCaseAttempts = 0;
  let profileAttempts = 0;
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async (activeCaseId) => {
        getCaseAttempts += 1;
        return { ...gate3Status, case_id: activeCaseId };
      },
    }),
    getStartupProfile: async () => {
      profileAttempts += 1;
      throw new FounderApiClientError(
        "api_timeout",
        503,
        "Transient profile hydration timeout after service restart",
      );
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
    schedule: (callback, delayMs) => {
      retryDelays.push(delayMs);
      scheduledRetries.push(callback);
      return () => {
        const index = scheduledRetries.indexOf(callback);
        if (index >= 0) scheduledRetries.splice(index, 1);
      };
    },
  });

  const resumedPromise = orchestrator.resumeCase(resumedCaseId);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(scheduledRetries.length, 1);
  scheduledRetries.shift()?.();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(scheduledRetries.length, 1);
  scheduledRetries.shift()?.();
  await new Promise((resolve) => setTimeout(resolve, 0));

  const resumed = await resumedPromise;
  const snapshot = orchestrator.getSnapshot();

  assert.equal(resumed, "retryable_failure");
  assert.deepEqual(retryDelays, [250, 500]);
  assert.equal(getCaseAttempts, 3);
  assert.equal(profileAttempts, 3);
  assert.equal(snapshot.caseId, resumedCaseId);
  assert.equal(snapshot.uploadAccepted, true);
  assert.equal((snapshot.error as FounderApiClientError | null)?.code, "api_timeout");
});

test("dispose cancels a pending resume retry", async () => {
  const resumedCaseId = "11111111-1111-4111-8111-111111111111";
  const scheduledRetries: (() => void)[] = [];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async (activeCaseId) => ({ ...gate3Status, case_id: activeCaseId }),
    }),
    getStartupProfile: async () => {
      throw new FounderApiClientError(
        "api_timeout",
        503,
        "Transient profile hydration timeout after service restart",
      );
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
    schedule: (callback) => {
      scheduledRetries.push(callback);
      return () => {
        const index = scheduledRetries.indexOf(callback);
        if (index >= 0) scheduledRetries.splice(index, 1);
      };
    },
  });

  const resumedPromise = orchestrator.resumeCase(resumedCaseId);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(scheduledRetries.length, 1);

  orchestrator.dispose();

  assert.equal(scheduledRetries.length, 0);
  assert.equal(await resumedPromise, "retryable_failure");
});

test("newer refresh cancels a pending resume retry and clears busy state", async () => {
  const resumedCaseId = "11111111-1111-4111-8111-111111111111";
  const calls: string[] = [];
  const scheduledRetries: (() => void)[] = [];
  let profileAttempts = 0;
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async (activeCaseId) => {
        calls.push(`case:${activeCaseId}`);
        return { ...gate3Status, case_id: activeCaseId };
      },
      getStartupGtm: async (activeCaseId) => ({
        ...startupGtm,
        case_id: activeCaseId,
      }),
    }),
    getStartupProfile: async (activeCaseId) => {
      profileAttempts += 1;
      calls.push(`profile:${activeCaseId}`);
      if (profileAttempts === 1) {
        throw new FounderApiClientError(
          "api_timeout",
          503,
          "Transient profile hydration timeout after service restart",
        );
      }
      return { ...startupProfile, case_id: activeCaseId, data_revision: 4 };
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
    schedule: (callback) => {
      scheduledRetries.push(callback);
      return () => {
        const index = scheduledRetries.indexOf(callback);
        if (index >= 0) scheduledRetries.splice(index, 1);
      };
    },
  });

  const resumedPromise = orchestrator.resumeCase(resumedCaseId);
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(orchestrator.getSnapshot().busy, true);
  assert.equal(scheduledRetries.length, 1);
  const staleResumeRetry = scheduledRetries[0];

  const refreshPromise = orchestrator.refresh();

  assert.equal(scheduledRetries.length, 0);
  assert.equal(await resumedPromise, "retryable_failure");
  await refreshPromise;
  staleResumeRetry?.();
  await new Promise((resolve) => setTimeout(resolve, 0));

  const snapshot = orchestrator.getSnapshot();
  assert.deepEqual(calls, [
    `case:${resumedCaseId}`,
    `profile:${resumedCaseId}`,
    `case:${resumedCaseId}`,
    `profile:${resumedCaseId}`,
  ]);
  assert.equal(snapshot.busy, false);
  assert.equal(snapshot.caseId, resumedCaseId);
  assert.equal(snapshot.uploadAccepted, true);
  assert.equal(snapshot.profile?.case_id, resumedCaseId);
  assert.equal(snapshot.error, null);
});

test("ignores invalid resume case identifiers without creating or uploading", async () => {
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      createCase: async () => {
        calls.push("create");
        return created;
      },
      uploadDocuments: async () => {
        calls.push("upload");
        return uploaded;
      },
      getCase: async () => {
        calls.push("case");
        return gate3Status;
      },
    }),
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  const resumed = await orchestrator.resumeCase("case-founder-001");

  assert.equal(resumed, "missing");
  assert.deepEqual(calls, []);
  assert.equal(orchestrator.getSnapshot().caseId, null);
  assert.equal(orchestrator.getSnapshot().error, null);
});

test("rejects launch pack lineage mismatches before updating workspace state", async () => {
  const workspaceApi: FounderWorkspaceApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async () => ({
      ...startupProfile,
      case_id: caseId,
      data_revision: 4,
    }),
    getCopilotState: async () => copilotState(),
    getScenarios: async () => scenarioProjection(),
    generateLaunchPack: async () =>
      launchPackResponse({
        selected_scenario_key: "optimistic",
      }),
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.generateLaunchPack();
  const snapshot = orchestrator.getSnapshot();

  assert.equal(snapshot.launchPack, null);
  assert.ok(snapshot.error);
  assert.match(snapshot.error.message, /Launch pack lineage mismatch/u);
});

test("refreshes the startup profile to the enriched revision during deep analysis", async () => {
  const calls: string[] = [];
  const enrichedProfile: StartupProfileResponse = {
    ...startupProfile,
    profile_id: enrichedProfileId,
    profile_hash: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    data_revision: 2,
    analysis_stage: "enriched",
    parent_profile_id: startupProfile.profile_id,
  };
  const workspaceApi: FounderWorkspaceProfileApi = {
    ...api({
      getCase: async () => gate3Status,
    }),
    getStartupProfile: async (id) => {
      calls.push(id);
      return calls.length === 1 ? startupProfile : enrichedProfile;
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.refresh();

  assert.deepEqual(calls, [caseId, caseId]);
  assert.equal(snapshotProfile(orchestrator.getSnapshot())?.analysis_stage, "enriched");
  assert.equal(
    snapshotProfile(orchestrator.getSnapshot())?.parent_profile_id,
    primaryProfileId,
  );
});

test("does not fetch startup profile before primary profile readiness", async () => {
  const calls: string[] = [];
  const workspaceApi: FounderWorkspaceProfileApi = {
    ...api({
      getCase: async () => ({
        ...gate2Status,
        analysis_status: "awaiting_start",
        gate2_status: "not_ready",
      }),
    }),
    getStartupProfile: async (id) => {
      calls.push(id);
      return startupProfile;
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
    schedule: () => () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.deepEqual(calls, []);
  assert.equal(snapshotProfile(orchestrator.getSnapshot()), null);
});

test("clears cached startup profile when starting a fresh case", async () => {
  const secondCaseId = "case-founder-002";
  const statuses = [
    gate2Status,
    {
      ...gate2Status,
      case_id: secondCaseId,
      analysis_status: "awaiting_upload",
      gate2_status: "not_ready",
    } satisfies StartupCaseStatus,
  ];
  const workspaceApi: FounderWorkspaceProfileApi = {
    ...api({
      createCase: async () => created,
      getCase: async () => statuses.shift() ?? gate2Status,
      uploadDocuments: async () => uploaded,
    }),
    getStartupProfile: async () => startupProfile,
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["first"], "first.pdf")]);
  assert.deepEqual(snapshotProfile(orchestrator.getSnapshot()), startupProfile);

  await orchestrator.start([new File(["second"], "second.pdf")]);

  assert.equal(snapshotProfile(orchestrator.getSnapshot()), null);
});

test("clears cached startup profile before stale profile failures", async () => {
  let profileReads = 0;
  const workspaceApi: FounderWorkspaceProfileApi = {
    ...api({
      getCase: async () => gate2Status,
    }),
    getStartupProfile: async () => {
      profileReads += 1;
      if (profileReads === 1) return startupProfile;
      throw new FounderApiClientError(
        "startup_profile_stale",
        409,
        "Profile snapshot no longer matches the case revision",
      );
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["first"], "first.pdf")]);
  assert.deepEqual(snapshotProfile(orchestrator.getSnapshot()), startupProfile);

  await orchestrator.refresh();

  assert.equal(snapshotProfile(orchestrator.getSnapshot()), null);
  assert.equal(
    (orchestrator.getSnapshot().error as FounderApiClientError | null)?.code,
    "startup_profile_stale",
  );
});

test("maps startup profile API failures to founder-safe copy", () => {
  assert.equal(
    founderErrorMessage(
      new FounderApiClientError(
        "startup_profile_not_ready",
        409,
        "startup_profile_not_ready",
      ),
    ),
    "Профиль стартапа ещё не готов. Обновите кейс после первичного разбора документов.",
  );
  assert.equal(
    founderErrorMessage(
      new FounderApiClientError(
        "startup_profile_stale",
        409,
        "startup_profile_stale",
      ),
    ),
    "Профиль стартапа устарел относительно текущей версии кейса. Обновите анализ перед продолжением.",
  );
  assert.equal(
    founderErrorMessage(
      new FounderApiClientError(
        "advisor_manual_answer_semantic_mismatch",
        422,
        "advisor_manual_answer_semantic_mismatch",
      ),
    ),
    "Ответ не похож на данные для текущего вопроса. Для выручки укажите MRR, ARR, цену, тариф или модель оплаты.",
  );
  assert.equal(
    founderErrorMessage(
      new FounderApiClientError(
        "startup_market_fixture_unavailable",
        500,
        "startup_market_fixture_unavailable",
      ),
    ),
    "Пакет офлайн-данных рынка недоступен. Кейс и документы сохранены; обновите локальную сборку и повторите анализ.",
  );
});

test("keeps every owner-facing mapped error free from Gate and token jargon", () => {
  const mappedErrorCodes = [
    "api_unreachable",
    "api_timeout",
    "empty_upload",
    "unsafe_path",
    "request_validation_error",
    "startup_document_intelligence_input_invalid",
    "resume_token_invalid",
    "startup_gtm_not_ready",
    "startup_gtm_stale",
    "startup_market_fixture_unavailable",
    "startup_profile_not_ready",
    "startup_profile_stale",
    "startup_report_snapshot_stale",
    "advisor_manual_answer_semantic_mismatch",
    "gate_3_not_ready",
    "report_not_ready",
    "gate_4_snapshot_mismatch",
    "report_renderer_unavailable",
  ];

  for (const code of mappedErrorCodes) {
    assert.doesNotMatch(
      founderErrorMessage(Object.assign(new Error(code), { code })),
      /Gate\s*\d|токен|token/u,
      `mapped owner-facing error ${code} must not expose workflow jargon`,
    );
  }
});

test("creates one idle live case, uploads the actual files, and only then starts toward Gate 2", async () => {
  const calls: Array<{ operation: string; value: unknown }> = [];
  const snapshots: FounderWorkspaceSnapshot[] = [];
  const selected = [new File(["pitch"], "pitch.pdf", { type: "application/pdf" })];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      createCase: async (request) => {
        calls.push({ operation: "create", value: request });
        return created;
      },
      uploadDocuments: async (id, request) => {
        calls.push({ operation: "upload", value: { id, request } });
        return uploaded;
      },
    }),
    onChange: (snapshot) => snapshots.push(snapshot),
  });

  await orchestrator.start(selected);

  assert.deepEqual(calls[0], {
    operation: "create",
    value: { fixture_mode: "live", auto_start: false },
  });
  const uploadCall = calls[1]?.value as {
    id: string;
    request: { files: readonly File[]; auto_start: boolean };
  };
  assert.equal(uploadCall.id, caseId);
  assert.equal(uploadCall.request.files[0], selected[0]);
  assert.equal(uploadCall.request.auto_start, true);
  assert.equal(latest(snapshots).display.stage, "gate2_preview_ready");
  assert.deepEqual(latest(snapshots).gate2Preview?.preview, {
    document_count: 1,
    detected_company: "FounderCo",
  });
});

test("loads startup profile when analysis reaches Gate 2 before gate2_status flips required", async () => {
  let profileReads = 0;
  const selected = [new File(["pitch"], "pitch.pdf", { type: "application/pdf" })];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => ({
        ...gate2Status,
        gate2_status: "not_ready",
      }),
      getStartupProfile: async () => {
        profileReads += 1;
        return startupProfile;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start(selected);

  assert.equal(orchestrator.getSnapshot().display.stage, "gate2_preview_ready");
  assert.equal(profileReads, 1);
  assert.deepEqual(snapshotProfile(orchestrator.getSnapshot()), startupProfile);
});

test("uses explicit launch offline mode without replacing the uploaded files", async () => {
  const calls: Array<{ operation: string; value: unknown }> = [];
  const selected = [new File(["real uploaded pitch"], "real-pitch.pdf")];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      createCase: async (request) => {
        calls.push({ operation: "create", value: request });
        return { ...created, provider_status: "deterministic_offline_fixture" };
      },
      getCase: async () => ({
        ...gate2Status,
        provider_status: "deterministic_offline_fixture",
      }),
      getGate2Preview: async () => ({
        ...gate2Preview,
        provider_mode: "deterministic_offline_fixture",
      }),
      uploadDocuments: async (id, request) => {
        calls.push({ operation: "upload", value: { id, request } });
        return uploaded;
      },
    }),
    caseFixtureMode: normalizeFounderCaseFixtureMode("deterministic_offline"),
    onChange: () => undefined,
  });

  await orchestrator.start(selected);

  assert.deepEqual(calls[0], {
    operation: "create",
    value: { fixture_mode: "deterministic_offline", auto_start: false },
  });
  const uploadCall = calls[1]?.value as {
    request: { files: readonly File[]; auto_start: boolean };
  };
  assert.equal(uploadCall.request.files[0], selected[0]);
  assert.equal(orchestrator.getSnapshot().display.providerSignal, "offline_fixture_active");
});

test("fails closed on an unknown launch fixture mode", () => {
  assert.throws(
    () => normalizeFounderCaseFixtureMode("demo"),
    /Unsupported FOUNDER_CASE_FIXTURE_MODE/,
  );
});

test("home page stays static and lets the browser resolve runtime fixture mode", () => {
  const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(page, /export const dynamic\s*=\s*"force-dynamic"/u);
  assert.doesNotMatch(page, /process\.env\.FOUNDER_CASE_FIXTURE_MODE/u);
  assert.match(page, /<FounderWorkspaceController\s*\/>/u);
  assert.match(controller, /resolveFounderRuntimeConfig/u);
  assert.match(controller, /runtimeMode === null/u);
  assert.doesNotMatch(controller, /caseFixtureMode = "live"/u);
});

test("controller persists only the active case UUID and resumes after runtime mode resolves", () => {
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const storage = readFileSync(
    new URL("../lib/founder-case-storage.ts", import.meta.url),
    "utf8",
  );

  assert.match(storage, /FOUNDER_ACTIVE_CASE_STORAGE_KEY/u);
  assert.match(controller, /readStoredFounderCaseId/u);
  assert.match(controller, /readLinkedFounderCaseId\(globalThis\.location\)/u);
  assert.match(controller, /linkedCaseId \?\? readStoredFounderCaseId/u);
  assert.match(controller, /writeStoredFounderCaseId/u);
  assert.match(controller, /clearStoredFounderCaseId/u);
  assert.match(controller, /instance\.resumeCase\(storedCaseId\)/u);
  assert.match(controller, /runtimeMode === null/u);
  assert.doesNotMatch(controller, /localStorage\.setItem\([^,]+,\s*JSON\.stringify/u);
});

test("keeps founder and admin linked to the same visible case identity", () => {
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const shell = readFileSync(new URL("./founder-shell.tsx", import.meta.url), "utf8");
  const adminPage = readFileSync(new URL("../app/admin/page.tsx", import.meta.url), "utf8");

  assert.match(
    controller,
    /function syncLinkedFounderCaseId\(caseId: string\): void \{[\s\S]*?founderUrlForCase\(globalThis\.location\.href,\s*caseId\)/u,
  );
  assert.match(controller, /syncLinkedFounderCaseId\(nextSnapshot\.caseId\)/u);
  assert.match(controller, /history\.replaceState\(history\.state,\s*"",\s*nextUrl\)/u);
  assert.match(shell, /caseId\?:\s*string/u);
  assert.match(shell, /adminConsoleLinkForCase\(workspace\?\.caseId/u);
  assert.match(shell, /data-founder-case-identity/u);
  assert.match(shell, /<code>\{workspace\.caseId\}<\/code>/u);
  assert.match(shell, /Открыть в Admin/u);
  assert.match(adminPage, /adminRedirectUrl/u);
  assert.match(adminPage, /type AdminRedirectSearchParams = Promise/u);
  assert.match(adminPage, /searchParams:\s*AdminRedirectSearchParams/u);
});

test("prevents duplicate case creation while the first submit is pending", async () => {
  let releaseCreate!: (value: StartupCreateResponse) => void;
  const pendingCreate = new Promise<StartupCreateResponse>((resolve) => {
    releaseCreate = resolve;
  });
  let createCalls = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      createCase: async () => {
        createCalls += 1;
        return pendingCreate;
      },
    }),
    onChange: () => undefined,
  });
  const files = [new File(["deck"], "deck.pdf")];

  const first = orchestrator.start(files);
  const second = orchestrator.start(files);
  releaseCreate(created);
  await Promise.all([first, second]);

  assert.equal(createCalls, 1);
});

test("retries a failed upload inside the already-created case", async () => {
  let createCalls = 0;
  let uploadCalls = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      createCase: async () => {
        createCalls += 1;
        return created;
      },
      uploadDocuments: async () => {
        uploadCalls += 1;
        if (uploadCalls === 1) {
          throw new FounderApiClientError(
            "api_unreachable",
            0,
            "Upload connection failed",
          );
        }
        return uploaded;
      },
    }),
    onChange: () => undefined,
  });
  const files = [new File(["deck"], "deck.pdf")];

  await orchestrator.start(files);
  assert.equal(orchestrator.getSnapshot().caseId, caseId);
  assert.equal(orchestrator.getSnapshot().uploadAccepted, false);

  await orchestrator.start(files);

  assert.equal(createCalls, 1);
  assert.equal(uploadCalls, 2);
  assert.equal(orchestrator.getSnapshot().uploadAccepted, true);
  assert.equal(orchestrator.getSnapshot().display.stage, "gate2_preview_ready");
});

test("keeps document-intelligence upload rejections on Documents with retry-safe state", async () => {
  let createCalls = 0;
  let uploadCalls = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      createCase: async () => {
        createCalls += 1;
        return created;
      },
      uploadDocuments: async () => {
        uploadCalls += 1;
        if (uploadCalls === 1) {
          throw new FounderApiClientError(
            "startup_document_intelligence_input_invalid",
            409,
            "startup_document_intelligence_input_invalid",
          );
        }
        return uploaded;
      },
    }),
    onChange: () => undefined,
  });
  const files = [new File(["smart-university"], "Smart University.pdf")];

  await orchestrator.start(files);
  const failed = orchestrator.getSnapshot();

  assert.equal(createCalls, 1);
  assert.equal(uploadCalls, 1);
  assert.equal(failed.caseId, caseId);
  assert.equal(failed.uploadAccepted, false);
  assert.deepEqual(failed.acceptedDocumentIds, []);
  assert.equal(failed.profile, null);
  assert.equal(failed.gate2Preview, null);
  assert.equal(failed.display.stage, "error");
  assert.equal(founderShellStage(failed.display.stage, true), "files_selected");
  assert.equal(failed.nextAction.kind, "fix_upload");
  assert.equal(
    founderErrorMessage(failed.error),
    "Не удалось безопасно прочитать документ для профиля. Выбранный файл остаётся в загрузке — повторите или приложите исправленную версию.",
  );

  await orchestrator.start(files);

  assert.equal(createCalls, 1);
  assert.equal(uploadCalls, 2);
  assert.equal(orchestrator.getSnapshot().uploadAccepted, true);
  assert.equal(orchestrator.getSnapshot().display.stage, "gate2_preview_ready");
});

test("uses the Gate 2 token, continues Gate 3 with explicit empty exclusions, and binds Gate 4 to the report tuple", async () => {
  const calls: Array<{ operation: string; value: unknown }> = [];
  let currentStatus = gate2Status;
  let currentReport = report;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => currentStatus,
      decideGate2: async (_id, request) => {
        calls.push({ operation: "gate2", value: request });
        currentStatus = gate3Status;
        return decision(gate3Status);
      },
      decideGate3: async (_id, request) => {
        calls.push({ operation: "gate3", value: request });
        currentStatus = reportStatus;
        return decision(reportStatus);
      },
      decideGate4: async (_id, request) => {
        calls.push({ operation: "gate4", value: request });
        currentReport = {
          ...report,
          freeze_status: request.decision === "approved" ? "approved" : "required",
          pdf_status: request.decision === "approved" ? "ready" : "freeze_required",
        };
        return decision({ ...reportStatus, gate4_status: "completed" });
      },
      getReport: async () => currentReport,
    }),
    onChange: () => undefined,
  });
  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  await orchestrator.decideGate2("approved");
  await orchestrator.decideGate3([]);
  await orchestrator.decideGate4("approved");

  assert.deepEqual(calls, [
    {
      operation: "gate2",
      value: { decision: "approved", resume_token: "resume-token-001" },
    },
    { operation: "gate3", value: { decision: "continue", exclusions: [] } },
    {
      operation: "gate4",
      value: {
        decision: "approved",
        snapshot_hash: "sha256:canonical-report",
        snapshot_revision: 4,
      },
    },
  ]);
  assert.deepEqual(orchestrator.getSnapshot().artifactUrls, {
    json: `/api/startup/cases/${caseId}/report/json`,
    html: `/api/startup/cases/${caseId}/report/html`,
    pdf: `/api/startup/cases/${caseId}/report/pdf`,
  });
  assert.equal(orchestrator.getSnapshot().display.stage, "report_pdf_ready");
});

test("surfaces provider unavailability without switching to the offline fixture", async () => {
  const unavailableStatus: StartupCaseStatus = {
    ...gate2Status,
    provider_status: "unavailable",
  };
  const modes: string[] = [];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      createCase: async (request) => {
        modes.push(request.fixture_mode);
        return { ...created, provider_status: "unavailable" };
      },
      getCase: async () => unavailableStatus,
      getGate2Preview: async () => ({
        ...gate2Preview,
        provider_mode: "unavailable",
      }),
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.deepEqual(modes, ["live"]);
  assert.equal(orchestrator.getSnapshot().display.providerSignal, "provider_unavailable");
});

test("keeps a denied Gate 2 decision visible instead of reopening the consumed preview", async () => {
  let statusReads = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => {
        statusReads += 1;
        return gate2Status;
      },
      decideGate2: async () =>
        decision({ ...gate2Status, gate2_status: "completed" }),
    }),
    onChange: () => undefined,
  });
  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  await orchestrator.decideGate2("denied");

  assert.equal(statusReads, 1);
  assert.equal(orchestrator.getSnapshot().display.stage, "gate2_denied");
  assert.equal(orchestrator.getSnapshot().gate2Preview, null);
});

test("fails closed when Gate 3 is requested before the canonical review stage", async () => {
  let gate3Calls = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate2Status,
      decideGate3: async () => {
        gate3Calls += 1;
        return decision(reportStatus);
      },
    }),
    onChange: () => undefined,
  });
  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  await orchestrator.decideGate3([]);

  assert.equal(gate3Calls, 0);
  assert.match(
    founderErrorMessage(orchestrator.getSnapshot().error),
    /сначала дождитесь.*глубинн.*анализ.*раздел.*план действий/iu,
  );
});

test("uses capped exponential polling and aborts the pending request on dispose", async () => {
  const delays: number[] = [];
  let scheduled: (() => void) | null = null;
  let observedSignal: AbortSignal | undefined;
  const runningStatus: StartupCaseStatus = {
    ...gate2Status,
    analysis_status: "awaiting_start",
    gate2_status: "completed",
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async (_id, options) => {
        observedSignal = options?.signal;
        return runningStatus;
      },
    }),
    onChange: () => undefined,
    schedule: (callback, delayMs) => {
      delays.push(delayMs);
      scheduled = callback;
      return () => {
        scheduled = null;
      };
    },
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  assert.equal(delays[0], 750);
  const firstPoll = scheduled as (() => void) | null;
  assert.ok(firstPoll);
  firstPoll();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(delays[1], 1500);

  orchestrator.dispose();

  assert.equal(observedSignal?.aborted, true);
  assert.equal(scheduled, null);
});

test("keeps polling while the canonical report endpoint is not ready yet", async () => {
  const delays: number[] = [];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => ({
        ...reportStatus,
        report_status: "not_ready",
        snapshot_hash: null,
        snapshot_revision: null,
      }),
      getReport: async () => {
        throw new FounderApiClientError(
          "report_not_ready",
          404,
          "Canonical report is still building",
        );
      },
    }),
    onChange: () => undefined,
    schedule: (_callback, delayMs) => {
      delays.push(delayMs);
      return () => undefined;
    },
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.equal(orchestrator.getSnapshot().display.stage, "gate4_pending");
  assert.equal(orchestrator.getSnapshot().error, null);
  assert.deepEqual(delays, [750]);
});

test("loads advisor question and six improvement proposals after the report tuple without blocking the report", async () => {
  const calls: string[] = [];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => reportStatus,
      getAdvisorNextQuestion: async (id) => {
        calls.push(`question:${id}`);
        return advisorQuestion;
      },
      getAdvisorImprovements: async (id) => {
        calls.push(`improvements:${id}`);
        return advisorImprovements;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.deepEqual(calls, [`question:${caseId}`, `improvements:${caseId}`]);
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorQuestion?.next_question
      ?.field_key,
    "icp",
  );
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorImprovements?.proposals
      .length,
    6,
  );
  assert.equal(orchestrator.getSnapshot().report?.case_id, caseId);
});

test("loads advisor question but not report-based improvements when Gate 3 review is ready", async () => {
  const calls: string[] = [];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getAdvisorNextQuestion: async (id) => {
        calls.push(`question:${id}`);
        return advisorQuestion;
      },
      getAdvisorImprovements: async (id) => {
        calls.push(`improvements:${id}`);
        return advisorImprovements;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.equal(orchestrator.getSnapshot().display.stage, "gate3_review_required");
  assert.equal(orchestrator.getSnapshot().report, null);
  assert.deepEqual(calls, [`question:${caseId}`]);
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorQuestion?.next_question
      ?.field_key,
    "icp",
  );
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorImprovements,
    null,
  );
});

test("rejects cross-case advisor question and improvement payloads before storing them", async () => {
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => reportStatus,
      getAdvisorNextQuestion: async () => ({
        ...advisorQuestion,
        case_id: "case-other",
      }),
      getAdvisorImprovements: async () => ({
        ...advisorImprovements,
        case_id: "case-other",
      }),
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  const advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorQuestion, null);
  assert.equal(advisor.advisorImprovements, null);
  assert.equal(advisor.advisorAnswer, null);
  assert.equal(advisor.advisorDecision, null);
  assert.equal(advisor.advisorError instanceof Error, true);
});

test("loads six advisor improvement proposals after an advisor answer before the report tuple", async () => {
  const calls: string[] = [];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getAdvisorNextQuestion: async (id) => {
        calls.push(`question:${id}`);
        return advisorQuestion;
      },
      submitAdvisorAnswer: async (id, request) => {
        calls.push(`answer:${id}:${request.answer_type}`);
        return advisorAnswer;
      },
      getAdvisorImprovements: async (id) => {
        calls.push(`improvements:${id}`);
        return advisorImprovements;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  assert.deepEqual(calls, [`question:${caseId}`]);
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorImprovements,
    null,
  );

  await orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Платные пилоты ещё не подтверждены.",
    document_id: null,
    consent_public_research: false,
  });

  assert.deepEqual(calls, [
    `question:${caseId}`,
    `answer:${caseId}:manual`,
    `question:${caseId}`,
    `improvements:${caseId}`,
  ]);
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorImprovements?.proposals
      .length,
    6,
  );
});

test("rejects stale advisor answer payloads that do not match active question and field", async () => {
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getAdvisorNextQuestion: async () => advisorQuestion,
      submitAdvisorAnswer: async () => ({
        ...advisorAnswer,
        question_id: `${caseId}:pricing_revenue_model`,
        field_key: "pricing_revenue_model",
      }),
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Операционные директора в компаниях 100–300 сотрудников.",
    document_id: null,
    consent_public_research: false,
  });

  const advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorAnswer, null);
  assert.equal(advisor.advisorImprovements, null);
  assert.equal(advisor.advisorError instanceof Error, true);
});

test("rejects advisor answers when no active next question is present", async () => {
  const completedQuestion: AdvisorNextQuestionResponse = {
    ...advisorQuestion,
    status: "complete",
    next_question: null,
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getAdvisorNextQuestion: async () => completedQuestion,
      submitAdvisorAnswer: async () => advisorAnswer,
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Операционные директора в компаниях 100–300 сотрудников.",
    document_id: null,
    consent_public_research: false,
  });

  const advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorQuestion?.status, "complete");
  assert.equal(advisor.advisorQuestion?.next_question, null);
  assert.equal(advisor.advisorAnswer, null);
  assert.equal(advisor.advisorImprovements, null);
  assert.equal(advisor.advisorError instanceof Error, true);
});

test("keeps core case and report usable when advisor endpoints fail and supports safe retry", async () => {
  let questionReads = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => reportStatus,
      getAdvisorNextQuestion: async () => {
        questionReads += 1;
        if (questionReads === 1) {
          throw new FounderApiClientError(
            "api_timeout",
            0,
            "Advisor request timed out",
          );
        }
        return advisorQuestion;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  assert.equal(orchestrator.getSnapshot().error, null);
  assert.equal(orchestrator.getSnapshot().report?.case_id, caseId);
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorError instanceof Error,
    true,
  );

  await orchestrator.retryAdvisor();

  assert.equal(snapshotAdvisor(orchestrator.getSnapshot()).advisorError, null);
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorQuestion?.status,
    "active",
  );
});

test("rejects stale improvement payloads and decisions that do not match active lineage", async () => {
  let staleImprovements = false;
  const firstProposalId = advisorImprovements.proposals[0]?.proposal_id ?? "";
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => reportStatus,
      getAdvisorNextQuestion: async () => advisorQuestion,
      getAdvisorImprovements: async () =>
        staleImprovements
          ? {
              ...advisorImprovements,
              improvement_version: 5,
              proposals: advisorImprovements.proposals.map((proposal) => ({
                ...proposal,
                proposal_id: crypto.randomUUID(),
              })),
            }
          : advisorImprovements,
      decideAdvisorImprovement: async () => ({
        case_id: caseId,
        proposal_id: crypto.randomUUID(),
        decision: "accepted",
        previous_version: 4,
        new_version: 5,
        changed_fields: ["positioning"],
        recalculation_status: "started",
        recalculation_data_revision: 2,
        recalculation_analysis_status: "gate2_preview_ready",
      }),
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  let advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorImprovements?.improvement_version, 6);

  staleImprovements = true;
  await orchestrator.retryAdvisor();
  advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorImprovements?.improvement_version, 6);
  assert.equal(advisor.advisorError instanceof Error, true);

  staleImprovements = false;
  await orchestrator.retryAdvisor();
  advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorError, null);

  await orchestrator.decideAdvisorImprovement(firstProposalId, "accepted");
  advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorDecision, null);
  assert.equal(advisor.advisorError instanceof Error, true);
});

test("rejects advisor improvement decisions when no current proposals are loaded", async () => {
  const firstProposalId = advisorImprovements.proposals[0]?.proposal_id ?? "";
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getAdvisorNextQuestion: async () => advisorQuestion,
      decideAdvisorImprovement: async (_id, proposalId, decisionValue) => ({
        case_id: caseId,
        proposal_id: proposalId,
        decision: decisionValue,
        previous_version: 6,
        new_version: 7,
        changed_fields: ["positioning"],
        recalculation_status: "started",
        recalculation_data_revision: 2,
        recalculation_analysis_status: "gate2_preview_ready",
      }),
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.decideAdvisorImprovement(firstProposalId, "accepted");

  const advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorImprovements, null);
  assert.equal(advisor.advisorDecision, null);
  assert.equal(advisor.advisorError instanceof Error, true);
});

test("submits advisor answers with explicit public research consent and updates proposal version decisions", async () => {
  const calls: Array<Readonly<{ operation: string; value: unknown }>> = [];
  let caseRefreshCount = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => {
        caseRefreshCount += 1;
        return reportStatus;
      },
      submitAdvisorAnswer: async (_id, request) => {
        calls.push({ operation: "answer", value: request });
        return {
          ...advisorAnswer,
          answer_type: request.answer_type,
          research_result:
            request.answer_type === "public_research"
              ? {
                  status: "partial",
                  summary_ru: "Публичный поиск выполнен с fallback.",
                  source_ids: [],
                  fallback_used: true,
                  fail_reason_ru: null,
                }
              : null,
        };
      },
      decideAdvisorImprovement: async (_id, proposalId, decisionValue) => {
        calls.push({
          operation: "decision",
          value: { proposalId, decisionValue },
        });
        return {
          case_id: caseId,
          proposal_id: proposalId,
          decision: decisionValue,
          previous_version: 6,
          new_version: decisionValue === "accepted" ? 7 : 6,
          changed_fields: decisionValue === "accepted" ? ["positioning"] : [],
          recalculation_status:
            decisionValue === "accepted" ? "started" : "not_requested",
          recalculation_data_revision: decisionValue === "accepted" ? 2 : null,
          recalculation_analysis_status:
            decisionValue === "accepted" ? "gate2_preview_ready" : null,
        };
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  assert.deepEqual(orchestrator.getSnapshot().acceptedDocumentIds, ["doc-0001"]);
  const refreshCountBeforeAnswer = caseRefreshCount;
  await orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "public_research",
    value: null,
    document_id: null,
    consent_public_research: true,
  });
  const refreshCountBeforeDecision = caseRefreshCount;
  await orchestrator.decideAdvisorImprovement(
    advisorImprovements.proposals[0]?.proposal_id ?? "",
    "accepted",
  );

  assert.deepEqual(calls[0], {
    operation: "answer",
    value: {
      question_id: `${caseId}:icp`,
      answer_type: "public_research",
      value: null,
      document_id: null,
      consent_public_research: true,
    },
  });
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorAnswer?.answer_type,
    "public_research",
  );
  assert.ok(caseRefreshCount > refreshCountBeforeAnswer);
  assert.ok(caseRefreshCount > refreshCountBeforeDecision);
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorDecision?.new_version,
    7,
  );
});

test("preserves accepted improvement lineage while the same case recalculates", async () => {
  let recalculationStarted = false;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () =>
        recalculationStarted
          ? {
              ...gate2Status,
              gate2_status: "required",
              analysis_status: "gate2_preview_ready",
              report_status: "not_ready",
              snapshot_hash: null,
              snapshot_revision: null,
            }
          : reportStatus,
      decideAdvisorImprovement: async (_id, proposalId, decisionValue) => {
        recalculationStarted = decisionValue === "accepted";
        return {
          case_id: caseId,
          proposal_id: proposalId,
          decision: decisionValue,
          previous_version: 6,
          new_version: decisionValue === "accepted" ? 7 : 6,
          changed_fields: decisionValue === "accepted" ? ["positioning"] : [],
          recalculation_status:
            decisionValue === "accepted" ? "started" : "not_requested",
          recalculation_data_revision: decisionValue === "accepted" ? 2 : null,
          recalculation_analysis_status:
            decisionValue === "accepted" ? "gate2_preview_ready" : null,
        };
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.decideAdvisorImprovement(
    advisorImprovements.proposals[0]?.proposal_id ?? "",
    "accepted",
  );
  await orchestrator.refresh();

  const advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorDecision?.decision, "accepted");
  assert.equal(advisor.advisorDecision?.new_version, 7);
  assert.equal(advisor.advisorImprovements, null);
});

test("clears stale advisor proposals when an answer reopens Gate 2 before recalculation is ready", async () => {
  let answerSubmitted = false;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () =>
        answerSubmitted
          ? {
              ...gate2Status,
              gate2_status: "required",
              analysis_status: "gate2_preview_ready",
              report_status: "not_ready",
              snapshot_hash: null,
              snapshot_revision: null,
            }
          : reportStatus,
      submitAdvisorAnswer: async () => {
        answerSubmitted = true;
        return advisorAnswer;
      },
      getAdvisorImprovements: async () => {
        if (answerSubmitted) {
          throw new FounderApiClientError(
            "advisor_improvements_not_ready",
            409,
            "Advisor proposals are recalculating",
          );
        }
        return advisorImprovements;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  assert.equal(
    snapshotAdvisor(orchestrator.getSnapshot()).advisorImprovements?.proposals
      .length,
    6,
  );

  await orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Операционные директора в компаниях 100–300 сотрудников.",
    document_id: null,
    consent_public_research: false,
  });

  const advisor = snapshotAdvisor(orchestrator.getSnapshot());
  assert.equal(advisor.advisorAnswer?.status, "applied");
  assert.equal(advisor.advisorError, null);
  assert.equal(advisor.advisorImprovements, null);
});

test("ignores a stale aborted refresh after an advisor answer reopens Gate 2", async () => {
  let caseReads = 0;
  let answerSubmitted = false;
  let staleRefreshSignal: AbortSignal | undefined;
  let rejectStaleRefresh!: (reason?: unknown) => void;
  const staleCaseRead = new Promise<StartupCaseStatus>((_resolve, reject) => {
    rejectStaleRefresh = reject;
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async (_id, options) => {
        caseReads += 1;
        if (caseReads === 1) return reportStatus;
        if (caseReads === 2) {
          staleRefreshSignal = options?.signal;
          return staleCaseRead;
        }
        return gate2Status;
      },
      submitAdvisorAnswer: async () => {
        answerSubmitted = true;
        return advisorAnswer;
      },
      getAdvisorImprovements: async () => {
        if (answerSubmitted) {
          throw new FounderApiClientError(
            "advisor_improvements_not_ready",
            409,
            "Advisor proposals are recalculating",
          );
        }
        return advisorImprovements;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const staleRefresh = orchestrator.refresh();
  await Promise.resolve();

  await orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Операционные директора в компаниях 100–300 сотрудников.",
    document_id: null,
    consent_public_research: false,
  });

  assert.equal(staleRefreshSignal?.aborted, true);
  assert.equal(orchestrator.getSnapshot().display.stage, "gate2_preview_ready");
  assert.equal(orchestrator.getSnapshot().gate2Preview?.resume_token, "resume-token-001");
  assert.ok(snapshotProfile(orchestrator.getSnapshot()));

  rejectStaleRefresh(Object.assign(new Error("The operation was aborted"), {
    name: "AbortError",
  }));
  await staleRefresh;

  const snapshot = orchestrator.getSnapshot();
  assert.equal(snapshot.error, null);
  assert.equal(snapshotAdvisor(snapshot).advisorError, null);
  assert.equal(snapshot.display.stage, "gate2_preview_ready");
  assert.equal(snapshot.gate2Preview?.resume_token, "resume-token-001");
  assert.ok(snapshotProfile(snapshot));
  assert.equal(snapshot.busy, false);
});

test("ignores stale refresh data when an aborted API call still resolves", async () => {
  let caseReads = 0;
  let answerSubmitted = false;
  let staleRefreshSignal: AbortSignal | undefined;
  let resolveStaleRefresh!: (status: StartupCaseStatus) => void;
  const staleCaseRead = new Promise<StartupCaseStatus>((resolve) => {
    resolveStaleRefresh = resolve;
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async (_id, options) => {
        caseReads += 1;
        if (caseReads === 1) return reportStatus;
        if (caseReads === 2) {
          staleRefreshSignal = options?.signal;
          return staleCaseRead;
        }
        return gate2Status;
      },
      submitAdvisorAnswer: async () => {
        answerSubmitted = true;
        return advisorAnswer;
      },
      getAdvisorImprovements: async () => {
        if (answerSubmitted) {
          throw new FounderApiClientError(
            "advisor_improvements_not_ready",
            409,
            "Advisor proposals are recalculating",
          );
        }
        return advisorImprovements;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const staleRefresh = orchestrator.refresh();
  await Promise.resolve();

  await orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Операционные директора в компаниях 100–300 сотрудников.",
    document_id: null,
    consent_public_research: false,
  });

  assert.equal(staleRefreshSignal?.aborted, true);
  resolveStaleRefresh(reportStatus);
  await staleRefresh;

  const snapshot = orchestrator.getSnapshot();
  assert.equal(snapshot.error, null);
  assert.equal(snapshot.display.stage, "gate2_preview_ready");
  assert.equal(snapshot.gate2Preview?.resume_token, "resume-token-001");
  assert.ok(snapshotProfile(snapshot));
});

test("submits Gate 2 approval while advisor proposals are still loading", async () => {
  let answerSubmitted = false;
  let gate2Approved = false;
  let releaseImprovementLoad!: () => void;
  let improvementsLoadStarted!: () => void;
  const improvementsLoadEntered = new Promise<void>((resolve) => {
    improvementsLoadStarted = resolve;
  });
  const pendingImprovementLoad = new Promise<AdvisorImprovementsResponse>(
    (resolve) => {
      releaseImprovementLoad = () => resolve(advisorImprovements);
    },
  );
  const gate2Decisions: StartupGate2Decision[] = [];
  const reopenedGate2Status: StartupCaseStatus = {
    ...gate2Status,
    gate2_status: "required",
    analysis_status: "gate2_preview_ready",
    report_status: "not_ready",
    snapshot_hash: null,
    snapshot_revision: null,
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () =>
        gate2Approved
          ? gate3Status
          : answerSubmitted
            ? reopenedGate2Status
            : reportStatus,
      submitAdvisorAnswer: async () => {
        answerSubmitted = true;
        return advisorAnswer;
      },
      getAdvisorImprovements: async () => {
        if (!answerSubmitted) return advisorImprovements;
        improvementsLoadStarted();
        return pendingImprovementLoad;
      },
      decideGate2: async (_id, request) => {
        gate2Decisions.push(request);
        gate2Approved = true;
        return decision(gate3Status);
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const answerPromise = orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Операционные директора в компаниях 100–300 сотрудников.",
    document_id: null,
    consent_public_research: false,
  });

  await improvementsLoadEntered;
  assert.equal(orchestrator.getSnapshot().display.stage, "gate2_preview_ready");
  assert.equal(orchestrator.getSnapshot().gate2Preview?.resume_token, "resume-token-001");

  try {
    await orchestrator.decideGate2("approved");

    assert.equal(gate2Decisions.length, 1);
    assert.deepEqual(gate2Decisions[0], {
      decision: "approved",
      resume_token: "resume-token-001",
    });
    assert.equal(orchestrator.getSnapshot().display.stage, "gate3_review_required");
  } finally {
    releaseImprovementLoad();
    await answerPromise;
  }
});

test("does not expose Gate 4 when report metadata says ready but the canonical tuple is unavailable", async () => {
  const delays: number[] = [];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => reportStatus,
      getReport: async () => {
        throw new FounderApiClientError(
          "report_not_ready",
          404,
          "Canonical tuple is not readable yet",
        );
      },
    }),
    onChange: () => undefined,
    schedule: (_callback, delayMs) => {
      delays.push(delayMs);
      return () => undefined;
    },
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.equal(orchestrator.getSnapshot().display.stage, "gate4_pending");
  assert.equal(orchestrator.getSnapshot().report, null);
  assert.deepEqual(delays, [750]);
});

test("fetches the canonical report snapshot only after report metadata is ready", async () => {
  const calls: string[] = [];
  const statuses: StartupCaseStatus[] = [
    gate2Status,
    {
      ...reportStatus,
      snapshot_hash: canonicalReportSnapshotHash,
      snapshot_revision: canonicalReportSnapshot.data_revision,
    },
  ];
  const workspaceApi: FounderWorkspaceReportSnapshotApi = {
    ...api({
      getCase: async () => statuses.shift() ?? statuses.at(-1) ?? reportStatus,
      getReport: async () => ({
        ...report,
        snapshot_id: canonicalReportSnapshotId,
        snapshot_hash: canonicalReportSnapshotHash,
        snapshot_revision: canonicalReportSnapshot.data_revision,
      }),
    }),
    getStartupReportSnapshot: async (id) => {
      calls.push(id);
      return canonicalReportSnapshot;
    },
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: workspaceApi,
    onChange: () => undefined,
    schedule: () => () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  assert.deepEqual(calls, []);
  assert.equal(snapshotReport(orchestrator.getSnapshot()), null);

  await orchestrator.refresh();

  assert.deepEqual(calls, [caseId]);
  assert.deepEqual(snapshotReport(orchestrator.getSnapshot()), canonicalReportSnapshot);
});

test("continues polling when the approved Gate 4 report snapshot is briefly stale after PDF generation", async () => {
  let approved = false;
  let approvedSnapshotReads = 0;
  let scheduled: (() => void) | null = null;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: {
      ...api({
        getCase: async () => ({
          ...reportStatus,
          gate4_status: approved ? "completed" : "not_ready",
        }),
        getReport: async () => ({
          ...report,
          freeze_status: approved ? "approved" : "required",
          pdf_status: approved ? "ready" : "freeze_required",
        }),
        decideGate4: async () => {
          approved = true;
          return decision({ ...reportStatus, gate4_status: "completed" });
        },
        downloadReportArtifact: async () => new Response("%PDF-1.4"),
      }),
      getStartupReportSnapshot: async () => {
        if (approved) {
          approvedSnapshotReads += 1;
          if (approvedSnapshotReads === 1) {
            return {
              ...canonicalReportSnapshot,
              data_revision: canonicalReportSnapshot.data_revision + 1,
            };
          }
        }
        return canonicalReportSnapshot;
      },
    } satisfies FounderWorkspaceReportSnapshotApi,
    onChange: () => undefined,
    schedule: (callback) => {
      scheduled = callback;
      return () => {
        scheduled = null;
      };
    },
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.decideGate4("approved");

  assert.ifError(orchestrator.getSnapshot().error);
  const reportRefresh = scheduled as (() => void) | null;
  assert.ok(reportRefresh);
  reportRefresh();
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(orchestrator.getSnapshot().display.stage, "report_pdf_ready");
  assert.equal(orchestrator.getSnapshot().report?.freeze_status, "approved");
  assert.equal(orchestrator.getSnapshot().report?.pdf_status, "ready");
  assert.deepEqual(orchestrator.getSnapshot().artifactUrls, {
    json: `/api/startup/cases/${caseId}/report/json`,
    html: `/api/startup/cases/${caseId}/report/html`,
    pdf: `/api/startup/cases/${caseId}/report/pdf`,
  });
});

test("continues polling when Gate 4 completed before the report freeze metadata converges", async () => {
  let approved = false;
  let reportReads = 0;
  let scheduled: (() => void) | null = null;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: {
      ...api({
        getCase: async () => ({
          ...reportStatus,
          gate4_status: approved ? "completed" : "not_ready",
        }),
        getReport: async () => {
          reportReads += 1;
          const freezeMetadataConverged = approved && reportReads > 2;
          return {
            ...report,
            freeze_status: freezeMetadataConverged ? "approved" : "required",
            pdf_status: freezeMetadataConverged ? "ready" : "freeze_required",
          };
        },
        decideGate4: async () => {
          approved = true;
          return decision({ ...reportStatus, gate4_status: "completed" });
        },
        downloadReportArtifact: async () => new Response("%PDF-1.4"),
      }),
      getStartupReportSnapshot: async () => canonicalReportSnapshot,
    } satisfies FounderWorkspaceReportSnapshotApi,
    onChange: () => undefined,
    schedule: (callback) => {
      scheduled = callback;
      return () => {
        scheduled = null;
      };
    },
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.decideGate4("approved");

  assert.ifError(orchestrator.getSnapshot().error);
  assert.equal(orchestrator.getSnapshot().report?.freeze_status, "required");
  assert.equal(orchestrator.getSnapshot().display.stage, "gate4_approved");
  const reportRefresh = scheduled as (() => void) | null;
  assert.ok(reportRefresh);
  reportRefresh();
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(orchestrator.getSnapshot().display.stage, "report_pdf_ready");
  assert.equal(orchestrator.getSnapshot().report?.freeze_status, "approved");
  assert.equal(orchestrator.getSnapshot().report?.pdf_status, "ready");
  assert.deepEqual(orchestrator.getSnapshot().artifactUrls, {
    json: `/api/startup/cases/${caseId}/report/json`,
    html: `/api/startup/cases/${caseId}/report/html`,
    pdf: `/api/startup/cases/${caseId}/report/pdf`,
  });
});

test("refreshes approved Gate 4 state without waiting for an eager PDF download", async () => {
  let approved = false;
  let pdfDownloads = 0;
  let releasePdfDownload: ((response: Response) => void) | null = null;
  const pendingPdfDownload = new Promise<Response>((resolve) => {
    releasePdfDownload = resolve;
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: {
      ...api({
        getCase: async () => ({
          ...reportStatus,
          gate4_status: approved ? "completed" : "not_ready",
        }),
        getReport: async () => ({
          ...report,
          freeze_status: approved ? "approved" : "required",
          pdf_status: approved ? "ready" : "freeze_required",
        }),
        decideGate4: async () => {
          approved = true;
          return decision({ ...reportStatus, gate4_status: "completed" });
        },
        downloadReportArtifact: async () => {
          pdfDownloads += 1;
          return await pendingPdfDownload;
        },
      }),
      getStartupReportSnapshot: async () => canonicalReportSnapshot,
    } satisfies FounderWorkspaceReportSnapshotApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  const approval = orchestrator.decideGate4("approved");
  try {
    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.equal(pdfDownloads, 0);
    assert.equal(orchestrator.getSnapshot().display.stage, "report_pdf_ready");
    assert.deepEqual(orchestrator.getSnapshot().artifactUrls, {
      json: `/api/startup/cases/${caseId}/report/json`,
      html: `/api/startup/cases/${caseId}/report/html`,
      pdf: `/api/startup/cases/${caseId}/report/pdf`,
    });
  } finally {
    const release = releasePdfDownload as ((response: Response) => void) | null;
    release?.(new Response("%PDF-1.4"));
    await approval;
  }
});

test("fails closed when an approved report belongs to another case", async () => {
  let scheduledPolls = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: {
      ...api({
        getCase: async () => reportStatus,
        getReport: async () => ({
          ...report,
          case_id: "case-founder-other",
          freeze_status: "approved",
          pdf_status: "ready",
        }),
      }),
      getStartupReportSnapshot: async () => canonicalReportSnapshot,
    } satisfies FounderWorkspaceReportSnapshotApi,
    onChange: () => undefined,
    schedule: () => {
      scheduledPolls += 1;
      return () => undefined;
    },
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.equal(orchestrator.getSnapshot().report, null);
  assert.equal(orchestrator.getSnapshot().display.stage, "error");
  assert.equal(
    (orchestrator.getSnapshot().error as FounderApiClientError | null)?.code,
    "startup_report_snapshot_stale",
  );
  assert.equal(scheduledPolls, 0);
});

test("fails closed and clears the report snapshot when the canonical snapshot tuple mismatches report metadata", async () => {
  let gate4Calls = 0;
  let pdfDownloads = 0;
  const staleSnapshot: StartupReportSnapshotResponse = {
    ...canonicalReportSnapshot,
    data_revision: canonicalReportSnapshot.data_revision + 1,
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: {
      ...api({
        getCase: async () => ({
          ...reportStatus,
          snapshot_hash: canonicalReportSnapshotHash,
          snapshot_revision: canonicalReportSnapshot.data_revision,
        }),
        getReport: async () => ({
          ...report,
          snapshot_id: canonicalReportSnapshotId,
          snapshot_hash: canonicalReportSnapshotHash,
          snapshot_revision: canonicalReportSnapshot.data_revision,
        }),
        decideGate4: async () => {
          gate4Calls += 1;
          return decision(reportStatus);
        },
        downloadReportArtifact: async () => {
          pdfDownloads += 1;
          return new Response("%PDF-1.4");
        },
      }),
      getStartupReportSnapshot: async () => staleSnapshot,
    } satisfies FounderWorkspaceReportSnapshotApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  assert.equal(snapshotReport(orchestrator.getSnapshot()), null);
  assert.equal(orchestrator.getSnapshot().report, null);
  assert.equal(orchestrator.getSnapshot().display.stage, "error");
  assert.equal(
    (orchestrator.getSnapshot().error as FounderApiClientError | null)?.code,
    "startup_report_snapshot_stale",
  );

  await orchestrator.decideGate4("approved");

  assert.equal(gate4Calls, 0);
  assert.equal(pdfDownloads, 0);
});

test("clears cached report snapshot on fresh cases and before stale report snapshot failures", async () => {
  const secondCaseId = "case-founder-002";
  let reportSnapshotReads = 0;
  const statuses: StartupCaseStatus[] = [
    {
      ...reportStatus,
      snapshot_hash: canonicalReportSnapshotHash,
      snapshot_revision: canonicalReportSnapshot.data_revision,
    },
    {
      ...gate2Status,
      case_id: secondCaseId,
      analysis_status: "awaiting_upload",
      gate2_status: "not_ready",
    },
    {
      ...reportStatus,
      case_id: secondCaseId,
      snapshot_hash: canonicalReportSnapshotHash,
      snapshot_revision: canonicalReportSnapshot.data_revision,
    },
  ];
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: {
      ...api({
        getCase: async () => statuses.shift() ?? gate2Status,
        getReport: async () => ({
          ...report,
          snapshot_id: canonicalReportSnapshotId,
          snapshot_hash: canonicalReportSnapshotHash,
          snapshot_revision: canonicalReportSnapshot.data_revision,
        }),
      }),
      getStartupReportSnapshot: async () => {
        reportSnapshotReads += 1;
        if (reportSnapshotReads === 1) return canonicalReportSnapshot;
        throw new FounderApiClientError(
          "startup_report_snapshot_stale",
          409,
          "Report snapshot no longer matches the case revision",
        );
      },
    } satisfies FounderWorkspaceReportSnapshotApi,
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["first"], "first.pdf")]);
  assert.deepEqual(snapshotReport(orchestrator.getSnapshot()), canonicalReportSnapshot);

  await orchestrator.start([new File(["second"], "second.pdf")]);
  assert.equal(snapshotReport(orchestrator.getSnapshot()), null);

  await orchestrator.refresh();

  assert.equal(snapshotReport(orchestrator.getSnapshot()), null);
  assert.equal(
    (orchestrator.getSnapshot().error as FounderApiClientError | null)?.code,
    "startup_report_snapshot_stale",
  );
});

test("maps workflow gates and API failures to founder-facing UI language", () => {
  assert.equal(founderShellStage("idle", false), "idle");
  assert.equal(founderShellStage("idle", true), "files_selected");
  assert.equal(founderShellStage("gate2_preview_ready", true), "primary_ready");
  assert.equal(founderShellStage("gate3_review_required", true), "deep_ready");
  assert.equal(founderShellStage("report_draft_ready", true), "deep_ready");
  assert.equal(founderShellStage("error", true), "files_selected");
  assert.equal(founderShellStage("error", false), "error");
  assert.equal(
    founderErrorMessage(
      new FounderApiClientError(
        "api_unreachable",
        0,
        "Founder API could not be reached",
      ),
    ),
    "Сервис анализа недоступен. Проверьте, что API запущен, и повторите запрос.",
  );
});

test("keeps founder-facing controller copy free from UTF-8 mojibake", () => {
  const mojibake = /[РС][°±²³´µ¶·ё№є»јЅѕї‚ѓ„…†‡€‰Љ‹ЊЌЋЏђ‘’“”•–—™љ›њќћўџ]/u;
  for (const source of [
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    new URL("./founder-workspace-orchestrator.ts", import.meta.url),
  ]) {
    const text = readFileSync(source, "utf8");
    assert.equal(mojibake.test(text), false, `${source.pathname} contains mojibake`);
  }
});

test("wires the canonical GTM snapshot into the deep-analysis UI", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const analysisPages = readFileSync(
    new URL("./founder-analysis-pages.tsx", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );

  assert.match(shell, /<FounderAnalysisPages[\s\S]*page="metrics"[\s\S]*workspace=\{workspace\}/u);
  assert.match(analysisPages, /buildFounderReportPresentation/u);
  assert.match(analysisPages, /key:\s*"go_to_market"/u);
  assert.match(shell, /<FounderStrategyPages[\s\S]*page="market"[\s\S]*workspace=\{workspace\}/u);
  assert.match(controller, /gtm:\s*snapshot\?\.gtm \?\? null/u);
});

test("labels Copilot fact saving as founder input instead of confirmed evidence", () => {
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );

  assert.match(controller, /copilot_saving_fact:\s*"Сохраняю значение как ответ основателя…"/u);
  assert.doesNotMatch(controller, /copilot_saving_fact:\s*"Сохраняю подтвержд[её]нный факт…"/u);
});

test("wires strategy public research CTA to Case Copilot research with visible busy feedback", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );

  assert.match(shell, /buildCaseCopilotSubmitPayload/u);
  assert.match(shell, /async function requestSafeResearch\(\s*acquisitionMode\?: RequestedResearchAcquisitionMode,/u);
  assert.match(shell, /workspace\?\.copilotState\?\.actions \?\? \[\]/u);
  assert.match(shell, /answerType:\s*"public_research"/u);
  assert.match(shell, /consentPublicResearch:\s*true/u);
  assert.match(shell, /await onCopilotResearchPrepare\?\.\(payload\)/u);
  assert.match(shell, /setCaseCopilotOpen\(true\)/u);
  assert.doesNotMatch(shell, /function requestSafeResearch\(\) \{\s*setPrivacyMode\("research_prepared"\);\s*openView\("data_room", "Новый анализ"\);/u);

  assert.match(shell, /workspace\?\.busyLabel \?\? "Загружаю…"/u);
  assert.match(shell, /className="founder-global-busy"/u);
  assert.match(shell, /role="status"/u);
  assert.match(shell, /aria-live="polite"/u);
  assert.match(shell, /aria-busy=\{workspace\?\.busy \?\? false\}/u);
  assert.match(controller, /function founderBusyLabel/u);
  assert.match(controller, /submitting_gate2_approved:\s*"Анализирую подтверждённое направление…"/u);
  assert.match(controller, /submitting_gate4_approved:\s*"Сохраняю финальную версию…"/u);
  assert.match(controller, /busyLabel:\s*founderBusyLabel\(\s*snapshot\?\.activity \?\? null,\s*snapshot\?\.activeResearchAcquisitionMode \?\? null,\s*\)/u);
  assert.match(controller, /activity:\s*snapshot\?\.activity \?\? null/u);
});

test("disables upload and start-analysis actions while the workspace is busy", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const uploadEntry = readFileSync(
    new URL("./upload-entry.tsx", import.meta.url),
    "utf8",
  );

  assert.match(uploadEntry, /busy\?:\s*boolean/u);
  assert.match(uploadEntry, /busyLabel\?:\s*string/u);
  assert.match(uploadEntry, /const isBusy = Boolean\(busy\)/u);
  assert.match(uploadEntry, /disabled=\{isBusy\}/u);
  assert.match(uploadEntry, /aria-disabled=\{isBusy\}/u);
  assert.match(uploadEntry, /pointerEvents: isBusy \? "none" : undefined/u);
  assert.match(uploadEntry, /const busyCopy = busyLabel \?\? "Идёт обработка материалов…"/u);
  assert.match(uploadEntry, /const selectFilesCopy = isBusy \? busyCopy : "Выбрать файлы"/u);
  assert.match(uploadEntry, /isBusy \? busyCopy : "Запустить анализ выбранных материалов"/u);
  assert.match(uploadEntry, /isBusy \? "disabledButton" : "secondaryButton"/u);
  assert.match(shell, /busy=\{workspace\?\.busy\}/u);
  assert.match(shell, /busyLabel=\{workspace\?\.busyLabel\}/u);
  assert.match(shell, /disabled=\{workspace\?\.busy\}/u);
  assert.match(shell, /workspace\?\.busy \? workspace\.busyLabel \?\? "Идёт обработка…" : "Начать анализ"/u);
});

test("wires the canonical startup profile into a founder-safe overview panel without protected deleted dependency", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const analysisPages = readFileSync(
    new URL("./founder-analysis-pages.tsx", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const panel = readFileSync(
    new URL("./founder-startup-overview-panel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(shell, /<FounderAnalysisPages[\s\S]*page="overview"[\s\S]*workspace=\{workspace\}/u);
  assert.match(analysisPages, /workspace\?\.profile/u);
  assert.match(analysisPages, /fieldValue\(workspace, "startup_name"/u);
  assert.doesNotMatch(shell, /founder-profile-panel/u);
  assert.match(controller, /profile:\s*snapshot\?\.profile \?\? null/u);
  assert.match(panel, /id="startup-profile-title"/u);
  assert.match(panel, /safeFounderText/u);
  assert.match(panel, /Обзор стартапа/u);
  assert.doesNotMatch(
    panel,
    /evidenceIds|gapCodes|profile_hash|artifact_hash|source_hashes/u,
  );
  assert.doesNotMatch(panel, /\b(score|MISSING|sha256)\b/iu);
});

test("wires the approved desktop advisor journey and keeps admin proof separate", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const advisorPages = readFileSync(
    new URL("./founder-advisor-pages.tsx", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const packageJson = readFileSync(
    new URL("../package.json", import.meta.url),
    "utf8",
  );

  assert.match(shell, /FounderAdvisorPages/u);
  assert.match(advisorPages, /data-founder-advisor-page="advisor-next-question"/u);
  assert.match(advisorPages, /data-founder-advisor-page="advisor-answer"/u);
  assert.match(advisorPages, /data-founder-advisor-page="advisor-updated-analysis"/u);
  assert.match(advisorPages, /data-founder-advisor-page="advisor-improved-plan"/u);
  assert.match(advisorPages, /acceptedDocumentIds/u);
  assert.match(advisorPages, /selectedDocumentId = props\.workspace\?\.acceptedDocumentIds/u);
  assert.doesNotMatch(shell, /function AdvisorWorkspace|<AdvisorWorkspace/u);
  assert.doesNotMatch(shell, /ADVISOR_DESKTOP_SEQUENCE|data-advisor-screen/u);
  assert.doesNotMatch(
    shell,
    /AI Advisor|Desktop journey|Admin proof|Экраны Advisor|<span className="advisor-pill">\{activeScreen\}<\/span>/u,
  );
  assert.match(shell, /const canOpenCaseCopilot = Boolean/u);
  assert.match(shell, /disabled=\{!canOpenCaseCopilot\}/u);
  assert.match(shell, /onClick=\{canOpenCaseCopilot \? openAdvisorOrDataRoom : undefined\}/u);
  assert.doesNotMatch(shell, /\["Советник", "advisor_next_question", Sparkles\]/u);
  assert.doesNotMatch(advisorPages, /Шаг 1 из 4 для повышения точности/u);
  assert.match(advisorPages, /question\.originLabel/u);
  assert.match(advisorPages, /question\.context/u);
  assert.match(controller, /onGate2=\{handleGate2Decision\}/u);
  assert.match(controller, /onGate3=\{handleGate3Decision\}/u);
  assert.doesNotMatch(controller, /workflowPanel=\{/u);
  assert.match(shell, /onAdvisorAnswer/u);
  assert.match(shell, /onAdvisorImprovementDecision/u);
  assert.match(
    shell,
    /onContinueRecalculation=\{\(\) => openView\("progress_gate2", "Новый анализ"\)\}/u,
  );
  assert.match(shell, /advisorAnswerTransitionKey/u);
  assert.match(
    shell,
    /selectedView === "advisor_answer" && currentAdvisorAnswerKey[\s\S]*\? "advisor_updated_analysis"/u,
  );
  assert.match(shell, /async function handleAdvisorAnswer/u);
  assert.match(shell, /if \(accepted\) \{\s*openView\("advisor_updated_analysis", "Советник"\);/u);
  assert.match(controller, /async function answerAdvisor\(input: FounderAdvisorAnswerInput\): Promise<boolean>/u);
  assert.match(controller, /return Boolean\(\s*next\.advisorAnswer/u);
  assert.doesNotMatch(
    shell,
    /caseId\.slice|snapshot_hash\.slice|MISSING|trace_ids|prompt_versions/iu,
  );
  assert.match(
    controller,
    /advisorQuestion:\s*snapshot\?\.advisorQuestion \?\? null/u,
  );
  assert.match(controller, /onAdvisorAnswer=\{/u);
  assert.match(controller, /answerAdvisor/u);
  assert.match(controller, /onAdvisorImprovementDecision=\{/u);
  assert.match(controller, /decideAdvisorImprovement/u);
  assert.match(packageJson, /lib\/advisor-contracts\.test\.ts/u);
  assert.match(packageJson, /lib\/advisor-presentation\.test\.ts/u);
});

test("keeps advisor placeholder proposals read-only until six backend proposals are loaded", () => {
  const advisorPages = readFileSync(
    new URL("./founder-advisor-pages.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    advisorPages,
    /const canDecideAdvisorProposals =\s*proposalCards\.length === 6/u,
  );
  assert.match(
    advisorPages,
    /disabled=\{isBusy \|\| !canDecideAdvisorProposals \|\| !props\.onAdvisorImprovementDecision\}/u,
  );
  assert.doesNotMatch(
    advisorPages,
    /id:\s*`proposal-\$\{index\}`[\s\S]*onAdvisorImprovementDecision\?\.\(proposal\.id/u,
  );
});

test("wires the canonical report snapshot into a founder-safe 12-section panel", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const panel = readFileSync(
    new URL("./founder-report-panel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(shell, /data-founder-view="report-center"/u);
  assert.match(shell, /<FounderStrategyPages[\s\S]*page="report_center"/u);
  assert.doesNotMatch(shell, /<FounderReportPanel|<CaseBrief|honesty-strip/u);
  assert.match(
    controller,
    /reportSnapshot:\s*snapshot\?\.reportSnapshot \?\? null/u,
  );
  assert.match(panel, /id="founder-report-title"/u);
  assert.match(panel, /buildFounderReportPresentation/u);
  assert.match(panel, /data-report-section/u);
  assert.doesNotMatch(panel, /methodology|source_appendix/iu);
  assert.doesNotMatch(panel, /\b(score|chart|forecast)\b/iu);
});

test("wires a report-derived readiness and deep-questions panel without private support sections", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const analysisPages = readFileSync(
    new URL("./founder-analysis-pages.tsx", import.meta.url),
    "utf8",
  );
  const panel = readFileSync(
    new URL("./founder-readiness-panel.tsx", import.meta.url),
    "utf8",
  );
  const packageJson = readFileSync(
    new URL("../package.json", import.meta.url),
    "utf8",
  );

  assert.match(shell, /<FounderAnalysisPages[\s\S]*page="metrics"[\s\S]*workspace=\{workspace\}/u);
  assert.match(analysisPages, /buildFounderReportPresentation/u);
  assert.match(analysisPages, /workspace\?\.reportSnapshot/u);
  assert.match(analysisPages, /readinessScore/u);
  assert.match(analysisPages, /evidenceScore/u);
  assert.match(panel, /id="founder-readiness-title"/u);
  assert.match(panel, /buildFounderReadinessPresentation/u);
  assert.match(panel, /data-readiness-dimension/u);
  assert.match(panel, /data-deep-section/u);
  assert.match(panel, /dimensionCards\.map\(\(card, index\) =>/u);
  assert.match(panel, /gaps\.map\(\(gap, index\) =>/u);
  assert.match(panel, /questions\.map\(\(question, index\) =>/u);
  assert.match(panel, /Что сделать дальше/u);
  assert.doesNotMatch(
    panel,
    /methodology|source_appendix|trace_ids|founder-readiness__lineage|snapshot_revision|snapshot_id|snapshotHash|metricPackHash|MISSING|Хеш снимка|Пакет метрик|Снимок готовности|<code>/iu,
  );
  assert.doesNotMatch(panel, /\b(score|chart|forecast|valuation)\b/iu);
  assert.match(packageJson, /lib\/readiness-presentation\.test\.ts/u);
});

test("wires canonical report charts without private support data or invented scores", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const analysisPages = readFileSync(
    new URL("./founder-analysis-pages.tsx", import.meta.url),
    "utf8",
  );
  const panel = readFileSync(
    new URL("./founder-charts-panel.tsx", import.meta.url),
    "utf8",
  );
  const packageJson = readFileSync(
    new URL("../package.json", import.meta.url),
    "utf8",
  );
  const css = readFileSync(
    new URL("./founder-analysis-pages.module.css", import.meta.url),
    "utf8",
  );

  assert.match(shell, /<FounderAnalysisPages[\s\S]*page="metrics"[\s\S]*workspace=\{workspace\}/u);
  assert.match(analysisPages, /buildFounderReportPresentation/u);
  assert.match(analysisPages, /workspace\?\.reportSnapshot/u);
  assert.match(panel, /id="founder-charts-title"/u);
  assert.match(panel, /buildFounderChartsPresentation/u);
  assert.match(panel, /data-founder-chart/u);
  assert.match(panel, /data-chart-key/u);
  assert.match(panel, /data-chart-point/u);
  assert.match(panel, /data-chart-scale/u);
  assert.match(panel, /chart\.scale === "shared"/u);
  assert.doesNotMatch(panel, /data-chart-lineage|lineage\.snapshotId|lineage\.snapshotHash/iu);
  assert.doesNotMatch(panel, /methodology|source_appendix|trace_ids/iu);
  assert.doesNotMatch(panel, /\b(score|forecast|valuation)\b/iu);
  assert.match(packageJson, /lib\/chart-presentation\.test\.ts/u);
  assert.match(css, /\.chartCard\s*\{/u);
  assert.match(css, /\.sparkline\s*\{/u);
});

test("keeps mounted founder report gtm and chart panels free from visible lineage codes", () => {
  const panels = [
    readFileSync(new URL("./founder-report-panel.tsx", import.meta.url), "utf8"),
    readFileSync(new URL("./founder-gtm-panel.tsx", import.meta.url), "utf8"),
    readFileSync(new URL("./founder-charts-panel.tsx", import.meta.url), "utf8"),
  ].join("\n");

  assert.match(panels, /Выводы, пробелы и следующие проверки/u);
  assert.match(panels, /План выхода на рынок/u);
  assert.match(panels, /7 \/ 30 \/ 60 \/ 90 дней/u);
  assert.match(panels, /Визуализация данных из документов/u);
  assert.match(panels, /Значения\s+метрик, заявленных в документах/u);
  assert.doesNotMatch(panels, /Визуализация подтвержденных данных|подтвержденных метрик/u);
  assert.doesNotMatch(
    panels,
    /data-report-lineage|data-chart-lineage|<code>|snapshotId|snapshotHash|snapshotLabel|gtm_hash|reasonCode|gapCode|experimentCodes\[index\]|lineage\.snapshotId|lineage\.snapshotHash|lineage\.profileId|lineage\.productValidationSnapshotId|lineage\.marketResearchSnapshotId|section_ref|sha256|MISSING/iu,
  );
  assert.match(panels, /Техническая проверка доступна в кабинете администратора/u);
});

test("lets the upload target shrink-wrap so the selected-file inventory expands the hero", () => {
  const css = readFileSync(
    new URL("./upload-entry.module.css", import.meta.url),
    "utf8",
  );
  const targetBlock = css.match(/\.dropZone\s*\{([^}]*)\}/u);

  const targetRules = targetBlock?.[1];
  assert.ok(targetRules, "upload target rules must exist");
  assert.doesNotMatch(targetRules, /height:\s*100%/u);
  assert.match(targetRules, /min-height:\s*304px/u);
});

test("renders the approved desktop dashboard shell instead of the legacy dossier topbar", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

  assert.match(shell, /founder-dashboard-shell/u);
  assert.match(shell, /founder-sidebar/u);
  assert.match(shell, /founder-ask-bar/u);
  assert.match(shell, /founder-ask-bar founder-ask-bar--full/u);
  assert.match(shell, /data-dashboard-bottom-row="three-columns"/u);
  assert.match(shell, /dashboard-card/u);
  assert.match(shell, /План улучшений/u);
  assert.match(shell, /Спросить ИИ-советника/u);
  assert.doesNotMatch(shell, /<header className="product-bar">/u);

  assert.match(css, /\.founder-dashboard-shell\s*\{/u);
  assert.match(css, /\.founder-sidebar\s*\{/u);
  assert.match(css, /\.founder-ask-bar\s*\{/u);
  assert.match(shell, /<Sparkles[\s\S]*className="founder-ask-bar__spark"/u);
  assert.match(shell, /<ArrowUpRight[\s\S]*className="founder-ask-bar__arrow"/u);
  assert.match(shell, /className="dashboard-pink-link"[\s\S]*Смотреть все выводы/u);
  assert.match(shell, /className="dashboard-soft-pink-button"[\s\S]*Центр отчётов/u);
  assert.match(css, /\.founder-dashboard-hero\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)/u);
  assert.match(css, /\.founder-ask-bar\s*\{[\s\S]*min-height:\s*64px/u);
  assert.match(css, /\.dashboard-bottom-row\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1\.18fr\) minmax\(0,\s*0\.94fr\) minmax\(0,\s*0\.9fr\)/u);
  assert.match(css, /\.dashboard-card\s*\{/u);
  assert.match(css, /--fi-sidebar-width:\s*232px/u);
  assert.match(css, /grid-template-columns:\s*var\(--fi-sidebar-width\) minmax\(0,\s*1fr\)/u);
  assert.match(css, /\.dashboard-pink-link,\s*\.dashboard-soft-pink-button\s*\{/u);
  assert.match(css, /\.dashboard-soft-pink-button\s*\{/u);
});

test("keeps the approved desktop views distinct instead of collapsing into the legacy analysis page", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

  assert.match(shell, /type FounderShellView =[\s\S]*\| "dashboard"[\s\S]*\| "advisor_improved_plan"/u);
  assert.match(shell, /useState<FounderShellView>\("dashboard"\)/u);
  assert.doesNotMatch(
    shell,
    /stage !== "idle"[\s\S]*selectedView === "dashboard"[\s\S]*"progress_gate2"/u,
  );
  assert.match(shell, /data-founder-view="dashboard"/u);
  assert.match(shell, /data-founder-view="progress-gate2"/u);
  assert.match(shell, /data-founder-view="overview"/u);
  assert.match(shell, /data-founder-view="data-room"/u);
  assert.match(shell, /data-founder-view="metrics"/u);
  assert.match(shell, /data-founder-view="market"/u);
  assert.match(shell, /data-founder-view="risks"/u);
  assert.match(shell, /data-founder-view="action-plan"/u);
  assert.match(shell, /data-founder-view="report-center"/u);
  assert.match(shell, /Материалы проекта/u);
  assert.match(shell, /Покрытие проекта/u);
  assert.match(shell, /Контроль приватности/u);
  assert.match(shell, /<h1>Новый анализ<\/h1>/u);
  assert.match(
    shell,
    /Добавьте всё, что уже есть — система сама определит модель бизнеса и нужные проверки/u,
  );
  assert.doesNotMatch(shell, /Добавьте материалы проекта/u);
  assert.match(shell, /data-room-primary-cta/u);
  const dataRoomUploadStart = shell.indexOf('<div className="data-room-upload">');
  const dataRoomUploadEnd = shell.indexOf("</div>", dataRoomUploadStart);
  assert.ok(dataRoomUploadStart >= 0 && dataRoomUploadEnd > dataRoomUploadStart);
  assert.doesNotMatch(
    shell.slice(dataRoomUploadStart, dataRoomUploadEnd),
    /onStartAnalysis=/u,
  );
  assert.match(
    shell,
    /<aside className="data-room-side">[\s\S]*data-room-primary-cta/u,
  );
  assert.match(shell, /<FounderAnalysisPages[\s\S]*page="progress_gate2"/u);
  assert.match(shell, /<FounderAnalysisPages[\s\S]*page="overview"/u);
  assert.match(shell, /<FounderAnalysisPages[\s\S]*page="metrics"/u);
  assert.match(shell, /onGate2=\{handleGate2Decision\}/u);
  assert.doesNotMatch(shell, /<CaseBrief[\s\S]*workflowPanel=|stage !== "idle"/u);
  assert.doesNotMatch(shell, /data-founder-view="analysis"/u);
  assert.doesNotMatch(
    shell,
    /FlowPilot|68 \/ 100|Спрос подтверждён|PayDock|LumenAI|GreenRoute|Клиенты видят ценность|Хорошо|Высокая/u,
  );

  assert.match(css, /\.founder-view\s*\{/u);
  assert.match(css, /\.data-room-layout\s*\{/u);
  assert.match(css, /\.data-room-header\s*\{/u);
  assert.match(css, /\.privacy-card\s*\{/u);
  assert.match(css, /\.privacy-choice\.is-selected\s*\{/u);
  assert.match(css, /\.coverage-grid\s*\{/u);
  assert.doesNotMatch(css, /\.founder-sidebar__advisor\s*\{/u);
});

test("clears the selected file draft exactly once after the current analysis is accepted", async () => {
  const selectedFiles = [new File(["pitch"], "pitch.pdf")];
  const startedFiles: Array<readonly File[]> = [];
  let clearDraftCalls = 0;
  const instance = {
    async start(files: readonly File[]) {
      startedFiles.push(files);
      return true;
    },
    getSnapshot: () => ({ uploadAccepted: true }),
  };

  await startFounderWorkspaceAnalysis({
    clearDraft: () => {
      clearDraftCalls += 1;
    },
    getCurrentInstance: () => instance,
    selectedFiles,
  });

  assert.deepEqual(startedFiles, [selectedFiles]);
  assert.equal(clearDraftCalls, 1);
});

test("retains the selected file draft when analysis start finishes without upload acceptance", async () => {
  let clearDraftCalls = 0;
  const instance = {
    async start() {
      return false;
    },
    getSnapshot: () => ({ uploadAccepted: false }),
  };

  await startFounderWorkspaceAnalysis({
    clearDraft: () => {
      clearDraftCalls += 1;
    },
    getCurrentInstance: () => instance,
    selectedFiles: [new File(["deck"], "deck.pdf")],
  });

  assert.equal(clearDraftCalls, 0);
});

test("counts populated profile fields without calling them independently confirmed", () => {
  const overview = readFileSync(
    new URL("./founder-startup-overview-panel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(overview, /Заполнено полей:/u);
  assert.doesNotMatch(overview, /Подтверждено полей:/u);
});

test("reports a rejected upload start so the shell can keep the Documents view selected", async () => {
  let clearDraftCalls = 0;
  const instance = {
    async start() {
      return false;
    },
    getSnapshot: () => ({ uploadAccepted: false }),
  };

  const accepted = await startFounderWorkspaceAnalysis({
    clearDraft: () => {
      clearDraftCalls += 1;
    },
    getCurrentInstance: () => instance,
    selectedFiles: [new File(["deck"], "deck.pdf")],
  });

  assert.equal(accepted, false);
  assert.equal(clearDraftCalls, 0);
});

test("retains a replacement draft when start is a no-op under a prior accepted snapshot", async () => {
  let clearDraftCalls = 0;
  let startCalls = 0;
  const instance = {
    async start() {
      startCalls += 1;
      return false;
    },
    getSnapshot: () => ({ uploadAccepted: true }),
  };

  const accepted = await startFounderWorkspaceAnalysis({
    clearDraft: () => {
      clearDraftCalls += 1;
    },
    getCurrentInstance: () => instance,
    selectedFiles: [new File(["replacement"], "replacement.pdf")],
  });

  assert.equal(startCalls, 1);
  assert.equal(accepted, false);
  assert.equal(clearDraftCalls, 0);
});

test("retains the selected file draft and propagates a failed analysis start", async () => {
  let clearDraftCalls = 0;
  const failure = new Error("Upload connection failed");
  const instance = {
    async start() {
      throw failure;
    },
    getSnapshot: () => ({ uploadAccepted: true }),
  };

  await assert.rejects(
    startFounderWorkspaceAnalysis({
      clearDraft: () => {
        clearDraftCalls += 1;
      },
      getCurrentInstance: () => instance,
      selectedFiles: [new File(["deck"], "deck.pdf")],
    }),
    failure,
  );
  assert.equal(clearDraftCalls, 0);
});

test("does not clear a newer draft when a stale analysis instance finishes later", async () => {
  let releaseStaleStart!: () => void;
  const staleStart = new Promise<void>((resolve) => {
    releaseStaleStart = resolve;
  });
  let clearDraftCalls = 0;
  const staleInstance = {
    async start() {
      await staleStart;
      return true;
    },
    getSnapshot: () => ({ uploadAccepted: true }),
  };
  const newerInstance = {
    async start() {
      return false;
    },
    getSnapshot: () => ({ uploadAccepted: false }),
  };
  let currentInstance = staleInstance;

  const startPromise = startFounderWorkspaceAnalysis({
    clearDraft: () => {
      clearDraftCalls += 1;
    },
    getCurrentInstance: () => currentInstance,
    selectedFiles: [new File(["old"], "old.pdf")],
  });
  currentInstance = newerInstance;
  releaseStaleStart();
  await startPromise;

  assert.equal(clearDraftCalls, 0);
});

test("removes only the accepted file batch when the same analysis instance finishes after a newer draft selection", async () => {
  let releaseStart!: () => void;
  const pendingStart = new Promise<void>((resolve) => {
    releaseStart = resolve;
  });
  const uploadedFile = new File(["old"], "old.pdf");
  const newerFile = new File(["new"], "new.pdf");
  let draftFiles = [uploadedFile];
  const instance = {
    async start() {
      await pendingStart;
      return true;
    },
    getSnapshot: () => ({ uploadAccepted: true }),
  };

  const startPromise = startFounderWorkspaceAnalysis({
    clearDraft: (acceptedFiles: readonly File[]) => {
      draftFiles = draftFiles.filter((file) => !acceptedFiles.includes(file));
    },
    getCurrentInstance: () => instance,
    selectedFiles: [uploadedFile],
  });
  draftFiles = [uploadedFile, newerFile];
  releaseStart();
  await startPromise;

  assert.deepEqual(draftFiles, [newerFile]);
});

test("wires Gate 2 and Gate 3 through founder-safe desktop pages without the legacy workflow panel", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const analysisPages = readFileSync(
    new URL("./founder-analysis-pages.tsx", import.meta.url),
    "utf8",
  );
  const strategyPages = readFileSync(
    new URL("./founder-strategy-pages.tsx", import.meta.url),
    "utf8",
  );

  assert.match(shell, /canApproveGate2\?:\s*boolean/u);
  assert.match(shell, /canApproveGate3\?:\s*boolean/u);
  assert.match(shell, /onGate2\?:[\s\S]*Promise<boolean>/u);
  assert.match(shell, /onGate3\?:[\s\S]*Promise<boolean>/u);
  assert.match(controller, /async function handleGate2Decision/u);
  assert.match(controller, /async function handleGate3Decision/u);
  assert.match(controller, /onGate2=\{handleGate2Decision\}/u);
  assert.match(controller, /onGate3=\{handleGate3Decision\}/u);
  assert.match(
    controller,
    /function hasHydratedGate2Evidence\([\s\S]*field\.status === "source_fact"[\s\S]*field\.values\.length > 0[\s\S]*field\.evidence_refs\.length > 0/u,
  );
  assert.match(
    controller,
    /canApproveGate2:\s*stage === "gate2_preview_ready"[\s\S]*hasHydratedGate2Evidence\(snapshot\)[\s\S]*!snapshot\?\.busy/u,
  );
  assert.match(controller, /canApproveGate3:\s*stage === "gate3_review_required"/u);
  assert.doesNotMatch(controller, /workflowPanel=\{/u);

  assert.match(analysisPages, /canApproveGate2\?:\s*boolean/u);
  assert.match(
    analysisPages,
    /workspace\?\.canApproveGate2 && hasDocumentReadEvidence\(workspace\)[\s\S]*\? handleGate2Approval[\s\S]*: undefined/u,
  );
  assert.doesNotMatch(analysisPages, /onGate2\?\.\("approved"\);\s*onStartDeepAnalysis\?\.\(\)/u);
  assert.doesNotMatch(analysisPages, /workflowPanel|workflowDecisionPanel|WorkspaceActionPanel/u);

  assert.match(shell, /async function handleGate2Approval/u);
  assert.match(shell, /const accepted = await onGate2\?\.\("approved"\)/u);
  assert.match(shell, /if \(accepted\) \{\s*openView\("overview", "Обзор"\)/u);
  assert.match(strategyPages, /onAcceptDirection\?:\s*\(\)\s*=>\s*void/u);
  assert.match(shell, /async function handleGate3Approval/u);
  assert.match(shell, /const accepted = await onGate3\?\.\(\)/u);
  assert.match(shell, /workspace\?\.canApproveGate3 \? handleGate3Approval : undefined/u);
  const gate3ApprovalBody =
    shell.match(/async function handleGate3Approval\(\) \{([\s\S]*?)\n  \}/u)?.[1] ?? "";
  assert.match(
    gate3ApprovalBody,
    /if \(accepted\) \{\s*openView\("report_center", "Отчёты"\)/u,
  );
  assert.match(controller, /const report = validatedReport\(next\)/u);
  assert.match(controller, /function canGenerateFinalLaunchPack\(\)/u);
  assert.match(
    controller,
    /return canGenerateLaunchPack\(\)/u,
  );
  const finalLaunchPackGate =
    controller.match(/function canGenerateFinalLaunchPack\(\) \{([\s\S]*?)\n  \}/u)?.[1] ?? "";
  assert.doesNotMatch(finalLaunchPackGate, /validatedReport\(snapshot\)/u);
  assert.match(
    controller,
    /onPrepareAiAsset=\{canGenerateLaunchPack\(\) \? prepareCaseAsset : undefined\}/u,
  );
  assert.match(
    controller,
    /onBuildWorkpack=\{canGenerateFinalLaunchPack\(\) \? generateLaunchPack : undefined\}/u,
  );
  assert.doesNotMatch(
    controller,
    /next\.display\.stage !== "gate3_review_required"[\s\S]*next\.display\.stage !== "error"/u,
  );
});

test("keeps advisor answers and report paging fail-closed and interactive", () => {
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const advisorPages = readFileSync(
    new URL("./founder-advisor-pages.tsx", import.meta.url),
    "utf8",
  );
  const strategyPages = readFileSync(
    new URL("./founder-strategy-pages.tsx", import.meta.url),
    "utf8",
  );

  assert.match(controller, /if \(!input\.questionId\.trim\(\)\) return false;/u);
  assert.match(controller, /if \(!instance\) return false;/u);
  assert.match(shell, /function openAdvisorOrDataRoom/u);
  assert.match(advisorPages, /const canAnswer = Boolean\(questionId\)/u);
  assert.match(advisorPages, /disabled=\{isBusy \|\| !canAnswer\}/u);
  assert.doesNotMatch(advisorPages, /questionId:\s*props\.workspace\?\.advisorQuestion\?\.next_question\?\.question_id \?\? ""/u);
  assert.match(strategyPages, /useState\(1\)/u);
  assert.match(strategyPages, /setReportPage/u);
  assert.match(strategyPages, /currentReportSection/u);
});

test("projects approved Gate 4 report state and artifact URLs into the founder report center", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const strategyPages = readFileSync(
    new URL("./founder-strategy-pages.tsx", import.meta.url),
    "utf8",
  );

  assert.match(shell, /freezeApproved\?:\s*boolean/u);
  assert.match(shell, /pdfUrl\?:\s*string/u);
  assert.match(controller, /freezeApproved:\s*report\.freeze_status === "approved"/u);
  assert.match(controller, /pdfUrl:\s*snapshot\?\.artifactUrls\?\.pdf/u);
  assert.match(controller, /snapshotLabel:\s*report\.freeze_status === "approved"\s*\?\s*"Версия зафиксирована"\s*:\s*"Финальная версия отчёта"/u);
  assert.doesNotMatch(controller, /snapshotLabel:\s*`Канонический снимок · rev\. \$\{report\.snapshot_revision\}`/u);
  assert.doesNotMatch(controller, /<strong>rev\. \{report\.snapshot_revision\}<\/strong>/u);
  assert.match(strategyPages, /const freezeApproved = Boolean\(workspace\?\.report\?\.freezeApproved\)/u);
  assert.match(strategyPages, /const allReportUrlsPresent = Boolean\(pdfUrl && htmlUrl && jsonUrl\)/u);
  assert.match(strategyPages, /const hasApprovedLineage = Boolean\(freezeApproved && allReportUrlsPresent\)/u);
  assert.match(strategyPages, /reportStatus = hasApprovedLineage[\s\S]*"Отчёт зафиксирован"/u);
  assert.match(strategyPages, /hasApprovedLineage && approvedPdfUrl[\s\S]*Открыть PDF/u);
  assert.match(
    strategyPages,
    /<small>Одобрено<\/small><strong>\{hasApprovedLineage \? "да" : "после подтверждения"\}<\/strong>/u,
  );
});

test("resolves the overview sidebar to the readiness screen when deep analysis is ready", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );

  assert.match(shell, /function resolveSidebarView\([\s\S]*stage === "deep_ready"[\s\S]*return "overview"/u);
  assert.match(
    shell,
    /selectedView === "dashboard" && stage === "deep_ready"\s*\? "overview"\s*:\s*selectedView/u,
  );
  assert.match(shell, /onContinueRecalculation=\{\(\) => openView\("progress_gate2", "Новый анализ"\)\}/u);
  assert.match(shell, /onClick=\{\(\) => openView\(resolvedView, label\)\}/u);
  assert.match(shell, /activeView === "overview"[\s\S]*\? "overview"/u);
});

test("keeps data-room privacy choice explicit and advisor tabs accessible", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    shell,
    /useState<\s*"local_documents" \| "research_prepared"\s*>\("local_documents"\)/u,
  );
  assert.match(shell, /aria-pressed=\{privacyMode === "research_prepared"\}/u);
  assert.match(shell, /aria-pressed=\{privacyMode === "local_documents"\}/u);
  assert.match(shell, /setPrivacyMode\("research_prepared"\)/u);
  assert.match(shell, /setPrivacyMode\("local_documents"\)/u);
  assert.match(shell, /Подготовить безопасный ресерч/u);
  assert.match(shell, /Согласие спросим отдельно перед публичным поиском/u);
  assert.doesNotMatch(shell, /Разрешить безопасный поиск/u);
  assert.match(shell, /<FounderAdvisorPages/u);
  assert.match(shell, /activeView === "advisor_next_question"/u);
  assert.match(shell, /activeView === "advisor_answer"/u);
  assert.match(shell, /activeView === "advisor_updated_analysis"/u);
  assert.match(shell, /activeView === "advisor_improved_plan"/u);
});

test("keeps shell navigation actions honest when data is not ready", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

  assert.match(
    shell,
    /const advisorQuestionId =\s*workspace\?\.advisorQuestion\?\.next_question\?\.question_id\.trim\(\)/u,
  );
  assert.match(shell, /const canOpenCaseCopilot = Boolean\(/u);
  assert.match(shell, /workspace\?\.copilotState \|\| workspace\?\.copilotThread \|\| advisorQuestionId/u);
  assert.match(shell, /disabled=\{!canOpenCaseCopilot\}/u);
  assert.match(shell, /onClick=\{canOpenCaseCopilot \? openAdvisorOrDataRoom : undefined\}/u);
  assert.doesNotMatch(shell, /const questionId = workspace\?\.advisorQuestion[\s\S]*openDataRoom\(\);/u);
  for (const page of ["progress_gate2", "overview", "metrics"] as const) {
    assert.match(
      shell,
      new RegExp(
        `<FounderAnalysisPages[\\s\\S]*onOpenAdvisor=\\{openCaseCopilot\\}[\\s\\S]*page="${page}"`,
        "u",
      ),
    );
  }

  assert.match(shell, /function openAnalysisOrDataRoom/u);
  assert.match(shell, /stage === "primary_ready"[\s\S]*openView\("progress_gate2", "Новый анализ"\)/u);
  assert.match(shell, /stage === "deep_ready"[\s\S]*openView\("overview", "Обзор"\)/u);
  assert.match(shell, /stage === "analysis_running"[\s\S]*openView\("progress_gate2", "Новый анализ"\)/u);
  assert.match(shell, /onBackToAnalysis=\{openAnalysisOrDataRoom\}/u);
  assert.doesNotMatch(shell, /onBackToAnalysis=\{openDataRoom\}/u);

  assert.match(shell, /aria-label="Настройки пока недоступны"/u);
  assert.match(shell, /aria-label="Помощь пока недоступна"/u);
  assert.match(shell, /disabled[\s\S]*>\s*<Info/u);
  assert.match(shell, /disabled[\s\S]*>\s*<CircleHelp/u);
  assert.match(css, /\.founder-ask-bar:disabled\s*\{/u);
  assert.match(css, /\.founder-sidebar__footer button:disabled\s*\{/u);
  assert.match(css, /\.founder-ask-bar:not\(:disabled\):hover\s*\{/u);
  assert.match(css, /\.founder-sidebar__footer button:not\(:disabled\):hover\s*\{/u);
  assert.doesNotMatch(css, /\.founder-ask-bar:hover\s*\{/u);
  assert.doesNotMatch(css, /\.founder-sidebar__footer button:hover\s*\{/u);
});

test("maps the approved desktop mockups to distinct founder views without a fabricated user name", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );

  const expectedViews = [
    "dashboard",
    "data_room",
    "progress_gate2",
    "overview",
    "metrics",
    "market",
    "risks",
    "action_plan",
    "report_center",
    "advisor_next_question",
    "advisor_answer",
    "advisor_updated_analysis",
    "advisor_improved_plan",
  ];

  for (const view of expectedViews) {
    assert.match(shell, new RegExp(`"${view}"`, "u"));
    assert.match(shell, new RegExp(`data-founder-view="${view.replaceAll("_", "-")}"`, "u"));
  }

  assert.doesNotMatch(shell, /Алексей/u);
  assert.doesNotMatch(shell, /data-founder-view="analysis"/u);
  assert.match(
    shell,
    /const sidebarItems = \[[\s\S]*\["Обзор", "dashboard", Landmark\][\s\S]*\["Новый анализ", "data_room", CircleDollarSign\][\s\S]*\["Метрики", "metrics", ChartNoAxesColumnIncreasing\][\s\S]*\["Рынок", "market", PieChart\][\s\S]*\["Риски", "risks", ShieldAlert\][\s\S]*\["План действий", "action_plan", Flag\][\s\S]*\["Отчёты", "report_center", FileText\][\s\S]*\] as const/u,
  );
  assert.doesNotMatch(
    shell,
    /\["Прогресс", "progress_gate2", Rocket\]|\["Советник", "advisor_next_question", Sparkles\]/u,
  );
  assert.match(shell, /openView\("progress_gate2", "Новый анализ"\)/u);
  assert.match(shell, /activeView === "progress_gate2"\s*\?\s*"data_room"/u);
  assert.match(
    shell,
    /activeView === "progress_gate2"\s*\?\s*view === "data_room"\s*:\s*activeSidebarView === resolvedView/u,
  );
  assert.match(shell, /sidebarItems\.map\(\(\[label, view, Icon\]\)/u);
  assert.doesNotMatch(shell, /advisorShortcutItems|initialScreen="next-question"|initialScreen="answer"|initialScreen="updated-analysis"|initialScreen="improved-plan"/u);
});

test("uses real icon components and approved upload variants instead of text glyphs", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const uploadEntry = readFileSync(
    new URL("./upload-entry.tsx", import.meta.url),
    "utf8",
  );

  assert.match(shell, /Sparkles/u);
  assert.match(shell, /ArrowUpRight/u);
  assert.match(uploadEntry, /UploadCloud/u);
  assert.match(shell, /<UploadEntry[\s\S]*?variant="dashboard"/u);
  assert.match(shell, /<UploadEntry[\s\S]*?variant="data-room"/u);
  assert.doesNotMatch(uploadEntry, /<span aria-hidden="true">\+<\/span>/u);
  assert.doesNotMatch(uploadEntry, /\?<\/span>|>\+<\/span>/u);
});

test("resets the desktop viewport and keeps advisor result screens anchored to their source navigation", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    shell,
    /function openView\([\s\S]*window\.scrollTo\(\{\s*top:\s*0,\s*left:\s*0,\s*behavior:\s*"instant"\s*\}\)/u,
  );
  assert.match(
    shell,
    /activeView === "advisor_updated_analysis"[\s\S]*\? resolveSidebarView\("dashboard"\)/u,
  );
  assert.match(
    shell,
    /activeView === "advisor_improved_plan"[\s\S]*\? "action_plan"/u,
  );
  assert.match(
    shell,
    /const activeNavLabel = activeView === "advisor_updated_analysis"[\s\S]*\? "Обзор"[\s\S]*activeView === "advisor_improved_plan"[\s\S]*\? "План действий"/u,
  );
});

test("keeps admin observability as a real sanitized Streamlit redirect instead of a fake product screen", () => {
  const adminPage = readFileSync(
    new URL("../app/admin/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(adminPage, /NEXT_PUBLIC_ADMIN_CONSOLE_URL/u);
  assert.match(adminPage, /8501/u);
  assert.match(adminPage, /redirect/u);
  assert.doesNotMatch(adminPage, /admin-bridge/u);
  assert.doesNotMatch(adminPage, /Streamlit Admin Console/u);
  assert.doesNotMatch(adminPage, /founder-admin-console/u);
  assert.doesNotMatch(adminPage, /Алексей/u);
});

test("keeps the public comparables route inside the new desktop visual system", () => {
  const comparablesPage = readFileSync(
    new URL("../app/comparables/page.tsx", import.meta.url),
    "utf8",
  );
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

  assert.match(comparablesPage, /founder-comparables-console/u);
  assert.match(comparablesPage, /PublicComparablesPanel/u);
  assert.match(comparablesPage, /Рынок и конкуренты/u);
  assert.doesNotMatch(comparablesPage, /className="brand"/u);
  assert.doesNotMatch(comparablesPage, /brand-mark/u);
  assert.doesNotMatch(comparablesPage, /product-bar/u);
  assert.doesNotMatch(comparablesPage, /Алексей/u);

  assert.match(css, /\.founder-comparables-console\s*\{/u);
  assert.match(css, /\.comparables-console-main\s*\{/u);
  assert.match(css, /\.comparables-lens-grid\s*\{/u);
});

test("keeps remaining generated founder chrome Russian-first while preserving internal identifiers", () => {
  const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const comparables = readFileSync(
    new URL("../app/comparables/page.tsx", import.meta.url),
    "utf8",
  );
  const shell = readFileSync(new URL("./founder-shell.tsx", import.meta.url), "utf8");
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const generatedChrome = [layout, comparables, shell, controller].join("\n");

  for (const required of [
    "Аналитика для основателя",
    "Понятный анализ стартапа с ИИ",
    "Публичные аналоги",
    "ориентиры экономики продукта",
    "Навигация по публичным аналогам",
    "Рынок<br />проекта",
    "подключения к актуальным источникам",
    "Спросить ИИ-советника",
    "провайдера ИИ",
  ]) {
    assert.match(
      generatedChrome,
      new RegExp(required.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "iu"),
    );
  }

  assert.doesNotMatch(
    generatedChrome,
    /Понятный AI-анализ|title: "Founder Intelligence"|Public comparables · Founder Intelligence|unit-economics proxies|aria-label="Comparables navigation"|<span>Founder<br \/>Market<\/span>|доступность public comparables|Отдельно от Admin, privacy и LangSmith|live-доступа|AI выделит|Спросить AI-советника|AI соберёт профиль|подключённого AI-провайдера|AI-провайдер недоступен/iu,
  );
  assert.doesNotMatch(controller, /caseFixtureMode = "live"/u);
  assert.match(controller, /resolveFounderRuntimeConfig/u);
  assert.match(shell, /onPrepareAiAsset/u);
  assert.match(shell, /"pricing"/u);
});

test("wires Case Copilot v1 as one canonical right rail and responsive drawer", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const orchestrator = readFileSync(
    new URL("./founder-workspace-orchestrator.ts", import.meta.url),
    "utf8",
  );
  const panel = readFileSync(
    new URL("./case-copilot-panel.tsx", import.meta.url),
    "utf8",
  );
  const panelCss = readFileSync(
    new URL("./case-copilot-panel.module.css", import.meta.url),
    "utf8",
  );
  const questionCard = readFileSync(
    new URL("./case-question-card.tsx", import.meta.url),
    "utf8",
  );
  const scenarioMetrics = readFileSync(
    new URL("./founder-scenario-metrics.tsx", import.meta.url),
    "utf8",
  );
  const casePresentation = readFileSync(
    new URL("../lib/case-copilot-presentation.ts", import.meta.url),
    "utf8",
  );

  assert.match(shell, /import \{ CaseCopilotPanel \} from "@\/components\/case-copilot-panel"/u);
  assert.match(shell, /import copilotStyles from "\.\/case-copilot-panel\.module\.css"/u);
  assert.match(shell, /founder-dashboard-shell \$\{copilotStyles\.shellWithCopilot\}/u);
  assert.match(shell, /caseCopilotOpen \? "" : copilotStyles\.shellCopilotClosed/u);
  assert.match(shell, /caseCopilotOpen/u);
  assert.match(shell, /caseCopilotFocus/u);
  assert.match(shell, /caseCopilotPreferredAnswerType/u);
  assert.match(shell, /<CaseCopilotPanel[\s\S]*copilotState=\{workspace\?\.copilotState/u);
  assert.match(shell, /preferredAnswerType=\{caseCopilotPreferredAnswerType\}/u);
  assert.match(shell, /copilotThread=\{workspace\?\.copilotThread/u);
  assert.match(shell, /researchPlan=\{workspace\?\.researchPlan \?\? null\}/u);
  assert.match(shell, /researchJob=\{workspace\?\.researchJob \?\? null\}/u);
  assert.match(shell, /providerStatus=\{workspace\?\.providerStatus \?\? null\}/u);
  assert.match(shell, /onOpenAdvisor=\{openCaseCopilot/u);
  assert.doesNotMatch(shell, /openView\("advisor_next_question", "Советник"\)/u);
  assert.match(controller, /copilotThread:\s*snapshot\?\.copilotThread \?\? null/u);
  assert.match(controller, /providerStatus:\s*snapshot\?\.status\?\.provider_status \?\? null/u);
  assert.match(controller, /researchPlan:\s*snapshot\?\.researchPlan \?\? null/u);
  assert.match(controller, /researchJob:\s*snapshot\?\.researchJob \?\? null/u);
  assert.match(controller, /onCopilotAssumptionSubmit=\{saveCaseCopilotAssumption\}/u);
  assert.match(controller, /onCopilotFactSubmit=\{saveCaseCopilotFact\}/u);
  assert.match(controller, /onCopilotResearchPrepare=\{prepareCaseCopilotResearch\}/u);
  assert.match(controller, /research_preparing:\s*"Готовлю безопасный план публичного поиска/u);
  assert.match(controller, /Record<RequestedResearchAcquisitionMode, string>/u);
  assert.match(controller, /deterministic_offline_fixture:\s*"Готовлю детерминированное офлайн-демо без интернет-запроса/u);
  assert.match(controller, /live_public_research:\s*"Ищу публичные источники в live-интернете/u);
  assert.doesNotMatch(controller, /configured:\s*"Ищу публичные источники в live-интернете/u);
  assert.doesNotMatch(controller, /unavailable:\s*"Фиксирую безопасный отложенный путь без live-провайдера/u);
  assert.match(controller, /research_recalculating:\s*"Пересчитываю сценарные метрики/u);
  assert.match(controller, /onCopilotUnknownSubmit=\{sendCaseCopilotUnknown\}/u);
  assert.match(controller, /buildCaseCopilotUnknownMessageRequest\(/u);
  assert.doesNotMatch(controller, /submitCopilotAssumption\(\{[\s\S]*message:\s*"unknown"/u);
  assert.match(controller, /onScenarioSelect=\{selectCaseScenario\}/u);
  assert.match(orchestrator, /copilotThread:\s*CopilotThreadResponse \| null/u);
  assert.match(orchestrator, /api\.getCopilotThread/u);
  assert.match(panel, /data-case-copilot-panel/u);
  assert.match(panel, /preferredAnswerType=\{preferredAnswerType\}/u);
  assert.match(panel, /key=\{`\$\{focusToken\}:\$\{preferredAnswerType \?\? "manual"\}`\}/u);
  assert.match(caseQuestionCardComponent, /preferredAnswerType\?: CaseQuestionAnswerType/u);
  assert.match(caseQuestionCardComponent, /useState<CaseQuestionAnswerType>\(preferredAnswerType \?\? "manual"\)/u);
  assert.doesNotMatch(caseQuestionCardComponent, /useEffect\(\(\) => \{\s*if \(!preferredAnswerType\) return;\s*setLocalError\(null\);\s*setAnswerType\(preferredAnswerType\)/u);
  assert.match(panel, /role="dialog"/u);
  assert.match(panel, /data-layout=\{open \? "rail" : "drawer"\}/u);
  assert.match(panel, /messages\.map/u);
  assert.match(panel, /formatCopilotActionStatus\(action\.status\)/u);
  assert.match(panel, /formatCopilotAction\(action\.action\)/u);
  assert.match(panel, /action\.status === "blocked"/u);
  assert.match(panel, /source_fact/u);
  assert.match(panel, /Заявлено в загруженном документе/u);
  assert.doesNotMatch(panel, /подтверждённое основание/u);
  assert.match(panel, /founder_statement/u);
  assert.match(panel, /public_benchmark/u);
  assert.match(panel, /ai_scenario/u);
  assert.match(panel, /data-case-copilot-research-status/u);
  assert.match(panel, /buildCaseCopilotResearchJobPresentation/u);
  assert.match(panel, /providerStatus=\{providerStatus\}/u);
  assert.match(panel, /не становятся фактами автоматически/u);
  assert.match(panel, /Изменённых метрик/u);
  assert.match(panel, /Публичных источников/u);
  assert.match(panel, /Сохранённых ссылок на источники/u);
  assert.match(panel, /Изменённые блоки/u);
  assert.match(panel, /После публичного поиска метрики не изменились/u);
  assert.match(panel, /presentPublicBenchmarkEntry/u);
  assert.match(panel, /presentation\.validationPlan/u);
  assert.match(panel, /presentation\.sourceUrl/u);
  assert.match(panel, /function formatManualOnlyKeys/u);
  assert.match(panel, /formatManualOnlyKeys\(researchPlan\.manual_only_keys\)/u);
  assert.doesNotMatch(panel, /manual_only_keys\.map\(fieldLabel\)\.join/u);
  assert.match(panel, /публичные ориентиры/iu);
  assert.match(panel, /внешние рыночные ориентиры/u);
  assert.doesNotMatch(panel, /публичный benchmark|benchmark добавлен|benchmark\.|benchmark,/u);
  assert.match(questionCard, /selectedAnswerType === "manual"/u);
  assert.match(questionCard, /selectedAnswerType === "file"/u);
  assert.match(questionCard, /selectedAnswerType === "public_research"/u);
  assert.match(questionCard, /selectedAnswerType === "skip"/u);
  assert.match(questionCard, /consentPublicResearch/u);
  assert.match(questionCard, /validationErrors/u);
  assert.match(questionCard, /if \(saved\) \{\s*setManualAmount\(""\)/u);
  assert.match(questionCard, /Ответить «не знаю»/u);
  assert.match(casePresentation, /внешние рыночные ориентиры/u);
  assert.match(casePresentation, /расход денег, остаток денег/u);
  assert.match(questionCard, /function selectAnswerType\(nextAnswerType: CaseQuestionAnswerType\)/u);
  assert.match(questionCard, /setLocalError\(null\);\s*setAnswerType\(nextAnswerType\);/u);
  assert.match(questionCard, /function setPublicResearchConsent\(enabled: boolean\)/u);
  assert.match(questionCard, /setConsentedResearchScope\(enabled \? researchConsentScope : null\);/u);
  assert.match(questionCard, /function primaryButtonLabel\(\): string/u);
  assert.match(questionCard, /presentPublicResearchPreRunCopy\(providerStatus\)/u);
  assert.match(casePresentation, /deterministic_offline_fixture/u);
  assert.match(casePresentation, /интернет-запроса не будет/u);
  assert.match(casePresentation, /configured:\s*\{/u);
  assert.match(casePresentation, /Live-поиск по публичному интернету/u);
  assert.match(casePresentation, /Live-провайдер публичного поиска не настроен/u);
  assert.match(questionCard, /setLocalError\(publicResearchStartError\);/u);
  assert.match(questionCard, /selectedAnswerType === "public_research" && busy/u);
  assert.match(questionCard, /publicResearchModeCopy\.busyDescription/u);
  assert.doesNotMatch(questionCard, /benchmark-ориентиры|benchmark/u);
  assert.doesNotMatch(questionCard, /burn, cash/u);
  assert.doesNotMatch(questionCard, /Сохранить как факт/u);
  assert.match(
    readFileSync(new URL("../../../scripts/capture_founder_screenshots.mjs", import.meta.url), "utf8"),
    /buttonByTextInCasePanel\(currentCaseId,[\s\S]*"case_copilot_save_unknown"\)/u,
  );
  assert.doesNotMatch(questionCard, /catch\s*\{[\s\S]*setManualAmount\(""\)/u);
  assert.doesNotMatch(scenarioMetrics, /describeScenarioMetricDisclosure/u);
  assert.match(scenarioMetrics, /Покрытие фактами/u);
  assert.match(scenarioMetrics, /Полнота сценария/u);
  assert.match(scenarioMetrics, /presentScenarioMetric/u);
  assert.match(scenarioMetrics, /formatCoverage/u);
  assert.match(scenarioMetrics, /formatScenario/u);
  assert.match(scenarioMetrics, /presentation\.validationPlan/u);
  assert.match(scenarioMetrics, /presentation\.confirmationGuidance/u);
  assert.match(scenarioMetrics, /presentation\.dependencies/u);
  assert.match(scenarioMetrics, /presentation\.sourceReferences/u);
  assert.match(scenarioMetrics, /Как рассчитано и проверить/u);
  assert.match(panelCss, /@media\s*\(max-width:\s*100rem\)/u);
  assert.doesNotMatch(panelCss, /:global\(\.founder-dashboard-shell\)/u);
  assert.match(panelCss, /@media\s*\(max-width:\s*100rem\)[\s\S]*?\.shellWithCopilot\s*\{[\s\S]*?grid-template-columns:\s*var\(--fi-sidebar-width\) minmax\(0,\s*1fr\);/u);
  assert.match(panelCss, /\.panel\s*\{[\s\S]*?inline-size:\s*100%;/u);
  assert.match(panelCss, /@media\s*\(max-width:\s*100rem\)[\s\S]*?\.panel\s*\{[\s\S]*?width:\s*min\(420px,\s*calc\(100vw - 32px\)\);/u);
  assert.match(panelCss, /\.researchStatus\s+article\s*>\s*small\s*\{[\s\S]*?display:\s*block;[\s\S]*?margin-block-start:\s*0\.35rem;/u);
  assert.match(panelCss, /\.modeBlock\s*>\s*small\s*\{[\s\S]*?grid-column:\s*2\s*\/\s*-1;/u);
  assert.match(panel, /open \? styles\.panelOpen : styles\.panelClosed/u);
  assert.match(panelCss, /\.shellCopilotClosed\s*\{[\s\S]*?grid-template-columns:\s*var\(--fi-sidebar-width\) minmax\(0,\s*1fr\);[\s\S]*?padding-right:\s*8px;/u);
  assert.match(panelCss, /@media\s*\(min-width:\s*64rem\)[\s\S]*?\.shellCopilotClosed\s*\{[\s\S]*?padding-right:\s*76px;/u);
  assert.match(panelCss, /\.panelClosed\s*\{[\s\S]*?display:\s*grid;[\s\S]*?overflow:\s*hidden;[\s\S]*?position:\s*fixed;[\s\S]*?right:\s*16px;[\s\S]*?top:\s*16px;[\s\S]*?width:\s*52px;/u);
  assert.match(panelCss, /\.panelClosed\s*>\s*:not\(\.panelHeader\)\s*\{[\s\S]*?display:\s*none;/u);
  assert.match(panelCss, /\.panelClosed\s+\.panelHeader\s*\{[\s\S]*?grid-template-columns:\s*1fr;[\s\S]*?place-items:\s*center;/u);
  assert.match(panelCss, /\.panelClosed\s+\.panelHeader\s+div\s*\{[\s\S]*?display:\s*none;/u);
  assert.match(panelCss, /\.panelClosed\s+\.panelHeader\s+button\s*\{[\s\S]*?justify-self:\s*center;/u);
  assert.doesNotMatch(panelCss, /\.rail\s*\{/u);
  assert.doesNotMatch(panelCss, /\.drawer\s*\{/u);
});

test("wires Case Copilot context, safe case name, action availability, and validation errors", () => {
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const orchestrator = readFileSync(
    new URL("./founder-workspace-orchestrator.ts", import.meta.url),
    "utf8",
  );
  const panel = readFileSync(
    new URL("./case-copilot-panel.tsx", import.meta.url),
    "utf8",
  );
  const questionCard = readFileSync(
    new URL("./case-question-card.tsx", import.meta.url),
    "utf8",
  );

  assert.match(orchestrator, /copilotValidationErrors:\s*readonly CaseMutationFieldError\[\]/u);
  assert.match(orchestrator, /validationErrorsFrom\(error\)/u);
  assert.match(controller, /copilotValidationErrors:\s*snapshot\?\.copilotValidationErrors \?\? \[\]/u);
  assert.match(shell, /function founderSafeCaseName/u);
  assert.match(shell, /workspace\?\.profile\?\.fields\.startup_name\.values\[0\]/u);
  assert.match(shell, /caseCopilotContext/u);
  assert.match(shell, /focusKey:\s*activeView/u);
  assert.match(shell, /const safeCaseName = founderSafeCaseName\(workspace\)/u);
  assert.match(shell, /caseName=\{safeCaseName\}/u);
  assert.match(shell, /validationErrors=\{workspace\?\.copilotValidationErrors \?\? \[\]\}/u);
  assert.match(shell, /contextFocus=\{caseCopilotContext\}/u);
  assert.match(panel, /caseName\?:\s*string/u);
  assert.match(panel, /contextFocus\?:\s*CaseCopilotContextFocus/u);
  assert.match(panel, /validationErrors\?:\s*readonly CaseMutationFieldError\[\]/u);
  assert.match(panel, /<strong>\{caseName \?\? "Проект после анализа"\}<\/strong>/u);
  assert.match(panel, /data-case-copilot-context/u);
  assert.match(panel, /validationErrors=\{validationErrors\}/u);
  assert.match(panel, /canSubmitFact=\{Boolean\(onAssumptionSubmit\)\}/u);
  assert.match(panel, /canPrepareResearch=\{Boolean\(onResearchPrepare\)\}/u);
  assert.match(panel, /canSubmitUnknown=\{Boolean\(onUnknownSubmit\)\}/u);
  assert.match(questionCard, /canRequestDocument/u);
  assert.match(questionCard, /const answerModes = useMemo/u);
  assert.match(questionCard, /canSubmitFactProp && factAction/u);
  assert.match(questionCard, /canPrepareResearchProp && researchAction/u);
  assert.match(questionCard, /canSubmitUnknown/u);
  assert.match(questionCard, /selectedAnswerType === "file" && !canRequestDocument/u);
  assert.match(questionCard, /selectedAnswerType === "skip" && !canSubmitUnknown/u);
  assert.match(questionCard, /documentUnavailableReason/u);
  assert.match(questionCard, /researchUnavailableReason/u);
  assert.match(questionCard, /skipUnavailableReason/u);
  assert.doesNotMatch(questionCard, /\(\["manual", "file", "public_research", "skip"\] as const\)\.map/u);
  assert.doesNotMatch(questionCard, /onDocumentRequested\?\.\(\);\s*return;/u);
});

test("shows a real Case Copilot recovery action when no answer action is available", () => {
  const questionCard = readFileSync(
    new URL("./case-question-card.tsx", import.meta.url),
    "utf8",
  );

  assert.match(questionCard, /presentCaseCopilotNoActionState/u);
  assert.match(questionCard, /data-case-copilot-no-action/u);
  assert.match(questionCard, /noActionState\.recoveryText/u);
  assert.match(questionCard, /noActionState\.recoveryLabel/u);
  assert.match(questionCard, /onClick=\{onDocumentRequested\}/u);
  assert.doesNotMatch(
    questionCard,
    /<div className=\{styles\.answerTabs\} role="tablist" aria-label="Способ ответа">[\s\S]*?\{modeTabs\.map/u,
  );
});

test("derives Case Copilot answer modes from canonical actions and real callbacks", () => {
  const modes = deriveCaseCopilotAnswerModes({
    actions: [
      copilotAction("open_fact_input", "requires_input", {
        field_key: "mrr",
        provenance: "founder_statement",
      }),
      copilotAction("open_document_upload", "blocked", { case_id: caseId }, "Backend upload is blocked."),
    ],
    canPrepareResearch: false,
    canSubmitFact: true,
    canSubmitUnknown: false,
    consentPublicResearch: false,
    hasDocumentHandler: true,
    manualDraft: "MRR is 1.4-2.0m KZT/month",
  });

  assert.deepEqual(modes.map((mode) => [mode.type, mode.enabled, mode.reason]), [
    ["manual", true, "Need a founder statement or source fact."],
    ["file", false, "Backend upload is blocked."],
  ]);

  assert.deepEqual(
    deriveCaseCopilotAnswerModes({
      actions: [],
      canPrepareResearch: false,
      canSubmitFact: false,
      canSubmitUnknown: false,
      consentPublicResearch: false,
      hasDocumentHandler: false,
      manualDraft: "",
    }),
    [],
  );
  assert.deepEqual(
    deriveCaseCopilotAnswerModes({
      actions: [],
      canPrepareResearch: false,
      canSubmitFact: false,
      canSubmitUnknown: false,
      consentPublicResearch: false,
      hasDocumentHandler: true,
      manualDraft: "",
    }),
    [],
  );
  assert.deepEqual(
    deriveCaseCopilotAnswerModes({
      actions: [],
      canPrepareResearch: false,
      canSubmitFact: false,
      canSubmitUnknown: true,
      consentPublicResearch: false,
      hasDocumentHandler: false,
      manualDraft: "",
    }),
    [],
  );
  assert.deepEqual(
    deriveCaseCopilotAnswerModes({
      actions: [
        copilotAction("open_fact_input", "blocked", {
          field_key: "mrr",
          provenance: "founder_statement",
        }, "Backend fact intake is blocked."),
      ],
      canPrepareResearch: false,
      canSubmitFact: false,
      canSubmitUnknown: true,
      consentPublicResearch: false,
      hasDocumentHandler: false,
      manualDraft: "",
    }),
    [],
  );
  assert.deepEqual(
    deriveCaseCopilotAnswerModes({
      actions: [
        copilotAction("open_fact_input", "requires_input", {
          field_key: "mrr",
          provenance: "founder_statement",
        }),
      ],
      canPrepareResearch: false,
      canSubmitFact: false,
      canSubmitUnknown: true,
      consentPublicResearch: false,
      hasDocumentHandler: false,
      manualDraft: "",
    }).map((mode) => [mode.type, mode.enabled, mode.reason]),
    [["skip", true, "Unknown will be sent as a Copilot thread reply, not saved as source_fact or a founder assumption."]],
  );
  assert.equal(selectCaseCopilotAnswerType([], "manual"), null);
});

test("builds public research submissions from the public action focus and expected revision", () => {
  const payload = buildCaseCopilotSubmitPayload({
    actions: [
      copilotAction("open_fact_input", "requires_input", {
        field_key: "mrr",
        provenance: "founder_statement",
      }),
      copilotAction("prepare_public_research", "requires_consent", {
        focus: "public_pricing_analogs",
        expected_case_revision: 4,
      }),
    ],
    answerType: "public_research",
    consentPublicResearch: true,
    manualDraft: "should not leak into public research",
  });

  assert.deepEqual(payload, {
    answerType: "public_research",
    fieldKey: "public_pricing_analogs",
    manualValue: "unknown",
    consentPublicResearch: true,
    expectedCaseRevision: 4,
  });
});

test("explains public research failure without framing it as answer saving", () => {
  assert.equal(
    caseCopilotSubmitFailureMessage("public_research"),
    "Публичный поиск не удалось запустить. Посмотрите показанную причину и повторите запуск безопасно.",
  );
  assert.equal(
    caseCopilotSubmitFailureMessage("manual"),
    "Не удалось сохранить ответ. Проверьте поле и попробуйте ещё раз.",
  );
});

test("derives Case Copilot public research consent scope from case focus and revision", () => {
  const action = copilotAction("prepare_public_research", "requires_consent", {
    focus: "public_pricing_analogs",
    expected_case_revision: 4,
  });

  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: action,
    }),
    "case-founder-001:public_pricing_analogs:4",
  );
  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: action,
    }),
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: action,
    }),
  );
  assert.notEqual(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-002",
      researchAction: action,
    }),
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: action,
    }),
  );
  assert.notEqual(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: copilotAction("prepare_public_research", "requires_consent", {
        focus: "tam_research",
        expected_case_revision: 4,
      }),
    }),
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: action,
    }),
  );
  assert.notEqual(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: copilotAction("prepare_public_research", "requires_consent", {
        focus: "public_pricing_analogs",
        expected_case_revision: 5,
      }),
    }),
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: action,
    }),
  );
  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: null,
      researchAction: action,
    }),
    null,
  );
  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: copilotAction("open_fact_input", "requires_input", {
        field_key: "mrr",
      }),
    }),
    null,
  );
  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: copilotAction("prepare_public_research", "requires_consent", {
        focus: "",
        expected_case_revision: 4,
      }),
    }),
    null,
  );
  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: copilotAction("prepare_public_research", "requires_consent", {
        focus: "public_pricing_analogs",
      }),
    }),
    null,
  );
  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: copilotAction("prepare_public_research", "available", {
        focus: "public_pricing_analogs",
        expected_case_revision: 4,
      }),
    }),
    null,
  );
  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: copilotAction("prepare_public_research", "requires_consent", {
        focus: "public_pricing_analogs",
        expected_case_revision: 0,
      }),
    }),
    null,
  );
  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: copilotAction("prepare_public_research", "requires_consent", {
        focus: "public_pricing_analogs",
        expected_case_revision: 4.5,
      }),
    }),
    null,
  );
  assert.equal(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: copilotAction("prepare_public_research", "requires_consent", {
        focus: "public_pricing_analogs",
        expected_case_revision: Number.NaN,
      }),
    }),
    null,
  );
});

test("shows a specific busy activity and blocks duplicate advisor actions", async () => {
  const snapshots: FounderWorkspaceSnapshot[] = [];
  let answerCalls = 0;
  let decisionCalls = 0;
  let retryReads = 0;
  let holdAnswerImprovements = false;
  let holdRetryRefresh = false;
  let releaseAnswer!: (response: AdvisorAnswerResponse) => void;
  let releaseAnswerImprovements!: (response: AdvisorImprovementsResponse) => void;
  let releaseDecision!: (response: AdvisorImprovementDecisionResponse) => void;
  let releaseRetry!: (response: AdvisorNextQuestionResponse) => void;
  const pendingAnswer = new Promise<AdvisorAnswerResponse>((resolve) => {
    releaseAnswer = resolve;
  });
  const pendingAnswerImprovements = new Promise<AdvisorImprovementsResponse>((resolve) => {
    releaseAnswerImprovements = resolve;
  });
  const pendingDecision = new Promise<AdvisorImprovementDecisionResponse>((resolve) => {
    releaseDecision = resolve;
  });
  const pendingRetry = new Promise<AdvisorNextQuestionResponse>((resolve) => {
    releaseRetry = resolve;
  });
  const firstProposalId = advisorImprovements.proposals[0]?.proposal_id ?? "";
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => reportStatus,
      getAdvisorNextQuestion: async () => {
        retryReads += 1;
        return holdRetryRefresh ? pendingRetry : advisorQuestion;
      },
      submitAdvisorAnswer: async () => {
        answerCalls += 1;
        return pendingAnswer;
      },
      getAdvisorImprovements: async () =>
        holdAnswerImprovements ? pendingAnswerImprovements : advisorImprovements,
      decideAdvisorImprovement: async (_id, proposalId, decisionValue) => {
        decisionCalls += 1;
        return pendingDecision.then(() => ({
          case_id: caseId,
          proposal_id: proposalId,
          decision: decisionValue,
          previous_version: 6,
          new_version: 7,
          changed_fields: ["positioning"],
          recalculation_status: "started",
          recalculation_data_revision: 2,
          recalculation_analysis_status: "gate2_preview_ready",
        }));
      },
    }),
    onChange: (snapshot) => snapshots.push(snapshot),
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  const answer = orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Операционные директора в компаниях 100-300 сотрудников.",
    document_id: null,
    consent_public_research: false,
  });
  await Promise.resolve();
  await orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Повторный клик",
    document_id: null,
    consent_public_research: false,
  });
  assert.equal(answerCalls, 1);
  assert.equal(latest(snapshots).activity, "advisor_answering");
  holdAnswerImprovements = true;
  releaseAnswer(advisorAnswer);
  await Promise.resolve();
  await orchestrator.answerAdvisor({
    question_id: `${caseId}:icp`,
    answer_type: "manual",
    value: "Повторный клик во время обновления рекомендаций",
    document_id: null,
    consent_public_research: false,
  });
  assert.equal(answerCalls, 1);
  assert.equal(latest(snapshots).activity, "advisor_answering");
  releaseAnswerImprovements(advisorImprovements);
  await answer;

  holdRetryRefresh = true;
  const retry = orchestrator.retryAdvisor();
  await Promise.resolve();
  await orchestrator.retryAdvisor();
  assert.equal(retryReads, 3);
  assert.equal(latest(snapshots).activity, "advisor_refreshing");
  releaseRetry(advisorQuestion);
  await retry;

  const decision = orchestrator.decideAdvisorImprovement(firstProposalId, "accepted");
  await Promise.resolve();
  await orchestrator.decideAdvisorImprovement(firstProposalId, "accepted");
  assert.equal(decisionCalls, 1);
  assert.equal(latest(snapshots).activity, "advisor_deciding");
  releaseDecision({
    case_id: caseId,
    proposal_id: firstProposalId,
    decision: "accepted",
    previous_version: 6,
    new_version: 7,
    changed_fields: ["positioning"],
    recalculation_status: "started",
    recalculation_data_revision: 2,
    recalculation_analysis_status: "gate2_preview_ready",
  });
  await decision;
  assert.equal(orchestrator.getSnapshot().busy, false);
  assert.equal(orchestrator.getSnapshot().activity, null);
});

test("wires Case Copilot public research consent to the current case scope", () => {
  const panel = readFileSync(
    new URL("./case-copilot-panel.tsx", import.meta.url),
    "utf8",
  );
  const questionCard = readFileSync(
    new URL("./case-question-card.tsx", import.meta.url),
    "utf8",
  );

  assert.match(panel, /caseId=\{caseId\}/u);
  assert.match(questionCard, /caseId:\s*string \| null/u);
  assert.match(questionCard, /deriveCaseCopilotResearchConsentScope/u);
  assert.match(questionCard, /consentedResearchScope/u);
  assert.doesNotMatch(questionCard, /useState\(false\)/u);
  assert.match(questionCard, /consentPublicResearch\s*=\s*researchConsentScope !== null &&\s*consentedResearchScope === researchConsentScope/u);
  assert.match(questionCard, /onChange=\{\(event\) => setPublicResearchConsent\(event\.target\.checked\)\}/u);
  assert.match(questionCard, /setConsentedResearchScope\(null\)/u);
  assert.match(panel, /aria-busy=\{busy\}/u);
  assert.match(questionCard, /data-case-question-consent="public_research"/u);
  assert.match(questionCard, /data-case-question-submit=\{selectedAnswerType \?\? undefined\}/u);
});

test("defaults Case Copilot public research to live mode from capabilities instead of initial offline state", () => {
  const questionCard = readFileSync(
    new URL("./case-question-card.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    questionCard,
    /useState<RequestedResearchAcquisitionMode \| null>\(null\)/u,
  );
  assert.match(
    questionCard,
    /selectedResearchAcquisitionMode &&\s*researchModeChoices\.some\(\(choice\) => choice\.mode === selectedResearchAcquisitionMode && choice\.available\)\s*\?\s*selectedResearchAcquisitionMode\s*:\s*defaultCaseCopilotPublicResearchMode\(researchAction\)/u,
  );
  assert.match(questionCard, /aria-checked=\{effectiveResearchAcquisitionMode === choice\.mode\}/u);
  assert.match(questionCard, /publicResearchModeCopy\.consentLabel/u);
  assert.match(questionCard, /acquisitionMode:\s*effectiveResearchAcquisitionMode/u);
});

test("keeps unavailable online research reason visible and accessible when offline is selected", () => {
  const questionCard = readFileSync(
    new URL("./case-question-card.tsx", import.meta.url),
    "utf8",
  );

  assert.match(questionCard, /data-case-question-research-disabled-reason=\{choice\.mode\}/u);
  assert.match(questionCard, /choice\.disabledReason \? \(/u);
  assert.doesNotMatch(
    questionCard,
    /<small\s+hidden=\{effectiveResearchAcquisitionMode !== choice\.mode\}[\s\S]*?\{choice\.disabledReason \?\? choice\.description\}/u,
  );
});

test("shows the selected public research mode description only once", () => {
  const questionCard = readFileSync(
    new URL("./case-question-card.tsx", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(
    questionCard,
    /<span>\{publicResearchModeCopy\.description\}<\/span>/u,
  );
  assert.match(
    questionCard,
    /hidden=\{effectiveResearchAcquisitionMode !== choice\.mode\}[\s\S]*?\{choice\.description\}/u,
  );
});

test("uses owner-selected research acquisition mode for busy copy instead of provider status", () => {
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const orchestrator = readFileSync(
    new URL("./founder-workspace-orchestrator.ts", import.meta.url),
    "utf8",
  );

  assert.match(controller, /researchBusyLabelByAcquisitionMode/u);
  assert.doesNotMatch(controller, /researchBusyLabelByProviderStatus/u);
  assert.match(
    controller,
    /busyLabel:\s*founderBusyLabel\(\s*snapshot\?\.activity \?\? null,\s*snapshot\?\.activeResearchAcquisitionMode \?\? null,\s*\)/u,
  );
  assert.match(orchestrator, /activeResearchAcquisitionMode:\s*RequestedResearchAcquisitionMode \| null/u);
  assert.match(orchestrator, /activeResearchAcquisitionMode:\s*request\.acquisitionMode/u);
});

test("combines live public research with the fresh Gate 2 decision created by its new revision", () => {
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    controller,
    /if \(\s*input\.acquisitionMode === "live_public_research" \|\|\s*instance\.getSnapshot\(\)\.display\.stage === "gate2_preview_ready"\s*\) \{\s*await instance\.launchCopilotResearchAndApproveGate2\(request\);/u,
  );
  assert.match(
    controller,
    /else \{\s*await instance\.prepareCopilotResearch\(request\);/u,
  );
});

test("builds structured Case Copilot manual assumptions without source_fact promotion", () => {
  const request = buildCaseCopilotManualAssumptionRequest({
    amount: "1850000",
    currency: "KZT",
    declaredSource: "founder interview",
    expectedRevision: 4,
    fieldKey: "mrr",
    periodMonth: "2026-07",
    rationale: "planning input",
    scale: "ones",
    validationPlan: "verify against CRM/finance",
  });

  assert.deepEqual(request, {
    requirement_key: "mrr",
    value: {
      kind: "money",
      amount: "1850000",
      scale: "ones",
      currency: "KZT",
    },
    period: {
      kind: "month",
      value: "2026-07",
      start: null,
      end: null,
    },
    source: {
      kind: "founder_statement",
      declared_source: "founder interview",
      evidence_ref: null,
    },
    rationale: "planning input",
    validation_plan: "verify against CRM/finance",
    expected_case_revision: 4,
    idempotency_key: "copilot-assumption:mrr:rev:4",
  });
  assert.notEqual(request.source.kind, "source_fact");
});

test("routes manual Case Copilot intake through assumptions while preserving explicit facts", () => {
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const shell = readFileSync(
    new URL("./founder-shell.tsx", import.meta.url),
    "utf8",
  );
  const panel = readFileSync(
    new URL("./case-copilot-panel.tsx", import.meta.url),
    "utf8",
  );
  const questionCard = readFileSync(
    new URL("./case-question-card.tsx", import.meta.url),
    "utf8",
  );

  assert.match(controller, /async function saveCaseCopilotAssumption/u);
  assert.match(controller, /buildCaseCopilotManualAssumptionRequest\(/u);
  assert.match(controller, /submitCopilotAssumption\(/u);
  assert.match(controller, /idempotency_key:\s*`copilot-assumption:\$\{input\.fieldKey\}:rev:\$\{expectedRevision\}`/u);
  assert.match(controller, /saveCaseCopilotFact/u);
  assert.match(controller, /submitCopilotFact\(/u);
  assert.match(controller, /onCopilotAssumptionSubmit=\{saveCaseCopilotAssumption\}/u);
  assert.match(shell, /onCopilotAssumptionSubmit\?:/u);
  assert.match(shell, /onAssumptionSubmit=\{onCopilotAssumptionSubmit\}/u);
  assert.match(panel, /onAssumptionSubmit\?:/u);
  assert.match(
    panel,
    /if \(input\.answerType === "manual"\) \{\s*return Boolean\(await onAssumptionSubmit\?\.\(input\)\);\s*\}\s*return Boolean\(await onFactSubmit\?\.\(input\)\);/u,
  );
  assert.match(questionCard, /data-case-copilot-manual-amount/u);
  assert.match(questionCard, /data-case-copilot-manual-scale/u);
  assert.match(questionCard, /data-case-copilot-manual-currency/u);
  assert.match(questionCard, /data-case-copilot-manual-period/u);
  assert.match(questionCard, /data-case-copilot-manual-source/u);
  assert.match(questionCard, /data-case-copilot-manual-rationale/u);
  assert.match(questionCard, /data-case-copilot-manual-validation-plan/u);
  assert.match(questionCard, /factFieldKey/u);
  assert.match(questionCard, /Структурированный ответ основателя/u);
  assert.match(questionCard, /data-case-copilot-manual-field-key/u);
  assert.doesNotMatch(questionCard, /<textarea[\s\S]*manualDraft/u);
});

test("renders Case Copilot manual fields from backend question input schema", () => {
  const questionCard = readFileSync(
    new URL("./case-question-card.tsx", import.meta.url),
    "utf8",
  );

  assert.match(questionCard, /presentCaseCopilotQuestionInputSchema/u);
  assert.match(questionCard, /questionInputSchema\?\.fields\.map/u);
  assert.match(questionCard, /answerValueField\?\.label/u);
  assert.match(questionCard, /answerValueField\?\.placeholder/u);
  assert.match(questionCard, /requiredLabel/u);
  assert.match(questionCard, /periodField \?/u);
  assert.doesNotMatch(questionCard, /manualInputKind === "money" \? \(/u);
  assert.match(questionCard, /questionInputSchema\.unlocksCopy/u);
});

test("reads the latest orchestrator revision before Case Copilot mutations", () => {
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    controller,
    /const liveSnapshot = orchestrator\.current\?\.getSnapshot\(\) \?\? snapshot;/u,
  );
  assert.match(
    controller,
    /return liveSnapshot\?\.copilotState\?\.data_revision \?\? liveSnapshot\?\.profile\?\.data_revision \?\? null;/u,
  );
  assert.doesNotMatch(
    controller,
    /return snapshot\?\.copilotState\?\.data_revision \?\? snapshot\?\.profile\?\.data_revision \?\? null;/u,
  );
});

test("builds deterministic Case Copilot unknown message requests for controller routing", async () => {
  const presentation = await import("../lib/case-copilot-presentation.ts");

  assert.equal(typeof presentation.buildCaseCopilotUnknownMessageRequest, "function");
  assert.deepEqual(
    presentation.buildCaseCopilotUnknownMessageRequest({
      fieldKey: "mrr",
      expectedRevision: 4,
    }),
    {
      message: "unknown",
      page_context: "case-copilot",
      current_section: "scenario-question",
      expected_case_revision: 4,
      focus_key: "mrr",
      idempotency_key: "copilot-unknown:mrr:rev:4",
    },
  );
});

test("queues consented Case Copilot public research and refreshes scenarios after plan preparation", async () => {
  const calls: string[] = [];
  let researchDone = false;
  const plan = researchPlanResponse();
  const job = researchJobResponse({ data_revision: 5 });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () =>
        researchDone
          ? scenarioProjectionWithMrrRange(5, { lower: "1800000", upper: "2600000" })
          : scenarioProjectionWithMrrRange(4, { lower: "1400000", upper: "2000000" }),
      prepareResearchPlan: async (_activeCaseId, request) => {
        calls.push(`prepare:${request.focus}:${request.expected_case_revision}`);
        assert.equal(calls.includes("queue"), false);
        return plan;
      },
      queueResearchJob: async (_activeCaseId, request) => {
        calls.push("queue");
        assert.equal(request.plan_id, plan.plan_id);
        assert.equal(request.plan_hash, plan.plan_hash);
        assert.equal(request.expected_case_revision, plan.data_revision);
        assert.equal(request.consent_public_research, true);
        assert.equal(request.retry_of_job_id, null);
        assert.equal(request.acquisition_mode, "live_public_research");
        assert.match(request.idempotency_key, /^copilot-research:live_public_research:public_pricing_analogs:/u);
        researchDone = true;
        return job;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.deepEqual(calls, ["prepare:public_pricing_analogs:4", "queue"]);
  assert.equal(snapshot.researchPlan?.plan_id, plan.plan_id);
  assert.equal(snapshot.researchJob?.status, "completed");
  assert.deepEqual(snapshot.researchJob?.citations, ["https://example.com/public-benchmark"]);
  assert.equal(snapshot.scenarios?.data_revision, 5);
  assert.deepEqual(snapshot.researchMetricComparison, {
    scenarioKey: "base",
    oldRevision: 4,
    newRevision: 5,
    changedMetrics: [
      {
        metricKey: "mrr",
        oldValue: {
          valueRange: { lower: "1400000", upper: "2000000" },
          unit: "KZT/month",
          gaps: [],
        },
        newValue: {
          valueRange: { lower: "1800000", upper: "2600000" },
          unit: "KZT/month",
          gaps: [],
        },
      },
    ],
  });
});

test("launches selected research and approves fresh Gate 2 token in one owner operation", async () => {
  const calls: string[] = [];
  let researchDone = false;
  let gate2Approved = false;
  let markGate2Started!: () => void;
  let releaseGate2Decision!: () => void;
  const gate2Started = new Promise<void>((resolve) => {
    markGate2Started = resolve;
  });
  const gate2DecisionCanComplete = new Promise<void>((resolve) => {
    releaseGate2Decision = resolve;
  });
  const plan = researchPlanResponse();
  const job = researchJobResponse({ data_revision: 5 });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => {
        if (gate2Approved) {
          calls.push("refresh:gate3");
          return gate3Status;
        }
        calls.push(researchDone ? "refresh:gate2:5" : "refresh:gate2:4");
        return gate2Status;
      },
      getGate2Preview: async () => {
        calls.push(researchDone ? "preview:5" : "preview:4");
        return {
          ...gate2Preview,
          resume_token: researchDone ? "resume-token-revision-5" : "resume-token-revision-4",
        };
      },
      getStartupProfile: async () => ({
        ...startupProfile,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () =>
        researchDone
          ? scenarioProjectionWithMrrRange(5, { lower: "1800000", upper: "2600000" })
          : scenarioProjectionWithMrrRange(4, { lower: "1400000", upper: "2000000" }),
      prepareResearchPlan: async (_activeCaseId, request) => {
        calls.push(`prepare:${request.expected_case_revision}`);
        return plan;
      },
      queueResearchJob: async (_activeCaseId, request) => {
        calls.push(`queue:${request.acquisition_mode}:${request.expected_case_revision}`);
        researchDone = true;
        return job;
      },
      decideGate2: async (_activeCaseId, request) => {
        calls.push(`gate2:${request.decision}:${request.resume_token}`);
        markGate2Started();
        await gate2DecisionCanComplete;
        gate2Approved = true;
        return decision(gate3Status);
      },
      decideGate3: async () => {
        calls.push("gate3");
        return decision(reportStatus);
      },
      decideGate4: async () => {
        calls.push("gate4");
        return decision(reportStatus);
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  calls.length = 0;
  const ownerOperation = orchestrator.launchCopilotResearchAndApproveGate2({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });
  await gate2Started;

  const whileGate2IsRunning = orchestrator.getSnapshot();
  assert.equal(whileGate2IsRunning.busy, true);
  assert.equal(whileGate2IsRunning.activity, "submitting_gate2_approved");

  releaseGate2Decision();
  await ownerOperation;

  assert.ifError(orchestrator.getSnapshot().error);
  assert.deepEqual(calls, [
    "prepare:4",
    "queue:live_public_research:4",
    "refresh:gate2:5",
    "preview:5",
    "preview:5",
    "gate2:approved:resume-token-revision-5",
    "refresh:gate3",
  ]);
  assert.equal(orchestrator.getSnapshot().display.stage, "gate3_review_required");
  assert.equal(calls.includes("gate3"), false);
  assert.equal(calls.includes("gate4"), false);
});

test("approves Gate 2 when live public research reuses a current cached result", async () => {
  const calls: string[] = [];
  let gate2Approved = false;
  const plan = researchPlanResponse();
  const cachedJob = researchJobResponse({
    data_revision: 4,
    old_revision: 4,
    new_revision: 4,
    reason: "cached_completed_research",
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => {
        if (gate2Approved) {
          calls.push("refresh:gate3");
          return { ...gate3Status, data_revision: 4 };
        }
        calls.push("refresh:gate2");
        return { ...gate2Status, data_revision: 4 };
      },
      getGate2Preview: async () => {
        calls.push("preview");
        return gate2Preview;
      },
      getStartupProfile: async () => ({ ...startupProfile, data_revision: 4 }),
      getCopilotState: async () =>
        copilotState({
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjection({ data_revision: 4 }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => cachedJob,
      decideGate2: async (_activeCaseId, request) => {
        calls.push(`gate2:${request.decision}:${request.resume_token}`);
        gate2Approved = true;
        return decision({ ...gate3Status, data_revision: 4 });
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  calls.length = 0;
  await orchestrator.launchCopilotResearchAndApproveGate2({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.equal(snapshot.display.stage, "gate3_review_required");
  assert.deepEqual(calls, [
    "refresh:gate2",
    "preview",
    "preview",
    "gate2:approved:resume-token-001",
    "refresh:gate3",
  ]);
});

test("does not reopen Gate 2 when cached live research is reused after Gate 2", async () => {
  const calls: string[] = [];
  const plan = researchPlanResponse();
  const cachedJob = researchJobResponse({
    data_revision: 4,
    old_revision: 4,
    new_revision: 4,
    reason: "cached_completed_research",
  });
  const completedStatus: StartupCaseStatus = {
    ...gate3Status,
    data_revision: 4,
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => {
        calls.push("refresh:completed");
        return completedStatus;
      },
      getGate2Preview: async () => {
        calls.push("unexpected:preview");
        throw new Error("completed case must not reopen Gate 2");
      },
      getStartupProfile: async () => ({ ...startupProfile, data_revision: 4 }),
      getCopilotState: async () => copilotState(),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjection({ data_revision: 4 }),
      prepareResearchPlan: async () => {
        calls.push("prepare");
        return plan;
      },
      queueResearchJob: async () => {
        calls.push("queue");
        return cachedJob;
      },
      decideGate2: async () => {
        calls.push("unexpected:gate2");
        throw new Error("completed case must not approve Gate 2 again");
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  calls.length = 0;
  await orchestrator.launchCopilotResearchAndApproveGate2({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.equal(snapshot.display.stage, "gate3_review_required");
  assert.deepEqual(calls, ["prepare", "queue", "refresh:completed"]);
});

test("does not approve Gate 2 when combined owner research has no useful result", async () => {
  const calls: string[] = [];
  const plan = researchPlanResponse();
  const partialWithoutSources = researchJobResponse({
    status: "partial",
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
    source_refs: [],
    old_revision: 4,
    new_revision: null,
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate2Status,
      getStartupProfile: async () => startupProfile,
      getCopilotState: async () =>
        copilotState({
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjection({ data_revision: 4 }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => partialWithoutSources,
      decideGate2: async () => {
        calls.push("gate2");
        return decision(gate3Status);
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.launchCopilotResearchAndApproveGate2({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.match(snapshot.error?.message ?? "", /не дал полезного результата/u);
  assert.equal(snapshot.display.stage, "gate2_preview_ready");
  assert.deepEqual(calls, []);
});

test("preserves the online research budget failure code for owner-facing recovery", async () => {
  const plan = researchPlanResponse();
  const budgetFailure = researchJobResponse({
    status: "failed",
    reason: "BUDGET_EXCEEDED",
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
    source_refs: [],
    old_revision: 4,
    new_revision: 4,
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => ({ ...gate2Status, data_revision: 4 }),
      getStartupProfile: async () => ({ ...startupProfile, data_revision: 4 }),
      getCopilotState: async () => copilotState(),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjection({ data_revision: 4 }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => budgetFailure,
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.launchCopilotResearchAndApproveGate2({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const error = orchestrator.getSnapshot().error as (Error & { code?: string }) | null;
  assert.equal(error?.code, "BUDGET_EXCEEDED");
  assert.match(error?.message ?? "", /Новый OpenAI-запрос не выполнен/u);
});

test("owner-facing combined research errors avoid Gate and token jargon", () => {
  const orchestrator = readFileSync(
    new URL("./founder-workspace-orchestrator.ts", import.meta.url),
    "utf8",
  );
  const noUsefulResult =
    /new Error\("Публичный поиск не дал полезного результата\.[^"]+"\)/u.exec(orchestrator)?.[0] ?? "";
  const noFreshVersion =
    /new Error\("Не удалось получить свежую версию данных[^"]+"\)/u.exec(orchestrator)?.[0] ?? "";

  assert.match(noUsefulResult, /Профиль не подтверждён/u);
  assert.match(noFreshVersion, /свежую версию данных/u);
  assert.doesNotMatch(`${noUsefulResult}\n${noFreshVersion}`, /Gate\s*\d|токен|token/u);
});

test("queues Case Copilot research with owner-selected mode in payload and idempotency", async () => {
  const calls: unknown[] = [];
  const plan = researchPlanResponse();
  const job = researchJobResponse({
    acquisition_mode: "deterministic_offline_fixture",
    status: "deferred",
    data_revision: 4,
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
    old_revision: 4,
    new_revision: null,
    source_refs: [],
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => startupProfile,
      getCopilotState: async () =>
        copilotState({
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: 4,
              available_acquisition_modes: [
                "live_public_research",
                "deterministic_offline_fixture",
              ],
              unavailable_acquisition_modes: [],
              default_acquisition_mode: "live_public_research",
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjection({ data_revision: 5 }),
      prepareResearchPlan: async (_activeCaseId, request) => {
        calls.push(["prepare", request]);
        return plan;
      },
      queueResearchJob: async (_activeCaseId, request) => {
        calls.push(["queue", request]);
        assert.equal(request.acquisition_mode, "deterministic_offline_fixture");
        assert.match(
          request.idempotency_key,
          /^copilot-research:deterministic_offline_fixture:public_pricing_analogs:/u,
        );
        return job;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "deterministic_offline_fixture",
  });

  assert.ifError(orchestrator.getSnapshot().error);
  assert.deepEqual(
    calls.map((call) => (Array.isArray(call) ? call[0] : null)),
    ["prepare", "queue"],
  );
  assert.equal(
    orchestrator.getSnapshot().researchJob?.acquisition_mode,
    "deterministic_offline_fixture",
  );
});

test("rejects live Case Copilot research responses that silently return offline fixture data", async () => {
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => startupProfile,
      getCopilotState: async () =>
        copilotState({
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjection({ data_revision: 4 }),
      prepareResearchPlan: async () => researchPlanResponse(),
      queueResearchJob: async () =>
        researchJobResponse({
          acquisition_mode: "deterministic_offline_fixture",
          status: "deferred",
          data_revision: 4,
          reason: "provider_unconfigured",
          accepted_entries: [],
          citations: [],
          changed_blocks: [],
          old_revision: 4,
          new_revision: null,
          source_refs: [],
        }),
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.match(snapshot.error?.message ?? "", /Research job acquisition mode mismatch/u);
  assert.equal(snapshot.researchJob, null);
});

test("rejects offline Case Copilot research responses that do not return the offline fixture mode", async () => {
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => startupProfile,
      getCopilotState: async () =>
        copilotState({
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: 4,
              available_acquisition_modes: [
                "live_public_research",
                "deterministic_offline_fixture",
              ],
              unavailable_acquisition_modes: [],
              default_acquisition_mode: "live_public_research",
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjection({ data_revision: 4 }),
      prepareResearchPlan: async () => researchPlanResponse(),
      queueResearchJob: async () =>
        researchJobResponse({
          acquisition_mode: "provider_unconfigured",
          status: "deferred",
          reason: "provider_unconfigured",
          accepted_entries: [],
          citations: [],
          changed_blocks: [],
          old_revision: 4,
          new_revision: null,
          source_refs: [],
        }),
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "deterministic_offline_fixture",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.match(snapshot.error?.message ?? "", /Research job acquisition mode mismatch/u);
  assert.equal(snapshot.researchJob, null);
});

test("prefetches comparison-only scenarios before live public research when scenarios are hidden", async () => {
  const calls: string[] = [];
  let researchDone = false;
  const plan = researchPlanResponse({ data_revision: 4 });
  const job = researchJobResponse({ data_revision: 5, old_revision: 4, new_revision: 5 });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          scenario_metrics: researchDone ? copilotState().scenario_metrics : [],
          accepted_inputs: researchDone
            ? [
                {
                  field_key: "monthly_price",
                  kind: "public_benchmark",
                  status: "accepted",
                  value: "45000-52000",
                  period: "month",
                  rationale: "Accepted external context.",
                  validation_plan: "Validate public source.",
                  declared_source: "public source",
                  source_refs: ["11111111-1111-4111-8111-111111111111"],
                },
              ]
            : [
                {
                  field_key: "source_fact",
                  kind: "source_fact",
                  status: "confirmed",
                  value: "Source-only coverage row",
                  period: null,
                  rationale: null,
                  validation_plan: null,
                  declared_source: null,
                  source_refs: [],
                },
              ],
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () => {
        if (researchDone) {
          calls.push("scenario:after:5");
          return scenarioProjectionWithMrrRange(5, { lower: "1800000", upper: "2600000" });
        }
        calls.push("scenario:before:4");
        return scenarioProjectionWithMrrRange(4, { lower: "1400000", upper: "2000000" });
      },
      prepareResearchPlan: async (_activeCaseId, request) => {
        calls.push(`prepare:${request.expected_case_revision}`);
        assert.equal(request.expected_case_revision, 4);
        return plan;
      },
      queueResearchJob: async (_activeCaseId, request) => {
        calls.push("queue");
        assert.equal(calls.at(-2), "scenario:before:4");
        assert.equal(request.expected_case_revision, 4);
        assert.equal(request.consent_public_research, true);
        researchDone = true;
        return job;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  assert.equal(orchestrator.getSnapshot().scenarios, null);

  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.deepEqual(calls, ["prepare:4", "scenario:before:4", "queue", "scenario:after:5"]);
  assert.equal(snapshot.scenarios?.data_revision, 5);
  assert.deepEqual(snapshot.researchMetricComparison, {
    scenarioKey: "base",
    oldRevision: 4,
    newRevision: 5,
    changedMetrics: [
      {
        metricKey: "mrr",
        oldValue: {
          valueRange: { lower: "1400000", upper: "2000000" },
          unit: "KZT/month",
          gaps: [],
        },
        newValue: {
          valueRange: { lower: "1800000", upper: "2600000" },
          unit: "KZT/month",
          gaps: [],
        },
      },
    ],
  });
});

test("loads source-status-only scenario projections after live research when backend materialized metrics", async () => {
  const calls: string[] = [];
  let researchDone = false;
  const plan = researchPlanResponse({ data_revision: 4 });
  const job = researchJobResponse({ data_revision: 5, old_revision: 4, new_revision: 5 });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          accepted_inputs: researchDone
            ? copilotSourceStatusRows()
            : [
                {
                  field_key: "monthly_price",
                  kind: "founder_statement",
                  status: "accepted",
                  value: "35000-40000",
                  period: "month",
                  rationale: "Founder statement.",
                  validation_plan: "Validate invoice data.",
                  declared_source: "founder",
                  source_refs: [],
                },
              ],
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () => {
        if (researchDone) {
          calls.push("scenario:after:5");
          return scenarioProjectionWithMrrRange(5, { lower: "1800000", upper: "2600000" });
        }
        calls.push("scenario:before:4");
        return scenarioProjectionWithMrrRange(4, { lower: "1400000", upper: "2000000" });
      },
      prepareResearchPlan: async (_activeCaseId, request) => {
        calls.push(`prepare:${request.expected_case_revision}`);
        assert.equal(request.expected_case_revision, 4);
        return plan;
      },
      queueResearchJob: async (_activeCaseId, request) => {
        calls.push("queue");
        assert.equal(request.expected_case_revision, 4);
        assert.equal(request.acquisition_mode, "live_public_research");
        researchDone = true;
        return job;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.deepEqual(calls, ["scenario:before:4", "prepare:4", "queue", "scenario:after:5"]);
  assert.equal(snapshot.scenarios?.data_revision, 5);
  assert.deepEqual(snapshot.researchMetricComparison, {
    scenarioKey: "base",
    oldRevision: 4,
    newRevision: 5,
    changedMetrics: [
      {
        metricKey: "mrr",
        oldValue: {
          valueRange: { lower: "1400000", upper: "2000000" },
          unit: "KZT/month",
          gaps: [],
        },
        newValue: {
          valueRange: { lower: "1800000", upper: "2600000" },
          unit: "KZT/month",
          gaps: [],
        },
      },
    ],
  });
});

test("retries a deferred Case Copilot research job with fresh consent and linked lineage", async () => {
  const calls: string[] = [];
  const plan = researchPlanResponse();
  const deferredJob = researchJobResponse({
    status: "deferred",
    reason: "provider_unconfigured",
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
    old_revision: 4,
    new_revision: 4,
    source_refs: [],
  });
  const completedRetry = researchJobResponse({
    job_id: "45454545-4545-4545-8545-454545454545",
    retry_of_job_id: deferredJob.job_id,
    data_revision: 5,
  } as Partial<ResearchJobResponse>);
  let researchDone = false;
  let queueCount = 0;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () =>
        researchDone
          ? scenarioProjectionWithMrrRange(5, { lower: "1800000", upper: "2600000" })
          : scenarioProjectionWithMrrRange(4, null),
      prepareResearchPlan: async (_activeCaseId, request) => {
        calls.push(`prepare:${request.expected_case_revision}`);
        return plan;
      },
      queueResearchJob: async (_activeCaseId, request) => {
        queueCount += 1;
        calls.push(`queue:${request.retry_of_job_id ?? "first"}`);
        assert.equal(request.consent_public_research, true);
        if (queueCount === 1) {
          assert.equal(request.retry_of_job_id, null);
          return deferredJob;
        }
        assert.equal(request.retry_of_job_id, deferredJob.job_id);
        assert.notEqual(
          request.idempotency_key,
          `copilot-research:${plan.focus}:${plan.plan_hash}`,
        );
        assert.match(request.idempotency_key, new RegExp(deferredJob.job_id, "u"));
        researchDone = true;
        return completedRetry;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.deepEqual(calls, [
    "prepare:4",
    "queue:first",
    "prepare:4",
    `queue:${deferredJob.job_id}`,
  ]);
  assert.equal(snapshot.researchJob?.job_id, completedRetry.job_id);
  assert.equal(snapshot.researchMetricComparison?.changedMetrics[0]?.oldValue.valueRange, null);
});

test("fetches a queued Case Copilot research job before refreshing scenarios", async () => {
  const calls: string[] = [];
  let researchDone = false;
  const plan = researchPlanResponse();
  const queuedJob = researchJobResponse({
    status: "queued",
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
    old_revision: null,
    new_revision: null,
  });
  const completedJob = researchJobResponse({ status: "completed", data_revision: 5 });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () =>
        scenarioProjection({ data_revision: researchDone ? 5 : 4 }),
      prepareResearchPlan: async (_activeCaseId, request) => {
        calls.push(`prepare:${request.expected_case_revision}`);
        return plan;
      },
      queueResearchJob: async () => {
        calls.push("queue");
        return queuedJob;
      },
      getResearchJob: async (_activeCaseId, jobId) => {
        calls.push(`get:${jobId}`);
        researchDone = true;
        return completedJob;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.deepEqual(calls, [
    "prepare:4",
    "queue",
    `get:${queuedJob.job_id}`,
  ]);
  assert.equal(snapshot.researchJob?.status, "completed");
  assert.equal(snapshot.scenarios?.data_revision, 5);
});

test("polls live Case Copilot research through visible search and recalculation stages", async () => {
  const calls: string[] = [];
  const activities: string[] = [];
  const scheduled: (() => void)[] = [];
  let researchDone = false;
  let fetchCount = 0;
  const plan = researchPlanResponse();
  const runningJob = researchJobResponse({
    status: "running",
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
    old_revision: null,
    new_revision: null,
  });
  const completedJob = researchJobResponse({ status: "completed", data_revision: 5 });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () =>
        researchDone
          ? scenarioProjectionWithMrrRange(5, { lower: "1800000", upper: "2600000" })
          : scenarioProjectionWithMrrRange(4, { lower: "1400000", upper: "2000000" }),
      prepareResearchPlan: async () => {
        calls.push("prepare");
        return plan;
      },
      queueResearchJob: async () => {
        calls.push("queue");
        return runningJob;
      },
      getResearchJob: async (_activeCaseId, jobId) => {
        calls.push(`get:${jobId}:${fetchCount}`);
        fetchCount += 1;
        if (fetchCount < 3) return runningJob;
        researchDone = true;
        return completedJob;
      },
    }),
    onChange: (snapshot) => {
      if (snapshot.activity) activities.push(snapshot.activity);
    },
    schedule: (callback) => {
      scheduled.push(callback);
      return () => undefined;
    },
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  const operation = orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });
  for (let index = 0; index < 6; index += 1) {
    await Promise.resolve();
    scheduled.shift()?.();
  }
  await operation;

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.deepEqual(calls, [
    "prepare",
    "queue",
    `get:${runningJob.job_id}:0`,
    `get:${runningJob.job_id}:1`,
    `get:${runningJob.job_id}:2`,
  ]);
  assert.ok(activities.includes("research_preparing"));
  assert.ok(activities.includes("research_searching"));
  assert.ok(activities.includes("research_recalculating"));
  assert.equal(snapshot.researchJob?.status, "completed");
  assert.equal(snapshot.researchMetricComparison?.changedMetrics.length, 1);
});

test("does not show recalculation or fake metric changes for deferred Case Copilot research", async () => {
  const activities: string[] = [];
  const plan = researchPlanResponse();
  const deferredJob = researchJobResponse({
    status: "deferred",
    reason: "provider_unconfigured",
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
    old_revision: 4,
    new_revision: null,
    source_refs: [],
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => startupProfile,
      getCopilotState: async () =>
        copilotState({
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjectionWithMrrRange(4, { lower: "1400000", upper: "2000000" }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => deferredJob,
    }),
    onChange: (snapshot) => {
      if (snapshot.activity) activities.push(snapshot.activity);
    },
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.equal(snapshot.busy, false);
  assert.equal(snapshot.researchJob?.status, "deferred");
  assert.equal(snapshot.researchMetricComparison, null);
  assert.ok(activities.includes("research_preparing"));
  assert.ok(activities.includes("research_searching"));
  assert.equal(activities.includes("research_recalculating"), false);
});

test("stops live Case Copilot research polling at the safe limit without hanging busy", async () => {
  const activities: string[] = [];
  let getCount = 0;
  const plan = researchPlanResponse();
  const runningJob = researchJobResponse({
    status: "running",
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
    old_revision: 4,
    new_revision: null,
    source_refs: [],
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => startupProfile,
      getCopilotState: async () =>
        copilotState({
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjectionWithMrrRange(4, { lower: "1400000", upper: "2000000" }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => runningJob,
      getResearchJob: async () => {
        getCount += 1;
        return runningJob;
      },
    }),
    onChange: (snapshot) => {
      if (snapshot.activity) activities.push(snapshot.activity);
    },
    schedule: (callback) => {
      queueMicrotask(callback);
      return () => undefined;
    },
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.equal(getCount, 8);
  assert.equal(snapshot.busy, false);
  assert.match(snapshot.error?.message ?? "", /безопасный лимит ожидания/u);
  assert.equal(snapshot.researchMetricComparison, null);
  assert.equal(activities.includes("research_recalculating"), false);
});

test("keeps zero-change Case Copilot research comparison explicit after recalculation", async () => {
  let researchDone = false;
  const plan = researchPlanResponse();
  const completedJob = researchJobResponse({ status: "completed", data_revision: 5 });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () =>
        scenarioProjectionWithMrrRange(
          researchDone ? 5 : 4,
          { lower: "1400000", upper: "2000000" },
        ),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => {
        researchDone = true;
        return completedJob;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ifError(snapshot.error);
  assert.equal(snapshot.busy, false);
  assert.equal(snapshot.researchJob?.status, "completed");
  assert.equal(snapshot.researchMetricComparison?.changedMetrics.length, 0);
});

test("cancels queued Case Copilot research polling on dispose", async () => {
  const scheduled: (() => void)[] = [];
  const cancellations: boolean[] = [];
  const plan = researchPlanResponse();
  const runningJob = researchJobResponse({
    status: "running",
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
    old_revision: 4,
    new_revision: null,
    source_refs: [],
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => startupProfile,
      getCopilotState: async () =>
        copilotState({
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjectionWithMrrRange(4, { lower: "1400000", upper: "2000000" }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => runningJob,
      getResearchJob: async () => runningJob,
    }),
    onChange: () => undefined,
    schedule: (callback) => {
      scheduled.push(callback);
      cancellations.push(false);
      const cancellationIndex = cancellations.length - 1;
      return () => {
        cancellations[cancellationIndex] = true;
      };
    },
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  const operation = orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });
  for (let index = 0; index < 4 && scheduled.length === 0; index += 1) {
    await Promise.resolve();
  }
  assert.equal(scheduled.length, 1);

  orchestrator.dispose();
  await operation;

  assert.deepEqual(cancellations, [true]);
});

test("rejects Case Copilot research jobs with inconsistent result revisions", async () => {
  let researchDone = false;
  const plan = researchPlanResponse();
  const badJob = researchJobResponse({ data_revision: 5, new_revision: 6 });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () => scenarioProjection({ data_revision: researchDone ? 5 : 4 }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => {
        researchDone = true;
        return badJob;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.match(snapshot.error?.message ?? "", /Research job lineage mismatch/u);
  assert.equal(snapshot.researchJob, null);
  assert.equal(snapshot.scenarios?.data_revision, 4);
});

test("rejects completed Case Copilot research jobs that advance without explicit new revision", async () => {
  let researchDone = false;
  const plan = researchPlanResponse();
  const badJob = researchJobResponse({ data_revision: 5, new_revision: null });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () => scenarioProjection({ data_revision: researchDone ? 5 : 4 }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => {
        researchDone = true;
        return badJob;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.match(snapshot.error?.message ?? "", /Research job lineage mismatch/u);
  assert.equal(snapshot.researchJob, null);
  assert.equal(snapshot.scenarios?.data_revision, 4);
});

test("rejects queued Case Copilot research jobs that already advance revision", async () => {
  let researchDone = false;
  const plan = researchPlanResponse();
  const badJob = researchJobResponse({
    status: "queued",
    data_revision: 5,
    old_revision: 4,
    new_revision: 5,
    accepted_entries: [],
    citations: [],
    changed_blocks: [],
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: researchDone ? 5 : 4,
      }),
      getCopilotState: async () =>
        copilotState({
          data_revision: researchDone ? 5 : 4,
          actions: [
            copilotAction("prepare_public_research", "requires_consent", {
              focus: "public_pricing_analogs",
              expected_case_revision: researchDone ? 5 : 4,
            }),
          ],
        }),
      getCopilotThread: async () => copilotThread({ data_revision: researchDone ? 5 : 4 }),
      getScenarios: async () => scenarioProjection({ data_revision: researchDone ? 5 : 4 }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => {
        researchDone = true;
        return badJob;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.prepareCopilotResearch({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.match(snapshot.error?.message ?? "", /Research job lineage mismatch/u);
  assert.equal(snapshot.researchJob, null);
  assert.equal(snapshot.scenarios?.data_revision, 4);
});

test("routes Case Copilot unknown skips as conversation turns without saving assumptions", async () => {
  let postedRequest: unknown = null;
  let posted = false;
  let assumptionSaveCalled = false;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: 4,
      }),
      getCopilotState: async () => copilotState(),
      getCopilotThread: async () =>
        posted
          ? copilotThread({
              messages: [
                ...copilotThread().messages,
                {
                  message_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                  case_id: caseId,
                  data_revision: 4,
                  role: "user",
                  content: "unknown",
                  page_context: "case-copilot",
                  current_section: "scenario-question",
                  idempotency_fingerprint: "copilot-unknown:mrr:fixed",
                  related_evidence_refs: [],
                  question_refs: ["question:mrr"],
                  action_refs: ["action:open_fact_input"],
                  action_snapshots: [],
                  action_result: null,
                },
              ],
            })
          : copilotThread(),
      postCopilotMessage: async (_activeCaseId, request): Promise<CopilotTurnResponse> => {
        postedRequest = request;
        posted = true;
        return {
          case_id: caseId,
          data_revision: 4,
          thread_id: copilotThread().thread_id,
          page_context: request.page_context,
          current_section: request.current_section,
          status: "accepted",
          message: request.message,
          available_actions: [],
        };
      },
      saveAssumption: async () => {
        assumptionSaveCalled = true;
        throw new Error("Unknown must not call /assumptions");
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.submitCopilotMessage({
    message: "unknown",
    page_context: "case-copilot",
    current_section: "scenario-question",
    expected_case_revision: 4,
    focus_key: "mrr",
    idempotency_key: "copilot-unknown:mrr:fixed",
  });

  assert.deepEqual(postedRequest, {
    message: "unknown",
    page_context: "case-copilot",
    current_section: "scenario-question",
    expected_case_revision: 4,
    focus_key: "mrr",
    idempotency_key: "copilot-unknown:mrr:fixed",
  });
  assert.equal(assumptionSaveCalled, false);
  assert.equal(orchestrator.getSnapshot().error, null);
  assert.equal(
    orchestrator.getSnapshot().copilotThread?.messages.at(-1)?.content,
    "unknown",
  );
});

test("does not treat an unmarked same-revision research job as a cache replay", async () => {
  const calls: string[] = [];
  const plan = researchPlanResponse();
  const unmarkedSameRevisionJob = researchJobResponse({
    data_revision: 4,
    old_revision: 4,
    new_revision: 4,
    reason: null,
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => ({ ...gate2Status, data_revision: 4 }),
      getStartupProfile: async () => ({ ...startupProfile, data_revision: 4 }),
      getCopilotState: async () => copilotState(),
      getCopilotThread: async () => copilotThread(),
      getScenarios: async () => scenarioProjection({ data_revision: 4 }),
      prepareResearchPlan: async () => plan,
      queueResearchJob: async () => unmarkedSameRevisionJob,
      decideGate2: async () => {
        calls.push("gate2");
        return decision({ ...gate3Status, data_revision: 4 });
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.launchCopilotResearchAndApproveGate2({
    focus: "public_pricing_analogs",
    intent: "prepare_public_benchmark_research",
    requested_private_value: null,
    expected_case_revision: 4,
    acquisitionMode: "live_public_research",
  });

  assert.equal(
    (orchestrator.getSnapshot().error as (Error & { code?: string }) | null)?.code,
    "research_no_useful_result",
  );
  assert.deepEqual(calls, []);
});

test("shows specific busy activities for Case Copilot fact assumption and message saves", async () => {
  const snapshots: FounderWorkspaceSnapshot[] = [];
  let factCalls = 0;
  let assumptionCalls = 0;
  let messageCalls = 0;
  let releaseFact!: () => void;
  let releaseAssumption!: () => void;
  let releaseMessage!: () => void;
  const pendingFact = new Promise<void>((resolve) => {
    releaseFact = resolve;
  });
  const pendingAssumption = new Promise<void>((resolve) => {
    releaseAssumption = resolve;
  });
  const pendingMessage = new Promise<void>((resolve) => {
    releaseMessage = resolve;
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: 4,
      }),
      getCopilotState: async () => copilotState(),
      getCopilotThread: async () => copilotThread(),
      saveFounderFact: async (): Promise<FactMutationResponse> => {
        factCalls += 1;
        await pendingFact;
        return {
          case_id: caseId,
          accepted: true,
          provenance: "founder_statement",
          source_type: "founder_statement",
          old_revision: 4,
          new_revision: 5,
          changed_keys: ["mrr"],
          delta: {
            accepted: true,
            old_revision: 4,
            new_revision: 5,
            changed_keys: ["mrr"],
            stale_scenario_ids: [],
            stale_report_ids: [],
            metric_before: {},
            metric_after: { mrr: "1400000-2000000" },
            readiness_before: {},
            readiness_after: {},
            next_question: null,
            validation_errors: [],
            original_draft: "1400000-2000000",
          },
        };
      },
      saveAssumption: async () => {
        assumptionCalls += 1;
        await pendingAssumption;
        return {
          case_id: caseId,
          status: "accepted",
          provenance: "founder_statement",
          reason: null,
          old_revision: 4,
          new_revision: 5,
          delta: {
            accepted: true,
            old_revision: 4,
            new_revision: 5,
            changed_keys: ["mrr"],
            stale_scenario_ids: [],
            stale_report_ids: [],
            metric_before: {},
            metric_after: { mrr: "1400000-2000000" },
            readiness_before: {},
            readiness_after: {},
            next_question: null,
            validation_errors: [],
            original_draft: "1400000-2000000",
          },
          accepted_input: {
            field_key: "mrr",
            kind: "founder_statement",
            status: "accepted",
            value: "1400000-2000000",
            period: null,
            rationale: "Founder input.",
            validation_plan: "Check finance records.",
            declared_source: "founder",
            source_refs: [],
          },
        };
      },
      postCopilotMessage: async (_activeCaseId, request): Promise<CopilotTurnResponse> => {
        messageCalls += 1;
        await pendingMessage;
        return {
          case_id: caseId,
          data_revision: 4,
          thread_id: copilotThread().thread_id,
          page_context: request.page_context,
          current_section: request.current_section,
          status: "accepted",
          message: request.message,
          available_actions: [],
        };
      },
    }),
    onChange: (snapshot) => snapshots.push(snapshot),
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);

  const saveFact = orchestrator.submitCopilotFact({
    requirement_key: "mrr",
    value: { kind: "text", value: "1400000-2000000" },
    period: null,
    source: {
      kind: "founder_statement",
      declared_source: "founder",
      evidence_ref: null,
    },
    note: null,
    resolves_contradiction_id: null,
    expected_case_revision: 4,
    idempotency_key: "fact:mrr:busy",
  });
  await Promise.resolve();
  await orchestrator.submitCopilotFact({
    requirement_key: "mrr",
    value: { kind: "text", value: "1400000-2000000" },
    period: null,
    source: {
      kind: "founder_statement",
      declared_source: "founder",
      evidence_ref: null,
    },
    note: null,
    resolves_contradiction_id: null,
    expected_case_revision: 4,
    idempotency_key: "fact:mrr:duplicate",
  });
  assert.equal(factCalls, 1);
  assert.equal(latest(snapshots).activity, "copilot_saving_fact");
  releaseFact();
  await saveFact;

  const saveAssumption = orchestrator.submitCopilotAssumption({
    requirement_key: "mrr",
    value: { kind: "text", value: "1400000-2000000" },
    period: null,
    source: {
      kind: "founder_statement",
      declared_source: "founder",
      evidence_ref: null,
    },
    rationale: "Founder input.",
    validation_plan: "Check finance records.",
    expected_case_revision: 4,
    idempotency_key: "assumption:mrr:busy",
  });
  await Promise.resolve();
  assert.equal(latest(snapshots).activity, "copilot_saving_assumption");
  releaseAssumption();
  await saveAssumption;

  const sendMessage = orchestrator.submitCopilotMessage({
    message: "unknown",
    page_context: "case-copilot",
    current_section: "scenario-question",
    expected_case_revision: 4,
    focus_key: "mrr",
    idempotency_key: "copilot-unknown:mrr:busy",
  });
  await Promise.resolve();
  assert.equal(latest(snapshots).activity, "copilot_sending_message");
  releaseMessage();
  await sendMessage;

  assert.equal(assumptionCalls, 1);
  assert.equal(messageCalls, 1);
  assert.equal(orchestrator.getSnapshot().busy, false);
  assert.equal(orchestrator.getSnapshot().activity, null);
});

test("shows Russian long-running upload feedback and blocks duplicate submission after acceptance", async () => {
  const controller = readFileSync(
    new URL("./founder-workspace-controller.tsx", import.meta.url),
    "utf8",
  );
  const snapshots: FounderWorkspaceSnapshot[] = [];
  let uploadCalls = 0;
  let releaseUpload!: () => void;
  const pendingUpload = new Promise<void>((resolve) => {
    releaseUpload = resolve;
  });
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      uploadDocuments: async () => {
        uploadCalls += 1;
        await pendingUpload;
        return uploaded;
      },
      getCase: async () => ({
        ...gate2Status,
        analysis_status: "awaiting_start",
        gate2_status: "not_ready",
      }),
    }),
    onChange: (snapshot) => snapshots.push(snapshot),
  });

  try {
    const start = orchestrator.start([new File(["deck"], "deck.pdf")]);
    await Promise.resolve();
    await orchestrator.start([new File(["deck"], "deck.pdf")]);

    assert.equal(uploadCalls, 1);
    assert.equal(latest(snapshots).activity, "uploading");
    assert.match(controller, /uploading:\s*"Загружаю материалы/u);
    assert.match(controller, /upload_accepted:\s*"Документы приняты/u);

    releaseUpload();
    const accepted = await start;

    assert.equal(accepted, true);
    assert.deepEqual(orchestrator.getSnapshot().acceptedDocumentIds, ["doc-0001"]);
    assert.equal(orchestrator.getSnapshot().uploadAccepted, true);
    const duplicateAccepted = await orchestrator.start([new File(["deck"], "deck.pdf")]);
    assert.equal(duplicateAccepted, false);
    assert.equal(uploadCalls, 1);
  } finally {
    orchestrator.dispose();
  }
});

test("treats blocked Case Copilot assumption outcomes as validation failures", async () => {
  const blockedOutcome: AssumptionOutcomeResponse = {
    case_id: caseId,
    status: "blocked",
    provenance: "founder_statement",
    reason: "Cannot save unknown as a structured assumption without evidence.",
    old_revision: 4,
    new_revision: 4,
    delta: {
      accepted: false,
      old_revision: 4,
      new_revision: 4,
      changed_keys: [],
      stale_scenario_ids: [],
      stale_report_ids: [],
      metric_before: {},
      metric_after: {},
      readiness_before: {},
      readiness_after: {},
      next_question: null,
      validation_errors: [
        {
          field: "mrr",
          message: "Unknown must stay a Copilot message, not an assumption.",
        },
      ],
      original_draft: "unknown",
    },
    accepted_input: null,
  };
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: 4,
      }),
      getCopilotState: async () => copilotState(),
      getCopilotThread: async () => copilotThread(),
      saveAssumption: async () => blockedOutcome,
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["brief"], "brief.txt", { type: "text/plain" })]);
  await orchestrator.submitCopilotAssumption({
    requirement_key: "mrr",
    value: { kind: "text", value: "unknown" },
    period: null,
    source: {
      kind: "founder_statement",
      declared_source: "founder",
      evidence_ref: null,
    },
    rationale: "Founder marked the value unknown in Case Copilot.",
    validation_plan: "Collect source evidence before using this as an actual.",
    expected_case_revision: 4,
    idempotency_key: "copilot-assumption:mrr:blocked",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.ok(snapshot.error instanceof FounderApiClientError);
  assert.equal(snapshot.error.code, "fact_validation_failed");
  assert.deepEqual(snapshot.copilotValidationErrors, [
    {
      field: "mrr",
      message: "Unknown must stay a Copilot message, not an assumption.",
    },
  ]);
  assert.equal(snapshot.assumptions?.some((input) => input.field_key === "mrr"), false);
});

test("clears stale Copilot validation errors when message input is unavailable", async () => {
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({
        ...startupProfile,
        case_id: caseId,
        data_revision: 4,
      }),
      getCopilotState: async () => copilotState(),
      getCopilotThread: async () => copilotThread(),
      saveFounderFact: async () => {
        throw new FounderApiClientError(
          "fact_validation_failed",
          422,
          "Field validation failed",
          null,
          [{ field: "mrr", message: "Use a number or range." }],
        );
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.submitCopilotFact({
    requirement_key: "mrr",
    value: { kind: "text", value: "" },
    period: null,
    source: {
      kind: "founder_statement",
      declared_source: "founder",
      evidence_ref: null,
    },
    note: null,
    resolves_contradiction_id: null,
    expected_case_revision: 4,
    idempotency_key: "fact:mrr:missing",
  });
  assert.deepEqual(orchestrator.getSnapshot().copilotValidationErrors, [
    { field: "mrr", message: "Use a number or range." },
  ]);

  await orchestrator.submitCopilotMessage({
    message: "unknown",
    page_context: "case-copilot",
    current_section: "scenario-question",
    expected_case_revision: 4,
    focus_key: "mrr",
    idempotency_key: "copilot-unknown:mrr:rev:4",
  });

  const snapshot = orchestrator.getSnapshot();
  assert.match(String(snapshot.error?.message), /Copilot message input is not available/u);
  assert.deepEqual(snapshot.copilotValidationErrors, []);
});

test("preserves Copilot validation field errors after a failed mutation and clears them on success", async () => {
  let rejectNextFact = true;
  const orchestrator = createFounderWorkspaceOrchestrator({
    api: api({
      getCase: async () => gate3Status,
      getStartupProfile: async () => ({ ...startupProfile, case_id: caseId, data_revision: 4 }),
      getCopilotState: async () => copilotState(),
      getCopilotThread: async () => copilotThread(),
      saveFounderFact: async () => {
        if (rejectNextFact) {
          rejectNextFact = false;
          throw new FounderApiClientError(
            "fact_validation_failed",
            422,
            "Field validation failed",
            null,
            [{ field: "mrr", message: "Укажите MRR диапазоном или числом." }],
          );
        }
        const mutation: FactMutationResponse = {
          case_id: caseId,
          accepted: true,
          provenance: "founder_statement",
          source_type: "founder_statement",
          old_revision: 4,
          new_revision: 5,
          changed_keys: ["mrr"],
          delta: {
            accepted: true,
            old_revision: 4,
            new_revision: 5,
            changed_keys: ["mrr"],
            stale_scenario_ids: [],
            stale_report_ids: [],
            metric_before: {},
            metric_after: { mrr: "1400000-2000000" },
            readiness_before: {},
            readiness_after: {},
            next_question: null,
            validation_errors: [],
            original_draft: "1400000-2000000",
          },
        };
        return mutation;
      },
    }),
    onChange: () => undefined,
  });

  await orchestrator.start([new File(["deck"], "deck.pdf")]);
  await orchestrator.submitCopilotFact({
    requirement_key: "mrr",
    value: { kind: "text", value: "" },
    period: null,
    source: {
      kind: "founder_statement",
      declared_source: "founder",
      evidence_ref: null,
    },
    note: null,
    resolves_contradiction_id: null,
    expected_case_revision: 4,
    idempotency_key: "fact:mrr:1",
  });

  assert.deepEqual(orchestrator.getSnapshot().copilotValidationErrors, [
    { field: "mrr", message: "Укажите MRR диапазоном или числом." },
  ]);

  await orchestrator.submitCopilotFact({
    requirement_key: "mrr",
    value: { kind: "text", value: "1400000-2000000" },
    period: null,
    source: {
      kind: "founder_statement",
      declared_source: "founder",
      evidence_ref: null,
    },
    note: null,
    resolves_contradiction_id: null,
    expected_case_revision: 4,
    idempotency_key: "fact:mrr:2",
  });

  assert.deepEqual(orchestrator.getSnapshot().copilotValidationErrors, []);
});
