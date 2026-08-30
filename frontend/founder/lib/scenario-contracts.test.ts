import assert from "node:assert/strict";
import test from "node:test";

import {
  parseCopilotStateResponse,
  parseCopilotThreadResponse,
  parseResearchJobResponse,
  parseScenarioProjectionResponse,
  parseStartupScenarioMetric,
} from "./contracts.ts";

const caseId = "11111111-1111-4111-8111-111111111111";
const foreignCaseId = "22222222-2222-4222-8222-222222222222";
const revision = 3;

function projectionMetric(overrides: Record<string, unknown> = {}) {
  return {
    metric_key: "mrr",
    label: "MRR",
    source_type: "deterministic_calculation",
    value: null,
    range: copilotScenarioRange(),
    formula: "mrr",
    dependencies: ["monthly_price", "paying_customers"],
    unit: "KZT/month",
    period: "month",
    confidence: "medium",
    source_refs: [],
    what_would_confirm: "Bank statement or billing export.",
    validation_plan: "Validate against actual revenue data.",
    ...overrides,
  };
}

function copilotScenarioRange(overrides: Record<string, unknown> = {}) {
  return {
    conservative: "7.2E+6:1.47E+7",
    base: "3.6E+4:86666.67",
    optimistic: null,
    ...overrides,
  };
}

function coverage(overrides: Record<string, unknown> = {}) {
  return {
    measure: "source_facts",
    status: "partial",
    source_fact_count: 1,
    accepted_input_count: 2,
    ...overrides,
  };
}

function action(overrides: Record<string, unknown> = {}) {
  return {
    action_id: "33333333-3333-4333-8333-333333333333",
    action: "open_fact_input",
    status: "requires_input",
    handler: "openFactInput",
    reason: "Needs founder input.",
    effect_preview: "Adds a planning input.",
    payload: { field_key: "mrr", provenance: "founder_statement" },
    ...overrides,
  };
}

function backendSourceStatusRows() {
  return [
    {
      field_key: "source_fact",
      kind: "source_fact",
      status: "confirmed",
      value: "",
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
      value: "",
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
      value: "",
      period: null,
      rationale: null,
      validation_plan: null,
      declared_source: null,
      source_refs: [],
    },
    {
      field_key: "deterministic_calculation",
      kind: "deterministic_calculation",
      status: "calculated",
      value: "",
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
      value: "",
      period: null,
      rationale: null,
      validation_plan: null,
      declared_source: null,
      source_refs: [],
    },
    {
      field_key: "contradiction",
      kind: "contradiction",
      status: "conflict_open",
      value: "",
      period: null,
      rationale: null,
      validation_plan: null,
      declared_source: null,
      source_refs: [],
    },
  ];
}

function researchJob(overrides: Record<string, unknown> = {}) {
  return {
    case_id: caseId,
    data_revision: revision,
    job_id: "99999999-9999-4999-8999-999999999999",
    plan_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    plan_hash: "hash",
    status: "completed",
    reason: null,
    acquisition_mode: "live_public_research",
    requested_acquisition_mode: "live_public_research",
    selected_acquisition_mode: "live_public_research",
    accepted_entries: [researchBenchmarkEntry()],
    rejected_entries: [],
    citations: ["https://example.com/public-benchmark"],
    manual_only_keys: ["monthly_recurring_revenue"],
    changed_blocks: ["public_benchmarks", "scenarios"],
    stale_scenario_ids: [],
    old_revision: revision,
    new_revision: revision + 1,
    source_refs: ["77777777-7777-4777-8777-777777777777"],
    updated_at: "2026-08-22T00:00:00Z",
    ...overrides,
  };
}

function researchBenchmarkEntry(overrides: Record<string, unknown> = {}) {
  return {
    entry_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    provenance: "public_benchmark",
    input_key: "acquisition_spend",
    url: "https://example.com/public-benchmark",
    publisher: "Example Research",
    publication_date: "2026-08-01",
    retrieval_date: "2026-08-22",
    as_of: "2026-08-01",
    source_class: "industry_report",
    confidence: "medium",
    value: null,
    range: { low: "1000.00", high: "2000.00" },
    unit: "USD/month",
    period: "month",
    formula: "public benchmark range",
    dependencies: ["public comparable companies"],
    validation_plan: "Use as external context until founder-specific evidence exists.",
    source_refs: ["77777777-7777-4777-8777-777777777777"],
    ...overrides,
  };
}

