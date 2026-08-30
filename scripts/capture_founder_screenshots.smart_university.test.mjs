import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  collectSmartUniversityLiveAuditEvidence,
  selectSmartUniversityLiveAcquisitionMode,
  selectSmartUniversityResearchTabLabel,
  validateSmartUniversitySinglePdfJourneyEvidence,
} from "./capture_founder_screenshots.mjs";

function validJourney(overrides = {}) {
  return {
    smartUniversitySinglePdfJourney: {
      case_identity: {
        case_id: "case-smart-university",
        thread_id: "thread-smart-university",
        research_job_id: "research-job-smart-university",
        selected_scenario_key: "base",
        asset_id: "asset-smart-university",
      },
      upload: {
        pdf_uploaded: true,
        receipt_visible: true,
        profile_source_grounded: true,
        gate2_ready: true,
      },
      founder_gap_handling: {
        question_visible: true,
        answered_or_skipped: true,
        private_metrics_manual_or_file_only: true,
      },
      public_research: {
        explicit_consent: true,
        status: "completed",
        visible_sources: ["https://example.com/public-benchmark"],
        scenario_delta_visible: true,
        scenario_change_evidence: {
          rendered_comparison_count: 3,
          rendered_change_count: 1,
        },
        source_fact_promotion_blocked: true,
        provenance_guard: {
          accepted_inputs_checked: true,
          profile_fields_checked: true,
          public_private_aliases_blocked: true,
        },
      },
      scenarios: {
        keys: ["conservative", "base", "optimistic"],
        selected_key: "base",
        provenance_complete: true,
      },
      outputs: {
        metrics_visible: true,
        market_reconstruction_visible: true,
        risks_visible: true,
        actions_visible: true,
        page_evidence: {
          metrics: {
            case_id: "case-smart-university",
            contract_satisfied: true,
            meaningful_item_count: 3,
            populated: true,
            placeholder_only: false,
            rendered_text_chars: 240,
            source_signal_count: 2,
          },
          market: {
            case_id: "case-smart-university",
            contract_satisfied: true,
            meaningful_item_count: 3,
            populated: true,
            placeholder_only: false,
            rendered_text_chars: 240,
            source_signal_count: 2,
          },
          risks: {
            case_id: "case-smart-university",
            contract_satisfied: true,
            meaningful_item_count: 2,
            populated: true,
            placeholder_only: false,
            rendered_text_chars: 200,
            source_signal_count: 1,
          },
          action_plan: {
            case_id: "case-smart-university",
            contract_satisfied: true,
            meaningful_item_count: 3,
            populated: true,
            placeholder_only: false,
            rendered_text_chars: 260,
            source_signal_count: 1,
          },
        },
        plan_7_30_60_90_visible: true,
        launch_pack_link_visible: true,
        launch_pack_downloaded: true,
        launch_pack_contract: {
          platform_vs_housing_separated: true,
          tariff_and_lead_economics_present: true,
          forecast_2027_2031_clear: true,
          rating_methodology_present: true,
          housing_legal_fire_sanitary_gates_present: true,
          tranche_plan_present: true,
          provenance_appendix_present: true,
        },
      },
      restart: {
        process_restarted: true,
        langgraph_checkpoint_reloaded: true,
        same_case_ui_rehydrated: true,
        same_case_reloaded: true,
        same_thread_reloaded: true,
        same_research_job_reloaded: true,
        same_scenario_reloaded: true,
        same_asset_reloaded: true,
      },
      ...overrides,
    },
  };
}

function validLiveResearch(overrides = {}) {
  return {
    ...validJourney().smartUniversitySinglePdfJourney.public_research,
    acquisition_mode: "live_public_research",
    latency_ms: 1200,
    provider: "openai",
    requested_acquisition_mode: "live_public_research",
    sanitized_sources: [
      {
        as_of: "2026-08-27",
        source_mode: "live",
        url: "https://example.com/public-benchmark",
      },
    ],
    selected_acquisition_mode: "live_public_research",
    source_count: 1,
    token_cost_status: {
      raw_values_excluded: true,
      status: "usage_observed",
    },
    tool: "web_search",
    tool_call_observed: true,
    trace_health: {
      audit_status: "ok",
      langsmith_status: "healthy",
      status: "healthy",
    },
    ...overrides,
  };
}

function validLiveJourney(publicResearch = validLiveResearch()) {
  return validJourney({
    public_research: publicResearch,
    outputs: {
      ...validJourney().smartUniversitySinglePdfJourney.outputs,
      final_decision_accepted: true,
      report_artifacts: {
        case_id: "case-smart-university",
        downloaded_formats: ["JSON", "HTML", "PDF"],
        html_path: "/api/startup/cases/case-smart-university/report/html",
        html_sha256: `sha256:${"a".repeat(64)}`,
        json_path: "/api/startup/cases/case-smart-university/report/json",
        json_sha256: `sha256:${"b".repeat(64)}`,
        pdf_bounded: true,
        pdf_magic: "%PDF",
        pdf_path: "/api/startup/cases/case-smart-university/report/pdf",
        pdf_sha256: `sha256:${"c".repeat(64)}`,
        report_snapshot_id: "snapshot-smart-university",
      },
    },
    restart: {
      ...validJourney().smartUniversitySinglePdfJourney.restart,
      same_final_decision_reloaded: true,
      same_report_artifacts_reloaded: true,
      langgraph_checkpoint: {
        checkpoint_hash: "d".repeat(64),
        checkpoint_id: "1f1a1fb3-c02e-6bb0-8008-d92ea1be1c4a",
        data_revision: 2,
        thread_id: "case-smart-university:r2",
      },
      report_artifacts: {
        html_sha256: `sha256:${"a".repeat(64)}`,
        json_sha256: `sha256:${"b".repeat(64)}`,
        pdf_sha256: `sha256:${"c".repeat(64)}`,
        report_snapshot_id: "snapshot-smart-university",
      },
    },
    case_identity: {
      ...validJourney().smartUniversitySinglePdfJourney.case_identity,
      langgraph_checkpoint: {
        checkpoint_hash: "d".repeat(64),
        checkpoint_id: "1f1a1fb3-c02e-6bb0-8008-d92ea1be1c4a",
        data_revision: 2,
        thread_id: "case-smart-university:r2",
      },
    },
  });
}

