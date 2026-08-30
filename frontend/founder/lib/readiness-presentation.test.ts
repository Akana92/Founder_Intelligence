import assert from "node:assert/strict";
import test from "node:test";

import type {
  StartupScenarioVariant,
  StartupReportSnapshotResponse,
} from "./contracts.ts";
import {
  buildFounderReadinessPresentation,
  buildFounderScenarioReadinessPresentation,
} from "./readiness-presentation.ts";

const startupProfile = {
  case_id: "case-founder-001",
  profile_id: "00000000-0000-4000-8000-000000000101",
  profile_hash:
    "sha256:3333333333333333333333333333333333333333333333333333333333333333",
  data_revision: 5,
  analysis_stage: "enriched",
  parent_profile_id: "00000000-0000-4000-8000-000000000100",
  fields: {},
  gaps: [],
  contradictions: [],
  parse_inventory: { source_hashes: {}, parse_outcomes: {} },
} as const;

const startupGtm = {
  case_id: "case-founder-001",
  schema_version: "startup_gtm@1",
  snapshot_id: "00000000-0000-4000-8000-000000000801",
  snapshot_hash:
    "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  snapshot_revision: 5,
  status: "partial",
  profile_id: "00000000-0000-4000-8000-000000000101",
  product_validation_snapshot_id: "00000000-0000-4000-8000-000000000701",
  market_research_snapshot_id: "00000000-0000-4000-8000-000000000901",
  dimensions: [],
  launch_plan: [],
  finding_ids: [],
  built_at: "2026-08-15T00:00:00.000Z",
} as const;

const reportSnapshot = {
  title_ru: "Отчёт для основателя",
  subtitle_ru: "Краткий разбор проекта, блокеры и следующие шаги",
  as_of_ru: "2026-08-15",
  data_revision: 5,
  main_sections: [
    section("market_size", "Размер рынка", "partial", ["TAM требует подтверждения"], ["Уточните TAM"]),
    section("competitors", "Конкуренты", "partial", ["LedgerPilot упомянут в материалах"], ["Добавьте win-loss"]),
    section("risks", "Риски", "confirmed", ["Adoption depends on finance workflow migration"]),
    section("action_plan", "План действий", "confirmed", [], ["Назначьте владельца доказательств"]),
    section("evidence_gaps", "Пробелы", "needs_input", [], ["Для GTM не хватает доказательства канала."]),
    section("diligence_questions", "Вопросы", "confirmed", [], [
      "Clarify ICP budget owner.",
      "Confirm paid pilot terms.",
      "Validate channel repeatability.",
      "Quantify churn cohort.",
    ]),
  ],
  metric_cards: {},
  improvement_proposals: [],
  technical_appendix: {
    methodology_ru: ["Отчёт построен по агрегированным разделам анализа."],
    sources_ru: ["Использованы материалы, загруженные в рабочую область."],
  },
  analytics: {
    metric_points: [],
    market_points: [],
    readiness_dimensions: [
      {
        key: "gross_margin",
        label_ru: "Валовая маржа",
        status: "ready",
        status_label_ru: "Готово",
        explanation_ru: "Метрика подтверждена в отчёте.",
      },
      {
        key: "retention",
        label_ru: "Удержание",
        status: "blocked",
        status_label_ru: "Нужны данные",
        explanation_ru: "Добавьте когорты удержания.",
      },
    ],
  },
} as const satisfies StartupReportSnapshotResponse;

function section(
  key: StartupReportSnapshotResponse["main_sections"][number]["key"],
  title_ru: string,
  status: StartupReportSnapshotResponse["main_sections"][number]["status"],
  known_facts_ru: readonly string[] = [],
  blockers_ru: readonly string[] = [],
) {
  return {
    key,
    title_ru,
    status,
    status_label_ru:
      status === "confirmed"
        ? "Подтверждено"
        : status === "partial"
          ? "Частично"
          : status === "contradiction"
            ? "Противоречие"
            : "Нужно доказательство",
    summary_ru: `${title_ru}: безопасное резюме.`,
    content_heading_ru: key === "risks" ? "Риск" : "Факт",
    known_facts_ru,
    blockers_ru,
    next_data_ru: [],
    unlocks_ru: [],
  };
}

