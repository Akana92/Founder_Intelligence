# Founder Intelligence Case Copilot v1 - New Chat Prompt

Use this file as the first message in a fresh Codex chat.

```text
Работай в репозитории:
D:\Agents\Projects\Capstone N3

Задача: продолжить Capstone N3 / Founder Intelligence и реализовать Case Copilot v1 по уже принятому владельцем варианту 3.

Не начинай с нуля и не переделывай визуальный дизайн. Сначала прочитай текущие source-of-truth:

1. docs/superpowers/specs/2026-08-22-founder-case-copilot-v1-design.md
2. docs/superpowers/specs/2026-08-22-founder-case-copilot-scenario-metrics-addendum.md
3. docs/superpowers/plans/2026-08-22-founder-case-copilot-scenario-launch.md
4. docs/handoffs/2026-08-21-founder-dynamic-safe-pause.md
5. docs/superpowers/plans/2026-08-21-founder-dynamic-analysis-fixes.md
6. docs/superpowers/plans/2026-08-21-founder-intelligence-dynamic-analysis-roadmap.md
7. docs/verification/2026-08-21-founder-dynamic-analysis-verification.md
8. frontend/founder/AGENTS.md before any frontend edits

Current owner decision:

Если пользователь загрузил произвольный документ идеи стартапа без расчётов и метрик, продукт не должен блокировать его пустыми экранами. Case Copilot должен:

1. определить стадию проекта: idea, first sales, growth;
2. извлечь всё известное из документа как typed facts or gaps;
3. запустить адаптивный вопросник по самым важным пробелам;
4. принять ответы основателя как founder statement / assumption, not source_fact;
5. если пользователь не знает ответ, предложить безопасный публичный research только для market/ICP/GTM/benchmark context;
6. сгенерировать conservative/base/optimistic scenarios для неизвестных чисел;
7. пересчитать метрики детерминированно по формулам, а не через LLM arithmetic;
8. обновить UI: metrics, readiness, market, risks, action plan, report;
9. показать плюсы, минусы, риски и варианты действий;
10. собрать полноценный go-to-market / launch document with provenance appendix.

Critical product boundaries:

- Public research must not try to find private startup values: MRR, ARR, actual revenue, burn, cash balance, factual customer count, contracts, bank data, private invoices.
- Public research may only add public market context: ICP benchmarks, market size, competitors, pricing analogs, channel benchmarks, CAC/LTV benchmark ranges, adoption trends, regulatory or regional context.
- AI hypothesis never becomes confirmed fact automatically.
- Promotion to confirmed/source fact requires eligible evidence processed through the existing Evidence Ledger. A founder-confirmed value remains `founder_statement`; acceptance alone never promotes it to `source_fact`.
- Founder statement, public benchmark, deterministic calculation, AI scenario, and source fact must stay separate in data model and UI.
- Forecasts and assumptions must use ranges where possible. Do not show fake precision.
- A metric card must show value/range, type, formula, dependency inputs, period/unit, source refs, confidence, and what would confirm it.
- UI must separate fact coverage from scenario completeness.
- No active CTA without an observable result or explicit blocker reason.
- Preserve existing Founder visual language: dark premium workspace, pink accent, current layout direction. Fix behavior and information architecture, not the art direction.
- Do not reset, clean, checkout, or revert existing WIP. The worktree is dirty by design.
- Do not push, deploy, or publish without explicit user request.
- Never print secrets. `.env` may contain OpenAI/LangSmith keys; only report configured/unconfigured.

Architecture already decided:

- Keep modular monolith and Ports and Adapters style.
- Keep LangGraph orchestration where it already exists.
- Deterministic Python services own metric calculations.
- OpenAI is optional via OPENAI_API_KEY; deterministic fallback must remain.
- No custom ML training or local generative LLM is required for v1.
- Reuse existing case state, Evidence Ledger, same-case revisions, advisor recalculation boundary, research policies, privacy/audit services, and API/frontend contract patterns.

Existing foundations:

- Document parsing exists.
- Evidence ledger and contradiction handling exist.
- Metric/readiness/report paths exist.
- Optional OpenAI adapters exist.
- Same-case recalculation after advisor answers exists.

Main missing product behavior:

- unified persistent Case Copilot thread;
- stage-aware idea validation route;
- assumptions/scenario ledger;
- conservative/base/optimistic scenario engine;
- registry-driven manual fact intake;
- public research plan/consent/job flow wired to visible UI;
- generated GTM/launch document;
- UI before/after deltas after accepted answers or research results.

Implementation style:

Use strict TDD. For each slice:

1. write a focused failing test first;
2. run it and capture the expected RED failure;
3. implement the minimum production change;
4. run targeted GREEN tests;
5. run broader regression tests proportional to the touched surface;
6. update handoff/progress notes with fresh evidence.

Start with Slice 0 and Slice 1 from the spec, because they unlock the rest:

Slice 0 - Contract freeze and RED tests

- Add/extend backend contract tests for:
  - idea-only document produces stage=idea, extracted facts, and prioritized gaps;
  - private metrics are manual_only and cannot be public-researched;
  - public benchmark results are not source facts;
  - AI scenario values remain scenario/assumption typed;
  - stale revision/idempotency behavior is enforced.
- Add/extend frontend contract tests for:
  - metric/action cards expose real handlers or blocker reasons;
  - empty metrics show actionable fact intake/Copilot path, not dead UI;
  - scenario toggle displays conservative/base/optimistic values with provenance;
  - before/after delta appears after saved answer.

Slice 1 - Structured intake, scenario assumptions, and readiness

- Implement registry-driven fact requirements:
  - mrr, arr, revenue, burn, cash_balance, gross_margin, churn, retention, cac, customer_count, pricing_revenue_model, icp, channel, geography, time_to_value.
- Implement typed manual fact save:
  - value, unit/currency/scale, period/date, declared source, note, expected_case_revision, idempotency_key.
- Add assumption/scenario entries for unknown values:
  - conservative/base/optimistic;
  - reason;
  - source type: founder_statement, public_benchmark, AI_scenario;
  - validation plan.
- Recalculate dependent metrics deterministically:
  - ARR = MRR * 12 where MRR exists;
  - gross margin from revenue and COGS where available;
  - burn and cash balance -> runway;
  - CAC/LTV only when inputs exist or scenario ranges are accepted.
- Readiness must not stay unexplained 0 when a case has idea-stage profile coverage. It should expose factors, gaps, source types, and revision.

Slice 2 - Safe public research

- Research plan is created locally before any external call.
- Consent is required per research job.
- Provider is injected; CI uses deterministic cited fake provider.
- Production adapter may use configured provider/OpenAI only after consent and redaction.
- Unconfigured provider returns deferred with manual fallback, not fake success.
- Private metric request is blocked before provider call.

Slice 3 - Persistent Case Copilot

- One local thread per case.
- Copilot reads bounded context from same case_id and data_revision.
- It asks gap-driven questions.
- It can open structured fact drawer, prepare research plan, generate asset draft, or explain blocker reason.
- LLM unavailable must not break deterministic forms/actions.
- Thread survives reload/restart.

Slice 4 - Generated assets and batch improvements

- Generate preview/download drafts:
  - customer interview script;
  - pricing experiment;
  - positioning map;
  - weekly funnel template;
  - GTM/launch document.
- Assets are drafts, not evidence.
- Batch accept/reject improvement proposals in one versioned operation.
- One batch decision creates one version and one recalculation.

Slice 5 - End-to-end hardening

- Same-case browser journey:
  - upload idea-only startup document;
  - Copilot asks prioritized questions;
  - founder answers some values;
  - user says "не знаю" for others;
  - safe research plan is prepared and consented for market data;
  - scenario metrics update;
  - GTM document is generated;
  - report shows provenance.
- Second fixture anti-hardcode:
  - different startup document must produce different questions, metrics, research scope, and advice.
- Restart/replay:
  - thread, jobs, assets, and revisions are still available.

Existing tests/fixtures likely to extend first:

- tests/api/test_startup_pdf_case_differentiation.py
- tests/api/test_startup_api.py
- tests/fixtures/startup_synthetic_v1/expected_contracts.json
- tests/unit/application/test_startup_advisor_api_service.py
- tests/unit/application/test_startup_advisor_research_service.py
- tests/unit/application/test_startup_advisor_service.py
- tests/unit/application/test_startup_profile_builder.py
- tests/unit/application/test_startup_live_research_policy.py
- tests/unit/metrics/test_startup_metrics.py
- tests/unit/llm/test_startup_calculation_assist.py
- tests/privacy/test_startup_redaction.py
- tests/graph/test_startup_workflow.py
- tests/smoke/test_founder_workspace_boot.py
- tests/smoke/test_startup_browser_qa.py
- frontend/founder/lib/*contract*.test.ts
- frontend/founder/lib/*presentation*.test.ts
- frontend/founder/components/founder-workspace-controller.test.ts
- frontend/founder/components/founder-analysis-pages.test.ts
- frontend/founder/components/founder-advisor-pages.test.ts
- frontend/founder/components/founder-strategy-pages.test.ts

Verification commands to use when relevant:

- Backend targeted:
  uv run --offline --no-sync --no-default-groups --group stage1a --group stage1b-light-ingest --group founder-api --group dev pytest <targeted tests> -q

- Frontend targeted:
  cd frontend/founder
  npm test
  npm run typecheck
  npm run lint
  npm run build

- Browser/API smoke pattern:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_founder_workspace.ps1 -Mode offline-fixture -CaptureScreenshots -RequirePdfUploadJourney -OfflineFixturePath output\pdf\nomadflow_ai_startup_test_business_plan_ru.pdf -ApiPort 8038 -WebPort 3038 -AdminPort 8538 -DataDir artifacts\runtime\<new-run>\data -ScreenshotDir artifacts\runtime\<new-run>\screens -BrowserEvidencePath artifacts\runtime\<new-run>\browser-evidence.json -AdminTraceEvidencePath artifacts\runtime\<new-run>\admin-trace.json

Before starting:

1. Run git status --short.
2. Read the source docs listed above.
3. Inspect existing API/domain/frontend patterns around startup advisor, research, readiness, metrics, and founder workspace.
4. Use `superpowers:subagent-driven-development` to execute `docs/superpowers/plans/2026-08-22-founder-case-copilot-scenario-launch.md` task by task, with review gates between tasks.
5. Begin with Task 0 RED tests. Do not rewrite the approved plan unless current code evidence proves a concrete contract error; record any necessary correction explicitly.

Stop condition for this new chat:

User-testable Case Copilot v1 MVP is ready when an idea-only document can move through:
upload -> extracted idea profile -> Copilot questions -> founder answers/unknown answers -> safe research plan -> accepted scenario assumptions -> recalculated metrics/readiness -> pros/cons/action advice -> generated GTM document,
with provenance visible and privacy boundaries enforced by tests.
```

