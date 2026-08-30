import type {
  ApiErrorCode,
  CaseValueKind,
  CopilotActionKey,
  CopilotActionStatus,
  CopilotCoverageProjection,
  CopilotMessageRole,
  ResearchAcquisitionMode,
  ResearchBenchmarkEntryProjection,
  ResearchJobResponse,
  ScenarioKey,
  StartupScenarioMetric,
} from "./contracts.ts";
import type { ScenarioMetricComparisonValue } from "./scenario-presentation.ts";

const provenanceLabels: Record<CaseValueKind, string> = {
  source_fact: "Заявлено в документе",
  founder_statement: "Со слов основателя",
  public_benchmark: "Публичный ориентир",
  ai_scenario: "Сценарное допущение",
  deterministic_calculation: "Расчёт по формуле",
  contradiction: "Противоречие",
};

const scenarioLabels: Record<ScenarioKey, string> = {
  conservative: "Осторожный",
  base: "Базовый",
  optimistic: "Оптимистичный",
};

const metricLabels: Record<string, string> = {
  arr: "ARR — годовая регулярная выручка",
  cac: "CAC — стоимость привлечения клиента",
  cac_payback: "Окупаемость CAC",
  gross_margin: "Валовая маржа",
  ltv: "LTV — ценность клиента за всё время",
  ltv_cac: "Соотношение LTV и CAC",
  mrr: "MRR — ежемесячная регулярная выручка",
  net_burn: "Чистый расход денег",
  runway: "Запас времени до окончания денег",
};

const dependencyLabels: Record<string, string> = {
  acquisition_spend: "расходы на привлечение",
  acquired_customers: "привлечённые клиенты",
  arpa: "средняя выручка на клиента",
  cac: "стоимость привлечения клиента (CAC)",
  cash_balance: "остаток денег",
  cogs: "себестоимость",
  gross_margin: "валовая маржа",
  ltv: "ценность клиента (LTV)",
  mrr: "ежемесячная регулярная выручка (MRR)",
  monthly_price: "средний чек",
  monthly_operating_expenses: "ежемесячные операционные расходы",
  monthly_revenue: "ежемесячная выручка",
  monthly_recurring_revenue: "ежемесячная регулярная выручка",
  net_burn: "чистый расход денег",
  new_customers: "новые клиенты",
  paying_customers: "платящие клиенты",
  pricing_revenue_model: "модель выручки",
  public_comparable_companies: "публичные сопоставимые компании",
  public_pricing_page: "публичная страница с ценами",
  revenue: "выручка",
  churn: "отток клиентов",
};

const gapLabels: Record<string, string> = {
  acquisition_spend: "расходы на привлечение",
  acquired_customers: "привлечённые клиенты",
  arpa: "средняя выручка на клиента",
  cac: "стоимость привлечения клиента (CAC)",
  cash_balance: "остаток денег",
  cogs: "себестоимость",
  churn: "отток клиентов",
  gross_margin: "валовая маржа",
  ltv: "ценность клиента (LTV)",
  mrr: "ежемесячная регулярная выручка (MRR)",
  monthly_operating_expenses: "ежемесячные операционные расходы",
  monthly_price: "средний чек",
  monthly_revenue: "ежемесячная выручка",
  monthly_recurring_revenue: "ежемесячная регулярная выручка",
  net_burn: "чистый расход денег",
  new_customers: "новые клиенты",
  paying_customers: "число платящих клиентов",
  revenue: "выручка",
};

const actionLabels: Record<CopilotActionKey, string> = {
  open_fact_input: "Добавить данные",
  open_document_upload: "Загрузить документ",
  prepare_public_research: "Подготовить публичный поиск",
  explain_metric: "Объяснить показатель",
  navigate: "Перейти к разделу",
  prepare_asset: "Подготовить материал",
  review_improvements: "Посмотреть улучшения",
};

const actionStatusLabels: Record<CopilotActionStatus, string> = {
  available: "Готово",
  requires_input: "Нужны данные",
  requires_consent: "Нужно согласие",
  blocked: "Заблокировано",
};

