import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiContractError,
  parseApiError,
  parseStartupAnalysis,
  parseStartupCaseReport,
  parseStartupCaseStatus,
  parseStartupCreateResponse,
  parseStartupGate2DecisionResult,
  parseStartupGate2Preview,
  parseStartupGate3DecisionResult,
  parseStartupGate4DecisionResult,
  parseStartupGtmResponse,
  parseLaunchPackMetadataResponse,
  parseStartupProfileResponse,
  parseStartupReportSnapshotResponse,
  parseStartupUploadResponse,
} from "./contracts.ts";

const startupProfileFieldNames = [
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

const profileEvidenceRef = (fieldName: string) => ({
  evidence_id: "11111111-1111-4111-8111-111111111111",
  fragment_id: "22222222-2222-4222-8222-222222222222",
  artifact_id: "33333333-3333-4333-8333-333333333333",
  artifact_hash: `sha256:${"1".repeat(64)}`,
  locator_hash: `sha256:${"2".repeat(64)}`,
  page: 1,
  table: null,
  cell: null,
  field_name: fieldName,
  confidence: "0.95",
});

const startupProfileField = (
  fieldName: string,
  overrides: Record<string, unknown> = {},
) => ({
  status: "insufficient_data",
  values: [],
  confidence: "0",
  evidence_refs: [],
  dependency_refs: [],
  reason_code: null,
  contradiction_ids: [],
  ...overrides,
});

const validStartupProfileResponse = () => ({
  case_id: "case-1",
  profile_id: "44444444-4444-4444-8444-444444444444",
  profile_hash: `sha256:${"3".repeat(64)}`,
  data_revision: 2,
  analysis_stage: "primary",
  parent_profile_id: null,
  fields: Object.fromEntries(
    startupProfileFieldNames.map((fieldName) => [
      fieldName,
      startupProfileField(fieldName),
    ]),
  ),
  contradictions: [],
  gaps: ["users"],
  parse_inventory: {
    source_hashes: { "doc-0001": `sha256:${"4".repeat(64)}` },
    parse_outcomes: { "doc-0001": "parsed" },
  },
});

const validStartupGtmResponse = () => ({
  case_id: "case-1",
  schema_version: "startup_gtm@1",
  snapshot_id: "gtm-snapshot-1",
  snapshot_hash:
    "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  snapshot_revision: 2,
  status: "partial",
  profile_id: "profile-1",
  product_validation_snapshot_id: "product-snapshot-1",
  market_research_snapshot_id: "market-snapshot-1",
  dimensions: [
    {
      name: "audience",
      status: "supported",
      evidence_fact_ids: ["fact-1"],
      market_source_ids: [],
      contradiction_ids: [],
      reason_code: "gtm_audience_supported",
      gap_code: null,
    },
    {
      name: "geography",
      status: "partial",
      evidence_fact_ids: ["fact-2"],
      market_source_ids: ["market-2"],
      contradiction_ids: [],
      reason_code: "gtm_geography_partial",
      gap_code: null,
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
      evidence_fact_ids: ["fact-3"],
      market_source_ids: [],
      contradiction_ids: [],
      reason_code: "gtm_offer_supported",
      gap_code: null,
    },
    {
      name: "market_context",
      status: "supported",
      evidence_fact_ids: [],
      market_source_ids: ["market-3"],
      contradiction_ids: [],
      reason_code: "gtm_market_context_supported",
      gap_code: null,
    },
    {
      name: "product_proof",
      status: "contradicted",
      evidence_fact_ids: ["fact-4"],
      market_source_ids: [],
      contradiction_ids: ["contradiction-1"],
      reason_code: "gtm_product_proof_contradicted",
      gap_code: null,
    },
    {
      name: "adoption_risk",
      status: "partial",
      evidence_fact_ids: [],
      market_source_ids: ["market-4"],
      contradiction_ids: [],
      reason_code: "gtm_adoption_risk_partial",
      gap_code: null,
    },
  ],
  launch_plan: [
    { horizon: "day_7", experiment_codes: ["clarify_audience"] },
    { horizon: "day_30", experiment_codes: ["validate_channel"] },
    { horizon: "day_60", experiment_codes: ["validate_offer"] },
    { horizon: "day_90", experiment_codes: ["review_launch_evidence"] },
  ],
  finding_ids: ["finding-1"],
  built_at: "2026-08-15T00:00:00Z",
});

const startupReportSection = (
  title: string,
  status: "SUPPORTED" | "PARTIAL" | "MISSING" | "CONTRADICTION" = "PARTIAL",
  overrides: Record<string, unknown> = {},
) => ({
  title,
  summary: `${title} summary is bounded and founder-safe.`,
  status,
  rows: [
    [
      `${title.toLowerCase().replaceAll(" ", "_")}_ref`,
      `sha256:${"7".repeat(64)}`,
      "bounded_source_ref",
    ],
  ],
  items: [`${title.toLowerCase().replaceAll(" ", "_")}_item`],
  ...overrides,
});

const validStartupReportSnapshotResponse = () => ({
  schema: "startup_report_snapshot.v1",
  integrity_preimage_contract: "report_hash excludes artifact hash fields",
  id: "22222222-2222-4222-8222-222222222222",
  case_id: "11111111-1111-4111-8111-111111111111",
  report_hash: `sha256:${"8".repeat(64)}`,
  case_snapshot_hash: `sha256:${"2".repeat(64)}`,
  source_hashes: { pitch_deck: `sha256:${"9".repeat(64)}` },
  as_of: "2026-08-15T00:00:00Z",
  graph_version: "startup-graph@1",
  prompt_versions: { report: "startup-report-template@1" },
  formula_versions: { arr: "arr@1" },
  model_versions: { analysis: "offline" },
  trace_ids: ["startup-report-trace-1"],
  sections: {
    business_idea_summary: startupReportSection("Business Idea Summary", "SUPPORTED"),
    problem_solution: startupReportSection("Problem / Solution"),
    market_size: startupReportSection("Market Size", "MISSING", {
      rows: [],
      items: ["tam_sam_som_inputs_missing"],
    }),
    competitors: startupReportSection("Competitors"),
    moat: startupReportSection("Moat"),
    go_to_market: startupReportSection("Go To Market"),
    metrics: startupReportSection("Metrics"),
    financial_assumptions: startupReportSection("Financial Assumptions"),
    risks: startupReportSection("Risks", "CONTRADICTION", {
      rows: [["contradiction_ref", "77777777-7777-4777-8777-777777777777"]],
    }),
    evidence_gaps: startupReportSection("Evidence Gaps", "MISSING"),
    diligence_questions: startupReportSection("Diligence Questions"),
    action_plan: startupReportSection("Action Plan"),
    methodology: startupReportSection("Methodology", "SUPPORTED", {
      rows: [
        ["profile_id", "33333333-3333-4333-8333-333333333333"],
        ["profile_hash", `sha256:${"3".repeat(64)}`],
        ["data_revision", "3"],
        ["readiness_snapshot_id", "44444444-4444-4444-8444-444444444444"],
        ["readiness_snapshot_hash", `sha256:${"4".repeat(64)}`],
        ["market_research_snapshot_id", "55555555-5555-4555-8555-555555555555"],
        ["market_research_snapshot_hash", `sha256:${"5".repeat(64)}`],
        ["gtm_snapshot_id", "66666666-6666-4666-8666-666666666666"],
        ["gtm_snapshot_hash", `sha256:${"6".repeat(64)}`],
      ],
      items: [],
    }),
    source_appendix: startupReportSection("Source Appendix", "SUPPORTED", {
      rows: [["pitch_deck", `sha256:${"9".repeat(64)}`]],
      items: [],
    }),
  },
  data_revision: 3,
  reproducibility: {
    code_commit: "offline",
    build_id: "local-startup-report",
    dependency_lock_hash: `sha256:${"a".repeat(64)}`,
    python_version: "3.13.0",
    package_versions: { pydantic: "2.0.0" },
    provider_model_id: "offline",
    model_alias_snapshot: "offline",
    reasoning_parameters: { network: "disabled" },
    adapter_versions: { html: "jinja-server-owned@1" },
    parser_versions: { report: "startup-report@1" },
    embedding_model_version: "offline",
    index_version: "none",
    redaction_policy_version: "standard",
    locale: "en-US",
    timezone: "UTC",
    fx_source: "USD",
    deterministic_seeds: { report: 1 },
    configuration_hash: `sha256:${"b".repeat(64)}`,
  },
  sensitivity: "confidential",
  created_at: "2026-08-15T00:00:00Z",
  version: 1,
});

const validFounderSafeStartupReportResponse = () => ({
  title_ru: "Отчёт для основателя",
  subtitle_ru: "Краткий разбор проекта, блокеры и следующие шаги",
  as_of_ru: "2026-08-15",
  data_revision: 3,
  main_sections: [
    {
      key: "business_idea_summary",
      title_ru: "Кратко о проекте",
      status: "confirmed",
      status_label_ru: "Подтверждено",
      summary_ru: "Проект описан достаточно для первого инвестиционного разбора.",
      content_heading_ru: "Что уже известно",
      known_facts_ru: ["Команда строит B2B продукт для финансовых команд."],
      blockers_ru: [],
      next_data_ru: [],
      unlocks_ru: ["Можно перейти к проверке позиционирования."],
    },
    {
      key: "metrics",
      title_ru: "Ключевые метрики",
      status: "partial",
      status_label_ru: "Нужно уточнить",
      summary_ru: "Часть метрик подтверждена, часть требует уточнения.",
      content_heading_ru: "Что уже известно",
      known_facts_ru: ["ARR указан как 120000 USD в год."],
      blockers_ru: ["Нужна детализация по удержанию."],
      next_data_ru: ["Добавить когорты удержания."],
      unlocks_ru: ["Станет понятнее качество выручки."],
    },
  ],
  metric_cards: {
    arr: {
      title_ru: "ARR",
      summary_ru: "120000 USD в год.",
      status: "confirmed",
      why_it_matters_ru: "Показывает текущий масштаб выручки.",
      next_unlock_ru: "Подтвердить повторяемость продаж.",
    },
  },
  improvement_proposals: [
    {
      target_area: "metrics",
      title_ru: "Уточнить удержание",
      recommendation_ru: "Добавить когорты удержания и churn по клиентам.",
      rationale_ru: "Это снижает неопределённость по качеству выручки.",
      expected_effect_ru: "Инвестору будет проще оценить повторяемость роста.",
      provenance: "ai_recommendation",
    },
  ],
  technical_appendix: {
    methodology_ru: ["Отчёт построен по агрегированным разделам анализа."],
    sources_ru: ["Использованы материалы, загруженные в рабочую область."],
  },
  analytics: {
    metric_points: [],
    market_points: [],
    readiness_dimensions: [],
  },
});

const validStartupCaseStatusResponse = () => ({
  case_id: "case-1",
  case_status: "awaiting_upload",
  analysis_status: "gate2_preview_ready",
  provider_status: "unavailable",
  data_revision: 3,
  active_analysis_thread_id: "startup-thread-001",
  langgraph_checkpoint: {
    checkpoint_id: "checkpoint:smart-university:01",
    checkpoint_hash: "a".repeat(64),
    data_revision: 3,
    thread_id: "startup-thread-001",
  },
  gate2_status: "required",
  gate3_status: "not_ready",
  gate4_status: "not_ready",
  report_status: "not_ready",
  snapshot_hash: null,
  snapshot_revision: null,
});

test("accepts every canonical startup DTO used by route handlers", () => {
  const created = parseStartupCreateResponse({
    case_id: "case-1",
    case_status: "awaiting_upload",
    analysis_status: "awaiting_upload",
    provider_status: "deterministic_offline_fixture",
    auto_start_triggered: false,
  });
  const status = parseStartupCaseStatus(validStartupCaseStatusResponse());
  const upload = parseStartupUploadResponse({
    case_id: "case-1",
    accepted_document_ids: ["doc-1", "doc-2"],
    analysis_status: "gate2_preview_ready",
    auto_start_triggered: true,
    next_poll_after_ms: 750,
  });
  const analysis = parseStartupAnalysis({
    ...validStartupCaseStatusResponse(),
    analysis_status: "gate3_review_required",
    gate2_status: "completed",
    gate3_status: "required",
  });
  const gate2Preview = parseStartupGate2Preview({
    case_id: "case-1",
    preview: { artifact_counts: { pdf: 1 } },
    resume_token: "opaque-token",
    provider_mode: "unavailable",
  });
  const gate2Decision = parseStartupGate2DecisionResult({
    case_id: "case-1",
    gate2_status: "completed",
    analysis_status: "gate3_review_required",
    gate3_status: "required",
    gate4_status: "not_ready",
    report_status: "not_ready",
    snapshot_hash: null,
    snapshot_revision: null,
  });
  const gate3Decision = parseStartupGate3DecisionResult({
    case_id: "case-1",
    gate2_status: "completed",
    gate3_status: "completed",
    gate4_status: "not_ready",
    analysis_status: "analysis_complete_report_pending",
    report_status: "not_ready",
    snapshot_hash: null,
    snapshot_revision: null,
  });
  const gate4Decision = parseStartupGate4DecisionResult({
    case_id: "case-1",
    gate2_status: "completed",
    gate3_status: "completed",
    gate4_status: "completed",
    analysis_status: "analysis_complete_report_pending",
    report_status: "pending",
    snapshot_hash: "sha256:abc",
    snapshot_revision: 3,
  });
  const report = parseStartupCaseReport({
    case_id: "case-1",
    report_status: "ready",
    snapshot_id: "snap-1",
    snapshot_hash: "sha256:abc",
    snapshot_revision: 3,
    json_url: "/api/startup/cases/case-1/report",
    html_url: "/api/startup/cases/case-1/report/html",
    pdf_url: "/api/startup/cases/case-1/report/pdf",
    freeze_status: "approved",
    pdf_status: "ready",
  });
  const gtm = parseStartupGtmResponse(validStartupGtmResponse());
  const apiError = parseApiError({
    code: "report_not_ready",
    message: "Report is not ready",
  });

  assert.equal(created.provider_status, "deterministic_offline_fixture");
  assert.equal(status.snapshot_hash, null);
  assert.equal(status.data_revision, 3);
  assert.equal(status.langgraph_checkpoint?.checkpoint_hash, "a".repeat(64));
  assert.deepEqual(upload.accepted_document_ids, ["doc-1", "doc-2"]);
  assert.equal(analysis.gate3_status, "required");
  assert.equal(gate2Preview.resume_token, "opaque-token");
  assert.equal(gate2Decision.gate2_status, "completed");
  assert.equal(gate3Decision.gate3_status, "completed");
  assert.equal(gate4Decision.snapshot_revision, 3);
  assert.equal(report.pdf_status, "ready");
  assert.equal(gtm.schema_version, "startup_gtm@1");
  assert.equal(gtm.dimensions.length, 7);
  assert.deepEqual(
    gtm.launch_plan.map((step) => step.horizon),
    ["day_7", "day_30", "day_60", "day_90"],
  );
  assert.equal(apiError.code, "report_not_ready");
  assert.equal(
    parseApiError({
      code: "advisor_manual_answer_semantic_mismatch",
      message: "Answer does not match the current advisor question",
    }).code,
    "advisor_manual_answer_semantic_mismatch",
  );
});

test("accepts initial startup status before the first LangGraph checkpoint", () => {
  const parsed = parseStartupCaseStatus({
    ...validStartupCaseStatusResponse(),
    data_revision: 0,
    active_analysis_thread_id: "case-1",
    langgraph_checkpoint: null,
  });

  assert.equal(parsed.data_revision, 0);
  assert.equal(parsed.active_analysis_thread_id, "case-1");
  assert.equal(parsed.langgraph_checkpoint, null);
});

test("enforces startup status LangGraph checkpoint lineage", () => {
  assert.throws(
    () =>
      parseStartupCaseStatus({
        ...validStartupCaseStatusResponse(),
        data_revision: -1,
      }),
    /data_revision/,
  );
  assert.throws(
    () =>
      parseStartupCaseStatus({
        ...validStartupCaseStatusResponse(),
        langgraph_checkpoint: {
          ...validStartupCaseStatusResponse().langgraph_checkpoint,
          data_revision: 4,
        },
      }),
    /data_revision/,
  );
  assert.throws(
    () =>
      parseStartupCaseStatus({
        ...validStartupCaseStatusResponse(),
        langgraph_checkpoint: {
          ...validStartupCaseStatusResponse().langgraph_checkpoint,
          thread_id: "startup-thread-002",
        },
      }),
    /thread_id/,
  );
  assert.throws(
    () =>
      parseStartupCaseStatus({
        ...validStartupCaseStatusResponse(),
        langgraph_checkpoint: {
          ...validStartupCaseStatusResponse().langgraph_checkpoint,
          checkpoint_hash: "A".repeat(64),
        },
      }),
    /checkpoint_hash/,
  );
  assert.throws(
    () =>
      parseStartupCaseStatus({
        ...validStartupCaseStatusResponse(),
        langgraph_checkpoint: {
          ...validStartupCaseStatusResponse().langgraph_checkpoint,
          checkpoint_id: "../unsafe",
        },
      }),
    /checkpoint_id/,
  );
});

test("accepts launch pack metadata with nullable csv url", () => {
  const parsed = parseLaunchPackMetadataResponse({
    case_id: "11111111-1111-4111-8111-111111111111",
    data_revision: 3,
    scenario_set_id: "22222222-2222-4222-8222-222222222222",
    selected_scenario_key: "base",
    asset_id: "33333333-3333-4333-8333-333333333333",
    asset_key: "gtm_launch_pack",
    asset_revision: 1,
    status: "draft",
    markdown_url:
      "/api/startup/cases/11111111-1111-4111-8111-111111111111/assets/33333333-3333-4333-8333-333333333333/markdown",
    csv_url: null,
    provenance_appendix_url:
      "/api/startup/cases/11111111-1111-4111-8111-111111111111/assets/33333333-3333-4333-8333-333333333333/provenance",
    body_markdown: "## Executive summary\n\nDraft.",
  });

  assert.equal(parsed.csv_url, null);
  assert.equal(parsed.asset_key, "gtm_launch_pack");
});

test("accepts launch pack metadata with full 12-section markdown body", () => {
  const sections = [
    "Executive summary",
    "Scenario context",
    "Founder facts",
    "Public benchmarks",
    "Scenario metrics",
    "GTM milestones",
    "Budget envelope",
    "Risks and gaps",
    "Dependencies",
    "Validation plan",
    "Source references",
    "Next actions",
  ];
  const bodyMarkdown = sections
    .map(
      (section, index) =>
        `## ${index + 1}. ${section}\n\n` +
        "Metric provenance, range, formula, dependencies, source refs, and validation plan. ".repeat(
          10,
        ),
    )
    .join("\n\n");

  assert.ok(bodyMarkdown.length > 1000);

  const parsed = parseLaunchPackMetadataResponse({
    case_id: "11111111-1111-4111-8111-111111111111",
    data_revision: 3,
    scenario_set_id: "22222222-2222-4222-8222-222222222222",
    selected_scenario_key: "base",
    asset_id: "33333333-3333-4333-8333-333333333333",
    asset_key: "gtm_launch_pack",
    asset_revision: 1,
    status: "draft",
    markdown_url:
      "/api/startup/cases/11111111-1111-4111-8111-111111111111/assets/33333333-3333-4333-8333-333333333333/markdown",
    csv_url: null,
    provenance_appendix_url:
      "/api/startup/cases/11111111-1111-4111-8111-111111111111/assets/33333333-3333-4333-8333-333333333333/provenance",
    body_markdown: `\n${bodyMarkdown}\n`,
  });

  assert.equal(parsed.body_markdown, bodyMarkdown.trim());
});

test("accepts founder-safe public startup report JSON projection", () => {
  const parsed = parseStartupReportSnapshotResponse(
    validFounderSafeStartupReportResponse(),
  );

  assert.equal(parsed.title_ru, "Отчёт для основателя");
  assert.equal(parsed.data_revision, 3);
  assert.deepEqual(
    parsed.main_sections.map((section) => section.key),
    ["business_idea_summary", "metrics"],
  );
  assert.equal(parsed.metric_cards.arr.status, "confirmed");
  assert.equal(parsed.improvement_proposals[0]?.target_area, "metrics");
  assert.deepEqual(parsed.technical_appendix.sources_ru, [
    "Использованы материалы, загруженные в рабочую область.",
  ]);
});

test("rejects founder-safe public startup report JSON without analytics", () => {
  const reportWithoutAnalytics = {
    ...validFounderSafeStartupReportResponse(),
  } as Record<string, unknown>;
  delete reportWithoutAnalytics.analytics;

  assert.throws(
    () => parseStartupReportSnapshotResponse(reportWithoutAnalytics),
    /analytics/,
  );
});

test("rejects raw canonical startup report JSON on the founder public report contract", () => {
  assert.throws(
    () => parseStartupReportSnapshotResponse(validStartupReportSnapshotResponse()),
    ApiContractError,
  );
});

test("recognizes founder-safe GTM availability failures", () => {
  assert.equal(
    parseApiError({
      code: "startup_gtm_not_ready",
      message: "GTM snapshot is not ready",
    }).code,
    "startup_gtm_not_ready",
  );
  assert.equal(
    parseApiError({
      code: "startup_gtm_stale",
      message: "GTM snapshot no longer matches the case revision",
    }).code,
    "startup_gtm_stale",
  );
});

test("recognizes founder-safe startup profile availability failures", () => {
  assert.equal(
    parseApiError({
      code: "startup_profile_not_ready",
      message: "startup_profile_not_ready",
    }).code,
    "startup_profile_not_ready",
  );
  assert.equal(
    parseApiError({
      code: "startup_profile_stale",
      message: "startup_profile_stale",
    }).code,
    "startup_profile_stale",
  );
});

test("accepts founder-safe report analytics without internal lineage fields", () => {
  const parsed = parseStartupReportSnapshotResponse({
    ...validFounderSafeStartupReportResponse(),
    analytics: {
      metric_points: [
        {
          key: "gross_margin",
          label_ru: "Валовая маржа",
          value: 0.72,
          unit: "ratio",
          period_ru: "Q2 2026",
          status: "confirmed",
        },
        {
          key: "gross_margin",
          label_ru: "Валовая маржа",
          value: 0.7,
          unit: "ratio",
          period_ru: "June 2026",
          status: "calculated",
        },
        {
          key: "monthly_recurring_revenue",
          label_ru: "MRR",
          value: 27900000,
          unit: "KZT",
          period_ru: "June 2026",
          status: "contradiction",
        },
      ],
      market_points: [
        {
          key: "tam",
          label_ru: "TAM",
          value: 1200000,
          unit: "USD",
          period_ru: "2026",
          status: "estimated",
        },
      ],
      readiness_dimensions: [
        {
          key: "retention",
          label_ru: "Удержание",
          status: "blocked",
          status_label_ru: "Нужны данные",
          explanation_ru: "Добавьте когорты удержания.",
        },
      ],
    },
  });

  assert.equal(parsed.analytics.metric_points[0]?.value, 0.72);
  assert.equal(parsed.analytics.metric_points[1]?.status, "calculated");
  assert.equal(parsed.analytics.metric_points[2]?.status, "contradiction");
  assert.equal(parsed.analytics.market_points[0]?.key, "tam");
  assert.equal(parsed.analytics.readiness_dimensions[0]?.status, "blocked");
  assert.equal("case_id" in parsed, false);
  assert.equal("report_hash" in parsed, false);
  assert.equal("trace_ids" in parsed, false);
});

test("rejects founder-safe report projection with private fields or unsafe values", () => {
  assert.throws(
    () =>
      parseStartupReportSnapshotResponse({
        ...validFounderSafeStartupReportResponse(),
        case_id: "11111111-1111-4111-8111-111111111111",
      }),
    /case_id/,
  );
  assert.throws(
    () =>
      parseStartupReportSnapshotResponse({
        ...validFounderSafeStartupReportResponse(),
        report_hash: `sha256:${"8".repeat(64)}`,
      }),
    /report_hash/,
  );
  assert.throws(
    () =>
      parseStartupReportSnapshotResponse({
        ...validFounderSafeStartupReportResponse(),
        main_sections: [
          {
            ...validFounderSafeStartupReportResponse().main_sections[0],
            known_facts_ru: ["MISSING document_text_block_001"],
          },
        ],
      }),
    /internal report content/,
  );
  assert.throws(
    () =>
      parseStartupReportSnapshotResponse({
        ...validFounderSafeStartupReportResponse(),
        analytics: {
          metric_points: [
            {
              key: "gross_margin",
              label_ru: "calculation_ref=calc-margin",
              value: 0.72,
              unit: "ratio",
              period_ru: "Q2 2026",
              status: "confirmed",
            },
          ],
          market_points: [],
          readiness_dimensions: [],
        },
      }),
    /internal report content/,
  );
});

test("accepts the exact backend startup profile DTO with all canonical fields", () => {
  const sourceFact = startupProfileField("startup_name", {
    status: "source_fact",
    values: ["FounderCo"],
    confidence: "0.95",
    evidence_refs: [profileEvidenceRef("startup_name")],
  });
  const inference = startupProfileField("business_model", {
    status: "inference",
    values: ["subscription"],
    confidence: "0.60",
    dependency_refs: ["11111111-1111-4111-8111-111111111111"],
    reason_code: "business_model_inferred_from_pricing",
  });
  const contradiction = startupProfileField("traction", {
    status: "contradiction",
    values: ["10 pilots", "100 pilots"],
    confidence: "0.50",
    evidence_refs: [
      profileEvidenceRef("traction"),
      {
        ...profileEvidenceRef("traction"),
        evidence_id: "55555555-5555-4555-8555-555555555555",
      },
    ],
    reason_code: "traction_conflict",
    contradiction_ids: ["66666666-6666-4666-8666-666666666666"],
  });

  const parsed = parseStartupProfileResponse({
    ...validStartupProfileResponse(),
    fields: {
      ...validStartupProfileResponse().fields,
      startup_name: sourceFact,
      business_model: inference,
      traction: contradiction,
    },
    contradictions: ["66666666-6666-4666-8666-666666666666"],
  });

  assert.deepEqual(Object.keys(parsed.fields), [...startupProfileFieldNames]);
  assert.equal(parsed.profile_hash, `sha256:${"3".repeat(64)}`);
  assert.equal(parsed.fields.startup_name.status, "source_fact");
  assert.deepEqual(parsed.fields.startup_name.values, ["FounderCo"]);
  assert.equal(parsed.fields.startup_name.evidence_refs[0]?.artifact_hash, `sha256:${"1".repeat(64)}`);
  assert.equal(parsed.fields.business_model.status, "inference");
  assert.deepEqual(parsed.fields.business_model.dependency_refs, [
    "11111111-1111-4111-8111-111111111111",
  ]);
  assert.equal(parsed.fields.traction.status, "contradiction");
  assert.deepEqual(parsed.gaps, ["users"]);
  assert.deepEqual(parsed.parse_inventory, {
    source_hashes: { "doc-0001": `sha256:${"4".repeat(64)}` },
    parse_outcomes: { "doc-0001": "parsed" },
  });
});

test("rejects startup profile DTOs with unknown keys or incomplete canonical fields", () => {
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        raw_filename: "secret-pitch.pdf",
      }),
    ApiContractError,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: {
          ...validStartupProfileResponse().fields,
          raw_prompt: startupProfileField("raw_prompt"),
        },
      }),
    /fields must contain each startup_profile@1 field exactly once/,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: Object.fromEntries(
          Object.entries(validStartupProfileResponse().fields).filter(
            ([key]) => key !== "users",
          ),
        ),
      }),
    /fields must contain each startup_profile@1 field exactly once/,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: {
          ...validStartupProfileResponse().fields,
          startup_name: {
            ...startupProfileField("startup_name"),
            raw_quote: "private founder excerpt",
          },
        },
      }),
    ApiContractError,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        parse_inventory: {
          source_hashes: { "doc-0001": `sha256:${"4".repeat(64)}` },
          parse_outcomes: { "doc-0001": "parsed" },
          private_path: "D:/Founder Pitch Secret.pdf",
        },
      }),
    ApiContractError,
  );
});

