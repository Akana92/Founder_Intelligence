import type {
  FounderReportAnalyticsPoint,
  FounderReportMetricCardResponse,
  FounderReportReadinessStatus,
  FounderReportSectionStatus,
  StartupReportSectionKey,
  StartupReportSnapshotResponse,
  StartupScenarioMetric,
  StartupScenarioVariant,
} from "./contracts.ts";
import {
  formatScenario,
  formatProvenance,
  presentScenarioMetric,
} from "./founder-readable-presentation.ts";
import { REPORT_MAIN_SECTION_ORDER } from "./report-presentation.ts";

export type FounderChartPoint = Readonly<{
  key: string;
  label: string;
  value: number;
  displayValue: string;
  detail: string;
}>;

export type FounderChartPresentation = Readonly<{
  key:
    | "market_sizing"
    | "confirmed_metrics"
    | "scenario_projection"
    | "readiness_coverage"
    | "report_coverage";
  title: string;
  description: string;
  points: readonly FounderChartPoint[];
  scale: "shared" | "independent";
}>;

export type FounderScenarioChartPoint = FounderChartPoint & Readonly<{
  provenance: string;
  rangeLabel: string;
  formula: string;
  dependencies: readonly string[];
  sourceRefs: readonly string[];
  validationPlan: string;
}>;

export type FounderMetricSlot =
  | "mrr"
  | "arr"
  | "gross_margin"
  | "burn_rate"
  | "runway"
  | "retention";

export type FounderMetricDashboardCard = FounderChartPoint & Readonly<{
  slot: FounderMetricSlot;
  provenance: "source_fact" | "calculated" | "estimated" | "contradiction";
}>;

export type FounderMetricDashboardContradiction = Readonly<{
  slot: FounderMetricSlot;
  detail: string;
}>;

export type FounderMetricDashboardPresentation = Readonly<{
  cards: readonly FounderMetricDashboardCard[];
  contradictions: readonly FounderMetricDashboardContradiction[];
  mrrSeries: readonly FounderMetricDashboardCard[];
  summary: Readonly<{
    title: string;
    detail: string;
  }>;
}>;

const missingFinancialSummary = {
  title: "Добавьте финансовые данные",
  detail: "Добавьте ежемесячную регулярную выручку (MRR), темп расходов и остаток денег — я построю динамику и проверю запас времени.",
} as const;

const reportCoverageStatuses = [
  "confirmed",
  "partial",
  "needs_input",
  "contradiction",
] as const satisfies readonly FounderReportSectionStatus[];

const readinessStatusLabels: Readonly<Record<FounderReportReadinessStatus, string>> = {
  ready: "Готово",
  provisional: "Предварительно",
  blocked: "Заблокировано",
};

const reportCoverageLabels: Readonly<Record<FounderReportSectionStatus, string>> = {
  confirmed: "Заявлено в документе",
  partial: "Частично",
  needs_input: "Нет данных",
  contradiction: "Противоречие",
};

const metricSlotOrder = [
  "mrr",
  "arr",
  "gross_margin",
  "burn_rate",
  "runway",
  "retention",
] as const satisfies readonly FounderMetricSlot[];

const metricAliases: Readonly<Record<string, FounderMetricSlot>> = {
  mrr: "mrr",
  monthly_recurring_revenue: "mrr",
  revenue: "mrr",
  arr: "arr",
  annual_recurring_revenue: "arr",
  gross_margin: "gross_margin",
  gross_margin_ratio: "gross_margin",
  burn: "burn_rate",
  burn_rate: "burn_rate",
  monthly_burn: "burn_rate",
  net_burn: "burn_rate",
  monthly_net_burn: "burn_rate",
  runway: "runway",
  runway_months: "runway",
  retention: "retention",
  logo_retention: "retention",
  net_revenue_retention: "retention",
  nrr: "retention",
};

