# Smart University real-document acceptance verification - 2026-08-29

Status: `RUN39_OWNER_JOURNEY_GREEN_WITH_CACHED_REPORT_AND_PDF`

This note records the current Smart University Task 5 evidence. The primary proof is live Run 39, not the older offline Run 13. The saved public research cache must be reused for the same case/revision/snapshot so repeated validation does not spend OpenAI API tokens again.

## Current primary evidence

| Requirement | Status | Evidence |
|---|---:|---|
| Real Smart University PDF was accepted and parsed into a source-grounded case | PASS | Run 39 case id `2dd8c3c7-69fb-4976-b148-2e96dc86bb40`; data revision advanced to `2` |
| User-approved online public research ran through a live provider | PASS | research job `88cccb9c-a7aa-4702-b92a-322fd7e77a88`; `provider=openai`; `tool=web_search`; `tool_call_observed=true` |
| Public research was cached for reuse | PASS | `artifacts/acceptance/smart-university-task5-live-final-20260828-39/research-cache-manifest.md` |
| Public research stayed public-only | PASS | all six sources have `source_mode=live`, `status=inference`, `supports_primary_financial_metrics=false` |
| Data revision moved from pre-research to post-research | PASS | `old_revision=1`, `new_revision=2`; `requested_acquisition_mode=live_public_research`; `selected_acquisition_mode=live_public_research` |
| Metrics, market, risk, GTM and report nodes completed | PASS | local audit records success spans for `metrics`, `market_research`, `financial_analysis`, `risk_analysis`, `market_analysis`, `gtm`, `report`; corrected cached artifacts were regenerated locally from the saved research snapshot |
| Owner final decision | PASS | Owner-facing ready case routes through `План действий`/`Отчёты`; browser proof opened report tabs and PDF without requiring owner to find the internal Gate 4 name |
| Report snapshot became canonical and ready | PASS | original report id `87671ccb-93d4-56db-8229-195f3a8ef2ef`; corrected cached report id `53116b7d-bebe-5d9a-bd62-961a328a96fe`; runtime status `report_status=ready` |
| Restart restored the same case | EVIDENCE_RECORDED | `artifacts/acceptance/smart-university-task5-live-final-20260828-39/screens/smart-university-restart-ready-1787918873324-7908.json` |
| Corrected cached Cyrillic PDF validation | PASS | `artifacts/runtime/founder-workspace/run39-cache-working-20260828/startup-api/output/pdf/smart-university-run39-cached-report-ru.pdf`; SHA256 `C90EA85323921F5C2F5FE2F292DA536100A97B4AD57DE2CE20806032BA744B74`; market page rendered and inspected |
| Full local validation after cached-report rebind | PASS | frontend tests/typecheck/lint/build passed; backend `2007 passed, 2 skipped, 3 deselected`; mypy/ruff passed; direct cached artifact verifier passed |
| Resume after browser storage loss/reboot | PASS | `http://127.0.0.1:3000/?caseId=2dd8c3c7-69fb-4976-b148-2e96dc86bb40` restored the same Run 39 case in browser and opened the PDF/HTML/JSON report endpoints |
| LangSmith safe display fields and usage/cost delivery | PASS | Live synthetic field-delivery run `langsmith-fields-synthetic-20260829-01` persisted safe Input/Output plus 120 prompt, 45 completion, 165 total tokens and USD 0.00123 on the root trace; OpenAI was not called; `First Token` remained null for the non-streaming path |

## Run 39 cache identity

