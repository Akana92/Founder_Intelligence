# Queue 4 startup charts verification — 2026-08-15

## Scope and result

- Deterministic backend chart rendering commit: `dbfdbb0`.
- Startup spreadsheet-fact integration commit: `64218dc`.
- Unit-safe metric scale correction commit: `75de454`.
- Founder report-derived chart panel commit: `513f441`.
- Offline browser/no-egress hardening commit: `75c990b`.
- Canonical HTML section-order repair commit: `4760783`.
- Result: the startup-chart remainder of Queue 4 Lane 4B is complete for the deterministic frozen/offline boundary.
- Combined with the previously verified Profile, GTM, report, Readiness/deep-questions, and Gate 4/download slices, Queue 4 is complete for that boundary.
- Queue 5 Demo Freeze and the Sellable Demo Gate remain open. No paid OpenAI, LangSmith, Yahoo Finance, GDELT, news, web-provider, or other live-provider call was made.

## Production and integration evidence

| Requirement | Production evidence | Integration/test evidence | Status |
| --- | --- | --- | --- |
| Snapshot-derived charts | Backend chart projections read only the canonical approved report snapshot and generate deterministic embedded PNGs for market sizing, confirmed metrics, readiness coverage, and report coverage | Unit/integration tests lock chart keys, deterministic PNG data URIs, and unchanged canonical JSON/hash | complete |
| Real startup metric path | Startup spreadsheet parsing admits the canonical startup metric inputs needed by the existing metric definitions; the frozen smoke CSV now yields an evidence-backed `gross_margin=0.72` | Parser and real API-flow regressions prove the fact reaches the report metric rows and HTML chart | complete |
| No invented values | Invalid/malformed rows are filtered; missing inputs remain absent instead of becoming synthetic chart points | Projection tests cover malformed rows and the report/UI renders only confirmed canonical values | complete |
| Unit-safe encoding | Backend splits confirmed metric charts by native unit; Founder presentation marks mixed-unit series as `independent` and suppresses comparative bars | RED/GREEN tests prove USD and ratio values are never compared on one shared scale | complete |
| Canonical JSON remains stable | Renderer-owned `chart_data_uri` and `startup_charts` never enter `startup_report_snapshot.v1` JSON or its integrity hash | Integration test compares the persisted JSON contract while HTML contains the embedded charts | complete |
| Safe standalone HTML/PDF | HTML accepts only bounded PNG data URIs and rejects external `src`, `srcset`, CSS URL loading, and non-PNG chart payloads; PDF is generated from the same approved snapshot | Renderer security tests, report smoke, Gate 4 download proof, and `%PDF` validation pass | complete |
| Canonical section order | The render-only chart region is semantic but does not impersonate an id-bearing canonical report section | The two previously failing report e2e order/restart tests pass after the minimal template repair | complete |
| Founder-safe chart projection | The Founder panel reads only validated report rows/statuses and exact profile/GTM/report lineage; stale lineage fails closed | Frontend mapper/component tests cover caps, privacy exclusions, lineage mismatch, and stable selectors | complete |
| Responsive product UI | The actual Founder Workspace renders three chart cards with eight bounded points and three lineage markers | Desktop 1440×1000 and mobile 390×844 browser runs show readable single-column/mobile and aligned desktop layouts without horizontal overflow | complete |
| Offline no-egress proof | Browser QA rejects external scripts in served HTML, observes CDP Network/Fetch events, and blocks all external requests by default | Real smoke used one explicit exact-origin quarantine for a locally injected Kaspersky parser script; the request was still failed before egress and logged for both viewports | complete for frozen/offline smoke |

## TDD and review evidence

