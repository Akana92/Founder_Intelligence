# Founder Case Copilot Scenario Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a user-testable same-case flow from an idea-only startup document through adaptive Copilot questions, founder-approved assumptions, consented public benchmarks, three deterministic metric scenarios, project advice and a downloadable GTM launch pack.

**Architecture:** Extend the current modular monolith and Ports-and-Adapters boundaries. New typed Copilot, assumption, scenario, research-job and asset models reference the existing canonical `case_id`, `data_revision`, Evidence Ledger and recalculation boundary; they never create a parallel case. LLM calls are optional orchestration/explanation, while validation, privacy classification, provenance and arithmetic remain deterministic.

**Tech Stack:** Python 3.13, Pydantic, FastAPI, LangGraph where already used, local JSON repositories, pytest, Next.js 16.3.0, React 19.2.8, TypeScript 5.9.3, Node TAP tests.

**Spec:** `docs/superpowers/specs/2026-08-22-founder-case-copilot-v1-design.md` plus `docs/superpowers/specs/2026-08-22-founder-case-copilot-scenario-metrics-addendum.md`

## Global Constraints

- Read `docs/handoffs/2026-08-21-founder-dynamic-safe-pause.md` and `docs/verification/2026-08-21-founder-dynamic-analysis-verification.md` before editing.
- Preserve the current dirty `main` working tree. Do not reset, clean, checkout or revert user-owned WIP.
- Do not commit, push, deploy or publish unless the owner explicitly requests it. Because the baseline is a shared dirty tree, each task ends with test evidence and `git diff --check` instead of an automatic commit.
- Read `frontend/founder/AGENTS.md` and the relevant local `frontend/founder/node_modules/next/dist/docs/` guide before frontend edits.
- Add no new dependency unless existing libraries cannot satisfy an accepted contract and the owner authorizes the dependency.
- One `case_id` owns one Copilot thread, one current assumption ledger, one selected scenario and its versioned assets.
- Every mutation requires `expected_case_revision` and `idempotency_key`, fails closed on stale revision and uses the existing same-case recalculation boundary.
- `source_fact`, `founder_statement`, `public_benchmark`, `deterministic_calculation`, `ai_scenario` and `contradiction` remain distinct in domain, API and UI.
- Public research must reject private startup values before a provider call. Consent is job-specific and never inferred from chat text.
- LLM arithmetic is forbidden. Scenario calculations use `Decimal` and deterministic Python services.
- Generated launch documents and working materials are drafts, not evidence.
- A visible CTA must have a real handler and observable result, be disabled with an exact reason, or be hidden by policy.
- Use new test ports and new artifact directories for every live browser run.

## Planned File Structure

### Backend domain and ports

- Create `src/due_diligence_agent/domain/startup/case_intake.py` for stage, provenance, registry requirements, founder statements and validation plans.
- Create `src/due_diligence_agent/domain/startup/scenario.py` for typed ranges, scenario inputs, derived metrics, scenario sets and selection.
- Create `src/due_diligence_agent/domain/startup/copilot.py` for questions, messages, action cards, thread state and system deltas.
- Create `src/due_diligence_agent/domain/startup/assets.py` for versioned draft asset metadata and launch-pack sections.
- Modify `src/due_diligence_agent/ports/repositories.py` with focused repository protocols.
- Create `src/due_diligence_agent/adapters/local_storage/case_copilot_repositories.py` for restart-safe JSON persistence without growing the existing repository file further.

### Backend application and API

- Create `src/due_diligence_agent/application/services/case_fact_intake_service.py`.
- Create `src/due_diligence_agent/application/services/case_question_service.py`.
- Create `src/due_diligence_agent/application/services/startup_scenario_service.py`.
- Create `src/due_diligence_agent/application/services/case_copilot_service.py`.
- Create `src/due_diligence_agent/application/services/case_research_job_service.py`.
- Create `src/due_diligence_agent/application/services/case_asset_service.py`.
- Create `src/due_diligence_agent/application/case_copilot_contracts.py` for founder-safe request/response models.
- Create `src/due_diligence_agent/presentation/api/routers/startup_copilot.py` and include it from `src/due_diligence_agent/presentation/api/app.py`.
- Modify `src/due_diligence_agent/presentation/api/dependencies.py` and `src/due_diligence_agent/bootstrap/container.py` for dependency wiring.
- Modify `src/due_diligence_agent/application/services/startup_metric_service.py`, `startup_readiness_service.py`, `startup_gtm_service.py` and `startup_report_service.py` only at their typed extension seams.

### Founder frontend

