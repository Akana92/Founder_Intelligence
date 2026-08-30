import type {
  AdvisorAnswerResponse,
  AdvisorAnswerType,
  AdvisorImprovementDecisionResponse,
  AdvisorImprovementProposal,
  AdvisorImprovementsResponse,
  AdvisorNextQuestionResponse,
} from "./contracts.ts";

export type AdvisorDesktopScreenId =
  | "start"
  | "data-room"
  | "progress-gate2"
  | "overview"
  | "metrics"
  | "market"
  | "risks"
  | "action-plan"
  | "report-center"
  | "admin-proof"
  | "next-question"
  | "answer"
  | "updated-analysis"
  | "improved-plan";

export type AdvisorDesktopScreen = Readonly<{
  id: AdvisorDesktopScreenId;
  title: string;
  mobile: false;
}>;

export const ADVISOR_DESKTOP_SEQUENCE: readonly AdvisorDesktopScreen[] = [
  { id: "start", title: "Старт", mobile: false },
  { id: "data-room", title: "Дата-рум", mobile: false },
  { id: "progress-gate2", title: "Прогресс и контроль 2", mobile: false },
  { id: "overview", title: "Обзор", mobile: false },
  { id: "next-question", title: "Лучший вопрос", mobile: false },
  { id: "answer", title: "Ответ", mobile: false },
  { id: "updated-analysis", title: "Обновлённый анализ", mobile: false },
  { id: "improved-plan", title: "Улучшенный план", mobile: false },
  { id: "metrics", title: "Метрики", mobile: false },
  { id: "market", title: "Рынок", mobile: false },
  { id: "risks", title: "Риски", mobile: false },
  { id: "action-plan", title: "План действий", mobile: false },
  { id: "report-center", title: "Центр отчётов", mobile: false },
  { id: "admin-proof", title: "Техническая проверка", mobile: false },
] as const;

const unsafeFounderTextPattern =
  /(?:\bMISSING\b|sha256:[0-9a-f]{64}|[A-Za-z]:[\\/][^\s]+|\b[\w-]+\.(?:pdf|docx|xlsx|csv|png|jpg|jpeg|webp|zip)\b|\b(?:system prompt|prompt_versions|trace_ids|trace|token|secret|private key|sk-[A-Za-z0-9_-]{8,})\b)/iu;

export function safeFounderText(
  value: string | null | undefined,
  fallback = "Недостаточно данных",
): string {
  const text = value?.trim() ?? "";
  if (!text || unsafeFounderTextPattern.test(text)) return fallback;
  return text.length > 240 ? `${text.slice(0, 237).trim()}…` : text;
}

export type AdvisorQuestionPresentation = Readonly<{
  context: string;
  originLabel: string;
  statusLabel: string;
  question: string;
  reason: string;
  unlocks: string;
  modes: readonly Readonly<{ type: AdvisorAnswerType; label: string }>[];
  publicResearchRequiresConsent: boolean;
  privacyNote: string;
}>;

export type AdvisorImpactPresentation = Readonly<{
  label: string;
  status: string;
  value: string;
}>;

const fieldLabels: Readonly<Record<string, string>> = {
  business_model: "Бизнес-модель",
  buyers: "Покупатель",
  cac: "Стоимость привлечения клиента (CAC)",
  channels_gtm: "Канал продаж",
  churn: "Отток клиентов",
  competitors_mentioned: "Конкуренты",
  customers: "Клиенты",
  geography: "География",
  gross_margin: "Валовая маржа",
  icp: "Целевой сегмент (ICP) и клиент",
  ltv_cac_ratio: "Ценность клиента (LTV) / стоимость привлечения (CAC)",
  market: "Рынок",
  monthly_recurring_revenue: "Ежемесячная регулярная выручка (MRR)",
  pricing_revenue_model: "Модель выручки и цена",
  report: "Отчёт",
  retention: "Удержание",
  revenue_pricing: "Монетизация",
  runway: "Запас времени",
  runway_months: "Запас времени",
  stage: "Стадия",
  traction: "Сигналы спроса",
  users: "Пользователи",
};

