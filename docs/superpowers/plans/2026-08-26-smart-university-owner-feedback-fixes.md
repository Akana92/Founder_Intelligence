# Smart University Owner Feedback Fixes

> **Status:** implemented and host-browser verified on 2026-08-26. Fresh Docker rebuild remains blocked before build by the unavailable local Docker Linux Engine; historical Docker acceptance is preserved separately.

## Execution result

- Task 1 completed in commits `4ebcda6f`, `00803d8d`, `b8cea588`, `453702e2`, and `be64effd`: the backend question descriptor now drives the visible question, typed form, validation guidance, and submitted founder input.
- Task 2 completed in commits `552762b1` and `2c1b6f15`: acquisition mode is explicit and the UI distinguishes `Офлайн-демо`, `Live-поиск`, and `Без live-провайдера` without implying Internet activity in deterministic mode.
- Task 3 completed in commits `d7690255` and `939be038`: the frozen Market resource is packaged and resolved portably; the real host journey renders the Market reconstruction.
- Task 4 completed in commit `7614895c`: resume retry is bounded, generation-aware, and cancellable, preserving the active case across a transient hydration failure.
- Task 5 host journey completed in `artifacts/acceptance/smart-university-task5-real-13/browser-evidence.json`: one real PDF, Gate 2, founder gap, explicit offline-research consent, scenario delta, Market, risks, actions, 7/30/60/90 plan, launch pack, actual service restart, and same-case rehydration all passed.
- The final harness fix waits for the preceding `Не знаю` submission to leave `aria-busy` before applying research consent, then uses a trusted pointer click and verifies the React postcondition. This removes the observed race without weakening the consent scope.
- Configured-live research was not exercised. The accepted proof is deterministic/offline with `network_external_calls=0`.
- A fresh Docker build was attempted only through safe startup/readiness checks. Docker client `29.7.2` remained unable to reach `//./pipe/dockerDesktopLinuxEngine`; no reset, WSL shutdown, socket deletion, or volume deletion was performed.

## Goal

Repair the four defects observed during the real Smart University acceptance run:

1. the visible question, requested fact, and input form must describe the same field in plain Russian;
2. deterministic/offline public benchmarks must never look like a live Internet search;
3. Market must run from an installed/package runtime instead of failing because repository-only fixtures are absent;
4. a transient hydration error after restart must not erase the active case.

This plan extends the accepted Case Copilot Tasks 1-11 and the Smart University real-document acceptance. It does not repeat either plan.

## Global constraints

- Work only in `C:\Users\Akana\.codex\worktrees\4839\Capstone N3`.
- Do not modify the source dirty worktree `C:\Users\Akana\.codex\worktrees\6e2b\Capstone N3`.
- Preserve existing untracked diagnostic and acceptance artifacts.
- Do not reset, clean, checkout, revert, or stash.
- Do not push, merge, deploy, or publish.
- Do not print secrets. Environment values may only be loaded from `D:\Agents\Projects\Capstone N3\.env` when a later live verification is explicitly in scope.
- `founder_statement`, `public_benchmark`, and `ai_scenario` never automatically become `source_fact`.
- Public research must not populate private MRR, ARR, revenue, burn, cash, customer, contract, invoice, or bank facts.
- No fallback may silently invent evidence, hide a provider failure, or claim Internet activity that did not occur.

## Task 1 — One structured question contract from backend to form

### RED

Add focused backend and frontend tests proving that:

- the displayed question, `field_key`, input kind, validation guidance, and submitted fact all refer to the same requirement;
- a text requirement renders a text input, while a money requirement renders amount, scale, currency, and period only when required by the backend schema;
- no fake numeric value, currency, month, source, or rationale appears as a prefilled answer;
- the card explains what the value means, why it is needed, what it unlocks, and gives a concrete example that is visually distinct from user data;
- submitting the card produces the existing provenance-safe `founder_statement` or explicit assumption request and never `source_fact`;
- legacy clients may still read the plain `next_question` string during the compatibility window.

Primary files:

- `src/due_diligence_agent/application/services/case_question_service.py`
- `src/due_diligence_agent/application/services/case_copilot_service.py`
- `src/due_diligence_agent/application/case_copilot_contracts.py`
- `frontend/founder/lib/startup-api-client.ts`
- `frontend/founder/components/case-question-card.tsx`
- `frontend/founder/lib/case-copilot-presentation.ts`
- focused backend and frontend tests adjacent to these contracts

### GREEN

Create one strict structured question descriptor from the canonical backend requirement registry. Use that same descriptor both for visible copy and the typed input action. Keep `next_question` as a compatibility projection, but stop independently selecting its text and action field. Render the form from the backend `input_schema`; placeholders are examples only and must never be submitted implicitly.