test("validates a sanitized single-PDF Smart University same-case journey", () => {
  const evidence = validateSmartUniversitySinglePdfJourneyEvidence(validJourney(), {
    mime_type: "application/pdf",
  });

  assert.equal(evidence.case_identity.case_id, "case-smart-university");
  assert.equal(evidence.public_research.status, "completed");
});

test("rejects text fixtures and raw owner-local evidence in the Smart University mode", () => {
  assert.throws(
    () =>
      validateSmartUniversitySinglePdfJourneyEvidence(validJourney(), {
        mime_type: "text/plain",
      }),
    /smart_university_single_pdf_journey_requires_pdf_fixture/u,
  );

  assert.throws(
    () =>
      validateSmartUniversitySinglePdfJourneyEvidence(
        validJourney({
          upload: {
            pdf_uploaded: true,
            receipt_visible: true,
            profile_source_grounded: true,
            gate2_ready: true,
            owner_path: "C:\\Users\\Owner\\Documents\\private-plan.pdf",
          },
        }),
        { mime_type: "application/pdf" },
      ),
    /smart_university_single_pdf_journey_sensitive_value/u,
  );
});

test("rejects non-base selected scenarios in the Smart University evidence contract", () => {
  assert.throws(
    () =>
      validateSmartUniversitySinglePdfJourneyEvidence(
        validJourney({
          case_identity: {
            case_id: "case-smart-university",
            thread_id: "thread-smart-university",
            research_job_id: "research-job-smart-university",
            selected_scenario_key: "optimistic",
            asset_id: "asset-smart-university",
          },
          scenarios: {
            keys: ["conservative", "base", "optimistic"],
            selected_key: "optimistic",
            provenance_complete: true,
          },
        }),
        { mime_type: "application/pdf" },
      ),
    /smart_university_single_pdf_journey_requires_base_scenario/u,
  );
});

test("rejects weak public research provenance and private alias promotion", () => {
  for (const override of [
    {
      scenario_delta_visible: true,
      scenario_change_evidence: {
        rendered_comparison_count: 3,
        rendered_change_count: 0,
      },
      source_fact_promotion_blocked: true,
      provenance_guard: {
        accepted_inputs_checked: true,
        profile_fields_checked: true,
        public_private_aliases_blocked: true,
      },
    },
    {
      scenario_delta_visible: true,
      scenario_change_evidence: {
        rendered_comparison_count: 3,
        rendered_change_count: 1,
      },
      source_fact_promotion_blocked: true,
      provenance_guard: {
        accepted_inputs_checked: true,
        profile_fields_checked: true,
        public_private_aliases_blocked: false,
      },
    },
  ]) {
    assert.throws(
      () =>
        validateSmartUniversitySinglePdfJourneyEvidence(
          validJourney({ public_research: {
            explicit_consent: true,
            status: "completed",
            visible_sources: ["https://example.com/public-benchmark"],
            ...override,
          } }),
          { mime_type: "application/pdf" },
        ),
      /smart_university_single_pdf_journey_(?:scenario_change_evidence|public_research_provenance_guard)_invalid/u,
    );
  }
});

test("Smart University private alias guard covers invoice and bank aliases", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const patternSource = script.match(/const privateFieldPattern = \/(.*?)\/iu;/su)?.[1] ?? "";

  for (const token of [
    "invoice",
    "invoice_register",
    "bank_data",
    "инвойс",
    "банк",
    "банков",
    "сч",
    "накладн",
  ]) {
    assert.match(patternSource, new RegExp(token, "iu"));
  }
});

test("rejects incomplete launch pack contract evidence", () => {
  const baseOutputs = validJourney().smartUniversitySinglePdfJourney.outputs;

  assert.throws(
    () =>
      validateSmartUniversitySinglePdfJourneyEvidence(
        validJourney({ outputs: {
          ...baseOutputs,
          metrics_visible: true,
          market_reconstruction_visible: true,
          risks_visible: true,
          actions_visible: true,
          plan_7_30_60_90_visible: true,
          launch_pack_link_visible: true,
          launch_pack_downloaded: true,
          launch_pack_contract: {
            platform_vs_housing_separated: true,
            tariff_and_lead_economics_present: true,
            forecast_2027_2031_clear: true,
            rating_methodology_present: true,
            housing_legal_fire_sanitary_gates_present: true,
            tranche_plan_present: true,
            provenance_appendix_present: false,
          },
        } }),
        { mime_type: "application/pdf" },
      ),
    /smart_university_single_pdf_journey_launch_pack_contract_invalid/u,
  );
});

test("rejects placeholder-only Smart University page evidence", () => {
  assert.throws(
    () =>
      validateSmartUniversitySinglePdfJourneyEvidence(
        validJourney({ outputs: {
          ...validJourney().smartUniversitySinglePdfJourney.outputs,
          page_evidence: {
            ...validJourney().smartUniversitySinglePdfJourney.outputs.page_evidence,
            market: {
              case_id: "case-smart-university",
              contract_satisfied: false,
              meaningful_item_count: 0,
              populated: true,
              placeholder_only: true,
              rendered_text_chars: 340,
              source_signal_count: 0,
            },
          },
        } }),
        { mime_type: "application/pdf" },
      ),
    /smart_university_single_pdf_journey_page_evidence_invalid page=market/u,
  );
});

test("accepts degraded LangSmith only when sanitized local audit proves live OpenAI web search", () => {
  const journey = validLiveJourney(
    validLiveResearch({
      trace_health: {
        audit_status: "ok",
        error_code: "external_export_failed",
        fallback_used: "local_audit",
        langsmith_status: "degraded",
        status: "degraded",
      },
    }),
  );

  assert.equal(
    validateSmartUniversitySinglePdfJourneyEvidence(
      journey,
      { mime_type: "application/pdf" },
      { requireLivePublicResearch: true },
    ).public_research.trace_health.fallback_used,
    "local_audit",
  );
});

