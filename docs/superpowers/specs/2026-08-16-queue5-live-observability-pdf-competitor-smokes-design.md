# Queue 5 Live Observability, PDF Journey, and Competitor Smoke Design

**Date:** 2026-08-16
**Status:** approved by the owner's 2026-08-16 course correction
**Scope:** Queue 5 Demo Freeze only; Queue 1-4 and R11/R12 are out of scope

## 1. Outcome

Queue 5 must retain the deterministic frozen/offline Sellable Demo packet and add three separate, reviewer-verifiable proof lanes:

1. one sanitized LangSmith trace produced by the real startup LangGraph workflow;
2. one pure-PDF same-case desktop/mobile/browser/API journey using the tracked frozen fixture;
3. one optional, bounded OpenAI competitor-synthesis smoke when a credential is present.

These lanes must never be folded into canonical Gate D/E semantics. Frozen packet status, LangSmith trace status, and OpenAI smoke status are separate evidence objects with separate hashes and lifecycle states.

## 2. Non-negotiable boundaries

- Gate B/C/D-A/D-B/E remain deterministic, tracing-disabled, offline, and network-independent.
- The LangSmith credential is inspected only as a boolean. Its value is never logged, persisted, emitted, or displayed.
- The live LangSmith call is exactly one bounded synthetic/frozen smoke after the full offline suite is green.
- No automatic LangGraph/LangChain tracing callback may receive startup graph state, PDF bytes, parsed text, prompts, or outputs.
- Local JSONL audit remains the source of truth. Export success or failure cannot change the workflow result.
- The OpenAI competitor smoke is at most one request, costs at most USD 0.25, runs only after Gate 2 approval, and performs no live web research.
- No SEC, Yahoo Finance, GDELT, news, or web call is permitted in Queue 5.
- Generated PDFs, screenshots, uploads, runtime databases, trace caches, and smoke outputs remain untracked runtime evidence.
- Existing Queue 5 RED-WIP and protected probe/runtime files remain untouched and unstaged.

## 3. Credential states

Credential detection is fail-closed and value-blind.

| Proof lane | Credential absent | Credential present |
| --- | --- | --- |
| Frozen packet | unaffected | unaffected |
| LangSmith live trace | `blocked_missing_credential` and sole Queue 5 readiness blocker | one bounded live smoke may run after offline GREEN |
| OpenAI competitor smoke | `skipped_missing_credential` and not a frozen-demo blocker | one bounded request may run after LangSmith and offline GREEN |

At design time both `LANGSMITH_API_KEY` and `OPENAI_API_KEY` are absent. This observation contains no secret value and may change before final verification.

## 4. LangSmith integration

### 4.1 Chosen approach

Instrument the existing startup graph node lifecycle rather than enabling automatic LangGraph callbacks.

`workflows/startup/graph.py::_record_node` already runs for actual startup LangGraph nodes and already emits compact node attributes. It records durable local audit before invoking the tracer. A best-effort composite tracer will keep the existing metric tracer and optionally add a LangSmith node tracer. The LangSmith tracer will:

- be inert when tracing is disabled;
- never construct a LangSmith client when disabled or when the credential is absent;
- sanitize an explicit metadata allowlist before any SDK call;
- emit an empty input and empty output for every remote run;
- group node runs below one case-level root run;
- close the root when the report node finishes or the workflow reaches a terminal failure;
- catch SDK construction, create, update, and flush failures;
- append a safe local exporter-health marker without raising into the workflow.

This is real workflow tracing because export is called from the graph's production node boundary during a real case, not from a unit-test-only wrapper. It remains privacy-safe because raw LangGraph state is never passed to LangSmith.

### 4.2 Rejected approaches

1. **Set `LANGSMITH_TRACING=true` globally and pass a LangGraph callback.** Rejected because automatic tracing captures inputs, outputs, and metadata surfaces that contain confidential startup state.
2. **Trace only a standalone test function.** Rejected because it does not prove integration with the startup LangGraph workflow.
3. **Make LangSmith export part of Gate D/E.** Rejected because network availability would corrupt deterministic frozen acceptance.

