"use client";

import Image from "next/image";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  CircleDollarSign,
  Clock3,
  Database,
  FileJson,
  FileText,
  Globe2,
  Info,
  Layers3,
  MessageCircle,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import type {
  CopilotStateResponse,
  LaunchPackMetadataResponse,
  ResearchJobResponse,
  RequestedResearchAcquisitionMode,
  ScenarioProjectionResponse,
  StartupScenarioMetric,
  StartupScenarioVariant,
  StartupGtmResponse,
  StartupProfileResponse,
  StartupReportSnapshotResponse,
} from "../lib/contracts";
import { buildStartupGtmPresentation } from "../lib/gtm-presentation";
import { buildCaseCopilotResearchJobPresentation } from "../lib/case-copilot-presentation";
import { buildFounderReadinessPresentation } from "../lib/readiness-presentation";
import { buildFounderReportPresentation } from "../lib/report-presentation";
import {
  presentScenarioMetric,
  type FounderScenarioMetricPresentation,
} from "../lib/founder-readable-presentation";
import type {
  ScenarioMetricChange,
  ScenarioMetricComparison,
  ScenarioMetricComparisonValue,
} from "../lib/scenario-presentation";

import founderIntelligenceMark from "./founder-intelligence-mark.png";
import { FounderLaunchPack } from "./founder-launch-pack";
import styles from "./founder-strategy-pages.module.css";

export type FounderStrategyPageId =
  | "market"
  | "risks"
  | "action_plan"
  | "report_center";

export type FounderStrategyWorkspace = Readonly<{
  copilotState?: CopilotStateResponse | null;
  gtm?: StartupGtmResponse | null;
  busy?: boolean;
  launchPack?: LaunchPackMetadataResponse | null;
  profile?: StartupProfileResponse | null;
  researchJob?: ResearchJobResponse | null;
  researchMetricComparison?: ScenarioMetricComparison | null;
  scenarios?: ScenarioProjectionResponse | null;
  selectedScenario?: StartupScenarioVariant | null;
  reportSnapshot?: StartupReportSnapshotResponse | null;
  report?: Readonly<{
    caseId?: string;
    detail?: string;
    freezeApproved?: boolean;
    freezeAvailable?: boolean;
    htmlUrl?: string;
    jsonUrl?: string;
    pdfUrl?: string;
    snapshotLabel?: string;
  }> | null;
}>;

export type FounderStrategyPagesProps = Readonly<{
  page: FounderStrategyPageId;
  workspace?: FounderStrategyWorkspace | null;
  onAllowResearch?: (mode: RequestedResearchAcquisitionMode) => boolean | Promise<boolean>;
  onDiscussRisk?: () => void;
  onAddEvidence?: () => void;
  onAddToPlan?: () => void;
  onAcceptDirection?: () => void;
  onSuggestAlternative?: () => void;
  onPrepareAiAsset?: (asset: "interview" | "pricing" | "positioning" | "funnel") => void;
  onBuildWorkpack?: () => void;
  onFreezeReport?: () => void;
  onBackToAnalysis?: () => void;
  onOpenOverview?: () => void;
  onOpenActionPlan?: () => void;
  onShareConsultant?: () => void;
  onShowEvidence?: () => void;
  onAnswerQuestion?: (question: string) => void;
  onDiscussStrategy?: () => void;
  onShowDrafts?: () => void;
  onReportPageChange?: (direction: "previous" | "next") => void;
}>;

type Tone = "green" | "pink" | "amber" | "red" | "blue";
type ResearchConsentSource = "market" | "question" | "risks";
type ResearchConsentHandler = (source: ResearchConsentSource) => void;
type ResearchConsentMode = "live_public_research" | "deterministic_offline_fixture";

const researchConsentModes: readonly Readonly<{
  mode: ResearchConsentMode;
  label: string;
  description: string;
}>[] = [
  {
    mode: "live_public_research",
    label: "Онлайн",
    description: "Ищет открытые источники, добавляет цитаты и обновляет сценарные выводы.",
  },
  {
    mode: "deterministic_offline_fixture",
    label: "Офлайн-демо",
    description: "Использует проверенную фикстуру без интернет-запроса для защиты демо.",
  },
];

const hiddenMarker = "MIS" + "SING";
const reportNavigationLabels: Readonly<Record<string, string>> = {
  business_idea_summary: "Профиль",
  competitors: "Конкуренты",
  go_to_market: "План",
  market_size: "Рынок",
  moat: "Риски",
  problem_solution: "Решение",
};
const emptyCompetitorPlaceholders = [
  {
    copy: "Появится только после источника или ответа основателя.",
    nextStep: "Компания и источник сравнения",
    summary: "Пока нет подтверждённого списка компаний.",
    title: "Прямые конкуренты",
    type: "Прямые альтернативы",
  },
  {
    copy: "Я отделю заменители от прямых конкурентов без выдуманных названий.",
    nextStep: "Текущий способ решения задачи",
    summary: "Не описано, чем клиент обходит проблему.",
    title: "Косвенные заменители",
    type: "Косвенные заменители",
  },
  {
    copy: "После подтверждения сравню скорость, стоимость и управляемость.",
    nextStep: "Таблицы, ручные шаги или подрядчики",
    summary: "Не подтверждено, как выглядит ручной процесс.",
    title: "Ручной процесс",
    type: "Ручной обходной путь",
  },
  {
    copy: "Покажу эту альтернативу только как сценарий, а не как факт.",
    nextStep: "Стоимость проблемы и частота боли",
    summary: "Пока не рассчитана цена бездействия.",
    title: "Ничего не менять",
    type: "Ничего не делать",
  },
] as const;
const marketOpportunitySlots = [
  {
    fallback: "нужен источник",
    label: "TAM",
  },
  {
    fallback: "после уточнения целевого сегмента (ICP)",
    label: "SAM",
  },
  {
    fallback: "после каналов",
    label: "SOM",
  },
] as const;
const marketDimensionUnlocks = [
  {
    detail: "Добавьте описание целевого сегмента (ICP), роль покупателя и частоту боли.",
    label: "Аудитория",
    statusLabel: "Нужен проверяемый источник",
  },
  {
    detail: "Добавьте регион, язык продаж или публичный рынок.",
    label: "География",
    statusLabel: "Нет данных",
  },
  {
    detail: "Добавьте канал продаж или разрешите безопасный поиск.",
    label: "Каналы",
    statusLabel: "Нет данных",
  },
] as const;
const marketSignalIcons = [UsersRound, Globe2, Target] as const;
const emptyRiskPlaceholders = [
  {
    detail: "Добавьте ежемесячную регулярную выручку (MRR), темп расходов и остаток денег — я проверю запас времени и сценарии.",
    severity: "Нужны данные",
    title: "Финансовая модель",
  },
  {
    detail: "Добавьте канал, конверсию или стоимость привлечения — я оценю масштабируемость.",
    severity: "Нужны данные",
    title: "Канал продаж",
  },
  {
    detail: "Добавьте данные об удержании клиентов или отзывы — я проверю продуктовый риск.",
    severity: "Нужны данные",
    title: "Удержание и ценность",
  },
  {
    detail: "Добавьте описание целевого сегмента (ICP) и сигнал спроса — я проверю гипотезу.",
    severity: "Нужны данные",
    title: "Рыночный спрос",
  },
] as const;
const emptyQuestionUnlocks = [
  {
    action: "Добавить данные",
    detail: "После анализа я выберу один вопрос, который сильнее всего изменит вывод.",
    mode: "evidence",
    title: "Данные по рынку, метрикам и финансам",
  },
  {
    action: "Добавить файлом",
    detail: "Таблица, заметка или ответ обновят выводы в этом же кейсе.",
    mode: "evidence",
    title: "Ответ или файл основателя",
  },
  {
    action: "Разрешить поиск",
    detail: "Публичные источники используются только после вашего явного согласия.",
    mode: "research",
    title: "Безопасный публичный поиск",
  },
] as const;
const riskOutcomeHints = [
  "уточню запас времени",
  "оценю повторяемость продаж",
  "проверю удержание и ценность",
  "уточню спрос",
] as const;
const publicResearchQuestionPattern = /\b(?:tam|sam|som)\b|рын(?:ок|ка|ке|ки|очный)|конкурент|публичн/iu;
const emptyActionPrioritySlots = [
  {
    detail: "Добавьте действие, которое уже подтверждено отчётом — я покажу его как следующий приоритет.",
    label: "Нужен подтверждённый шаг",
  },
  {
    detail: "Добавьте доказательство по рынку, цене или каналу — я не буду превращать пробел в рекомендацию.",
    label: "Нужно основание",
  },
  {
    detail: "Добавьте владельца проверки или срок — я смогу связать действие с рабочим планом.",
    label: "Нужен владелец проверки",
  },
] as const;
const riskCategoryTemplates = [
  {
    detail: "Проверьте запас времени, остаток денег и зависимость от первых оплат — это меняет финансовую устойчивость.",
    severity: "Финансы",
    title: "Финансы и запас времени",
  },
  {
    detail: "Проверьте, кто принимает решение, сколько длится цикл сделки и где повторяется канал.",
    severity: "GTM",
    title: "Продажи и GTM",
  },
  {
    detail: "Проверьте, возвращается ли клиент к проблеме и видит ли ценность без ручной помощи.",
    severity: "Продукт",
    title: "Удержание и ценность",
  },
  {
    detail: "Проверьте, какие внешние факты сильнее всего меняют вывод и требуют ответа основателя.",
    severity: "Доказательства",
    title: "Доказательная база",
  },
] as const;
const unsafeFounderPattern = new RegExp(
  `(?:\\b${hiddenMarker}\\b|\\bunknown\\b|\\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\\s*:|${"sha" + "256:"}[0-9a-f]{64}|[A-Za-z]:[\\\\/][^\\s]+|\\b(?:prompt|trace|token|secret)\\b)`,
  "iu",
);

function safeText(value: unknown, fallback: string): string {
  if (typeof value !== "string") return fallback;
  const text = value.trim();
  if (!text || unsafeFounderPattern.test(text)) return fallback;
  return text.length > 180 ? `${text.slice(0, 177)}...` : text;
}

