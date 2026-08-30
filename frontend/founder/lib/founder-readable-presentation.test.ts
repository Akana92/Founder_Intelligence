import assert from "node:assert/strict";
import test from "node:test";

import type {
  ApiErrorCode,
  ResearchBenchmarkEntryProjection,
  ResearchJobResponse,
  StartupScenarioMetric,
} from "./contracts.ts";
import {
  formatCopilotAction,
  formatCopilotActionStatus,
  formatCopilotRole,
  formatCoverage,
  formatDependency,
  formatGap,
  formatMetric,
  formatProvenance,
  formatScenario,
  formatScenarioComparisonValue,
  formatScenarioMetricValue,
  presentPublicResearchOutcome,
  presentPublicBenchmarkEntry,
  presentScenarioMetric,
} from "./founder-readable-presentation.ts";

const metric: StartupScenarioMetric = {
  metric_id: "44444444-4444-4444-8444-444444444444",
  case_id: "11111111-1111-4111-8111-111111111111",
  data_revision: 3,
  metric_key: "mrr",
  value_range: { lower: "7.2E+6", upper: "1.47E+7" },
  unit: "KZT/month",
  period: "month",
  provenance: "deterministic_calculation",
  source_refs: ["77777777-7777-4777-8777-777777777777"],
  dependency_refs: ["monthly_price", "55555555-5555-4555-8555-555555555555"],
  formula_key: "mrr",
  formula_description: "monthly_price * paying_customers",
  confidence: "medium",
  rationale: "Derived from scenario inputs.",
  validation_plan: "Validate against billing export.",
  what_would_confirm: "Billing export with paid customer count.",
  acceptance: "needs_validation",
  gaps: ["missing:churn"],
};

const publicBenchmark: ResearchBenchmarkEntryProjection = {
  entry_id: "56565656-5656-4656-8656-565656565656",
  provenance: "public_benchmark",
  input_key: "monthly_price",
  url: "https://example.com/public-benchmark",
  publisher: "Example Research",
  publication_date: null,
  retrieval_date: "2026-08-25",
  as_of: "2026-08-25",
  source_class: "industry_report",
  confidence: "medium",
  value: null,
  range: { low: "35000", high: "85000" },
  unit: "KZT/month",
  period: "month",
  formula: "Reported public KZT monthly pricing range.",
  dependencies: ["public pricing page"],
  validation_plan: "Use only as external context until founder-specific evidence exists.",
  source_refs: ["77777777-7777-4777-8777-777777777777"],
};

const researchJob: ResearchJobResponse = {
  case_id: "11111111-1111-4111-8111-111111111111",
  data_revision: 4,
  job_id: "22222222-2222-4222-8222-222222222222",
  plan_id: "33333333-3333-4333-8333-333333333333",
  plan_hash: "plan-hash",
  status: "deferred",
  reason: "provider_unconfigured",
  acquisition_mode: "provider_unconfigured",
  requested_acquisition_mode: "live_public_research",
  selected_acquisition_mode: "provider_unconfigured",
  accepted_entries: [],
  rejected_entries: [],
  citations: [],
  manual_only_keys: ["monthly_recurring_revenue", "contracts", "bank_data"],
  changed_blocks: [],
  stale_scenario_ids: [],
  old_revision: 4,
  new_revision: 4,
  source_refs: [],
  updated_at: "2026-08-25T10:00:00Z",
};