function copilotState(overrides: Record<string, unknown> = {}) {
  return {
    case_id: caseId,
    data_revision: revision,
    stage: "idea",
    next_question: "What is current MRR?",
    question_descriptor: null,
    suggested_action: "open_fact_input",
    selected_scenario_key: "base",
    extracted_facts: [
      { field_key: "startup_name", value: "FounderCo", source_type: "source_fact" },
    ],
    prioritized_gaps: [
      {
        gap_code: "missing_mrr",
        field_key: "mrr",
        privacy_class: "private",
        allowed_action: "open_fact_input",
      },
    ],
    scenario_metrics: [projectionMetric()],
    fact_coverage: coverage({ measure: "fact_coverage" }),
    scenario_completeness: coverage({ measure: "scenario_completeness" }),
    accepted_inputs: [
      {
        field_key: "mrr",
        kind: "founder_statement",
        status: "accepted",
        value: "1.4m-2m",
        period: "month",
        rationale: "Founder planning assumption.",
        validation_plan: "Validate via billing export.",
        declared_source: "founder",
        source_refs: ["77777777-7777-4777-8777-777777777777"],
      },
    ],
    actions: [action()],
    ...overrides,
  };
}

function scenarioRange(lower = "1400000", upper = "2000000") {
  return { lower, upper };
}

function scenarioMetric(overrides: Record<string, unknown> = {}) {
  return {
    metric_id: "44444444-4444-4444-8444-444444444444",
    case_id: caseId,
    data_revision: revision,
    metric_key: "mrr",
    value_range: scenarioRange(),
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
    rationale: "Derived from scenario inputs.",
    validation_plan: "Validate against billing export.",
    what_would_confirm: "Billing export with paid customer count.",
    acceptance: "needs_validation",
    gaps: [],
    ...overrides,
  };
}

function scenarioInput(inputKey: string, overrides: Record<string, unknown> = {}) {
  const provenance = inputKey === "monthly_price" ? "founder_statement" : "public_benchmark";
  return {
    input_id: crypto.randomUUID(),
    case_id: caseId,
    data_revision: revision,
    input_key: inputKey,
    value_range: inputKey === "monthly_price" ? scenarioRange("35000", "40000") : scenarioRange("40", "50"),
    unit: inputKey === "monthly_price" ? "KZT/month" : "count/month",
    period: "month",
    provenance,
    source_refs: ["77777777-7777-4777-8777-777777777777"],
    dependency_refs: [],
    confidence: "medium",
    rationale: "Scenario planning input.",
    validation_plan: "Validate independently.",
    what_would_confirm: "Independent evidence.",
    acceptance: provenance === "founder_statement" ? "accepted" : "needs_validation",
    ...overrides,
  };
}

function scenarioVariant(scenarioKey: "conservative" | "base" | "optimistic") {
  return {
    scenario_key: scenarioKey,
    inputs: {
      monthly_price: scenarioInput("monthly_price"),
      paying_customers: scenarioInput("paying_customers", {
        provenance: "public_benchmark",
        source_refs: ["77777777-7777-4777-8777-777777777777"],
      }),
    },
    metrics: { mrr: scenarioMetric() },
    gaps: {},
  };
}

function scenarioProjection(overrides: Record<string, unknown> = {}) {
  return {
    scenario_set_id: "88888888-8888-4888-8888-888888888888",
    case_id: caseId,
    data_revision: revision,
    selected_scenario_key: "base",
    scenarios: {
      conservative: scenarioVariant("conservative"),
      base: scenarioVariant("base"),
      optimistic: scenarioVariant("optimistic"),
    },
    fact_coverage: coverage({ measure: "fact_coverage" }),
    scenario_completeness: coverage({ measure: "scenario_completeness" }),
    ...overrides,
  };
}

