import assert from "node:assert/strict";
import test from "node:test";

import type {
  ApiError,
  StartupCaseReport,
  StartupCaseStatus,
} from "./contracts.ts";
import {
  deriveFounderDisplayState,
  deriveNextAction,
  derivePollingDecision,
  mapApiErrorToRecovery,
  type FounderStateInput,
} from "./startup-state-machine.ts";

function caseStatus(
  overrides: Partial<StartupCaseStatus> = {},
): StartupCaseStatus {
  return {
    case_id: "case-1",
    case_status: "awaiting_upload",
    analysis_status: "awaiting_upload",
    provider_status: "configured",
    data_revision: 0,
    active_analysis_thread_id: "case-1",
    langgraph_checkpoint: null,
    gate2_status: "not_ready",
    gate3_status: "not_ready",
    gate4_status: "not_ready",
    report_status: "not_ready",
    snapshot_hash: null,
    snapshot_revision: null,
    ...overrides,
  };
}

function report(
  overrides: Partial<StartupCaseReport> = {},
): StartupCaseReport {
  return {
    case_id: "case-1",
    report_status: "ready",
    snapshot_id: "snapshot-1",
    snapshot_hash: "sha256:report",
    snapshot_revision: 1,
    json_url: "/api/startup/cases/case-1/report/json",
    html_url: "/api/startup/cases/case-1/report/html",
    pdf_url: "/api/startup/cases/case-1/report/pdf",
    freeze_status: "required",
    pdf_status: "freeze_required",
    ...overrides,
  };
}

test("maps the complete founder case path without inventing backend statuses", () => {
  const path: readonly Readonly<{
    input: FounderStateInput;
    expected: string;
  }>[] = [
    { input: {}, expected: "idle" },
    {
      input: { status: caseStatus(), activity: "uploading" },
      expected: "uploading",
    },
    {
      input: {
        status: caseStatus({ analysis_status: "awaiting_start" }),
        activity: "upload_accepted",
      },
      expected: "primary_queued",
    },
    {
      input: {
        status: caseStatus({ analysis_status: "awaiting_start" }),
        activity: "primary_intake",
      },
      expected: "primary_intake",
    },
    {
      input: {
        status: caseStatus({ analysis_status: "awaiting_start" }),
        activity: "document_ready",
      },
      expected: "document_ready",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "gate2_preview_ready",
          gate2_status: "required",
        }),
      },
      expected: "gate2_preview_ready",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "gate2_preview_ready",
          gate2_status: "required",
        }),
        activity: "submitting_gate2_approved",
      },
      expected: "gate2_approved",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "gate2_preview_ready",
          gate2_status: "required",
          provider_status: "unavailable",
        }),
        activity: "submitting_gate2_denied",
      },
      expected: "gate2_denied",
    },
    {
      input: {
        status: caseStatus({ gate2_status: "completed" }),
        activity: "primary_running",
      },
      expected: "primary_running",
    },
    {
      input: {
        status: caseStatus({
          provider_status: "deterministic_offline_fixture",
          gate2_status: "completed",
        }),
        activity: "primary_running",
      },
      expected: "primary_deterministic_running",
    },
    {
      input: {
        status: caseStatus({ gate2_status: "completed" }),
        activity: "deep_running",
      },
      expected: "deep_running",
    },
    {
      input: {
        status: caseStatus({ gate2_status: "completed" }),
        activity: "research_preparing",
      },
      expected: "deep_running",
    },
    {
      input: {
        status: caseStatus({ gate2_status: "completed" }),
        activity: "research_searching",
      },
      expected: "deep_running",
    },
    {
      input: {
        status: caseStatus({ gate2_status: "completed" }),
        activity: "research_recalculating",
      },
      expected: "deep_running",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "gate3_review_required",
          gate2_status: "completed",
          gate3_status: "required",
        }),
      },
      expected: "gate3_review_required",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "gate3_review_required",
          gate2_status: "completed",
          gate3_status: "required",
        }),
        activity: "submitting_gate3",
      },
      expected: "gate4_pending",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "analysis_complete_report_pending",
          gate2_status: "completed",
          gate3_status: "completed",
          report_status: "ready",
          snapshot_hash: "sha256:report",
          snapshot_revision: 1,
        }),
        report: report(),
      },
      expected: "report_draft_ready",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "analysis_complete_report_pending",
          gate2_status: "completed",
          gate3_status: "completed",
          gate4_status: "completed",
          report_status: "ready",
          snapshot_hash: "sha256:report",
          snapshot_revision: 1,
        }),
        report: report({ freeze_status: "approved", pdf_status: "not_ready" }),
      },
      expected: "gate4_approved",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "analysis_complete_report_pending",
          gate2_status: "completed",
          gate3_status: "completed",
          gate4_status: "completed",
          report_status: "ready",
          snapshot_hash: "sha256:report",
          snapshot_revision: 1,
        }),
        report: report({ freeze_status: "approved", pdf_status: "ready" }),
      },
      expected: "report_pdf_ready",
    },
  ];

  for (const step of path) {
    assert.equal(deriveFounderDisplayState(step.input).stage, step.expected);
  }
});

