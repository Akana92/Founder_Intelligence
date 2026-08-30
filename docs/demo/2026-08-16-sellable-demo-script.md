# Queue 5 Sellable Demo Script

Updated: 2026-08-21

## Scope

This script covers the post-visual Founder AI Advisor / Founder Workspace demo path for Queue 5 / Task 8 evidence refresh.

Do not claim Pilot-Ready, Production-Ready, live web research, production observability, or Admin owner-final acceptance from this document. The current packet input lanes are green for the desktop-only 2026-08-21 evidence set after the user authorized one fresh Edge capture, one sanitized LangSmith live smoke, and one bounded OpenAI competitor-synthesis smoke. This script does not self-reference a future freeze packet or binder hash.

Target runtime: 7-10 minutes.

Canonical desktop viewport: `1440x1000`.

Canonical fixture:

```text
tests/fixtures/startup_synthetic_v1/cases/saas/pitch.pdf
```

## Current Evidence Lanes

Keep these lanes separate. Offline Gates and deterministic evidence remain network-independent. The fresh Edge route is an offline-fixture capture. LangSmith and OpenAI are external side lanes and were executed exactly once each for this evidence cycle. No Research Agent live web smoke is authorized or claimed here.

| Lane | Current status | Evidence |
| --- | --- | --- |
| Founder Workspace visual route | PASS for fresh r7 14-state Edge desktop capture; Admin remains provisional | `.local/post-visual-final-fa4405a-20260821-03-r7/edge-14-state`; exact 14-state manifest below at `1440x1000`; case `bdb2a8cc-db69-4b7d-bc81-7cb68b3dc802`; Gate 4 approved; offline fixture `true`; project external calls `0`; 232 browser requests; 2 blocked external requests; 2 blocked parser injections. Screen 07 records `verticalOverflowPx=1` within `tolerancePx=1`; screen 08 records `verticalOverflowPx=0`. |
| Same-case advisor restart and lineage | PASS for focused API acceptance | `tests/api/test_startup_api.py::test_startup_api_restart_resumes_revised_same_case_thread_without_duplicate_public_research` proves r2 -> r3 -> r4 on the same case, restart-safe continuation, revised report lineage, and no repeated deterministic frozen fallback public-research collection. This is not proof of a live external provider call. Three focused API tests passed. |
| LangGraph / multi-agent architecture | PASS for local typed behavior and trace boundaries | Stage C has 16 LangSmith-focused unit/integration tests PASS, covering typed Plan-and-Execute roles, tool boundaries, telemetry, fallback, Gates, restart, local audit, and sanitized LangSmith mapping. |
| Founder-safe JSON and lineage | PASS | Exact public projection with mandatory analytics; freeze/browser/Queue5 evaluators require exact report metadata and same Admin id/revision/checksum. Wrong-id/hash regressions pass. |
| Fresh offline Gates | PASS | `.local/post-visual-final-fa4405a-20260821-01`; Gates B/C/D-A2/D-B2/E PASS; privacy 0; denied/live external calls 0 where measured. D-A2/D-B2 semantic and persisted fingerprints are 4/4 equal. |
| Full backend | PASS | Ruff PASS; strict mypy PASS with `Success: no issues found in 239 source files`; pytest `1460 passed, 1 skipped`. The skip is the expected Windows symlink privilege case. |
| Full frontend | PASS | `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build` PASS after the r7 stabilization. |
| Failure matrix | PASS | `.local/post-visual-final-fa4405a-20260821-01/failure-matrix`; 13 proof tests PASS; 6/6 matrix rows PASS; no live calls; matrix hash `sha256:c0bd16ea3ea47099e4bf22918c8eadc97f6477b8c0fbb7b3cdac63f4a01b23e8`. |
| LangSmith external smoke | PASS | `.local/post-visual-final-fa4405a-20260821-01/langsmith-live/langsmith-trace-evidence.json`: one authorized live smoke, `status=pass`, `run_count=25`, `flush_count=2`, `export_errors=0`, Admin health `healthy`, privacy 0. |
| OpenAI competitor synthesis smoke | PASS | `.local/post-visual-final-fa4405a-20260821-01/openai-live/openai-competitor-smoke-evidence.json`: one authorized call, `status=pass`, `call_count=1`, five categories, `live_inference`, `not_live_web_research`, privacy 0, estimated cost `$0.007544 <= $0.25`. |
| Packet/binder output | Not asserted in this packet-bound script | Frozen packet and final binder are downstream artifacts. Their final decision and hashes belong in the downstream verification record, not in this script input. |