## Operator Note

This handoff is the durable first-message source for the new implementation task. The new task must preserve the current working-tree state and must not repeat the already accepted 2026-08-21 Tasks 1-9.

## Execution Progress

### 2026-08-22 - Task 0 RED contract freeze

- Added `startup_case_copilot_v1` idea-only fixtures for `idea_inventory` and `idea_clinic`; both are uploaded without starting the existing deterministic analysis pipeline so the RED run reaches the future Copilot route contract.
- Exact RED command requested by the plan:
  `.venv\Scripts\python.exe -B -m pytest tests/api/test_startup_case_copilot_contract.py -q -p no:cacheprovider`
- In this worktree, that exact command cannot start because `.venv\Scripts\python.exe` is absent. `cmd /c ".venv\Scripts\python.exe -B -m pytest tests/api/test_startup_case_copilot_contract.py -q -p no:cacheprovider"` returned: `The system cannot find the path specified.`
- Equivalent RED evidence with the available repository venv and this worktree on `PYTHONPATH`:
  `D:\Agents\Projects\Capstone N3\.venv\Scripts\python.exe -B -m pytest tests/api/test_startup_case_copilot_contract.py -q -p no:cacheprovider`
- Result: expected RED failures. Uploads succeed; `/api/v1/startup/cases/{case_id}/copilot/state`, `/copilot/messages`, `/research/plans`, and `/research/jobs` return `404`, proving the failure is the missing Case Copilot scenario/research contract rather than malformed fixtures.
- Approved research boundary: Copilot may only suggest `prepare_public_research`; plan creation is `POST /api/v1/startup/cases/{case_id}/research/plans`, and consented execution is `POST /api/v1/startup/cases/{case_id}/research/jobs`.
- Fixture sanity check:
  `D:\Agents\Projects\Capstone N3\.venv\Scripts\python.exe -B -m pytest tests/api/test_startup_pdf_case_differentiation.py::test_case_copilot_idea_fixtures_are_distinct_and_metric_free -q -p no:cacheprovider`
  returned `1 passed`.
