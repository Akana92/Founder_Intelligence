"use client";

import {
  ArrowRight,
  AlertTriangle,
  BarChart3,
  Calculator,
  CheckCircle2,
  CircleCheckBig,
  CircleDollarSign,
  CircleDotDashed,
  ChevronDown,
  FileUp,
  FlaskConical,
  Funnel,
  Info,
  LockKeyhole,
  MessageCircle,
  PencilLine,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  UsersRound,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import type {
  AdvisorAnswerResponse,
  AdvisorAnswerType,
  AdvisorImprovementDecisionResponse,
  AdvisorImprovementsResponse,
  AdvisorNextQuestionResponse,
} from "../lib/contracts";
import {
  buildAdvisorAnswerPresentation,
  buildAdvisorImprovementPresentation,
  buildAdvisorQuestionImpactPresentation,
  buildAdvisorQuestionPresentation,
  safeFounderText,
} from "../lib/advisor-presentation";

import styles from "./founder-advisor-pages.module.css";

export type FounderAdvisorPageId =
  | "advisor_next_question"
  | "advisor_answer"
  | "advisor_updated_analysis"
  | "advisor_improved_plan";

export type FounderAdvisorAnswerInput = Readonly<{
  questionId: string;
  answerType: AdvisorAnswerType;
  manualValue: string;
  documentId: string | null;
  publicResearchConsent: boolean;
}>;

export type FounderAdvisorPagesWorkspace = Readonly<{
  acceptedDocumentIds?: readonly string[];
  advisorAnswer?: AdvisorAnswerResponse | null;
  advisorDecision?: AdvisorImprovementDecisionResponse | null;
  advisorError?: Error | null;
  advisorImprovements?: AdvisorImprovementsResponse | null;
  advisorQuestion?: AdvisorNextQuestionResponse | null;
  busy?: boolean;
  busyLabel?: string;
  canApproveGate2?: boolean;
}>;

export type FounderAdvisorPagesProps = Readonly<{
  page: FounderAdvisorPageId;
  workspace?: FounderAdvisorPagesWorkspace | null;
  onAddData?: () => void;
  onAdvisorAnswer?: (input: FounderAdvisorAnswerInput) => Promise<boolean> | boolean;
  onAdvisorImprovementDecision?: (
    proposalId: string,
    decision: "accepted" | "rejected",
  ) => void;
  onAdvisorRetry?: () => void;
  onApplyToReport?: () => void;
  onBackToQuestion?: () => void;
  onContinueRecalculation?: () => void;
  onOpenImprovedPlan?: () => void;
  onOpenPreparedAsset?: (
    asset: "interview" | "pricing" | "positioning" | "funnel",
  ) => void;
  onReturnPreviousVersion?: () => void;
}>;

const unavailableMarker = "MIS" + "SING";
const digestPrefix = "sha" + "256:";
const technicalPrivacyTerms = [
  "system " + "prompt",
  "prompt_" + "versions",
  "trace_" + "ids",
  "trace",
  "token",
  "secret",
  "private key",
  "sk-[A-Za-z0-9_-]{8,}",
].join("|");
const unsafeFounderPattern = new RegExp(
  `(?:\\b${unavailableMarker}\\b|${digestPrefix}[0-9a-f]{64}|[A-Za-z]:[\\\\/][^\\s]+|\\b[\\w-]+\\.(?:pdf|docx|xlsx|csv|png|jpg|jpeg|webp|zip)\\b|\\b(?:${technicalPrivacyTerms})\\b)`,
  "iu",
);
const consentPublicResearchField = "consent_public_research";

type IconTextCard = Readonly<{
  icon: LucideIcon;
  label: string;
  value: string;
}>;

type AdvisorQuestionCategory =
  | "customer"
  | "generic"
  | "market"
  | "retention"
  | "revenue_pricing"
  | "runway_cost";

type AdvisorQuestionContext = Readonly<{
  category: AdvisorQuestionCategory;
  fallbackAdvice: string;
  helperCopy: string;
  impacts: readonly IconTextCard[];
  manualPlaceholder: string;
  publicResearchNote: string;
  recalculationLabel: string;
  remainingInputLabel: string;
  savedLabel: string;
  subtitle: string;
  unlocks: readonly IconTextCard[];
}>;

const fieldCategoryByKey: Readonly<Record<string, AdvisorQuestionCategory>> = {
  business_model: "revenue_pricing",
  buyers: "customer",
  cac: "runway_cost",
  channels_gtm: "market",
  churn: "retention",
  competitors_mentioned: "market",
  customers: "customer",
  geography: "market",
  gross_margin: "revenue_pricing",
  icp: "customer",
  market: "market",
  monthly_recurring_revenue: "revenue_pricing",
  pricing_revenue_model: "revenue_pricing",
  retention: "retention",
  revenue_pricing: "revenue_pricing",
  runway: "runway_cost",
  stage: "generic",
  traction: "retention",
  users: "customer",
};

const advisorContextCopies: Record<AdvisorQuestionCategory, AdvisorQuestionContext> = {
  revenue_pricing: {
    category: "revenue_pricing",
    fallbackAdvice:
      "Зафиксируйте модель выручки, цену и базу клиентов — тогда я смогу предложить проверку тарифов и юнит-экономики.",
    helperCopy:
      "Модель выручки и цена: можно указать текущую месячную выручку или загрузить финансовую таблицу. Публичные аналоги я могу исследовать отдельно.",
    impacts: [
      { icon: Calculator, label: "Регулярная выручка (MRR/ARR)", value: "Можно пересчитать после сохранения" },
      { icon: TrendingUp, label: "Валовая маржа", value: "Уточнится по выручке и себестоимости" },
      { icon: ShieldCheck, label: "Риск монетизации", value: "Станет понятнее после проверки цены" },
      { icon: Target, label: "Следующий тарифный тест", value: "Появится как действие" },
    ],
    manualPlaceholder:
      "Например: подписка, цена за клиента, текущая месячная выручка и валовая маржа",
    publicResearchNote:
      "Публичный поиск поможет найти аналоги цен, но текущую выручку стартапа лучше указать вручную или файлом.",
    recalculationLabel: "Можно пересчитать регулярную выручку (MRR/ARR) и маржу",
    remainingInputLabel: "Для точности добавьте себестоимость, отток клиентов или количество платящих клиентов.",
    savedLabel: "Модель выручки сохранена",
    subtitle: "Ответ уточнит модель выручки, цену и применимые расчёты регулярной выручки (MRR/ARR) и маржи",
    unlocks: [
      { icon: Calculator, label: "Регулярная выручка (MRR/ARR)", value: "расчёт" },
      { icon: Target, label: "Цены и тарифы", value: "проверка цены" },
      { icon: TrendingUp, label: "Валовая маржа", value: "экономика" },
      { icon: ShieldCheck, label: "Риск монетизации", value: "проверка" },
    ],
  },
  retention: {
    category: "retention",
    fallbackAdvice:
      "Сначала подтвердите удержание по когортам — после этого ИИ сможет оценить ценность клиента (LTV) и риск повторного спроса.",
    helperCopy:
      "Можно описать продления вручную или загрузить таблицу CSV по когортам. Публичный поиск здесь полезен только для отраслевых ориентиров.",
    impacts: [
      { icon: UsersRound, label: "Удержание", value: "Будет пересчитано после сохранения" },
      { icon: Calculator, label: "Ценность клиента (LTV)", value: "Уточнится по когортным данным" },
      { icon: TrendingUp, label: "Повторная выручка", value: "Станет понятнее после ответа" },
      { icon: ShieldCheck, label: "Риск удержания", value: "Обновится после ответа" },
    ],
    manualPlaceholder: "Например: сколько клиентов продлевает через 3 месяца и сколько ушло",
    publicResearchNote:
      "Внутреннее удержание обычно не находится публично; поиск даст только отраслевые ориентиры.",
    recalculationLabel: "Можно пересчитать удержание, ценность клиента (LTV) и риск оттока клиентов",
    remainingInputLabel: "Для точности добавьте когорты, период наблюдения и число ушедших клиентов.",
    savedLabel: "Данные удержания сохранены",
    subtitle: "Ответ уточнит удержание, ценность клиента (LTV) и устойчивость повторного спроса",
    unlocks: [
      { icon: UsersRound, label: "Удержание", value: "когорты" },
      { icon: Calculator, label: "Ценность клиента (LTV)", value: "расчёт" },
      { icon: TrendingUp, label: "Повторная выручка", value: "прогноз" },
      { icon: ShieldCheck, label: "Риск оттока клиентов", value: "проверка" },
    ],
  },
  customer: {
    category: "customer",
    fallbackAdvice:
      "Сначала уточните целевой сегмент (ICP) и покупателя — после этого ИИ сможет предложить более точный канал продаж и интервью.",
    helperCopy:
      "Можно описать клиента вручную, приложить интервью или разрешить публичный поиск сегмента.",
    impacts: [
      { icon: UsersRound, label: "Целевой сегмент (ICP)", value: "Станет конкретнее после ответа" },
      { icon: Target, label: "Покупатель", value: "Отделится от пользователя" },
      { icon: TrendingUp, label: "Канал продаж", value: "Можно будет уточнить" },
      { icon: ShieldCheck, label: "Риск сегмента", value: "Обновится после ответа" },
    ],
    manualPlaceholder: "Например: кто пользователь, кто платит и в какой ситуации возникает боль",
    publicResearchNote:
      "Публичный поиск поможет проверить сегмент и похожие кейсы, но ваши интервью лучше добавить вручную.",
    recalculationLabel: "Можно уточнить целевой сегмент (ICP), портрет покупателя и канал",
    remainingInputLabel: "Для точности добавьте роли пользователей, покупателей и признаки боли.",
    savedLabel: "Клиентский сегмент сохранён",
    subtitle: "Ответ уточнит целевой сегмент (ICP), покупателя и путь продаж",
    unlocks: [
      { icon: UsersRound, label: "Целевой сегмент (ICP)", value: "сегмент" },
      { icon: Target, label: "Покупатель", value: "роль" },
      { icon: TrendingUp, label: "Канал", value: "выход" },
      { icon: ShieldCheck, label: "Риск сегмента", value: "проверка" },
    ],
  },
  market: {
    category: "market",
    fallbackAdvice:
      "Сначала уточните рынок и конкурентов — после этого ИИ сможет отделить прямые аналоги от заменителей.",
    helperCopy:
      "Можно добавить список конкурентов вручную, файлом или разрешить публичный поиск аналогов.",
    impacts: [
      { icon: Target, label: "Конкуренты", value: "Станут структурированнее" },
      { icon: BarChart3, label: "TAM / SAM / SOM", value: "Можно будет уточнить" },
      { icon: TrendingUp, label: "Дифференциация", value: "Появится в плане" },
      { icon: ShieldCheck, label: "Рыночный риск", value: "Обновится после ответа" },
    ],
    manualPlaceholder: "Например: прямые конкуренты, заменители и почему клиенты выберут вас",
    publicResearchNote:
      "Публичный поиск подходит для конкурентов и рыночных аналогов; внутренние данные не отправляются.",
    recalculationLabel: "Можно уточнить конкурентов, рынок и дифференциацию",
    remainingInputLabel: "Для точности добавьте сегмент рынка, географию и список альтернатив.",
    savedLabel: "Рыночный контекст сохранён",
    subtitle: "Ответ уточнит рынок, конкурентов и альтернативы",
    unlocks: [
      { icon: Target, label: "Конкуренты", value: "карта" },
      { icon: BarChart3, label: "TAM / SAM / SOM", value: "размер" },
      { icon: TrendingUp, label: "Отстройка", value: "позиция" },
      { icon: ShieldCheck, label: "Риск рынка", value: "проверка" },
    ],
  },
  runway_cost: {
    category: "runway_cost",
    fallbackAdvice:
      "Сначала уточните темп расходов, остаток денег и стоимость привлечения клиента (CAC) — после этого ИИ сможет проверить запас времени и экономику привлечения.",
    helperCopy:
      "Можно указать расходы вручную или загрузить финансовую таблицу. Публичный поиск даст только бенчмарки.",
    impacts: [
      { icon: Calculator, label: "Запас времени", value: "Можно будет рассчитать" },
      { icon: TrendingUp, label: "Темп расходов", value: "Уточнится после ответа" },
      { icon: Target, label: "Стоимость привлечения клиента (CAC)", value: "Появится в экономике продукта" },
      { icon: ShieldCheck, label: "Финансовый риск", value: "Обновится после ответа" },
    ],
    manualPlaceholder: "Например: остаток денег, ежемесячный темп расходов, стоимость привлечения клиента (CAC) или маркетинговые расходы",
    publicResearchNote:
      "Публичный поиск не узнает ваш остаток денег и темп расходов; он полезен только для отраслевых ориентиров.",
    recalculationLabel: "Можно пересчитать запас времени, темп расходов и стоимость привлечения клиента (CAC)",
    remainingInputLabel: "Для точности добавьте остаток денег, ежемесячный темп расходов, стоимость привлечения клиента (CAC) и план продаж.",
    savedLabel: "Финансовые расходы сохранены",
    subtitle: "Ответ уточнит запас времени, темп расходов и экономику продукта",
    unlocks: [
      { icon: Calculator, label: "Запас времени", value: "месяцы" },
      { icon: TrendingUp, label: "Темп расходов", value: "расход" },
      { icon: Target, label: "Стоимость привлечения клиента (CAC)", value: "привлечение" },
      { icon: ShieldCheck, label: "Риск остатка денег", value: "проверка" },
    ],
  },
  generic: {
    category: "generic",
    fallbackAdvice:
      "Сначала сохраните ответ на текущий вопрос — после этого ИИ покажет, какая часть отчёта улучшилась.",
    helperCopy:
      "Можно ответить вручную, приложить документ или разрешить публичный поиск, если вопрос относится к открытым данным.",
    impacts: [
      { icon: Target, label: "Профиль", value: "Станет точнее после ответа" },
      { icon: Calculator, label: "Метрики", value: "Будут пересчитаны, если есть база" },
      { icon: TrendingUp, label: "План действий", value: "Уточнится после ответа" },
      { icon: ShieldCheck, label: "Риски", value: "Станут понятнее" },
    ],
    manualPlaceholder: "Напишите короткий ответ или добавьте подтверждающий документ",
    publicResearchNote:
      "Публичный поиск запускается только для открытых фактов и только после согласия.",
    recalculationLabel: "Можно пересчитать релевантные блоки отчёта",
    remainingInputLabel: "Для точности добавьте источник, период и единицы измерения.",
    savedLabel: "Ответ сохранён",
    subtitle: "Ответ уточнит самый слабый участок анализа сейчас",
    unlocks: [
      { icon: Target, label: "Профиль", value: "факт" },
      { icon: Calculator, label: "Метрики", value: "расчёт" },
      { icon: TrendingUp, label: "План", value: "следующий шаг" },
      { icon: ShieldCheck, label: "Риски", value: "проверка" },
    ],
  },
};

function founderSafe(value: string | null | undefined, fallback: string): string {
  const safe = safeFounderText(value, fallback);
  return unsafeFounderPattern.test(safe) ? fallback : safe;
}

function compactFounderSafe(value: string | null | undefined, fallback: string): string {
  const safe = founderSafe(value, fallback);
  return safe.length > 150 ? `${safe.slice(0, 147).trim()}…` : safe;
}

function advisorErrorCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("code" in error)) {
    return null;
  }
  return typeof error.code === "string" ? error.code : null;
}