test("keeps provider availability as a display signal without hiding workflow progress", () => {
  const unavailable = deriveFounderDisplayState({
    status: caseStatus({
      analysis_status: "gate2_preview_ready",
      gate2_status: "required",
      provider_status: "unavailable",
    }),
  });
  const fixture = deriveFounderDisplayState({
    status: caseStatus({
      provider_status: "deterministic_offline_fixture",
      analysis_status: "awaiting_start",
    }),
    activity: "primary_running",
  });

  assert.deepEqual(unavailable, {
    stage: "gate2_preview_ready",
    providerSignal: "provider_unavailable",
  });
  assert.deepEqual(fixture, {
    stage: "primary_deterministic_running",
    providerSignal: "offline_fixture_active",
  });
});

test("uses backend gate and report progress ahead of stale client activity", () => {
  const gate3 = deriveFounderDisplayState({
    status: caseStatus({
      analysis_status: "gate3_review_required",
      gate2_status: "completed",
      gate3_status: "required",
    }),
    activity: "primary_running",
  });
  const finalReport = deriveFounderDisplayState({
    status: caseStatus({
      analysis_status: "analysis_complete_report_pending",
      gate2_status: "completed",
      gate3_status: "completed",
      gate4_status: "completed",
      report_status: "ready",
      snapshot_hash: "sha256:report",
      snapshot_revision: 1,
    }),
    report: report({ freeze_status: "approved", pdf_status: "ready" }),
    activity: "submitting_gate4_approved",
  });

  assert.equal(gate3.stage, "gate3_review_required");
  assert.equal(finalReport.stage, "report_pdf_ready");
});

test("distinguishes rejected Gate 4 from an approved report awaiting PDF", () => {
  const rejected = deriveFounderDisplayState({
    status: caseStatus({
      analysis_status: "analysis_complete_report_pending",
      gate2_status: "completed",
      gate3_status: "completed",
      gate4_status: "completed",
      report_status: "ready",
      snapshot_hash: "sha256:report",
      snapshot_revision: 1,
    }),
    report: report(),
  });
  const approved = deriveFounderDisplayState({
    status: caseStatus({
      analysis_status: "analysis_complete_report_pending",
      gate2_status: "completed",
      gate3_status: "completed",
      gate4_status: "completed",
      report_status: "ready",
      snapshot_hash: "sha256:report",
      snapshot_revision: 1,
    }),
    report: report({ freeze_status: "approved", pdf_status: "not_ready" }),
  });

  assert.equal(rejected.stage, "gate4_rejected");
  assert.equal(approved.stage, "gate4_approved");
});

