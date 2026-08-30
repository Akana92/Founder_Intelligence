# Queue 5 Live Proof Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve deterministic Queue 5 freeze evidence while adding a sanitized real-workflow LangSmith trace, a pure-PDF same-case browser/API/Admin journey, and an optional one-call OpenAI competitor-synthesis smoke.

**Architecture:** The real startup LangGraph keeps local audit as source of truth and fans only an explicit sanitized node envelope to a best-effort LangSmith tracer. PDF and OpenAI proof are separate Queue 5 side evaluators, and the final verification summary binds their independent statuses without making Gate D/E network-dependent.

**Tech Stack:** Python 3.12/3.13, Pydantic, LangGraph 1.2, LangSmith 0.10, OpenAI Responses structured parsing, FastAPI, Streamlit Admin, Playwright/CDP Node helper, PowerShell, pytest, Ruff, strict mypy.

## Global Constraints

- Gate B/C/D-A/D-B/E stay deterministic, tracing-disabled, offline, and network-independent.
- Never print or persist credential values; inspect only boolean presence.
- Never export PDF/document text, filenames, paths, prompts, chain-of-thought, PII, secrets, graph state, or raw model I/O.
- Local JSONL audit remains canonical and exporter failure never changes workflow outcome.
- LangSmith trace, OpenAI smoke, PDF journey, and frozen packet use separate status fields and semantic hashes.
- Use exactly one bounded LangSmith live smoke only after offline GREEN.
- Use at most one OpenAI request, `max_retries=0`, timeout bounded, total budget at or below USD 0.25, and no live web sources.
- Do not modify Queue 1-4 behavior or begin R11/R12.
- Do not edit `frontend/founder` without first reading `frontend/founder/AGENTS.md`.
- Do not stage protected RED-WIP, probe files, pytest stores, generated PDFs/screenshots/runtime files, or use broad Git commands.

---

## File responsibility map

- `adapters/observability/privacy.py`: shared primitive allowlist and value validation.
- `adapters/observability/langsmith.py`: privacy-hardened lazy LangSmith client creation only.
- `adapters/observability/startup_langsmith.py`: startup node/root run lifecycle, best-effort export, and provider-specific local health markers.
- `workflows/startup/tracing.py`: composite node tracer and fixed node-to-agent-role mapping.
- `workflows/startup/graph.py`: produces the compact safe node envelope; never receives SDK concerns.
- `bootstrap/container.py`: single integration point that composes metric and optional LangSmith tracers.
- `presentation/api/dependencies.py`: reads `DDA_LANGSMITH_TRACING` and boolean credential presence for the normal startup composer; deterministic composer remains untraced unless an explicit Queue 5 smoke supplies a tracer.
- `application/services/startup_trace_query_service.py`: keeps existing OTel exporter health and adds separate provider-specific LangSmith health.
- `presentation/streamlit/components/audit.py`: displays LangSmith health separately from OTel health.
- `evals/langsmith_live_smoke.py`: credential-gated Queue 5 LangSmith evidence schema/runner.
- `evals/openai_competitor_smoke.py`: Gate-2-gated one-call structured competitor inference and evidence schema.
- `scripts/run_queue5_langsmith_smoke.ps1`: offline-first LangSmith smoke orchestration.
- `scripts/run_queue5_openai_competitor_smoke.ps1`: offline-first optional OpenAI smoke orchestration.
- `scripts/smoke_founder_workspace.ps1`: opt-in frozen PDF fixture mode while retaining the Queue 4 CSV default.
- `scripts/capture_founder_screenshots.mjs`: safe PDF input proof and same-case Admin trace proof in browser evidence.
- `evals/sellable_demo_freeze.py`: binds, but does not merge, independent Queue 5 side evidence.
- `evals/queue5_verification.py`: final status/hash summary across frozen, PDF, LangSmith, and OpenAI lanes.

---

### Task 1: Extend the strict telemetry allowlist

**Files:**
- Modify: `src/due_diligence_agent/adapters/observability/privacy.py`
- Modify: `tests/privacy/test_langsmith_masking.py`

**Interfaces:**
- Consumes: `StrictTraceSanitizer.sanitize_attributes(attributes, drop_disallowed=False)`.
- Produces: validation for `agent_role`, `gate`, `gate_status`, `report_id`, `report_revision`, `report_checksum`, and `exporter_provider`.

