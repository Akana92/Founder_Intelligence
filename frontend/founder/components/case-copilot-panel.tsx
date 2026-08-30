"use client";

import { MessageSquareText, PanelRightClose, PanelRightOpen, ShieldCheck } from "lucide-react";

import {
  CaseQuestionCard,
  type CaseQuestionAnswerType,
  type CaseQuestionSubmitInput,
} from "@/components/case-question-card";
import { FounderScenarioMetrics } from "@/components/founder-scenario-metrics";
import { buildCaseCopilotResearchJobPresentation } from "@/lib/case-copilot-presentation";
import type {
  CaseMutationFieldError,
  CaseValueKind,
  CopilotActionAvailability,
  CopilotStateResponse,
  CopilotThreadResponse,
  ProviderStatus,
  ResearchJobResponse,
  ResearchPlanResponse,
  ScenarioKey,
  ScenarioProjectionResponse,
  StartupScenarioVariant,
} from "@/lib/contracts";
import {
  formatCopilotAction,
  formatCopilotActionStatus,
  formatCopilotRole,
  formatCopilotThreadMessage,
  formatDependency,
  formatMetric,
  formatProvenance,
  formatResearchAcquisitionMode,
  formatScenario,
  formatScenarioComparisonValue,
  presentPublicBenchmarkEntry,
} from "@/lib/founder-readable-presentation";
import type { ScenarioMetricComparison } from "@/lib/scenario-presentation";

import styles from "./case-copilot-panel.module.css";

export type CaseCopilotPanelProps = Readonly<{
  busy?: boolean;
  caseName?: string;
  copilotState: CopilotStateResponse | null | undefined;
  copilotThread: CopilotThreadResponse | null | undefined;
  contextFocus?: CaseCopilotContextFocus;
  focusToken?: number;
  open: boolean;
  preferredAnswerType?: CaseQuestionAnswerType;
  providerStatus?: ProviderStatus | null;
  researchJob: ResearchJobResponse | null | undefined;
  researchMetricComparison: ScenarioMetricComparison | null | undefined;
  researchPlan: ResearchPlanResponse | null | undefined;
  scenarios: ScenarioProjectionResponse | null | undefined;
  selectedScenario: StartupScenarioVariant | null | undefined;
  validationErrors?: readonly CaseMutationFieldError[];
  onClose?: () => void;
  onAssumptionSubmit?: (input: CaseQuestionSubmitInput) => Promise<boolean> | boolean;
  onDocumentRequested?: () => void;
  onFactSubmit?: (input: CaseQuestionSubmitInput) => Promise<boolean> | boolean;
  onResearchPrepare?: (input: CaseQuestionSubmitInput) => Promise<boolean> | boolean;
  onScenarioSelect?: (scenarioKey: ScenarioKey) => Promise<boolean> | boolean;
  onUnknownSubmit?: (input: CaseQuestionSubmitInput) => Promise<boolean> | boolean;
}>;

export type CaseCopilotContextFocus = Readonly<{
  page: string;
  focusKey: string;
  label: string;
}>;

const sourceBoundaryDescriptions: Record<CaseValueKind, string> = {
  source_fact: "Заявлено в загруженном документе; это не независимая проверка.",
  founder_statement: "Остаётся предположением, пока не подтверждено документом.",
  public_benchmark: "Контекст рынка, а не внутренний факт компании.",
  ai_scenario: "Плановая гипотеза для проверки, а не факт.",
  deterministic_calculation: "Производная метрика с явными входными данными.",
  contradiction: "Нужно решение или новый источник.",
};

const sourceKinds = Object.keys(sourceBoundaryDescriptions) as CaseValueKind[];

function readableActionCopy(action: CopilotActionAvailability): string {
  if (action.status === "blocked") return "Сначала устраните указанное ограничение или добавьте недостающие данные.";
  if (action.action === "open_fact_input") return "Добавьте значение вручную и укажите, как его проверить.";
  if (action.action === "open_document_upload") return "Приложите документ, который подтверждает значение.";
  if (action.action === "prepare_public_research") return "Сначала подтвердите согласие: внешние рыночные ориентиры ищутся только после разрешения.";
  return "Откройте действие, чтобы продолжить работу с кейсом.";
}

