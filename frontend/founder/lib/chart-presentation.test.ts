import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFounderChartsPresentation,
  buildFounderMetricDashboardPresentation,
  buildFounderScenarioMetricChartPresentation,
  founderChartBarWidth,
} from "./chart-presentation.ts";
import type { StartupReportSnapshotResponse, StartupScenarioVariant } from "./contracts.ts";

const snapshot = {
  title_ru: "Отчёт для основателя",
  subtitle_ru: "Краткий разбор проекта, блокеры и следующие шаги",
  as_of_ru: "2026-08-15",
  data_revision: 4,
  main_sections: [
    section("business_idea_summary", "confirmed"),
    section("problem_solution", "confirmed"),
    section("market_size", "needs_input"),
    section("competitors", "partial"),
    section("moat", "partial"),
    section("go_to_market", "confirmed"),
    section("metrics", "partial"),
    section("financial_assumptions", "partial"),
    section("risks", "contradiction"),
    section("evidence_gaps", "needs_input"),
    section("diligence_questions", "confirmed"),
    section("action_plan", "confirmed"),
  ],
  metric_cards: {},
  improvement_proposals: [],
  technical_appendix: {
    methodology_ru: ["Отчёт построен по агрегированным разделам анализа."],
    sources_ru: ["Использованы материалы, загруженные в рабочую область."],
  },
  analytics: {
    metric_points: [
      {
        key: "arr",
        label_ru: "ARR",
        value: 1_200_000,
        unit: "USD",
        period_ru: "Q2 2026",
        status: "confirmed",
      },
      {
        key: "gross_margin",
        label_ru: "Валовая маржа",
        value: 0.72,
        unit: "ratio",
        period_ru: "Q2 2026",
        status: "confirmed",
      },
    ],
    market_points: [
      {
        key: "tam",
        label_ru: "TAM",
        value: 1_200_000_000,
        unit: "USD",
        period_ru: "2026",
        status: "estimated",
      },
      {
        key: "sam",
        label_ru: "SAM",
        value: 260_000_000,
        unit: "USD",
        period_ru: "2026",
        status: "estimated",
      },
    ],
    readiness_dimensions: [
      {
        key: "activation",
        label_ru: "Активация",
        status: "ready",
        status_label_ru: "Готово",
        explanation_ru: "Метрика подтверждена.",
      },
      {
        key: "retention",
        label_ru: "Удержание",
        status: "provisional",
        status_label_ru: "Нужно подтвердить",
        explanation_ru: "Нужны когорты.",
      },
      {
        key: "runway",
        label_ru: "Runway",
        status: "blocked",
        status_label_ru: "Нужны данные",
        explanation_ru: "Нужен burn.",
      },
    ],
  },
} as const satisfies StartupReportSnapshotResponse;

function section(
  key: StartupReportSnapshotResponse["main_sections"][number]["key"],
  status: StartupReportSnapshotResponse["main_sections"][number]["status"],
) {
  return {
    key,
    title_ru: key,
    status,
    status_label_ru: status,
    summary_ru: `${key} summary`,
    content_heading_ru: "Факт",
    known_facts_ru: [],
    blockers_ru: [],
    next_data_ru: [],
    unlocks_ru: [],
  };
}

test("builds founder charts from safe analytics and public section coverage only", () => {
  const charts = buildFounderChartsPresentation(snapshot);

  assert.deepEqual(charts.map((chart) => chart.key), [
    "market_sizing",
    "confirmed_metrics",
    "readiness_coverage",
    "report_coverage",
  ]);
  assert.equal(charts[0]?.scale, "shared");
  assert.equal(charts[1]?.scale, "independent");
  assert.equal(charts[2]?.scale, "shared");
  assert.equal(charts[3]?.scale, "shared");
  assert.deepEqual(
    charts[0]?.points.map((point) => [point.key, point.value, point.detail]),
    [
      ["tam", 1_200_000_000, "оценка · 2026"],
      ["sam", 260_000_000, "оценка · 2026"],
    ],
  );
  assert.deepEqual(
    charts[1]?.points.map((point) => [point.key, point.value, point.displayValue]),
    [
      ["arr", 1_200_000, "$1 200 000"],
      ["gross_margin", 0.72, "72%"],
    ],
  );
  assert.deepEqual(
    charts[2]?.points.map((point) => [point.key, point.label, point.value]),
    [
      ["ready", "Готово", 1],
      ["provisional", "Предварительно", 1],
      ["blocked", "Заблокировано", 1],
    ],
  );
  assert.deepEqual(
    charts[3]?.points.map((point) => [point.key, point.label, point.value]),
    [
      ["confirmed", "Заявлено в документе", 5],
      ["partial", "Частично", 4],
      ["needs_input", "Нет данных", 2],
      ["contradiction", "Противоречие", 1],
    ],
  );
});