- [ ] **Step 1: Write the failing allowlist tests**

```python
def test_langsmith_startup_metadata_allowlist_accepts_safe_operational_fields() -> None:
    safe = StrictTraceSanitizer().sanitize_attributes(
        {
            "case_id": str(uuid4()),
            "run_id": "startup-api-case-1",
            "node_name": "report",
            "agent_role": "report",
            "gate": "gate4",
            "gate_status": "completed",
            "duration_ms": 12,
            "retry_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "report_id": str(uuid4()),
            "report_revision": 1,
            "report_checksum": "a" * 64,
            "exporter_provider": "langsmith",
        }
    )
    assert safe["agent_role"] == "report"
    assert safe["report_revision"] == 1

@pytest.mark.parametrize(
    "key",
    ["filename", "local_path", "prompt", "document_text", "private_name", "api_key"],
)
def test_langsmith_startup_metadata_rejects_payload_and_identity_fields(key: str) -> None:
    with pytest.raises(ValueError, match="trace_attribute.disallowed"):
        StrictTraceSanitizer().sanitize_attributes({key: "unsafe"})
```

- [ ] **Step 2: Run the RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/privacy/test_langsmith_masking.py -q`

Expected: the new safe fields fail with `trace_attribute.disallowed`.

- [ ] **Step 3: Add exact key/type validation**

Add the six operational fields plus `exporter_provider` to `ALLOWED_TRACE_ATTRIBUTE_KEYS`; add `report_id` to `_ID_KEYS`, `report_checksum` to `_HASH_KEYS`, `report_revision` to `_NUMERIC_KEYS`, and constrain role/gate/provider strings with the existing safe token/status regexes. Do not relax the sensitive-value regex or any denied prefix/key.

- [ ] **Step 4: Run focused tests and static checks**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/privacy/test_langsmith_masking.py -q
.venv\Scripts\ruff.exe check src/due_diligence_agent/adapters/observability/privacy.py tests/privacy/test_langsmith_masking.py
.venv\Scripts\mypy.exe --strict src/due_diligence_agent/adapters/observability/privacy.py
```

Expected: PASS.

- [ ] **Step 5: Commit only Task 1 files**

```powershell
git add -- src/due_diligence_agent/adapters/observability/privacy.py tests/privacy/test_langsmith_masking.py
git commit -m "feat(observability): extend safe startup trace fields"
```

---

### Task 2: Add a best-effort startup LangSmith tracer

**Files:**
- Create: `src/due_diligence_agent/adapters/observability/startup_langsmith.py`
- Modify: `src/due_diligence_agent/adapters/observability/audit_spool.py`
- Create: `src/due_diligence_agent/workflows/startup/tracing.py`
- Create: `tests/unit/observability/test_startup_langsmith_tracer.py`

**Interfaces:**
- Produces: `StartupLangSmithTracerConfig(enabled: bool, credential_present: bool, project_name: str = "dda-queue5-frozen-smoke")`.
- Produces: `StartupLangSmithNodeTracer(config, audit_spool, client_factory=None, sanitizer=None, clock=None)` with `record(**attributes: object) -> None` and `flush() -> None`.
- Produces: `CompositeNodeTracer(*tracers)` with `record(**attributes: object) -> None` and `record_checkpoint_keys(keys: set[str]) -> None`.
- LangSmith client calls use `create_run(name, inputs={}, run_type="chain", **safe_kwargs)` and `update_run(run_id, outputs={}, end_time=...)` only.

- [ ] **Step 1: Write RED tests for disabled, enabled, and outage paths**