test("derives one actionable founder step for each waiting boundary", () => {
  const states: readonly Readonly<{
    input: FounderStateInput;
    expected: string;
  }>[] = [
    { input: {}, expected: "upload_documents" },
    {
      input: {
        status: caseStatus({ analysis_status: "awaiting_start" }),
        activity: "primary_intake",
      },
      expected: "wait_for_analysis",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "gate2_preview_ready",
          gate2_status: "required",
        }),
      },
      expected: "review_gate2",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "gate3_review_required",
          gate2_status: "completed",
          gate3_status: "required",
        }),
      },
      expected: "review_gate3",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "analysis_complete_report_pending",
          gate2_status: "completed",
          gate3_status: "completed",
          report_status: "ready",
          snapshot_hash: "sha256:report",
          snapshot_revision: 1,
        }),
        report: report(),
      },
      expected: "review_gate4",
    },
    {
      input: {
        status: caseStatus({
          analysis_status: "analysis_complete_report_pending",
          gate2_status: "completed",
          gate3_status: "completed",
          gate4_status: "completed",
          report_status: "ready",
          snapshot_hash: "sha256:report",
          snapshot_revision: 1,
        }),
        report: report({ freeze_status: "approved", pdf_status: "ready" }),
      },
      expected: "download_pdf",
    },
  ];

  for (const item of states) {
    assert.equal(deriveNextAction(item.input).kind, item.expected);
  }
});

test("polling uses jitter-free capped exponential backoff", () => {
  const input: FounderStateInput = {
    status: caseStatus({ analysis_status: "awaiting_start" }),
    activity: "primary_running",
  };

  assert.deepEqual(
    [0, 1, 2, 3, 4, 20].map((attempt) =>
      derivePollingDecision(input, { attempt }).delayMs,
    ),
    [750, 1500, 3000, 6000, 8000, 8000],
  );
  assert.equal(
    derivePollingDecision(input, { attempt: 1, serverHintMs: 2000 }).delayMs,
    4000,
  );
});

test("polling stops on gates, terminal states, client-owned requests, and abort", () => {
  const gate2: FounderStateInput = {
    status: caseStatus({
      analysis_status: "gate2_preview_ready",
      gate2_status: "required",
    }),
  };
  const finalReport: FounderStateInput = {
    status: caseStatus({
      analysis_status: "analysis_complete_report_pending",
      gate2_status: "completed",
      gate3_status: "completed",
      gate4_status: "completed",
      report_status: "ready",
      snapshot_hash: "sha256:report",
      snapshot_revision: 1,
    }),
    report: report({ freeze_status: "approved", pdf_status: "ready" }),
  };
  const uploading: FounderStateInput = {
    status: caseStatus(),
    activity: "uploading",
  };
  const running: FounderStateInput = {
    status: caseStatus({ analysis_status: "awaiting_start" }),
    activity: "deep_running",
  };

  assert.deepEqual(derivePollingDecision(gate2, { attempt: 0 }), {
    shouldPoll: false,
    delayMs: null,
    reason: "gate_waiting",
  });
  assert.deepEqual(derivePollingDecision(finalReport, { attempt: 0 }), {
    shouldPoll: false,
    delayMs: null,
    reason: "terminal",
  });
  assert.deepEqual(derivePollingDecision(uploading, { attempt: 0 }), {
    shouldPoll: false,
    delayMs: null,
    reason: "client_request",
  });
  assert.deepEqual(
    derivePollingDecision(running, {
      attempt: 2,
      signal: { aborted: true },
    }),
    {
      shouldPoll: false,
      delayMs: null,
      reason: "aborted",
    },
  );
});

test("polling continues while the startup report builds and until approved PDF is ready", () => {
  const reportBuilding: FounderStateInput = {
    status: caseStatus({
      analysis_status: "analysis_complete_report_pending",
      gate2_status: "completed",
      gate3_status: "completed",
      report_status: "pending",
    }),
  };
  const approvedPdfPending: FounderStateInput = {
    status: caseStatus({
      analysis_status: "analysis_complete_report_pending",
      gate2_status: "completed",
      gate3_status: "completed",
      gate4_status: "completed",
      report_status: "ready",
      snapshot_hash: "sha256:report",
      snapshot_revision: 1,
    }),
    report: report({ freeze_status: "approved", pdf_status: "not_ready" }),
  };

  assert.deepEqual(derivePollingDecision(reportBuilding, { attempt: 1 }), {
    shouldPoll: true,
    delayMs: 1500,
    reason: "poll",
  });
  assert.deepEqual(derivePollingDecision(approvedPdfPending, { attempt: 2 }), {
    shouldPoll: true,
    delayMs: 3000,
    reason: "poll",
  });
});

