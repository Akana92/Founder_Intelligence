# Queue 4 GTM Founder UI verification — 2026-08-15

## Scope and result

- Founder GTM panel commit: `412ab16a338a36024dd2ff116277c8cbdc79a3e1`.
- Real browser journey commit: `28af637c4510c446f443b5a66025d82209fb33b2`.
- Result: the first Queue 4 Lane 4A vertical slice is complete for the deterministic frozen/offline boundary.
- This closes only the canonical GTM/Action Plan read projection. The canonical report-section, Readiness/deep-questions, browser-visible Gate 4/download, and startup-chart slices are now verified separately; Queue 5 Demo Freeze and the Sellable Demo Gate remain open.
- No paid OpenAI, LangSmith, Yahoo Finance, GDELT, news, web-provider, or other external network call was made.

## Production evidence

| Requirement | Production evidence | Integration/test evidence | Status |
| --- | --- | --- | --- |
| Canonical GTM projection | Founder orchestrator reads `StartupGtmResponse` through the existing same-origin `/gtm` route only after Gate 3 is required/completed | Controller tests cover Gate 3 fetch and no pre-deep fetch | complete |
| Fail-closed lifecycle | Cached GTM is cleared before refetch and for a fresh case; `startup_gtm_not_ready` and `startup_gtm_stale` map to explicit founder-safe recovery | Tests cover stale and not-ready responses without leaving an old snapshot visible | complete |
| Evidence-aware presentation | The panel renders exactly seven canonical dimensions, statuses, reason/gap codes, evidence/source/contradiction references, and snapshot lineage | Presentation tests lock deterministic ordering and absence of invented scores/forecasts | complete |
| Frozen Action Plan | The panel renders the canonical four launch experiments for 7/30/60/90-day horizons | Presentation and UI tests lock all four horizon codes | complete |
| Responsive Founder UI | GTM dimensions and launch cards have desktop/mobile layouts and keyboard-visible expandable details | Frontend test/typecheck/lint/build pass; independent UX review passes | complete for this panel |
| Real offline browser journey | CDP helper uploads the frozen CSV, starts primary analysis, approves Gate 2, waits for deep analysis, and asserts the actual GTM panel | Desktop and mobile runs each report `founder_gtm_panel_visible dimensions=7 horizons=4` | complete |
| No false-positive screenshot fallback | A fixture-backed journey requires Edge/Chrome CDP; an alternate screenshot-only driver fails clearly | RED/GREEN regression locks `founder_gtm_journey_requires_cdp_browser` | complete |

## TDD and review evidence

- Initial frontend RED: three controller tests failed because no GTM fetch/snapshot lifecycle existed.
- Minimal GREEN added the orchestrator fetch boundary, strict DTO/error handling, deterministic presentation mapper, Founder panel, and responsive styles.
- Browser-smoke RED: the script did not set `FOUNDER_CASE_FIXTURE_MODE`, pass a fixture to the CDP helper, drive upload/HITL, or assert the GTM contract.
- Independent review found a non-CDP false-positive path. A fresh RED test required a fail-closed marker; the production script now refuses to claim a fixture-backed GTM smoke without a CDP-capable browser.
- An adjacent smoke regression also caught removal of the literal `documents/founder_metrics.csv` fixture contract; the shared fixture root restored that contract without duplicating paths.
- Independent read-only code review and follow-up UX review in the implementation run passed after the fixes; the browser-smoke follow-up review also returned PASS after the fail-closed driver correction.

## Verification evidence

```text
frontend tests                         -> PASS
frontend typecheck                     -> PASS
frontend lint                          -> PASS
frontend production build              -> PASS
focused browser-QA tests               -> 6 passed
combined browser-QA/Founder smoke pack -> 17 passed
Ruff on changed Python smoke test       -> PASS
Node syntax check                       -> PASS
PowerShell parse + ValidateOnly         -> PASS
real offline API/Founder browser smoke  -> PASS
  desktop viewport                      -> inner=1440, scroll=1425, body=1425
  mobile viewport                       -> inner=390, scroll=375, body=375
  GTM contract, each viewport           -> dimensions=7, horizons=4
  external network snapshots            -> clean before and after flow/capture
git diff --check                        -> PASS
```

The real smoke ran the local API and Next application on loopback ports, used the frozen CSV fixture, and exercised the actual UI controls rather than calling the backend directly for the browser assertion. Tracked desktop/mobile screenshot bytes were backed up and restored after capture; generated logs, runtime data, screenshots, and diagnostic artifacts were not committed.

## Privacy, determinism, and boundaries

- The panel exposes bounded DTO codes, counts, UUID references, and canonical lineage only. It does not expose raw documents, extracted text, filenames, local paths, prompts, credentials, or internal trace payloads.
- The UI does not invent scores, conversion forecasts, market claims, or experiment outcomes. Missing/partial/contradicted states remain explicit.
- Offline browser smoke verifies the local process tree has no established or pending non-loopback connection around the journey and capture.
- The separately verified Readiness/deep-questions, Gate 4/download, and startup-chart slices cover explicit primary/deep stage state, readiness lineage, bounded gaps, priority questions, exact artifact paths, the visible approved PDF, and report-derived visualizations.
- Queue 5 still owns the final Gate B/C/D/E packet, frozen screenshots/sample PDF, demo script/runbook, failure matrix, and Sellable Demo acceptance.

## Gate decision

Queue 4 GTM/Action Plan Founder UI slice for frozen/offline scope: **PASS**. Queue 4 overall is now **complete for the deterministic frozen/offline scope**; Queue 5 and the Sellable Demo Gate remain open.
