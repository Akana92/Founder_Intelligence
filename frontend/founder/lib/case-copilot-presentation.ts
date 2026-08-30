import type {
  CopilotActionAvailability,
  CopilotQuestionDescriptor,
  ProviderStatus,
  ResearchAcquisitionMode,
  RequestedResearchAcquisitionMode,
  ResearchJobResponse,
} from "./contracts.ts";
import type {
  PostCopilotMessageRequest,
  SaveAssumptionRequest,
} from "./founder-api-client.ts";
import {
  formatResearchAcquisitionMode,
  presentPublicResearchOutcome,
} from "./founder-readable-presentation.ts";

export type CaseCopilotAnswerType = "manual" | "file" | "public_research" | "skip";

export type CaseCopilotMetricCardLike = Readonly<{
  slot: string;
  status: string;
}>;

export type CaseCopilotAnswerMode = Readonly<{
  type: CaseCopilotAnswerType;
  enabled: boolean;
  reason: string;
}>;

export type CaseCopilotSubmitPayload = Readonly<{
  answerType: CaseCopilotAnswerType;
  fieldKey: string;
  manualValue: string;
  consentPublicResearch: boolean;
  expectedCaseRevision: number | null;
  acquisitionMode?: RequestedResearchAcquisitionMode;
}>;

export type CaseCopilotManualAssumptionFields = Readonly<{
  amount: string;
  scale: string;
  currency: string;
  periodMonth: string;
  declaredSource: string;
  rationale: string;
  validationPlan: string;
}>;

export type CaseCopilotManualAssumptionRequestInput =
  Partial<CaseCopilotManualAssumptionFields> &
  Readonly<{
    fieldKey: string;
    expectedRevision: number;
    questionDescriptor?: CopilotQuestionDescriptor | null;
    textValue?: string;
  }>;

export type CaseCopilotResearchJobPresentation = Readonly<{
  label: string;
  description: string;
  acquisitionMode: ResearchAcquisitionMode;
  modeLabel: string;
  citations: readonly string[];
  sourceRefCount: number;
  changedBlocks: readonly string[];
  invalidProviderContract: boolean;
  acceptedSourceSummaries: readonly Readonly<{
    sourceLabel: string;
    sourceUrl: string;
    sourceDomain: string | null;
    retrievalDate: string;
    acquisitionMode: ResearchAcquisitionMode;
    modeLabel: string;
    sourceRefCount: number;
  }>[];
  comparisonNote: string;
}>;

export type CaseCopilotQuestionInputPresentation = Readonly<{
  fieldKey: string;
  label: string;
  inputKind: "text" | "decimal" | "select" | "month";
  required: boolean;
  requiredLabel: string;
  placeholder: string;
}>;

export type CaseCopilotQuestionInputSchemaPresentation = Readonly<{
  kind: "text" | "money";
  fields: readonly CaseCopilotQuestionInputPresentation[];
  unlocksCopy: string;
}>;

export type PublicResearchPreRunCopy = Readonly<{
  actionHint: string;
  busyDescription: string;
  busyLabel: string;
  buttonLabel: string;
  consentLabel: string;
  description: string;
  tabLabel: string;
}>;

export type CaseCopilotPublicResearchModeChoice = Readonly<{
  mode: RequestedResearchAcquisitionMode;
  label: string;
  available: boolean;
  selectedByDefault: boolean;
  actionHint: string;
  description: string;
  buttonLabel: string;
  busyLabel: string;
  busyDescription: string;
  consentLabel: string;
  disabledReason: string | null;
}>;

const publicResearchPreRunCopyByProviderStatus: Record<
  ProviderStatus,
  PublicResearchPreRunCopy
