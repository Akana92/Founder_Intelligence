# Queue 3 GTM/API freeze verification — 2026-08-15

## Scope and result

- GTM domain/service commit: `0b315a2225b8a5bf69a045c84b6ac26123736e1b`.
- GTM graph integration commit: `43052ba7a25e9a068099f5048cea0f67c2a2c2f2`.
- Backend API/query/report-lineage freeze commit: `54230a8b43755ffe8b3982086f009352e0bfa9c5`.
- Founder DTO/client/proxy freeze commit: `dbf8a9817b6ac8de5b6c990ed045e0cb09c169ea`.
- Real offline smoke contract commit: `4f72d0b65561082e9ad4b94512157efb7446bce1`.
- Windows quarantine-test isolation commit: `f2a8d381e1f4e6dd620fd5cb1f88a9b0df1e0ff8`.
- Result: Queue 3 is closed for the deterministic frozen/offline product boundary, and Queue 4 is unblocked.
- This does not close Queue 4 deep-analysis UX/report expansion, Queue 5 Demo Freeze, or the final Sellable Demo Gate.
- No paid OpenAI, LangSmith, Yahoo Finance, GDELT, news, web-provider, or other external network call was made.

## Frozen contract

| Requirement | Production evidence | Test/integration evidence | Status |
| --- | --- | --- | --- |
| Deterministic bounded GTM role | `StartupGtmService`, `StartupGtmSnapshot`, exact seven dimensions and four launch horizons | GTM unit tests and startup graph tests cover determinism, incomplete evidence, restart, audit, and Gate 3 invalidation | complete |
| Canonical GTM ownership | Full `startup_gtm_artifact` remains in the graph workflow store; API coordinator projects only id/hash/revision and upstream lineage | Real deterministic composition asserts `/gtm` succeeds while the coordinator runtime contains no full GTM artifact | complete |
| Founder-safe backend query | `GET /api/v1/startup/cases/{case_id}/gtm` returns the frozen `startup_gtm@1` DTO through a dedicated query port | API tests cover success, not-ready, stale tuple, authoritative revision advance, and stale runtime profile hash | complete |
| Strict same-origin frontend boundary | Next route wrapper, allowlisted proxy path, client method, and exact TypeScript parser | Frontend tests reject unknown fields, invalid hashes/codes/refs, invalid dimension semantics, duplicates, and incomplete enum sets | complete |
| Report lineage and integrity | Report adapter loads the exact GTM snapshot and validates case, revision, profile, market, and Product Validation lineage; the report integrity preimage and methodology bind its identity | Report unit and graph tests cover identity changes and stale/mismatched lineage | complete |
| Real local journey | Offline smoke runs the real API and Next app, reaches Gates 2–4, queries `/gtm`, validates schema/cardinality/hash, downloads the report PDF, and opens Founder/Admin/Comparables/API pages in a headless browser | `startup_founder_workspace_smoke_passed` with repeated `offline_network_snapshot_clean` | complete |

## TDD and review evidence

- Frontend RED established that the GTM parser, client method, proxy allowlist, manifest entry, and route wrapper were absent; the minimal strict DTO/route implementation made the focused and full frontend suites GREEN.
- A stale-but-self-consistent GTM runtime initially returned HTTP 200 after the authoritative case revision advanced. The new regression expected `409 startup_gtm_stale`; the coordinator now checks the authoritative current profile and canonical revision.
- The first real deterministic composition test returned `startup_gtm_not_ready` because the API coordinator and graph runtime use separate stores. The fix added a dedicated canonical graph-store query adapter and projected only reference tuples into the coordinator runtime.
- Independent final review found that persisted coordinator `profile_hash` was not compared during `/gtm` lookup. The RED regression returned HTTP 200; the minimal fail-closed comparison now returns `409 startup_gtm_stale` for a missing or mismatched runtime profile hash.
- Review also required the new Next route wrapper to be included explicitly. It is tracked in `dbf8a98`; no broad staging command was used.
- The final independent follow-up found no remaining code issue after the profile-hash correction and explicit route inclusion.

## Verification evidence

```text
focused GTM/API regression                 -> 5 passed, 22 deselected
affected API/graph/report/smoke/security   -> 147 passed
backend pytest after final fix             -> 1133 passed, 1 Windows symlink skip
Ruff src/tests                             -> PASS
mypy --strict --no-incremental src         -> PASS, 219 source files
frontend tests                             -> PASS, 56 subtests
frontend typecheck                         -> PASS
frontend lint                              -> PASS
frontend production build                  -> PASS; /api/startup/cases/[caseId]/gtm present
real offline API/headless-browser smoke    -> PASS
git diff --check                           -> PASS
```

The single backend skip is the existing Windows privilege-dependent symlink test (`WinError 1314`). Sandboxed pytest attempts that could not create or traverse Windows temp roots were treated as infrastructure-invalid; the identical offline suites passed outside the sandbox with fresh project-local `--basetemp` directories.

The browser smoke captured desktop and mobile renderings. The pre-existing tracked screenshot bytes were restored from a verified SHA-256 backup after the diagnostic run, so generated screenshots, logs, PDF output, runtime databases, and temp directories were not committed.

## Privacy, determinism, restart, and lineage

- The public GTM DTO contains bounded statuses, safe codes, UUID references, and a canonical hash; it does not expose document bytes, extracted raw text, private paths, filenames, prompts, credentials, or source URLs.
- API lookup fails closed unless the exact GTM tuple matches the canonical graph artifact, authoritative case revision, current/exact profile identity and hash, and persisted upstream Product Validation/Market lineage.
- Graph restart and Gate 3 rebuild preserve bounded history and replace stale GTM lineage without reintroducing excluded evidence, finding, or contradiction references.
- Canonical report hashing changes when the bound GTM identity changes, and the methodology records only the bounded GTM identity/status/schema/upstream references.
- The offline smoke checks the process tree for non-loopback established or pending connections before and after the founder flow and browser capture.

## Intentional Queue 4 and Queue 5 boundaries

- Queue 4 owns full Founder screens for Product Validation, GTM, risks, evidence, questions, and Action Plan; primary-versus-deep analysis presentation; expanded report sections; startup charts; and final responsive UX refinement.
- Queue 3 freezes the query DTO and report lineage only; it does not claim that those Queue 4 visual/report projections are already complete.
- Queue 5 still owns the final Gate B/C/D/E rerun packet, demo fixtures and screenshots, pitch/defense script, runbook, and Sellable Demo acceptance.
- Live market/news research, controlled Python execution inside the startup workflow, and external LangSmith/OTel export remain explicitly separate optional production integrations.

## Gate decision

Queue 3 frozen/offline Graph + API/query freeze gate: **PASS**. Queue 4 may proceed. The overall product and Sellable Demo remain incomplete until Queue 4 and Queue 5 pass their own gates.
