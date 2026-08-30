# Queue 4 Startup Report Founder UI verification - 2026-08-15

## Scope and result

- Founder canonical report sections commit: `c55d0f7`.
- Real browser/API report smoke commit: `fe0a2b4`.
- Result: the canonical Startup Report sections slice of Queue 4 Lane 4B is complete for the deterministic frozen/offline boundary.
- This closes only the Founder UI read projection for canonical report sections. The separate Readiness/deep-questions, Gate 4/download, and startup-chart slices now cover the remaining Queue 4 scope; Queue 5 Demo Freeze and the Sellable Demo Gate remain open.
- This slice did not close Queue 4 by itself; the combined Queue 4 evidence now does.
- No paid OpenAI, LangSmith, Yahoo Finance, GDELT, news, web-provider, or other external network call was made.

## Production evidence

| Requirement | Production evidence | Integration/test evidence | Status |
| --- | --- | --- | --- |
| Strict canonical report contract | The Founder parser accepts only `startup_report_snapshot.v1` with the bounded top-level contract, deterministic section order, valid hashes/UUIDs, reproducibility metadata, sensitivity, and lineage | Contract tests cover the accepted canonical snapshot and reject malformed or overflowing `trace_ids` | complete |
| Exact report tuple binding | The smoke binds `/report` metadata to `/report/json`: `snapshot_id == id`, `snapshot_hash == report_hash`, and `snapshot_revision == data_revision` for the same case | Smoke coverage fails on `smoke_report_tuple_mismatch`; Gate 4 submits the matching `snapshot_hash` and `snapshot_revision` | complete |
| Canonical section projection | Backend report JSON carries 14 sections in order; the Founder main panel renders the 12 user-facing sections | Presentation and controller tests lock the 12-section order and render contract | complete |
| Private/support sections excluded | `methodology` and `source_appendix` remain available for backend lineage but are excluded from the main Founder projection | Presentation tests prove `methodology`, `source_appendix`, private local paths, raw excerpts, prompts, tokens, scores, charts, and forecasts do not appear in the projection | complete |
| Fail-closed Gate 4 | Gate 4 controls are available only when the canonical report tuple is present and current; stale snapshot responses clear unsafe state | Controller/state-machine tests cover missing tuple and `startup_report_snapshot_stale` recovery | complete |
| Trace lineage ceiling | The frontend contract accepts backend `trace_ids` up to the bounded ceiling required by the backend but strips them from the parsed Founder-safe response | Contract tests accept 10,000 trace IDs, reject overflow, and verify `trace_ids` is not exposed after parsing | complete |
| Responsive Founder UI | The report panel renders all 12 main sections, statuses, rows/items, and lineage in the real Founder workspace | Frontend tests, typecheck, lint, production build, and browser smoke pass | complete for this panel |
| Real offline browser journey | The smoke uploads the frozen CSV, drives the actual API/UI flow, reads the real report JSON, and asserts the rendered DOM | Desktop and mobile runs each report `founder_report_panel_visible sections=12 statuses=12 lineage=true` with no horizontal overflow | complete |

## TDD and review evidence

- Report presentation RED: the 12-section Founder projection and methodology/source-appendix exclusion did not exist.
- Controller/workflow RED: the Founder workspace did not fetch, hold, render, or Gate-4-bind the canonical report snapshot.
- Contract RED: strict parsing for the `startup_report_snapshot.v1` response, lineage normalization, and `trace_ids` stripping/ceiling were not locked for the Founder client.
- Browser/API smoke RED: the real offline smoke did not verify `/report/json`, the exact report tuple, the rendered 12-section panel, or the report lineage marker.
- Minimal GREEN added the strict contract parser, report presentation mapper, panel rendering, Gate 4 tuple binding, responsive styles, and real offline smoke assertions.

## Verification evidence

```text
frontend tests                         -> PASS, 90 tests
frontend typecheck                     -> PASS
frontend lint                          -> PASS
frontend production build              -> PASS
focused backend/report/smoke tests     -> 48 passed
full backend pytest                    -> 1140 passed, 1 expected Windows symlink skip
Ruff                                   -> PASS
strict mypy                            -> PASS, 219 source files
real offline API/Founder browser smoke  -> PASS
  desktop viewport                      -> sections=12, statuses=12, lineage=true, no horizontal overflow
  mobile viewport                       -> sections=12, statuses=12, lineage=true, no horizontal overflow
  report contract                       -> schema=startup_report_snapshot.v1, backend sections=14, UI sections=12
  external network snapshots            -> clean; no external egress
git diff --check                        -> PASS
```

The real smoke ran the local API and Next application on loopback ports, used the frozen CSV fixture, exercised the actual Founder controls, and asserted the report panel from the browser DOM. Desktop and mobile screenshots were stored outside the repository; generated logs, runtime data, screenshots, and diagnostic artifacts were not committed.

## Privacy, determinism, and boundaries

- The panel exposes only bounded report section titles, summaries, statuses, rows/items, and canonical report lineage. It does not expose raw documents, extracted text, filenames, local paths, prompts, credentials, tokens, or internal trace payloads.
- The UI does not invent scores, charts, forecasts, market claims, or unsupported conclusions. Missing, partial, and contradicted section states remain explicit.
- `trace_ids` are accepted for backend ceiling validation but are not exposed in the Founder-safe parsed response or rendered panel.
- Offline smoke verifies the local process tree has no established or pending non-loopback connection around the journey and capture.
- The separately verified Readiness/deep-questions, Gate 4/download, and startup-chart slices close the bounded Queue 4 remainder at the current canonical snapshot boundary. Queue 5 still owns Demo Freeze. The Sellable Demo Gate remains open.

## Gate decision

Queue 4 canonical Startup Report sections Founder UI slice for frozen/offline scope: **PASS**. Queue 4 overall is now **complete for the deterministic frozen/offline scope**; Queue 5 and the Sellable Demo Gate remain open.
