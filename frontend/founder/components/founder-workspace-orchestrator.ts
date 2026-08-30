import {
  createCase,
  decideAdvisorImprovement,
  decideGate2,
  decideGate3,
  decideGate4,
  downloadReportArtifact,
  generateLaunchPack,
  getAdvisorImprovements,
  getAdvisorNextQuestion,
  getCopilotThread,
  getCopilotState,
  getResearchJob,
  FounderApiClientError,
  listCaseAssets,
  getCase,
  getGate2Preview,
  getReport,
  getScenarios,
  getStartupGtm,
  getStartupProfile,
  getStartupReportSnapshot,
  postCopilotMessage,
  prepareResearchPlan,
  queueResearchJob,
  reportArtifactUrl,
  saveAssumption,
  saveFounderFact,
  selectScenario,
  uploadDocuments,
  submitAdvisorAnswer,
  type AdvisorAnswerRequest,
  type AdvisorImprovementDecision,
  type FounderApiRequestOptions,
  type GenerateLaunchPackRequest,
  type PostCopilotMessageRequest,
  type PrepareResearchPlanRequest,
  type QueueResearchJobRequest,
  type ReportArtifact,
  type SaveAssumptionRequest,
  type SelectScenarioRequest,
  type SaveFounderFactRequest,
  type StartupDocumentUpload,
  type StartupGate2Decision,
  type StartupGate3Decision,
  type StartupGate4Decision,
} from "../lib/founder-api-client.ts";
import type {
  AdvisorAnswerResponse,
  AdvisorImprovementDecisionResponse,
  AdvisorImprovementsResponse,
  AdvisorNextQuestionResponse,
  CaseAssetListResponse,
  CaseMutationFieldError,
  CopilotAcceptedInputProjection,
  CopilotCoverageProjection,
  CopilotStateResponse,
  CopilotThreadResponse,
  CopilotTurnResponse,
  AssumptionOutcomeResponse,
  FactMutationResponse,
  LaunchPackMetadataResponse,
  ResearchJobResponse,
  ResearchPlanResponse,
  RequestedResearchAcquisitionMode,
  ScenarioKey,
  ScenarioProjectionResponse,
  StartupCaseReport,
  StartupCaseStatus,
  StartupCreateRequest,
  StartupCreateResponse,
  StartupDecisionResult,
  StartupGate2Preview,
  StartupGtmResponse,
  StartupProfileResponse,
  StartupReportSnapshotResponse,
  StartupUploadResponse,
} from "../lib/contracts.ts";
import {
  deriveFounderDisplayState,
  deriveNextAction,
  derivePollingDecision,
  type FounderClientActivity,
  type FounderDisplayState,
  type FounderNextAction,
  type FounderWorkflowStage,
} from "../lib/startup-state-machine.ts";
import {
  compareScenarioMetricChanges,
  type ScenarioMetricComparison,
} from "../lib/scenario-presentation.ts";
import { isFounderCaseId } from "../lib/founder-case-storage.ts";

export { normalizeFounderCaseFixtureMode } from "../lib/runtime-config.ts";

export type FounderShellVisualStage =
  | "idle"
  | "files_selected"
  | "analysis_running"
  | "primary_ready"
  | "deep_ready"
  | "error";