## 7-10 Minute Demo Run

| Time | Action | Say | Evidence cue |
| --- | --- | --- | --- |
| 0:00-0:45 | State the boundary. | "This is the post-visual Founder Workspace evidence path. The packet input lanes are green for the desktop-only evidence set; Admin owner-final acceptance, Pilot-Ready, Production-Ready, and live web research are separate." | Show this lane table. |
| 0:45-1:30 | Open the Founder Workspace route. | "The founder starts from the product workspace and proceeds through the accepted 14-state desktop route." | Fresh Edge r7 14-state artifact: `.local/post-visual-final-fa4405a-20260821-03-r7/edge-14-state`. |
| 1:30-2:30 | Show upload/intake and primary analysis. | "The route remains PDF-first and desktop-only for this acceptance pass." | Canonical fixture path; r7 desktop captures; no mobile acceptance claim. |
| 2:30-3:45 | Show the advisor question and answer flow. | "The next best question is part of the same case, not a separate demo state." | Same-case acceptance test proves r2 -> r3 -> r4 lineage. |
| 3:45-4:45 | Show the recalculated analysis and improved proposal state. | "Advisor input restarts the canonical same-case analysis, creates revised report lineage, and does not repeat deterministic frozen fallback public-research collection." | `test_startup_api_restart_resumes_revised_same_case_thread_without_duplicate_public_research`; three focused API tests PASS. |
| 4:45-5:45 | Show metrics, market, risks, and action-plan screens. | "These views are backed by the post-visual graph/API contract and the refreshed local test suite." | Frontend test/typecheck/lint/build PASS; backend `1460 passed`. |
| 5:45-6:45 | Show Gate 4 / report center and Admin trace boundary. | "Same-case report lineage and local audit are the source of truth. Admin visual acceptance is still provisional." | Stage B lineage test; Stage C typed trace tests; Admin provisional note. |
| 6:45-7:45 | Show offline gates and failure matrix. | "The deterministic Gates are offline and network-independent. The fresh failure matrix has no live calls." | `.local/post-visual-final-fa4405a-20260821-01`; failure matrix hash. |
| 7:45-8:45 | Show LangSmith live evidence. | "LangSmith ran once with sanitized metadata only. Raw documents, prompts, private payloads, local paths, and secrets are absent." | `langsmith-live/langsmith-trace-evidence.json`; status `pass`; `run_count=25`; privacy 0. |
| 8:45-9:30 | Show OpenAI live evidence. | "OpenAI ran one bounded competitor-synthesis inference from sanitized inputs. It is not live web research." | `openai-live/openai-competitor-smoke-evidence.json`; `call_count=1`; five categories; budget `$0.007544 <= $0.25`. |
| 9:30-10:00 | Close with the packet boundary. | "The packet inputs keep offline Edge, offline Gates, LangSmith, OpenAI, and the failure matrix separate. Admin remains provisional and broader readiness is out of scope." | Point to this script, the requirement map, the r7 Edge evidence, and the two root01 live-smoke JSON files. |

## Current Evidence Snapshot