> = {
  deterministic_offline_fixture: {
    actionHint: "Офлайн-демо начнётся только после явного согласия; интернет-запроса не будет.",
    busyDescription:
      "Готовится детерминированная офлайн-фикстура. Интернет-запрос не выполняется; ниже появятся демо-ориентиры и изменения метрик.",
    busyLabel: "Готовлю офлайн-демо…",
    buttonLabel: "Запустить офлайн-демо",
    consentLabel:
      "Разрешаю детерминированную офлайн-демо фикстуру для этого кейса. Интернет-запроса и отправки частных данных не будет.",
    description:
      "Детерминированная офлайн-демо фикстура не обращается к интернету и не подтверждает внутреннюю выручку, MRR, расход денег, остаток денег или другие данные компании. Эти значения нужны как ответ основателя или документ.",
    tabLabel: "Офлайн-демо",
  },
  configured: {
    actionHint: "Live-поиск начнётся только после явного согласия.",
    busyDescription:
      "Идёт live-поиск по публичному интернету. После завершения я покажу найденные ориентиры и изменения метрик ниже.",
    busyLabel: "Идёт live-поиск…",
    buttonLabel: "Запустить live-поиск",
    consentLabel:
      "Разрешаю live-поиск публичных ориентиров для этого кейса. Частные ответы и документы не отправляются.",
    description:
      "Live-поиск по публичному интернету не подтверждает внутреннюю выручку, MRR, расход денег, остаток денег или другие данные компании. Эти значения нужны как ответ основателя или документ. Поиск может добавить внешние рыночные ориентиры и пересчитать затронутые сценарные метрики.",
    tabLabel: "Live-поиск",
  },
  unavailable: {
    actionHint: "Live-провайдер не настроен; можно продолжить безопасно вручную или отложить запуск.",
    busyDescription:
      "Live-провайдер не настроен. Система фиксирует безопасный отложенный путь; интернет-запрос не выполняется.",
    busyLabel: "Фиксирую отложенный путь…",
    buttonLabel: "Продолжить без live-провайдера",
    consentLabel:
      "Понимаю, что live-провайдер не настроен. Частные ответы и документы не отправляются; можно продолжить вручную или отложить запуск.",
    description:
      "Live-провайдер публичного поиска не настроен. Интернет-запрос не выполняется; используйте безопасный ручной ответ, документ или отложите запуск до настройки провайдера.",
    tabLabel: "Без live-провайдера",
  },
};

const publicResearchModeOrder: readonly RequestedResearchAcquisitionMode[] = [
  "live_public_research",
  "deterministic_offline_fixture",
];

const publicResearchCopyByAcquisitionMode: Record<
  RequestedResearchAcquisitionMode,
  Omit<
    CaseCopilotPublicResearchModeChoice,
    "available" | "disabledReason" | "mode" | "selectedByDefault"
  >
> = {
  live_public_research: {
    label: "Онлайн-ресерч",
    actionHint: "Онлайн-ресерч начнётся только после явного согласия.",
    description:
      "Онлайн-ресерч отправляет только санитизированный публичный запрос к открытым источникам. Частные документы и ответы не отправляются в web search.",
    buttonLabel: "Запустить онлайн-ресерч",
    busyLabel: "Ищу публичные источники…",
    busyDescription:
      "Этапы: готовлю план, ищу публичные источники, пересчитываю сценарий, обновляю кейс.",
    consentLabel:
      "Разрешаю онлайн-ресерч: только санитизированный публичный запрос, без отправки частных документов и ответов основателя.",
  },
  deterministic_offline_fixture: {
    label: "Офлайн-демо",
    actionHint: "Офлайн-демо начнётся только после явного согласия; интернет-запроса не будет.",
    description:
      "Офлайн-демо работает без интернета на детерминированной демо-фикстуре. Оно не подтверждает частные факты компании.",
    buttonLabel: "Запустить офлайн-демо",
    busyLabel: "Готовлю офлайн-демо…",
    busyDescription:
      "Этапы: готовлю план, беру офлайн-демо ориентиры без интернета, пересчитываю сценарий, обновляю кейс.",
    consentLabel:
      "Разрешаю офлайн-демо для этого кейса: интернет не используется и частные документы не отправляются.",
  },
};

function isRequestedResearchAcquisitionMode(
  value: unknown,
): value is RequestedResearchAcquisitionMode {
  return (
    value === "live_public_research" ||
    value === "deterministic_offline_fixture"
  );
}

function actionStringArray(
  action: CopilotActionAvailability | null,
  key: string,
): readonly string[] {
  const value = action?.payload[key];
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? value
    : [];
}

function acquisitionModeDisabledReason(
  mode: RequestedResearchAcquisitionMode,
): string {
  if (mode === "live_public_research") {
    return "Онлайн-ресерч недоступен: провайдер публичного поиска не настроен.";
  }
  return "Офлайн-демо недоступно: детерминированная демо-фикстура не подключена.";
}

