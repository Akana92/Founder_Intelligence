# Queue 3 budget-exhaustion verification — 2026-08-14

## Scope and result

- Production commit: `a039e4df9e305ddf8d79e9abddf75a728d226910` (`feat: control startup budget exhaustion`).
- Result: the Queue 3 budget-exhaustion Graph Gate passes for the enforced persistent per-case provider budget.
- This closes only the budget-exhaustion boundary. Queue 3 still requires explicit GTM and Document Intelligence/Product Validation role surfaces; Queue 4, Queue 5, and the Sellable Demo Gate remain open.
- No paid OpenAI, LangSmith, Yahoo Finance, GDELT, news, or web-provider calls were made.

## TDD evidence

RED:

```text
tests/graph/test_startup_workflow.py -k budget_exhaustion
2 failed, 52 deselected
expected BUDGET_EXCEEDED, received workflow_unexpected

tests/api/test_startup_api.py -k budget_exhaustion
1 failed, 22 deselected
expected budget_exceeded, received workflow_failed
```

GREEN contract:

- the persistent `BudgetGuard` admits two bounded provider operations and rejects the third before the provider body runs;
- graph execution terminates with internal `BUDGET_EXCEEDED`, no report is built, and the failed node is recorded once;
- audit and trace retain only safe case/run/checkpoint/tool/error metadata and exclude raw payload/source references;
- reopening the same checkpoint and runtime returns the same terminal state with zero new provider calls, two durable usage records, and no active reservation;
- the public API projects the allowlisted internal code to safe lowercase `budget_exceeded` while continuing to sanitize arbitrary failure text.

Focused GREEN:

```text
tests/graph/test_startup_workflow.py -k budget_exhaustion  -> 2 passed
tests/api/test_startup_api.py -k budget_exhaustion        -> 1 passed
tests/graph/test_startup_workflow.py                       -> 54 passed
tests/api/test_startup_api.py                              -> 23 passed
tests/unit/llm/test_budget_guard.py                         -> 9 passed
```

## Full regression evidence

```text
backend pytest       -> 1111 passed, 1 Windows symlink skip
Ruff src/tests       -> PASS
mypy --strict src    -> PASS, 211 source files
frontend tests       -> 54 passed
frontend typecheck   -> PASS
frontend lint        -> PASS
frontend build       -> PASS
```

The Windows skip is the existing privilege-dependent symlink test. It is unrelated to budget handling.

## Real local API/browser smoke

The existing deterministic Founder workspace smoke ran local API and Next processes, uploaded the frozen CSV, completed Gates 2–4, fetched JSON/PDF report artifacts, and launched headless Edge for desktop and mobile rendering.

```text
offline_network_snapshot_clean
offline_network_snapshot_clean
viewport_geometry label=desktop inner=1440 scroll=1425 body=1425
viewport_geometry label=mobile inner=390 scroll=375 body=375
offline_network_snapshot_clean
startup_founder_workspace_smoke_passed
```

The browser smoke covers the real offline product path. Budget failure itself is proven without paid calls by the graph integration test plus the API projection contract; the offline fixture intentionally does not invoke the live provider.

## Independent review

The independent code review approved the boundary with no blocker. Its only low-risk note was that the API projection test and real graph budget test are separate seams rather than one paid-provider API scenario. The offline local browser/API smoke above and the restart-safe graph proof address the release boundary without enabling external calls.

## Remaining Queue 3 work

- explicit GTM bounded node/service and its graph contract;
- explicit Document Intelligence/Product Validation role surfaces;
- final Queue 3 API/query-contract freeze only after those role surfaces pass their focused and end-to-end gates.
