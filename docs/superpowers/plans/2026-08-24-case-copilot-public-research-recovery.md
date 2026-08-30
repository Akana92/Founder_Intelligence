# Case Copilot Public Research Recovery Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` task-by-task with TDD and independent review gates.

**Goal:** Make the local user-testable Case Copilot complete consented public-benchmark research, allow a previously deferred job to be retried after provider recovery, and show a readable Russian comparison of scenario metrics before and after recalculation.

**Root cause:** The running API accepted the research job but persisted `status=deferred`, `reason=provider_unconfigured`, `old_revision=1`, `new_revision=1`. `scripts/start_founder_workspace.ps1` forwards `FOUNDER_CASE_FIXTURE_MODE` only to the web process, while the backend chooses its deterministic local benchmark provider from that environment variable.

**Source of truth:**
- `docs/superpowers/specs/2026-08-22-founder-case-copilot-v1-design.md`
- `docs/superpowers/specs/2026-08-22-founder-case-copilot-scenario-metrics-addendum.md`

## Global constraints

- Preserve the shared dirty WIP. Do not reset, clean, checkout, revert, stage, commit, push, deploy, or publish.
- Private company values such as actual revenue, MRR, burn, cash and customer counts remain manual/file-only.
- `founder_statement`, `public_benchmark`, and `ai_scenario` never automatically become `source_fact`.
- Public research remains plan-first and explicitly consent-gated for every queued job, including retries.
- Public benchmarks may update scenario inputs and deterministic metrics, but remain visibly labelled external context.
- Every scenario metric retains provenance, range, formula, dependencies, source references, and validation plan.
- Russian is the default founder-facing language; raw reason codes are never shown as user copy.
- Add no dependency and keep changes focused.
- Run heavy commands sequentially because the owner machine is resource constrained.

## Task 1: Propagate the selected provider mode into the API launcher

**Files:**
- Modify: `scripts/run_founder_api.ps1`
- Modify: `scripts/start_founder_workspace.ps1`
- Modify: `tests/smoke/test_start_founder_workspace.py`
- Modify: `tests/smoke/test_founder_workspace_boot.py`

- [x] Write a RED executable launcher test proving `deterministic_offline` is accepted by the API launcher and visible in validation output, plus a focused integration assertion that the workspace launcher passes the selected case mode to `run_founder_api.ps1`.
- [x] Run only the focused smoke tests and observe the expected failure.
- [x] Add a validated `CaseMode` input to the API launcher, set `FOUNDER_CASE_FIXTURE_MODE` before API startup, add a non-starting validation path, and pass `CaseMode` from the workspace launcher.
- [x] Run the focused smoke tests GREEN and self-review without committing.

## Task 2: Retry deferred research and show metric changes

**Files:**
- Modify: `frontend/founder/lib/scenario-presentation.ts`
- Modify: `frontend/founder/lib/scenario-presentation.test.ts`
- Modify: `frontend/founder/lib/founder-readable-presentation.ts`
- Modify: `frontend/founder/lib/founder-readable-presentation.test.ts`
- Modify: `frontend/founder/components/founder-workspace-orchestrator.ts`
- Modify: `frontend/founder/components/founder-workspace-controller.tsx`
- Modify: `frontend/founder/components/founder-workspace-controller.test.ts`
- Modify: `frontend/founder/components/founder-shell.tsx`
- Modify: `frontend/founder/components/case-question-card.tsx`
- Modify: `frontend/founder/components/case-copilot-panel.tsx`
- Modify: `frontend/founder/components/case-copilot-panel.module.css`

- [x] Write RED behavior tests proving a deferred/failed research job is retried with `retry_of_job_id` and a new idempotency key after fresh explicit consent.
- [x] Write RED pure-presentation tests that compare the same scenario across revisions and return literal before/after metric changes without inventing zero values.
- [x] Run the focused tests and observe the expected failures.
- [x] Implement retry lineage, retain the pre-research scenario snapshot, derive the post-refresh comparison, and pass it through the workspace shell.
- [x] Render a compact Russian `До → после` comparison for changed metrics and clear explanations for provider-unavailable, no-eligible-result, and completed states.
- [x] Explain in the public-search mode that it cannot confirm internal revenue; it only adds external benchmarks to the scenario and recalculates affected metrics.
- [x] Translate the founder-approved revenue question into clear Russian founder-facing copy and lock the literal translation with a focused test.
- [x] Run focused frontend tests, typecheck and lint GREEN; self-review without committing.

## Task 3: Restore the user-testable runtime and verify the journey

**Files:**
- Modify: `docs/verification/2026-08-22-founder-case-copilot-scenario-verification.md`
- Create: `artifacts/ui/task13-public-research-recovery/`

- [x] Build the isolated production frontend with source parity.
- [x] Restart only the scoped local API/web processes, preserving the current runtime data directory, with API mode `deterministic_offline`.
- [x] Use a fresh test case and explicit consent to verify plan → job → accepted public benchmark → revision advance → refreshed scenarios.
- [x] Capture browser evidence showing the public benchmark and readable metric `До → после` comparison.
- [x] Run proportionate final tests, `git diff --check`, and an independent final review; document remaining limitations.