const roleLabels: Record<CopilotMessageRole, string> = {
  system: "Системное сообщение",
  system_event: "Системное событие",
  user: "Пользователь",
  assistant: "Помощник по кейсу",
  tool: "Результат действия",
};

const knownCopilotQuestions: Readonly<Record<string, string>> = {
  "Provide founder-approved input for revenue.":
    "Укажите выручку, которую основатель готов использовать как ручной ввод для сценария.",
  "Which clinic role owns follow-up quality, and what non-financial proof shows the service can fit clinic operations safely?":
    "Кто в клинике отвечает за качество последующей работы с пациентами и какие нефинансовые доказательства показывают, что сервис можно безопасно встроить в работу клиники?",
};

const knownCopilotMessages: Readonly<Record<string, string>> = {
  "Case Copilot is ready with same-case facts and scenario boundaries.":
    "Помощник по кейсу готов: факты этого кейса и границы сценариев учтены раздельно.",
  "Accepted public_benchmark research updated scenario context.":
    "Принятый публичный ориентир обновил сценарный контекст.",
};

const founderStageLabels: Readonly<Record<string, string>> = {
  idea: "Идея",
};

const knownScenarioValidationPlans: Readonly<Record<string, string>> = {
  "Validate against billing export.": "Сверьте с выгрузкой биллинга.",
  "Validate billing export.": "Сверьте с выгрузкой биллинга.",
  "Validate against signed customers and invoices after launch.":
    "Сверьте прогноз с подписанными клиентами и выставленными счетами после запуска.",
  "Validate once MRR is evidenced for a stable month.":
    "Проверьте после подтверждения ежемесячной регулярной выручки (MRR) за стабильный репрезентативный месяц.",
  "Validate using invoices, cloud bills, support costs and recognized revenue.":
    "Сверьте счета, облачные расходы, затраты поддержки и признанную выручку за один период.",
  "Validate using bank, payroll, expense and revenue records.":
    "Сверьте банковские операции, фонд оплаты труда, расходы и выручку за один период.",
  "Validate using cash balance and monthly burn evidence.":
    "Сверьте текущий остаток денег и подтверждённый ежемесячный чистый расход.",
  "Validate using channel spend and customer acquisition records.":
    "Сверьте расходы по каналам с данными о привлечённых клиентах.",
  "Validate using cohort retention and revenue evidence.":
    "Сверьте расчёт с когортным удержанием и подтверждённой выручкой.",
  "Validate after LTV and CAC are independently evidenced.":
    "Проверьте после независимого подтверждения LTV и CAC.",
  "Validate using CAC, ARPA and gross margin evidence.":
    "Сверьте CAC, среднюю выручку на клиента и валовую маржу по одному сегменту.",
};

const knownScenarioConfirmationGuidance: Readonly<Record<string, string>> = {
  "Billing export with paid customer count.":
    "Выгрузка биллинга с числом платящих клиентов.",
  "Signed paid customers and invoices for the forecast month.":
    "Подписанные платящие клиенты и счета за прогнозный месяц.",
  "A verified MRR source fact for a representative month.":
    "Подтверждённый источник ежемесячной регулярной выручки (MRR) за репрезентативный месяц.",
  "Recognized revenue and cost-of-goods evidence for the same period.":
    "Подтверждённые выручка и себестоимость за один и тот же период.",
  "Monthly revenue and expense source facts for the same period.":
    "Подтверждённые ежемесячные выручка и расходы за один период.",
  "A current cash balance and positive net burn source fact.":
    "Подтверждённые текущий остаток денег и положительный чистый расход за месяц.",
  "Attributed acquisition spend and acquired customer counts.":
    "Распределённые расходы на привлечение и подтверждённое число новых клиентов.",
  "Observed cohort churn or a cited comparable churn benchmark.":
    "Наблюдаемый когортный отток или публичный ориентир с указанным источником.",
  "Eligible LTV and CAC calculations for the same customer segment.":
    "Сопоставимые расчёты LTV и CAC для одного клиентского сегмента.",
  "Eligible CAC, ARPA and gross margin for the same segment.":
    "Подтверждённые CAC, средняя выручка на клиента и валовая маржа для одного сегмента.",
};