### 4.3 Safe telemetry contract

Only primitive values from an explicit allowlist may be exported:

- identity: `case_id`, `run_id`, `correlation_id`;
- workflow: `workflow_type`, `node_name`, `agent_role`, `schema_version`;
- outcome: `status`, `duration_ms`, `retry_count`, `attempt`, `error_code`, `fallback_used`;
- gate: `gate`, `gate_status`;
- usage: `input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`;
- lineage: `report_id`, `report_revision`, `report_checksum`;
- checkpoint: `checkpoint_id`, `checkpoint_hash`;
- provider: a fixed safe provider identifier such as `langsmith`.

The following are always absent from remote runs and live evidence:

- PDF bytes or parsed document text;
- upload filename or any local/absolute path;
- prompts, completions, chain-of-thought, graph state, tool arguments, or payloads;
- company/person names, email, phone, PII, API keys, authorization data, or environment dumps;
- exception messages or stack traces; only a bounded error code is allowed.

The sanitizer is applied both to metadata supplied by the graph and to the final SDK client hook. Disallowed keys are dropped at the client boundary and fail focused privacy tests at the stricter producer boundary.

### 4.4 Exporter health and local truth

Each traced run may produce one local health record with status:

- `disabled`: tracing was explicitly disabled; no external client/export occurred;
- `blocked_missing_credential`: tracing was requested but no credential was available;
- `healthy`: remote node/root writes and final flush succeeded;
- `degraded`: the exporter failed; the workflow and local audit continued.

Admin derives LangSmith health from provider-specific local audit markers. Existing OTel exporter health remains a separate DTO/row and is not overloaded with LangSmith status. A degraded LangSmith marker contains only a stable error code and `fallback_used=local_audit`; it contains no exception text. Local node timeline, Gate decisions, usage, and report lineage remain readable regardless of external health.

### 4.5 Live trace evidence

The one live smoke runs the tracked frozen startup case through the real deterministic startup composer with LangSmith export explicitly enabled for that smoke only. It must produce a side-evidence object that records:

- schema/version and timestamp;
- status and credential-present boolean;
- case/run/trace/root identifiers;
- node span count and required node coverage;
- exported metadata key inventory;
- empty-input/empty-output proof;
- local audit count and Admin exporter health;
- report lineage identity;
- privacy scan result;
- SDK/project identifiers only when they pass the same sanitizer;
- a stable semantic evidence hash that excludes timestamps and remote timing.

No trace URL containing tenant information is required in committed documentation. Runtime evidence may be shown locally during defense.

## 5. Pure-PDF same-case journey

### 5.1 Fixture

Use exactly the tracked frozen fixture:

`tests/fixtures/startup_synthetic_v1/cases/saas/pitch.pdf`

The smoke uploads only this PDF. It supplies no founder prompt, industry selection, CSV, XLSX, or live source.

The existing CSV Queue 4 smoke remains the default for compatibility. PDF mode is an explicit Queue 5 parameter and must not replace or rewrite the proven Queue 4 path.

### 5.2 Required journey

One `case_id` must bind all of the following:

1. PDF upload and MIME/parser proof;
2. primary profile;
3. Gate 2 approval;
4. deep analysis;
5. metrics and readiness;
6. competitors and TAM/SAM/SOM;
7. contradiction summary and diligence questions;
8. GTM and action plan;
9. Gate 4 approval;
10. JSON, HTML, and PDF report artifacts;
11. Admin trace with the same `case_id` and run lineage.

The same browser session drives desktop 1440x1000 and mobile 390x844 views. Browser evidence fails closed on case mismatch, missing PDF proof, horizontal overflow, missing required panels/sections, missing report lineage, or an unsafe trace field.

### 5.3 Evidence privacy

Browser/API evidence may record `application/pdf`, byte count, and SHA-256. It must not persist the upload filename or absolute/relative local path. The fixture path belongs only in the committed orchestration/test configuration, not runtime telemetry.

