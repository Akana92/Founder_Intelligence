# Queue 2 verification — 2026-08-14

## Scope and identity

- Branch: `main`
- Original merge verification commit: `a7e807bc0860bf94cc8009b4f98ec973168ef352`
- Closure verification commit: `759482f8760f71eec6395ffffbc9ac2b9265d8d8`
- Mode: fully offline; OpenAI keys blank; LangSmith/LangChain tracing disabled; Hugging Face and Transformers offline.
- Result: Queue 2 frozen/offline closure passed after the requirement-by-requirement [closure audit](./2026-08-14-queue2-closure-audit.md). This does not claim Queue 3–5 or the final Sellable Demo are complete.

## Closure supplement

The initial PASS report proved the broad Gate C/D/E and regression state, but the child plans still contained unchecked or partially evidenced Queue 2A–2D requirements. The closure audit found and remediated the remaining Queue 2 functional gaps:

- `723ca77`: production Gate D fixture-manifest validation before startup analysis.
- `42481e7`: unique, non-overwriting Gate D/E output-root contract and CLI collision behavior.
- `9f3fd25`: durable exporter-degradation marker, query DTO, and bounded Admin rendering.
- `f93000b`, `9ecc02e`, `759482f`: byte-level fixture hash and LF line-ending portability.
- `4ed2898`: stable persisted disclosure fingerprints across independent processes.

## Automated gates

| Gate | Result | Key evidence |
| --- | --- | --- |
| Gate C — secure ingest / Queue 1 regression | PASS | Final root `output/verification/queue2-closure-20260814-gate-c-final`; canonical profile determinism and restart/profile determinism true; PDF, DOCX, JPEG, PNG, CSV, XLSX and safe ZIP covered; privacy leaks `0`; denied Gate 2 external calls `0` |
| Gate D — startup deep analysis | PASS | Final HEAD roots `output/verification/queue2-closure-20260814-gate-d-head-c` and `output/verification/queue2-closure-20260814-gate-d-head-d`; both record commit `759482f8760f71eec6395ffffbc9ac2b9265d8d8`; readiness scored; maximum questions `3`; contradictions `5`; unsupported claims `4`; report and trace sections present; privacy leaks `0`; 4/4 semantic fingerprints and 4/4 canonical persisted fingerprints match across independent outer processes |
| Gate E — combined verticals | PASS | Final HEAD root `output/verification/queue2-closure-20260814-gate-e-head`, commit `759482f8760f71eec6395ffffbc9ac2b9265d8d8`; Public Company and Startup both passed; shared schema compatible; report repository sanitized; checkpoint recovery and ReportLab PDF fallback confirmed |

Commands:

```powershell
.\scripts\run_stage1b_gate_c.ps1 -OutputDir .tmp-merge-gate-c
.\scripts\run_stage1b_gate_d.ps1 -OutputDir .tmp-merge-gate-d
.\scripts\run_stage1b_gate_e.ps1 -OutputDir .tmp-merge-gate-e-post-main
.\scripts\run_stage1b_gate_c.ps1 -OutputDir output\verification\queue2-closure-20260814-gate-c-final
.\scripts\run_stage1b_gate_d.ps1 -OutputDir output\verification\queue2-closure-20260814-gate-d-head-c
.\scripts\run_stage1b_gate_d.ps1 -OutputDir output\verification\queue2-closure-20260814-gate-d-head-d
.\scripts\run_stage1b_gate_e.ps1 -OutputDir output\verification\queue2-closure-20260814-gate-e-head
```

## Regression and product checks

- Focused Queue 2 closure regression: `338 passed`.
- Full backend: `1101 passed, 1 skipped` in 171.01 seconds. The skip is the expected Windows symlink-privilege case.
- Ruff: all checks passed.
- Strict mypy: no issues in 210 source files.
- Founder frontend: unit/contract tests passed; TypeScript passed; ESLint passed.
- Production Next.js build passed. The root route remained static and the direction contract was injected into and verified against the emitted `index.html`.
- Launcher contract: 7 tests passed.
- Actual offline Founder smoke passed: local API and Next UI started, external network snapshots stayed clean, Gates 2–4 completed and the report artifact was downloaded. A browser/API smoke also loaded `/`, `/admin`, `/comparables`, and `/docs` locally with no console errors.
- Independent closure review: PASS after the fresh HEAD Gate D/D/E rerun; no remaining code, privacy, evidence-ledger, or correctness blocker was found for the frozen/offline Queue 2 scope.

Raw artifact hashes, report artifact ids, and metric-pack artifact hashes remain run-bound when they include run identity or timestamped artifact references. Queue 2 determinism is asserted through canonical semantic fingerprints and canonical persisted fingerprints, not raw timestamped file hashes.

## Known non-blocking warnings

- Native WeasyPrint libraries are unavailable on this workstation; Gate E explicitly proved the ReportLab PDF fallback.
- LangGraph reports a future strict-msgpack registration warning for `AnalysisPlan`.
- Starlette reports an `httpx` deprecation warning in the frozen evaluator.

These warnings do not invalidate the offline gates, but should be addressed during Queue 3–5 hardening.

## Next step

Queue 3 is unblocked. It must finish the bounded graph/Reflexion product path before Queue 4 deep-analysis UX/report work and Queue 5 Demo Freeze.