const knownPublicBenchmarkFormulas: Readonly<Record<string, string>> = {
  "reported public kzt monthly pricing range.":
    "Диапазон взят с публичной страницы цен.",
  "public benchmark range": "Диапазон взят из публичного ориентира.",
};

const knownPublicBenchmarkValidationPlans: Readonly<Record<string, string>> = {
  "use only as external context until founder-specific evidence exists.":
    "Используйте только как внешний ориентир, пока он не подтверждён данными конкретного кейса.",
};

const knownPublicBenchmarkDependencies: Readonly<Record<string, string>> = {
  "plan scope and included integrations vary by tier.":
    "состав тарифа и интеграции зависят от уровня плана",
  "pricing varies by plan and team-size selector.":
    "цена зависит от плана и размера команды",
  "cloud price is per user; pro price is per company.":
    "часть тарифов считается за пользователя, часть — за компанию",
};

const coverageStatusLabels: Record<string, string> = {
  complete: "Полное покрытие",
  partial: "Частичное покрытие",
  draft: "Черновое покрытие",
};

const formulaLabels: Record<string, string> = {
  mrr: "MRR = средний чек × платящие клиенты",
  arr: "ARR = MRR × 12",
  cac: "CAC = расходы на привлечение ÷ новые клиенты",
  cac_payback: "Окупаемость CAC = CAC ÷ (средняя выручка на клиента × валовая маржа)",
  gross_margin: "Валовая маржа = (выручка − себестоимость) ÷ выручка",
  ltv: "LTV = средний чек × валовая маржа ÷ отток клиентов",
  ltv_cac: "Соотношение LTV и CAC = LTV ÷ CAC",
  net_burn: "Чистый расход денег = операционные расходы − выручка",
  runway: "Запас времени = остаток денег ÷ чистый расход денег",
};

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;
const numberFormatter = new Intl.NumberFormat("ru-RU", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function formatCount(count: number, one: string, few: string, many: string): string {
  const normalized = Math.abs(count);
  const lastTwo = normalized % 100;
  const last = normalized % 10;
  const noun = lastTwo >= 11 && lastTwo <= 14
    ? many
    : last === 1
      ? one
      : last >= 2 && last <= 4
        ? few
        : many;
  return `${count} ${noun}`;
}

export type FounderScenarioMetricPresentation = Readonly<{
  title: string;
  value: string;
  trustStatement: string;
  formula: string;
  dependencies: readonly string[];
  gaps: readonly string[];
  sourceLabel: string;
  sourceReferences: readonly string[];
  validationPlan: string;
  confirmationGuidance: string;
}>;

export type PublicBenchmarkEntryPresentation = Readonly<{
  title: string;
  provenanceLabel: string;
  sourceLabel: string;
  sourceUrl: string;
  dateLabel: string;
  rangeLabel: string;
  formula: string;
  dependencies: readonly string[];
  validationPlan: string;
}>;

export type PublicResearchOutcomePresentation = Readonly<{
  title: string;
  description: string;
  recoveryLabel: string;
  invalidProviderContract: boolean;
}>;

const researchAcquisitionModeLabels: Record<ResearchAcquisitionMode, string> = {
  deterministic_offline_fixture: "Детерминированная офлайн-фикстура",
  live_public_research: "Live-поиск по публичному интернету",
  provider_unconfigured: "Провайдер live-поиска не настроен",
};

export function formatProvenance(value: CaseValueKind): string {
  return provenanceLabels[value];
}

export function formatResearchAcquisitionMode(value: ResearchAcquisitionMode): string {
  return researchAcquisitionModeLabels[value];
}

export function presentPublicResearchOutcome({
  errorCode,
  job,
}: Readonly<{
  errorCode?: ApiErrorCode | null;
  job?: ResearchJobResponse | null;
}>): PublicResearchOutcomePresentation {
  if (errorCode === "public_research_consent_required") {
    return {
      title: "Публичный поиск не запущен: нужно согласие",
      description:
        "Отметьте согласие на поиск по открытым источникам. Внутренние метрики, документы и локальные файлы не отправляются.",
      recoveryLabel: "Дать согласие и запустить заново",
      invalidProviderContract: false,
    };
  }

  const hasInvalidProviderContract = Boolean(
    job?.rejected_entries.some((entry) => entry.reason_code === "invalid_benchmark_entry"),
  );
  const sourceCount = job?.citations.length ?? 0;
  const acquisitionMode = job?.acquisition_mode ?? "provider_unconfigured";
  const changedBlocks = new Set(job?.changed_blocks ?? []);
  const changedBlockCopy =
    changedBlocks.has("public_benchmarks") && changedBlocks.has("scenarios")
      ? "обновлены публичные ориентиры и сценарии"
      : changedBlocks.has("public_benchmarks")
        ? "обновлены публичные ориентиры"
        : changedBlocks.has("scenarios")
          ? "обновлены сценарии"
          : "данные кейса не изменились";

  if (
    (job?.status === "completed" || job?.status === "partial") &&
    job.reason === "cached_completed_research"
  ) {
    return {
      title: "Сохранённый онлайн-ресерч использован",
      description: `${formatCount(sourceCount, "источник", "источника", "источников")}; новый интернет- и OpenAI-запрос не выполнялся. Сохранённый публичный контекст использован повторно; это не факты компании.`,
      recoveryLabel: "Продолжить с сохранённым публичным контекстом",
      invalidProviderContract: hasInvalidProviderContract,
    };
  }

  if (job?.status === "completed") {
    if (acquisitionMode === "deterministic_offline_fixture") {
      return {
        title: "Офлайн-демо ориентир принят",
        description: `${formatCount(sourceCount, "источник", "источника", "источников")}; ${changedBlockCopy}. Это детерминированная офлайн-фикстура без интернет-запроса, не факты компании.`,
        recoveryLabel: "Использовать как демо-ориентир сценария",
        invalidProviderContract: hasInvalidProviderContract,
      };
    }
    if (acquisitionMode === "provider_unconfigured") {
      return {
        title: "Провайдер публичного поиска не настроен",
        description:
          "Live-провайдер не настроен; используйте безопасный ручной ввод или отложите запуск. Данные кейса и сценарии не изменились.",
        recoveryLabel: "Продолжить вручную или повторить после настройки",
        invalidProviderContract: hasInvalidProviderContract,
      };
    }
    return {
      title: "Live-поиск по публичному интернету принят",
      description: `${formatCount(sourceCount, "источник", "источника", "источников")}; ${changedBlockCopy}. Это live public Internet research: публичный контекст и сценарные изменения, не факты компании.`,
      recoveryLabel: "Использовать как ориентир сценария",
      invalidProviderContract: hasInvalidProviderContract,
    };
  }
  if (job?.status === "partial") {
    if (acquisitionMode === "deterministic_offline_fixture") {
      return {
        title: "Офлайн-демо ориентир принят частично",
        description: `${formatCount(sourceCount, "источник", "источника", "источников")}; ${changedBlockCopy}. Часть строк отброшена; это детерминированная офлайн-фикстура без интернет-запроса, не факты компании.`,
        recoveryLabel: "Проверить демо-ориентиры",
        invalidProviderContract: hasInvalidProviderContract,
      };
    }
    if (acquisitionMode === "provider_unconfigured") {
      return {
        title: "Провайдер публичного поиска не настроен",
        description:
          "Live-провайдер не настроен; используйте безопасный ручной ввод или отложите запуск. Данные кейса и сценарии не изменились.",
        recoveryLabel: "Продолжить вручную или повторить после настройки",
        invalidProviderContract: hasInvalidProviderContract,
      };
    }
    return {
      title: "Live-поиск по публичному интернету принят частично",
      description: `${formatCount(sourceCount, "источник", "источника", "источников")}; ${changedBlockCopy}. Неподходящие строки отброшены; это live public Internet research и не факты компании.`,
      recoveryLabel: "Проверить принятые источники",
      invalidProviderContract: hasInvalidProviderContract,
    };
  }
  if (hasInvalidProviderContract) {
    return {
      title: "Провайдер вернул неподходящий формат ориентира",
      description:
        "Источник найден, но его числовой ориентир не прошёл контракт. Данные кейса не изменились; можно повторить поиск позже.",
      recoveryLabel: "Повторить поиск позже",
      invalidProviderContract: true,
    };
  }

  if (job?.reason === "provider_unconfigured") {
    return {
      title: "Провайдер публичного поиска не настроен",
      description:
        "Live-провайдер не настроен; используйте безопасный ручной ввод или отложите запуск. Данные кейса и сценарии не изменились.",
      recoveryLabel: "Продолжить вручную или повторить после настройки",
      invalidProviderContract: false,
    };
  }
  if (job?.reason === "stale_research_plan") {
    return {
      title: "План публичного поиска устарел",
      description: "Обновите вопрос или профиль и подготовьте новый план для текущей версии кейса.",
      recoveryLabel: "Подготовить новый план",
      invalidProviderContract: false,
    };
  }
  if (job?.reason === "BUDGET_EXCEEDED") {
    return {
      title: "Лимит онлайн-ресерча исчерпан",
      description:
        "Новый OpenAI-запрос не выполнен из-за лимита. Используйте сохранённый публичный ресерч или повторите после увеличения бюджета; внутренние факты компании не менялись.",
      recoveryLabel: "Использовать сохранённый результат",
      invalidProviderContract: false,
    };
  }
  if (job?.reason === "provider_failed" || job?.status === "failed") {
    return {
      title: "Публичный поиск завершился ошибкой провайдера",
      description:
        "Повторите запуск позже. Согласие относится только к одному запуску; внутренние факты компании не менялись.",
      recoveryLabel: "Повторить запуск",
      invalidProviderContract: false,
    };
  }
  if (job?.reason === "no_eligible_public_benchmarks") {
    return {
      title: "Публичный ориентир не принят",
      description:
        "Открытые источники не дали безопасного ориентира для сценария; внутренние факты компании остались без изменений.",
      recoveryLabel: "Уточнить вопрос и повторить",
      invalidProviderContract: false,
    };
  }
  if (job?.reason === "research_interrupted") {
    return {
      title: "Публичный поиск был прерван",
      description:
        "Перезапустите поиск после проверки текущей версии кейса. Прерванный запуск не менял факты и сценарии.",
      recoveryLabel: "Перезапустить поиск",
      invalidProviderContract: false,
    };
  }
  if (job?.status === "running" || job?.status === "queued") {
    if (acquisitionMode === "deterministic_offline_fixture") {
      return {
        title: "Готовится офлайн-демо без интернет-запроса",
        description:
          "Детерминированная офлайн-фикстура выполняется без обращения к интернету; внутренние значения компании не отправляются и не подменяются.",
        recoveryLabel: "Дождаться результата",
        invalidProviderContract: false,
      };
    }
    if (acquisitionMode === "provider_unconfigured") {
      return {
        title: "Провайдер live-поиска не настроен",
        description:
          "Live-провайдер не настроен; запуск безопасно отложен до ручного ввода или настройки провайдера.",
        recoveryLabel: "Продолжить вручную или повторить после настройки",
        invalidProviderContract: false,
      };
    }
    return {
      title: "Идёт live-поиск по публичному интернету",
      description: "Live public Internet research выполняется. Внутренние значения компании не отправляются и не подменяются.",
      recoveryLabel: "Дождаться результата",
      invalidProviderContract: false,
    };
  }
  return {
    title: "Исследование отложено",
    description: "Публичный поиск не изменил данные кейса. Подготовьте новый запуск для текущей версии.",
    recoveryLabel: "Подготовить новый запуск",
    invalidProviderContract: false,
  };
}

export function formatScenario(value: ScenarioKey): string {
  return scenarioLabels[value];
}

export function formatMetric(value: string): string {
  return metricLabels[value] ?? "Показатель сценария";
}

export function formatDependency(value: string): string {
  if (uuidPattern.test(value)) return "связанный входной показатель";
  const normalized = value.trim().toLocaleLowerCase("en-US").replace(/[\s-]+/gu, "_");
  return dependencyLabels[normalized] ?? "связанный входной показатель";
}

function formatDependencies(values: readonly string[]): readonly string[] {
  const readable = values.map(formatDependency);
  const opaqueLabel = "связанный входной показатель";
  const opaqueCount = readable.filter((value) => value === opaqueLabel).length;
  const known = [...new Set(readable.filter((value) => value !== opaqueLabel))];

  if (opaqueCount === 0) return known;
  if (opaqueCount === 1) return [...known, opaqueLabel];

  const modulo100 = opaqueCount % 100;
  const modulo10 = opaqueCount % 10;
  const suffix = modulo100 >= 11 && modulo100 <= 14
    ? "связанных входных показателей"
    : modulo10 >= 2 && modulo10 <= 4
      ? "связанных входных показателя"
      : "связанных входных показателей";
  return [...known, `${opaqueCount} ${suffix}`];
}

export function formatGap(value: string): string {
  const key = value.replace(/^input\.missing:|^missing:/u, "");
  return `Не хватает данных: ${gapLabels[key] ?? "входных показателей"}`;
}

export function formatCopilotAction(value: CopilotActionKey): string {
  return actionLabels[value];
}

export function formatCopilotActionStatus(value: CopilotActionStatus): string {
  return actionStatusLabels[value];
}

export function formatCopilotRole(value: CopilotMessageRole): string {
  return roleLabels[value];
}

export function formatCopilotQuestion(value: string): string {
  const normalized = value.trim();
  const knownQuestion = knownCopilotQuestions[normalized];
  if (knownQuestion) return knownQuestion;
  const founderApprovedInput =
    /^Provide founder-approved input for ([a-z][a-z0-9]*(?:_[a-z0-9]+)*)\.$/u.exec(normalized);
  if (founderApprovedInput?.[1]) {
    return `Укажите показатель «${formatDependency(founderApprovedInput[1])}». Основатель готов использовать его как ручной ввод для сценария.`;
  }
  return value;
}

export function formatCopilotMessage(value: string): string {
  const normalized = value.trim();
  const knownMessage = knownCopilotMessages[normalized];
  if (knownMessage) return knownMessage;
  const savedFounderAssumption = /^Saved founder_statement assumption for ([a-z][a-z0-9_]*)\.$/u.exec(normalized);
  if (savedFounderAssumption?.[1]) {
    return `Значение со слов основателя сохранено для показателя «${formatDependency(savedFounderAssumption[1])}».`;
  }
  const savedSourceFact = /^Saved source_fact evidence for ([a-z][a-z0-9_]*)\.$/u.exec(normalized);
  if (savedSourceFact?.[1]) {
    return `Заявленное в документе значение сохранено для показателя «${formatDependency(savedSourceFact[1])}».`;
  }
  return value;
}

export function formatCopilotThreadMessage(
  role: CopilotMessageRole,
  value: string,
): string {
  if (role !== "system" && role !== "system_event" && role !== "tool") return value;
  return formatCopilotMessage(value)
    .replace(/source_fact/gu, "заявлено в документе")
    .replace(/founder_statement/gu, "ответ основателя")
    .replace(/public_benchmark/gu, "публичный ориентир")
    .replace(/ai_scenario/gu, "сценарное допущение")
    .replace(/deterministic_calculation/gu, "расчёт по формуле")
    .replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/giu, "внутренняя ссылка")
    .replace(/\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\b/giu, "связанный показатель");
}