export type FounderWorkspaceApi = Readonly<{
  createCase: (
    request: StartupCreateRequest,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupCreateResponse>;
  uploadDocuments: (
    caseId: string,
    request: StartupDocumentUpload,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupUploadResponse>;
  getCase: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupCaseStatus>;
  getGate2Preview: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupGate2Preview>;
  getStartupGtm: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupGtmResponse>;
  getStartupProfile: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupProfileResponse>;
  getCopilotState?: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<CopilotStateResponse>;
  getCopilotThread?: (
    caseId: string,
    threadId?: string | null,
    options?: FounderApiRequestOptions,
  ) => Promise<CopilotThreadResponse>;
  postCopilotMessage?: (
    caseId: string,
    request: PostCopilotMessageRequest,
    options?: FounderApiRequestOptions,
  ) => Promise<CopilotTurnResponse>;
  saveFounderFact?: (
    caseId: string,
    request: SaveFounderFactRequest,
    options?: FounderApiRequestOptions,
  ) => Promise<FactMutationResponse>;
  saveAssumption?: (
    caseId: string,
    request: SaveAssumptionRequest,
    options?: FounderApiRequestOptions,
  ) => Promise<AssumptionOutcomeResponse>;
  getScenarios?: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<ScenarioProjectionResponse>;
  selectScenario?: (
    caseId: string,
    request: SelectScenarioRequest,
    options?: FounderApiRequestOptions,
  ) => Promise<Readonly<{
    case_id: string;
    data_revision: number;
    scenario_set_id: string;
    old_scenario_key: ScenarioKey;
    new_scenario_key: ScenarioKey;
    changed_keys: readonly string[];
  }>>;
  generateLaunchPack?: (
    caseId: string,
    request: GenerateLaunchPackRequest,
    options?: FounderApiRequestOptions,
  ) => Promise<LaunchPackMetadataResponse>;
  listCaseAssets?: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<CaseAssetListResponse>;
  prepareResearchPlan?: (
    caseId: string,
    request: PrepareResearchPlanRequest,
    options?: FounderApiRequestOptions,
  ) => Promise<ResearchPlanResponse>;
  queueResearchJob?: (
    caseId: string,
    request: QueueResearchJobRequest,
    options?: FounderApiRequestOptions,
  ) => Promise<ResearchJobResponse>;
  getResearchJob?: (
    caseId: string,
    jobId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<ResearchJobResponse>;
  getStartupReportSnapshot: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupReportSnapshotResponse>;
  getAdvisorNextQuestion: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<AdvisorNextQuestionResponse>;
  submitAdvisorAnswer: (
    caseId: string,
    request: AdvisorAnswerRequest,
    options?: FounderApiRequestOptions,
  ) => Promise<AdvisorAnswerResponse>;
  getAdvisorImprovements: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<AdvisorImprovementsResponse>;
  decideAdvisorImprovement: (
    caseId: string,
    proposalId: string,
    decision: AdvisorImprovementDecision,
    options?: FounderApiRequestOptions,
  ) => Promise<AdvisorImprovementDecisionResponse>;
  decideGate2: (
    caseId: string,
    request: StartupGate2Decision,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupDecisionResult>;
  decideGate3: (
    caseId: string,
    request: StartupGate3Decision,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupDecisionResult>;
  decideGate4: (
    caseId: string,
    request: StartupGate4Decision,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupDecisionResult>;
  getReport: (
    caseId: string,
    options?: FounderApiRequestOptions,
  ) => Promise<StartupCaseReport>;
  downloadReportArtifact: (
    caseId: string,
    artifact: ReportArtifact,
    options?: FounderApiRequestOptions,
  ) => Promise<Response>;
  reportArtifactUrl: (caseId: string, artifact: ReportArtifact) => string;
}>;

export type FounderWorkspaceArtifactUrls = Readonly<{
  json: string;
  html: string;
  pdf: string;
}>;

export type FounderWorkspaceSnapshot = Readonly<{
  caseId: string | null;
  status: StartupCaseStatus | null;
  report: StartupCaseReport | null;
  reportSnapshot: StartupReportSnapshotResponse | null;
  advisorQuestion: AdvisorNextQuestionResponse | null;
  advisorAnswer: AdvisorAnswerResponse | null;
  advisorImprovements: AdvisorImprovementsResponse | null;
  advisorDecision: AdvisorImprovementDecisionResponse | null;
  advisorError: Error | null;
  copilotState: CopilotStateResponse | null;
  copilotThread: CopilotThreadResponse | null;
  copilotValidationErrors: readonly CaseMutationFieldError[];
  assumptions: readonly CopilotAcceptedInputProjection[] | null;
  researchPlan: ResearchPlanResponse | null;
  researchJob: ResearchJobResponse | null;
  researchMetricComparison: ScenarioMetricComparison | null;
  activeResearchAcquisitionMode: RequestedResearchAcquisitionMode | null;
  scenarios: ScenarioProjectionResponse | null;
  selectedScenario:
    | ScenarioProjectionResponse["scenarios"][ScenarioProjectionResponse["selected_scenario_key"]]
    | null;
  scenarioCompleteness: CopilotCoverageProjection | null;
  launchPack: LaunchPackMetadataResponse | null;
  gtm: StartupGtmResponse | null;
  profile: StartupProfileResponse | null;
  gate2Preview: StartupGate2Preview | null;
  acceptedDocumentIds: readonly string[];
  activity: FounderClientActivity | null;
  error: Error | null;
  busy: boolean;
  uploadAccepted: boolean;
  display: FounderDisplayState;
  nextAction: FounderNextAction;
  artifactUrls: FounderWorkspaceArtifactUrls | null;
}>;

export type FounderWorkspaceScheduler = (
  callback: () => void,
  delayMs: number,
) => () => void;

export type FounderResumeCaseResult =
  | "resumed"
  | "missing"
  | "retryable_failure";

export type FounderWorkspaceOrchestrator = Readonly<{
  getSnapshot: () => FounderWorkspaceSnapshot;
  start: (files: readonly File[]) => Promise<boolean>;
  resumeCase: (caseId: string) => Promise<FounderResumeCaseResult>;
  refresh: () => Promise<void>;
  decideGate2: (decision: "approved" | "denied", reason?: string) => Promise<void>;
  decideGate3: (
    exclusions?: readonly Readonly<{ evidence_fact_id: string; reason?: string }>[],
  ) => Promise<void>;
  decideGate4: (decision: "approved" | "rejected", reason?: string) => Promise<void>;
  answerAdvisor: (request: AdvisorAnswerRequest) => Promise<void>;
  submitCopilotMessage: (request: PostCopilotMessageRequest) => Promise<void>;
  submitCopilotFact: (request: SaveFounderFactRequest) => Promise<void>;
  submitCopilotAssumption: (request: SaveAssumptionRequest) => Promise<void>;
  prepareCopilotResearch: (request: PrepareCopilotResearchRequest) => Promise<void>;
  launchCopilotResearchAndApproveGate2: (
    request: PrepareCopilotResearchRequest,
  ) => Promise<void>;
  decideAdvisorImprovement: (
    proposalId: string,
    decision: AdvisorImprovementDecision,
  ) => Promise<void>;
  selectScenario: (scenarioKey: ScenarioKey) => Promise<void>;
  generateAsset: (assetType: GenerateLaunchPackRequest["asset_type"]) => Promise<void>;
  generateLaunchPack: () => Promise<void>;
  retryAdvisor: () => Promise<void>;
  dispose: () => void;
}>;

export type FounderCaseFixtureMode = StartupCreateRequest["fixture_mode"];

export type PrepareCopilotResearchRequest = PrepareResearchPlanRequest &
  Readonly<{
    acquisitionMode: RequestedResearchAcquisitionMode;
  }>;

type MutableWorkspaceState = {
  caseId: string | null;
  status: StartupCaseStatus | null;
  report: StartupCaseReport | null;
  reportSnapshot: StartupReportSnapshotResponse | null;
  advisorQuestion: AdvisorNextQuestionResponse | null;
  advisorAnswer: AdvisorAnswerResponse | null;
  advisorImprovements: AdvisorImprovementsResponse | null;
  advisorDecision: AdvisorImprovementDecisionResponse | null;
  advisorError: Error | null;
  copilotState: CopilotStateResponse | null;
  copilotThread: CopilotThreadResponse | null;
  copilotValidationErrors: readonly CaseMutationFieldError[];
  assumptions: readonly CopilotAcceptedInputProjection[] | null;
  researchPlan: ResearchPlanResponse | null;
  researchJob: ResearchJobResponse | null;
  researchMetricComparison: ScenarioMetricComparison | null;
  activeResearchAcquisitionMode: RequestedResearchAcquisitionMode | null;
  scenarios: ScenarioProjectionResponse | null;
  selectedScenario:
    | ScenarioProjectionResponse["scenarios"][ScenarioProjectionResponse["selected_scenario_key"]]
    | null;
  scenarioCompleteness: CopilotCoverageProjection | null;
  launchPack: LaunchPackMetadataResponse | null;
  gtm: StartupGtmResponse | null;
  profile: StartupProfileResponse | null;
  gate2Preview: StartupGate2Preview | null;
  acceptedDocumentIds: readonly string[];
  activity: FounderClientActivity | null;
  error: Error | null;
  busy: boolean;
  uploadAccepted: boolean;
};

const browserApi: FounderWorkspaceApi = {
  createCase,
  uploadDocuments,
  getCase,
  getGate2Preview,
  getStartupGtm,
  getStartupProfile,
  getCopilotState,
  getCopilotThread,
  postCopilotMessage,
  saveFounderFact,
  saveAssumption,
  getScenarios,
  selectScenario,
  generateLaunchPack,
  listCaseAssets,
  prepareResearchPlan,
  queueResearchJob,
  getResearchJob,
  getStartupReportSnapshot,
  getAdvisorNextQuestion,
  submitAdvisorAnswer,
  getAdvisorImprovements,
  decideAdvisorImprovement,
  decideGate2,
  decideGate3,
  decideGate4,
  getReport,
  downloadReportArtifact,
  reportArtifactUrl,
};

const RESEARCH_JOB_MAX_POLLS = 8;
const RESEARCH_JOB_BASE_POLL_DELAY_MS = 1_000;
const RESEARCH_JOB_MAX_POLL_DELAY_MS = 5_000;
const RESUME_CASE_MAX_ATTEMPTS = 3;
const RESUME_CASE_RETRY_DELAY_MS = 250;

function browserSchedule(callback: () => void, delayMs: number): () => void {
  const timer = globalThis.setTimeout(callback, delayMs);
  return () => globalThis.clearTimeout(timer);
}

function asError(error: unknown): Error {
  return error instanceof Error ? error : new Error("Не удалось выполнить запрос");
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function hasErrorCode(error: unknown, code: string): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === code
  );
}

function isCaseNotFoundError(error: unknown): boolean {
  return (
    error instanceof FounderApiClientError &&
    error.code === "case_not_found" &&
    error.status === 404
  );
}

function advisorContractError(message: string): FounderApiClientError {
  return new FounderApiClientError("invalid_contract", 502, message);
}

function assertAdvisorQuestionForCase(
  response: AdvisorNextQuestionResponse,
  activeCaseId: string,
): void {
  if (response.case_id !== activeCaseId) {
    throw advisorContractError("Advisor question case mismatch");
  }
}

function assertCopilotStateForCase(
  response: CopilotStateResponse,
  activeCaseId: string,
  profile: StartupProfileResponse | null,
): void {
  if (response.case_id !== activeCaseId) {
    throw advisorContractError("Copilot state case mismatch");
  }
  if (profile && response.data_revision !== profile.data_revision) {
    throw advisorContractError("Copilot state revision mismatch");
  }
}

function assertScenariosForCopilot(
  response: ScenarioProjectionResponse,
  activeCaseId: string,
  copilotState: CopilotStateResponse | null,
): void {
  if (
    !copilotState ||
    response.case_id !== activeCaseId ||
    response.case_id !== copilotState.case_id ||
    response.data_revision !== copilotState.data_revision ||
    response.selected_scenario_key !== copilotState.selected_scenario_key
  ) {
    throw advisorContractError("Scenario projection lineage mismatch");
  }
}

function assertLaunchPackForScenario(
  response: LaunchPackMetadataResponse,
  activeCaseId: string,
  request: GenerateLaunchPackRequest,
  scenarios: ScenarioProjectionResponse,
): void {
  if (
    response.case_id !== activeCaseId ||
    response.data_revision !== request.expected_case_revision ||
    response.data_revision !== scenarios.data_revision ||
    response.scenario_set_id !== scenarios.scenario_set_id ||
    response.selected_scenario_key !== request.selected_scenario_key ||
    response.asset_key !== request.asset_type ||
    response.status !== "draft"
  ) {
    throw advisorContractError("Launch pack lineage mismatch");
  }
}

function latestAssetForScenario(
  response: CaseAssetListResponse,
  activeCaseId: string,
  scenarios: ScenarioProjectionResponse,
): LaunchPackMetadataResponse | null {
  if (response.case_id !== activeCaseId || response.data_revision !== scenarios.data_revision) {
    throw advisorContractError("Case asset list lineage mismatch");
  }
  const selected = response.assets
    .filter(
      (asset) =>
        asset.case_id === activeCaseId &&
        asset.data_revision === scenarios.data_revision &&
        asset.scenario_set_id === scenarios.scenario_set_id &&
        asset.selected_scenario_key === scenarios.selected_scenario_key &&
        asset.asset_key === "gtm_launch_pack" &&
        asset.status === "draft",
    )
    .sort((left, right) => right.asset_revision - left.asset_revision);
  return selected[0] ?? null;
}

function assertCopilotThreadForState(
  response: CopilotThreadResponse,
  activeCaseId: string,
  copilotState: CopilotStateResponse,
): void {
  if (
    response.case_id !== activeCaseId ||
    response.case_id !== copilotState.case_id ||
    response.data_revision !== copilotState.data_revision
  ) {
    throw advisorContractError("Copilot thread lineage mismatch");
  }
}

function assertResearchPlanForRequest(
  response: ResearchPlanResponse,
  activeCaseId: string,
  request: PrepareResearchPlanRequest,
): void {
  if (
    response.case_id !== activeCaseId ||
    response.data_revision !== request.expected_case_revision ||
    response.focus !== request.focus ||
    response.status !== "prepared"
  ) {
    throw advisorContractError("Research plan lineage mismatch");
  }
}

function assertResearchJobForPlan(
  response: ResearchJobResponse,
  activeCaseId: string,
  request: QueueResearchJobRequest,
  plan: ResearchPlanResponse,
): void {
  if (
    response.case_id !== activeCaseId ||
    response.plan_id !== request.plan_id ||
    response.plan_id !== plan.plan_id ||
    response.plan_hash !== request.plan_hash ||
    response.plan_hash !== plan.plan_hash
  ) {
    throw advisorContractError("Research job lineage mismatch");
  }

  const startingRevision = response.old_revision ?? response.data_revision;
  const resultRevision = response.new_revision ?? response.data_revision;
  const advancedRevision = response.data_revision > startingRevision;
  if (
    startingRevision !== request.expected_case_revision ||
    startingRevision !== plan.data_revision ||
    resultRevision !== response.data_revision ||
    resultRevision < startingRevision ||
    (advancedRevision &&
      (!isTerminalResearchJob(response) ||
        response.old_revision !== startingRevision ||
        response.new_revision !== response.data_revision)) ||
    (!advancedRevision && response.data_revision !== startingRevision)
  ) {
    throw advisorContractError("Research job lineage mismatch");
  }

  if (request.acquisition_mode === "deterministic_offline_fixture") {
    if (response.acquisition_mode !== "deterministic_offline_fixture") {
      throw advisorContractError("Research job acquisition mode mismatch");
    }
    return;
  }

  if (response.acquisition_mode === "live_public_research") {
    return;
  }

  if (
    response.acquisition_mode === "provider_unconfigured" &&
    response.status === "deferred" &&
    response.reason === "provider_unconfigured" &&
    response.accepted_entries.length === 0 &&
    response.citations.length === 0 &&
    response.changed_blocks.length === 0 &&
    response.source_refs.length === 0 &&
    response.new_revision === null &&
    response.data_revision === request.expected_case_revision
  ) {
    return;
  }

  throw advisorContractError("Research job acquisition mode mismatch");
}

function isTerminalResearchJob(job: ResearchJobResponse): boolean {
  return ["completed", "partial", "deferred", "failed"].includes(job.status);
}

function completedOrPartialResearchJob(job: ResearchJobResponse): boolean {
  return job.status === "completed" || job.status === "partial";
}

function researchJobPollDelay(attempt: number): number {
  const multiplier = 2 ** Math.min(Math.max(0, attempt - 1), 6);
  return Math.min(
    RESEARCH_JOB_MAX_POLL_DELAY_MS,
    RESEARCH_JOB_BASE_POLL_DELAY_MS * multiplier,
  );
}

function retryableResearchJobForPlan(
  job: ResearchJobResponse | null,
  activeCaseId: string,
  plan: ResearchPlanResponse,
): ResearchJobResponse | null {
  if (
    !job ||
    job.case_id !== activeCaseId ||
    (job.status !== "deferred" && job.status !== "failed") ||
    job.plan_hash !== plan.plan_hash
  ) {
    return null;
  }
  const resultRevision = job.new_revision ?? job.data_revision;
  return resultRevision <= plan.data_revision ? job : null;
}

function assertAdvisorAnswerForActiveQuestion(
  response: AdvisorAnswerResponse,
  activeCaseId: string,
  request: AdvisorAnswerRequest,
  activeQuestion: AdvisorNextQuestionResponse | null,
): void {
  const question = activeQuestion?.next_question ?? null;
  if (
    !question ||
    response.case_id !== activeCaseId ||
    response.question_id !== request.question_id ||
    response.question_id !== question.question_id ||
    response.field_key !== question.field_key
  ) {
    throw advisorContractError("Advisor answer lineage mismatch");
  }
}

function assertAdvisorImprovementsForCase(
  response: AdvisorImprovementsResponse,
  activeCaseId: string,
  current: AdvisorImprovementsResponse | null,
): void {
  if (response.case_id !== activeCaseId) {
    throw advisorContractError("Advisor improvements case mismatch");
  }
  if (current && response.improvement_version < current.improvement_version) {
    throw advisorContractError("Advisor improvements version regressed");
  }
}

function assertAdvisorDecisionForActiveProposal(
  response: AdvisorImprovementDecisionResponse,
  activeCaseId: string,
  proposalId: string,
  current: AdvisorImprovementsResponse | null,
): void {
  const knownProposal = current?.proposals.some(
    (proposal) => proposal.proposal_id === proposalId,
  );
  if (
    !current ||
    response.case_id !== activeCaseId ||
    response.proposal_id !== proposalId ||
    knownProposal !== true ||
    response.previous_version !== current.improvement_version ||
    response.new_version < response.previous_version
  ) {
    throw advisorContractError("Advisor improvement decision lineage mismatch");
  }
}

function errorCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("code" in error)) {
    return null;
  }
  return typeof error.code === "string" ? error.code : null;
}

function scenarioHasScenarioCapableInput(
  copilotState: CopilotStateResponse | null,
): boolean {
  return Boolean(
    copilotState?.accepted_inputs.some(
      (input) =>
        input.status === "accepted" &&
        (input.kind === "founder_statement" ||
          input.kind === "public_benchmark" ||
          input.kind === "ai_scenario"),
    ) || (copilotState?.scenario_metrics.length ?? 0) > 0,
  );
}

export function founderErrorMessage(error: unknown): string {
  switch (errorCode(error)) {
    case "api_unreachable":
    case "api_timeout":
      return "Сервис анализа недоступен. Проверьте, что API запущен, и повторите запрос.";
    case "empty_upload":
    case "unsafe_path":
    case "request_validation_error":
      return "Не удалось принять документы. Проверьте выбранные файлы и повторите загрузку.";
    case "startup_document_intelligence_input_invalid":
      return "Не удалось безопасно прочитать документ для профиля. Выбранный файл остаётся в загрузке — повторите или приложите исправленную версию.";
    case "resume_token_invalid":
      return "Срок подтверждения истёк. Обновите предварительный разбор документов.";
    case "startup_gtm_not_ready":
      return "План выхода на рынок ещё не готов. Обновите кейс после завершения глубинного анализа.";
    case "startup_gtm_stale":
      return "План выхода на рынок устарел относительно текущей версии кейса. Обновите анализ перед продолжением.";
    case "startup_market_fixture_unavailable":
      return "Пакет офлайн-данных рынка недоступен. Кейс и документы сохранены; обновите локальную сборку и повторите анализ.";
    case "startup_profile_not_ready":
      return "Профиль стартапа ещё не готов. Обновите кейс после первичного разбора документов.";
    case "startup_profile_stale":
      return "Профиль стартапа устарел относительно текущей версии кейса. Обновите анализ перед продолжением.";
    case "startup_report_snapshot_stale":
      return "Канонический отчёт обновился. Загрузите актуальный снимок перед продолжением.";
    case "advisor_manual_answer_semantic_mismatch":
      return "Ответ не похож на данные для текущего вопроса. Для выручки укажите MRR, ARR, цену, тариф или модель оплаты.";
    case "gate_3_not_ready":
      return "Сначала дождитесь завершения глубинного анализа, затем откройте раздел «План действий» для проверки стратегии.";
    case "report_not_ready":
      return "Канонический отчёт ещё формируется. Обновление продолжится автоматически.";
    case "gate_4_snapshot_mismatch":
      return "Отчёт обновился после проверки. Просмотрите актуальную версию перед фиксацией.";
    case "report_renderer_unavailable":
      return "PDF пока не создан. JSON и HTML доступны; PDF можно повторить позже.";
    default:
      return "Не удалось продолжить анализ. Повторите запрос; выбранные документы и кейс сохранены.";
  }
}

export function founderShellStage(
  stage: FounderWorkflowStage,
  hasFiles: boolean,
): FounderShellVisualStage {
  if (stage === "error") return hasFiles ? "files_selected" : "error";
  if (stage === "idle") return hasFiles ? "files_selected" : "idle";
  if (stage === "gate2_preview_ready") return "primary_ready";
  if (
    stage === "gate3_review_required" ||
    stage === "gate4_pending" ||
    stage === "report_draft_ready" ||
    stage === "gate4_approved" ||
    stage === "gate4_rejected" ||
    stage === "report_pdf_ready"
  ) {
    return "deep_ready";
  }
  return "analysis_running";
}

function statusFromCreate(response: StartupCreateResponse): StartupCaseStatus {
  return {
    case_id: response.case_id,
    case_status: response.case_status,
    analysis_status: response.analysis_status,
    provider_status: response.provider_status,
    data_revision: 0,
    active_analysis_thread_id: response.case_id,
    langgraph_checkpoint: null,
    gate2_status: "not_ready",
    gate3_status: "not_ready",
    gate4_status: "not_ready",
    report_status: "not_ready",
    snapshot_hash: null,
    snapshot_revision: null,
  };
}

function artifactUrls(
  api: FounderWorkspaceApi,
  caseId: string | null,
  report: StartupCaseReport | null,
  reportSnapshot: StartupReportSnapshotResponse | null,
): FounderWorkspaceArtifactUrls | null {
  if (!caseId || !isValidatedReportTuple(caseId, report, reportSnapshot)) return null;
  return {
    json: api.reportArtifactUrl(caseId, "json"),
    html: api.reportArtifactUrl(caseId, "html"),
    pdf: api.reportArtifactUrl(caseId, "pdf"),
  };
}

function isValidatedReportTuple(
  caseId: string | null,
  report: StartupCaseReport | null,
  reportSnapshot: StartupReportSnapshotResponse | null,
): report is StartupCaseReport {
  return Boolean(
    caseId &&
      report &&
      reportSnapshot &&
      report.case_id === caseId &&
      report.snapshot_revision === reportSnapshot.data_revision,
  );
}

function validationErrorsFrom(error: unknown): readonly CaseMutationFieldError[] {
  if (!(error instanceof FounderApiClientError)) return [];
  return error.validationErrors.map((fieldError) => ({
    field: fieldError.field,
    message: fieldError.message,
  }));
}

function assertAssumptionOutcomeAccepted(
  outcome: AssumptionOutcomeResponse,
): AssumptionOutcomeResponse {
  if (outcome.status === "accepted") return outcome;
  throw new FounderApiClientError(
    "fact_validation_failed",
    200,
    outcome.reason ?? "Case Copilot assumption was blocked.",
    outcome,
    outcome.delta?.validation_errors ?? [],
  );
}

async function loadSameLineageScenarios(
  api: FounderWorkspaceApi,
  activeCaseId: string,
  copilotState: CopilotStateResponse,
  options: () => FounderApiRequestOptions,
): Promise<ScenarioProjectionResponse> {
  if (!api.getScenarios) {
    throw advisorContractError("Scenario API is not available");
  }
  const first = await api.getScenarios(activeCaseId, options());
  try {
    assertScenariosForCopilot(first, activeCaseId, copilotState);
    return first;
  } catch (error) {
    if (!hasErrorCode(error, "invalid_contract")) {
      throw error;
    }
  }
  const refetched = await api.getScenarios(activeCaseId, options());
  assertScenariosForCopilot(refetched, activeCaseId, copilotState);
  return refetched;
}

async function loadSameLineageCopilotState(
  api: FounderWorkspaceApi,
  activeCaseId: string,
  profile: StartupProfileResponse,
  options: () => FounderApiRequestOptions,
): Promise<CopilotStateResponse> {
  if (!api.getCopilotState) {
    throw advisorContractError("Copilot API is not available");
  }
  const first = await api.getCopilotState(activeCaseId, options());
  try {
    assertCopilotStateForCase(first, activeCaseId, profile);
    return first;
  } catch (error) {
    if (
      !hasErrorCode(error, "invalid_contract") ||
      !(error instanceof Error) ||
      !error.message.includes("revision mismatch")
    ) {
      throw error;
    }
  }
  const refetched = await api.getCopilotState(activeCaseId, options());
  assertCopilotStateForCase(refetched, activeCaseId, profile);
  return refetched;
}

async function loadSameLineageCopilotThread(
  api: FounderWorkspaceApi,
  activeCaseId: string,
  copilotState: CopilotStateResponse,
  options: () => FounderApiRequestOptions,
): Promise<CopilotThreadResponse> {
  if (!api.getCopilotThread) {
    throw advisorContractError("Copilot thread API is not available");
  }
  const thread = await api.getCopilotThread(activeCaseId, null, options());
  assertCopilotThreadForState(thread, activeCaseId, copilotState);
  return thread;
}

export function createFounderWorkspaceOrchestrator({
  api = browserApi,
  caseFixtureMode = "live",
  onChange,
  schedule = browserSchedule,
}: Readonly<{
  api?: FounderWorkspaceApi;
  caseFixtureMode?: FounderCaseFixtureMode;
  onChange: (snapshot: FounderWorkspaceSnapshot) => void;
  schedule?: FounderWorkspaceScheduler;
}>): FounderWorkspaceOrchestrator {
  const state: MutableWorkspaceState = {
    caseId: null,
    status: null,
    report: null,
    reportSnapshot: null,
    advisorQuestion: null,
    advisorAnswer: null,
    advisorImprovements: null,
    advisorDecision: null,
    advisorError: null,
    copilotState: null,
    copilotThread: null,
    copilotValidationErrors: [],
    assumptions: null,
    researchPlan: null,
    researchJob: null,
    researchMetricComparison: null,
    activeResearchAcquisitionMode: null,
    scenarios: null,
    selectedScenario: null,
    scenarioCompleteness: null,
    launchPack: null,
    gtm: null,
    profile: null,
    gate2Preview: null,
    acceptedDocumentIds: [],
    activity: null,
    error: null,
    busy: false,
    uploadAccepted: false,
  };
  let disposed = false;
  let pollAttempt = 0;
  let cancelPoll: (() => void) | null = null;
  let cancelResearchPoll: (() => void) | null = null;
  let cancelResumeRetry: (() => void) | null = null;
  let requestController: AbortController | null = null;
  let operationGeneration = 0;

  function getSnapshot(): FounderWorkspaceSnapshot {
    const input = {
      status: state.status,
      report: state.report,
      activity: state.activity,
      error: state.error,
    };
    return {
      ...state,
      display: deriveFounderDisplayState(input),
      nextAction: deriveNextAction(input),
      artifactUrls: artifactUrls(
        api,
        state.caseId,
        state.report,
        state.reportSnapshot,
      ),
    };
  }

  function acceptedCaseStillProcessing(): boolean {
    if (!state.uploadAccepted) return false;
    const stage = deriveFounderDisplayState({
      status: state.status,
      report: state.report,
      activity: state.activity,
      error: state.error,
    }).stage;
    return [
      "primary_queued",
      "primary_intake",
      "document_ready",
      "gate2_approved",
      "primary_running",
      "primary_deterministic_running",
      "deep_running",
    ].includes(stage);
  }

  function resetWorkspaceState(
    caseId: string | null,
    uploadAccepted: boolean,
  ): void {
    Object.assign(state, {
      caseId,
      status: null,
      report: null,
      reportSnapshot: null,
      advisorQuestion: null,
      advisorAnswer: null,
      advisorImprovements: null,
      advisorDecision: null,
      advisorError: null,
      copilotState: null,
      copilotThread: null,
      copilotValidationErrors: [],
      assumptions: null,
      researchPlan: null,
      researchJob: null,
      researchMetricComparison: null,
      activeResearchAcquisitionMode: null,
      scenarios: null,
      selectedScenario: null,
      scenarioCompleteness: null,
      launchPack: null,
      gtm: null,
      profile: null,
      gate2Preview: null,
      acceptedDocumentIds: [],
      activity: null,
      error: null,
      busy: false,
      uploadAccepted,
    });
  }

  function emit(): void {
    if (!disposed) onChange(getSnapshot());
  }

  function update(values: Partial<MutableWorkspaceState>): void {
    Object.assign(state, values);
    emit();
  }

  function stopPolling(): void {
    cancelPoll?.();
    cancelPoll = null;
  }

  function stopResearchPolling(): void {
    cancelResearchPoll?.();
    cancelResearchPoll = null;
  }

  function stopResumeRetry(): void {
    cancelResumeRetry?.();
    cancelResumeRetry = null;
  }

  function requestOptions(): FounderApiRequestOptions {
    requestController?.abort();
    requestController = new AbortController();
    return { signal: requestController.signal };
  }

  function beginOperation(): number {
    operationGeneration += 1;
    requestController?.abort();
    stopResearchPolling();
    stopResumeRetry();
    return operationGeneration;
  }

  function isCurrentOperation(generation: number): boolean {
    return !disposed && generation === operationGeneration;
  }

  function schedulePoll(serverHintMs?: number): void {
    stopPolling();
    const decision = derivePollingDecision(
      {
        status: state.status,
        report: state.report,
        activity: state.activity,
        error: state.error,
      },
      {
        attempt: pollAttempt,
        serverHintMs,
        signal: requestController?.signal,
      },
    );
    if (!decision.shouldPoll || decision.delayMs === null || disposed) return;
    pollAttempt += 1;
    cancelPoll = schedule(() => {
      cancelPoll = null;
      if (disposed || state.busy) return;
      void refreshInternal(true);
    }, decision.delayMs);
  }

  async function waitForResearchPoll(
    delayMs: number,
    generation: number,
  ): Promise<boolean> {
    if (!isCurrentOperation(generation)) return false;
    return await new Promise<boolean>((resolve) => {
      let settled = false;
      let cancelTimer: (() => void) | null = null;
      const cancelResearch = (): void => {
        cancelTimer?.();
        finish(false);
      };
      const finish = (current: boolean): void => {
        if (settled) return;
        settled = true;
        if (cancelResearchPoll === cancelResearch) {
          cancelResearchPoll = null;
        }
        resolve(current);
      };
      cancelTimer = schedule(
        () => finish(isCurrentOperation(generation)),
        delayMs,
      );
      cancelResearchPoll = cancelResearch;
    });
  }

  async function waitForResumeRetry(
    delayMs: number,
    generation: number,
  ): Promise<boolean> {
    if (!isCurrentOperation(generation)) return false;
    return await new Promise<boolean>((resolve) => {
      let settled = false;
      let cancelTimer: (() => void) | null = null;
      const cancelResume = (): void => {
        cancelTimer?.();
        finish(false);
      };
      const finish = (current: boolean): void => {
        if (settled) return;
        settled = true;
        if (cancelResumeRetry === cancelResume) {
          cancelResumeRetry = null;
        }
        resolve(current);
      };
      cancelTimer = schedule(
        () => finish(isCurrentOperation(generation)),
        delayMs,
      );
      cancelResumeRetry = cancelResume;
    });
  }

  async function pollResearchJobUntilTerminal(
    activeCaseId: string,
    initialJob: ResearchJobResponse,
    queueRequest: QueueResearchJobRequest,
    plan: ResearchPlanResponse,
    generation: number,
  ): Promise<ResearchJobResponse> {
    if (isTerminalResearchJob(initialJob)) return initialJob;
    if (!api.getResearchJob) {
      throw advisorContractError("Public research job polling is not available");
    }

    let job = initialJob;
    for (let attempt = 1; attempt <= RESEARCH_JOB_MAX_POLLS; attempt += 1) {
      if (attempt > 1) {
        const current = await waitForResearchPoll(
          researchJobPollDelay(attempt),
          generation,
        );
        if (!current) return job;
      }
      state.activity = "research_searching";
      emit();
      const fetchedJob = await api.getResearchJob(
        activeCaseId,
        job.job_id,
        requestOptions(),
      );
      if (!isCurrentOperation(generation)) return job;
      assertResearchJobForPlan(fetchedJob, activeCaseId, queueRequest, plan);
      job = fetchedJob;
      state.researchJob = job;
      emit();
      if (isTerminalResearchJob(job)) return job;
    }

    throw new Error(
      "Публичный поиск не завершился в безопасный лимит ожидания. Метрики не изменены; запустите поиск повторно позже.",
    );
  }

  function emitGate2PrimaryReady(
    status: StartupCaseStatus,
    unlockGate2WhileHydrating: boolean,
  ): void {
    if (
      status.gate2_status !== "required" &&
      status.analysis_status !== "gate2_preview_ready"
    ) {
      return;
    }
    if (!state.gate2Preview?.resume_token || !state.profile) return;
    if (unlockGate2WhileHydrating) state.busy = false;
    emit();
  }

  async function refreshInternal(
    fromPoll = false,
    generation = beginOperation(),
    unlockGate2WhileHydrating = true,
  ): Promise<void> {
    const activeCaseId = state.caseId;
    if (!activeCaseId || !isCurrentOperation(generation)) return;
    const gate4ApprovalWasPending = state.activity === "submitting_gate4_approved";
    try {
      const status = await api.getCase(activeCaseId, requestOptions());
      if (!isCurrentOperation(generation)) return;
      state.status = status;
      state.activity = null;
      state.error = null;
      state.copilotValidationErrors = [];

      if (
        status.gate2_status === "required" ||
        status.analysis_status === "gate2_preview_ready"
      ) {
        const gate2Preview = await api.getGate2Preview(
          activeCaseId,
          requestOptions(),
        );
        if (!isCurrentOperation(generation)) return;
        state.gate2Preview = gate2Preview;
      } else {
        state.gate2Preview = null;
      }

      if (
        status.gate2_status === "required" ||
        status.analysis_status === "gate2_preview_ready" ||
        status.gate2_status === "completed"
      ) {
        state.profile = null;
        state.copilotState = null;
        state.copilotThread = null;
        state.copilotValidationErrors = [];
        state.assumptions = null;
        if (state.researchPlan?.case_id !== activeCaseId) state.researchPlan = null;
        if (state.researchJob?.case_id !== activeCaseId) {
          state.researchJob = null;
          state.researchMetricComparison = null;
        }
        state.scenarios = null;
        state.selectedScenario = null;
        state.scenarioCompleteness = null;
        state.launchPack = null;
        const profile = await api.getStartupProfile(
          activeCaseId,
          requestOptions(),
        );
        if (!isCurrentOperation(generation)) return;
        state.profile = profile;
        emitGate2PrimaryReady(status, unlockGate2WhileHydrating);
        if (api.getCopilotState) {
          const copilotState = await loadSameLineageCopilotState(
            api,
            activeCaseId,
            state.profile,
            requestOptions,
          );
          if (!isCurrentOperation(generation)) return;
          state.copilotState = copilotState;
          state.copilotThread = api.getCopilotThread
            ? await loadSameLineageCopilotThread(
                api,
                activeCaseId,
                copilotState,
                requestOptions,
              )
            : null;
          if (!isCurrentOperation(generation)) return;
          state.assumptions = copilotState.accepted_inputs;
          state.scenarioCompleteness = copilotState.scenario_completeness;
          if (api.getScenarios && scenarioHasScenarioCapableInput(copilotState)) {
            const scenarios = await loadSameLineageScenarios(
              api,
              activeCaseId,
              copilotState,
              requestOptions,
            );
            if (!isCurrentOperation(generation)) return;
            state.scenarios = scenarios;
            state.selectedScenario = scenarios.scenarios[scenarios.selected_scenario_key];
            state.scenarioCompleteness = scenarios.scenario_completeness;
            if (api.listCaseAssets) {
              const assets = await api.listCaseAssets(activeCaseId, requestOptions());
              if (!isCurrentOperation(generation)) return;
              state.launchPack = latestAssetForScenario(
                assets,
                activeCaseId,
                scenarios,
              );
            } else {
              state.launchPack = null;
            }
          } else {
            state.scenarios = null;
            state.selectedScenario = null;
            state.launchPack = null;
          }
        }
      } else {
        state.profile = null;
        state.copilotState = null;
        state.copilotThread = null;
        state.copilotValidationErrors = [];
        state.assumptions = null;
        state.researchPlan = null;
        state.researchJob = null;
        state.researchMetricComparison = null;
        state.scenarios = null;
        state.selectedScenario = null;
        state.scenarioCompleteness = null;
        state.launchPack = null;
      }

      if (status.gate3_status === "required" || status.gate3_status === "completed") {
        state.gtm = null;
        const gtm = await api.getStartupGtm(activeCaseId, requestOptions());
        if (!isCurrentOperation(generation)) return;
        state.gtm = gtm;
      } else {
        state.gtm = null;
      }

      if (
        status.report_status === "ready" ||
        status.analysis_status === "analysis_complete_report_pending"
      ) {
        try {
          const report = await api.getReport(activeCaseId, requestOptions());
          if (!isCurrentOperation(generation)) return;
          state.report = report;
          state.reportSnapshot = null;
          const reportSnapshot = await api.getStartupReportSnapshot(
            activeCaseId,
            requestOptions(),
          );
          if (!isCurrentOperation(generation)) return;
          if (
            report.case_id !== activeCaseId ||
            reportSnapshot.data_revision !== report.snapshot_revision
          ) {
            throw new FounderApiClientError(
              "startup_report_snapshot_stale",
              409,
              "Founder report view no longer matches report metadata",
            );
          }
          state.reportSnapshot = reportSnapshot;
          await refreshAdvisorInternal(activeCaseId, generation);
          if (!isCurrentOperation(generation)) return;
        } catch (error) {
          if (!isCurrentOperation(generation) || isAbortError(error)) return;
          const approvedSnapshotStillConverging = Boolean(
            state.report?.case_id === activeCaseId &&
              state.report.freeze_status === "approved" &&
              hasErrorCode(error, "startup_report_snapshot_stale"),
          );
          state.report = null;
          state.reportSnapshot = null;
          clearAdvisorDerivedState();
          // Gate 4 approval can commit just before its canonical snapshot read model
          // becomes visible. Retry only an already-approved same-case tuple;
          // pre-approval and cross-case mismatches remain fail-closed.
          if (
            !hasErrorCode(error, "report_not_ready") &&
            !approvedSnapshotStillConverging
          ) {
            throw error;
          }
          state.status = {
            ...status,
            report_status: "not_ready",
            snapshot_hash: null,
            snapshot_revision: null,
          };
        }
      } else {
        state.report = null;
        state.reportSnapshot = null;
        await refreshAdvisorInternal(activeCaseId, generation);
        if (!isCurrentOperation(generation)) return;
      }
      // A successful approval response can lead the canonical report read model by
      // one or more polls. Preserve the explicit approved intent until the same-case
      // report exposes its approved freeze, so `required` is not misread as rejection.
      if (
        gate4ApprovalWasPending &&
        state.report?.freeze_status !== "approved" &&
        state.status?.analysis_status !== "failed"
      ) {
        state.activity = "submitting_gate4_approved";
      }
      if (!fromPoll) pollAttempt = 0;
      emit();
      schedulePoll();
    } catch (error) {
      if (!isCurrentOperation(generation) || isAbortError(error)) return;
      update({ activity: null, error: asError(error) });
    }
  }

  async function start(files: readonly File[]): Promise<boolean> {
    if (state.busy || disposed) return false;
    if (acceptedCaseStillProcessing()) return false;
    if (files.length === 0) {
      update({ error: new Error("Добавьте хотя бы один документ") });
      return false;
    }
    stopPolling();
    const generation = beginOperation();
    update({
      busy: true,
      activity: "uploading",
      error: null,
      report: null,
      reportSnapshot: null,
      advisorQuestion: null,
      advisorAnswer: null,
      advisorImprovements: null,
      advisorDecision: null,
      advisorError: null,
      copilotState: null,
      copilotThread: null,
      copilotValidationErrors: [],
      assumptions: null,
      researchPlan: null,
      researchJob: null,
      researchMetricComparison: null,
      scenarios: null,
      selectedScenario: null,
      scenarioCompleteness: null,
      launchPack: null,
      gtm: null,
      profile: null,
      gate2Preview: null,
      acceptedDocumentIds: [],
    });
    try {
      let activeCaseId = state.caseId;
      if (!activeCaseId || state.uploadAccepted) {
        const created = await api.createCase(
          { fixture_mode: caseFixtureMode, auto_start: false },
          requestOptions(),
        );
        if (!isCurrentOperation(generation)) return false;
        activeCaseId = created.case_id;
        state.caseId = activeCaseId;
        state.status = statusFromCreate(created);
        state.uploadAccepted = false;
        state.acceptedDocumentIds = [];
        emit();
      }
      const upload = await api.uploadDocuments(
        activeCaseId,
        { files, auto_start: true },
        requestOptions(),
      );
      if (!isCurrentOperation(generation)) return false;
      state.uploadAccepted = true;
      state.acceptedDocumentIds = upload.accepted_document_ids;
      state.activity = "upload_accepted";
      emit();
      await refreshInternal(false, generation, true);
      if (
        isCurrentOperation(generation) &&
        !state.error &&
        state.status?.analysis_status === "awaiting_start"
      ) {
        schedulePoll(upload.next_poll_after_ms);
      }
      return true;
    } catch (error) {
      if (isCurrentOperation(generation) && !isAbortError(error)) {
        update({
          activity: null,
          error: asError(error),
          copilotValidationErrors: validationErrorsFrom(error),
        });
      }
      return false;
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        emit();
      }
    }
  }

  async function resumeCaseAction(caseId: string): Promise<FounderResumeCaseResult> {
    const normalizedCaseId = caseId.trim().toLowerCase();
    if (state.busy || disposed) return "retryable_failure";
    if (!isFounderCaseId(normalizedCaseId)) return "missing";
    stopPolling();
    const generation = beginOperation();
    resetWorkspaceState(normalizedCaseId, true);
    update({ busy: true });
    try {
      for (let attempt = 1; attempt <= RESUME_CASE_MAX_ATTEMPTS; attempt += 1) {
        await refreshInternal(false, generation);
        if (!isCurrentOperation(generation)) return "retryable_failure";
        const resumed =
          !state.error &&
          state.caseId === normalizedCaseId &&
          state.status?.case_id === normalizedCaseId;
        if (resumed) return "resumed";
        if (isCaseNotFoundError(state.error)) {
          resetWorkspaceState(null, false);
          emit();
          return "missing";
        }
        if (attempt < RESUME_CASE_MAX_ATTEMPTS) {
          const current = await waitForResumeRetry(
            RESUME_CASE_RETRY_DELAY_MS * attempt,
            generation,
          );
          if (!current) return "retryable_failure";
        }
      }
      return "retryable_failure";
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        emit();
      }
    }
  }

  async function refreshAction(): Promise<void> {
    const generation = beginOperation();
    try {
      await refreshInternal(false, generation);
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        emit();
      }
    }
  }

  async function runDecision(
    activity: FounderClientActivity,
    operation: (caseId: string, options: FounderApiRequestOptions) => Promise<unknown>,
    refreshAfter = true,
  ): Promise<unknown | null> {
    if (state.busy || disposed || !state.caseId) return null;
    stopPolling();
    const generation = beginOperation();
    update({ busy: true, activity, error: null, copilotValidationErrors: [] });
    try {
      const result = await operation(state.caseId, requestOptions());
      if (!isCurrentOperation(generation)) return null;
      if (refreshAfter) await refreshInternal(false, generation);
      return result;
    } catch (error) {
      if (isCurrentOperation(generation) && !isAbortError(error)) {
        update({
          activity: null,
          error: asError(error),
          copilotValidationErrors: validationErrorsFrom(error),
        });
      }
      return null;
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        emit();
      }
    }
  }

  async function decideGate2Action(
    decision: "approved" | "denied",
    reason?: string,
  ): Promise<void> {
    const token = state.gate2Preview?.resume_token;
    if (!token) {
      update({ error: new Error("Обновите предварительный разбор документов") });
      return;
    }
    const result = await runDecision(
      decision === "approved"
        ? "submitting_gate2_approved"
        : "submitting_gate2_denied",
      (activeCaseId, options) =>
        api.decideGate2(
          activeCaseId,
          {
            decision,
            resume_token: token,
            ...(reason ? { reason } : {}),
          },
          options,
        ),
      decision === "approved",
    );
    if (decision === "denied" && !state.error) {
      const status = result as StartupDecisionResult | null;
      if (state.status && status?.case_id === state.caseId) {
        state.status = { ...state.status, ...status };
      }
      state.gate2Preview = null;
      emit();
    }
  }

  async function decideGate3Action(
    exclusions: readonly Readonly<{
      evidence_fact_id: string;
      reason?: string;
    }>[] = [],
  ): Promise<void> {
    if (
      state.status?.analysis_status !== "gate3_review_required" ||
      state.status.gate3_status !== "required"
    ) {
      update({
        error: Object.assign(new Error("Gate 3 review is not ready"), {
          code: "gate_3_not_ready",
        }),
      });
      return;
    }
    await runDecision("submitting_gate3", (activeCaseId, options) =>
      api.decideGate3(
        activeCaseId,
        {
          decision: "continue",
          exclusions: exclusions.map((item) => ({ ...item })),
        },
        options,
      ),
    );
  }

  async function decideGate4Action(
    decision: "approved" | "rejected",
    reason?: string,
  ): Promise<void> {
    const currentReport = state.report;
    if (!isValidatedReportTuple(state.caseId, currentReport, state.reportSnapshot)) {
      update({ error: new Error("Канонический отчёт ещё не готов") });
      return;
    }
    await runDecision(
      decision === "approved"
        ? "submitting_gate4_approved"
        : "submitting_gate4_rejected",
      (activeCaseId, options) =>
        api.decideGate4(
          activeCaseId,
          {
            decision,
            snapshot_hash: currentReport.snapshot_hash,
            snapshot_revision: currentReport.snapshot_revision,
            ...(reason ? { reason } : {}),
          },
          options,
        ),
    );
  }

  function clearAdvisorDerivedState(): void {
    state.advisorQuestion = null;
    state.advisorImprovements = null;
    state.advisorError = null;
  }

  function canLoadAdvisor(activeCaseId: string): boolean {
    return Boolean(
      state.status &&
        (state.status.gate3_status === "required" ||
          state.status.gate3_status === "completed") &&
        state.profile?.case_id === activeCaseId &&
        state.gtm?.case_id === activeCaseId,
    );
  }

  async function refreshAdvisorInternal(
    activeCaseId: string | null,
    generation: number,
  ): Promise<void> {
    if (!activeCaseId || !isCurrentOperation(generation)) return;
    if (!canLoadAdvisor(activeCaseId)) {
      clearAdvisorDerivedState();
      return;
    }
    try {
      const advisorQuestion = await api.getAdvisorNextQuestion(
        activeCaseId,
        requestOptions(),
      );
      if (!isCurrentOperation(generation)) return;
      assertAdvisorQuestionForCase(advisorQuestion, activeCaseId);
      state.advisorQuestion = advisorQuestion;
      if (
        isValidatedReportTuple(
          activeCaseId,
          state.report,
          state.reportSnapshot,
        )
      ) {
        const advisorImprovements = await api.getAdvisorImprovements(
          activeCaseId,
          requestOptions(),
        );
        if (!isCurrentOperation(generation)) return;
        assertAdvisorImprovementsForCase(
          advisorImprovements,
          activeCaseId,
          state.advisorImprovements,
        );
        state.advisorImprovements = advisorImprovements;
      } else {
        state.advisorImprovements = null;
      }
      state.advisorError = null;
    } catch (error) {
      if (!isCurrentOperation(generation) || isAbortError(error)) return;
      state.advisorError = asError(error);
    }
  }

  async function loadAdvisorImprovementsIfReady(
    activeCaseId: string,
    generation: number,
  ): Promise<void> {
    try {
      const advisorImprovements = await api.getAdvisorImprovements(
        activeCaseId,
        requestOptions(),
      );
      if (!isCurrentOperation(generation)) return;
      assertAdvisorImprovementsForCase(
        advisorImprovements,
        activeCaseId,
        state.advisorImprovements,
      );
      state.advisorImprovements = advisorImprovements;
      state.advisorError = null;
    } catch (error) {
      if (!isCurrentOperation(generation) || isAbortError(error)) return;
      if (!hasErrorCode(error, "advisor_improvements_not_ready")) {
        throw error;
      }
      state.advisorImprovements = null;
    }
  }

  async function retryAdvisorAction(): Promise<void> {
    if (state.busy || disposed || !state.caseId) return;
    stopPolling();
    const generation = beginOperation();
    update({ busy: true, activity: "advisor_refreshing", advisorError: null });
    try {
      await refreshAdvisorInternal(state.caseId, generation);
      if (isCurrentOperation(generation)) emit();
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        state.activity = null;
        emit();
      }
    }
  }

  async function answerAdvisorAction(request: AdvisorAnswerRequest): Promise<void> {
    if (state.busy || disposed || !state.caseId) return;
    stopPolling();
    const generation = beginOperation();
    update({ busy: true, activity: "advisor_answering", advisorError: null });
    try {
      const advisorAnswer = await api.submitAdvisorAnswer(
        state.caseId,
        request,
        requestOptions(),
      );
      if (!isCurrentOperation(generation)) return;
      assertAdvisorAnswerForActiveQuestion(
        advisorAnswer,
        state.caseId,
        request,
        state.advisorQuestion,
      );
      state.advisorAnswer = advisorAnswer;
      await refreshInternal(false, generation);
      if (!isCurrentOperation(generation)) return;

      if (state.caseId) {
        await loadAdvisorImprovementsIfReady(state.caseId, generation);
      }
      if (!isCurrentOperation(generation)) return;
      state.advisorAnswer = advisorAnswer;
      emit();
    } catch (error) {
      if (isCurrentOperation(generation) && !isAbortError(error)) {
        state.advisorError = asError(error);
        emit();
      }
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        state.activity = null;
        emit();
      }
    }
  }

  async function decideAdvisorImprovementAction(
    proposalId: string,
    decision: AdvisorImprovementDecision,
  ): Promise<void> {
    if (state.busy || disposed || !state.caseId || proposalId.trim() === "") return;
    stopPolling();
    const generation = beginOperation();
    update({ busy: true, activity: "advisor_deciding", advisorError: null });
    try {
      const advisorDecision = await api.decideAdvisorImprovement(
        state.caseId,
        proposalId,
        decision,
        requestOptions(),
      );
      if (!isCurrentOperation(generation)) return;
      assertAdvisorDecisionForActiveProposal(
        advisorDecision,
        state.caseId,
        proposalId,
        state.advisorImprovements,
      );
      state.advisorDecision = advisorDecision;
      await refreshInternal(false, generation);
      if (!isCurrentOperation(generation)) return;
      state.advisorDecision = advisorDecision;
      emit();
    } catch (error) {
      if (isCurrentOperation(generation) && !isAbortError(error)) {
        state.advisorError = asError(error);
        emit();
      }
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        emit();
      }
    }
  }

  async function submitCopilotFactAction(
    request: SaveFounderFactRequest,
  ): Promise<void> {
    if (!api.saveFounderFact) {
      update({ error: advisorContractError("Copilot fact input is not available") });
      return;
    }
    await runDecision("copilot_saving_fact", (activeCaseId, options) =>
      api.saveFounderFact!(activeCaseId, request, options),
    );
  }

  async function submitCopilotMessageAction(
    request: PostCopilotMessageRequest,
  ): Promise<void> {
    if (!api.postCopilotMessage) {
      update({
        error: advisorContractError("Copilot message input is not available"),
        copilotValidationErrors: [],
      });
      return;
    }
    await runDecision("copilot_sending_message", (activeCaseId, options) =>
      api.postCopilotMessage!(activeCaseId, request, options),
    );
  }

  async function submitCopilotAssumptionAction(
    request: SaveAssumptionRequest,
  ): Promise<void> {
    if (!api.saveAssumption) {
      update({ error: advisorContractError("Copilot assumption input is not available") });
      return;
    }
    await runDecision("copilot_saving_assumption", async (activeCaseId, options) =>
      assertAssumptionOutcomeAccepted(
        await api.saveAssumption!(activeCaseId, request, options),
      ),
    );
  }

  function researchJobHasUsefulGate2Result(job: ResearchJobResponse): boolean {
    const revisionAdvanced =
      job.old_revision !== null &&
      job.new_revision !== null &&
      job.new_revision > job.old_revision &&
      job.data_revision === job.new_revision;
    const cachedOnCurrentRevision =
      job.reason === "cached_completed_research" &&
      job.old_revision === job.data_revision &&
      job.new_revision === job.data_revision;
    const hasAcceptedFacts = job.accepted_entries.length > 0;
    const hasPublicContext =
      job.citations.length > 0 ||
      job.changed_blocks.length > 0 ||
      job.source_refs.length > 0;
    return (
      completedOrPartialResearchJob(job) &&
      (revisionAdvanced || cachedOnCurrentRevision) &&
      (hasAcceptedFacts || hasPublicContext)
    );
  }

  async function runCopilotResearchSequence(
    activeCaseId: string,
    request: PrepareCopilotResearchRequest,
    generation: number,
    unlockGate2WhileHydrating = true,
  ): Promise<Readonly<{ plan: ResearchPlanResponse; job: ResearchJobResponse }> | null> {
    if (!api.prepareResearchPlan || !api.queueResearchJob) {
      throw advisorContractError("Public research planning is not available");
    }
    const plan = await api.prepareResearchPlan(
      activeCaseId,
      {
        focus: request.focus,
        intent: request.intent,
        requested_private_value: request.requested_private_value,
        expected_case_revision: request.expected_case_revision,
      },
      requestOptions(),
    );
    if (!isCurrentOperation(generation)) return null;
    assertResearchPlanForRequest(plan, activeCaseId, request);
    const previousResearchJob = retryableResearchJobForPlan(
      state.researchJob,
      activeCaseId,
      plan,
    );
    state.researchPlan = plan;
    state.researchJob = null;
    state.researchMetricComparison = null;
    state.activeResearchAcquisitionMode = request.acquisitionMode;
    emit();
    let beforeResearchScenarios =
      state.scenarios?.case_id === activeCaseId &&
      state.scenarios.data_revision === plan.data_revision
        ? state.scenarios
        : null;
    if (
      !beforeResearchScenarios &&
      api.getScenarios &&
      state.copilotState?.case_id === activeCaseId &&
      state.copilotState.data_revision === plan.data_revision
    ) {
      beforeResearchScenarios = await loadSameLineageScenarios(
        api,
        activeCaseId,
        state.copilotState,
        requestOptions,
      );
      if (!isCurrentOperation(generation)) return null;
    }

    const queueRequest: QueueResearchJobRequest = {
      plan_id: plan.plan_id,
      plan_hash: plan.plan_hash,
      expected_case_revision: plan.data_revision,
      idempotency_key: previousResearchJob
        ? `copilot-research-retry:${request.acquisitionMode}:${previousResearchJob.job_id}:${plan.focus}:${plan.plan_hash}`
        : `copilot-research:${request.acquisitionMode}:${plan.focus}:${plan.plan_hash}`,
      consent_public_research: true,
      acquisition_mode: request.acquisitionMode,
      retry_of_job_id: previousResearchJob?.job_id ?? null,
    };
    state.activity = "research_searching";
    emit();
    let job = await api.queueResearchJob(
      activeCaseId,
      queueRequest,
      requestOptions(),
    );
    if (!isCurrentOperation(generation)) return null;
    assertResearchJobForPlan(job, activeCaseId, queueRequest, plan);
    state.researchJob = job;
    emit();

    if (!isTerminalResearchJob(job)) {
      job = await pollResearchJobUntilTerminal(
        activeCaseId,
        job,
        queueRequest,
        plan,
        generation,
      );
      if (!isCurrentOperation(generation)) return null;
    }

    if (completedOrPartialResearchJob(job)) {
      state.activity = "research_recalculating";
      emit();
      await refreshInternal(false, generation, unlockGate2WhileHydrating);
      if (!isCurrentOperation(generation)) return null;
      state.researchPlan = plan;
      state.researchJob = job;
      state.researchMetricComparison = state.scenarios
        ? compareScenarioMetricChanges(
            beforeResearchScenarios,
            state.scenarios,
            beforeResearchScenarios?.selected_scenario_key ?? state.scenarios.selected_scenario_key,
            plan.data_revision,
          )
        : null;
    } else {
      state.researchPlan = plan;
      state.researchJob = job;
      state.researchMetricComparison = null;
      state.activity = null;
    }
    emit();
    return { plan, job };
  }

  async function prepareCopilotResearchAction(
    request: PrepareCopilotResearchRequest,
  ): Promise<void> {
    if (!api.prepareResearchPlan || !api.queueResearchJob) {
      update({ error: advisorContractError("Public research planning is not available") });
      return;
    }
    if (state.busy || disposed || !state.caseId) return;
    stopPolling();
    const generation = beginOperation();
    update({
      busy: true,
      activity: "research_preparing",
      error: null,
      copilotValidationErrors: [],
      activeResearchAcquisitionMode: request.acquisitionMode,
    });
    try {
      await runCopilotResearchSequence(state.caseId, request, generation);
    } catch (error) {
      if (isCurrentOperation(generation) && !isAbortError(error)) {
        update({
          activity: null,
          error: asError(error),
          copilotValidationErrors: validationErrorsFrom(error),
        });
      }
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        state.activeResearchAcquisitionMode = null;
        emit();
      }
    }
  }

  async function launchCopilotResearchAndApproveGate2Action(
    request: PrepareCopilotResearchRequest,
  ): Promise<void> {
    if (!api.prepareResearchPlan || !api.queueResearchJob) {
      update({ error: advisorContractError("Public research planning is not available") });
      return;
    }
    if (state.busy || disposed || !state.caseId) return;
    stopPolling();
    const generation = beginOperation();
    update({
      busy: true,
      activity: "research_preparing",
      error: null,
      copilotValidationErrors: [],
      activeResearchAcquisitionMode: request.acquisitionMode,
    });
    try {
      const activeCaseId = state.caseId;
      const researchResult = await runCopilotResearchSequence(
        activeCaseId,
        request,
        generation,
        false,
      );
      if (!isCurrentOperation(generation)) return;
      if (!researchResult) return;
      const { job } = researchResult;
      if (!researchJobHasUsefulGate2Result(job)) {
        const failure = job.reason === "BUDGET_EXCEEDED"
          ? Object.assign(
              new Error("Лимит онлайн-ресерча исчерпан. Новый OpenAI-запрос не выполнен; используйте сохранённый публичный ресерч или повторите после увеличения бюджета."),
              { code: "BUDGET_EXCEEDED" },
            )
          : Object.assign(
              new Error("Публичный поиск не дал полезного результата. Профиль не подтверждён; попробуйте онлайн-поиск повторно или добавьте ответ вручную."),
              { code: "research_no_useful_result" },
            );
        update({
          activity: null,
          error: failure,
          copilotValidationErrors: [],
        });
        return;
      }
      if (
        job.reason === "cached_completed_research" &&
        state.status?.gate2_status === "completed"
      ) {
        // The durable cache did not create a new case revision. Reopening Gate 2 here
        // would repeat an already-approved analysis and may spend provider budget again.
        state.activity = null;
        emit();
        return;
      }
      const gate2Preview = await api.getGate2Preview(activeCaseId, requestOptions());
      if (!isCurrentOperation(generation)) return;
      state.gate2Preview = gate2Preview;
      const token = state.gate2Preview?.resume_token;
      if (!token) {
        update({
          activity: null,
          error: new Error("Не удалось получить свежую версию данных для подтверждения профиля после ресерча. Обновите кейс и повторите запуск."),
          copilotValidationErrors: [],
        });
        return;
      }
      state.activity = "submitting_gate2_approved";
      emit();
      await api.decideGate2(
        activeCaseId,
        {
          decision: "approved",
          resume_token: token,
        },
        requestOptions(),
      );
      if (!isCurrentOperation(generation)) return;
      await refreshInternal(false, generation);
    } catch (error) {
      if (isCurrentOperation(generation) && !isAbortError(error)) {
        update({
          activity: null,
          error: asError(error),
          copilotValidationErrors: validationErrorsFrom(error),
        });
      }
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        state.activeResearchAcquisitionMode = null;
        emit();
      }
    }
  }

  async function selectScenarioAction(scenarioKey: ScenarioKey): Promise<void> {
    if (state.busy || disposed || !state.caseId || !state.scenarios || !api.selectScenario) return;
    stopPolling();
    const generation = beginOperation();
    const request: SelectScenarioRequest = {
      scenario_set_id: state.scenarios.scenario_set_id,
      scenario_key: scenarioKey,
      expected_case_revision: state.scenarios.data_revision,
      idempotency_key: globalThis.crypto.randomUUID(),
    };
    update({ busy: true, activity: "scenario_selecting", error: null });
    try {
      const result = await api.selectScenario(
        state.caseId,
        request,
        requestOptions(),
      );
      if (!isCurrentOperation(generation)) return;
      if (
        result.case_id !== state.caseId ||
        result.data_revision !== request.expected_case_revision ||
        result.scenario_set_id !== request.scenario_set_id ||
        result.new_scenario_key !== scenarioKey
      ) {
        throw advisorContractError("Scenario selection lineage mismatch");
      }
      await refreshInternal(false, generation);
    } catch (error) {
      if (isCurrentOperation(generation) && !isAbortError(error)) {
        update({
          activity: null,
          error: asError(error),
          copilotValidationErrors: validationErrorsFrom(error),
        });
      }
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        state.activity = null;
        emit();
      }
    }
  }

  async function generateAssetAction(
    assetType: GenerateLaunchPackRequest["asset_type"],
  ): Promise<void> {
    if (
      state.busy ||
      disposed ||
      !state.caseId ||
      !state.scenarios ||
      !api.generateLaunchPack
    ) {
      return;
    }
    stopPolling();
    const generation = beginOperation();
    const activeCaseId = state.caseId;
    const activeScenarios = state.scenarios;
    const selectedScenarioKey = activeScenarios.selected_scenario_key;
    const request: GenerateLaunchPackRequest = {
      asset_type: assetType,
      selected_scenario_key: selectedScenarioKey,
      expected_case_revision: activeScenarios.data_revision,
      idempotency_key: globalThis.crypto.randomUUID(),
    };
    update({
      busy: true,
      activity: assetType === "gtm_launch_pack" ? "launch_pack_generating" : "asset_generating",
      error: null,
      copilotValidationErrors: [],
    });
    try {
      const result = await api.generateLaunchPack(
        activeCaseId,
        request,
        requestOptions(),
      );
      if (!isCurrentOperation(generation)) return;
      assertLaunchPackForScenario(result, activeCaseId, request, activeScenarios);
      state.launchPack = result;
      state.error = null;
      emit();
    } catch (error) {
      if (isCurrentOperation(generation) && !isAbortError(error)) {
        update({
          activity: null,
          error: asError(error),
          copilotValidationErrors: validationErrorsFrom(error),
        });
      }
    } finally {
      if (isCurrentOperation(generation)) {
        state.busy = false;
        state.activity = null;
        emit();
      }
    }
  }

  function dispose(): void {
    disposed = true;
    stopPolling();
    stopResearchPolling();
    stopResumeRetry();
    requestController?.abort();
  }

  return {
    getSnapshot,
    start,
    resumeCase: resumeCaseAction,
    refresh: refreshAction,
    decideGate2: decideGate2Action,
    decideGate3: decideGate3Action,
    decideGate4: decideGate4Action,
    answerAdvisor: answerAdvisorAction,
    submitCopilotMessage: submitCopilotMessageAction,
    submitCopilotFact: submitCopilotFactAction,
    submitCopilotAssumption: submitCopilotAssumptionAction,
    prepareCopilotResearch: prepareCopilotResearchAction,
    launchCopilotResearchAndApproveGate2: launchCopilotResearchAndApproveGate2Action,
    decideAdvisorImprovement: decideAdvisorImprovementAction,
    selectScenario: selectScenarioAction,
    generateAsset: generateAssetAction,
    generateLaunchPack: () => generateAssetAction("gtm_launch_pack"),
    retryAdvisor: retryAdvisorAction,
    dispose,
  };
}
