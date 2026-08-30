import assert from "node:assert/strict";
import test from "node:test";

import type { ResearchJobResponse } from "./contracts.ts";
import {
  ApiContractError,
  parseCopilotStateResponse,
  type CopilotQuestionDescriptor,
} from "./contracts.ts";
import {
  buildCaseCopilotManualAssumptionRequest,
  buildCaseCopilotPublicResearchModeChoices,
  buildCaseCopilotResearchJobPresentation,
  buildCaseCopilotSubmitPayload,
  caseCopilotOperationFailureMessage,
  caseCopilotSubmitFailureMessage,
  deriveCaseCopilotResearchConsentScope,
  isCaseCopilotManualAssumptionComplete,
  presentPublicResearchPreRunCopy,
  presentCaseCopilotQuestionInputSchema,
  resetCaseCopilotManualDraftForQuestionChange,
} from "./case-copilot-presentation.ts";

function researchJobResponse(
  overrides: Partial<ResearchJobResponse> = {},
): ResearchJobResponse {
  return {
    case_id: "11111111-1111-4111-8111-111111111111",
    data_revision: 4,
    job_id: "34343434-3434-4343-8343-343434343434",
    plan_id: "12121212-1212-4121-8121-121212121212",
    plan_hash: "sha256:task-d-plan",
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

const questionDescriptor: CopilotQuestionDescriptor = {
  question_id: "11111111-1111-4111-8111-111111111111",
  field_key: "buyer",
  question: "Кто экономический покупатель Smart University?",
  label: "Экономический покупатель",
  description: "Роль или команда, которая утверждает покупку.",
  why_needed: "Это нужно, чтобы выбрать канал продаж и доказательство боли.",
  unlocks: ["purchase_trigger", "channel"],
  unlocks_copy: "Этот ответ открывает: Причина покупки сейчас, Канал продаж.",
  example: "Например: проректор по академическим программам.",
  validation_guidance: "Укажите роль и источник ответа; пример не является данными кейса.",
  provenance: "founder_statement",
  input_schema: {
    kind: "text",
    fields: [
      {
        field_key: "value",
        label: "Ответ",
        input_kind: "text",
        required: true,
        placeholder: "Например: проректор по академическим программам",
      },
      {
        field_key: "declared_source",
        label: "Откуда ответ",
        input_kind: "text",
        required: true,
        placeholder: "Например: интервью с основателем",
      },
      {
        field_key: "rationale",
        label: "Почему это важно",
        input_kind: "text",
        required: true,
        placeholder: "Например: влияет на канал продаж",
      },
      {
        field_key: "validation_plan",
        label: "Как проверить",
        input_kind: "text",
        required: true,
        placeholder: "Например: подтвердить в CRM или письме",
      },
    ],
  },
};

function copilotStatePayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    case_id: "22222222-2222-4222-8222-222222222222",
    data_revision: 4,
    stage: "idea",
    next_question: questionDescriptor.question,
    question_descriptor: questionDescriptor,
    suggested_action: "open_fact_input",
    selected_scenario_key: "base",
    extracted_facts: [],
    prioritized_gaps: [],
    scenario_metrics: [],
    fact_coverage: {
      measure: "evidence-backed",
      status: "partial",
      source_fact_count: 0,
      accepted_input_count: null,
    },
    scenario_completeness: {
      measure: "planning-model",
      status: "draft",
      source_fact_count: null,
      accepted_input_count: 0,
    },
    accepted_inputs: [],
    actions: [
      {
        action_id: "33333333-3333-4333-8333-333333333333",
        action: "open_fact_input",
        status: "requires_input",
        handler: "openFactInput",
        reason: "Нужен ответ основателя.",
        effect_preview: "Открыть ручной ввод для buyer.",
        payload: {
          field_key: "buyer",
          provenance: "founder_statement",
        },
      },
    ],
    ...overrides,
  };
}