- `git diff --check` returned clean.

### 2026-08-23 - Task 11 checkpoint / browser blocker

- Task 10 remains accepted; do not repeat Tasks 1-10.
- Task 11 dirty-WIP baseline was captured in `.superpowers/sdd/2026-08-22-founder-case-copilot-scenario-launch/task-11-baseline/`.
- First required RED was captured as the absent test path:
  `tests/evaluation/test_founder_case_copilot_scenario_e2e.py::test_case_copilot_idea_fixture_browser_contract_accepts_text_briefs_and_requires_complete_journey`.
- First smoke RED proved canonical `brief.txt` fixtures were rejected before `.txt -> text/plain` support.
- Current Task11 GREEN evidence:
  - `tests/evaluation/test_founder_browser_evidence_orchestration.py tests/evaluation/test_founder_case_copilot_scenario_e2e.py` -> `37 passed`.
  - Post-production scoped backend/evaluation recheck with Case Copilot contract/research job tests -> `100 passed`.
  - Repo-pinned Ruff over `src tests` -> `All checks passed!`.
  - mypy over `src\due_diligence_agent` -> `Success: no issues found in 252 source files`.
  - Full frontend `test`, `typecheck`, and `lint` passed.
  - Direct worktree `npm --prefix frontend/founder run build` remains blocked by the known Turbopack `node_modules` junction; isolated-copy `npm ci` + `npm run build` passed and verified the direction contract.
  - Smoke validate-only passed for both idea fixtures with `case_copilot_scenario_journey=True` and `fixture_mime=text/plain`.
  - API/runtime scenario smoke passed deterministically and wrote structured evidence to `artifacts/runtime/founder-case-copilot-scenario-task11-browser-inventory/admin-trace.json`.