export function formatFounderStage(value: string): string {
  const normalized = value.trim();
  return founderStageLabels[normalized] ?? value;
}

function generatedGuidanceFallback(value: string, fallback: string): string {
  const normalized = value.trim();
  if (!normalized) return fallback;
  return normalized;
}

export function formatScenarioValidationPlan(value: string): string {
  const normalized = value.trim();
  return knownScenarioValidationPlans[normalized]
    ?? generatedGuidanceFallback(value, "Сверьте показатель с первичным источником за сопоставимый период.");
}

export function formatScenarioConfirmationGuidance(value: string): string {
  const normalized = value.trim();
  return knownScenarioConfirmationGuidance[normalized]
    ?? generatedGuidanceFallback(value, "Подтверждённый первичный источник за сопоставимый период.");
}

export function formatCoverage(value: CopilotCoverageProjection | null): string {
  if (!value) return "Покрытие пока не рассчитано";
  const status = coverageStatusLabels[value.status] ?? "Покрытие требует проверки";
  if (value.source_fact_count === null || value.accepted_input_count === null) {
    return `${status}: показатели пока не рассчитаны`;
  }
  const sourceFacts = value.source_fact_count;
  const acceptedInputs = value.accepted_input_count;
  return `${status}: фактов — ${sourceFacts}, ответов — ${acceptedInputs}`;
}

