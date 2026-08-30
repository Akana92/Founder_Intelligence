import type {
  FounderReportSectionStatus,
  StartupReportSectionKey,
  StartupReportSnapshotResponse,
  StartupScenarioMetric,
  StartupScenarioVariant,
} from "./contracts.ts";
import { presentScenarioMetric } from "./founder-readable-presentation.ts";

const DEEP_SECTION_ORDER = [
  "market_size",
  "competitors",
  "risks",
  "action_plan",
] as const satisfies readonly StartupReportSectionKey[];

const MAX_PRIORITY_QUESTIONS = 3;
const MAX_FOUNDER_GAPS = 12;
const MAX_DEEP_SECTION_ROWS = 8;
const MAX_DEEP_SECTION_ITEMS = 8;

type FounderAnalysisStageStatus =
  | "available"
  | "missing_readiness"
  | "lineage_mismatch";

export type FounderReadinessStagePresentation = Readonly<{
  key: "primary" | "deep";
  label: string;
  status: FounderAnalysisStageStatus;
}>;

export type FounderReadinessSectionPresentation = Readonly<{
  key: (typeof DEEP_SECTION_ORDER)[number];
  status: FounderReportSectionStatus;
  summary: string;
  rows: readonly (readonly string[])[];
  items: readonly string[];
}>;

export type FounderReadinessDimensionCard = Readonly<{
  key: string;
  labelRu: string;
  statusLabelRu: string;
  explanationRu: string;
}>;

export type FounderReadinessGapCard = Readonly<{
  code: string;
  textRu: string;
}>;

export type FounderScenarioReadinessCard = Readonly<{
  key: string;
  labelRu: string;
  statusLabelRu: string;
  explanationRu: string;
}>;

export type FounderReadinessPresentation = Readonly<{
  stages: readonly FounderReadinessStagePresentation[];
  readiness: Readonly<{
    status: "available" | "missing" | "lineage_mismatch";
    dimensionCards: readonly FounderReadinessDimensionCard[];
  }>;
  gaps: readonly string[];
  gapCards: readonly FounderReadinessGapCard[];
  questions: readonly string[];
  deepSections: readonly FounderReadinessSectionPresentation[];
  scenarioValidationCards: readonly FounderScenarioReadinessCard[];
}>;

type FounderReadinessProfileIdentity = Readonly<{
  case_id: string;
  data_revision: number;
}>;

type FounderReadinessGtmIdentity = Readonly<{
  case_id: string;
  snapshot_revision: number;
}>;

const deepHeadingFallbacks: Readonly<Record<(typeof DEEP_SECTION_ORDER)[number], string>> = {
  market_size: "Подтверждённые факты",
  competitors: "Подтверждённые факты",
  risks: "Подтверждённые факты",
  action_plan: "Следующие действия",
};

function publicRevisionMatches(
  profile: FounderReadinessProfileIdentity,
  gtm: FounderReadinessGtmIdentity,
  reportCaseId: string | null,
  reportSnapshot: StartupReportSnapshotResponse,
): boolean {
  return (
    profile.case_id === gtm.case_id &&
    profile.case_id === reportCaseId &&
    profile.data_revision === reportSnapshot.data_revision &&
    gtm.snapshot_revision === reportSnapshot.data_revision
  );
}

