import assert from "node:assert/strict";
import test from "node:test";

import { FOUNDER_API_REQUEST_TIMEOUT_MS } from "./founder-api-client.ts";
import {
  FounderApiProxyError,
  STARTUP_PROXY_REQUEST_TIMEOUT_MS,
  buildStartupProxyRequest,
  mapSameOriginStartupPath,
  proxyFounderApi,
  startupRouteManifest,
} from "./startup-proxy.ts";

test("keeps long-running startup requests bounded without cutting off the API proxy first", () => {
  assert.equal(STARTUP_PROXY_REQUEST_TIMEOUT_MS, 55_000);
  assert.equal(FOUNDER_API_REQUEST_TIMEOUT_MS, 60_000);
  assert.ok(STARTUP_PROXY_REQUEST_TIMEOUT_MS < FOUNDER_API_REQUEST_TIMEOUT_MS);
});

test("maps exact same-origin startup routes to api v1 paths without path escape", () => {
  assert.equal(
    mapSameOriginStartupPath("/api/startup/cases/case-1/gate2/preview"),
    "/api/v1/startup/cases/case-1/gate2/preview",
  );
  assert.equal(
    mapSameOriginStartupPath("/api/startup/cases/case-1/report/json"),
    "/api/v1/startup/cases/case-1/report/json",
  );
  assert.equal(
    mapSameOriginStartupPath("/api/startup/cases/case-1/profile"),
    "/api/v1/startup/cases/case-1/profile",
  );
  assert.equal(
    mapSameOriginStartupPath("/api/startup/cases/case-1/gtm"),
    "/api/v1/startup/cases/case-1/gtm",
  );
  assert.equal(
    mapSameOriginStartupPath("/api/startup/cases/case-1/copilot/state"),
    "/api/v1/startup/cases/case-1/copilot/state",
  );
  assert.equal(
    mapSameOriginStartupPath("/api/startup/cases/case-1/scenarios/selection"),
    "/api/v1/startup/cases/case-1/scenarios/selection",
  );
  assert.equal(
    mapSameOriginStartupPath("/api/startup/cases/case-1/research/jobs/job-1"),
    "/api/v1/startup/cases/case-1/research/jobs/job-1",
  );
  assert.equal(
    mapSameOriginStartupPath("/api/startup/cases/case-1/advisor/next-question"),
    "/api/v1/startup/cases/case-1/advisor/next-question",
  );
  assert.equal(
    mapSameOriginStartupPath("/api/startup/cases/case-1/advisor/improvements/proposal-1/decision"),
    "/api/v1/startup/cases/case-1/advisor/improvements/proposal-1/decision",
  );
  assert.equal(
    mapSameOriginStartupPath("/api/capabilities"),
    "/api/v1/product/capabilities",
  );
  assert.throws(
    () =>
      mapSameOriginStartupPath(
        "https://founder.local/api/startup/cases/case-1/report",
      ),
    /unsafe_path/,
  );
  assert.throws(
    () => mapSameOriginStartupPath("//founder.local/api/startup/cases/case-1"),
    /unsafe_path/,
  );
  assert.throws(
    () => mapSameOriginStartupPath("javascript:/api/startup/cases/case-1"),
    /unsafe_path/,
  );
  assert.throws(
    () => mapSameOriginStartupPath("/api/startup/cases/../admin"),
    /unsafe_path/,
  );
  assert.throws(
    () => mapSameOriginStartupPath("/api/startup/cases/%2e%2e/admin"),
    /unsafe_path/,
  );
  assert.throws(
    () => mapSameOriginStartupPath("/api/startup/cases/case%2F1/report"),
    /unsafe_path/,
  );
  assert.throws(
    () => mapSameOriginStartupPath("/api/startup/cases/case%252F1/report"),
    /unsafe_path/,
  );
  assert.throws(
    () => mapSameOriginStartupPath("/api/startup/cases/case%2F1/gate2/preview"),
    /unsafe_path/,
  );
  assert.throws(
    () =>
      mapSameOriginStartupPath(
        "/api/startup/cases/case-1/advisor/improvements/proposal%2F1/decision",
      ),
    /unsafe_path/,
  );
  assert.throws(
    () => mapSameOriginStartupPath("/api/startup/cases/case-1\\admin"),
    /unsafe_path/,
  );
  assert.throws(
    () => mapSameOriginStartupPath("/api/admin?path=/api/startup/cases"),
    /unsafe_path/,
  );
});

