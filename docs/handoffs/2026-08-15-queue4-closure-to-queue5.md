# Queue 4 closure and Queue 5 continuation handoff

**Date:** 2026-08-15
**Workspace:** `D:\Agents\Projects\Capstone N3`
**Branch:** `main`
**Queue 4 code/docs closure baseline:** `b4f15cdeece9979796c9a7748a32b23494442510`
**Scope of the closure claim:** deterministic frozen/offline only

This document is the durable continuation point for a new Codex chat. The commit that contains this file is documentation-only and sits on top of the Queue 4 closure baseline above.

## 1. Honest project state

Queue 4 is complete for the deterministic frozen/offline product boundary. Queue 5 Demo Freeze, the final Sellable Demo Gate, live research, controlled Python inside the startup workflow, and external LangSmith/OTel delivery are not complete and must not be reported as complete.

The six completed Queue 4 slices are:

| Slice | Main commits | Result |
| --- | --- | --- |
| Canonical GTM and Action Plan | `412ab16`, `28af637` | Seven GTM dimensions and four frozen launch horizons are shown in the real Founder flow. |
| Canonical Startup Profile | `d0b95a0`, `808493a` | Eighteen evidence-aware profile fields are shown without private/raw internals. |
| Canonical report projection | `c55d0f7`, `fe0a2b4` | Twelve canonical report sections are shown with exact snapshot lineage. |
| Readiness and deep questions | `835f9bd`, `a13ac12` | Primary/deep state, 22 readiness dimensions, four bounded deep summaries, and up to three priority questions are shown. |
| Browser-visible Gate 4 and downloads | `321fd61` | The real UI approves Gate 4 and exposes same-case JSON/HTML/PDF; PDF content type, byte cap, and `%PDF` magic are verified. |
| Deterministic startup charts | `dbfdbb0`, `64218dc`, `75de454`, `513f441`, `75c990b`, `4760783` | Three Founder chart cards with eight bounded report-derived points and three lineage markers are shown on desktop and mobile. |

Queue 4 documentation closure is commit `b4f15cd`. The authoritative closure documents are:

- `docs/verification/2026-08-15-queue4-gtm-founder-ui-verification.md`
- `docs/verification/2026-08-15-queue4-profile-founder-ui-verification.md`
- `docs/verification/2026-08-15-queue4-report-founder-ui-verification.md`
- `docs/verification/2026-08-15-queue4-readiness-founder-ui-verification.md`
- `docs/verification/2026-08-15-queue4-gate4-download-verification.md`
- `docs/verification/2026-08-15-queue4-startup-charts-verification.md`
- `docs/superpowers/plans/2026-08-13-capstone-completion-staircase.md`

## 2. Fresh Queue 4 closure evidence

The following checks were rerun on the Queue 4 baseline immediately before this handoff.

```text
focused Q4 backend/report/browser-QA tests  -> 48 passed
full backend pytest                         -> 1162 passed, 1 expected Windows symlink skip
Ruff                                        -> PASS
strict mypy                                 -> PASS, 219 source files
frontend tests                              -> PASS, 104 tests
frontend lint                               -> PASS
frontend production build                   -> PASS
frontend typecheck after build               -> PASS
real offline API/browser smoke               -> PASS
desktop screenshot                           -> 1440x1000
mobile screenshot                            -> 390x844
```

The full backend command explicitly ignored only the preserved, unfinished Queue 5 RED test:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest -q -p no:cacheprovider --basetemp .tmp-q4-handoff-full-20260815-01 --ignore=tests/evaluation/test_sellable_demo_freeze.py
```

The browser journey passed upload -> primary analysis -> Gate 2 -> deep analysis -> Gate 3 -> canonical report -> Readiness -> Gate 4 -> JSON/HTML/PDF for the same case. Both viewports reported:

```text
profile fields=18 evidence_fields=2
GTM dimensions=7 horizons=4
report sections=12 statuses=12 lineage=true
readiness stages=2 dimensions=22 deep_sections=4 questions=3 lineage=true
charts=3 points=8 lineage=3
PDF ready with application/pdf and %PDF bytes
```

Fresh screenshots are runtime evidence only and remain ignored/uncommitted:

- `.local/q4-handoff-smoke-r2/founder-desktop.png` — 1440x1000.
- `.local/q4-handoff-smoke-r2/founder-mobile.png` — 390x844.

The strict first browser run stopped on a local Kaspersky parser injection from `http://me.kis.v2.scr.kaspersky-labs.com`. The successful second run used the existing explicit exact-origin, parser-only quarantine. The request was still failed before egress and logged once per viewport. This is an environmental boundary, not a silent allowlist and not a claim of zero attempted injection.