test("parses Copilot state scenario metric projections without normalizing them into full scenario metrics", () => {
  const parsed = parseCopilotStateResponse(copilotState());

  assert.equal(parsed.case_id, caseId);
  assert.equal(parsed.data_revision, revision);
  assert.equal(parsed.scenario_metrics[0]?.source_type, "deterministic_calculation");
  assert.deepEqual(parsed.scenario_metrics[0]?.range, {
    conservative: "7.2E+6:1.47E+7",
    base: "3.6E+4:86666.67",
    optimistic: null,
  });
  assert.equal(parsed.scenario_metrics[0]?.formula, "mrr");
  assert.deepEqual(parsed.scenario_metrics[0]?.dependencies, [
    "monthly_price",
    "paying_customers",
  ]);
});

test("parses backend Copilot multi-scenario encoded metric ranges verbatim", () => {
  const parsed = parseCopilotStateResponse(
    copilotState({
      scenario_metrics: [
        projectionMetric({
          range: copilotScenarioRange(),
        }),
      ],
    }),
  );

  assert.deepEqual(parsed.scenario_metrics[0]?.range, {
    conservative: "7.2E+6:1.47E+7",
    base: "3.6E+4:86666.67",
    optimistic: null,
  });

  for (const badRange of [
    { base: "3.6E+4:86666.67", optimistic: null },
    { conservative: "7.2E+6:1.47E+7", base: "3.6E+4:86666.67", optimistic: null, stretch: "1:2" },
    { conservative: "7.2E+6:1.47E+7", base: "3.6E+4", optimistic: null },
    { conservative: "7.2E+6:1.47E+7", base: "86666.67:3.6E+4", optimistic: null },
    { conservative: "7.2E+6:1.47E+7", base: "9007199254740993:9007199254740992", optimistic: null },
    {
      conservative: "7.2E+6:1.47E+7",
      base: "9.000000000000003E+15:9.000000000000002E+15",
      optimistic: null,
    },
    { conservative: "7.2E+6:1.47E+7", base: "-1:2", optimistic: null },
    { conservative: "7.2E+6:1.47E+7", base: "1:Infinity", optimistic: null },
  ]) {
    assert.throws(
      () =>
        parseCopilotStateResponse(
          copilotState({
            scenario_metrics: [projectionMetric({ range: badRange })],
          }),
        ),
      /range|scenario|decimal|lower|upper/,
    );
  }

  assert.deepEqual(
    parseCopilotStateResponse(
      copilotState({
        scenario_metrics: [
          projectionMetric({
            range: copilotScenarioRange({
              conservative: null,
              base: null,
              optimistic: null,
            }),
          }),
        ],
      }),
    ).scenario_metrics[0]?.range,
    { conservative: null, base: null, optimistic: null },
  );
});

test("accepts canonical lowercase missing gap codes while rejecting private machine sentinels", () => {
  const parsed = parseCopilotStateResponse(
    copilotState({
      prioritized_gaps: [
        {
          gap_code: "input.missing:monthly_recurring_revenue",
          field_key: "monthly_recurring_revenue",
          privacy_class: "private",
          allowed_action: "open_fact_input",
        },
      ],
    }),
  );

  assert.equal(parsed.prioritized_gaps[0]?.gap_code, "input.missing:monthly_recurring_revenue");

  for (const gapCode of [
    "input.MISSING:monthly_recurring_revenue",
    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "input.token:monthly_recurring_revenue",
    "pitch.pdf",
  ]) {
    assert.throws(
      () =>
        parseCopilotStateResponse(
          copilotState({
            prioritized_gaps: [
              {
                gap_code: gapCode,
                field_key: "monthly_recurring_revenue",
                privacy_class: "private",
                allowed_action: "open_fact_input",
              },
            ],
          }),
        ),
      /gap_code|unsafe advisor code/,
    );
  }
});