function buildAdvisorQuestionContext(
  workspace?: FounderAdvisorPagesWorkspace | null,
): AdvisorQuestionContext {
  const question = workspace?.advisorQuestion?.next_question ?? null;
  const fieldKey = (workspace?.advisorAnswer?.field_key || question?.field_key || "")
    .trim()
    .toLowerCase();
  const category = fieldCategoryByKey[fieldKey] ?? "generic";
  return advisorContextCopies[category];
}

function advisorBusyState(workspace?: FounderAdvisorPagesWorkspace | null) {
  const isBusy = Boolean(workspace?.busy);
  const busyCopy = workspace?.busyLabel ?? "Идёт обработка…";
  return { busyCopy, isBusy } as const;
}

function categoryTextMatches(
  category: AdvisorQuestionCategory,
  value: string | null | undefined,
): boolean {
  const text = value?.toLowerCase() ?? "";
  return Object.entries(fieldCategoryByKey).some(
    ([fieldKey, fieldCategory]) =>
      fieldCategory === category && text.includes(fieldKey),
  );
}

const founderTargetLabels: Readonly<Record<string, string>> = {
  "positioning": "Позиционирование",
  "monetization": "Монетизация",
  "metrics": "Метрики",
  "gtm": "Выход на рынок",
  "risk_reduction": "Снижение рисков",
  "investor_readiness": "Инвестиционная готовность",
};