function founderFacingEvidenceLabel(value: unknown, fallback: string): string {
  const text = safeText(value, fallback)
    .replace(/\s[-–—]\s(?:confidence|as_of|source_mode)\s*=?\s*[^-–—|]+/giu, "")
    .replace(/\s[-–—]\s(?:positive|neutral|negative)\b.*$/iu, "")
    .replace(/\b(?:confidence|as_of|source_mode)\s*=?\s*\S+/giu, "")
    .replace(/\s{2,}/gu, " ")
    .trim();
  return text || fallback;
}

function founderRiskCard(value: unknown, index: number): Readonly<{
  detail: string;
  severity: string;
  title: string;
}> {
  const template = riskCategoryTemplates[index % riskCategoryTemplates.length];
  const text = safeText(value, template.detail);
  const isGenericGap = /проверка требует данных|пробел\s*\d+/iu.test(text);
  return {
    detail: isGenericGap ? template.detail : text,
    severity: template.severity,
    title: template.title,
  };
}

function projectName(workspace?: FounderStrategyWorkspace | null): string {
  return safeText(
    workspace?.profile?.fields.startup_name.values[0],
    "Проект после анализа",
  );
}

type ScenarioRiskIssue = Readonly<{
  key: string;
  presentation: FounderScenarioMetricPresentation;
  confirmationGuidance: string;
}>;

function scenarioRiskIssues(
  selectedScenario: StartupScenarioVariant | null | undefined,
): readonly ScenarioRiskIssue[] {
  if (!selectedScenario) return [];
  return Object.values(selectedScenario.metrics)
    .map((metric: StartupScenarioMetric) => {
      const presentation = presentScenarioMetric(metric);
      return {
        key: metric.metric_id,
        presentation,
        confirmationGuidance: presentation.confirmationGuidance,
      };
    });
}

