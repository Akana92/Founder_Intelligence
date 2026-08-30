# Queue 1 Universal Startup Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development for every behavior change and superpowers:verification-before-completion before each completion claim.

**Goal:** Convert every supported startup upload into a deterministic, persisted, evidence-grounded `StartupProfile v1` that survives process restarts, distinguishes facts/inferences/gaps/contradictions, and becomes the canonical input for downstream report synthesis.

**Architecture:** Keep safe ingestion, document parsing, tabular normalization, startup understanding, and report rendering as separate layers. Add a persisted unified parse-result envelope and a persisted immutable `StartupProfile` aggregate between parsing/evidence and metrics/reporting. Structured extraction may receive only bounded redacted fragments after Gate 2; deterministic local assembly remains available when external access is denied or unavailable. Graph checkpoints contain identifiers, hashes, revisions, and status only.

**Tech Stack:** Python 3.12+, Pydantic v2, FastAPI, LangGraph, SQLite, DuckDB, OpenPyXL, existing OpenAI Responses gateway, pytest, Ruff, strict mypy, PowerShell Gate C runner.

## Global Constraints

- [ ] Do not call live OpenAI during Queue 1 development or regression tests.
- [ ] Preserve current Gate B and canonical Gate C behavior.
- [ ] Preserve bounded recursive ZIP support already implemented; do not weaken archive traversal, quota, compression, macro, or MIME protections.
- [ ] Never put raw uploaded bytes, raw document text, raw local paths, original filenames, API keys, or unrestricted model prompts in LangGraph state, node traces, audit attributes, profile metadata, or report metadata.
- [ ] Keep normalized spreadsheet tables structured; do not flatten them into narrative text.
- [ ] Use the exact profile field status vocabulary: `source_fact`, `inference`, `insufficient_data`, `contradiction`.
- [ ] Produce a local `primary` profile before Gate 2 so upload immediately yields useful analysis; an optional `enriched` profile may be created only after Gate 2 approval. This prepares the primary/deep product split without pretending Queue 1 already contains Queue 2 market research.
- [ ] Keep Queue 1 local to uploaded-material understanding. External competitor discovery, TAM/SAM/SOM research, readiness scoring, adaptive questions, Admin tracing UX, and investor-grade charts stay in later queues.
- [ ] Shared composition roots (`bootstrap/container.py`, startup graph/state, SQLite schema/repositories) have one integrator owner after lane contracts are green.
- [ ] All canonical identifiers and hashes must be derived from sorted normalized input, not wall-clock time or input iteration order.
- [ ] `DueDiligenceCase.data_revision` in the canonical case repository is the sole authoritative data revision. Coordinator/runtime values are projections of it; profile selection, report snapshots, Gate 2 scope, and Gate 4 stale checks must all use that same revision.
- [ ] Graph startup receives document IDs/canonical private filenames only. The data-room adapter resolves those refs under its configured inbox root after containment checks; absolute paths never cross the coordinator-to-graph boundary or enter runtime.
- [ ] Existing user-owned screenshot changes under `artifacts/ui/` are out of scope and must remain untouched.

---

## Task 1: Preserve safe upload metadata and make re-analysis revision-aware

**Files:**

- Modify: `src/due_diligence_agent/presentation/api/routers/startup.py`
- Modify: `src/due_diligence_agent/application/startup_cases.py`
- Modify: `tests/api/test_startup_api.py`
- Modify: `tests/unit/application/test_startup_case_coordinator.py`

### Contract

- [ ] FastAPI passes `UploadFile.filename`, declared MIME type, and bytes to the coordinator.
- [ ] The coordinator derives an allowlisted canonical suffix from the basename only: `.pdf`, `.docx`, `.png`, `.jpg`, `.jpeg`, `.csv`, `.xlsx`, `.zip`; all other suffixes become `.bin`.
- [ ] Private files use deterministic names such as `doc-0001.pdf`; user-supplied path components never become filesystem paths.
- [ ] Runtime document metadata stores `document_id`, canonical private filename, declared MIME type, byte size, and SHA-256 source-name/content references. It does not store the raw original filename or an absolute private path.
- [ ] Public upload responses expose only accepted document IDs and workflow status.
- [ ] First upload uses `data_revision=1`; a later accepted artifact increments the revision, clears stale Gate 2-4/report/profile tuples, and starts a new analysis thread `case_id:rN`.
- [ ] Gate resume operations use the stored active analysis thread instead of assuming `thread_id == case_id`.
- [ ] Duplicate content in the same case is idempotently skipped and does not increment the revision.
- [ ] The coordinator sends only `source_document_ids`/canonical source refs and requested `data_revision` to the analysis service; the internal data-room resolver added in Task 6 converts them to contained paths.

