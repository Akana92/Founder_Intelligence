# Queue 0 Gate C and Baseline Implementation Plan

> **Execution contract:** Follow strict RED -> GREEN TDD. This plan is subordinate to `docs/superpowers/plans/2026-08-13-capstone-completion-staircase.md`. Do not call a live LLM provider and do not modify the startup LLM/graph path in Queue 0.

**Goal:** Create and run the missing canonical offline Gate C, then record a reproducible backend/frontend baseline without changing product behavior.

**Architecture:** Gate C is an evaluation boundary, not a source-code marker check. It executes the existing behavior suites that prove secure ingestion, no-network parsing, OCR confidence handling, privacy/egress controls, and denied-Gate-2 zero-provider-call behavior. It also invokes the existing Gate B evaluator once. The runner emits a machine-readable JSON result with per-criterion evidence, command outcomes, environment proof, revision metadata, and artifact paths.

**Technology:** Python 3.12+, pytest, uv offline/no-sync, argparse CLI, PowerShell wrapper, JSON artifacts, Ruff, mypy, Next.js frontend gates.

---

## Task 1: Add the canonical offline Gate C evaluator

**Files:**
- Create: `tests/evaluation/test_startup_gate_c.py`
- Create: `src/due_diligence_agent/evals/gate_c.py`
- Modify: `src/due_diligence_agent/presentation/cli.py`

**Acceptance:**
- The evaluator owns a fixed `startup_secure_ingest_v1` dataset contract.
- It executes real behavior tests for archive safety, document/spreadsheet parsing, privacy/egress, and denied Gate 2.
- It invokes the existing `run_public_eval("public_us_frozen_v1")` exactly once for Gate B regression.
- A failed criterion makes Gate C fail and is represented in `fail_reasons`.
- The JSON artifact reports `gate_c_passed`, `privacy_leak_count`, `denied_gate2_external_calls`, per-check command evidence, commit/environment metadata, and offline/no-key proof. Zero is reported only when the corresponding behavioral proof passes; a failed proof is reported as unknown rather than a fabricated positive count.
- The evaluator never performs a live provider call and uses a bounded, unique per-run local pytest/log directory beneath the explicit output root.
- The canonical CLI is an explicit `run-gate-c` subcommand; the existing public `run-eval` behavior remains backward-compatible.

**TDD sequence:**
1. Write result-contract, pass/fail propagation, command-selection, and CLI exit-code tests.
2. Run the focused test module and capture a behavioral RED caused by the missing evaluator/CLI command.
3. Implement the smallest evaluator and CLI boundary.
4. Run the focused module GREEN.
5. Run Ruff and strict mypy on changed Python files.

## Task 2: Add the reproducible PowerShell Gate C entrypoint

**Files:**
- Create: `scripts/run_stage1b_gate_c.ps1`
- Modify: `tests/evaluation/test_startup_gate_c.py`

**Acceptance:**
- The script resolves the repository root, blanks `OPENAI_API_KEY`, disables LangSmith, and enables offline Hugging Face/Transformers mode.
- The script uses `uv run --offline --no-sync` with the existing dependency groups and calls the Gate C CLI command.
- The script accepts an explicit output directory for isolated verification.
- A process-level test proves argument forwarding and non-zero exit propagation without contacting external services.

**TDD sequence:**
1. Add a failing process-level contract test for the missing script behavior.
2. Run the selected test and capture RED.
3. Implement the wrapper without adding dependencies.
4. Run the selected test GREEN, then the complete Gate C unit module.

## Task 3: Execute Gate C, Gate B, and focused startup baseline

**Files:**
- Create: `docs/verification/2026-08-13-queue0-baseline.md`
- Generated: `output/gate-c/startup_secure_ingest_v1/eval-result.json`
- Generated: isolated Queue 0 logs under a task-specific `.tmp-q0-*` directory

**Acceptance:**
- Gate C is GREEN from the PowerShell entrypoint and its JSON artifact is readable.
- Gate B is GREEN in the same Gate C run.
- Startup API/report/provider focused suites are GREEN.
- Backend Ruff and mypy are GREEN.
- Frontend `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build` are GREEN.
- No paid OpenAI request is made.
- The verification report records exact commands, counts, artifact hashes/paths, dirty-worktree ownership, and any environmental limitation without claiming a false pass.

## Task 4: Review, integrate, and freeze Queue 0 evidence

**Files:**
- Modify if required by review: only Task 1-3 owned files
- Update: `docs/verification/2026-08-13-queue0-baseline.md`

**Acceptance:**
- Spec review confirms every canonical Gate C criterion is backed by a behavior test or evaluator result.
- Quality review confirms no live-call path, no secrets in artifacts, deterministic command selection, bounded logs, and no unrelated dirty files in the scoped diff.
- `git diff --check` is clean for owned files.
- Queue 1 remains blocked until the final Queue 0 evidence is GREEN.

---

## Execution result

Queue 0 completed GREEN on 2026-08-13.

- Gate C and its embedded Gate B regression passed from the canonical PowerShell entrypoint without live provider calls.
- Focused startup backend batches passed `36/36` and `81/81`.
- Ruff, strict mypy, Founder tests, typecheck, lint, and production build passed.
- Final artifact and environmental evidence are frozen in `docs/verification/2026-08-13-queue0-baseline.md`.
- Review found no blocking issue. The one low-priority legacy tracing gap was fixed before the final artifact.
- Queue 1 is unblocked, with CSV/XLSX active-parser wiring and canonical `StartupProfile` explicitly carried as the first product gaps.
