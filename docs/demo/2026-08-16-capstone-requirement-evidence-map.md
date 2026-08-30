# Queue 5 Capstone Requirement Evidence Map

Updated: 2026-08-21

## Claim Boundary

This map covers the current post-visual Founder AI Advisor / Founder Workspace evidence refresh for Queue 5 / Task 8. It does not close Queue 5, Sellable Demo, Pilot-Ready, Production-Ready, live web research, or production observability.

Offline/local evidence is green for the packet input lanes below. The user authorized one fresh Edge capture, one sanitized LangSmith live smoke, and one bounded OpenAI competitor-synthesis smoke; all three passed. This map is an input to the packet/binder workflow and does not self-reference a future freeze packet or binder hash.

## Evidence Boundary

Offline Gates, determinism, restart/lineage tests, failure matrix, and local audit are network-independent. The fresh Edge route is an offline-fixture capture. LangSmith and OpenAI are external side lanes and must stay outside canonical Gate D/E semantics and offline hashes. No Research Agent live web smoke is authorized or claimed here.

## Evidence Lanes

| Lane | Required proof | Current 2026-08-21 evidence |
| --- | --- | --- |
| Founder visual route | Desktop-only `1440x1000` accepted route with no new visual redesign cycle | Fresh Edge r7 14-state artifact `.local/post-visual-final-fa4405a-20260821-03-r7/edge-14-state`; exact 14-state manifest below; case `bdb2a8cc-db69-4b7d-bc81-7cb68b3dc802`; Gate 4 approved; offline fixture `true`; project external calls `0`; 232 browser requests; 2 blocked external requests; 2 blocked parser injections. Admin Console remains provisional, not owner-final accepted. |
| Same-case advisor restart | Advisor answer/restart keeps one case, revises report lineage, and avoids duplicate deterministic fallback public-research collection | `tests/api/test_startup_api.py::test_startup_api_restart_resumes_revised_same_case_thread_without_duplicate_public_research`; r2 -> r3 -> r4 same case; restart-safe continuation; three focused API tests PASS. This is not live external-provider proof. |
| Typed autonomous graph | Real typed Plan-and-Execute roles, tool boundaries, fallback, gates, restart, local audit, sanitized trace mapping | Stage C 16 LangSmith-focused unit/integration tests PASS. |
| Founder-safe report JSON | Exact public projection, mandatory analytics, and exact internal report/Admin lineage binding | PASS: public top-level keys are exact; freeze/browser/Queue5 validators bind public `data_revision` to `{case_id, snapshot_id, snapshot_hash, snapshot_revision}` and Admin id/revision/checksum; mismatch regressions pass. |
| Offline Gates B/C/D-A/D-B/E | Fresh offline Gates, privacy 0, no key/network dependency, Gate D semantic and persisted equivalence | PASS under `.local/post-visual-final-fa4405a-20260821-01`; D-A2/D-B2 semantic and persisted fingerprints 4/4 equal. |
| Backend toolchain | Full backend pytest, Ruff, strict mypy | PASS: Ruff PASS; strict mypy PASS for 239 source files; pytest `1460 passed, 1 skipped`. Expected skip is Windows symlink privilege. |
| Frontend toolchain | Full Founder frontend test/typecheck/lint/build | PASS: `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`. |
| Failure matrix | Required proof rows, no live calls, restart/fallback/lineage coverage, stable hash | PASS in `.local/post-visual-final-fa4405a-20260821-01/failure-matrix`; 13 proof tests; 6/6 matrix rows PASS; no live calls; hash `sha256:c0bd16ea3ea47099e4bf22918c8eadc97f6477b8c0fbb7b3cdac63f4a01b23e8`. |
| LangSmith external trace | One sanitized remote trace only after explicit authorization | PASS: `.local/post-visual-final-fa4405a-20260821-01/langsmith-live/langsmith-trace-evidence.json`; one authorized live smoke; `status=pass`; `run_count=25`; `flush_count=2`; `export_errors=0`; Admin health `healthy`; privacy 0. |
| OpenAI competitor synthesis | One bounded live-inference call only after explicit authorization | PASS: `.local/post-visual-final-fa4405a-20260821-01/openai-live/openai-competitor-smoke-evidence.json`; one authorized call; `status=pass`; `call_count=1`; five categories; `not_live_web_research`; privacy 0; estimated cost `$0.007544 <= $0.25`. |
| Packet/binder output | Frozen packet and final binder are downstream artifacts, not inputs to this map | Not asserted here. This packet-bound map intentionally records the input lanes only and does not include a future freeze packet hash, binder hash, or final binder decision. |