function compactNumber(value: string): string | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return numberFormatter.format(parsed).replace(/[\u00a0\u202f]/gu, " ");
}

function currencySuffix(unit: string): string {
  if (unit.startsWith("KZT")) return " ₸";
  if (unit.startsWith("USD")) return " $";
  if (unit.startsWith("EUR")) return " €";
  if (unit === "month" || unit === "months") return " мес.";
  if (unit === "ratio") return " доля";
  return unit ? ` ${unit}` : "";
}

function formatRussianDate(value: string): string {
  const [year, month, day] = value.split("-");
  if (!year || !month || !day) return value;
  return `${day}.${month}.${year}`;
}

function publicBenchmarkUnitSuffix(unit: string): string {
  if (unit.startsWith("KZT")) return " ₸";
  if (unit.startsWith("USD")) return " $";
  if (unit.startsWith("EUR")) return " €";
  return unit ? ` ${unit}` : "";
}

function publicBenchmarkPeriodSuffix(period: string): string {
  if (period === "month") return " в месяц";
  if (period === "year") return " в год";
  return period ? ` за период: ${period}` : "";
}

function formatPublicBenchmarkRange(entry: ResearchBenchmarkEntryProjection): string {
  if (entry.value) {
    const exact = compactNumber(entry.value);
    return `${exact ?? entry.value}${publicBenchmarkUnitSuffix(entry.unit)}${publicBenchmarkPeriodSuffix(entry.period)}`;
  }
  const low = entry.range.low ? compactNumber(entry.range.low) : null;
  const high = entry.range.high ? compactNumber(entry.range.high) : null;
  const suffix = `${publicBenchmarkUnitSuffix(entry.unit)}${publicBenchmarkPeriodSuffix(entry.period)}`;
  if (low && high) {
    const lowParts = /^(.*) (тыс\.?|млн|млрд)$/u.exec(low);
    const highParts = /^(.*) (тыс\.?|млн|млрд)$/u.exec(high);
    if (lowParts?.[2] && lowParts[2] === highParts?.[2]) {
      return `${lowParts[1]}–${highParts?.[1]} ${lowParts[2]}${suffix}`;
    }
    return `${low}–${high}${suffix}`;
  }
  if (low) return `от ${low}${suffix}`;
  if (high) return `до ${high}${suffix}`;
  return "Диапазон не указан";
}