### TDD steps

- [ ] Add RED API tests proving the filename reaches private metadata but never the JSON response.
- [ ] Add RED coordinator tests for traversal-style filenames, unsupported suffix fallback, duplicate-content idempotency, revision increment, stale tuple invalidation, revision-specific thread IDs, and absence of inbox-root/absolute-path/raw-filename strings in runtime and analysis payloads.
- [ ] Run RED:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest tests/api/test_startup_api.py tests/unit/application/test_startup_case_coordinator.py -q -p no:cacheprovider
```

- [ ] Implement the minimum helpers and coordinator behavior.
- [ ] Re-run the same command GREEN.
- [ ] Run Ruff and strict mypy on the four owned files.
- [ ] Self-review: verify no raw filename/path appears in response models, resume tokens, trace-safe previews, or new runtime metadata.

---

## Task 2: Add a persisted unified startup parse-result contract

**Files:**

- Create: `src/due_diligence_agent/domain/documents/startup.py`
- Modify: `src/due_diligence_agent/domain/documents/__init__.py`
- Modify: `src/due_diligence_agent/application/services/startup_parsing_service.py`
- Create: `src/due_diligence_agent/ports/parsed_artifacts.py`
- Create: `tests/parsing/test_startup_parsing_service.py`

### Contract

- [ ] Add immutable `ParsedStartupArtifact` with:
  - `artifact_id`;
  - `kind`: `document`, `spreadsheet`, or `unsupported`;
  - unified `status`: `parsed`, `partial`, `parser_unavailable`, `damaged`, `unsupported`, `rejected`, or `quota_exceeded`;
  - parser name/version, detected MIME, safe error code;
  - exactly one optional payload: `ParsedDocument` or `SpreadsheetParseResult`.
- [ ] Model validation rejects mismatched kind/payload combinations.
- [ ] `StartupParsingService` detects content first, then selects PDF, DOCX, PNG/JPEG OCR, CSV, or XLSX.
- [ ] CSV/XLSX use the existing `SpreadsheetParser` and `TableNormalizationService`; macro-enabled workbooks remain rejected.
- [ ] Damaged/unsupported inputs produce typed outcomes instead of exceptions or invented values.
- [ ] The result representation hides nested raw text/cell values; serialization is repository-only and never placed in graph state or traces.

### TDD steps

- [ ] Add RED model tests for invalid discriminators and payload combinations.
- [ ] Add RED parametrized service tests for PDF, DOCX, PNG, JPEG, CSV, XLSX, damaged OOXML, and unsupported bytes using injected parsers/normalizer where binaries are optional.
- [ ] Add RED assertions that artifact identity and typed status are preserved and raw bytes are absent from `repr()`.
- [ ] Run RED:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest tests/parsing/test_startup_parsing_service.py -q -p no:cacheprovider
```

