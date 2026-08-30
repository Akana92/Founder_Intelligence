# Queue 2C Runtime Tracing and Admin Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать администратору безопасное и проверяемое представление траектории startup-анализа: case/run, узлы, checkpoints, tools, retries, tokens/cost, ошибки и canonical report lineage.

**Architecture:** Существующий sanitized JSONL audit остаётся обязательным source of truth. Новый `StartupTraceQueryService` читает bounded `AuditEvent` batches и строит immutable safe DTO `startup_trace_view@1`; он не читает raw prompts/outputs. OTel и LangSmith остаются опциональными экспортерами. Streamlit Admin потребляет только query DTO. Next `/admin` остаётся bridge на Streamlit.

**Tech Stack:** Python 3.12/3.13, dataclasses/Pydantic, JSONL audit, OTel, optional LangSmith, Streamlit, pytest, Ruff, strict mypy.

## Closure status — 2026-08-14

Queue 2C is complete for local audit, bounded trace query, report/usage lineage, Admin proof, and local exporter-degradation visibility. Evidence: focused observability/Admin/privacy tests in the `338 passed` Queue 2 regression, Gate D/E closure PASS, backend `1101 passed, 1 skipped`, Ruff and strict mypy PASS, and real offline `/admin` browser smoke with no console errors. External LangSmith/OTel delivery remains optional/production scope; Queue 2 only proves safe disabled/default behavior, durable local audit, and degraded-state visibility when a configured exporter fails.

## Global Constraints

- Local audit всегда доступен независимо от внешнего exporter.
- Не показывать raw startup content, prompt/output, filenames, tokens/keys, email, local paths или unrestricted error strings.
- Только allowlisted scalar metadata; list sizes and text lengths bounded.
- Exporter outage не ломает workflow, если локальная audit persistence успешна и `audit_required` contract соблюдён.
- Tracing disabled означает отсутствие LangSmith callback/export, но не отключает local audit.
- No paid/network calls в tests.
- `graph.py`, `runtime.py`, `container.py`, Streamlit pages/components и startup API меняются только в Wave 3.

## Task 2C.1 — Lock a Bounded Trace Read Model

**Files:**
- Create: `src/due_diligence_agent/application/services/startup_trace_query_service.py`
- Create: `tests/unit/observability/test_startup_trace_query.py`

- [x] Write RED tests for `StartupTraceNodeRow`, `StartupTraceUsageSummary`, `StartupTraceReportLineage` and `StartupTraceView`.
- [x] Require schema `startup_trace_view@1`, case/run filters, maximum 200 events, stable timestamp/event-id ordering and safe scalar fields only.
- [x] Model nullable checkpoint/tool/token/cost/report fields honestly; absence stays `None`, never zero/invented.
- [x] Run RED:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/observability/test_startup_trace_query.py
```

Expected RED: module import failure.

- [x] Implement immutable DTOs and a service accepting an `AuditSpool` or bounded event-reader dependency.
- [x] Reuse `StrictTraceSanitizer`; reject unsafe case/run filters and drop disallowed attributes.
- [x] Run GREEN, Ruff and strict mypy.
- [x] Commit: `feat: add bounded startup trace query contract`.

## Task 2C.2 — Aggregate Case/Run/Node/Retry/Tool Lineage

**Files:**
- Modify: `src/due_diligence_agent/application/services/startup_trace_query_service.py`
- Modify: `tests/unit/observability/test_startup_trace_query.py`

- [x] Write RED events covering two cases, two runs, repeated node attempts, a tool span, missing optional fields and out-of-order timestamps.
- [x] Filter on exact sanitized `case_id` and `run_id`; never infer case from filenames or directory paths.
- [x] Aggregate each node attempt with status, retry count, bounded latency, tool name and stable error code.
- [x] Prove duplicate `run_id` across different case ids cannot cross-contaminate views; include both identifiers in grouping.
- [x] Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/observability/test_startup_trace_query.py -k "lineage or collision"
```

Expected GREEN: no cross-case rows and deterministic ordering.
- [x] Commit: `feat: aggregate startup trace node lineage`.

## Task 2C.3 — Prove Token, Cost and Report Lineage

**Files:**
- Modify: `src/due_diligence_agent/application/services/startup_trace_query_service.py`
- Modify: `tests/unit/observability/test_startup_trace_query.py`

- [x] Write RED tests joining usage events to one canonical report snapshot id/hash/revision; rejected or stale report ids remain diagnostics rather than canonical lineage.
- [x] Sum input/output/total tokens and Decimal USD only from allowlisted numeric attributes; reject NaN, negative values and unbounded integers.
- [x] Require trace lineage to expose Gate 4 status and canonical report tuple without report content.
- [x] Run focused `-k "usage or report"` tests.
- [x] Commit: `feat: link startup trace usage to canonical report`.

## Task 2C.4 — Lock Exporter Outage and Tracing-Disabled Semantics

**Files:**
- Modify: `tests/unit/observability/test_exporter_fallback.py`
- Modify: `tests/unit/observability/test_admin_trace_sanitization.py`
- Modify: `tests/unit/observability/test_startup_trace_query.py`

- [x] Add RED regression where OTel/LangSmith delegate fails but durable local audit remains readable and the query view marks exporter degradation.
- [x] Add tracing-disabled regression proving no LangSmith callback/export is constructed or receives metadata.
- [x] Preserve hard failure when required local audit append itself fails.
- [x] Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/observability/test_exporter_fallback.py tests/unit/observability/test_admin_trace_sanitization.py tests/unit/observability/test_startup_trace_query.py
```

Expected GREEN: external outage non-blocking, local persistence failure fail-closed and zero unsafe metadata.
- [x] Commit: `test: prove startup tracing fallback and privacy`.

## Task 2C.5 — Wave 3 Runtime Instrumentation Handoff

**Integration owner files only:**
- Modify: `src/due_diligence_agent/workflows/startup/graph.py`
- Modify: `src/due_diligence_agent/workflows/startup/ports.py`
- Modify: `src/due_diligence_agent/workflows/startup/runtime.py`
- Modify: `src/due_diligence_agent/adapters/observability/privacy.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Modify: `tests/graph/test_startup_workflow.py`

- [x] Emit allowlisted case/run/node/attempt/retry/checkpoint/tool/usage/report fields at the real lifecycle boundary; do not synthesize them in Admin.
- [x] Preserve current startup node span names and retry behavior.
- [x] Add stable checkpoint id/hash only; never checkpoint bytes or raw state.
- [x] Ensure report generation/Gate 4 emits canonical snapshot tuple and data revision.
- [x] Run graph plus observability regressions and commit `feat: complete startup trace lineage`.

## Task 2C.6 — Render the Safe View in Streamlit Admin

**Files:**
- Modify: `src/due_diligence_agent/presentation/streamlit/pages/admin.py`
- Modify: `src/due_diligence_agent/presentation/streamlit/components/audit.py`
- Modify: `tests/unit/observability/test_admin_trace_sanitization.py`
- Verify only: `frontend/founder/app/admin/page.tsx`

- [x] Add RED tests for node timeline, retry/error nodes, budget/latency, exporter health and report lineage rows.
- [x] Inject/use `StartupTraceQueryService` instead of parsing unrestricted attributes in the rendering layer.
- [x] Keep `ADMIN_AUDIT_EVENT_LIMIT` and bounded file/byte/line limits.
- [x] Confirm Next `/admin` still bridges to Streamlit and its capability label stays truthful.
- [x] Run focused tests plus frontend contract tests if the bridge/capability files changed.
- [x] Commit: `feat: show bounded startup trace proof in admin`.