function founderLabelForTarget(target: string): string {
  const normalized = target.toLowerCase();
  if (founderTargetLabels[normalized]) return founderTargetLabels[normalized];
  if (categoryTextMatches("revenue_pricing", normalized) || normalized.includes("monetization")) {
    return "Монетизация и метрики";
  }
  if (normalized.includes("positioning")) return "Позиционирование";
  if (categoryTextMatches("customer", normalized)) return "Клиент и целевой сегмент (ICP)";
  if (categoryTextMatches("market", normalized) || normalized.includes("gtm")) {
    return "Рынок и выход на рынок";
  }
  if (categoryTextMatches("runway_cost", normalized)) return "Финансы и запас времени";
  if (categoryTextMatches("retention", normalized)) return "Удержание";
  return founderSafe(target, "Область улучшения");
}

function selectCategoryProposal<T extends Readonly<{
  recommendation: string;
  target: string;
}>>(
  proposals: readonly T[],
  context: AdvisorQuestionContext,
): T | undefined {
  return proposals.find(
    (proposal) =>
      categoryTextMatches(context.category, proposal.target) ||
      categoryTextMatches(context.category, proposal.recommendation) ||
      (context.category === "revenue_pricing" &&
        /monetization|metrics|pricing|revenue|выруч|цен|тариф|марж/iu.test(
          `${proposal.target} ${proposal.recommendation}`,
        )),
  );
}

type ImprovedPlanTone = "amber" | "green" | "pink" | "red";
type PreparedAssetId = "interview" | "pricing" | "positioning" | "funnel";

const preparedAssets: readonly Readonly<{
  asset: PreparedAssetId;
  description: string;
  icon: LucideIcon;
  title: string;
}>[] = [
  {
    asset: "interview",
    description: "Вопросы для проверки выбранного целевого сегмента (ICP)",
    icon: MessageCircle,
    title: "Сценарий интервью",
  },
  {
    asset: "pricing",
    description: "Шаблон проверки цены и готовности платить",
    icon: CircleDollarSign,
    title: "Тест цены",
  },
  {
    asset: "positioning",
    description: "Сравнение обещания продукта и альтернатив",
    icon: Target,
    title: "Карта позиционирования",
  },
  {
    asset: "funnel",
    description: "Контроль этапов продаж и следующего действия",
    icon: Funnel,
    title: "Недельная воронка",
  },
];

const improvedPlanCadence = [
  { day: "7", label: "7 дней", tone: "pink" },
  { day: "30", label: "30 дней", tone: "pink" },
  { day: "60", label: "60 дней", tone: "amber" },
  { day: "90", label: "90 дней", tone: "green" },
] as const satisfies readonly Readonly<{
  day: string;
  label: string;
  tone: ImprovedPlanTone;
}>[];

function CenteredIcon({
  icon: Icon,
  size = 20,
  tone = "pink",
}: Readonly<{
  icon: LucideIcon;
  size?: number;
  tone?: ImprovedPlanTone;
}>) {
  return (
    <span className={styles.centeredIcon} data-tone={tone}>
      <Icon aria-hidden="true" size={size} strokeWidth={1.8} />
    </span>
  );
}

function isKnownAdvisorAnswerMode(type: AdvisorAnswerType): boolean {
  return (
    type === "manual" ||
    type === "file" ||
    type === "public_research" ||
    type === "skip"
  );
}

function AdvisorHero({
  action,
  eyebrow,
  subtitle,
  title,
}: Readonly<{
  action?: React.ReactNode;
  eyebrow?: string;
  subtitle: string;
  title: string;
}>) {
  return (
    <header className={styles.hero}>
      <div>
        {eyebrow ? <span className={styles.eyebrow}>{eyebrow}</span> : null}
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action ? <div className={styles.heroAction}>{action}</div> : null}
    </header>
  );
}