| Field | Value |
|---|---|
| Acceptance root | `artifacts/acceptance/smart-university-task5-live-final-20260828-39` |
| Data root | `artifacts/acceptance/smart-university-task5-live-final-20260828-39/live-api-1787918873324/startup-api` |
| Case id | `2dd8c3c7-69fb-4976-b148-2e96dc86bb40` |
| Research job id | `88cccb9c-a7aa-4702-b92a-322fd7e77a88` |
| Research snapshot id | `58e6981b-cae2-504e-b926-fa02e5084a9a` |
| Research snapshot hash | `sha256:6c963500609c076cc35d2f33b165b3f99ada9315d957c30dad9a54171835a50b` |
| Original report snapshot id | `87671ccb-93d4-56db-8229-195f3a8ef2ef` |
| Original report snapshot hash | `sha256:952815cd9e9f44af63565e8f3d3e8f21122c322b76b32aa227333592f967d532` |
| Corrected cached report snapshot id | `53116b7d-bebe-5d9a-bd62-961a328a96fe` |
| Corrected cached report snapshot hash | `sha256:1eca5e28aaf86782f4a1dc2186ac29c1ff32cdaa949cf994e80b5006cf279e16` |
| Corrected regenerated local PDF hash | `sha256:c90ea85323921f5c2f5fe2f292da536100a97b4ad57de2ce20806032ba744b74` |

## Public research evidence

Audit file:

`artifacts/acceptance/smart-university-task5-live-final-20260828-39/live-api-1787918873324/startup-api/startup-audit-spool/2026/08/28/startup-public-research-88cccb9c-a7aa-4702-b92a-322fd7e77a88.jsonl`

Recorded safe fields:

- `provider=openai`;
- `model=gpt-5.6-luna`;
- `tool=web_search`;
- `tool_call_observed=true`;
- `query_count=2`;
- `source_count=6`;
- `latency_ms=21108`;
- token accounting is present in local audit and no secret values are recorded in this note.

Public URLs recorded by the case repository:

- `https://easyent.kz/`;
- `https://kazent.kz/`;
- `https://sigma-center.kz/ent`;
- `https://eco-service.kz/podgotovka-k-ent/`;
- `https://onlineaiplus.kz/ent`;
- `https://www.edtech.kz/ru/`.

## Trace-validator note

The original Run 39 capture reached the application state successfully but the controller threw on the final evidence validation because LangSmith export was degraded:

- `status=degraded`;
- `exporter_provider=langsmith`;
- `error_code=external_export_failed`;
- `fallback_used=local_audit`.

That condition is accepted only when the sanitized local audit proves the live public research call and complete local spans. The trace validator has since been fixed to allow exactly this degraded LangSmith/local audit combination and to reject disabled/offline/missing/wrong fallback cases. The post-fix validation is recorded in the final local validation section below.

## Corrected cached report rebind

The original Run 39 report was created while the workflow runtime could still point the report path at an older frozen market snapshot. The corrected local run did not call OpenAI, web search, LangSmith or fresh research. It rebound saved live public research snapshot `58e6981b-cae2-504e-b926-fa02e5084a9a` into the working runtime, recalculated downstream GTM/report locally, and produced final canonical report `53116b7d-bebe-5d9a-bd62-961a328a96fe`.

Founder-facing JSON, HTML and PDF show `Kazent`, `Sigma Center`, and `EDTECH.KZ` as public market orientirs / public hypotheses. The same outputs do not expose raw `source_refs=`, `source_mode=live`, `source_fact`, UUID/hash evidence markers, or stale `HubSpot`/`Salesforce` competitor placeholders.

## Historical evidence

Run 13 remains useful historical evidence for the deterministic offline branch:

- evidence: `artifacts/acceptance/smart-university-task5-real-13/browser-evidence.json`;
- screenshot: `artifacts/acceptance/smart-university-task5-real-13/screenshots/founder-desktop.png`;
- visible mode: `Офлайн-демо`;
- `network_external_calls=0`;
- no configured-live provider proof was claimed there.

The earlier Docker evidence also remains historical:

- browser evidence: `artifacts/acceptance/smart-university-task-e-docker-01/browser-evidence.json`;
- restart evidence: `artifacts/acceptance/smart-university-task-e-docker-01/docker-restart-evidence.json`.

It should not be cited as a fresh Docker proof for the current live Run 39 state.

