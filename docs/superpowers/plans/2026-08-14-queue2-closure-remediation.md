# Queue 2 Closure Remediation Plan

> **Execution contract:** Follow TDD for every functional change: observe RED, add the minimum production behavior, observe GREEN, run focused regressions, then commit only the named files. Queue 3 work remains paused until this plan and the Queue 2 closure verification are complete.

**Goal:** Close the evidence-backed functional gaps left by Queue 2A-2D, reconcile the Queue 2 plans with the implemented product, and re-run the complete offline closure gate without changing Queue 3 scope.

**Baseline:** `main` at `f6c6803dc91439504c2ffd56399c3986a7610941`. The untracked `task15_r3_probe_app.py` and `task15_r3_probe_data/` are user-owned and excluded from every command and commit.

**Closure status (2026-08-14):** Tasks 1–5 are complete for the frozen/offline Queue 2 scope. Functional remediation is verified through `759482f8760f71eec6395ffffbc9ac2b9265d8d8`; focused Queue 2 tests, fresh Gate C/D/E, full backend/static/frontend checks, real local API/browser smoke, and independent review are recorded in the closure audit and verification report. The deferred seams listed below remain outside Queue 2 completion.

**Scope boundaries:**

- No paid OpenAI, LangSmith, Yahoo Finance, GDELT, news, or web calls.
- Frozen research and the live-research policy boundary are reported separately. A live provider is not a Queue 2 closure requirement.
- The controlled-Python policy is reported separately from real startup-flow use. It stays disabled and outside frozen Gate D.
- Local durable audit is the Queue 2 source of truth. External exporter delivery remains optional, but a failed configured exporter must be visible as degraded in the bounded Admin view.
- Queue 3 Reflexion, Queue 4 deep-analysis UX, and Queue 5 Demo Freeze are not counted as Queue 2 completion.
- Work stays on `main`; no worktree, branch deletion, reset, checkout, clean, or broad staging.

## Task 1: Validate the Queue 2 frozen manifest before analysis

**Files:**

- Create: `src/due_diligence_agent/evals/startup_fixture_contract.py`
- Modify: `src/due_diligence_agent/evals/startup_frozen_runtime.py`
- Modify: `tests/evaluation/test_startup_frozen_runtime.py`

### RED

1. Copy `tests/fixtures/startup_synthetic_v1` into a test-owned temporary directory.
2. Add parameterized failures for a tampered case file, tampered `expected_contracts.json`, unsafe manifest path, invalid offline/privacy policy, and byte-cap overflow.
3. Monkeypatch the runtime fixture root and `_run_all_cases`; prove each invalid contract raises a stable `startup_fixture_*` error before `_run_all_cases` is called and before runtime artifacts are produced.
4. Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/evaluation/test_startup_frozen_runtime.py -k "manifest or fixture_contract"
```

Expected RED: the runtime currently reads only case names and proceeds without production manifest/hash validation.

### GREEN

1. Add a small production validator that:
   - accepts only `startup_synthetic_fixture_manifest@1` and `startup_synthetic_v1`;
   - requires `no_external_network` and `synthetic_no_secrets_no_emails_no_local_paths`;
   - resolves every declared path inside the fixture root;
   - verifies file existence, declared bytes, SHA-256, non-empty cases, and the total byte cap;
   - verifies the expected-contract artifact before returning sorted case names;
   - raises stable, content-free error codes.
2. Call the validator before output-directory creation and before entering the API/runtime analysis loop.
3. Run the RED selector, then the complete fixture/runtime regressions:

```powershell
uv run pytest -q -p no:cacheprovider tests/evaluation/test_startup_frozen_runtime.py tests/evaluation/test_queue2_startup_fixtures.py
uv run ruff check src/due_diligence_agent/evals/startup_fixture_contract.py src/due_diligence_agent/evals/startup_frozen_runtime.py tests/evaluation/test_startup_frozen_runtime.py
uv run mypy --strict src/due_diligence_agent/evals/startup_fixture_contract.py src/due_diligence_agent/evals/startup_frozen_runtime.py
```

4. Commit only these files with `fix: validate frozen startup fixtures before analysis`.

## Task 2: Enforce unique, non-overwriting Gate D/E output roots

**Files:**

- Create: `src/due_diligence_agent/evals/output_root.py`
- Modify: `src/due_diligence_agent/evals/gate_d.py`
- Modify: `src/due_diligence_agent/evals/gate_e.py`
- Modify: `src/due_diligence_agent/presentation/cli.py`
- Modify: `tests/evaluation/test_startup_gate_d.py`
- Modify: `tests/evaluation/test_combined_gate_e.py`

### RED

1. Replace the stale-result overwrite expectation with fail-closed collision behavior.
2. Add direct Gate D and Gate E tests proving a non-empty output root raises `evaluation_output_dir_not_empty` before commands or nested evaluators run and does not alter a sentinel file.
3. Add CLI tests proving collision returns exit code `2`, writes a stable message to stderr, does not invoke the evaluator, and leaves the sentinel unchanged.
4. Keep compatibility with the existing test pattern where the caller supplies an already-created but empty temporary directory.
5. Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/evaluation/test_startup_gate_d.py tests/evaluation/test_combined_gate_e.py -k "collision or output_dir or atomically"
```

Expected RED: Gate D currently overwrites stale `eval-result.json`, and Gate D/E accept arbitrary non-empty roots.

