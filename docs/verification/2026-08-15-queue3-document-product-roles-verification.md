# Queue 3 Document Intelligence/Product Validation verification — 2026-08-15

## Scope and result

- Production commit: `71d95b6d4f97a9beb52974ed58afd5bbd2669610` (`feat(queue3): add document intelligence and product validation startup role nodes`).
- Result: the Queue 3 backend role boundary for Document Intelligence and Product Validation passes its deterministic/offline graph gate.
- This commit closes only the two backend role surfaces. The then-remaining GTM and API/query-contract work was subsequently completed and is recorded in [Queue 3 GTM/API freeze verification](2026-08-15-queue3-gtm-api-freeze-verification.md). Founder Product Validation/GTM UI and expanded report projection remain Queue 4 work; Queue 5 and the Sellable Demo Gate remain open.
- No paid OpenAI, LangSmith, Yahoo Finance, GDELT, news, or web-provider calls were made.

## Production boundary

- `StartupDocumentIntelligenceService` produces a deterministic, bounded, reference-only snapshot from inventory, parsed-artifact, evidence, claim, and quarantine references. It records coverage/gap codes without raw paths, filenames, document content, or content hashes.
- `StartupProductValidationService` evaluates exactly eight product-validation dimensions: problem clarity, ICP precision, pain intensity, urgency, willingness to pay, existing customer behavior, adoption risk, and validation evidence.
- Product Validation emits evidence-backed statuses, reason/gap codes, and allowlisted lineage IDs instead of invented numeric scores.
- Both roles are explicit Plan-and-Execute nodes with state IDs/hashes/revisions, production dependency injection, audit/trace events, checkpoint persistence, and idempotent restart behavior.
- Gate 3 evidence exclusion invalidates and rebuilds Product Validation, retains bounded snapshot history, removes excluded evidence, and never reintroduces an excluded contradiction ID from a stale profile field.
- Document Intelligence remains immutable ingestion/parse/extraction history and is not recomputed when a founder later excludes analysis evidence.

## TDD evidence

Initial RED:

```text
tests/graph/test_startup_workflow.py -k "explicit_document or role_outputs or roles_emit or routes_only_affected or plan_registry or default_startup_plan"
6 failed, 51 deselected

tests/unit/application/test_startup_role_services.py
collection error: startup role service module did not exist
```

Gate 3 lineage RED discovered by review:

```text
test_product_validation_does_not_reintroduce_excluded_contradiction_ids
1 failed: excluded contradiction ID was emitted when two allowed evidence refs remained
```

Minimal GREEN:

```text
tests/unit/application/test_startup_role_services.py  -> 5 passed
tests/graph/test_startup_workflow.py                  -> 58 passed
combined focused role suite                          -> 63 passed
```

The regression keeps the dimension status `contradicted` when current allowed evidence still supports that state, while emitted `contradiction_ids` are restricted to the active allowlist.

## Restart, privacy, and lineage evidence

- Role outputs survive checkpoint restart without reprocessing.
- Real deterministic composer tests persist both role artifacts and preserve reference-only payloads.
- Gate 3 rebuild produces a new Product Validation snapshot, keeps a two-entry history for the exercised case, and excludes the rejected fact from every dimension.
- Audit and trace rows include bounded node/checkpoint/tool metadata and exclude raw source text and filenames.
- Independent review initially requested the stale contradiction-lineage fix, then approved the focused correction with no remaining issue.

## Full regression evidence

```text
backend pytest       -> 1120 passed, 1 Windows symlink skip
Ruff src/tests       -> PASS
mypy --strict src    -> PASS, 216 source files
frontend tests       -> 54 passed
frontend typecheck   -> PASS
frontend lint        -> PASS
frontend build       -> PASS
```

The Windows skip is the existing privilege-dependent symlink test. The first sandboxed full-test/build attempts were invalidated by local temp ACL and process-spawn restrictions; identical offline commands passed outside the sandbox using project-local temp storage. No inaccessible pre-existing temp directory was removed or modified.

## Real local API/browser smoke

The deterministic Founder workspace smoke ran the real local API and Next.js processes, uploaded the frozen CSV, completed Gates 2–4, fetched JSON/PDF report artifacts, and rendered desktop and mobile views through headless Edge.

```text
offline_network_snapshot_clean
offline_network_snapshot_clean
viewport_geometry label=desktop inner=1440 scroll=1425 body=1425
viewport_geometry label=mobile inner=390 scroll=375 body=375
offline_network_snapshot_clean
startup_founder_workspace_smoke_passed
```

Generated screenshot/build artifacts were restored to the production commit and were not included in the verification documentation commit.

## Subsequent Queue 3 closure

- deterministic GTM domain/service was added in `0b315a2`, and graph execution/restart/Gate 3 invalidation in `43052ba`;
- the founder-safe API/query/report-lineage freeze was completed in `54230a8`, `dbf8a98`, and `4f72d0b`;
- Queue 4 deep-analysis UX/report work is now unblocked, while Queue 5 remains open.