test("rejects degraded live research evidence without exact local-audit fallback reason", () => {
  for (const traceHealth of [
    {
      audit_status: "ok",
      langsmith_status: "degraded",
      status: "degraded",
    },
    {
      audit_status: "ok",
      error_code: "external_export_failed",
      fallback_used: "offline_demo",
      langsmith_status: "degraded",
      status: "degraded",
    },
    {
      audit_status: "ok",
      error_code: "timeout",
      fallback_used: "local_audit",
      langsmith_status: "degraded",
      status: "degraded",
    },
    {
      audit_status: "missing",
      error_code: "external_export_failed",
      fallback_used: "local_audit",
      langsmith_status: "degraded",
      status: "degraded",
    },
  ]) {
    assert.throws(
      () =>
        validateSmartUniversitySinglePdfJourneyEvidence(
          validLiveJourney(validLiveResearch({ trace_health: traceHealth })),
          { mime_type: "application/pdf" },
          { requireLivePublicResearch: true },
        ),
      /smart_university_single_pdf_journey_live_trace_invalid/u,
    );
  }
});

test("rejects disabled or offline tracing even when local live audit exists", () => {
  for (const traceHealth of [
    {
      audit_status: "ok",
      error_code: "external_export_failed",
      fallback_used: "local_audit",
      langsmith_status: "disabled",
      status: "degraded",
    },
    {
      audit_status: "ok",
      error_code: "external_export_failed",
      fallback_used: "local_audit",
      langsmith_status: "degraded",
      status: "offline",
    },
  ]) {
    assert.throws(
      () =>
        validateSmartUniversitySinglePdfJourneyEvidence(
          validLiveJourney(validLiveResearch({ trace_health: traceHealth })),
          { mime_type: "application/pdf" },
          { requireLivePublicResearch: true },
        ),
      /smart_university_single_pdf_journey_live_trace_invalid/u,
    );
  }
});

test("live Smart University evidence requires a stable LangGraph checkpoint across restart", () => {
  const liveJourney = validJourney({
    public_research: validLiveResearch(),
    outputs: {
      ...validJourney().smartUniversitySinglePdfJourney.outputs,
      final_decision_accepted: true,
      report_artifacts: {
        case_id: "case-smart-university",
        downloaded_formats: ["JSON", "HTML", "PDF"],
        html_path: "/api/startup/cases/case-smart-university/report/html",
        html_sha256: `sha256:${"a".repeat(64)}`,
        json_path: "/api/startup/cases/case-smart-university/report/json",
        json_sha256: `sha256:${"b".repeat(64)}`,
        pdf_bounded: true,
        pdf_magic: "%PDF",
        pdf_path: "/api/startup/cases/case-smart-university/report/pdf",
        pdf_sha256: `sha256:${"c".repeat(64)}`,
        report_snapshot_id: "snapshot-smart-university",
      },
    },
    restart: {
      ...validJourney().smartUniversitySinglePdfJourney.restart,
      same_final_decision_reloaded: true,
      same_report_artifacts_reloaded: true,
      report_artifacts: {
        html_sha256: `sha256:${"a".repeat(64)}`,
        json_sha256: `sha256:${"b".repeat(64)}`,
        pdf_sha256: `sha256:${"c".repeat(64)}`,
        report_snapshot_id: "snapshot-smart-university",
      },
    },
  });

  assert.throws(
    () =>
      validateSmartUniversitySinglePdfJourneyEvidence(
        liveJourney,
        { mime_type: "application/pdf" },
        { requireLivePublicResearch: true },
      ),
    /smart_university_single_pdf_journey_langgraph_checkpoint_invalid/u,
  );

  liveJourney.smartUniversitySinglePdfJourney.case_identity.langgraph_checkpoint = {
    checkpoint_hash: "d".repeat(64),
    checkpoint_id: "1f1a1fb3-c02e-6bb0-8008-d92ea1be1c4a",
    data_revision: 2,
    thread_id: "case-smart-university:r2",
  };
  liveJourney.smartUniversitySinglePdfJourney.restart.langgraph_checkpoint = {
    checkpoint_hash: "d".repeat(64),
    checkpoint_id: "1f1a1fb3-c02e-6bb0-8008-d92ea1be1c4a",
    data_revision: 2,
    thread_id: "case-smart-university:r2",
  };
  assert.equal(
    validateSmartUniversitySinglePdfJourneyEvidence(
      liveJourney,
      { mime_type: "application/pdf" },
      { requireLivePublicResearch: true },
    ).restart.langgraph_checkpoint_reloaded,
    true,
  );

  liveJourney.smartUniversitySinglePdfJourney.restart.langgraph_checkpoint.checkpoint_hash =
    "e".repeat(64);
  assert.throws(
    () =>
      validateSmartUniversitySinglePdfJourneyEvidence(
        liveJourney,
        { mime_type: "application/pdf" },
        { requireLivePublicResearch: true },
      ),
    /smart_university_single_pdf_journey_langgraph_checkpoint_mismatch/u,
  );

  liveJourney.smartUniversitySinglePdfJourney.restart.langgraph_checkpoint.checkpoint_hash =
    "d".repeat(64);
  liveJourney.smartUniversitySinglePdfJourney.restart.langgraph_checkpoint.checkpoint_id =
    "1f1a1fb3-c02e-6bb0-8008-d92ea1be1c4b";
  assert.throws(
    () =>
      validateSmartUniversitySinglePdfJourneyEvidence(
        liveJourney,
        { mime_type: "application/pdf" },
        { requireLivePublicResearch: true },
      ),
    /smart_university_single_pdf_journey_langgraph_checkpoint_mismatch/u,
  );
});

test("rejects restart evidence without same-case UI rehydration", () => {
  assert.throws(
    () =>
      validateSmartUniversitySinglePdfJourneyEvidence(
        validJourney({ restart: {
          process_restarted: true,
          same_case_ui_rehydrated: false,
          same_case_reloaded: true,
          same_thread_reloaded: true,
          same_research_job_reloaded: true,
          same_scenario_reloaded: true,
          same_asset_reloaded: true,
        } }),
        { mime_type: "application/pdf" },
      ),
    /smart_university_single_pdf_journey_missing_restart_same_case_ui_rehydrated/u,
  );
});