export function buildFounderChartsPresentation(
  snapshot: StartupReportSnapshotResponse | null,
): readonly FounderChartPresentation[] {
  if (!snapshot) return [];
  const charts: FounderChartPresentation[] = [];
  const marketSizing = analyticsProjection(snapshot.analytics.market_points.slice(0, 3));
  if (marketSizing.points.length > 0) {
    charts.push({
      key: "market_sizing",
      title: "Размер рынка",
      description: "TAM / SAM / SOM из безопасной аналитической проекции отчета.",
      points: marketSizing.points,
      scale: marketSizing.scale,
    });
  }
  const confirmedMetrics = analyticsProjection(snapshot.analytics.metric_points.slice(0, 8));
  if (confirmedMetrics.points.length > 0) {
    charts.push({
      key: "confirmed_metrics",
      title: "Метрики из документов",
      description:
        "Только безопасные рассчитанные бизнес-метрики; внутренние ссылки не используются.",
      points: confirmedMetrics.points,
      scale: confirmedMetrics.scale,
    });
  }
  const readinessCoverage = readinessCoveragePoints(snapshot);
  if (readinessCoverage.length > 0) {
    charts.push({
      key: "readiness_coverage",
      title: "Готовность метрик",
      description: "Измерения готовности сгруппированы по проверяемому статусу.",
      points: readinessCoverage,
      scale: "shared",
    });
  }
  charts.push({
    key: "report_coverage",
    title: "Покрытие отчета",
    description: "Статусы доказательности по 12 основным разделам отчета.",
    points: reportCoveragePoints(snapshot),
    scale: "shared",
  });
  return charts;
}

export function buildFounderMetricDashboardPresentation(
  snapshot: StartupReportSnapshotResponse | null,
): FounderMetricDashboardPresentation {
  if (!snapshot) {
    return { cards: [], contradictions: [], mrrSeries: [], summary: missingFinancialSummary };
  }

  const cardsBySlot = new Map<FounderMetricSlot, FounderMetricDashboardCard>();
  const mrrSeries: FounderMetricDashboardCard[] = [];
  snapshot.analytics.metric_points.slice(0, 100).forEach((point, index) => {
    const slot = metricAliases[normalizeMetricKey(point.key)];
    if (!slot) return;

    const safePeriod = point.period_ru?.trim() || "Текущий период";
    const provenance = metricPointProvenance(point.status);
    const projected: FounderMetricDashboardCard = {
      slot,
      provenance,
      key: `${slot}-${index}`,
      label: safePeriod,
      value: point.value,
      displayValue: displayFounderMetricValue(slot, point.value, point.unit ?? undefined),
      detail: `${safePeriod} · ${metricPointDetail(provenance)}`,
    };
    cardsBySlot.set(slot, projected);
    if (slot === "mrr" && provenance === "source_fact") mrrSeries.push(projected);
  });

  const cards = metricSlotOrder.flatMap((slot) => {
      const point = cardsBySlot.get(slot);
      return point ? [point] : [];
    });
  const contradictions = metricContradictions(snapshot.metric_cards);
  return {
    cards,
    contradictions,
    mrrSeries: mrrSeries.slice(-6),
    summary: financialSummary(cards, contradictions),
  };
}

export function buildFounderScenarioMetricChartPresentation(
  selectedScenario: StartupScenarioVariant | null,
): FounderChartPresentation | null {
  if (!selectedScenario) return null;
  const points = Object.values(selectedScenario.metrics)
    .slice(0, 6)
    .map(scenarioMetricChartPoint)
    .filter((point): point is FounderScenarioChartPoint => point !== null);
  if (points.length === 0) return null;
  return {
    key: "scenario_projection",
    title: `Сценарный диапазон: ${formatScenario(selectedScenario.scenario_key)}`,
    description:
      "Сценарная проекция: диапазон не заменяет подтверждённые фактические данные и требует отдельной проверки.",
    points,
    scale: sharedScale(points.map((point) => point.key)),
  };
}