test("enforces startup profile field statuses evidence refs hashes confidence and safe references", () => {
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: {
          ...validStartupProfileResponse().fields,
          startup_name: startupProfileField("startup_name", {
            status: "source_fact",
            values: ["FounderCo"],
            confidence: "0.95",
            evidence_refs: [],
          }),
        },
      }),
    /source_fact requires evidence refs/,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: {
          ...validStartupProfileResponse().fields,
          business_model: startupProfileField("business_model", {
            status: "inference",
            values: ["subscription"],
            confidence: "0.60",
            dependency_refs: [],
            reason_code: "business_model_inferred",
          }),
        },
      }),
    /inference requires dependency refs/,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: {
          ...validStartupProfileResponse().fields,
          users: startupProfileField("users", {
            status: "insufficient_data",
            values: ["1000"],
            confidence: "0.20",
          }),
        },
      }),
    /insufficient_data must not invent values/,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: {
          ...validStartupProfileResponse().fields,
          traction: startupProfileField("traction", {
            status: "contradiction",
            values: ["10 pilots", "100 pilots"],
            confidence: "0.50",
            evidence_refs: [profileEvidenceRef("traction")],
            contradiction_ids: [],
            reason_code: "traction_conflict",
          }),
        },
      }),
    /contradiction requires competing refs or contradiction ids/,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: {
          ...validStartupProfileResponse().fields,
          startup_name: startupProfileField("startup_name", {
            status: "source_fact",
            values: ["FounderCo"],
            confidence: "1.10",
            evidence_refs: [profileEvidenceRef("startup_name")],
          }),
        },
      }),
    /confidence/,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: {
          ...validStartupProfileResponse().fields,
          startup_name: startupProfileField("startup_name", {
            status: "source_fact",
            values: ["FounderCo"],
            confidence: "0.95",
            evidence_refs: [
              {
                ...profileEvidenceRef("startup_name"),
                artifact_hash: "sha256:not-a-hash",
              },
            ],
          }),
        },
      }),
    /artifact_hash/,
  );
  assert.throws(
    () =>
      parseStartupProfileResponse({
        ...validStartupProfileResponse(),
        fields: {
          ...validStartupProfileResponse().fields,
          startup_name: startupProfileField("startup_name", {
            status: "source_fact",
            values: ["FounderCo"],
            confidence: "0.95",
            evidence_refs: [
              {
                ...profileEvidenceRef("startup_name"),
                table: "../private",
              },
            ],
          }),
        },
      }),
    /table/,
  );
});

