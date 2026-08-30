import assert from "node:assert/strict";
import test from "node:test";

import {
  FounderApiClientError,
  createCase,
  decideGate2,
  decideGate3,
  decideGate4,
  downloadReportArtifact,
  decideAdvisorImprovement,
  generateLaunchPack,
  getAnalysis,
  getAdvisorImprovements,
  getAdvisorNextQuestion,
  getCase,
  getCopilotState,
  getCopilotThread,
  getGate2Preview,
  getCaseAsset,
  getResearchJob,
  getScenarios,
  getStartupGtm,
  getStartupProfile,
  getStartupReportSnapshot,
  getReport,
  listCaseAssets,
  postCopilotMessage,
  prepareResearchPlan,
  queueResearchJob,
  saveAssumption,
  saveFounderFact,
  submitAdvisorAnswer,
  reportArtifactUrl,
  selectScenario,
  uploadDocuments,
} from "./founder-api-client.ts";

type FetchHandler = (
  input: string | URL | Request,
  init?: RequestInit,
) => Promise<Response>;

function asFetcher(handler: FetchHandler): typeof fetch {
  return handler as typeof fetch;
}

function statusBody(overrides: Record<string, unknown> = {}) {
  return {
    case_id: "case-1",
    case_status: "awaiting_upload",
    analysis_status: "gate2_preview_ready",
    provider_status: "deterministic_offline_fixture",
    data_revision: 1,
    active_analysis_thread_id: "case-1",
    langgraph_checkpoint: null,
    gate2_status: "required",
    gate3_status: "not_ready",
    gate4_status: "not_ready",
    report_status: "not_ready",
    snapshot_hash: null,
    snapshot_revision: null,
    ...overrides,
  };
}

function decisionBody(overrides: Record<string, unknown> = {}) {
  return {
    case_id: "case-1",
    analysis_status: "gate2_preview_ready",
    gate2_status: "required",
    gate3_status: "not_ready",
    gate4_status: "not_ready",
    report_status: "not_ready",
    snapshot_hash: null,
    snapshot_revision: null,
    ...overrides,
  };
}

test("createCase sends the exact same-origin JSON request and parses its response", async () => {
  const result = await createCase(
    {
      fixture_mode: "deterministic_offline",
      auto_start: true,
      company_name: "Signal Labs",
      website: null,
      as_of: "2026-08-13",
      document_class_hint: "pitch_deck",
    },
    {
      fetcher: asFetcher(async (input, init) => {
        assert.equal(input, "/api/startup/cases");
        assert.equal(init?.method, "POST");
        assert.equal(new Headers(init?.headers).get("accept"), "application/json");
        assert.equal(
          new Headers(init?.headers).get("content-type"),
          "application/json",
        );
        assert.deepEqual(JSON.parse(String(init?.body)), {
          fixture_mode: "deterministic_offline",
          auto_start: true,
          company_name: "Signal Labs",
          website: null,
          as_of: "2026-08-13",
          document_class_hint: "pitch_deck",
        });
        return Response.json(
          {
            case_id: "case-1",
            case_status: "awaiting_upload",
            analysis_status: "awaiting_upload",
            provider_status: "deterministic_offline_fixture",
            auto_start_triggered: false,
          },
          { status: 201 },
        );
      }),
    },
  );

  assert.equal(result.case_id, "case-1");
  assert.equal(result.provider_status, "deterministic_offline_fixture");
});

test("uploadDocuments sends files and metadata as FormData without a manual content type", async () => {
  const pitch = new File(["pitch"], "pitch.pdf", { type: "application/pdf" });
  const metrics = new File(["arr,100"], "metrics.csv", { type: "text/csv" });

  const result = await uploadDocuments(
    "case-1",
    {
      files: [pitch, metrics],
      auto_start: true,
      company_name: "Signal Labs",
      website: "https://signal.example",
      as_of: "2026-08-13",
      document_class_hint: "mixed",
    },
    {
      fetcher: asFetcher(async (input, init) => {
        assert.equal(input, "/api/startup/cases/case-1/documents");
        assert.equal(init?.method, "POST");
        assert.equal(new Headers(init?.headers).get("content-type"), null);
        assert.ok(init?.body instanceof FormData);
        const form = init.body;
        assert.deepEqual(
          form.getAll("files").map((file) => (file as File).name),
          ["pitch.pdf", "metrics.csv"],
        );
        assert.equal(form.get("auto_start"), "true");
        assert.equal(form.get("company_name"), "Signal Labs");
        assert.equal(form.get("website"), "https://signal.example");
        assert.equal(form.get("as_of"), "2026-08-13");
        assert.equal(form.get("document_class_hint"), "mixed");
        return Response.json({
          case_id: "case-1",
          accepted_document_ids: ["doc-1", "doc-2"],
          analysis_status: "gate2_preview_ready",
          auto_start_triggered: true,
          next_poll_after_ms: 750,
        });
      }),
    },
  );

  assert.deepEqual(result.accepted_document_ids, ["doc-1", "doc-2"]);
  assert.equal(result.next_poll_after_ms, 750);
});