- [ ] Implement the wrapper and parser selection.
- [ ] Re-run the focused suite GREEN.
- [ ] Run existing parser/spreadsheet regressions:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest tests/parsing/test_document_parsers.py tests/parsing/test_spreadsheets.py -q -p no:cacheprovider
```

- [ ] Run Ruff and strict mypy on owned source/tests.

---

## Task 3: Freeze the canonical `StartupProfile v1` domain and persistence contracts

**Files:**

- Create: `src/due_diligence_agent/domain/startup/__init__.py`
- Create: `src/due_diligence_agent/domain/startup/profile.py`
- Create: `src/due_diligence_agent/ports/startup_profiles.py`
- Create: `tests/unit/domain/test_startup_profile.py`

### Domain contract

- [ ] Add `StartupProfileFieldName` values:
  - `startup_name`, `one_line_description`, `problem`, `solution`, `icp`, `users`, `buyers`, `geography`, `stage`, `business_model`, `pricing_revenue_model`, `traction`, `channels_gtm`, `competitors_mentioned`, `assumptions`, `strengths`, `weaknesses`, `metric_pack_candidates`.
- [ ] Add `StartupProfileFieldStatus`: `source_fact`, `inference`, `insufficient_data`, `contradiction`.
- [ ] Add safe `StartupProfileEvidenceRef` containing evidence/fragment/artifact IDs, artifact hash, deterministic locator hash, page/cell coordinates where safe, confidence, and no raw locator value/path.
- [ ] Add immutable `StartupProfileField` with bounded normalized values, status, confidence, evidence refs, safe reason code, and contradiction IDs.
- [ ] Enforce invariants:
  - `source_fact` requires at least one evidence ref;
  - `inference` requires dependency refs and a safe reason code;
  - `insufficient_data` has no invented values;
  - `contradiction` retains competing refs or contradiction IDs and never silently selects one fact.
- [ ] Add immutable `StartupProfile` with deterministic ID/hash, case ID, schema/profile/extractor versions, `analysis_stage` (`primary` or `enriched`), optional parent profile ID, data revision, source hashes, parse outcome inventory, all required fields, gap codes, contradiction IDs, and deterministic `built_at` derived from the case revision timestamp.
- [ ] Canonical hash preimage excludes self-referential ID/hash fields and sorts maps, fields, values, refs, and source hashes.

### TDD steps

- [ ] Write model-invariant RED tests first.
- [ ] Run RED:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest tests/unit/domain/test_startup_profile.py -q -p no:cacheprovider
```

- [ ] Implement domain models and canonical hashing helpers only; the service and its acceptance tests come in Task 5.
- [ ] Re-run domain tests GREEN.
- [ ] Run Ruff and strict mypy on owned files.

---

## Task 4: Persist parse results and profiles with idempotent append-only semantics

**Files:**

- Modify: `src/due_diligence_agent/adapters/local_storage/sqlite_db.py`
- Modify: `src/due_diligence_agent/adapters/local_storage/repositories.py`
- Modify: `src/due_diligence_agent/ports/repositories.py`
- Modify: `tests/integration/storage/test_local_repositories.py`

### Contract

- [ ] Add `startup_parse_results` table keyed by artifact ID with case ID, status sort key, and canonical JSON payload.
- [ ] Add `startup_profiles` table keyed by profile ID with case ID, data revision, `analysis_stage`, profile hash, deterministic created/built timestamp, and canonical JSON payload; index `(case_id, data_revision, analysis_stage, id)`.
- [ ] Add `LocalParsedStartupArtifactRepository.add/get/list_for_case`.
- [ ] Add `LocalStartupProfileRepository.add/get/list_for_case/get_for_stage/get_current`.
- [ ] Re-adding byte-identical canonical payload is a no-op; same ID with different payload raises a typed conflict.
- [ ] Foreign keys enforce case/artifact lineage.
- [ ] Repository round-trip preserves Decimal, UUID, enums, tuples, locators, and nested parse/profile structures.
- [ ] `get_for_stage(case_id, data_revision, stage)` returns that exact immutable stage.
- [ ] `get_current(case_id)` selects the authoritative case repository revision, then returns `enriched` when present, otherwise `primary`; deterministic ID is only a final tie breaker and may not decide stage precedence.

### TDD steps

