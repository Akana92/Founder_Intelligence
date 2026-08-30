# Queue 2 Parallel Product Lanes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в startup-продукт адаптивные метрики, проверяемое исследование рынка, сквозной tracing для Admin Console и frozen evaluation contracts, сохранив Queue 1, privacy и Public Company regression зелёными.

**Architecture:** Queue 2 выполняется четырьмя независимыми contract-first линиями. Первые две волны меняют только файлы, которыми владеет конкретная линия. Общие composition roots (`workflows/startup/ports.py`, `graph.py`, `state.py`, `runtime.py`, `bootstrap/container.py`, startup report и Streamlit Admin) остаются закрыты до Wave 3 и изменяются одним интегратором после заморозки контрактов.

**Tech Stack:** Python 3.13, Pydantic v2, LangGraph, SQLite/JSONL audit, pytest, Ruff, strict mypy, PowerShell, существующие WeasyPrint/ReportLab и Streamlit/Next.js поверхности.

## Global Constraints

- Queue 1 commits `459fe34` и `4688a8b` являются regression baseline; пользовательские изображения и runtime/temp artifacts не трогать.
- Во время Queue 2 не выполнять OpenAI, LangSmith, Yahoo Finance, GDELT или иные сетевые/платные вызовы. Все исследования и evaluations сначала frozen/offline.
- Raw document text, filenames, email, токены, локальные пути и секреты не попадают в graph state, runtime trace, Admin DTO или report.
- Canonical deterministic calculations остаются источником истины; controlled Python создаёт только отдельный provisional artifact и не перезаписывает calculation.
- Local audit обязателен. Внешний exporter опционален и не является источником истины.
- Heavy gates (`full pytest`, Gate C/D/E, frontend build) выполняются последовательно одним владельцем, чтобы не перегружать CPU и не конфликтовать за Windows temp/cache.
- Каждый lane сначала добавляет RED-тест, фиксирует ожидаемую причину падения, затем минимальную реализацию и GREEN.
- Ни один lane не делает `git add -A`, broad commit, reset, cleanup или изменение чужих файлов.

## Ownership Matrix

| Lane | Wave 1–2 ownership | Shared files forbidden until Wave 3 |
|---|---|---|
| 2A Metrics/readiness | `domain/startup/readiness.py`, `application/services/startup_readiness_service.py`, focused tests | startup graph/ports/runtime/container/report |
| 2B Market research | `domain/startup/market.py`, `ports/startup_research.py`, `application/services/startup_market_research_service.py`, frozen adapter/fixtures, focused tests | startup graph/ports/container/report |
| 2C Tracing/Admin proof | `application/services/startup_trace_query_service.py`, focused observability tests | graph/runtime/container/Streamlit Admin |
| 2D Evaluation | `evals/gate_d.py`, `evals/gate_e.py`, Gate D/E tests, synthetic frozen datasets, runner scripts | CLI changes coordinated in Wave 3 |
| Integration owner | no lane-owned domain redesign | all shared composition and presentation files |

## Child Plans

- [Queue 2A — Adaptive Metrics and Readiness](./2026-08-13-queue2a-adaptive-metrics-readiness.md)
- [Queue 2B — Startup Market Research](./2026-08-13-queue2b-startup-market-research.md)
- [Queue 2C — Runtime Tracing and Admin Proof](./2026-08-13-queue2c-runtime-tracing-admin-proof.md)
- [Queue 2D — Frozen Evaluation Contracts](./2026-08-13-queue2d-frozen-evaluation-contracts.md)

## Closure status — 2026-08-14

Queue 2 is closed for the frozen/offline product scope on `main` commit `759482f8760f71eec6395ffffbc9ac2b9265d8d8`.

Closure evidence:

- Focused Queue 2A–2D regression: `338 passed`.
- Gate C final: `output/verification/queue2-closure-20260814-gate-c-final`, PASS.
- Gate D final on closure HEAD: `output/verification/queue2-closure-20260814-gate-d-head-c` and `output/verification/queue2-closure-20260814-gate-d-head-d`, both PASS; 4/4 semantic fingerprints and 4/4 canonical persisted fingerprints match.
- Gate E final on closure HEAD: `output/verification/queue2-closure-20260814-gate-e-head`, PASS.
- Full backend: `1101 passed, 1 skipped`; Ruff PASS; strict mypy PASS.
- Founder frontend test/typecheck/lint/build PASS.
- Real offline browser/API smoke across `/`, `/admin`, `/comparables`, and `/docs` PASS with no console errors.

Explicit non-Queue2/deferred scope: actual live research execution, actual controlled-Python workflow use, external LangSmith/OTel delivery, Queue 3 substantive Reflexion, Queue 4 deep-analysis UX/report work, and Queue 5 Demo Freeze.

## Wave 1 — Freeze New Contracts in Parallel

- [x] **Task W1.A:** implement the Queue 2A domain contract and deterministic identity tests from Task 2A.1.
- [x] **Task W1.B:** implement the Queue 2B market research domain/source contract and validation tests from Task 2B.1.
- [x] **Task W1.C:** implement the Queue 2C bounded trace query DTO/service contract and privacy tests from Task 2C.1.
- [x] **Task W1.D:** implement Queue 2D Gate D/E result schemas and manifest contract tests from Task 2D.1.
- [x] Lane agents may run only their own focused pytest with unique `--basetemp .tmp-q2/<lane>/pytest`; the integration owner runs Ruff and strict mypy sequentially after all four lane test runs finish.
- [x] Review lane diffs for overlapping paths before any commit.