### Review gates

1. Spec: question/form/action identity, provenance invariants, backward compatibility.
2. Quality: one canonical mapping, no UI-only hidden requirement registry, accessible labels and errors.

## Task 2 — Honest public-research execution mode

### RED

Add contract and presentation tests proving that:

- `configured` is presented as live public Internet research;
- `deterministic_offline_fixture` is presented as an offline demo benchmark and never uses copy such as “ищу в интернете” or “публичный поиск выполнен” without the mode qualifier;
- `unavailable` explains that live research cannot run and offers the existing safe manual/deferred path;
- deterministic/offline runtime never calls the live OpenAI/web-search adapter even if live credentials are configured;
- results show source identity, URL/domain when present, retrieval time, and the execution mode;
- a public benchmark remains `public_benchmark` and cannot fill private company facts.

Primary files:

- startup/provider status contracts and Case Copilot API composition
- `frontend/founder/lib/startup-api-client.ts`
- `frontend/founder/components/case-question-card.tsx`
- `frontend/founder/lib/founder-readable-presentation.ts`
- focused API/service/presentation tests

### GREEN

Expose a strict acquisition-mode marker on each research job/result and the existing provider capability status to the Case Copilot presentation. Rename controls and status messages by mode. Preserve the current deterministic fixture for offline acceptance, label it unambiguously as a demo without Internet access, and make runtime fixture mode authoritative so it cannot fall through to a configured live port. Do not enable live calls automatically.

### Review gates

1. Spec: no false Internet claim, visible source/mode, private-fact prohibition.
2. Quality: exhaustive typed mapping for every provider state, no string heuristics.

## Task 3 — Package the frozen Market fixture

### RED

Add a packaged-runtime regression that simulates an installed wheel/container where repository `tests/fixtures` is absent and proves that:

- the frozen startup market fixture still resolves from package resources;
- the Market Research node completes for deterministic/offline mode;
- an unreadable fixture returns a stable founder-safe diagnostic code rather than only `workflow_unexpected`;
- no local path or traceback leaks through the API.

Primary files:

- `src/due_diligence_agent/bootstrap/container.py`
- `src/due_diligence_agent/adapters/market/frozen_market_research.py`
- package fixture directory under `src/due_diligence_agent/fixtures/`
- package/runtime smoke and graph error-contract tests

### GREEN

Move or copy the canonical fixture into package data and resolve it with the existing package-resource pattern. Use the resolver at both workflow and advisor fallback call sites. Preserve fail-closed validation and map the known fixture failure to a safe stable code with actionable copy.

### Review gates

1. Spec: installed runtime works, deterministic data remains frozen and traceable.
2. Quality: one resolver, packaged asset included by build metadata, no repository-path dependency.

## Task 4 — Bounded, typed resume after restart

### RED

Keep the existing regression `resumeCase retries a transient hydration failure and preserves the active case`, then add tests proving that:

- one transient hydration failure schedules one bounded retry and retains the persisted case id;
- only a typed `case_not_found` result clears persisted case state;
- retry is cancelled after `dispose()` or a newer operation generation;
- resume never creates a new case or re-uploads documents.

Primary files:

- `frontend/founder/components/founder-workspace-orchestrator.ts`
- `frontend/founder/components/founder-workspace-controller.tsx`
- their focused tests

### GREEN

Replace the ambiguous boolean resume result with a typed outcome. Keep retry policy inside `resumeCaseAction`, not the shared refresh path. Make the single bounded retry scheduler-driven, generation-aware, and cancellable. Clear storage only for a proven missing case.

### Review gates

1. Spec: same case survives transient restart hydration failures; missing case still resets safely.
2. Quality: bounded/cancellable retry, no generic refresh side effects, no timer leak.

## Task 5 — Integrated verification and owner handoff

Run in this order:

1. focused RED/GREEN tests for each task;
2. proportional backend regression, Ruff, frontend tests, typecheck, lint, and production build;
3. rebuild the local Docker runtime without deleting the persistent case volume;
4. run the real Smart University PDF through the same-case browser journey;
5. verify question/form identity, honest offline/live labels, Market success, and same-case restart recovery;
6. verify source lineage and confirm that public research did not promote private company facts;
7. update the Russian owner guide and verification note with exact observed behavior and any live-provider validation gap.

Configured-live Internet research is not a completion requirement unless credentials and egress are available within the authorized environment. If it is not exercised, document that limitation explicitly; do not infer it from deterministic/offline success.

## Completion claim

The task is complete only when the three owner-visible issues and the discovered resume defect have passing focused tests, pass both review gates, pass proportional repository checks, and are demonstrated in the same Smart University case in the browser—or when a genuine external blocker is proved with safe evidence and a working non-deceptive fallback.
