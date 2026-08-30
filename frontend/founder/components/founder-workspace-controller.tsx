"use client";

import { useEffect, useRef, useState } from "react";

import {
  FounderShell,
  type FounderAdvisorAnswerInput,
  type FounderShellWorkspace,
  type FounderWorkspaceReportState,
} from "@/components/founder-shell";
import type { CaseQuestionSubmitInput } from "@/components/case-question-card";
import {
  createFounderWorkspaceOrchestrator,
  founderErrorMessage,
  founderShellStage,
  type FounderCaseFixtureMode,
  type FounderWorkspaceOrchestrator,
  type FounderWorkspaceSnapshot,
} from "@/components/founder-workspace-orchestrator";
import { startFounderWorkspaceAnalysis } from "@/components/founder-workspace-analysis-start";
import { safeFounderText } from "@/lib/advisor-presentation";
import {
  buildCaseCopilotManualAssumptionRequest,
  buildCaseCopilotUnknownMessageRequest,
} from "@/lib/case-copilot-presentation";
import type { FounderWorkflowStage } from "@/lib/startup-state-machine";
import type { RequestedResearchAcquisitionMode } from "@/lib/contracts";
import {
  buildLocalInventory,
  type LocalFileInventoryItem,
} from "@/lib/upload";
import { resolveFounderRuntimeConfig } from "@/lib/runtime-config";
import {
  clearStoredFounderCaseId,
  isFounderCaseId,
  readStoredFounderCaseId,
  writeStoredFounderCaseId,
} from "@/lib/founder-case-storage";
import { founderUrlForCase } from "@/lib/navigation";

const stageCopy: Record<
  FounderWorkflowStage,
  Readonly<{ eyebrow: string; title: string; detail: string }>
> = {
  idle: {
    eyebrow: "Новый кейс",
    title: "Добавьте материалы для анализа",
    detail: "Один запуск создаёт один приватный кейс без выбора готового демо.",
  },
  uploading: {
    eyebrow: "Безопасная загрузка",
    title: "Передаём документы в кейс",
    detail: "Повторный запуск заблокирован, пока сервер принимает материалы.",
  },
  primary_queued: {
    eyebrow: "Первичный анализ",
    title: "Кейс поставлен в очередь",
    detail: "Статус обновляется автоматически с увеличивающимся интервалом.",
  },
  primary_intake: {
    eyebrow: "Первичный анализ",
    title: "Определяем структуру материалов",
    detail: "Агент выделяет заявления, факты и недостающие доказательства.",
  },
  document_ready: {
    eyebrow: "Первичный анализ",
    title: "Документы готовы к разбору",
    detail: "Следующий статус появится автоматически.",
  },
  gate2_preview_ready: {
    eyebrow: "Контрольная точка 1",
    title: "Проверьте предварительное понимание",
    detail: "Подтвердите направление анализа или остановите кейс до глубокого исследования.",
  },
  gate2_approved: {
    eyebrow: "Контрольная точка 1",
    title: "Направление подтверждено",
    detail: "Запускаем глубокую проверку рынка, рисков и доказательств.",
  },
  gate2_denied: {
    eyebrow: "Контрольная точка 1",
    title: "Анализ остановлен пользователем",
    detail: "Документы остаются в текущем кейсе; можно начать новый анализ с уточнённым набором.",
  },
  primary_running: {
    eyebrow: "Первичный анализ",
    title: "Формируем карту бизнес-идеи",
    detail: "Проверяем проблему, клиента, модель, метрики и исходные риски.",
  },
  primary_deterministic_running: {
    eyebrow: "Офлайн-режим",
    title: "Выполняется детерминированная проверка",
    detail: "Этот режим явно отмечен и не подменяет подключённого провайдера ИИ.",
  },
  deep_running: {
    eyebrow: "Глубинный анализ",
    title: "Проверяем рынок и противоречия",
    detail: "Агент собирает внешние сигналы, расчёты, конкурентов и контрдоказательства.",
  },
  gate3_review_required: {
    eyebrow: "Контрольная точка 2",
    title: "Проверьте доказательную базу",
    detail: "На первой версии можно продолжить без исключений; позже здесь появится точечное исключение фактов.",
  },
  gate4_pending: {
    eyebrow: "Канонический отчёт",
    title: "Собираем итоговый снимок",
    detail: "Порядок разделов, ссылки на доказательства и расчёты фиксируются в одной версии.",
  },
  gate4_approved: {
    eyebrow: "Фиксация отчёта",
    title: "Версия утверждена",
    detail: "Готовим финальный PDF; JSON и HTML остаются привязаны к тому же снимку.",
  },
  gate4_rejected: {
    eyebrow: "Фиксация отчёта",
    title: "Версия не утверждена",
    detail: "Черновик сохранён. Просмотрите его и подтвердите актуальную версию, когда будете готовы.",
  },
  report_draft_ready: {
    eyebrow: "Контрольная точка 3",
    title: "Отчёт готов к фиксации",
    detail: "Проверьте черновик и зафиксируйте именно этот хеш и ревизию.",
  },
  report_pdf_ready: {
    eyebrow: "Результат готов",
    title: "Инвестиционный пакет сформирован",
    detail: "Доступны канонический JSON, браузерная версия HTML и зафиксированный PDF.",
  },
  error: {
    eyebrow: "Нужна проверка",
    title: "Процесс приостановлен",
    detail: "Кейс и выбранные документы сохранены, если сервер уже успел их принять.",
  },
};

