import type {
  ApiError,
  ProviderStatus,
  StartupCaseReport,
  StartupCaseStatus,
} from "./contracts.ts";

export type FounderWorkflowStage =
  | "idle"
  | "uploading"
  | "primary_queued"
  | "primary_intake"
  | "document_ready"
  | "gate2_preview_ready"
  | "gate2_approved"
  | "gate2_denied"
  | "primary_running"
  | "primary_deterministic_running"
  | "deep_running"
  | "gate3_review_required"
  | "gate4_pending"
  | "gate4_approved"
  | "gate4_rejected"
  | "report_draft_ready"
  | "report_pdf_ready"
  | "error";

export type FounderProviderSignal =
  | "provider_unavailable"
  | "offline_fixture_active"
  | null;

export type FounderClientActivity =
  | "uploading"
  | "upload_accepted"
  | "primary_intake"
  | "document_ready"
  | "submitting_gate2_approved"
  | "submitting_gate2_denied"
  | "primary_running"
  | "deep_running"
  | "research_preparing"
  | "research_searching"
  | "research_recalculating"
  | "advisor_refreshing"
  | "advisor_answering"
  | "advisor_deciding"
  | "copilot_saving_fact"
  | "copilot_saving_assumption"
  | "copilot_sending_message"
  | "scenario_selecting"
  | "asset_generating"
  | "launch_pack_generating"
  | "submitting_gate3"
  | "submitting_gate4_approved"
  | "submitting_gate4_rejected";

export type FounderStateInput = Readonly<{
  status?: StartupCaseStatus | null;
  report?: StartupCaseReport | null;
  activity?: FounderClientActivity | null;
  providerStatus?: ProviderStatus | null;
  error?: ApiError | Error | null;
}>;

export type FounderDisplayState = Readonly<{
  stage: FounderWorkflowStage;
  providerSignal: FounderProviderSignal;
}>;

export type FounderNextActionKind =
  | "upload_documents"
  | "wait_for_upload"
  | "wait_for_analysis"
  | "review_gate2"
  | "review_gate3"
  | "wait_for_report"
  | "review_gate4"
  | "wait_for_pdf"
  | "download_pdf"
  | "retry_request"
  | "fix_upload"
  | "restart_case"
  | "refresh_gate2"
  | "retry_pdf"
  | "contact_support";

export type FounderNextAction = Readonly<{
  kind: FounderNextActionKind;
  enabled: boolean;
}>;

export type PollingStopReason =
  | "poll"
  | "aborted"
  | "gate_waiting"
  | "terminal"
  | "client_request"
  | "idle";

export type PollingDecision = Readonly<{
  shouldPoll: boolean;
  delayMs: number | null;
  reason: PollingStopReason;
}>;

export type PollingOptions = Readonly<{
  attempt: number;
  serverHintMs?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  signal?: Readonly<{ aborted: boolean }>;
}>;

export type RecoveryAction =
  | "retry_request"
  | "fix_upload"
  | "restart_case"
  | "wait_for_analysis"
  | "refresh_gate2"
  | "review_gate2"
  | "review_gate3"
  | "wait_for_report"
  | "review_gate4"
  | "retry_pdf"
  | "contact_support";

export type ApiErrorRecovery = Readonly<{
  action: RecoveryAction;
  retryable: boolean;
  preserveCase: boolean;
}>;

const DEFAULT_POLL_DELAY_MS = 750;
const DEFAULT_MAX_POLL_DELAY_MS = 8_000;

function providerSignal(input: FounderStateInput): FounderProviderSignal {
  const status = input.status?.provider_status ?? input.providerStatus;
  if (status === "unavailable") {
    return "provider_unavailable";
  }
  if (status === "deterministic_offline_fixture") {
    return "offline_fixture_active";
  }
  return null;
}