- Extend `frontend/founder/lib/contracts.ts` and `frontend/founder/lib/founder-api-client.ts`.
- Create `frontend/founder/lib/scenario-presentation.ts` and `frontend/founder/lib/scenario-contracts.test.ts`.
- Create `frontend/founder/components/case-copilot-panel.tsx` and `case-copilot-panel.module.css`.
- Create `frontend/founder/components/case-question-card.tsx`.
- Create `frontend/founder/components/founder-scenario-metrics.tsx`.
- Create `frontend/founder/components/founder-launch-pack.tsx`.
- Extend `founder-workspace-orchestrator.ts`, `founder-workspace-controller.tsx`, `founder-shell.tsx`, existing advisor/analysis/strategy pages and their tests.
- Add Next API proxy routes under `frontend/founder/app/api/startup/cases/[caseId]/` for Copilot state/messages, facts, assumptions, scenarios, research jobs and assets.

---

### Task 0: Freeze The Idea-Only Acceptance Contract

**Files:**
- Create: `tests/fixtures/startup_case_copilot_v1/cases/idea_inventory/brief.txt`
- Create: `tests/fixtures/startup_case_copilot_v1/cases/idea_clinic/brief.txt`
- Create: `tests/fixtures/startup_case_copilot_v1/expected_contracts.json`
- Create: `tests/api/test_startup_case_copilot_contract.py`
- Modify: `tests/api/test_startup_pdf_case_differentiation.py`

**Interfaces:**
- Consumes: current create/upload/profile/advisor/metrics/report endpoints.
- Produces: two anti-hardcode fixtures and executable owner acceptance assertions used by every later task.

- [ ] **Step 1: Write two genuinely different idea-only fixtures**

`idea_inventory/brief.txt` describes a Central Asian inventory-planning SaaS with a target launch window but no revenue or expense values. `idea_clinic/brief.txt` describes a clinic follow-up service with different buyer, user, geography, pricing hypothesis and launch constraints. Do not include hidden expected answers in either document.

- [ ] **Step 2: Write the RED API journey**

```python
def test_idea_only_cases_get_distinct_questions_and_scenario_contracts(client):
    inventory = upload_idea_case(client, "idea_inventory")
    clinic = upload_idea_case(client, "idea_clinic")

    inventory_state = client.get(f"/api/v1/startup/cases/{inventory}/copilot/state")
    clinic_state = client.get(f"/api/v1/startup/cases/{clinic}/copilot/state")

    assert inventory_state.status_code == 200
    assert clinic_state.status_code == 200
    assert inventory_state.json()["stage"] == "idea"
    assert clinic_state.json()["stage"] == "idea"
    assert inventory_state.json()["next_question"] != clinic_state.json()["next_question"]
    assert inventory_state.json()["fact_coverage"] != inventory_state.json()["scenario_completeness"]
```

Add negative assertions that no response contains an actual MRR, ARR, burn, cash or customer count invented from the idea document.

- [ ] **Step 3: Run the RED test and preserve the failure reason**

```powershell
.venv\Scripts\python.exe -B -m pytest tests/api/test_startup_case_copilot_contract.py -q -p no:cacheprovider
```

Expected: failure because `/copilot/state` and the scenario contract do not exist. A failure caused only by a malformed fixture must be corrected before production work.

- [ ] **Step 4: Lock privacy and anti-promotion expectations**

Add tests asserting `founder_statement`, `public_benchmark` and `ai_scenario` never parse as `source_fact`, and that a public-research request for private MRR is rejected before the fake provider records a call.

- [ ] **Step 5: Record the baseline checkpoint**

Run `git diff --check`. Record the exact RED command and expected failure in `docs/handoffs/2026-08-22-case-copilot-v1-new-chat-prompt.md` under a new `Execution progress` section; do not claim implementation complete.

### Task 1: Add Provenance, Assumption, Scenario And Copilot Domain Models

**Files:**
- Create: `src/due_diligence_agent/domain/startup/case_intake.py`
- Create: `src/due_diligence_agent/domain/startup/scenario.py`
- Create: `src/due_diligence_agent/domain/startup/copilot.py`
- Create: `src/due_diligence_agent/domain/startup/assets.py`
- Create: `tests/unit/domain/test_case_intake.py`
- Create: `tests/unit/domain/test_startup_scenario.py`
- Create: `tests/unit/domain/test_case_copilot.py`

**Interfaces:**
- Produces: `CaseValueKind`, `CaseStage`, `CaseFactRequirement`, `FounderStatement`, `ScenarioRange`, `ScenarioInput`, `ScenarioMetric`, `StartupScenarioSet`, `CopilotQuestion`, `CopilotAction`, `CopilotMessage`, `CopilotThread`, `CaseAssetDraft`.
- Later tasks must import these exact names rather than recreating dict schemas.

- [ ] **Step 1: Write model validation tests**