function validatedReport(
  snapshot: FounderWorkspaceSnapshot | null,
): FounderWorkspaceSnapshot["report"] {
  const report = snapshot?.report;
  const reportSnapshot = snapshot?.reportSnapshot;
  if (
    !snapshot?.caseId ||
    !report ||
    !reportSnapshot ||
    report.case_id !== snapshot.caseId ||
    report.snapshot_revision !== reportSnapshot.data_revision
  ) {
    return null;
  }
  return report;
}

function hasHydratedGate2Evidence(
  snapshot: FounderWorkspaceSnapshot | null,
): boolean {
  const fields = snapshot?.profile?.fields;
  return Boolean(
    fields &&
      Object.values(fields).some(
        (field) =>
          field.status === "source_fact" &&
          field.values.length > 0 &&
          field.evidence_refs.length > 0,
      ),
  );
}

function fileId(file: File): string {
  return buildLocalInventory([file])[0]?.id ?? `${file.lastModified}-${file.name}`;
}

function previewValue(value: unknown): string {
  if (typeof value === "string") return safeFounderText(value, "Не указано").slice(0, 180);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `${value.length} элемент(а)`;
  if (value && typeof value === "object") return "Структурированные данные";
  return "Не указано";
}

function idempotencyKey(prefix: string): string {
  return `${prefix}:${globalThis.crypto.randomUUID()}`;
}

const researchBusyLabelByAcquisitionMode: Record<RequestedResearchAcquisitionMode, string> = {
  deterministic_offline_fixture:
    "Готовлю детерминированное офлайн-демо без интернет-запроса…",
  live_public_research: "Ищу публичные источники в live-интернете…",
};

function readLinkedFounderCaseId(location: Location): string | null {
  let value: string | null = null;
  try {
    value = new URLSearchParams(location.search).get("caseId");
  } catch {
    return null;
  }
  if (!value) return null;
  const normalized = value.trim().toLowerCase();
  return isFounderCaseId(normalized) ? normalized : null;
}

function syncLinkedFounderCaseId(caseId: string): void {
  const nextUrl = founderUrlForCase(globalThis.location.href, caseId);
  const currentUrl =
    `${globalThis.location.pathname}${globalThis.location.search}${globalThis.location.hash}`;
  if (nextUrl !== currentUrl) {
    history.replaceState(history.state, "", nextUrl);
  }
}

