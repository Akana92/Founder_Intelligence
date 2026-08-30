import {
  ApiContractError,
  parseAdvisorAnswerResponse,
  parseAdvisorImprovementDecisionResponse,
  parseAdvisorImprovementsResponse,
  parseAdvisorNextQuestionResponse,
  parseApiError,
  parseAssumptionOutcomeResponse,
  parseCopilotThreadResponse,
  parseCopilotStateResponse,
  parseCopilotTurnResponse,
  parseCaseAssetListResponse,
  parseFactMutationResponse,
  parseLaunchPackMetadataResponse,
  parseResearchJobResponse,
  parseResearchPlanResponse,
  parseScenarioProjectionResponse,
  parseScenarioSelectionResponse,
  parseStartupAnalysis,
  parseStartupCaseReport,
  parseStartupCaseStatus,
  parseStartupCreateResponse,
  parseStartupGate2DecisionResult,
  parseStartupGate2Preview,
  parseStartupGate3DecisionResult,
  parseStartupGate4DecisionResult,
  parseStartupGtmResponse,
  parseStartupProfileResponse,
  parseStartupReportSnapshotResponse,
  parseStartupUploadResponse,
  type ApiErrorCode,
  type ApiFieldError,
  type AdvisorAnswerResponse,
  type AdvisorAnswerType,
  type AdvisorImprovementDecisionResponse,
  type AdvisorImprovementsResponse,
  type AdvisorNextQuestionResponse,
  type AssumptionOutcomeResponse,
  type CaseAssetListResponse,
  type CaseValueKind,
  type CopilotStateResponse,
  type CopilotThreadResponse,
  type CopilotTurnResponse,
  type FactMutationResponse,
  type LaunchPackMetadataResponse,
  type ResearchJobResponse,
  type ResearchPlanResponse,
  type RequestedResearchAcquisitionMode,
  type ScenarioKey,
  type ScenarioProjectionResponse,
  type ScenarioSelectionResponse,
  type StartupCaseReport,
  type StartupCaseStatus,
  type StartupCreateRequest,
  type StartupCreateResponse,
  type StartupDecisionResult,
  type StartupGate2Preview,
  type StartupGtmResponse,
  type StartupProfileResponse,
  type StartupReportSnapshotResponse,
  type StartupUploadResponse,
} from "./contracts.ts";

export const FOUNDER_API_REQUEST_TIMEOUT_MS = 60_000;

export type FounderApiRequestOptions = Readonly<{
  fetcher?: typeof fetch;
  signal?: AbortSignal;
  timeoutMs?: number;
}>;

export type StartupDocumentUpload = Readonly<{
  files: readonly File[];
  auto_start: boolean;
  company_name?: string | null;
  website?: string | null;
  as_of?: string | null;
  document_class_hint?: string | null;
}>;

export type StartupGate2Decision = Readonly<{
  decision: "approved" | "denied";
  resume_token: string;
  reason?: string | null;
}>;

export type StartupGate3Exclusion = Readonly<{
  evidence_fact_id: string;
  reason?: string | null;
}>;

export type StartupGate3Decision = Readonly<{
  decision: "continue";
  exclusions: readonly StartupGate3Exclusion[];
}>;

export type StartupGate4Decision = Readonly<{
  decision: "approved" | "rejected";
  snapshot_hash: string;
  snapshot_revision: number;
  reason?: string | null;
}>;

export type ReportArtifact = "json" | "html" | "pdf";

export type AdvisorAnswerRequest = Readonly<{
  question_id: string;
  answer_type: AdvisorAnswerType;
  value: string | null;
  document_id: string | null;
  consent_public_research: boolean;
}>;

export type AdvisorImprovementDecision = "accepted" | "rejected";

export type SelectScenarioRequest = Readonly<{
  scenario_set_id: string | null;
  scenario_key: ScenarioKey;
  expected_case_revision: number;
  idempotency_key: string;
}>;

export type FounderFactValue =
  | Readonly<{
      kind: "money";
      amount: string | number | null;
      scale: string | null;
      currency: string | null;
    }>
  | Readonly<{
      kind: "text";
      value: string;
    }>;