```python
def test_ai_scenario_cannot_claim_source_fact() -> None:
    with pytest.raises(ValidationError, match="scenario provenance"):
        ScenarioInput(
            input_key="monthly_price",
            value_range=ScenarioRange(lower=Decimal("30000"), upper=Decimal("50000")),
            unit="KZT/month",
            provenance=CaseValueKind.SOURCE_FACT,
            source_refs=(),
            dependency_refs=(),
            confidence="low",
            rationale="Copilot estimate",
            validation_plan="Run five paid pilots",
            acceptance="proposed",
        )
```

Cover non-negative ranges, `lower <= upper`, required currency/period, source refs for `source_fact` and `public_benchmark`, dependency refs for `deterministic_calculation`, same-case/revision ownership and immutable message history.

- [ ] **Step 2: Run model tests to prove RED**

```powershell
.venv\Scripts\python.exe -B -m pytest tests/unit/domain/test_case_intake.py tests/unit/domain/test_startup_scenario.py tests/unit/domain/test_case_copilot.py -q -p no:cacheprovider
```

Expected: import failure for the new models.

- [ ] **Step 3: Implement the exact enums and immutable models**

```python
class CaseValueKind(StrEnum):
    SOURCE_FACT = "source_fact"
    FOUNDER_STATEMENT = "founder_statement"
    PUBLIC_BENCHMARK = "public_benchmark"
    DETERMINISTIC_CALCULATION = "deterministic_calculation"
    AI_SCENARIO = "ai_scenario"
    CONTRADICTION = "contradiction"


class CaseStage(StrEnum):
    IDEA = "idea"
    FIRST_SALES = "first_sales"
    GROWTH = "growth"
```

Use frozen Pydantic models with `extra="forbid"`. Put scenario arithmetic nowhere in these models; validation only.

- [ ] **Step 4: Run GREEN domain tests**

Run the Task 1 pytest command. Expected: all Task 1 tests pass.

- [ ] **Step 5: Checkpoint**

Run `.venv\Scripts\python.exe -m ruff check` on the four new source files and three tests, followed by `git diff --check`.

### Task 2: Persist One Same-Case Ledger, Thread, Research Job And Asset Registry

**Files:**
- Modify: `src/due_diligence_agent/ports/repositories.py`
- Create: `src/due_diligence_agent/adapters/local_storage/case_copilot_repositories.py`
- Create: `tests/unit/adapters/test_case_copilot_repositories.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`

**Interfaces:**
- Produces repository protocols `CaseAssumptionRepository`, `CaseScenarioRepository`, `CaseCopilotThreadRepository`, `CaseResearchJobRepository`, `CaseAssetRepository`.
- Each protocol exposes `get_current(case_id)`, `save(value, expected_revision, idempotency_key)` and type-specific list/get operations. Repository keys include `case_id`; cross-case reads fail closed.

- [ ] **Step 1: Write restart, idempotency and cross-case RED tests**

```python
def test_thread_survives_repository_recreation(tmp_path: Path) -> None:
    first = LocalCaseCopilotThreadRepository(tmp_path)
    first.save(make_thread(case_id=CASE_A), expected_revision=1, idempotency_key="msg-1")

    second = LocalCaseCopilotThreadRepository(tmp_path)
    restored = second.get_current(CASE_A)

    assert restored.messages[-1].message_id == "msg-1"
    with pytest.raises(CaseScopeError):
        second.get_for_case(CASE_B, restored.thread_id)
```

Also prove duplicate idempotency keys do not append a second message and stale revisions do not write partial JSON.

- [ ] **Step 2: Run repository tests to prove RED**

```powershell
.venv\Scripts\python.exe -B -m pytest tests/unit/adapters/test_case_copilot_repositories.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement atomic local JSON repositories**

Write to a temporary sibling, flush, then replace the target file. Persist under the configured case data root, not under frontend state. Never persist raw external-provider payloads or unredacted chat context.

- [ ] **Step 4: Wire repositories through the existing container**

Create one instance per data root and inject it into later services. Do not create a second case-revision store.

- [ ] **Step 5: Run GREEN and static checks**

Run the Task 2 pytest command, targeted Ruff, targeted mypy and `git diff --check`.

### Task 3: Implement Registry-Driven Intake And Adaptive Question Ranking

**Files:**
- Create: `src/due_diligence_agent/application/services/case_fact_intake_service.py`
- Create: `src/due_diligence_agent/application/services/case_question_service.py`
- Modify: `src/due_diligence_agent/application/startup_advisor_recalculation.py`
- Modify: `src/due_diligence_agent/application/services/startup_advisor_api_service.py`
- Create: `tests/unit/application/test_case_fact_intake_service.py`
- Create: `tests/unit/application/test_case_question_service.py`
- Modify: `tests/unit/application/test_startup_advisor_api_service.py`

**Interfaces:**
- `CaseQuestionService.next_question(case_id: UUID, *, page_context: str, focus_key: str | None) -> CopilotQuestion | None`.
- `CaseFactIntakeService.save_founder_statement(command: SaveFounderStatementCommand) -> CaseMutationDelta`.
- `CaseMutationDelta` contains old/new revision, changed keys, stale scenario ids, metric/readiness before/after and the next question.

- [ ] **Step 1: Write RED ranking tests**

```python
def test_idea_stage_ranks_buyer_before_actual_churn() -> None:
    question = service.next_question(IDEA_CASE, page_context="overview", focus_key=None)
    assert question.requirement_key == "buyer"
    assert "churn" not in question.unlocks
