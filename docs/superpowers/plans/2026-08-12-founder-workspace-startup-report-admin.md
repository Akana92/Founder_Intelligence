# Founder Workspace Startup Report + Admin Console Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task by task. Keep changes review-sized and preserve shared seams.

**Goal:** собрать profile B, готовый к показу инвесторам: один универсальный upload-путь без demo/vertical selector, один кейс с `primary analysis -> deep analysis`, canonical startup report snapshot (`JSON -> HTML -> PDF`), Gate 4 как единственный выключатель final PDF, отдельный Founder Workspace в браузере и отдельную Streamlit Admin Console для tracing/privacy/evals/cost/latency. Переход к profile C должен остаться возможным без переписывания core-анализа и `/api/v1` контрактов.

**Architecture:** canonical core живёт в domain/application/workflows/reporting слоях. Founder Workspace — отдельный Next.js browser surface, который читает только same-origin proxy routes, а те уже проксируют в FastAPI `/api/v1`. Founder UI не считает метрики, не формирует findings и не показывает сырой tracing. Streamlit остаётся отдельной Admin Console для technical observability, privacy, evals, source health, cost/latency и report integrity. Canonical startup report snapshot — единственный source of truth для JSON/HTML/PDF, а `ReportService(snapshot, output_dir)` остаётся render orchestration boundary.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, uv, LangGraph, SQLite, Jinja2, WeasyPrint, OpenTelemetry, sanitized LangSmith adapter, Next.js App Router, React 19, TypeScript, CSS tokens, Node test runner, ESLint, `ruff`, `mypy`, `pytest`.

## Global Constraints

- Profile B only. No demo project selector, no industry selector, no “choose a research mode” screen.
- Universal upload must accept arbitrary startup documents and route them into the same case flow.
- The same case must support `primary analysis -> deep analysis` without forcing a second upload.
- Startup capabilities that are not ready yet must be truthfully marked `planned` or `unavailable`; never shown as completed real work.
- Final PDF is allowed only after Gate 4 approval/freeze. Draft JSON/HTML may exist before Gate 4.
- Founder Workspace must not expose raw prompts, traces, secrets, PII, filenames, or internal model settings.
- Admin Console must be structurally separate and the only surface for tracing/privacy/evals/cost/latency.
- Preserve C seams: additive `/api/v1` changes only, nullable identity/workspace seams stay nullable, no auth/tenancy/billing hard-coding in B.
- No placeholders, no `TODO`, no synthetic fake scores presented as real evidence.
- Every task ends with tests and a scoped commit message.

## Canonical v1 schemas and state machine

### Product contract

- `founder_capabilities.v1` remains the versioned product contract.
- `delivery_profile = sales_ready_hybrid`
- surfaces stay `founder_workspace=separate_web`, `admin_console=streamlit`
- `user_selectable_modes = ()`
- `research_policy = guarded_live_with_cached_fallback`
- capability lifecycle states are truthful: `available`, `planned`, `unavailable`

### Startup case and report schemas

- `StartupCaseCreateRequest`
  - `fixture_mode: "live" | "deterministic_offline"`
  - `auto_start: bool = true`
  - optional founder-supplied metadata only (`company_name`, `website`, `as_of`, `document_class_hint`)
- `StartupCaseCreateResponse`
  - `case_id`
  - `case_status`
  - `analysis_status`
  - `provider_status`
  - `auto_start_triggered`
- `StartupDocumentUploadRequest` via `multipart/form-data`
  - `files[]`
  - `auto_start`
  - optional metadata fields
- `StartupDocumentUploadResponse`
  - `case_id`
  - `accepted_document_ids`
  - `auto_start_triggered`
  - `next_poll_after_ms`
- `StartupCaseStatusResponse`
  - `case_status`
  - `analysis_status`
  - `gate2_status`
  - `gate3_status`
  - `gate4_status`
  - `report_status`
  - `snapshot_hash`
  - `snapshot_revision`
- `Gate2PreviewResponse`
  - disclosure preview summary
  - `resume_token`
  - `provider_mode`
- `Gate2DecisionRequest`
  - `decision: "approved" | "denied"`
  - optional reason
- `Gate3DecisionRequest`
  - `decision: "continue"`
  - `exclusions: [{ evidence_fact_id, reason? }]`
- `Gate4DecisionRequest`
  - `decision: "approved" | "rejected"`
  - `snapshot_hash`
  - `snapshot_revision`
  - optional reason
- `StartupReportSnapshotResponse`
  - canonical snapshot id/hash/revision
  - JSON/HTML/PDF URLs
  - `freeze_status`
  - `pdf_status`

### State machine