test("case analysis and gate operations use their exact routes and typed parsers", async () => {
  const calls: Array<Readonly<{ path: string; method: string; body: unknown }>> = [];
  const fetcher = asFetcher(async (input, init) => {
    const path = String(input);
    calls.push({
      path,
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    if (path.endsWith("/gate2/preview")) {
      return Response.json({
        case_id: "case-1",
        preview: { artifact_counts: { pdf: 1 } },
        resume_token: "resume-1",
        provider_mode: "deterministic_offline_fixture",
      });
    }
    if (path.includes("/gate2/decision")) {
      return Response.json(
        decisionBody({
          analysis_status: "gate3_review_required",
          gate2_status: "completed",
          gate3_status: "required",
        }),
      );
    }
    if (path.includes("/gate3/decision")) {
      return Response.json(
        decisionBody({
          analysis_status: "analysis_complete_report_pending",
          gate2_status: "completed",
          gate3_status: "completed",
          report_status: "pending",
        }),
      );
    }
    if (path.includes("/gate4/decision")) {
      return Response.json(
        decisionBody({
          analysis_status: "analysis_complete_report_pending",
          gate2_status: "completed",
          gate3_status: "completed",
          gate4_status: "completed",
          report_status: "ready",
          snapshot_hash: "sha256:abc",
          snapshot_revision: 4,
        }),
      );
    }
    return Response.json(statusBody());
  });
  const options = { fetcher };

  const status = await getCase("case-1", options);
  const analysis = await getAnalysis("case-1", options);
  const preview = await getGate2Preview("case-1", options);
  const gate2 = await decideGate2(
    "case-1",
    { decision: "approved", resume_token: "resume-1", reason: "Looks right" },
    options,
  );
  const gate3 = await decideGate3(
    "case-1",
    {
      decision: "continue",
      exclusions: [{ evidence_fact_id: "fact-9", reason: "stale" }],
    },
    options,
  );
  const gate4 = await decideGate4(
    "case-1",
    {
      decision: "approved",
      snapshot_hash: "sha256:abc",
      snapshot_revision: 4,
      reason: "Freeze",
    },
    options,
  );

  assert.equal(status.gate2_status, "required");
  assert.equal(analysis.analysis_status, "gate2_preview_ready");
  assert.equal(preview.resume_token, "resume-1");
  assert.equal(gate2.gate3_status, "required");
  assert.equal(gate3.report_status, "pending");
  assert.equal(gate4.snapshot_revision, 4);
  assert.deepEqual(calls, [
    { path: "/api/startup/cases/case-1", method: "GET", body: null },
    { path: "/api/startup/cases/case-1/analysis", method: "GET", body: null },
    { path: "/api/startup/cases/case-1/gate2/preview", method: "GET", body: null },
    {
      path: "/api/startup/cases/case-1/gate2/decision",
      method: "POST",
      body: {
        decision: "approved",
        resume_token: "resume-1",
        reason: "Looks right",
      },
    },
    {
      path: "/api/startup/cases/case-1/gate3/decision",
      method: "POST",
      body: {
        decision: "continue",
        exclusions: [{ evidence_fact_id: "fact-9", reason: "stale" }],
      },
    },
    {
      path: "/api/startup/cases/case-1/gate4/decision",
      method: "POST",
      body: {
        decision: "approved",
        snapshot_hash: "sha256:abc",
        snapshot_revision: 4,
        reason: "Freeze",
      },
    },
  ]);
});

test("case copilot client covers thread, actions, facts, assumptions, scenarios and research routes", async () => {
  const caseId = "11111111-1111-4111-8111-111111111111";
  const threadId = "22222222-2222-4222-8222-222222222222";
  const actionId = "33333333-3333-4333-8333-333333333333";
  const scenarioSetId = "44444444-4444-4444-8444-444444444444";
  const planId = "55555555-5555-4555-8555-555555555555";
  const jobId = "66666666-6666-4666-8666-666666666666";
  const sourceId = "77777777-7777-4777-8777-777777777777";
  const dependencyId = "88888888-8888-4888-8888-888888888888";
  const revision = 4;
  const calls: Array<Readonly<{ path: string; method: string; body: unknown }>> = [];
  const founderInput = {
    field_key: "mrr",
    kind: "founder_statement",
    status: "accepted",
    value: "1400000-2000000",
    period: "month",
    rationale: "Founder supplied planning input.",
    validation_plan: "Validate against billing export.",
    declared_source: "founder",
    source_refs: [sourceId],
  };
  const action = {
    action_id: actionId,
    action: "prepare_public_research",
    status: "requires_consent",
    handler: "prepareResearchPlan",
    reason: "Benchmark needed.",
    effect_preview: "Creates a safe public research plan.",
    payload: {
      focus: "public_pricing_analogs",
      expected_case_revision: revision,
      available_acquisition_modes: [
        "live_public_research",
        "deterministic_offline_fixture",
      ],
      unavailable_acquisition_modes: [],
      default_acquisition_mode: "live_public_research",
    },
  };
  const coverage = {
    measure: "fact_coverage",
    status: "partial",
    source_fact_count: 1,
    accepted_input_count: 1,
  };
  const delta = {
    accepted: true,
    old_revision: revision,
    new_revision: revision + 1,
    changed_keys: ["mrr"],
    stale_scenario_ids: [scenarioSetId],
    stale_report_ids: [],
    metric_before: { mrr: "unknown" },
    metric_after: { mrr: "1400000-2000000" },
    readiness_before: { metrics: 10 },
    readiness_after: { metrics: 20 },
    next_question: null,
    validation_errors: [],
    original_draft: null,
  };
  const scenarioMetric = {
    metric_id: "99999999-9999-4999-8999-999999999999",
    case_id: caseId,
    data_revision: revision,
    metric_key: "mrr",
    value_range: { lower: "1400000", upper: "2000000" },
    unit: "KZT/month",
    period: "month",
    provenance: "deterministic_calculation",
    source_refs: [],
    dependency_refs: [dependencyId],
    formula_key: "mrr",
    formula_description: "monthly_price * paying_customers",
    confidence: "medium",
    rationale: "Derived from accepted inputs.",
    validation_plan: "Validate against billing export.",
    what_would_confirm: "Billing export.",
    acceptance: "needs_validation",
    gaps: [],
  };
  const scenarioVariant = (scenario_key: "conservative" | "base" | "optimistic") => ({
    scenario_key,
    inputs: {},
    metrics: { mrr: scenarioMetric },
    gaps: {},
  });
  const researchJob = {
    case_id: caseId,
    data_revision: revision + 1,
    job_id: jobId,
    plan_id: planId,
    plan_hash: "plan-hash-1",
    status: "completed",
    reason: null,
    acquisition_mode: "live_public_research",
    requested_acquisition_mode: "live_public_research",
    selected_acquisition_mode: "live_public_research",
    accepted_entries: [
      {
        entry_id: sourceId,
        provenance: "public_benchmark",
        input_key: "public_pricing_analogs",
        url: "https://example.com/pricing",
        publisher: "Example",
        publication_date: "2026-08-01",
        retrieval_date: "2026-08-23",
        as_of: "2026-08-23",
        source_class: "pricing_page",
        confidence: "medium",
        value: null,
        range: { low: "30000", high: "50000" },
        unit: "KZT/month",
        period: "month",
        formula: "observed public price range",
        dependencies: ["public comparable companies"],
        validation_plan: "Recheck source before using in model.",
        source_refs: [sourceId],
      },
    ],
    rejected_entries: [],
    citations: ["https://example.com/pricing"],
    manual_only_keys: ["mrr"],
    changed_blocks: ["public_benchmarks", "scenarios"],
    stale_scenario_ids: [scenarioSetId],
    old_revision: revision,
    new_revision: revision + 1,
    source_refs: [sourceId],
    updated_at: "2026-08-23T12:00:00Z",
  };
  const fetcher = asFetcher(async (input, init) => {
    const path = String(input);
    calls.push({
      path,
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    if (path.endsWith("/copilot/state")) {
      return Response.json({
        case_id: caseId,
        data_revision: revision,
        stage: "idea",
        next_question: "What is current MRR?",
        question_descriptor: null,
        suggested_action: "prepare_public_research",
        selected_scenario_key: "base",
        extracted_facts: [
          { field_key: "startup_name", value: "FounderCo", source_type: "source_fact" },
        ],
        prioritized_gaps: [],
        scenario_metrics: [
          {
            metric_key: "mrr",
            label: "MRR",
            source_type: "deterministic_calculation",
            value: null,
            range: {
              conservative: "7.2E+6:1.47E+7",
              base: "3.6E+4:86666.67",
              optimistic: null,
            },
            formula: "monthly_price * paying_customers",
            dependencies: ["monthly_price", "paying_customers"],
            unit: "KZT/month",
            period: "month",
            confidence: "medium",
            source_refs: [],
            what_would_confirm: "Billing export.",
            validation_plan: "Validate against billing export.",
          },
        ],
        fact_coverage: coverage,
        scenario_completeness: { ...coverage, measure: "scenario_completeness" },
        accepted_inputs: [founderInput],
        actions: [action],
      });
    }
    if (path.includes("/copilot/thread")) {
      return Response.json({
        thread_id: threadId,
        case_id: caseId,
        data_revision: revision,
        messages: [
          {
            message_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            case_id: caseId,
            data_revision: revision,
            role: "assistant",
            content: "I can prepare a safe public benchmark.",
            page_context: "metrics",
            current_section: "mrr",
            idempotency_fingerprint: null,
            related_evidence_refs: [],
            question_refs: [],
            action_refs: [actionId],
            action_snapshots: [action],
            action_result: null,
          },
        ],
      });
    }
    if (path.endsWith("/copilot/messages")) {
      return Response.json({
        case_id: caseId,
        data_revision: revision,
        thread_id: threadId,
        page_context: "metrics",
        current_section: "mrr",
        status: "accepted",
        message: "Draft accepted.",
        available_actions: [action],
      });
    }
    if (path.endsWith("/facts")) {
      return Response.json({
        case_id: caseId,
        accepted: true,
        provenance: "founder_statement",
        source_type: "founder_statement",
        old_revision: revision,
        new_revision: revision + 1,
        changed_keys: ["mrr"],
        delta,
      });
    }
    if (path.endsWith("/assumptions")) {
      return Response.json({
        case_id: caseId,
        status: "accepted",
        provenance: "founder_statement",
        reason: null,
        old_revision: revision,
        new_revision: revision + 1,
        delta,
        accepted_input: founderInput,
      });
    }
    if (path.endsWith("/scenarios")) {
      return Response.json({
        scenario_set_id: scenarioSetId,
        case_id: caseId,
        data_revision: revision,
        selected_scenario_key: "base",
        scenarios: {
          conservative: scenarioVariant("conservative"),
          base: scenarioVariant("base"),
          optimistic: scenarioVariant("optimistic"),
        },
        fact_coverage: coverage,
        scenario_completeness: { ...coverage, measure: "scenario_completeness" },
      });
    }
    if (path.endsWith("/scenarios/selection")) {
      return Response.json({
        case_id: caseId,
        data_revision: revision,
        scenario_set_id: scenarioSetId,
        old_scenario_key: "base",
        new_scenario_key: "optimistic",
        changed_keys: ["selected_scenario_key"],
      });
    }
    if (path.endsWith("/assets") && init?.method === "GET") {
      return Response.json({
        case_id: caseId,
        data_revision: revision,
        assets: [
          {
            case_id: caseId,
            data_revision: revision,
            scenario_set_id: scenarioSetId,
            selected_scenario_key: "optimistic",
            asset_id: "33333333-3333-4333-8333-333333333333",
            asset_key: "weekly_funnel_template",
            asset_revision: 2,
            status: "draft",
            markdown_url: `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333/markdown`,
            csv_url: `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333/csv`,
            provenance_appendix_url: `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333/provenance`,
            body_markdown: "## Weekly funnel template\n\nDraft.",
          },
        ],
      });
    }
    if (path.endsWith("/assets") && init?.method === "POST") {
      return Response.json(
        {
          case_id: caseId,
          data_revision: revision,
          scenario_set_id: scenarioSetId,
          selected_scenario_key: "optimistic",
          asset_id: "33333333-3333-4333-8333-333333333333",
          asset_key: "weekly_funnel_template",
          asset_revision: 1,
          status: "draft",
          markdown_url: `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333/markdown`,
          csv_url: `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333/csv`,
          provenance_appendix_url: `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333/provenance`,
          body_markdown: "## Weekly funnel template\n\nDraft.",
        },
        { status: 201 },
      );
    }
    if (path.endsWith("/assets/33333333-3333-4333-8333-333333333333")) {
      return Response.json({
        case_id: caseId,
        data_revision: revision,
        scenario_set_id: scenarioSetId,
        selected_scenario_key: "optimistic",
        asset_id: "33333333-3333-4333-8333-333333333333",
        asset_key: "weekly_funnel_template",
        asset_revision: 2,
        status: "draft",
        markdown_url: `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333/markdown`,
        csv_url: `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333/csv`,
        provenance_appendix_url: `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333/provenance`,
        body_markdown: "## Weekly funnel template\n\nDraft.",
      });
    }
    if (path.endsWith("/research/plans")) {
      return Response.json(
        {
          case_id: caseId,
          data_revision: revision,
          status: "prepared",
          plan_id: planId,
          plan_hash: "plan-hash-1",
          focus: "public_pricing_analogs",
          query_previews: ["public pricing analogs"],
          manual_only_keys: ["mrr"],
          consent_text: "Only public pricing pages will be queried.",
          created_at: "2026-08-23T11:00:00Z",
          expires_at: "2026-08-24T11:00:00Z",
        },
        { status: 201 },
      );
    }
    if (path.endsWith("/research/jobs") || path.includes(`/research/jobs/${jobId}`)) {
      return Response.json(researchJob, {
        status: path.endsWith("/research/jobs") ? 202 : 200,
      });
    }
    throw new Error(`Unexpected path ${path}`);
  });
  const options = { fetcher };

  await getCopilotState(caseId, options);
  await getCopilotThread(caseId, threadId, options);
  await postCopilotMessage(
    caseId,
    {
      message: "Explain MRR",
      page_context: "metrics",
      current_section: "mrr",
      expected_case_revision: revision,
      focus_key: "mrr",
      idempotency_key: "message-1",
    },
    options,
  );
  await saveFounderFact(
    caseId,
    {
      requirement_key: "mrr",
      value: { kind: "money", amount: "1400000", scale: "absolute", currency: "KZT" },
      period: { kind: "month", start: null, end: null, value: "2026-08" },
      source: { kind: "founder_statement", declared_source: "founder", evidence_ref: null },
      note: null,
      resolves_contradiction_id: null,
      expected_case_revision: revision,
      idempotency_key: "fact-1",
    },
    options,
  );
  await saveAssumption(
    caseId,
    {
      requirement_key: "monthly_price",
      value: { kind: "money", amount: "40000", scale: "absolute", currency: "KZT" },
      period: { kind: "month", start: null, end: null, value: "2026-08" },
      source: { kind: "founder_statement", declared_source: "founder", evidence_ref: null },
      rationale: "Founder planning input.",
      validation_plan: "Validate later.",
      expected_case_revision: revision,
      idempotency_key: "assumption-1",
    },
    options,
  );
  await getScenarios(caseId, options);
  await selectScenario(
    caseId,
    {
      scenario_set_id: scenarioSetId,
      scenario_key: "optimistic",
      expected_case_revision: revision,
      idempotency_key: "scenario-1",
    },
    options,
  );
  await generateLaunchPack(
    caseId,
    {
      asset_type: "weekly_funnel_template",
      selected_scenario_key: "optimistic",
      expected_case_revision: revision,
      idempotency_key: "weekly-funnel-1",
    },
    options,
  );
  const listedAssets = await listCaseAssets(caseId, options);
  const fetchedAsset = await getCaseAsset(
    caseId,
    "33333333-3333-4333-8333-333333333333",
    options,
  );
  await prepareResearchPlan(
    caseId,
    {
      focus: "public_pricing_analogs",
      intent: "Prepare public pricing analog research.",
      requested_private_value: null,
      expected_case_revision: revision,
    },
    options,
  );
  await queueResearchJob(
    caseId,
    {
      plan_id: planId,
      plan_hash: "plan-hash-1",
      expected_case_revision: revision,
      idempotency_key: "research-job-1",
      consent_public_research: true,
      acquisition_mode: "live_public_research",
      retry_of_job_id: null,
    },
    options,
  );
  const fetchedJob = await getResearchJob(caseId, jobId, options);

  assert.equal(fetchedJob.accepted_entries[0]?.provenance, "public_benchmark");
  assert.deepEqual(fetchedJob.accepted_entries[0]?.dependencies, ["public comparable companies"]);
  assert.equal(listedAssets.assets[0]?.csv_url?.endsWith("/csv"), true);
  assert.equal(fetchedAsset.asset_key, "weekly_funnel_template");
  assert.deepEqual(
    calls.map((call) => [call.method, call.path]),
    [
      ["GET", `/api/startup/cases/${caseId}/copilot/state`],
      ["GET", `/api/startup/cases/${caseId}/copilot/thread?thread_id=${threadId}`],
      ["POST", `/api/startup/cases/${caseId}/copilot/messages`],
      ["POST", `/api/startup/cases/${caseId}/facts`],
      ["POST", `/api/startup/cases/${caseId}/assumptions`],
      ["GET", `/api/startup/cases/${caseId}/scenarios`],
      ["POST", `/api/startup/cases/${caseId}/scenarios/selection`],
      ["POST", `/api/startup/cases/${caseId}/assets`],
      ["GET", `/api/startup/cases/${caseId}/assets`],
      ["GET", `/api/startup/cases/${caseId}/assets/33333333-3333-4333-8333-333333333333`],
      ["POST", `/api/startup/cases/${caseId}/research/plans`],
      ["POST", `/api/startup/cases/${caseId}/research/jobs`],
      ["GET", `/api/startup/cases/${caseId}/research/jobs/${jobId}`],
    ],
  );
  assert.deepEqual(calls[7]?.body, {
    asset_type: "weekly_funnel_template",
    selected_scenario_key: "optimistic",
    expected_case_revision: revision,
    idempotency_key: "weekly-funnel-1",
  });
  assert.deepEqual(calls[10]?.body, {
    focus: "public_pricing_analogs",
    intent: "Prepare public pricing analog research.",
    requested_private_value: null,
    expected_case_revision: revision,
  });
  assert.deepEqual(calls[11]?.body, {
    plan_id: planId,
    plan_hash: "plan-hash-1",
    expected_case_revision: revision,
    idempotency_key: "research-job-1",
    consent_public_research: true,
    acquisition_mode: "live_public_research",
    retry_of_job_id: null,
  });
});

test("queueResearchJob sends the selected acquisition mode explicitly", async () => {
  await queueResearchJob(
    "11111111-1111-4111-8111-111111111111",
    {
      plan_id: "55555555-5555-4555-8555-555555555555",
      plan_hash: "sha256:plan",
      expected_case_revision: 4,
      idempotency_key: "copilot-research:live_public_research:public_pricing_analogs:sha256:plan",
      consent_public_research: true,
      acquisition_mode: "live_public_research",
      retry_of_job_id: null,
    },
    {
      fetcher: asFetcher(async (input, init) => {
        assert.equal(
          input,
          "/api/startup/cases/11111111-1111-4111-8111-111111111111/research/jobs",
        );
        assert.deepEqual(JSON.parse(String(init?.body)), {
          plan_id: "55555555-5555-4555-8555-555555555555",
          plan_hash: "sha256:plan",
          expected_case_revision: 4,
          idempotency_key: "copilot-research:live_public_research:public_pricing_analogs:sha256:plan",
          consent_public_research: true,
          acquisition_mode: "live_public_research",
          retry_of_job_id: null,
        });
        return Response.json(
          {
            case_id: "11111111-1111-4111-8111-111111111111",
            data_revision: 4,
            job_id: "66666666-6666-4666-8666-666666666666",
            plan_id: "55555555-5555-4555-8555-555555555555",
            plan_hash: "sha256:plan",
            status: "deferred",
            reason: "provider_unconfigured",
            acquisition_mode: "provider_unconfigured",
            requested_acquisition_mode: "live_public_research",
            selected_acquisition_mode: "provider_unconfigured",
            accepted_entries: [],
            rejected_entries: [],
            citations: [],
            manual_only_keys: ["mrr"],
            changed_blocks: [],
            stale_scenario_ids: [],
            old_revision: 4,
            new_revision: null,
            source_refs: [],
            updated_at: "2026-08-23T00:00:00Z",
          },
          { status: 202 },
        );
      }),
    },
  );
});

test("case copilot client rejects responses outside the requested case resource and revision context", async () => {
  const caseId = "11111111-1111-4111-8111-111111111111";
  const otherCaseId = "22222222-2222-4222-8222-222222222222";
  const threadId = "33333333-3333-4333-8333-333333333333";
  const otherThreadId = "44444444-4444-4444-8444-444444444444";
  const scenarioSetId = "55555555-5555-4555-8555-555555555555";
  const otherScenarioSetId = "66666666-6666-4666-8666-666666666666";
  const planId = "77777777-7777-4777-8777-777777777777";
  const otherPlanId = "88888888-8888-4888-8888-888888888888";
  const jobId = "99999999-9999-4999-8999-999999999999";
  const otherJobId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const actionId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const revision = 7;
  const coverage = {
    measure: "fact_coverage",
    status: "partial",
    source_fact_count: 1,
    accepted_input_count: 1,
  };
  const action = {
    action_id: actionId,
    action: "open_fact_input",
    status: "requires_input",
    handler: "openFactInput",
    reason: "Needs founder input.",
    effect_preview: "Adds a planning input.",
    payload: { field_key: "mrr", provenance: "founder_statement" },
  };
  const delta = {
    accepted: true,
    old_revision: revision + 1,
    new_revision: revision + 2,
    changed_keys: ["mrr"],
    stale_scenario_ids: [],
    stale_report_ids: [],
    metric_before: {},
    metric_after: {},
    readiness_before: {},
    readiness_after: {},
    next_question: null,
    validation_errors: [],
    original_draft: null,
  };
  const scenarioMetric = {
    metric_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    case_id: caseId,
    data_revision: revision,
    metric_key: "mrr",
    value_range: { lower: "1000", upper: "2000" },
    unit: "KZT/month",
    period: "month",
    provenance: "deterministic_calculation",
    source_refs: [],
    dependency_refs: ["dddddddd-dddd-4ddd-8ddd-dddddddddddd"],
    formula_key: "mrr",
    formula_description: "monthly_price * paying_customers",
    confidence: "medium",
    rationale: "Derived.",
    validation_plan: "Validate.",
    what_would_confirm: "Billing export.",
    acceptance: "needs_validation",
    gaps: [],
  };
  const scenarioVariant = (scenario_key: "conservative" | "base" | "optimistic") => ({
    scenario_key,
    inputs: {},
    metrics: { mrr: scenarioMetric },
    gaps: {},
  });
  const researchJob = {
    case_id: caseId,
    data_revision: revision,
    job_id: jobId,
    plan_id: planId,
    plan_hash: "plan-hash-1",
    status: "queued",
    reason: null,
    acquisition_mode: "live_public_research",
    requested_acquisition_mode: "live_public_research",
    selected_acquisition_mode: "live_public_research",
    accepted_entries: [],
    rejected_entries: [],
    citations: [],
    manual_only_keys: [],
    changed_blocks: [],
    stale_scenario_ids: [],
    old_revision: revision,
    new_revision: null,
    source_refs: [],
    updated_at: "2026-08-23T12:00:00Z",
  };
  const requestInit = {
    fetcher: asFetcher(async (input) => {
      const path = String(input);
      if (path.endsWith("/copilot/state")) {
        return Response.json({
          case_id: otherCaseId,
          data_revision: revision,
          stage: "idea",
          next_question: null,
          question_descriptor: null,
          suggested_action: "open_fact_input",
          selected_scenario_key: "base",
          extracted_facts: [],
          prioritized_gaps: [],
          scenario_metrics: [],
          fact_coverage: coverage,
          scenario_completeness: { ...coverage, measure: "scenario_completeness" },
          accepted_inputs: [],
          actions: [action],
        });
      }
      if (path.includes("/copilot/thread")) {
        return Response.json({
          thread_id: otherThreadId,
          case_id: caseId,
          data_revision: revision,
          messages: [],
        });
      }
      if (path.endsWith("/copilot/messages")) {
        return Response.json({
          case_id: caseId,
          data_revision: revision + 1,
          thread_id: threadId,
          page_context: "wrong-page",
          current_section: "wrong-section",
          status: "accepted",
          message: "Accepted.",
          available_actions: [action],
        });
      }
      if (path.endsWith("/facts")) {
        return Response.json({
          case_id: caseId,
          accepted: true,
          provenance: "founder_statement",
          source_type: "founder_statement",
          old_revision: revision + 1,
          new_revision: revision + 2,
          changed_keys: ["mrr"],
          delta,
        });
      }
      if (path.endsWith("/assumptions")) {
        return Response.json({
          case_id: caseId,
          status: "accepted",
          provenance: "founder_statement",
          reason: null,
          old_revision: revision + 1,
          new_revision: revision + 2,
          delta,
          accepted_input: null,
        });
      }
      if (path.endsWith("/scenarios")) {
        return Response.json({
          scenario_set_id: scenarioSetId,
          case_id: otherCaseId,
          data_revision: revision,
          selected_scenario_key: "base",
          scenarios: {
            conservative: scenarioVariant("conservative"),
            base: scenarioVariant("base"),
            optimistic: scenarioVariant("optimistic"),
          },
          fact_coverage: coverage,
          scenario_completeness: { ...coverage, measure: "scenario_completeness" },
        });
      }
      if (path.endsWith("/scenarios/selection")) {
        return Response.json({
          case_id: caseId,
          data_revision: revision + 1,
          scenario_set_id: otherScenarioSetId,
          old_scenario_key: "base",
          new_scenario_key: "base",
          changed_keys: ["selected_scenario_key"],
        });
      }
      if (path.endsWith("/research/plans")) {
        return Response.json({
          case_id: otherCaseId,
          data_revision: revision,
          status: "prepared",
          plan_id: planId,
          plan_hash: "plan-hash-1",
          focus: "public_pricing_analogs",
          query_previews: ["public pricing analogs"],
          manual_only_keys: ["mrr"],
          consent_text: "Only public pricing pages will be queried.",
          created_at: "2026-08-23T11:00:00Z",
          expires_at: "2026-08-24T11:00:00Z",
        });
      }
      if (path.endsWith("/research/jobs")) {
        return Response.json({ ...researchJob, plan_id: otherPlanId });
      }
      if (path.includes(`/research/jobs/${jobId}`)) {
        return Response.json({ ...researchJob, job_id: otherJobId });
      }
      throw new Error(`Unexpected path ${path}`);
    }),
  };

  await assert.rejects(() => getCopilotState(caseId, requestInit), /case/i);
  await assert.rejects(() => getCopilotThread(caseId, threadId, requestInit), /thread/i);
  await assert.rejects(
    () =>
      postCopilotMessage(
        caseId,
        {
          message: "Explain MRR",
          page_context: "metrics",
          current_section: "mrr",
          expected_case_revision: revision,
          focus_key: "mrr",
          idempotency_key: "message-1",
        },
        requestInit,
      ),
    /revision|page_context|current_section/i,
  );
  await assert.rejects(
    () =>
      saveFounderFact(
        caseId,
        {
          requirement_key: "mrr",
          value: { kind: "money", amount: "1400000", scale: "absolute", currency: "KZT" },
          period: { kind: "month", start: null, end: null, value: "2026-08" },
          source: { kind: "founder_statement", declared_source: "founder", evidence_ref: null },
          note: null,
          resolves_contradiction_id: null,
          expected_case_revision: revision,
          idempotency_key: "fact-1",
        },
        requestInit,
      ),
    /revision/i,
  );
  await assert.rejects(
    () =>
      saveAssumption(
        caseId,
        {
          requirement_key: "monthly_price",
          value: { kind: "money", amount: "40000", scale: "absolute", currency: "KZT" },
          period: { kind: "month", start: null, end: null, value: "2026-08" },
          source: { kind: "founder_statement", declared_source: "founder", evidence_ref: null },
          rationale: "Founder planning input.",
          validation_plan: "Validate later.",
          expected_case_revision: revision,
          idempotency_key: "assumption-1",
        },
        requestInit,
      ),
    /revision/i,
  );
  await assert.rejects(() => getScenarios(caseId, requestInit), /case/i);
  await assert.rejects(
    () =>
      selectScenario(
        caseId,
        {
          scenario_set_id: scenarioSetId,
          scenario_key: "optimistic",
          expected_case_revision: revision,
          idempotency_key: "scenario-1",
        },
        requestInit,
      ),
    /scenario|revision/i,
  );
  await assert.rejects(
    () =>
      prepareResearchPlan(
        caseId,
        {
          focus: "public_pricing_analogs",
          intent: "Prepare public pricing analog research.",
          requested_private_value: null,
          expected_case_revision: revision,
        },
        requestInit,
      ),
    /case/i,
  );
  await assert.rejects(
    () =>
      queueResearchJob(
        caseId,
        {
          plan_id: planId,
          plan_hash: "plan-hash-1",
          expected_case_revision: revision,
          idempotency_key: "research-job-1",
          consent_public_research: true,
          acquisition_mode: "live_public_research",
          retry_of_job_id: null,
        },
        requestInit,
      ),
    /plan|revision/i,
  );
  await assert.rejects(() => getResearchJob(caseId, jobId, requestInit), /job/i);
});

test("getReport replaces backend artifact URLs with safe same-origin URLs", async () => {
  const report = await getReport("case / 1", {
    fetcher: asFetcher(async (input) => {
      assert.equal(input, "/api/startup/cases/case%20%2F%201/report");
      return Response.json({
        case_id: "case / 1",
        report_status: "ready",
        snapshot_id: "snapshot-1",
        snapshot_hash: "sha256:abc",
        snapshot_revision: 2,
        json_url: "https://untrusted.example/private.json",
        html_url: "file:///D:/private.html",
        pdf_url: "javascript:alert(1)",
        freeze_status: "approved",
        pdf_status: "ready",
      });
    }),
  });

  assert.equal(report.json_url, "/api/startup/cases/case%20%2F%201/report/json");
  assert.equal(report.html_url, "/api/startup/cases/case%20%2F%201/report/html");
  assert.equal(report.pdf_url, "/api/startup/cases/case%20%2F%201/report/pdf");
  assert.equal(reportArtifactUrl("case / 1", "pdf"), report.pdf_url);
});

test("getStartupGtm uses the frozen same-origin GTM route and strict parser", async () => {
  const result = await getStartupGtm("case / 1", {
    fetcher: asFetcher(async (input, init) => {
      assert.equal(input, "/api/startup/cases/case%20%2F%201/gtm");
      assert.equal(init?.method, "GET");
      assert.equal(new Headers(init?.headers).get("accept"), "application/json");
      return Response.json({
        case_id: "case / 1",
        schema_version: "startup_gtm@1",
        snapshot_id: "gtm-snapshot-1",
        snapshot_hash: `sha256:${"a".repeat(64)}`,
        snapshot_revision: 2,
        status: "supported",
        profile_id: "profile-1",
        product_validation_snapshot_id: "product-snapshot-1",
        market_research_snapshot_id: "market-snapshot-1",
        dimensions: [
          {
            name: "audience",
            status: "supported",
            evidence_fact_ids: ["fact-1"],
            market_source_ids: ["market-1"],
            contradiction_ids: [],
            reason_code: "gtm_audience_supported",
            gap_code: null,
          },
          {
            name: "geography",
            status: "supported",
            evidence_fact_ids: ["fact-2"],
            market_source_ids: [],
            contradiction_ids: [],
            reason_code: "gtm_geography_supported",
            gap_code: null,
          },
          {
            name: "channels",
            status: "partial",
            evidence_fact_ids: [],
            market_source_ids: ["market-2"],
            contradiction_ids: [],
            reason_code: "gtm_channels_partial",
            gap_code: null,
          },
          {
            name: "offer",
            status: "supported",
            evidence_fact_ids: ["fact-3"],
            market_source_ids: [],
            contradiction_ids: [],
            reason_code: "gtm_offer_supported",
            gap_code: null,
          },
          {
            name: "market_context",
            status: "supported",
            evidence_fact_ids: [],
            market_source_ids: ["market-3"],
            contradiction_ids: [],
            reason_code: "gtm_market_context_supported",
            gap_code: null,
          },
          {
            name: "product_proof",
            status: "supported",
            evidence_fact_ids: ["fact-4"],
            market_source_ids: [],
            contradiction_ids: [],
            reason_code: "gtm_product_proof_supported",
            gap_code: null,
          },
          {
            name: "adoption_risk",
            status: "partial",
            evidence_fact_ids: [],
            market_source_ids: ["market-4"],
            contradiction_ids: [],
            reason_code: "gtm_adoption_risk_partial",
            gap_code: null,
          },
        ],
        launch_plan: [
          { horizon: "day_7", experiment_codes: ["clarify_audience"] },
          { horizon: "day_30", experiment_codes: ["validate_channel"] },
          { horizon: "day_60", experiment_codes: ["measure_channel_signal"] },
          { horizon: "day_90", experiment_codes: ["review_launch_evidence"] },
        ],
        finding_ids: ["finding-1"],
        built_at: "2026-08-15T00:00:00Z",
      });
    }),
  });

  assert.equal(result.snapshot_id, "gtm-snapshot-1");
  assert.equal(result.dimensions[0]?.name, "audience");
});

test("getStartupProfile uses the frozen same-origin profile route and strict parser", async () => {
  const result = await getStartupProfile("case / 1", {
    fetcher: asFetcher(async (input, init) => {
      assert.equal(input, "/api/startup/cases/case%20%2F%201/profile");
      assert.equal(init?.method, "GET");
      assert.equal(new Headers(init?.headers).get("accept"), "application/json");
      return Response.json({
        case_id: "case / 1",
        profile_id: "44444444-4444-4444-8444-444444444444",
        profile_hash: `sha256:${"3".repeat(64)}`,
        data_revision: 2,
        analysis_stage: "primary",
        parent_profile_id: null,
        fields: {
          startup_name: {
            status: "source_fact",
            values: ["FounderCo"],
            confidence: "0.95",
            evidence_refs: [
              {
                evidence_id: "11111111-1111-4111-8111-111111111111",
                fragment_id: "22222222-2222-4222-8222-222222222222",
                artifact_id: "33333333-3333-4333-8333-333333333333",
                artifact_hash: `sha256:${"1".repeat(64)}`,
                locator_hash: `sha256:${"2".repeat(64)}`,
                page: 1,
                table: null,
                cell: null,
                field_name: "startup_name",
                confidence: "0.95",
              },
            ],
            dependency_refs: [],
            reason_code: null,
            contradiction_ids: [],
          },
          one_line_description: profileInsufficientField(),
          problem: profileInsufficientField(),
          solution: profileInsufficientField(),
          icp: profileInsufficientField(),
          users: profileInsufficientField(),
          buyers: profileInsufficientField(),
          geography: profileInsufficientField(),
          stage: profileInsufficientField(),
          business_model: {
            status: "inference",
            values: ["subscription"],
            confidence: "0.60",
            evidence_refs: [],
            dependency_refs: ["11111111-1111-4111-8111-111111111111"],
            reason_code: "business_model_inferred",
            contradiction_ids: [],
          },
          pricing_revenue_model: profileInsufficientField(),
          traction: {
            status: "contradiction",
            values: ["10 pilots", "100 pilots"],
            confidence: "0.50",
            evidence_refs: [
              profileEvidence("traction", "55555555-5555-4555-8555-555555555555"),
              profileEvidence("traction", "66666666-6666-4666-8666-666666666666"),
            ],
            dependency_refs: [],
            reason_code: "traction_conflict",
            contradiction_ids: ["77777777-7777-4777-8777-777777777777"],
          },
          channels_gtm: profileInsufficientField(),
          competitors_mentioned: profileInsufficientField(),
          assumptions: profileInsufficientField(),
          strengths: profileInsufficientField(),
          weaknesses: profileInsufficientField(),
          metric_pack_candidates: profileInsufficientField(),
        },
        contradictions: ["77777777-7777-4777-8777-777777777777"],
        gaps: ["users"],
        parse_inventory: {
          source_hashes: { "doc-0001": `sha256:${"4".repeat(64)}` },
          parse_outcomes: { "doc-0001": "parsed" },
        },
      });
    }),
  });

  assert.equal(result.profile_id, "44444444-4444-4444-8444-444444444444");
  assert.equal(result.fields.startup_name.status, "source_fact");
  assert.equal(result.fields.business_model.status, "inference");
  assert.equal(result.fields.traction.status, "contradiction");
  assert.deepEqual(result.gaps, ["users"]);
});

test("getStartupReportSnapshot fetches the founder-safe JSON artifact through the same-origin route", async () => {
  const result = await getStartupReportSnapshot("case / 1", {
    fetcher: asFetcher(async (input, init) => {
      assert.equal(input, "/api/startup/cases/case%20%2F%201/report/json");
      assert.equal(init?.method, "GET");
      assert.equal(new Headers(init?.headers).get("accept"), "application/json");
      return Response.json({
        title_ru: "Отчёт для основателя",
        subtitle_ru: "Краткий разбор проекта",
        as_of_ru: "2026-08-15",
        data_revision: 3,
        main_sections: [
          {
            key: "go_to_market",
            title_ru: "Выход на рынок",
            status: "partial",
            status_label_ru: "Нужно уточнить",
            summary_ru: "Канал продаж подтверждён частично.",
            content_heading_ru: "Что уже известно",
            known_facts_ru: ["Есть первый канал продаж."],
            blockers_ru: [],
            next_data_ru: ["Добавить доказательство канала."],
            unlocks_ru: ["Можно точнее оценить GTM."],
          },
        ],
        metric_cards: {},
        improvement_proposals: [],
        technical_appendix: {
          methodology_ru: ["Отчёт построен по безопасной проекции."],
          sources_ru: ["Внутренние идентификаторы скрыты."],
        },
        analytics: {
          metric_points: [
            {
              key: "arr",
              label_ru: "ARR",
              value: 1200000,
              unit: "USD",
              period_ru: "Q2 2026",
              status: "confirmed",
            },
          ],
          market_points: [],
          readiness_dimensions: [],
        },
      });
    }),
  });

  assert.equal(result.title_ru, "Отчёт для основателя");
  assert.equal(result.data_revision, 3);
  assert.equal(result.main_sections[0]?.key, "go_to_market");
  assert.equal(result.analytics.metric_points[0]?.key, "arr");
});

function profileInsufficientField() {
  return {
    status: "insufficient_data",
    values: [],
    confidence: "0",
    evidence_refs: [],
    dependency_refs: [],
    reason_code: null,
    contradiction_ids: [],
  };
}

function profileEvidence(fieldName: string, evidenceId: string) {
  return {
    evidence_id: evidenceId,
    fragment_id: "22222222-2222-4222-8222-222222222222",
    artifact_id: "33333333-3333-4333-8333-333333333333",
    artifact_hash: `sha256:${"1".repeat(64)}`,
    locator_hash: `sha256:${"2".repeat(64)}`,
    page: 1,
    table: null,
    cell: null,
    field_name: fieldName,
    confidence: "0.95",
  };
}

test("downloadReportArtifact returns the same-origin response without interpreting binary data", async () => {
  const response = await downloadReportArtifact("case-1", "pdf", {
    fetcher: asFetcher(async (input, init) => {
      assert.equal(input, "/api/startup/cases/case-1/report/pdf");
      assert.equal(init?.method, "GET");
      assert.equal(new Headers(init?.headers).get("accept"), "application/pdf");
      return new Response(new Uint8Array([37, 80, 68, 70]), {
        headers: { "content-type": "application/pdf" },
      });
    }),
  });

  assert.deepEqual(
    new Uint8Array(await response.arrayBuffer()),
    new Uint8Array([37, 80, 68, 70]),
  );
});

test("advisor client uses the Task 5 same-origin routes and preserves consent boundaries", async () => {
  const calls: Array<Readonly<{ path: string; method: string; body: unknown }>> = [];
  const result = await getAdvisorNextQuestion("case / 1", {
    fetcher: asFetcher(async (input, init) => {
      calls.push({
        path: String(input),
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      return Response.json({
        case_id: "case / 1",
        status: "active",
        next_question: {
          question_id: "case-1:icp",
          field_key: "icp",
          question_ru: "Кто платит за продукт?",
          reason_ru: "Уточняет ICP.",
          unlocks_ru: "Улучшит оценку GTM.",
          answer_modes: ["manual", "file", "public_research", "skip"],
          origin: "document_gap",
          origin_label_ru: "Пробел в документе",
          context_ru: "Документ не подтверждает ICP.",
          answer_mode_labels_ru: {
            manual: "Ответить вручную",
            file: "Прикрепить файл",
            public_research: "Разрешить публичный поиск",
            skip: "Пропустить",
          },
        },
        answered_count: 1,
        total_count: 5,
      });
    }),
  });

  const answer = await submitAdvisorAnswer(
    "case / 1",
    {
      question_id: "case-1:icp",
      answer_type: "public_research",
      value: null,
      document_id: null,
      consent_public_research: true,
    },
    {
      fetcher: asFetcher(async (input, init) => {
        calls.push({
          path: String(input),
          method: init?.method ?? "GET",
          body: init?.body ? JSON.parse(String(init.body)) : null,
        });
        return Response.json({
          case_id: "case / 1",
          question_id: "case-1:icp",
          field_key: "icp",
          answer_type: "public_research",
          status: "applied",
          confidence_delta: 5,
          analysis_blocked: false,
          answered_count: 2,
          total_count: 5,
          research_result: {
            status: "partial",
            summary_ru: "Найдены публичные сигналы без раскрытия источников.",
            source_ids: ["11111111-1111-4111-8111-111111111111"],
            fallback_used: true,
            fail_reason_ru: null,
          },
          recalculation_status: "started",
          recalculation_data_revision: 2,
          recalculation_analysis_status: "gate2_preview_ready",
          recalculation_delta: {
            previous_revision: 1,
            new_revision: 2,
            fields_changed: ["icp"],
            core_coverage_delta: 1,
            conflicts_resolved: 0,
            conflicts_remaining: 0,
            calculations_recalculated: [],
            calculations_pending: ["report"],
          },
        });
      }),
    },
  );
  const improvements = await getAdvisorImprovements("case / 1", {
    fetcher: asFetcher(async (input, init) => {
      calls.push({
        path: String(input),
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      return Response.json({
        case_id: "case / 1",
        improvement_version: 6,
        proposals: Array.from({ length: 6 }, (_, index) => ({
          proposal_id: crypto.randomUUID(),
          target_area: "POSITIONING",
          recommendation_ru: `Рекомендация ${index + 1}.`,
          rationale_ru: `Логика ${index + 1}.`,
          expected_effect_ru: `Эффект ${index + 1}.`,
          evidence_kinds: ["live_inference"],
          confidence: "0.7",
        })),
      });
    }),
  });
  const decision = await decideAdvisorImprovement(
    "case / 1",
    improvements.proposals[0]?.proposal_id ?? crypto.randomUUID(),
    "accepted",
    {
      fetcher: asFetcher(async (input, init) => {
        calls.push({
          path: String(input),
          method: init?.method ?? "GET",
          body: init?.body ? JSON.parse(String(init.body)) : null,
        });
        return Response.json({
          case_id: "case / 1",
          proposal_id: (input as string).split("/").at(-2),
          decision: "accepted",
          previous_version: 6,
          new_version: 7,
          changed_fields: ["positioning"],
          recalculation_status: "started",
          recalculation_data_revision: 2,
          recalculation_analysis_status: "gate2_preview_ready",
        });
      }),
    },
  );

  assert.equal(result.next_question?.field_key, "icp");
  assert.equal(answer.answer_type, "public_research");
  assert.equal(improvements.proposals.length, 6);
  assert.equal(decision.new_version, 7);
  assert.equal(calls[0]?.path, "/api/startup/cases/case%20%2F%201/advisor/next-question");
  assert.equal(calls[1]?.path, "/api/startup/cases/case%20%2F%201/advisor/answers");
  assert.deepEqual(calls[1]?.body, {
    question_id: "case-1:icp",
    answer_type: "public_research",
    value: null,
    document_id: null,
    consent_public_research: true,
  });
  assert.equal(calls[2]?.path, "/api/startup/cases/case%20%2F%201/advisor/improvements");
  assert.match(
    calls[3]?.path ?? "",
    /^\/api\/startup\/cases\/case%20%2F%201\/advisor\/improvements\/[^/]+\/decision$/u,
  );
  assert.deepEqual(calls[3]?.body, { decision: "accepted" });
});

test("non-JSON failures become typed api_rejected errors without leaking response text", async () => {
  await assert.rejects(
    getCase("case-1", {
      fetcher: asFetcher(async () =>
        new Response("stack trace D:/secret token=abc", {
          status: 502,
          headers: { "content-type": "text/plain" },
        }),
      ),
    }),
    (error: unknown) => {
      assert.ok(error instanceof FounderApiClientError);
      assert.equal(error.code, "api_rejected");
      assert.equal(error.status, 502);
      assert.equal(error.details, null);
      assert.doesNotMatch(error.message, /secret|token|D:\//i);
      return true;
    },
  );
});

test("backend error code status message and details are preserved", async () => {
  const details = { expected_revision: 4, actual_revision: 5 };

  await assert.rejects(
    decideGate4(
      "case-1",
      {
        decision: "approved",
        snapshot_hash: "sha256:stale",
        snapshot_revision: 4,
      },
      {
        fetcher: asFetcher(async () =>
          Response.json(
            {
              code: "gate_4_snapshot_mismatch",
              message: "The report changed after review",
              details,
            },
            { status: 409 },
          ),
        ),
      },
    ),
    (error: unknown) => {
      assert.ok(error instanceof FounderApiClientError);
      assert.equal(error.code, "gate_4_snapshot_mismatch");
      assert.equal(error.status, 409);
      assert.equal(error.message, "The report changed after review");
      assert.deepEqual(error.details, details);
      return true;
    },
  );
});

test("fact validation failures expose strictly parsed field errors on typed client errors", async () => {
  await assert.rejects(
    saveFounderFact(
      "case-1",
      {
        requirement_key: "mrr",
        value: { kind: "money", amount: "not numeric", scale: "absolute", currency: "KZT" },
        period: { kind: "month", start: null, end: null, value: "2026-08" },
        source: { kind: "founder_statement", declared_source: "founder", evidence_ref: null },
        note: null,
        resolves_contradiction_id: null,
        expected_case_revision: 4,
        idempotency_key: "fact-validation-1",
      },
      {
        fetcher: asFetcher(async () =>
          Response.json(
            {
              code: "fact_validation_failed",
              message: "Founder fact validation failed",
              errors: [{ field: "value.amount", message: "must be numeric" }],
            },
            { status: 422 },
          ),
        ),
      },
    ),
    (error: unknown) => {
      assert.ok(error instanceof FounderApiClientError);
      assert.equal(error.code, "fact_validation_failed");
      assert.equal(error.status, 422);
      assert.equal(error.message, "Founder fact validation failed");
      assert.equal(error.details, null);
      assert.deepEqual(error.validationErrors, [
        { field: "value.amount", message: "must be numeric" },
      ]);
      return true;
    },
  );
});

test("malformed or unsafe validation errors become generic client failures", async () => {
  const hostileErrors = [
    { label: "non-array errors", errors: { field: "value.amount", message: "must be numeric" } },
    { label: "unknown entry key", errors: [{ field: "value.amount", message: "must be numeric", leak: "secret" }] },
    { label: "blank field", errors: [{ field: " ", message: "must be numeric" }] },
    { label: "unsafe field", errors: [{ field: "../../secret", message: "must be numeric" }] },
    { label: "blank message", errors: [{ field: "value.amount", message: " " }] },
    { label: "unsafe message", errors: [{ field: "value.amount", message: "stack trace D:/secret token=abc" }] },
  ] as const;

  for (const entry of hostileErrors) {
    await assert.rejects(
      saveFounderFact(
        "case-1",
        {
          requirement_key: "mrr",
          value: { kind: "money", amount: "not numeric", scale: "absolute", currency: "KZT" },
          period: { kind: "month", start: null, end: null, value: "2026-08" },
          source: { kind: "founder_statement", declared_source: "founder", evidence_ref: null },
          note: null,
          resolves_contradiction_id: null,
          expected_case_revision: 4,
          idempotency_key: `fact-validation-${entry.label}`,
        },
        {
          fetcher: asFetcher(async () =>
            Response.json(
              {
                code: "fact_validation_failed",
                message: "Founder fact validation failed",
                errors: entry.errors,
              },
              { status: 422 },
            ),
          ),
        },
      ),
      (error: unknown) => {
        assert.ok(error instanceof FounderApiClientError, entry.label);
        assert.equal(error.code, "api_rejected", entry.label);
        assert.equal(error.status, 422, entry.label);
        assert.equal(error.details, null, entry.label);
        assert.deepEqual(error.validationErrors, [], entry.label);
        assert.doesNotMatch(error.message, /secret|token|D:\//i, entry.label);
        return true;
      },
    );
  }
});

test("field errors attached to non-fact-validation codes become generic client failures", async () => {
  const masqueradingErrors = [
    { code: "case_not_found", status: 404 },
    { code: "case_revision_conflict", status: 409 },
  ] as const;

  for (const entry of masqueradingErrors) {
    await assert.rejects(
      saveFounderFact(
        "case-1",
        {
          requirement_key: "mrr",
          value: { kind: "money", amount: "not numeric", scale: "absolute", currency: "KZT" },
          period: { kind: "month", start: null, end: null, value: "2026-08" },
          source: { kind: "founder_statement", declared_source: "founder", evidence_ref: null },
          note: null,
          resolves_contradiction_id: null,
          expected_case_revision: 4,
          idempotency_key: `fact-validation-${entry.code}`,
        },
        {
          fetcher: asFetcher(async () =>
            Response.json(
              {
                code: entry.code,
                message: `${entry.code} message`,
                errors: [{ field: "value.amount", message: "must be numeric" }],
              },
              { status: entry.status },
            ),
          ),
        },
      ),
      (error: unknown) => {
        assert.ok(error instanceof FounderApiClientError, entry.code);
        assert.equal(error.code, "api_rejected", entry.code);
        assert.equal(error.status, entry.status, entry.code);
        assert.equal(error.details, null, entry.code);
        assert.deepEqual(error.validationErrors, [], entry.code);
        assert.doesNotMatch(error.message, /value\.amount|must be numeric/u, entry.code);
        return true;
      },
    );
  }
});

test("an external AbortSignal cancels a request through the composed fetch signal", async () => {
  const controller = new AbortController();
  const reason = new DOMException("User left the case", "AbortError");
  let observedSignal: AbortSignal | undefined;
  const pending = getAnalysis("case-1", {
    signal: controller.signal,
    timeoutMs: 30_000,
    fetcher: asFetcher(async (_input, init) => {
      observedSignal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        observedSignal?.addEventListener("abort", () => reject(observedSignal?.reason), {
          once: true,
        });
      });
    }),
  });

  controller.abort(reason);

  await assert.rejects(pending, (error: unknown) => error === reason);
  assert.ok(observedSignal);
  assert.notEqual(observedSignal, controller.signal);
  assert.equal(observedSignal.aborted, true);
});