export function buildFounderReadinessPresentation({
  profile,
  gtm,
  reportCaseId,
  reportSnapshot,
  selectedScenario = null,
}: Readonly<{
  profile: FounderReadinessProfileIdentity;
  gtm: FounderReadinessGtmIdentity;
  reportCaseId: string | null;
  reportSnapshot: StartupReportSnapshotResponse;
  selectedScenario?: StartupScenarioVariant | null;
}>): FounderReadinessPresentation {
  const revisionMatches = publicRevisionMatches(profile, gtm, reportCaseId, reportSnapshot);
  const hasReadiness = reportSnapshot.analytics.readiness_dimensions.length > 0;
  const stages: readonly FounderReadinessStagePresentation[] = [
    {
      key: "primary",
      label: "Первичный анализ",
      status: revisionMatches ? "available" : "lineage_mismatch",
    },
    {
      key: "deep",
      label: "Готовность проекта и глубокие вопросы",
      status: !revisionMatches
        ? "lineage_mismatch"
        : hasReadiness
          ? "available"
          : "missing_readiness",
    },
  ];

  if (!revisionMatches) {
    return {
      stages,
      readiness: { status: "lineage_mismatch", dimensionCards: [] },
      gaps: [],
      gapCards: [],
      questions: [],
      deepSections: [],
      scenarioValidationCards: [],
    };
  }

  const sectionsByKey = new Map(
    reportSnapshot.main_sections.map((section) => [section.key, section]),
  );
  const gaps = founderItemsFromSection(sectionsByKey.get("evidence_gaps")).slice(
    0,
    MAX_FOUNDER_GAPS,
  );
  const questions = founderItemsFromSection(
    sectionsByKey.get("diligence_questions"),
  ).slice(0, MAX_PRIORITY_QUESTIONS);

  return {
    stages,
    readiness: {
      status: hasReadiness ? "available" : "missing",
      dimensionCards: reportSnapshot.analytics.readiness_dimensions.map((dimension) => ({
        key: dimension.key,
        labelRu: dimension.label_ru,
        statusLabelRu: dimension.status_label_ru,
        explanationRu: dimension.explanation_ru,
      })),
    },
    gaps,
    gapCards: gaps.map((gap) => ({ code: gap, textRu: gap })),
    questions,
    scenarioValidationCards: buildFounderScenarioReadinessPresentation(selectedScenario),
    deepSections: DEEP_SECTION_ORDER.flatMap((key) => {
      const section = sectionsByKey.get(key);
      if (!section) return [];
      return {
        key,
        status: section.status,
        summary: section.summary_ru,
        rows: section.known_facts_ru
          .slice(0, MAX_DEEP_SECTION_ROWS)
          .map((fact) => [section.content_heading_ru || deepHeadingFallbacks[key], fact]),
        items: [
          ...section.blockers_ru,
          ...section.next_data_ru,
          ...section.unlocks_ru,
        ].slice(0, MAX_DEEP_SECTION_ITEMS),
      };
    }),
  };
}

export function buildFounderScenarioReadinessPresentation(
  selectedScenario: StartupScenarioVariant | null,
): readonly FounderScenarioReadinessCard[] {
  if (!selectedScenario) return [];
  return Object.values(selectedScenario.metrics).slice(0, 6).map(scenarioReadinessCard);
}

function scenarioReadinessCard(metric: StartupScenarioMetric): FounderScenarioReadinessCard {
  const hasGaps = metric.gaps.length > 0 || metric.value_range === null;
  const presentation = presentScenarioMetric(metric);
  const statusLabelRu = hasGaps
    ? "Нужны зависимости сценария"
    : metric.acceptance === "accepted"
      ? "Сценарий принят как план"
      : "Нужна проверка сценария";
  return {
    key: metric.metric_key,
    labelRu: presentation.title,
    statusLabelRu,
    explanationRu: [
      `Происхождение: ${presentation.trustStatement}`,
      `Диапазон: ${presentation.value}`,
      `Формула: ${presentation.formula}`,
      `Зависимости: ${presentation.dependencies.join(", ") || "не требуются"}`,
      `Источники: ${presentation.sourceLabel}${presentation.sourceReferences.length > 0 ? `; ${presentation.sourceReferences.join(", ")}` : ""}`,
      `План проверки: ${presentation.validationPlan}`,
      `Что подтвердит: ${presentation.confirmationGuidance}`,
      presentation.gaps.length > 0 ? `Пробелы: ${presentation.gaps.join(", ")}` : null,
    ].filter(Boolean).join(" · "),
  };
}

function founderItemsFromSection(
  section:
    | StartupReportSnapshotResponse["main_sections"][number]
    | undefined,
): readonly string[] {
  if (!section) return [];
  return [...section.blockers_ru, ...section.next_data_ru, ...section.unlocks_ru];
}