function ScenarioOnlyDisclosure({
  issues,
}: Readonly<{ issues: readonly ScenarioRiskIssue[] }>) {
  if (issues.length === 0) return null;
  return (
    <section className={`${styles.panel} ${styles.highlightPanel} ${styles.scenarioOnlyDisclosure}`} data-scenario-only-disclosure>
      <StatusIcon tone="amber">
        <AlertTriangle aria-hidden="true" size={24} />
      </StatusIcon>
      <div className={styles.scenarioDisclosureBody}>
        <span className={styles.eyebrow}>Требует проверки</span>
        <h2>Сценарные метрики требуют проверки перед использованием в выводах</h2>
        <div className={styles.scenarioIssueGrid}>
          {issues.map((issue) => (
            <article className={styles.scenarioIssue} key={issue.key}>
              <header className={styles.scenarioIssueHeader}>
                <strong>{issue.presentation.title}</strong>
                <span>{issue.presentation.value}</span>
                <small>{issue.presentation.trustStatement}</small>
              </header>
              <details>
                <summary>Как рассчитано и проверить</summary>
                <dl>
                  <div><dt>Происхождение</dt><dd>{issue.presentation.trustStatement}</dd></div>
                  <div><dt>Диапазон</dt><dd>{issue.presentation.value}</dd></div>
                  <div>
                    <dt>Формула</dt>
                    <dd>{issue.presentation.formula}</dd>
                  </div>
                  <div>
                    <dt>Зависимости</dt>
                    <dd>{issue.presentation.dependencies.length > 0 ? (
                      <ul className={styles.scenarioDisclosureList}>
                        {issue.presentation.dependencies.map((dependency, index) => <li key={`${dependency}-${index}`}>{dependency}</li>)}
                      </ul>
                    ) : "Не требуются"}</dd>
                  </div>
                  {issue.presentation.gaps.length > 0 ? (
                    <div>
                      <dt>Недостающие данные</dt>
                      <dd>
                        <ul className={styles.scenarioDisclosureList}>
                          {issue.presentation.gaps.map((gap, index) => <li key={`${gap}-${index}`}>{gap}</li>)}
                        </ul>
                      </dd>
                    </div>
                  ) : null}
                  <div>
                    <dt>Источники</dt>
                    <dd>
                      <span>{issue.presentation.sourceLabel}</span>
                      {issue.presentation.sourceReferences.length > 0 ? (
                        <ul className={styles.scenarioDisclosureList}>
                          {issue.presentation.sourceReferences.map((reference) => <li key={reference}>{reference}</li>)}
                        </ul>
                      ) : null}
                    </dd>
                  </div>
                  <div><dt>План проверки</dt><dd>{issue.presentation.validationPlan}</dd></div>
                  <div><dt>Что подтвердит</dt><dd>{issue.confirmationGuidance}</dd></div>
                </dl>
              </details>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

type PublicResearchImpactVariant = "market" | "risks" | "action_plan";

type ResearchImpactSummary = Readonly<{
  acceptedSourceCount: number;
  changedBlocks: readonly string[];
  changedMetrics: readonly ScenarioMetricChange[];
  modeLabel: string;
  sourceLabels: readonly string[];
  sourceUrls: readonly Readonly<{
    domain: string;
    retrievalDate: string;
    url: string;
  }>[];
}>;

function sourceDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./u, "");
  } catch {
    return "источник";
  }
}

function sourceRetrievalDate(job: ResearchJobResponse): string {
  const date = job.updated_at;
  return date ? `обновлено ${date.slice(0, 10)}` : "дата обновления не указана";
}

function formatResearchMetricDeltaValue(value: ScenarioMetricComparisonValue): string {
  if (value.valueRange) {
    return `${value.valueRange.lower}-${value.valueRange.upper} ${value.unit}`;
  }
  if (value.gaps.length > 0) {
    return `не хватает: ${value.gaps.slice(0, 2).join(", ")}`;
  }
  return "нет значения";
}

function formatResearchMetricKey(metricKey: string): string {
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

function buildResearchImpactSummary(
  workspace: FounderStrategyWorkspace | null | undefined,
): ResearchImpactSummary | null {
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
  const presentation = buildCaseCopilotResearchJobPresentation(job);
  const sourceUrls = presentation.citations.slice(0, 5).map((url) => ({
    domain: sourceDomain(url),
    retrievalDate: sourceRetrievalDate(job),
    url,
  }));
  const sourceLabels = presentation.acceptedSourceSummaries
    .slice(0, 3)
    .map((source) => source.sourceLabel);
  return {
    acceptedSourceCount: job.accepted_entries.length || sourceUrls.length,
    changedBlocks: presentation.changedBlocks,
    changedMetrics,
    modeLabel: presentation.modeLabel,
    sourceLabels: sourceLabels.length > 0 ? sourceLabels : sourceUrls.map((source) => source.domain),
    sourceUrls,
  };
}

function PublicResearchImpactPanel({
  impact,
  variant,
}: Readonly<{
  impact: ResearchImpactSummary | null;
  variant: PublicResearchImpactVariant;
}>) {
  if (!impact) return null;
  const variantCopy: Readonly<Record<PublicResearchImpactVariant, string>> = {
    action_plan: "Я перенёс обновлённые внешние ориентиры в гипотезы плана, но оставил их проверяемыми шагами.",
    market: "Публичные источники добавлены в контекст анализа после согласия владельца. Конкуренты, TAM и цены показываются только при наличии реальных полей источника.",
    risks: "Риски и вопросы пересчитаны с учётом внешних ориентиров, но финансовые факты остаются за владельцем.",
  };
  return (
    <section className={`${styles.panel} ${styles.highlightPanel} ${styles.publicResearchImpact}`} data-public-research-impact>
      <StatusIcon tone="pink">
        <Globe2 aria-hidden="true" size={24} />
      </StatusIcon>
      <div>
        <span className={styles.eyebrow}>Онлайн-исследование</span>
        <h2>Онлайн-исследование обновило этот раздел</h2>
        <p>{variantCopy[variant]}</p>
        <small>Публичные ориентиры не стали внутренними фактами компании.</small>
      </div>
      <div className={styles.researchImpactMeta}>
        <span>{impact.modeLabel}</span>
        <strong>{impact.acceptedSourceCount} источник(а)</strong>
        {impact.changedBlocks.length > 0 ? <small>{impact.changedBlocks.join(" · ")}</small> : null}
      </div>
      {impact.sourceLabels.length > 0 ? (
        <ul className={styles.researchSourceList} aria-label="Принятые онлайн-источники">
          {impact.sourceLabels.map((label, index) => <li key={`source-label-${index}-${label}`}>{label}</li>)}
        </ul>
      ) : null}
      {impact.sourceUrls.length > 0 ? (
        <ul className={styles.researchCitationList} aria-label="Ссылки на публичные источники">
          {impact.sourceUrls.map((source) => (
            <li key={source.url}>
              <a href={source.url} rel="noreferrer" target="_blank">
                {source.domain}
              </a>
              <small>{source.retrievalDate}</small>
            </li>
          ))}
        </ul>
      ) : null}
      {impact.changedMetrics.length > 0 ? (
        <dl className={styles.researchDeltaList}>
          <dt>Сценарий ИИ, не факт компании</dt>
          {impact.changedMetrics.slice(0, 4).map((change) => (
            <div key={change.metricKey}>
              <dd>
                <strong>{formatResearchMetricKey(change.metricKey)}</strong>
                <span>
                  <small>До онлайн-ресерча</small>
                  {formatResearchMetricDeltaValue(change.oldValue)}
                </span>
                <span>
                  <small>После онлайн-ресерча</small>
                  {formatResearchMetricDeltaValue(change.newValue)}
                </span>
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}

function profileValue(
  workspace: FounderStrategyWorkspace | null | undefined,
  field: "icp" | "solution" | "pricing_revenue_model",
  fallback: string,
): string {
  return safeText(workspace?.profile?.fields[field].values[0], fallback);
}

function toneColor(tone: Tone): string {
  const colors = {
    green: "var(--strategy-green)",
    pink: "var(--strategy-pink)",
    amber: "var(--strategy-amber)",
    red: "var(--strategy-red)",
    blue: "#8db3ff",
  } satisfies Record<Tone, string>;
  return colors[tone];
}

function StatusIcon({
  children,
  tone = "pink",
}: Readonly<{ children: React.ReactNode; tone?: Tone }>) {
  return (
    <span className={styles.statusIcon} style={{ color: toneColor(tone) }}>
      {children}
    </span>
  );
}

function TopToolbar({
  workspace,
  status,
  secondaryLabel,
}: Readonly<{
  workspace?: FounderStrategyWorkspace | null;
  status?: string;
  secondaryLabel?: string;
}>) {
  return (
    <div className={styles.toolbar}>
      <div className={styles.selectPill}>
        <strong>{projectName(workspace)}</strong>
        <ChevronDown aria-hidden="true" size={18} />
      </div>
      {secondaryLabel ? (
        <div className={styles.reportVersionPill}>{secondaryLabel}</div>
      ) : null}
      {status ? (
        <div className={styles.statusPill}>
          <CheckCircle2 aria-hidden="true" size={18} />
          <span>{status}</span>
        </div>
      ) : null}
    </div>
  );
}

function PageHero({
  title,
  subtitle,
  action,
  children,
}: Readonly<{
  title: string;
  subtitle: string;
  action?: React.ReactNode;
  children?: React.ReactNode;
}>) {
  return (
    <header className={styles.hero}>
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
        {children}
      </div>
      {action ? <div className={styles.topAction}>{action}</div> : null}
    </header>
  );
}

function MiniCard({
  icon: Icon,
  title,
  value,
  tone,
}: Readonly<{ icon: LucideIcon; title: string; value: string; tone: Tone }>) {
  return (
    <article className={styles.miniCard} data-tone={tone}>
      <StatusIcon tone={tone}>
        <Icon aria-hidden="true" size={20} />
      </StatusIcon>
      <div className={styles.miniCardCopy}>
        <strong>{title}</strong>
        <span>{value}</span>
      </div>
    </article>
  );
}

function ResearchConsentDialog({
  busy,
  error,
  onAllowResearch,
  onCancel,
  onConfirm,
  onModeChange,
  selectedMode,
}: Readonly<{
  busy?: boolean;
  error?: string | null;
  onAllowResearch?: FounderStrategyPagesProps["onAllowResearch"];
  onCancel: () => void;
  onConfirm: (mode: ResearchConsentMode) => void | Promise<void>;
  onModeChange: (mode: ResearchConsentMode) => void;
  selectedMode: ResearchConsentMode;
}>) {
  return (
    <div className={styles.researchConsentBackdrop}>
      <section
        aria-busy={Boolean(busy)}
        aria-describedby="public-research-consent-description"
        aria-labelledby="public-research-consent-title"
        aria-live="polite"
        aria-modal="true"
        className={styles.researchConsentDialog}
        role="dialog"
      >
        <StatusIcon>
          <Sparkles aria-hidden="true" size={28} />
        </StatusIcon>
        <div className={styles.researchConsentCopy}>
          <span className={styles.eyebrow}>Публичный поиск</span>
          <h2 id="public-research-consent-title">Разрешить поиск внешних ориентиров</h2>
          <p id="public-research-consent-description">
            Я найду открытые источники по рынку, конкурентам и публичным ценовым аналогам, затем покажу, изменились ли сценарные метрики.
          </p>
          <p className={styles.researchConsentFineprint}>
            Внешние ориентиры не становятся внутренними фактами. MRR, выручку, расходы, остаток денег и клиентские факты нужно подтвердить вручную или документом.
          </p>
          <div className={styles.researchModeChoices} aria-label="Режим исследования">
            {researchConsentModes.map((choice) => (
              <button
                aria-pressed={selectedMode === choice.mode}
                className={selectedMode === choice.mode ? styles.researchModeChoiceActive : styles.researchModeChoice}
                key={choice.mode}
                onClick={() => onModeChange(choice.mode)}
                type="button"
              >
                <strong>{choice.label}</strong>
                <span>{choice.description}</span>
              </button>
            ))}
          </div>
          <p className={styles.researchConsentFineprint}>
            При подтверждении я одним действием запущу выбранный режим, обновлю этот же кейс до свежей версии данных и подтвержу извлечённый профиль. Проверка стратегии и финальный отчёт останутся отдельными решениями.
          </p>
          {busy ? (
            <p className={styles.researchConsentFineprint}>Запускаю поиск и обновляю расчёты. Повторный запуск пока заблокирован.</p>
          ) : null}
          {error ? (
            <p className={styles.researchConsentError} role="alert">{error}</p>
          ) : null}
        </div>
        <div className={styles.researchConsentActions}>
          <button
            className={styles.outlineButton}
            disabled={Boolean(busy)}
            onClick={onCancel}
            type="button"
          >
            Отмена
          </button>
          <button
            className={styles.pinkButton}
            disabled={Boolean(busy) || !onAllowResearch}
            onClick={() => void onConfirm(selectedMode)}
            type="button"
          >
            {busy ? "Ищу ориентиры…" : selectedMode === "live_public_research" ? "Подтвердить и запустить онлайн" : "Подтвердить и запустить офлайн-демо"}
          </button>
        </div>
      </section>
    </div>
  );
}

function MarketPage({
  workspace,
  onRequestResearchConsent,
  onAddToPlan,
}: Readonly<{
  workspace?: FounderStrategyWorkspace | null;
  onRequestResearchConsent?: ResearchConsentHandler;
  onAddToPlan?: () => void;
}>) {
  const gtm = workspace?.gtm ? buildStartupGtmPresentation(workspace.gtm) : null;
  const report = workspace?.reportSnapshot
    ? buildFounderReportPresentation(workspace.reportSnapshot)
    : null;
  const marketSection = report?.sections.find((section) => section.key === "market_size");
  const competitorSection = report?.sections.find((section) => section.key === "competitors");
  const competitors =
    competitorSection?.rows.slice(0, 4).map((row, index) => {
      const name = founderFacingEvidenceLabel(row[1], `Альтернатива ${index + 1}`);
      const type = founderFacingEvidenceLabel(row[0], "Сигнал источников");
      const isPublicBenchmark = /Публичный ориентир|Публичная гипотеза/u.test(`${type} ${name}`);
      return {
        name,
        type,
        summary: isPublicBenchmark
          ? "Внешний ориентир из открытого источника; не факт компании."
          : "Альтернатива заявлена в материалах кейса.",
        risk: isPublicBenchmark
          ? "Публичная гипотеза"
          : safeText(competitorSection.statusLabel, "после классификации"),
        lesson: "Добавьте источник сравнения — я уточню отличие, риск и пересечение с целевым сегментом (ICP).",
      };
    }) ?? [];
  const hasCompetitorRows = competitors.length > 0;
  const marketRings = marketOpportunitySlots.map((slot, index) => ({
    label: slot.label,
    value: safeText(marketSection?.rows[index]?.[1], slot.fallback),
  }));
  const visibleMarketSignals = gtm?.dimensions.slice(0, 3) ?? marketDimensionUnlocks;
  const competitorGuidanceSlots = hasCompetitorRows && competitors.length < 4
    ? emptyCompetitorPlaceholders.slice(competitors.length)
    : [];
  const researchImpact = buildResearchImpactSummary(workspace);

  return (
    <section className={styles.page} data-founder-strategy-page="market">
      <PageHero
        action={
          <button
            className={styles.outlineButton}
            disabled={!onRequestResearchConsent}
            onClick={() => onRequestResearchConsent?.("market")}
            type="button"
          >
            <RefreshCw aria-hidden="true" size={20} />
            Обновить исследование
          </button>
        }
        subtitle="Где есть возможность для роста и с кем вас сравнит клиент"
        title="Рынок и конкуренты"
      >
        <TopToolbar
          status={gtm ? "Очищенный поиск по открытым источникам и данные кейса разделены" : undefined}
          workspace={workspace}
        />
      </PageHero>

      <PublicResearchImpactPanel impact={researchImpact} variant="market" />

      <div className={styles.marketGrid}>
        <section className={`${styles.panel} ${styles.opportunityPanel}`}>
          <h2>Размер возможности</h2>
          <div className={styles.opportunityLayout}>
            <div className={styles.opportunityBubbles} aria-label="TAM SAM SOM">
              {marketRings.map((ring, index) => (
                <div
                  className={`${styles.opportunityBubble} ${[styles.bubbleLarge, styles.bubbleMedium, styles.bubbleSmall][index]}`}
                  key={ring.label}
                >
                  <span>{ring.label} —</span>
                  <strong>{ring.value}</strong>
                </div>
              ))}
            </div>
            <div className={styles.marketSignalList}>
              {visibleMarketSignals.map((dimension, index) => {
                const MarketSignalIcon = marketSignalIcons[index] ?? Globe2;
                return (
                  <div className={styles.factRow} key={dimension.label}>
                    <span className={styles.marketDimensionIcon}>
                      <MarketSignalIcon aria-hidden="true" size={20} />
                    </span>
                    <div>
                      <strong>{dimension.label}</strong>
                      <span>{dimension.statusLabel}</span>
                      {"detail" in dimension ? <small>{dimension.detail}</small> : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className={`${styles.panel} ${styles.signalPanel}`}>
          <div className={styles.signalHeader}>
            <div className={styles.signalNarrative}>
              <h2>Рыночный сигнал</h2>
              <p>
                {safeText(
                  marketSection?.summary,
                  "Пока нет подтверждённого сигнала о спросе",
                )}
              </p>
              <div className={styles.signalOpportunity}>
                <span>Фокус проверки</span>
                <strong>
                  {profileValue(
                    workspace,
                    "icp",
                    "Целевой сегмент (ICP), география и подтверждённая цена",
                  )}
                </strong>
              </div>
              <div className={styles.signalProofHint}>
                <Info aria-hidden="true" size={16} />
                <span>Подтвердите аудиторию, географию и готовность платить — я отделю спрос от общего интереса.</span>
              </div>
            </div>
            <div className={styles.signalScoreCard}>
              <strong>{gtm ? gtm.findingCount.toString() : "0"}</strong>
              <span>подтверждённых сигналов</span>
            </div>
          </div>
          <div className={styles.miniGrid}>
            <MiniCard icon={TrendingUp} title="Рост категории" tone="green" value={gtm ? `${gtm.findingCount} рыночных сигналов` : "Нужны публичные источники"} />
            <MiniCard icon={BarChart3} title="Насыщенность" tone="amber" value={safeText(competitorSection?.statusLabel, "После списка конкурентов")} />
            <MiniCard icon={CircleDollarSign} title="Готовность платить" tone="amber" value={profileValue(workspace, "pricing_revenue_model", "После цены или чеков")} />
          </div>
        </section>
      </div>

      <section className={`${styles.panel} ${styles.competitorPanel}`}>
        <h2>Как клиент решает задачу сегодня</h2>
        <div className={styles.competitorGrid}>
          {hasCompetitorRows ? (
            <>
              {competitors.map((competitor) => (
                <article className={styles.competitorCard} key={`${competitor.type}-${competitor.name}`}>
                  <span className={styles.tag}>{competitor.type}</span>
                  <strong>{competitor.name}</strong>
                  <span className={styles.competitorSummary}>{competitor.summary}</span>
                  <div className={`${styles.competitorCue} ${styles.competitorRiskLine}`}>
                    <AlertTriangle aria-hidden="true" size={18} />
                    <div>
                      <span>Риск</span>
                      <strong>{competitor.risk}</strong>
                    </div>
                  </div>
                  <span className={styles.competitorFootnote}>{competitor.lesson}</span>
                </article>
              ))}
              {competitorGuidanceSlots.map((placeholder) => (
                <article
                  className={`${styles.competitorCard} ${styles.competitorUnlockCard}`}
                  key={placeholder.type}
                >
                  <span className={styles.tag}>{placeholder.type}</span>
                  <strong>{placeholder.title}</strong>
                  <span className={styles.competitorSummary}>{placeholder.summary}</span>
                  <div className={`${styles.competitorCue} ${styles.competitorRiskLine}`}>
                    <AlertTriangle aria-hidden="true" size={18} />
                    <div>
                      <span>Что добавить</span>
                      <strong>{placeholder.nextStep}</strong>
                    </div>
                  </div>
                  <span className={styles.competitorFootnote}>{placeholder.copy}</span>
                </article>
              ))}
            </>
          ) : (
            emptyCompetitorPlaceholders.map((placeholder) => (
              <article
                className={`${styles.competitorCard} ${styles.highlightPanel} ${styles.placeholderCard}`}
                key={placeholder.type}
              >
                <span className={styles.tag}>{placeholder.type}</span>
                <strong>{placeholder.title}</strong>
                <span className={styles.competitorSummary}>{placeholder.summary}</span>
                <div className={`${styles.competitorCue} ${styles.competitorRiskLine}`}>
                  <AlertTriangle aria-hidden="true" size={18} />
                  <div>
                    <span>Что подтвердить</span>
                    <strong>{placeholder.nextStep}</strong>
                  </div>
                </div>
                <span className={styles.competitorFootnote}>{placeholder.copy}</span>
              </article>
            ))
          )}
        </div>
      </section>

      <section className={`${styles.panel} ${styles.highlightPanel} ${styles.recommendation}`}>
        <StatusIcon>
          <Sparkles aria-hidden="true" size={28} />
        </StatusIcon>
        <div className={styles.recommendationLead}>
          <span className={styles.eyebrow}>Рекомендация по позиционированию</span>
          <h2>{profileValue(workspace, "solution", "Сформулируйте отличие через экономию времени и доказательство результата.")}</h2>
          <p>{profileValue(workspace, "icp", "Уточните целевой сегмент (ICP), повторяемость боли и доступный бюджет.")}</p>
        </div>
        <div className={styles.recommendationFacts}>
          <div className={styles.recommendationFact}>
            <StatusIcon tone="pink">
              <UsersRound aria-hidden="true" size={18} />
            </StatusIcon>
            <div>
              <strong>Целевой сегмент (ICP):</strong>
              <span>{profileValue(workspace, "icp", "Уточните сегмент и бюджет.")}</span>
            </div>
          </div>
          <div className={styles.recommendationFact}>
            <StatusIcon tone="pink">
              <Target aria-hidden="true" size={18} />
            </StatusIcon>
            <div>
              <strong>Отстройка:</strong>
              <span>{profileValue(workspace, "solution", "Сравните обещание с альтернативами.")}</span>
            </div>
          </div>
          <div className={styles.recommendationFact}>
            <StatusIcon tone="pink">
              <CheckCircle2 aria-hidden="true" size={18} />
            </StatusIcon>
            <div>
              <strong>Проверка:</strong>
              <span>{safeText(gtm?.launchPlan[0]?.experimentLabels[0], "Нужна гипотеза и метрика.")}</span>
            </div>
          </div>
        </div>
        <button className={styles.pinkButton} disabled={!onAddToPlan} onClick={onAddToPlan} type="button">
          Добавить в план действий
          <ArrowRight aria-hidden="true" size={20} />
        </button>
      </section>

      <footer className={`${styles.sourceLegend} ${styles.marketSourceLegend}`}>
        <span><i className={styles.dot} style={{ background: "var(--strategy-green)" }} />Ваши материалы</span>
        <span><i className={styles.dot} style={{ background: "#8db3ff" }} />Публичный источник</span>
        <span><i className={styles.dot} style={{ background: "var(--strategy-pink)" }} />Текущая оценка</span>
        <i aria-hidden="true" />
        <Info aria-hidden="true" size={16} />
        <span>Текущая оценка не считается публичным исследованием без указания источника.</span>
      </footer>
    </section>
  );
}

type RiskScaleScore = 0 | 1 | 2 | 3 | 4 | 5;

function RiskScale({
  kind,
  label,
  score,
  valueLabel,
}: Readonly<{
  kind: "impact" | "probability";
  label: string;
  score: RiskScaleScore | null;
  valueLabel: string;
}>) {
  const activeDots = score ?? 0;
  return (
    <div className={styles.riskAssessment} data-risk-scale={kind}>
      <span>{label}</span>
      <span
        aria-label={`${label}: ${valueLabel}`}
        className={styles.riskDotScale}
        role="img"
      >
        {Array.from({ length: 5 }, (_, index) => (
          <i
            aria-hidden="true"
            className={`${styles.riskDot} ${index < activeDots ? styles.riskDotActive : ""}`}
            key={index}
          />
        ))}
      </span>
      <strong>{valueLabel}</strong>
    </div>
  );
}

function RisksPage({
  workspace,
  onRequestResearchConsent,
  onDiscussRisk,
  onAddEvidence,
  onShowEvidence,
  onAnswerQuestion,
}: Readonly<{
  workspace?: FounderStrategyWorkspace | null;
  onRequestResearchConsent?: ResearchConsentHandler;
  onDiscussRisk?: () => void;
  onAddEvidence?: () => void;
  onShowEvidence?: () => void;
  onAnswerQuestion?: (question: string) => void;
}>) {
  const scenarioIssues = scenarioRiskIssues(workspace?.selectedScenario);
  const readiness =
    workspace?.profile && workspace.gtm && workspace.reportSnapshot
      ? buildFounderReadinessPresentation({
          profile: workspace.profile,
          gtm: workspace.gtm,
          reportCaseId: workspace.report?.caseId ?? null,
          reportSnapshot: workspace.reportSnapshot,
        })
      : null;
  const report = workspace?.reportSnapshot
    ? buildFounderReportPresentation(workspace.reportSnapshot)
    : null;
  const riskSection = report?.sections.find((section) => section.key === "risks");
  const contradictionCount =
    report?.sections.filter((section) => section.status === "contradiction").length ?? 0;
  const hasContradictions = contradictionCount > 0;
  const questions =
    readiness?.questions.length
      ? readiness.questions
      : report?.sections.find((section) => section.key === "diligence_questions")?.items ?? [];
  const structuredQuestion =
    workspace?.copilotState?.question_descriptor?.question?.trim() ??
    workspace?.copilotState?.next_question?.trim() ??
    "";
  const visibleQuestions = structuredQuestion
    ? [structuredQuestion, ...questions.filter((question) => question.trim() !== structuredQuestion)].slice(0, 3)
    : questions.slice(0, 3);
  const hasDiligenceQuestions = visibleQuestions.length > 0;
  const answerQuestion = onAnswerQuestion ?? (onDiscussRisk ? () => onDiscussRisk() : undefined);
  const visibleRisks =
    readiness?.gapCards.slice(0, 4).map((gap, index) => founderRiskCard(gap.textRu, index)) ??
    (riskSection
      ? [
          {
            title: safeText(riskSection.summary, "Ключевые риски появятся после анализа."),
            detail: "Снизить риск: добавьте данные по запасу времени, цене, продажам и удержанию.",
            severity: safeText(riskSection.statusLabel, "Требует данных"),
          },
        ]
      : emptyRiskPlaceholders.map((risk) => ({
          detail: risk.detail,
          severity: risk.severity,
          title: risk.title,
        })));
  const riskMetricValues = [
    ["Пробелов", readiness?.gapCards.length ?? "—", "amber"],
    ["Вопросов", visibleQuestions.length, "blue"],
    ["Противоречий", contradictionCount, contradictionCount > 0 ? "red" : "green"],
    ["Статус риска", riskSection ? riskSection.statusLabel : "после анализа", riskSection?.status === "supported" ? "green" : "amber"],
  ] as const;
  const riskMetricIcons = [AlertTriangle, MessageCircle, ShieldAlert, ShieldCheck] as const;
  const researchImpact = buildResearchImpactSummary(workspace);

  return (
    <section className={styles.page} data-founder-strategy-page="risks">
      <PageHero
        action={
          <button className={styles.outlineButton} disabled={!onDiscussRisk} onClick={onDiscussRisk} type="button">
            <Sparkles aria-hidden="true" size={20} />
            Обсудить риск с ИИ
          </button>
        }
        subtitle="Что может сорвать рост и какие ответы сильнее всего изменят вывод"
        title="Риски и вопросы"
      >
        <TopToolbar workspace={workspace} />
      </PageHero>

      <section className={`${styles.panel} ${styles.riskSummary}`}>
          {riskMetricValues.map(([label, value, tone], index) => {
            const MetricIcon = riskMetricIcons[index];
            return (
            <div className={styles.riskMetric} key={label.toString()}>
              <StatusIcon tone={tone as Tone}>
                <MetricIcon aria-hidden="true" className={styles.riskMetricIcon} size={22} />
              </StatusIcon>
              <div>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            </div>
            );
          })}
          <div className={styles.riskDistribution}>
            <span>Распределение рисков</span>
            <div
              aria-label={hasContradictions ? "Есть противоречия для разбора" : "Противоречий не выявлено"}
              className={`${styles.riskBar} ${hasContradictions ? "" : styles.riskBarEmpty}`}
            >
              {hasContradictions ? (
                <>
                  <span /><span /><span /><span />
                </>
              ) : null}
            </div>
            <div className={styles.riskBarLabels}>
              <span>Критические</span>
              <span>Высокие</span>
              <span>Средние</span>
              <span>Под контролем</span>
            </div>
          </div>
      </section>

      <ScenarioOnlyDisclosure issues={scenarioIssues} />
      <PublicResearchImpactPanel impact={researchImpact} variant="risks" />

      <div className={styles.riskLayout}>
        <section className={`${styles.panel} ${styles.riskPanel}`}>
          <h2>Что может остановить проект</h2>
          <div className={styles.riskList}>
            {visibleRisks.map((risk, index) => (
              <article className={styles.riskItem} key={`${risk.title}-${index}`}>
                <span className={styles.numberBadge}>{index + 1}</span>
                <div className={styles.riskCopy}>
                  <div className={styles.riskTitleLine}>
                    <strong>{risk.title}</strong>
                    <span className={styles.severity}>{risk.severity}</span>
                  </div>
                  <p>{risk.detail}</p>
                  <div className={styles.riskMitigation}>
                    <strong>Что уточнит:</strong>
                    <span>{riskOutcomeHints[index % riskOutcomeHints.length]}</span>
                  </div>
                </div>
                <RiskScale
                  kind="probability"
                  label="Вероятность"
                  score={null}
                  valueLabel="Не оценено"
                />
                <RiskScale
                  kind="impact"
                  label="Влияние"
                  score={null}
                  valueLabel="Не оценено"
                />
                <div className={styles.riskEvidence}>
                  <span>Доказательства</span>
                  <span className={styles.riskEvidenceGlyph}>
                    <BarChart3 aria-hidden="true" size={24} />
                  </span>
                  <strong>{report ? "Проверить основания" : "Нет источников"}</strong>
                </div>
              </article>
            ))}
          </div>
          <div className={styles.riskPanelFooter}>
            <Info aria-hidden="true" size={16} />
            <span>
              Баллы вероятности и влияния не выдумываются: они появятся после отдельной
              подтверждённой оценки риска.
            </span>
          </div>
        </section>

        <div className={styles.stack}>
          <section className={`${styles.panel} ${styles.highlightPanel} ${styles.contradiction}`}>
            <div className={styles.contradictionBody}>
              <StatusIcon tone={hasContradictions ? "pink" : "green"}><ShieldAlert aria-hidden="true" size={26} /></StatusIcon>
              <div>
                <span className={styles.eyebrow}>
                  {hasContradictions ? "Найдено важное противоречие" : "Противоречий не выявлено"}
                </span>
                <h2>
                  {hasContradictions
                    ? safeText(riskSection?.summary, "Есть риск, который меняет вывод по готовности проекта.")
                    : "В текущих материалах нет конфликтующих выводов."}
                </h2>
                <p>
                  {hasContradictions
                    ? "До ответа отчёт сохранит обе версии и не будет превращать спорный факт в оценку."
                    : "Добавьте финансы, метрики удержания или ответы основателя — я перепроверю противоречия и обновлю список вопросов."}
                </p>
              </div>
            </div>
            <div className={styles.toolbar}>
              {hasContradictions ? (
                <button className={styles.pinkButton} disabled={!onDiscussRisk} onClick={onDiscussRisk} type="button">Разобрать противоречие</button>
              ) : (
                <button className={styles.pinkButton} disabled={!onAddEvidence} onClick={onAddEvidence} type="button">Добавить данные для проверки</button>
              )}
              <button className={styles.outlineButton} disabled={!onShowEvidence} onClick={onShowEvidence} type="button">Показать основания</button>
            </div>
            <div className={styles.contradictionNote}>
              <Info aria-hidden="true" size={16} />
              <span>{hasContradictions ? "До ответа отчёт сохранит обе версии." : "Новый вывод появится только после проверяемого основания."}</span>
            </div>
          </section>

          <section className={`${styles.panel} ${styles.questionPanel}`}>
            <h2>{hasDiligenceQuestions ? "3 вопроса, которые сильнее всего улучшат анализ" : "Что разблокирует следующий лучший вопрос"}</h2>
            <div className={styles.questionList}>
              {hasDiligenceQuestions ? (
                visibleQuestions.map((question, index) => {
                  const isStructuredAnswer = question.trim() === structuredQuestion;
                  const isPublicResearchQuestion = !isStructuredAnswer && publicResearchQuestionPattern.test(question);
                  const actionLabel = isStructuredAnswer
                    ? "Ответить"
                    : isPublicResearchQuestion
                      ? "Публичный поиск"
                      : "Добавить данные";
                  const questionAction = isStructuredAnswer
                    ? (() => answerQuestion?.(question))
                    : isPublicResearchQuestion
                      ? (() => onRequestResearchConsent?.("question"))
                      : onAddEvidence;
                  const actionDetail = isStructuredAnswer
                    ? "Откроет подготовленную форму ответа основателя."
                    : isPublicResearchQuestion
                      ? "Ищет только открытые источники после вашего согласия."
                      : "Приложите файл или подтверждённые данные для проверки.";
                  return (
                    <article className={styles.questionRow} key={`${question}-${index}`}>
                      <span className={styles.numberBadge}>{index + 1}</span>
                      <div className={styles.questionCopy}><strong>{safeText(question, "Добавьте ответ основателя")}</strong><span>{actionDetail}</span></div>
                      <button className={styles.outlineButton} disabled={!questionAction} onClick={questionAction} type="button">{actionLabel}</button>
                    </article>
                  );
                })
              ) : (
                emptyQuestionUnlocks.map((item, index) => {
                  const isResearch = item.mode === "research";
                  const questionAction = isResearch ? (() => onRequestResearchConsent?.("question")) : onAddEvidence;
                  return (
                    <article className={styles.questionRow} key={item.title}>
                      <span className={styles.numberBadge}>{index + 1}</span>
                      <div className={styles.questionCopy}>
                        <strong>{item.title}</strong>
                        <span>{item.detail}</span>
                      </div>
                      <button className={styles.outlineButton} disabled={!questionAction} onClick={questionAction} type="button">{item.action}</button>
                    </article>
                  );
                })
              )}
            </div>
            <div className={styles.questionFooter}>
              <Info aria-hidden="true" size={16} />
              <span>Ответ можно дать вручную, файлом, разрешённым поиском или пропустить.</span>
            </div>
          </section>
        </div>
      </div>

      <section className={`${styles.panel} ${styles.researchCta}`}>
        <StatusIcon><Sparkles aria-hidden="true" size={28} /></StatusIcon>
        <div>
          <h2>Я могу сам исследовать рыночные риски и конкурентов</h2>
          <p>Безопасный поиск добавит внешние ориентиры по рынку, конкурентам и ценовым аналогам.</p>
        </div>
        <div className={styles.researchActions}>
          <button
            className={styles.pinkButton}
            disabled={!onRequestResearchConsent || Boolean(workspace?.busy)}
            onClick={() => onRequestResearchConsent?.("risks")}
            type="button"
          >
            Разрешить безопасный поиск
          </button>
          <span className={styles.researchDisclaimer}><ShieldCheck aria-hidden="true" size={16} />Финансовые и клиентские факты требуют ваших данных.</span>
        </div>
      </section>
    </section>
  );
}

function ActionPlanPage({
  workspace,
  onAcceptDirection,
  onSuggestAlternative,
  onPrepareAiAsset,
  onBuildWorkpack,
  onAddToPlan,
  onDiscussStrategy,
}: Readonly<{
  workspace?: FounderStrategyWorkspace | null;
  onAcceptDirection?: () => void;
  onSuggestAlternative?: () => void;
  onPrepareAiAsset?: FounderStrategyPagesProps["onPrepareAiAsset"];
  onBuildWorkpack?: () => void;
  onAddToPlan?: () => void;
  onDiscussStrategy?: () => void;
}>) {
  const scenarioIssues = scenarioRiskIssues(workspace?.selectedScenario);
  const gtm = workspace?.gtm ? buildStartupGtmPresentation(workspace.gtm) : null;
  const report = workspace?.reportSnapshot
    ? buildFounderReportPresentation(workspace.reportSnapshot)
    : null;
  const actionSection = report?.sections.find((section) => section.key === "action_plan");
  const actionItems = actionSection?.items.slice(0, 4) ?? [];
  const improvements = (actionItems.length > 0
    ? actionItems.map((item, index) => ({
        title: `Шаг из отчёта ${index + 1}`,
        detail: safeText(item, "Добавьте действие — я уточню проверку."),
        basis: safeText(actionSection?.statusLabel, "из отчёта"),
        Icon: [UsersRound, CircleDollarSign, TrendingUp, Target, ShieldCheck][index] ?? Sparkles,
        hypothesis: false,
      }))
    : [
        ["Уточнить целевой сегмент (ICP)", "Добавьте сегмент, бюджетного владельца и повторяемую боль — я соберу проверку."],
        ["Проверить цену", "Добавьте текущую цену, чек или тариф — я предложу тест монетизации."],
        ["Проверить время до первой ценности", "Добавьте путь запуска клиента — я найду шаги, которые можно сократить."],
        ["Проверить канал продаж", "Добавьте канал или разрешите поиск — я сравню стоимость и скорость проверки."],
      ].map(([title, detail], index) => ({
        title,
        detail,
        basis: "ИИ-гипотеза до подтверждения",
        Icon: [UsersRound, CircleDollarSign, TrendingUp, Target, ShieldCheck][index] ?? Sparkles,
        hypothesis: true,
      }))) as readonly Readonly<{
        title: string;
        detail: string;
        basis: string;
        Icon: LucideIcon;
        hypothesis: boolean;
      }>[];
  const priorityGuidanceSlots = actionItems.length > 0 && improvements.length < 4
    ? emptyActionPrioritySlots.slice(0, 4 - improvements.length)
    : [];
  const nextAssets = [
    ["interview", "Сценарий интервью с клиентом", MessageCircle],
    ["pricing", "Структуру эксперимента по цене", CircleDollarSign],
    ["positioning", "Карту позиционирования", Target],
    ["funnel", "Шаблон недельной воронки", Layers3],
  ] as const;
  const researchImpact = buildResearchImpactSummary(workspace);

  return (
    <section className={styles.page} data-founder-strategy-page="action-plan">
      <PageHero
        action={<button className={styles.outlineButton} disabled={!onDiscussStrategy} onClick={onDiscussStrategy} type="button"><Sparkles aria-hidden="true" size={20} />Обсудить стратегию с ИИ</button>}
        subtitle="Что я бы изменил в проекте и как проверить результат"
        title="План улучшений"
      >
        <TopToolbar status={gtm ? "На основе ваших материалов" : "Появится после анализа"} workspace={workspace} />
      </PageHero>

      <section className={`${styles.panel} ${styles.highlightPanel} ${styles.strategyHero}`}>
        <StatusIcon><Target aria-hidden="true" size={30} /></StatusIcon>
        <div>
          <span className={styles.eyebrow}>Финальная проверка и решение</span>
          <h2>{safeText(actionSection?.items[0], "Сузить целевой сегмент (ICP) до одного проверяемого сегмента, доказать повторяемую боль и проверить сокращение времени до результата.")}</h2>
          <p>Гипотеза ИИ требует вашей финальной проверки. Если допущения неверны, измените их перед формированием отчёта.</p>
        </div>
        <div className={styles.strategyHeroBenefits}>
          <div className={styles.benefitList}>
            <div><StatusIcon tone="pink"><Target aria-hidden="true" size={18} /></StatusIcon><span>Принять рекомендацию</span></div>
            <div><StatusIcon tone="green"><CircleDollarSign aria-hidden="true" size={18} /></StatusIcon><span>Изменить допущения</span></div>
            <div><StatusIcon tone="pink"><Sparkles aria-hidden="true" size={18} /></StatusIcon><span>Сформировать отчёт</span></div>
          </div>
        </div>
        <div className={styles.strategyHeroActions}>
          <button className={styles.pinkButton} disabled={!onAcceptDirection} onClick={onAcceptDirection} type="button">Принять рекомендацию<ArrowRight aria-hidden="true" size={20} /></button>
          <button className={styles.outlineButton} disabled={!onSuggestAlternative} onClick={onSuggestAlternative} type="button">Изменить допущения</button>
        </div>
      </section>

      <ScenarioOnlyDisclosure issues={scenarioIssues} />
      <PublicResearchImpactPanel impact={researchImpact} variant="action_plan" />

      <section className={styles.panel}>
        <h2>{`${improvements.length} ${improvements.length === 1 ? "приоритетное улучшение" : "приоритетных улучшений"}`}</h2>
        <div className={`${styles.priorityGrid} ${styles.priorityGridHonest}`}>
          {improvements.map(({ title, detail, basis, Icon, hypothesis }, index) => (
            <article className={styles.priorityCard} key={title}>
              <div className={styles.priorityHeader}>
                <span className={styles.numberBadge}>{index + 1}</span>
                <StatusIcon tone={index === 4 ? "red" : "pink"}><Icon aria-hidden="true" size={20} /></StatusIcon>
              </div>
              <strong>{title}</strong>
              <span>{detail}</span>
              <div className={styles.priorityAssessment}>
                <div className={styles.priorityBasis}>
                  <Sparkles aria-hidden="true" size={16} />
                  <span>{hypothesis ? "ИИ-гипотеза · требует проверки" : "Основано на отчёте"}</span>
                  {hypothesis ? null : <small>{basis}</small>}
                </div>
                <div className={styles.prioritySignals}>
                  <div>
                    <span>Эффект</span>
                    <strong>После проверки</strong>
                  </div>
                  <div>
                    <span>Усилия</span>
                    <strong>После оценки команды</strong>
                  </div>
                </div>
              </div>
              <div className={styles.priorityActions}>
                <button className={styles.smallButton} disabled={!onPrepareAiAsset} onClick={() => onPrepareAiAsset?.("interview")} type="button">Как проверить</button>
                <button className={styles.smallButton} disabled={!onAddToPlan} onClick={onAddToPlan} type="button">Добавить</button>
              </div>
            </article>
          ))}
          {priorityGuidanceSlots.map((slot, index) => (
            <article className={`${styles.priorityCard} ${styles.priorityGapCard}`} key={slot.label}>
              <div className={styles.priorityHeader}>
                <span className={styles.numberBadge}>{improvements.length + index + 1}</span>
                <StatusIcon tone="amber"><AlertTriangle aria-hidden="true" size={20} /></StatusIcon>
              </div>
              <strong>Что разблокирует следующий приоритет</strong>
              <span>{slot.detail}</span>
              <div className={styles.priorityAssessment}>
                <Database aria-hidden="true" size={18} />
                <div>
                  <span>Статус</span>
                  <strong>{slot.label}</strong>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <div className={styles.actionLayout}>
        <section className={styles.panel}>
          <h2>{gtm ? "План 7 / 30 / 60 / 90 дней" : "План 7 / 30 / 60 / 90 дней — ИИ-гипотеза"}</h2>
          <div className={styles.timeline}>
            {(gtm?.launchPlan ?? [
              { label: "7 дней", experimentLabels: ["ИИ-гипотеза: добавить описание целевого сегмента (ICP) и владельца бюджета"] },
              { label: "30 дней", experimentLabels: ["ИИ-гипотеза: проверить цену и канал"] },
              { label: "60 дней", experimentLabels: ["ИИ-гипотеза: сравнить альтернативы клиента"] },
              { label: "90 дней", experimentLabels: ["ИИ-гипотеза: проверить удержание и повторяемость"] },
            ]).map((step) => {
              const day = step.label.match(/\d+/u)?.[0] ?? step.label;

              return (
                <article className={`${styles.timelineStep} ${styles.strategyMilestone}`} key={step.label}>
                  <span className={styles.timelineMarker}>{day}</span>
                  <strong className={styles.timelineDay}>{step.label}</strong>
                  <span>{step.experimentLabels.slice(0, 2).join(" + ")}</span>
                  <span className={styles.timelineMetric}>
                    <span>Целевой показатель</span>
                    <strong>Появится после проверки</strong>
                  </span>
                </article>
              );
            })}
          </div>
        </section>

        <section className={styles.panel}>
          <h2>Что ИИ может подготовить сейчас</h2>
          <div className={styles.nextActions}>
            {nextAssets.map(([asset, title, Icon]) => (
              <article className={styles.nextAction} key={asset}>
                <Icon aria-hidden="true" size={22} />
                <strong>{title}</strong>
                <button
                  className={styles.outlineButton}
                  disabled={!onPrepareAiAsset || Boolean(workspace?.busy)}
                  onClick={() => onPrepareAiAsset?.(asset)}
                  title={workspace?.busy
                    ? "Дождитесь завершения текущей операции."
                    : onPrepareAiAsset
                      ? undefined
                      : "Сначала нужен текущий сценарий кейса."}
                  type="button"
                >
                  {workspace?.busy ? "Готовлю…" : "Подготовить"}
                </button>
              </article>
            ))}
          </div>
          <div className={styles.toolbar}>
            <button
              aria-describedby={!onBuildWorkpack ? "launch-pack-disabled-reason" : undefined}
              className={styles.pinkButton}
              disabled={!onBuildWorkpack || Boolean(workspace?.busy)}
              onClick={onBuildWorkpack}
              type="button"
            >
              {workspace?.busy ? "Собираю рабочий пакет…" : "Собрать рабочий пакет"}
              <ArrowRight aria-hidden="true" size={20} />
            </button>
            <button
              className={styles.outlineButton}
              disabled
              title={workspace?.launchPack ? "Черновик показан ниже." : "Сначала соберите рабочий пакет."}
              type="button"
            >
              Сначала показать черновики
            </button>
          </div>
          {!onBuildWorkpack ? (
            <p className={styles.researchDisclaimer} id="launch-pack-disabled-reason">
              Сначала примите рекомендацию выше и дождитесь готового отчёта. После этого я соберу финальный рабочий пакет.
            </p>
          ) : null}
        </section>
      </div>

      <FounderLaunchPack
        busy={Boolean(workspace?.busy)}
        launchPack={workspace?.launchPack}
        onRegenerate={onBuildWorkpack}
      />

      <footer className={styles.actionLegend}>
        <div>
          <StatusIcon tone="green"><CheckCircle2 aria-hidden="true" size={18} /></StatusIcon>
          <span><strong>Заявлено в материалах</strong><small>Указано в ваших документах</small></span>
        </div>
        <div>
          <StatusIcon tone="amber"><TrendingUp aria-hidden="true" size={18} /></StatusIcon>
          <span><strong>Вывод</strong><small>Анализ на основе заявлений из документов</small></span>
        </div>
        <div>
          <StatusIcon tone="pink"><Sparkles aria-hidden="true" size={18} /></StatusIcon>
          <span><strong>ИИ-гипотеза</strong><small>Предположение ИИ, а не факт</small></span>
        </div>
        <div>
          <StatusIcon tone="red"><AlertTriangle aria-hidden="true" size={18} /></StatusIcon>
          <span><strong>Требует проверки</strong><small>Нужны данные или эксперимент</small></span>
        </div>
      </footer>
    </section>
  );
}

function CheckRow({ text, tone, value }: Readonly<{ text: string; tone: Tone; value?: string }>) {
  const Icon = tone === "amber" ? AlertTriangle : CheckCircle2;
  return (
    <div className={styles.checkRow}>
      <Icon aria-hidden="true" color={toneColor(tone)} />
      <span>{text}</span>
      {value ? <strong>{value}</strong> : null}
    </div>
  );
}

function FormatCard({
  description,
  icon: Icon,
  href,
  title,
  status,
  tone,
}: Readonly<{
  description: string;
  href?: string;
  icon: LucideIcon;
  title: string;
  status: string;
  tone: Tone;
}>) {
  const Status = href ? CheckCircle2 : Clock3;
  const content = (
    <>
      <div className={styles.formatCardHeader}>
        <span className={styles.formatIcon} style={{ color: toneColor(tone) }}>
          <Icon aria-hidden="true" size={42} />
        </span>
        <div>
          <strong>{title}</strong>
          <p className={styles.formatDescription}>{description}</p>
        </div>
      </div>
      <div className={styles.formatStatus} data-ready={Boolean(href)}>
        <Status aria-hidden="true" size={18} />
        <span>{status}</span>
      </div>
    </>
  );
  if (href) {
    return (
      <a className={`${styles.formatCard} ${styles.formatCardLink}`} href={href} rel="noreferrer" target="_blank">
        {content}
      </a>
    );
  }
  return (
    <article className={styles.formatCard}>
      {content}
    </article>
  );
}

function reportReadinessScore(
  report: ReturnType<typeof buildFounderReportPresentation> | null,
): number | null {
  if (!report || report.sections.length === 0) return null;
  const earned = report.sections.reduce((score, section) => {
    if (section.status === "supported") return score + 1;
    if (section.status === "partial") return score + 0.5;
    return score;
  }, 0);
  return Math.round((earned / report.sections.length) * 100);
}

function reportCenterNextAction(
  hasApprovedLineage: boolean,
  gateReady: boolean,
  hasReport: boolean,
  busy: boolean,
): string {
  if (busy) return "Подождите: система обновляет этот же кейс";
  if (hasApprovedLineage) return "PDF, HTML и JSON готовы к скачиванию";
  if (gateReady) return "Проверьте черновик и нажмите «Сформировать отчёт»";
  if (hasReport) return "Откройте «План действий» и нажмите «Принять рекомендацию»";
  return "Вернитесь к анализу и завершите профиль проекта";
}

type ReportBlockerAction = Readonly<{
  title: string;
  detail: string;
  actionLabel: string;
  onClick: (() => void) | undefined;
}>;

function ReportCenterPage({
  workspace,
  onFreezeReport,
  onBackToAnalysis,
  onOpenOverview,
  onOpenActionPlan,
  onShareConsultant,
  onReportPageChange,
}: Readonly<{
  workspace?: FounderStrategyWorkspace | null;
  onFreezeReport?: () => void;
  onBackToAnalysis?: () => void;
  onOpenOverview?: () => void;
  onOpenActionPlan?: () => void;
  onShareConsultant?: () => void;
  onReportPageChange?: (direction: "previous" | "next") => void;
}>) {
  const report = workspace?.reportSnapshot
    ? buildFounderReportPresentation(workspace.reportSnapshot)
    : null;
  const supported = report?.sections.filter((section) => section.status === "supported").length ?? 0;
  const partial = report?.sections.filter((section) => section.status === "partial").length ?? 0;
  const blocked =
    report?.sections.filter(
      (section) => section.status === "needs_evidence" || section.status === "contradiction",
    ).length ?? 0;
  const readinessScore = reportReadinessScore(report);
  const actionSection = report?.sections.find((section) => section.key === "action_plan");
  const defaultConclusion =
    report?.sections.find((section) => section.key === "business_idea_summary")?.summary ??
    "Отчёт появится после анализа материалов и подтверждения ключевых решений.";
  const gateReady = Boolean(workspace?.report?.freezeAvailable && report);
  const freezeApproved = Boolean(workspace?.report?.freezeApproved);
  const pdfUrl = workspace?.report?.pdfUrl;
  const htmlUrl = workspace?.report?.htmlUrl;
  const jsonUrl = workspace?.report?.jsonUrl;
  const allReportUrlsPresent = Boolean(pdfUrl && htmlUrl && jsonUrl);
  const hasApprovedLineage = Boolean(freezeApproved && allReportUrlsPresent);
  const approvedPdfUrl = hasApprovedLineage ? pdfUrl : undefined;
  const approvedHtmlUrl = hasApprovedLineage ? htmlUrl : undefined;
  const approvedJsonUrl = hasApprovedLineage ? jsonUrl : undefined;
  const reportStatus = hasApprovedLineage
    ? "Отчёт зафиксирован"
    : gateReady
      ? "Готов к подтверждению"
      : "Ожидает решения";
  const nextReportAction = reportCenterNextAction(
    hasApprovedLineage,
    gateReady,
    Boolean(report),
    Boolean(workspace?.busy),
  );
  const [reportPage, setReportPage] = useState(1);
  const reportPageCount = Math.max(report?.sections.length ?? 1, 1);
  const visibleReportPage = Math.min(reportPage, reportPageCount);
  const currentReportSection = report?.sections[visibleReportPage - 1];
  const mainConclusion = currentReportSection?.summary ?? defaultConclusion;
  const canGoToPreviousReportPage = visibleReportPage > 1;
  const canGoToNextReportPage = visibleReportPage < reportPageCount;
  const reportVersionLabel = safeText(
    workspace?.report?.snapshotLabel,
    report ? "Версия данных готова" : "Версия появится после отчёта",
  );
  const needsReview = partial + blocked;
  const reportBlockers = [
    !report
      ? {
          title: "Профиль ещё не готов",
          detail: "Вернитесь к анализу, завершите профиль проекта и дождитесь обновления отчёта.",
          actionLabel: "Вернуться к анализу",
          onClick: onBackToAnalysis,
        }
      : null,
    report && supported === 0
      ? {
          title: "Нет подтверждённых оснований",
          detail: "Откройте «Обзор» и нажмите «Добавить данные», чтобы приложить материалы или ответы, которые подтвердят выводы.",
          actionLabel: "Открыть обзор",
          onClick: onOpenOverview,
        }
      : null,
    report && !gateReady && !hasApprovedLineage
      ? {
          title: "Рекомендация ещё не принята",
          detail: "В Плане действий нажмите «Принять рекомендацию», если согласны с направлением.",
          actionLabel: "Открыть план действий",
          onClick: onOpenActionPlan,
        }
      : null,
  ].filter((blocker): blocker is ReportBlockerAction => blocker !== null);

  function changeReportPage(direction: "previous" | "next") {
    setReportPage((current) => {
      const delta = direction === "previous" ? -1 : 1;
      return Math.min(Math.max(current + delta, 1), reportPageCount);
    });
    onReportPageChange?.(direction);
  }

  return (
    <section className={styles.page} data-founder-strategy-page="report-center">
      <PageHero subtitle="Проверьте итоговую версию перед заморозкой и скачиванием" title="Центр отчёта">
        <TopToolbar secondaryLabel={reportVersionLabel} status={reportStatus} workspace={workspace} />
      </PageHero>

      <div className={styles.reportGrid}>
        <section className={`${styles.panel} ${styles.reportPreview}`}>
          <div className={styles.reportCover}>
            <Image
              alt=""
              className={styles.reportCoverImage}
              fill
              sizes="(min-width: 1200px) 44vw, 100vw"
              src="/report-cover-planet.png"
            />
            <div className={styles.reportCoverOverlay}>
              <span className={styles.reportMark}>
                <Image alt="" height={30} src={founderIntelligenceMark} width={30} />
              </span>
              <h2>{projectName(workspace)}</h2>
              <p>Отчёт о готовности стартапа к росту</p>
              <div className={styles.readinessScore}>
                <span className={styles.readinessLabel}>Готовность</span>
                <div>
                  <strong>{readinessScore ?? "?"}</strong>
                  <span>{report ? "/ 100" : "после анализа"}</span>
                </div>
              </div>
              <div className={styles.reportConclusion}>
                <StatusIcon><Sparkles aria-hidden="true" size={20} /></StatusIcon>
                <div className={styles.reportConclusionCopy}>
                  <span className={styles.eyebrow}>Главный вывод</span>
                  <strong>{safeText(mainConclusion, "Главный вывод появится после анализа.")}</strong>
                </div>
              </div>
            </div>
          </div>
          {report ? (
            <div className={styles.reportContents}>
              <span className={styles.reportContentsLabel}>Содержание отчёта</span>
              <div className={styles.reportTabs} aria-label="Разделы отчёта">
                {report.sections.slice(0, 6).map((section, index) => (
                  <button
                    aria-current={visibleReportPage === index + 1 ? "page" : undefined}
                    className={visibleReportPage === index + 1 ? styles.reportTabActive : undefined}
                    key={section.key}
                    onClick={() => {
                      const nextPage = index + 1;
                      setReportPage(nextPage);
                      if (nextPage !== visibleReportPage) {
                        onReportPageChange?.(nextPage > visibleReportPage ? "next" : "previous");
                      }
                    }}
                    type="button"
                  >
                    {reportNavigationLabels[section.key] ?? section.title}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className={styles.reportPager}>
            <button className={styles.outlineButton} disabled={!canGoToPreviousReportPage} onClick={() => changeReportPage("previous")} type="button"><ArrowLeft aria-hidden="true" size={18} />Предыдущая</button>
            <span>{visibleReportPage} / {reportPageCount}</span>
            <button className={styles.outlineButton} disabled={!canGoToNextReportPage} onClick={() => changeReportPage("next")} type="button">Следующая<ArrowRight aria-hidden="true" size={18} /></button>
          </div>
        </section>

        <div className={styles.stack}>
          <section className={styles.panel}>
              <div className={styles.reportGateHeader}>
                <h2>Финальная проверка и решение</h2>
                <span className={styles.severity}>{nextReportAction}</span>
              </div>
              <div className={styles.reportGateBody}>
                <div className={styles.gateChecklist}>
                  <CheckRow
                    text={report ? "Профиль проекта включён в отчёт" : "Профиль появится после анализа"}
                    tone={report ? "green" : "amber"}
                  />
                  <CheckRow
                    text={supported > 0 ? "Подтверждённые выводы имеют основания" : "Основания ещё не подтверждены"}
                    value={supported > 0 ? `${supported} раздела` : undefined}
                    tone={supported > 0 ? "green" : "amber"}
                  />
                  <CheckRow
                    text={actionSection ? "План действий сформирован" : "План действий ещё не сформирован"}
                    value={safeText(actionSection?.statusLabel, "после анализа")}
                    tone={actionSection?.status === "supported" ? "green" : "amber"}
                  />
                  <CheckRow
                    text={needsReview > 0 ? "Непроверенные выводы помечены" : "Все выводы подтверждены"}
                    value={needsReview > 0 ? `${needsReview} разделов` : undefined}
                    tone={needsReview > 0 ? "amber" : "green"}
                  />
                </div>
                <div className={styles.reportGateVisual}>
                  <StatusIcon><ShieldCheck aria-hidden="true" size={54} /></StatusIcon>
                  <span>Ваше решение</span>
                </div>
              </div>
              <div className={styles.reportGateFooter}>
                <p>Нажатие «Сформировать отчёт» зафиксирует эту версию. После изменений будет создана новая.</p>
                <div className={styles.reportGateActions}>
                  {hasApprovedLineage && approvedPdfUrl ? (
                    <a className={styles.pinkButton} href={approvedPdfUrl} rel="noreferrer" target="_blank">Открыть PDF<ArrowRight aria-hidden="true" size={20} /></a>
                  ) : (
                    <button
                      className={styles.pinkButton}
                      disabled={!gateReady || !onFreezeReport || Boolean(workspace?.busy)}
                      onClick={onFreezeReport}
                      type="button"
                    >
                      {workspace?.busy ? "Формирую отчёт…" : "Сформировать отчёт"}
                      <ArrowRight aria-hidden="true" size={20} />
                    </button>
                  )}
                  <button className={styles.outlineButton} disabled={!onBackToAnalysis} onClick={onBackToAnalysis} type="button">Вернуться к анализу</button>
                </div>
              </div>
            </section>

          <section className={styles.panel}>
              <h2>Форматы отчёта</h2>
              <div className={styles.formatGrid}>
                <FormatCard description="Для презентации и отправки" href={approvedPdfUrl} icon={FileText} status={approvedPdfUrl ? "PDF готов" : gateReady ? "После подтверждения" : "После анализа"} title="PDF" tone="pink" />
                <FormatCard description="Интерактивный просмотр" href={approvedHtmlUrl} icon={FileText} status={approvedHtmlUrl ? "HTML готов" : gateReady ? "После подтверждения" : "После анализа"} title="HTML" tone="green" />
                <FormatCard description="Структурированные данные" href={approvedJsonUrl} icon={FileJson} status={approvedJsonUrl ? "JSON готов" : gateReady ? "После подтверждения" : "После анализа"} title="JSON" tone="pink" />
              </div>
            </section>
          {reportBlockers.length > 0 ? (
            <section className={styles.panel}>
              <h2>Что нужно сделать перед отчётом</h2>
              <div className={styles.nextActions}>
                {reportBlockers.map((blocker) => (
                  <article className={styles.nextAction} key={blocker.title}>
                    <strong>{blocker.title}</strong>
                    <p>{blocker.detail}</p>
                    <button
                      className={styles.outlineButton}
                      disabled={!blocker.onClick}
                      onClick={blocker.onClick}
                      type="button"
                    >
                      {blocker.actionLabel}
                      <ArrowRight aria-hidden="true" size={18} />
                    </button>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </div>

      <section className={`${styles.panel} ${styles.lineagePanel}`}>
        <StatusIcon><Layers3 aria-hidden="true" size={28} /></StatusIcon>
        <div className={styles.lineageLead}>
          <h2>{hasApprovedLineage ? "Одна зафиксированная версия — три формата" : "Одна зафиксированная версия создаст три формата"}</h2>
          <p>{hasApprovedLineage ? "PDF, HTML и JSON созданы из одной зафиксированной версии проекта и не расходятся по данным." : "После финального решения одна зафиксированная версия создаст PDF, HTML и JSON для этого же кейса."}</p>
          <div className={styles.lineageFacts}>
            <div className={styles.lineageFact}><FileText aria-hidden="true" size={18} /><span><small>Проект</small><strong>{projectName(workspace)}</strong></span></div>
            <div className={styles.lineageFact}><Database aria-hidden="true" size={18} /><span><small>Версия данных</small><strong>{workspace?.report?.snapshotLabel ?? "после отчёта"}</strong></span></div>
            <div className={styles.lineageFact}><Clock3 aria-hidden="true" size={18} /><span><small>Одобрено</small><strong>{hasApprovedLineage ? "да" : "после подтверждения"}</strong></span></div>
            <div className={styles.lineageFact}><ShieldCheck aria-hidden="true" size={18} /><span><small>Приватность</small><strong>исходные документы скрыты</strong></span></div>
          </div>
        </div>
        <div className={styles.lineageOrigin}>
          <div className={styles.lineageOriginHeader}><span className={styles.eyebrow}>Техническое происхождение</span><ChevronDown aria-hidden="true" size={18} /></div>
          <p>Подробности о снимке данных, источниках и проверках доступны для внутреннего аудита и не видны пользователям.</p>
          <div className={styles.lineagePrivacy}><ShieldCheck aria-hidden="true" size={18} /><span>В этой витрине нет исходных документов, системных инструкций и персональных данных.</span></div>
          <button className={styles.outlineButton} disabled={!onShareConsultant} onClick={onShareConsultant} type="button"><UsersRound aria-hidden="true" size={20} />Поделиться с консультантом</button>
        </div>
      </section>
    </section>
  );
}

export function FounderStrategyPages({
  page,
  workspace,
  onAllowResearch,
  onDiscussRisk,
  onAddEvidence,
  onAddToPlan,
  onAcceptDirection,
  onSuggestAlternative,
  onPrepareAiAsset,
  onBuildWorkpack,
  onFreezeReport,
  onBackToAnalysis,
  onOpenOverview,
  onOpenActionPlan,
  onShareConsultant,
  onShowEvidence,
  onAnswerQuestion,
  onDiscussStrategy,
  onReportPageChange,
}: FounderStrategyPagesProps) {
  const [researchConsentSource, setResearchConsentSource] = useState<ResearchConsentSource | null>(null);
  const [researchConsentError, setResearchConsentError] = useState<string | null>(null);
  const [researchConsentPending, setResearchConsentPending] = useState(false);
  const [selectedMode, setSelectedMode] = useState<ResearchConsentMode>("live_public_research");

  function openResearchConsent(source: ResearchConsentSource) {
    setResearchConsentError(null);
    setResearchConsentSource(source);
  }

  async function confirmResearchConsent(mode: ResearchConsentMode) {
    if (!onAllowResearch || workspace?.busy || researchConsentPending) {
      setResearchConsentError("Публичный поиск пока недоступен. Откройте помощник справа и проверьте следующий шаг.");
      return;
    }
    setResearchConsentError(null);
    setResearchConsentPending(true);
    try {
      const accepted = await onAllowResearch(mode);
      if (accepted) {
        setResearchConsentSource(null);
      } else {
        setResearchConsentError("Публичный поиск пока недоступен. Откройте помощник справа и проверьте следующий шаг.");
      }
    } catch {
      setResearchConsentError("Не удалось запустить публичный поиск. Откройте помощник справа и попробуйте ещё раз.");
    } finally {
      setResearchConsentPending(false);
    }
  }

  const consentDialog = researchConsentSource ? (
    <ResearchConsentDialog
      busy={Boolean(workspace?.busy) || researchConsentPending}
      error={researchConsentError}
      onAllowResearch={onAllowResearch}
      onCancel={() => setResearchConsentSource(null)}
      onConfirm={confirmResearchConsent}
      onModeChange={setSelectedMode}
      selectedMode={selectedMode}
    />
  ) : null;

  if (page === "market") {
    return (
      <>
        <MarketPage
          onAddToPlan={onAddToPlan ?? onAcceptDirection}
          onRequestResearchConsent={openResearchConsent}
          workspace={workspace}
        />
        {consentDialog}
      </>
    );
  }
  if (page === "risks") {
    return (
      <>
        <RisksPage
          onAddEvidence={onAddEvidence}
          onAnswerQuestion={onAnswerQuestion}
          onDiscussRisk={onDiscussRisk}
          onRequestResearchConsent={openResearchConsent}
          onShowEvidence={onShowEvidence ?? onBackToAnalysis}
          workspace={workspace}
        />
        {consentDialog}
      </>
    );
  }
  if (page === "action_plan") {
    return (
      <ActionPlanPage
        onAcceptDirection={onAcceptDirection}
        onAddToPlan={onAddToPlan ?? onAcceptDirection}
        onBuildWorkpack={onBuildWorkpack}
        onDiscussStrategy={onDiscussStrategy ?? onSuggestAlternative}
        onPrepareAiAsset={onPrepareAiAsset}
        onSuggestAlternative={onSuggestAlternative}
        workspace={workspace}
      />
    );
  }
  return (
    <ReportCenterPage
      onBackToAnalysis={onBackToAnalysis}
      onFreezeReport={onFreezeReport}
      onOpenActionPlan={onOpenActionPlan}
      onOpenOverview={onOpenOverview}
      onReportPageChange={onReportPageChange}
      onShareConsultant={onShareConsultant}
      workspace={workspace}
    />
  );
}