## Section 34 Mapping

| Capstone requirement | Reviewer-visible proof |
| --- | --- |
| Startup Launch Analyzer is the primary scenario | Founder Workspace r7 route plus post-visual Gates and API evidence. |
| Founder UX is desktop-only for this owner acceptance pass | r7 captures target `1440x1000`; mobile acceptance is excluded by Task 8 brief and must not be reintroduced as a new requirement. |
| Upload and analysis proceed without a prompt-first demo state | Canonical PDF fixture remains `tests/fixtures/startup_synthetic_v1/cases/saas/pitch.pdf`; r7 route starts from Founder Workspace intake. |
| AI Advisor asks one next best question | r7 states 11-14 and same-case API test cover advisor question/answer/recalculation/proposal lineage. |
| Advisor answer restarts canonical analysis for the same case | Focused API test proves r2 -> r3 -> r4 same case and revised report lineage after restart. |
| Public research behavior is privacy- and consent-bounded | Same-case test proves deterministic frozen fallback collection is not repeated; it does not claim live provider execution. Separate live Research Agent web smoke is not authorized. |
| Metrics, market, risks, Gate 3, action plan, Gate 4, report center remain in the canonical route | r7 14-state visual artifact plus full frontend and backend suites passed after post-visual stabilization. r7 manifest records screen 07 at `verticalOverflowPx=1` within `tolerancePx=1` and screen 08 at `verticalOverflowPx=0`. |
| JSON/HTML/PDF and Admin trace must share lineage | Stage B same-case/revision/restart acceptance and Stage C local audit/sanitized trace tests cover the contract; final live external proof is still blocked. |
| Autonomous multi-agent architecture is visible and typed | Stage C 16 tests cover Plan-and-Execute roles, typed tool boundaries, fallback/replanning, Gates, restart-safe continuation, local audit, and sanitized LangSmith mapping. |
| Offline Gates remain deterministic and network-independent | Gates B/C/D-A2/D-B2/E PASS under `.local/post-visual-final-fa4405a-20260821-01`; Gate D semantic/persisted fingerprints 4/4 equal. |
| Failure and recovery behavior is demonstrated | Fresh failure matrix PASS with 13 proof tests, 6/6 matrix rows, no live calls, and hash `sha256:c0bd16ea3ea47099e4bf22918c8eadc97f6477b8c0fbb7b3cdac63f4a01b23e8`. |
| LangSmith must be real but privacy-safe | PASS with one authorized live smoke; metadata-only, privacy 0, Admin health healthy. |
| OpenAI competitor synthesis must be bounded and honestly labeled | PASS with one authorized bounded live-inference call; one call, privacy 0, `$0.007544 <= $0.25`, not live web research. |

## Authoritative Local Artifacts

```text
Offline evidence root:    .local/post-visual-final-fa4405a-20260821-01
Edge 14-state capture:    .local/post-visual-final-fa4405a-20260821-03-r7/edge-14-state
Edge evidence JSON:       .local/post-visual-final-fa4405a-20260821-03-r7/edge-14-state/browser-evidence.json
Edge state manifest:      .local/post-visual-final-fa4405a-20260821-03-r7/edge-14-state/desktop-states/desktop-state-manifest.json
Failure matrix:           .local/post-visual-final-fa4405a-20260821-01/failure-matrix
LangSmith live:           .local/post-visual-final-fa4405a-20260821-01/langsmith-live/langsmith-trace-evidence.json
OpenAI live:              .local/post-visual-final-fa4405a-20260821-01/openai-live/openai-competitor-smoke-evidence.json
Handoff source:           docs/superpowers/plans/2026-08-20-founder-intelligence-post-visual-functional-handoff.md
Task 8 brief:             .superpowers/sdd/2026-08-16-founder-ai-advisor-ux-completion/task-8-brief.md
```

## Exact r7 Edge 14-State Manifest