| Stage | Event | Next state | Notes |
| --- | --- | --- | --- |
| Case created | `POST /api/v1/startup/cases` | `awaiting_upload` | Creates a case shell only. |
| Multipart upload accepted | `POST /documents` | `primary_queued` or `primary_running` | `auto_start=true` must be explicit in response; default is on. |
| Safe ingest/parse/classify complete | workflow resume | `gate2_preview_ready` | Founder sees disclosure preview; primary analysis has not started yet. |
| Gate 2 approved | decision `approved` | `primary_running` | Live/provider-dependent primary analysis starts only after approval. |
| Gate 2 denied | decision `denied` | `primary_deterministic_running` | Resume on deterministic local branch where supported; explicit policy blocks remain visible. |
| Primary analysis finished | workflow resume | `deep_running` | Deep analysis starts after primary analysis finishes. |
| Deep analysis complete | workflow resume | `gate3_review_required` | Exclusions UI becomes active. |
| Gate 3 exclusions submitted | decision with exclusions | `gate3_recompute_running` | Invalidates dependent evidence/findings/contradictions. |
| Recompute complete | workflow resume | `draft_ready` | Canonical JSON/HTML snapshot exists. |
| Gate 4 approved | decision `approved` + matching hash/revision | `gate4_approved` -> `final_pdf_ready` | Final PDF allowed only here. |
| Gate 4 rejected | decision `rejected` | `gate4_rejected` | Draft JSON/HTML preserved; PDF blocked. |

### Report error semantics

- `GET report.json` returns `200` whenever a draft/frozen snapshot exists; otherwise `404 report_not_ready`.
- `GET report.html` returns `200` with the same canonical snapshot; otherwise `404 report_not_ready`.
- `GET report.pdf` returns `200` only when Gate 4 is approved and snapshot hash/revision still match.
- `GET report.pdf` returns `409 gate_4_freeze_required` when Gate 4 is missing/rejected/mismatched.
- `GET report.pdf` returns `503 pdf_renderer_unavailable` only when the rendering backend fails, not when approval is missing.

### Provider availability semantics

- `provider_status = unavailable` means the live upstream/provider or its contract is unavailable.
- `provider_status = deterministic_offline_fixture` means the explicit demo/fixture mode is active; that is not an error.
- UI must show these states differently.

---

## Task 1: Build the same-origin proxy layer and exact startup API v1 surface

**Blocks:** Tasks 3–5.

**Files**

- Modify: `src/due_diligence_agent/presentation/api/app.py`
- Modify: `src/due_diligence_agent/presentation/api/context.py`
- Modify: `src/due_diligence_agent/presentation/api/dependencies.py`
- Create: `src/due_diligence_agent/presentation/api/routers/startup.py`
- Modify: `src/due_diligence_agent/presentation/api/routers/system.py`
- Modify: `src/due_diligence_agent/application/product/capabilities.py`
- Modify: `frontend/founder/package.json`
- Modify: `frontend/founder/lib/api.ts`
- Create: `frontend/founder/lib/server-proxy.ts`
- Modify: `frontend/founder/app/api/capabilities/route.ts`
- Create: `frontend/founder/app/api/startup/cases/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/documents/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/analysis/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/gate2/preview/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/gate2/decision/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/gate3/decision/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/gate4/decision/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/report/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/report/html/route.ts`
- Create: `frontend/founder/app/api/startup/cases/[caseId]/report/pdf/route.ts`
- Test: `tests/api/test_system_api.py`
- Test: `tests/api/test_request_context.py`
- Test: `tests/api/test_startup_api.py`
- Test: `tests/unit/application/product/test_capabilities.py`
- Test: `frontend/founder/lib/contracts.test.ts`
- Test: `frontend/founder/lib/api.test.ts`
- Test: `frontend/founder/app/api/startup/routes.test.ts`

**Interfaces**

- `GET /health/live`
- `GET /api/v1/product/capabilities`
- `POST /api/v1/startup/cases`
- `GET /api/v1/startup/cases/{case_id}`
- `POST /api/v1/startup/cases/{case_id}/documents`
- `GET /api/v1/startup/cases/{case_id}/analysis`
- `GET /api/v1/startup/cases/{case_id}/gate2/preview`
- `POST /api/v1/startup/cases/{case_id}/gate2/decision`
- `POST /api/v1/startup/cases/{case_id}/gate3/decision`
- `POST /api/v1/startup/cases/{case_id}/gate4/decision`
- `GET /api/v1/startup/cases/{case_id}/report`
- `GET /api/v1/startup/cases/{case_id}/report/html`
- `GET /api/v1/startup/cases/{case_id}/report/pdf`