const moneyDescriptorWithoutPeriod = {
  ...questionDescriptor,
  field_key: "available_budget",
  question: "Какой бюджет доступен для запуска?",
  label: "Доступный бюджет",
  input_schema: {
    kind: "money",
    fields: [
      { field_key: "amount", label: "Сумма", input_kind: "decimal", required: true, placeholder: "Введите сумму" },
      { field_key: "scale", label: "Масштаб", input_kind: "select", required: true, placeholder: "Выберите масштаб" },
      { field_key: "currency", label: "Валюта", input_kind: "text", required: true, placeholder: "KZT" },
      { field_key: "declared_source", label: "Источник", input_kind: "text", required: true, placeholder: "Например: интервью" },
      { field_key: "rationale", label: "Почему важно", input_kind: "text", required: true, placeholder: "Например: влияет на runway" },
      { field_key: "validation_plan", label: "Как проверить", input_kind: "text", required: true, placeholder: "Например: финансовый план" },
    ],
  },
} as CopilotQuestionDescriptor;

const moneyDescriptorWithOptionalPeriod = {
  ...moneyDescriptorWithoutPeriod,
  input_schema: {
    kind: "money",
    fields: [
      ...moneyDescriptorWithoutPeriod.input_schema.fields,
      { field_key: "period", label: "Период", input_kind: "month", required: false, placeholder: "Если есть месяц" },
    ],
  },
} as CopilotQuestionDescriptor;

test("parses the exact structured question descriptor and preserves legacy next_question", () => {
  const parsed = parseCopilotStateResponse(copilotStatePayload());

  assert.equal(parsed.next_question, questionDescriptor.question);
  assert.deepEqual(parsed.question_descriptor, questionDescriptor);
  assert.equal(parsed.actions[0]?.payload.field_key, parsed.question_descriptor?.field_key);
});

test("rejects structured question descriptors that do not match open_fact_input", () => {
  assert.throws(
    () =>
      parseCopilotStateResponse(
        copilotStatePayload({
          actions: [
            {
              action_id: "33333333-3333-4333-8333-333333333333",
              action: "open_fact_input",
              status: "requires_input",
              handler: "openFactInput",
              reason: "Нужен ответ основателя.",
              effect_preview: "Открыть ручной ввод для mrr.",
              payload: {
                field_key: "mrr",
                provenance: "founder_statement",
              },
            },
          ],
        }),
      ),
    (error: unknown) =>
      error instanceof ApiContractError &&
      /question_descriptor.*open_fact_input.*field_key/iu.test(error.message),
  );
});

test("builds a text founder-statement assumption from backend input schema without money defaults", () => {
  const request = buildCaseCopilotManualAssumptionRequest({
    declaredSource: "интервью с основателем",
    expectedRevision: 4,
    fieldKey: "buyer",
    questionDescriptor,
    rationale: "помогает выбрать канал продаж",
    textValue: "проректор по академическим программам",
    validationPlan: "подтвердить в CRM",
  });

  assert.equal(request.requirement_key, "buyer");
  assert.deepEqual(request.value, {
    kind: "text",
    value: "проректор по академическим программам",
  });
  assert.equal(request.period, null);
  assert.equal(request.source.kind, "founder_statement");
  assert.equal(request.source.declared_source, "интервью с основателем");
  assert.equal(JSON.stringify(request), JSON.stringify(request).replace(/source_fact/u, ""));
});