test("parses backend Copilot source status rows without treating planning provenance as source facts", () => {
  const parsed = parseCopilotStateResponse(
    copilotState({
      accepted_inputs: [
        ...backendSourceStatusRows(),
        {
          field_key: "mrr",
          kind: "founder_statement",
          status: "accepted",
          value: "1850000; scale=ones; currency=KZT; period=2026-07",
          period: "2026-07",
          rationale: "Founder stated July 2026 recognized MRR excludes unpaid pilots.",
          validation_plan: "Verify against bank deposits and invoice register before source_fact upgrade.",
          declared_source: "Founder interview on 2026-08-22",
          source_refs: ["77777777-7777-4777-8777-777777777777"],
        },
      ],
    }),
  );

  assert.deepEqual(
    Object.fromEntries(parsed.accepted_inputs.slice(0, 6).map((row) => [row.kind, row.status])),
    {
      source_fact: "confirmed",
      founder_statement: "provisional",
      public_benchmark: "external_context",
      deterministic_calculation: "calculated",
      ai_scenario: "planning_assumption",
      contradiction: "conflict_open",
    },
  );
  const founderStatement = parsed.accepted_inputs.at(-1);
  assert.equal(founderStatement?.kind, "founder_statement");
  assert.equal(founderStatement?.status, "accepted");
  assert.notEqual(founderStatement?.kind, "source_fact");
});

test("preserves accepted public benchmark inputs as scenario-capable planning context", () => {
  const benchmarkSourceRef = "88888888-8888-4888-8888-888888888888";
  const parsed = parseCopilotStateResponse(
    copilotState({
      accepted_inputs: [
        backendSourceStatusRows()[2],
        {
          field_key: "monthly_price",
          kind: "public_benchmark",
          status: "accepted",
          value: "1000-2000 USD/month",
          period: "month",
          rationale: "Comparable public tools disclose this pricing band.",
          validation_plan: "Validate against current pricing pages before source_fact upgrade.",
          declared_source: "Public benchmark collection",
          source_refs: [benchmarkSourceRef],
        },
      ],
    }),
  );

  assert.deepEqual(parsed.accepted_inputs[0], {
    field_key: "public_benchmark",
    kind: "public_benchmark",
    status: "external_context",
    value: "",
    period: null,
    rationale: null,
    validation_plan: null,
    declared_source: null,
    source_refs: [],
  });
  assert.deepEqual(parsed.accepted_inputs[1], {
    field_key: "monthly_price",
    kind: "public_benchmark",
    status: "accepted",
    value: "1000-2000 USD/month",
    period: "month",
    rationale: "Comparable public tools disclose this pricing band.",
    validation_plan: "Validate against current pricing pages before source_fact upgrade.",
    declared_source: "Public benchmark collection",
    source_refs: [benchmarkSourceRef],
  });
});

test("rejects source status legend rows with accepted-input metadata", () => {
  for (const badRow of [
    { value: "Evidence-backed fact" },
    { period: "month" },
    { rationale: "Has rationale." },
    { validation_plan: "Has plan." },
    { declared_source: "founder" },
    { source_refs: ["77777777-7777-4777-8777-777777777777"] },
  ]) {
    assert.throws(
      () =>
        parseCopilotStateResponse(
          copilotState({
            accepted_inputs: [{ ...backendSourceStatusRows()[0], ...badRow }],
          }),
        ),
      /legend|metadata|source_refs|value|period|rationale|validation_plan|declared_source/,
    );
  }
});

test("rejects accepted inputs that auto-promote to source facts or omit required source refs", () => {
  const acceptedFounderInput = {
    field_key: "monthly_price",
    kind: "founder_statement",
    status: "accepted",
    value: "1000-2000 USD/month",
    period: "month",
    rationale: "Founder planning assumption.",
    validation_plan: "Validate independently.",
    declared_source: "Founder interview",
    source_refs: ["77777777-7777-4777-8777-777777777777"],
  };

  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotState({
          accepted_inputs: [{ ...acceptedFounderInput, kind: "source_fact" }],
        }),
      ),
    /source_fact/,
  );
  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotState({
          accepted_inputs: [
            {
              ...acceptedFounderInput,
              kind: "public_benchmark",
              source_refs: [],
            },
          ],
        }),
      ),
    /source_refs/,
  );
});