### GREEN

1. Add one shared output-root guard that accepts a missing root or an existing empty directory, rejects files and non-empty directories, and creates missing directories without overwriting prior run evidence.
2. Call it at the start of the direct Gate D/E runners before commands or nested evaluators.
3. Reject a non-empty root in the CLI before evaluator dispatch so the command has a stable exit code and stderr contract.
4. Run focused and full Gate D/E contract tests, Ruff, and strict mypy.
5. Commit only the named files with `fix: prevent Gate D and E output collisions`.

## Task 3: Persist and expose external exporter degradation

**Files:**

- Modify: `src/due_diligence_agent/adapters/observability/audit_spool.py`
- Modify: `src/due_diligence_agent/adapters/observability/otel.py`
- Modify: `src/due_diligence_agent/application/services/startup_trace_query_service.py`
- Modify: `src/due_diligence_agent/presentation/streamlit/components/audit.py`
- Modify: `tests/unit/observability/test_exporter_fallback.py`
- Modify: `tests/unit/observability/test_startup_trace_query.py`
- Modify: `tests/unit/observability/test_admin_trace_sanitization.py`
- Verify unchanged: `tests/privacy/test_langsmith_masking.py`

### RED

1. Add an exporter regression proving an exception or `SpanExportResult.FAILURE` appends a sanitized `observability.exporter_degraded` audit marker for each correlatable startup span while preserving the original local span event.
2. Add a query-service regression proving the marker produces an honest exporter-health DTO (`status=degraded`, stable error code, local-audit fallback) for exactly one case/run and does not become a fake graph node.
3. Add an Admin snapshot regression proving exporter health is rendered from the DTO and no private/raw attributes are exposed.
4. Retain tracing-disabled coverage proving disabled LangSmith construction remains lazy and receives no metadata.
5. Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/observability/test_exporter_fallback.py tests/unit/observability/test_startup_trace_query.py tests/unit/observability/test_admin_trace_sanitization.py tests/privacy/test_langsmith_masking.py -k "exporter or degradation or disabled"
```

Expected RED: local fallback exists, but the bounded startup trace view has no exporter-health contract.

### GREEN

1. Allow one dedicated safe audit event type for exporter degradation.
2. When the configured delegate raises or returns failure, append a content-free marker containing only allowlisted correlation fields and stable status/error/fallback values. If required local persistence fails, preserve `AUDIT_PERSISTENCE_ERROR` fail-closed behavior.
3. Add immutable `StartupTraceExporterHealth` to `StartupTraceView`; absence stays nullable/unknown and is never fabricated as healthy.
4. Detect the dedicated marker after exact case/run filtering, expose it in Admin, and exclude it from the graph-node timeline.
5. Run all named observability/privacy tests, Ruff, and strict mypy.
6. Commit only the named files with `fix: surface startup exporter degradation`.

## Task 4: Reconcile Queue 2 documentation with evidence

**Files:**

- Add/update: `docs/verification/2026-08-14-queue2-closure-audit.md`
- Modify: `docs/superpowers/plans/2026-08-13-queue2-parallel-product-lanes.md`
- Modify: `docs/superpowers/plans/2026-08-13-queue2a-adaptive-metrics-readiness.md`
- Modify: `docs/superpowers/plans/2026-08-13-queue2b-startup-market-research.md`
- Modify: `docs/superpowers/plans/2026-08-13-queue2c-runtime-tracing-admin-proof.md`
- Modify: `docs/superpowers/plans/2026-08-13-queue2d-frozen-evaluation-contracts.md`
- Modify: `docs/superpowers/plans/2026-08-13-capstone-completion-staircase.md`
- Modify: `docs/verification/2026-08-14-queue2-verification.md`

1. Preserve the exhaustive requirement-to-file/test/integration/status tables from the four-lane closure audit.
2. After Tasks 1-3 are green, change only evidence-backed Queue 2 checkboxes to complete.
3. Add explicit deferred notes for actual live research execution, controlled Python in the startup workflow, external LangSmith/OTel delivery, Queue 3 Reflexion, Queue 4 UX, and Queue 5 demo freeze.
4. Record fresh commands, counts, Gate artifacts, commit ids, and any Windows-only skip. Do not copy runtime artifacts into git.
5. Confirm the roadmap, parent plan, child plans, closure audit, and verification report no longer contradict each other.
6. Commit only documentation with `docs: close Queue 2 evidence ledger`.

## Task 5: Final offline closure verification

Run in this order and retain only concise evidence in documentation:

1. Focused Queue 2A-2D tests, including restart, privacy, determinism, report lineage, Admin, fixtures, Gate D, and Gate E.
2. Gate C into a fresh unique output root.
3. Gate D twice into two fresh unique output roots and compare canonical Queue 2 assertions/semantic fingerprints.
4. Gate E once into a fresh unique output root.
5. Full backend `pytest`, Ruff, and strict mypy.
6. Founder frontend tests, typecheck, lint, and build if DTO/UI/report-facing behavior is affected.
7. A real local offline API/browser smoke using the frozen founder fixture; no paid provider keys or network.
8. Independent code review followed by an evidence-only verifier pass.

Queue 2 may be marked closed only if every required child-plan row is `complete` or explicitly assigned to Queue 3-5/deferred optional provider scope, all fresh checks pass, and the worktree contains only the protected user-owned untracked files.
