# Sales-Ready Hybrid Reuse / Create / Extend Matrix

Date: 2026-08-12

Scope: implementation ownership map for delivery profile B with an explicit C upgrade seam. Classification values are `reuse`, `extend`, `new adapter`, or `defer to C`.

## Matrix

| Subsystem | Decision | Current source file(s) | First new owner module/file | Rule |
|---|---|---|---|---|
| Package root and typed package marker | reuse | `src/due_diligence_agent/__init__.py`, `src/due_diligence_agent/py.typed` | none | Keep package identity stable; no product rename in Python package during B. |
| Runtime configuration | extend | `src/due_diligence_agent/config.py` | `src/due_diligence_agent/presentation/api/app.py` and later C `deploy/*` | Add API/web configuration through typed settings; do not store secrets in UI or traces. |
| Composition root | extend | `src/due_diligence_agent/bootstrap/container.py` | `src/due_diligence_agent/presentation/api/dependencies.py` | API dependencies call the container/application services; C swaps adapters behind ports. |
| Shared domain primitives | reuse | `src/due_diligence_agent/domain/common.py` | future startup domain modules as needed | Keep shared value objects and primitives free of presentation, auth, tenant, and storage concerns. |
| Case domain | reuse | `src/due_diligence_agent/domain/cases/models.py` | future `src/due_diligence_agent/domain/startups/models.py` only if the existing case model is insufficient | Keep case identity independent from transport, auth, and tenant storage. |
| Artifact domain | reuse | `src/due_diligence_agent/domain/artifacts/models.py` | future `src/due_diligence_agent/application/services/startup_ingest_service.py` | Startup data room artifacts reuse the same artifact contract and locator discipline. |
| Evidence facts | reuse | `src/due_diligence_agent/domain/evidence/models.py` | future `src/due_diligence_agent/application/services/startup_evidence_service.py` | Claims, counter-evidence, and insufficient-data states must point to evidence/locators. |
| Evidence ledger | extend | `src/due_diligence_agent/domain/evidence/ledger.py`, `src/due_diligence_agent/application/services/evidence_service.py` | future `src/due_diligence_agent/application/services/startup_claim_service.py` | Extend ledger usage for startup claims; do not create a parallel evidence store. |
| Metric definitions | extend | `src/due_diligence_agent/domain/metrics/definitions.py` | future `src/due_diligence_agent/domain/metrics/startup.py` | Add startup metric packs through the metric registry and deterministic formulas. |
| Metric engine | reuse | `src/due_diligence_agent/domain/metrics/engine.py` | none | Frontend and API routers never recalculate metrics. |
| Public company metrics | reuse | `src/due_diligence_agent/domain/metrics/public_company.py` | none | Keep as secondary comparable analysis. |
| Findings | extend | `src/due_diligence_agent/domain/findings/models.py`, `src/due_diligence_agent/domain/findings/risk.py` | future `src/due_diligence_agent/domain/findings/startup.py` | Startup risks, market weaknesses, missing evidence, and next actions reuse finding semantics. |
| Approvals/HITL | extend | `src/due_diligence_agent/domain/approvals/models.py`, `src/due_diligence_agent/workflows/public_company/nodes/approvals.py` | future `src/due_diligence_agent/workflows/startup/nodes/approvals.py` | Reuse approval states for external egress and ambiguous evidence decisions. |
| Report snapshots | extend | `src/due_diligence_agent/domain/reports/models.py`, `src/due_diligence_agent/application/services/report_service.py` | future `src/due_diligence_agent/domain/reports/startup_sections.py` | Startup report extends sections; public report schema remains backward-compatible. |
| Rendering port | reuse | `src/due_diligence_agent/ports/rendering.py` | none | HTML/PDF renderers stay behind the port. |
| Repository ports | extend | `src/due_diligence_agent/ports/repositories.py` | future C `src/due_diligence_agent/adapters/postgres/repositories.py` | B uses local repos; C adds tenant-aware repos without changing domain/workflow code. |
| Collector ports | reuse | `src/due_diligence_agent/ports/collectors.py` | future `src/due_diligence_agent/adapters/research/*` | New web/news/competitor collectors implement ports and source policies. |
| LLM port | reuse | `src/due_diligence_agent/ports/llm.py` | future startup structured-output services | Keep provider logic outside domain/workflows. |
| Retrieval port | reuse | `src/due_diligence_agent/ports/retrieval.py` | future startup artifact retrieval service | Retrieval backend remains replaceable. |
| Tracing port | extend | `src/due_diligence_agent/ports/tracing.py` | `src/due_diligence_agent/presentation/api/middleware.py` | API middleware attaches safe request metadata; C can add production exporters. |
| Public workflow graph | reuse | `src/due_diligence_agent/workflows/public_company/graph.py` | none | Do not rewrite the working public comparable graph. |
| Public workflow plan/state | reuse | `src/due_diligence_agent/workflows/public_company/plan.py`, `src/due_diligence_agent/workflows/public_company/state.py` | future `src/due_diligence_agent/workflows/startup/plan.py`, future `src/due_diligence_agent/workflows/startup/state.py` | Keep graph state and plan contracts workflow-local; startup receives sibling contracts only when needed. |
| Public workflow scope node | reuse | `src/due_diligence_agent/workflows/public_company/nodes/scope.py` | future `src/due_diligence_agent/workflows/startup/nodes/scope.py` | Use as proven scoping pattern; startup scope logic stays in sibling workflow code. |
| Public workflow collection node | reuse | `src/due_diligence_agent/workflows/public_company/nodes/collect.py` | future `src/due_diligence_agent/workflows/startup/nodes/collect.py` | Reuse collection orchestration pattern without sharing public-company-specific source assumptions. |
| Public workflow normalization node | reuse | `src/due_diligence_agent/workflows/public_company/nodes/normalize.py` | future `src/due_diligence_agent/workflows/startup/nodes/normalize.py` | Startup normalization is sibling code using shared artifact/evidence contracts. |
| Public workflow metrics node | reuse | `src/due_diligence_agent/workflows/public_company/nodes/metrics.py` | future `src/due_diligence_agent/workflows/startup/nodes/metrics.py` | Reuse deterministic metric invocation pattern; startup formulas live in startup metric packs. |
| Public workflow financial analysis node | reuse | `src/due_diligence_agent/workflows/public_company/nodes/financial_analysis.py` | future `src/due_diligence_agent/workflows/startup/nodes/financial_analysis.py` | Reuse analysis-node shape; startup financial logic must use startup evidence and metric contracts. |
| Public workflow market analysis node | reuse | `src/due_diligence_agent/workflows/public_company/nodes/market_analysis.py` | future `src/due_diligence_agent/workflows/startup/nodes/market_analysis.py` | Reuse market-analysis orchestration pattern; startup market research adds its own source policy. |
| Public workflow risk analysis node | reuse | `src/due_diligence_agent/workflows/public_company/nodes/risk_analysis.py` | future `src/due_diligence_agent/workflows/startup/nodes/risk_analysis.py` | Reuse finding/risk synthesis pattern. |
| Public workflow reflexion node | reuse | `src/due_diligence_agent/workflows/public_company/nodes/reflexion.py` | future `src/due_diligence_agent/workflows/startup/nodes/reflexion.py` | Reuse contradiction/reflexion loop shape while preserving domain-specific evidence rules. |
| Public workflow approvals node | extend | `src/due_diligence_agent/workflows/public_company/nodes/approvals.py` | future `src/due_diligence_agent/workflows/startup/nodes/approvals.py` | Reuse approval states for external egress and ambiguous evidence decisions. |
| Shared workflow primitives | reuse | `src/due_diligence_agent/workflows/shared/plan.py`, `src/due_diligence_agent/workflows/shared/node_result.py`, `src/due_diligence_agent/workflows/shared/reflexion.py` | future `src/due_diligence_agent/workflows/startup/graph.py` | Reflexion and plan/node contracts are shared across public and startup analysis. |
| Public analysis service | reuse | `src/due_diligence_agent/application/services/public_analysis_service.py` | none | Remains available as Public Comparables. |
| Public metric service | reuse | `src/due_diligence_agent/application/services/public_metric_service.py` | none | Keeps public comparable metric calculations. |
| Filing parsing service | reuse | `src/due_diligence_agent/application/services/filing_parsing_service.py` | none | SEC filing parsing remains public-company source processing. |
| Retrieval service | extend | `src/due_diligence_agent/application/services/retrieval_service.py` | future `src/due_diligence_agent/application/services/startup_retrieval_service.py` if startup retrieval needs separate query shape | Reuse first; split only if startup retrieval contract differs. |
| Case service | extend | `src/due_diligence_agent/application/services/case_service.py` | future `src/due_diligence_agent/application/services/startup_case_service.py` | Startup case lifecycle can extend service contracts while keeping repository ports. |
| Data egress policy | reuse | `src/due_diligence_agent/application/policies/data_egress.py` | future Startup Gate 2 API route/service | Startup external calls must pass this policy; default-deny until approved. |
| Content rights policy | reuse | `src/due_diligence_agent/application/policies/content_rights.py` | future startup ingest policy | Keep parser/external-use rights explicit. |
| Budget policy | reuse | `src/due_diligence_agent/application/policies/budget.py` | future C entitlement policy | B budget controls are local; C entitlements are deferred. |
| Model routing policy | reuse | `src/due_diligence_agent/application/policies/model_routing.py` | future startup orchestration services | Model selection stays outside UI. |
| Source priority policy | extend | `src/due_diligence_agent/application/policies/source_priority.py` | future `src/due_diligence_agent/application/policies/startup_source_priority.py` if needed | Startup research inherits explicit source-priority behavior. |
| Product capabilities contract | new adapter | none | `src/due_diligence_agent/application/product/capabilities.py` | Framework-independent contract consumed by API and UI to show truthful available/planned status. |
| FastAPI application | new adapter | none | `src/due_diligence_agent/presentation/api/app.py` | Owns HTTP app factory and `/api/v1` registration only. |
| API request context | new adapter | none | `src/due_diligence_agent/presentation/api/context.py` | B creates request IDs and nullable identity/workspace seams; C replaces resolver. |
| API dependency wiring | new adapter | none | `src/due_diligence_agent/presentation/api/dependencies.py` | Keeps route functions thin and replaceable. |
| API middleware | new adapter | none | `src/due_diligence_agent/presentation/api/middleware.py` | Owns request ID normalization and safe OTel attributes. |
| API system routes | new adapter | none | `src/due_diligence_agent/presentation/api/routers/system.py` | Owns health and product capability endpoints. |
| API local runner | new adapter | none | `src/due_diligence_agent/presentation/api/__main__.py`, `scripts/run_founder_api.ps1` | B runner binds to localhost by default. |
| Founder Workspace | new adapter | none | `frontend/founder/app/page.tsx`, `frontend/founder/components/*`, `frontend/founder/lib/*` | Main founder-facing UI; consumes API contracts and displays honest planned states. |
| Founder design contract | new adapter | none | `PRODUCT.md`, `.impeccable/surface-briefs/founder-workspace.md`, `DESIGN.md` | Locks investor-grade visual/product surface without changing analysis logic. |
| Streamlit shell | extend | `src/due_diligence_agent/presentation/streamlit/app.py` | future `src/due_diligence_agent/presentation/streamlit/pages/admin.py` if split is needed | Keep as Admin Console and secondary public comparable interface. |
| Streamlit public page | reuse | `src/due_diligence_agent/presentation/streamlit/pages/public_case.py` | none | Preserve public comparable demo during B. |
| Streamlit audit component | extend | `src/due_diligence_agent/presentation/streamlit/components/audit.py` | future admin-only tracing component | Reuse for Admin Console audit/tracing proofs; do not make it the founder main UX. |
| Streamlit evidence component | extend | `src/due_diligence_agent/presentation/streamlit/components/evidence.py` | future admin-only evidence inspection component | Reuse for Admin Console evidence inspection while Founder Workspace consumes API summaries. |
| Streamlit metrics component | extend | `src/due_diligence_agent/presentation/streamlit/components/metrics.py` | future admin-only metrics inspection component | Reuse for Admin Console metric proofs; frontend still does not calculate metrics. |
| Streamlit risks component | extend | `src/due_diligence_agent/presentation/streamlit/components/risks.py` | future admin-only risk inspection component | Reuse for Admin Console risk proofs and public comparable diagnostics. |
| CLI | reuse | `src/due_diligence_agent/presentation/cli.py` | none | Keeps operational smoke path. |
| SEC EDGAR adapter | reuse | `src/due_diligence_agent/adapters/sec/edgar.py`, `src/due_diligence_agent/adapters/sec/models.py` | none | Public comparable source adapter. |
| HTTP fixture/cache adapters | reuse | `src/due_diligence_agent/adapters/http/fair_access.py`, `src/due_diligence_agent/adapters/http/snapshot_cache.py`, `src/due_diligence_agent/adapters/http/public_fixture_manifest.py` | future startup research cache adapters | Keep B reproducible and fair-access bounded. |
| YFinance demo adapter | reuse | `src/due_diligence_agent/adapters/market_data/yfinance_demo.py` | future `src/due_diligence_agent/adapters/market_data/live_yfinance.py` if live mode is enabled | Research-only market snapshot, not source of record. |
| GDELT news adapter | extend | `src/due_diligence_agent/adapters/news/gdelt.py` | future startup market/news research service | Reuse as a research/news signal adapter with source dates and coverage limits; not a verified source of record. |
| OpenAI gateway | reuse | `src/due_diligence_agent/adapters/openai/gateway.py` | future startup structured-output services | Use only through policy/service boundaries; no raw secrets in logs/traces. |
| Code Interpreter adapter | reuse | `src/due_diligence_agent/adapters/openai/code_interpreter.py` | future metric exploration service | Exploratory calculations must be locally verified by deterministic engine. |
| Local SQLite DB | reuse | `src/due_diligence_agent/adapters/local_storage/sqlite_db.py` | C `src/due_diligence_agent/adapters/postgres/*` | B persistence only; no tenant guarantees. |
| Local repositories | reuse | `src/due_diligence_agent/adapters/local_storage/repositories.py` | C tenant-aware repositories | Same repository ports, different adapter. |
| Local artifact store | extend | `src/due_diligence_agent/adapters/local_storage/artifact_store.py` | future startup ingest service and C object storage adapter | B stores artifacts locally; C stores objects durably. |
| FAISS retrieval | reuse | `src/due_diligence_agent/adapters/retrieval/faiss_index.py` | future startup retrieval index adapter | Keep behind retrieval port. |
| Local embeddings | reuse | `src/due_diligence_agent/adapters/retrieval/local_embeddings.py`, `src/due_diligence_agent/adapters/retrieval/fixture_embeddings.py` | future startup retrieval profile | Preserve frozen/offline behavior for demo. |
| HTML report renderer | extend | `src/due_diligence_agent/adapters/reports/html_renderer.py`, `src/due_diligence_agent/adapters/reports/templates/public_report.html.j2` | future startup report template | Add startup sections without breaking public report template. |
| PDF report renderer | reuse | `src/due_diligence_agent/adapters/reports/pdf_renderer.py`, `src/due_diligence_agent/adapters/reports/reportlab_renderer.py` | future startup PDF renderer/template | Reuse rendering path; handle runtime gaps explicitly. |
| Chart rendering | extend | `src/due_diligence_agent/adapters/reports/charts.py` | future startup metric charts | Charts consume service/domain outputs, not UI-only formulas. |
| Observability audit spool | extend | `src/due_diligence_agent/adapters/observability/audit_spool.py` | future Admin Console tracing page | B exposes local trace/audit proofs; C adds production storage/export. |
| Observability context | extend | `src/due_diligence_agent/adapters/observability/context.py` | `src/due_diligence_agent/presentation/api/context.py` and future C identity/workspace resolver | Reuse local context propagation; C replaces anonymous context with trusted principal/workspace context. |
| Observability metrics adapter | extend | `src/due_diligence_agent/adapters/observability/metrics.py` | future Admin Console metrics page and C production dashboards | Reuse local metrics surface for B; C adds production-grade exporter/dashboard wiring. |
| OTel adapter | extend | `src/due_diligence_agent/adapters/observability/otel.py` | API middleware and C deployment exporters | Safe scalar attributes only. |
| LangSmith adapter | reuse | `src/due_diligence_agent/adapters/observability/langsmith.py` | future Admin Console integration | Optional tracing adapter; no raw startup content. |
| Observability privacy | reuse | `src/due_diligence_agent/adapters/observability/privacy.py` | API middleware and startup graph nodes | Redaction/safe metadata boundary. |
| Evaluation runner | extend | `src/due_diligence_agent/evals/runner.py`, `src/due_diligence_agent/evals/metrics.py` | future startup gates | Public Gate B remains regression; add Gate C/D/E separately. |
| Frozen public fixture | reuse | `tests/fixtures/public_us_frozen_v1/**` | none | Regression barrier for public comparable path. |
| Architecture guard tests | new adapter | none | `tests/architecture/test_b_to_c_boundaries.py` | Proves no forbidden imports/coupling and protects B-to-C seam. |
| Auth/RBAC | defer to C | none | `src/due_diligence_agent/adapters/identity/*`, `src/due_diligence_agent/application/policies/workspace_access.py` | B includes nullable seams only; no fake auth. |
| Billing/entitlements | defer to C | none | `src/due_diligence_agent/application/policies/entitlements.py` | Not part of B demo. |
| PostgreSQL persistence | defer to C | none | `src/due_diligence_agent/adapters/postgres/*` | B uses SQLite; C adds durable tenant-aware storage. |
| Object storage | defer to C | none | `src/due_diligence_agent/adapters/object_storage/*` | B uses local artifacts; C adds object storage. |
| Durable job queue | defer to C | none | `src/due_diligence_agent/adapters/jobs/*` | B can run locally/synchronously; C adds durable asynchronous execution. |
| Backup/restore | defer to C | none | `src/due_diligence_agent/adapters/backup/*`, `deploy/*` | C acceptance requires tested restore. |
| Production SLO and deployment operations | defer to C | none | `deploy/*`, `infra/*`, production observability dashboards | B documents health/local runner only; C owns uptime, backups, incident and SLO controls. |

## Review rules for future tasks

1. If a task touches `domain`, `application/services`, `application/policies`, or `workflows`, it must prove it did not import presentation/platform dependencies.
2. If a task touches `frontend/founder`, it must prove business status, metrics, evidence sufficiency, and findings come from API/application contracts.
3. If a task touches C-deferred areas, it must either stay at seam-definition level or move the delivery profile from B to C with explicit approval.
4. If a task changes `/api/v1`, it must state whether the change is compatible. Breaking changes require `/api/v2`.
5. If a task adds tracing attributes, it must prove that raw documents, filenames, request bodies, cookies, authorization headers, prompts, and secrets are not emitted.