test("presents backend-provided input schema labels placeholders required flags and field presence", () => {
  const schema = presentCaseCopilotQuestionInputSchema({
    ...questionDescriptor,
    input_schema: {
      kind: "text",
      fields: [
        {
          field_key: "value",
          label: "Короткий ответ владельца",
          input_kind: "text",
          required: true,
          placeholder: "Введите роль покупателя",
        },
        {
          field_key: "declared_source",
          label: "Источник ответа",
          input_kind: "text",
          required: true,
          placeholder: "Например: интервью",
        },
      ],
    },
  } as CopilotQuestionDescriptor);

  assert.deepEqual(schema.fields.map((field) => field.fieldKey), ["value", "declared_source"]);
  assert.equal(schema.fields[0]?.label, "Короткий ответ владельца");
  assert.equal(schema.fields[0]?.placeholder, "Введите роль покупателя");
  assert.equal(schema.fields[0]?.requiredLabel, "обязательно");
  assert.equal(schema.fields.some((field) => field.fieldKey === "period"), false);
  assert.match(schema.unlocksCopy, /открывает: Причина покупки сейчас, Канал продаж/iu);
});

test("uses backend-owned unlocks copy without leaking raw unlock codes", () => {
  const cases = [
    {
      unlocks: ["icp_decision", "purchase_trigger"],
      unlocks_copy: "Этот ответ открывает: выбор целевого сегмента и причину покупки сейчас.",
    },
    {
      unlocks: ["mrr", "revenue", "scenario_pricing"],
      unlocks_copy: "Этот ответ открывает: MRR, выручку и ценовой сценарий.",
    },
    {
      unlocks: ["public_research_plan", "funnel"],
      unlocks_copy: "Этот ответ открывает: план публичного поиска и воронку продаж.",
    },
  ];

  for (const item of cases) {
    const schema = presentCaseCopilotQuestionInputSchema({
      ...questionDescriptor,
      unlocks: item.unlocks,
      unlocks_copy: item.unlocks_copy,
    } as CopilotQuestionDescriptor);

    assert.equal(schema.unlocksCopy, item.unlocks_copy);
    assert.doesNotMatch(schema.unlocksCopy, /icp_decision|scenario_pricing|public_research_plan/u);
  }
});

test("parses money question descriptors without period when schema omits it", () => {
  const parsed = parseCopilotStateResponse(
    copilotStatePayload({
      next_question: moneyDescriptorWithoutPeriod.question,
      question_descriptor: moneyDescriptorWithoutPeriod,
      actions: [
        {
          action_id: "33333333-3333-4333-8333-333333333333",
          action: "open_fact_input",
          status: "requires_input",
          handler: "openFactInput",
          reason: "Нужен ответ основателя.",
          effect_preview: "Открыть ручной ввод для available_budget.",
          payload: {
            field_key: "available_budget",
            provenance: "founder_statement",
          },
        },
      ],
    }),
  );

  assert.deepEqual(
    parsed.question_descriptor?.input_schema.fields.map((field) => field.field_key),
    ["amount", "scale", "currency", "declared_source", "rationale", "validation_plan"],
  );
});

test("does not require or submit a blank optional money period", () => {
  const fields = {
    amount: "5000000",
    scale: "ones",
    currency: "KZT",
    periodMonth: "",
    declaredSource: "интервью",
    rationale: "влияет на runway",
    validationPlan: "сверить с финансовым планом",
  };

  assert.equal(isCaseCopilotManualAssumptionComplete(fields, moneyDescriptorWithoutPeriod), true);
  assert.equal(isCaseCopilotManualAssumptionComplete(fields, moneyDescriptorWithOptionalPeriod), true);
  assert.equal(
    buildCaseCopilotManualAssumptionRequest({
      ...fields,
      expectedRevision: 4,
      fieldKey: "available_budget",
      questionDescriptor: moneyDescriptorWithoutPeriod,
    }).period,
    null,
  );
  assert.equal(
    buildCaseCopilotManualAssumptionRequest({
      ...fields,
      expectedRevision: 4,
      fieldKey: "available_budget",
      questionDescriptor: moneyDescriptorWithOptionalPeriod,
    }).period,
    null,
  );
});