test("enforces backend startup GTM semantic constraints", () => {
  const parsed = parseStartupGtmResponse({
    ...validStartupGtmResponse(),
    dimensions: validStartupGtmResponse().dimensions.map((dimension) =>
      dimension.name === "audience"
        ? {
            ...dimension,
            evidence_fact_ids: [" fact-2 ", "fact-1", "fact-1"],
            reason_code: " GTM_AUDIENCE_SUPPORTED ",
          }
        : dimension,
    ),
    launch_plan: validStartupGtmResponse().launch_plan.map((step) =>
      step.horizon === "day_7"
        ? {
            ...step,
            experiment_codes: [
              "review_launch_evidence",
              "clarify_audience",
              "clarify_audience",
            ],
          }
        : step,
    ),
  });

  assert.deepEqual(parsed.dimensions[0].evidence_fact_ids, ["fact-1", "fact-2"]);
  assert.equal(parsed.dimensions[0].reason_code, "gtm_audience_supported");
  assert.deepEqual(parsed.launch_plan[0].experiment_codes, [
    "clarify_audience",
    "review_launch_evidence",
  ]);

  assert.throws(
    () =>
      parseStartupGtmResponse({
        ...validStartupGtmResponse(),
        snapshot_hash: "sha256:gtm",
      }),
    /snapshot_hash/,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        ...validStartupGtmResponse(),
        launch_plan: validStartupGtmResponse().launch_plan.map((step) =>
          step.horizon === "day_7"
            ? { ...step, experiment_codes: ["landing_page_smoke"] }
            : step,
        ),
      }),
    /experiment_codes/,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        ...validStartupGtmResponse(),
        dimensions: validStartupGtmResponse().dimensions.map((dimension) =>
          dimension.name === "audience"
            ? { ...dimension, evidence_fact_ids: ["../fact-1"] }
            : dimension,
        ),
      }),
    /evidence_fact_ids/,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        ...validStartupGtmResponse(),
        dimensions: validStartupGtmResponse().dimensions.map((dimension) =>
          dimension.name === "channels" ? { ...dimension, gap_code: null } : dimension,
        ),
      }),
    /gap_code/,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        ...validStartupGtmResponse(),
        dimensions: validStartupGtmResponse().dimensions.map((dimension) =>
          dimension.name === "geography"
            ? { ...dimension, gap_code: "gtm_geography_gap" }
            : dimension,
        ),
      }),
    /gap_code/,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        ...validStartupGtmResponse(),
        dimensions: validStartupGtmResponse().dimensions.map((dimension) =>
          dimension.name === "offer"
            ? { ...dimension, evidence_fact_ids: [], market_source_ids: [] }
            : dimension,
        ),
      }),
    /evidence references/,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        ...validStartupGtmResponse(),
        dimensions: validStartupGtmResponse().dimensions.map((dimension) =>
          dimension.name === "product_proof"
            ? { ...dimension, contradiction_ids: [] }
            : dimension,
        ),
      }),
    /contradiction references/,
  );
});

