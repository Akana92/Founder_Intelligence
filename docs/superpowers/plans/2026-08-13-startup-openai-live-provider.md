# Startup OpenAI Live Provider Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Connect the live startup-analysis workflow to OpenAI structured outputs while keeping document egress approval-gated, traceable, and capped at USD 0.25 per case by default.

**Architecture:** A dedicated startup provider resolves only persisted evidence facts and calculations referenced by the workflow state, converts them into bounded minimized fragments, and calls the existing `OpenAIGateway`. The gateway remains the single boundary for egress policy, audit events, model routing, schema validation, and budget reservation. The synchronous LangGraph startup node uses a small synchronous bridge around the async gateway; raw uploaded document text is not exported in this slice.

**Tech Stack:** Python 3.12, Pydantic Settings/SecretStr, OpenAI Python SDK Responses API structured outputs, existing LangGraph workflow, SQLite repositories, existing BudgetGuard/DataEgressPolicy/JsonlAuditSpool, pytest, Ruff, mypy.

---

## Task 1: Configuration and provider-status contract

**Files:**
- Modify: `src/due_diligence_agent/config.py`
- Modify: `src/due_diligence_agent/application/startup_cases.py`
- Modify: `.env.example`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/application/test_startup_case_coordinator.py`

- [ ] Add RED tests proving `OPENAI_API_KEY` is optional, remains a secret type, and live cases report `configured` only when the coordinator is explicitly wired with a provider.
- [ ] Add a dedicated OpenAI startup settings contract with `gpt-5.6-luna`, conservative timeouts/retries, per-call reservation, and a default USD 0.25 per-case hard cap.
- [ ] Add an explicit `live_provider_configured` coordinator input and persist the resulting provider status across start/resume.
- [ ] Run the focused configuration and coordinator tests.

## Task 2: Evidence-first structured startup provider

**Files:**
- Create: `src/due_diligence_agent/adapters/openai/startup_provider.py`
- Modify: `src/due_diligence_agent/workflows/startup/ports.py`
- Modify: `src/due_diligence_agent/workflows/startup/nodes/financial.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Test: `tests/unit/llm/test_startup_openai_provider.py`
- Test: `tests/graph/test_startup_workflow.py`

- [ ] Add RED tests proving only requested in-case facts/calculations become minimized fragments, restricted inputs never call OpenAI, invalid references are rejected, and structured results become domain `Finding` objects with valid provenance.
- [ ] Extend the provider boundary with `case_id` so generated findings are correctly owned without database-private lookups.
- [ ] Implement bounded context serialization and Pydantic structured-output schemas for financial, risk, and market findings.
- [ ] Bridge the async `OpenAIGateway` safely from the synchronous workflow and keep schema repair/fallback inside the existing gateway.
- [ ] Preserve the existing persistence contract in `_StartupProviderWorkflowPort`.
- [ ] Run provider, budget-guard, and graph regression tests.

## Task 3: Live API wiring and audit/budget guarantees

**Files:**
- Modify: `src/due_diligence_agent/presentation/api/dependencies.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Test: `tests/api/test_startup_api.py`

- [ ] Add RED API tests for configured/unavailable provider status without making network calls.
- [ ] Build the real OpenAI client only when the key is configured, pass the provider factory into the live composer, and retain deterministic-offline behavior unchanged.
- [ ] Use the existing local audit spool and one shared per-process `BudgetGuard` so every attempt is reserved before network egress.
- [ ] Run API, egress, audit-spool, and budget regressions.

## Task 4: Verification and one bounded live smoke

**Files:**
- No credential-bearing files committed.

- [ ] Run focused pytest, full backend Ruff, strict mypy, and relevant startup API/graph/report regressions with a workspace-local pytest temp root.
- [ ] Verify `.env` stays ignored and no secret appears in tracked diffs or logs.
- [ ] Perform exactly one minimal structured Responses API smoke call using the configured key and the cost-efficient model; do not run a paid full workflow.
- [ ] Record only model/usage/status, never the key or response metadata that may contain sensitive content.
- [ ] Request an independent code review and resolve any load-bearing findings before completion.