**Checklist**

- [ ] Write failing tests for the product contract, startup create/upload/status routes, gate decision routes, report error semantics, and request-context safety.
- [ ] Keep browser traffic same-origin: the frontend must call Next route handlers, and only those handlers may call FastAPI upstream.
- [ ] Keep `RequestContext` C-ready but B-safe: nullable `actor_id` and `workspace_id`, normalized request IDs, no trust in arbitrary identity headers.
- [ ] Make multipart upload explicit: `auto_start=true|false` must be visible in request/response semantics and in UI state.
- [ ] Add explicit live/provider vs deterministic fixture semantics to the contract and UI payloads.
- [ ] Keep the capability contract truthful about `planned` vs `available` lifecycle states.

**Verification**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev pytest tests/api/test_system_api.py tests/api/test_request_context.py tests/api/test_startup_api.py tests/unit/application/product/test_capabilities.py -q
npm --prefix frontend/founder run test
npm --prefix frontend/founder run lint
npm --prefix frontend/founder run typecheck
```

**Commit**

```powershell
git add src/due_diligence_agent/presentation/api src/due_diligence_agent/application/product tests/api tests/unit/application/product frontend/founder/package.json frontend/founder/lib frontend/founder/app/api
git commit -m "feat: expose startup API v1 through same-origin proxy"
```

---

## Task 2: Separate snapshot building from render orchestration and freeze Gate 4 semantics

**Depends on:** Task 1.

**Files**

- Modify: `src/due_diligence_agent/application/services/report_service.py`
- Create: `src/due_diligence_agent/application/services/startup_report_service.py`
- Modify: `src/due_diligence_agent/workflows/startup/graph.py`
- Modify: `src/due_diligence_agent/workflows/startup/nodes/report.py`
- Modify: `src/due_diligence_agent/domain/reports/models.py`
- Modify: `src/due_diligence_agent/adapters/reports/html_renderer.py`
- Create: `src/due_diligence_agent/adapters/reports/templates/startup_report.html.j2`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Test: `tests/graph/test_startup_workflow.py`
- Test: `tests/e2e/test_startup_report.py`
- Test: `tests/unit/reporting/test_startup_report_snapshot.py`
- Test: `tests/unit/reporting/test_report_freeze.py`
- Test: `tests/unit/reporting/test_report_service_orchestration.py`

**Boundary decision**

- `StartupReportSnapshotBuilder` builds the canonical startup `ReportSnapshot`.
- `StartupReportRepository` / query adapter stores and reads snapshot + hash + revision + approval state.
- `ReportService` remains render orchestration only:
  - `render_draft(snapshot, output_dir)`
  - `render_final_pdf(snapshot, output_dir)`
  - `render_approved(snapshot_id, output_dir)` can stay as an approved-snapshot convenience wrapper
- Workflow nodes may ask for build/save/query/render services, but the render service must not own case state or gate logic.

**Interfaces**

- `StartupReportSnapshotResponse` must include snapshot id/hash/revision.
- `render_draft(snapshot, output_dir)` emits canonical JSON + HTML derived from the same snapshot.
- `render_final_pdf(snapshot, output_dir)` stays blocked until Gate 4 approval/freeze succeeds and hash/revision still match.
- Startup sections must cover, at minimum: business idea summary, problem/solution, market size, competitors, moat, GTM, metrics, financial assumptions, risks, evidence gaps, diligence questions, and action plan.

**Checklist**

- [ ] Write failing tests that prove canonical JSON/HTML/PDF derivation and Gate 4 blocking semantics.
- [ ] Extend the report model additively so public report contracts stay intact.
- [ ] Store snapshot hash and revision in the report boundary, not in the frontend.
- [ ] Keep Gate 4 `approved` vs `rejected` exact and echo snapshot hash/revision in decisions and responses.
- [ ] Ensure `report.pdf` errors distinguish approval failure from renderer failure.

**Verification**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev pytest tests/graph/test_startup_workflow.py tests/e2e/test_startup_report.py tests/unit/reporting/test_startup_report_snapshot.py tests/unit/reporting/test_report_freeze.py tests/unit/reporting/test_report_service_orchestration.py -q
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev ruff check src/due_diligence_agent/application/services src/due_diligence_agent/workflows/startup src/due_diligence_agent/domain/reports src/due_diligence_agent/adapters/reports tests/graph tests/e2e tests/unit/reporting
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev mypy src/due_diligence_agent/application/services src/due_diligence_agent/workflows/startup src/due_diligence_agent/domain/reports
```

**Commit**

