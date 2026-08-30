# Queue 2A Adaptive Metrics and Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Автоматически выбрать уместный набор метрик для модели и стадии стартапа, рассчитать только доказуемые показатели, отдельно оценить готовность данных и сформировать максимум три приоритетных вопроса основателю.

**Architecture:** Новый immutable `StartupReadinessSnapshot` строится детерминированным application service из persisted `StartupProfile` и существующих `metric_diagnostics`. Domain/service слой не зависит от LangGraph. Полный snapshot хранится вне checkpoint; graph получает только его id/hash/revision. Существующий `StartupMetricService` остаётся единственным canonical calculator. `OpenAICodeInterpreterAdapter` подключается позднее отдельным opt-in портом и возвращает только provisional artifacts.

**Tech Stack:** Python 3.12/3.13, Pydantic v2, существующие `domain/metrics/startup.py`, `application/services/startup_metric_service.py`, LangGraph runtime, pytest, Ruff, strict mypy.

## Closure status — 2026-08-14

Queue 2A is complete for the offline deterministic metrics/readiness scope. Evidence: readiness domain/service/workflow/report integration, adaptive questions, focused Queue 2 regression `338 passed`, Gate C/D/E closure PASS, backend `1101 passed, 1 skipped`, Ruff and strict mypy PASS. The controlled-Python policy boundary is complete and default-off; actual controlled-Python use inside the startup workflow remains an explicit deferred/opt-in seam and is not counted as Queue 2 completion.

## Global Constraints

- Не изменять `CHECKPOINT_STATE_KEYS` в contract-first задачах.
- Не выполнять OpenAI/Code Interpreter calls в Queue 2A verification.
- Не превращать confidence или evidence coverage в readiness score: это отдельные измерения.
- Не подставлять значения за отсутствующие inputs; такие метрики получают `insufficient_data` и вопросы.
- Максимум три вопроса, стабильная сортировка по priority, stable code, затем question id.
- Controlled Python не создаёт и не изменяет canonical `Calculation` и не попадает в metric score без нового доказанного fact.
- `workflows/startup/ports.py`, `graph.py`, `nodes/metrics.py`, `runtime.py`, `bootstrap/container.py` и report wiring меняет только Wave 3 integration owner.

## Task 2A.1 — Lock the Readiness Domain Contract

**Files:**
- Create: `src/due_diligence_agent/domain/startup/readiness.py`
- Create: `tests/unit/domain/test_startup_readiness.py`

- [x] Write RED tests for `StartupMetricPack`, `StartupReadinessDimension`, `StartupAdaptiveQuestion` and `StartupReadinessSnapshot`.
- [x] Require schema/version `startup_readiness@1`, deterministic UUID/hash, frozen/extra-forbid Pydantic models, normalized metric ids, unique dimension/question ids and at most three questions.
- [x] Require readiness states `ready|provisional|blocked`, source profile id/hash/revision and calculation/diagnostic identity inputs.
- [x] Run RED:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/domain/test_startup_readiness.py
```

Expected RED: collection fails because `domain.startup.readiness` does not exist.

- [x] Implement the minimum immutable models and canonical JSON/hash/id derivation using the same normalization style as `domain/startup/profile.py`.
- [x] Run GREEN with the same command; expected result is all tests passing.
- [x] Import the contract from its explicit module so Wave 1 does not collide with Queue 2B over `domain/startup/__init__.py`.
- [x] Run `uv run ruff check` and `uv run mypy --strict` on the changed source file.
- [x] Commit: `feat: add startup readiness domain contract`.

## Task 2A.2 — Select a Deterministic Metric Pack

**Files:**
- Create: `src/due_diligence_agent/application/services/startup_readiness_service.py`
- Create: `tests/unit/application/test_startup_readiness_service.py`

- [x] Write RED cases for subscription SaaS, marketplace/transactional, pre-revenue and unknown-model profiles.
- [x] Define explicit allowlisted packs over the 16 metric ids in `domain/metrics/startup.py`; never parse arbitrary profile text as a metric id.
- [x] Use `business_model`, `pricing_revenue_model`, `stage` and normalized `metric_pack_candidates` only as signals. Invalid candidates are ignored and recorded as safe diagnostic codes.
- [x] Require stable pack selection across field order and profile restart.
- [x] Run RED:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/application/test_startup_readiness_service.py -k metric_pack
```

Expected RED: import failure for `StartupReadinessService`.