test("Smart University live audit reader tails newest JSONL bytes", () => {
  const root = mkdtempSync(join(tmpdir(), "smart-university-audit-tail-"));
  const path = join(root, "audit.jsonl");
  const event = {
    attributes: {
      case_id: "case-smart-university",
      checkpoint_hash: "d".repeat(64),
      checkpoint_id: "startup-market_research-ab12cd34",
      data_revision: 2,
      provider: "openai",
      request_id: "research-job-smart-university",
      research_label: "live_public_research",
      source_count: 1,
      status: "completed",
      thread_id: "case-smart-university:r2",
      tool: "web_search",
      tool_call_observed: true,
      total_tokens: 12,
    },
    event_type: "tool_call",
    span_name: "startup.public_research",
    timestamp_utc: "2026-08-27T10:00:00Z",
  };
  writeFileSync(path, `${"x".repeat(1_050_000)}\n${JSON.stringify(event)}\n`, "utf8");

  const evidence = collectSmartUniversityLiveAuditEvidence(
    root,
    "case-smart-university",
    "research-job-smart-university",
  );

  assert.equal(evidence.provider, "openai");
  assert.equal(evidence.langgraph_checkpoint, undefined);
});

test("Smart University live audit reader exposes only founder-safe LangSmith fallback metadata", () => {
  const root = mkdtempSync(join(tmpdir(), "smart-university-audit-langsmith-"));
  const path = join(root, "audit.jsonl");
  const providerEvent = {
    attributes: {
      case_id: "case-smart-university",
      latency_ms: 1500,
      provider: "openai",
      request_id: "research-job-smart-university",
      research_label: "live_public_research",
      source_count: 2,
      status: "completed",
      tool: "web_search",
      tool_call_observed: true,
      total_tokens: 12,
    },
    event_type: "tool_call",
    span_name: "startup.public_research",
    timestamp_utc: "2026-08-27T10:00:00Z",
  };
  const langsmithEvent = {
    attributes: {
      case_id: "case-smart-university",
      error_code: "external_export_failed",
      exporter_provider: "langsmith",
      fallback_used: "local_audit",
      prompt: "must not be copied",
      status: "degraded",
      total_tokens: 999,
    },
    event_type: "observability.langsmith_status",
    timestamp_utc: "2026-08-27T10:00:01Z",
  };
  writeFileSync(
    path,
    `${JSON.stringify(providerEvent)}\n${JSON.stringify(langsmithEvent)}\n`,
    "utf8",
  );

  const evidence = collectSmartUniversityLiveAuditEvidence(
    root,
    "case-smart-university",
    "research-job-smart-university",
  );

  assert.deepEqual(evidence.trace_health, {
    audit_status: "ok",
    error_code: "external_export_failed",
    fallback_used: "local_audit",
    langsmith_status: "degraded",
    status: "degraded",
  });
});

test("Smart University restart checkpoint is not echoed from pre-restart args", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");

  assert.doesNotMatch(
    script,
    /checkpoint_hash:\s*String\(args\.langgraphCheckpoint\?\.checkpoint_hash/u,
  );
  assert.doesNotMatch(
    script,
    /checkpoint_id:\s*String\(args\.langgraphCheckpoint\?\.checkpoint_id/u,
  );
});

test("Smart University page evidence ignores generic scenario and formula placeholder text", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");

  assert.doesNotMatch(script, /\/сценар\/iu/u);
  assert.doesNotMatch(script, /\/расч\[её\]т\/iu/u);
  assert.match(script, /structuredSelectorsByView/u);
  assert.match(script, /contractChecksByView/u);
  assert.match(script, /Object\.values\(contractChecks\)\.every/u);
  assert.match(script, /populated:\s*hasVisibleView && hasRequiredText && contractSatisfied/u);
  assert.match(script, /\[class\*='metricsSourceList'\] li/u);
  assert.match(script, /\[class\*='metricsDeltaList'\] > div/u);
  assert.match(script, /\["7", "30", "60", "90"\]\.every/u);
  for (const clause of [
    "research_summary",
    "source_or_delta",
    "scenario_details",
    "public_research_impact",
    "non_placeholder_opportunity",
    "real_competitor",
    "real_signal",
    "scenario_issue",
    "risk_assessment",
    "actual_question",
    "priority_basis",
    "non_ai_timeline",
    "draft_markdown_ready",
    "draft_provenance_ready",
  ]) {
    assert.match(script, new RegExp(clause, "u"));
  }
});

test("validate-only CLI exposes a Smart University single-PDF evidence contract", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");

  assert.match(script, /require-smart-university-single-pdf-journey/u);
  assert.match(script, /smart_university_single_pdf_journey_required/u);
  assert.doesNotMatch(script, /Akana|Business[_ -]?Plan[_ -]?2026\.pdf/iu);
});

test("non-validate Smart University mode drives one real PDF journey before writing evidence", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");

  assert.match(script, /async function driveSmartUniversitySinglePdfJourney\(/u);
  assert.match(
    script,
    /if \(requireSmartUniversitySinglePdfJourney\) \{[\s\S]*driveSmartUniversitySinglePdfJourney\(/u,
  );
  assert.match(
    script,
    /driveSmartUniversitySinglePdfJourney\([\s\S]*caseCopilotRestartRequestPath[\s\S]*caseCopilotRestartReadyPath/u,
  );
});

test("Smart University driver validates the complete journey only after restart evidence exists", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const restartRequest = driver.indexOf("requestCaseCopilotServiceRestart(");
  const fullValidation = driver.indexOf(
    "validateSmartUniversitySinglePdfJourneyEvidence(",
  );

  assert.notEqual(driverStart, -1);
  assert.notEqual(driverEnd, -1);
  assert.notEqual(restartRequest, -1);
  assert.equal(
    fullValidation === -1 || fullValidation > restartRequest,
    true,
    "pre-restart evidence cannot satisfy the mandatory restart assertions",
  );
});

test("Smart University driver freezes each routed view before it is unmounted", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);

  for (const frozenFlag of [
    "marketReconstructionVisible",
    "risksVisible",
    "actionsVisible",
    "planHorizonVisible",
    "scenarioDeltaVisible",
  ]) {
    assert.match(driver, new RegExp(`const ${frozenFlag} = await evaluateValue`, "u"));
    assert.match(driver, new RegExp(`${frozenFlag},`, "u"));
  }
  assert.doesNotMatch(
    driver,
    /visibleText\('\[data-founder-view="(?:market|risks)"\]'\)/u,
  );
});

test("Smart University driver waits for scenario recalculation before freezing the research delta", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const researchDone = driver.indexOf('"smart_university_public_research_done"');
  const deltaReady = driver.indexOf('"smart_university_research_scenario_delta_ready"');
  const deltaSnapshot = driver.indexOf("const scenarioDeltaVisible = await evaluateValue");

  assert.ok(researchDone >= 0);
  assert.ok(deltaReady > researchDone);
  assert.ok(deltaSnapshot > deltaReady);
  assert.match(driver, /data-research-metric-comparison/u);
  assert.match(driver, /aria-busy/u);
});