```powershell
git add src/due_diligence_agent/application/services src/due_diligence_agent/workflows/startup src/due_diligence_agent/domain/reports src/due_diligence_agent/adapters/reports src/due_diligence_agent/bootstrap/container.py tests/graph tests/e2e tests/unit/reporting
git commit -m "feat: separate startup snapshot building from report rendering"
```

---

## Task 3: Build the Founder Workspace browser surface around the startup case state machine

**Depends on:** Tasks 1–2.

**Files**

- Modify: `frontend/founder/app/page.tsx`
- Modify: `frontend/founder/app/layout.tsx`
- Modify: `frontend/founder/app/globals.css`
- Modify: `frontend/founder/components/founder-shell.tsx`
- Modify: `frontend/founder/components/upload-entry.tsx`
- Modify: `frontend/founder/components/capability-status.tsx`
- Modify: `frontend/founder/components/public-comparables-panel.tsx`
- Modify: `frontend/founder/app/admin/page.tsx`
- Modify: `frontend/founder/app/comparables/page.tsx`
- Modify: `frontend/founder/lib/api.ts`
- Modify: `frontend/founder/lib/server-proxy.ts`
- Modify: `frontend/founder/lib/contracts.ts`
- Test: `frontend/founder/lib/navigation.test.ts`
- Test: `frontend/founder/lib/upload.test.ts`
- Test: `frontend/founder/lib/contracts.test.ts`
- Test: `frontend/founder/components/founder-shell.test.ts`

**UI contract**

- Single upload CTA.
- One case view with primary analysis and deep analysis as two connected horizons in the same case.
- Evidence spine, case brief, report state, and next action surface.
- Secondary comparables route only; it cannot become the main user flow.
- Admin bridge remains a bridge, not the actual admin console.
- Polling/backoff is explicit: UI polls case status from the same-origin proxy with exponential backoff and aborts on terminal states.

**UI state mapping**

- `idle`
- `uploading`
- `primary_queued`
- `primary_intake`
- `document_ready`
- `gate2_preview_ready`
- `gate2_approved`
- `gate2_denied`
- `primary_running`
- `primary_deterministic_running`
- `deep_running`
- `gate3_review_required`
- `gate4_pending`
- `gate4_approved`
- `gate4_rejected`
- `report_draft_ready`
- `report_pdf_ready`
- `provider_unavailable`
- `offline_fixture_active`
- `error`

**Checklist**

- [ ] Remove any demo/project/vertical selector behavior from the founder flow.
- [ ] Turn `UploadEntry` into a real founder-facing document intake shell with clear empty/loading/error states and no technical jargon.
- [ ] Map multipart upload -> auto-start -> safe ingest/parse/classify -> Gate 2 preview/decision -> primary analysis -> deep analysis -> report availability in the UI state machine.
- [ ] Make provider unavailable vs offline fixture visible as different badges/messages.
- [ ] Use `primary intake` / `document readiness` for the pre-Gate 2 UI stage.
- [ ] Keep public comparables explicitly secondary and visually separate from the main startup case.
- [ ] Make the visual system investor-grade: dark evidence-dossier style, clear hierarchy, dense but readable panels, and mobile-safe layout.

**Verification**

```powershell
npm --prefix frontend/founder run test
npm --prefix frontend/founder run lint
npm --prefix frontend/founder run typecheck
npm --prefix frontend/founder run build
```

**Commit**

```powershell
git add frontend/founder/app frontend/founder/components frontend/founder/lib
git commit -m "feat: shape Founder Workspace for the startup case state machine"
```

---

## Task 4: Split Streamlit into a real Admin Console for tracing, privacy, evals, and cost/latency

**Depends on:** Tasks 1–2.

**Files**

- Modify: `src/due_diligence_agent/presentation/streamlit/app.py`
- Create: `src/due_diligence_agent/presentation/streamlit/pages/admin.py`
- Modify: `src/due_diligence_agent/presentation/streamlit/pages/public_case.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/audit.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/evidence.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/metrics.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/risks.py`
- Modify: `src/due_diligence_agent/adapters/observability/context.py`
- Modify: `src/due_diligence_agent/adapters/observability/audit_spool.py`
- Modify: `src/due_diligence_agent/adapters/observability/otel.py`
- Modify: `src/due_diligence_agent/adapters/observability/langsmith.py`
- Modify: `src/due_diligence_agent/adapters/observability/privacy.py`
- Test: `tests/smoke/test_streamlit_admin_console.py`
- Test: `tests/unit/observability/test_admin_trace_sanitization.py`
- Test: `tests/unit/observability/test_privacy_redaction.py`

**Interfaces**