function fieldLabel(value: string): string {
  return formatDependency(value);
}

function formatManualOnlyKeys(values: readonly string[]): string {
  const labels = [...new Set(values.map(fieldLabel))];
  return labels.join(", ") || "нет";
}

export function CaseCopilotPanel({
  busy = false,
  caseName,
  copilotState,
  copilotThread,
  contextFocus,
  focusToken = 0,
  onAssumptionSubmit,
  onClose,
  onDocumentRequested,
  onFactSubmit,
  onResearchPrepare,
  onScenarioSelect,
  onUnknownSubmit,
  open,
  preferredAnswerType,
  providerStatus = null,
  researchJob,
  researchMetricComparison,
  researchPlan,
  scenarios,
  selectedScenario,
  validationErrors = [],
}: CaseCopilotPanelProps) {
  const actions = copilotState?.actions ?? [];
  const messages = copilotThread?.messages ?? [];
  const revision = copilotState?.data_revision ?? copilotThread?.data_revision ?? null;
  const caseId = copilotState?.case_id ?? copilotThread?.case_id ?? null;
  const researchJobPresentation = researchJob
    ? buildCaseCopilotResearchJobPresentation(researchJob)
    : null;

  async function submitQuestion(input: CaseQuestionSubmitInput): Promise<boolean> {
    if (input.answerType === "public_research") {
      return Boolean(await onResearchPrepare?.(input));
    }
    if (input.answerType === "skip") {
      return Boolean(await onUnknownSubmit?.(input));
    }
    if (input.answerType === "manual") {
      return Boolean(await onAssumptionSubmit?.(input));
    }
    return Boolean(await onFactSubmit?.(input));
  }

  return (
    <>
      {open ? (
        <button
          aria-label="Закрыть помощника и вернуться к рабочей области"
          className={styles.drawerBackdrop}
          onClick={onClose}
          type="button"
        />
      ) : null}
      <aside
      aria-label="Помощник по кейсу"
      aria-busy={busy}
      aria-modal={open ? "false" : undefined}
      className={`${styles.panel} ${open ? styles.panelOpen : styles.panelClosed}`}
      data-case-id={caseId ?? undefined}
      data-case-copilot-focus={focusToken}
      data-case-copilot-panel
      data-layout={open ? "rail" : "drawer"}
      role="dialog"
    >
      <header className={styles.panelHeader}>
        <div>
          <span>Помощник по кейсу</span>
          <strong>{caseName ?? "Проект после анализа"}</strong>
          <small>{revision ? `Версия данных ${revision}` : "Жду состояние кейса"}</small>
        </div>
        <button aria-label={open ? "Свернуть помощника по кейсу" : "Открыть помощника по кейсу"} onClick={onClose} type="button">
          {open ? <PanelRightClose aria-hidden="true" size={18} /> : <PanelRightOpen aria-hidden="true" size={18} />}
        </button>
      </header>

      <div className={styles.contextSummary}>
        <ShieldCheck aria-hidden="true" size={18} />
        <span>
          Ответы основателя, публичные ориентиры и сценарии ИИ не становятся фактами автоматически.
        </span>
      </div>

      <div className={styles.contextSummary} data-case-copilot-context>
        <MessageSquareText aria-hidden="true" size={18} />
        <span>
          Сейчас открыт раздел: {contextFocus?.label ?? "рабочее пространство"}.
        </span>
      </div>

      <CaseQuestionCard
        actions={actions}
        busy={busy}
        canPrepareResearch={Boolean(onResearchPrepare)}
        canSubmitFact={Boolean(onAssumptionSubmit)}
        canSubmitUnknown={Boolean(onUnknownSubmit)}
        caseId={caseId}
        key={`${focusToken}:${preferredAnswerType ?? "manual"}`}
        onDocumentRequested={onDocumentRequested}
        onSubmit={submitQuestion}
        preferredAnswerType={preferredAnswerType}
        providerStatus={providerStatus}
        question={copilotState?.next_question ?? null}
        questionDescriptor={copilotState?.question_descriptor ?? null}
        validationErrors={validationErrors}
      />

      {(researchPlan || researchJob) ? (
        <section className={styles.researchStatus} data-case-copilot-research-status>
          <h2>Публичное исследование</h2>
          {researchPlan ? (
            <article data-research-plan-id={researchPlan.plan_id}>
              <strong>План поиска публичных ориентиров</strong>
              <span>План готов для версии {researchPlan.data_revision}</span>
              <p>Поиск охватывает только открытые источники и начнётся после явного согласия.</p>
              <small>Запросов к поиску: {researchPlan.query_previews.length}</small>
              <small>Требуют ручного ответа: {formatManualOnlyKeys(researchPlan.manual_only_keys)}</small>
            </article>
          ) : null}
          {researchJob ? (
            <article data-research-job-id={researchJob.job_id} data-research-job-status={researchJob.status}>
              <strong>{researchJobPresentation?.label}</strong>
              <span>
                Версия {researchJob.old_revision ?? researchJob.data_revision} →{" "}
                {researchJob.new_revision ?? researchJob.data_revision}
              </span>
              <p>{researchJobPresentation?.description}</p>
              {researchJobPresentation ? (
                <small>Режим получения: {researchJobPresentation.modeLabel}</small>
              ) : null}
              <small>Публичных источников: {researchJobPresentation?.citations.length ?? 0}</small>
              {researchJobPresentation && researchJobPresentation.citations.length > 0 ? (
                <ul>
                  {researchJobPresentation.citations.map((citation, index) => (
                    <li key={`${citation}-${index}`}>
                      <a href={citation} rel="noreferrer" target="_blank">
                        Публичный источник {index + 1}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : null}
              {researchJobPresentation && researchJobPresentation.sourceRefCount > 0 ? (
                <small>Сохранённых ссылок на источники: {researchJobPresentation.sourceRefCount}</small>
              ) : null}
              {researchJobPresentation && researchJobPresentation.acceptedSourceSummaries.length > 0 ? (
                <ul>
                  {researchJobPresentation.acceptedSourceSummaries.map((source, index) => (
                    <li key={`${source.sourceUrl}-${index}`}>
                      <span>{source.sourceLabel}</span>
                      {source.sourceDomain ? <small>{source.sourceDomain}</small> : null}
                      <small>Получено: {source.retrievalDate}</small>
                      <small>Режим: {source.modeLabel}</small>
                    </li>
                  ))}
                </ul>
              ) : null}
              {researchJobPresentation && researchJobPresentation.changedBlocks.length > 0 ? (
                <>
                  <small>Изменённые блоки</small>
                  <ul>
                    {researchJobPresentation.changedBlocks.map((block) => (
                      <li key={block}>{block}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {researchJobPresentation?.invalidProviderContract ? (
                <small>Неподходящие строки провайдера отброшены без изменения фактов компании.</small>
              ) : null}
              {researchJob.accepted_entries.map((entry) => (
                <PublicBenchmarkDisclosure
                  acquisitionMode={researchJob.acquisition_mode}
                  entry={entry}
                  key={entry.entry_id}
                />
              ))}
            </article>
          ) : null}
          {researchMetricComparison ? (
            <article data-research-metric-comparison>
              <strong>До → после</strong>
              <span>
                {formatScenario(researchMetricComparison.scenarioKey)} сценарий · версия{" "}
                {researchMetricComparison.oldRevision} → {researchMetricComparison.newRevision}
              </span>
              <small>
                Изменённых метрик: {researchMetricComparison.changedMetrics.length}
              </small>
              {researchMetricComparison.changedMetrics.length > 0 ? (
                <dl className={styles.metricDeltaList}>
                  {researchMetricComparison.changedMetrics.map((change) => (
                    <div key={change.metricKey}>
                      <dt>{formatMetric(change.metricKey)}</dt>
                      <dd>
                        {formatScenarioComparisonValue(change.oldValue)} →{" "}
                        {formatScenarioComparisonValue(change.newValue)}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p>После публичного поиска метрики не изменились.</p>
              )}
              <small>{researchJobPresentation?.comparisonNote ?? "Это пересчёт сценария на публичном контексте, не факт компании."}</small>
            </article>
          ) : null}
        </section>
      ) : null}

      <section className={styles.threadList}>
        <h2><MessageSquareText aria-hidden="true" size={17} /> Диалог</h2>
        {messages.length > 0 ? messages.map((message) => (
          <article data-role={message.role} key={message.message_id}>
            <span>{formatCopilotRole(message.role)}</span>
            <p>{formatCopilotThreadMessage(message.role, message.content)}</p>
            {message.action_result ? <small>Обновлены данные кейса</small> : null}
          </article>
        )) : (
          <p className={styles.blocker}>Диалог по кейсу ещё не загружен.</p>
        )}
      </section>

      <section className={styles.actionList}>
        <h2>Что нужно сделать</h2>
        {actions.map((action) => (
          <article data-action-status={action.status} key={action.action_id}>
            <strong>{formatCopilotAction(action.action)}</strong>
            <span>{formatCopilotActionStatus(action.status)}</span>
            <p>{readableActionCopy(action)}</p>
          </article>
        ))}
        {actions.length === 0 ? <p className={styles.blocker}>Система пока не предложила следующее действие.</p> : null}
      </section>

      <section className={styles.sourceLegend}>
        <h2>Как читать источники</h2>
        {sourceKinds.map((kind) => (
          <div data-source-kind={kind} key={kind}>
            <strong>{formatProvenance(kind)}</strong>
            <span>{sourceBoundaryDescriptions[kind]}</span>
          </div>
        ))}
      </section>

      <FounderScenarioMetrics
        busy={busy}
        factCoverage={scenarios?.fact_coverage ?? copilotState?.fact_coverage ?? null}
        onScenarioSelect={onScenarioSelect}
        scenarioCompleteness={scenarios?.scenario_completeness ?? copilotState?.scenario_completeness ?? null}
        scenarios={scenarios ?? null}
        selectedScenario={selectedScenario ?? null}
      />
      </aside>
    </>
  );
}

function PublicBenchmarkDisclosure({
  acquisitionMode,
  entry,
}: Readonly<{
  acquisitionMode: ResearchJobResponse["acquisition_mode"];
  entry: ResearchJobResponse["accepted_entries"][number];
}>) {
  const presentation = presentPublicBenchmarkEntry(entry);
  const sourceDomain = publicDomainFromUrl(entry.url);

  return (
    <details className={styles.metricDisclosure}>
      <summary>
        <strong>{presentation.title}</strong>
        <em>{presentation.provenanceLabel}</em>
      </summary>
      <dl>
        <div>
          <dt>Источник</dt>
          <dd>
            <a href={presentation.sourceUrl} rel="noreferrer" target="_blank">
              {presentation.sourceLabel}
            </a>
          </dd>
        </div>
        <div>
          <dt>Режим получения</dt>
          <dd>{formatResearchAcquisitionMode(acquisitionMode)}</dd>
        </div>
        {sourceDomain ? (
          <div>
            <dt>Домен</dt>
            <dd>{sourceDomain}</dd>
          </div>
        ) : null}
        <div>
          <dt>URL</dt>
          <dd>
            <a href={entry.url} rel="noreferrer" target="_blank">
              {entry.url}
            </a>
          </dd>
        </div>
        <div>
          <dt>Получено</dt>
          <dd>{entry.retrieval_date}</dd>
        </div>
        <div>
          <dt>Дата</dt>
          <dd>{presentation.dateLabel}</dd>
        </div>
        <div>
          <dt>Диапазон</dt>
          <dd>{presentation.rangeLabel}</dd>
        </div>
        <div>
          <dt>Формула</dt>
          <dd>{presentation.formula}</dd>
        </div>
        <div>
          <dt>Зависимости</dt>
          <dd>
            {presentation.dependencies.length > 0
              ? presentation.dependencies.map((dependency, index) => (
                  <span key={`${dependency}-${index}`}>{dependency}</span>
                ))
              : "Нет"}
          </dd>
        </div>
        <div>
          <dt>План проверки</dt>
          <dd>{presentation.validationPlan}</dd>
        </div>
      </dl>
    </details>
  );
}

function publicDomainFromUrl(value: string): string | null {
  try {
    return new URL(value).hostname || null;
  } catch {
    return null;
  }
}