test("requires money scale and currency from backend input schema", () => {
  const fields = {
    amount: "5000000",
    scale: "ones",
    currency: "KZT",
    periodMonth: "",
    declaredSource: "интервью",
    rationale: "влияет на runway",
    validationPlan: "сверить с финансовым планом",
  };

  assert.equal(isCaseCopilotManualAssumptionComplete(fields, moneyDescriptorWithoutPeriod), true);

  for (const blankRequiredField of [
    "amount",
    "scale",
    "currency",
    "declaredSource",
    "rationale",
    "validationPlan",
  ] as const) {
    assert.equal(
      isCaseCopilotManualAssumptionComplete(
        { ...fields, [blankRequiredField]: "" },
        moneyDescriptorWithoutPeriod,
      ),
      false,
      `${blankRequiredField} is required by backend schema`,
    );
  }
});

test("requires and submits period only when money schema marks period required", () => {
  const requiredPeriodDescriptor = {
    ...moneyDescriptorWithOptionalPeriod,
    input_schema: {
      kind: "money",
      fields: moneyDescriptorWithOptionalPeriod.input_schema.fields.map((field) =>
        field.field_key === "period" ? { ...field, required: true } : field,
      ),
    },
  } as CopilotQuestionDescriptor;
  const fields = {
    amount: "5000000",
    scale: "ones",
    currency: "KZT",
    periodMonth: "",
    declaredSource: "интервью",
    rationale: "влияет на runway",
    validationPlan: "сверить с финансовым планом",
  };

  assert.equal(isCaseCopilotManualAssumptionComplete(fields, requiredPeriodDescriptor), false);
  assert.deepEqual(
    buildCaseCopilotManualAssumptionRequest({
      ...fields,
      periodMonth: "2026-07",
      expectedRevision: 4,
      fieldKey: "available_budget",
      questionDescriptor: requiredPeriodDescriptor,
    }).period,
    {
      kind: "month",
      value: "2026-07",
      start: null,
      end: null,
    },
  );
});

test("normalizes descriptor-null legacy aliases before manual assumption submit", () => {
  const mrrRequest = buildCaseCopilotManualAssumptionRequest({
    amount: "1850000",
    currency: "KZT",
    declaredSource: "интервью",
    expectedRevision: 4,
    fieldKey: "monthly_recurring_revenue",
    periodMonth: "2026-07",
    rationale: "планирование",
    scale: "ones",
    validationPlan: "сверить с CRM",
  });
  const burnRequest = buildCaseCopilotManualAssumptionRequest({
    amount: "700000",
    currency: "KZT",
    declaredSource: "интервью",
    expectedRevision: 4,
    fieldKey: "monthly_net_burn",
    periodMonth: "2026-07",
    rationale: "планирование runway",
    scale: "ones",
    validationPlan: "сверить с финансами",
  });

  assert.equal(mrrRequest.requirement_key, "mrr");
  assert.equal(mrrRequest.idempotency_key, "copilot-assumption:mrr:rev:4");
  assert.equal(burnRequest.requirement_key, "burn");
  assert.equal(burnRequest.idempotency_key, "copilot-assumption:burn:rev:4");
});

test("resets manual draft when rerendered with a different text question identity", () => {
  const previousDraft = {
    amount: "проректор по академическим программам",
    scale: "",
    currency: "",
    periodMonth: "",
    declaredSource: "интервью",
    rationale: "важно для продаж",
    validationPlan: "проверить в CRM",
  };
  const nextDescriptor: CopilotQuestionDescriptor = {
    ...questionDescriptor,
    question_id: "44444444-4444-4444-8444-444444444444",
    field_key: "purchase_trigger",
    question: "Что запускает покупку сейчас?",
    label: "Причина покупки сейчас",
  };

  assert.deepEqual(
    resetCaseCopilotManualDraftForQuestionChange(questionDescriptor, nextDescriptor, previousDraft),
    {
      amount: "",
      scale: "",
      currency: "",
      periodMonth: "",
      declaredSource: "",
      rationale: "",
      validationPlan: "",
    },
  );
});