function QuestionPreview({
  workspace,
}: Readonly<{ workspace?: FounderAdvisorPagesWorkspace | null }>) {
  const question = buildAdvisorQuestionPresentation(workspace?.advisorQuestion ?? null);
  const questionContext = buildAdvisorQuestionContext(workspace);
  return (
    <section className={`${styles.questionCard} ${styles.questionFocusCard}`}>
      <span className={styles.roundIcon}>
        <Sparkles aria-hidden="true" size={34} />
      </span>
      <div>
        <span className={styles.kicker}>Следующий лучший вопрос</span>
        <h2>{question.question}</h2>
        <span className={styles.originBadge}>{question.originLabel}</span>
        <p className={styles.contextNote}>{question.context}</p>
        <h3>Почему сейчас</h3>
        <p>{question.reason}</p>
        <h3>После ответа я смогу</h3>
        <div className={styles.unlockGrid}>
          {questionContext.unlocks.map(({ icon: Icon, label, value }) => (
            <article key={label}>
              <Icon aria-hidden="true" size={20} />
              <span>{label}</span>
              <small>{value}</small>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function NextQuestionPage(props: FounderAdvisorPagesProps) {
  const { busyCopy, isBusy } = advisorBusyState(props.workspace);
  const question = buildAdvisorQuestionPresentation(props.workspace?.advisorQuestion ?? null);
  const questionContext = buildAdvisorQuestionContext(props.workspace);
  const activeQuestion = props.workspace?.advisorQuestion?.next_question ?? null;
  const questionImpactRows = buildAdvisorQuestionImpactPresentation({
    context: question.context,
    fieldKey: activeQuestion?.field_key ?? "",
    originLabel: question.originLabel,
    unlocks: question.unlocks,
  });
  const questionId =
    props.workspace?.advisorQuestion?.next_question?.question_id.trim() ?? "";
  const canAnswer = Boolean(questionId);
  return (
    <section
      className={styles.page}
      data-founder-advisor-page="advisor-next-question"
    >
      <AdvisorHero
        subtitle="Система задаёт один вопрос, который сильнее всего улучшит анализ сейчас"
        title="ИИ-советник"
      />
      <span className={styles.advisorStepPill}>
        <Sparkles aria-hidden="true" size={16} />
        {question.statusLabel} для повышения точности
      </span>
      <div className={`${styles.questionLayout} ${styles.advisorQuestionCanvas}`}>
        <div className={`${styles.glassPanel} ${styles.questionFocusColumn} ${styles.advisorSummaryRail}`}>
          <QuestionPreview workspace={props.workspace} />
          <div className={styles.actionRow}>
            <button
              className={styles.pinkButton}
              disabled={isBusy || !canAnswer}
              onClick={canAnswer ? props.onBackToQuestion : undefined}
              type="button"
            >
              {isBusy ? busyCopy : "Ответить на вопрос"}
              {!isBusy ? <ArrowRight aria-hidden="true" size={22} /> : null}
            </button>
            <button
              className={styles.outlineButton}
              disabled={isBusy || !canAnswer || !props.onAdvisorAnswer}
              onClick={() => {
                if (!questionId) return;
                props.onAdvisorAnswer?.({
                  answerType: "skip",
                  documentId: null,
                  manualValue: "",
                  publicResearchConsent: false,
                  questionId,
                });
              }}
              type="button"
            >
              Пропустить пока
            </button>
          </div>
          <p className={styles.privacyNote}>
            <Info aria-hidden="true" size={18} />
            {questionContext.helperCopy}
          </p>
        </div>
        <aside className={`${styles.glassPanel} ${styles.metricRailPanel} ${styles.metricRailCompact} ${styles.advisorSummaryRail}`}>
          <section aria-label="Что изменится после ответа" className={`${styles.metricRibbon} ${styles.metricRail}`}>
            {questionImpactRows.map((row, index) => {
              const Icon = index === 0 ? Target : index === 1 ? Calculator : ShieldCheck;
              return (
                <article className={styles.impactStat} key={row.label}>
                  <span className={styles.metricRing}>
                    <Icon aria-hidden="true" size={28} />
                  </span>
                  <div>
                    <span>{row.label}</span>
                    <strong>{row.value}</strong>
                    <em>{row.status}</em>
                  </div>
                </article>
              );
            })}
          </section>
        </aside>
      </div>
      <section className={`${styles.glassPanel} ${styles.advisorKnownStrip}`}>
        <h2>Что стоит добавить для точного анализа</h2>
        <div className={styles.factGrid}>
          {questionImpactRows.map((row, index) => {
            const Icon = index === 0 ? Target : index === 1 ? MessageCircle : BarChart3;
            return (
              <article className={styles.factCard} key={row.label}>
                <span className={styles.roundIcon}>
                  <Icon aria-hidden="true" size={24} />
                </span>
                <div>
                  <strong>{row.label}</strong>
                  <span>{row.value}</span>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </section>
  );
}

function AnswerModeCard({
  active,
  disabled,
  icon: Icon,
  label,
  note,
  onClick,
  recommended,
  warning,
}: Readonly<{
  active: boolean;
  disabled?: boolean;
  icon: LucideIcon;
  label: string;
  note: string;
  onClick: () => void;
  recommended?: boolean;
  warning?: boolean;
}>) {
  return (
    <button
      aria-pressed={active}
      className={`${styles.modeCard} ${styles.answerModeRow} ${active ? styles.modeCardActive : ""}`}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      <span aria-hidden="true" className={styles.modeSelector} />
      <span className={styles.modeIcon}>
        <Icon aria-hidden="true" size={24} />
      </span>
      <span>
        <strong>{label}</strong>
        <small>{note}</small>
      </span>
      {recommended ? <em>Рекомендуется</em> : null}
      {warning ? <em className={styles.warning}>Требует согласия</em> : null}
    </button>
  );
}

function AnswerPage(props: FounderAdvisorPagesProps) {
  const { busyCopy, isBusy } = advisorBusyState(props.workspace);
  const question = buildAdvisorQuestionPresentation(props.workspace?.advisorQuestion ?? null);
  const questionContext = buildAdvisorQuestionContext(props.workspace);
  const questionId = props.workspace?.advisorQuestion?.next_question?.question_id ?? "";
  const selectedDocumentId = props.workspace?.acceptedDocumentIds?.[0] ?? null;
  const [selectedMode, setSelectedMode] = useState<AdvisorAnswerType>("manual");
  const [manualValue, setManualValue] = useState("");
  const [publicResearchConsent, setPublicResearchConsent] = useState(false);
  const currentAdvisorErrorCode = advisorErrorCode(props.workspace?.advisorError);
  const semanticMismatch = currentAdvisorErrorCode === "advisor_manual_answer_semantic_mismatch";
  const manualInputError =
    selectedMode === "manual" && semanticMismatch
      ? "Ответ не подходит к текущему вопросу. Укажите источник, период, единицы и значение именно для этого поля."
      : null;
  const generalAnswerError =
    currentAdvisorErrorCode && currentAdvisorErrorCode !== "advisor_manual_answer_semantic_mismatch"
      ? "Не удалось сохранить ответ. Проверьте данные и попробуйте снова."
      : null;
  const modeLabels = new Map(
    question.modes
      .filter((mode) => isKnownAdvisorAnswerMode(mode.type))
      .map((mode) => [mode.type, mode.label]),
  );

  async function submitAnswer(answerType: AdvisorAnswerType = selectedMode) {
    if (isBusy) return;
    if (!questionId || !props.onAdvisorAnswer) return;
    if (answerType === "public_research" && !publicResearchConsent) return;
    if (answerType === "file" && !selectedDocumentId) return;
    if (answerType === "manual" && manualValue.trim() === "") return;
    const saved = await props.onAdvisorAnswer({
      answerType,
      documentId: answerType === "file" ? selectedDocumentId : null,
      manualValue: answerType === "manual" ? manualValue : "",
      publicResearchConsent,
      questionId,
    });
    if (saved) {
      setManualValue("");
    }
  }

  const canSave =
    selectedMode === "skip" ||
    (selectedMode === "manual" && manualValue.trim() !== "") ||
    (selectedMode === "file" && Boolean(selectedDocumentId)) ||
    (selectedMode === "public_research" && publicResearchConsent);

  return (
    <section className={styles.page} data-founder-advisor-page="advisor-answer">
      <AdvisorHero
        action={
          <button
            className={styles.outlineButton}
            disabled={isBusy || !props.onAdvisorRetry}
            onClick={props.onAdvisorRetry}
            type="button"
          >
            <Sparkles aria-hidden="true" size={20} />
            {isBusy ? busyCopy : "Обсудить риск с ИИ"}
          </button>
        }
        subtitle={questionContext.subtitle}
        title="Ответ на вопрос ИИ"
      />
      <div className={`${styles.answerGrid} ${styles.advisorAnswerCanvas}`}>
        <section className={`${styles.glassPanel} ${styles.advisorSummaryRail} ${styles.answerModePanel}`}>
          <div className={styles.numberedQuestion}>
            <span>1</span>
            <h2>{question.question}</h2>
          </div>
          <h3>Выберите способ ответа</h3>
          <div className={styles.modeStack}>
            <div
              className={`${styles.answerModeGroup} ${selectedMode === "manual" ? styles.answerModeGroupActive : ""}`}
            >
              <AnswerModeCard
                active={selectedMode === "manual"}
                disabled={isBusy}
                icon={PencilLine}
                label={modeLabels.get("manual") ?? "Ввести вручную"}
                note="Короткое значение или пояснение основателя"
                onClick={() => setSelectedMode("manual")}
                recommended
              />
              {selectedMode === "manual" ? (
                <label className={styles.manualInput}>
                  <span>Значение</span>
                  <textarea
                    aria-label="Ручной ответ советнику"
                    aria-invalid={manualInputError ? true : undefined}
                    disabled={isBusy}
                    onChange={(event) => setManualValue(event.currentTarget.value)}
                    placeholder={questionContext.manualPlaceholder}
                    rows={2}
                    value={manualValue}
                  />
                  {manualInputError ? (
                    <em className={styles.manualInputError} role="alert">
                      {manualInputError}
                    </em>
                  ) : null}
                  {generalAnswerError ? (
                    <em className={styles.manualInputError} role="alert">
                      {generalAnswerError}
                    </em>
                  ) : null}
                </label>
              ) : null}
            </div>
            <AnswerModeCard
              active={selectedMode === "file"}
              disabled={isBusy || !selectedDocumentId}
              icon={FileUp}
              label={modeLabels.get("file") ?? "Загрузить файл"}
              note={
                selectedDocumentId
                  ? "Использовать выбранный документ кейса"
                  : "Сначала добавьте CSV или Excel с данными"
              }
              onClick={() => setSelectedMode("file")}
            />
            <AnswerModeCard
              active={selectedMode === "public_research"}
              disabled={isBusy}
              icon={Sparkles}
              label={modeLabels.get("public_research") ?? "Попросить ИИ найти публичные данные"}
              note={questionContext.publicResearchNote}
              onClick={() => setSelectedMode("public_research")}
              warning={!publicResearchConsent}
            />
            <AnswerModeCard
              active={selectedMode === "skip"}
              disabled={isBusy}
              icon={RefreshCw}
              label={modeLabels.get("skip") ?? "Пропустить пока"}
              note="Вернуться к этому вопросу позже"
              onClick={() => setSelectedMode("skip")}
            />
          </div>
          {selectedMode === "public_research" ? (
            <label
              className={styles.consentBox}
              data-consent-field={consentPublicResearchField}
            >
              <input
                checked={publicResearchConsent}
                disabled={isBusy}
                onChange={(event) => setPublicResearchConsent(event.currentTarget.checked)}
                type="checkbox"
              />
              Публичный поиск запускается отдельно. Разрешить безопасный поиск только для этого вопроса
            </label>
          ) : null}
          <p className={styles.privacyNote}>{question.privacyNote}</p>
        </section>
        <section className={`${styles.glassPanel} ${styles.answerImpactPanel} ${styles.answerCtaStack}`}>
          <h2>Что изменится после ответа</h2>
          <div className={styles.impactList}>
            {questionContext.impacts.map(({ icon: Icon, label, value }) => (
              <article className={styles.impactRow} key={label}>
                <span className={styles.roundIcon}>
                  <Icon aria-hidden="true" size={24} />
                </span>
                <div>
                  <strong>{label}</strong>
                  <span>{value}</span>
                </div>
                <em>Ожидает сохранения</em>
              </article>
            ))}
          </div>
          <button
            className={styles.pinkButton}
            disabled={isBusy || !canSave}
            onClick={() => submitAnswer()}
            type="button"
          >
            <Sparkles aria-hidden="true" size={22} />
            {isBusy ? busyCopy : "Сохранить и пересчитать"}
          </button>
          <button
            className={styles.outlineButton}
            disabled={isBusy}
            onClick={props.onBackToQuestion}
            type="button"
          >
            Вернуться к вопросам
          </button>
          <div className={styles.safeNotice}>
            <ShieldCheck aria-hidden="true" size={24} />
            <div>
              <strong>Внутренние данные остаются локально</strong>
              <span>Факт основателя не смешивается с публичным поиском.</span>
            </div>
          </div>
        </section>
      </div>
    </section>
  );
}

function UpdatedAnalysisPage(props: FounderAdvisorPagesProps) {
  const { busyCopy, isBusy } = advisorBusyState(props.workspace);
  const answer = buildAdvisorAnswerPresentation(props.workspace?.advisorAnswer ?? null);
  const answerContext = buildAdvisorQuestionContext(props.workspace);
  const recalculationStarted =
    props.workspace?.advisorAnswer?.recalculation_status === "started";
  const hasConfirmedImprovementProposals =
    props.workspace?.advisorImprovements?.proposals.length === 6;
  const isAwaitingRecalculationConfirmation =
    recalculationStarted &&
    !hasConfirmedImprovementProposals &&
    Boolean(props.onContinueRecalculation);
  const canContinueRecalculation =
    isAwaitingRecalculationConfirmation &&
    props.workspace?.canApproveGate2 === true;
  const proposal = selectCategoryProposal(
    buildAdvisorImprovementPresentation(
      props.workspace?.advisorImprovements ?? null,
      props.workspace?.advisorDecision ?? null,
    ).proposals,
    answerContext,
  );
  const advice = compactFounderSafe(proposal?.recommendation, answerContext.fallbackAdvice);
  const recalculationStateCopy: Record<typeof answer.recalculationState, string> = {
    completed: "Пересчёт завершён",
    deferred: "Пересчёт отложен",
    none: "Нет пересчёта",
    pending: "Ожидает подтверждения",
  };
  const updatedHeroCopy: Record<
    typeof answer.recalculationState,
    Readonly<{ subtitle: string; title: string }>
  > = {
    completed: {
      subtitle: "Пересчёт завершён. Показываю только изменения, которые вернул API этого кейса.",
      title: "Анализ обновлён",
    },
    deferred: {
      subtitle: "Ответ сохранён, но пересчёт отложен. Отчёт не считается обновлённым.",
      title: "Ответ сохранён, пересчёт отложен",
    },
    none: {
      subtitle: "Ответ сохранён без пересчёта. Новых изменений отчёта пока нет.",
      title: "Ответ сохранён без пересчёта",
    },
    pending: {
      subtitle: "Профиль обновлён, отчёт ожидает подтверждения пересчёта этого же кейса.",
      title: "Профиль обновлён, отчёт ожидает пересчёта",
    },
  };

  return (
    <section
      className={styles.page}
      data-founder-advisor-page="advisor-updated-analysis"
    >
      <AdvisorHero
        action={
          <button
            className={styles.searchBarButton}
            disabled={isBusy || !props.onAdvisorRetry}
            onClick={props.onAdvisorRetry}
            type="button"
          >
            <Sparkles aria-hidden="true" size={20} />
            {isBusy ? busyCopy : "Спросить ИИ-советника о проекте"}
            {!isBusy ? <ArrowRight aria-hidden="true" size={22} /> : null}
          </button>
        }
        subtitle={updatedHeroCopy[answer.recalculationState].subtitle}
        title={updatedHeroCopy[answer.recalculationState].title}
      />
      <div className={`${styles.glassPanel} ${styles.updatedMetricRibbon} ${styles.updatedSummaryBand}`}>
        <section aria-label="Реальные изменения после ответа" className={`${styles.metricRibbon} ${styles.metricSegmented}`}>
          {answer.deltaRows.slice(0, 3).map((row, index) => {
            const Icon = index === 0 ? Target : index === 1 ? ShieldCheck : Calculator;
            return (
              <article className={styles.impactStat} key={row.label}>
                <span className={styles.metricRing}>
                  <Icon aria-hidden="true" size={28} />
                </span>
                <div>
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                  <em>{row.status}</em>
                </div>
              </article>
            );
          })}
        </section>
      </div>
      <div className={`${styles.updatedGrid} ${styles.advisorUpdatedCanvas}`}>
        <section className={`${styles.stack} ${styles.updatedDetailStack}`}>
          <article className={`${styles.glassPanel} ${styles.updatedConfirmedPanel}`}>
            <h2>
              <CheckCircle2 aria-hidden="true" size={28} />
              Что изменилось в профиле
            </h2>
            {answer.deltaRows.map((row) => (
              <div className={styles.resultRow} key={row.label}>
                <span className={styles.resultIcon}>
                  <UsersRound aria-hidden="true" size={24} />
                </span>
                <div className={styles.resultText}>
                  <strong>{row.label}</strong>
                  <span>{row.value}</span>
                </div>
                <em>{row.status}</em>
              </div>
            ))}
          </article>
          <article className={`${styles.glassPanel} ${styles.updatedRecalculatedPanel}`}>
            <h2>
              <RefreshCw aria-hidden="true" size={28} />
              Статус пересчёта
            </h2>
            <div className={styles.resultRow}>
              <span className={styles.resultIcon}>
                <Calculator aria-hidden="true" size={24} />
              </span>
              <div className={styles.resultText}>
                <strong>{answer.revisionLabel}</strong>
                <span>{answer.statusLabel}</span>
              </div>
              <em>{recalculationStateCopy[answer.recalculationState]}</em>
            </div>
            <div className={styles.resultRow}>
              <span className={styles.resultIcon}>
                <BarChart3 aria-hidden="true" size={24} />
              </span>
              <div className={styles.resultText}>
                <strong>{answer.progressLabel}</strong>
                <span>Ответов учтено в этом кейсе</span>
              </div>
              <em>Прогресс</em>
            </div>
          </article>
          <article className={`${styles.glassPanel} ${styles.updatedRiskPanel}`}>
            <h2>
              <ShieldCheck aria-hidden="true" size={28} />
              Что остаётся проверить
            </h2>
            <div className={styles.resultRow}>
              <span className={styles.resultIcon}>
                <AlertTriangle aria-hidden="true" size={24} />
              </span>
              <div className={styles.resultText}>
                <strong>{answer.deltaRows.at(-1)?.label ?? "Дальнейшая проверка"}</strong>
                <span className={styles.riskHint}>
                  {answer.deltaRows.at(-1)?.status ?? "Требует подтверждения"}
                </span>
              </div>
              <em>Требует подтверждения</em>
            </div>
          </article>
        </section>
        <aside className={`${styles.glassPanel} ${styles.advicePanel} ${styles.updatedAdviceColumn} ${styles.advisorSummaryRail}`}>
          <div className={styles.updatedAdviceCard}>
            <span className={styles.kicker}>
              <Sparkles aria-hidden="true" size={18} />
              Обновлённый совет ИИ-советника
            </span>
            <div className={styles.bigSpark}>
              <Sparkles aria-hidden="true" size={56} />
            </div>
            <h2>{advice}</h2>
            <em>Гипотеза ИИ</em>
            <p>
              Совет строится после сохранённого ответа и остаётся проверяемой гипотезой
              до следующего подтверждённого отчёта.
            </p>
          </div>
          <button
            className={styles.pinkButton}
            disabled={
              isBusy || (!hasConfirmedImprovementProposals && !canContinueRecalculation)
            }
            onClick={
              canContinueRecalculation
                  ? props.onContinueRecalculation
                  : hasConfirmedImprovementProposals
                    ? props.onOpenImprovedPlan
                  : undefined
            }
            type="button"
          >
            {isBusy
              ? busyCopy
              : isAwaitingRecalculationConfirmation
                ? "Продолжить обновление"
                : "Перейти к улучшенному плану"}
            {!isBusy ? <ArrowRight aria-hidden="true" size={22} /> : null}
          </button>
          {isAwaitingRecalculationConfirmation || !hasConfirmedImprovementProposals ? (
            <p>
              {isAwaitingRecalculationConfirmation
                ? "Подтвердите обновлённые данные — я пересчитаю анализ и подготовлю новый план этого же кейса."
                : "Улучшенный план появится после подготовки канонического отчёта этого же кейса."}
            </p>
          ) : null}
          <button
            className={styles.outlineButton}
            disabled={isBusy || !props.onAddData}
            onClick={props.onAddData}
            type="button"
          >
            Добавить ещё данные
          </button>
        </aside>
      </div>
      <p className={styles.updatedSourceStrip}>
        <Info aria-hidden="true" size={18} />
        Источник: ответ пользователя + сохранённые доказательства кейса.
      </p>
    </section>
  );
}

function ImprovedPlanPage(props: FounderAdvisorPagesProps) {
  const { busyCopy, isBusy } = advisorBusyState(props.workspace);
  const questionContext = buildAdvisorQuestionContext(props.workspace);
  const improvements = buildAdvisorImprovementPresentation(
    props.workspace?.advisorImprovements ?? null,
    props.workspace?.advisorDecision ?? null,
  );
  const proposalCards = improvements.proposals;
  const canDecideAdvisorProposals =
    proposalCards.length === 6 &&
    proposalCards.every((proposal) => proposal.id.trim() !== "");
  const mainProposal = selectCategoryProposal(proposalCards, questionContext) ?? proposalCards[0];
  const monetizationProposal =
    selectCategoryProposal(proposalCards, advisorContextCopies.revenue_pricing) ??
    mainProposal;
  const icpProposal =
    selectCategoryProposal(proposalCards, advisorContextCopies.customer) ?? mainProposal;
  const timelineProposals = proposalCards.slice(0, 4);
  const groundedProposalCount = proposalCards.filter((proposal) =>
    proposal.evidenceLabel.startsWith("Основано"),
  ).length;
  const proposalsToVerifyCount = Math.max(
    0,
    proposalCards.length - groundedProposalCount,
  );
  const advisorDecision = props.workspace?.advisorDecision ?? null;
  const recalculationStarted = advisorDecision?.recalculation_status === "started";
  const decisionStatusCopy = advisorDecision
    ? advisorDecision.decision === "accepted"
      ? recalculationStarted
        ? "Изменение принято — анализ этого же кейса пересчитывается"
        : "Изменение принято — следующая версия сохранит историю решения"
      : "Предложение отклонено — версия отчёта не изменилась"
    : "Выберите улучшения — новая версия появится только после вашего решения";

  return (
    <section className={styles.page} data-founder-advisor-page="advisor-improved-plan">
      <AdvisorHero
        action={
          <div className={styles.improvedTopActions}>
            <button
              className={`${styles.pinkButton} ${styles.improvedPrimaryAction}`}
              disabled={isBusy || !props.onApplyToReport}
              onClick={props.onApplyToReport}
              type="button"
            >
              <span>
                <strong>{isBusy ? busyCopy : "Применить изменения к отчёту"}</strong>
                <small className={styles.improvedActionHint}>
                  {props.onApplyToReport
                    ? "Обновить подтверждённую версию этого же кейса"
                    : "Доступно после финальной проверки отчёта"}
                </small>
              </span>
              {props.onApplyToReport ? (
                <ArrowRight aria-hidden="true" size={22} />
              ) : (
                <LockKeyhole aria-hidden="true" size={18} />
              )}
            </button>
            <button
              className={styles.outlineButton}
              disabled={isBusy || !props.onReturnPreviousVersion}
              onClick={props.onReturnPreviousVersion}
              type="button"
            >
              <RefreshCw aria-hidden="true" size={17} />
              Вернуться к предыдущей версии
            </button>
          </div>
        }
        eyebrow={
          canDecideAdvisorProposals
            ? "На основе подтверждённого ответа"
            : "Подготовка проверяемых улучшений"
        }
        subtitle={canDecideAdvisorProposals ? decisionStatusCopy : "ИИ готовит проверяемые предложения без выдуманных метрик."}
        title={
          canDecideAdvisorProposals
            ? improvements.heroTitle
            : "Улучшенный план ещё не сформирован"
        }
      />
      {!canDecideAdvisorProposals ? (
        <section className={styles.glassPanel}>
          <h2>Нужен канонический отчёт этого же кейса</h2>
          <p>
            Шесть проверяемых улучшений появятся после канонического отчёта этого же кейса.
          </p>
        </section>
      ) : (
        <div className={styles.advisorImprovedCanvas}>
          <section className={`${styles.improvedTopBand} ${styles.improvedPlanLayout}`}>
            <article
              className={`${styles.glassPanel} ${styles.beforeAfter} ${styles.improvedFocusPanel}`}
            >
              <h2>Главное изменение</h2>
              <div className={styles.beforeAfterState}>
                <CenteredIcon icon={XCircle} size={21} tone="pink" />
                <div>
                  <span>Было</span>
                  <p>Формулировка проекта до уточнения.</p>
                </div>
              </div>
              <span className={styles.changeFlowArrow}>
                <ArrowRight aria-hidden="true" size={30} strokeWidth={1.7} />
              </span>
              <div className={styles.beforeAfterState}>
                <CenteredIcon icon={CircleCheckBig} size={22} tone="green" />
                <div>
                  <span>Стало</span>
                  <p>
                    {compactFounderSafe(
                      mainProposal?.recommendation,
                      questionContext.fallbackAdvice,
                    )}
                  </p>
                </div>
              </div>
            </article>
            <article className={`${styles.glassPanel} ${styles.monetizationPanel}`}>
              <div className={styles.panelTitleRow}>
                <CenteredIcon icon={CircleDollarSign} size={28} tone="pink" />
                <div>
                  <h2>Обновлённая монетизация</h2>
                  <p>
                    {compactFounderSafe(
                      monetizationProposal?.recommendation,
                      "Модель монетизации уточнится после проверки цены и каналов.",
                    )}
                  </p>
                </div>
              </div>
              <div className={styles.miniStats}>
                <span className={styles.metricSignal}>
                  <CircleDotDashed aria-hidden="true" size={17} />
                  <small>Готовность</small>
                  <strong>После решения</strong>
                </span>
                <span className={styles.metricSignal}>
                  <ShieldCheck aria-hidden="true" size={17} />
                  <small>Доказательства</small>
                  <strong>После отчёта</strong>
                </span>
              </div>
            </article>
          </section>
          <section className={styles.improvedMiddleBand}>
            <article className={`${styles.glassPanel} ${styles.icpPanel}`}>
              <div className={styles.panelTitleRow}>
                <CenteredIcon icon={UsersRound} size={22} tone="pink" />
                <h2>Обновлённый целевой сегмент (ICP)</h2>
              </div>
              <p>
                {compactFounderSafe(
                  icpProposal?.recommendation,
                  "Сегмент станет точнее после ответа основателя.",
                )}
              </p>
              <div className={styles.verificationList}>
                {[
                  ["Соответствие боли", "Требует подтверждения"],
                  ["Бюджетная готовность", "Требует подтверждения"],
                  ["Доступ к решению", "Требует подтверждения"],
                ].map(([label, value]) => (
                  <span className={styles.verificationRow} key={label}>
                    <CircleDotDashed aria-hidden="true" size={16} />
                    <small>{label}</small>
                    <strong>{value}</strong>
                  </span>
                ))}
              </div>
            </article>
            <article className={`${styles.glassPanel} ${styles.pricingPanel}`}>
              <div className={styles.panelTitleRow}>
                <CenteredIcon icon={FlaskConical} size={22} tone="pink" />
                <h2>Эксперимент с ценой</h2>
              </div>
              <p>
                {compactFounderSafe(
                  monetizationProposal?.expectedEffect,
                  "Проверить цену и готовность платить без подмены фактов гипотезами.",
                )}
              </p>
              <div className={styles.verificationList}>
                {[
                  ["Готовность платить", "Требует подтверждения"],
                  ["Проверяемая цена", "Требует подтверждения"],
                  ["Окупаемость", "Добавьте стоимость привлечения клиента (CAC) и маржу"],
                ].map(([label, value]) => (
                  <span className={styles.verificationRow} key={label}>
                    <CircleDotDashed aria-hidden="true" size={16} />
                    <small>{label}</small>
                    <strong>{value}</strong>
                  </span>
                ))}
              </div>
            </article>
            <article
              className={`${styles.glassPanel} ${styles.evidenceStatePanel} ${styles.advisorSummaryRail}`}
            >
              <div className={styles.panelTitleRow}>
                <CenteredIcon icon={ShieldCheck} size={22} tone="pink" />
                <h2>Состояние доказательств</h2>
              </div>
              <div className={styles.evidenceOverview}>
                <div className={`${styles.donut} ${styles.evidenceScore}`}>
                  <strong>После</strong>
                  <span>отчёта</span>
                </div>
                <div className={styles.evidenceLegend}>
                  <span className={styles.evidenceLegendRow} data-tone="green">
                    <CircleCheckBig aria-hidden="true" size={15} />
                    <small>С доказательствами</small>
                    <strong>{groundedProposalCount}</strong>
                  </span>
                  <span className={styles.evidenceLegendRow} data-tone="amber">
                    <Calculator aria-hidden="true" size={15} />
                    <small>Расчёты</small>
                    <strong>После отчёта</strong>
                  </span>
                  <span className={styles.evidenceLegendRow} data-tone="pink">
                    <Sparkles aria-hidden="true" size={15} />
                    <small>Требуют проверки</small>
                    <strong>{proposalsToVerifyCount}</strong>
                  </span>
                </div>
              </div>
              <div className={styles.evidenceConfidenceStrip}>
                <BarChart3 aria-hidden="true" size={18} />
                <span>Уверенность анализа</span>
                <strong>Уточнится после проверки</strong>
              </div>
            </article>
          </section>
          <details className={styles.proposalDecisionDisclosure}>
            <summary className={styles.proposalDecisionSummary}>
              <span className={styles.proposalDisclosureIcon}>
                <Sparkles aria-hidden="true" size={18} />
              </span>
              <span className={styles.proposalDisclosureCopy}>
                <strong>6 проверяемых предложений</strong>
                <small>Откройте, чтобы принять или отклонить каждое</small>
              </span>
              <span className={styles.proposalDisclosureAction}>
                Выбрать решения
                <ChevronDown aria-hidden="true" size={18} />
              </span>
            </summary>
            <section className={styles.proposalDecisionPanel}>
              <div className={styles.proposalDecisionHeader}>
                <h2>Решения по улучшениям</h2>
                <p>Каждое решение сохранится в истории этого кейса и попадёт в следующую версию только после вашего выбора.</p>
              </div>
              <div className={`${styles.proposalDecisionGrid} ${styles.proposalCompactGrid}`}>
              {proposalCards.slice(0, 6).map((proposal, index) => (
                <article
                  className={styles.proposalDecisionItem}
                  key={proposal.id || `${proposal.target}-${index}`}
                >
                  <span className={styles.roundIcon}>
                    <Sparkles aria-hidden="true" size={17} />
                  </span>
                  <div>
                    <strong>{founderLabelForTarget(proposal.target)}</strong>
                    <p>{compactFounderSafe(proposal.recommendation, "Совет появится после анализа.")}</p>
                    <em>{proposal.confidenceLabel}</em>
                  </div>
                  <div className={styles.actionRow}>
                    <button
                      className={styles.outlineButton}
                      disabled={isBusy || !canDecideAdvisorProposals || !props.onAdvisorImprovementDecision}
                      onClick={() => props.onAdvisorImprovementDecision?.(proposal.id, "accepted")}
                      type="button"
                    >
                      Принять
                    </button>
                    <button
                      className={styles.outlineButton}
                      disabled={isBusy || !canDecideAdvisorProposals || !props.onAdvisorImprovementDecision}
                      onClick={() => props.onAdvisorImprovementDecision?.(proposal.id, "rejected")}
                      type="button"
                    >
                      Отклонить
                    </button>
                  </div>
                </article>
              ))}
              </div>
            </section>
          </details>
          <section className={`${styles.improvedBottomBand} ${styles.improvedEvidenceDeck}`}>
            <section className={`${styles.glassPanel} ${styles.improvedTimelinePanel}`}>
              <h2>План 7 / 30 / 60 / 90 дней</h2>
              <div className={`${styles.timeline} ${styles.timelineConnected}`}>
                {improvedPlanCadence.map(({ day, label, tone }, index) => {
                  const proposal = timelineProposals[index] ?? mainProposal!;
                  const milestoneStatus = recalculationStarted
                    ? index === 0
                      ? "В пересчёте"
                      : "После пересчёта"
                    : advisorDecision?.decision === "accepted"
                      ? index === 0
                        ? "Принято"
                        : "Следующий этап"
                      : index === 0
                        ? "Ожидает выбора"
                        : "После принятия";
                  return (
                    <article className={styles.timelineMilestone} key={day}>
                      <strong data-tone={tone}>{day}</strong>
                      <div className={styles.timelineContent}>
                        <b>{label}</b>
                        <small>{founderLabelForTarget(proposal.target)}</small>
                        <p>
                          {compactFounderSafe(proposal.expectedEffect, proposal.recommendation)}
                        </p>
                        <span className={styles.timelineStatus} data-tone={tone}>
                          <CircleDotDashed aria-hidden="true" size={13} />
                          {milestoneStatus}
                        </span>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
            <section className={`${styles.glassPanel} ${styles.improvedAssetsPanel}`}>
              <h2>Материалы, подготовленные ИИ</h2>
              <div className={`${styles.assetList} ${styles.preparedAssetList}`}>
                {preparedAssets.map(({ asset, description, icon, title }) => (
                  <button
                    className={styles.assetRow}
                    disabled={isBusy || !props.onOpenPreparedAsset}
                    key={asset}
                    onClick={() => props.onOpenPreparedAsset?.(asset)}
                    type="button"
                  >
                    <CenteredIcon icon={icon} size={18} tone="pink" />
                    <span className={styles.assetCopy}>
                      <strong>{title}</strong>
                      <small>{description}</small>
                    </span>
                    <span className={styles.assetAvailability}>
                      {isBusy ? (
                        busyCopy
                      ) : props.onOpenPreparedAsset ? (
                        <>
                          Открыть
                          <ArrowRight aria-hidden="true" size={17} />
                        </>
                      ) : (
                        <>
                          <LockKeyhole aria-hidden="true" size={13} />
                          После выбора решений
                        </>
                      )}
                    </span>
                  </button>
                ))}
              </div>
            </section>
            <footer className={styles.legend}>
              <span>
                <CenteredIcon icon={CircleCheckBig} size={14} tone="green" />
                <span><strong>Заявлено</strong><small>Указано в материалах кейса</small></span>
              </span>
              <span>
                <CenteredIcon icon={Calculator} size={14} tone="amber" />
                <span><strong>Расчёт</strong><small>На данных, заявленных в документах</small></span>
              </span>
              <span>
                <CenteredIcon icon={Sparkles} size={14} tone="pink" />
                <span><strong>Гипотеза ИИ</strong><small>Требует проверки</small></span>
              </span>
            </footer>
          </section>
        </div>
      )}
    </section>
  );
}

export function FounderAdvisorPages(props: FounderAdvisorPagesProps) {
  if (props.page === "advisor_next_question") {
    return <NextQuestionPage {...props} />;
  }
  if (props.page === "advisor_answer") {
    return <AnswerPage {...props} />;
  }
  if (props.page === "advisor_updated_analysis") {
    return <UpdatedAnalysisPage {...props} />;
  }
  return <ImprovedPlanPage {...props} />;
}
