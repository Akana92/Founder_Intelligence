# Queue 2B Startup Market Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить Startup Profile в проверяемый market research snapshot: карта конкурентов, TAM/SAM/SOM с допущениями и цитатами, а также датированные news/sentiment signals, воспроизводимые offline и явно отличимые от live research.

**Architecture:** `StartupMarketResearchService` сначала строит bounded research plan из безопасных полей профиля, затем вызывает отдельный `StartupResearchPort`. Frozen adapter загружает manifest-verified источники и является обязательным первым implementation. Live adapter позже переиспользует `GdeltNewsAdapter` и разрешённый web-search provider через egress/budget boundary. Yahoo Finance остаётся только secondary public-comparable context и не используется для поиска частных стартапов или primary financial claims.

**Tech Stack:** Python 3.12/3.13, Pydantic v2, existing source governance in `ports/collectors.py`, GDELT/news fixtures, pytest, Ruff, strict mypy.

## Closure status — 2026-08-14

Queue 2B is complete for frozen/offline market research. Evidence: bounded research-plan contracts, manifest-verified frozen competitor/news adapter, TAM/SAM/SOM assumption lineage, dated secondary sentiment, graph/report integration, focused Queue 2 regression `338 passed`, Gate C/D/E closure PASS, backend `1101 passed, 1 skipped`, Ruff and strict mypy PASS. The live research protocol/provider seam is documented and default-off; actual live web/GDELT/Yahoo/OpenAI/news execution remains deferred outside frozen Queue 2 and was not called during closure.

## Global Constraints

- Frozen mode не читает сеть, ключи или mutable cache.
- Каждый competitor/market assertion имеет source id, source mode, as-of and confidence либо явный `inference`/`insufficient_data` status.
- Competitor taxonomy: `direct`, `indirect`, `substitute`, `do_nothing`, `potential_entrant`.
- News/sentiment — датированный secondary signal; никогда не поддерживает primary financial metrics.
- TAM/SAM/SOM не генерируются из одной LLM-оценки: каждая величина содержит формулу, unit/currency, as-of, assumption refs и source refs; отсутствие input даёт partial/insufficient.
- Не использовать paid/live calls в Queue 2B implementation/verification.
- Shared startup graph/container/report files закрыты до Wave 3.

## Task 2B.1 — Lock Market Research Domain and Source Contracts

**Files:**
- Create: `src/due_diligence_agent/domain/startup/market.py`
- Create: `src/due_diligence_agent/ports/startup_research.py`
- Create: `tests/unit/domain/test_startup_market.py`

- [x] Write RED tests for `StartupResearchSourceMode`, `StartupResearchSource`, `StartupCompetitor`, `MarketSizingAssumption`, `MarketSizingEstimate`, `StartupSentimentSignal` and `StartupMarketResearchSnapshot`.
- [x] Require frozen Pydantic models, bounded labels/URLs, SHA-256 source hashes, UTC/as-of dates, taxonomy enum, deterministic snapshot id/hash and schema `startup_market_research@1`.
- [x] Define `StartupResearchPlan` and `StartupResearchPort.collect(plan) -> StartupMarketResearchSnapshot` without importing adapters.
- [x] Run RED:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/domain/test_startup_market.py
```

Expected RED: module import failure.

- [x] Import contracts from their explicit modules so Wave 1 does not collide with Queue 2A over `domain/startup/__init__.py`.
- [x] Implement minimum models/protocol and run GREEN.
- [x] Run Ruff/strict mypy on changed source files.
- [x] Commit: `feat: add startup market research contracts`.

## Task 2B.2 — Build a Bounded Research Plan from Startup Profile

**Files:**
- Create: `src/due_diligence_agent/application/services/startup_market_research_service.py`
- Create: `tests/unit/application/test_startup_market_research_service.py`

- [x] Write RED tests for complete profile, missing ICP/geography, contradictory business model and private-looking values.
- [x] Implement deterministic plan construction from `solution`, `icp`, `users`, `buyers`, `geography`, `business_model`, `pricing_revenue_model` and `competitors_mentioned` only.
- [x] Reject/omit unsafe query values using the existing privacy policy style; cap query count and length.
- [x] Mark incomplete plan dimensions rather than inventing search terms.
- [x] Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/application/test_startup_market_research_service.py -k research_plan
```

Expected GREEN: stable queries independent of field order; gaps remain explicit.
- [x] Commit: `feat: build bounded startup research plans`.

## Task 2B.3 — Implement Frozen-First Competitor and News Research

