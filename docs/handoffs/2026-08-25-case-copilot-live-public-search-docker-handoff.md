# Capstone N3 — live public search and Docker handoff

**Updated:** 2026-08-25

**Worktree:** `C:\Users\Akana\.codex\worktrees\6e2b\Capstone N3`

**Branch:** `codex/case-copilot-docker`

**Implementation checkpoint:** `85a6251` — `Use current Case Copilot revision for saves`

**Status:** user-testable web + API + optional Streamlit admin are running through Docker Compose; a real consented OpenAI public-search job produced accepted public benchmarks and recalculated scenario metrics.

## Start here in a new chat

Read, in this order:

1. `docs/handoffs/2026-08-22-case-copilot-v1-new-chat-prompt.md`;
2. `docs/superpowers/specs/2026-08-22-founder-case-copilot-v1-design.md`;
3. `docs/superpowers/specs/2026-08-22-founder-case-copilot-scenario-metrics-addendum.md`;
4. `docs/superpowers/plans/2026-08-22-founder-case-copilot-scenario-launch.md`;
5. `docs/handoffs/2026-08-24-capstone-n3-docker-packaging-handoff.md`;
6. this handoff.

Do not repeat already accepted Case Copilot Tasks 1–11 or Docker Tasks 0–4. Preserve the existing dirty WIP. Do not run reset, clean, checkout, revert, or stash. Local commits are authorized when safe; do not push, merge, deploy, or publish images unless the owner explicitly requests it.

## Credential and tracing boundary

- OpenAI and LangSmith credentials are loaded only from `D:\Agents\Projects\Capstone N3\.env` through Compose `--env-file`.
- Never print, copy into source, commit, bake into an image, or include credential values in logs or handoffs.
- `OPENAI_API_KEY` is configured. `OPENAI_STARTUP_API_KEY` is optional and currently uses the supported fallback to `OPENAI_API_KEY`.
- `LANGSMITH_API_KEY` is configured and passed to API/admin containers.
- LangSmith tracing remains intentionally disabled unless `DDA_LANGSMITH_TRACING=true` is explicitly set.

## Exact Docker commands

Port `8000` is occupied by another local project, so this verified profile publishes the API on `8180`.

Start or refresh the complete stack:

```powershell
$env:API_PORT='8180'; docker compose --env-file 'D:\Agents\Projects\Capstone N3\.env' --profile admin up -d
```

Open:

- Founder interface: `http://127.0.0.1:3000/`
- API docs: `http://127.0.0.1:8180/docs`
- API health: `http://127.0.0.1:8180/health/live`
- Streamlit admin: `http://127.0.0.1:8501/`

Stop without deleting the named data volume:

```powershell
$env:API_PORT='8180'; docker compose --env-file 'D:\Agents\Projects\Capstone N3\.env' --profile admin down
```

Never add `-v` unless the owner explicitly asks to delete persisted case data.

## Verified runtime state

The backend image was rebuilt from commit `e4e8e41` and API/admin were force-recreated without removing the data volume. Fresh checks returned:

- web: HTTP `200` on `127.0.0.1:3000`;
- API: `{"status":"ok"}` on `127.0.0.1:8180/health/live`;
- admin: HTTP `200`, body `ok` on `127.0.0.1:8501/_stcore/health`;
- all three Compose services: `healthy`.

The Streamlit fixture packaging failure is already fixed by `27d9a311` and covered by `dbb8b4c8`. The admin is no longer crashing on the missing `/app/.venv/.../tests/fixtures/.../manifest.json` path.

## Real public-search proof

This was not the deterministic fixture path. A real consented OpenAI Responses web-search job completed through the Docker API and persisted across API/admin recreation:

- case: `56232d3a-992d-42ba-8b6f-976ed15eed6d`;
- job: `b1d67e10-d72f-4365-84a5-e9da4e64dbcf`;
- terminal status: `partial`, with no failure reason;
- revision: `1 -> 2`;
- accepted entries: `3` public benchmarks;
- rejected entries: `2` candidates that did not satisfy acceptance rules;
- citations: `3`;
- source refs: `3`;
- changed blocks: `public_benchmarks, scenarios`.

The first accepted input is `monthly_price`, provenance `public_benchmark`, range `14,990–29,990 KZT/month`. Its formula/rationale, dependencies, source refs, and validation plan remain present in the API response.