test("resets money draft when rerendered with a text question identity", () => {
  const moneyDescriptor: CopilotQuestionDescriptor = {
    ...questionDescriptor,
    field_key: "mrr",
    label: "MRR",
    input_schema: {
      kind: "money",
      fields: [
        { field_key: "amount", label: "Сумма", input_kind: "decimal", required: true, placeholder: "Сумма" },
        { field_key: "scale", label: "Масштаб", input_kind: "select", required: true, placeholder: "Масштаб" },
        { field_key: "currency", label: "Валюта", input_kind: "text", required: true, placeholder: "Валюта" },
        { field_key: "period", label: "Период", input_kind: "month", required: true, placeholder: "Период" },
        { field_key: "declared_source", label: "Источник", input_kind: "text", required: true, placeholder: "Источник" },
        { field_key: "rationale", label: "Зачем", input_kind: "text", required: true, placeholder: "Зачем" },
        { field_key: "validation_plan", label: "Проверка", input_kind: "text", required: true, placeholder: "Проверка" },
      ],
    },
  };
  const previousDraft = {
    amount: "1850000",
    scale: "ones",
    currency: "KZT",
    periodMonth: "2026-07",
    declaredSource: "интервью",
    rationale: "планирование",
    validationPlan: "сверить",
  };

  assert.deepEqual(
    resetCaseCopilotManualDraftForQuestionChange(moneyDescriptor, questionDescriptor, previousDraft),
    {
      amount: "",
      scale: "",
      currency: "",
      periodMonth: "",
      declaredSource: "",
      rationale: "",
      validationPlan: "",
    },
  );
});

test("public research post-submit failure points to the displayed reason without consent instructions", () => {
  const message = caseCopilotSubmitFailureMessage("public_research");

  assert.match(message, /причин/u);
  assert.match(message, /повтор/iu);
  assert.doesNotMatch(message, /согласие/iu);
  assert.doesNotMatch(message, /провайдер|ориентир|контракт/iu);
});

test("maps online research budget failures to actionable founder-safe copy", () => {
  const message = caseCopilotOperationFailureMessage(
    "public_research",
    Object.assign(new Error("private provider detail"), { code: "BUDGET_EXCEEDED" }),
  );

  assert.match(message, /лимит онлайн-ресерча исчерпан/iu);
  assert.match(message, /сохранённ/iu);
  assert.match(message, /новый OpenAI-запрос не выполнен/iu);
  assert.doesNotMatch(message, /private provider detail|согласие/iu);
});

test("presents distinct founder-safe recovery copy for terminal public research outcomes", () => {
  const cases = [
    {
      name: "provider_unconfigured",
      job: researchJobResponse({
        status: "deferred",
        reason: "provider_unconfigured",
        acquisition_mode: "provider_unconfigured",
        accepted_entries: [],
        changed_blocks: [],
        citations: [],
        source_refs: [],
      }),
      wantLabel: /провайдер публичного поиска не настроен/iu,
      wantDescription: /данные кейса и сценарии не изменились/iu,
    },
    {
      name: "stale_research_plan",
      job: researchJobResponse({
        status: "deferred",
        reason: "stale_research_plan",
        accepted_entries: [],
        changed_blocks: [],
        citations: [],
        source_refs: [],
      }),
      wantLabel: /план публичного поиска устарел/iu,
      wantDescription: /подготовьте новый план для текущей версии кейса/iu,
    },
    {
      name: "provider_failed",
      job: researchJobResponse({
        status: "failed",
        reason: "provider_failed",
        accepted_entries: [],
        changed_blocks: [],
        citations: [],
        source_refs: [],
      }),
      wantLabel: /ошибкой провайдера/iu,
      wantDescription: /согласие относится только к одному запуску/iu,
    },
    {
      name: "no_eligible_public_benchmarks",
      job: researchJobResponse({
        status: "deferred",
        reason: "no_eligible_public_benchmarks",
        accepted_entries: [],
        changed_blocks: [],
        citations: [],
        source_refs: [],
      }),
      wantLabel: /ориентир не принят/iu,
      wantDescription: /не дали безопасного ориентира для сценария/iu,
    },
    {
      name: "invalid_benchmark_entry",
      job: researchJobResponse({
        status: "deferred",
        reason: "no_eligible_public_benchmarks",
        accepted_entries: [],
        rejected_entries: [
          {
            rejected_id: "67676767-6767-4676-8676-676767676767",
            reason_code: "invalid_benchmark_entry",
            input_key: "monthly_price",
            provenance: "public_benchmark",
            metadata: { contract_error: "range_missing" },
          },
        ],
        changed_blocks: [],
        citations: [],
        source_refs: [],
      }),
      wantLabel: /неподходящий формат ориентира/iu,
      wantDescription: /не прошёл контракт/iu,
    },
    {
      name: "research_interrupted",
      job: researchJobResponse({
        status: "running",
        reason: "research_interrupted",
        accepted_entries: [],
        changed_blocks: [],
        citations: [],
        source_refs: [],
      }),
      wantLabel: /поиск был прерван/iu,
      wantDescription: /прерванный запуск не менял факты и сценарии/iu,
    },
  ];

  for (const item of cases) {
    const presentation = buildCaseCopilotResearchJobPresentation(item.job);
    assert.match(presentation.label, item.wantLabel, item.name);
    assert.match(presentation.description, item.wantDescription, item.name);
    assert.doesNotMatch(presentation.description, /проверьте согласие/iu, item.name);
    assert.match(presentation.description, /факт|данные кейса|версии кейса/iu, item.name);
  }
});

