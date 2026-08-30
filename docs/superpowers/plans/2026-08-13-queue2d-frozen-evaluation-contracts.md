# Queue 2D Frozen Evaluation Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Создать полностью offline Gate D для startup deep analysis и Gate E для совместимости Public Company + Startup, чтобы Queue 2–4 проверялись без ключа, сети и ручного выбора подготовленного проекта в UI.

**Architecture:** Frozen fixtures → manifest validation → evaluator functions → thin CLI/PowerShell wrappers → immutable machine-readable `eval-result.json`. Queue 2D создаёт контракты, datasets и dry-run доказательства; окончательный Gate D/E sign-off и demo packet выполняются в Queue 5.

**Tech Stack:** Python 3.12/3.13, pytest, existing Gate B/C evaluator patterns, JSON manifests/hashes, PowerShell, Ruff, strict mypy.

## Closure status — 2026-08-14

Queue 2D is complete for frozen Gate D/E contracts and closure dry-run evidence. Evidence: production fixture-manifest validation before analysis, non-overwriting Gate D/E output roots, Gate C final PASS, two independent Gate D roots PASS with 4/4 semantic and 4/4 canonical persisted fingerprints equal, Gate E final PASS, focused Queue 2 regression `338 passed`, backend `1101 passed, 1 skipped`, Ruff and strict mypy PASS. Raw artifact hashes remain run-bound; canonical semantic/persisted fingerprints are the determinism contract. Queue 5 still owns final demo freeze, repeated final sign-off packet, screenshots, and defense script.

## Global Constraints

- `OPENAI_API_KEY`, `OPENAI_STARTUP_API_KEY` пусты; LangSmith/transformer hubs/network disabled.
- Каждый runner получает уникальный caller-provided output root и не перезаписывает другой run.
- Fixture documents synthetic and privacy-safe; raw user files and filenames never copied.
- Manifest hashes validate before analysis; tampering fails closed.
- Gate D validates actual startup profile, readiness, metrics, market research, contradiction/reflexion, report and trace contracts.
- Gate E runs Public + Startup compatibility and proves shared repository/report/tracing changes did not regress either vertical.
- Queue 2D dry run does not claim Queue 5 completion.

## Task 2D.1 — Lock Gate D/E Result Schemas

**Files:**
- Create: `src/due_diligence_agent/evals/gate_d.py`
- Create: `src/due_diligence_agent/evals/gate_e.py`
- Create: `tests/evaluation/test_startup_gate_d.py`
- Create: `tests/evaluation/test_combined_gate_e.py`

- [x] Write RED tests for frozen dataclass/Pydantic results with schema, dataset, pass flag, fail reasons, command evidence, artifact paths, commit/environment/offline proof and Queue 2 assertions.
- [x] Require `gate_d_result@1` and `gate_e_result@1`; `to_json_dict()` must be canonical and contain no exception text or local temp path beyond explicitly published artifact refs.
- [x] Run RED:

```powershell
uv run pytest -q -p no:cacheprovider tests/evaluation/test_startup_gate_d.py tests/evaluation/test_combined_gate_e.py
```

Expected RED: evaluator modules missing.

- [x] Implement result schemas and unsupported-dataset validation only; keep runners injectable for tests.
- [x] Run GREEN, Ruff and strict mypy.
- [x] Commit: `test: define Gate D and Gate E result contracts`.

## Task 2D.2 — Freeze a Multi-Model Startup Case Matrix

**Files:**
- Create: `tests/fixtures/startup_synthetic_v1/manifest.json`
- Create: `tests/fixtures/startup_synthetic_v1/expected_contracts.json`
- Create: `tests/fixtures/startup_synthetic_v1/cases/saas/`
- Create: `tests/fixtures/startup_synthetic_v1/cases/marketplace/`
- Create: `tests/fixtures/startup_synthetic_v1/cases/transactional/`
- Create: `tests/fixtures/startup_synthetic_v1/cases/pre_revenue_service/`
- Create: `tests/evaluation/test_queue2_startup_fixtures.py`