**Files:**
- Create: `src/due_diligence_agent/adapters/startup/frozen_market_research.py`
- Create: `tests/fixtures/startup_market_research_v1/manifest.json`
- Create: `tests/fixtures/startup_market_research_v1/sources/competitors.json`
- Create: `tests/fixtures/startup_market_research_v1/sources/news.json`
- Create: `tests/integration/retrieval/test_startup_market_research.py`

- [x] Write RED tests for manifest hashes, frozen/live provenance, all five competitor categories, duplicate competitor merge, source dates, stale signals, partial source outage and no network client construction.
- [x] Implement a manifest-verified adapter. Reuse `NewsItem` governance rules where compatible; keep licensed metadata only.
- [x] Ensure a damaged optional source produces a partial snapshot with stable diagnostic code while manifest tampering fails closed.
- [x] Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/integration/retrieval/test_startup_market_research.py tests/contract/sources/test_market_news.py
```

Expected GREEN: deterministic offline snapshot, explicit partial behavior and secondary-source governance preserved.
- [x] Commit: `feat: add frozen startup competitor research`.

## Task 2B.4 — Calculate TAM/SAM/SOM with Assumption Lineage

**Files:**
- Modify: `src/due_diligence_agent/application/services/startup_market_research_service.py`
- Modify: `tests/unit/application/test_startup_market_research_service.py`

- [x] Write RED cases for top-down and bottom-up inputs, currency/unit mismatch, missing adoption rate, invalid hierarchy (`SOM > SAM` or `SAM > TAM`) and conflicting sources.
- [x] Implement deterministic Decimal formulas and bounded assumptions; every estimate stores formula version, input refs, assumption refs, unit, currency and as-of.
- [x] Never turn narrative estimates into numeric market sizes without explicit numeric inputs.
- [x] Run:

```powershell
uv run pytest -q -p no:cacheprovider tests/unit/application/test_startup_market_research_service.py -k market_sizing
```

Expected GREEN: valid hierarchy and reproducible calculations; insufficient inputs produce no amount.
- [x] Commit: `feat: add cited startup market sizing`.

## Task 2B.5 — Keep Sentiment Dated and Secondary-Only

**Files:**
- Modify: `src/due_diligence_agent/application/services/startup_market_research_service.py`
- Modify: `tests/unit/application/test_startup_market_research_service.py`

- [x] Write RED tests proving sentiment without source/as-of is rejected, stale windows are flagged, and sentiment cannot support a primary financial claim.
- [x] Aggregate only bounded `positive|neutral|negative` signals with counts and date window; retain source ids rather than article bodies.
- [x] Run the focused `-k sentiment` tests and commit `feat: add dated secondary startup sentiment signals`.

## Task 2B.6 — Define the Live Research Boundary without Calling It

**Files:**
- Create: `src/due_diligence_agent/ports/startup_web_search.py`
- Create: `tests/unit/application/test_startup_live_research_policy.py`

- [x] Specify an allowlisted, timeout/budget/citation-returning web search protocol and stable outage codes.
- [x] Prove disabled/default/frozen mode makes zero calls and that news/web outages yield partial research rather than invented competitors.
- [x] Reuse `adapters/news/gdelt.py` only behind this later integration; document that `adapters/market_data/yfinance_demo.py` is public-comparable secondary context, not startup discovery.
- [x] Run focused tests; no network traffic is permitted.
- [x] Commit: `feat: define bounded live startup research boundary`.

## Task 2B.7 — Wave 3 Graph and Report Handoff

**Integration owner files only:**
- Modify: `src/due_diligence_agent/workflows/startup/ports.py`
- Modify: `src/due_diligence_agent/workflows/startup/nodes/market.py`
- Modify: `src/due_diligence_agent/workflows/startup/graph.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Modify: `src/due_diligence_agent/application/services/startup_report_service.py`
- Modify: `src/due_diligence_agent/workflows/startup/nodes/report.py`
- Modify: `tests/graph/test_startup_workflow.py`
- Modify: `tests/unit/reporting/test_startup_report_snapshot.py`

- [x] Add a bounded `market_research` node after `profile_enrichment`, execute it in parallel with the metrics→financial→risk branch, and extend the existing `workflows/startup/nodes/market.py::market_analysis` as the join/synthesis point before Reflexion. Do not create a duplicate market-analysis node.
- [x] Store full research outside checkpoint; checkpoint/report input carries snapshot id/hash/revision.
- [x] Render market size, competitor groups, source/as-of, inference/partial labels and dated sentiment from the canonical research snapshot.
- [x] Verify Gate 2 denial makes zero research calls, frozen mode is deterministic and report hash changes when research identity changes.
- [x] Commit: `feat: integrate startup market research into graph and report`.