function founderLabelForCode(code: string): string | null {
  return fieldLabels[code.trim().toLowerCase()] ?? null;
}

function summarizeCodes(
  codes: readonly string[],
  unknownSingular: string,
  unknownPlural: string,
): string {
  const known = codes
    .map(founderLabelForCode)
    .filter((label): label is string => Boolean(label));
  const uniqueKnown = [...new Set(known)];
  const unknownCount = Math.max(0, codes.length - uniqueKnown.length);
  const unknownLabel =
    unknownCount === 0
      ? null
      : unknownCount === 1
        ? unknownSingular
        : `${unknownPlural}: ${unknownCount}`;
  const parts = unknownLabel ? [...uniqueKnown, unknownLabel] : uniqueKnown;
  if (parts.length === 0) return "Нет изменений";
  return parts.join(", ").replace(`1 ${unknownPlural}`, `1 ${unknownSingular}`);
}

export function buildAdvisorQuestionPresentation(
  response: AdvisorNextQuestionResponse | null,
): AdvisorQuestionPresentation {
  const question = response?.next_question ?? null;
  const modes = question?.answer_modes ?? ["manual", "file", "skip"];
  const labels = question?.answer_mode_labels_ru;
  return {
    statusLabel:
      response?.status === "complete"
        ? "Вопросы закрыты"
        : response
          ? `Вопрос ${Math.min(response.answered_count + 1, response.total_count)} из ${response.total_count}`
          : "Вопрос уточняется",
    originLabel: safeFounderText(question?.origin_label_ru, "Пробел в данных"),
    context: safeFounderText(
      question?.context_ru,
      "Советник выбрал этот вопрос по текущему состоянию профиля.",
    ),
    question: safeFounderText(
      question?.question_ru,
      "Что нужно уточнить, чтобы повысить качество анализа?",
    ),
    reason: safeFounderText(question?.reason_ru, "Ответ улучшит профиль стартапа."),
    unlocks: safeFounderText(
      question?.unlocks_ru,
      "После ответа советник пересчитает рекомендации.",
    ),
    modes: modes.map((type) => ({
      type,
      label: safeFounderText(labels?.[type], defaultModeLabel(type)),
    })),
    publicResearchRequiresConsent: modes.includes("public_research"),
    privacyNote:
      "Публичный поиск запускается только после явного согласия; ручной ответ не показывается повторно.",
  };
}

export function buildAdvisorQuestionImpactPresentation(input: Readonly<{
  context: string;
  fieldKey: string;
  originLabel: string;
  unlocks: string;
}>): readonly AdvisorImpactPresentation[] {
  const fieldLabel = founderLabelForCode(input.fieldKey) ?? "Поле профиля";
  const lowerField = input.fieldKey.trim().toLowerCase();
  const value = safeFounderText(input.context, "Советник нашёл пробел в текущем профиле.");
  const unlocks = safeFounderText(input.unlocks, "После ответа обновятся только подтверждённые выводы.");
  const origin = safeFounderText(input.originLabel, "Нужно уточнение");
  if (["pricing_revenue_model", "monthly_recurring_revenue", "gross_margin", "business_model", "revenue_pricing"].includes(lowerField)) {
    return [
      { label: "Монетизация", value: fieldLabel, status: origin },
      { label: "Регулярная выручка (MRR/ARR)", value: unlocks, status: "После ответа" },
      { label: "Валовая маржа", value, status: "Проверка" },
    ];
  }
  if (["icp", "customers", "users", "buyers"].includes(lowerField)) {
    return [
      { label: "Клиент и целевой сегмент (ICP)", value: fieldLabel, status: origin },
      { label: "Сегмент", value, status: "Проверка" },
      { label: "Канал продаж", value: unlocks, status: "После ответа" },
    ];
  }
  if (["runway", "cac"].includes(lowerField)) {
    return [
      { label: "Запас времени", value: fieldLabel, status: origin },
      { label: "Темп расходов / стоимость привлечения (CAC)", value, status: "Проверка" },
      { label: "Финансовый риск", value: unlocks, status: "После ответа" },
    ];
  }
  if (["retention", "traction", "churn"].includes(lowerField)) {
    return [
      { label: "Сигналы спроса", value: fieldLabel, status: origin },
      { label: "Удержание", value, status: "Проверка" },
      { label: "Повторный спрос", value: unlocks, status: "После ответа" },
    ];
  }
  return [
    { label: fieldLabel, value, status: origin },
    { label: "Что изменится", value: unlocks, status: "После ответа" },
    { label: "Доказательства", value: "Будут связаны с текущим кейсом", status: "Проверка" },
  ];
}