function financialSummary(
  cards: readonly FounderMetricDashboardCard[],
  contradictions: readonly FounderMetricDashboardContradiction[],
): FounderMetricDashboardPresentation["summary"] {
  if (contradictions.length > 0) {
    return {
      title: "Финансовые данные требуют сверки источников",
      detail: cards.length > 0
        ? "Часть текущих метрик уже извлечена, но противоречивые значения нельзя использовать как единый факт."
        : "В отчёте есть конкурирующие значения — подтвердите источник и период перед расчётами.",
    };
  }
  if (cards.length > 0) {
    return {
      title: "Текущие финансовые наблюдения загружены",
      detail: "Факты, расчёты и оценки показаны отдельно; добавьте временной ряд для анализа динамики.",
    };
  }
  return missingFinancialSummary;
}

function metricContradictions(
  cards: Readonly<Record<string, FounderReportMetricCardResponse>>,
): readonly FounderMetricDashboardContradiction[] {
  const bySlot = new Map<FounderMetricSlot, FounderMetricDashboardContradiction>();
  Object.entries(cards).forEach(([key, card]) => {
    if (card.status !== "contradiction") return;
    const slot = metricAliases[normalizeMetricKey(key)];
    if (!slot) return;
    bySlot.set(slot, {
      slot,
      detail: card.summary_ru.trim() || card.next_unlock_ru.trim(),
    });
  });
  return metricSlotOrder.flatMap((slot) => {
    const contradiction = bySlot.get(slot);
    return contradiction ? [contradiction] : [];
  });
}

function scenarioMetricChartPoint(metric: StartupScenarioMetric): FounderScenarioChartPoint | null {
  const range = metric.value_range;
  if (!range) return null;
  const midpoint = scenarioRangeMidpoint(range.lower, range.upper);
  if (midpoint === null) return null;
  const presentation = presentScenarioMetric(metric);
  const dependencySummary = presentation.dependencies.join(", ") || "не требуются";
  const sourceSummary = presentation.sourceReferences.length > 0
    ? `${presentation.sourceLabel}; ${presentation.sourceReferences.join(", ")}`
    : presentation.sourceLabel;
  return {
    key: presentation.title,
    label: presentation.title,
    value: midpoint,
    displayValue: presentation.value,
    detail: [
      presentation.trustStatement,
      `Диапазон: ${presentation.value}`,
      `Формула: ${presentation.formula}`,
      `Зависимости: ${dependencySummary}`,
      `Источники: ${sourceSummary}`,
      `План проверки: ${presentation.validationPlan}`,
    ].join(" · "),
    provenance: presentation.trustStatement,
    rangeLabel: presentation.value,
    formula: presentation.formula,
    dependencies: presentation.dependencies,
    sourceRefs: presentation.sourceReferences,
    validationPlan: presentation.validationPlan,
  };
}

function scenarioRangeMidpoint(lower: string | null, upper: string | null): number | null {
  const parsedLower = scenarioRangeNumber(lower);
  const parsedUpper = scenarioRangeNumber(upper);
  if (parsedLower !== null && parsedUpper !== null) return (parsedLower + parsedUpper) / 2;
  return parsedLower ?? parsedUpper;
}