export function buildCaseCopilotPublicResearchModeChoices(
  researchAction: CopilotActionAvailability | null,
): readonly CaseCopilotPublicResearchModeChoice[] {
  const availableModes = new Set(
    actionStringArray(researchAction, "available_acquisition_modes").filter(
      isRequestedResearchAcquisitionMode,
    ),
  );
  const unavailableModes = new Set(
    actionStringArray(researchAction, "unavailable_acquisition_modes").filter(
      isRequestedResearchAcquisitionMode,
    ),
  );
  const defaultMode = isRequestedResearchAcquisitionMode(
    researchAction?.payload.default_acquisition_mode,
  )
    ? researchAction.payload.default_acquisition_mode
    : null;
  const selectedByDefault = availableModes.has("live_public_research")
    ? "live_public_research"
    : availableModes.has("deterministic_offline_fixture")
      ? "deterministic_offline_fixture"
      : defaultMode;

  return publicResearchModeOrder.map((mode) => {
    const declaredAvailable = availableModes.has(mode);
    const declaredUnavailable = unavailableModes.has(mode);
    const available =
      declaredAvailable ||
      (!declaredUnavailable && defaultMode === mode && availableModes.size === 0);
    return {
      mode,
      ...publicResearchCopyByAcquisitionMode[mode],
      available,
      selectedByDefault: selectedByDefault === mode && available,
      disabledReason: available ? null : acquisitionModeDisabledReason(mode),
    };
  });
}

export function defaultCaseCopilotPublicResearchMode(
  researchAction: CopilotActionAvailability | null,
): RequestedResearchAcquisitionMode {
  return (
    buildCaseCopilotPublicResearchModeChoices(researchAction).find(
      (choice) => choice.selectedByDefault,
    )?.mode ?? "deterministic_offline_fixture"
  );
}

export function presentPublicResearchPreRunCopy(
  providerStatus: ProviderStatus | null,
): PublicResearchPreRunCopy {
  return publicResearchPreRunCopyByProviderStatus[providerStatus ?? "unavailable"];
}

const changedBlockLabels: Readonly<Record<string, string>> = {
  public_benchmarks: "Публичные ориентиры",
  scenarios: "Сценарии",
};

const fieldKeyAliases: Readonly<Record<string, string>> = {
  monthly_recurring_revenue: "mrr",
  monthly_net_burn: "burn",
  net_burn: "burn",
};

function normalizeCaseCopilotFieldKey(fieldKey: string): string {
  const normalized = fieldKey.trim();
  return fieldKeyAliases[normalized] ?? normalized;
}

function emptyManualAssumptionFields(): CaseCopilotManualAssumptionFields {
  return {
    amount: "",
    scale: "",
    currency: "",
    periodMonth: "",
    declaredSource: "",
    rationale: "",
    validationPlan: "",
  };
}

function actionFor(
  actions: readonly CopilotActionAvailability[],
  action: CopilotActionAvailability["action"],
): CopilotActionAvailability | null {
  return actions.find((candidate) => candidate.action === action) ?? null;
}

function fieldKeyFromAction(action: CopilotActionAvailability | null): string {
  const value = action?.payload.field_key;
  return typeof value === "string" && value.trim()
    ? normalizeCaseCopilotFieldKey(value)
    : "next_question";
}

export function caseCopilotQuestionIdentity(
  questionDescriptor: CopilotQuestionDescriptor | null,
): string {
  if (questionDescriptor === null) return "legacy:null";
  const fieldKeys = questionDescriptor.input_schema.fields
    .map((field) => `${field.field_key}:${field.input_kind}:${field.required}`)
    .join(",");
  return [
    questionDescriptor.question_id,
    questionDescriptor.field_key,
    questionDescriptor.input_schema.kind,
    fieldKeys,
  ].join("|");
}

export function resetCaseCopilotManualDraftForQuestionChange(
  previousQuestionDescriptor: CopilotQuestionDescriptor | null,
  nextQuestionDescriptor: CopilotQuestionDescriptor | null,
  draft: CaseCopilotManualAssumptionFields,
): CaseCopilotManualAssumptionFields {
  if (
    caseCopilotQuestionIdentity(previousQuestionDescriptor) ===
    caseCopilotQuestionIdentity(nextQuestionDescriptor)
  ) {
    return draft;
  }
  return emptyManualAssumptionFields();
}