function stageFromActivity(
  activity: FounderClientActivity | null | undefined,
  provider: FounderProviderSignal,
): FounderWorkflowStage | null {
  switch (activity) {
    case "uploading":
      return "uploading";
    case "upload_accepted":
      return "primary_queued";
    case "primary_intake":
      return "primary_intake";
    case "document_ready":
      return "document_ready";
    case "submitting_gate2_approved":
      return "gate2_approved";
    case "submitting_gate2_denied":
      return "gate2_denied";
    case "primary_running":
      return provider === "offline_fixture_active"
        ? "primary_deterministic_running"
        : "primary_running";
    case "deep_running":
      return "deep_running";
    case "research_preparing":
    case "research_searching":
    case "research_recalculating":
      return "deep_running";
    case "submitting_gate3":
      return "gate4_pending";
    case "submitting_gate4_approved":
      return "gate4_approved";
    case "submitting_gate4_rejected":
      return "gate4_rejected";
    default:
      return null;
  }
}

function deriveStage(
  input: FounderStateInput,
  provider: FounderProviderSignal,
): FounderWorkflowStage {
  const status = input.status;
  const report = input.report;

  if ((input.error && errorCode(input.error) !== "research_no_useful_result") || status?.analysis_status === "failed") {
    return "error";
  }

  if (report?.freeze_status === "approved" && report.pdf_status === "ready") {
    return "report_pdf_ready";
  }

  if (input.activity === "submitting_gate4_rejected") {
    return "gate4_rejected";
  }
  if (input.activity === "submitting_gate4_approved") {
    return "gate4_approved";
  }

  if (status?.gate4_status === "completed" && report) {
    return report.freeze_status === "approved"
      ? "gate4_approved"
      : "gate4_rejected";
  }

  if (report || status?.report_status === "ready") {
    return "report_draft_ready";
  }

  if (input.activity === "submitting_gate3") {
    return "gate4_pending";
  }
  if (status?.analysis_status === "analysis_complete_report_pending") {
    return "gate4_pending";
  }

  if (input.activity === "submitting_gate2_approved") {
    return "gate2_approved";
  }
  if (input.activity === "submitting_gate2_denied") {
    return "gate2_denied";
  }

  if (
    status?.gate2_status === "required" ||
    status?.analysis_status === "gate2_preview_ready"
  ) {
    return "gate2_preview_ready";
  }

  if (
    status?.gate3_status === "required" ||
    status?.analysis_status === "gate3_review_required"
  ) {
    return "gate3_review_required";
  }

  const activeStage = stageFromActivity(input.activity, provider);
  if (activeStage) {
    return activeStage;
  }

  if (status?.analysis_status === "awaiting_start") {
    return "primary_queued";
  }

  return "idle";
}

export function deriveFounderDisplayState(
  input: FounderStateInput,
): FounderDisplayState {
  const signal = providerSignal(input);
  return {
    stage: deriveStage(input, signal),
    providerSignal: signal,
  };
}

export function deriveNextAction(input: FounderStateInput): FounderNextAction {
  const stage = deriveFounderDisplayState(input).stage;

  if (stage === "error") {
    const recovery = mapApiErrorToRecovery(input.error);
    return {
      kind: recovery.action,
      enabled: recovery.action !== "wait_for_analysis",
    };
  }

  switch (stage) {
    case "idle":
      return { kind: "upload_documents", enabled: true };
    case "uploading":
      return { kind: "wait_for_upload", enabled: false };
    case "primary_queued":
    case "primary_intake":
    case "document_ready":
    case "gate2_approved":
    case "gate2_denied":
    case "primary_running":
    case "primary_deterministic_running":
    case "deep_running":
      return { kind: "wait_for_analysis", enabled: false };
    case "gate2_preview_ready":
      return { kind: "review_gate2", enabled: true };
    case "gate3_review_required":
      return { kind: "review_gate3", enabled: true };
    case "gate4_pending":
      return { kind: "wait_for_report", enabled: false };
    case "report_draft_ready":
    case "gate4_rejected":
      return { kind: "review_gate4", enabled: true };
    case "gate4_approved":
      return { kind: "wait_for_pdf", enabled: false };
    case "report_pdf_ready":
      return { kind: "download_pdf", enabled: true };
  }
}