```

Cover page focus, contradictions taking priority, `не знаю`, manual-only private values and public-researchable market context.

- [ ] **Step 2: Write RED intake tests**

Assert field-level errors list missing amount, scale, currency, period and source. Assert invalid input returns the original draft. Assert accepted founder data is stored as `founder_statement`, advances the canonical revision exactly once and invalidates only dependent scenarios/reports.

- [ ] **Step 3: Run RED tests**

```powershell
.venv\Scripts\python.exe -B -m pytest tests/unit/application/test_case_fact_intake_service.py tests/unit/application/test_case_question_service.py tests/unit/application/test_startup_advisor_api_service.py -q -p no:cacheprovider
```

- [ ] **Step 4: Implement the canonical requirement registry and services**

The registry covers `problem`, `solution`, `icp`, `buyer`, `purchase_trigger`, `pricing_revenue_model`, `monthly_price`, `launch_date`, `team_capacity`, `available_budget`, `channel`, `funnel`, `revenue`, `mrr`, `burn`, `cash_balance`, `cogs`, `gross_margin`, `cac`, `churn`, `retention`, `customer_count` and `time_to_value`. Each entry defines input schema, allowed answer modes, privacy class, metric dependencies, stage relevance and validation copy.

- [ ] **Step 5: Run GREEN and regression selection**

Run the Task 3 tests plus `tests/api/test_startup_pdf_case_differentiation.py`. Run `git diff --check`.

### Task 4: Build Conservative, Base And Optimistic Scenarios Deterministically

**Files:**
- Create: `src/due_diligence_agent/application/services/startup_scenario_service.py`
- Modify: `src/due_diligence_agent/application/services/startup_metric_service.py`
- Modify: `src/due_diligence_agent/application/services/startup_readiness_service.py`
- Create: `tests/unit/application/test_startup_scenario_service.py`
- Modify: `tests/unit/metrics/test_startup_metrics.py`
- Modify: `tests/unit/application/test_startup_readiness_service.py`

**Interfaces:**
- `StartupScenarioService.build(case_id: UUID, *, expected_case_revision: int, idempotency_key: str) -> StartupScenarioSet`.
- `StartupScenarioService.select(case_id: UUID, scenario_key: Literal["conservative", "base", "optimistic"], *, expected_case_revision: int, idempotency_key: str) -> ScenarioSelectionDelta`.
- `StartupMetricService.calculate_scenario(metric_key: str, inputs: Mapping[str, ScenarioRange]) -> ScenarioMetric`.

- [ ] **Step 1: Write formula and provenance RED tests**

```python
def test_base_mrr_and_arr_ranges_are_decimal_calculations() -> None:
    result = service.build(CASE_ID, expected_case_revision=2, idempotency_key="build-2")
    base = result.scenarios["base"]
    assert base.metrics["mrr"].value_range == ScenarioRange(
        lower=Decimal("1400000"), upper=Decimal("2000000")
    )
    assert base.metrics["arr"].dependency_refs == (base.metrics["mrr"].metric_id,)
    assert base.metrics["arr"].provenance is CaseValueKind.DETERMINISTIC_CALCULATION
```

Test range multiplication/division, division-by-zero, negative burn, runway only for positive net burn, LTV only with eligible inputs, stale scenario invalidation and no `float` in serialized values.

- [ ] **Step 2: Run RED tests**

```powershell
.venv\Scripts\python.exe -B -m pytest tests/unit/application/test_startup_scenario_service.py tests/unit/metrics/test_startup_metrics.py tests/unit/application/test_startup_readiness_service.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement scenario construction and formulas**

Use accepted founder statements first, then cited public benchmark ranges, then bounded AI-scenario defaults. Never synthesize an actual historical value. Record every input and formula dependency. Missing inputs create a gap plus `what_would_confirm`, not zero.