export function presentCaseCopilotQuestionInputSchema(
  questionDescriptor: CopilotQuestionDescriptor,
): CaseCopilotQuestionInputSchemaPresentation {
  return {
    kind: questionDescriptor.input_schema.kind,
    fields: questionDescriptor.input_schema.fields.map((field) => ({
      fieldKey: field.field_key,
      label: field.label,
      inputKind: field.input_kind,
      required: field.required,
      requiredLabel: field.required ? "обязательно" : "необязательно",
      placeholder: field.placeholder ?? "",
    })),
    unlocksCopy: questionDescriptor.unlocks_copy,
  };
}

export function deriveCaseCopilotResearchConsentScope({
  acquisitionMode,
  caseId,
  researchAction,
}: Readonly<{
  acquisitionMode?: RequestedResearchAcquisitionMode;
  caseId: string | null | undefined;
  researchAction: CopilotActionAvailability | null;
}>): string | null {
  const normalizedCaseId = typeof caseId === "string" ? caseId.trim() : "";
  const focus = researchAction?.payload.focus;
  const expectedCaseRevision = researchAction?.payload.expected_case_revision;
  if (
    !normalizedCaseId ||
    researchAction?.action !== "prepare_public_research" ||
    researchAction.status !== "requires_consent" ||
    typeof focus !== "string" ||
    !focus.trim() ||
    typeof expectedCaseRevision !== "number" ||
    !Number.isInteger(expectedCaseRevision) ||
    expectedCaseRevision < 1
  ) {
    return null;
  }
  const baseScope = `${normalizedCaseId}:${focus.trim()}:${expectedCaseRevision}`;
  return acquisitionMode ? `${baseScope}:${acquisitionMode}` : baseScope;
}

export function mergeCaseCopilotMetricCards<TCard extends CaseCopilotMetricCardLike>(
  baseCards: readonly TCard[],
  scenarioCards: readonly TCard[],
): readonly TCard[] {
  const scenarioBySlot = new Map(scenarioCards.map((card) => [card.slot, card]));
  return baseCards.map((card) => {
    if (card.status !== "needs") return card;
    return scenarioBySlot.get(card.slot) ?? card;
  });
}

export function deriveCaseCopilotAnswerModes({
  actions,
  busy = false,
  canPrepareResearch,
  canSubmitFact,
  canSubmitUnknown,
  hasDocumentHandler,
  manualDraft,
  consentPublicResearch,
}: Readonly<{
  actions: readonly CopilotActionAvailability[];
  busy?: boolean;
  canPrepareResearch: boolean;
  canSubmitFact: boolean;
  canSubmitUnknown: boolean;
  hasDocumentHandler: boolean;
  manualDraft: string;
  consentPublicResearch: boolean;
}>): readonly CaseCopilotAnswerMode[] {
  const factAction = actionFor(actions, "open_fact_input");
  const documentAction = actionFor(actions, "open_document_upload");
  const researchAction = actionFor(actions, "prepare_public_research");
  const modes: CaseCopilotAnswerMode[] = [];
  if (canSubmitFact && factAction) {
    modes.push({
      type: "manual",
      enabled:
        factAction.status === "requires_input" &&
        manualDraft.trim().length > 0 &&
        !busy,
      reason: factAction.reason ?? factAction.effect_preview,
    });
  }
  if (documentAction) {
    modes.push({
      type: "file",
      enabled: Boolean(hasDocumentHandler && documentAction?.status === "available" && !busy),
      reason: documentAction?.reason ?? documentAction?.effect_preview ?? "Case-document upload is not wired in this workspace.",
    });
  }
  if (canPrepareResearch && researchAction) {
    modes.push({
      type: "public_research",
      enabled: researchAction.status === "requires_consent" && consentPublicResearch && !busy,
      reason: researchAction.reason ?? researchAction.effect_preview,
    });
  }
  if (canSubmitUnknown && factAction?.status === "requires_input") {
    modes.push({
      type: "skip",
      enabled: !busy,
      reason: "Unknown will be sent as a Copilot thread reply, not saved as source_fact or a founder assumption.",
    });
  }
  return modes;
}