```text
01-start-dashboard.png
02-data-room.png
03-analysis-progress-gate2.png
04-overview-readiness.png
11-ai-advisor-next-question.png
12-ai-advisor-answer.png
13-ai-advisor-updated-analysis.png
14-ai-advisor-improved-plan.png
05-metrics-finance.png
06-market-competitors.png
07-risks-questions.png
08-ai-action-plan.png
09-report-center.png
10-admin-observability-v2.png
```

## Stop Condition

Do not broaden the claim beyond the technical packet input lanes while Admin visual status remains provisional, commit is not authorized/performed, or Pilot-Ready/Production-Ready/live Research Agent web smoke are being discussed.

The completed LangSmith/OpenAI smokes were the only authorized external live calls for this cycle. The live Research Agent web smoke is outside this Task 8 authorization and must not be run without a separate explicit approval.

## Historical 2026-08-16 freeze evidence (preserved, not current)

Warning: the section below is the prior tracked Queue 5 evidence map restored from `git show HEAD:docs/demo/2026-08-16-capstone-requirement-evidence-map.md`. It is preserved for lineage only. Its `PASS`, live LangSmith, live OpenAI, final decision, and mobile evidence statements describe the historical 2026-08-16 freeze packet, not the current 2026-08-20 post-visual acceptance record. The old mobile evidence inside this archived text is explicitly excluded from the current desktop-only `1440x1000` owner acceptance.

````markdown
# Queue 5 Capstone Requirement Evidence Map

**Claim boundary:** this map covers Queue 5 Sellable Demo only. It does not claim Pilot-Ready or Production-Ready. Queue 1-4 remain frozen and are not redesigned here.

**Evidence boundary:** offline Gates and the deterministic packet remain tracing-disabled and network-independent. The real LangSmith trace and the bounded OpenAI competitor inference are separate side evidence and never participate in canonical Gate D/E semantics or hashes.

## Evidence lanes

| Lane | Required proof | Current evidence |
| --- | --- | --- |
| Frozen Gates B/C/D-A/D-B/E | Fresh offline results, privacy 0, provider calls 0, same Gate commit, semantic Gate D equivalence | PASS on code HEAD `2ec2611e6ed3033b39187ec4709dd5bc31538216` under `.local\queue5-final-2ec2611-20260816-04\gate-*`. Gate C/D/E record that commit; Gate B was launched in the same pinned process boundary. |
| Backend and frontend toolchain | Full backend pytest, Ruff, strict mypy, frontend test/typecheck/lint/build and post-build typecheck | PASS on implementation commit `72e5856` under `.local\queue5-final-2ec2611-20260816-04\toolchain-final-72e5856`: backend `1339 passed, 1 skipped`; Ruff PASS; strict mypy PASS for 227 source files; frontend 104 tests plus typecheck/lint/build/post-build typecheck PASS. |
| Real PDF browser/API/Admin journey | One PDF, no prompt/industry selection, same case through Gate 2/deep analysis/Gate 4, JSON/HTML/PDF/Admin lineage, desktop and mobile | PASS under `.local\queue5-final-2ec2611-20260816-04\pdf-browser`; case `80836367-af35-4a95-86dd-8e871f47905c`, desktop `1440x1000`, mobile `390x844`, `network_external_calls=0`. |
| Failure matrix | Bounded proof command, timeout evidence, required rows and supporting validations, no live calls, recomputed matrix hash | PASS under `.local\queue5-final-2ec2611-20260816-04\failure-matrix`; 12 proof tests, timeout false, matrix hash `sha256:15fec1331c56783845fee89152e6030bbe9b898ea78c3a078f3a31be14a0b98b`. |
| Real LangSmith workflow trace | One actual startup LangGraph workflow, sanitized spans, Admin exporter health, zero raw inputs/outputs/files/paths/secrets | PASS in `.local\queue5-live-6ba58c5-langsmith-proof-01\langsmith-trace-evidence.json`: 22 runs, 20 nodes, 2 flushes, 0 export errors, Admin health `healthy`, privacy leaks 0. |
| Bounded OpenAI competitor inference | Exactly one call after Gate 2, structured five-category result, sanitized frozen inputs, no web research, budget and privacy guards | PASS in `.local\queue5-live-9b9ed8e-openai-proof-03\openai-competitor-smoke-evidence.json`: call count 1, five categories, usage `1231/937/2168`, worst-case `$0.017 <= $0.25`, privacy leaks 0. The model name and derived price are runtime-configuration facts, not fields asserted by this evidence JSON. |
| Deterministic packet and final binder | Two clean strict packet runs with identical bytes/canonical hash; final binder binds frozen, PDF, LangSmith, OpenAI and failure-matrix lanes separately | Record the resulting hashes and final decision only in `docs/verification/2026-08-16-queue5-verification.md`; this input map intentionally does not self-reference its future packet hash. |