- [ ] **Step 4: Separate readiness from scenario completeness**

Keep evidence-based readiness/fact coverage unchanged in meaning. Add `scenario_completeness` from accepted planning inputs and executable formulas. An idea case may have low fact coverage and non-zero scenario completeness.

- [ ] **Step 5: Run GREEN, regression and static checks**

Run the Task 4 tests, `tests/unit/reporting/test_startup_report_snapshot.py`, targeted Ruff/mypy and `git diff --check`.

### Task 5: Add Typed Founder API Commands And Same-Case State Projection

**Files:**
- Create: `src/due_diligence_agent/application/case_copilot_contracts.py`
- Create: `src/due_diligence_agent/application/services/case_copilot_service.py`
- Create: `src/due_diligence_agent/presentation/api/routers/startup_copilot.py`
- Modify: `src/due_diligence_agent/presentation/api/app.py`
- Modify: `src/due_diligence_agent/presentation/api/dependencies.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Modify: `tests/api/test_startup_case_copilot_contract.py`

**Interfaces:**
- `GET /api/v1/startup/cases/{case_id}/copilot/state`.
- `GET /api/v1/startup/cases/{case_id}/copilot/thread`.
- `POST /api/v1/startup/cases/{case_id}/copilot/messages`.
- `POST /api/v1/startup/cases/{case_id}/facts`.
- `POST /api/v1/startup/cases/{case_id}/assumptions`.
- `GET /api/v1/startup/cases/{case_id}/scenarios`.
- `POST /api/v1/startup/cases/{case_id}/scenarios/selection`.

- [ ] **Step 1: Freeze strict API models with contract tests**

```python
class SaveFounderStatementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_key: str
    value: str
    unit: str | None = None
    currency: str | None = None
    scale: str | None = None
    period: str | None = None
    declared_source: str
    note: str | None = None
    expected_case_revision: StrictInt
    idempotency_key: str
```

Require response models to expose provenance, formula/dependencies, `what_would_confirm`, before/after delta, revision and action availability. Unknown fields fail with 422; stale revisions fail with 409 before mutation.

- [ ] **Step 2: Run API RED tests**

Run `tests/api/test_startup_case_copilot_contract.py`. Expected: missing router/service failures.

- [ ] **Step 3: Implement state aggregation and commands**

`CaseCopilotService` reads existing profile, contradictions, readiness, metrics, selected scenario and thread for the same case/revision. It delegates mutations to intake/scenario services and appends a system event only after successful recalculation.

- [ ] **Step 4: Prove stale, idempotent and cross-case behavior**

Add API tests for 409 stale revision, duplicate idempotency key returning the original result, foreign scenario/thread ids returning 404/409 and no report/evidence mutation on validation failure.

- [ ] **Step 5: Run GREEN API selection**

```powershell
.venv\Scripts\python.exe -B -m pytest tests/api/test_startup_case_copilot_contract.py tests/api/test_startup_api.py tests/api/test_startup_pdf_case_differentiation.py -q -p no:cacheprovider
```

Run targeted Ruff/mypy and `git diff --check`.

### Task 6: Implement Safe Benchmark Research With Explicit Consent

**Files:**
- Create: `src/due_diligence_agent/application/services/case_research_job_service.py`
- Modify: `src/due_diligence_agent/application/services/startup_advisor_research_service.py`
- Modify: `src/due_diligence_agent/application/services/startup_advisor_api_service.py`
- Modify: `src/due_diligence_agent/presentation/api/routers/startup_copilot.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Create: `tests/unit/application/test_case_research_job_service.py`
- Modify: `tests/unit/application/test_startup_advisor_research_service.py`
- Modify: `tests/privacy/test_startup_redaction.py`
- Modify: `tests/unit/application/test_startup_live_research_policy.py`

**Interfaces:**
- `POST /api/v1/startup/cases/{case_id}/research/plans` creates no provider call.
- `POST /api/v1/startup/cases/{case_id}/research/jobs` requires matching plan/hash/revision and `consent_public_research=true`.
- `GET /api/v1/startup/cases/{case_id}/research/jobs/{job_id}` returns status, citations, benchmark entries and changed blocks.

- [ ] **Step 1: Write privacy-first RED tests**

```python
def test_private_mrr_research_is_blocked_before_provider_call() -> None:
    response = service.prepare_plan(case_id=CASE_ID, focus="mrr", expected_case_revision=2)
    assert response.status == "blocked"
    assert response.manual_only_keys == ("mrr",)
    assert fake_provider.calls == []
```

Cover no call before consent, expired plan, stale revision, mismatched hash, prompt sanitization, cited benchmark provenance and unconfigured provider returning `deferred` without evidence mutation.

- [ ] **Step 2: Run RED tests**