- [ ] Add RED round-trip, ordering, idempotency, conflict, referential-integrity, and reopened-database tests.
- [ ] Run RED selector:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest tests/integration/storage/test_local_repositories.py -k "startup_parse_result or startup_profile" -q -p no:cacheprovider
```

- [ ] Implement schema/repositories/protocols.
- [ ] Re-run the selector GREEN, then the full repository module GREEN.
- [ ] Run Ruff and project strict mypy.

---

## Task 5: Build bounded redacted profile extraction and deterministic assembly

**Files:**

- Create: `src/due_diligence_agent/application/services/startup_profile_service.py`
- Create: `src/due_diligence_agent/ports/startup_profile_extraction.py`
- Create: `src/due_diligence_agent/adapters/startup/deterministic_profile_extractor.py`
- Create: `src/due_diligence_agent/adapters/startup/__init__.py`
- Create: `src/due_diligence_agent/adapters/openai/startup_profile_extractor.py`
- Create: `tests/unit/application/test_startup_profile_builder.py`
- Create: `tests/unit/llm/test_startup_profile_extraction.py`
- Modify: `tests/unit/llm/test_startup_openai_provider.py`
- Create: `tests/unit/llm/test_startup_openai_profile_extractor.py`

### Extraction contract

- [ ] `StartupProfileExtractionRequest` carries only bounded redacted fragment text plus safe fragment/evidence/artifact/hash/locator refs and spreadsheet evidence facts.
- [ ] Enforce per-fragment, total-character, fragment-count, and output-item limits before adapter calls.
- [ ] Strict extraction response contains field name, normalized values, status, confidence, fragment/evidence refs, and safe reason code; extra keys are rejected.
- [ ] Unknown refs, oversized output, unsafe status transitions, or invalid model output produce a controlled partial profile and gap code.
- [ ] Gate 2 denied/unavailable provider makes zero external calls and uses the deterministic local extractor.
- [ ] Gate 2 approved may call the existing budgeted OpenAI gateway exactly once for profile extraction; retry/repair remains bounded by the gateway policy.
- [ ] `OpenAIStartupProfileExtractor` implements `StartupProfileExtractionPort` as a separate adapter. Do not overload or change the meaning of `OpenAIStartupProvider.analyze()`, which remains the finding-analysis boundary.
- [ ] No prompt/response body is added to audit or trace attributes.

### Assembly contract

- [ ] `StartupProfileService.build_primary(case_id)` loads persisted case, artifacts, parse results, evidence, claims, contradictions, and local redacted fragment refs; it never calls an external provider.
- [ ] `StartupProfileService.enrich(case_id, primary_profile_id, disclosure_scope)` optionally calls the bounded external extractor and creates an immutable child profile; denied/unavailable external access returns the existing primary profile without a provider call.
- [ ] It merges candidates deterministically, dedupes by normalized value plus evidence identity, preserves all material conflicts, and emits explicit gaps.
- [ ] Spreadsheet numeric facts populate traction/metric candidates without inventing narrative fields.
- [ ] A spreadsheet-only case may be partial but must still produce a valid profile.
- [ ] Same frozen inputs yield the same primary and enriched profile IDs/hashes across process restarts.
- [ ] Profile persistence is idempotent.

### TDD steps

- [ ] Write the builder suite RED for normal, sparse, spreadsheet-heavy, contradiction, multilingual, order-independent, changed source/revision, and invalid-extractor cases.
- [ ] Add RED privacy tests with path/email/token sentinels proving only redacted bounded fragments reach the fake external adapter and nothing unsafe reaches profile JSON.
- [ ] Add RED zero-call test for denied Gate 2 and one-call test for approved Gate 2.
- [ ] Run RED/GREEN:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest tests/unit/application/test_startup_profile_builder.py tests/unit/llm/test_startup_profile_extraction.py tests/unit/llm/test_startup_openai_profile_extractor.py tests/unit/llm/test_startup_openai_provider.py -q -p no:cacheprovider
```

- [ ] Run Ruff and strict mypy on all changed files.

---

## Task 6: Integrate persisted parsing and profile assembly into the startup graph

**Files:**

- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Modify: `src/due_diligence_agent/workflows/startup/graph.py`
- Modify: `src/due_diligence_agent/workflows/startup/state.py`
- Modify: `src/due_diligence_agent/workflows/startup/nodes/ingest.py`
- Modify: `src/due_diligence_agent/workflows/startup/nodes/parse.py`
- Modify: `src/due_diligence_agent/workflows/startup/nodes/evidence.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/profile.py`
- Modify: `src/due_diligence_agent/workflows/startup/nodes/report.py`
- Modify: `tests/graph/test_startup_workflow.py`
- Create: `tests/integration/test_startup_ingest_parse_pipeline.py`

### Contract