The first frontend typecheck was run before Next regenerated `.next/types` and therefore reported missing generated declarations. A successful production build regenerated them; the repeated typecheck passed. No production code change was required.

## 3. Preserved Queue 5 RED WIP

Do not delete, revert, move, or overwrite this file:

- `tests/evaluation/test_sellable_demo_freeze.py`

It is intentionally untracked and not staged because it is the first Queue 5 TDD RED boundary. Its current focused result is:

```text
7 failed
all seven failures: ModuleNotFoundError for due_diligence_agent.evals.sellable_demo_freeze
```

The test contract currently expects:

- `SellableDemoFreezeInputs`;
- `build_sellable_demo_freeze_packet`;
- `validate_sellable_demo_freeze_packet`;
- fail-closed output-root collision protection;
- Gate B/C/D-A/D-B/E evidence;
- Gate D semantic equivalence rather than raw timestamp/hash equality;
- desktop 1440x1000 and mobile 390x844 evidence;
- same-case JSON/HTML/PDF lineage;
- privacy leak rejection;
- a canonical stable packet hash.

Before implementing, review the test critically against the real Gate B/C/D/E schemas. Keep useful RED coverage, but correct any invented fixture field or unsafe assumption through an explicit test edit rather than blindly implementing a false contract.

## 4. Files that must remain untouched

The following user/runtime files are outside the task and must not be deleted, cleaned, staged, or rewritten:

- `task15_r3_probe_app.py`
- `task15_r3_probe_data/`
- `.pytest-debug-readonly-store/`
- inaccessible pytest/runtime directories already present in the workspace
- existing worktrees and feature branches

Never use `git reset`, `git checkout`, `git clean`, broad recursive deletion, or `git add -A` in this workspace.

## 5. Required reading order for the next chat

Read these sources before making Queue 5 changes:

1. `README.md`
2. `PRODUCT.md`
3. `DESIGN.md`
4. `docs/superpowers/specs/2026-08-11-founder-launch-intelligence-product-tz.md` — especially section 34
5. `docs/superpowers/plans/2026-08-11-founder-launch-intelligence-delivery-roadmap.md`
6. `docs/superpowers/plans/2026-08-13-capstone-completion-staircase.md`
7. all six Queue 4 verification documents listed in section 1
8. this handoff document
9. `tests/evaluation/test_sellable_demo_freeze.py`

Read `frontend/founder/AGENTS.md` only before changing `frontend/founder`.

After reading, run:

```powershell
git status --short --branch
git rev-parse HEAD
git log -5 --oneline
```

The branch must be `main`, and `b4f15cd` must be an ancestor of HEAD. Explain any difference before editing.

## 6. Next implementation boundary: Queue 5A

The first independently verifiable Queue 5 result is a machine-readable deterministic/offline Demo Freeze packet. It must bind, without copying secrets or local absolute paths into the public packet:

- fresh Gate B, Gate C, Gate D run A, Gate D run B, and Gate E evidence;
- semantic/persisted Gate D fingerprints separately from raw file hashes;
- fixture manifests and expected hashes;
- browser evidence for desktop and mobile;
- same-case approved JSON/HTML/PDF lineage and a sample PDF hash;
- backend/frontend/static verification results;
- failure-mode evidence for provider unavailable, external-source outage, retry, budget exhaustion, and report-renderer fallback;
- demo script and one-page capstone requirements map;
- explicit `deferred_by_policy` status for paid/live provider smoke while the current no-live instruction remains active.

Use TDD: preserve the existing seven RED tests, implement the smallest production module, obtain GREEN, then add CLI/PowerShell orchestration and real evidence incrementally. Keep generated packets, screenshots, PDFs, logs, databases, and runtime uploads under ignored local output roots; commit only code, tests, scripts, and documentation.

Do not run OpenAI, LangSmith, Yahoo Finance, GDELT, news, web, or any other paid/live provider. The local `.env` key must never be printed.