export function selectCaseCopilotAnswerType(
  modes: readonly CaseCopilotAnswerMode[],
  current: CaseCopilotAnswerType,
): CaseCopilotAnswerType | null {
  return modes.some((mode) => mode.type === current) ? current : modes[0]?.type ?? null;
}

export function buildCaseCopilotSubmitPayload({
  acquisitionMode,
  actions,
  answerType,
  manualDraft,
  consentPublicResearch,
}: Readonly<{
  acquisitionMode?: RequestedResearchAcquisitionMode;
  actions: readonly CopilotActionAvailability[];
  answerType: CaseCopilotAnswerType;
  manualDraft: string;
  consentPublicResearch: boolean;
}>): CaseCopilotSubmitPayload {
  const factAction = actionFor(actions, "open_fact_input");
  const researchAction = actionFor(actions, "prepare_public_research");
  const expectedCaseRevision = researchAction?.payload.expected_case_revision;
  const researchFocus = researchAction?.payload.focus;
  return {
    answerType,
    fieldKey: answerType === "public_research" && typeof researchFocus === "string"
      ? researchFocus
      : fieldKeyFromAction(factAction),
    manualValue: answerType === "manual" ? manualDraft.trim() : "unknown",
    consentPublicResearch,
    expectedCaseRevision: answerType === "public_research" && typeof expectedCaseRevision === "number"
      ? expectedCaseRevision
      : null,
    ...(answerType === "public_research" && acquisitionMode
      ? { acquisitionMode }
      : {}),
  };
}

export function caseCopilotSubmitFailureMessage(
  answerType: CaseCopilotAnswerType,
): string {
  if (answerType === "public_research") {
    return "Публичный поиск не удалось запустить. Посмотрите показанную причину и повторите запуск безопасно.";
  }
  if (answerType === "skip") {
    return "Не удалось отправить ответ «не знаю». Попробуйте ещё раз.";
  }
  if (answerType === "file") {
    return "Не удалось открыть загрузку документа. Попробуйте ещё раз.";
  }
  return "Не удалось сохранить ответ. Проверьте поле и попробуйте ещё раз.";
}

export function caseCopilotOperationFailureMessage(
  answerType: CaseCopilotAnswerType,
  error: unknown,
): string {
  if (answerType !== "public_research") {
    return answerType === "skip"
      ? "Не удалось отправить ответ «не знаю». Попробуйте ещё раз."
      : answerType === "file"
        ? "Не удалось открыть загрузку документа. Попробуйте ещё раз."
        : "Не удалось сохранить ответ. Черновик оставлен на месте.";
  }
  const code =
    typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
      ? error.code
      : null;
  if (code === "BUDGET_EXCEEDED") {
    return "Лимит онлайн-ресерча исчерпан. Новый OpenAI-запрос не выполнен. Используйте сохранённый публичный ресерч или повторите после увеличения бюджета.";
  }
  if (code === "provider_unconfigured") {
    return "Онлайн-ресерч пока недоступен: провайдер публичного поиска не настроен.";
  }
  if (code === "research_no_useful_result") {
    return "Онлайн-ресерч завершён, но безопасных публичных ориентиров для этого вопроса не найдено. Уточните вопрос или добавьте ответ вручную.";
  }
  return caseCopilotSubmitFailureMessage("public_research");
}

export function buildCaseCopilotResearchJobPresentation(
  job: ResearchJobResponse,
): CaseCopilotResearchJobPresentation {
  const outcome = presentPublicResearchOutcome({ job });

  return {
    label: outcome.title,
    description: outcome.description,
    acquisitionMode: job.acquisition_mode,
    modeLabel: formatResearchAcquisitionMode(job.acquisition_mode),
    citations: job.citations,
    sourceRefCount: job.source_refs.length,
    changedBlocks: job.changed_blocks.map((block) => changedBlockLabels[block] ?? block),
    invalidProviderContract: outcome.invalidProviderContract,
    acceptedSourceSummaries: job.accepted_entries.map((entry) => ({
      sourceLabel: entry.publisher,
      sourceUrl: entry.url,
      sourceDomain: publicDomainFromUrl(entry.url),
      retrievalDate: entry.retrieval_date,
      acquisitionMode: job.acquisition_mode,
      modeLabel: formatResearchAcquisitionMode(job.acquisition_mode),
      sourceRefCount: entry.source_refs.length,
    })),
    comparisonNote: "Это пересчёт сценария на публичном контексте, не факт компании.",
  };
}