1. Backend RED: no deterministic chart renderer or report chart context existed.
2. Startup-flow RED: the real frozen CSV/API journey produced no confirmed metric row because canonical startup metric inputs were not admitted by the spreadsheet parser.
3. Unit-safety RED: heterogeneous metric units could be presented with one misleading comparative scale.
4. Founder RED: no canonical report-derived chart projection/panel or fail-closed lineage contract existed.
5. Browser RED: the smoke did not prove chart DOM, embedded report images, in-viewport screenshots, or CDP-level no-egress behavior.
6. Security review RED: an unconditional injected-script exception could have hidden unrelated external requests; it was replaced by strict default failure plus an explicit exact-origin, parser-only, loopback-document quarantine that still blocks the request.
7. Full-regression RED: the renderer-owned chart `<section id>` appeared before the 12 canonical report sections; the wrapper no longer claims a canonical section id.
8. Minimal GREEN and independent reviews passed for backend integration, frontend privacy/lineage, browser no-egress, unit-safe encoding, and desktop/mobile visual quality.

## Verification evidence

```text
focused report order e2e             -> 2 passed
focused chart + browser-QA           -> 22 passed
focused startup ingestion/API        -> 57 passed
focused backend chart/smoke           -> 31 passed
Gate D/E regression                   -> 43 passed
Gate D missing-root stress            -> 20/20 passed
full backend pytest                   -> 1162 passed, 1 expected Windows symlink skip
Ruff                                  -> PASS
strict mypy                           -> PASS, 219 source files
frontend tests                        -> PASS, 104 tests
frontend typecheck / lint / build     -> PASS / PASS / PASS
focused browser-QA pytest             -> 17 passed
node --check capture helper           -> PASS
real offline API/browser smoke r12    -> PASS
git diff --check                      -> PASS
```

The final browser/API smoke ran the local API and Next development application on loopback ports, uploaded the frozen startup CSV, traversed primary analysis, Gates 2–4, report generation, Readiness, charts, and JSON/HTML/PDF delivery for the same case. The production build was verified separately. Both viewports reported `charts=3`, `points=8`, `lineage=3`; the PDF response was bounded, `application/pdf`, and began with `%PDF`.

Evidence screenshots were stored outside the repository and were not committed:

- `C:\Users\Akana\.codex\visualizations\2026\08\14\019ffeb3-c3f0-74d0-9129-3b8961cf9456\q4-charts-smoke-r12\founder-desktop.png` — 1440×1000.
- `C:\Users\Akana\.codex\visualizations\2026\08\14\019ffeb3-c3f0-74d0-9129-3b8961cf9456\q4-charts-smoke-r12\founder-mobile.png` — 390×844.

One intermediate full-suite run passed all product assertions but hit a non-reproducible Windows `shutil.rmtree` `WinError 145` during Gate D test cleanup. Twenty isolated repetitions, the full 43-test Gate D/E set, and the final 1162-test backend run passed, so no production Gate D code was changed or exception masked.

## Privacy, determinism, and explicit boundaries

- Renderer-owned PNG payloads are bounded and remain outside canonical JSON, API DTOs, report hashes, traces, and Founder presentation data.
- Founder charts expose only canonical labels, values, units, status counts, and snapshot lineage; raw source text, local paths, prompts, credentials, tokens, methodology, source appendix, and trace payloads remain excluded.
- The strict browser-smoke default treats every external request as fatal. The Kaspersky exception is an explicit local-environment argument, exact-origin and parser-script constrained, and still calls `Fetch.failRequest`.
- The production CSP materially blocks external scripts, frames, objects, and base-URI changes. It still contains Next-compatible `unsafe-inline`; nonce/hash hardening is a future security improvement and this verification does not claim complete inline-XSS protection.
- Live research, controlled Python inside the startup workflow, external LangSmith/OTel delivery, Queue 5 Demo Freeze, and Sellable Demo acceptance are not claimed complete here.

## Gate decision

Queue 4 startup charts slice for deterministic frozen/offline scope: **PASS**.

Queue 4 overall for the same scope: **PASS**. Queue 5 Demo Freeze and the Sellable Demo Gate remain open.