function buildInput(
  snapshot: StartupReportSnapshotResponse = reportSnapshot,
  reportCaseId = "case-founder-001",
) {
  return {
    profile: startupProfile,
    gtm: startupGtm,
    reportCaseId,
    reportSnapshot: snapshot,
  };
}

test("projects stages and readiness dimensions from founder-safe public report analytics", () => {
  const presentation = buildFounderReadinessPresentation(buildInput());

  assert.deepEqual(presentation.stages, [
    {
      key: "primary",
      label: "Первичный анализ",
      status: "available",
    },
    {
      key: "deep",
      label: "Готовность проекта и глубокие вопросы",
      status: "available",
    },
  ]);
  assert.deepEqual(presentation.readiness, {
    status: "available",
    dimensionCards: [
      {
        key: "gross_margin",
        labelRu: "Валовая маржа",
        statusLabelRu: "Готово",
        explanationRu: "Метрика подтверждена в отчёте.",
      },
      {
        key: "retention",
        labelRu: "Удержание",
        statusLabelRu: "Нужны данные",
        explanationRu: "Добавьте когорты удержания.",
      },
    ],
  });
  assert.deepEqual(presentation.scenarioValidationCards, []);
});

test("projects selected scenario validation readiness without promoting it to source_fact", () => {
  const conservative = scenarioVariant("conservative", "700000", "900000", []);
  const optimistic = scenarioVariant("optimistic", "1800000", "2400000", ["paid customer count missing"]);
  const conservativeCards = buildFounderScenarioReadinessPresentation(conservative);
  const optimisticCards = buildFounderScenarioReadinessPresentation(optimistic);
  const presentation = buildFounderReadinessPresentation({
    ...buildInput(),
    selectedScenario: optimistic,
  });

  assert.equal(conservativeCards[0]?.statusLabelRu, "Нужна проверка сценария");
  assert.equal(optimisticCards[0]?.statusLabelRu, "Нужны зависимости сценария");
  assert.notEqual(conservativeCards[0]?.explanationRu, optimisticCards[0]?.explanationRu);
  assert.equal(optimisticCards[0]?.labelRu, "MRR — ежемесячная регулярная выручка");
  assert.match(optimisticCards[0]?.explanationRu ?? "", /Происхождение: Расчёт по формуле/u);
  assert.match(optimisticCards[0]?.explanationRu ?? "", /Диапазон: 1,8–2,4 млн ₸/u);
  assert.match(optimisticCards[0]?.explanationRu ?? "", /Формула: MRR = средний чек × платящие клиенты/u);
  assert.match(optimisticCards[0]?.explanationRu ?? "", /Зависимости: средний чек, платящие клиенты/u);
  assert.match(optimisticCards[0]?.explanationRu ?? "", /Источники: 1 источник; Источник 1/u);
  assert.match(optimisticCards[0]?.explanationRu ?? "", /План проверки: Сверьте с выгрузкой биллинга/u);
  assert.match(optimisticCards[0]?.explanationRu ?? "", /Что подтвердит: Выгрузка биллинга с числом платящих клиентов/u);
  assert.doesNotMatch(
    JSON.stringify(optimisticCards),
    /scenario-only|source_fact|deterministic_calculation|monthly_price|paying_customers|public-benchmark-1|Validate billing export|KZT\/month|paid customer count missing/u,
  );
  assert.deepEqual(presentation.scenarioValidationCards, optimisticCards);
});