function founderBusyLabel(
  activity: FounderWorkspaceSnapshot["activity"],
  researchAcquisitionMode: RequestedResearchAcquisitionMode | null = null,
): string {
  if (activity === "research_searching") {
    return researchAcquisitionMode
      ? researchBusyLabelByAcquisitionMode[researchAcquisitionMode]
      : "Ищу публичные источники и рыночные ориентиры…";
  }
  const labels: Record<NonNullable<FounderWorkspaceSnapshot["activity"]>, string> = {
    deep_running: "Анализирую рынок и риски…",
    document_ready: "Готовлю документы к анализу…",
    primary_intake: "Читаю материалы проекта…",
    primary_running: "Анализирую профиль проекта…",
    research_preparing: "Готовлю безопасный план публичного поиска…",
    research_searching: "Ищу публичные источники и рыночные ориентиры…",
    research_recalculating: "Пересчитываю сценарные метрики после публичного поиска…",
    advisor_refreshing: "Обновляю вопрос и рекомендации…",
    advisor_answering: "Сохраняю ответ и обновляю рекомендации…",
    advisor_deciding: "Сохраняю решение по улучшению…",
    copilot_saving_fact: "Сохраняю значение как ответ основателя…",
    copilot_saving_assumption: "Сохраняю предположение для сценария…",
    copilot_sending_message: "Сохраняю ответ в диалоге…",
    scenario_selecting: "Переключаю сценарий расчёта…",
    asset_generating: "Готовлю выбранный рабочий материал…",
    launch_pack_generating: "Собираю рабочий пакет запуска…",
    submitting_gate2_approved: "Анализирую подтверждённое направление…",
    submitting_gate2_denied: "Сохраняю остановку анализа…",
    submitting_gate3: "Собираю итоговый отчёт…",
    submitting_gate4_approved: "Сохраняю финальную версию…",
    submitting_gate4_rejected: "Сохраняю решение по отчёту…",
    upload_accepted: "Документы приняты, обновляю кейс…",
    uploading: "Загружаю материалы…",
  };
  return activity ? labels[activity] : "Загружаю…";
}

