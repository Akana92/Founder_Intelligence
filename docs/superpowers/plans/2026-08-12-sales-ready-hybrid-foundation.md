# Sales-Ready Hybrid Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** создать проверяемый фундамент варианта B — отдельный Founder Workspace и versioned Python API поверх существующего аналитического ядра — так, чтобы вариант C позднее добавил multi-user, security, tenancy и operations без переписывания анализа.

**Architecture:** существующие domain/application/workflow/reporting слои остаются каноническими и не зависят от HTTP или React. FastAPI становится новым presentation-адаптером с контрактами `/api/v1`, честной картой возможностей, request/trace context и dependency seams для будущей identity/tenancy. Founder Workspace строится на Next.js App Router и получает данные только через API/BFF; бизнес-формулы, статусы анализа и source-of-truth не дублируются во frontend. Streamlit сохраняется как временный Admin Console и secondary Public Company interface. Переход к C заменяет local persistence и anonymous request context на tenant-aware adapters, auth/RBAC и production operations, сохраняя API v1 и application contracts.

**Tech Stack:** Python 3.12, uv, Pydantic 2, FastAPI 0.137.x, Uvicorn, OpenTelemetry, pytest, Ruff, mypy, Next.js 16.2+, React 19.2, TypeScript, ESLint, CSS design tokens, существующие LangGraph/OpenAI/SQLite/DuckDB/FAISS/Jinja2/WeasyPrint/Streamlit компоненты.

## Global Constraints

- В пользовательском потоке нет выбора demo project, отрасли, SaaS/marketplace/e-commerce/fintech или технического research mode.
- Один кейс проходит `upload -> primary analysis -> deep analysis`; повторная загрузка для deep analysis не требуется.
- Неготовые Startup-возможности маркируются `planned` или `unavailable`; UI не показывает синтетические результаты как выполненный реальный анализ.
- Frontend не считает бизнес-метрики, не формирует findings и не решает, какие evidence достаточны.
- Raw startup documents, PII, API keys и секреты не попадают в tracing, response metadata или frontend logs.
- Public Company Gate B и frozen fixture остаются регрессионным барьером.
- B остаётся single-operator/local-or-hosted-single-tenant поставкой. Auth, RBAC, multi-tenancy, billing, backup orchestration и SLO implementation относятся к C.
- Все новые HTTP-контракты версионируются с первого дня; breaking change требует нового API version.
- Тесты пишутся до production-кода; каждый task завершается собственным проверяемым commit.

---

## Task 1: Make the frozen baseline reproducible in every Windows worktree

**Files:**

- Create: `.gitattributes`
- Verify: `tests/fixtures/public_us_frozen_v1/**`
- Test: `tests/smoke/test_application_boot.py`