test("presents exhaustive mode-sensitive public research copy without implying offline Internet access", () => {
  const offline = buildCaseCopilotResearchJobPresentation(
    researchJobResponse({
      acquisition_mode: "deterministic_offline_fixture",
      accepted_entries: [
        {
          ...researchJobResponse().accepted_entries[0]!,
          publisher: "Deterministic Case Copilot Fixture",
          url: "https://example.com/case-copilot-deterministic-benchmark",
          retrieval_date: "2026-08-23",
        },
      ],
      citations: ["https://example.com/case-copilot-deterministic-benchmark"],
    }),
  );

  assert.match(offline.label, /офлайн|offline|демо|фикстур/iu);
  assert.match(offline.description, /детерминирован/iu);
  assert.match(offline.description, /без интернет-запроса|no internet/iu);
  assert.doesNotMatch(offline.description, /live|живой|интернет-поиск|искал[аи]? в интернете/iu);
  assert.equal(offline.acquisitionMode, "deterministic_offline_fixture");
  assert.match(offline.modeLabel, /офлайн|offline|фикстур/iu);
  assert.equal(offline.acceptedSourceSummaries[0]?.sourceLabel, "Deterministic Case Copilot Fixture");
  assert.equal(offline.acceptedSourceSummaries[0]?.sourceUrl, "https://example.com/case-copilot-deterministic-benchmark");
  assert.equal(offline.acceptedSourceSummaries[0]?.sourceDomain, "example.com");
  assert.equal(offline.acceptedSourceSummaries[0]?.retrievalDate, "2026-08-23");

  const live = buildCaseCopilotResearchJobPresentation(
    researchJobResponse({ acquisition_mode: "live_public_research" }),
  );
  assert.equal(live.acquisitionMode, "live_public_research");
  assert.match(live.label, /live|интернет/iu);
  assert.match(live.description, /публичн.*интернет|internet/iu);

  const unconfigured = buildCaseCopilotResearchJobPresentation(
    researchJobResponse({
      status: "deferred",
      reason: "provider_unconfigured",
      acquisition_mode: "provider_unconfigured",
      accepted_entries: [],
      changed_blocks: [],
      citations: [],
      source_refs: [],
    }),
  );
  assert.equal(unconfigured.acquisitionMode, "provider_unconfigured");
  assert.match(unconfigured.label, /провайдер публичного поиска не настроен/iu);
  assert.match(unconfigured.description, /безопасн.*ручн|отлож/iu);
});