The Admin same-case assertion uses the same sanitized local trace query service that powers the Admin UI. It records case/run identity, node coverage, exporter health, Gate/report lineage, and privacy validation. It never embeds the PDF or raw audit lines.

## 6. OpenAI competitor-synthesis smoke

### 6.1 Placement

The smoke is a Queue 5 side evaluator, not a canonical startup graph node and not part of Gate D/E. It runs only after an existing frozen case has a persisted Gate 2 approval.

### 6.2 Input contract

The single model call receives only:

- a bounded, sanitized `StartupProfile` projection;
- existing frozen competitor evidence summaries;
- existing frozen source-summary identifiers/hashes;
- a fixed schema/instruction version.

It never receives PDF bytes, parsed text, filenames, paths, prompts from the founder, raw source documents, or live-retrieved content.

### 6.3 Output contract

Structured output must cover:

- `direct`, `indirect`, `substitute`, `do_nothing`, and `potential_entrant` competitor classes;
- ICP overlap;
- differentiation;
- risk;
- confidence;
- evidence references;
- unknowns.

The result is labeled `live_inference`, never `live_web_research`. Evidence identifiers must bind only to the supplied frozen summaries.

### 6.4 Guards and fallback

- exactly one SDK request per smoke execution;
- `max_retries=0`;
- bounded timeout;
- reserved and worst-case cost both at or below USD 0.25;
- explicit Gate 2 approval check before request construction;
- single-call guard remains closed after any attempt, including timeout;
- parse/timeout/provider failure returns a structured partial fallback and never changes the canonical report;
- absence of `OPENAI_API_KEY` returns `skipped_missing_credential` without client construction.

Side evidence records status, call count, budget bounds, Gate 2 lineage, input/output schema versions, evidence identifiers/hashes, inference label, fallback/error code, privacy result, and its own semantic hash.

## 7. Separate evidence and packet binding

The canonical Queue 5 packet remains `sellable_demo_freeze_packet@1`. It may bind side-evidence files by path/hash/status, but its canonical frozen packet hash must not depend on volatile remote identifiers or timings.

Required status namespaces:

- `frozen_demo.status`: deterministic packet and Gates only;
- `langsmith_trace.status`: live observability proof only;
- `openai_competitor_smoke.status`: optional live inference only;
- `pdf_journey.status`: same-case browser/API/Admin proof only.

A final verification summary binds all four namespaces, the failure matrix, demo script, capstone map, and fresh command evidence. Queue 5 may be declared ready only when frozen and PDF lanes pass, LangSmith is `healthy`, and the OpenAI lane is either `passed` or the explicitly permitted `skipped_missing_credential`.

## 8. TDD and integration order

1. Write failing LangSmith workflow/privacy/outage/Admin-health tests.
2. Implement the minimum tracer, sanitizer extensions, composer wiring, and live evidence runner.
3. Prove offline tracing-disabled behavior before any live attempt.
4. Write failing PDF orchestration/evidence/same-case Admin tests.
5. Implement PDF mode and validate-only evidence.
6. Write failing OpenAI single-call/Gate 2/privacy/budget/fallback tests.
7. Implement the optional smoke and missing-credential evidence.
8. Bind separate side evidence into Queue 5 orchestration and documentation.
9. Run the complete offline verification boundary and independent reviews.
10. Run live LangSmith/OpenAI smokes only when credentials are present and all prior checks are green.

## 9. Completion boundary

Queue 5 is not complete until fresh Gate B/C/D-A/D-B/E, backend pytest, Ruff, strict mypy, frontend test/typecheck/lint/build, pure-PDF desktop/mobile browser/API/Admin smoke, privacy/determinism/restart/report-lineage checks, failure matrix, demo script, capstone map, and independent reviews pass.

With no LangSmith credential, all implementation and offline verification continue, but final Queue 5 readiness remains blocked solely on the one real sanitized LangSmith trace. The absent OpenAI credential is reported separately as an allowed optional-smoke skip.