```text
Offline evidence root:     .local/post-visual-final-fa4405a-20260821-01
Edge 14-state capture:     .local/post-visual-final-fa4405a-20260821-03-r7/edge-14-state
Edge evidence JSON:        .local/post-visual-final-fa4405a-20260821-03-r7/edge-14-state/browser-evidence.json
Edge state manifest:       .local/post-visual-final-fa4405a-20260821-03-r7/edge-14-state/desktop-states/desktop-state-manifest.json
Edge visual overflow:      screen 07 = 1px within 1px tolerance; screen 08 = 0px
Failure matrix hash:       sha256:c0bd16ea3ea47099e4bf22918c8eadc97f6477b8c0fbb7b3cdac63f4a01b23e8
Backend pytest:            1460 passed, 1 skipped
Backend static checks:     Ruff PASS; strict mypy PASS for 239 source files
Frontend checks:           npm test/typecheck/lint/build PASS
LangSmith external smoke:  pass; run_count 25; flush_count 2; export_errors 0; privacy 0
OpenAI external smoke:     pass; call_count 1; five categories; estimated cost $0.007544; privacy 0
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

## Honest Limitations to State

- The current evidence proves the packet input lanes for the desktop-only evidence set; it does not prove Pilot-Ready, Production-Ready, live web research, or Admin owner-final acceptance.
- The same-case restart test uses deterministic frozen fallback research; it is not proof of a live public-research provider call.
- The LangSmith live smoke proves one sanitized trace lane, not production observability.
- The OpenAI live smoke proves one bounded competitor-synthesis inference, not live web research.
- Admin Console visual acceptance is provisional.
- Pilot-Ready and Production-Ready remain separate unfinished stages.

## Historical 2026-08-16 freeze evidence (preserved, not current)

Warning: the section below is the prior tracked Queue 5 freeze script restored from `git show HEAD:docs/demo/2026-08-16-sellable-demo-script.md`. It is preserved for lineage only. Its `PASS`, `ready`, live LangSmith, live OpenAI, and mobile evidence statements describe the historical 2026-08-16 freeze packet, not the current 2026-08-20 post-visual acceptance record. The old mobile evidence inside this archived text is explicitly excluded from the current desktop-only `1440x1000` owner acceptance.

````markdown
# Queue 5 Sellable Demo Script

**Scope:** Queue 5 Demo Freeze and reviewer defense. Do not claim Pilot-Ready, Production-Ready, live web research, SEC/Yahoo/GDELT/news coverage, or production observability.

**Audience:** founder, investor, reviewer, or capstone jury.

**Runtime target:** 7-10 minutes.

**Implementation code HEAD at the final toolchain/packet refresh:** `72e5856`.

**Evidence pins:** frozen Gates, the real PDF journey and the failure matrix were refreshed on code HEAD `2ec2611e6ed3033b39187ec4709dd5bc31538216`. The only implementation delta to `72e5856` is the TDD-verified confined resolver for those repo-relative Gate D runtime-evidence paths. The full backend/static/frontend toolchain and the strict packet builds run on `72e5856`.

**Canonical PDF fixture:**

```text
tests/fixtures/startup_synthetic_v1/cases/saas/pitch.pdf
```

## Evidence Lanes

Keep these lanes separate. Live LangSmith and OpenAI evidence do not alter canonical Gate D/E semantics, offline determinism, or the frozen packet hash.

| Lane | Required status for Queue 5 Sellable Demo | Current evidence |
| --- | --- | --- |
| `frozen_demo.status` | `pass` | Gate B/C/D-A/D-B/E PASS on `2ec2611e6ed3033b39187ec4709dd5bc31538216` under `.local\queue5-final-2ec2611-20260816-04\gate-{b,c,d-a,d-b,e}\eval-result.json`. |
| `pdf_journey.status` | `pass` | PASS in `.local\queue5-final-2ec2611-20260816-04\pdf-browser\browser-evidence.json`. |
| `langsmith_trace.status` | `pass`, with Admin health `healthy` | PASS in `.local\queue5-live-6ba58c5-langsmith-proof-01\langsmith-trace-evidence.json`. |
| `openai_competitor_smoke.status` | `pass` under the bounded live-inference contract | PASS in `.local\queue5-live-9b9ed8e-openai-proof-03\openai-competitor-smoke-evidence.json`: one call, 5 categories, usage `1231/937/2168`, privacy leaks 0, worst-case `$0.017` under the `$0.25` cap. The Luna model and derived estimated cost come from the configured OpenAI startup settings/pricing path, not from standalone evidence JSON fields. |
| `failure_matrix.status` | `pass` | PASS in `.local\queue5-final-2ec2611-20260816-04\failure-matrix\failure-matrix.json`; 12 named proof tests, offline no-live-calls true, timeout false, matrix hash `sha256:15fec1331c56783845fee89152e6030bbe9b898ea78c3a078f3a31be14a0b98b`. |
| `final_binder.status` | `pass` before external readiness claim | Build the two strict packets and binder only after this script/map are final. Their hashes belong in the external verification record, not in these packet inputs. |

Current stop condition: **Queue 5 is not a closed claim until the final deterministic packet pair, final binder, and independent code/docs/acceptance review are present and passing against the intended evidence set.**

## Before the Audience

Use a fresh local evidence root for offline refreshes. Runtime evidence, screenshots, PDFs, databases, and trace outputs stay untracked.

```powershell
$RunId = Get-Date -Format "yyyyMMdd-HHmmss"
$EvidenceRoot = ".local\queue5-demo-$RunId"
$CommitId = (git rev-parse HEAD).Trim()

