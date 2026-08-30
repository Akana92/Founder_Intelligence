"use client";

import { CheckCircle2, FilePlus2, Search, XCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  CaseMutationFieldError,
  CopilotActionAvailability,
  CopilotQuestionDescriptor,
  ProviderStatus,
  RequestedResearchAcquisitionMode,
} from "@/lib/contracts";
import {
  buildCaseCopilotPublicResearchModeChoices,
  buildCaseCopilotSubmitPayload,
  caseCopilotOperationFailureMessage,
  caseCopilotSubmitFailureMessage,
  caseCopilotQuestionIdentity,
  defaultCaseCopilotPublicResearchMode,
  deriveCaseCopilotResearchConsentScope,
  deriveCaseCopilotAnswerModes,
  isCaseCopilotManualAssumptionComplete,
  presentPublicResearchPreRunCopy,
  presentCaseCopilotQuestionInputSchema,
  resetCaseCopilotManualDraftForQuestionChange,
  selectCaseCopilotAnswerType,
} from "@/lib/case-copilot-presentation";
import {
  formatCopilotActionStatus,
  formatCopilotQuestion,
  formatDependency,
} from "@/lib/founder-readable-presentation";
import { presentCaseCopilotNoActionState } from "./founder-task-b-presentation";

import styles from "./case-copilot-panel.module.css";

export type CaseQuestionAnswerType = "manual" | "file" | "public_research" | "skip";

export type CaseQuestionSubmitInput = Readonly<{
  answerType: CaseQuestionAnswerType;
  fieldKey: string;
  manualValue: string;
  consentPublicResearch: boolean;
  expectedCaseRevision?: number | null;
  acquisitionMode?: RequestedResearchAcquisitionMode;
  amount: string;
  scale: string;
  currency: string;
  periodMonth: string;
  declaredSource: string;
  rationale: string;
  validationPlan: string;
  questionDescriptor: CopilotQuestionDescriptor | null;
}>;

type AnswerMode = Readonly<{
  type: CaseQuestionAnswerType;
  label: string;
}>;
export type CaseQuestionCardProps = Readonly<{
  actions: readonly CopilotActionAvailability[];
  busy?: boolean;
  canPrepareResearch?: boolean;
  canSubmitFact?: boolean;
  canSubmitUnknown?: boolean;
  caseId: string | null;
  preferredAnswerType?: CaseQuestionAnswerType;
  question: string | null;
  questionDescriptor?: CopilotQuestionDescriptor | null;
  validationErrors?: readonly CaseMutationFieldError[];
  onSubmit?: (input: CaseQuestionSubmitInput) => Promise<boolean> | boolean;
  onDocumentRequested?: () => void;
  providerStatus?: ProviderStatus | null;
}>;

function actionFor(
  actions: readonly CopilotActionAvailability[],
  action: CopilotActionAvailability["action"],
): CopilotActionAvailability | null {
  return actions.find((candidate) => candidate.action === action) ?? null;
}

function actionReason(action: CopilotActionAvailability | null, fallback: string): string {
  if (!action) return fallback;
  if (action.status === "available") return fallback;
  return `${formatCopilotActionStatus(action.status)}. ${fallback}`;
}

function validationMessage(message: string): string {
  return /[А-Яа-яЁё]/u.test(message)
    ? message
    : "Проверьте значение и формат поля.";
}

function actionAvailable(action: CopilotActionAvailability | null): boolean {
  return Boolean(action && action.status === "available");
}