- [ ] Add safe checkpoint keys `data_revision`, `primary_profile_id`, `profile_id`, `profile_hash`, and `profile_revision`.
- [ ] Graph path becomes `ingest -> parse -> classify_redact -> evidence -> claims -> primary_profile -> disclosure -> plan -> profile_enrichment -> metrics -> ... -> report`.
- [ ] Parse node persists `ParsedStartupArtifact`; checkpoint keeps artifact IDs only.
- [ ] Add a contained source resolver to `_StartupDataRoomWorkflowPort`: resolve canonical private filenames under configured `inbox_root/case_id`, reject missing/traversal/absolute refs, and pass resolved paths directly to `DataRoomService` without saving them in workflow runtime.
- [ ] Accepted first upload creates the canonical case at revision 1. Each later accepted non-duplicate upload atomically advances `DueDiligenceCase.data_revision` with optimistic concurrency; this same repository value drives profile `get_current`, disclosure snapshots, report snapshots, and Gate 4 stale checks.
- [ ] Evidence adapter reloads parse results from the repository after restart and adds spreadsheet-generated `EvidenceFact`s idempotently.
- [ ] Primary-profile node loads only persisted normalized inputs/local redacted refs and returns a useful profile before the Gate 2 interrupt.
- [ ] Enrichment node loads the persisted primary profile plus approved disclosure scope; denial/unavailability preserves the primary profile and makes zero external calls.
- [ ] Report node consumes the current canonical profile reference; it never re-parses raw documents.
- [ ] Safe mixed ZIP containing PDF/DOCX/CSV/XLSX/PNG/JPEG expands into member artifacts and every accepted member reaches the correct parser.
- [ ] Archive ingestion remains atomic per uploaded archive: an unsafe or damaged ZIP is quarantined without publishing partial member artifacts. Independently uploaded safe sibling files continue through ingestion and appear beside the typed quarantine outcome in the visible inventory.
- [ ] Restart after parse and restart after Gate 2 yield the same profile hash.
- [ ] A new authoritative case data revision builds a new profile and invalidates stale runtime/current pointers, report snapshot approval, and Gate 4 state without deleting append-only historical rows.
- [ ] Archive safety semantics are frozen at source-transaction granularity: no implementation may partially publish members from a rejected archive.

### TDD steps

- [ ] Add RED mixed-source pipeline tests using in-memory generated fixtures and the existing archive inspector safety limits: a fully safe ZIP expands transactionally, while an unsafe ZIP is quarantined atomically and does not block separately uploaded safe files.
- [ ] Add RED graph tests for primary profile availability at the Gate 2 interrupt, enrichment ordering, IDs-only checkpoint state, restart equivalence, denied Gate 2 zero external calls, partial parse outcome, authoritative second-revision recomputation, and source-ref containment.
- [ ] Add a privacy regression that scans `workflow_store.load(case_id)`, checkpoint bytes, trace/audit serialization, profile JSON, and report JSON after auto-start and resume; absolute inbox paths and raw original filenames must be absent.
- [ ] Run RED:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest tests/integration/test_startup_ingest_parse_pipeline.py tests/graph/test_startup_workflow.py -k "profile or mixed_archive or second_revision or restart" -q -p no:cacheprovider
```

- [ ] Integrate repositories/services/dependencies in one owner-controlled pass.
- [ ] Run the focused selector GREEN, then full startup workflow, disclosure, archive, parsing, spreadsheet, privacy, and repository suites.
- [ ] Run Ruff and strict mypy for the project.

---

## Task 7: Expose the canonical profile and bind it to startup report synthesis

**Files:**

- Modify: `src/due_diligence_agent/application/startup_cases.py`
- Modify: `src/due_diligence_agent/presentation/api/routers/startup.py`
- Modify: `src/due_diligence_agent/presentation/api/dependencies.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Modify: `src/due_diligence_agent/application/services/startup_report_service.py`
- Modify: `src/due_diligence_agent/workflows/startup/ports.py`
- Modify: `tests/api/test_startup_api.py`
- Modify: `tests/unit/reporting/test_startup_report_snapshot.py`
- Modify: `tests/e2e/test_startup_report.py`

### Contract

- [ ] Add `GET /api/v1/startup/cases/{case_id}/profile` with a strict response model.
- [ ] Response contains analysis stage and parent ID plus canonical fields, statuses, confidence, safe evidence refs, gaps, contradictions, parse inventory, profile hash, and data revision.
- [ ] Response contains no private paths, raw filenames, raw document excerpts, prompt text, or secrets.
- [ ] `StartupReportInput` accepts the persisted current profile.
- [ ] Problem/solution, competitors-mentioned, strengths/weaknesses, assumptions, and evidence-gaps sections derive from profile fields when present and retain `MISSING` semantics when insufficient.
- [ ] Report snapshot identity changes when the canonical profile hash changes.
- [ ] Existing public-company report behavior remains unchanged.

### TDD steps

- [ ] Add RED API happy/not-ready/stale/privacy tests.
- [ ] Add RED report tests proving profile-backed sections and hash identity.
- [ ] Run RED/GREEN:

```powershell
uv run --offline --no-sync --no-default-groups --group stage1b --group founder-api --group dev pytest tests/api/test_startup_api.py tests/unit/reporting/test_startup_report_snapshot.py tests/e2e/test_startup_report.py -q -p no:cacheprovider
```

