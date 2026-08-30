"use client";

import Link from "next/link";
import Image from "next/image";
import {
  ArrowUpRight,
  BadgeCheck,
  Box,
  ChartNoAxesColumnIncreasing,
  ChartSpline,
  CircleDollarSign,
  CircleHelp,
  FileText,
  Flag,
  Info,
  Landmark,
  PieChart,
  Rocket,
  ShieldCheck,
  ShieldAlert,
  Sparkles,
  Users,
  WandSparkles,
  WalletCards,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import { FounderAdvisorPages } from "@/components/founder-advisor-pages";
import { FounderAnalysisPages } from "@/components/founder-analysis-pages";
import { CaseCopilotPanel } from "@/components/case-copilot-panel";
import type {
  CaseQuestionAnswerType,
  CaseQuestionSubmitInput,
} from "@/components/case-question-card";
import { FounderStrategyPages } from "@/components/founder-strategy-pages";
import { UploadEntry } from "@/components/upload-entry";
import founderIntelligenceMark from "@/components/founder-intelligence-mark.png";
import analysisStyles from "./founder-analysis-pages.module.css";
import copilotStyles from "./case-copilot-panel.module.css";
import {
  buildCaseCopilotSubmitPayload,
  defaultCaseCopilotPublicResearchMode,
} from "@/lib/case-copilot-presentation";
import { adminConsoleLinkForCase } from "@/lib/navigation";
import type {
  AdvisorAnswerResponse,
  AdvisorAnswerType,
  AdvisorImprovementDecisionResponse,
  AdvisorImprovementsResponse,
  AdvisorNextQuestionResponse,
  CaseMutationFieldError,
  CopilotStateResponse,
  CopilotThreadResponse,
  LaunchPackMetadataResponse,
  ProviderStatus,
  ResearchJobResponse,
  ResearchPlanResponse,
  RequestedResearchAcquisitionMode,
  ScenarioKey,
  ScenarioProjectionResponse,
  StartupScenarioVariant,
  StartupGtmResponse,
  StartupProfileResponse,
  StartupReportSnapshotResponse,
} from "@/lib/contracts";
import type { ScenarioMetricComparison } from "@/lib/scenario-presentation";
import {
  buildLocalInventory,
  type LocalFileInventoryItem,
} from "@/lib/upload";

export type FounderWorkspaceStage =
  | "idle"
  | "files_selected"
  | "analysis_running"
  | "primary_ready"
  | "deep_ready"
  | "error";

export type FounderWorkspaceReportState = Readonly<{
  caseId?: string;
  detail?: string;
  freezeApproved?: boolean;
  freezeAvailable?: boolean;
  htmlUrl?: string;
  jsonUrl?: string;
  pdfUrl?: string;
  snapshotLabel?: string;
}>;

export type FounderShellWorkspace = Readonly<{
  canApproveGate2?: boolean;
  canApproveGate3?: boolean;
  caseId?: string;
  files?: readonly File[];
  gtm?: StartupGtmResponse | null;
  profile?: StartupProfileResponse | null;
  reportSnapshot?: StartupReportSnapshotResponse | null;
  acceptedDocumentIds?: readonly string[];
  lastKnownStatus?: string | null;
  inventory?: readonly LocalFileInventoryItem[];
  report?: FounderWorkspaceReportState;
  stage?: FounderWorkspaceStage;
  advisorQuestion?: AdvisorNextQuestionResponse | null;
  advisorAnswer?: AdvisorAnswerResponse | null;
  advisorImprovements?: AdvisorImprovementsResponse | null;
  advisorDecision?: AdvisorImprovementDecisionResponse | null;
  advisorError?: Error | null;
  activity?: string | null;
  busy?: boolean;
  busyLabel?: string;
  copilotState?: CopilotStateResponse | null;
  copilotThread?: CopilotThreadResponse | null;
  copilotValidationErrors?: readonly CaseMutationFieldError[];
  providerStatus?: ProviderStatus | null;
  researchPlan?: ResearchPlanResponse | null;
  researchJob?: ResearchJobResponse | null;
  researchMetricComparison?: ScenarioMetricComparison | null;
  launchPack?: LaunchPackMetadataResponse | null;
  scenarios?: ScenarioProjectionResponse | null;
  selectedScenario?: StartupScenarioVariant | null;
}>;

export type FounderAdvisorAnswerInput = Readonly<{
  questionId: string;
  answerType: AdvisorAnswerType;
  manualValue: string;
  documentId: string | null;
  publicResearchConsent: boolean;
}>;

export type FounderShellProps = Readonly<{
  onFilesSelected?: (files: File[]) => void;
  onFreezeReport?: () => void;
  onGate2?: (decision: "approved" | "denied") => Promise<boolean>;
  onGate3?: () => Promise<boolean>;
  onInventoryChange?: (inventory: LocalFileInventoryItem[]) => void;
  onStartAnalysis?: (files: readonly File[]) => Promise<boolean | void> | boolean | void;
  onAdvisorAnswer?: (input: FounderAdvisorAnswerInput) => Promise<boolean> | boolean;
  onAdvisorImprovementDecision?: (
    proposalId: string,
    decision: "accepted" | "rejected",
  ) => void;
  onAdvisorRetry?: () => void;
  onCopilotAssumptionSubmit?: (input: CaseQuestionSubmitInput) => Promise<boolean> | boolean;
  onCopilotFactSubmit?: (input: CaseQuestionSubmitInput) => Promise<boolean> | boolean;
  onCopilotResearchPrepare?: (input: CaseQuestionSubmitInput) => Promise<boolean> | boolean;
  onCopilotUnknownSubmit?: (input: CaseQuestionSubmitInput) => Promise<boolean> | boolean;
  onScenarioSelect?: (scenarioKey: ScenarioKey) => Promise<boolean> | boolean;
  onPrepareAiAsset?: (asset: "interview" | "pricing" | "positioning" | "funnel") => void;
  onBuildWorkpack?: () => void;
  workspace?: FounderShellWorkspace;
}>;

type FounderShellView =
  | "dashboard"
  | "data_room"
  | "progress_gate2"
  | "overview"
  | "metrics"
  | "market"
  | "risks"
  | "action_plan"
  | "report_center"
  | "advisor_next_question"
  | "advisor_answer"
  | "advisor_updated_analysis"
  | "advisor_improved_plan";

export type CaseCopilotContextFocus = Readonly<{
  page: FounderShellView;
  focusKey: string;
  label: string;
}>;

const sidebarItems = [
  ["Обзор", "dashboard", Landmark],
  ["Новый анализ", "data_room", CircleDollarSign],
  ["Метрики", "metrics", ChartNoAxesColumnIncreasing],
  ["Рынок", "market", PieChart],
  ["Риски", "risks", ShieldAlert],
  ["План действий", "action_plan", Flag],
  ["Отчёты", "report_center", FileText],
] as const satisfies readonly (readonly [
  string,
  FounderShellView,
  LucideIcon,
])[];

const quickInsights = [
  [
    "Понятный профиль",
    "ИИ выделит продукт, клиента, рынок, модель выручки и текущие риски.",
    BadgeCheck,
    "profile",
  ],
  [
    "Метрики и точки усиления",
    "Система покажет, что уже можно рассчитать и какие данные усилят вывод.",
    ChartSpline,
    "metric",
  ],
  [
    "План улучшений",
    "После анализа появятся конкретные шаги, вопросы и безопасные варианты ресерча.",
    WandSparkles,
    "plan",
  ],
] as const satisfies readonly (readonly [string, string, LucideIcon, string])[];

const advisorViews = new Set<FounderShellView>([
  "advisor_next_question",
  "advisor_answer",
  "advisor_updated_analysis",
  "advisor_improved_plan",
]);

function inventoryIdForFile(file: File): string {
  return (
    buildLocalInventory([file])[0]?.id ??
    `${file.lastModified}-${file.name}-${file.size}`
  );
}

function advisorAnswerTransitionKey(
  answer: AdvisorAnswerResponse | null | undefined,
): string | null {
  if (!answer || answer.status !== "applied") {
    return null;
  }
  return [
    answer.case_id,
    answer.question_id,
    answer.answered_count,
    answer.confidence_delta,
  ].join(":");
}

function founderSafeCaseName(workspace?: FounderShellWorkspace): string {
  const name = workspace?.profile?.fields.startup_name.values[0];
  const trimmed = typeof name === "string" ? name.trim() : "";
  const blockedAbsentToken = "MIS" + "SING";
  const unsafeCaseNamePattern = new RegExp(
    `(?:\\b${blockedAbsentToken}\\b|sha256:|profile_hash|snapshot_hash|[A-Za-z]:[\\\\/]|token|secret)`,
    "iu",
  );
  if (!trimmed || unsafeCaseNamePattern.test(trimmed)) {
    return "Проект после анализа";
  }
  return trimmed.length > 80 ? `${trimmed.slice(0, 77)}...` : trimmed;
}

export function FounderShell({
  onFilesSelected,
  onFreezeReport,
  onGate2,
  onGate3,
  onInventoryChange,
  onStartAnalysis,
  onAdvisorAnswer,
  onAdvisorImprovementDecision,
  onAdvisorRetry,
  onCopilotAssumptionSubmit,
  onCopilotFactSubmit,
  onCopilotResearchPrepare,
  onCopilotUnknownSubmit,
  onScenarioSelect,
  onPrepareAiAsset,
  onBuildWorkpack,
  workspace,
}: FounderShellProps = {}) {
  const [localInventory, setLocalInventory] = useState<LocalFileInventoryItem[]>([]);
  const [localFiles, setLocalFiles] = useState<File[]>([]);
  const inventory = workspace?.inventory ?? localInventory;
  const files = workspace?.files ?? localFiles;
  const hasFiles = inventory.length > 0;
  const stage = workspace?.stage ?? (hasFiles ? "files_selected" : "idle");
  const safeCaseName = founderSafeCaseName(workspace);
  const adminConsoleLink = adminConsoleLinkForCase(workspace?.caseId);

  function handleInventoryChange(nextInventory: LocalFileInventoryItem[]) {
    if (!workspace?.inventory) {
      setLocalInventory(nextInventory);
    }
    if (!workspace?.files) {
      const nextIds = new Set(nextInventory.map((item) => item.id));
      setLocalFiles((currentFiles) =>
        currentFiles.filter((file) => nextIds.has(inventoryIdForFile(file))),
      );
    }
    onInventoryChange?.(nextInventory);
  }

  function handleFilesSelected(selectedFiles: File[]) {
    if (!workspace?.files) {
      setLocalFiles((currentFiles) => {
        const byId = new Map(
          currentFiles.map((file) => [inventoryIdForFile(file), file]),
        );
        selectedFiles.forEach((file) => {
          byId.set(inventoryIdForFile(file), file);
        });
        return Array.from(byId.values());
      });
    }
    onFilesSelected?.(selectedFiles);
  }

  async function handleStartAnalysis() {
    if (files.length === 0) return;
    const accepted = await onStartAnalysis?.(files);
    if (accepted !== false) {
      openView("progress_gate2", "Новый анализ");
    }
  }

  async function handleGate2Approval() {
    const accepted = await onGate2?.("approved");
    if (accepted) {
      openView("overview", "Обзор");
    }
  }

  function handleGate2Decision(decision: "approved" | "denied") {
    if (decision === "approved") {
      void handleGate2Approval();
      return;
    }
    void onGate2?.("denied");
  }

  async function handleGate3Approval() {
    const accepted = await onGate3?.();
    if (accepted) {
      openView("report_center", "Отчёты");
    }
  }

  async function handleAdvisorAnswer(input: FounderAdvisorAnswerInput) {
    const accepted = await onAdvisorAnswer?.(input);
    if (accepted) {
      openView("advisor_updated_analysis", "Советник");
    }
    return Boolean(accepted);
  }

  const coverageCards = [
    ["Продукт", hasFiles ? "На проверке" : "После загрузки", hasFiles ? "partial" : "empty", Box],
    ["Клиенты", hasFiles ? "На проверке" : "После загрузки", hasFiles ? "partial" : "empty", Users],
    ["Финансы", hasFiles ? "На проверке" : "После загрузки", hasFiles ? "partial" : "empty", WalletCards],
    ["Рынок", hasFiles ? "На проверке" : "После загрузки", hasFiles ? "partial" : "empty", ChartSpline],
  ] as const satisfies readonly (readonly [string, string, string, LucideIcon])[];
  const [selectedView, setActiveView] = useState<FounderShellView>("dashboard");
  const [selectedNavLabel, setSelectedNavLabel] = useState("Обзор");
  const [caseCopilotOpen, setCaseCopilotOpen] = useState(false);
  const [caseCopilotFocus, setCaseCopilotFocus] = useState(0);
  const [caseCopilotPreferredAnswerType, setCaseCopilotPreferredAnswerType] =
    useState<CaseQuestionAnswerType>("manual");
  const [caseCopilotContext, setCaseCopilotContext] =
    useState<CaseCopilotContextFocus>({
      page: "dashboard",
      focusKey: "dashboard",
      label: "Обзор",
    });
  const [privacyMode, setPrivacyMode] = useState<
    "local_documents" | "research_prepared"
  >("local_documents");
  const currentAdvisorAnswerKey = advisorAnswerTransitionKey(
    workspace?.advisorAnswer,
  );
  const advisorQuestionId =
    workspace?.advisorQuestion?.next_question?.question_id.trim();
  const canOpenCaseCopilot = Boolean(
    workspace?.copilotState || workspace?.copilotThread || advisorQuestionId,
  );
  const activeView =
    selectedView === "advisor_answer" && currentAdvisorAnswerKey
      ? "advisor_updated_analysis"
      : selectedView === "dashboard" && stage === "primary_ready"
        ? "progress_gate2"
      : selectedView === "dashboard" && stage === "deep_ready"
        ? "overview"
        : selectedView;
  const activeNavLabel = activeView === "advisor_updated_analysis"
    ? "Обзор"
    : activeView === "advisor_improved_plan"
      ? "План действий"
      : selectedNavLabel;
  function resolveSidebarView(view: FounderShellView): FounderShellView {
    if (
      stage === "primary_ready" &&
      (view === "dashboard" || view === "data_room" || view === "report_center")
    ) {
      return "progress_gate2";
    }
    if (view === "report_center" && workspace?.canApproveGate3) {
      return "action_plan";
    }
    if (view === "dashboard" && stage === "deep_ready") {
      return "overview";
    }
    return view;
  }

  const activeSidebarView = activeView === "advisor_updated_analysis"
    ? resolveSidebarView("dashboard")
    : activeView === "advisor_improved_plan"
      ? "action_plan"
      : advisorViews.has(activeView)
        ? null
        : activeView === "progress_gate2"
      ? "data_room"
      : activeView === "overview"
        ? "overview"
        : activeView;

  function openView(view: FounderShellView, navLabel?: string) {
    setCaseCopilotOpen(false);
    setActiveView(view);
    if (navLabel) {
      setSelectedNavLabel(navLabel);
    }
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }

  function openDataRoom() {
    openView("data_room", "Новый анализ");
  }

  function openAdvisorOrDataRoom() {
    if (canOpenCaseCopilot) {
      openCaseCopilot();
    }
  }

  function openCaseCopilot() {
    setCaseCopilotPreferredAnswerType("manual");
    setCaseCopilotContext({
      page: activeView,
      focusKey: activeView,
      label: activeNavLabel,
    });
    setCaseCopilotOpen(true);
    setCaseCopilotFocus((value) => value + 1);
  }

  function openCaseCopilotForQuestion(question: string) {
    setCaseCopilotPreferredAnswerType("manual");
    setCaseCopilotContext({
      page: "risks",
      focusKey: `risk-question:${question}`,
      label: `Риски → ${question}`,
    });
    setCaseCopilotOpen(true);
    setCaseCopilotFocus((value) => value + 1);
  }

  function openCaseCopilotForResearch() {
    setCaseCopilotPreferredAnswerType("public_research");
    setCaseCopilotContext({
      page: activeView,
      focusKey: `${activeView}:public-research`,
      label: `${activeNavLabel} → онлайн-ресерч`,
    });
    setCaseCopilotOpen(true);
    setCaseCopilotFocus((value) => value + 1);
  }

  function openRiskEvidence() {
    if (stage === "primary_ready") {
      openView("progress_gate2", "Новый анализ");
      return;
    }
    openView("overview", "Обзор");
  }

  function openPlanOrDataRoom() {
    if (stage === "deep_ready") {
      openView("action_plan", "План действий");
      return;
    }
    openDataRoom();
  }

  function openReportOrDataRoom() {
    if (workspace?.canApproveGate3) {
      openView("action_plan", "План действий");
      return;
    }
    if (workspace?.reportSnapshot) {
      openView("report_center", "Отчёты");
      return;
    }
    if (stage === "primary_ready") {
      openView("progress_gate2", "Новый анализ");
      return;
    }
    openDataRoom();
  }

  function openAnalysisOrDataRoom() {
    if (stage === "primary_ready") {
      openView("progress_gate2", "Новый анализ");
      return;
    }
    if (stage === "deep_ready") {
      openView("overview", "Обзор");
      return;
    }
    if (stage === "analysis_running") {
      openView("progress_gate2", "Новый анализ");
      return;
    }
    openDataRoom();
  }

  async function requestSafeResearch(
    acquisitionMode?: RequestedResearchAcquisitionMode,
  ): Promise<boolean> {
    setCaseCopilotOpen(true);
    const actions = workspace?.copilotState?.actions ?? [];
    const publicResearchAction = actions.find((action) => action.action === "prepare_public_research");
    if (
      !onCopilotResearchPrepare ||
      !publicResearchAction ||
      publicResearchAction.status !== "requires_consent" ||
      typeof publicResearchAction.payload.focus !== "string" ||
      !Number.isInteger(publicResearchAction.payload.expected_case_revision) ||
      workspace?.busy
    ) {
      return false;
    }
    const researchAcquisitionMode =
      acquisitionMode ?? defaultCaseCopilotPublicResearchMode(publicResearchAction);
    const payload: CaseQuestionSubmitInput = {
      ...buildCaseCopilotSubmitPayload({
        acquisitionMode: researchAcquisitionMode,
        actions,
        answerType: "public_research",
        manualDraft: "",
        consentPublicResearch: true,
      }),
      amount: "",
      currency: "",
      declaredSource: "",
      periodMonth: "",
      rationale: "",
      scale: "",
      validationPlan: "",
      questionDescriptor: workspace?.copilotState?.question_descriptor ?? null,
    };
    const accepted = await onCopilotResearchPrepare?.(payload);
    if (accepted) {
      setPrivacyMode("research_prepared");
    }
    return accepted;
  }

  return (
    <div
      className={`founder-shell founder-dashboard-shell ${copilotStyles.shellWithCopilot} ${caseCopilotOpen ? "" : copilotStyles.shellCopilotClosed} ${activeView === "progress_gate2" ? analysisStyles.progressGate2Shell : ""}`}
      data-founder-active-view={activeView}
    >
      <aside className="founder-sidebar" aria-label="Навигация по аналитике для основателя">
        <Link className="founder-sidebar__brand" href="/" aria-label="Аналитика для основателя">
          <span className="founder-logo" aria-hidden="true">
            <Image
              alt=""
              height={34}
              priority
              src={founderIntelligenceMark}
              width={34}
            />
          </span>
          <span>Founder<br />Intelligence</span>
        </Link>
        {workspace?.caseId ? (
          <section
            aria-label="Идентификатор текущего кейса"
            className="founder-case-identity"
            data-founder-case-identity
          >
            <span>Текущий проект</span>
            <strong>{safeCaseName}</strong>
            <code>{workspace.caseId}</code>
            <Link href={adminConsoleLink.href}>Открыть в Admin</Link>
          </section>
        ) : null}
        <nav aria-label="Главная навигация" className="founder-sidebar__nav">
          {sidebarItems.map(([label, view, Icon]) => {
            const resolvedView = resolveSidebarView(view);
            const isActive = activeView === "progress_gate2"
              ? view === "data_room"
              : activeSidebarView === resolvedView && activeNavLabel === label;
            return (
              <button
                aria-current={isActive ? "page" : undefined}
                className={isActive ? "is-active" : ""}
                key={label}
                onClick={() => openView(resolvedView, label)}
                type="button"
              >
                <Icon aria-hidden="true" size={22} strokeWidth={1.75} />
                {label}
              </button>
            );
          })}
        </nav>
        <div className="founder-sidebar__footer">
          <button
            aria-label="Настройки пока недоступны"
            disabled
            type="button"
          >
            <Info aria-hidden="true" size={22} strokeWidth={1.75} />
            Настройки
          </button>
          <button
            aria-label="Помощь пока недоступна"
            disabled
            type="button"
          >
            <CircleHelp aria-hidden="true" size={22} strokeWidth={1.75} />
            Помощь
          </button>
        </div>
      </aside>

      <main className="founder-dashboard-main" id="new-analysis">
        {activeView === "dashboard" ? (
          <section className="founder-dashboard-hero founder-dashboard-hero--overview">
            <div className="founder-dashboard-title-row">
              <h1>Добро пожаловать</h1>
              <p>Превратим материалы стартапа в понятный план роста</p>
            </div>
            <button
              className="founder-ask-bar founder-ask-bar--full"
              disabled={!canOpenCaseCopilot}
              onClick={canOpenCaseCopilot ? openAdvisorOrDataRoom : undefined}
              type="button"
            >
              <Sparkles
                aria-hidden="true"
                className="founder-ask-bar__spark"
                size={24}
                strokeWidth={1.7}
              />
              <span>Спросить ИИ-советника</span>
              <strong>Получить рекомендацию</strong>
              <ArrowUpRight
                aria-hidden="true"
                className="founder-ask-bar__arrow"
                size={22}
                strokeWidth={1.8}
              />
            </button>
          </section>
        ) : null}

        {activeView === "dashboard" ? (
          <section
            aria-label="Рабочий стол анализа"
            className="founder-view dashboard-grid dashboard-grid--start"
            data-founder-view="dashboard"
          >
            <div className="dashboard-card dashboard-card--upload" id="upload">
              <UploadEntry
                busy={workspace?.busy}
                busyLabel={workspace?.busyLabel}
                inventory={inventory}
                onFilesSelected={handleFilesSelected}
                onInventoryChange={handleInventoryChange}
                onStartAnalysis={onStartAnalysis ? handleStartAnalysis : undefined}
                variant="dashboard"
              />
            </div>

            <article className="dashboard-card dashboard-card--project">
              <span>Что станет яснее</span>
              <div className="project-summary">
                <div className="project-mark" aria-hidden="true">
                  <Rocket aria-hidden="true" strokeWidth={1.8} />
                </div>
                <div>
                  <h2>Первичный профиль без лишних настроек</h2>
                  <p>
                    Добавьте материалы — я смогу уточнить продукт и аудиторию,
                    рассчитать проверяемые метрики и обозначить риски.
                    Либо, после вашего разрешения, могу найти публичные источники.
                  </p>
                </div>
              </div>
              <ul className="project-outcomes">
                <li><span><strong>Продукт и клиент</strong> — только по содержанию файлов</span></li>
                <li><span><strong>Метрики</strong> — расчёт или честная отметка о данных</span></li>
                <li><span><strong>Следующий вопрос</strong> — один, с максимальным влиянием</span></li>
              </ul>
            </article>

            <div className="dashboard-bottom-row" data-dashboard-bottom-row="three-columns">
              <section className="dashboard-card dashboard-card--insights" id="overview">
                <h2>Что вы получите</h2>
                <ul>
                  {quickInsights.map(([title, detail, Icon, tone]) => (
                    <li key={title}>
                      <span className="dashboard-insight-icon" data-tone={tone}>
                        <Icon aria-hidden="true" size={19} strokeWidth={1.8} />
                      </span>
                      <div>
                        <strong>{title}</strong>
                        <p>{detail}</p>
                      </div>
                    </li>
                  ))}
                </ul>
                <button
                  className="dashboard-pink-link"
                  onClick={() => openView("metrics", "Метрики")}
                  type="button"
                >
                  Смотреть все выводы
                </button>
              </section>

              <section className="dashboard-card dashboard-card--next">
                <h2>Следующий лучший шаг</h2>
                <p>
                  Загрузить бизнес-план, презентацию или заметки — после этого
                  ИИ соберёт профиль и покажет, что улучшить в проекте.
                </p>
                <button
                  className="button button--primary"
                  onClick={openPlanOrDataRoom}
                  type="button"
                >
                  {stage === "deep_ready" ? "Открыть план" : "Добавить материалы"}
                </button>
                <button
                  className="dashboard-soft-pink-button"
                  onClick={openReportOrDataRoom}
                  type="button"
                >
                  Центр отчётов
                </button>
              </section>

              <section className="dashboard-card dashboard-card--recent">
                <h2>История анализов</h2>
                <div className="recent-empty-state">
                  <strong>История появится после первого анализа</strong>
                  <p>
                    Здесь будут сохранённые кейсы, отчёты и принятые версии
                    плана. Сейчас список честно пуст.
                  </p>
                </div>
              </section>
            </div>
          </section>
        ) : null}

        {activeView === "data_room" ? (
          <section
            aria-label="Новый анализ и материалы проекта"
            className="founder-view data-room-layout"
            data-founder-view="data-room"
          >
            <header className="data-room-header">
              <h1>Новый анализ</h1>
              <p>Добавьте всё, что уже есть — система сама определит модель бизнеса и нужные проверки</p>
            </header>
            <div className="dashboard-card data-room-card">
              <div className="dashboard-section-title">
                <h2>Материалы проекта</h2>
              </div>
              <div className="data-room-upload">
                <UploadEntry
                  busy={workspace?.busy}
                  busyLabel={workspace?.busyLabel}
                  inventory={inventory}
                  onFilesSelected={handleFilesSelected}
                  onInventoryChange={handleInventoryChange}
                  variant="data-room"
                />
              </div>
              <p className="data-room-note">
                Неполный набор допустим — анализ начнётся с доступных данных.
              </p>
            </div>

            <aside className="data-room-side">
              <section className="dashboard-card coverage-card">
                <h2>Покрытие проекта</h2>
                <div className="coverage-grid">
                  {coverageCards.map(([label, status, tone, Icon]) => (
                    <article data-coverage-tone={tone} key={label}>
                      <div className="coverage-card-title">
                        <Icon aria-hidden="true" size={24} strokeWidth={1.65} />
                        <strong>{label}</strong>
                      </div>
                      <span className="coverage-card-status">{status}</span>
                    </article>
                  ))}
                </div>
              </section>

              <section className="dashboard-card privacy-card">
                <h2>Контроль приватности</h2>
                <div className="privacy-card-intro">
                  <span className="privacy-card-shield" aria-hidden="true">
                    <ShieldCheck size={34} strokeWidth={1.55} />
                  </span>
                  <p>
                    Документы остаются локально. Для внешнего исследования
                    используются только очищенные факты после вашего разрешения.
                  </p>
                </div>
                <button
                  aria-pressed={privacyMode === "research_prepared"}
                  className={`button button--primary privacy-choice ${
                    privacyMode === "research_prepared" ? "is-selected" : ""
                  }`}
                  onClick={() => setPrivacyMode("research_prepared")}
                  type="button"
                >
                  Подготовить безопасный ресерч
                </button>
                <button
                  aria-pressed={privacyMode === "local_documents"}
                  className={`button button--secondary privacy-choice ${
                    privacyMode === "local_documents" ? "is-selected" : ""
                  }`}
                  onClick={() => setPrivacyMode("local_documents")}
                  type="button"
                >
                  Продолжить без интернета
                </button>
                <strong>
                  {privacyMode === "research_prepared"
                    ? "Согласие спросим отдельно перед публичным поиском"
                    : "Публичный поиск выключен"}
                </strong>
                <div className="privacy-protection-status">
                  <ShieldCheck aria-hidden="true" size={20} strokeWidth={1.75} />
                  Личные данные защищены
                </div>
              </section>
              {hasFiles ? (
                <button
                  className="button button--primary data-room-primary-cta"
                  disabled={workspace?.busy}
                  onClick={handleStartAnalysis}
                  type="button"
                >
                  {workspace?.busy ? workspace.busyLabel ?? "Идёт обработка…" : "Начать анализ"}
                </button>
              ) : null}
            </aside>
          </section>
        ) : null}

        {activeView === "progress_gate2" ? (
          <section className="founder-view" data-founder-view="progress-gate2">
            <FounderAnalysisPages
              onAddEvidence={openDataRoom}
              onOpenAdvisor={openCaseCopilot}
              onOpenResearch={openCaseCopilotForResearch}
              onOpenMarket={() => openView("market", "Рынок")}
              onOpenMetrics={() => openView("metrics", "Метрики")}
              onOpenReport={() => openView("report_center", "Отчёты")}
              onGate2={handleGate2Decision}
              page="progress_gate2"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "overview" ? (
          <section className="founder-view" data-founder-view="overview">
            <FounderAnalysisPages
              onAddEvidence={openDataRoom}
              onOpenAdvisor={openCaseCopilot}
              onOpenMarket={() => openView("market", "Рынок")}
              onOpenMetrics={() => openView("metrics", "Метрики")}
              onOpenReport={() => openView("report_center", "Отчёты")}
              page="overview"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "metrics" ? (
          <section className="founder-view" data-founder-view="metrics">
            <FounderAnalysisPages
              onAddEvidence={openDataRoom}
              onOpenAdvisor={openCaseCopilot}
              onOpenMarket={() => openView("market", "Рынок")}
              onOpenMetrics={() => openView("metrics", "Метрики")}
              onOpenReport={() => openView("report_center", "Отчёты")}
              page="metrics"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "market" ? (
          <section className="founder-view" data-founder-view="market">
            <FounderStrategyPages
              onAllowResearch={requestSafeResearch}
              page="market"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "risks" ? (
          <section className="founder-view" data-founder-view="risks">
            <FounderStrategyPages
              onAddEvidence={openDataRoom}
              onAllowResearch={requestSafeResearch}
              onAnswerQuestion={openCaseCopilotForQuestion}
              onDiscussRisk={openCaseCopilot}
              onShowEvidence={openRiskEvidence}
              page="risks"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "action_plan" ? (
          <section className="founder-view" data-founder-view="action-plan">
            <FounderStrategyPages
              onAcceptDirection={
                workspace?.canApproveGate3 ? handleGate3Approval : undefined
              }
              onBuildWorkpack={onBuildWorkpack}
              onPrepareAiAsset={onPrepareAiAsset}
              onSuggestAlternative={openCaseCopilot}
              page="action_plan"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "report_center" ? (
          <section className="founder-view report-center-layout" data-founder-view="report-center">
            <FounderStrategyPages
              onBackToAnalysis={openAnalysisOrDataRoom}
              onFreezeReport={onFreezeReport}
              onOpenActionPlan={() => openView("action_plan", "План действий")}
              onOpenOverview={() => openView("overview", "Обзор")}
              page="report_center"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "advisor_next_question" ? (
          <section className="founder-view advisor-view-shell" data-founder-view="advisor-next-question">
            <FounderAdvisorPages
              onAdvisorAnswer={handleAdvisorAnswer}
              onAdvisorImprovementDecision={onAdvisorImprovementDecision}
              onAdvisorRetry={onAdvisorRetry}
              onBackToQuestion={openCaseCopilot}
              onOpenImprovedPlan={() => openView("advisor_improved_plan", "Советник")}
              page="advisor_next_question"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "advisor_answer" ? (
          <section className="founder-view advisor-view-shell" data-founder-view="advisor-answer">
            <FounderAdvisorPages
              onAdvisorAnswer={handleAdvisorAnswer}
              onAdvisorImprovementDecision={onAdvisorImprovementDecision}
              onAdvisorRetry={onAdvisorRetry}
              onBackToQuestion={openCaseCopilot}
              onOpenImprovedPlan={() => openView("advisor_improved_plan", "Советник")}
              page="advisor_answer"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "advisor_updated_analysis" ? (
          <section className="founder-view advisor-view-shell" data-founder-view="advisor-updated-analysis">
            <FounderAdvisorPages
              onAdvisorAnswer={handleAdvisorAnswer}
              onAdvisorImprovementDecision={onAdvisorImprovementDecision}
              onAdvisorRetry={onAdvisorRetry}
              onBackToQuestion={openCaseCopilot}
              onContinueRecalculation={() => openView("progress_gate2", "Новый анализ")}
              onOpenImprovedPlan={() => openView("advisor_improved_plan", "Советник")}
              page="advisor_updated_analysis"
              workspace={workspace}
            />
          </section>
        ) : null}

        {activeView === "advisor_improved_plan" ? (
          <section className="founder-view advisor-view-shell" data-founder-view="advisor-improved-plan">
            <FounderAdvisorPages
              onAdvisorAnswer={handleAdvisorAnswer}
              onAdvisorImprovementDecision={onAdvisorImprovementDecision}
              onAdvisorRetry={onAdvisorRetry}
              onBackToQuestion={openCaseCopilot}
              onOpenImprovedPlan={() => openView("advisor_improved_plan", "Советник")}
              page="advisor_improved_plan"
              workspace={workspace}
            />
          </section>
        ) : null}

      </main>
      {workspace?.busy ? (
        <div
          aria-busy={workspace?.busy ?? false}
          aria-live="polite"
          className="founder-global-busy"
          role="status"
        >
          <span aria-hidden="true" className="founder-global-busy__spinner" />
          <span>{workspace?.busyLabel ?? "Загружаю…"}</span>
        </div>
      ) : null}
      <CaseCopilotPanel
        busy={workspace?.busy}
        caseName={safeCaseName}
        copilotState={workspace?.copilotState ?? null}
        copilotThread={workspace?.copilotThread ?? null}
        contextFocus={caseCopilotContext}
        focusToken={caseCopilotFocus}
        onAssumptionSubmit={onCopilotAssumptionSubmit}
        onClose={() => setCaseCopilotOpen((value) => !value)}
        onDocumentRequested={openDataRoom}
        onFactSubmit={onCopilotFactSubmit}
        onResearchPrepare={onCopilotResearchPrepare}
        onScenarioSelect={onScenarioSelect}
        onUnknownSubmit={onCopilotUnknownSubmit}
        open={caseCopilotOpen}
        preferredAnswerType={caseCopilotPreferredAnswerType}
        providerStatus={workspace?.providerStatus ?? null}
        researchJob={workspace?.researchJob ?? null}
        researchMetricComparison={workspace?.researchMetricComparison ?? null}
        researchPlan={workspace?.researchPlan ?? null}
        scenarios={workspace?.scenarios ?? null}
        selectedScenario={workspace?.selectedScenario ?? null}
        validationErrors={workspace?.copilotValidationErrors ?? []}
      />
    </div>
  );
}