function publicDomainFromUrl(value: string): string | null {
  try {
    return new URL(value).hostname || null;
  } catch {
    return null;
  }
}

export function isCaseCopilotManualAssumptionComplete(
  fields: CaseCopilotManualAssumptionFields,
  questionDescriptor: CopilotQuestionDescriptor | null = null,
): boolean {
  if (questionDescriptor !== null) {
    return questionDescriptor.input_schema.fields
      .filter((field) => field.required)
      .every((field) => manualAssumptionFieldValue(fields, field.field_key).trim().length > 0);
  }
  return Boolean(
    fields.amount.trim() &&
      fields.scale.trim() &&
      fields.currency.trim() &&
      fields.periodMonth.trim() &&
      fields.declaredSource.trim() &&
      fields.rationale.trim() &&
      fields.validationPlan.trim(),
  );
}

function manualAssumptionFieldValue(
  fields: CaseCopilotManualAssumptionFields,
  fieldKey: string,
): string {
  if (fieldKey === "value") return fields.amount;
  if (fieldKey === "amount") return fields.amount;
  if (fieldKey === "scale") return fields.scale;
  if (fieldKey === "currency") return fields.currency;
  if (fieldKey === "period") return fields.periodMonth;
  if (fieldKey === "declared_source") return fields.declaredSource;
  if (fieldKey === "rationale") return fields.rationale;
  if (fieldKey === "validation_plan") return fields.validationPlan;
  return "";
}

export function buildCaseCopilotManualAssumptionRequest({
  amount = "",
  currency = "",
  declaredSource = "",
  expectedRevision,
  fieldKey,
  periodMonth = "",
  questionDescriptor = null,
  rationale = "",
  scale = "",
  textValue,
  validationPlan = "",
}: CaseCopilotManualAssumptionRequestInput): SaveAssumptionRequest {
  if (questionDescriptor?.input_schema.kind === "text") {
    const requirementKey = normalizeCaseCopilotFieldKey(fieldKey);
    return {
      requirement_key: requirementKey,
      value: {
        kind: "text",
        value: (textValue ?? amount).trim(),
      },
      period: null,
      source: {
        kind: "founder_statement",
        declared_source: declaredSource.trim(),
        evidence_ref: null,
      },
      rationale: rationale.trim(),
      validation_plan: validationPlan.trim(),
      expected_case_revision: expectedRevision,
      idempotency_key: `copilot-assumption:${requirementKey}:rev:${expectedRevision}`,
    };
  }
  const requirementKey = normalizeCaseCopilotFieldKey(fieldKey);
  const periodField = questionDescriptor?.input_schema.fields.find((field) => field.field_key === "period") ?? null;
  const shouldSubmitPeriod = questionDescriptor === null || (periodField !== null && periodMonth.trim().length > 0);
  return {
    requirement_key: requirementKey,
    value: {
      kind: "money",
      amount: amount.trim(),
      scale: scale.trim(),
      currency: currency.trim(),
    },
    period: shouldSubmitPeriod
      ? {
          kind: "month",
          value: periodMonth.trim(),
          start: null,
          end: null,
        }
      : null,
    source: {
      kind: "founder_statement",
      declared_source: declaredSource.trim(),
      evidence_ref: null,
    },
    rationale: rationale.trim(),
    validation_plan: validationPlan.trim(),
    expected_case_revision: expectedRevision,
    idempotency_key: `copilot-assumption:${requirementKey}:rev:${expectedRevision}`,
  };
}

export function buildCaseCopilotUnknownMessageRequest({
  fieldKey,
  expectedRevision,
}: Readonly<{
  fieldKey: string;
  expectedRevision: number;
}>): PostCopilotMessageRequest {
  return {
    message: "unknown",
    page_context: "case-copilot",
    current_section: "scenario-question",
    expected_case_revision: expectedRevision,
    focus_key: fieldKey,
    idempotency_key: `copilot-unknown:${fieldKey}:rev:${expectedRevision}`,
  };
}
