# Sales-Ready Hybrid B-to-C Architecture Boundaries

Date: 2026-08-12

Scope: this document freezes the architecture boundary for delivery profile B, Sales-Ready Hybrid, and the later C upgrade path. B ships a sellable single-operator/local-or-hosted-single-tenant product. C adds platform infrastructure without rewriting the analytical core.

## 1. Invariants

1. B and C use the same analytical pipeline and business methodology.
2. The user flow is universal upload, primary analysis, deep analysis in the same case. The product must not ask the user to choose a demo project, vertical, SaaS/marketplace/e-commerce/fintech mode, or technical research mode before the first analysis.
3. `/api/v1` contracts introduced in B remain compatible when C is introduced. C may add fields that are nullable or optional in v1, but breaking changes require a new API version.
4. Startup capabilities that are not implemented yet must be represented as `planned` or `unavailable`; neither API nor UI may present synthetic analysis as completed real work.
5. Raw startup documents, PII, prompts, API keys, file names, request bodies, cookies, and arbitrary headers must not be copied into tracing attributes, frontend logs, or response metadata.

## 2. Reusable core

These modules are product core and stay independent from HTTP, React, browser state, storage engine choice, and tenant policy.

| Core area | Current source of truth | B/C rule |
|---|---|---|
| Case model | `src/due_diligence_agent/domain/cases/models.py` | Reuse and extend with startup case concepts through domain contracts only. |
| Artifact model | `src/due_diligence_agent/domain/artifacts/models.py` | Reuse for uploaded/parsed documents; storage implementation remains an adapter. |
| Evidence model and ledger | `src/due_diligence_agent/domain/evidence/models.py`, `src/due_diligence_agent/domain/evidence/ledger.py` | Reuse for public comparables and startup claims. Evidence provenance remains first-class. |
| Calculation engine | `src/due_diligence_agent/domain/metrics/engine.py`, `src/due_diligence_agent/domain/metrics/definitions.py` | Reuse deterministic metric execution. Frontend and HTTP routes must not recalculate business metrics. |
| Public metrics | `src/due_diligence_agent/domain/metrics/public_company.py` | Reuse as comparable-analysis metric pack; startup packs extend the registry later. |
| Findings and risks | `src/due_diligence_agent/domain/findings/models.py`, `src/due_diligence_agent/domain/findings/risk.py` | Reuse finding/risk primitives for startup market, competition, readiness, and contradiction findings. |
| Approvals/HITL | `src/due_diligence_agent/domain/approvals/models.py` | Reuse where user approval is required for external data egress or ambiguous evidence. |
| Report model | `src/due_diligence_agent/domain/reports/models.py` | Reuse report snapshot semantics; startup report adds new sections without replacing public report contracts. |
| Application services | `src/due_diligence_agent/application/services/*.py` | Reuse as orchestration boundary between presentation and domain/adapters. New API and UI call services, not adapters directly. |
| Policies | `src/due_diligence_agent/application/policies/*.py` | Reuse for model routing, budget, data egress, content rights, and source priority. |
| Public workflow pattern | `src/due_diligence_agent/workflows/public_company/graph.py`, `src/due_diligence_agent/workflows/public_company/nodes/*.py` | Reuse Plan-and-Execute and Reflexion patterns. Startup graph is added as a sibling workflow, not by embedding presentation logic in public workflow nodes. |
| Shared workflow utilities | `src/due_diligence_agent/workflows/shared/*.py` | Reuse for plan, node result, and reflexion loops. |
| Ports | `src/due_diligence_agent/ports/*.py` | Reuse as dependency boundaries for repositories, collectors, LLM, retrieval, rendering, and tracing. |
| Bootstrap composition | `src/due_diligence_agent/bootstrap/container.py` | Extend as the composition root for B adapters; C swaps implementations behind the same ports. |

## 3. B adapters and presentation surfaces

B is allowed to add or use these adapters:

| B concern | Current/new owner | Boundary |
|---|---|---|
| Local persistence | `src/due_diligence_agent/adapters/local_storage/sqlite_db.py`, `src/due_diligence_agent/adapters/local_storage/repositories.py`, `src/due_diligence_agent/adapters/local_storage/artifact_store.py` | SQLite and local artifacts are acceptable for B. Domain and workflows must only see repository/artifact abstractions. |
| Cached/frozen public data | `src/due_diligence_agent/adapters/http/snapshot_cache.py`, `src/due_diligence_agent/adapters/http/public_fixture_manifest.py`, `tests/fixtures/public_us_frozen_v1/**` | B demo must remain reproducible without paid API usage. |
| Public SEC adapter | `src/due_diligence_agent/adapters/sec/edgar.py` | Reused for secondary comparable analysis and public-company evidence. |
| Market data snapshot | `src/due_diligence_agent/adapters/market_data/yfinance_demo.py` | Research-only adapter with visible source limitations. |
| Local observability | `src/due_diligence_agent/adapters/observability/context.py`, `src/due_diligence_agent/adapters/observability/audit_spool.py`, `src/due_diligence_agent/adapters/observability/otel.py`, `src/due_diligence_agent/adapters/observability/langsmith.py`, `src/due_diligence_agent/adapters/observability/privacy.py` | B may expose tracing and audit in Admin Console. Trace attributes must be safe scalar metadata only. |
| FastAPI presentation | `src/due_diligence_agent/presentation/api/*` | New B adapter. It owns HTTP concerns, request IDs, versioned routes, response schemas, and dependency wiring. |
| Founder Workspace | `frontend/founder/*` | New separate web UI. It consumes `/api/v1` contracts and never duplicates formulas, findings, evidence sufficiency, or analysis status logic. |
| Streamlit Admin Console | `src/due_diligence_agent/presentation/streamlit/app.py`, `src/due_diligence_agent/presentation/streamlit/pages/public_case.py`, `src/due_diligence_agent/presentation/streamlit/components/*.py` | Kept as Admin Console and secondary public comparable surface during B. It is not the main founder-facing product shell. |
| CLI | `src/due_diligence_agent/presentation/cli.py` | Kept for smoke/demo operations and non-UI verification. |

B request context is anonymous/single-operator. It may generate a request ID and local operator/session marker, but it must not infer trusted identity from anonymous headers.

## 4. C replacements and extensions

C replaces or extends B through named seams:

| C capability | First seam in B | C owner module target | Acceptance boundary |
|---|---|---|---|
| Authenticated principal resolver | `src/due_diligence_agent/presentation/api/context.py` | `src/due_diligence_agent/adapters/identity/*` plus API dependency replacement | Route functions receive a trusted principal from dependency injection; no route parses cookies or auth headers directly. |
| RBAC and workspace policy | Nullable `actor_id` and `workspace_id` in API request context | `src/due_diligence_agent/application/policies/workspace_access.py` | Access decisions sit in application policy/services, not in domain models or frontend-only checks. |
| Multi-tenancy | Repository ports in `src/due_diligence_agent/ports/repositories.py` | tenant-aware repository implementations | Domain and workflow signatures remain storage-neutral; tenant filters are enforced by adapters/policies. |
| PostgreSQL persistence | local repository port implementations | `src/due_diligence_agent/adapters/postgres/*` | Same application service contracts; no tenant SQL inside domain/workflows. |
| Object storage | artifact store seam | `src/due_diligence_agent/adapters/object_storage/*` | Artifact IDs and locators stay stable; raw object locations are not leaked to frontend contracts. |
| Durable job queue | service/workflow invocation seam | `src/due_diligence_agent/adapters/jobs/*` | Asynchronous execution can replace local synchronous runner without changing analysis results or report schema. |
| Deployment controls | runner/config seams | `deploy/*`, `infra/*`, `src/due_diligence_agent/config.py` extensions | C adds production deployment, health, backup, and SLO checks; B local runner remains simple and safe by default. |
| Backup and restore | persistence adapter boundary | `src/due_diligence_agent/adapters/backup/*` | Backups cover database, artifacts, audit logs, and reports with tested restore; B does not imply this guarantee. |
| SLO/operations | observability ports and Admin Console metrics | `src/due_diligence_agent/adapters/observability/*` extensions and deployment dashboards | C can add uptime/error-budget monitoring without changing business analysis code. |
| Billing/subscriptions | no B implementation | `src/due_diligence_agent/application/policies/entitlements.py` plus platform adapters | Deferred to C; B must not hard-code billing assumptions in product capabilities. |