Run the four Task 6 test files.

- [ ] **Step 3: Implement plan/job state machine**

Allowed focus keys are `market`, `icp`, `competitors`, `alternatives`, `channels`, `public_pricing_analogs` and `unit_economics_benchmarks`. Convert provider results into `public_benchmark` entries with URL, publisher, publication/retrieval date, as-of, source class and confidence. Keep raw provider text out of founder state.

- [ ] **Step 4: Connect completed benchmark jobs to scenarios**

A completed job advances the case revision only when eligible new benchmark entries are accepted into the external-context ledger. It invalidates dependent scenario sets and records before/after; it never closes a private factual gap.

- [ ] **Step 5: Run GREEN, privacy and regression checks**

Run Task 6 tests plus `tests/privacy/test_ai_egress.py`, targeted Ruff/mypy and `git diff --check`.

### Task 7: Persist Copilot Messages And Execute Typed Actions

**Files:**
- Modify: `src/due_diligence_agent/application/services/case_copilot_service.py`
- Modify: `src/due_diligence_agent/presentation/api/routers/startup_copilot.py`
- Create: `tests/unit/application/test_case_copilot_service.py`
- Modify: `tests/api/test_startup_case_copilot_contract.py`

**Interfaces:**
- `CaseCopilotService.post_message(case_id, command) -> CopilotTurnResponse`.
- Action types: `open_fact_input`, `open_document_upload`, `prepare_public_research`, `explain_metric`, `navigate`, `prepare_asset`, `review_improvements`.
- Each action has `available`, `requires_input`, `requires_consent` or `blocked`, an exact reason, typed payload and effect preview.

- [ ] **Step 1: Write RED tests for distinct case context and fallback**

Assert the two idea fixtures get different questions/advice, raw documents and local paths never enter an external prompt, restart restores history and an unavailable LLM still returns deterministic question/action cards.

- [ ] **Step 2: Run RED tests**