uv run --offline --no-sync --no-default-groups `
  --group stage1a --group stage1a-rag-local --group eval-ragas --group dev `
  python -c "from pathlib import Path; import json, sys; from due_diligence_agent.evals.runner import run_public_eval; result=run_public_eval('public_us_frozen_v1', output_dir=Path(r'$EvidenceRoot\gate-b')); print(json.dumps(result.to_json_dict(), sort_keys=True, default=str)); sys.exit(0 if result.gate_b_passed else 1)"
.\scripts\run_stage1b_gate_c.ps1 -OutputDir "$EvidenceRoot\gate-c"
.\scripts\run_stage1b_gate_d.ps1 -OutputDir "$EvidenceRoot\gate-d-a"
.\scripts\run_stage1b_gate_d.ps1 -OutputDir "$EvidenceRoot\gate-d-b"
.\scripts\run_stage1b_gate_e.ps1 -OutputDir "$EvidenceRoot\gate-e"
.\scripts\run_queue5_failure_matrix.ps1 -OutputDir "$EvidenceRoot\failure-matrix" -CommitId $CommitId
.\scripts\smoke_founder_workspace.ps1 `
  -Mode offline-fixture `
  -CaptureScreenshots `
  -RequirePdfUploadJourney `
  -OfflineFixturePath "tests\fixtures\startup_synthetic_v1\cases\saas\pitch.pdf" `
  -BlockedBrowserInjectionOrigin "http://me.kis.v2.scr.kaspersky-labs.com" `
  -DataDir "$EvidenceRoot\data" `
  -ScreenshotDir "$EvidenceRoot\browser" `
  -BrowserEvidencePath "$EvidenceRoot\browser\browser-evidence.json" `
  -AdminTraceEvidencePath "$EvidenceRoot\browser\admin-trace.json"
.\scripts\run_queue5_sellable_demo_freeze.ps1 `
  -OutputDir "$EvidenceRoot\freeze-a" `
  -GateBResult "$EvidenceRoot\gate-b\eval-result.json" `
  -GateCResult "$EvidenceRoot\gate-c\eval-result.json" `
  -GateDFirstResult "$EvidenceRoot\gate-d-a\eval-result.json" `
  -GateDSecondResult "$EvidenceRoot\gate-d-b\eval-result.json" `
  -GateEResult "$EvidenceRoot\gate-e\eval-result.json" `
  -BrowserEvidence "$EvidenceRoot\browser\browser-evidence.json" `
  -DesktopScreenshot "$EvidenceRoot\browser\founder-desktop.png" `
  -MobileScreenshot "$EvidenceRoot\browser\founder-mobile.png" `
  -SamplePdf "$EvidenceRoot\browser\sample-report.pdf" `
  -DemoScript "docs\demo\2026-08-16-sellable-demo-script.md" `
  -CapstoneMap "docs\demo\2026-08-16-capstone-requirement-evidence-map.md"
.\scripts\run_queue5_sellable_demo_freeze.ps1 `
  -OutputDir "$EvidenceRoot\freeze-b" `
  -GateBResult "$EvidenceRoot\gate-b\eval-result.json" `
  -GateCResult "$EvidenceRoot\gate-c\eval-result.json" `
  -GateDFirstResult "$EvidenceRoot\gate-d-a\eval-result.json" `
  -GateDSecondResult "$EvidenceRoot\gate-d-b\eval-result.json" `
  -GateEResult "$EvidenceRoot\gate-e\eval-result.json" `
  -BrowserEvidence "$EvidenceRoot\browser\browser-evidence.json" `
  -DesktopScreenshot "$EvidenceRoot\browser\founder-desktop.png" `
  -MobileScreenshot "$EvidenceRoot\browser\founder-mobile.png" `
  -SamplePdf "$EvidenceRoot\browser\sample-report.pdf" `
  -DemoScript "docs\demo\2026-08-16-sellable-demo-script.md" `
  -CapstoneMap "docs\demo\2026-08-16-capstone-requirement-evidence-map.md"
```

The bounded LangSmith and OpenAI live smokes for this evidence cycle have already passed. Present the saved side evidence; do not spend another live call during the demo.