## Section 34 mapping

| Capstone requirement | Reviewer-visible proof |
| --- | --- |
| Startup Launch Analyzer is the primary scenario. | Founder Workspace PDF journey plus startup Gate C/D/E results. |
| Upload works without prompt or industry selection. | Browser evidence: `pdf_upload_journey=true`, `intake_mode=pdf_upload_only`, one `application/pdf`, prompt/industry flags false and DOM-observed intake. |
| Primary profile precedes deep analysis and Gate 2 controls progression. | Same-case browser/API journey and Admin nodes `primary_profile`, `disclosure`, then deep-analysis nodes. |
| Deep analysis exposes metrics/readiness, competitors, market sizing limits, contradictions, questions, GTM and actions. | Browser evidence: 18 profile fields, 22 readiness dimensions, 5 competitor categories, 8 rows, 20 diligence questions, 7 GTM dimensions and 2 actions; Gate D preserves contradictions/unsupported claims. |
| Gate 4 controls the final report. | Browser evidence `gate4_status=approved`; Admin lineage `gate4_status=completed`. |
| JSON, HTML and PDF share one approved snapshot and case. | Report `1f87d2cd-9df7-5f6b-b0e1-3117059744ae`, revision 1, checksum `c103e0231581981cf852936394dc62528162eb4c4df6596ef50f6a5f3d0de7c4`; artifact hashes are recorded in browser evidence. |
| Founder Workspace and Admin Console are separate. | Browser journey plus `startup_trace_view@1` Admin evidence for the same `case_id` and `run_id`. |
| LangSmith is visibly real but privacy-safe. | Live side evidence contains safe metadata-only workflow/node spans, empty inputs/outputs, no attachments, filesystem disabled, privacy leak count 0, and Admin health `healthy/local_audit`. |
| OpenAI is visibly real but bounded and honestly labeled. | One `live_inference` call using sanitized StartupProfile plus frozen summaries after Gate 2; `research_label=not_live_web_research`; no SEC/Yahoo/GDELT/news/web. |
| Gate D determinism is semantic, not a raw-runtime-hash claim. | Packet compares canonical semantic and persisted fingerprints separately from raw run hashes. |
| Failure handling and restart/report lineage are demonstrated. | Failure matrix covers unavailable provider, outage/partial fallback, bounded retry, budget exhaustion/restart, renderer fallback, checkpoint privacy/restart, report lineage and exporter fallback. |
| Desktop and compact mobile paths are reviewable. | Real Edge screenshots at `1440x1000` and `390x844`; no global viewport overflow; mobile visibly shows PDF-only intake. |
| Public Company stays a secondary comparable module. | Gate B public frozen fixture plus Gate E public/startup compatibility. |

## Authoritative local artifacts

```text
Frozen Gates:           .local\queue5-final-2ec2611-20260816-04\gate-*\
Toolchain:              .local\queue5-final-2ec2611-20260816-04\toolchain-final-72e5856\
PDF browser/Admin:      .local\queue5-final-2ec2611-20260816-04\pdf-browser\
Failure matrix:         .local\queue5-final-2ec2611-20260816-04\failure-matrix\
LangSmith live:         .local\queue5-live-6ba58c5-langsmith-proof-01\langsmith-trace-evidence.json
OpenAI live:            .local\queue5-live-9b9ed8e-openai-proof-03\openai-competitor-smoke-evidence.json
Final decision:         docs\verification\2026-08-16-queue5-verification.md
```

## Stop condition

Do not claim Queue 5 Sellable Demo ready if any required lane is missing, failed, stale in a behavior-affecting way, cross-case, privacy-leaking, over budget, multi-call where one call is required, dependent on live networking inside an offline Gate, or rejected by the final independent code/docs/acceptance review. Pilot-Ready and Production-Ready remain separate unfinished stages.
````