## 7. Verification required before Queue 5 or Sellable Demo closure

Do not declare Queue 5 complete until all of the following are freshly proven on one pinned commit:

- Gate B, C, D-A, D-B, and E offline;
- stable Gate D semantic/persisted fingerprints across the two runs;
- full backend pytest, Ruff, and strict mypy;
- frontend tests, typecheck, lint, and production build;
- real desktop/mobile browser/API smoke;
- same approved snapshot for JSON/HTML/PDF;
- provider unavailable, offline external-source outage, retry, budget exhaustion, and renderer fallback;
- frozen dataset/fixture hashes, screenshots, and sample PDF;
- 7-10 minute demo script and one-page capstone map;
- independent code/docs/acceptance review;
- roadmap and verification docs synchronized without overclaiming live or production scope.

## 8. Copy-paste prompt for a new chat

```text
Продолжи разработку Investment Due Diligence Agent в рабочей папке:
D:\Agents\Projects\Capstone N3

Работай автономно в ветке main. Queue 4 уже полностью закрыта для deterministic frozen/offline scope. Её кодовый baseline — b4f15cdeece9979796c9a7748a32b23494442510; поверх него должен находиться только documentation handoff commit, содержащий:
docs/handoffs/2026-08-15-queue4-closure-to-queue5.md

Сначала полностью прочитай, строго по порядку:
1. README.md
2. PRODUCT.md
3. DESIGN.md
4. docs/superpowers/specs/2026-08-11-founder-launch-intelligence-product-tz.md, особенно раздел 34
5. docs/superpowers/plans/2026-08-11-founder-launch-intelligence-delivery-roadmap.md
6. docs/superpowers/plans/2026-08-13-capstone-completion-staircase.md
7. шесть docs/verification/2026-08-15-queue4-*-verification.md
8. docs/handoffs/2026-08-15-queue4-closure-to-queue5.md
9. tests/evaluation/test_sellable_demo_freeze.py

frontend/founder/AGENTS.md читай только перед изменением frontend/founder.

Затем выполни git status --short --branch, git rev-parse HEAD и git log -5 --oneline. Подтверди main и что b4f15cd является предком HEAD. Не удаляй, не откатывай, не перемещай и не перезаписывай незакоммиченный Queue 5 RED WIP:
tests/evaluation/test_sellable_demo_freeze.py

Не трогай и не добавляй в git:
- task15_r3_probe_app.py
- task15_r3_probe_data/
- .pytest-debug-readonly-store/
- посторонние runtime/temp artifacts
- существующие worktree и feature branches

Не используй git reset, checkout, clean, broad delete или git add -A.

Продолжай с Queue 5A по TDD. Текущая RED-граница: 7 tests/evaluation/test_sellable_demo_freeze.py failures из-за отсутствующего due_diligence_agent.evals.sellable_demo_freeze. Сначала сверь тестовые fixture-поля с реальными Gate B/C/D/E и startup runtime-evidence schemas. Затем минимально реализуй machine-readable sellable_demo_freeze_packet@1 с fail-closed collision, privacy, semantic determinism, screenshot dimensions и same-case JSON/HTML/PDF lineage. После GREEN добавь CLI/PowerShell orchestration, fresh Gate B/C/D-A/D-B/E evidence, browser evidence, failure matrix, demo script и capstone map.

Никаких платных/live OpenAI, LangSmith, Yahoo Finance, GDELT, news или web-вызовов. Не выводи ключ из .env. Live smoke сейчас помечай deferred_by_policy; он не блокирует frozen demo.

Shared graph/ports/container/report меняет только один интегратор. Делай маленькие сфокусированные коммиты с явным git add отдельных файлов. Перед заявлением о Queue 5/Sellable Demo readiness обязательно прогони Gate B/C/D/E, полный backend pytest, Ruff, strict mypy, frontend test/typecheck/lint/build и настоящий local desktop/mobile browser/API smoke. Не выдавай Queue 5, Sellable Demo, Pilot-Ready или Production-Ready за завершённые до фактического прохождения соответствующих gates.

После чтения дай короткую сводку состояния и сразу продолжай реализацию Queue 5A, не ожидая подтверждения на очевидные локальные действия.
```