test("proxy preserves upstream typed startup 404 and 409 error contracts", async () => {
  const notFound = await proxyFounderApi(
    new Request("http://localhost/api/startup/cases/missing/report", {
      method: "GET",
    }),
    {
      upstreamBaseUrl: "http://127.0.0.1:8000",
      timeoutMs: 1000,
      fetcher: async () =>
        Response.json(
          { code: "report_not_ready", message: "Report is not ready" },
          { status: 404 },
        ),
    },
  );
  const conflict = await proxyFounderApi(
    new Request("http://localhost/api/startup/cases/case-1/report/pdf", {
      method: "GET",
    }),
    {
      upstreamBaseUrl: "http://127.0.0.1:8000",
      timeoutMs: 1000,
      fetcher: async () =>
        Response.json(
          {
            code: "gate_4_freeze_required",
            message: "Gate 4 approval is required",
          },
          { status: 409 },
        ),
    },
  );

  assert.equal(notFound.status, 404);
  assert.deepEqual(await notFound.json(), {
    code: "report_not_ready",
    message: "Report is not ready",
  });
  assert.equal(conflict.status, 409);
  assert.deepEqual(await conflict.json(), {
    code: "gate_4_freeze_required",
    message: "Gate 4 approval is required",
  });
});

test("proxy preserves every backend startup error code with original status and safe body", async () => {
  const backendStartupErrors = [
    ["case_not_found", 404],
    ["gate2_preview_not_ready", 404],
    ["report_not_ready", 404],
    ["empty_upload", 422],
    ["invalid_gate2_decision", 422],
    ["invalid_gate3_decision", 422],
    ["invalid_gate3_exclusions", 422],
    ["unknown_evidence_fact_id", 422],
    ["startup_profile_not_ready", 409],
    ["startup_profile_stale", 409],
    ["invalid_gate4_decision", 422],
    ["invalid_fixture_mode", 422],
    ["request_validation_error", 422],
    ["resume_token_invalid", 409],
    ["gate2_resume_failed", 409],
    ["gate_4_snapshot_mismatch", 409],
    ["gate_4_freeze_required", 409],
    ["report_renderer_unavailable", 503],
    ["advisor_question_stale", 409],
    ["advisor_answer_type_invalid", 422],
    ["advisor_manual_answer_semantic_mismatch", 422],
    ["advisor_answer_shape_invalid", 422],
    ["advisor_answer_type_unavailable", 409],
    ["advisor_improvements_not_ready", 409],
    ["advisor_proposal_unknown", 404],
    ["advisor_proposal_stale", 409],
    ["advisor_decision_conflict", 409],
    ["case_revision_conflict", 409],
    ["stale_research_plan", 409],
    ["private_public_research_rejected", 422],
    ["public_research_consent_required", 422],
    ["idempotency_key_conflict", 409],
    ["research_plan_not_found", 404],
    ["research_job_not_found", 404],
    ["research_job_already_running", 409],
    ["copilot_action_snapshot_corrupt", 409],
    ["fact_validation_failed", 422],
  ] as const;

  for (const [code, status] of backendStartupErrors) {
    const response = await proxyFounderApi(
      new Request("http://localhost/api/startup/cases/case-1/report", {
        method: "GET",
      }),
      {
        upstreamBaseUrl: "http://127.0.0.1:8000",
        timeoutMs: 1000,
        fetcher: async () =>
          Response.json({ code, message: `${code} message` }, { status }),
      },
    );

    assert.equal(response.status, status, code);
    assert.deepEqual(
      await response.json(),
      { code, message: `${code} message` },
      code,
    );
  }
});