- Exact expanded backend suite from the plan returned `163 passed, 2 failed`; both failures are missing-artifact failures for `output/pdf/nomadflow_ai_startup_test_business_plan_ru.pdf`.
- Do not claim Task11 complete yet. Full browser/UI journey is still blocked:
  - Round1 fixed the frontend UI controller/orchestrator path: explicit consent prepares the plan, queues the public research job with idempotency, fetches queued/running job status, stores/renders `researchPlan`/`researchJob`, citations/source refs and benchmark disclosure, then refreshes scenarios.
  - CDP screenshot capture still fails closed after blocking Kaspersky injection because the desktop state overflows the 1440x1000 viewport before the new strict two-fixture `caseCopilotScenarioJourney` browser evidence object can be written.
  - `scripts/capture_founder_screenshots.mjs` was edited before it was included in the Task11 baseline manifest; record this baseline coverage gap transparently and include the current file in the next snapshot.
- Verification note: `docs/verification/2026-08-22-founder-case-copilot-scenario-verification.md`.

### 2026-08-23 - Task 11 round1 continuation

- Additive baselines were captured before newly scoped frontend shell/style edits:
  `.superpowers/sdd/2026-08-22-founder-case-copilot-scenario-launch/task-11-baseline-extension-20260823-065704/`
  and `task-11-baseline-extension-20260823-070200/`.
- UI/orchestrator RED proved `prepareResearchPlan` ran without `queueResearchJob`; GREEN now executes prepare -> queue -> optional `getResearchJob` for queued/running -> scenario refresh.
- The Case Copilot rail now displays public research plan/job status, citations, source refs, accepted benchmark provenance/range/formula/dependencies/validation plan, and explicit non-promotion copy.
- Strengthened E2E/browser contracts:
  - mutation metric/readiness deltas;
  - launch-pack risk/action sections;
  - persisted `running` research job restart -> `deferred/research_interrupted`;
  - legacy/single-fixture browser evidence rejected.