Expected evidence: four focused GREEN test modules; no modifications to shared composition files; no network processes or API usage.

## Wave 2 — Services, Frozen Adapters and Dry Evaluators in Parallel

- [x] **Task W2.A:** implement deterministic pack selection, readiness scoring and maximum-three question selection.
- [x] **Task W2.B:** implement frozen research plan/execution with competitor taxonomy, TAM/SAM/SOM assumption lineage and dated sentiment.
- [x] **Task W2.C:** aggregate sanitized JSONL audit events into bounded case/run/node/tool/retry/token/cost/report lineage.
- [x] **Task W2.D:** complete synthetic datasets, golden assertions and direct Python Gate D/E dry runs without CLI wiring.
- [x] Run focused lane regression suites sequentially if two commands would both execute more than 50 tests.

Expected evidence: deterministic hashes repeat across two runs; no invented metric/market values; all outward trace fields pass privacy scans; Gate D/E dry-run artifacts write to unique caller-provided roots.

## Wave 3 — Single-Owner Integration

- [x] Inspect all lane commits and freeze these exact runtime artifacts: `startup_readiness@1`, `startup_market_research@1`, `startup_trace_view@1`, `gate_d_result@1`, `gate_e_result@1`.
- [x] Add explicit workflow ports to `src/due_diligence_agent/workflows/startup/ports.py` without importing adapters into the workflow layer.
- [x] Wire readiness and a new bounded `market_research` node after `profile_enrichment`; run it in parallel with the metrics→financial→risk branch, then join both branches in the existing `market_analysis` node before Reflexion. Do not add a second market-analysis synthesis node. Preserve Gate 2 denial, Gate 3 invalidation/recompute, checkpoint id-only policy and maximum two Reflexion iterations.
- [x] Persist only IDs/hashes/revisions in checkpoint state; keep complete readiness/research payloads in repositories/runtime artifacts.
- [x] Wire dependencies in `src/due_diligence_agent/bootstrap/container.py` for deterministic/frozen mode first. Live research and controlled Python remain explicit opt-in provider seams.
- [x] Bind readiness/research/trace lineage into `src/due_diligence_agent/application/services/startup_report_service.py` and `src/due_diligence_agent/workflows/startup/nodes/report.py` without creating duplicate report snapshots.
- [x] Extend `src/due_diligence_agent/presentation/streamlit/pages/admin.py` and `components/audit.py` through the safe query service. Keep `frontend/founder/app/admin/page.tsx` as the existing Streamlit bridge.
- [x] Add `run-gate-d`/`run-gate-e` CLI commands only after evaluator contracts are stable.

Focused integration command:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/metrics/test_startup_metrics.py tests/unit/observability/test_startup_trace_query.py tests/graph/test_startup_workflow.py tests/unit/reporting/test_startup_report_snapshot.py
```

Expected result: all selected tests pass; Gate 2 denied path records zero external calls; Gate 3 recompute replaces only affected artifacts; report snapshot identity changes when readiness/research identity changes.

## Wave 4 — Queue 2 Verification Gate

- [x] Run Queue 2 focused suites and frozen Gate D dry run in unique directories.
- [x] Run Gate C once as Queue 1 regression; compare its canonical profile hash with the Queue 1 baseline.
- [x] Run full backend pytest, then Ruff, then strict mypy sequentially.
- [x] Run frontend tests/typecheck/lint/build sequentially only if shared API/report DTOs changed.
- [x] Run privacy scan over Gate D/E JSON, HTML, PDF metadata and audit JSONL.
- [x] Have an independent reviewer verify source provenance, deterministic identity, substantive report sections and no private payloads.
- [x] Update the staircase only after all evidence above is fresh.

Queue 2 passes when all four lane contracts are integrated, Gate C remains green, Gate D dry run is deterministic and Admin can prove case/run/node/retry/token/cost/report lineage from bounded sanitized local data. The closure evidence above satisfies this gate, so Queue 3 is unblocked.

**Verification status (2026-08-14):** the original merged implementation passed at `a7e807bc0860bf94cc8009b4f98ec973168ef352`; the requirement-by-requirement closure remediation and fresh offline verification are complete through `759482f8760f71eec6395ffffbc9ac2b9265d8d8`. See the [Queue 2 closure audit](../../verification/2026-08-14-queue2-closure-audit.md) and [Queue 2 verification evidence](../../verification/2026-08-14-queue2-verification.md). Queue 3 is unblocked; Queue 4 and Queue 5 remain future work.

## Commit Sequence

1. `docs: plan Queue 2 parallel product lanes`
2. `feat: add startup readiness contracts`
3. `feat: add frozen startup market research contracts`
4. `feat: add startup trace query contracts`
5. `test: add Gate D and Gate E frozen contracts`
6. `feat: integrate Queue 2 startup intelligence lanes`
7. `docs: record Queue 2 verification`