test("Smart University driver waits for canonical Gate 2 analysis and current GTM before scenario actions", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const researchDelta = driver.indexOf('"smart_university_research_scenario_delta_ready"');
  const gate2Ready = driver.indexOf('"smart_university_gate2_analysis_ready"', researchDelta);
  const scenarioSelection = driver.indexOf('"smart_university_base_scenario_selected"', researchDelta);

  assert.notEqual(researchDelta, -1);
  assert.ok(gate2Ready > researchDelta);
  assert.ok(scenarioSelection > gate2Ready);
  assert.match(driver, /gate2_status\s*!==\s*"completed"/u);
  assert.match(driver, /gate3_status\s*!==\s*"required"/u);
  assert.match(driver, /\/gtm/u);
});

test("Smart University driver proves Gate 3 click and report readiness before report export", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const clickHelper = driver.slice(
    driver.indexOf("async function clickSmartUniversityButton("),
    driver.indexOf("async function readSmartUniversityCaseId()"),
  );
  const acceptDecision = driver.indexOf('"smart_university_accept_final_decision"');
  const reportReady = driver.indexOf('"smart_university_gate3_report_ready"', acceptDecision);
  const gate3UiReady = driver.indexOf(
    '"smart_university_gate3_ui_ready"',
    reportReady,
  );
  const buildLaunchPack = driver.indexOf('"smart_university_build_launch_pack"', gate3UiReady);
  const launchPackVisible = driver.indexOf('"smart_university_launch_pack_visible"', buildLaunchPack);
  const reportsNav = driver.indexOf('clickSidebarView("Отчёты"', launchPackVisible);
  const generateReport = driver.indexOf('"smart_university_generate_report"', reportsNav);
  const earlyBuildLaunchPack = driver.lastIndexOf('"smart_university_build_launch_pack"', acceptDecision);

  assert.match(clickHelper, /const clicked = await evaluateValue/u);
  assert.match(clickHelper, /if \(!clicked\) throw new Error\(`browser_click_failed label=\$\{label\}`\)/u);
  assert.notEqual(acceptDecision, -1);
  assert.ok(reportReady > acceptDecision);
  assert.ok(gate3UiReady > reportReady);
  assert.equal(earlyBuildLaunchPack, -1);
  assert.ok(buildLaunchPack > gate3UiReady);
  assert.ok(launchPackVisible > buildLaunchPack);
  assert.ok(reportsNav > launchPackVisible);
  assert.ok(generateReport > reportsNav);
  assert.match(driver, /report_status === "ready"/u);
  assert.match(driver, /snapshot_hash/u);
  assert.match(driver, /snapshot_revision/u);
  assert.match(
    driver.slice(reportReady, buildLaunchPack),
    /data-founder-view="action-plan"[\s\S]*Собрать рабочий пакет/u,
  );
  assert.doesNotMatch(
    driver.slice(reportReady, buildLaunchPack),
    /clickSidebarView\("План действий"|data-founder-view="report-center"/u,
  );
});

test("Smart University driver waits for the three concrete report artifact links", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const readyLabel = driver.indexOf('"smart_university_report_formats_ready"');
  const readyBlock = driver.slice(Math.max(0, readyLabel - 1_200), readyLabel + 100);

  assert.notEqual(readyLabel, -1);
  assert.match(readyBlock, /\[data-ready="true"\]/u);
  assert.match(readyBlock, /\["pdf",\s*"html",\s*"json"\]/u);
  assert.match(readyBlock, /endsWith\("\/report\/" \+ format\)/u);
  assert.doesNotMatch(readyBlock, /!\/после анализа\/iu/u);
});

test("Smart University driver carries the visible launch-pack asset into evidence collection", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const launchPackVisible = driver.indexOf('"smart_university_launch_pack_visible"');
  const launchPackSnapshot = driver.indexOf("const launchPackEvidence = await evaluateValue", launchPackVisible);
  const reportsNav = driver.indexOf('clickSidebarView("Отчёты"', launchPackSnapshot);
  const collectEvidence = driver.indexOf("collectSmartUniversityEvidence(args)", reportsNav);
  const collectBlock = driver.slice(collectEvidence, driver.indexOf("const [analysisStatus", collectEvidence));

  assert.notEqual(launchPackVisible, -1);
  assert.ok(launchPackSnapshot > launchPackVisible);
  assert.ok(reportsNav > launchPackSnapshot);
  assert.ok(collectEvidence > reportsNav);
  assert.match(driver, /launchPackEvidence,/u);
  assert.match(driver, /launchPackEvidence\.asset_id/u);
  assert.match(driver, /launchPackEvidence\.markdown_url/u);
  assert.match(driver, /launchPackEvidence\.provenance_appendix_url/u);
  assert.match(driver, /asset_id:\s*launchPackEvidence\.asset_id/u);
  assert.match(driver, /launch_pack_link_visible:\s*Boolean\(launchPackEvidence\.link_visible && asset\.asset_id === launchPackEvidence\.asset_id\)/u);
  assert.doesNotMatch(collectBlock, /querySelectorAll\('\[data-founder-launch-pack="draft"\] a\[href\]'\)/u);
});

test("Smart University action-plan page evidence reuses the captured launch-pack readiness", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const helperStart = driver.indexOf("async function collectVisibleSmartUniversityPageEvidence(");
  const helperEnd = driver.indexOf('await clickSmartUniversityButton(\n    ["Новый анализ"', helperStart);
  const helper = driver.slice(helperStart, helperEnd);
  const launchPackSnapshot = driver.indexOf("const launchPackEvidence = await evaluateValue");
  const actionPlanEvidence = driver.indexOf("const actionPlanPageEvidence = await collectVisibleSmartUniversityPageEvidence", launchPackSnapshot);
  const actionPlanCall = driver.slice(actionPlanEvidence, driver.indexOf(");", actionPlanEvidence) + 2);

  assert.notEqual(helperStart, -1);
  assert.notEqual(helperEnd, -1);
  assert.ok(actionPlanEvidence > launchPackSnapshot);
  assert.match(actionPlanCall, /launchPackEvidence/u);
  assert.match(helper, /args\.launchPackEvidence/u);
  assert.match(helper, /draft_markdown_ready:\s*launchPackReady/u);
  assert.match(helper, /draft_provenance_ready:\s*launchPackReady/u);
  assert.doesNotMatch(helper, /const linkIsReady = \(link, suffix\)/u);
});