function defaultModeLabel(type: AdvisorAnswerType): string {
  const labels: Record<AdvisorAnswerType, string> = {
    manual: "Ответить вручную",
    file: "Прикрепить файл",
    public_research: "Разрешить публичный поиск",
    skip: "Пропустить",
  };
  return labels[type];
}

export type AdvisorAnswerPresentation = Readonly<{
  title: string;
  deltaLabel: string;
  deltaRows: readonly Readonly<{
    label: string;
    value: string;
    status: string;
  }>[];
  progressLabel: string;
  recalculationState: "completed" | "deferred" | "none" | "pending";
  revisionLabel: string;
  statusLabel: string;
  researchLabel: string;
  nonBlocking: true;
}>;

export function buildAdvisorAnswerPresentation(
  response: AdvisorAnswerResponse | null,
  input: Readonly<{ manualAnswer?: string | null }> = {},
): AdvisorAnswerPresentation {
  void input;
  const delta = response?.confidence_delta ?? 0;
  const sign = delta > 0 ? "+" : "";
  const recalculationStatus = response?.recalculation_status ?? "not_requested";
  const recalculationDelta = response?.recalculation_delta ?? null;
  const recalculationState =
    recalculationStatus === "started" && recalculationDelta
      ? "pending"
      : recalculationStatus === "deferred"
        ? "deferred"
        : recalculationDelta
          ? "completed"
          : "none";
  return {
    title:
      response?.status === "blocked"
        ? "Советник не заблокировал основной отчёт"
        : recalculationStatus === "started"
          ? "Ответ учтён; новая ревизия запущена"
          : "Ответ учтён без повторного показа текста",
    deltaLabel: `${sign}${delta} к уверенности`,
    progressLabel: response
      ? `${response.answered_count} из ${response.total_count}`
      : "Ответ ещё не сохранён",
    statusLabel:
      response?.status === "blocked"
        ? "Нужна другая форма ответа"
        : recalculationStatus === "started"
          ? "Кейс обновлён; анализ ожидает подтверждения"
          : recalculationStatus === "deferred"
            ? "Ответ сохранён; пересчёт отложен"
        : response
          ? "Ответ сохранён без пересчёта"
          : "Пока нет сохранённого ответа",
    recalculationState,
    revisionLabel: recalculationDelta
      ? `Ревизия ${recalculationDelta.previous_revision} → ${recalculationDelta.new_revision}`
      : recalculationStatus === "deferred"
        ? "Пересчёт отложен"
        : "Пересчёт не запускался",
    deltaRows: buildAdvisorDeltaRows(response ?? null),
    researchLabel: safeFounderText(
      response?.research_result?.summary_ru,
      "Публичный поиск не запускался.",
    ),
    nonBlocking: true,
  };
}