test("rejects malformed Copilot state revisions, ranges, provenance and active action payloads", () => {
  assert.throws(
    () => parseCopilotStateResponse(copilotState({ data_revision: undefined })),
    /data_revision/,
  );
  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotState({
          scenario_metrics: [
            projectionMetric({
              range: copilotScenarioRange({ base: "9:1" }),
            }),
          ],
        }),
      ),
    /range/,
  );
  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotState({
          scenario_metrics: [projectionMetric({ source_type: "ai_guess" })],
        }),
      ),
    /source_type/,
  );
  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotState({
          actions: [action({ payload: {} })],
        }),
      ),
    /payload/,
  );
  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotState({
          actions: [action({ status: "available", result: { ok: true } })],
        }),
      ),
    /result|not allowed/,
  );
});

test("rejects action and thread lineage gaps using active case revision context", () => {
  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotState({
          actions: [
            action({
              action: "open_document_upload",
              status: "available",
              handler: "openDocumentUpload",
              reason: null,
              payload: { case_id: foreignCaseId },
            }),
          ],
        }),
      ),
    /case_id/,
  );
  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotState({
          actions: [
            action({
              action: "prepare_public_research",
              status: "requires_consent",
              handler: "prepareResearchPlan",
              reason: null,
              payload: {
                focus: "public_pricing_analogs",
                expected_case_revision: revision + 1,
                available_acquisition_modes: ["live_public_research", "deterministic_offline_fixture"],
                unavailable_acquisition_modes: [],
                default_acquisition_mode: "live_public_research",
              },
            }),
          ],
        }),
      ),
    /reason|revision/,
  );
  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotState({
          actions: [
            action({
              action: "prepare_public_research",
              status: "requires_consent",
              handler: "prepareResearchPlan",
              reason: "Public research requires consent.",
              payload: {
                focus: "public_pricing_analogs",
                expected_case_revision: revision + 1,
                available_acquisition_modes: ["live_public_research", "deterministic_offline_fixture"],
                unavailable_acquisition_modes: [],
                default_acquisition_mode: "live_public_research",
              },
            }),
          ],
        }),
      ),
    /revision/,
  );
  assert.throws(
    () =>
      parseCopilotThreadResponse({
        thread_id: "99999999-9999-4999-8999-999999999999",
        case_id: caseId,
        data_revision: revision,
        messages: [
          {
            message_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            case_id: caseId,
            data_revision: revision,
            role: "assistant",
            content: "Use actions.",
            page_context: "overview",
            current_section: "question",
            idempotency_fingerprint: null,
            related_evidence_refs: [],
            question_refs: [],
            action_refs: ["bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"],
            action_snapshots: [action()],
            action_result: null,
          },
        ],
      }),
    /action_refs/,
  );
});

test("parses full scenario projections with distinct metric provenance and formula metadata", () => {
  const parsed = parseScenarioProjectionResponse(scenarioProjection());

  assert.equal(parsed.case_id, caseId);
  assert.equal(parsed.scenarios.base.metrics.mrr.provenance, "deterministic_calculation");
  assert.deepEqual(parsed.scenarios.base.metrics.mrr.value_range, {
    lower: "1400000",
    upper: "2000000",
  });
  assert.equal(parsed.scenarios.base.metrics.mrr.formula_key, "mrr");
  assert.equal(
    parsed.scenarios.base.metrics.mrr.formula_description,
    "monthly_price * paying_customers",
  );
  assert.deepEqual(parsed.scenarios.base.metrics.mrr.dependency_refs, [
    "55555555-5555-4555-8555-555555555555",
    "66666666-6666-4666-8666-666666666666",
  ]);
});