test("Smart University report format wait accepts duplicate PDF links only when a visible ready marker is on that link", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const readyLabel = script.indexOf('"smart_university_report_formats_ready"');
  const readyBlock = script.slice(Math.max(0, readyLabel - 1_200), readyLabel + 100);

  assert.notEqual(readyLabel, -1);
  assert.match(readyBlock, /\.some\(\(candidate\) =>/u);
  assert.match(readyBlock, /candidate\.getAttribute\("href"\)\?\.endsWith\("\/report\/" \+ format\)/u);
  assert.match(readyBlock, /candidate\.getClientRects\(\)\.length > 0/u);
  assert.match(readyBlock, /Boolean\(candidate\.querySelector\('\[data-ready="true"\]'\)\)/u);
  assert.doesNotMatch(readyBlock, /\.find\(\(candidate\)/u);
});

test("Smart University driver arms fetch diagnostics before the single-PDF owner journey", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const shellReady = driver.indexOf('"smart_university_browser_shell_ready"');
  const diagnostics = driver.indexOf(
    "armCaseCopilotFetchDiagnostics(client, sessionId)",
  );
  const openDataRoom = driver.indexOf('"smart_university_open_data_room"');

  assert.notEqual(shellReady, -1);
  assert.ok(
    diagnostics > shellReady,
    "same-process API diagnostics must be installed after the page is ready",
  );
  assert.ok(
    openDataRoom > diagnostics,
    "same-process API diagnostics must be active before the owner journey starts",
  );
});

test("Smart University driver proves approved report API readiness before waiting for report links", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const generateReport = driver.indexOf('"smart_university_generate_report"');
  const apiReady = driver.indexOf('"smart_university_report_api_ready"', generateReport);
  const linksReady = driver.indexOf('"smart_university_report_formats_ready"', apiReady);
  const apiReadyBlock = driver.slice(generateReport, linksReady);

  assert.notEqual(generateReport, -1);
  assert.ok(apiReady > generateReport);
  assert.ok(linksReady > apiReady);
  assert.match(apiReadyBlock, /\/analysis/u);
  assert.match(apiReadyBlock, /\/report/u);
  assert.match(apiReadyBlock, /gate4_status\s*!==\s*"completed"/u);
  assert.match(apiReadyBlock, /freeze_status\s*!==\s*"approved"/u);
  assert.match(apiReadyBlock, /pdf_status\s*!==\s*"ready"/u);
  assert.match(apiReadyBlock, /snapshot_hash/u);
  assert.match(apiReadyBlock, /snapshot_revision/u);
  assert.match(apiReadyBlock, /\["json_url",\s*"html_url",\s*"pdf_url"\]/u);
});

test("Smart University timeout diagnostics summarize report readiness without exposing full artifact URLs", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const diagnosticsStart = script.indexOf(
    "async function armCaseCopilotFetchDiagnostics(",
  );
  const diagnosticsEnd = script.indexOf(
    "async function collectCaseCopilotScenarioFixtureUiEvidence(",
    diagnosticsStart,
  );
  const waitStateStart = script.indexOf("async function describeBrowserWaitState(");
  const waitStateEnd = script.indexOf("async function waitForExpression(", waitStateStart);
  const diagnostics = script.slice(diagnosticsStart, diagnosticsEnd);
  const waitState = script.slice(waitStateStart, waitStateEnd);

  assert.notEqual(diagnosticsStart, -1);
  assert.notEqual(diagnosticsEnd, -1);
  assert.notEqual(waitStateStart, -1);
  assert.notEqual(waitStateEnd, -1);
  assert.match(diagnostics, /reportArtifactSuffix/u);
  assert.match(diagnostics, /report\\\\\/snapshot/u);
  assert.match(diagnostics, /freezeStatus:\s*payload\.freeze_status/u);
  assert.match(diagnostics, /pdfStatus:\s*payload\.pdf_status/u);
  assert.match(diagnostics, /jsonUrlSuffix:\s*reportArtifactSuffix\(payload\.json_url\)/u);
  assert.match(diagnostics, /htmlUrlSuffix:\s*reportArtifactSuffix\(payload\.html_url\)/u);
  assert.match(diagnostics, /pdfUrlSuffix:\s*reportArtifactSuffix\(payload\.pdf_url\)/u);
  assert.match(diagnostics, /gate4Status:\s*payload\.gate4_status/u);
  assert.match(diagnostics, /reportStatus:\s*payload\.report_status/u);
  assert.match(waitState, /hrefSuffix:\s*reportSuffix\(link\.getAttribute\("href"\)\)/u);
  assert.doesNotMatch(waitState, /href:\s*link\.getAttribute\("href"\)/u);
});

test("Smart University driver derives Gate2 receipt and post-restart UI from DOM state", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);

  assert.match(driver, /const gate2AcceptedReceiptVisible = await evaluateValue/u);
  assert.match(driver, /Ожида(?:ем|ет) материалы|waiting materials|waiting-materials/iu);
  assert.doesNotMatch(driver, /gate2_ready:\s*true/u);
  assert.match(driver, /receipt_visible:\s*args\.gate2AcceptedReceiptVisible/u);
  const gate2ClickIndex = driver.indexOf(
    'actionSelectorExpression(smartUniversityGate2Action, "click")',
  ) === -1
    ? driver.indexOf('actionSelectorExpression("gate2-approve", "click")')
    : driver.indexOf('actionSelectorExpression(smartUniversityGate2Action, "click")');
  assert.ok(
    driver.indexOf("const gate2AcceptedReceiptVisible = await evaluateValue") <
      gate2ClickIndex,
  );
  assert.match(driver, /client\.send\("Page\.(?:reload|navigate)"/u);
  assert.match(driver, /smart_university_post_restart_same_case_ui/u);
  assert.match(driver, /same_case_ui_rehydrated/u);
});