export function WorkspaceActionPanel({
  filesAvailable,
  onGate2,
  onGate3,
  onGate4,
  onRetry,
  snapshot,
}: Readonly<{
  filesAvailable: boolean;
  onGate2: (decision: "approved" | "denied") => void;
  onGate3: () => void;
  onGate4: (decision: "approved" | "rejected") => void;
  onRetry: () => void;
  snapshot: FounderWorkspaceSnapshot | null;
}>) {
  const stage = snapshot?.display.stage ?? "idle";
  const copy = stageCopy[stage];
  const preview = Object.entries(snapshot?.gate2Preview?.preview ?? {}).slice(0, 6);
  const report = validatedReport(snapshot);
  const canReviewGate4 = Boolean(
    report && (stage === "report_draft_ready" || stage === "gate4_rejected"),
  );
  const hasArtifacts = Boolean(report && snapshot?.artifactUrls);

  return (
    <section
      aria-busy={snapshot?.busy ?? false}
      aria-live="polite"
      className={`workflow-action-panel workflow-action-panel--${stage}`}
    >
      <div className="workflow-action-panel__head">
        <span>{copy.eyebrow}</span>
        {snapshot?.caseId ? <strong>Кейс создан</strong> : null}
      </div>
      <h2>{copy.title}</h2>
      <p>{copy.detail}</p>

      {snapshot?.display.providerSignal === "provider_unavailable" ? (
        <div className="workflow-signal workflow-signal--error" role="alert">
          Провайдер ИИ недоступен. Мы не переключаем кейс на тестовые данные автоматически.
        </div>
      ) : null}
      {snapshot?.display.providerSignal === "offline_fixture_active" ? (
        <div className="workflow-signal workflow-signal--fixture" role="status">
          Активен явно выбранный офлайн-стенд. Результат помечен как демонстрационный.
        </div>
      ) : null}
      {snapshot?.error ? (
        <div className="workflow-signal workflow-signal--error" role="alert">
          {founderErrorMessage(snapshot.error)}
        </div>
      ) : null}

      {stage === "gate2_preview_ready" ? (
        <div className="workflow-review">
          {preview.length > 0 ? (
            <dl>
              {preview.map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>{previewValue(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p>Предварительный разбор готов без дополнительных полей для подтверждения.</p>
          )}
          <div className="workflow-actions">
            <button
              className="button button--primary"
              disabled={snapshot?.busy}
              onClick={() => onGate2("approved")}
              type="button"
            >
              Подтвердить и углубить
            </button>
            <button
              className="button button--secondary"
              disabled={snapshot?.busy}
              onClick={() => onGate2("denied")}
              type="button"
            >
              Остановить анализ
            </button>
          </div>
        </div>
      ) : null}

      {stage === "gate3_review_required" ? (
        <div className="workflow-review">
          <p>
            Продолжение без исключений сохранит все проверенные факты в каноническом отчёте.
          </p>
          <button
            className="button button--primary"
            disabled={snapshot?.busy}
            onClick={onGate3}
            type="button"
          >
            Собрать итоговый отчёт
          </button>
        </div>
      ) : null}

      {report ? (
        <div className="workflow-report-tuple">
          <span>Версия отчёта</span>
          <strong>{report.freeze_status === "approved" ? "Версия зафиксирована" : "Финальная версия отчёта"}</strong>
          <span>{report.freeze_status === "approved" ? "PDF, HTML и JSON готовы" : "Готова к проверке"}</span>
        </div>
      ) : null}

      {canReviewGate4 ? (
        <div className="workflow-actions">
          <button
            className="button button--primary"
            disabled={snapshot?.busy}
            onClick={() => onGate4("approved")}
            type="button"
          >
            Зафиксировать версию
          </button>
          <button
            className="button button--secondary"
            disabled={snapshot?.busy}
            onClick={() => onGate4("rejected")}
            type="button"
          >
            Отклонить версию
          </button>
        </div>
      ) : null}

      {hasArtifacts ? (
        <nav aria-label="Форматы отчёта" className="workflow-artifacts">
          <a href={snapshot?.artifactUrls?.json} rel="noreferrer" target="_blank">
            JSON
          </a>
          <a href={snapshot?.artifactUrls?.html} rel="noreferrer" target="_blank">
            HTML
          </a>
          {report?.freeze_status === "approved" ? (
            <a href={snapshot?.artifactUrls?.pdf} rel="noreferrer" target="_blank">
              PDF
            </a>
          ) : (
            <span aria-disabled="true">PDF после фиксации</span>
          )}
        </nav>
      ) : null}

      {stage === "error" ? (
        <button
          className="button button--secondary"
          disabled={snapshot?.busy || (!snapshot?.caseId && !filesAvailable)}
          onClick={onRetry}
          type="button"
        >
          Повторить безопасно
        </button>
      ) : null}
    </section>
  );
}

export function FounderWorkspaceController({
  caseFixtureMode,
}: Readonly<{ caseFixtureMode?: FounderCaseFixtureMode }>) {
  const [files, setFiles] = useState<File[]>([]);
  const [inventory, setInventory] = useState<LocalFileInventoryItem[]>([]);
  const [snapshot, setSnapshot] = useState<FounderWorkspaceSnapshot | null>(null);
  const [fetchedRuntimeMode, setFetchedRuntimeMode] =
    useState<FounderCaseFixtureMode | null>(null);
  const [runtimeConfigError, setRuntimeConfigError] = useState<Error | null>(null);
  const orchestrator = useRef<FounderWorkspaceOrchestrator | null>(null);
  const runtimeMode = caseFixtureMode ?? fetchedRuntimeMode;
  const activeRuntimeConfigError = caseFixtureMode ? null : runtimeConfigError;

  useEffect(() => {
    if (caseFixtureMode) {
      return;
    }

    let cancelled = false;
    void resolveFounderRuntimeConfig()
      .then((config) => {
        if (!cancelled) {
          setFetchedRuntimeMode(config.caseFixtureMode);
          setRuntimeConfigError(null);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setRuntimeConfigError(
            error instanceof Error
              ? error
              : new Error("Runtime fixture mode is unavailable"),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [caseFixtureMode]);

  useEffect(() => {
    if (runtimeMode === null) return;
    let cancelled = false;
    const instance = createFounderWorkspaceOrchestrator({
      caseFixtureMode: runtimeMode,
      onChange: (nextSnapshot) => {
        setSnapshot(nextSnapshot);
        if (nextSnapshot.caseId) {
          writeStoredFounderCaseId(globalThis.localStorage, nextSnapshot.caseId);
          syncLinkedFounderCaseId(nextSnapshot.caseId);
        }
      },
    });
    orchestrator.current = instance;
    const linkedCaseId = readLinkedFounderCaseId(globalThis.location);
    const storedCaseId =
      linkedCaseId ?? readStoredFounderCaseId(globalThis.localStorage);
    if (storedCaseId) {
      void instance.resumeCase(storedCaseId).then((resumed) => {
        if (cancelled || orchestrator.current !== instance) return;
        if (resumed === "missing") clearStoredFounderCaseId(globalThis.localStorage);
      });
    }
    return () => {
      cancelled = true;
      instance.dispose();
      orchestrator.current = null;
    };
  }, [runtimeMode]);

  function handleFilesSelected(selectedFiles: File[]) {
    setFiles((current) => {
      const byId = new Map(current.map((file) => [fileId(file), file]));
      selectedFiles.forEach((file) => byId.set(fileId(file), file));
      return Array.from(byId.values());
    });
  }

  function handleInventoryChange(nextInventory: LocalFileInventoryItem[]) {
    const nextIds = new Set(nextInventory.map((item) => item.id));
    setInventory(nextInventory);
    setFiles((current) => current.filter((file) => nextIds.has(fileId(file))));
  }

  async function startAnalysis(selectedFiles: readonly File[]) {
    return await startFounderWorkspaceAnalysis({
      clearDraft: (acceptedFiles) => {
        const acceptedIds = new Set(acceptedFiles.map((file) => fileId(file)));
        setFiles((current) => current.filter((file) => !acceptedIds.has(fileId(file))));
        setInventory((current) => current.filter((item) => !acceptedIds.has(item.id)));
      },
      getCurrentInstance: () => orchestrator.current,
      selectedFiles,
    });
  }

  async function handleGate2Decision(
    decision: "approved" | "denied",
  ): Promise<boolean> {
    const instance = orchestrator.current;
    if (!instance) return false;
    await instance.decideGate2(decision);
    const next = instance.getSnapshot();
    if (decision === "denied") {
      return !next.error && next.display.stage === "gate2_denied";
    }
    return (
      !next.error &&
      next.display.stage !== "gate2_preview_ready" &&
      next.display.stage !== "error"
    );
  }

  async function handleGate3Decision(): Promise<boolean> {
    const instance = orchestrator.current;
    if (!instance) return false;
    await instance.decideGate3([]);
    const next = instance.getSnapshot();
    const report = validatedReport(next);
    return !next.error && Boolean(report) && next.display.stage !== "error";
  }

  async function answerAdvisor(input: FounderAdvisorAnswerInput): Promise<boolean> {
    if (!input.questionId.trim()) return false;
    const instance = orchestrator.current;
    if (!instance) return false;
    await instance.answerAdvisor({
      question_id: input.questionId,
      answer_type: input.answerType,
      value: input.answerType === "manual" ? input.manualValue.trim() : null,
      document_id: input.answerType === "file" ? input.documentId : null,
      consent_public_research: input.publicResearchConsent,
    });
    const next = instance.getSnapshot();
    return Boolean(
      next.advisorAnswer &&
        next.advisorAnswer.status === "applied" &&
        next.advisorAnswer.question_id === input.questionId &&
        !next.advisorError,
    );
  }

  function currentCopilotRevision(): number | null {
    const liveSnapshot = orchestrator.current?.getSnapshot() ?? snapshot;
    return liveSnapshot?.copilotState?.data_revision ?? liveSnapshot?.profile?.data_revision ?? null;
  }

  async function saveCaseCopilotFact(input: CaseQuestionSubmitInput): Promise<boolean> {
    const instance = orchestrator.current;
    const expectedRevision = currentCopilotRevision();
    if (!instance || expectedRevision === null || input.answerType !== "manual") return false;
    await instance.submitCopilotFact({
      requirement_key: input.fieldKey,
      value: { kind: "text", value: input.manualValue },
      period: null,
      source: {
        kind: "founder_statement",
        declared_source: "founder",
        evidence_ref: null,
      },
      note: null,
      resolves_contradiction_id: null,
      expected_case_revision: expectedRevision,
      idempotency_key: idempotencyKey(`copilot-fact:${input.fieldKey}`),
    });
    const next = instance.getSnapshot();
    return !next.error;
  }

  async function saveCaseCopilotAssumption(input: CaseQuestionSubmitInput): Promise<boolean> {
    const instance = orchestrator.current;
    const expectedRevision = currentCopilotRevision();
    if (!instance || expectedRevision === null || input.answerType !== "manual") return false;
    await instance.submitCopilotAssumption({
      ...buildCaseCopilotManualAssumptionRequest({
        amount: input.amount,
        currency: input.currency,
        declaredSource: input.declaredSource,
        expectedRevision,
        fieldKey: input.fieldKey,
        periodMonth: input.periodMonth,
        questionDescriptor: input.questionDescriptor,
        rationale: input.rationale,
        scale: input.scale,
        textValue: input.manualValue,
        validationPlan: input.validationPlan,
      }),
      idempotency_key: `copilot-assumption:${input.fieldKey}:rev:${expectedRevision}`,
    });
    const next = instance.getSnapshot();
    return !next.error;
  }

  async function sendCaseCopilotUnknown(input: CaseQuestionSubmitInput): Promise<boolean> {
    const instance = orchestrator.current;
    const expectedRevision = currentCopilotRevision();
    if (!instance || expectedRevision === null) return false;
    await instance.submitCopilotMessage(
      buildCaseCopilotUnknownMessageRequest({
        fieldKey: input.fieldKey,
        expectedRevision,
      }),
    );
    const next = instance.getSnapshot();
    return !next.error;
  }

  async function prepareCaseCopilotResearch(input: CaseQuestionSubmitInput): Promise<boolean> {
    const instance = orchestrator.current;
    const expectedRevision = input.expectedCaseRevision ?? currentCopilotRevision();
    if (
      !instance ||
      expectedRevision === null ||
      !input.consentPublicResearch ||
      !input.acquisitionMode
    ) {
      return false;
    }
    const request = {
      focus: input.fieldKey,
      intent: "prepare_public_benchmark_research",
      requested_private_value: null,
      expected_case_revision: expectedRevision,
      acquisitionMode: input.acquisitionMode,
    } as const;
    if (
      input.acquisitionMode === "live_public_research" ||
      instance.getSnapshot().display.stage === "gate2_preview_ready"
    ) {
      await instance.launchCopilotResearchAndApproveGate2(request);
    } else {
      await instance.prepareCopilotResearch(request);
    }
    const next = instance.getSnapshot();
    if (next.error) throw next.error;
    return !next.error && (
      next.display.stage !== "gate2_preview_ready" ||
      input.acquisitionMode !== "live_public_research"
    );
  }

  async function selectCaseScenario(
    scenarioKey: NonNullable<FounderShellWorkspace["scenarios"]>["selected_scenario_key"],
  ): Promise<boolean> {
    const instance = orchestrator.current;
    const previousKey = instance?.getSnapshot().scenarios?.selected_scenario_key ?? null;
    if (!instance) return false;
    await instance.selectScenario(scenarioKey);
    const next = instance.getSnapshot();
    const nextSelectedKey =
      next.scenarios?.selected_scenario_key ?? next.selectedScenario?.scenario_key ?? null;
    return !next.error && nextSelectedKey === scenarioKey && nextSelectedKey !== previousKey;
  }

  function decideAdvisorImprovement(
    proposalId: string,
    decision: "accepted" | "rejected",
  ) {
    void orchestrator.current?.decideAdvisorImprovement(proposalId, decision);
  }

  function retryAdvisor() {
    void orchestrator.current?.retryAdvisor();
  }

  function generateLaunchPack() {
    void orchestrator.current?.generateLaunchPack();
  }

  function canGenerateLaunchPack() {
    return Boolean(
      snapshot?.caseId &&
        snapshot?.scenarios &&
        snapshot.scenarios.case_id === snapshot.caseId &&
        snapshot.scenarios.selected_scenario_key &&
        !snapshot.busy,
    );
  }

  function canGenerateFinalLaunchPack() {
    return canGenerateLaunchPack();
  }

  function prepareCaseAsset(asset: "interview" | "pricing" | "positioning" | "funnel") {
    const assetType = {
      funnel: "weekly_funnel_template",
      interview: "customer_interview_script",
      positioning: "positioning_map",
      pricing: "pricing_experiment",
    } as const;
    void orchestrator.current?.generateAsset(assetType[asset]);
  }

  const stage = snapshot?.display.stage ?? "idle";
  const report = validatedReport(snapshot);
  const reportState: FounderWorkspaceReportState | undefined = report
    ? {
        caseId: report.case_id,
        freezeAvailable:
          report.freeze_status !== "approved" && !snapshot?.busy,
        freezeApproved: report.freeze_status === "approved",
        htmlUrl: snapshot?.artifactUrls?.html,
        jsonUrl: snapshot?.artifactUrls?.json,
        pdfUrl: snapshot?.artifactUrls?.pdf,
        snapshotLabel: report.freeze_status === "approved" ? "Версия зафиксирована" : "Финальная версия отчёта",
        detail:
          report.freeze_status === "approved"
            ? "Версия зафиксирована. Форматы JSON, HTML и PDF связаны одним хешем."
            : "Проверьте черновик перед фиксацией неизменяемой версии.",
      }
    : undefined;

  if (activeRuntimeConfigError) {
    return (
      <div className="founder-workspace-runtime">
        <div className="workflow-signal workflow-signal--error" role="alert">
          Не удалось загрузить режим анализа. Проверьте FOUNDER_CASE_FIXTURE_MODE.
        </div>
      </div>
    );
  }

  if (runtimeMode === null) {
    return (
      <div className="founder-workspace-runtime">
        <div aria-live="polite" className="workflow-signal" role="status">
          Загружаю режим анализа…
        </div>
      </div>
    );
  }

  return (
    <div className="founder-workspace-runtime">
      <FounderShell
        onFilesSelected={handleFilesSelected}
        onFreezeReport={() => void orchestrator.current?.decideGate4("approved")}
        onGate2={handleGate2Decision}
        onGate3={handleGate3Decision}
        onInventoryChange={handleInventoryChange}
        onStartAnalysis={startAnalysis}
        onAdvisorAnswer={answerAdvisor}
        onAdvisorImprovementDecision={decideAdvisorImprovement}
        onAdvisorRetry={retryAdvisor}
        onCopilotAssumptionSubmit={saveCaseCopilotAssumption}
        onCopilotFactSubmit={saveCaseCopilotFact}
        onCopilotUnknownSubmit={sendCaseCopilotUnknown}
        onCopilotResearchPrepare={prepareCaseCopilotResearch}
        onPrepareAiAsset={canGenerateLaunchPack() ? prepareCaseAsset : undefined}
        onScenarioSelect={selectCaseScenario}
        onBuildWorkpack={canGenerateFinalLaunchPack() ? generateLaunchPack : undefined}
        workspace={{
          busy: snapshot?.busy ?? false,
          files,
          gtm: snapshot?.gtm ?? null,
          profile: snapshot?.profile ?? null,
          copilotState: snapshot?.copilotState ?? null,
          copilotThread: snapshot?.copilotThread ?? null,
          copilotValidationErrors: snapshot?.copilotValidationErrors ?? [],
          providerStatus: snapshot?.status?.provider_status ?? null,
          caseId: snapshot?.caseId ?? undefined,
          researchPlan: snapshot?.researchPlan ?? null,
          researchJob: snapshot?.researchJob ?? null,
          researchMetricComparison: snapshot?.researchMetricComparison ?? null,
          launchPack: snapshot?.launchPack ?? null,
          scenarios: snapshot?.scenarios ?? null,
          selectedScenario: snapshot?.selectedScenario ?? null,
          reportSnapshot: snapshot?.reportSnapshot ?? null,
          acceptedDocumentIds: snapshot?.acceptedDocumentIds ?? [],
          lastKnownStatus: snapshot?.status?.analysis_status ?? null,
          advisorQuestion: snapshot?.advisorQuestion ?? null,
          advisorAnswer: snapshot?.advisorAnswer ?? null,
          advisorImprovements: snapshot?.advisorImprovements ?? null,
          advisorDecision: snapshot?.advisorDecision ?? null,
          advisorError: snapshot?.advisorError ?? null,
          activity: snapshot?.activity ?? null,
          canApproveGate2:
            stage === "gate2_preview_ready" &&
            Boolean(snapshot?.gate2Preview?.resume_token) &&
            hasHydratedGate2Evidence(snapshot) &&
            !snapshot?.busy,
          canApproveGate3: stage === "gate3_review_required" && !snapshot?.busy,
          busyLabel: founderBusyLabel(
            snapshot?.activity ?? null,
            snapshot?.activeResearchAcquisitionMode ?? null,
          ),
          inventory,
          report: reportState,
          stage: founderShellStage(stage, files.length > 0),
        }}
      />
    </div>
  );
}
