# Founder Dynamic Analysis Verification — 2026-08-21

## Final Status

`ACCEPTED` for roadmap Tasks 1–9. The Founder workspace now reacts to the uploaded startup document and to the founder's accepted clarification; it no longer relies on fixed desktop-suite counters or placeholder project values for the verified path.

Canonical acceptance document:

- `output/pdf/nomadflow_ai_startup_test_business_plan_ru.pdf`
- SHA256 `8295079037E4C149BAF02FBB6270383C2833CE64718130DA72F7DE672981173D`

Final live evidence:

- `artifacts/runtime/founder-dynamic-task9-nomadflow-20260821-17/browser-evidence.json`
- `artifacts/runtime/founder-dynamic-task9-nomadflow-20260821-17/admin-trace.json`
- `artifacts/runtime/founder-dynamic-task9-nomadflow-20260821-17/report.json`
- `artifacts/runtime/founder-dynamic-task9-nomadflow-20260821-17/screens/desktop-states/desktop-state-manifest.json`

## Verified User-Visible Behaviour

- The intake is observed from the real DOM as a one-file `application/pdf` upload, not a prompt/industry fallback.
- Gate 2 shows document-derived NomadFlow profile content, approximately `76%` evidence-weighted confidence, and `50%` field coverage (`9/18`). Coverage is derived from populated fields rather than copied from confidence.
- The overview, metrics, market, risk, action-plan, and report views are rendered from the approved same-case public API state.
- The finance view distinguishes confirmed observations, calculations, estimates, and contradictions. It does not silently choose between equal-confidence contradictory source values.
- The advisor question comes from the backend advisor response for the current case. A bare `60%` is semantically rejected for the revenue/pricing question.
- The accepted founder clarification recalculates the same case. The final selected MRR is `27,900,000 KZT`; the prior conflicting `28,600,000 KZT` is not retained as the selected report value.
- The updated-analysis screen shows a real revision transition and changed fields; the improved report is revision `3` and Gate 4 is approved.

## Fresh Automated Checks

Final affected backend selection:

```powershell
.venv\Scripts\python.exe -B -m pytest tests/unit/application/test_startup_advisor_api_service.py tests/unit/application/test_startup_evidence_source_conflicts.py tests/api/test_startup_pdf_case_differentiation.py -q -p no:cacheprovider
```

Result: `35 passed in 16.67s`. The complete startup API selection also passed `40 passed`; the expanded backend regression selection passed `191 passed`.

Browser-evidence orchestration:

```powershell
.venv\Scripts\python.exe -B -m pytest tests/evaluation/test_founder_browser_evidence_orchestration.py -q -p no:cacheprovider
```

Result: `33 passed in 1.49s`.

Static/backend checks:

```powershell
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m mypy src\due_diligence_agent
node --check scripts\capture_founder_screenshots.mjs
```

Results: Ruff passed; mypy passed across `239` source files; Node syntax check passed.

Frontend checks from `frontend/founder`:

```powershell
npm test
npm run typecheck
npm run lint
npm run build
```

Results: the full TAP suite, TypeScript typecheck, ESLint, and production Next.js build passed. The production build required execution outside the sandbox because Windows denied a sandboxed TypeScript child process with `spawn EPERM`.

## Final Live Browser Journey

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_founder_workspace.ps1 -Mode live-api -CaptureScreenshots -RequirePdfUploadJourney -OfflineFixturePath output\pdf\nomadflow_ai_startup_test_business_plan_ru.pdf -AdvisorAnswer "Use bank and invoice register for June 2026: recognized MRR is 27.9m KZT; exclude CRM-only free-extension accounts." -InvalidAdvisorAnswer "60%" -BlockedBrowserInjectionOrigin "http://gc.kis.v2.scr.kaspersky-labs.com,http://me.kis.v2.scr.kaspersky-labs.com" -ApiPort 8038 -WebPort 3038 -AdminPort 8538 -DataDir artifacts\runtime\founder-dynamic-task9-nomadflow-20260821-17\data -ScreenshotDir artifacts\runtime\founder-dynamic-task9-nomadflow-20260821-17\screens -BrowserEvidencePath artifacts\runtime\founder-dynamic-task9-nomadflow-20260821-17\browser-evidence.json -AdminTraceEvidencePath artifacts\runtime\founder-dynamic-task9-nomadflow-20260821-17\admin-trace.json
```

Result: `startup_founder_workspace_smoke_passed`.

Key browser evidence:

- `pdf_upload_journey: true`
- `intake_mode: pdf_upload_only`
- `intake_observed_from_dom: true`
- `selected_file_count: 1`
- `gate4_status: approved`
- `network_external_calls: 0`
- `blocked_parser_injections: 2`
- `startup_profile_fields: 18`
- `gtm_dimensions: 7`
- `readiness_dimensions: 22`
- `action_plan_items: 4`
- `chart_cards: 2`
- `chart_points: 25`
- 14 screenshot files exist and every manifest viewport and PNG is `1440x1000`

The final report JSON contains `27900000`, `22400000`, and runway `7.8`; it does not contain the superseded selected MRR `28600000`. Gross margin remains an explicit contradiction instead of being mislabelled as confirmed.

Visual inspection covered screens 03, 04, 05, 11, 13, and 14: document understanding/profile, overview coverage, finance metrics, advisor question, recalculation delta, and improved report.

## Independent Gates

- Independent Task 9 code review: `ACCEPTED`; no Critical or Important findings in founder-clarification marker handling, bounded source-conflict reconciliation, or browser diagnostics.
- Independent acceptance verifier: `ACCEPTED`; canonical hash, same-case public counters, report values, 14 screenshots, report lineage revision `3`, targeted hardcoding scan, and stopped ports were confirmed.

## Explicit Limitations And Safety State

- External market/finance/risk provider calls remain intentionally deferred by disclosure policy in this local acceptance run: `live_provider_smoke.status = deferred_by_policy`. The Admin trace records policy-blocked nodes and local audit fallback; it does not report external-provider success.
- Windows sandbox temp/cache ACL restrictions required some pytest/build commands to run with approved local escalation. This was an environment constraint, not a product-test failure.
- After the live run, listeners on ports `8038`, `3038`, and `8538` were absent and no matching Capstone API/Next.js/Streamlit smoke process remained.
- No commit or push was made. The large pre-existing shared WIP on `main` was preserved.