test("parses full scenario projection scientific ranges verbatim with backend decimal semantics", () => {
  const parsed = parseScenarioProjectionResponse(
    scenarioProjection({
      scenarios: {
        conservative: {
          ...scenarioVariant("conservative"),
          inputs: {
            monthly_price: scenarioInput("monthly_price", {
              value_range: scenarioRange("3.6E+4", "86666.67"),
            }),
            paying_customers: scenarioInput("paying_customers", {
              value_range: scenarioRange("40", "50"),
            }),
          },
        },
        base: {
          ...scenarioVariant("base"),
          metrics: {
            mrr: scenarioMetric({
              value_range: scenarioRange("1.4E+6", "2E+6"),
            }),
          },
        },
        optimistic: scenarioVariant("optimistic"),
      },
    }),
  );

  assert.deepEqual(parsed.scenarios.base.metrics.mrr.value_range, {
    lower: "1.4E+6",
    upper: "2E+6",
  });
  assert.deepEqual(parsed.scenarios.conservative.inputs.monthly_price.value_range, {
    lower: "3.6E+4",
    upper: "86666.67",
  });
});

test("rejects invalid full scenario ranges without using floating point ordering", () => {
  for (const value_range of [
    scenarioRange("1.234", "2"),
    scenarioRange("-1", "2"),
    scenarioRange("Infinity", "2"),
    scenarioRange("9.000000000000003E+15", "9.000000000000002E+15"),
    scenarioRange("1.234E+0", "2E+0"),
  ]) {
    assert.throws(
      () =>
        parseStartupScenarioMetric(
          scenarioMetric({ value_range }),
          caseId,
          revision,
          "metrics.mrr",
        ),
      /range|decimal|non-negative|lower|upper/,
    );
  }
});

test("rejects cross-case scenario identifiers and unsupported scenario metric provenance", () => {
  assert.throws(
    () => parseStartupScenarioMetric(scenarioMetric({ provenance: "ai_guess" }), caseId, revision, "metrics.mrr"),
    /provenance/,
  );
  assert.throws(
    () =>
      parseStartupScenarioMetric(
        scenarioMetric({ provenance: "source_fact", source_refs: [] }),
        caseId,
        revision,
        "metrics.mrr",
      ),
    /source refs/,
  );
  assert.throws(
    () =>
      parseScenarioProjectionResponse(
        scenarioProjection({
          scenarios: {
            conservative: scenarioVariant("conservative"),
            base: {
              ...scenarioVariant("base"),
              metrics: { mrr: scenarioMetric({ case_id: foreignCaseId }) },
            },
            optimistic: scenarioVariant("optimistic"),
          },
        }),
      ),
    /case_id/,
  );
  assert.throws(
    () =>
      parseScenarioProjectionResponse(
        scenarioProjection({
          scenarios: {
            conservative: scenarioVariant("conservative"),
            base: {
              ...scenarioVariant("base"),
              metrics: {
                mrr: scenarioMetric({
                  data_revision: revision + 1,
                }),
              },
            },
            optimistic: scenarioVariant("optimistic"),
          },
        }),
      ),
    /data_revision/,
  );
});

test("matches backend scenario and research benchmark range/source semantics", () => {
  assert.deepEqual(
    parseResearchJobResponse(researchJob()).accepted_entries[0]?.range,
    { low: "1000.00", high: "2000.00" },
  );
  assert.throws(
    () =>
      parseStartupScenarioMetric(
        scenarioMetric({
          unit: "KZT/month",
          period: "quarter",
        }),
        caseId,
        revision,
        "metrics.mrr",
      ),
    /period|unit/,
  );
  assert.throws(
    () =>
      parseScenarioProjectionResponse(
        scenarioProjection({
          scenarios: {
            conservative: scenarioVariant("conservative"),
            base: {
              ...scenarioVariant("base"),
              inputs: {
                monthly_price: scenarioInput("monthly_price", {
                  provenance: "founder_statement",
                  acceptance: "needs_validation",
                  source_refs: ["77777777-7777-4777-8777-777777777777"],
                }),
              },
              metrics: { mrr: scenarioMetric() },
            },
            optimistic: scenarioVariant("optimistic"),
          },
        }),
      ),
    /accepted/,
  );
});