The base scenario was recalculated deterministically:

- monthly price changed from the prior planning range `35,000–40,000 KZT` to the accepted public benchmark range `14,990–29,990 KZT`;
- MRR changed from `1.4M–2.0M KZT/month` to `599,600–1,499,500 KZT/month`;
- MRR provenance remains `deterministic_calculation`;
- formula remains `Monthly price multiplied by projected paying customers`;
- dependency refs, source refs, and validation plan are present.

This proves the required flow: public search fills eligible public benchmark gaps, advances the same-case revision, and refreshes scenario metrics. It does not invent private startup facts.

## Public-search resilience fix

Commit `e4e8e41` adds one bounded application-owned retry for transient provider failures only:

- total attempts: at most `2`;
- retries: timeout, OpenAI connection failures, rate limits/HTTP `429`, and server errors/HTTP `5xx`;
- no retry: invalid/incomplete/citation-less output, authentication/permission failures, and stable non-`429` 4xx errors;
- OpenAI SDK retries remain disabled (`max_retries=0`), so retry behavior stays explicit and auditable;
- audit events contain stable `attempt` and `retry_count` metadata and never raw provider exception text;
- one `20,000`-token reservation covers one user-triggered research operation, including its single transient retry, then reconciles or releases exactly once.

Independent review verdict: APPROVE, no blocking findings.

## Loader and user feedback behavior

Async founder actions show a Russian busy label/spinner and disable duplicate input. Public research has visible stages:

1. searching sources;
2. recalculating metrics;
3. complete, partial, deferred, or error with an explicit reason.

The controller polls a running research job to a terminal state, stops at a safe limit, clears busy/activity state, refreshes scenarios only when allowed, and never displays fabricated metric deltas for deferred/failed jobs.

## 2026-08-25 UI unblock after owner screenshot

Commit `02166a5d` fixes the right-rail Case Copilot question card after the owner reported that selecting `Публичный поиск` showed `Не удалось сохранить ответ` and appeared stuck.

- Public-search failure copy no longer says the app failed to save a founder answer.
- Switching answer modes and toggling public-search consent clears stale local errors.
- While public research is running, the primary button says `Идёт публичный поиск…` and the panel explains that benchmark/metric changes will appear after completion.
- The boundary remains intact: public research can add external public benchmarks and refresh scenario metrics, but it does not fill or promote private MRR/revenue/cash/burn facts.

Fresh verification after this fix:

```text
node --experimental-strip-types components/founder-workspace-controller.test.ts -> 116 passed
npm test                                                                  -> PASS
npm run typecheck                                                         -> PASS
npm run lint                                                              -> PASS
.venv\Scripts\python.exe -m pytest tests/api/test_startup_case_copilot_contract.py -k "research" -> 11 passed
```

Docker was rebuilt and started with:

```powershell
$env:API_PORT='8180'; $env:WEB_PORT='3000'; $env:ADMIN_PORT='8501'; docker compose --env-file 'D:\Agents\Projects\Capstone N3\.env' --profile admin up -d --build
```

Current container checks:

- API: `http://127.0.0.1:8180/health/live` -> `{"status":"ok"}`;
- web: `http://127.0.0.1:3000/` -> HTTP `200`;
- admin: `http://127.0.0.1:8501/_stcore/health` -> HTTP `200 ok`;
- `docker compose ps` shows api/web/admin `healthy`;
- container `FOUNDER_CASE_FIXTURE_MODE` is `deterministic_offline`, so this currently verifies the safe deterministic public benchmark provider, not a new live OpenAI web-search call.

## 2026-08-25 save/progress fix after public research

Commit `85a6251` fixes the real `POST /assumptions -> 409 case_revision_conflict` that prevented the owner from saving a manual answer after public research.

Root cause and fix:

- completed public research refreshed the orchestrator from case revision `N` to `N+1`;
- the React event handler could still close over the older rendered snapshot and submit `expected_case_revision: N`;
- `currentCopilotRevision()` now reads `orchestrator.current.getSnapshot()` at click time and uses the rendered snapshot only as a fallback;
- fact, assumption, `Не знаю`, and fallback research mutations all share this live revision lookup;
- there is no automatic retry that could duplicate a founder mutation.

The owner case that exposed the bug was inspected read-only. Its Docker log sequence was `POST /research/plans -> 201`, `POST /research/jobs -> 202`, then `POST /assumptions -> 409`. No invented revenue value was written to that case during diagnosis.

