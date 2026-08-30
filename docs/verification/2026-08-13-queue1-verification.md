# Queue 1 verification evidence

Date: 2026-08-13

Branch: `codex/founder-sales-ready-hybrid`

Verified code commit: `459fe343e8f203eddb426dd8cdfb44eed3a74ec4`

Queue 1 status: **GREEN**

Queue 1 now provides the universal startup intake and canonical profile boundary required by the completion staircase. This is a Queue 1 milestone, not a declaration that Queues 2–5 or the whole product roadmap are complete.

## Product behavior proved

- A founder can create a private deterministic case, upload a supported document, approve Gate 2, continue through Gate 3, receive a canonical startup report, approve its exact Gate 4 tuple, and download a valid PDF.
- Live and deterministic modes share only the private upload inbox. Their metadata, checkpoints, reports, artifacts, audit spools, budgets, and normalized stores remain isolated.
- The canonical startup profile contains all 18 required fields with explicit grounded, missing, inferred, partial, conflicting, or not-applicable status instead of fabricated values.
- Conflicting ARR evidence and partial or damaged inputs remain visible.
- Spreadsheet metrics are bounded deterministically to the profile contract; values and evidence references stay aligned and truncation is represented by `deterministic_spreadsheet_metrics_truncated`.
- The canonical report is bound to the persisted profile tuple and exposes structured metrics, evidence, risks, gaps, reflexion output, JSON, HTML, and PDF artifacts.
- Founder UI and Admin/Tracing remain separate product surfaces.

## Frozen fixture identities

| Artifact | SHA-256 |
|---|---|
| `startup_profile_v1/manifest.json` | `721a5ceb0840eb578bdb25bba4cc4a9e4c163b7b0c0950e1c946f47dff006779` |
| `startup_profile_v1/expected_profile.json` | `ef600d08f013021df4c871ffed22f964c076876e10ed2bd7030d9d2fcccff54f` |
| Canonical Queue 1 profile | `sha256:a2e84e3391035484236b2c31042191585af726e7812b1ea14f6fe3ec66181eb7` |
| Canonical profile ID | `d6481aed-af9a-5760-b6e8-ac2fa408a83b` |

Active parser matrix: `csv`, `docx`, `jpeg`, `pdf`, `png`, `safe_zip`, `xlsx`.

## Canonical Gate C A/B

Both runs used the offline PowerShell entrypoint. It blanked OpenAI keys, disabled LangSmith and legacy LangChain tracing, enabled Hugging Face/Transformers offline mode, and executed the embedded Gate B regression.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_stage1b_gate_c.ps1 `
  -OutputDir output\gate-c\startup_secure_ingest_v1-queue1-final-a

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_stage1b_gate_c.ps1 `
  -OutputDir output\gate-c\startup_secure_ingest_v1-queue1-final-b
```

| Evidence | Run A | Run B |
|---|---:|---:|
| Gate C | PASS | PASS |
| Embedded Gate B | PASS | PASS |
| Privacy leaks | 0 | 0 |
| Denied Gate 2 external calls | 0 | 0 |
| Profile field/status coverage | 100% | 100% |
| Profile determinism | true | true |
| Restart equivalence | true | true |
| Contradiction retention | true | true |
| Canonical profile hash | `sha256:a2e84e3391035484236b2c31042191585af726e7812b1ea14f6fe3ec66181eb7` | same |
| `eval-result.json` SHA-256 | `1bdd6d89806ac724f64d70f9c7f1c33bc8b4d65e4570045e21c38df1a0dd766d` | `92253c5982fcbce90b8e0b41161ec63d14a9051ad487c340052bc3a9a984460a` |

The two evaluation files differ only in run-specific evidence such as timing and run directories; the canonical profile identity is identical.

## Full automated verification

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider -o filterwarnings= -q `
  --basetemp .tmp-q1-full-backend-commit-459fe34