test("presents Case Copilot contract values in founder-readable Russian", () => {
  assert.equal(formatProvenance("source_fact"), "Заявлено в документе");
  assert.equal(formatProvenance("deterministic_calculation"), "Расчёт по формуле");
  assert.equal(formatScenario("base"), "Базовый");
  assert.equal(formatMetric("mrr"), "MRR — ежемесячная регулярная выручка");
  assert.equal(formatDependency("monthly_price"), "средний чек");
  assert.equal(formatDependency("55555555-5555-4555-8555-555555555555"), "связанный входной показатель");
  assert.equal(formatGap("missing:churn"), "Не хватает данных: отток клиентов");
  assert.equal(formatCopilotAction("open_fact_input"), "Добавить данные");
  assert.equal(formatCopilotActionStatus("requires_consent"), "Нужно согласие");
  assert.equal(formatCopilotRole("system_event"), "Системное событие");
  assert.equal(
    formatCoverage({ measure: "fact_coverage", status: "partial", source_fact_count: 1, accepted_input_count: 2 }),
    "Частичное покрытие: фактов — 1, ответов — 2",
  );
  assert.equal(formatScenarioMetricValue(metric), "7,2–14,7 млн ₸");

  const presentation = presentScenarioMetric(metric);
  assert.equal(presentation.title, "MRR — ежемесячная регулярная выручка");
  assert.equal(presentation.value, "7,2–14,7 млн ₸");
  assert.equal(presentation.trustStatement, "Расчёт по формуле");
  assert.deepEqual(presentation.dependencies, ["средний чек", "связанный входной показатель"]);
  assert.deepEqual(presentation.gaps, ["Не хватает данных: отток клиентов"]);
  assert.equal(presentation.formula, "MRR = средний чек × платящие клиенты");

  const founderSummary = JSON.stringify(presentation);
  assert.doesNotMatch(
    founderSummary,
    /source_fact|deterministic_calculation|missing:|[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|\d(?:\.\d+)?E[+-]?\d+/iu,
  );
});

test("presents undated public benchmarks as readable external context with a source link", () => {
  const presentation = presentPublicBenchmarkEntry(publicBenchmark);

  assert.deepEqual(presentation, {
    title: "средний чек",
    provenanceLabel: "Публичный ориентир, не факт из ваших документов",
    sourceLabel: "Example Research",
    sourceUrl: "https://example.com/public-benchmark",
    dateLabel: "Дата публикации не указана; источник проверен 25.08.2026",
    rangeLabel: "35–85 тыс. ₸ в месяц",
    formula: "Диапазон взят с публичной страницы цен.",
    dependencies: ["публичная страница с ценами"],
    validationPlan: "Используйте только как внешний ориентир, пока он не подтверждён данными конкретного кейса.",
  });
  assert.doesNotMatch(
    JSON.stringify(presentation),
    /public_benchmark|industry_report|77777777-7777-4777-8777-777777777777/u,
  );
});

test("localizes live public pricing benchmark formula dependencies and validation guidance", () => {
  const presentation = presentPublicBenchmarkEntry({
    ...publicBenchmark,
    publisher: "B2B.kz",
    url: "https://b2b.kz/",
    formula:
      "Published monthly B2B portal plan prices: 100000, 250000, and 600000 KZT/month; no currency or period conversion.",
    dependencies: [
      "Plan scope and included integrations vary by tier.",
      "Pricing varies by plan and team-size selector.",
      "Cloud price is per user; PRO price is per company.",
    ],
    validation_plan:
      "Use only as external context until founder-specific evidence confirms comparable segment fit.",
  });

  assert.equal(
    presentation.formula,
    "Диапазон взят из опубликованных месячных тарифов; валюта и период не пересчитывались.",
  );
  assert.deepEqual(presentation.dependencies, [
    "состав тарифа и интеграции зависят от уровня плана",
    "цена зависит от плана и размера команды",
    "часть тарифов считается за пользователя, часть — за компанию",
  ]);
  assert.equal(
    presentation.validationPlan,
    "Проверьте, подходит ли этот внешний ориентир к сегменту, географии и модели цены конкретного кейса.",
  );

  assert.doesNotMatch(
    `${presentation.formula} ${presentation.dependencies.join(" ")} ${presentation.validationPlan}`,
    /Published monthly|varies by|per user|external context|founder-specific|KZT\/month|public_benchmark/u,
  );
});

test("collapses repeated opaque dependency references into one readable count", () => {
  const presentation = presentScenarioMetric({
    ...metric,
    dependency_refs: [
      "55555555-5555-4555-8555-555555555555",
      "66666666-6666-4666-8666-666666666666",
    ],
  });

  assert.deepEqual(presentation.dependencies, ["2 связанных входных показателя"]);
});

test("keeps every emitted scenario formula and validation plan specific in Russian", () => {
  const cases = [
    {
      key: "mrr",
      description: "Monthly price multiplied by projected paying customers.",
      formula: "MRR = средний чек × платящие клиенты",
      validation: "Validate against signed customers and invoices after launch.",
      validationRu: "Сверьте прогноз с подписанными клиентами и выставленными счетами после запуска.",
      confirmation: "Signed paid customers and invoices for the forecast month.",
      confirmationRu: "Подписанные платящие клиенты и счета за прогнозный месяц.",
    },
    {
      key: "arr",
      description: "Monthly recurring revenue multiplied by 12.",
      formula: "ARR = MRR × 12",
      validation: "Validate once MRR is evidenced for a stable month.",
      validationRu: "Проверьте после подтверждения ежемесячной регулярной выручки (MRR) за стабильный репрезентативный месяц.",
      confirmation: "A verified MRR source fact for a representative month.",
      confirmationRu: "Подтверждённый источник ежемесячной регулярной выручки (MRR) за репрезентативный месяц.",
    },
    {
      key: "gross_margin",
      description: "Revenue minus cost of goods sold divided by revenue.",
      formula: "Валовая маржа = (выручка − себестоимость) ÷ выручка",
      validation: "Validate using invoices, cloud bills, support costs and recognized revenue.",
      validationRu: "Сверьте счета, облачные расходы, затраты поддержки и признанную выручку за один период.",
      confirmation: "Recognized revenue and cost-of-goods evidence for the same period.",
      confirmationRu: "Подтверждённые выручка и себестоимость за один и тот же период.",
    },
    {
      key: "net_burn",
      description: "Monthly operating expenses minus monthly revenue.",
      formula: "Чистый расход денег = операционные расходы − выручка",
      validation: "Validate using bank, payroll, expense and revenue records.",
      validationRu: "Сверьте банковские операции, фонд оплаты труда, расходы и выручку за один период.",
      confirmation: "Monthly revenue and expense source facts for the same period.",
      confirmationRu: "Подтверждённые ежемесячные выручка и расходы за один период.",
    },
    {
      key: "runway",
      description: "Cash balance divided by positive monthly net burn.",
      formula: "Запас времени = остаток денег ÷ чистый расход денег",
      validation: "Validate using cash balance and monthly burn evidence.",
      validationRu: "Сверьте текущий остаток денег и подтверждённый ежемесячный чистый расход.",
      confirmation: "A current cash balance and positive net burn source fact.",
      confirmationRu: "Подтверждённые текущий остаток денег и положительный чистый расход за месяц.",
    },
    {
      key: "cac",
      description: "Acquisition spend divided by acquired customers.",
      formula: "CAC = расходы на привлечение ÷ новые клиенты",
      validation: "Validate using channel spend and customer acquisition records.",
      validationRu: "Сверьте расходы по каналам с данными о привлечённых клиентах.",
      confirmation: "Attributed acquisition spend and acquired customer counts.",
      confirmationRu: "Распределённые расходы на привлечение и подтверждённое число новых клиентов.",
    },
    {
      key: "ltv",
      description: "ARPA multiplied by gross margin and divided by churn.",
      formula: "LTV = средний чек × валовая маржа ÷ отток клиентов",
      validation: "Validate using cohort retention and revenue evidence.",
      validationRu: "Сверьте расчёт с когортным удержанием и подтверждённой выручкой.",
      confirmation: "Observed cohort churn or a cited comparable churn benchmark.",
      confirmationRu: "Наблюдаемый когортный отток или публичный ориентир с указанным источником.",
    },
    {
      key: "ltv_cac",
      description: "LTV divided by CAC.",
      formula: "Соотношение LTV и CAC = LTV ÷ CAC",
      validation: "Validate after LTV and CAC are independently evidenced.",
      validationRu: "Проверьте после независимого подтверждения LTV и CAC.",
      confirmation: "Eligible LTV and CAC calculations for the same customer segment.",
      confirmationRu: "Сопоставимые расчёты LTV и CAC для одного клиентского сегмента.",
    },
    {
      key: "cac_payback",
      description: "CAC divided by ARPA multiplied by gross margin.",
      formula: "Окупаемость CAC = CAC ÷ (средняя выручка на клиента × валовая маржа)",
      validation: "Validate using CAC, ARPA and gross margin evidence.",
      validationRu: "Сверьте CAC, среднюю выручку на клиента и валовую маржу по одному сегменту.",
      confirmation: "Eligible CAC, ARPA and gross margin for the same segment.",
      confirmationRu: "Подтверждённые CAC, средняя выручка на клиента и валовая маржа для одного сегмента.",
    },
  ] as const;

  for (const item of cases) {
    const presentation = presentScenarioMetric({
      ...metric,
      metric_key: item.key,
      formula_key: item.key,
      formula_description: item.description,
      validation_plan: item.validation,
      what_would_confirm: item.confirmation,
    });

    assert.equal(presentation.formula, item.formula, item.key);
    assert.equal(presentation.validationPlan, item.validationRu, item.key);
    assert.equal(presentation.confirmationGuidance, item.confirmationRu, item.key);
  }
});

test("does not render unknown coverage counts as zero", () => {
  assert.equal(
    formatCoverage({
      measure: "fact_coverage",
      status: "complete",
      source_fact_count: null,
      accepted_input_count: null,
    }),
    "Полное покрытие: показатели пока не рассчитаны",
  );
});

test("retains founder-safe source-reference disclosure labels", () => {
  const presentation = presentScenarioMetric(metric);

  assert.deepEqual(presentation.sourceReferences, ["Источник 1"]);
  assert.doesNotMatch(
    JSON.stringify(presentation),
    /77777777-7777-4777-8777-777777777777/u,
  );
});

test("translates only known generated Case Copilot copy and profile stages", async () => {
  const presentation = await import("./founder-readable-presentation.ts");

  assert.equal(typeof presentation.formatCopilotQuestion, "function");
  assert.equal(typeof presentation.formatCopilotMessage, "function");
  assert.equal(typeof presentation.formatFounderStage, "function");
  assert.equal(
    presentation.formatCopilotQuestion?.(
      "Provide founder-approved input for revenue.",
    ),
    "Укажите выручку, которую основатель готов использовать как ручной ввод для сценария.",
  );
  const generatedQuestionCases = [
    {
      input: "Provide founder-approved input for mrr.",
      output:
        "Укажите показатель «ежемесячная регулярная выручка (MRR)». Основатель готов использовать его как ручной ввод для сценария.",
    },
    {
      input: "Provide founder-approved input for cash_balance.",
      output:
        "Укажите показатель «остаток денег». Основатель готов использовать его как ручной ввод для сценария.",
    },
    {
      input: "Provide founder-approved input for churn.",
      output:
        "Укажите показатель «отток клиентов». Основатель готов использовать его как ручной ввод для сценария.",
    },
    {
      input: "Provide founder-approved input for monthly_revenue.",
      output:
        "Укажите показатель «ежемесячная выручка». Основатель готов использовать его как ручной ввод для сценария.",
    },
    {
      input: "Provide founder-approved input for unknown_safe_key.",
      output:
        "Укажите показатель «связанный входной показатель». Основатель готов использовать его как ручной ввод для сценария.",
    },
  ] as const;
  for (const item of generatedQuestionCases) {
    const result = presentation.formatCopilotQuestion?.(item.input);
    assert.equal(result, item.output, item.input);
    assert.doesNotMatch(result ?? "", /Provide founder-approved input/iu, item.input);
  }
  assert.equal(
    presentation.formatCopilotQuestion?.(
      "Which clinic role owns follow-up quality, and what non-financial proof shows the service can fit clinic operations safely?",
    ),
    "Кто в клинике отвечает за качество последующей работы с пациентами и какие нефинансовые доказательства показывают, что сервис можно безопасно встроить в работу клиники?",
  );
  assert.equal(
    presentation.formatCopilotMessage?.(
      "Case Copilot is ready with same-case facts and scenario boundaries.",
    ),
    "Помощник по кейсу готов: факты этого кейса и границы сценариев учтены раздельно.",
  );
  assert.equal(
    presentation.formatCopilotMessage?.(
      "Accepted public_benchmark research updated scenario context.",
    ),
    "Принятый публичный ориентир обновил сценарный контекст.",
  );
  assert.equal(
    presentation.formatCopilotMessage?.(
      "Saved founder_statement assumption for monthly_price.",
    ),
    "Значение со слов основателя сохранено для показателя «средний чек».",
  );
  assert.equal(presentation.formatFounderStage?.("idea"), "Идея");
  assert.equal(
    presentation.formatCopilotQuestion?.("Source excerpt in English."),
    "Source excerpt in English.",
  );
  assert.equal(formatCopilotRole("assistant"), "Помощник по кейсу");
});

test("preserves user and assistant thread excerpts while localizing generated roles", async () => {
  const presentation = await import("./founder-readable-presentation.ts");
  const sourceExcerpt =
    "Founder wrote monthly_price, source_fact and 11111111-1111-4111-8111-111111111111 verbatim.";

  assert.equal(typeof presentation.formatCopilotThreadMessage, "function");
  assert.equal(
    presentation.formatCopilotThreadMessage?.("user", sourceExcerpt),
    sourceExcerpt,
  );
  assert.equal(
    presentation.formatCopilotThreadMessage?.("assistant", sourceExcerpt),
    sourceExcerpt,
  );
  assert.equal(
    presentation.formatCopilotThreadMessage?.(
      "system_event",
      "Case Copilot is ready with same-case facts and scenario boundaries.",
    ),
    "Помощник по кейсу готов: факты этого кейса и границы сценариев учтены раздельно.",
  );
  assert.equal(
    presentation.formatCopilotThreadMessage?.(
      "tool",
      "Saved founder_statement assumption for monthly_price.",
    ),
    "Значение со слов основателя сохранено для показателя «средний чек».",
  );
  assert.equal(
    presentation.formatCopilotThreadMessage?.(
      "tool",
      "Accepted public_benchmark research updated scenario context.",
    ),
    "Принятый публичный ориентир обновил сценарный контекст.",
  );
  assert.equal(
    presentation.formatCopilotThreadMessage?.(
      "tool",
      "Saved source_fact evidence for pricing_revenue_model.",
    ),
    "Заявленное в документе значение сохранено для показателя «модель выручки».",
  );
});

test("presents every public research outcome as distinct founder-safe recovery copy", () => {
  const byError = (errorCode: ApiErrorCode) => presentPublicResearchOutcome({ errorCode });
  assert.deepEqual(byError("public_research_consent_required"), {
    title: "Публичный поиск не запущен: нужно согласие",
    description:
      "Отметьте согласие на поиск по открытым источникам. Внутренние метрики, документы и локальные файлы не отправляются.",
    recoveryLabel: "Дать согласие и запустить заново",
    invalidProviderContract: false,
  });

  const cases = [
    [
      {
        ...researchJob,
        status: "completed",
        reason: "cached_completed_research",
        acquisition_mode: "live_public_research",
        accepted_entries: [publicBenchmark],
        citations: ["https://example.com/public-benchmark"],
        source_refs: ["77777777-7777-4777-8777-777777777777"],
      },
      "Сохранённый онлайн-ресерч использован",
      "1 источник; новый интернет- и OpenAI-запрос не выполнялся. Сохранённый публичный контекст использован повторно; это не факты компании.",
    ],
    [
      { ...researchJob, status: "failed", reason: "BUDGET_EXCEEDED" },
      "Лимит онлайн-ресерча исчерпан",
      "Новый OpenAI-запрос не выполнен из-за лимита. Используйте сохранённый публичный ресерч или повторите после увеличения бюджета; внутренние факты компании не менялись.",
    ],
    [
      { ...researchJob, reason: "provider_unconfigured" },
      "Провайдер публичного поиска не настроен",
      "Live-провайдер не настроен; используйте безопасный ручной ввод или отложите запуск. Данные кейса и сценарии не изменились.",
    ],
    [
      { ...researchJob, reason: "stale_research_plan" },
      "План публичного поиска устарел",
      "Обновите вопрос или профиль и подготовьте новый план для текущей версии кейса.",
    ],
    [
      { ...researchJob, status: "failed", reason: "provider_failed" },
      "Публичный поиск завершился ошибкой провайдера",
      "Повторите запуск позже. Согласие относится только к одному запуску; внутренние факты компании не менялись.",
    ],
    [
      { ...researchJob, reason: "no_eligible_public_benchmarks" },
      "Публичный ориентир не принят",
      "Открытые источники не дали безопасного ориентира для сценария; внутренние факты компании остались без изменений.",
    ],
    [
      {
        ...researchJob,
        reason: "no_eligible_public_benchmarks",
        rejected_entries: [
          {
            rejected_id: "44444444-4444-4444-8444-444444444444",
            reason_code: "invalid_benchmark_entry",
            input_key: "monthly_price",
            provenance: "public_benchmark",
            metadata: {},
          },
        ],
      },
      "Провайдер вернул неподходящий формат ориентира",
      "Источник найден, но его числовой ориентир не прошёл контракт. Данные кейса не изменились; можно повторить поиск позже.",
    ],
    [
      { ...researchJob, reason: "research_interrupted" },
      "Публичный поиск был прерван",
      "Перезапустите поиск после проверки текущей версии кейса. Прерванный запуск не менял факты и сценарии.",
    ],
  ] as const;

  for (const [job, title, description] of cases) {
    const presentation = presentPublicResearchOutcome({ job });
    assert.equal(presentation.title, title);
    assert.equal(presentation.description, description);
    assert.doesNotMatch(
      `${presentation.title} ${presentation.description} ${presentation.recoveryLabel}`,
      /проверьте согласие/iu,
    );
  }

  const partial = presentPublicResearchOutcome({
    job: {
      ...researchJob,
      status: "partial",
      reason: null,
      acquisition_mode: "live_public_research",
      accepted_entries: [publicBenchmark],
      rejected_entries: [
        {
          rejected_id: "55555555-5555-4555-8555-555555555555",
          reason_code: "invalid_benchmark_entry",
          input_key: "monthly_price",
          provenance: "public_benchmark",
          metadata: {},
        },
      ],
      citations: ["https://example.com/public-benchmark"],
      changed_blocks: ["public_benchmarks", "scenarios"],
      source_refs: ["77777777-7777-4777-8777-777777777777"],
      new_revision: 5,
    },
  });
  assert.equal(partial.title, "Live-поиск по публичному интернету принят частично");
  assert.match(partial.description, /1 источник/u);
  assert.match(partial.description, /обновлены публичные ориентиры и сценарии/u);
  assert.match(partial.description, /не факты компании/u);
  assert.equal(partial.invalidProviderContract, true);
  assert.doesNotMatch(JSON.stringify(partial), /source_fact|MRR|cash|bank|contracts/iu);
});

test("localizes non-currency scenario units without changing their values", () => {
  assert.equal(
    formatScenarioMetricValue({
      ...metric,
      unit: "months",
      value_range: { lower: "7.2", upper: "14.7" },
    }),
    "7,2–14,7 мес.",
  );
  assert.equal(
    formatScenarioMetricValue({
      ...metric,
      unit: "ratio",
      value_range: { lower: "0.4", upper: "0.8" },
    }),
    "0,4–0,8 доля",
  );
});

test("formats scenario comparison values without scientific notation", () => {
  const value = formatScenarioComparisonValue({
    valueRange: { lower: "7.2E+6", upper: "1.47E+7" },
    unit: "KZT",
    gaps: [],
  });

  assert.equal(value, "7,2–14,7 млн ₸");
  assert.doesNotMatch(value, /\d(?:\.\d+)?E[+-]?\d+/iu);
});

test("presents generated scenario validation guidance in Russian", async () => {
  const presentation = await import("./founder-readable-presentation.ts");

  assert.equal(typeof presentation.formatScenarioValidationPlan, "function");
  assert.equal(typeof presentation.formatScenarioConfirmationGuidance, "function");
  assert.equal(
    presentation.formatScenarioValidationPlan?.(
      "Validate once MRR is evidenced for a stable month.",
    ),
    "Проверьте после подтверждения ежемесячной регулярной выручки (MRR) за стабильный репрезентативный месяц.",
  );
  assert.equal(
    presentation.formatScenarioConfirmationGuidance?.(
      "A verified MRR source fact for a representative month.",
    ),
    "Подтверждённый источник ежемесячной регулярной выручки (MRR) за репрезентативный месяц.",
  );
  assert.equal(
    presentation.formatScenarioValidationPlan?.("Сверить с банковской выпиской."),
    "Сверить с банковской выпиской.",
  );
});