```powershell
.\.venv\Scripts\python.exe -c "import os; from dotenv import dotenv_values; values=dotenv_values('.env'); print('LANGSMITH_API_KEY_PRESENT=' + str(bool(os.environ.get('LANGSMITH_API_KEY') or values.get('LANGSMITH_API_KEY'))))"
.\.venv\Scripts\python.exe -c "import json, pathlib; p=pathlib.Path(r'.local\queue5-live-6ba58c5-langsmith-proof-01\langsmith-trace-evidence.json'); d=json.loads(p.read_text(encoding='utf-8')); print({'status': d['status'], 'credential_present': d['credential_present'], 'live_call_succeeded': d['live_call_succeeded'], 'admin_health_status': d['workflow']['admin_langsmith_health']['status'], 'privacy_leak_count': d['privacy']['privacy_leak_count']})"
.\.venv\Scripts\python.exe -c "import json, pathlib; p=pathlib.Path(r'.local\queue5-live-9b9ed8e-openai-proof-03\openai-competitor-smoke-evidence.json'); d=json.loads(p.read_text(encoding='utf-8')); print({'status': d['status'], 'call_count': d['call_count'], 'live_call_succeeded': d['live_call_succeeded'], 'inference_label': d['inference_label'], 'research_label': d['research_label'], 'privacy_leak_count': d['privacy']['privacy_leak_count'], 'total_tokens': d['usage']['total_tokens'], 'worst_case_usd': d['budget']['worst_case_usd']})"
```

Build the final fail-closed binder from the two deterministic packet runs and the separately saved live evidence:

```powershell
.\scripts\run_queue5_verification.ps1 `
  -OutputDir "$EvidenceRoot\verification" `
  -FrozenPacket "$EvidenceRoot\freeze-a\sellable-demo-freeze-packet.json" `
  -PdfBrowserEvidence "$EvidenceRoot\browser\browser-evidence.json" `
  -LangSmithEvidence ".local\queue5-live-6ba58c5-langsmith-proof-01\langsmith-trace-evidence.json" `
  -OpenAICompetitorEvidence ".local\queue5-live-9b9ed8e-openai-proof-03\openai-competitor-smoke-evidence.json" `
  -FailureMatrix "$EvidenceRoot\failure-matrix\failure-matrix.json" `
  -DemoScript "docs\demo\2026-08-16-sellable-demo-script.md" `
  -CapstoneMap "docs\demo\2026-08-16-capstone-requirement-evidence-map.md"
```

Stop before the demo if any required lane is missing, stale, cross-case, privacy-leaking, or failed.

## 7-10 Minute Run

| Time | Action | Say | Evidence cue |
| --- | --- | --- | --- |
| 0:00-0:45 | State the boundary. | "This is Founder Launch Intelligence in delivery profile B: Founder Workspace over the Python application/API, with Streamlit Admin separate. Frozen Gates are offline and deterministic. LangSmith and OpenAI evidence are separate side lanes." | Show lane table; frozen packet stays offline and live fields remain side evidence. |
| 0:45-1:30 | Open Founder Workspace. | "The founder starts from a PDF upload, not a prompt, industry picker, or prepared catalog." | `http://127.0.0.1:3000/`; canonical fixture is one `application/pdf`, 1523 bytes. |
| 1:30-2:30 | Upload the PDF and run primary analysis. | "Incomplete input is valid. The system separates source facts, inference, contradictions, unsupported claims, and insufficient data." | Same case `80836367-af35-4a95-86dd-8e871f47905c`; 18 profile fields. |
| 2:30-3:45 | Approve Gate 2 and run deep analysis. | "Deep analysis continues the same case and adds market, metrics, competitors, questions, GTM, and action planning without re-upload." | PDF upload only; no prompt/industry selection; no live web research; external network calls 0. |
| 3:45-5:00 | Show conclusions and limitations. | "Readiness, confidence, and coverage are separate. Recommendations are tied to evidence, gaps, contradictions, or explicit limitations." | 7 GTM dimensions, 22 readiness dimensions, 5 competitor categories, 8 competitor rows, 20 questions. |
| 5:00-6:15 | Approve Gate 4 and download artifacts. | "JSON, HTML, and PDF come from one approved snapshot for the same case." | Gate 4 approved; report id `1f87d2cd-9df7-5f6b-b0e1-3117059744ae`, revision 1, checksum `c103e0231581981cf852936394dc62528162eb4c4df6596ef50f6a5f3d0de7c4`. |
| 6:15-7:15 | Open Admin Console. | "Admin is operator proof: local audit, graph nodes, privacy, evals, cost/latency, retries, integrity, and exporter health." | Admin trace has 21 successful rows and same case/run/report lineage. Offline LangSmith health is `disabled/local_audit`. |
| 7:15-8:15 | Show LangSmith side evidence. | "One real startup LangGraph workflow emitted sanitized LangSmith spans. Raw PDF, text, filenames, prompts, PII, local paths, and secrets are absent." | `langsmith_trace_evidence@1`, `status=pass`, 22 runs, 20 nodes, Admin health `healthy`, privacy leaks 0. |
| 8:15-9:00 | Show OpenAI competitor smoke result. | "This was a bounded live inference smoke, not live web research. It used only a sanitized profile plus frozen competitor/source summaries after Gate 2." | `openai_competitor_smoke_evidence@1`, `status=pass`, `call_count=1`, 5 categories, total tokens 2168, privacy leaks 0, worst-case `$0.017` under `$0.25`. |
| 9:00-9:45 | Close with failure matrix, deterministic packet, and fail-closed binder. | "Sellable Demo readiness is claimed only when frozen Gates, PDF journey, LangSmith trace, OpenAI smoke, privacy, deterministic packet, failure matrix, same-case report lineage, and reviews all pass." | Show final verification record; if `freeze-final-a/b` or `verification-final` is missing, call it a final-ready candidate rather than closed Queue 5. |