## 5. Prohibited coupling

The following imports or concepts are prohibited in core modules:

- `fastapi`, `starlette`, HTTP status codes, headers, cookies, request objects, or response objects inside `src/due_diligence_agent/domain/**`, `src/due_diligence_agent/application/services/**`, `src/due_diligence_agent/application/policies/**`, and `src/due_diligence_agent/workflows/**`.
- React, JSX/TSX, browser storage, CSS classes, DOM concepts, or Next.js types inside any Python core module.
- Tenant SQL, auth provider SDKs, cookie parsing, JWT parsing, billing provider SDKs, or deployment-specific secrets inside domain or workflow modules.
- Business metric formulas or evidence sufficiency rules in `frontend/founder/**` or `src/due_diligence_agent/presentation/api/routers/**`.
- Raw document text, uploaded filenames, request bodies, query strings, cookies, authorization headers, API keys, prompts, or model outputs as OpenTelemetry/LangSmith attribute values unless explicitly redacted and summarized by a privacy adapter.

Architecture guard tests must enforce this boundary before UI or C work is considered complete.

## 6. API compatibility rule

All new HTTP routes are versioned under `/api/v1`. The first B API must include compatibility seams for C:

- stable capability/status discriminators;
- canonical request ID in every response;
- nullable `actor_id` and `workspace_id` in request context, not trusted in B;
- explicit lifecycle statuses for `available`, `planned`, and `unavailable`;
- optional fields only for future C metadata unless a new API version is introduced.

C may add authentication, tenancy, durable jobs, and production metadata behind these fields. C must not change the meaning of B analysis outputs, evidence references, metric definitions, or report snapshots.

## 7. Stop conditions

B foundation is acceptable when:

1. Stage 1A Public Company Gate B remains green.
2. The product contract truthfully shows public comparable analysis as available and universal startup analysis as planned until safe ingest and startup graph are implemented.
3. Founder Workspace and Admin Console are visually and structurally separate.
4. API contracts expose only versioned, safe metadata.
5. The architecture guard proves presentation and platform concerns do not enter domain/workflow modules.

C work starts only after B has a working Founder Workspace, API v1 foundation, Admin tracing view, and documented upgrade seams.

## 8. C migration checklist

Analytics depth does not change between B and C. Universal upload, primary analysis, deep analysis, evidence sufficiency, deterministic metrics, risk and contradiction logic, bounded Reflexion, and report snapshot semantics remain the same. C adds platform infrastructure through the seams already defined above.

- [ ] Auth provider — validate signed credentials through a dedicated identity adapter; never parse provider tokens in routes, domain models, or workflow nodes.
- [ ] Principal resolver — replace the anonymous B dependency with a trusted principal resolver that populates the existing nullable request-context seams.
- [ ] Tenant policy — enforce actor/workspace access in application policy and service boundaries, with deny-by-default behavior and no frontend-only authorization.
- [ ] PostgreSQL persistence — add tenant-aware repository implementations behind the existing repository ports and migration tooling with rollback evidence.
- [ ] Object storage — store raw artifacts behind the artifact-store seam while keeping stable artifact IDs and opaque frontend locators.
- [ ] Background job execution — move long-running workflow invocation behind a durable job adapter with idempotency, retry, cancellation, and resume semantics.
- [ ] Secrets management — load provider and infrastructure credentials from a production secret manager; never expose them through traces, logs, reports, or browser contracts.
- [ ] Backup and restore — cover PostgreSQL, object storage, audit data, and report snapshots with an exercised restore procedure.
- [ ] Rate limits — enforce per-principal and per-workspace limits at the API/platform boundary without changing analytical decisions.
- [ ] Audit retention — define immutable audit retention, redaction, export, and deletion policies without copying raw document content into trace attributes.
- [ ] SLOs — define and monitor availability, latency, queue delay, recovery, and error-budget objectives for the API, jobs, storage, and critical analysis path.