- [x] Implement `select_metric_pack(profile: StartupProfile) -> StartupMetricPack` with conservative defaults and explicit selection reasons.
- [x] Run GREEN with the same command.
- [x] Commit: `feat: select deterministic startup metric packs`.

## Task 2A.3 — Evaluate Readiness Separately from Confidence

**Files:**
- Modify: `src/due_diligence_agent/application/services/startup_readiness_service.py`
- Modify: `tests/unit/application/test_startup_readiness_service.py`

- [x] Write RED tests proving that source confidence alone cannot make a dimension ready, contradictions prevent ready status, calculated metrics preserve formula/input/period/warning lineage, and missing inputs never create values.
- [x] Define versioned dimensions for `business_model`, `traction`, `unit_economics`, `market_evidence`, `gtm_evidence` and `risk_disclosure` with method codes, not free-form reasoning.
- [x] Implement `evaluate(profile, metric_diagnostics, calculation_ids) -> StartupReadinessSnapshot`.
- [x] Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/application/test_startup_readiness_service.py -k readiness
```

Expected GREEN: deterministic snapshot/hash, explicit blocked/provisional reasons and zero invented numeric values.
- [x] Commit: `feat: evaluate evidence-backed startup readiness`.

## Task 2A.4 — Generate at Most Three Adaptive Questions

**Files:**
- Modify: `src/due_diligence_agent/application/services/startup_readiness_service.py`
- Modify: `tests/unit/application/test_startup_readiness_service.py`

- [x] Write RED tests with more than three gaps, duplicate missing inputs and contradictory fields.
- [x] Implement `priority_questions(snapshot) -> tuple[StartupAdaptiveQuestion, ...]` using templates keyed by stable gap/reason codes; do not send profile text to an LLM.
- [x] Questions must name the missing decision/input, explain the affected metric/readiness dimension, and contain no file/path/evidence locator content.
- [x] Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/application/test_startup_readiness_service.py -k questions
```

Expected GREEN: zero to three unique questions in stable priority order.
- [x] Commit: `feat: add bounded adaptive founder questions`.

## Task 2A.5 — Lock the Controlled Python Boundary

**Files:**
- Create: `src/due_diligence_agent/ports/startup_calculation_assist.py`
- Create: `tests/unit/llm/test_startup_calculation_assist.py`

- [x] Write RED protocol/policy tests for default disabled, explicit disclosure+budget requirement, network-disabled execution and provisional output with empty canonical calculation ids.
- [x] Define a startup-specific wrapper contract around existing `CodeInterpreterPort.run_public_analysis`; do not modify the proven OpenAI adapter in this task.
- [x] Reject code/templates outside an allowlist and artifacts that are not redacted/minimized and approved for egress.
- [x] Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/llm/test_startup_calculation_assist.py tests/unit/llm/test_code_interpreter.py
```

Expected GREEN: existing Code Interpreter regression stays green; no provider call occurs when disabled or denied.
- [x] Commit: `feat: define controlled startup calculation assist port`.

## Task 2A.6 — Wave 3 Integration Handoff

**Integration owner files only:**
- Modify: `src/due_diligence_agent/workflows/startup/ports.py`
- Modify: `src/due_diligence_agent/workflows/startup/nodes/metrics.py`
- Modify: `src/due_diligence_agent/workflows/startup/graph.py`
- Modify: `src/due_diligence_agent/workflows/startup/runtime.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Modify: `src/due_diligence_agent/application/services/startup_report_service.py`
- Modify: `tests/graph/test_startup_workflow.py`
- Modify: `tests/unit/reporting/test_startup_report_snapshot.py`

- [x] Add a profile-aware metric workflow input without changing legacy default behavior.
- [x] Persist readiness snapshot through a repository/runtime artifact; checkpoint contains only id/hash/revision.
- [x] Recompute readiness when Gate 3 invalidates profile facts/calculations; preserve unrelated artifacts.
- [x] Bind pack, diagnostics, questions and readiness identity into the canonical startup report.
- [x] Keep controlled Python disabled by default and outside the deterministic frozen Gate D path.
- [x] Run focused integration:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/metrics/test_startup_metrics.py tests/unit/application/test_startup_readiness_service.py tests/graph/test_startup_workflow.py tests/unit/reporting/test_startup_report_snapshot.py
```

Expected GREEN: pack-specific deterministic calculations, stable readiness/questions, Gate 2 denial with zero external calls, Gate 3 recompute correctness and report hash binding.
- [x] Commit: `feat: integrate startup readiness into analysis and report`.