function buildAdvisorDeltaRows(
  response: AdvisorAnswerResponse | null,
): AdvisorAnswerPresentation["deltaRows"] {
  const delta = response?.recalculation_delta ?? null;
  if (!delta) {
    const value =
      response?.recalculation_status === "deferred"
        ? "Нет пересчёта"
        : response?.recalculation_status === "started"
          ? "Ожидает данных"
          : "Без изменений";
    return [
      {
        label: "Поля профиля",
        value,
        status: "Не обновлялись",
      },
    ];
  }
  const changedFields = summarizeCodes(delta.fields_changed, "ещё 1 поле", "ещё полей");
  const coreSign = delta.core_coverage_delta > 0 ? "+" : "";
  const recalculatedCalculations = summarizeCodes(
    delta.calculations_recalculated,
    "ещё 1 расчёт",
    "ещё расчётов",
  );
  const pendingCalculations = summarizeCodes(
    delta.calculations_pending,
    "ещё 1 расчёт ожидает отчёта",
    "ещё расчётов ожидают отчёта",
  );
  const calculations =
    delta.calculations_recalculated.length > 0 && delta.calculations_pending.length > 0
      ? `${recalculatedCalculations}; ожидает отчёта: ${pendingCalculations}`
      : delta.calculations_recalculated.length > 0
        ? recalculatedCalculations
        : delta.calculations_pending.length > 0
          ? `Ожидает отчёта: ${pendingCalculations}`
          : "Нет изменений";
  return [
    {
      label: "Поля профиля",
      value: changedFields,
      status:
        delta.fields_changed.length > 0
          ? "Обновлено из ответа"
          : "Новых полей нет",
    },
    {
      label: "Покрытие ядра",
      value: `${coreSign}${delta.core_coverage_delta}`,
      status: "Изменение после пересчёта",
    },
    {
      label: "Противоречия",
      value: `${delta.conflicts_resolved} закрыто, ${delta.conflicts_remaining} открыто`,
      status:
        delta.conflicts_resolved > 0
          ? "Сужено по ответу"
          : "Без закрытых конфликтов",
    },
    {
      label: "Расчёты",
      value: calculations,
      status:
        delta.calculations_pending.length > 0
          ? "Часть ожидает отчёта"
          : delta.calculations_recalculated.length > 0
            ? "Пересчитано"
            : "Не пересчитывались",
    },
  ];
}

export type AdvisorProposalPresentation = Readonly<{
  id: string;
  target: string;
  recommendation: string;
  rationale: string;
  expectedEffect: string;
  confidenceLabel: string;
  evidenceLabel: string;
  actions: readonly ["Принять", "Отклонить"];
}>;

export type AdvisorImprovementPresentation = Readonly<{
  heroTitle: string;
  versionLabel: string;
  decisionLabel: string;
  proposals: readonly AdvisorProposalPresentation[];
}>;

export function buildAdvisorImprovementPresentation(
  response: AdvisorImprovementsResponse | null,
  decision: AdvisorImprovementDecisionResponse | null = null,
): AdvisorImprovementPresentation {
  const version = decision?.new_version ?? response?.improvement_version ?? 1;
  const proposals = (response?.proposals ?? []).map(buildProposalPresentation);
  const acceptedVersionAdvanced =
    decision?.decision === "accepted" &&
    decision.new_version > decision.previous_version;
  return {
    heroTitle: acceptedVersionAdvanced
      ? `Проект улучшен — версия ${decision.new_version}`
      : `Улучшения готовы к выбору — версия предложений ${response?.improvement_version ?? 1}`,
    versionLabel: `Версия ${version}`,
    decisionLabel: decision
      ? decision.decision === "accepted"
        ? decision.recalculation_status === "started"
          ? "Изменение принято; кейс обновлён и ожидает подтверждения Gate 2"
          : decision.recalculation_status === "deferred"
            ? "Изменение принято; пересчёт кейса отложен"
            : "Изменение принято и добавлено в новую версию"
        : "Изменение отклонено, версия не изменилась"
      : "Выберите улучшения для следующей версии отчёта",
    proposals: proposals.slice(0, 6),
  };
}

function buildProposalPresentation(
  proposal: AdvisorImprovementProposal,
): AdvisorProposalPresentation {
  return {
    id: proposal.proposal_id,
    target: safeFounderText(proposal.target_area),
    recommendation: safeFounderText(proposal.recommendation_ru),
    rationale: safeFounderText(proposal.rationale_ru),
    expectedEffect: safeFounderText(proposal.expected_effect_ru),
    confidenceLabel: `${Math.round(proposal.confidence * 100)}% уверенности`,
    evidenceLabel:
      proposal.evidence_kinds.length > 0
        ? "Основано на сохранённых доказательствах кейса"
        : "Требует подтверждения",
    actions: ["Принять", "Отклонить"],
  };
}