## Provenance and privacy boundaries

The accepted behavior keeps these invariants:

- `founder_statement`, `public_benchmark` and `ai_scenario` do not auto-promote to `source_fact`;
- a PDF-derived `source_fact` means "stated in the uploaded document with locator", not "independently verified truth";
- public research may add public market, ICP, competitor, pricing, channel, regulation and benchmark context only;
- public research does not fill private revenue, MRR, ARR, burn, cash, customer, contract, invoice or bank values;
- scenario metrics keep provenance, formula, dependency/source references and validation plan;
- failed browser diagnostics preserve status/url/method/timing but no raw response bodies.

Manual-only or private-document-only fields:

- monthly recurring revenue, annual recurring revenue, recognized revenue;
- monthly net burn, cash, cash balance, runway;
- actual customers, private churn, private retention, private CAC, private margin;
- contracts, contract registers, invoices, invoice registers, bank and bank data.

## Final local validation

No new OpenAI, web search, LangSmith, scenario recomputation, or source mutation was used for this final validation. It reused the saved Run 39 cache.

- Final owner browser journey on 2026-08-29 clicked the safe navigation, advisor, metrics, market, risk, plan and report controls, then opened PDF from the running UI. A fresh repeat used `/?caseId=2dd8c3c7-69fb-4976-b148-2e96dc86bb40` so the same case can be restored after reboot or missing browser storage. It skipped only new-spend/new-generation controls: `Обновить исследование`, `Разрешить безопасный поиск`, and workpack regeneration.
- Browser layout proof: `Обзор gap=64 overlap=0`; `Рынок cardOverflow=0 factOverflow=0 competitorToRecommendationGap=12 recommendationToFooterGap=12 documentWidth=viewportWidth=1440`; `Риски gap=12 overlap=0 documentWidth=viewportWidth=1440`.
- Report endpoints from the UI: PDF `/api/startup/cases/2dd8c3c7-69fb-4976-b148-2e96dc86bb40/report/pdf` returned `200`, `application/pdf`, 94,795 bytes, magic `%PDF`; HTML and JSON endpoints returned `200`; all artifact URLs used the same case id. Fresh browser-smoke PDF hash matched the canonical cached PDF hash `C90EA85323921F5C2F5FE2F292DA536100A97B4AD57DE2CE20806032BA744B74`.
- Browser screenshots: `artifacts/acceptance/smart-university-task5-live-final-20260828-39/browser-final-20260829/1440x1000-overview-default-closed-fixed.png`, `1440x1000-market-auto-height-final.png`, `1440x1000-risks-expanded-no-overlap-fixed.png`, `1440x1000-report-ready-fixed.png`, `1440x1000-fresh-report-smoke-20260829.png`.
- Current canonical PDF and browser-downloaded PDF hashes both equal `C90EA85323921F5C2F5FE2F292DA536100A97B4AD57DE2CE20806032BA744B74`.
- Corrected cached PDF text/structure check: 7 pages, 94,795 bytes; pypdf found `Kazent`, `Sigma Center`, and `EDTECH.KZ`; forbidden stale competitor markers `HubSpot` and `Salesforce` were absent; replacement glyphs `■` and `�` were absent.
- Corrected cached canonical/founder projection check: `market_size.status=PARTIAL`; `market_size.items` includes two structured `public_benchmark` rows for Kazent `37000..45000 KZT/month` and Sigma Center `20000..52000 KZT/month`, both `status=inference`; benchmark rows contain no `source_fact`; founder JSON contains public benchmark values and does not expose `source_ref`.
- Corrected cached PDF render check: `artifacts/runtime/founder-workspace/run39-cache-working-20260828/startup-api/output/pdf/smart-university-run39-page1.png` and `artifacts/runtime/founder-workspace/run39-cache-working-20260828/startup-api/output/pdf/smart-university-run39-page3-market.png`; visual inspection found readable Cyrillic and public-market entries.
- Frontend verification on 2026-08-29: `npm run typecheck` passed; `npm run lint` passed; `npm test` passed including `founder-workspace-controller.test.ts` `152/152`; `npm run build` passed outside sandbox after in-sandbox `spawn EPERM`.
- Backend verification on 2026-08-29: focused OpenAI/profile pytest passed outside sandbox, `76 passed in 3.13s`; targeted mypy passed on 24 source files; targeted ruff passed; `scripts/verify_run39_cached_report.py` passed.
- Final full backend verification on 2026-08-29: `2008 passed, 2 skipped, 3 deselected in 401.86s`. A preceding non-deselected run produced the same `2008 passed, 2 skipped` plus exactly three `FileNotFoundError` failures for the pre-existing `canonical_nomadflow` checks. Their ignored `output/pdf/nomadflow_ai_startup_test_business_plan_ru.pdf` fixture is absent from this isolated worktree and was not fabricated or copied from the original dirty worktree.
- Synthetic runtime determinism regression: the repeated four-case API flow passed after the eval canonicalizer stopped treating runtime-local `document_text_block_NNN` numbering and disclosure-fragment ordering as semantic changes. Production Gate D still keeps its ordered disclosure hash strict.
- Focused backend/report/e2e tests: `61 passed in 11.90s` after rerun outside sandbox with `--basetemp=.run39-pytest-elevated`; the in-sandbox run was blocked by local pytest basetemp ACL (`WinError 5`) before assertions.
- Static checks: `ruff check` passed on changed Python sources/tests/scripts; `mypy` passed on the three changed source files plus two cache scripts; `git diff --check` passed with CRLF warnings only.
- Running project status: `http://127.0.0.1:3000/` returned 200, `http://127.0.0.1:8501/` returned 200, backend `http://127.0.0.1:8000/docs` and `/openapi.json` returned 200.
- Fresh full same-case acceptance on `cb231c18-4a79-48da-b85b-602b2f87c895`: Gate 2 profile confirmation, Gate 3 owner recommendation acceptance, Gate 4 report generation, and same-case PDF/HTML/JSON retrieval all completed.
- Fresh final PDF: `artifacts/acceptance/smart-university-final-20260829/smart-university-report.pdf`, 96,757 bytes, 7 pages. All rendered pages passed visual review for clipping, overlap, broken glyphs, and unreadable text.
- Fresh UI screenshots: `artifacts/acceptance/smart-university-final-20260829/ui-overview-1440x1000.png`, `ui-metrics-1440x1000.png`, `ui-market-1440x1000.png`, `ui-risks-1440x1000.png`, `ui-action-plan-1440x1000.png`, and `ui-reports-1440x1000.png`; all measured `clientWidth=scrollWidth=1440` with no horizontal overflow.
- Risk action routing browser proof: the backend structured founder question is the only row with `Ответить`; the TAM/SAM/SOM evidence question uses `Публичный поиск` and opens explicit consent without starting a request; unmatched diligence questions use `Добавить данные` and open Data Room. The opened structured form question matched the selected row exactly.
- Risk scoring truthfulness: the current backend contract provides no evidence-backed per-risk probability/impact score. The UI therefore renders `Не оценено` instead of fabricated dots and explains what evidence is required before scoring.

## Residual limitations

- No new network/API public research should run for the same Run 39 case/revision/snapshot; use the cache manifest instead.
- `case_status=awaiting_upload` is a legacy startup-shell field fixed by the current API contract, not the workflow progress field. Founder UI and acceptance use `analysis_status`, `gate2_status`, `gate3_status`, `gate4_status`, and `report_status`; changing the legacy field requires a separate backend/frontend contract migration and is not a Gate 3/Gate 4/PDF blocker.
- No push, merge or deploy is claimed by this verification note.
- The ignored NomadFlow PDF fixture is still absent. It was not fabricated or copied from the original dirty worktree; this does not block the Smart University Run 39 acceptance path.