export type FounderFactPeriod = Readonly<{
  kind: "month" | "date" | "range";
  start: string | null;
  end: string | null;
  value: string | null;
}>;

export type FounderFactSource = Readonly<{
  kind: CaseValueKind;
  declared_source: string | null;
  evidence_ref: string | null;
}>;

export type SaveFounderFactRequest = Readonly<{
  requirement_key: string;
  value: FounderFactValue;
  period: FounderFactPeriod | null;
  source: FounderFactSource;
  note: string | null;
  resolves_contradiction_id: string | null;
  expected_case_revision: number;
  idempotency_key: string;
}>;

export type SaveAssumptionRequest = Readonly<{
  requirement_key: string;
  value: FounderFactValue;
  period: FounderFactPeriod | null;
  source: FounderFactSource;
  rationale: string;
  validation_plan: string;
  expected_case_revision: number;
  idempotency_key: string;
}>;

export type PostCopilotMessageRequest = Readonly<{
  message: string;
  page_context: string;
  current_section: string;
  expected_case_revision: number;
  focus_key: string | null;
  idempotency_key: string;
}>;

export type PrepareResearchPlanRequest = Readonly<{
  focus: string;
  intent: string;
  requested_private_value: string | null;
  expected_case_revision: number;
}>;

export type QueueResearchJobRequest = Readonly<{
  plan_id: string;
  plan_hash: string;
  expected_case_revision: number;
  idempotency_key: string;
  consent_public_research: boolean;
  acquisition_mode: RequestedResearchAcquisitionMode;
  retry_of_job_id: string | null;
}>;

export type GenerateLaunchPackRequest = Readonly<{
  asset_type:
    | "customer_interview_script"
    | "pricing_experiment"
    | "positioning_map"
    | "weekly_funnel_template"
    | "gtm_launch_pack";
  selected_scenario_key: ScenarioKey;
  expected_case_revision: number;
  idempotency_key: string;
}>;

export class FounderApiClientError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly details: unknown | null;
  readonly validationErrors: readonly ApiFieldError[];

  constructor(
    code: ApiErrorCode,
    status: number,
    message: string,
    details: unknown | null = null,
    validationErrors: readonly ApiFieldError[] = [],
  ) {
    super(message);
    this.name = "FounderApiClientError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.validationErrors = validationErrors;
  }
}

type JsonParser<T> = (value: unknown) => T;

function safeCaseSegment(caseId: string): string {
  const normalized = caseId.trim();
  if (normalized === "" || normalized === "." || normalized === "..") {
    throw new FounderApiClientError(
      "invalid_contract",
      0,
      "Startup case id is invalid",
    );
  }
  return encodeURIComponent(caseId);
}

function casePath(caseId: string): string {
  return `/api/startup/cases/${safeCaseSegment(caseId)}`;
}

function requestSignal(options: FounderApiRequestOptions): {
  signal: AbortSignal;
  timeoutSignal: AbortSignal;
} {
  const configuredTimeout = options.timeoutMs ?? FOUNDER_API_REQUEST_TIMEOUT_MS;
  const timeoutMs =
    Number.isFinite(configuredTimeout) && configuredTimeout > 0
      ? Math.floor(configuredTimeout)
      : FOUNDER_API_REQUEST_TIMEOUT_MS;
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  return {
    signal: options.signal
      ? AbortSignal.any([options.signal, timeoutSignal])
      : timeoutSignal,
    timeoutSignal,
  };
}