```python
def test_disabled_tracer_never_constructs_client() -> None:
    calls = 0
    def factory(**_: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("client must stay lazy")
    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=False, credential_present=True),
        audit_spool=_memory_spool(),
        client_factory=factory,
    )
    tracer.record(**_safe_node_attributes())
    assert calls == 0

def test_enabled_tracer_creates_empty_payload_root_and_child_runs() -> None:
    client = RecordingLangSmithClient()
    tracer = _enabled_tracer(client)
    tracer.record(**_safe_node_attributes(node_name="ingest"))
    tracer.record(**_safe_node_attributes(node_name="report", report_id=REPORT_ID))
    assert all(call["inputs"] == {} for call in client.created)
    assert all(call.get("outputs", {}) == {} for call in client.updated)
    assert {call["name"] for call in client.created} >= {"startup.workflow", "startup.ingest", "startup.report"}

def test_export_failure_spools_sanitized_langsmith_health_without_raising() -> None:
    tracer = _enabled_tracer(FailingLangSmithClient("private C:\\secret\\pitch.pdf"))
    tracer.record(**_safe_node_attributes())
    events = tracer.audit_spool.read_bounded(max_events=10)
    marker = next(e for e in events if e.event_type == "observability.langsmith_status")
    assert marker.attributes["status"] == "degraded"
    assert marker.attributes["error_code"] == "external_export_failed"
    assert "secret" not in repr(marker)
```

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/observability/test_startup_langsmith_tracer.py -q`

Expected: import failure for the new tracer module.

- [ ] **Step 3: Implement minimal root/child lifecycle**

Use deterministic UUID5 identifiers derived from safe `case_id`, `run_id`, node name, and attempt. Create one root per `(case_id, run_id)`, create/update a child per node record, and close/flush the root on report or terminal failure. Always pass `{}` for SDK inputs/outputs, never attachments, never runtime info, and sanitize metadata before SDK calls. Add the provider-specific event type to the strict JSONL audit spool with exact status/error validation. Catch every external SDK error, append one provider-specific health event, and return normally.

`CompositeNodeTracer` must preserve checkpoint-key forwarding and call the metric tracer even when the LangSmith child is disabled. It must not swallow failures from local audit because local audit is outside this composite.

- [ ] **Step 4: Run focused tests and static checks**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/observability/test_startup_langsmith_tracer.py tests/privacy/test_langsmith_masking.py -q
.venv\Scripts\ruff.exe check src/due_diligence_agent/adapters/observability/startup_langsmith.py src/due_diligence_agent/adapters/observability/audit_spool.py src/due_diligence_agent/workflows/startup/tracing.py tests/unit/observability/test_startup_langsmith_tracer.py
.venv\Scripts\mypy.exe --strict src/due_diligence_agent/adapters/observability/startup_langsmith.py src/due_diligence_agent/adapters/observability/audit_spool.py src/due_diligence_agent/workflows/startup/tracing.py
```

Expected: PASS.

- [ ] **Step 5: Commit only tracer core files**

```powershell
git add -- src/due_diligence_agent/adapters/observability/startup_langsmith.py src/due_diligence_agent/adapters/observability/audit_spool.py src/due_diligence_agent/workflows/startup/tracing.py tests/unit/observability/test_startup_langsmith_tracer.py
git commit -m "feat(observability): add best-effort startup LangSmith tracer"
```

---

### Task 3: Wire the tracer into the real startup LangGraph workflow

**Files:**
- Modify: `src/due_diligence_agent/workflows/startup/graph.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Modify: `src/due_diligence_agent/presentation/api/dependencies.py`
- Create: `tests/integration/observability/test_startup_langsmith_tracing.py`
- Modify: `tests/api/test_startup_api.py`

**Interfaces:**
- `build_startup_analysis_composer(..., external_node_tracer: object | None = None)` composes metrics plus the optional tracer.
- `build_deterministic_startup_analysis_composer(..., external_node_tracer: object | None = None)` accepts explicit smoke instrumentation but defaults to no external tracer.
- `_record_node` emits only the Task 1 safe envelope, including truthful zero token/cost fields for deterministic nodes and report lineage only on the report node.

- [ ] **Step 1: Write a RED real-workflow integration test**

Build a deterministic composer around a fake LangSmith client, copy the tiny PDF to the service inbox as `doc-0001.pdf`, call `service.start(...)`, approve disclosure, then approve Gate 3. Assert one case/run across representative node spans, `inputs == outputs == {}`, required agent roles, Gate metadata where present, zero deterministic token/cost values, and report lineage on the report node. Scan `repr(client.calls)` for `%PDF`, document prose, `.pdf`, temp path, `prompt`, `completion`, `email`, `api_key`, and `private_name` and require all to be absent.

- [ ] **Step 2: Write RED API dependency tests**

```python
def test_api_wires_langsmith_only_to_normal_composer_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDA_LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "present-but-never-logged")
    normal, deterministic = _capture_composer_kwargs()
    get_startup_case_coordinator.cache_clear()
    get_startup_case_coordinator()
    assert normal["external_node_tracer"] is not None
    assert "external_node_tracer" not in deterministic