- [ ] Run public report regression and full frontend contract tests; the current status response remains backward compatible, while the new profile endpoint is additive.
- [ ] Run Ruff, strict mypy, frontend tests, typecheck, lint, and build.

---

## Task 8: Add Queue 1 frozen fixtures and extend canonical offline evidence

**Files:**

- Create: `tests/fixtures/startup_profile_v1/manifest.json`
- Create: `tests/fixtures/startup_profile_v1/documents/` synthetic fixture files
- Create: `tests/fixtures/startup_profile_v1/expected_profile.json`
- Create: `tests/evaluation/test_queue1_startup_profile.py`
- Modify: `src/due_diligence_agent/evals/gate_c.py`
- Modify: `tests/evaluation/test_startup_gate_c.py`
- Modify: `src/due_diligence_agent/application/product/capabilities.py`
- Modify: `tests/unit/application/product/test_capabilities.py`
- Modify: `docs/superpowers/plans/2026-08-13-capstone-completion-staircase.md`
- Create: `docs/verification/2026-08-13-queue1-verification.md`

### Fixture matrix

- [ ] Normal mixed startup pitch with problem, solution, ICP, pricing, traction, and named competitors.
- [ ] Spreadsheet-heavy case with numeric evidence but missing narrative fields.
- [ ] Contradictory ARR case preserving both sources.
- [ ] Safe mixed ZIP case.
- [ ] Damaged/unsupported sibling case producing partial output.
- [ ] Privacy sentinel case proving no path/email/token leakage.

### Gate contract

- [ ] Queue 1 evaluation runs with both OpenAI keys blank, tracing exporters disabled, Hugging Face/Transformers offline, and bounded repo-local temp/output roots.
- [ ] Machine-readable output records profile determinism, required field/status coverage, contradiction retention, parse-format coverage, restart equivalence, privacy leak count, and denied-Gate-2 external call count.
- [ ] `universal_upload` capability becomes `available` only after the active startup flow supports the full format matrix; profile capability reports honest partial/live-provider boundaries.

### Verification steps

- [ ] Run the Queue 1 evaluator twice and compare canonical profile hashes.
- [ ] Run canonical Gate C with a new unique output directory.
- [ ] Run all backend tests in ACL-safe batches, Ruff, and strict mypy.
- [ ] Run founder/admin frontend tests, typecheck, lint, and production builds.
- [ ] Scan generated JSON/HTML/PDF/audit/checkpoint/profile artifacts for sentinel secrets and absolute private paths.
- [ ] Record exact commands, pass counts, hashes, warnings, and known non-blockers in the Queue 1 verification report.
- [ ] Request an independent architecture/code review and resolve all MUST findings before marking Queue 1 complete.

---

## Final Queue 1 Acceptance

- [ ] PDF, DOCX, PNG, JPEG, CSV, XLSX, and safe ZIP members all traverse the active startup flow.
- [ ] Same frozen input and revision produce the same persisted profile ID/hash after restart.
- [ ] Every required field is a grounded fact, bounded inference, explicit insufficiency, or first-class contradiction.
- [ ] No unsupported or damaged input causes fabricated profile values.
- [ ] Denied Gate 2 produces zero external calls and still yields a deterministic local profile.
- [ ] The deterministic primary profile is already queryable while Gate 2 is pending; later enriched/deep stages never overwrite it in place.
- [ ] Approved Gate 2 can use the bounded structured OpenAI extractor under the existing budget/timeout/audit controls.
- [ ] New accepted artifacts increment data revision and invalidate/recompute profile-dependent outputs.
- [ ] Profile API and startup report consume the same canonical persisted profile.
- [ ] Raw content, paths, filenames, secrets, prompts, and unrestricted model output are absent from graph state, traces, audit attributes, profile/report metadata, and public responses.
- [ ] Canonical Gate B and Gate C remain green with no paid API calls.

## Commit Strategy

- [ ] Commit 1: upload metadata and revision semantics.
- [ ] Commit 2: unified parse contract and active spreadsheet routing.
- [ ] Commit 3: profile domain and persistence contracts.
- [ ] Commit 4: bounded extraction and profile assembly.
- [ ] Commit 5: graph/restart integration.
- [ ] Commit 6: API/report binding.
- [ ] Commit 7: Queue 1 fixtures, evaluator, capabilities, and verification report.
