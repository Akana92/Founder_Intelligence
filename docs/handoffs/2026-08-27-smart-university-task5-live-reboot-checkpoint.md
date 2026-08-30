# Smart University Task 5 — safe reboot checkpoint

Date: 2026-08-27

## Workspace boundary

- Continue only in `C:\Users\Akana\.codex\worktrees\4839\Capstone N3`.
- Do not modify the original dirty worktree `C:\Users\Akana\.codex\worktrees\6e2b\Capstone N3`.
- Environment source remains only `D:\Agents\Projects\Capstone N3\.env`; never print or copy its secrets into artifacts, logs, commits, or chat.
- No reset, clean, checkout, revert, stash, push, merge, or deploy.

## Objective

Finish the real same-case Smart University owner journey using the real PDF:

`C:\Users\Akana\OneDrive\Рабочий стол\Smart_University_Full_Business_Plan_2026.pdf`

The journey must cover upload, explicit consent for online AI research, real OpenAI web search, Metrics, Market, Risks, Action Plan, the human decision, and stable PDF/HTML/JSON report output after a restart with the same data directory.

## Provenance invariants

- `founder_statement`, `public_benchmark`, and `ai_scenario` never become `source_fact`.
- Public research never fills private actual revenue, MRR, ARR, cash, burn, customer, contract, invoice, or bank facts.
- Online research must be attributable to the current case and current research job, with an observed provider tool call rather than an inferred request setting.

## Checkpoint base and scoped changes

HEAD before this checkpoint: `366797b6 Align Smart University live driver contract test`.

Task 5 changes to preserve:

- `scripts/capture_founder_screenshots.mjs`
- `scripts/capture_founder_screenshots.smart_university.test.mjs`
- `src/due_diligence_agent/adapters/observability/privacy.py`
- `src/due_diligence_agent/adapters/openai/startup_web_research.py`
- `src/due_diligence_agent/application/services/case_research_job_service.py`
- `src/due_diligence_agent/domain/startup/market.py`
- `src/due_diligence_agent/ports/repositories.py`
- `tests/evaluation/test_founder_browser_evidence_orchestration.py`
- `tests/unit/application/test_case_research_job_service.py`
- `tests/unit/application/test_startup_advisor_research_service.py`
- `tests/unit/observability/test_privacy_redaction.py`

Do not include unrelated modified fixtures, `frontend/founder/components/founder-analysis-pages.test.ts`, generated `.next*` directories, acceptance artifacts, or the untracked owner-journey plan in this checkpoint.

## Implemented review fixes

### Owner acceptance review

- The Smart University browser journey now opens and verifies the Metrics page.
- Report evidence records the snapshot ID and SHA-256 hashes for JSON, HTML, and PDF before restart.
- The restarted workspace must return the same snapshot ID and the same three report hashes.
- Regression tests reject a missing Metrics step and changed report artifacts after restart.

### Technical review

- The OpenAI adapter accepts online research only when the response contains an observed `web_search_call` output item.
- Citations without an observed web-search tool call fail closed with `startup_public_research_invalid_output`.
- Sanitized audit evidence includes the boolean `tool_call_observed`.
- The current research-job ID is threaded through the case plan, startup plan, wrapper, provider audit, and browser collector.
- Browser evidence must match both the exact case ID and current `request_id`; stale same-case provider evidence is rejected.

## Fresh verification already completed

- `tests/unit/application/test_startup_advisor_research_service.py`: 40 passed.
- `tests/unit/application/test_case_research_job_service.py`: 70 passed.
- `tests/unit/observability/test_privacy_redaction.py`: 3 passed.
- `tests/evaluation/test_founder_browser_evidence_orchestration.py`: 70 passed.
- `scripts/capture_founder_screenshots.smart_university.test.mjs`: 23 passed.
- `node --check scripts/capture_founder_screenshots.mjs`: passed.
- Focused current-job provider-audit tests: 3 passed.
- The stale same-case audit regression was observed RED before the fix and GREEN after it.

The scoped Ruff run is not a clean repository-wide gate because existing files contain broad E501 line-length debt. The import-order issue found in the touched privacy adapter was fixed; no broad unrelated formatting cleanup was attempted.

## Safe pause state

- No live API or frontend service was launched in this continuation, so there is no service process to stop.
- No live OpenAI request was sent after the review fixes.
- The two review gates have not yet been rerun against the corrected checkpoint.
- The real same-case browser acceptance and restart-stability proof are still pending.

## Exact continuation after reboot

1. Read this checkpoint and run `git status --short`; preserve all unrelated dirty files.
2. Rerun both review gates against the checkpoint commit:
   - owner acceptance review;
   - technical/provenance review.
3. If both gates pass, launch the workspace using only `D:\Agents\Projects\Capstone N3\.env`, without printing secrets.
4. Run the real PDF through the complete same-case browser journey with explicit online consent and observed OpenAI web search.
5. Verify Metrics, Market, Risks, Action Plan, the human decision, and PDF/HTML/JSON outputs.
6. Restart with the same data directory and prove the decision plus report snapshot/hashes remain identical.
7. Save the final verification evidence and a clear Russian owner instruction.
8. Leave the verified restarted project running for owner review.