test("presents provider-status-specific public research copy before a run", () => {
  const offline = presentPublicResearchPreRunCopy("deterministic_offline_fixture");
  assert.equal(offline.tabLabel, "Офлайн-демо");
  assert.match(offline.description, /не обращается к интернету/iu);
  assert.match(offline.buttonLabel, /офлайн-демо/iu);
  assert.doesNotMatch(offline.description, /live-поиск|ищет в интернете/iu);

  const live = presentPublicResearchPreRunCopy("configured");
  assert.equal(live.tabLabel, "Live-поиск");
  assert.match(live.description, /публичному интернету/iu);
  assert.match(live.buttonLabel, /live-поиск/iu);

  for (const status of ["unavailable", null] as const) {
    const unavailable = presentPublicResearchPreRunCopy(status);
    assert.equal(unavailable.tabLabel, "Без live-провайдера");
    assert.match(unavailable.description, /не настроен/iu);
    assert.match(unavailable.description, /интернет-запрос не выполняется/iu);
  }
});

test("presents explicit adjacent online and offline public research mode choices", () => {
  const action = parseCopilotStateResponse(
    copilotStatePayload({
      actions: [
        {
          action_id: "44444444-4444-4444-8444-444444444444",
          action: "open_fact_input",
          status: "requires_input",
          handler: "openFactInput",
          reason: "Нужен ответ основателя.",
          effect_preview: "Открыть ручной ввод для buyer.",
          payload: {
            field_key: "buyer",
            provenance: "founder_statement",
          },
        },
        {
          action_id: "33333333-3333-4333-8333-333333333333",
          action: "prepare_public_research",
          status: "requires_consent",
          handler: "prepareResearchPlan",
          reason: "Public research requires consent.",
          effect_preview: "Prepare public benchmark research.",
          payload: {
            focus: "public_pricing_analogs",
            expected_case_revision: 4,
            available_acquisition_modes: [
              "live_public_research",
              "deterministic_offline_fixture",
            ],
            unavailable_acquisition_modes: [],
            default_acquisition_mode: "live_public_research",
          },
        },
      ],
    }),
  ).actions.find((candidate) => candidate.action === "prepare_public_research") ?? null;

  const choices = buildCaseCopilotPublicResearchModeChoices(action);

  assert.deepEqual(
    choices.map((choice) => [
      choice.mode,
      choice.label,
      choice.available,
      choice.selectedByDefault,
    ]),
    [
      ["live_public_research", "Онлайн-ресерч", true, true],
      ["deterministic_offline_fixture", "Офлайн-демо", true, false],
    ],
  );
  assert.match(choices[0]?.description ?? "", /санитизированный публичный запрос/iu);
  assert.match(choices[0]?.description ?? "", /частные документы и ответы не отправляются/iu);
  assert.match(choices[1]?.description ?? "", /без интернета/iu);
});

test("keeps unavailable online visible disabled and selects offline by default", () => {
  const action = parseCopilotStateResponse(
    copilotStatePayload({
      actions: [
        {
          action_id: "44444444-4444-4444-8444-444444444444",
          action: "open_fact_input",
          status: "requires_input",
          handler: "openFactInput",
          reason: "Нужен ответ основателя.",
          effect_preview: "Открыть ручной ввод для buyer.",
          payload: {
            field_key: "buyer",
            provenance: "founder_statement",
          },
        },
        {
          action_id: "33333333-3333-4333-8333-333333333333",
          action: "prepare_public_research",
          status: "requires_consent",
          handler: "prepareResearchPlan",
          reason: "Public research requires consent.",
          effect_preview: "Prepare public benchmark research.",
          payload: {
            focus: "public_pricing_analogs",
            expected_case_revision: 4,
            available_acquisition_modes: ["deterministic_offline_fixture"],
            unavailable_acquisition_modes: ["live_public_research"],
            default_acquisition_mode: "deterministic_offline_fixture",
          },
        },
      ],
    }),
  ).actions.find((candidate) => candidate.action === "prepare_public_research") ?? null;

  const choices = buildCaseCopilotPublicResearchModeChoices(action);

  assert.deepEqual(
    choices.map((choice) => [
      choice.mode,
      choice.label,
      choice.available,
      choice.selectedByDefault,
      choice.disabledReason,
    ]),
    [
      [
        "live_public_research",
        "Онлайн-ресерч",
        false,
        false,
        "Онлайн-ресерч недоступен: провайдер публичного поиска не настроен.",
      ],
      ["deterministic_offline_fixture", "Офлайн-демо", true, true, null],
    ],
  );
});