async function performRequest(
  path: string,
  init: RequestInit,
  options: FounderApiRequestOptions,
): Promise<Response> {
  const { signal, timeoutSignal } = requestSignal(options);
  try {
    return await (options.fetcher ?? fetch)(path, {
      ...init,
      cache: "no-store",
      credentials: "same-origin",
      signal,
    });
  } catch (error) {
    if (options.signal?.aborted) {
      throw options.signal.reason ?? error;
    }
    if (timeoutSignal.aborted) {
      throw new FounderApiClientError(
        "api_timeout",
        0,
        "Founder API request timed out",
      );
    }
    throw new FounderApiClientError(
      "api_unreachable",
      0,
      "Founder API could not be reached",
    );
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function responseError(response: Response): Promise<FounderApiClientError> {
  let body: unknown;
  try {
    body = JSON.parse(await response.text());
  } catch {
    return new FounderApiClientError(
      "api_rejected",
      response.status,
      `Founder API returned ${response.status}`,
    );
  }

  if (isRecord(body)) {
    try {
      const parsed = parseApiError(
        "errors" in body
          ? { code: body.code, message: body.message, errors: body.errors }
          : { code: body.code, message: body.message },
      );
      return new FounderApiClientError(
        parsed.code,
        response.status,
        parsed.message,
        "details" in body ? body.details : null,
        parsed.errors ?? [],
      );
    } catch (error) {
      if (!(error instanceof ApiContractError)) {
        throw error;
      }
    }
  }

  return new FounderApiClientError(
    "api_rejected",
    response.status,
    `Founder API returned ${response.status}`,
  );
}

async function requestJson<T>(
  path: string,
  init: RequestInit,
  parser: JsonParser<T>,
  options: FounderApiRequestOptions,
): Promise<T> {
  const response = await performRequest(path, init, options);
  if (!response.ok) {
    throw await responseError(response);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new FounderApiClientError(
      "invalid_contract",
      response.status,
      "Founder API response was not valid JSON",
    );
  }

  try {
    return parser(body);
  } catch (error) {
    if (error instanceof ApiContractError) {
      throw new FounderApiClientError(
        "invalid_contract",
        response.status,
        error.message,
      );
    }
    throw error;
  }
}

function jsonInit(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  };
}

function getJsonInit(): RequestInit {
  return {
    method: "GET",
    headers: { Accept: "application/json" },
  };
}

export async function createCase(
  request: StartupCreateRequest,
  options: FounderApiRequestOptions = {},
): Promise<StartupCreateResponse> {
  return requestJson(
    "/api/startup/cases",
    jsonInit(request),
    parseStartupCreateResponse,
    options,
  );
}

export async function uploadDocuments(
  caseId: string,
  request: StartupDocumentUpload,
  options: FounderApiRequestOptions = {},
): Promise<StartupUploadResponse> {
  const body = new FormData();
  for (const file of request.files) {
    body.append("files", file, file.name);
  }
  body.append("auto_start", String(request.auto_start));
  for (const field of [
    "company_name",
    "website",
    "as_of",
    "document_class_hint",
  ] as const) {
    const value = request[field];
    if (value !== null && value !== undefined) {
      body.append(field, value);
    }
  }

  return requestJson(
    `${casePath(caseId)}/documents`,
    { method: "POST", headers: { Accept: "application/json" }, body },
    parseStartupUploadResponse,
    options,
  );
}

export async function getCase(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<StartupCaseStatus> {
  return requestJson(casePath(caseId), getJsonInit(), parseStartupCaseStatus, options);
}

export async function getAnalysis(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<StartupCaseStatus> {
  return requestJson(
    `${casePath(caseId)}/analysis`,
    getJsonInit(),
    parseStartupAnalysis,
    options,
  );
}

export async function getGate2Preview(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<StartupGate2Preview> {
  return requestJson(
    `${casePath(caseId)}/gate2/preview`,
    getJsonInit(),
    parseStartupGate2Preview,
    options,
  );
}

export async function getStartupGtm(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<StartupGtmResponse> {
  return requestJson(
    `${casePath(caseId)}/gtm`,
    getJsonInit(),
    parseStartupGtmResponse,
    options,
  );
}

export async function getStartupProfile(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<StartupProfileResponse> {
  return requestJson(
    `${casePath(caseId)}/profile`,
    getJsonInit(),
    parseStartupProfileResponse,
    options,
  );
}

function boundParser<T>(
  parser: JsonParser<T>,
  assertBound: (response: T) => void,
): JsonParser<T> {
  return (value) => {
    const response = parser(value);
    assertBound(response);
    return response;
  };
}

function assertCaseId(responseCaseId: string, caseId: string, field: string): void {
  if (responseCaseId !== caseId) {
    throw new ApiContractError(`${field} case mismatch`);
  }
}

function assertRevision(responseRevision: number, expectedRevision: number, field: string): void {
  if (responseRevision !== expectedRevision) {
    throw new ApiContractError(`${field} revision mismatch`);
  }
}

export async function getCopilotState(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<CopilotStateResponse> {
  return requestJson(
    `${casePath(caseId)}/copilot/state`,
    getJsonInit(),
    boundParser(parseCopilotStateResponse, (response) => {
      assertCaseId(response.case_id, caseId, "copilot_state");
    }),
    options,
  );
}

export async function getCopilotThread(
  caseId: string,
  threadId: string | null = null,
  options: FounderApiRequestOptions = {},
): Promise<CopilotThreadResponse> {
  const query = threadId
    ? `?${new URLSearchParams({ thread_id: threadId }).toString()}`
    : "";
  return requestJson(
    `${casePath(caseId)}/copilot/thread${query}`,
    getJsonInit(),
    boundParser(parseCopilotThreadResponse, (response) => {
      assertCaseId(response.case_id, caseId, "copilot_thread");
      if (threadId !== null && response.thread_id !== threadId) {
        throw new ApiContractError("copilot_thread thread mismatch");
      }
    }),
    options,
  );
}

export async function postCopilotMessage(
  caseId: string,
  request: PostCopilotMessageRequest,
  options: FounderApiRequestOptions = {},
): Promise<CopilotTurnResponse> {
  return requestJson(
    `${casePath(caseId)}/copilot/messages`,
    jsonInit(request),
    boundParser(parseCopilotTurnResponse, (response) => {
      assertCaseId(response.case_id, caseId, "copilot_turn");
      assertRevision(response.data_revision, request.expected_case_revision, "copilot_turn");
      if (
        response.page_context !== request.page_context ||
        response.current_section !== request.current_section
      ) {
        throw new ApiContractError("copilot_turn page context mismatch");
      }
    }),
    options,
  );
}

export async function saveFounderFact(
  caseId: string,
  request: SaveFounderFactRequest,
  options: FounderApiRequestOptions = {},
): Promise<FactMutationResponse> {
  return requestJson(
    `${casePath(caseId)}/facts`,
    jsonInit(request),
    boundParser(parseFactMutationResponse, (response) => {
      assertCaseId(response.case_id, caseId, "fact_mutation");
      assertRevision(response.old_revision, request.expected_case_revision, "fact_mutation");
      if (response.delta.old_revision !== response.old_revision) {
        throw new ApiContractError("fact_mutation delta revision mismatch");
      }
    }),
    options,
  );
}

export async function saveAssumption(
  caseId: string,
  request: SaveAssumptionRequest,
  options: FounderApiRequestOptions = {},
): Promise<AssumptionOutcomeResponse> {
  return requestJson(
    `${casePath(caseId)}/assumptions`,
    jsonInit(request),
    boundParser(parseAssumptionOutcomeResponse, (response) => {
      assertCaseId(response.case_id, caseId, "assumption_outcome");
      assertRevision(response.old_revision, request.expected_case_revision, "assumption_outcome");
      if (response.delta && response.delta.old_revision !== response.old_revision) {
        throw new ApiContractError("assumption_outcome delta revision mismatch");
      }
    }),
    options,
  );
}

export async function getScenarios(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<ScenarioProjectionResponse> {
  return requestJson(
    `${casePath(caseId)}/scenarios`,
    getJsonInit(),
    boundParser(parseScenarioProjectionResponse, (response) => {
      assertCaseId(response.case_id, caseId, "scenarios");
    }),
    options,
  );
}

export async function selectScenario(
  caseId: string,
  request: SelectScenarioRequest,
  options: FounderApiRequestOptions = {},
): Promise<ScenarioSelectionResponse> {
  return requestJson(
    `${casePath(caseId)}/scenarios/selection`,
    jsonInit(request),
    boundParser(parseScenarioSelectionResponse, (response) => {
      assertCaseId(response.case_id, caseId, "scenario_selection");
      assertRevision(response.data_revision, request.expected_case_revision, "scenario_selection");
      if (request.scenario_set_id !== null && response.scenario_set_id !== request.scenario_set_id) {
        throw new ApiContractError("scenario_selection scenario set mismatch");
      }
      if (response.new_scenario_key !== request.scenario_key) {
        throw new ApiContractError("scenario_selection scenario key mismatch");
      }
    }),
    options,
  );
}

export async function generateLaunchPack(
  caseId: string,
  request: GenerateLaunchPackRequest,
  options: FounderApiRequestOptions = {},
): Promise<LaunchPackMetadataResponse> {
  return requestJson(
    `${casePath(caseId)}/assets`,
    jsonInit(request),
    boundParser(parseLaunchPackMetadataResponse, (response) => {
      assertCaseId(response.case_id, caseId, "launch_pack");
      assertRevision(response.data_revision, request.expected_case_revision, "launch_pack");
      if (response.selected_scenario_key !== request.selected_scenario_key) {
        throw new ApiContractError("launch_pack selected scenario mismatch");
      }
      if (response.asset_key !== request.asset_type) {
        throw new ApiContractError("launch_pack asset mismatch");
      }
    }),
    options,
  );
}

export async function listCaseAssets(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<CaseAssetListResponse> {
  return requestJson(
    `${casePath(caseId)}/assets`,
    getJsonInit(),
    boundParser(parseCaseAssetListResponse, (response) => {
      assertCaseId(response.case_id, caseId, "case_assets");
    }),
    options,
  );
}

export async function getCaseAsset(
  caseId: string,
  assetId: string,
  options: FounderApiRequestOptions = {},
): Promise<LaunchPackMetadataResponse> {
  return requestJson(
    `${casePath(caseId)}/assets/${encodeURIComponent(assetId)}`,
    getJsonInit(),
    boundParser(parseLaunchPackMetadataResponse, (response) => {
      assertCaseId(response.case_id, caseId, "case_asset");
    }),
    options,
  );
}

export async function prepareResearchPlan(
  caseId: string,
  request: PrepareResearchPlanRequest,
  options: FounderApiRequestOptions = {},
): Promise<ResearchPlanResponse> {
  return requestJson(
    `${casePath(caseId)}/research/plans`,
    jsonInit(request),
    boundParser(parseResearchPlanResponse, (response) => {
      assertCaseId(response.case_id, caseId, "research_plan");
      assertRevision(response.data_revision, request.expected_case_revision, "research_plan");
    }),
    options,
  );
}

export async function queueResearchJob(
  caseId: string,
  request: QueueResearchJobRequest,
  options: FounderApiRequestOptions = {},
): Promise<ResearchJobResponse> {
  return requestJson(
    `${casePath(caseId)}/research/jobs`,
    jsonInit(request),
    boundParser(parseResearchJobResponse, (response) => {
      assertCaseId(response.case_id, caseId, "research_job");
      if (response.plan_id !== null && response.plan_id !== request.plan_id) {
        throw new ApiContractError("research_job plan mismatch");
      }
      if (response.plan_hash !== null && response.plan_hash !== request.plan_hash) {
        throw new ApiContractError("research_job plan hash mismatch");
      }
      if (response.old_revision !== null) {
        assertRevision(response.old_revision, request.expected_case_revision, "research_job");
      } else {
        assertRevision(response.data_revision, request.expected_case_revision, "research_job");
      }
    }),
    options,
  );
}

export async function getResearchJob(
  caseId: string,
  jobId: string,
  options: FounderApiRequestOptions = {},
): Promise<ResearchJobResponse> {
  return requestJson(
    `${casePath(caseId)}/research/jobs/${safeCaseSegment(jobId)}`,
    getJsonInit(),
    boundParser(parseResearchJobResponse, (response) => {
      assertCaseId(response.case_id, caseId, "research_job");
      if (response.job_id !== jobId) {
        throw new ApiContractError("research_job job mismatch");
      }
    }),
    options,
  );
}

export async function getStartupReportSnapshot(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<StartupReportSnapshotResponse> {
  return requestJson(
    reportArtifactUrl(caseId, "json"),
    getJsonInit(),
    parseStartupReportSnapshotResponse,
    options,
  );
}

export async function getAdvisorNextQuestion(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<AdvisorNextQuestionResponse> {
  return requestJson(
    `${casePath(caseId)}/advisor/next-question`,
    getJsonInit(),
    parseAdvisorNextQuestionResponse,
    options,
  );
}

export async function submitAdvisorAnswer(
  caseId: string,
  request: AdvisorAnswerRequest,
  options: FounderApiRequestOptions = {},
): Promise<AdvisorAnswerResponse> {
  return requestJson(
    `${casePath(caseId)}/advisor/answers`,
    jsonInit(request),
    parseAdvisorAnswerResponse,
    options,
  );
}

export async function getAdvisorImprovements(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<AdvisorImprovementsResponse> {
  return requestJson(
    `${casePath(caseId)}/advisor/improvements`,
    getJsonInit(),
    parseAdvisorImprovementsResponse,
    options,
  );
}

export async function decideAdvisorImprovement(
  caseId: string,
  proposalId: string,
  decision: AdvisorImprovementDecision,
  options: FounderApiRequestOptions = {},
): Promise<AdvisorImprovementDecisionResponse> {
  return requestJson(
    `${casePath(caseId)}/advisor/improvements/${safeCaseSegment(proposalId)}/decision`,
    jsonInit({ decision }),
    parseAdvisorImprovementDecisionResponse,
    options,
  );
}

export async function decideGate2(
  caseId: string,
  decision: StartupGate2Decision,
  options: FounderApiRequestOptions = {},
): Promise<StartupDecisionResult> {
  return requestJson(
    `${casePath(caseId)}/gate2/decision`,
    jsonInit(decision),
    parseStartupGate2DecisionResult,
    options,
  );
}

export async function decideGate3(
  caseId: string,
  decision: StartupGate3Decision,
  options: FounderApiRequestOptions = {},
): Promise<StartupDecisionResult> {
  return requestJson(
    `${casePath(caseId)}/gate3/decision`,
    jsonInit(decision),
    parseStartupGate3DecisionResult,
    options,
  );
}

export async function decideGate4(
  caseId: string,
  decision: StartupGate4Decision,
  options: FounderApiRequestOptions = {},
): Promise<StartupDecisionResult> {
  return requestJson(
    `${casePath(caseId)}/gate4/decision`,
    jsonInit(decision),
    parseStartupGate4DecisionResult,
    options,
  );
}

export async function getReport(
  caseId: string,
  options: FounderApiRequestOptions = {},
): Promise<StartupCaseReport> {
  const report = await requestJson(
    `${casePath(caseId)}/report`,
    getJsonInit(),
    parseStartupCaseReport,
    options,
  );
  return {
    ...report,
    json_url: reportArtifactUrl(caseId, "json"),
    html_url: reportArtifactUrl(caseId, "html"),
    pdf_url: reportArtifactUrl(caseId, "pdf"),
  };
}

export function reportArtifactUrl(
  caseId: string,
  artifact: ReportArtifact,
): string {
  return `${casePath(caseId)}/report/${artifact}`;
}

export async function downloadReportArtifact(
  caseId: string,
  artifact: ReportArtifact,
  options: FounderApiRequestOptions = {},
): Promise<Response> {
  const accepts: Record<ReportArtifact, string> = {
    json: "application/json",
    html: "text/html",
    pdf: "application/pdf",
  };
  const response = await performRequest(
    reportArtifactUrl(caseId, artifact),
    { method: "GET", headers: { Accept: accepts[artifact] } },
    options,
  );
  if (!response.ok) {
    throw await responseError(response);
  }
  return response;
}