function formatPublicBenchmarkFormula(value: string): string {
  const normalized = value.trim().toLocaleLowerCase("en-US");
  if (/^published monthly .+ plan prices?/u.test(normalized)) {
    return "Диапазон взят из опубликованных месячных тарифов; валюта и период не пересчитывались.";
  }
  return knownPublicBenchmarkFormulas[normalized] ?? formatCopilotThreadMessage("tool", value);
}

function formatPublicBenchmarkValidationPlan(value: string): string {
  const normalized = value.trim().toLocaleLowerCase("en-US");
  if (knownPublicBenchmarkValidationPlans[normalized]) {
    return knownPublicBenchmarkValidationPlans[normalized];
  }
  if (normalized.includes("external context") || normalized.includes("founder-specific evidence")) {
    return "Проверьте, подходит ли этот внешний ориентир к сегменту, географии и модели цены конкретного кейса.";
  }
  return formatCopilotThreadMessage("tool", value);
}

function formatPublicBenchmarkDependency(value: string): string {
  const normalized = value.trim().toLocaleLowerCase("en-US");
  if (knownPublicBenchmarkDependencies[normalized]) {
    return knownPublicBenchmarkDependencies[normalized];
  }
  return formatDependency(value);
}

export function presentPublicBenchmarkEntry(
  entry: ResearchBenchmarkEntryProjection,
): PublicBenchmarkEntryPresentation {
  return {
    title: formatDependency(entry.input_key),
    provenanceLabel: "Публичный ориентир, не факт из ваших документов",
    sourceLabel: entry.publisher,
    sourceUrl: entry.url,
    dateLabel: entry.publication_date
      ? `Опубликовано ${formatRussianDate(entry.publication_date)}`
      : `Дата публикации не указана; источник проверен ${formatRussianDate(entry.retrieval_date)}`,
    rangeLabel: formatPublicBenchmarkRange(entry),
    formula: formatPublicBenchmarkFormula(entry.formula),
    dependencies: [...new Set(entry.dependencies.map(formatPublicBenchmarkDependency))],
    validationPlan: formatPublicBenchmarkValidationPlan(entry.validation_plan),
  };
}

