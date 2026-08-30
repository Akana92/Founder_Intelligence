# Case Copilot Readable Russian UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a fluid, readable, Russian Case Copilot UI without weakening evidence and scenario provenance boundaries.

**Architecture:** Add one focused founder-presentation module that converts domain enums, metric keys, values, gaps, actions, and roles into Russian display models. Existing React components consume that module and keep full scenario disclosure inside collapsed Russian details. CSS changes make the shell fluid, preserve main-column priority, and remove nested scrolling from the permanent rail.

**Tech Stack:** Next.js 16.3, React 19.2, TypeScript 5.9, CSS Modules, Node test runner, Playwright CLI/browser evidence.

**Spec:** `docs/superpowers/specs/2026-08-24-case-copilot-readable-russian-ui-design.md`

## Global Constraints

- Preserve all existing dirty WIP. Do not reset, clean, checkout, revert, stage, commit, push, or deploy.
- `founder_statement`, `public_benchmark`, and `ai_scenario` never automatically become `source_fact`.
- Every scenario metric retains provenance, range, formula, dependencies, source references, and validation plan.
- Unknown actuals are never rendered as zero.
- Russian is the default founder-facing language; raw enum/action/reference identifiers are not default copy.
- Use the full available shell width; do not introduce a fixed pixel shell max-width.
- The permanent desktop rail follows document height; only drawer mode may have its own vertical scroll.
- Add no dependencies and change no backend/API contracts.

---

### Task 1: Founder-readable presentation model

**Files:**
- Create: `frontend/founder/lib/founder-readable-presentation.ts`
- Create: `frontend/founder/lib/founder-readable-presentation.test.ts`
- Modify: `frontend/founder/package.json`

**Interfaces:**
- Consumes: `ScenarioKey`, `StartupScenarioMetric`, provenance and Copilot action types from `frontend/founder/lib/contracts.ts`.
- Produces: exported helpers for localized provenance, scenario, metric, dependency/gap, action/status, role, coverage, and scenario metric value/summary presentation.

- [x] **Step 1: Write failing behavior tests**

Use literal fixtures to require labels such as `Подтверждённый факт`, `Расчёт по формуле`, `Базовый`, `MRR — ежемесячная регулярная выручка`, `Не хватает данных: отток клиентов`, and a localized compact range such as `7,2–14,7 млн ₸`. Assert that founder summaries do not contain raw enum names, `missing:`, UUIDs, or scientific notation.

- [x] **Step 2: Run the focused test and record RED**

Run from `frontend/founder`:

```powershell
node --experimental-strip-types lib/founder-readable-presentation.test.ts
```

Expected: FAIL because the presentation module or required behavior does not exist.

- [x] **Step 3: Implement the minimal presentation helpers**

Use explicit typed maps and `Intl.NumberFormat("ru-RU", ...)`. Preserve raw values in inputs; return founder-readable display values without mutating domain objects.

- [x] **Step 4: Add the focused test to the package test script and run GREEN**

```powershell
node --experimental-strip-types lib/founder-readable-presentation.test.ts
```

Expected: all tests PASS with pristine output.

- [x] **Step 5: Self-review without committing**

Confirm mappings cover every currently rendered provenance, scenario, action, role, metric, coverage state, and known missing dependency shown by the Case Copilot fixtures.

### Task 2: Russian human-first Case Copilot and analysis copy

**Files:**
- Modify: `frontend/founder/components/case-copilot-panel.tsx`
- Modify: `frontend/founder/components/case-question-card.tsx`
- Modify: `frontend/founder/components/founder-scenario-metrics.tsx`
- Modify: `frontend/founder/components/founder-analysis-pages.tsx`
- Modify: `frontend/founder/components/founder-strategy-pages.tsx`
- Modify: `frontend/founder/components/founder-workspace-controller.test.ts`
- Modify: `frontend/founder/components/founder-analysis-pages.test.ts`
- Modify: `frontend/founder/components/founder-strategy-pages.test.ts`

**Interfaces:**
- Consumes: presentation helpers produced by Task 1 and unchanged API/domain data.
- Produces: Russian founder-facing panels with short default summaries and collapsed complete disclosure under `Как рассчитано и проверить`.

- [x] **Step 1: Write failing component contract tests**

Require Russian headings, form labels, action/status labels, scenario labels, human-readable metric copy, and a collapsed disclosure. Require that the default JSX copy no longer interpolates raw provenance/action/role/field identifiers or raw dependency/source arrays.

- [x] **Step 2: Run the focused tests and record RED**

```powershell
node --experimental-strip-types components/founder-analysis-pages.test.ts
node --experimental-strip-types components/founder-strategy-pages.test.ts
node --experimental-strip-types components/founder-workspace-controller.test.ts
```

Expected: FAIL on the new Russian human-readable contract.

- [x] **Step 3: Implement the minimal component changes**

Replace visible debug concatenation with presentation helpers. Keep full provenance/range/formula/dependencies/source references/validation plan in collapsed Russian details. Translate the founder form, research state, conversation, action list, coverage labels, scenario selector, and empty/error states.

- [x] **Step 4: Run the focused tests and record GREEN**

Run the three commands from Step 2. Expected: all tests PASS with pristine output.

- [x] **Step 5: Self-review without committing**

Search the modified components for user-visible English/raw tokens and verify every remaining raw key is contract logic, test fixture data, a non-visible attribute, or a collapsed diagnostic identifier.

### Task 3: Fluid shell, readable metric grid, and browser proof

**Files:**
- Modify: `frontend/founder/app/globals.css`
- Modify: `frontend/founder/app/globals.visual.test.ts`
- Modify: `frontend/founder/components/case-copilot-panel.module.css`
- Modify: `frontend/founder/components/founder-analysis-pages.module.css`
- Create: `artifacts/ui/task12-readable-russian-case-copilot/` browser evidence
- Modify: `docs/verification/2026-08-22-founder-case-copilot-scenario-verification.md`

**Interfaces:**
- Consumes: localized components from Task 2.
- Produces: full-width desktop shell, fluid rail, drawer fallback, natural-height cards, and captured user-testable evidence.

- [x] **Step 1: Write failing layout contract tests**

Require `width: 100%`, no fixed shell `max-width`, a fluid `clamp(...)` rail, a breakpoint that converts the rail to a drawer before it squeezes the main page, normal document flow for the permanent rail, natural metric-card height, and a three-column readable metric grid on wide screens.

- [x] **Step 2: Run the layout test and record RED**

```powershell
node --experimental-strip-types app/globals.visual.test.ts
```

Expected: FAIL because the current shell is capped at 1440px, the rail is 360px with nested scrolling, and metric cards are fixed/clipped.

- [x] **Step 3: Implement the minimal fluid layout**

Use a full-width shell, `minmax(0, 1fr)` for main content, `clamp(24rem, 26vw, 32rem)` for the rail, and a drawer breakpoint chosen from measured content fit. Remove permanent-rail `max-height`/`overflow: auto`; retain scrolling only inside drawer mode. Use natural heights and a responsive three-column metric-card grid.

- [x] **Step 4: Run frontend verification**

```powershell
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

Expected: all commands PASS.

- [x] **Step 5: Capture real browser evidence**

Capture New Analysis, Metrics, and Action Plan with Case Copilot open at 1440x1000 and 1920x1080. Verify no horizontal clipping, no nested rail scroll on the wide layout, readable Russian copy, working expand/collapse controls, and preserved scenario provenance disclosure.

- [x] **Step 6: Update verification evidence without committing**

Record commands, results, artifact paths, and any remaining non-blocking limitation. Do not claim live-provider verification.