test("Smart University driver re-arms API diagnostics after post-restart reload", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const reload = driver.indexOf('client.send("Page.reload"');
  const pageReady = driver.indexOf('"smart_university_post_restart_page_ready"', reload);
  const rearmDiagnostics = driver.indexOf(
    "armCaseCopilotFetchDiagnostics(client, sessionId)",
    pageReady,
  );
  const sameCaseUi = driver.indexOf(
    '"smart_university_post_restart_same_case_ui"',
    pageReady,
  );

  assert.notEqual(reload, -1);
  assert.notEqual(pageReady, -1);
  assert.ok(
    rearmDiagnostics > pageReady,
    "Page.reload creates a fresh page context, so diagnostics must be re-installed after readiness",
  );
  assert.ok(
    sameCaseUi > rearmDiagnostics,
    "post-restart same-case UI wait must preserve fresh fetch/API diagnostics",
  );
});

test("Smart University launch-pack contract accepts explicit 2027-2031 forecast ranges", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const forecastContract = driver.match(
    /forecast_2027_2031_clear:\s*(?<pattern>\/.*?\/[a-z]*)\.test\(launchPackText\)/su,
  );

  assert.ok(forecastContract?.groups?.pattern);
  const patternLiteral = forecastContract.groups.pattern;
  const lastSlash = patternLiteral.lastIndexOf("/");
  const source = patternLiteral.slice(1, lastSlash);
  const flags = patternLiteral.slice(lastSlash + 1);
  const pattern = new RegExp(source, flags);

  assert.equal(pattern.test("Forecast guardrail: 2027-2031 revenue and EBITDA are forecasts."), true);
});

test("Smart University driver invokes the React file-change handler after CDP upload", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);

  assert.match(driver, /DOM\.setFileInputFiles/u);
  assert.match(driver, /materializeBrowserUploadPath\(fixturePath\)/u);
  assert.match(driver, /__reactProps\$/u);
  assert.match(driver, /globalThis\.__queue5ObservedIntake/u);
  assert.match(driver, /const observedIntake = globalThis\.__queue5ObservedIntake/u);
  assert.match(driver, /const fileCount = observedIntake\?\.fileCount \?\? files\.length/u);
  assert.match(driver, /reactOnChange\(\{\s*currentTarget:\s*input,\s*target:\s*input\s*\}\)/u);
  assert.ok(
    driver.indexOf("browserUpload.cleanup()") >
      driver.indexOf('"smart_university_gate2_ready"'),
  );
  assert.doesNotMatch(
    driver,
    /smart_university_pdf_receipt_visible[\s\S]*input\?\.files\?\.length === 1/u,
  );
});

test("Smart University driver derives public sources from rendered DOM", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);

  assert.match(driver, /renderedSourceTexts/u);
  assert.match(driver, /querySelectorAll\('\[data-research-source\]/u);
  assert.match(driver, /rendered_change_count/u);
});

test("Smart University driver records one unknown and waits for UI idle before research", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const unknown = driver.indexOf('clickCopilotTab(caseId, "Не знаю")');
  const unknownCount = driver.indexOf("waitForUnknownAnswerCount", unknown);
  const uiIdle = driver.indexOf(
    '"smart_university_unknown_ui_idle"',
    unknownCount,
  );
  const publicAvailable = driver.indexOf(
    "waitForSmartUniversityResearchTab",
    uiIdle,
  );
  const publicTabClick = driver.indexOf(
    'clickCopilotTab(caseId, "Публичный поиск")',
    publicAvailable,
  );
  const acquisitionMode = driver.indexOf(
    "waitForSmartUniversityLiveAcquisitionMode",
    publicTabClick,
  );
  const researchTab = driver.indexOf(
    '[data-case-question-research-mode="live_public_research"]',
    acquisitionMode,
  );
  const consent = driver.indexOf('[data-case-question-consent="public_research"]', researchTab);
  const submit = driver.indexOf('[data-case-question-submit="public_research"]', consent);

  assert.match(script, /SMART_UNIVERSITY_ONLINE_RESEARCH_TAB_LABELS[\s\S]*"Онлайн-ресерч"/u);
  assert.match(script, /SMART_UNIVERSITY_OFFLINE_RESEARCH_TAB_LABELS[\s\S]*"Офлайн-демо"/u);
  assert.match(script, /SMART_UNIVERSITY_UNAVAILABLE_RESEARCH_TAB_LABELS[\s\S]*"Без live-провайдера"/u);
  assert.notEqual(unknown, -1);
  assert.ok(unknown < unknownCount);
  assert.ok(unknownCount < uiIdle);
  assert.ok(uiIdle < publicAvailable);
  assert.ok(publicAvailable < publicTabClick);
  assert.ok(publicTabClick < acquisitionMode);
  assert.ok(publicAvailable < researchTab);
  assert.ok(researchTab < consent);
  assert.ok(consent < submit);
  assert.match(driver, /smart_university_public_research_tab_unavailable/u);
  assert.match(driver, /data-case-question-research-mode="live_public_research"/u);
  assert.match(driver, /readCopilotTabLabels/u);
  assert.match(driver, /panel\.getAttribute\("aria-busy"\) !== "true"/u);
  assert.doesNotMatch(driver, /Разрешаю публичный поиск/u);
});

test("Smart University live research tab selector targets the public-search answer tab", () => {
  assert.equal(
    selectSmartUniversityResearchTabLabel(["Ответ", "Документ", "Не знаю"], {
      requireLivePublicResearch: true,
    }),
    null,
  );
  assert.equal(
    selectSmartUniversityResearchTabLabel(["Ответ", "Документ", "Публичный поиск", "Не знаю"], {
      requireLivePublicResearch: true,
    }),
    "Публичный поиск",
  );
});

test("Smart University live acquisition selector requires an available online research control", () => {
  assert.equal(
    selectSmartUniversityLiveAcquisitionMode([
      {
        disabled: false,
        label: "Онлайн-ресерч",
        mode: "live_public_research",
        visible: true,
      },
      {
        disabled: false,
        label: "Офлайн-демо",
        mode: "deterministic_offline_fixture",
        visible: true,
      },
    ]),
    "live_public_research",
  );
  assert.equal(selectSmartUniversityLiveAcquisitionMode([]), null);
  assert.throws(
    () =>
      selectSmartUniversityLiveAcquisitionMode([
        {
          disabled: false,
          label: "Офлайн-демо",
          mode: "deterministic_offline_fixture",
          visible: true,
        },
      ]),
    /smart_university_live_research_mode_unavailable/u,
  );
  assert.throws(
    () =>
      selectSmartUniversityLiveAcquisitionMode([
        {
          disabled: true,
          label: "Онлайн-ресерч",
          mode: "live_public_research",
          visible: true,
        },
        {
          disabled: false,
          label: "Офлайн-демо",
          mode: "deterministic_offline_fixture",
          visible: true,
        },
      ]),
    /smart_university_live_research_mode_unavailable/u,
  );
});