- Admin sections for tracing, privacy, evals, cost/latency, source health, and report integrity.
- Founder-facing content must remain out of the Admin Console unless safely redacted/summarized.
- Trace metadata must stay scalar and safe; no raw startup documents, prompts, keys, or filenames.

**Checklist**

- [ ] Separate the admin entry from the public case surface so the operator path is visibly technical and the founder path is not.
- [ ] Reuse the existing audit/observability adapters to show traces, redaction, and integrity checks without exposing sensitive content.
- [ ] Add privacy and source-health summaries so the admin user can understand what was redacted, denied, or blocked.
- [ ] Add latency/cost summaries that support investor-demo credibility without turning the founder UI into a monitoring console.
- [ ] Keep the public case page as a secondary surface, not the primary product shell.

**Verification**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev pytest tests/smoke/test_streamlit_admin_console.py tests/unit/observability/test_admin_trace_sanitization.py tests/unit/observability/test_privacy_redaction.py -q
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev ruff check src/due_diligence_agent/presentation/streamlit src/due_diligence_agent/adapters/observability tests/smoke tests/unit/observability
```

**Commit**

```powershell
git add src/due_diligence_agent/presentation/streamlit src/due_diligence_agent/adapters/observability tests/smoke tests/unit/observability
git commit -m "feat: split Streamlit into admin observability surface"
```

---

## Task 5: Add one PowerShell orchestration script for offline fixture, hidden processes, screenshots, and no-network assertions

**Depends on:** Tasks 1–4.

**Files**

- Create: `scripts/smoke_founder_workspace.ps1`
- Modify: `scripts/run_founder_api.ps1`
- Create: `tests/fixtures/startup_founder_frozen_v1/**`
- Create or modify: `scripts/refresh_startup_fixture.py`
- Create: `tests/evaluation/test_startup_demo_fixture.py`
- Create: `tests/smoke/test_founder_workspace_boot.py`
- Create: `tests/smoke/test_startup_offline_fixture.py`
- Create: `tests/smoke/test_startup_browser_qa.py`

**Orchestration script contract**

`scripts\smoke_founder_workspace.ps1` must:

1. start backend and frontend as hidden processes only;
2. wait for `http://127.0.0.1:8000/health/live` and `http://127.0.0.1:3000/`;
3. run the founder flow against either live provider or explicit offline fixture mode;
4. assert no uncontrolled network access during offline fixture mode;
5. drive desktop and mobile browser checks and save artifacts to the existing UI pattern;
6. stop only the PIDs it started.

**Fixture contract**

- deterministic synthetic startup documents;
- frozen expected outputs for upload, analysis, report snapshot, and Gate 4;
- explicit `offline_fixture_active` provider state;
- no dependence on paid APIs or network reachability.

**Checklist**

- [ ] Build a deterministic startup fixture bundle that exercises upload, case creation, primary analysis, deep analysis, report snapshot, and Gate 4 freeze without network calls.
- [ ] Keep the offline fixture distinct from provider-unavailable behavior.
- [ ] Save screenshot evidence under the existing UI artifact pattern, including `artifacts/ui/founder-desktop.png` and `artifacts/ui/founder-mobile.png`.
- [ ] Verify the founder shell still reads as a premium investor demo at desktop and mobile widths.

**Verification**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_founder_workspace.ps1 -Mode offline-fixture -CaptureScreenshots
powershell -ExecutionPolicy Bypass -File scripts\smoke_founder_workspace.ps1 -Mode live-api -CaptureScreenshots
pytest tests/smoke/test_founder_workspace_boot.py tests/smoke/test_startup_offline_fixture.py tests/smoke/test_startup_browser_qa.py tests/evaluation/test_startup_demo_fixture.py -q
```

Browser review checkpoints:

- `http://127.0.0.1:3000/`
- `http://127.0.0.1:3000/admin`
- `http://127.0.0.1:3000/comparables`
- `http://127.0.0.1:8000/docs`

**Commit**

```powershell
git add scripts tests/fixtures/startup_founder_frozen_v1 tests/smoke tests/evaluation
git commit -m "test: add startup offline fixture and founder smoke orchestration"
```

---

## Final Review and Handoff

- Run `git diff --check` across every touched path.
- Run a placeholder scan on touched files and confirm there is no `TODO`, `FIXME`, or fake-data placeholder left in the shipped flow.
- Confirm the founder surface never shows raw tracing or operator-only controls.
- Confirm the admin surface never becomes the main founder UX.
- Confirm the startup report snapshot is the single source for JSON, HTML, and PDF.
- Confirm the plan preserves C seams: no auth/tenancy/billing rewrite, no breaking `/api/v1` contract drift, no duplicate analysis logic in the frontend.