- Fresh round1 evidence:
  - frontend focused gate `3 passed`;
  - full frontend `test`, `typecheck`, `lint` passed;
  - backend focused Task11/API/evidence gate `101 passed`;
  - Ruff `All checks passed!`;
  - mypy `Success: no issues found in 252 source files`;
  - isolated production build passed after copying round1 frontend files;
  - static smoke validate-only passed for both idea fixtures;
  - API/runtime smoke with isolated frontend passed and wrote `artifacts/runtime/task11-round1-browser-isolated2/admin-trace.json`.
- Remaining blocker: CDP/browser evidence is still not complete. Latest CDP run with isolated frontend failed at `vertical_overflow state=01-start-dashboard.png viewportHeight=1000 documentScrollHeight=1184 bodyScrollHeight=1184 overflowPx=184`.

### 2026-08-23 - Task 11 owner-requested safe pause

- Canonical resume checkpoint: `docs/handoffs/2026-08-23-task11-safe-pause.md`.
- The `.txt`/idea-profile backend repair is present and root-verified: focused `11 passed`, affected regression `214 passed`, exact Task 11 backend gate `166 passed`, Ruff clean, mypy clean.
- Fresh browser attempt `artifacts/ui/task11-case-copilot-browser-round2-real8/` was interrupted before artifact creation by owner request; the directory has `0` entries and is not evidence.
- Task 11 remains in progress. Independent repair review and a new real two-fixture browser run (`round2-real9` or later) are the first resume actions.
- All smoke/reviewer agents were interrupted and a process audit found no remaining Task 11 Python/Next/CDP/Chrome processes. No destructive Git or filesystem action, commit, push, or deploy occurred.

### 2026-08-23 - Task 11 complete / offline user-testable Case Copilot v1

- The safe-pause browser blocker is resolved. Final real browser run `artifacts/ui/task11-case-copilot-browser-round2-real31` passed the full two-fixture journey and a complete API/admin/web restart.
- Inventory case `d8106052-0316-47d3-a2cb-bbade2bb390c` and clinic case `a411f624-e736-4c40-86ed-4d676d6e6b68` produced distinct questions, benchmark scopes, scenario inputs, advice, and versioned launch-pack assets.
- Browser-observed provider boundary passed for each current case: zero `/research/jobs` mutations before explicit queueing and exactly one successful current-case `POST` after consent. Browser external calls remained `0`; Kaspersky parser injections were blocked fail-closed.
- New Analysis upload isolation passed: each case inbox contains exactly one distinct brief; the CareLoop case contains no inventory/SilkStock content.
- Scenario disclosure boundary passed: `founder_statement`, `public_benchmark`, and `ai_scenario` never auto-promote to `source_fact`; metrics expose provenance, range, formula, dependencies, source refs, and validation plan.
- Restart proof passed: the same case, selected base scenario, and versioned launch-pack asset reload after full service restart.
- Final verification: exact approved-plan backend suite `201 passed`; full founder frontend tests/typecheck/lint PASS; production frontend build PASS in immutable r11; pinned Ruff PASS; full mypy `252 source files` PASS.
- Immutable proof chain:
  - frontend/harness r11: `C:\Users\Akana\.codex\visualizations\2026\08\22\01a02900-c399-7dc0-99f8-2eb08e019c45\task11-build-proof\run-20260823-provider-json-r11`;
  - final backend/browser r12: `C:\Users\Akana\.codex\visualizations\2026\08\22\01a02900-c399-7dc0-99f8-2eb08e019c45\task11-build-proof\run-20260823-final-backend-browser-r12\PROOF.md`.
- Configured-live OpenAI/public-provider execution remains explicitly UNVERIFIED because no live credential or allowed external egress was used. The deterministic/offline Case Copilot v1 is user-testable and verified.
- No reset, clean, checkout, revert, commit, push, or deploy was performed. The existing dirty WIP was preserved.