test("proxy preserves backend fact validation failures with safe field errors", async () => {
  const response = await proxyFounderApi(
    new Request("http://localhost/api/startup/cases/case-1/facts", {
      method: "POST",
      body: JSON.stringify({}),
    }),
    {
      upstreamBaseUrl: "http://127.0.0.1:8000",
      timeoutMs: 1000,
      fetcher: async () =>
        Response.json(
          {
            code: "fact_validation_failed",
            message: "Founder fact validation failed",
            errors: [{ field: "value.amount", message: "must be numeric" }],
          },
          { status: 422 },
        ),
    },
  );

  assert.equal(response.status, 422);
  assert.deepEqual(await response.json(), {
    code: "fact_validation_failed",
    message: "Founder fact validation failed",
    errors: [{ field: "value.amount", message: "must be numeric" }],
  });
});

test("proxy rejects malformed or unsafe backend validation errors without reflecting them", async () => {
  const hostileErrors = [
    { label: "non-array errors", errors: { field: "value.amount", message: "must be numeric" } },
    { label: "unknown entry key", errors: [{ field: "value.amount", message: "must be numeric", leak: "secret" }] },
    { label: "blank field", errors: [{ field: " ", message: "must be numeric" }] },
    { label: "unsafe field", errors: [{ field: "../../secret", message: "must be numeric" }] },
    { label: "blank message", errors: [{ field: "value.amount", message: " " }] },
    { label: "unsafe message", errors: [{ field: "value.amount", message: "stack trace D:/secret token=abc" }] },
  ] as const;

  for (const entry of hostileErrors) {
    const response = await proxyFounderApi(
      new Request("http://localhost/api/startup/cases/case-1/facts", {
        method: "POST",
        body: JSON.stringify({}),
      }),
      {
        upstreamBaseUrl: "http://127.0.0.1:8000",
        timeoutMs: 1000,
        fetcher: async () =>
          Response.json(
            {
              code: "fact_validation_failed",
              message: "Founder fact validation failed",
              errors: entry.errors,
            },
            { status: 422 },
          ),
      },
    );

    assert.equal(response.status, 502, entry.label);
    assert.deepEqual(
      await response.json(),
      {
        code: "api_rejected",
        message: "Founder API request was rejected",
      },
      entry.label,
    );
  }
});

test("proxy rejects field errors attached to non-fact-validation backend codes", async () => {
  const masqueradingErrors = [
    { code: "case_not_found", status: 404 },
    { code: "case_revision_conflict", status: 409 },
  ] as const;

  for (const entry of masqueradingErrors) {
    const response = await proxyFounderApi(
      new Request("http://localhost/api/startup/cases/case-1/facts", {
        method: "POST",
        body: JSON.stringify({}),
      }),
      {
        upstreamBaseUrl: "http://127.0.0.1:8000",
        timeoutMs: 1000,
        fetcher: async () =>
          Response.json(
            {
              code: entry.code,
              message: `${entry.code} message`,
              errors: [{ field: "value.amount", message: "must be numeric" }],
            },
            { status: entry.status },
          ),
      },
    );

    assert.equal(response.status, 502, entry.code);
    assert.deepEqual(
      await response.json(),
      {
        code: "api_rejected",
        message: "Founder API request was rejected",
      },
      entry.code,
    );
  }
});

test("forwards method query body and only safe request headers", async () => {
  const body = JSON.stringify({ decision: "approved" });
  const request = new Request(
    "http://localhost/api/startup/cases/case-1/gate2/decision?dry_run=true",
    {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        cookie: "secret=1",
        authorization: "Bearer secret",
        host: "attacker.test",
        origin: "http://attacker.test",
        forwarded: "for=attacker",
        "x-forwarded-host": "attacker.test",
        "x-request-id": "123e4567-e89b-12d3-a456-426614174000",
      },
      body,
    },
  );

  const upstream = await buildStartupProxyRequest(request, {
    upstreamBaseUrl: "http://127.0.0.1:8000",
    timeoutMs: 1000,
  });

  assert.equal(
    upstream.url,
    "http://127.0.0.1:8000/api/v1/startup/cases/case-1/gate2/decision?dry_run=true",
  );
  assert.equal(upstream.init.method, "POST");
  assert.equal(upstream.init.headers.get("accept"), "application/json");
  assert.equal(upstream.init.headers.get("content-type"), "application/json");
  assert.equal(
    upstream.init.headers.get("x-request-id"),
    "123e4567-e89b-12d3-a456-426614174000",
  );
  assert.equal(upstream.init.headers.get("authorization"), null);
  assert.equal(upstream.init.headers.get("cookie"), null);
  assert.equal(upstream.init.headers.get("host"), null);
  assert.equal(upstream.init.headers.get("origin"), null);
  assert.equal(upstream.init.headers.get("forwarded"), null);
  assert.equal(await new Response(upstream.init.body).text(), body);
});