test("projects report-derived gaps questions and deep summaries without internal lineage", () => {
  const presentation = buildFounderReadinessPresentation(buildInput());
  const serialized = JSON.stringify(presentation);

  assert.deepEqual(presentation.gaps, [
    "Для GTM не хватает доказательства канала.",
  ]);
  assert.deepEqual(presentation.questions, [
    "Clarify ICP budget owner.",
    "Confirm paid pilot terms.",
    "Validate channel repeatability.",
  ]);
  assert.deepEqual(
    presentation.deepSections.map((section) => [
      section.key,
      section.status,
      section.rows,
      section.items,
    ]),
    [
      ["market_size", "partial", [["Факт", "TAM требует подтверждения"]], ["Уточните TAM"]],
      ["competitors", "partial", [["Факт", "LedgerPilot упомянут в материалах"]], ["Добавьте win-loss"]],
      ["risks", "confirmed", [["Риск", "Adoption depends on finance workflow migration"]], []],
      ["action_plan", "confirmed", [], ["Назначьте владельца доказательств"]],
    ],
  );
  assert.doesNotMatch(
    serialized,
    /profile_id|profile_hash|snapshot_id|snapshot_hash|trace_ids|source_hashes|source_appendix|sha256|00000000/u,
  );
});

test("fails closed across mismatched public data revisions", () => {
  const presentation = buildFounderReadinessPresentation(
    buildInput({ ...reportSnapshot, data_revision: 6 }),
  );

  assert.equal(presentation.stages[0]?.status, "lineage_mismatch");
  assert.equal(presentation.stages[1]?.status, "lineage_mismatch");
  assert.deepEqual(presentation.readiness, {
    status: "lineage_mismatch",
    dimensionCards: [],
  });
  assert.deepEqual(presentation.gaps, []);
  assert.deepEqual(presentation.questions, []);
  assert.deepEqual(presentation.deepSections, []);
});

test("fails closed when a report from another case shares the same numeric revision", () => {
  const presentation = buildFounderReadinessPresentation(
    buildInput(reportSnapshot, "case-other"),
  );

  assert.equal(presentation.stages[0]?.status, "lineage_mismatch");
  assert.equal(presentation.stages[1]?.status, "lineage_mismatch");
  assert.deepEqual(presentation.readiness, {
    status: "lineage_mismatch",
    dimensionCards: [],
  });
  assert.deepEqual(presentation.gaps, []);
  assert.deepEqual(presentation.questions, []);
  assert.deepEqual(presentation.deepSections, []);
});

test("handles missing readiness analytics explicitly without inventing dimensions", () => {
  const presentation = buildFounderReadinessPresentation(
    buildInput({
      ...reportSnapshot,
      analytics: { ...reportSnapshot.analytics, readiness_dimensions: [] },
    }),
  );

  assert.equal(presentation.stages[1]?.status, "missing_readiness");
  assert.deepEqual(presentation.readiness, {
    status: "missing",
    dimensionCards: [],
  });
});

function scenarioVariant(
  scenarioKey: StartupScenarioVariant["scenario_key"],
  lower: string,
  upper: string,
  gaps: readonly string[],
): StartupScenarioVariant {
  return {
    scenario_key: scenarioKey,
    inputs: {},
    metrics: {
      mrr: {
        metric_id: `metric-${scenarioKey}`,
        case_id: "case-founder-001",
        data_revision: 5,
        metric_key: "mrr",
        value_range: { lower, upper },
        unit: "KZT/month",
        period: "month",
        provenance: "deterministic_calculation",
        source_refs: ["public-benchmark-1"],
        dependency_refs: ["monthly_price", "paying_customers"],
        formula_key: "mrr",
        formula_description: "monthly_price * paying_customers",
        confidence: "medium",
        rationale: "Scenario planning input.",
        validation_plan: "Validate billing export.",
        what_would_confirm: "Billing export with paid customer count.",
        acceptance: "needs_validation",
        gaps,
      },
    },
    gaps: {},
  };
}