test("rejects exact-key violations and unsafe startup DTO internals", () => {
  assert.throws(
    () =>
      parseStartupCreateResponse({
        case_id: "case-1",
        case_status: "awaiting_upload",
        analysis_status: "awaiting_upload",
        provider_status: "unavailable",
        auto_start_triggered: false,
        filename: "pitch.pdf",
      }),
    ApiContractError,
  );
  assert.throws(
    () =>
      parseStartupCaseStatus({
        ...validStartupCaseStatusResponse(),
        provider_status: "deterministic_fixture",
      }),
    /provider_status/,
  );
  assert.throws(
    () =>
      parseStartupCaseStatus({
        ...validStartupCaseStatusResponse(),
        case_status: "analysis",
      }),
    /case_status/,
  );
  assert.throws(
    () =>
      parseStartupGate2Preview({
        case_id: "case-1",
        preview: { artifact_counts: { pdf: 1 } },
        resume_token: "opaque-token",
        provider_mode: "unavailable",
        checkpoint_id: "internal",
      }),
    ApiContractError,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        case_id: "case-1",
        schema_version: "startup_gtm@1",
        snapshot_id: "gtm-snapshot-1",
        snapshot_hash:
          "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        snapshot_revision: 2,
        status: "partial",
        profile_id: "profile-1",
        product_validation_snapshot_id: "product-snapshot-1",
        market_research_snapshot_id: "market-snapshot-1",
        dimensions: [],
        launch_plan: [],
        finding_ids: [],
        built_at: "2026-08-15T00:00:00Z",
        raw_evidence: { secret: "must not pass through" },
      }),
    ApiContractError,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        case_id: "case-1",
        schema_version: "startup_gtm@1",
        snapshot_id: "gtm-snapshot-1",
        snapshot_hash:
          "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        snapshot_revision: 2,
        status: "partial",
        profile_id: "profile-1",
        product_validation_snapshot_id: "product-snapshot-1",
        market_research_snapshot_id: "market-snapshot-1",
        dimensions: [
          {
            name: "audience",
            status: "supported",
            evidence_fact_ids: ["fact-1"],
            market_source_ids: [],
            contradiction_ids: [],
            reason_code: "gtm_audience_supported",
            gap_code: null,
          },
        ],
        launch_plan: [
          { horizon: "day_7", experiment_codes: ["clarify_audience"] },
        ],
        finding_ids: [],
        built_at: "2026-08-15T00:00:00Z",
      }),
    /dimensions must contain each startup_gtm@1 dimension exactly once/,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        case_id: "case-1",
        schema_version: "startup_gtm@1",
        snapshot_id: "gtm-snapshot-1",
        snapshot_hash:
          "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        snapshot_revision: 2,
        status: "supported",
        profile_id: "profile-1",
        product_validation_snapshot_id: "product-snapshot-1",
        market_research_snapshot_id: "market-snapshot-1",
        dimensions: [
          {
            name: "audience",
            status: "supported",
            evidence_fact_ids: ["fact-1"],
            market_source_ids: [],
            contradiction_ids: [],
            reason_code: "gtm_audience_supported",
            gap_code: null,
            raw_quote: "not allowed",
          },
        ],
        launch_plan: [
          { horizon: "day_7", experiment_codes: ["clarify_audience"] },
        ],
        finding_ids: [],
        built_at: "2026-08-15T00:00:00Z",
      }),
    ApiContractError,
  );
  assert.throws(
    () =>
      parseStartupGtmResponse({
        case_id: "case-1",
        schema_version: "startup_gtm@1",
        snapshot_id: "gtm-snapshot-1",
        snapshot_hash:
          "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        snapshot_revision: 2,
        status: "supported",
        profile_id: "profile-1",
        product_validation_snapshot_id: "product-snapshot-1",
        market_research_snapshot_id: "market-snapshot-1",
        dimensions: [
          {
            name: "unsupported_dimension",
            status: "supported",
            evidence_fact_ids: [],
            market_source_ids: [],
            contradiction_ids: [],
            reason_code: "gtm_bad",
            gap_code: null,
          },
        ],
        launch_plan: [
          { horizon: "day_120", experiment_codes: ["clarify_audience"] },
        ],
        finding_ids: [],
        built_at: "2026-08-15T00:00:00Z",
      }),
    /dimensions\[0\]\.name|launch_plan\[0\]\.horizon/,
  );
});