test("normalizes invalid request ids and forwards multipart bodies", async () => {
  const formData = new FormData();
  formData.append("auto_start", "true");
  formData.append("files", new Blob(["pitch"]), "pitch.pdf");
  const request = new Request(
    "http://localhost/api/startup/cases/case-1/documents",
    {
      method: "POST",
      headers: {
        "x-request-id": "bad request id with spaces",
      },
      body: formData,
    },
  );

  const upstream = await buildStartupProxyRequest(request, {
    upstreamBaseUrl: "http://127.0.0.1:8000",
    timeoutMs: 1000,
  });

  assert.equal(upstream.init.headers.get("content-type"), null);
  assert.match(upstream.init.headers.get("x-request-id") ?? "", /^[0-9a-f-]{36}$/);
  assert.ok(upstream.init.body instanceof FormData);
});

test("keeps route wrappers representable without importing next server modules", () => {
  assert.deepEqual(
    startupRouteManifest.map((route) => `${route.method} ${route.sameOriginPath}`),
    [
      "POST /api/startup/cases",
      "GET /api/startup/cases/[caseId]",
      "POST /api/startup/cases/[caseId]/documents",
      "GET /api/startup/cases/[caseId]/analysis",
      "GET /api/startup/cases/[caseId]/profile",
      "GET /api/startup/cases/[caseId]/gtm",
      "GET /api/startup/cases/[caseId]/copilot/state",
      "GET /api/startup/cases/[caseId]/copilot/thread",
      "POST /api/startup/cases/[caseId]/copilot/messages",
      "POST /api/startup/cases/[caseId]/facts",
      "POST /api/startup/cases/[caseId]/assumptions",
      "GET /api/startup/cases/[caseId]/scenarios",
      "POST /api/startup/cases/[caseId]/scenarios/selection",
      "POST /api/startup/cases/[caseId]/research/plans",
      "POST /api/startup/cases/[caseId]/research/jobs",
      "GET /api/startup/cases/[caseId]/research/jobs/[jobId]",
      "GET /api/startup/cases/[caseId]/assets",
      "POST /api/startup/cases/[caseId]/assets",
      "GET /api/startup/cases/[caseId]/assets/[assetId]",
      "GET /api/startup/cases/[caseId]/assets/[assetId]/markdown",
      "GET /api/startup/cases/[caseId]/assets/[assetId]/provenance",
      "GET /api/startup/cases/[caseId]/assets/[assetId]/csv",
      "GET /api/startup/cases/[caseId]/advisor/next-question",
      "POST /api/startup/cases/[caseId]/advisor/answers",
      "GET /api/startup/cases/[caseId]/advisor/improvements",
      "POST /api/startup/cases/[caseId]/advisor/improvements/[proposalId]/decision",
      "GET /api/startup/cases/[caseId]/gate2/preview",
      "POST /api/startup/cases/[caseId]/gate2/decision",
      "POST /api/startup/cases/[caseId]/gate3/decision",
      "POST /api/startup/cases/[caseId]/gate4/decision",
      "GET /api/startup/cases/[caseId]/report",
      "GET /api/startup/cases/[caseId]/report/json",
      "GET /api/startup/cases/[caseId]/report/html",
      "GET /api/startup/cases/[caseId]/report/pdf",
    ],
  );
});