test("public research consent scope and submit payload include selected acquisition mode", () => {
  const action = parseCopilotStateResponse(
    copilotStatePayload({
      actions: [
        {
          action_id: "44444444-4444-4444-8444-444444444444",
          action: "open_fact_input",
          status: "requires_input",
          handler: "openFactInput",
          reason: "Нужен ответ основателя.",
          effect_preview: "Открыть ручной ввод для buyer.",
          payload: {
            field_key: "buyer",
            provenance: "founder_statement",
          },
        },
        {
          action_id: "33333333-3333-4333-8333-333333333333",
          action: "prepare_public_research",
          status: "requires_consent",
          handler: "prepareResearchPlan",
          reason: "Public research requires consent.",
          effect_preview: "Prepare public benchmark research.",
          payload: {
            focus: "public_pricing_analogs",
            expected_case_revision: 4,
            available_acquisition_modes: [
              "live_public_research",
              "deterministic_offline_fixture",
            ],
            unavailable_acquisition_modes: [],
            default_acquisition_mode: "live_public_research",
          },
        },
      ],
    }),
  ).actions.find((candidate) => candidate.action === "prepare_public_research") ?? null;

  assert.notEqual(
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: action,
      acquisitionMode: "live_public_research",
    }),
    deriveCaseCopilotResearchConsentScope({
      caseId: "case-founder-001",
      researchAction: action,
      acquisitionMode: "deterministic_offline_fixture",
    }),
  );
  assert.deepEqual(
    buildCaseCopilotSubmitPayload({
      actions: action ? [action] : [],
      answerType: "public_research",
      consentPublicResearch: true,
      manualDraft: "must not leak",
      acquisitionMode: "deterministic_offline_fixture",
    }),
    {
      answerType: "public_research",
      fieldKey: "public_pricing_analogs",
      manualValue: "unknown",
      consentPublicResearch: true,
      expectedCaseRevision: 4,
      acquisitionMode: "deterministic_offline_fixture",
    },
  );
});

test("presents accepted public research sources, saved source ref count, changed blocks, and scenario-only comparison copy", () => {
  const presentation = buildCaseCopilotResearchJobPresentation(researchJobResponse());

  assert.match(presentation.label, /live-поиск по публичному интернету принят/iu);
  assert.match(presentation.description, /live public internet research|публичный контекст/iu);
  assert.match(presentation.description, /не факты компании/iu);
  assert.equal(presentation.sourceRefCount, 1);
  assert.doesNotMatch(JSON.stringify(presentation), /78787878-7878-4787-8787-787878787878/u);
  assert.deepEqual(presentation.changedBlocks, ["Публичные ориентиры", "Сценарии"]);
  assert.deepEqual(presentation.citations, ["https://example.com/public-benchmark"]);
  assert.equal(presentation.acceptedSourceSummaries[0]?.sourceLabel, "Example Research");
  assert.equal(presentation.acceptedSourceSummaries[0]?.sourceRefCount, 1);
  assert.match(presentation.comparisonNote, /пересчёт сценария на публичном контексте/iu);
  assert.doesNotMatch(presentation.comparisonNote, /частн|MRR|выруч|договор|контракт/iu);
});