- [ ] **Step 1: Reproduce the line-ending failure**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group dev pytest tests/smoke/test_application_boot.py::test_fixture_retrieval_index_survives_container_reopen tests/smoke/test_application_boot.py::test_run_eval_executes_gate_b_for_frozen_public_fixture -q --basetemp .local/pytest-fixture-eol-red
```

Expected: FAIL with `fixture hash mismatch` in a fresh worktree created under global `core.autocrlf=true`.

- [ ] **Step 2: Pin frozen fixture bytes to LF**

Add a narrow attribute rule:

```gitattributes
tests/fixtures/public_us_frozen_v1/** text eol=lf
```

Verify the fixture directory is clean before rehydrating its worktree bytes, then restore only that tracked directory from `HEAD` so the new attribute is applied. Do not touch user-owned or untracked files.

- [ ] **Step 3: Re-run the two regression tests**

Run the command from Step 1 with a fresh basetemp.

Expected: PASS.

- [ ] **Step 4: Run the complete Stage 1A offline regression**

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group dev pytest -q --basetemp .local/pytest-stage1a-green
```

Expected: all tests PASS. If WeasyPrint runtime blocks only PDF-specific checks, run the official runtime diagnostic and record the exact gap; do not waive logical test failures.

- [ ] **Step 5: Commit**

```powershell
git add .gitattributes
git commit -m "test: preserve frozen fixture bytes across worktrees"
```

## Task 2: Freeze B-to-C boundaries and the reuse matrix

**Files:**

- Create: `docs/architecture/2026-08-12-sales-ready-hybrid-boundaries.md`
- Create: `docs/architecture/2026-08-12-reuse-create-extend-matrix.md`
- Modify: `docs/superpowers/plans/2026-08-12-sales-ready-hybrid-foundation.md`

- [ ] **Step 1: Write the boundary document**

Record these invariants with concrete module references:

- reusable core: `domain`, `application/services`, `workflows`, evidence, calculations, findings, contradictions, reporting and tracing ports;
- B adapters: local SQLite/artifact storage, anonymous/single-operator request context, FastAPI presentation, Next.js Founder Workspace and Streamlit Admin Console;
- C replacements/extensions: authenticated principal resolver, workspace/tenant policy, PostgreSQL/object storage adapters, durable job queue, deployment/backup/SLO controls;
- prohibited coupling: no `fastapi`, HTTP headers, cookies, React types or tenant SQL inside domain/workflow modules;
- API compatibility: `/api/v1` schemas remain stable when C is introduced.

- [ ] **Step 2: Write the reuse/create/extend matrix**

For every existing subsystem, classify `reuse`, `extend`, `new adapter` or `defer to C`, and name the exact current source file plus the first new owner module.

- [ ] **Step 3: Self-review**

Read both architecture documents once as a clean-room reviewer and run:

```powershell
git diff --check -- docs/architecture docs/superpowers/plans/2026-08-12-sales-ready-hybrid-foundation.md
```

Expected: no whitespace defects, contradictory ownership or unresolved implementation placeholders. Explicitly deferred C features are allowed only when paired with a named seam and acceptance boundary.

- [ ] **Step 4: Commit**

```powershell
git add docs/architecture docs/superpowers/plans/2026-08-12-sales-ready-hybrid-foundation.md
git commit -m "docs: freeze Sales-Ready Hybrid architecture boundaries"
```

## Task 3: Add framework-independent product capability contracts

**Files:**

- Create: `src/due_diligence_agent/application/product/__init__.py`
- Create: `src/due_diligence_agent/application/product/capabilities.py`
- Test: `tests/unit/application/product/test_capabilities.py`

- [ ] **Step 1: Write the failing unit tests**

Test that the service returns immutable/versioned Pydantic models with:

- delivery profile `sales_ready_hybrid`;
- universal upload, primary analysis and deep analysis as separate capabilities with truthful lifecycle status;
- public comparable analysis as currently available;
- research policy `guarded_live_with_cached_fallback`;
- surfaces `founder_workspace=separate_web` and `admin_console=streamlit`;
- upgrade target `full_platform` with preserved analytics/API contracts;
- no user-selectable demo vertical or technical research mode.

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group dev pytest tests/unit/application/product/test_capabilities.py -q
```

Expected: FAIL because the product contract module does not exist.

- [ ] **Step 2: Implement the minimum domain-neutral contract**

Use frozen Pydantic models and a small `ProductCapabilitiesService`. Do not import FastAPI, Streamlit or repository adapters.

- [ ] **Step 3: Re-run the unit test**

Expected: PASS.

- [ ] **Step 4: Run type and style checks for the new module**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group dev ruff check src/due_diligence_agent/application/product tests/unit/application/product
uv run --offline --no-sync --no-default-groups --group stage1a --group dev mypy src/due_diligence_agent/application/product
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/due_diligence_agent/application/product tests/unit/application/product
git commit -m "feat: define versioned Founder product capabilities"
```

## Task 4: Introduce the FastAPI presentation adapter and C-ready request context

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/due_diligence_agent/presentation/api/__init__.py`
- Create: `src/due_diligence_agent/presentation/api/app.py`
- Create: `src/due_diligence_agent/presentation/api/context.py`
- Create: `src/due_diligence_agent/presentation/api/dependencies.py`
- Create: `src/due_diligence_agent/presentation/api/middleware.py`
- Create: `src/due_diligence_agent/presentation/api/routers/__init__.py`
- Create: `src/due_diligence_agent/presentation/api/routers/system.py`
- Test: `tests/api/test_system_api.py`
- Test: `tests/api/test_request_context.py`

- [ ] **Step 1: Add a locked `founder-api` dependency group**

Add compatible ranges for FastAPI 0.137.x and Uvicorn. Keep `stage1a` unchanged. Regenerate `uv.lock` through uv; do not hand-edit the lockfile.

- [ ] **Step 2: Write failing API tests**

Cover:

- `GET /health/live` returns a minimal no-secret response;
- `GET /api/v1/product/capabilities` validates against the application contract;
- OpenAPI publishes the versioned route and response schema;
- every response has a canonical `X-Request-ID`;
- a malformed incoming request ID is replaced rather than reflected;
- `RequestContext` contains nullable `actor_id` and `workspace_id` seams but B does not trust anonymous headers as identity;
- a safe OTel span name and route/version attributes are emitted without request body or filename content.

Run:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev pytest tests/api -q
```

Expected: FAIL because the API adapter is missing.

- [ ] **Step 3: Implement app factory and routers**

Use `create_app()` and `APIRouter`. Construct `ProductCapabilitiesService` through a FastAPI dependency so C can replace identity/workspace policies without modifying route functions. Keep the app import free of database and embedding-model side effects.

- [ ] **Step 4: Implement request/trace middleware**

Generate UUID request IDs, accept only canonical UUID input, return the ID in headers, and attach safe scalar attributes to the active OTel span. Never record raw headers, bodies, query strings, filenames or document text.

- [ ] **Step 5: Re-run API tests and the presentation import smoke**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev pytest tests/api tests/smoke/test_application_boot.py::test_presentation_modules_import_without_runtime_side_effects -q
```

Expected: PASS.

- [ ] **Step 6: Run Ruff and mypy**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev ruff check src/due_diligence_agent/presentation/api tests/api
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev mypy src/due_diligence_agent/presentation/api
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml uv.lock src/due_diligence_agent/presentation/api tests/api
git commit -m "feat: expose the Founder API v1 foundation"
```

## Task 5: Add local API run commands and a contract smoke

**Files:**

- Modify: `pyproject.toml`
- Create: `src/due_diligence_agent/presentation/api/__main__.py`
- Create: `scripts/run_founder_api.ps1`
- Modify: `README.md`
- Test: `tests/smoke/test_founder_api_boot.py`

- [ ] **Step 1: Write the failing subprocess smoke**

Start the API on an ephemeral localhost port, poll `/health/live`, call `/api/v1/product/capabilities`, assert the request ID header and terminate cleanly. Ensure the smoke uses no network source and no paid API key.

- [ ] **Step 2: Add the `investment-dd-api` entry point and PowerShell runner**

The runner must bind to `127.0.0.1` by default, accept an explicit port, and avoid exposing the service on all interfaces unless the operator opts in.

- [ ] **Step 3: Document local use**

Add exact setup/run URLs and distinguish:

- Founder API: `http://127.0.0.1:8000`;
- API docs: `http://127.0.0.1:8000/docs`;
- Admin Console: current Streamlit runner;
- Founder web: added by Task 7.

- [ ] **Step 4: Run the smoke**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev pytest tests/smoke/test_founder_api_boot.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml src/due_diligence_agent/presentation/api/__main__.py scripts/run_founder_api.ps1 README.md tests/smoke/test_founder_api_boot.py
git commit -m "build: add a reproducible Founder API runner"
```

## Task 6: Lock the Founder Workspace product and visual contract

**Files:**

- Create: `PRODUCT.md`
- Create: `.impeccable/surface-briefs/founder-workspace.md`
- Reference: `docs/superpowers/specs/2026-08-11-founder-launch-intelligence-product-tz.md`

- [ ] **Step 1: Record product truth**

Capture the primary user, no-prompt job, universal upload, two-level same-case analysis, honest partial states, Admin separation, and B-to-C boundary. Mark the public product name as a working name rather than inventing a final trademark.

- [ ] **Step 2: Lock the Operate-mode surface brief**

The first viewport must explain the task and expose the upload action immediately. The visual world follows the approved brief: professional deep navy/near-black analytics, cyan/teal system signals, amber/red only for warning/risk, high legibility, no generic AI gradients, no Bloomberg imitation and no terminal noise.

- [ ] **Step 3: Produce and approve a concrete composition before UI code**

Follow the Impeccable new-work flow. Generate the required three compositional sketches inside the already pinned visual world, select one based on task clarity and investor-demo comprehension, and preserve the result as the implementation target. This is a composition choice, not a new B/C product decision.

- [ ] **Step 4: Commit**

```powershell
git add PRODUCT.md .impeccable
git commit -m "docs: lock the Founder Workspace product and surface brief"
```

## Task 7: Build the separate Next.js Founder Workspace shell

**Files:**

- Create: `frontend/founder/package.json`
- Create: `frontend/founder/package-lock.json`
- Create: `frontend/founder/next.config.ts`
- Create: `frontend/founder/tsconfig.json`
- Create: `frontend/founder/eslint.config.mjs`
- Create: `frontend/founder/app/layout.tsx`
- Create: `frontend/founder/app/page.tsx`
- Create: `frontend/founder/app/admin/page.tsx`
- Create: `frontend/founder/app/globals.css`
- Create: `frontend/founder/components/founder-shell.tsx`
- Create: `frontend/founder/components/capability-status.tsx`
- Create: `frontend/founder/components/upload-entry.tsx`
- Create: `frontend/founder/lib/api.ts`
- Create: `frontend/founder/lib/contracts.ts`
- Create: `frontend/founder/public/*` only for authored assets approved by the visual contract

- [ ] **Step 1: Scaffold a pinned Next.js App Router project**

Use TypeScript, ESLint and the current stable Next 16.2 line with React 19.2. Commit `package-lock.json`. Do not add a generic component kit before the visual system proves it is needed.

- [ ] **Step 2: Add a typed API client**

Fetch `/api/v1/product/capabilities` server-side or through a same-origin BFF route. Validate required discriminators at the boundary and render an explicit unavailable state if the backend is unreachable.

- [ ] **Step 3: Implement the selected Founder composition**

The shell must include:

- one primary universal upload entry without sector/demo selectors;
- an honest analysis path `Документы -> Первичный анализ -> Глубинный анализ -> План действий`;
- available/planned status derived from the API, not hard-coded claims;
- a clear secondary path to Public Comparables;
- a visually separate Admin Console bridge that opens the Streamlit surface;
- responsive desktop-first behavior, keyboard focus, reduced-motion support and WCAG AA contrast.

- [ ] **Step 4: Keep upload honest**

Until Safe Startup Ingest exists, file selection may demonstrate local inventory only; submission/analysis actions remain disabled with business-readable status. No synthetic score, competitor or report is shown as a completed result.

- [ ] **Step 5: Add production checks**

Run:

```powershell
npm run lint
npm run typecheck
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/founder
git commit -m "feat: add the separate Founder Workspace shell"
```

## Task 8: Verify the UI in the browser and document the built design system

**Files:**

- Create: `DESIGN.md`
- Create: `.impeccable/design-system.json`
- Create: `artifacts/ui/founder-desktop.png`
- Create: `artifacts/ui/founder-mobile.png`
- Modify: `frontend/founder/**` only for defects found in the bounded review

- [ ] **Step 1: Run API and web locally**

Start the API on `127.0.0.1:8000` and Founder web on `127.0.0.1:3000` using hidden/background processes suitable for the Codex desktop environment.

- [ ] **Step 2: Capture one desktop and one mobile review round**

Use the in-app browser. Capture 1440px desktop and a representative mobile viewport. Inspect task clarity, overflow, contrast, focus, backend-unavailable state and separation from Admin Console.

- [ ] **Step 3: Apply one batched defect fix**

Fix all material findings together, rebuild and capture one confirmation round. Stop after the second round.

- [ ] **Step 4: Run the mechanical design detector once**

```powershell
node C:\Users\Akana\.agents\skills\impeccable\scripts\detect.mjs --json frontend/founder
```

Expected: no unresolved blocking findings.

- [ ] **Step 5: Run the independent finish review and documenter**

Pass both screenshots, the visual contract, detector output and changed targets to the Impeccable finish reviewer. Apply only its material findings within the bounded review budget. Then create `DESIGN.md` and its sidecar from the shipped implementation.

- [ ] **Step 6: Commit**

```powershell
git add frontend/founder DESIGN.md .impeccable artifacts/ui
git commit -m "design: finish and document the Founder Workspace"
```

## Task 9: Prove B today and the C upgrade seam tomorrow

**Files:**

- Create: `tests/architecture/test_b_to_c_boundaries.py`
- Modify: `README.md`
- Modify: `docs/architecture/2026-08-12-sales-ready-hybrid-boundaries.md`

- [ ] **Step 1: Add architecture guard tests**

Use AST/import scans to prove:

- domain/application/workflow modules do not import FastAPI or frontend artifacts;
- API routes depend on application services/contracts rather than local repository classes;
- request context defines actor/workspace extension points but anonymous B cannot claim an authenticated identity;
- Streamlit and FastAPI remain sibling presentation adapters.

- [ ] **Step 2: Add the B-to-C migration checklist**

Name the later C tasks: auth provider, principal resolver, tenant policy, PostgreSQL/object storage adapters, background job execution, secrets management, backup/restore, rate limits, audit retention and SLOs. State explicitly that analytics depth does not change.

- [ ] **Step 3: Run the focused architecture test**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev pytest tests/architecture/test_b_to_c_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add tests/architecture README.md docs/architecture
git commit -m "test: protect the B-to-C upgrade boundaries"
```

## Task 10: Final integrated verification

**Files:**

- Verify only; edit failures at their owning task.

- [ ] **Step 1: Python quality gates**

```powershell
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev ruff check src tests
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev mypy src/due_diligence_agent
uv run --offline --no-sync --no-default-groups --group stage1a --group founder-api --group dev pytest -q --basetemp .local/pytest-final
```

Expected: PASS.

- [ ] **Step 2: Frontend quality gates**

```powershell
npm --prefix frontend/founder run lint
npm --prefix frontend/founder run typecheck
npm --prefix frontend/founder run build
```

Expected: PASS.

- [ ] **Step 3: Local browser smoke**

Verify:

- Founder Workspace loads on `http://127.0.0.1:3000`;
- capability status comes from the Python API;
- backend outage is represented honestly;
- Admin link opens the separate Streamlit surface;
- API docs load on `http://127.0.0.1:8000/docs`;
- no paid API call is required.

- [ ] **Step 4: Repository evidence**

```powershell
git status --short
git log --oneline --decorate -12
```

Expected: no unexpected tracked or untracked artifacts outside documented generated outputs; commits correspond to completed tasks.

---

## First Execution Slice

Execute Tasks 1-5 first. This creates a green, versioned and traced Python boundary without waiting for visual composition work. Tasks 6-8 then create the separate Founder surface. Tasks 9-10 close the non-rewrite C upgrade guarantee and integrated verification.

## Definition of Done for this plan

- Stage 1A frozen regression is reproducible in this worktree.
- `/api/v1/product/capabilities` and `/health/live` are tested, typed and free of database/model startup side effects.
- Every API response has a safe request ID and trace context without sensitive payloads.
- Founder Workspace is a separate browser product, not a reskinned Streamlit page.
- Founder and Admin surfaces are visibly and operationally separate.
- Startup capabilities are reported honestly until their real application services land.
- Architecture tests prove that C can add identity, tenancy and production adapters without moving analytics into HTTP or frontend layers.
- Python and frontend quality gates pass with fresh evidence.