test("proxy preserves safe upstream success status body and content type only", async () => {
  const response = await proxyFounderApi(
    new Request("http://localhost/api/startup/cases/case-1/report/html", {
      method: "GET",
    }),
    {
      upstreamBaseUrl: "http://127.0.0.1:8000",
      timeoutMs: 1000,
      fetcher: async () =>
        new Response("<h1>Report</h1>", {
          status: 202,
          headers: {
            "content-type": "text/html; charset=utf-8",
            "set-cookie": "secret=1",
            "x-internal-path": "D:/secret",
          },
        }),
    },
  );

  assert.equal(response.status, 202);
  assert.equal(response.headers.get("content-type"), "text/html; charset=utf-8");
  assert.equal(response.headers.get("set-cookie"), null);
  assert.equal(response.headers.get("x-internal-path"), null);
  assert.equal(await response.text(), "<h1>Report</h1>");
});

test("proxy preserves downloadable asset text types and content disposition", async () => {
  const markdown = await proxyFounderApi(
    new Request(
      "http://localhost/api/startup/cases/case-1/assets/asset-1/markdown",
      { method: "GET" },
    ),
    {
      upstreamBaseUrl: "http://127.0.0.1:8000",
      timeoutMs: 1000,
      fetcher: async () =>
        new Response("## Draft\n", {
          status: 200,
          headers: {
            "content-type": "text/markdown; charset=utf-8",
            "content-disposition": 'attachment; filename="case-asset.md"',
            "x-internal-path": "D:/secret",
          },
        }),
    },
  );
  const csv = await proxyFounderApi(
    new Request("http://localhost/api/startup/cases/case-1/assets/asset-1/csv", {
      method: "GET",
    }),
    {
      upstreamBaseUrl: "http://127.0.0.1:8000",
      timeoutMs: 1000,
      fetcher: async () =>
        new Response("week,stage\n", {
          status: 200,
          headers: {
            "content-type": "text/csv; charset=utf-8",
            "content-disposition": 'attachment; filename="weekly-funnel.csv"',
            "set-cookie": "secret=1",
          },
        }),
    },
  );

  assert.equal(markdown.headers.get("content-type"), "text/markdown; charset=utf-8");
  assert.equal(
    markdown.headers.get("content-disposition"),
    'attachment; filename="case-asset.md"',
  );
  assert.equal(markdown.headers.get("x-internal-path"), null);
  assert.equal(await markdown.text(), "## Draft\n");
  assert.equal(csv.headers.get("content-type"), "text/csv; charset=utf-8");
  assert.equal(
    csv.headers.get("content-disposition"),
    'attachment; filename="weekly-funnel.csv"',
  );
  assert.equal(csv.headers.get("set-cookie"), null);
  assert.equal(await csv.text(), "week,stage\n");
});

test("proxy maps timeout and rejected upstream failures to safe error bodies", async () => {
  const timeout = await proxyFounderApi(
    new Request("http://localhost/api/startup/cases", { method: "POST" }),
    {
      upstreamBaseUrl: "http://127.0.0.1:8000",
      timeoutMs: 1,
      fetcher: async () => {
        throw new DOMException("The operation was aborted", "TimeoutError");
      },
    },
  );
  const rejected = await proxyFounderApi(
    new Request("http://localhost/api/startup/cases", { method: "POST" }),
    {
      upstreamBaseUrl: "http://127.0.0.1:8000",
      timeoutMs: 1,
      fetcher: async () =>
        new Response("trace D:/secret token abc", {
          status: 500,
          headers: { "content-type": "text/plain" },
        }),
    },
  );

  assert.equal(timeout.status, 504);
  assert.equal((await timeout.json()).code, "api_timeout");
  assert.equal(rejected.status, 502);
  assert.deepEqual(await rejected.json(), {
    code: "api_rejected",
    message: "Founder API request was rejected",
  });
});

test("proxy maps unreachable upstream to typed 503 response", async () => {
  const response = await proxyFounderApi(
    new Request("http://localhost/api/startup/cases", { method: "GET" }),
    {
      upstreamBaseUrl: "http://127.0.0.1:8000",
      timeoutMs: 1,
      fetcher: async () => {
        throw new FounderApiProxyError("api_unreachable", "offline");
      },
    },
  );

  assert.equal(response.status, 503);
  assert.equal((await response.json()).code, "api_unreachable");
});