test("Smart University driver never treats an absent public research tab as success", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const unavailable = driver.indexOf(
    "smart_university_public_research_tab_unavailable",
  );
  const consent = driver.indexOf('[data-case-question-consent="public_research"]');

  assert.notEqual(unavailable, -1);
  assert.ok(unavailable < consent);
  assert.doesNotMatch(
    driver,
    /public_research:\s*\{\s*status:\s*"completed"[\s\S]*smart_university_public_research_unavailable/u,
  );
});

test("Smart University driver applies research consent through a trusted pointer click", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);
  const helper = driver.indexOf(
    "async function activateControlledCheckboxWithTrustedPointer(",
  );
  const helperEnd = driver.indexOf(
    "async function clickCopilotPanelButton(",
    helper,
  );
  const helperSource = driver.slice(helper, helperEnd);
  const bringToFront = helperSource.indexOf('"Page.bringToFront"');
  const focus = helperSource.indexOf("checkbox.focus({ preventScroll: true })");
  const focusProof = helperSource.indexOf("const focused = document.activeElement === checkbox", focus);
  const rect = helperSource.indexOf("checkbox.getBoundingClientRect()", focusProof);
  const mouseMoved = helperSource.indexOf('type: "mouseMoved"', rect);
  const mousePressed = helperSource.indexOf('type: "mousePressed"', mouseMoved);
  const mouseReleased = helperSource.indexOf('type: "mouseReleased"', mousePressed);
  const researchTab = driver.indexOf(
    "clickCopilotTab(caseId, publicResearchTabLabel)",
  );
  const consentClick = driver.indexOf(
    "activateControlledCheckboxWithTrustedPointer(",
    researchTab,
  );
  const consentApplied = driver.indexOf(
    '"smart_university_public_research_consent_applied"',
    consentClick,
  );
  const submit = driver.indexOf(
    '[data-case-question-submit="public_research"]',
    consentApplied,
  );

  assert.notEqual(helper, -1);
  assert.notEqual(helperEnd, -1);
  assert.ok(bringToFront < focus);
  assert.ok(focus < focusProof);
  assert.ok(focusProof < rect);
  assert.ok(rect < mouseMoved);
  assert.ok(mouseMoved < mousePressed);
  assert.ok(mousePressed < mouseReleased);
  assert.match(helperSource, /"Input\.dispatchMouseEvent"/u);
  assert.match(helperSource, /button:\s*"left"/u);
  assert.match(helperSource, /clickCount:\s*1/u);
  assert.ok(researchTab < consentClick);
  assert.ok(consentClick < consentApplied);
  assert.ok(consentApplied < submit);
  assert.doesNotMatch(helperSource, /smart_university_consent_diagnostic/u);
  assert.doesNotMatch(helperSource, /data-case-question-consent-change-count/u);
  assert.doesNotMatch(helperSource, /data-case-question-consent-last-event/u);
  assert.doesNotMatch(helperSource, /data-case-question-consent-last-scope/u);
  assert.doesNotMatch(helperSource, /__reactProps\$/u);
  assert.doesNotMatch(helperSource, /Object\.getOwnPropertyDescriptor/u);
  assert.doesNotMatch(driver, /if \(!checkbox\.checked\) checkbox\.click\(\)/u);
});

test("browser DevTools startup retries transient Windows file locks", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const helperStart = script.indexOf("async function waitForDevTools(");
  const helperEnd = script.indexOf("async function connect(", helperStart);
  const helperSource = script.slice(helperStart, helperEnd);

  assert.notEqual(helperStart, -1);
  assert.notEqual(helperEnd, -1);
  assert.match(helperSource, /try \{[\s\S]*readFileSync\(activePortFile, "utf8"\)/u);
  assert.match(helperSource, /\["EBUSY", "ENOENT"\]\.includes\(error\?\.code\)/u);
  assert.match(helperSource, /throw error;/u);
  assert.ok(helperSource.indexOf("browserProcess.exitCode") > helperSource.indexOf("catch"));
});

test("Smart University driver never embeds failed API response bodies in diagnostics", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const driverStart = script.indexOf(
    "async function driveSmartUniversitySinglePdfJourney(",
  );
  const driverEnd = script.indexOf(
    "async function writeCaseCopilotBrowserEvidence(",
    driverStart,
  );
  const driver = script.slice(driverStart, driverEnd);

  assert.doesNotMatch(
    driver,
    /smart_university_(?:post_restart_)?request_failed[^\n]*body=/u,
  );
});

test("Case Copilot request failures never append raw response bodies to thrown errors", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");

  assert.doesNotMatch(
    script,
    /case_copilot_(?:browser|post_restart)_request_failed[^\n]*body=\$\{await response\.text\(\)\}/u,
  );
});

test("Case Copilot fetch diagnostics never persist raw failed response bodies", () => {
  const script = readFileSync("scripts/capture_founder_screenshots.mjs", "utf8");
  const helperStart = script.indexOf("async function armCaseCopilotFetchDiagnostics(");
  const helperEnd = script.indexOf(
    "async function collectCaseCopilotScenarioFixtureUiEvidence(",
    helperStart,
  );
  const helper = script.slice(helperStart, helperEnd);
  const failedResponseStart = helper.indexOf('if (url.includes("/api/") && !response.ok)');
  const failedResponseEnd = helper.indexOf("return response;", failedResponseStart);
  const failedResponseBranch = helper.slice(failedResponseStart, failedResponseEnd);

  assert.notEqual(helperStart, -1);
  assert.notEqual(helperEnd, -1);
  assert.notEqual(failedResponseStart, -1);
  assert.notEqual(failedResponseEnd, -1);
  assert.doesNotMatch(failedResponseBranch, /body:\s*body\.slice/u);
  assert.doesNotMatch(failedResponseBranch, /response\.clone\(\)\.text\(\)/u);
  assert.doesNotMatch(helper, /body:\s*String\(error\?\./u);
  assert.match(helper, /body:\s*""/u);
});