export function formatScenarioMetricValue(metric: StartupScenarioMetric): string {
  if (!metric.value_range) {
    return metric.gaps[0] ? formatGap(metric.gaps[0]) : "Нужна проверка данных";
  }
  const lower = compactNumber(metric.value_range.lower);
  const upper = compactNumber(metric.value_range.upper);
  if (!lower || !upper) return "Нужна проверка данных";
  const lowerParts = /^(.*) (тыс|млн|млрд)$/u.exec(lower);
  const upperParts = /^(.*) (тыс|млн|млрд)$/u.exec(upper);
  if (lowerParts?.[2] && lowerParts[2] === upperParts?.[2]) {
    return `${lowerParts[1]}–${upperParts?.[1]} ${lowerParts[2]}${currencySuffix(metric.unit)}`;
  }
  return `${lower}–${upper}${currencySuffix(metric.unit)}`;
}

export function formatScenarioComparisonValue(value: ScenarioMetricComparisonValue): string {
  if (!value.valueRange) {
    return value.gaps[0] ? formatGap(value.gaps[0]) : "Нужны данные";
  }
  const lower = compactNumber(value.valueRange.lower);
  const upper = compactNumber(value.valueRange.upper);
  if (!lower || !upper) return "Нужны данные";
  const lowerParts = /^(.*) (тыс|млн|млрд)$/u.exec(lower);
  const upperParts = /^(.*) (тыс|млн|млрд)$/u.exec(upper);
  if (lowerParts?.[2] && lowerParts[2] === upperParts?.[2]) {
    return `${lowerParts[1]}–${upperParts?.[1]} ${lowerParts[2]}${currencySuffix(value.unit)}`;
  }
  return `${lower}–${upper}${currencySuffix(value.unit)}`;
}

export function presentScenarioMetric(metric: StartupScenarioMetric): FounderScenarioMetricPresentation {
  return {
    title: formatMetric(metric.metric_key),
    value: formatScenarioMetricValue(metric),
    trustStatement: formatProvenance(metric.provenance),
    formula: formulaLabels[metric.formula_key]
      ?? metric.formula_description.trim()
      ?? "Расчёт по связанным входным данным",
    dependencies: formatDependencies(metric.dependency_refs),
    gaps: metric.gaps.map(formatGap),
    sourceLabel: metric.source_refs.length === 1 ? "1 источник" : `${metric.source_refs.length} источников`,
    sourceReferences: metric.source_refs.map((_, index) => `Источник ${index + 1}`),
    validationPlan: formatScenarioValidationPlan(metric.validation_plan),
    confirmationGuidance: formatScenarioConfirmationGuidance(metric.what_would_confirm),
  };
}