```

Also test `DDA_LANGSMITH_TRACING=false` with a client factory that raises on construction and assert zero imports/exports.

- [ ] **Step 3: Run RED tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/observability/test_startup_langsmith_tracing.py tests/api/test_startup_api.py -q
```

Expected: missing composer parameter and missing safe fields.

- [ ] **Step 4: Implement the minimal graph/container/API wiring**

Add a fixed node-role mapping in `workflows/startup/tracing.py`. In `_record_node`, add only role, gate/status, zero usage, and report snapshot identity derived from already-persisted state. Do not pass state, source refs, data refs, warnings, or raw errors to the external tracer. Keep `audit.record(...)` before `tracer.record(...)`.

In the container, wrap `MetricContractNodeTracer` and `external_node_tracer` in `CompositeNodeTracer`. In API dependencies, use only `settings.langsmith_tracing` plus `bool(os.getenv("LANGSMITH_API_KEY"))`; never read or log the value. The standard deterministic composer call remains unchanged.

- [ ] **Step 5: Run integration, graph, API, Ruff, and strict mypy checks**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/observability/test_startup_langsmith_tracing.py tests/graph/test_startup_workflow.py tests/api/test_startup_api.py -q
.venv\Scripts\ruff.exe check src/due_diligence_agent/workflows/startup/graph.py src/due_diligence_agent/bootstrap/container.py src/due_diligence_agent/presentation/api/dependencies.py tests/integration/observability/test_startup_langsmith_tracing.py tests/api/test_startup_api.py
.venv\Scripts\mypy.exe --strict src/due_diligence_agent/workflows/startup/graph.py src/due_diligence_agent/bootstrap/container.py src/due_diligence_agent/presentation/api/dependencies.py
```

Expected: PASS and no external call in disabled tests.

- [ ] **Step 6: Commit only workflow wiring files**

```powershell
git add -- src/due_diligence_agent/workflows/startup/graph.py src/due_diligence_agent/bootstrap/container.py src/due_diligence_agent/presentation/api/dependencies.py tests/integration/observability/test_startup_langsmith_tracing.py tests/api/test_startup_api.py
git commit -m "feat(startup): wire sanitized LangSmith node tracing"
```

---

### Task 4: Show separate LangSmith health in Admin

**Files:**
- Modify: `src/due_diligence_agent/application/services/startup_trace_query_service.py`
- Modify: `src/due_diligence_agent/presentation/streamlit/components/audit.py`
- Modify: `tests/unit/observability/test_startup_trace_query.py`
- Modify: `tests/unit/observability/test_admin_trace_sanitization.py`

**Interfaces:**
- Produces: `StartupLangSmithHealth(provider, status, error_code, fallback_used)`.
- Adds `StartupTraceView.langsmith_health` while preserving `StartupTraceView.exporter_health` for existing OTel markers.
- Recognizes only `observability.langsmith_status` as the LangSmith health event and excludes it from node rows.

- [ ] **Step 1: Write RED query and rendering tests**

Create disabled, blocked, healthy, and degraded LangSmith marker cases. Assert they project to `langsmith_health`, never replace `exporter_health`, never count as nodes, and never expose raw exception text. Assert the Admin snapshot/render data contains a separate `LangSmith Exporter Health` row.

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/observability/test_startup_trace_query.py tests/unit/observability/test_admin_trace_sanitization.py -q`

Expected: missing `langsmith_health` field.

- [ ] **Step 3: Implement provider-specific projection and UI row**

Keep the existing OTel degradation parser unchanged. Add a strict parser accepting only provider `langsmith`, the four allowed statuses, bounded stable error code, and `fallback_used=local_audit`. Update Admin copy so OTel and LangSmith are visibly separate.