```

Result: `888 passed, 1 skipped, 1 warning in 106.88s`.

The single skip is the Windows symlink-boundary test because this account lacks symlink privilege (`WinError 1314`). The same containment and source-hash boundaries are exercised by non-symlink tests.

```powershell
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m mypy --strict src
```

Results: Ruff clean; strict mypy clean across `193` source files.

```powershell
cd frontend\founder
npm test
npm run typecheck
npm run lint
npm run build
```

Results: `50/50` frontend tests passed; TypeScript and ESLint passed; Next.js production build passed with five static pages and all Founder startup API proxy routes present.

## Real offline workspace smoke

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_founder_workspace.ps1 `
  -Mode offline-fixture -ApiPort 18004 -WebPort 13004 `
  -DataDir .tmp-q1-founder-offline-smoke-final
```

Result: `startup_founder_workspace_smoke_passed`; API and Web process trees were cleaned in `finally`, and all three network snapshots were clean.

Observed analysis trace:

`ingest:success → parse:success → classify_redact:success → evidence:success → claims:success → primary_profile:success → disclosure:success → plan:success → profile_enrichment:success → metrics:success → financial_analysis:blocked → risk_analysis:blocked → market_analysis:blocked → reflexion:success → report:success`

The three deep provider-backed modules are intentionally `blocked` in deterministic offline mode; the graph reports that boundary and still produces the primary analysis, metrics, reflexion result, and report instead of crashing or fabricating live research.

Smoke artifact evidence:

| Artifact | Result |
|---|---|
| Canonical report | `startup_report_snapshot.v1` |
| Metrics | `PARTIAL`, 27 structured rows |
| Report hash | `sha256:1ff533a41e64a43fc3fa226be1694eb434fa06340265e282b151690c50967945` |
| JSON | 18,705 bytes; SHA-256 `730d0200a873da0484aeb318a8bbf35c730b2ab6120c0616c44b7aee8f642e25` |
| HTML | 29,397 bytes; SHA-256 `652b84e7dd74535595e81b83e164c64ec8301b2ec9affbb73102d02f4ed67ba6` |
| PDF | 15,669 bytes; `%PDF-1.4`; SHA-256 `2cb3031461174ff2db1884db2d996d869974c7ddcf16dbc49affd8e0053d0bd9` |
| Audit events | 17 |

A binary privacy scan of the outward JSON/HTML/PDF, audit spool, workflow checkpoints, and runtime stores found zero matches for the synthetic email, token, upload filename, workspace path, or user path. Internal artifact repository storage locators are deliberately excluded from this outward-surface assertion.

## Bounded live OpenAI connectivity smoke

After every offline gate passed, one direct OpenAI Responses request was made through the project settings with `max_retries=0`, a 20-second timeout, a 64-output-token ceiling, and no response body, request ID, or key printed.

Result: `PASS`; model `gpt-5.6-luna`; response received; output non-empty; `11` input tokens and `5` output tokens.

This proves the configured key, priced model, SDK, and network connection. It is deliberately not presented as a full paid live-case analysis; full live provider orchestration remains subject to the product's per-call and per-case budget gates.

## Independent review

The scoped independent code review found no implementation or privacy blocker. Its one MUST finding was to ensure the new CSV smoke fixture was tracked; the fixture is included in commit `459fe34`. Its SHOULD recommendation was to automate the real API path; `test_startup_api_real_deterministic_composition_builds_uploaded_metrics` was added, and the complete API module passed `18/18` before the final `888`-test run.

## Known non-blocking notes

- WeasyPrint native libraries are unavailable on this Windows host; the verified ReportLab fallback produces the final PDF.
- LangGraph warns that `AnalysisPlan` must be explicitly allowlisted before a future strict msgpack default. Current checkpoint recovery passes; this is a future-compatibility task.
- Starlette reports the existing `httpx` TestClient deprecation warning.
- The local `.env` is ignored and was not read or committed as plaintext by the verification workflow. No key value appears in logs or artifacts.

## Next roadmap boundary

Queue 2 is next: provider-backed primary and deep startup analysis with web/market research, financial calculations, explicit cost envelopes, resilient tool fallback, and live tracing. Queue 1 remains the stable deterministic fallback and evidence/profile foundation for that work.