export function derivePollingDecision(
  input: FounderStateInput,
  options: PollingOptions,
): PollingDecision {
  if (options.signal?.aborted) {
    return { shouldPoll: false, delayMs: null, reason: "aborted" };
  }

  const stage = deriveFounderDisplayState(input).stage;
  if (stage === "uploading") {
    return { shouldPoll: false, delayMs: null, reason: "client_request" };
  }
  if (stage === "idle") {
    return { shouldPoll: false, delayMs: null, reason: "idle" };
  }
  if (
    stage === "report_pdf_ready" ||
    stage === "gate4_rejected" ||
    stage === "error"
  ) {
    return { shouldPoll: false, delayMs: null, reason: "terminal" };
  }
  if (
    stage === "gate2_preview_ready" ||
    stage === "gate3_review_required" ||
    stage === "report_draft_ready"
  ) {
    return { shouldPoll: false, delayMs: null, reason: "gate_waiting" };
  }

  const baseDelay = positiveFiniteOr(options.baseDelayMs, DEFAULT_POLL_DELAY_MS);
  const maxDelay = Math.max(
    baseDelay,
    positiveFiniteOr(options.maxDelayMs, DEFAULT_MAX_POLL_DELAY_MS),
  );
  const serverHint = nonNegativeFiniteOr(options.serverHintMs, 0);
  const seedDelay = Math.max(baseDelay, serverHint);
  const attempt = Math.max(
    0,
    Math.floor(nonNegativeFiniteOr(options.attempt, 0)),
  );
  const multiplier = 2 ** Math.min(attempt, 30);

  return {
    shouldPoll: true,
    delayMs: Math.min(maxDelay, seedDelay * multiplier),
    reason: "poll",
  };
}

function positiveFiniteOr(value: number | undefined, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? value
    : fallback;
}

function nonNegativeFiniteOr(
  value: number | undefined,
  fallback: number,
): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : fallback;
}

function errorCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("code" in error)) {
    return null;
  }
  return typeof error.code === "string" ? error.code : null;
}

function recovery(
  action: RecoveryAction,
  retryable: boolean,
): ApiErrorRecovery {
  return {
    action,
    retryable,
    preserveCase: action !== "restart_case",
  };
}

export function mapApiErrorToRecovery(error: unknown): ApiErrorRecovery {
  switch (errorCode(error)) {
    case "api_unreachable":
    case "api_timeout":
    case "startup_profile_not_ready":
    case "startup_profile_stale":
    case "startup_gtm_not_ready":
    case "startup_gtm_stale":
    case "startup_report_snapshot_stale":
      return recovery("retry_request", true);
    case "startup_market_fixture_unavailable":
      return recovery("contact_support", false);
    case "empty_upload":
    case "unsafe_path":
    case "request_validation_error":
    case "invalid_fixture_mode":
    case "startup_document_intelligence_input_invalid":
      return recovery("fix_upload", false);
    case "case_not_found":
      return recovery("restart_case", false);
    case "gate2_preview_not_ready":
      return recovery("wait_for_analysis", true);
    case "resume_token_invalid":
      return recovery("refresh_gate2", false);
    case "invalid_gate2_decision":
      return recovery("review_gate2", false);
    case "invalid_gate3_decision":
    case "invalid_gate3_exclusions":
    case "unknown_evidence_fact_id":
      return recovery("review_gate3", false);
    case "report_not_ready":
      return recovery("wait_for_report", true);
    case "gate_4_freeze_required":
    case "gate_4_snapshot_mismatch":
    case "invalid_gate4_decision":
      return recovery("review_gate4", false);
    case "report_renderer_unavailable":
      return recovery("retry_pdf", true);
    case "gate2_resume_failed":
      return recovery("restart_case", false);
    case "api_rejected":
    case "invalid_contract":
    default:
      return recovery("contact_support", false);
  }
}
