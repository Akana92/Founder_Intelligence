"use client";

import {
  ArrowRight,
  BarChart3,
  Calculator,
  CalendarDays,
  ChartNoAxesColumnIncreasing,
  CheckCircle2,
  ChevronDown,
  CircleCheck,
  CircleDollarSign,
  Clock3,
  FilePlus2,
  FileText,
  Globe2,
  Hourglass,
  LineChart,
  LoaderCircle,
  MessageSquareText,
  Rocket,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
  TriangleAlert,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import type {
  ResearchJobResponse,
  StartupGtmResponse,
  ScenarioProjectionResponse,
  StartupScenarioMetric,
  StartupScenarioVariant,
  StartupProfileFieldName,
  StartupProfileResponse,
  StartupReportSectionKey,
  StartupReportSnapshotResponse,
} from "../lib/contracts";
import {
  buildFounderMetricDashboardPresentation,
  buildFounderScenarioMetricChartPresentation,
  founderChartBarWidth,
  type FounderMetricDashboardCard,
  type FounderMetricDashboardContradiction,
  type FounderMetricSlot,
} from "../lib/chart-presentation";
import { mergeCaseCopilotMetricCards } from "../lib/case-copilot-presentation";
import {
  formatFounderStage,
  formatScenario,
  presentScenarioMetric,
  type FounderScenarioMetricPresentation,
} from "../lib/founder-readable-presentation";
import { buildFounderScenarioReadinessPresentation } from "../lib/readiness-presentation";
import { buildFounderReportPresentation } from "../lib/report-presentation";
import type {
  ScenarioMetricChange,
  ScenarioMetricComparison,
  ScenarioMetricComparisonValue,
} from "../lib/scenario-presentation";
import {
  presentAcceptedDocumentGateState,
  presentGate2ApprovalBlock,
} from "./founder-task-b-presentation";

import styles from "./founder-analysis-pages.module.css";

export type FounderAnalysisPageId = "progress_gate2" | "overview" | "metrics";
export type FounderAnalysisStage =
  | "idle"
  | "files_selected"
  | "analysis_running"
  | "primary_ready"
  | "deep_ready"
  | "error";

export type FounderAnalysisWorkspace = Readonly<{
  acceptedDocumentIds?: readonly string[];
  canApproveGate2?: boolean;
  profile?: StartupProfileResponse | null;
  gtm?: StartupGtmResponse | null;
  scenarios?: ScenarioProjectionResponse | null;
  selectedScenario?: StartupScenarioVariant | null;
  researchJob?: ResearchJobResponse | null;
  researchMetricComparison?: ScenarioMetricComparison | null;
  reportSnapshot?: StartupReportSnapshotResponse | null;
  stage?: FounderAnalysisStage;
  filesCount?: number;
  lastKnownStatus?: string | null;
  report?: Readonly<{
    freezeAvailable?: boolean;
    snapshotLabel?: string;
  }> | null;
}>;

export type FounderAnalysisPagesProps = Readonly<{
  page: FounderAnalysisPageId;
  workspace?: FounderAnalysisWorkspace | null;
  onGate2?: (decision: "approved" | "denied") => void;
  onGate3?: () => void;
  onOpenAdvisor?: () => void;
  onOpenResearch?: () => void;
  onOpenMetrics?: () => void;
  onOpenMarket?: () => void;
  onOpenReport?: () => void;
  onAddEvidence?: () => void;
}>;

type Tone = "pink" | "green" | "amber" | "blue" | "muted";
type MetricCardTone = "green" | "amber" | "pink" | "needs";
type Gate2AgentIconTone = "document" | "profile" | "metrics" | "market" | "risk" | "gtm";
type Gate2AgentRouteTone = "complete" | "active" | "queued";

type MetricCardView = Readonly<{
  slot: FounderMetricSlot;
  title: string;
  value: string;
  copy: string;
  status: FounderMetricDashboardCard["provenance"] | StartupScenarioMetric["provenance"] | "needs";
  tone: MetricCardTone;
  presentation?: FounderScenarioMetricPresentation;
  confirmationGuidance?: string;
}>;

type Gate2AgentRow = Readonly<{
  title: string;
  copy: string;
  status: string;
  statusA11y?: string;
  icon: LucideIcon;
  iconTone: Gate2AgentIconTone;
  routeTone: Gate2AgentRouteTone;
  statusIcon: LucideIcon;
  tone: Tone;
  active: boolean;
  progress: Readonly<{
    value: number;
    label: string;
  }> | null;
}>;

type OverviewSignalCard = Readonly<{
  title: string;
  copy: string;
  status: string;
  tone: Tone;
  icon: LucideIcon;
}>;

type DocumentUnderstoodRow = Readonly<{
  fieldName: StartupProfileFieldName;
  label: string;
  value: string;
  statusLabel: string;
  tone: Tone;
}>;

type ProfileCoverageStats = Readonly<{
  totalFieldCount: number;
  coveredFieldCount: number;
  sourceFactFieldCount: number;
  missingFieldCount: number;
  contradictionFieldCount: number;
  coveragePercent: number;
  evidenceBackedPercent: number;
}>;

type OverviewSuggestion = Readonly<{
  title: string;
  issue: string;
  action: string;
}>;

type MetricsResearchSummary = Readonly<{
  acceptedSourceCount: number;
  changedMetrics: readonly ScenarioMetricChange[];
  changedBlockLabels: readonly string[];
  revisionLabel: string | null;
  sourceLabels: readonly string[];
  sourceUrls: readonly Readonly<{
    domain: string;
    researchRunDate: string;
    url: string;
  }>[];
}>;

const blockedToken = "MIS" + "SING";
const unsafeFounderPattern = new RegExp(
  `(?:\\b${blockedToken}\\b|\\bunknown\\b|\\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\\s*:|${"sha" + "256:"}[0-9a-f]{64}|[A-Za-z]:[\\\\/][^\\s]+|\\b(?:secret|token)\\b)`,
  "iu",
);

const gateSteps = [
  ["1", "Документы"],
  ["2", "Профиль"],
  ["3", "Метрики"],
  ["4", "Рынок"],
  ["5", "Риски"],
  ["6", "Рекомендации"],
  ["7", "Отчёт"],
] as const;

const overviewMrrBoosterTitle = "Добавьте ежемесячную регулярную выручку (MRR)";
const overviewDataBoosters = [
  [overviewMrrBoosterTitle, "уточню темп роста", LineChart],
  ["Добавьте данные об оттоке клиентов", "рассчитаю удержание и ценность клиента (LTV)", CalendarDays],
  ["Добавьте расходы на продажи", "проверю стоимость привлечения клиента (CAC) и окупаемость", CircleDollarSign],
] as const satisfies readonly (readonly [string, string, LucideIcon])[];

const metricDataBoosters = [
  ["Расходы на продажи + новые клиенты", "рассчитаю стоимость привлечения клиента (CAC)", BarChart3],
  ["Отток клиентов + средний чек", "рассчитаю ценность клиента (LTV)", CalendarDays],
  ["Движение денег", "построю сценарии запаса времени", CircleDollarSign],
] as const satisfies readonly (readonly [string, string, LucideIcon])[];

const metricPeriods = ["3M", "6M", "12M"] as const;

const requiredPrimaryProfileFields = [
  "startup_name",
  "one_line_description",
  "problem",
  "icp",
  "pricing_revenue_model",
  "stage",
] as const satisfies readonly StartupProfileFieldName[];

const problemActions = [
  "Проверить тарифы по ценности",
  "Снизить время подключения клиента",
  "Зафиксировать недельную воронку продаж",
] as const;

function safeText(value: unknown, fallback: string): string {
  if (typeof value !== "string") return fallback;
  const text = value.trim();
  if (!text || unsafeFounderPattern.test(text)) return fallback;
  return text.length > 170 ? `${text.slice(0, 167)}...` : text;
}

function fieldValue(
  workspace: FounderAnalysisWorkspace | null | undefined,
  field: StartupProfileFieldName,
  fallback: string,
): string {
  return safeText(workspace?.profile?.fields[field].values[0], fallback);
}

function isSourceFactWithEvidence(
  field: StartupProfileResponse["fields"][StartupProfileFieldName] | undefined,
): boolean {
  return Boolean(
    field &&
    field.status === "source_fact" &&
    field.values.length > 0 &&
    field.evidence_refs.length > 0,
  );
}

function sourceConfidenceWeight(confidence: string | undefined): number {
  const numericConfidence = Number(confidence);
  if (!Number.isFinite(numericConfidence)) return 0;
  return Math.min(1, Math.max(0, numericConfidence));
}

function profileConfidenceScore(
  workspace: FounderAnalysisWorkspace | null | undefined,
): number | null {
  const fields = workspace?.profile?.fields;
  if (!fields) return null;
  const coveredCoreWeight = requiredPrimaryProfileFields.reduce((total, fieldName) => {
    const field = fields[fieldName];
    if (!isSourceFactWithEvidence(field)) return total;
    return total + sourceConfidenceWeight(fields[fieldName]?.confidence);
  }, 0);
  return Math.round((coveredCoreWeight / requiredPrimaryProfileFields.length) * 100);
}

function profileFieldStatusPresentation(
  field: StartupProfileResponse["fields"][StartupProfileFieldName] | undefined,
): Readonly<{ statusLabel: string; tone: Tone }> {
  if (isSourceFactWithEvidence(field)) {
    return { statusLabel: "Заявлено в документе", tone: "green" };
  }
  if (field?.status === "contradiction") {
    return { statusLabel: "Противоречие — нужно решение", tone: "pink" };
  }
  if (field?.status === "inference") {
    return { statusLabel: "Гипотеза — подтвердите", tone: "blue" };
  }
  return { statusLabel: "Нужно заполнить", tone: "muted" };
}

function documentUnderstoodRows(
  workspace: FounderAnalysisWorkspace | null | undefined,
): readonly DocumentUnderstoodRow[] {
  const rows = [
    {
      fieldName: "one_line_description",
      label: "Продукт",
      fallback: "Не найдено в документе — опишите продукт одной строкой",
    },
    {
      fieldName: "icp",
      label: "Клиент",
      fallback: "Уточните целевую аудиторию",
    },
    {
      fieldName: "problem",
      label: "Проблема",
      fallback: "Не найдено в документе — укажите боль клиента",
    },
    {
      fieldName: "pricing_revenue_model",
      label: "Монетизация",
      fallback: "Не найдено в документе — укажите, кто и за что платит",
    },
    {
      fieldName: "stage",
      label: "Стадия",
      fallback: "Укажите текущую стадию",
    },
  ] as const satisfies readonly {
    fieldName: StartupProfileFieldName;
    label: string;
    fallback: string;
  }[];
  return rows.map(({ fieldName, label, fallback }) => {
    const field = workspace?.profile?.fields[fieldName];
    const status = profileFieldStatusPresentation(field);
    return {
      fieldName,
      label,
      value: isSourceFactWithEvidence(field)
        ? fieldName === "stage"
          ? formatFounderStage(fieldValue(workspace, fieldName, fallback))
          : fieldValue(workspace, fieldName, fallback)
        : fallback,
      ...status,
    };
  });
}

function stageCopy(stage: FounderAnalysisStage | undefined): string {
  if (stage === "analysis_running") return "Анализ выполняется";
  if (stage === "primary_ready") return "Этап 2 готов";
  if (stage === "deep_ready") return "Глубокий анализ готов";
  if (stage === "error") return "Нужна безопасная проверка";
  if (stage === "files_selected") return "Материалы готовы к анализу";
  return "Новый анализ";
}

function analysisProgressStage(stage: FounderAnalysisStage | undefined): Readonly<{
  active: number;
  completedThrough: number;
  current: number;
}> {
  if (stage === "deep_ready") {
    return { active: 6, completedThrough: 5, current: 7 };
  }
  if (stage === "primary_ready") {
    return { active: 1, completedThrough: 0, current: 2 };
  }
  if (stage === "analysis_running" || stage === "error") {
    return { active: 1, completedThrough: 0, current: 2 };
  }
  return { active: 0, completedThrough: -1, current: 1 };
}

function stageProgressSummary(stage: FounderAnalysisStage | undefined): Readonly<{
  completed: number;
  value: number;
  label: string;
}> {
  const analysisProgress = analysisProgressStage(stage);
  const progress = {
    completed: Math.max(
      0,
      Math.min(gateSteps.length, analysisProgress.completedThrough + 1),
    ),
  };
  const value = Math.round((progress.completed / gateSteps.length) * 100);
  return {
    ...progress,
    value,
    label: `${progress.completed} из ${gateSteps.length} этапов завершено`,
  };
}

function report(workspace: FounderAnalysisWorkspace | null | undefined) {
  return workspace?.reportSnapshot
    ? buildFounderReportPresentation(workspace.reportSnapshot)
    : null;
}

function sectionStatusCounts(workspace: FounderAnalysisWorkspace | null | undefined) {
  const presentation = report(workspace);
  return {
    supported:
      presentation?.sections.filter((section) => section.status === "supported").length ?? 0,
    partial:
      presentation?.sections.filter((section) => section.status === "partial").length ?? 0,
    open:
      presentation?.sections.filter(
        (section) =>
          section.status === "needs_evidence" || section.status === "contradiction",
      ).length ?? 0,
    total: presentation?.sections.length ?? 12,
  };
}

function gate2AgentRows(
  workspace: FounderAnalysisWorkspace | null | undefined,
): readonly Gate2AgentRow[] {
  const stage = workspace?.stage;
  const stageProgress = stageProgressSummary(stage);
  const hasFiles = (workspace?.filesCount ?? 0) > 0;
  const hasDocumentRead = hasDocumentReadEvidence(workspace);
  const hasProfile = hasSourceBackedPrimaryProfile(workspace);
  const hasDeepAnalysis = stage === "deep_ready" && Boolean(workspace?.reportSnapshot);
  const isRunning = stage === "analysis_running";
  const isAwaitingGate2 = stage === "primary_ready";
  const documentState = presentAcceptedDocumentGateState({
    acceptedDocumentCount: (workspace?.acceptedDocumentIds ?? []).length,
    hasDocumentReadEvidence: hasDocumentRead,
    isRunning: hasFiles && isRunning,
    lastKnownStatus: workspace?.lastKnownStatus ?? null,
  });

  return [
    {
      title: "Анализ документов",
      copy: documentState.documentCopy,
      status: documentState.documentStatus,
      icon: FileText,
      iconTone: "document",
      routeTone: hasDocumentRead ? "complete" : documentState.documentActive ? "active" : "queued",
      statusIcon: hasDocumentRead ? CircleCheck : documentState.documentActive ? LoaderCircle : Clock3,
      tone: hasDocumentRead ? "green" : documentState.documentActive ? "pink" : "muted",
      active: documentState.documentActive,
      progress: null,
    },
    {
      title: "Профиль проекта",
      copy: hasProfile
        ? "Профиль собран из полей, заявленных в документах"
        : isRunning
          ? "Формирует первичный профиль"
          : "Нужны данные для первичного профиля",
      status: hasProfile
        ? isAwaitingGate2
          ? "Нужно решение"
          : "Завершено"
        : isRunning
          ? "В процессе"
          : "Ожидает",
      icon: UserRound,
      iconTone: "profile",
      routeTone: hasProfile ? "complete" : isRunning ? "active" : "queued",
      statusIcon: hasProfile && !isAwaitingGate2 ? CircleCheck : Clock3,
      tone: hasProfile ? (isAwaitingGate2 ? "pink" : "green") : isRunning ? "pink" : "muted",
      active: isRunning && !hasProfile,
      progress: null,
    },
    {
      title: "Анализ метрик",
      copy: hasDeepAnalysis
        ? "Метрики и локально перепроверяемые расчёты готовы"
        : isAwaitingGate2
          ? "Продолжит после вашего решения"
          : "Запустится после подтверждения профиля",
      status: hasDeepAnalysis ? "Результат доступен" : isAwaitingGate2 ? "Ждёт решения на этапе 2" : "В очереди",
      statusA11y: isAwaitingGate2 ? "Ожидает решения на этапе 2" : undefined,
      icon: ChartNoAxesColumnIncreasing,
      iconTone: "metrics",
      routeTone: hasDeepAnalysis ? "complete" : isAwaitingGate2 ? "active" : "queued",
      statusIcon: hasDeepAnalysis ? CircleCheck : isAwaitingGate2 ? Clock3 : Hourglass,
      tone: hasDeepAnalysis ? "green" : isAwaitingGate2 ? "pink" : "muted",
      active: isAwaitingGate2,
      progress: isAwaitingGate2 ? stageProgress : null,
    },
    {
      title: "Анализ рынка",
      copy: hasDeepAnalysis
        ? "Рынок, конкуренты и доступные источники сопоставлены"
        : "Следует за проверкой метрик",
      status: hasDeepAnalysis ? "Результат доступен" : "В очереди",
      icon: Globe2,
      iconTone: "market",
      routeTone: hasDeepAnalysis ? "complete" : "queued",
      statusIcon: hasDeepAnalysis ? CircleCheck : Hourglass,
      tone: hasDeepAnalysis ? "green" : "muted",
      active: false,
      progress: null,
    },
    {
      title: "Риски и критика",
      copy: hasDeepAnalysis
        ? "Риски и противоречия проверены"
        : "Начнёт после метрик и рынка",
      status: hasDeepAnalysis ? "Результат доступен" : "В очереди",
      icon: ShieldCheck,
      iconTone: "risk",
      routeTone: hasDeepAnalysis ? "complete" : "queued",
      statusIcon: hasDeepAnalysis ? CircleCheck : Hourglass,
      tone: hasDeepAnalysis ? "green" : "muted",
      active: false,
      progress: null,
    },
    {
      title: "Советник по выходу на рынок",
      copy: hasDeepAnalysis
        ? "Приоритетный план действий готов"
        : "Подготовит план 7 / 30 / 60 / 90 дней",
      status: hasDeepAnalysis ? "Результат доступен" : "В очереди",
      icon: Rocket,
      iconTone: "gtm",
      routeTone: hasDeepAnalysis ? "complete" : "queued",
      statusIcon: hasDeepAnalysis ? CircleCheck : Hourglass,
      tone: hasDeepAnalysis ? "green" : "muted",
      active: false,
      progress: null,
    },
  ];
}

function hasSourceBackedPrimaryProfile(
  workspace: FounderAnalysisWorkspace | null | undefined,
): boolean {
  const fields = workspace?.profile?.fields;
  if (!fields) {
    return false;
  }
  return requiredPrimaryProfileFields.every((fieldName) =>
    isSourceFactWithEvidence(fields[fieldName]),
  );
}

function hasDocumentReadEvidence(
  workspace: FounderAnalysisWorkspace | null | undefined,
): boolean {
  const fields = workspace?.profile?.fields;
  if (!fields) return false;
  return Object.values(fields).some(isSourceFactWithEvidence);
}

function gate2ApprovalMissingPrerequisite(
  workspace: FounderAnalysisWorkspace | null | undefined,
): string | null {
  return presentGate2ApprovalBlock({
    acceptedDocumentCount: (workspace?.acceptedDocumentIds ?? []).length,
    canApproveGate2: Boolean(workspace?.canApproveGate2),
    hasDocumentReadEvidence: hasDocumentReadEvidence(workspace),
  }).disabledPrerequisite;
}

function profileSignalCard(
  workspace: FounderAnalysisWorkspace | null | undefined,
  {
    fieldName,
    label,
    missingCopy,
    icon,
  }: Readonly<{
    fieldName: StartupProfileFieldName;
    label: string;
    missingCopy: string;
    icon: LucideIcon;
  }>,
): OverviewSignalCard {
  const field = workspace?.profile?.fields[fieldName];
  const status = field?.status ?? "insufficient_data";
  const copy = fieldValue(workspace, fieldName, missingCopy);
  if (status === "source_fact") {
    return { title: label, copy, status: "Заявлено", tone: "green", icon };
  }
  if (status === "inference") {
    return { title: label, copy, status: "Гипотеза", tone: "blue", icon };
  }
  if (status === "contradiction") {
    return {
      title: label,
      copy,
      status: "Противоречие",
      tone: "pink",
      icon,
    };
  }
  return {
    title: label,
    copy,
    status: "Нужны данные",
    tone: "muted",
    icon,
  };
}

function profileCoverageStats(
  workspace: FounderAnalysisWorkspace | null | undefined,
): ProfileCoverageStats | null {
  const fields = workspace?.profile ? Object.values(workspace.profile.fields) : [];
  if (fields.length === 0) return null;
  const sourceFactFieldCount = fields.filter(
    (field) =>
      field.status === "source_fact" &&
      field.values.length > 0 &&
      field.evidence_refs.length > 0,
  ).length;
  const contradictionFieldCount = fields.filter(
    (field) => field.status === "contradiction" && field.values.length > 0,
  ).length;
  const missingFieldCount = fields.filter(
    (field) => field.status === "insufficient_data" || field.values.length === 0,
  ).length;
  const coveredFieldCount =
    sourceFactFieldCount;
  const totalFieldCount = fields.length;
  return {
    totalFieldCount,
    coveredFieldCount,
    sourceFactFieldCount,
    missingFieldCount,
    contradictionFieldCount,
    coveragePercent: Math.round((coveredFieldCount / totalFieldCount) * 100),
    evidenceBackedPercent: Math.round((sourceFactFieldCount / totalFieldCount) * 100),
  };
}

function reportIssueCard(
  workspace: FounderAnalysisWorkspace | null | undefined,
  {
    key,
    title,
    missingCopy,
    icon,
  }: Readonly<{
    key: StartupReportSectionKey;
    title: string;
    missingCopy: string;
    icon: LucideIcon;
  }>,
): OverviewSignalCard {
  const section = report(workspace)?.sections.find((candidate) => candidate.key === key);
  const copy = section?.items[0] ?? section?.rows[0]?.slice(1).join(" · ") ?? missingCopy;
  if (!section) return { title, copy, status: "Нужны данные", tone: "muted", icon };
  if (section.status === "supported") {
    return { title, copy, status: section.statusLabel, tone: "green", icon };
  }
  if (section.status === "contradiction") {
    return { title, copy, status: section.statusLabel, tone: "pink", icon };
  }
  if (section.status === "partial") {
    return { title, copy, status: section.statusLabel, tone: "amber", icon };
  }
  return { title, copy, status: section.statusLabel, tone: "muted", icon };
}

function overviewAdvisorSuggestions(
  workspace: FounderAnalysisWorkspace | null | undefined,
): readonly OverviewSuggestion[] {
  const icpStatus = workspace?.profile?.fields.icp.status ?? "insufficient_data";
  const sections = report(workspace)?.sections ?? [];
  const pricingStatus = sections.find((section) => section.key === "financial_assumptions")?.status;
  const gtmStatus = sections.find((section) => section.key === "go_to_market")?.status;

  const icpIssue =
    icpStatus === "source_fact"
      ? "Целевой сегмент (ICP) найден в материалах; проверьте роль покупателя и бюджет."
      : icpStatus === "contradiction"
        ? "В материалах есть противоречивые описания целевой аудитории."
        : icpStatus === "inference"
          ? "Целевой сегмент (ICP) пока остаётся гипотезой и требует подтверждения."
          : "Сегмент, роль покупателя и бюджет требуют подтверждения.";
  const pricingIssue =
    pricingStatus === "supported"
      ? "Финансовые данные есть; проверьте связь цены с ценностью."
      : pricingStatus === "contradiction"
        ? "В цене или финансовой модели есть противоречия."
        : pricingStatus === "partial"
          ? "Цена и финансовая модель подтверждены только частично."
          : "Платёжная готовность и тарифные допущения пока не подтверждены.";
  const gtmIssue =
    gtmStatus === "supported"
      ? "Канал подтверждён; следующий риск — повторяемость конверсий."
      : gtmStatus === "contradiction"
        ? "Данные о канале и воронке противоречат друг другу."
        : gtmStatus === "partial"
          ? "Канал и конверсии подтверждены только частично."
          : "Канал, этапы воронки и конверсии пока не подтверждены.";

  return [
    {
      title: "Уточнить целевой сегмент (ICP)",
      issue: icpIssue,
      action: "Добавьте интервью или описание покупки — я уточню целевой сегмент и канал.",
    },
    {
      title: "Проверить модель цены",
      issue: pricingIssue,
      action: "Добавьте тарифы или результаты пилотов — я сопоставлю цену и ценность.",
    },
    {
      title: "Собрать повторяемую воронку",
      issue: gtmIssue,
      action: "Добавьте этапы и конверсии — я найду узкое место и первый тест.",
    },
  ];
}

function ToneIcon({
  children,
  iconTone,
  tone = "pink",
}: Readonly<{
  children: React.ReactNode;
  iconTone?: Gate2AgentIconTone;
  tone?: Tone;
}>) {
  return (
    <span
      className={`${styles.iconBubble} ${styles[`tone_${tone}`]} ${iconTone ? styles[`agentIcon_${iconTone}`] : ""}`}
    >
      {children}
    </span>
  );
}

function Header({
  title,
  subtitle,
  workspace,
  action,
}: Readonly<{
  title: string;
  subtitle: string;
  workspace?: FounderAnalysisWorkspace | null;
  action?: React.ReactNode;
}>) {
  return (
    <header className={styles.hero}>
      <div>
        <span className={styles.eyebrow}>Карта анализа</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className={styles.heroAside}>
        <span>{stageCopy(workspace?.stage)}</span>
        <strong>{fieldValue(workspace, "startup_name", "Проект без названия")}</strong>
        {action}
      </div>
    </header>
  );
}

function SemicircleGauge({ score }: Readonly<{ score: number }>) {
  const boundedScore = Math.max(0, Math.min(100, score));
  const arcPath = "M 18 144 A 142 142 0 0 1 302 144";

  return (
    <div className={styles.gaugeArc}>
      <svg aria-hidden="true" viewBox="0 0 320 160">
        <defs>
          <linearGradient id="overview-gauge-progress" x1="0" x2="1">
            <stop offset="0" stopColor="#f3a2cf" />
            <stop offset="1" stopColor="#e98bc3" />
          </linearGradient>
        </defs>
        <path
          className={styles.gaugeTrack}
          d={arcPath}
          pathLength="100"
          strokeLinecap="round"
        />
        {boundedScore > 0 ? (
          <path
            className={styles.gaugeProgress}
            d={arcPath}
            pathLength="100"
            strokeDasharray={`${boundedScore} 100`}
            strokeLinecap="round"
          />
        ) : null}
      </svg>
      <span className={styles.gaugeValue}>
        <strong>{boundedScore}</strong>
        <em>/ 100</em>
      </span>
    </div>
  );
}

function DonutMetric({
  children,
  score,
}: Readonly<{ children: React.ReactNode; score: number }>) {
  const boundedScore = Math.max(0, Math.min(100, score));

  return (
    <div className={styles.circularMetricRing}>
      <svg aria-hidden="true" viewBox="0 0 100 100">
        <circle
          className={styles.donutTrack}
          cx="50"
          cy="50"
          pathLength="100"
          r="41"
          strokeLinecap="round"
        />
        {boundedScore > 0 ? (
          <circle
            className={styles.donutProgress}
            cx="50"
            cy="50"
            pathLength="100"
            r="41"
            strokeDasharray={`${boundedScore} 100`}
            strokeLinecap="round"
            transform="rotate(-90 50 50)"
          />
        ) : null}
      </svg>
      <span className={styles.donutIcon}>{children}</span>
    </div>
  );
}

function PinkButton({
  action,
  children,
  onClick,
}: Readonly<{
  action?: string;
  children: React.ReactNode;
  onClick?: () => void;
}>) {
  return (
    <button
      className={styles.pinkButton}
      data-founder-action={action}
      disabled={!onClick}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  );
}

function OutlineButton({
  children,
  onClick,
}: Readonly<{ children: React.ReactNode; onClick?: () => void }>) {
  return (
    <button className={styles.outlineButton} disabled={!onClick} onClick={onClick} type="button">
      {children}
    </button>
  );
}

function ProgressGatePage({
  workspace,
  onGate2,
  onOpenAdvisor,
  onOpenResearch,
}: Readonly<{
  workspace?: FounderAnalysisWorkspace | null;
  onGate2?: (decision: "approved" | "denied") => void;
  onOpenAdvisor?: () => void;
  onOpenResearch?: () => void;
}>) {
  const agentRows = gate2AgentRows(workspace);
  const analysisProgress = analysisProgressStage(workspace?.stage);
  const gateCoverage = profileCoverageStats(workspace);
  const confidenceScore = profileConfidenceScore(workspace);
  const gate2ApprovalBlock = presentGate2ApprovalBlock({
    acceptedDocumentCount: (workspace?.acceptedDocumentIds ?? []).length,
    canApproveGate2: Boolean(workspace?.canApproveGate2),
    hasDocumentReadEvidence: hasDocumentReadEvidence(workspace),
  });
  const acceptedDocumentGateState = presentAcceptedDocumentGateState({
    acceptedDocumentCount: (workspace?.acceptedDocumentIds ?? []).length,
    hasDocumentReadEvidence: hasDocumentReadEvidence(workspace),
    isRunning: workspace?.stage === "analysis_running",
    lastKnownStatus: workspace?.lastKnownStatus ?? null,
  });
  const gate2MissingPrerequisite = gate2ApprovalMissingPrerequisite(workspace);
  const handleGate2Approval = onGate2
    ? () => onGate2("approved")
    : undefined;

  return (
    <section className={styles.page} data-founder-analysis-page="progress-gate2">
      <Header
        action={
          <>
            <span className={styles.statusPill}>
              <LoaderCircle aria-hidden="true" size={18} />
              Шаг {analysisProgress.current} из 7
            </span>
            <button className={styles.backgroundButton} disabled type="button">
              <Clock3 aria-hidden="true" size={18} />
              Работать в фоне
            </button>
          </>
        }
        subtitle="Система читает документы, проверяет выводы и собирает план улучшений."
        title={`Анализ проекта ${fieldValue(workspace, "startup_name", "вашего стартапа")}`}
        workspace={workspace}
      />

      <div className={styles.progressRail} aria-label="Прогресс анализа из семи шагов">
        {gateSteps.map(([number, title], index) => {
          const isDone = index <= analysisProgress.completedThrough;
          const isActive = index === analysisProgress.active;
          const isBeforeActive = index === analysisProgress.active - 1;
          return (
            <article
              className={`${styles.railStep} ${isDone ? styles.isDone : ""} ${isActive ? styles.isActive : ""} ${isBeforeActive ? styles.isBeforeActive : ""}`}
              key={title}
            >
              <span>{isDone ? <CheckCircle2 aria-hidden="true" size={18} /> : number}</span>
              <strong>{title}</strong>
            </article>
          );
        })}
      </div>

      <div className={styles.progressLayout}>
        <section className={`${styles.glassPanel} ${styles.agentPanel}`}>
          <h2>Команда аналитических помощников</h2>
          <div className={styles.agentTimeline}>
            {agentRows.map(({ title, copy, status, statusA11y, icon: Icon, iconTone, routeTone, statusIcon: StatusIcon, tone, active, progress }) => (
              <article
                className={`${styles.agentRow} ${active ? styles.activeAgentRow : ""}`}
                key={title}
              >
                <span
                  aria-hidden="true"
                  className={styles.agentRouteNode}
                  data-route-tone={routeTone}
                />
                <ToneIcon iconTone={iconTone} tone={tone}>
                  <Icon aria-hidden="true" size={23} strokeWidth={2.25} />
                </ToneIcon>
                <div>
                  <strong>{title}</strong>
                  <span>{copy}</span>
                </div>
                <em aria-label={statusA11y} data-tone={tone}>
                  <StatusIcon aria-hidden="true" size={15} strokeWidth={1.9} />
                  {status}
                </em>
                {progress ? (
                  <div className={styles.agentProgress}>
                    <span>{progress.label}</span>
                    <strong>{progress.value}%</strong>
                    <span className={styles.agentProgressTrack} aria-hidden="true">
                      <i style={{ "--agent-progress": `${progress.value}%` } as React.CSSProperties} />
                    </span>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </section>

        <div className={styles.gateColumn}>
          <main className={`${styles.glassPanel} ${styles.gateCard}`}>
            <div className={styles.gateTitle}>
              <span className={styles.gateBadge}>
                <Shield aria-hidden="true" size={52} strokeWidth={1.7} />
                <b>2</b>
              </span>
              <div>
                <span className={styles.eyebrow}>Этап 2</span>
                <h2>Вот как я понял ваш стартап</h2>
              </div>
            </div>
            <span className={styles.eyebrow}>Документ понял так</span>
            <dl className={styles.gateProfile}>
              {documentUnderstoodRows(workspace).map((row) => (
                <div key={row.fieldName}>
                  <dt>{row.label}:</dt>
                  <dd>
                    {row.value}
                    <em data-tone={row.tone}>{row.statusLabel}</em>
                  </dd>
                </div>
              ))}
              <div>
                <dt>Уверенность:</dt>
                <dd className={styles.gateConfidence}>
                  {gateCoverage === null || confidenceScore === null
                    ? "требует подтверждения"
                    : `${confidenceScore}% · ${gateCoverage.sourceFactFieldCount} полей заявлено в документе`}
                </dd>
              </div>
            </dl>
            {(workspace?.acceptedDocumentIds ?? []).length > 0 ? (
              <div className={styles.gateReceipt} role="status">
                <CheckCircle2 aria-hidden="true" size={17} />
                <span>
                  {acceptedDocumentGateState.receiptTitle}
                </span>
                <small>
                  {acceptedDocumentGateState.receiptDetail}
                </small>
              </div>
            ) : null}
            {gate2MissingPrerequisite ? (
              <p className={styles.gatePrerequisite} data-gate2-prerequisite>
                {gate2MissingPrerequisite}. {gate2ApprovalBlock.repairCopy}
              </p>
            ) : null}
            <div className={styles.actionStrip}>
              <PinkButton
                action="gate2-approve"
                onClick={
                  workspace?.canApproveGate2 && hasDocumentReadEvidence(workspace)
                    ? handleGate2Approval
                    : undefined
                }
              >
                Подтвердить и продолжить <ArrowRight aria-hidden="true" size={18} />
              </PinkButton>
              <OutlineButton onClick={onOpenAdvisor}>Заполнить пропуски</OutlineButton>
            </div>
          </main>
          <section className={styles.searchStatus}>
            <ToneIcon tone="pink">
              <Globe2 aria-hidden="true" size={22} />
            </ToneIcon>
            <span>
              Онлайн-ресерч использует только очищенные факты и запускается после явного согласия.
            </span>
            <OutlineButton onClick={onOpenResearch}>Онлайн-ресерч</OutlineButton>
          </section>
        </div>
      </div>

      <section className={styles.safeBanner}>
        <ShieldCheck aria-hidden="true" className={styles.safeBannerIcon} size={34} strokeWidth={1.6} />
        <strong>
          Если вы добавите метрики, я смогу уточнить рост и рассчитать запас времени.
          Либо, после вашего разрешения, могу найти публичные источники.
        </strong>
      </section>
    </section>
  );
}

function OverviewPage({
  workspace,
  onOpenAdvisor,
  onOpenMetrics,
  onOpenMarket,
}: Readonly<{
  workspace?: FounderAnalysisWorkspace | null;
  onOpenAdvisor?: () => void;
  onOpenMetrics?: () => void;
  onOpenMarket?: () => void;
}>) {
  const counts = sectionStatusCounts(workspace);
  const readinessScore = workspace?.reportSnapshot
    ? Math.round(((counts.supported + counts.partial * 0.5) / counts.total) * 100)
    : 0;
  const profileCoverage = profileCoverageStats(workspace);
  const profileCoverageScore = profileCoverage?.coveragePercent ?? null;
  const evidenceScore = workspace?.reportSnapshot
    ? Math.round((counts.supported / counts.total) * 100)
    : 0;
  const scenarioReadinessCards = buildFounderScenarioReadinessPresentation(
    workspace?.selectedScenario ?? null,
  );
  const working = [
    profileSignalCard(workspace, {
      fieldName: "problem",
      label: "Проблема клиента",
      missingCopy: "Если добавите интервью или презентацию, я покажу, чем подтверждается боль.",
      icon: MessageSquareText,
    }),
    profileSignalCard(workspace, {
      fieldName: "traction",
      label: "Сигнал спроса",
      missingCopy: "Если добавите сигналы спроса — выручку, сделки или активность клиентов, я покажу их динамику.",
      icon: CircleDollarSign,
    }),
    profileSignalCard(workspace, {
      fieldName: "icp",
      label: "Целевая аудитория",
      missingCopy: "Если добавите описание целевого сегмента (ICP), я уточню покупателя и канал.",
      icon: Target,
    }),
  ];
  const blockers = [
    reportIssueCard(workspace, {
      key: "financial_assumptions",
      title: "Цена и финансовая модель",
      missingCopy: "Добавьте тарифы, платежи, остаток денег и темп расходов — я проверю цену и рассчитаю запас времени.",
      icon: TriangleAlert,
    }),
    reportIssueCard(workspace, {
      key: "go_to_market",
      title: "Канал продаж",
      missingCopy: "Добавьте канал, конверсию или воронку — я покажу, что можно масштабировать.",
      icon: UserRound,
    }),
    reportIssueCard(workspace, {
      key: "metrics",
      title: "Метрики роста",
      missingCopy: "Добавьте ежемесячную регулярную выручку (MRR), отток клиентов и расходы — я отделю факты от расчётов и гипотез.",
      icon: CircleDollarSign,
    }),
  ];
  const suggestions = overviewAdvisorSuggestions(workspace);
  const growthStage = formatFounderStage(fieldValue(workspace, "stage", "Стадия требует подтверждения"));
  const updateLabel = safeText(
    workspace?.report?.snapshotLabel,
    "Версия отчёта ещё не создана",
  );

  return (
    <section className={styles.page} data-founder-analysis-page="overview">
      <Header
        subtitle={fieldValue(
          workspace,
          "one_line_description",
          "Краткое описание появится после подтверждения профиля",
        )}
        title={fieldValue(workspace, "startup_name", "Проект после анализа")}
        workspace={workspace}
      />

      <div className={styles.overviewHeroActions}>
        <div className={styles.overviewChips}>
          <span className={styles.growthStagePill}>{growthStage}</span>
          <span className={styles.updatedBadge}>
            <CalendarDays aria-hidden="true" size={18} />
            {updateLabel}
          </span>
        </div>
        <OutlineButton onClick={onOpenAdvisor}>
          <Sparkles aria-hidden="true" size={18} />
          Спросить ИИ-советника о проекте
          <ArrowRight aria-hidden="true" size={18} />
        </OutlineButton>
      </div>

      <div className={styles.readinessTop}>
        <section className={`${styles.glassPanel} ${styles.readinessGauge}`}>
          <span>Готовность к росту</span>
          <div className={styles.gaugeStage}>
            <SemicircleGauge score={readinessScore} />
            <p className={styles.gaugeCaption}>
              {workspace?.reportSnapshot ? (
                <>
                  <span>Расчёт сформирован по статусам разделов.</span>
                  <span>
                    {scenarioReadinessCards[0]
                      ? `Сценарная проверка: ${scenarioReadinessCards[0].statusLabelRu}. Подробности расчёта раскрыты в карточках метрик.`
                      : "Факты, пробелы и противоречия показаны ниже."}
                  </span>
                </>
              ) : (
                <>
                  <span>Пока нет документальных данных для оценки.</span>
                  <span>Добавьте материалы — я соберу выводы.</span>
                </>
              )}
            </p>
          </div>
        </section>
        <section className={`${styles.glassPanel} ${styles.circleMetric}`}>
          <span>Покрытие профиля</span>
          <div className={styles.circleMetricBody}>
            <DonutMetric score={profileCoverageScore ?? 0}>
              <ShieldCheck aria-hidden="true" size={36} />
            </DonutMetric>
            <div className={styles.circleMetricCopy}>
              <strong>{profileCoverageScore === null ? "—" : `${profileCoverageScore}%`}</strong>
              <p>
                {profileCoverage === null
                  ? "Добавьте материалы или ответы — я покажу покрытие профиля по полям."
                  : `${profileCoverage.coveredFieldCount}/${profileCoverage.totalFieldCount} полей заполнено, ${profileCoverage.missingFieldCount} требует данных.`}
              </p>
            </div>
          </div>
        </section>
        <section className={`${styles.glassPanel} ${styles.circleMetric}`}>
          <span>Покрытие доказательств</span>
          <div className={styles.circleMetricBody}>
            <DonutMetric score={evidenceScore}>
              <Search aria-hidden="true" size={36} />
            </DonutMetric>
            <div className={styles.circleMetricCopy}>
              <strong>{evidenceScore}%</strong>
              <p>
                {workspace?.reportSnapshot
                  ? "Охвачены области из документов, открытые вопросы отделены от заявлений."
                  : "Покрытие появится после отчёта или ответов на уточняющие вопросы."}
              </p>
            </div>
          </div>
        </section>
      </div>

      <div className={styles.overviewGrid}>
        <section className={`${styles.glassPanel} ${styles.profileMap}`}>
          <h2>Что уже работает</h2>
          <div className={styles.evidenceList}>
            {working.map((card) => (
              <article className={styles.evidenceItem} key={card.title}>
                <ToneIcon tone={card.tone}><card.icon aria-hidden="true" size={23} /></ToneIcon>
                <div>
                  <strong>{card.title}</strong>
                  <span>{card.copy}</span>
                </div>
                <em className={`${styles.evidenceStatus} ${styles[`evidenceStatus_${card.tone}`]}`}>
                  {card.status}
                </em>
              </article>
            ))}
          </div>
        </section>

        <section className={`${styles.glassPanel} ${styles.profileMap}`}>
          <h2>Что требует проверки</h2>
          <div className={styles.evidenceList}>
            {blockers.map((card) => (
              <article className={styles.evidenceItem} key={card.title}>
                <ToneIcon tone={card.tone}><card.icon aria-hidden="true" size={23} /></ToneIcon>
                <div>
                  <strong>{card.title}</strong>
                  <span>{card.copy}</span>
                </div>
                <em className={`${styles.evidenceStatus} ${styles[`evidenceStatus_${card.tone}`]}`}>
                  {card.status}
                </em>
              </article>
            ))}
          </div>
        </section>

        <aside className={`${styles.glassPanel} ${styles.aiSuggestion}`}>
          <span className={styles.eyebrow}>Что предлагает ИИ сейчас</span>
          <div className={styles.evidenceList}>
            {suggestions.map((suggestion) => (
              <article className={styles.suggestionRow} key={suggestion.title}>
                <span className={styles.suggestionIcon}>
                  <Sparkles aria-hidden="true" size={19} />
                </span>
                <div>
                  <div className={styles.suggestionTitleLine}>
                    <strong>{suggestion.title}</strong>
                    <em>Гипотеза ИИ</em>
                  </div>
                  <span className={styles.suggestionIssue}>{suggestion.issue}</span>
                  <span className={styles.suggestionAction}>{suggestion.action}</span>
                </div>
              </article>
            ))}
          </div>
          <PinkButton onClick={onOpenAdvisor}>
            Открыть план улучшений <ArrowRight aria-hidden="true" size={18} />
          </PinkButton>
        </aside>
      </div>

      <section className={styles.addDataStrip}>
        <h2>Что усилит анализ</h2>
        <div>
          {overviewDataBoosters.map(([title, copy, Icon]) => (
            <button
              disabled={title === overviewMrrBoosterTitle ? !onOpenMetrics : !onOpenMarket}
              key={title}
              onClick={title === overviewMrrBoosterTitle ? onOpenMetrics : onOpenMarket}
              type="button"
            >
              <Icon aria-hidden="true" size={22} />
              <span><strong>{title}</strong><em>{copy}</em></span>
              <ArrowRight aria-hidden="true" size={18} />
            </button>
          ))}
          <button
            className={styles.addDataCtaPane}
            disabled={!onOpenMetrics}
            onClick={onOpenMetrics}
            type="button"
          >
            <FilePlus2 aria-hidden="true" size={22} />
            <div>
              <strong>Добавить данные</strong>
              <em>я обновлю выводы и план</em>
            </div>
            <ArrowRight aria-hidden="true" size={18} />
          </button>
        </div>
      </section>

      <p className={styles.overviewDisclaimer}>
        <ShieldCheck aria-hidden="true" size={16} />
        Оценка помогает расставить приоритеты и не является инвестиционной рекомендацией.
      </p>
    </section>
  );
}

function metricCards(
  confirmedCards: readonly FounderMetricDashboardCard[],
  contradictions: readonly FounderMetricDashboardContradiction[],
  scenarioCards: readonly MetricCardView[] = [],
): readonly MetricCardView[] {
  const emptyCards = [
    {
      slot: "mrr",
      title: "MRR — ежемесячная регулярная выручка",
      value: "добавьте ежемесячную выручку",
      copy: "Добавьте регулярную выручку — я покажу темп роста.",
      status: "needs",
      tone: "needs",
    },
    {
      slot: "arr",
      title: "ARR — годовая регулярная выручка",
      value: "расчёт по ежемесячной выручке (MRR)",
      copy: "Появится автоматически после подтверждения ежемесячной выручки (MRR).",
      status: "needs",
      tone: "needs",
    },
    {
      slot: "gross_margin",
      title: "Валовая маржа",
      value: "нужна себестоимость",
      copy: "Добавьте себестоимость — я проверю ориентир для сервисной модели.",
      status: "needs",
      tone: "amber",
    },
    {
      slot: "burn_rate",
      title: "Темп расходов",
      value: "добавьте расходы",
      copy: "Добавьте расходы — я покажу устойчивость трат.",
      status: "needs",
      tone: "needs",
    },
    {
      slot: "runway",
      title: "Запас времени",
      value: "требуется остаток денег",
      copy: "Добавьте остаток денег и чистый расход — я рассчитаю запас времени.",
      status: "needs",
      tone: "needs",
    },
    {
      slot: "retention",
      title: "Удержание клиентов",
      value: "нужна когорта",
      copy: "Добавьте когорту 30 дней — я оценю удержание.",
      status: "needs",
      tone: "needs",
    },
  ] as const satisfies readonly MetricCardView[];
  const confirmedBySlot = new Map(confirmedCards.map((card) => [card.slot, card]));
  const baseCards = emptyCards.map((card) => {
    const confirmed = confirmedBySlot.get(card.slot);
    if (!confirmed) return contradictionMetricCard(card, contradictions) ?? card;
    return {
      ...card,
      value: confirmed.displayValue,
      copy: confirmed.detail,
      status: confirmed.provenance,
      tone: metricToneFromProvenance(confirmed.provenance),
    };
  });
  return mergeCaseCopilotMetricCards(baseCards, scenarioCards);
}

const scenarioMetricSlots = new Set<FounderMetricSlot>([
  "mrr",
  "arr",
  "gross_margin",
  "burn_rate",
  "runway",
  "retention",
]);

function scenarioMetricCards(
  selectedScenario: StartupScenarioVariant | null | undefined,
): readonly MetricCardView[] {
  if (!selectedScenario) return [];
  return Object.values(selectedScenario.metrics)
    .filter((metric): metric is StartupScenarioMetric & { metric_key: FounderMetricSlot } =>
      scenarioMetricSlots.has(metric.metric_key as FounderMetricSlot),
    )
    .map((metric) => {
      const presentation = presentScenarioMetric(metric);
      return {
        slot: metric.metric_key,
        title: presentation.title,
        value: presentation.value,
        copy: `Сценарная оценка. ${presentation.trustStatement}.`,
        status: metric.provenance,
        tone: metric.provenance === "source_fact" ? "green" : "amber",
        presentation,
        confirmationGuidance: presentation.confirmationGuidance,
      };
    });
}

function contradictionMetricCard(
  card: MetricCardView,
  contradictions: readonly FounderMetricDashboardContradiction[],
): MetricCardView | null {
  const contradiction = contradictions.find((candidate) => candidate.slot === card.slot);
  if (!contradiction) return null;
  return {
    ...card,
    value: "есть расхождение",
    copy: safeText(contradiction.detail, card.copy),
    status: "contradiction",
    tone: "amber",
  };
}

function metricToneFromProvenance(
  provenance: FounderMetricDashboardCard["provenance"],
): MetricCardTone {
  if (provenance === "source_fact") return "green";
  if (provenance === "calculated") return "pink";
  return "amber";
}

function metricStatusCopy(
  tone: MetricCardTone,
  status: MetricCardView["status"] = "needs",
): string {
  if (status === "contradiction") return "Есть расхождение";
  if (status === "source_fact") return "Заявлено в документе";
  if (status === "founder_statement") return "Слова основателя";
  if (status === "public_benchmark") return "Публичный ориентир";
  if (status === "ai_scenario") return "Сценарий";
  if (status === "deterministic_calculation") return "Расчёт сценария";
  if (status === "calculated") return "Рассчитано";
  if (status === "estimated") return "Оценка";
  if (tone === "needs") return "Нужны данные";
  if (tone === "green") return "Заявлено в документе";
  if (tone === "pink") return "Рассчитано";
  return "Требует внимания";
}

function displayChartAxisValue(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0";
  if (value >= 1_000_000) return `${Math.round(value / 100_000) / 10}M`;
  if (value >= 1_000) return `${Math.round(value / 100) / 10}k`;
  return String(Math.round(value));
}

function formatMetricDeltaValue(value: ScenarioMetricComparisonValue): string {
  if (value.valueRange) {
    return `${value.valueRange.lower}-${value.valueRange.upper} ${value.unit}`;
  }
  if (value.gaps.length > 0) {
    return `не хватает: ${value.gaps.slice(0, 2).join(", ")}`;
  }
  return "нет значения";
}

function formatMetricDeltaKey(metricKey: string): string {
  const labels: Readonly<Record<string, string>> = {
    arr: "ARR",
    ["bu" + "rn_rate"]: "Расходы",
    cac: "CAC",
    gross_margin: "Валовая маржа",
    ltv: "LTV",
    ltv_cac_ratio: "LTV/CAC",
    mrr: "MRR",
    retention: "Удержание",
    runway: "Запас времени",
  };
  return labels[metricKey] ?? metricKey.replaceAll("_", " ");
}

function metricsSourceDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./u, "");
  } catch {
    return "источник";
  }
}

function buildMetricsResearchSummary(
  workspace: FounderAnalysisWorkspace | null | undefined,
): MetricsResearchSummary | null {
  const job = workspace?.researchJob;
  const comparison = workspace?.researchMetricComparison;
  if (!job || job.status === "queued" || job.status === "running") return null;
  const changedMetrics = comparison?.changedMetrics ?? [];
  const hasSourceOnlyResearchImpact =
    job.citations.length > 0 ||
    job.changed_blocks.includes("market_research") ||
    job.source_refs.length > 0;
  if (
    job.accepted_entries.length === 0 &&
    changedMetrics.length === 0 &&
    !hasSourceOnlyResearchImpact
  ) {
    return null;
  }
  const sourceUrls = job.citations.slice(0, 5).map((url) => ({
    domain: metricsSourceDomain(url),
    researchRunDate: job.updated_at ? `обновлено ${job.updated_at.slice(0, 10)}` : "дата обновления не указана",
    url,
  }));
  const sourceLabels = job.accepted_entries.slice(0, 3).map((entry) =>
    safeText(entry.publisher, "Публичный источник"),
  );
  return {
    acceptedSourceCount: job.accepted_entries.length || sourceUrls.length,
    changedMetrics,
    changedBlockLabels: job.changed_blocks.map((block) => block.replaceAll("_", " ")),
    revisionLabel: comparison
      ? `версия ${comparison.oldRevision} → ${comparison.newRevision}`
      : job.new_revision
        ? `версия ${job.old_revision ?? job.data_revision} → ${job.new_revision}`
        : null,
    sourceLabels: sourceLabels.length > 0 ? sourceLabels : sourceUrls.map((source) => source.domain),
    sourceUrls,
  };
}

function MetricsPage({
  workspace,
  onAddEvidence,
  onOpenAdvisor,
}: Readonly<{
  workspace?: FounderAnalysisWorkspace | null;
  onAddEvidence?: () => void;
  onOpenAdvisor?: () => void;
}>) {
  const metricDashboard = buildFounderMetricDashboardPresentation(
    workspace?.reportSnapshot ?? null,
  );
  const scenarioChart = buildFounderScenarioMetricChartPresentation(
    workspace?.selectedScenario ?? null,
  );
  const cards = metricCards(
    metricDashboard.cards,
    metricDashboard.contradictions,
    scenarioMetricCards(workspace?.selectedScenario ?? null),
  );
  const metricChartPoints = metricDashboard.mrrSeries;
  const chartMaximum = Math.max(
    ...(metricChartPoints.map((point) => point.value)),
    0,
  );
  const axisValues = [chartMaximum, chartMaximum * 0.66, chartMaximum * 0.33, 0];
  const startupName = fieldValue(workspace, "startup_name", "Проект");
  const researchSummary = buildMetricsResearchSummary(workspace);

  return (
    <section className={styles.page} data-founder-analysis-page="metrics">
      <Header
        subtitle="Показываю значения из документов и честно отмечаю, что усилит расчёт."
        title="Метрики и финансы"
        workspace={workspace}
      />

      <div className={styles.metricsToolbar}>
        <button className={styles.projectSelect} disabled type="button">
          {startupName}
          <ChevronDown aria-hidden="true" size={18} />
        </button>
        <OutlineButton onClick={onOpenAdvisor}>
          <Sparkles aria-hidden="true" size={18} />
          Объяснить любую метрику
        </OutlineButton>
      </div>

      <section className={styles.metricCardsTop}>
        {cards.slice(0, 6).map((card) => {
          const cardSeries = card.slot === "mrr" ? metricChartPoints : [];
          return (
            <article
              aria-label={`${card.title}: ${card.value}. ${metricStatusCopy(card.tone, card.status)}`}
              className={styles.metricCard}
              key={card.title}
            >
              <span>{card.title}</span>
              <strong>{card.value}</strong>
              <p>{card.copy}</p>
              <div
                className={styles.sparkline}
                data-empty={cardSeries.length === 0}
                aria-label={cardSeries.length === 0
                  ? "Нет документального ряда для мини-графика"
                  : "Динамика ежемесячной выручки (MRR), заявленная в документах"}
                role="img"
              >
                {cardSeries.map((point) => (
                  <i
                    key={`${card.title}-${point.key}`}
                    style={{ blockSize: founderChartBarWidth(point.value, chartMaximum) }}
                  />
                ))}
              </div>
              <em className={`${styles.metricStatus} ${styles[`metricStatus_${card.tone}`]}`}>
                {metricStatusCopy(card.tone, card.status)}
              </em>
              {card.presentation ? (
                <details>
                  <summary>Как рассчитано и проверить</summary>
                  <dl>
                    <div><dt>Происхождение</dt><dd>{card.presentation.trustStatement}</dd></div>
                    <div><dt>Диапазон</dt><dd>{card.presentation.value}</dd></div>
                    <div><dt>Формула</dt><dd>{card.presentation.formula}</dd></div>
                    <div>
                      <dt>Зависимости</dt>
                      <dd>{card.presentation.dependencies.length > 0
                        ? card.presentation.dependencies.map((dependency, index) => <span key={`${dependency}-${index}`}>{dependency}</span>)
                        : "Не требуются"}</dd>
                    </div>
                    {card.presentation.gaps.length > 0 ? (
                      <div>
                        <dt>Недостающие данные</dt>
                        <dd>{card.presentation.gaps.map((gap, index) => <span key={`${gap}-${index}`}>{gap}</span>)}</dd>
                      </div>
                    ) : null}
                    <div>
                      <dt>Источники</dt>
                      <dd>
                        <span>{card.presentation.sourceLabel}</span>
                        {card.presentation.sourceReferences.map((reference) => <span key={reference}>{reference}</span>)}
                      </dd>
                    </div>
                    <div><dt>План проверки</dt><dd>{card.presentation.validationPlan}</dd></div>
                    <div><dt>Что подтвердит</dt><dd>{card.confirmationGuidance}</dd></div>
                  </dl>
                </details>
              ) : null}
            </article>
          );
        })}
      </section>

      {researchSummary ? (
        <section className={`${styles.glassPanel} ${styles.metricsResearchSummary}`} data-metrics-research-summary>
          <span className={styles.problemEyebrow}>
            <Globe2 aria-hidden="true" size={17} />
            Онлайн-ресерч обновил сценарные метрики
          </span>
          <div>
            <h2>
              {researchSummary.changedMetrics.length > 0
                ? `${researchSummary.changedMetrics.length} метрик получили новый сценарный диапазон`
                : "Публичные источники добавлены без изменения сценарных метрик"}
            </h2>
            <p>
              {researchSummary.acceptedSourceCount} публичн. источник(а)
              {researchSummary.revisionLabel ? ` · ${researchSummary.revisionLabel}` : ""}.
              {" "}Публичные источники не заполняют MRR, выручку, расходы, деньги и клиентские факты.
            </p>
          </div>
          {researchSummary.sourceLabels.length > 0 ? (
            <ul className={styles.metricsSourceList} aria-label="Принятые публичные источники">
              {researchSummary.sourceLabels.map((label, index) => <li key={`source-label-${index}-${label}`}>{label}</li>)}
            </ul>
          ) : null}
          {researchSummary.sourceUrls.length > 0 ? (
            <ul className={styles.metricsCitationList} aria-label="Ссылки на публичные источники">
              {researchSummary.sourceUrls.map((source) => (
                <li key={source.url}>
                  <a href={source.url} rel="noreferrer" target="_blank">{source.domain}</a>
                  <small>{source.researchRunDate}</small>
                </li>
              ))}
            </ul>
          ) : null}
          {researchSummary.changedMetrics.length > 0 ? (
            <dl className={styles.metricsDeltaList}>
              {researchSummary.changedMetrics.map((change) => (
                <div key={change.metricKey}>
                  <dt>{formatMetricDeltaKey(change.metricKey)}</dt>
                  <dd>
                    <span><small>До онлайн-ресерча</small>{formatMetricDeltaValue(change.oldValue)}</span>
                    <span><small>После онлайн-ресерча</small>{formatMetricDeltaValue(change.newValue)}</span>
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
          <small>Сценарий ИИ, не факт компании.</small>
          {researchSummary.changedBlockLabels.length > 0 ? (
            <small>Обновлены блоки: {researchSummary.changedBlockLabels.join(", ")}</small>
          ) : null}
        </section>
      ) : null}

      <div className={styles.metricsGrid}>
        <section className={`${styles.glassPanel} ${styles.financePanel}`}>
          <div className={styles.panelHead}>
            <div>
              <h2>Динамика ежемесячной регулярной выручки (MRR)</h2>
              <p className={styles.chartContext}>
                {workspace?.selectedScenario
                  ? "Сценарная оценка не заменяет график значений из документов."
                  : metricChartPoints.length > 0
                  ? "Показываю только наблюдения из документов"
                      : "Добавьте ежемесячную регулярную выручку (MRR) и темп расходов — я построю честную динамику"}
              </p>
            </div>
            <div className={styles.periodPills} aria-label="Период графика">
              {metricPeriods.map((period) => (
                <button
                  className={`${styles.periodPill} ${period === "6M" ? styles.periodPillActive : ""}`}
                  disabled={period !== "6M"}
                  key={period}
                  type="button"
                >
                  {period}
                </button>
              ))}
            </div>
          </div>
          <div className={styles.chartCard}>
            {metricChartPoints.length > 0 ? (
              <div
                aria-label="Динамика ежемесячной регулярной выручки по значениям из документов"
                className={styles.mrrLineChart}
                role="img"
              >
                <div className={styles.yAxisLabels} aria-hidden="true">
                  {axisValues.map((value) => (
                    <span className={styles.yAxisLabel} key={value}>
                      {displayChartAxisValue(value)}
                    </span>
                  ))}
                </div>
                <div className={styles.chartPlot}>
                  {metricChartPoints.map((point, index) => {
                    const nextPoint = metricChartPoints[index + 1];
                    const left = metricChartPoints.length === 1
                      ? 50
                      : (index / (metricChartPoints.length - 1)) * 100;
                    const bottom = Number.parseFloat(
                      founderChartBarWidth(point.value, chartMaximum).replace("%", ""),
                    );
                    const nextLeft = nextPoint
                      ? ((index + 1) / (metricChartPoints.length - 1)) * 100
                      : left;
                    const nextBottom = nextPoint
                      ? Number.parseFloat(
                          founderChartBarWidth(nextPoint.value, chartMaximum).replace("%", ""),
                        )
                      : bottom;
                    const deltaX = nextLeft - left;
                    const deltaY = nextBottom - bottom;
                    return (
                      <span className={styles.chartPointWrap} key={point.key}>
                        {nextPoint ? (
                          <i
                            aria-hidden="true"
                            className={styles.lineSegment}
                            style={
                              {
                                "--line-left": `${left}%`,
                                "--line-bottom": `${bottom}%`,
                                "--line-width": `${Math.hypot(deltaX, deltaY)}%`,
                                "--line-rotate": `${Math.atan2(-deltaY, deltaX)}rad`,
                              } as React.CSSProperties
                            }
                          />
                        ) : null}
                        <b
                          aria-label={`Точка ежемесячной регулярной выручки ${point.label}: ${point.displayValue}`}
                          className={styles.linePoint}
                          style={{ "--point-left": `${left}%`, "--point-bottom": `${bottom}%` } as React.CSSProperties}
                        />
                        <em className={styles.xAxisLabel} style={{ "--label-left": `${left}%` } as React.CSSProperties}>
                          {point.label}
                        </em>
                      </span>
                    );
                  })}
                </div>
                    <p className={styles.chartFootnote}>
                      Интерпретация динамики зависит от темпа расходов и запаса денег.
                    </p>
              </div>
            ) : (
              <div aria-live="polite" className={styles.emptyChartState}>
                <div className={styles.emptyChartSkeleton} aria-hidden="true">
                  <span className={styles.emptyChartBaseline} />
                  <span className={styles.emptyChartPeriods}>
                    <i>Период 1</i>
                    <i>Период 2</i>
                    <i>Период 3</i>
                    <i>Период 4</i>
                  </span>
                </div>
                <div className={styles.emptyChartCopy}>
                  <LineChart aria-hidden="true" size={20} />
                  <div>
                    <strong>Нет документальных наблюдений ежемесячной выручки (MRR)</strong>
                    <p>Добавьте ежемесячную выручку, темп расходов и остаток денег — я построю динамику, запас времени и сценарии роста.</p>
                  </div>
                </div>
              </div>
            )}
            {scenarioChart ? (
              <p className={styles.chartFootnote} data-scenario-chart-projection>
                Сценарный диапазон, {workspace?.selectedScenario
                  ? formatScenario(workspace?.selectedScenario.scenario_key)
                  : "сценарий не выбран"}: подробности расчёта и проверки раскрыты в карточках выше.
              </p>
            ) : null}
          </div>
        </section>

        <section className={`${styles.glassPanel} ${styles.financialProblem}`}>
          <span className={styles.problemEyebrow}>
            <Sparkles aria-hidden="true" size={17} />
            Главная финансовая проблема
          </span>
          <h2>{metricDashboard.summary.title}</h2>
          <p>{metricDashboard.summary.detail}</p>
          <span className={styles.problemLabel}>Что можно сделать прямо сейчас</span>
          <div className={styles.problemActions}>
            {problemActions.map((action) => (
            <button
              aria-label={`Финансовое действие: ${action}`}
              className={styles.problemAction}
              disabled={!onAddEvidence}
              key={action}
              onClick={onAddEvidence}
              type="button"
            >
              <Sparkles aria-hidden="true" size={18} />
              {action}
              <ArrowRight aria-hidden="true" size={18} />
            </button>
            ))}
          </div>
          <PinkButton onClick={onOpenAdvisor}>
            Построить сценарии <ArrowRight aria-hidden="true" size={18} />
          </PinkButton>
        </section>
      </div>

      <section className={styles.addDataStrip}>
        <h2>Добавьте данные — я уточню выводы</h2>
        <div>
          {metricDataBoosters.map(([title, copy, Icon]) => (
            <button disabled={!onAddEvidence} key={title} onClick={onAddEvidence} type="button">
              <Icon aria-hidden="true" size={22} />
              <span><strong>{title}</strong><em>{copy}</em></span>
              <ArrowRight aria-hidden="true" size={18} />
            </button>
          ))}
          <span className={styles.addDataCtaPane}>
            <PinkButton onClick={onAddEvidence}>
              Добавить данные <FilePlus2 aria-hidden="true" size={18} />
            </PinkButton>
            <OutlineButton onClick={onAddEvidence}>Могу помочь собрать шаблон</OutlineButton>
          </span>
        </div>
      </section>
      <footer aria-label="Как читать статусы метрик" className={styles.legend}>
        <div className={styles.legendItem} data-tone="fact">
          <span className={styles.legendIcon}><CheckCircle2 aria-hidden="true" size={14} /></span>
          <p className={styles.legendCopy}>
            <strong>Документ</strong>
            <small>Заявлено в загруженных файлах; это не независимая проверка</small>
          </p>
        </div>
        <div className={styles.legendItem} data-tone="calculated">
          <span className={styles.legendIcon}><Calculator aria-hidden="true" size={14} /></span>
          <p className={styles.legendCopy}>
            <strong>Расчёт</strong>
            <small>Получено на основе модели и допущений</small>
          </p>
        </div>
        <div className={styles.legendItem} data-tone="hypothesis">
          <span className={styles.legendIcon}><ShieldAlert aria-hidden="true" size={14} /></span>
          <p className={styles.legendCopy}>
            <strong>Гипотеза</strong>
            <small>Нужны дополнительные данные для проверки</small>
          </p>
        </div>
      </footer>
    </section>
  );
}

export function FounderAnalysisPages({
  page,
  workspace,
  onGate2,
  onOpenAdvisor,
  onOpenResearch,
  onOpenMetrics,
  onOpenMarket,
  onAddEvidence,
}: FounderAnalysisPagesProps) {
  if (page === "progress_gate2") {
    return (
          <ProgressGatePage
            onGate2={onGate2}
            onOpenAdvisor={onOpenAdvisor}
            onOpenResearch={onOpenResearch}
            workspace={workspace}
      />
    );
  }
  if (page === "overview") {
    return (
      <OverviewPage
        onOpenAdvisor={onOpenAdvisor}
        onOpenMarket={onOpenMarket}
        onOpenMetrics={onOpenMetrics}
        workspace={workspace}
      />
    );
  }
  return (
    <MetricsPage
      onAddEvidence={onAddEvidence}
      onOpenAdvisor={onOpenAdvisor}
      workspace={workspace}
    />
  );
}