test("maps API errors to deterministic recovery without retrying invalid input", () => {
  const cases: readonly Readonly<{
    error: ApiError | Error;
    action: string;
    retryable: boolean;
  }>[] = [
    {
      error: { code: "api_timeout", message: "timed out" },
      action: "retry_request",
      retryable: true,
    },
    {
      error: { code: "empty_upload", message: "empty" },
      action: "fix_upload",
      retryable: false,
    },
    {
      error: {
        code: "startup_document_intelligence_input_invalid",
        message: "startup_document_intelligence_input_invalid",
      },
      action: "fix_upload",
      retryable: false,
    },
    {
      error: { code: "case_not_found", message: "missing" },
      action: "restart_case",
      retryable: false,
    },
    {
      error: { code: "resume_token_invalid", message: "expired" },
      action: "refresh_gate2",
      retryable: false,
    },
    {
      error: { code: "invalid_gate3_exclusions", message: "invalid" },
      action: "review_gate3",
      retryable: false,
    },
    {
      error: { code: "startup_gtm_not_ready", message: "pending" },
      action: "retry_request",
      retryable: true,
    },
    {
      error: { code: "startup_gtm_stale", message: "stale" },
      action: "retry_request",
      retryable: true,
    },
    {
      error: { code: "startup_profile_not_ready", message: "pending" },
      action: "retry_request",
      retryable: true,
    },
    {
      error: { code: "startup_profile_stale", message: "stale" },
      action: "retry_request",
      retryable: true,
    },
    {
      error: { code: "startup_report_snapshot_stale", message: "stale" },
      action: "retry_request",
      retryable: true,
    },
    {
      error: { code: "startup_market_fixture_unavailable", message: "unavailable" },
      action: "contact_support",
      retryable: false,
    },
    {
      error: { code: "report_not_ready", message: "pending" },
      action: "wait_for_report",
      retryable: true,
    },
    {
      error: { code: "gate_4_snapshot_mismatch", message: "stale" },
      action: "review_gate4",
      retryable: false,
    },
    {
      error: { code: "report_renderer_unavailable", message: "renderer" },
      action: "retry_pdf",
      retryable: true,
    },
    {
      error: new Error("unknown"),
      action: "contact_support",
      retryable: false,
    },
  ];

  for (const item of cases) {
    const recovery = mapApiErrorToRecovery(item.error);
    assert.equal(recovery.action, item.action);
    assert.equal(recovery.retryable, item.retryable);
    assert.equal(recovery.preserveCase, item.action !== "restart_case");
  }
});

test("backend failure and unknown client failure both enter the error state", () => {
  const backendFailure = deriveFounderDisplayState({
    status: caseStatus({ analysis_status: "failed" }),
  });
  const clientFailure = deriveFounderDisplayState({
    status: caseStatus({ analysis_status: "awaiting_start" }),
    error: new Error("network exploded"),
  });

  assert.equal(backendFailure.stage, "error");
  assert.equal(clientFailure.stage, "error");
  assert.equal(deriveNextAction({ error: new Error("unknown") }).kind, "contact_support");
});

test("keeps the current Gate 2 preview authoritative over stale downstream Gate 3 state", () => {
  const display = deriveFounderDisplayState({
    status: caseStatus({
      analysis_status: "gate2_preview_ready",
      gate2_status: "required",
      gate3_status: "required",
      data_revision: 3,
    }),
  });

  assert.equal(display.stage, "gate2_preview_ready");
});

test("does not offer a retry loop when packaged market fixtures are missing", () => {
  const error: ApiError = {
    code: "startup_market_fixture_unavailable",
    message: "unavailable",
  };

  assert.deepEqual(mapApiErrorToRecovery(error), {
    action: "contact_support",
    retryable: false,
    preserveCase: true,
  });
  assert.deepEqual(deriveNextAction({ error }), {
    kind: "contact_support",
    enabled: true,
  });
});