test("keeps chart presentation free from internal report identifiers", () => {
  const projected = JSON.stringify(buildFounderChartsPresentation(snapshot));

  assert.doesNotMatch(
    projected,
    /source_appendix|methodology|profile_id|snapshot_id|trace_ids|source_hashes|sha256|[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|\bprompt\b|\btoken\b|raw excerpt/iu,
  );
  assert.doesNotMatch(projected, /\b(score|forecast|valuation)\b/iu);
  assert.doesNotMatch(projected, /Подтвержденные метрики|подтверждено источником|подтверждено/u);
});

test("keeps the metrics dashboard on six canonical slots and builds MRR trend from safe metric points", () => {
  const withMrrHistory = {
    ...snapshot,
    analytics: {
      ...snapshot.analytics,
      metric_points: [
        ...snapshot.analytics.metric_points,
        {
          key: "mrr",
          label_ru: "MRR",
          value: 92_000,
          unit: "USD",
          period_ru: "Янв",
          status: "confirmed",
        },
        {
          key: "monthly_recurring_revenue",
          label_ru: "MRR",
          value: 101_000,
          unit: "USD",
          period_ru: "Фев",
          status: "confirmed",
        },
        {
          key: "monthly_net_burn",
          label_ru: "Net burn",
          value: 22_400_000,
          unit: "KZT/month",
          period_ru: "Июнь 2026",
          status: "confirmed",
        },
      ],
    },
  } as const satisfies StartupReportSnapshotResponse;
  const dashboard = buildFounderMetricDashboardPresentation(withMrrHistory);

  assert.deepEqual(
    dashboard.cards.map((card) => [card.slot, card.displayValue, card.provenance]),
    [
      ["mrr", "$101 000", "source_fact"],
      ["arr", "$1 200 000", "source_fact"],
      ["gross_margin", "72%", "source_fact"],
      ["burn_rate", "22 400 000 KZT/month", "source_fact"],
    ],
  );
  assert.deepEqual(
    dashboard.mrrSeries.map((point) => [point.slot, point.label, point.value]),
    [
      ["mrr", "Янв", 92_000],
      ["mrr", "Фев", 101_000],
    ],
  );
  assert.deepEqual(
    dashboard.mrrSeries.map((point) => point.detail),
    ["Янв · заявлено в документе", "Фев · заявлено в документе"],
  );
  assert.equal(dashboard.summary.title, "Текущие финансовые наблюдения загружены");
});

test("preserves calculated, estimated, and contradiction provenance for metric cards", () => {
  const mixedStatusSnapshot = {
    ...snapshot,
    analytics: {
      ...snapshot.analytics,
      metric_points: [
        {
          key: "mrr",
          label_ru: "MRR",
          value: 27900000,
          unit: "KZT",
          period_ru: "Июнь 2026",
          status: "contradiction",
        },
        {
          key: "gross_margin",
          label_ru: "Валовая маржа",
          value: 0.7,
          unit: "ratio",
          period_ru: "Июнь 2026",
          status: "calculated",
        },
        {
          key: "runway_months",
          label_ru: "Runway",
          value: 7.8,
          unit: "months",
          period_ru: "Июнь 2026",
          status: "estimated",
        },
      ],
    },
  } as const satisfies StartupReportSnapshotResponse;

  const dashboard = buildFounderMetricDashboardPresentation(mixedStatusSnapshot);

  assert.deepEqual(
    dashboard.cards.map((card) => [card.slot, card.provenance, card.detail]),
    [
      ["mrr", "contradiction", "Июнь 2026 · есть расхождение в источниках"],
      ["gross_margin", "calculated", "Июнь 2026 · рассчитано по данным отчета"],
      ["runway", "estimated", "Июнь 2026 · оценка по данным отчета"],
    ],
  );
  assert.deepEqual(dashboard.mrrSeries, []);
});

test("builds scenario-only chart projections without plotting them as actual MRR", () => {
  const conservative = scenarioVariant("conservative", "700000", "900000");
  const optimistic = scenarioVariant("optimistic", "1800000", "2400000");

  const conservativeChart = buildFounderScenarioMetricChartPresentation(conservative);
  const optimisticChart = buildFounderScenarioMetricChartPresentation(optimistic);
  const actualDashboard = buildFounderMetricDashboardPresentation({
    ...snapshot,
    analytics: { ...snapshot.analytics, metric_points: [] },
  });

  assert.equal(conservativeChart?.key, "scenario_projection");
  assert.equal(conservativeChart?.title, "Сценарный диапазон: Осторожный");
  assert.equal(
    conservativeChart?.description,
    "Сценарная проекция: диапазон не заменяет подтверждённые фактические данные и требует отдельной проверки.",
  );
  assert.equal(conservativeChart?.points[0]?.value, 800000);
  assert.equal(optimisticChart?.points[0]?.value, 2100000);
  assert.notEqual(conservativeChart?.points[0]?.displayValue, optimisticChart?.points[0]?.displayValue);
  assert.deepEqual(conservativeChart?.points[0], {
    key: "MRR — ежемесячная регулярная выручка",
    label: "MRR — ежемесячная регулярная выручка",
    value: 800000,
    displayValue: "700 тыс.–900 тыс. ₸",
    detail:
      "Расчёт по формуле · Диапазон: 700 тыс.–900 тыс. ₸ · Формула: MRR = средний чек × платящие клиенты · Зависимости: средний чек, платящие клиенты · Источники: 1 источник; Источник 1 · План проверки: Сверьте с выгрузкой биллинга.",
    provenance: "Расчёт по формуле",
    rangeLabel: "700 тыс.–900 тыс. ₸",
    formula: "MRR = средний чек × платящие клиенты",
    dependencies: ["средний чек", "платящие клиенты"],
    sourceRefs: ["Источник 1"],
    validationPlan: "Сверьте с выгрузкой биллинга.",
  });
  const founderFacingScenario = JSON.stringify(conservativeChart);
  assert.doesNotMatch(
    founderFacingScenario,
    /conservative|deterministic_calculation|Scenario-only projection|scenario-only|\bactual\b|monthly_price|paying_customers|public-benchmark-1|Validate billing export|KZT\/month/u,
  );
  assert.doesNotMatch(founderFacingScenario, /source_fact/u);
  assert.deepEqual(actualDashboard.mrrSeries, []);
});

test("projects report contradiction cards through canonical metric aliases", () => {
  const contradictionSnapshot = {
    ...snapshot,
    metric_cards: {
      monthly_recurring_revenue: contradictionCard("MRR", "CRM и банковская выписка расходятся."),
      gross_margin: contradictionCard("Валовая маржа", "Есть две методики себестоимости."),
      monthly_net_burn: contradictionCard("Net burn", "Расходы требуют сверки."),
      runway: contradictionCard("Runway", "Текущий срок требует сверки."),
    },
    analytics: {
      ...snapshot.analytics,
      metric_points: [],
    },
  } as const satisfies StartupReportSnapshotResponse;

  const dashboard = buildFounderMetricDashboardPresentation(contradictionSnapshot);

  assert.deepEqual(
    dashboard.contradictions.map((item) => [item.slot, item.detail]),
    [
      ["mrr", "CRM и банковская выписка расходятся."],
      ["gross_margin", "Есть две методики себестоимости."],
      ["burn_rate", "Расходы требуют сверки."],
      ["runway", "Текущий срок требует сверки."],
    ],
  );
  assert.equal(dashboard.summary.title, "Финансовые данные требуют сверки источников");
});

test("returns no presentation before a report snapshot exists", () => {
  assert.deepEqual(buildFounderChartsPresentation(null), []);
  assert.deepEqual(buildFounderMetricDashboardPresentation(null), {
    cards: [],
    contradictions: [],
    mrrSeries: [],
    summary: {
      title: "Добавьте финансовые данные",
      detail: "Добавьте ежемесячную регулярную выручку (MRR), темп расходов и остаток денег — я построю динамику и проверю запас времени.",
    },
  });
});

test("renders zero as an empty bar and bounds positive chart widths", () => {
  assert.equal(founderChartBarWidth(0, 12), "0%");
  assert.equal(founderChartBarWidth(1, 100), "4%");
  assert.equal(founderChartBarWidth(12, 12), "100%");
});

test("uses a shared scale only when confirmed metrics have one native unit", () => {
  const sameUnitSnapshot = {
    ...snapshot,
    analytics: {
      ...snapshot.analytics,
      metric_points: snapshot.analytics.metric_points.map((point) =>
        point.key === "gross_margin" ? { ...point, value: 72, unit: "USD" } : point,
      ),
    },
  } as const satisfies StartupReportSnapshotResponse;

  const confirmed = buildFounderChartsPresentation(sameUnitSnapshot).find(
    (chart) => chart.key === "confirmed_metrics",
  );

  assert.equal(confirmed?.scale, "shared");
});

function contradictionCard(title: string, summary: string) {
  return {
    title_ru: title,
    summary_ru: summary,
    status: "contradiction" as const,
    why_it_matters_ru: "Нужно выбрать подтверждённый источник.",
    next_unlock_ru: "Сверьте значения и период.",
  };
}

function scenarioVariant(
  scenarioKey: StartupScenarioVariant["scenario_key"],
  lower: string,
  upper: string,
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
        gaps: [],
      },
    },
    gaps: {},
  };
}