- [x] Build four synthetic cases using supported PDF/DOCX/PNG/JPEG/CSV/XLSX/safe ZIP formats already proven in Queue 1.
- [x] Include at least one gap, one contradiction and one unsupported claim per case without embedding secrets, emails or local paths.
- [x] Freeze expected profile field/status coverage, metric pack, readiness/questions, research source modes, competitor categories, market-sizing status and report section assertions.
- [x] Verify every file hash, no-network manifest and fixture byte cap before any service call.
- [x] Run fixture tests twice and assert identical contract hashes.
- [x] Commit: `test: add frozen Queue 2 startup case matrix`.

## Task 2D.3 — Implement Gate D Startup Deep Benchmark

**Files:**
- Modify: `src/due_diligence_agent/evals/gate_d.py`
- Modify: `tests/evaluation/test_startup_gate_d.py`

- [x] Write RED runner tests with injected commands for all four cases, tampered manifest, partial external-source outage, privacy leak, missing contradiction and non-deterministic report hash.
- [x] Reuse Gate C offline environment and command evidence patterns, but execute the Queue 2 frozen contracts rather than merely embedding Gate C.
- [x] Require evidence: deterministic profile/readiness/research/report hashes, zero privacy leaks/external calls, max-three questions, valid metric formulas, all competitor source/as-of labels, bounded Reflexion and trace→report lineage.
- [x] Write `eval-result.json` atomically to the caller's unique output root.
- [x] Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/evaluation/test_startup_gate_d.py tests/evaluation/test_queue2_startup_fixtures.py
```

Expected GREEN: positive case passes and each negative fixture fails for its stable reason.
- [x] Commit: `feat: implement offline startup Gate D evaluator`.

## Task 2D.4 — Implement Gate E Combined Compatibility

**Files:**
- Modify: `src/due_diligence_agent/evals/gate_e.py`
- Modify: `tests/evaluation/test_combined_gate_e.py`

- [x] Write RED tests injecting Gate B/C/D results and shared compatibility probes.
- [x] Gate E passes only when Gate B, Gate C and Gate D pass and report repositories, trace sanitization, PDF fallback, checkpoint recovery and shared schemas pass for both verticals.
- [x] Preserve separate artifact paths/hashes for public and startup results; do not merge raw payloads.
- [x] Run focused tests and commit `feat: implement combined offline Gate E evaluator`.

## Task 2D.5 — Add Thin CLI and PowerShell Runners in Wave 3

**Integration owner files:**
- Modify: `src/due_diligence_agent/presentation/cli.py`
- Create: `scripts/run_stage1b_gate_d.ps1`
- Create: `scripts/run_stage1b_gate_e.ps1`
- Modify: `tests/evaluation/test_startup_gate_d.py`
- Modify: `tests/evaluation/test_combined_gate_e.py`

- [x] Add `investment-dd run-gate-d --dataset startup_synthetic_v1 --output-dir <unique>` and `run-gate-e --dataset capstone_combined_v1 --output-dir <unique>`.
- [x] Scripts blank provider keys/tracing flags locally, force offline hubs, validate output root is not the repository root, and return evaluator exit status.
- [x] Add command tests for success, invalid dataset, missing output dir, collision and evaluator failure.
- [x] Commit: `feat: add offline Gate D and Gate E runners`.

## Task 2D.6 — Queue 2 Dry Run and Queue 5 Handoff

- [x] Run Gate D twice into `output/gate-d/<unique-a>` and `<unique-b>`; compare canonical contract hashes, not timestamped file hashes.
- [x] Run Gate C once to prove Queue 1 regression remains green.
- [x] Run Gate E once after integration and retain `eval-result.json`, report JSON/HTML/PDF refs and sanitized audit refs.
- [x] Scan outward artifacts for fixture privacy sentinels, secrets, emails and local paths; expected matches: zero.
- [x] Record Queue 2 verification under `docs/verification/`; final repeated Gate B/C/D/E, screenshots and demo script remain Queue 5.
- [x] Commit: `docs: record Queue 2 frozen evaluation evidence`.