- [ ] **Step 4: Run tests and static checks**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/observability/test_startup_trace_query.py tests/unit/observability/test_admin_trace_sanitization.py -q
.venv\Scripts\ruff.exe check src/due_diligence_agent/application/services/startup_trace_query_service.py src/due_diligence_agent/presentation/streamlit/components/audit.py tests/unit/observability/test_startup_trace_query.py tests/unit/observability/test_admin_trace_sanitization.py
.venv\Scripts\mypy.exe --strict src/due_diligence_agent/application/services/startup_trace_query_service.py src/due_diligence_agent/presentation/streamlit/components/audit.py
```

Expected: PASS.

- [ ] **Step 5: Commit only Admin health files**

```powershell
git add -- src/due_diligence_agent/application/services/startup_trace_query_service.py src/due_diligence_agent/presentation/streamlit/components/audit.py tests/unit/observability/test_startup_trace_query.py tests/unit/observability/test_admin_trace_sanitization.py
git commit -m "feat(admin): expose separate LangSmith exporter health"
```

---

### Task 5: Add credential-gated LangSmith live-smoke evidence

**Files:**
- Create: `src/due_diligence_agent/evals/langsmith_live_smoke.py`
- Create: `scripts/run_queue5_langsmith_smoke.ps1`
- Create: `tests/evaluation/test_queue5_langsmith_live_smoke.py`

**Interfaces:**
- Produces: `langsmith_trace_evidence@1` with `status`, boolean credential presence, safe identities/counts/key inventory, empty-payload/privacy/Admin/report-lineage proofs, and `semantic_hash`.
- Produces CLI: `python -m due_diligence_agent.evals.langsmith_live_smoke --output-root <new-dir> [--execute-live]`.
- Default/no-key execution performs no SDK import and returns `blocked_missing_credential`.

- [ ] **Step 1: Write RED evidence tests**

Test fail-closed output collision, missing-key no-client behavior, fake-client healthy evidence, fake-client outage evidence, stable semantic hash across timestamps/latencies, and rejection of unsafe captured keys/values. Assert that `--execute-live` is required even when a key is present.

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/evaluation/test_queue5_langsmith_live_smoke.py -q`

Expected: missing module.

- [ ] **Step 3: Implement offline-first runner and PowerShell wrapper**

The runner must construct a fresh output root, run one tracked frozen startup case through the real deterministic composer, query local Admin trace evidence, flush the LangSmith client only in explicit live mode, and write one canonical JSON file. PowerShell must set `DDA_LANGSMITH_TRACING=false` for validation mode and enable it only for the bounded live invocation; it must never echo the key.

- [ ] **Step 4: Run focused tests and missing-key smoke**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/evaluation/test_queue5_langsmith_live_smoke.py -q
.venv\Scripts\python.exe -m due_diligence_agent.evals.langsmith_live_smoke --output-root .queue5-evidence\langsmith-missing-key
```

Expected: tests PASS; runtime evidence says `blocked_missing_credential`; no network call occurs. Remove or leave the runtime directory ignored, never stage it.

- [ ] **Step 5: Commit only smoke implementation files**

```powershell
git add -- src/due_diligence_agent/evals/langsmith_live_smoke.py scripts/run_queue5_langsmith_smoke.ps1 tests/evaluation/test_queue5_langsmith_live_smoke.py
git commit -m "feat(queue5): add bounded LangSmith trace evidence"
```

---

### Task 6: Prove the pure-PDF desktop/mobile/API/Admin journey

**Files:**
- Modify: `scripts/smoke_founder_workspace.ps1`
- Modify: `scripts/capture_founder_screenshots.mjs`
- Modify: `tests/evaluation/test_founder_browser_evidence_orchestration.py`
- Modify: `tests/smoke/test_founder_workspace_boot.py`
- Modify: `tests/api/test_startup_api.py`

**Interfaces:**
- Adds PowerShell parameter `-OfflineFixturePath` defaulting to the current CSV and switch `-RequirePdfUploadJourney`.
- Browser evidence adds `upload_mime_type`, `upload_bytes`, `upload_sha256`, `pdf_upload_journey`, and sanitized `admin_trace` identity/coverage/lineage/privacy fields.
- It never records a fixture filename or local path.

- [ ] **Step 1: Write RED orchestration and API tests**

Assert Queue 4 CSV remains the default. Assert PDF mode accepts exactly the tracked `saas/pitch.pdf`, rejects a CSV when `-RequirePdfUploadJourney` is set, and records only MIME/bytes/hash. Add an API integration path that uploads the PDF with no prompt/industry, approves Gate 2, completes deep/Gate 3 and Gate 4, fetches same-case JSON/HTML/PDF, and queries the same-case local Admin trace.

- [ ] **Step 2: Write RED browser evidence tests**

Require desktop 1440x1000 and mobile 390x844 for one case; primary/deep readiness; metrics; competitors; market sizing; contradictions/questions; GTM/action plan; Gate 4; JSON/HTML/PDF; and Admin `case_id/run_id/report_id/revision/checksum`. Reject mismatches, missing PDF proof, unsafe trace fields, or overflow.

- [ ] **Step 3: Run RED tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/evaluation/test_founder_browser_evidence_orchestration.py tests/smoke/test_founder_workspace_boot.py tests/api/test_startup_api.py -q
```