test("research job parser requires a strict acquisition mode", () => {
  const missingMode: Record<string, unknown> = { ...researchJob() };
  delete missingMode.acquisition_mode;

  assert.throws(
    () => parseResearchJobResponse(missingMode),
    /acquisition_mode/,
  );

  for (const acquisition_mode of [
    "live",
    "deterministic_offline",
    "configured",
    "unknown",
    null,
  ]) {
    assert.throws(
      () => parseResearchJobResponse(researchJob({ acquisition_mode })),
      /acquisition_mode/,
    );
  }

  for (const field of ["requested_acquisition_mode", "selected_acquisition_mode"]) {
    const missingRequestedOrSelected: Record<string, unknown> = { ...researchJob() };
    delete missingRequestedOrSelected[field];
    assert.throws(
      () => parseResearchJobResponse(missingRequestedOrSelected),
      new RegExp(field),
    );

    assert.throws(
      () => parseResearchJobResponse(researchJob({ [field]: "unknown" })),
      new RegExp(field),
    );
  }
});

test("accepts backend research job requested and selected acquisition modes", () => {
  const parsed = parseResearchJobResponse(
    researchJob({
      acquisition_mode: "live_public_research",
      requested_acquisition_mode: "live_public_research",
      selected_acquisition_mode: "live_public_research",
    }),
  );

  assert.equal(parsed.requested_acquisition_mode, "live_public_research");
  assert.equal(parsed.selected_acquisition_mode, "live_public_research");
});

test("accepts live public benchmark entries without a publication date", () => {
  const parsed = parseResearchJobResponse(
    researchJob({
      accepted_entries: [
        researchBenchmarkEntry({
          publication_date: null,
          retrieval_date: "2026-08-25",
          as_of: "2026-08-25",
        }),
      ],
    }),
  );

  assert.equal(parsed.accepted_entries[0]?.publication_date, null);
  assert.equal(parsed.accepted_entries[0]?.retrieval_date, "2026-08-25");
});

test("accepts bounded human-readable live research source classes", () => {
  const parsed = parseResearchJobResponse(
    researchJob({
      accepted_entries: [
        researchBenchmarkEntry({
          source_class: "official pricing page",
        }),
      ],
    }),
  );

  assert.equal(parsed.accepted_entries[0]?.source_class, "official pricing page");
});

test("accepts bounded human-readable research benchmark dependencies without weakening scenario metric refs", () => {
  assert.deepEqual(
    parseResearchJobResponse(
      researchJob({
        accepted_entries: [
          researchBenchmarkEntry({
            dependencies: ["public comparable companies"],
          }),
        ],
      }),
    ).accepted_entries[0]?.dependencies,
    ["public comparable companies"],
  );

  for (const dependencies of [[""], ["   "], ["x".repeat(1001)]]) {
    assert.throws(
      () =>
        parseResearchJobResponse(
          researchJob({
            accepted_entries: [
              researchBenchmarkEntry({
                dependencies,
              }),
            ],
          }),
        ),
      /dependencies/,
    );
  }
});

test("validates exact research benchmark values with numeric range rules and XOR shape", () => {
  assert.equal(
    parseResearchJobResponse(
      researchJob({
        accepted_entries: [
          researchBenchmarkEntry({
            value: "1500.00",
            range: { low: null, high: null },
          }),
        ],
      }),
    ).accepted_entries[0]?.value,
    "1500.00",
  );

  for (const value of ["-1", "1.234", "not a number"]) {
    assert.throws(
      () =>
        parseResearchJobResponse(
          researchJob({
            accepted_entries: [
              researchBenchmarkEntry({
                value,
                range: { low: null, high: null },
              }),
            ],
          }),
        ),
      /value|decimal|non-negative/,
    );
  }

  for (const entry of [
    researchBenchmarkEntry({ value: "1500.00", range: { low: "1000.00", high: "2000.00" } }),
    researchBenchmarkEntry({ value: null, range: { low: "1000.00", high: null } }),
    researchBenchmarkEntry({ value: null, range: { low: null, high: null } }),
  ]) {
    assert.throws(
      () => parseResearchJobResponse(researchJob({ accepted_entries: [entry] })),
      /range|value|exclusive|both/,
    );
  }
});
