# Queue 4 Startup Profile Founder UI verification — 2026-08-15

## Scope and result

- Founder Startup Profile panel commit: `d0b95a0735134216d3925885850eb79a62141386`.
- Real API/browser profile smoke commit: `808493a2fa84a10e65c813da41ddd4cb5680ae44`.
- Result: the canonical Startup Profile slice of Queue 4 Lane 4A is complete for the deterministic frozen/offline boundary.
- This closes only the Startup Profile read projection. The canonical report-section, Readiness/deep-questions, browser-visible Gate 4/download, and startup-chart slices are now verified separately; Queue 5 Demo Freeze and the Sellable Demo Gate remain open.
- No paid OpenAI, LangSmith, Yahoo Finance, GDELT, news, web-provider, or other external network call was made.

## Production evidence

| Requirement | Production evidence | Integration/test evidence | Status |
| --- | --- | --- | --- |
| Strict canonical profile contract | The Founder contract parser accepts exactly the 18 canonical fields and the four allowed evidence states, with UUID/hash/confidence/reference validation and rejection of unknown or private fields | Contract tests cover valid primary/enriched profiles and hostile contract mutations | complete |
| Same-origin founder-safe read path | The Founder client and proxy expose only `GET /api/startup/cases/{caseId}/profile`, mapped to the existing backend profile query | Client/proxy tests lock encoding, HTTP method, manifest registration, strict parsing, and safe 409 propagation | complete |
| Workflow lifecycle | The orchestrator fetches the primary profile at the Gate 2 boundary, refreshes it after deep analysis, and never fetches it before readiness | Controller tests cover primary fetch, enriched refresh, fresh-case clearing, and pre-readiness absence | complete |
| Fail-closed recovery | Cached profile state is cleared before refresh and on stale/not-ready failures; recovery copy remains founder-safe | State-machine and controller tests cover `startup_profile_not_ready` and `startup_profile_stale` | complete |
| Evidence-aware presentation | The panel renders all 18 fields with source fact, inference, insufficient-data, or contradiction state; evidence, dependency, contradiction, gap, and lineage references remain explicit | Presentation tests lock deterministic ordering and prohibit invented scores or private/raw material | complete |
| Responsive Founder UI | The profile panel is part of the real workspace shell after the primary-analysis horizon and remains responsive on desktop/mobile | Frontend tests, typecheck, lint, production build, and independent review pass | complete for this panel |
| Real offline browser journey | The smoke uploads the frozen CSV, reaches the primary/Gate 2 flow, reads the real profile endpoint, and checks the rendered DOM | Desktop and mobile runs each report `founder_profile_panel_visible fields=18 evidence_fields=2` | complete |

## TDD and review evidence

- Controller RED: `20 passed, 6 failed`; the profile fetch/snapshot lifecycle did not exist.
- Presentation RED: `0 passed, 2 failed`; the deterministic profile presentation module did not exist.
- Recovery RED: `9 passed, 1 failed`; profile not-ready/stale errors were not mapped to the retry boundary.
- UI wiring RED: `26 passed, 1 failed`; the workspace shell did not render a profile panel.
- Browser/API smoke RED: the real profile endpoint and rendered profile DOM were not asserted.
- Minimal GREEN added the strict contract/client/proxy route, workflow lifecycle, presentation mapper, panel, responsive styles, and offline smoke assertions.
- A smoke review found an invalid assumption that every valid flow must already have an enriched revision. The smoke now accepts either a valid primary lineage or a valid enriched lineage and still fails closed on malformed revision/parent/hash data.
- Independent contract review and UI/browser review passed after UUID-valid parsed fixtures and real CDP DOM assertions replaced source-string-only evidence.

## Verification evidence

```text
focused backend profile/API/coordinator tests -> 9 passed, 77 deselected
focused Python smoke pack                    -> 11 passed
full backend pytest                          -> 1137 passed, 1 expected Windows symlink skip
Ruff                                         -> PASS
strict mypy                                  -> PASS, 219 source files
frontend tests                               -> PASS, 79 tests
frontend typecheck                           -> PASS
frontend lint                                -> PASS
frontend production build                    -> PASS
real offline API/Founder browser smoke       -> PASS
  desktop viewport                           -> inner=1440, scroll=1425, body=1425
  mobile viewport                            -> inner=390, scroll=375, body=375
  profile contract, each viewport            -> fields=18, evidence_fields=2
  GTM contract, each viewport                -> dimensions=7, horizons=4
  external network snapshots                 -> clean before, during, and after the flow
git diff --check                             -> PASS
```

The real smoke ran the local API and Next application on loopback ports, exercised the actual Founder controls, and used the frozen CSV fixture. It accepted the canonical primary profile returned by the deterministic runtime: revision 1, no parent profile, all 18 fields, two source-fact fields, and two evidence-bearing fields. Tracked desktop/mobile screenshots were backed up and restored byte-identically after capture; generated logs, runtime data, screenshots, and diagnostic artifacts were not committed.

## Privacy, determinism, and boundaries

- The panel exposes bounded canonical values, statuses, confidence, reference IDs, counts, and lineage only. It does not expose raw documents, extracted text, filenames, local paths, prompts, credentials, tokens, or internal traces.
- The UI does not invent scores, market claims, business values, or confidence. Missing and contradicted fields remain explicit.
- Primary and enriched profile lineage are validated separately; a primary revision is not falsely presented as enriched.
- Offline smoke verifies the local process tree has no established or pending non-loopback connection around the journey and capture.
- The separately verified Readiness/deep-questions, Gate 4/download, and startup-chart slices cover explicit primary/deep stage state, readiness lineage, bounded gaps, priority questions, exact artifact paths, the visible approved PDF, and report-derived visualizations.
- Queue 5 still owns the final Gate B/C/D/E packet, frozen screenshots/sample PDF, demo script/runbook, failure matrix, and Sellable Demo acceptance.

## Gate decision

Queue 4 Startup Profile Founder UI slice for frozen/offline scope: **PASS**. Queue 4 overall is now **complete for the deterministic frozen/offline scope**; Queue 5 and the Sellable Demo Gate remain open.