Expected: missing PDF parameter/evidence/Admin fields.

- [ ] **Step 4: Implement minimal fixture parameter and evidence capture**

Thread the selected fixture through the existing API upload and screenshot helper. Compute MIME/bytes/SHA-256 before upload, but serialize no path/name. Query the existing sanitized trace service after Gate 4 and add only bounded same-case fields to browser evidence. Preserve existing CSV behavior unchanged.

- [ ] **Step 5: Run focused checks and real PDF smoke**

Run the focused tests, Node syntax check, then one real local smoke with `-OfflineFixturePath tests/fixtures/startup_synthetic_v1/cases/saas/pitch.pdf -RequirePdfUploadJourney`. Keep generated uploads/reports/screenshots outside Git.

- [ ] **Step 6: Commit only PDF journey files**

```powershell
git add -- scripts/smoke_founder_workspace.ps1 scripts/capture_founder_screenshots.mjs tests/evaluation/test_founder_browser_evidence_orchestration.py tests/smoke/test_founder_workspace_boot.py tests/api/test_startup_api.py
git commit -m "feat(queue5): prove same-case frozen PDF journey"
```

---

### Task 7: Add the optional one-call OpenAI competitor smoke

**Files:**
- Create: `src/due_diligence_agent/evals/openai_competitor_smoke.py`
- Create: `scripts/run_queue5_openai_competitor_smoke.ps1`
- Create: `tests/evaluation/test_queue5_openai_competitor_smoke.py`

**Interfaces:**
- Produces Pydantic `CompetitorSynthesis` with five competitor classes, ICP overlap, differentiation, risk, confidence, evidence refs, and unknowns.
- Produces `openai_competitor_smoke_evidence@1` with independent status/hash and `inference_kind="live_inference"`.
- CLI returns `skipped_missing_credential` without client construction when `OPENAI_API_KEY` is absent.

- [ ] **Step 1: Write RED guard/privacy/structured-output tests**

Use a recording fake client. Assert no call before persisted Gate 2 approval, exactly one call after approval, no retry after timeout/parse failure, reservation and worst-case cost at or below USD 0.25, only sanitized profile/frozen summary fields in input, all five competitor classes in parsed output, `live_inference` label, and partial fallback on any provider failure.

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/evaluation/test_queue5_openai_competitor_smoke.py -q`

Expected: missing module.

- [ ] **Step 3: Implement the dedicated side evaluator**

Load Gate 2 status/profile/frozen market artifacts from local persisted state; build a bounded projection; reserve budget before the sole SDK request; invoke structured parsing with timeout and `max_retries=0`; validate evidence references; write side evidence; never mutate the report/runtime or call live sources.

- [ ] **Step 4: Run tests and missing-key smoke**

Run focused pytest/Ruff/mypy and the CLI without a key. Expected evidence is `skipped_missing_credential`, zero client calls, and no Queue 5 blocker.

- [ ] **Step 5: Commit only OpenAI smoke files**

```powershell
git add -- src/due_diligence_agent/evals/openai_competitor_smoke.py scripts/run_queue5_openai_competitor_smoke.ps1 tests/evaluation/test_queue5_openai_competitor_smoke.py
git commit -m "feat(queue5): add bounded competitor inference smoke"
```

---

### Task 8: Bind independent proof lanes and update demo artifacts

**Files:**
- Modify: `src/due_diligence_agent/evals/sellable_demo_freeze.py`
- Create: `src/due_diligence_agent/evals/queue5_verification.py`
- Create: `tests/evaluation/test_queue5_verification.py`
- Modify: `docs/demo/2026-08-16-sellable-demo-script.md`
- Modify: `docs/demo/2026-08-16-capstone-requirement-evidence-map.md`
- Create: `docs/verification/2026-08-16-queue5-verification.md`

**Interfaces:**
- Frozen packet binds optional side-evidence `path/hash/status` records without putting volatile live IDs/timings into `packet_hash`.
- `queue5_verification_summary@1` has separate `frozen_demo`, `pdf_journey`, `langsmith_trace`, and `openai_competitor_smoke` sections.
- Readiness requires frozen/PDF PASS plus LangSmith `healthy`; OpenAI may be `passed` or `skipped_missing_credential`.

- [ ] **Step 1: Write a new RED verification-summary test file**

Do not modify or stage `tests/evaluation/test_sellable_demo_freeze.py`. In the new test file, assert status separation, semantic-hash stability across volatile trace IDs/timings, fail-closed side-evidence case mismatch, required failure-matrix binding, and readiness blocked only by absent LangSmith evidence when all offline evidence passes.

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/evaluation/test_queue5_verification.py -q`