function scenarioRangeNumber(value: string | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function analyticsProjection(points: readonly FounderReportAnalyticsPoint[]): Readonly<{
  points: readonly FounderChartPoint[];
  scale: "shared" | "independent";
}> {
  return {
    points: points.map(chartPointFromAnalytics),
    scale: sharedScale(points.map((point) => point.unit ?? "")),
  };
}

function chartPointFromAnalytics(point: FounderReportAnalyticsPoint): FounderChartPoint {
  return {
    key: point.key,
    label: point.label_ru,
    value: point.value,
    displayValue: displayAnalyticsValue(point),
    detail: [analyticsStatusLabel(point.status), point.period_ru]
      .filter(Boolean)
      .join(" · "),
  };
}

function analyticsStatusLabel(status: FounderReportAnalyticsPoint["status"]): string {
  if (status === "confirmed") return formatProvenance("source_fact").toLocaleLowerCase("ru-RU");
  if (status === "calculated") return "расчёт";
  if (status === "contradiction") return "есть расхождение";
  return "оценка";
}

function metricPointProvenance(
  status: FounderReportAnalyticsPoint["status"],
): FounderMetricDashboardCard["provenance"] {
  if (status === "confirmed") return "source_fact";
  if (status === "calculated") return "calculated";
  if (status === "contradiction") return "contradiction";
  return "estimated";
}

function metricPointDetail(
  provenance: FounderMetricDashboardCard["provenance"],
): string {
  if (provenance === "source_fact") return formatProvenance("source_fact").toLocaleLowerCase("ru-RU");
  if (provenance === "calculated") return "рассчитано по данным отчета";
  if (provenance === "contradiction") return "есть расхождение в источниках";
  return "оценка по данным отчета";
}

function sharedScale(keys: readonly string[]): "shared" | "independent" {
  return new Set(keys).size <= 1 ? "shared" : "independent";
}

function readinessCoveragePoints(snapshot: StartupReportSnapshotResponse): FounderChartPoint[] {
  const counts = new Map<FounderReportReadinessStatus, number>();
  for (const dimension of snapshot.analytics.readiness_dimensions) {
    counts.set(dimension.status, (counts.get(dimension.status) ?? 0) + 1);
  }
  return (["ready", "provisional", "blocked"] as const).flatMap((status) => {
    const count = counts.get(status) ?? 0;
    if (count === 0 && counts.size === 0) return [];
    return [
      {
        key: status,
        label: readinessStatusLabels[status],
        value: count,
        displayValue: String(count),
        detail: "измерения готовности",
      },
    ];
  });
}

function reportCoveragePoints(snapshot: StartupReportSnapshotResponse): FounderChartPoint[] {
  const counts = new Map<FounderReportSectionStatus, number>(
    reportCoverageStatuses.map((status) => [status, 0]),
  );
  const sectionsByKey = new Map(snapshot.main_sections.map((section) => [section.key, section]));
  for (const sectionKey of REPORT_MAIN_SECTION_ORDER) {
    const status =
      sectionsByKey.get(sectionKey as StartupReportSectionKey)?.status ?? "needs_input";
    counts.set(status, (counts.get(status) ?? 0) + 1);
  }
  return reportCoverageStatuses.map((status) => {
    const count = counts.get(status) ?? 0;
    return {
      key: status,
      label: reportCoverageLabels[status],
      value: count,
      displayValue: String(count),
      detail: "основные разделы отчета",
    };
  });
}

function normalizeMetricKey(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/gu, "_");
}

function displayAnalyticsValue(point: FounderReportAnalyticsPoint): string {
  return displayFounderMetricValue(
    metricAliases[normalizeMetricKey(point.key)] ?? "arr",
    point.value,
    point.unit ?? undefined,
  );
}

function displayFounderMetricValue(
  slot: FounderMetricSlot,
  value: number,
  unit: string | undefined,
): string {
  const normalizedUnit = unit?.trim().toLowerCase() ?? "";
  if (
    normalizedUnit === "ratio" ||
    ((slot === "gross_margin" || slot === "retention") && value >= 0 && value <= 1)
  ) {
    return `${formatFounderNumber(value * 100)}%`;
  }
  if (normalizedUnit === "%" || normalizedUnit === "percent" || normalizedUnit === "percentage") {
    return `${formatFounderNumber(value)}%`;
  }
  if (slot === "runway" || normalizedUnit === "month" || normalizedUnit === "months") {
    return `${formatFounderNumber(value)} мес.`;
  }
  const currencySymbol =
    normalizedUnit === "usd"
      ? "$"
      : normalizedUnit === "eur"
        ? "€"
        : normalizedUnit === "rub"
          ? "₽"
          : normalizedUnit === "kzt"
            ? "₸"
            : null;
  if (currencySymbol) return `${currencySymbol}${formatFounderNumber(value)}`;
  return [formatFounderNumber(value), unit?.trim()].filter(Boolean).join(" ");
}

function formatFounderNumber(value: number): string {
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(value);
}

export function founderChartBarWidth(value: number, maximum: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0%";
  const safeMaximum = Number.isFinite(maximum) && maximum > 0 ? maximum : value;
  return `${Math.min(100, Math.max(4, (value / safeMaximum) * 100))}%`;
}
