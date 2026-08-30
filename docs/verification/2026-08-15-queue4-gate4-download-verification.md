# Queue 4 Founder Gate 4 and artifact download verification — 2026-08-15

## Scope and result

- Browser-visible Gate 4/download proof commit: `321fd612a598c0ebc9991f817cd1707b1c0256de`.
- Result: the existing production Gate 4 approval and JSON/HTML/PDF delivery path is now proven through the real Founder browser journey for the deterministic frozen/offline boundary.
- This closes only the browser-visible Gate 4/download slice. Startup charts are now verified separately; Queue 5 Demo Freeze and the Sellable Demo Gate remain open.
- No paid OpenAI, LangSmith, Yahoo Finance, GDELT, news, web-provider, or other external network call was made.

## Production and integration evidence

| Requirement | Production evidence | Integration/test evidence | Status |
| --- | --- | --- | --- |
| Visible Gate 4 review | `WorkspaceActionPanel` exposes approve/reject controls only for a validated canonical report tuple | Browser smoke waits for and clicks `Зафиксировать версию`; controller tests bind the decision to exact hash/revision | complete |
| Draft artifact state | Founder UI exposes JSON/HTML while PDF remains explicitly disabled before approval | CDP contract verifies exact draft paths and `PDF после фиксации` before the click | complete |
| Same-case approval | Orchestrator keeps the active case and submits the current snapshot hash/revision | Smoke preserves the draft case id and rejects any approved artifact path for another case | complete |
| Same-origin artifacts | API client emits fixed same-origin report artifact paths | Smoke validates exact `/api/startup/cases/{case_id}/report/{json,html,pdf}` paths and the browser origin | complete |
| Real PDF delivery | Approved Gate 4 calls the PDF artifact endpoint and refreshes to `report_pdf_ready` | Browser fetches the visible PDF link with `Accept: application/pdf`, validates status/content type and `%PDF` magic | complete |
| Bounded browser proof | Artifact validation must not consume an unbounded response | Optional `Content-Length` precheck plus streaming reader enforces a 5 MB cap and cancels on overflow | complete |
| Desktop/mobile evidence | Final approved panel and JSON/HTML/PDF links must be visible, not only present in the DOM | Deterministic scroll/viewport assertion and manual screenshot inspection passed at 1440×1000 and 390×844 | complete |
| Offline/privacy boundary | Frozen flow must not use external providers or expose private internals | Three no-egress snapshots passed; UI shows bounded tuple data and artifact links only | complete |

## TDD evidence

1. Initial RED: focused browser-QA test failed because the CDP helper did not click Gate 4 or validate the visible PDF artifact.
2. Minimal GREEN: helper verified draft JSON/HTML, blocked PDF, approval, approved paths, response content type and PDF magic; the focused test passed.
3. Review RED: same-case continuity, byte bounding, and viewport visibility were added as failing requirements.
4. Real-smoke RED: same-origin proxy omitted `Content-Length`; the first bounded implementation failed closed before reading the valid PDF.
5. Minimal GREEN: bounded streaming accepted absent length, rejected invalid/oversized declared length, and cancelled reads above 5 MB.
6. Visual RED: smooth scrolling produced an empty mobile screenshot, then a strict viewport wait exposed that the final Gate 4 panel was not visible.
7. Minimal GREEN: coordinate-based deterministic scrolling placed the final panel inside both viewports; independent code review returned PASS.

## Verification evidence

```text
browser-QA pytest                     -> 13 passed
node --check capture helper           -> PASS
full backend pytest                   -> 1143 passed, 1 expected Windows symlink skip
Ruff                                  -> PASS
strict mypy                           -> PASS, 219 source files
frontend tests                        -> PASS, 98 tests
frontend typecheck / lint / build     -> PASS / PASS / PASS
real offline API/browser smoke        -> PASS
```

The final real smoke ran the local API and Next app on loopback ports, uploaded the frozen founder metrics CSV, passed Gates 2 and 3, verified Profile/GTM/report/Readiness, then approved Gate 4 in the browser. Both desktop and mobile runs preserved the same case id, exposed exact JSON/HTML/PDF links, returned `application/pdf` with `%PDF`, and showed the final `Инвестиционный пакет сформирован` panel without horizontal overflow.

Runtime screenshots and smoke data were written outside the repository and were not committed:

- `C:\Users\Akana\.codex\visualizations\2026\08\14\019ffeb3-c3f0-74d0-9129-3b8961cf9456\q4-gate4-smoke-r4\founder-desktop.png`
- `C:\Users\Akana\.codex\visualizations\2026\08\14\019ffeb3-c3f0-74d0-9129-3b8961cf9456\q4-gate4-smoke-r4\founder-mobile.png`

## Gate decision

PASS for the Queue 4 browser-visible Gate 4/download slice at the deterministic frozen/offline boundary.

Queue 4 is now complete for the deterministic frozen/offline scope after the separate startup-chart verification. Queue 5 Demo Freeze and the Sellable Demo Gate remain open.