The product boundary is unchanged: a manual revenue answer remains `founder_statement`; public research sends `requested_private_value: null`; neither becomes `source_fact` automatically.

Fresh verification for the fix:

```text
RED: node --experimental-strip-types components/founder-workspace-controller.test.ts
     -> 116 passed, 1 failed on stale rendered revision lookup
GREEN: same targeted suite -> 117 passed
npm test                    -> PASS
npm run typecheck           -> PASS
npm run lint                -> PASS
Docker Next.js build        -> PASS
docker compose ps           -> api/web/admin healthy
web                         -> HTTP 200
API /health/live            -> HTTP 200 {"status":"ok"}
admin /_stcore/health       -> HTTP 200
independent code review     -> APPROVE, no findings
```

An independent configured-provider API smoke also proved the complete revision chain without touching the owner case or calling live OpenAI: public research completed at `1 -> 2`, the following founder assumption returned HTTP `200` at `2 -> 3`, and the final case revision was `3`.

Owner verification path:

1. Open `http://127.0.0.1:3000/` and create a test analysis. The current frontend does not yet expose persisted-case history after a container/browser restart.
2. For a private revenue/MRR question, run consented `Публичный поиск` if market context is wanted.
3. Switch to `Ответ`, fill the required structured fields, and press `Сохранить ответ`.
4. Expected: visible `Сохраняю ответ…`, no stale `409`, then refreshed Case Copilot state and the next question/updated scenarios.
5. If the private value is unavailable, choose `Не знаю`; public search alone intentionally cannot certify private company revenue.

## Product invariants

These are non-negotiable:

- `founder_statement`, `public_benchmark`, and `ai_scenario` never automatically become `source_fact`;
- deterministic calculations remain typed separately from source facts;
- public research is limited to public market/ICP/GTM/pricing/benchmark context and must not search for private MRR, ARR, actual revenue, burn, cash balance, factual customer count, contracts, invoices, or bank data;
- every scenario metric continues to expose range, provenance, formula, dependency refs, source refs, and validation plan;
- consent is required before each public research job;
- provider output is accepted only when quantitative and cited; otherwise it is rejected or deferred fail-closed.

## Fresh verification evidence

Backend:

```text
py -3.13 -m ruff check <3 touched files>                         -> PASS
py -3.13 -m ruff format --check <3 touched files>                -> PASS
pytest startup research + research jobs + privacy + API contract -> 66 passed
```

Frontend:

```text
npm test          -> PASS
npm run typecheck -> PASS
npm run lint      -> PASS
```

The frontend suite includes explicit coverage for visible public-research stages, bounded polling, cancellation, no fake deltas, duplicate-action blocking, Russian busy feedback, responsive consent modal placement, and activity cleanup.

## Relevant commits after Docker packaging

- `27d9a311` — fix packaged Streamlit admin fixtures;
- `dbb8b4c8` — test packaged Docker fixture resources;
- `b66abc9b` — wire LangSmith key through Docker Compose;
- `73a20d35`, `37ebe45` — fix and unify public-research consent UI;
- `75a3a967`, `a6818464` — accept cited live public benchmarks safely;
- `61c77f88`, `470952be`, `bd9415ba`, `e295fb5` — show progress/loaders and clean async activity;
- `9dc81bcc`, `e1342c71`, `a9355227` — enforce provider/privacy/audit boundaries and public pricing queries;
- `6a306bcc`, `1badb6d3`, `b1cb0e3a`, `fc8fc11c`, `778b825` — fail-closed provider/output/date handling;
- `ded2947c`, `cae4f555` — Russian presentation and responsive consent modal contract;
- `e4e8e41` — bounded transient retry and corrected public-search token reservation.

## Preserved dirty state

The following tracked frontend files were already dirty and were deliberately not included in the public-search commit:

- `frontend/founder/next-env.d.ts`;
- `frontend/founder/tsconfig.json`.

Many untracked runtime/test/browser artifacts also remain. Do not clean or delete them as part of ordinary continuation work.

## Safe next step

The project is ready for owner testing at `http://127.0.0.1:3000/`. If a later live search hits a transient OpenAI outage, the UI now remains visibly busy and the backend retries once. A stable provider/auth/configuration failure remains explicit; do not hide it with fixture success or auto-promote any public result to `source_fact`.