export function CaseQuestionCard({
  actions,
  busy = false,
  canPrepareResearch: canPrepareResearchProp,
  canSubmitFact: canSubmitFactProp,
  canSubmitUnknown: canSubmitUnknownProp,
  caseId,
  onDocumentRequested,
  onSubmit,
  preferredAnswerType,
  providerStatus = null,
  question,
  questionDescriptor = null,
  validationErrors = [],
}: CaseQuestionCardProps) {
  const factAction = actionFor(actions, "open_fact_input");
  const factActionPayload =
    factAction?.payload && typeof factAction.payload === "object"
      ? (factAction.payload as Record<string, unknown>)
      : {};
  const factFieldKey =
    typeof factActionPayload.field_key === "string"
      ? factActionPayload.field_key.trim()
      : "";
  const documentAction = actionFor(actions, "open_document_upload");
  const researchAction = actionFor(actions, "prepare_public_research");
  const [answerType, setAnswerType] = useState<CaseQuestionAnswerType>(preferredAnswerType ?? "manual");
  const [manualAmount, setManualAmount] = useState("");
  const [manualScale, setManualScale] = useState("");
  const [manualCurrency, setManualCurrency] = useState("");
  const [manualPeriodMonth, setManualPeriodMonth] = useState("");
  const [manualDeclaredSource, setManualDeclaredSource] = useState("");
  const [manualRationale, setManualRationale] = useState("");
  const [manualValidationPlan, setManualValidationPlan] = useState("");
  const [consentedResearchScope, setConsentedResearchScope] = useState<string | null>(null);
  const [selectedResearchAcquisitionMode, setSelectedResearchAcquisitionMode] =
    useState<RequestedResearchAcquisitionMode | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const questionIdentity = caseCopilotQuestionIdentity(questionDescriptor);
  const previousQuestionDescriptor = useRef<CopilotQuestionDescriptor | null>(questionDescriptor);
  const researchModeChoices = useMemo(
    () => buildCaseCopilotPublicResearchModeChoices(researchAction),
    [researchAction],
  );
  const effectiveResearchAcquisitionMode =
    selectedResearchAcquisitionMode &&
    researchModeChoices.some((choice) => choice.mode === selectedResearchAcquisitionMode && choice.available)
      ? selectedResearchAcquisitionMode
      : defaultCaseCopilotPublicResearchMode(researchAction);
  const selectedResearchChoice =
    researchModeChoices.find((choice) => choice.mode === effectiveResearchAcquisitionMode) ??
    researchModeChoices.find((choice) => choice.selectedByDefault) ??
    researchModeChoices[0] ??
    null;
  const researchConsentScope = useMemo(
    () => deriveCaseCopilotResearchConsentScope({
      acquisitionMode: effectiveResearchAcquisitionMode,
      caseId,
      researchAction,
    }),
    [caseId, researchAction, effectiveResearchAcquisitionMode],
  );
  const consentPublicResearch = researchConsentScope !== null && consentedResearchScope === researchConsentScope;
  const manualAssumption = useMemo(() => ({
    amount: manualAmount,
    scale: manualScale,
    currency: manualCurrency,
    periodMonth: manualPeriodMonth,
    declaredSource: manualDeclaredSource,
    rationale: manualRationale,
    validationPlan: manualValidationPlan,
    questionDescriptor,
  }), [
    manualAmount,
    manualScale,
    manualCurrency,
    manualPeriodMonth,
    manualDeclaredSource,
    manualRationale,
    manualValidationPlan,
    questionDescriptor,
  ]);
  const manualReady = isCaseCopilotManualAssumptionComplete(
    manualAssumption,
    questionDescriptor,
  );
  const questionInputSchema = questionDescriptor
    ? presentCaseCopilotQuestionInputSchema(questionDescriptor)
    : null;
  const manualInputKind = questionInputSchema?.kind ?? "money";
  const schemaFieldByKey = new Map(
    questionInputSchema?.fields.map((field) => [field.fieldKey, field]) ?? [],
  );
  const answerValueField = schemaFieldByKey.get(manualInputKind === "text" ? "value" : "amount") ?? null;
  const scaleField = schemaFieldByKey.get("scale") ?? null;
  const currencyField = schemaFieldByKey.get("currency") ?? null;
  const periodField = schemaFieldByKey.get("period") ?? null;
  const sourceField = schemaFieldByKey.get("declared_source") ?? null;
  const rationaleField = schemaFieldByKey.get("rationale") ?? null;
  const validationPlanField = schemaFieldByKey.get("validation_plan") ?? null;
  const canRequestDocument = Boolean(onDocumentRequested) && actionAvailable(documentAction) && !busy;
  const documentUnavailableReason = !onDocumentRequested
    ? "Загрузка документов недоступна в этом рабочем пространстве."
    : actionReason(documentAction, "Система пока не открыла загрузку документа для этого вопроса.");
  const researchUnavailableReason = !onSubmit || !canPrepareResearchProp
    ? "Публичное исследование недоступно в этом рабочем пространстве."
    : actionReason(researchAction, "Система пока не открыла публичный поиск для этого вопроса.");
  const publicResearchStartError = caseCopilotSubmitFailureMessage("public_research");
  const skipUnavailableReason = !onSubmit || !canSubmitUnknownProp
    ? "Ответ «не знаю» пока недоступен в помощнике."
    : "Ответ уйдёт в диалог и не будет сохранён как факт или предположение.";
  const canSubmitFactAction = Boolean(onSubmit && canSubmitFactProp && factAction);
  const canPrepareResearchAction = Boolean(onSubmit && canPrepareResearchProp && researchAction);
  const canSubmitUnknownAction = Boolean(onSubmit && canSubmitUnknownProp);
  const publicResearchModeCopy =
    selectedResearchChoice ?? presentPublicResearchPreRunCopy(providerStatus);
  const validationCopy = useMemo(
    () => validationErrors.map((error) => `${formatDependency(error.field)}: ${validationMessage(error.message)}`),
    [validationErrors],
  );
  const answerModes = useMemo(() => deriveCaseCopilotAnswerModes({
    actions,
    busy,
    canPrepareResearch: canPrepareResearchAction,
    canSubmitFact: canSubmitFactAction,
    canSubmitUnknown: canSubmitUnknownAction,
    consentPublicResearch,
    hasDocumentHandler: Boolean(onDocumentRequested),
    manualDraft: manualReady ? "structured_manual_assumption" : "",
  }), [
    actions,
    busy,
    canPrepareResearchAction,
    canSubmitFactAction,
    canSubmitUnknownAction,
    consentPublicResearch,
    manualReady,
    onDocumentRequested,
  ]);
  const modeTabs = useMemo(() => answerModes.map((mode): AnswerMode => ({
    type: mode.type,
    label:
      mode.type === "manual"
        ? "Ответ"
        : mode.type === "file"
          ? "Документ"
          : mode.type === "public_research"
            ? "Публичный поиск"
            : "Не знаю",
  })), [answerModes]);
  const selectedAnswerType = selectCaseCopilotAnswerType(answerModes, answerType);
  const selectedMode = answerModes.find((mode) => mode.type === selectedAnswerType) ?? null;
  const canPrepareResearch = Boolean(selectedMode?.type === "public_research" && selectedMode.enabled);
  const canSubmitUnknown = Boolean(selectedMode?.type === "skip" && selectedMode.enabled);
  const canSubmitManual = Boolean(selectedMode?.type === "manual" && selectedMode.enabled);
  const noActionState = presentCaseCopilotNoActionState({
    answerActionCount: answerModes.length,
    busy,
    hasDocumentRequestHandler: Boolean(onDocumentRequested),
  });
  const hasAnswerActions = noActionState.showAnswerControls;
  const answerTabButtons = modeTabs.map((mode) => (
    <button
      aria-pressed={selectedAnswerType === mode.type}
      className={selectedAnswerType === mode.type ? styles.activeTab : ""}
      key={mode.type}
      onClick={() => selectAnswerType(mode.type)}
      type="button"
    >
      {mode.label}
    </button>
  ));

  useEffect(() => {
    const resetDraft = resetCaseCopilotManualDraftForQuestionChange(
      previousQuestionDescriptor.current,
      questionDescriptor,
      manualAssumption,
    );
    previousQuestionDescriptor.current = questionDescriptor;
    if (resetDraft !== manualAssumption) {
      setManualAmount(resetDraft.amount);
      setManualScale(resetDraft.scale);
      setManualCurrency(resetDraft.currency);
      setManualPeriodMonth(resetDraft.periodMonth);
      setManualDeclaredSource(resetDraft.declaredSource);
      setManualRationale(resetDraft.rationale);
      setManualValidationPlan(resetDraft.validationPlan);
      setLocalError(null);
    }
  }, [manualAssumption, questionDescriptor, questionIdentity]);

  function selectAnswerType(nextAnswerType: CaseQuestionAnswerType) {
    setLocalError(null);
    setAnswerType(nextAnswerType);
  }

  function setPublicResearchConsent(enabled: boolean) {
    setLocalError(null);
    setConsentedResearchScope(enabled ? researchConsentScope : null);
  }

  function selectResearchAcquisitionMode(mode: RequestedResearchAcquisitionMode) {
    const choice = researchModeChoices.find((candidate) => candidate.mode === mode);
    setLocalError(choice?.available === false ? choice.disabledReason : null);
    if (!choice?.available) return;
    setSelectedResearchAcquisitionMode(mode);
    setConsentedResearchScope(null);
  }

  function primaryButtonLabel(): string {
    if (selectedAnswerType === "file") return "Открыть загрузку";
    if (selectedAnswerType === "public_research") {
      return busy ? publicResearchModeCopy.busyLabel : publicResearchModeCopy.buttonLabel;
    }
    if (selectedAnswerType === "skip") return "Ответить «не знаю»";
    return busy ? "Сохраняю ответ…" : "Сохранить ответ";
  }

  async function submit(answer: CaseQuestionAnswerType) {
    setLocalError(null);
    if (answer === "file") {
      if (!canRequestDocument) {
        setLocalError(documentUnavailableReason);
        return;
      }
      if (!onDocumentRequested) {
        setLocalError(documentUnavailableReason);
        return;
      }
      onDocumentRequested();
      return;
    }
    if (!onSubmit) {
      setLocalError("Действие сейчас недоступно в системе.");
      return;
    }
    if (answer === "public_research" && !canPrepareResearch) {
      setLocalError(publicResearchStartError);
      return;
    }
    if (answer === "public_research" && selectedResearchChoice?.available === false) {
      setLocalError(selectedResearchChoice.disabledReason);
      return;
    }
    try {
      const saved = await onSubmit({
        ...buildCaseCopilotSubmitPayload({
          acquisitionMode: effectiveResearchAcquisitionMode,
          actions,
          answerType: answer,
          consentPublicResearch,
          manualDraft: manualReady ? "structured_manual_assumption" : "",
        }),
        answerType: answer,
        ...manualAssumption,
        manualValue: manualInputKind === "text" ? manualAmount.trim() : manualAmount.trim(),
      });
      if (saved) {
        setManualAmount("");
        setManualScale("");
        setManualCurrency("");
        setManualPeriodMonth("");
        setManualDeclaredSource("");
        setManualRationale("");
        setManualValidationPlan("");
        setConsentedResearchScope(null);
        setLocalError(null);
      } else {
        setLocalError(answer === "public_research" ? publicResearchStartError : caseCopilotSubmitFailureMessage(answer));
      }
    } catch (error) {
      setLocalError(caseCopilotOperationFailureMessage(answer, error));
    }
  }

  return (
    <section className={styles.questionCard} data-case-question-card>
      <div className={styles.questionHeader}>
        <span>Один главный вопрос</span>
          <strong>{questionDescriptor?.question ?? (question ? formatCopilotQuestion(question) : "Добавьте следующий недостающий бизнес-факт")}</strong>
      </div>

      {hasAnswerActions ? (
        <div className={styles.answerTabs} role="tablist" aria-label="Способ ответа">
          {answerTabButtons}
        </div>
      ) : null}

      {noActionState.showRecoveryAction ? (
        <div className={styles.modeBlock} data-case-copilot-no-action>
          <XCircle aria-hidden="true" size={18} />
          <span>{noActionState.recoveryText}</span>
          <button
            className={styles.inlineAction}
            disabled={noActionState.recoveryDisabled}
            onClick={onDocumentRequested}
            type="button"
          >
            {noActionState.recoveryLabel}
          </button>
        </div>
      ) : null}

      {selectedAnswerType === "manual" ? (
        <div className={styles.manualField}>
          <span data-case-copilot-manual-field-key={factFieldKey}>
            {questionDescriptor?.label ?? "Структурированный ответ основателя"}
          </span>
          {questionDescriptor ? (
            <>
              <small>{questionDescriptor.description}</small>
              <small>{questionDescriptor.why_needed}</small>
              {questionInputSchema ? <small>{questionInputSchema.unlocksCopy}</small> : null}
              <small data-case-question-example>Пример: {questionDescriptor.example}</small>
              <small>{questionDescriptor.validation_guidance}</small>
            </>
          ) : null}
          <label>
            <span>{answerValueField?.label ?? (manualInputKind === "text" ? "Ответ" : "Значение")}</span>
            {answerValueField?.required ? <small>{answerValueField.requiredLabel}</small> : null}
            <input
              data-case-copilot-manual-amount
              inputMode={manualInputKind === "text" ? "text" : "decimal"}
              onChange={(event) => setManualAmount(event.target.value)}
              placeholder={answerValueField?.placeholder ?? ""}
              type="text"
              value={manualAmount}
            />
          </label>
          {scaleField ? (
            <label>
              <span>{scaleField.label}</span>
              {scaleField.required ? <small>{scaleField.requiredLabel}</small> : null}
              <select
                data-case-copilot-manual-scale
                onChange={(event) => setManualScale(event.target.value)}
                value={manualScale}
              >
                <option value="">{scaleField.placeholder || "Выберите масштаб"}</option>
                <option value="ones">единицы</option>
                <option value="thousands">тысячи</option>
                <option value="millions">миллионы</option>
              </select>
            </label>
          ) : null}
          {currencyField ? (
            <label>
              <span>{currencyField.label}</span>
              {currencyField.required ? <small>{currencyField.requiredLabel}</small> : null}
              <input
                data-case-copilot-manual-currency
                onChange={(event) => setManualCurrency(event.target.value)}
                placeholder={currencyField.placeholder}
                type="text"
                value={manualCurrency}
              />
            </label>
          ) : null}
          {periodField ? (
            <label>
              <span>{periodField.label}</span>
              {periodField.required ? <small>{periodField.requiredLabel}</small> : null}
              <input
                data-case-copilot-manual-period
                onChange={(event) => setManualPeriodMonth(event.target.value)}
                placeholder={periodField.placeholder}
                type="month"
                value={manualPeriodMonth}
              />
            </label>
          ) : null}
          {manualInputKind === "money" && !questionInputSchema ? (
            <>
              <label>
                <span>Масштаб</span>
                <select
                  data-case-copilot-manual-scale
                  onChange={(event) => setManualScale(event.target.value)}
                  value={manualScale}
                >
                  <option value="">Выберите масштаб</option>
                  <option value="ones">единицы</option>
                  <option value="thousands">тысячи</option>
                  <option value="millions">миллионы</option>
                </select>
              </label>
              <label>
                <span>Валюта</span>
                <input
                  data-case-copilot-manual-currency
                  onChange={(event) => setManualCurrency(event.target.value)}
                  placeholder={questionDescriptor?.input_schema.fields.find((field) => field.field_key === "currency")?.placeholder ?? ""}
                  type="text"
                  value={manualCurrency}
                />
              </label>
              <label>
                <span>Месяц</span>
                <input
                  data-case-copilot-manual-period
                  onChange={(event) => setManualPeriodMonth(event.target.value)}
                  type="month"
                  value={manualPeriodMonth}
                />
              </label>
            </>
          ) : null}
          <label>
            <span>{sourceField?.label ?? "Откуда значение"}</span>
            {sourceField?.required ? <small>{sourceField.requiredLabel}</small> : null}
            <input
              data-case-copilot-manual-source
              onChange={(event) => setManualDeclaredSource(event.target.value)}
              placeholder={sourceField?.placeholder ?? "интервью с основателем"}
              type="text"
              value={manualDeclaredSource}
            />
          </label>
          <label>
            <span>{rationaleField?.label ?? "Почему это важно"}</span>
            {rationaleField?.required ? <small>{rationaleField.requiredLabel}</small> : null}
            <input
              data-case-copilot-manual-rationale
              onChange={(event) => setManualRationale(event.target.value)}
              placeholder={rationaleField?.placeholder ?? "входные данные для планирования"}
              type="text"
              value={manualRationale}
            />
          </label>
          <label>
            <span>{validationPlanField?.label ?? "Как проверить"}</span>
            {validationPlanField?.required ? <small>{validationPlanField.requiredLabel}</small> : null}
            <input
              data-case-copilot-manual-validation-plan
              onChange={(event) => setManualValidationPlan(event.target.value)}
              placeholder={validationPlanField?.placeholder ?? "сверить с CRM или финансами"}
              type="text"
              value={manualValidationPlan}
            />
          </label>
          <small>{actionReason(factAction, "Ручной ответ станет доступен после подготовки вопроса системой.")}</small>
        </div>
      ) : null}

      {selectedAnswerType === "file" ? (
        <div className={styles.modeBlock}>
          <FilePlus2 aria-hidden="true" size={18} />
          <span>{canRequestDocument ? actionReason(documentAction, "Загрузите документ по кейсу.") : documentUnavailableReason}</span>
        </div>
      ) : null}

      {selectedAnswerType === "public_research" ? (
        <div className={styles.modeBlock}>
          <Search aria-hidden="true" size={18} />
          <div
            aria-label="Режим публичного исследования"
            className={styles.answerTabs}
            role="radiogroup"
          >
            {researchModeChoices.map((choice) => (
              <button
                aria-checked={effectiveResearchAcquisitionMode === choice.mode}
                aria-describedby={
                  choice.disabledReason
                    ? `${choice.mode}-description ${choice.mode}-disabled-reason`
                    : `${choice.mode}-description`
                }
                className={effectiveResearchAcquisitionMode === choice.mode ? styles.activeTab : ""}
                data-case-question-research-mode={choice.mode}
                disabled={!choice.available}
                key={choice.mode}
                onClick={() => selectResearchAcquisitionMode(choice.mode)}
                role="radio"
                title={choice.disabledReason ?? choice.description}
                type="button"
              >
                {choice.label}
              </button>
            ))}
          </div>
          {researchModeChoices.map((choice) => (
            <small
              hidden={effectiveResearchAcquisitionMode !== choice.mode}
              id={`${choice.mode}-description`}
              key={`${choice.mode}-description`}
            >
              {choice.description}
            </small>
          ))}
          {researchModeChoices.map((choice) =>
            choice.disabledReason ? (
              <small
                data-case-question-research-disabled-reason={choice.mode}
                id={`${choice.mode}-disabled-reason`}
                key={`${choice.mode}-disabled-reason`}
              >
                {choice.disabledReason}
              </small>
            ) : null,
          )}
          <small>{canPrepareResearch ? actionReason(researchAction, publicResearchModeCopy.actionHint) : researchUnavailableReason}</small>
          {selectedAnswerType === "public_research" && busy ? (
            <small>{publicResearchModeCopy.busyDescription}</small>
          ) : null}
          <label className={styles.consentRow}>
            <input
              checked={consentPublicResearch}
              data-case-question-consent="public_research"
              onChange={(event) => setPublicResearchConsent(event.target.checked)}
              type="checkbox"
            />
            {publicResearchModeCopy.consentLabel}
          </label>
        </div>
      ) : null}

      {selectedAnswerType === "skip" ? (
        <div className={styles.modeBlock}>
          <XCircle aria-hidden="true" size={18} />
          <span>{canSubmitUnknown ? "Ответить «не знаю» в диалоге. Полнота сценария останется отдельно от покрытия фактами." : skipUnavailableReason}</span>
        </div>
      ) : null}

      {validationCopy.length > 0 || localError ? (
        <div className={styles.errorList} role="alert">
          {localError ? <p>{localError}</p> : null}
          {validationCopy.map((item) => <p key={item}>{item}</p>)}
        </div>
      ) : null}

      {noActionState.showPrimaryAnswerSubmit ? (
        <button
          className={styles.primaryButton}
          data-case-question-submit={selectedAnswerType ?? undefined}
          disabled={
            busy ||
            selectedAnswerType === null ||
            (selectedAnswerType === "manual" && !canSubmitManual) ||
            (selectedAnswerType === "file" && !canRequestDocument) ||
            (selectedAnswerType === "public_research" && !canPrepareResearch) ||
            (selectedAnswerType === "skip" && !canSubmitUnknown)
          }
          onClick={() => {
            if (selectedAnswerType) void submit(selectedAnswerType);
          }}
          type="button"
        >
          <CheckCircle2 aria-hidden="true" size={16} />
          {primaryButtonLabel()}
        </button>
      ) : null}
    </section>
  );
}