Expected: missing verification module/fields.

- [ ] **Step 3: Implement binding and final summary**

Add side-evidence references without changing the existing frozen semantic contract. Hash normalized status/schema/case/lineage/privacy fields only; retain raw file hashes separately. Fail closed on output collision and case/report mismatch.

- [ ] **Step 4: Update the 7-10 minute script, capstone map, and verification report**

Document the exact pure-PDF journey, separate LangSmith/Admin proof, optional OpenAI inference wording, failure-matrix recovery, artifact locations, and current credential blocker. Never claim Queue 5 ready while LangSmith status is not `healthy`.

- [ ] **Step 5: Run focused tests and docs scans**

Run focused Queue 5 tests, Ruff/mypy on changed modules, `git diff --check`, and an `rg` scan for stale `deferred_by_policy` claims in Queue 5 demo/verification docs.

- [ ] **Step 6: Commit exact binding/docs files**

Use explicit `git add --` paths and confirm `git diff --cached --name-only` excludes protected/runtime files before committing.

---

### Task 9: Execute the final offline/live verification boundary and independent reviews

**Files:**
- Modify only the final verification report with fresh evidence after commands complete.

**Interfaces:**
- Consumes all previous committed artifacts.
- Produces final evidence-backed status without broad staging or runtime artifacts.

- [ ] **Step 1: Run fresh offline gates in order**

Run Gate B, C, D-A, D-B, and E with tracing disabled and all live keys blanked by the existing offline orchestration. Preserve command logs outside Git and bind their hashes in the verification summary.

- [ ] **Step 2: Run the complete backend/static boundary**

Run full backend pytest, Ruff, and strict mypy. Read outputs and repair any regression before continuing.

- [ ] **Step 3: Read frontend instructions, then run frontend verification**

Read `frontend/founder/AGENTS.md` fully before any frontend command/change. Run frontend test, typecheck, lint, and build without editing generated artifacts into Git.

- [ ] **Step 4: Run real local pure-PDF desktop/mobile/browser/API/Admin smoke**

Start local services, drive the tracked PDF through the full journey, validate same-case evidence and artifacts, then stop services cleanly. Do not commit the PDF copy, runtime databases, reports, or screenshots.

- [ ] **Step 5: Run privacy/determinism/restart/report-lineage/failure-matrix checks**

Require all proof rows and stable semantic hashes to pass. Keep raw hashes as diagnostics only.

- [ ] **Step 6: Run credential-gated live smokes**

If `LANGSMITH_API_KEY` is present, run exactly one live trace and require `healthy`; otherwise record `blocked_missing_credential` as the sole Queue 5 readiness blocker. If `OPENAI_API_KEY` is present after LangSmith/offline GREEN, run exactly one competitor request; otherwise record the allowed `skipped_missing_credential` status.

- [ ] **Step 7: Dispatch independent code, docs, and acceptance reviews**

Give reviewers read-only scope and require exact findings with file/line evidence. Resolve all critical/high findings and rerun affected checks.

- [ ] **Step 8: Finalize the verification report and focused commit**

Record exact commit IDs, commands, pass counts, browser dimensions, same-case IDs/hashes, privacy status, live status, and remaining blocker. Stage only the report and any reviewer-approved doc corrections.