```powershell
.venv\Scripts\python.exe -B -m pytest tests/unit/application/test_case_copilot_service.py tests/api/test_startup_case_copilot_contract.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement bounded context and deterministic action selection**

Build the LLM context only from founder-safe profile projection, current gaps, provenance summaries and allowed evidence refs. Parse provider output into typed text/advice; discard unknown actions. Deterministic ranking remains the source for actionable next steps.

- [ ] **Step 4: Append system events after successful domain changes**

Events report revision, changed fields, metric/readiness/scenario before/after and links to evidence or research sources. Failed actions append no success event.

- [ ] **Step 5: Run GREEN and static checks**

Run Task 7 tests, targeted Ruff/mypy and `git diff --check`.

### Task 8: Add Strict Frontend Contracts, Proxies And Workspace Orchestration

**Files:**
- Modify: `frontend/founder/lib/contracts.ts`
- Modify: `frontend/founder/lib/founder-api-client.ts`
- Create: `frontend/founder/lib/scenario-contracts.test.ts`
- Create: `frontend/founder/lib/scenario-presentation.ts`
- Create: `frontend/founder/lib/scenario-presentation.test.ts`
- Modify: `frontend/founder/components/founder-workspace-orchestrator.ts`
- Modify: `frontend/founder/components/founder-workspace-controller.tsx`
- Modify: `frontend/founder/components/founder-workspace-controller.test.ts`
- Create: corresponding Next proxy `route.ts` files under `frontend/founder/app/api/startup/cases/[caseId]/`.
- Modify: `frontend/founder/package.json` to include the two new test files in the existing `npm test` chain.

**Interfaces:**
- Produces strict parsers for Copilot state, assumption ledger, scenario set, metric provenance, coverage and launch-pack metadata.
- Extends `FounderWorkspaceSnapshot` with `copilotState`, `assumptions`, `scenarios`, `selectedScenario`, `scenarioCompleteness` and `launchPack`.

- [ ] **Step 1: Read local Next.js route-handler documentation**

Read the relevant files under `frontend/founder/node_modules/next/dist/docs/` for Next 16 route handlers and caching. Record the selected guide path in the progress note.

- [ ] **Step 2: Write strict parser RED tests**

```typescript
assert.throws(
  () => parseScenarioMetric({ value: 1200000, provenance: "source_fact", source_refs: [] }),
  /source refs/,
);
```

Reject unknown provenance, malformed ranges, missing revision, cross-case ids and active actions without typed payload/result.

- [ ] **Step 3: Implement parsers, client methods and transparent proxies**

Every API response is parsed before state changes. Proxies preserve backend status codes and founder-safe error codes; they do not synthesize success payloads.

- [ ] **Step 4: Extend orchestration with same-case lineage checks**

Load Copilot state after a profile exists, scenarios after statements/benchmarks exist and the launch pack only for its recorded revision/selected scenario. A stale response is discarded and refetched; it is never merged into the current workspace.

- [ ] **Step 5: Run frontend GREEN checks**

```powershell
npm --prefix frontend/founder test
npm --prefix frontend/founder run typecheck
npm --prefix frontend/founder run lint
```

Run `git diff --check`.

### Task 9: Implement Persistent Copilot, Stage-Aware Metrics And Working Actions In The UI

**Files:**
- Create: `frontend/founder/components/case-copilot-panel.tsx`
- Create: `frontend/founder/components/case-copilot-panel.module.css`
- Create: `frontend/founder/components/case-question-card.tsx`
- Create: `frontend/founder/components/founder-scenario-metrics.tsx`
- Modify: `frontend/founder/components/founder-shell.tsx`
- Modify: `frontend/founder/components/founder-advisor-pages.tsx`
- Modify: `frontend/founder/components/founder-advisor-pages.test.ts`
- Modify: `frontend/founder/components/founder-analysis-pages.tsx`
- Modify: `frontend/founder/components/founder-analysis-pages.test.ts`
- Modify: `frontend/founder/lib/chart-presentation.ts`
- Modify: `frontend/founder/lib/chart-presentation.test.ts`
- Modify: `frontend/founder/lib/readiness-presentation.ts`
- Modify: `frontend/founder/lib/readiness-presentation.test.ts`

**Interfaces:**
- `CaseCopilotPanel` receives the canonical thread/state and callbacks; it owns no independent case facts.
- `FounderScenarioMetrics` receives a parsed scenario set and selected key; selection callback calls the backend before updating canonical state.

- [ ] **Step 1: Write component RED assertions**

Cover idea-stage route title, one prioritized question, persisted draft, valid answer modes, explicit public-research consent, scenario selector, formula/provenance drawer, fact coverage vs scenario completeness and every CTA handler/blocker.

- [ ] **Step 2: Run RED frontend suite**

```powershell
npm --prefix frontend/founder test
```

- [ ] **Step 3: Implement the persistent right rail/drawer**

Header and contextual AI buttons open the same case thread. Desktop uses a right rail without horizontal overflow; smaller supported widths use a drawer. Do not add a second advisor page with independent state.

- [ ] **Step 4: Implement stage-aware metric presentation**

Actual, calculated, benchmark, founder statement, AI scenario and contradiction get distinct text labels/badges. Unknown actuals show a scenario range or exact missing dependency with a working action; they never render as unexplained zero.

- [ ] **Step 5: Run GREEN frontend verification**

Run `npm test`, `npm run typecheck`, `npm run lint` and `npm run build` from `frontend/founder`. If the sandbox produces the known Windows `spawn EPERM`, rerun only the build with the required escalation and record it. Run `git diff --check`.

### Task 10: Generate Project Advice And A Versioned GTM Launch Pack

**Files:**
- Create: `src/due_diligence_agent/application/services/case_asset_service.py`
- Modify: `src/due_diligence_agent/application/services/startup_gtm_service.py`
- Modify: `src/due_diligence_agent/application/services/startup_report_service.py`
- Modify: `src/due_diligence_agent/presentation/api/routers/startup_copilot.py`
- Create: `tests/unit/application/test_case_asset_service.py`
- Modify: `tests/unit/application/test_startup_gtm_service.py`
- Modify: `tests/unit/reporting/test_startup_report_snapshot.py`
- Create: `frontend/founder/components/founder-launch-pack.tsx`
- Modify: `frontend/founder/components/founder-strategy-pages.tsx`
- Modify: `frontend/founder/components/founder-strategy-pages.test.ts`

**Interfaces:**
- `CaseAssetService.generate(case_id, asset_type, selected_scenario, expected_case_revision, idempotency_key) -> CaseAssetDraft`.
- Asset types include the base four plus `gtm_launch_pack`.
- `GET /assets`, `POST /assets` and `GET /assets/{asset_id}` expose preview/download metadata; downloads are founder-safe Markdown, and weekly funnel additionally supports CSV.

- [ ] **Step 1: Write RED content/provenance tests**

Assert the launch pack contains all twelve addendum sections, scenario comparison, sources, assumptions, limitations and 7/30/60/90 actions. Assert it is marked `draft`, references its case revision/selected scenario and never enters Evidence Ledger.

- [ ] **Step 2: Run RED backend and frontend tests**

Run `tests/unit/application/test_case_asset_service.py`, the GTM/report tests and `npm --prefix frontend/founder test`.

- [ ] **Step 3: Implement deterministic document assembly with optional LLM prose**

Section membership, tables, provenance appendix and metric values come from deterministic typed state. Optional LLM output may improve founder-safe prose and alternatives but cannot add unreferenced facts, change numbers or remove limitations.

- [ ] **Step 4: Wire real preview, regenerate and download actions**

Replace inert `Подготовить`, `Собрать рабочий пакет` and report actions with service calls, loading/error/success states and asset revision metadata. Disabled actions show the missing inputs.

- [ ] **Step 5: Run GREEN and document checks**

Run the Task 10 backend tests, full frontend checks, targeted Ruff/mypy and `git diff --check`.

### Task 11: Prove The Complete Journey, Privacy Boundary And Restart Behaviour

**Files:**
- Create: `tests/evaluation/test_founder_case_copilot_scenario_e2e.py`
- Modify: `tests/evaluation/test_founder_browser_evidence_orchestration.py`
- Modify: `scripts/smoke_founder_workspace.ps1`
- Create: `docs/verification/2026-08-22-founder-case-copilot-scenario-verification.md`
- Update: `docs/handoffs/2026-08-22-case-copilot-v1-new-chat-prompt.md`

**Interfaces:**
- Produces a fresh browser evidence bundle for both idea fixtures, a privacy/audit trace and a verification note that distinguishes deterministic/offline, configured-live and unverified capabilities.

- [ ] **Step 1: Add the full same-case browser journey**

```text
upload idea-only document
-> observe extracted profile and stage=idea
-> Copilot asks a document-specific question
-> accept founder statement
-> answer "не знаю" to a researchable market question
-> prepare plan without provider call
-> consent and complete cited deterministic research job
-> accept/rebuild three scenarios
-> select base scenario
-> observe metric/readiness/risk/action deltas
-> generate and download GTM launch pack
-> restart services and reload thread/scenario/asset
```

- [ ] **Step 2: Add second-fixture and hostile negative paths**

Prove different questions, benchmark scope, metric ranges and advice. Attempt private MRR research, stale selection, reused foreign asset id, malicious chat prompt, missing provider and duplicate idempotency key; verify no leakage or false success.

- [ ] **Step 3: Run targeted and expanded backend verification**

```powershell
.venv\Scripts\python.exe -B -m pytest tests/unit/domain/test_case_intake.py tests/unit/domain/test_startup_scenario.py tests/unit/domain/test_case_copilot.py tests/unit/application/test_case_fact_intake_service.py tests/unit/application/test_case_question_service.py tests/unit/application/test_startup_scenario_service.py tests/unit/application/test_case_research_job_service.py tests/unit/application/test_case_copilot_service.py tests/unit/application/test_case_asset_service.py tests/api/test_startup_case_copilot_contract.py tests/api/test_startup_pdf_case_differentiation.py tests/privacy/test_startup_redaction.py tests/evaluation/test_founder_case_copilot_scenario_e2e.py -q -p no:cacheprovider
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m mypy src\due_diligence_agent
```

- [ ] **Step 4: Run full frontend verification**

```powershell
npm --prefix frontend/founder test
npm --prefix frontend/founder run typecheck
npm --prefix frontend/founder run lint
npm --prefix frontend/founder run build
```

- [ ] **Step 5: Run fresh browser smoke on unused ports**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_founder_workspace.ps1 -Mode offline-fixture -CaptureScreenshots -RequirePdfUploadJourney -OfflineFixturePath output\pdf\nomadflow_ai_startup_test_business_plan_ru.pdf -ApiPort 8042 -WebPort 3042 -AdminPort 8542 -DataDir artifacts\runtime\founder-case-copilot-scenario-20260822-01\data -ScreenshotDir artifacts\runtime\founder-case-copilot-scenario-20260822-01\screens -BrowserEvidencePath artifacts\runtime\founder-case-copilot-scenario-20260822-01\browser-evidence.json -AdminTraceEvidencePath artifacts\runtime\founder-case-copilot-scenario-20260822-01\admin-trace.json
```

- [ ] **Step 6: Publish an evidence-based verification note**

Record exact commands/results, two-fixture differences, before/after values, source/provenance examples, privacy rejection proof, restart proof, screenshots and any live-provider gap. Do not label external research live-verified unless a real configured provider call succeeds with allowed egress and citations.

## Execution Stop Condition

Stop only when the two-fixture evidence proves this complete flow without hardcoded values:

```text
idea upload
-> stage-aware questions
-> founder statements / unknowns
-> consented public benchmarks
-> conservative / base / optimistic scenarios
-> deterministic metrics and separate coverage measures
-> project-specific strengths / weaknesses / risks / alternatives
-> versioned GTM launch pack
```

All provenance and privacy boundaries must pass fresh tests. Any missing credential or external egress is reported as a live-integration gap, not disguised as completion.