## Current Local PDF Evidence Snapshot

```text
evidence root: .local\queue5-final-2ec2611-20260816-04\pdf-browser
case_id: 80836367-af35-4a95-86dd-8e871f47905c
run_id: startup-api-80836367-af35-4a95-86dd-8e871f47905c
upload: application/pdf, 1523 bytes
intake: pdf_upload_only, observed_from_dom=true, selected_file_count=1
selection: prompt_selection_used=false, industry_selection_used=false
external network calls: 0
desktop: 1440x1000
mobile: 390x844
Admin nodes: 21
LangSmith health in offline PDF run: disabled / local_audit
report_id: 1f87d2cd-9df7-5f6b-b0e1-3117059744ae
report_revision: 1
report checksum: c103e0231581981cf852936394dc62528162eb4c4df6596ef50f6a5f3d0de7c4
charts: 2 cards, 7 points
sample PDF: sample-report.pdf
```

## Live Side Evidence Snapshot

```text
LangSmith live: .local\queue5-live-6ba58c5-langsmith-proof-01\langsmith-trace-evidence.json
LangSmith status: pass
LangSmith run_count: 22
LangSmith workflow nodes: 20
LangSmith Admin health: healthy
LangSmith privacy leaks: 0

OpenAI live: .local\queue5-live-9b9ed8e-openai-proof-03\openai-competitor-smoke-evidence.json
OpenAI status: pass
OpenAI configured model: gpt-5.6-luna (runtime settings, not a standalone evidence JSON field)
OpenAI label: live_inference / not_live_web_research
OpenAI call_count: 1
OpenAI categories: direct, indirect, substitute, do_nothing, potential_entrant
OpenAI usage: input=1231, output=937, total=2168
OpenAI cost guard: derived estimate about $0.006853 from configured pricing plus recorded usage; evidence worst-case $0.017 <= $0.25
OpenAI privacy leaks: 0
```

## Toolchain Snapshot

```text
backend pytest on 72e5856 implementation code: 1339 passed, 1 expected Windows symlink skip
Ruff: PASS
strict mypy: PASS, 227 source files
frontend tests: PASS, 104 aggregate tests
frontend typecheck: PASS before and after production build
frontend lint: PASS
frontend production build: PASS
```

## Recovery Cues

- If a port is busy, rerun the workspace/smoke script with alternate local ports and a unique evidence root.
- If local browser middleware injects a parser script, rerun only with the exact observed local parser origin through the dedicated block option; do not broaden the exception.
- If Gate D raw hashes differ but semantic and persisted fingerprints match, continue; the packet validates semantic determinism separately from raw run artifacts.
- If LangSmith is missing or unhealthy, Queue 5 is not ready.
- If OpenAI evidence is missing, failed, over budget, multi-call, privacy-leaking, or labeled as live web research, Queue 5 is not ready.
- If any artifact contains a local absolute path, email, bearer token, `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, or `sk-` value, stop and treat the lane as failed.

## Honest Limitations to State

- The frozen demo proves a sellable local evidence path, not a production SaaS.
- The LangSmith trace proves one bounded sanitized workflow trace, not full production observability.
- The OpenAI competitor smoke is live inference from frozen summaries, not live market or web research.
- Pilot-Ready requires permitted real cases, measured parser/OCR failure handling, retention, backup, and pilot success metrics.
- Production-Ready requires auth, tenancy, security, object storage, durable jobs, monitoring, backup/restore, provider/licensing decisions, and a separate security specification.
````
