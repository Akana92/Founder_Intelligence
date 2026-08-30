# Founder Dynamic Analysis Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Founder Intelligence visibly and technically depend on the uploaded startup document and same-case advisor answers instead of static placeholder UI.

**Architecture:** Keep the existing offline deterministic architecture. Fix the pipeline at the source: profile extraction creates source-backed startup facts, confidence/readiness measure completeness, advisor questions are selected from actual profile gaps, answers are semantically validated and bound to the active question field, and the frontend renders real profile/report/advisor state with honest gaps.

**Tech Stack:** Python 3.13, Pydantic domain models, pytest, FastAPI startup API, Next.js/React Founder frontend, Node test/typecheck/lint/build.

**Spec:** `docs/superpowers/plans/2026-08-20-founder-intelligence-post-visual-functional-handoff.md`

**Canonical acceptance fixture:** `output/pdf/nomadflow_ai_startup_test_business_plan_ru.pdf` (15 pages). End-to-end claims in this plan must be proven against this exact file, not only against the older FlowPilot fixture.

## Execution Status — 2026-08-21

- [x] Baseline restored from the canonical handoff, screenshots, source mockups, current WIP, and the NomadFlow PDF.
- [x] Existing narrow backend baseline verified: 42 targeted extractor/advisor tests pass with an isolated pytest temp directory.
- [x] Frontend question origin, progress, impact, semantic feedback, recalculation delta, and stale-lineage guards are API-bound and independently reviewed.
- [x] NomadFlow extraction, contradiction preservation, advisor ranking, recalculation deltas, two-fixture differentiation, and 14-state browser acceptance are verified.
- [x] Post-acceptance hardening is complete: decimal confidence/profile coverage, source-backed financial metric projection, founder-answer reconciliation, and non-placeholder browser evidence passed the fresh live NomadFlow run plus independent review and verification.

## Global Constraints

- Preserve the existing WIP; do not run `git reset`, `git checkout`, `git clean`, broad delete, or blind restore.
- Work on current `main`; the checkpoint explicitly says not to create a new branch or worktree.
- Do not add external web calls, new dependencies, or new demo-only frontend state.
- Do not display fabricated startup names, MRR/ARR, percentages, risks, competitors, sources, or success statuses.
- Do not show raw document text, filenames, paths, hashes, prompts, secrets, PII, or internal reason codes in Founder UI.
- Every production behavior change needs a RED test first and a GREEN verification run.
- Completion requires one same-case path: upload/process the NomadFlow PDF -> document-understood summary -> profile -> overview/metrics -> contradiction-aware advisor question -> answer validation/recalculation -> updated profile/metrics/report state.
- A second, materially different startup fixture must produce different visible values and a different highest-value question; this prevents a hidden one-document demo path.

---

## File Structure

- `src/due_diligence_agent/adapters/startup/deterministic_profile_extractor.py`: deterministic Russian/English profile fact extraction with bounded evidence refs.
- `src/due_diligence_agent/adapters/startup/profile_fragment_inventory.py`: deterministic relevance-aware fragment selection so the extractor receives the important blocks of a long PDF.
- `src/due_diligence_agent/adapters/documents/pdf_parser.py`: table text blocks with safe page/table provenance for PDF evidence.
- `src/due_diligence_agent/bootstrap/container.py`: producer-order, first-seen-deduplicated parser blocks instead of content-hash order.
- `src/due_diligence_agent/ports/startup_profile_extraction.py`: bounded fragment provenance contract, including founder-safe page/table/cell coordinates.
- `src/due_diligence_agent/application/services/startup_profile_service.py`: validation that preserves the relevance order selected by the inventory.
- `src/due_diligence_agent/application/services/explicit_contradiction_signal_service.py`: explicit numeric contradiction rows from the document become domain contradictions.
- `src/due_diligence_agent/application/services/startup_advisor_service.py`: gap-driven question selection and domain-level answer acceptance rules.
- `src/due_diligence_agent/application/services/startup_advisor_api_service.py`: API validation, answer-to-profile binding, recalculation/report invalidation handoff.
- `src/due_diligence_agent/application/startup_advisor_recalculation.py`: same-case data revision and recalculation payload.
- `frontend/founder/components/founder-analysis-pages.tsx`: honest profile summary, progress, confidence, dashboard gaps, and AI suggestions.
- `frontend/founder/components/founder-advisor-pages.tsx`: advisor question/answer copy and validation feedback presentation.
- `frontend/founder/lib/advisor-presentation.ts`: dynamic impact labels derived from API state, not fixed strips.
- `frontend/founder/lib/readiness-presentation.ts`: readiness and evidence presentation based on actual profile/report state.
- `src/due_diligence_agent/application/services/claim_extraction_service.py`: line-scoped bilingual financial observations, decimal-comma support, and current-versus-target filtering.
- `src/due_diligence_agent/application/services/startup_report_service.py`: safe direct-metric status/confidence markers without founder-visible lineage.
- `src/due_diligence_agent/application/services/founder_report_presentation_service.py`: unique observation selection and explicit `confirmed` / `calculated` / `estimated` / `contradiction` statuses.
- `frontend/founder/lib/chart-presentation.ts`: metric aliases and provenance-aware cards for the Founder metrics screen.
- `scripts/capture_founder_screenshots.mjs`: same-case public-state evidence counts for the 14-screen browser run.
- Tests: `tests/unit/llm/test_startup_profile_extraction.py`, `tests/unit/application/test_startup_advisor_service.py`, `tests/unit/application/test_startup_advisor_api_service.py`, `tests/api/test_startup_api.py`, `frontend/founder/components/founder-analysis-pages.test.ts`, `frontend/founder/components/founder-advisor-pages.test.ts`, `frontend/founder/lib/advisor-presentation.test.ts`.

## Task 1: Roadmap And Baseline Reproduction

**Files:**
- Create: `docs/superpowers/plans/2026-08-21-founder-dynamic-analysis-fixes.md`
- Read-only evidence: user screenshots and `output/pdf/nomadflow_ai_startup_test_business_plan_ru.pdf`

**Interfaces:**
- Consumes: existing Founder API and parser outputs.
- Produces: exact regression list and acceptance targets for Tasks 2-6.

- [x] **Step 1: Confirm active failure from the user's real case**

Run targeted API/UI checks against the current startup case and record:
- profile fields remain fallback for product/client/problem/monetization/stage;
- confidence shows 70% despite insufficient core fields;
- dashboard readiness/evidence stay 0/generic;
- advisor asks a fixed revenue/pricing question even when another gap is more important;
- manual answer `60%` is accepted for revenue/pricing.

- [x] **Step 2: Mark the plan as the execution source**

Update `Docs/superpowers/plans/` only; do not touch old handoff files except if final verification docs require a new status note.

## Task 2: RED Tests For Document-Backed Profile Extraction

**Files:**
- Modify: `tests/unit/llm/test_startup_profile_extraction.py`
- Modify: `src/due_diligence_agent/adapters/startup/deterministic_profile_extractor.py`

**Interfaces:**
- Consumes: `StartupProfileExtractionRequest`.
- Produces: `StartupProfileExtractionResponse.fields` where `startup_name`, `one_line_description`, `problem`, `icp`, `pricing_revenue_model`, `stage`, `traction`, and `metric_pack_candidates` are populated only when supported by bounded fragments.

- [x] **Step 1: Write RED test**

Add a test with bounded Russian free-form/table fragments from the canonical NomadFlow startup document. Assert literal expected values, not helper-derived values:
- startup name is not a fallback;
- product/description states the cloud inventory, procurement, and routing platform;
- problem, ICP, Kazakhstan geography, Seed stage, business model, pricing, and GTM are source facts;
- Starter `240 000 ₸`, Growth `690 000 ₸`, and Enterprise `1 900 000 ₸` remain attributable to the document;
- contradictory MRR (`28.6m ₸` vs `27.9m ₸`), customer count (`31` vs `29`), margin (`74%` vs `70%`), and CAC payback (`4.3` vs `5.5` months) are preserved as conflicts instead of flattened into one answer;
- page/table/cell evidence refs survive extraction.

- [x] **Step 2: Run RED**

Run: `py -3.13 -B -m pytest tests/unit/llm/test_startup_profile_extraction.py -k "russian or deterministic" -q`

Expected: FAIL because current deterministic extractor misses Russian narrative fields or produces noisy metric values.

- [x] **Step 3: Implement minimal extraction**

Add deterministic Russian/English section/label extraction in the existing extractor. Keep extraction conservative:
- one evidence ref per extracted fact;
- no invented values;
- if a field is absent, leave `INSUFFICIENT_DATA`;
- metric extraction must keep `MRR`, `ARR`, `gross_margin`, `runway`, `burn`, `CAC`, and similar values as separate normalized facts;
- a contradiction remains a founder-visible verification gap until a later source or answer resolves it.

- [x] **Step 4: Run GREEN**

Run the same pytest command and confirm PASS.

## Task 2B: RED Tests For Long-PDF Fragment Selection And Provenance

**Files:**
- Modify: `tests/integration/test_startup_parsing_composition.py`
- Modify: `src/due_diligence_agent/adapters/startup/profile_fragment_inventory.py`
- Modify: `src/due_diligence_agent/ports/startup_profile_extraction.py`
- Modify: `src/due_diligence_agent/application/services/startup_profile_service.py`
- Modify only for provenance propagation: `src/due_diligence_agent/adapters/startup/deterministic_profile_extractor.py`

**Observed root cause:** the canonical PDF produces 243 unique text blocks. The current inventory sorts them by content hash and picks 24 evenly-spaced blocks; the selected set omits the startup name, product summary, pricing values, and most contradictory metrics. An improved extractor cannot recover facts it never receives.

- [x] **Step 1: Write producer-shaped RED tests**

Build more than 24 safe fragments containing both ordinary narrative and high-value profile/metric/conflict blocks. Assert the bounded inventory keeps deterministic coverage while selecting the startup name, product, pricing, MRR conflict, customer conflict, margin conflict, and CAC-payback conflict.

- [x] **Step 2: Implement deterministic relevance-aware selection**

Rank bounded redacted fragments by explicit profile labels, business-section headings, metric names, contradiction markers, and quantitative context. Reserve part of the 24-fragment budget for deterministic document-wide coverage. Do not add an LLM, a new dependency, or unbounded/raw content.

Preserve the inventory's deterministic relevance order when validating and building the extraction request; do not sort the selected fragments again by UUID.

- [x] **Step 3: Preserve safe provenance**

Carry optional page/table/cell coordinates from the validated parser locator into `StartupProfileBoundedFragment` and then into `StartupProfileSafeRef`. Do not expose raw filenames, local paths, bounding boxes, or document text in Founder responses.

- [x] **Step 4: Run GREEN and a real NomadFlow inventory diagnostic**

The integration suite must pass, and the real 15-page PDF inventory must demonstrably contain all acceptance signals needed by Task 2 without exceeding 24 fragments / 12,000 characters.

## Task 2C: RED Tests For PDF Table Visibility And Domain Contradictions

**Files:**
- Modify: `tests/parsing/test_document_parsers.py`
- Modify: `tests/unit/evidence/test_explicit_contradiction_signal_service.py`
- Modify: `tests/integration/test_startup_parsing_composition.py`
- Modify: `src/due_diligence_agent/adapters/documents/pdf_parser.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Modify: `src/due_diligence_agent/application/services/explicit_contradiction_signal_service.py`

**Observed root cause:** PDF tables are stored as `ParsedTable` objects whose `text_blocks` are empty, while the startup text inventory consumes only text blocks. In addition, explicit contradiction detection recognizes a narrower English/colon form and misses rows such as `MRR CONTRADICTION CRM 28,6 млн ₸; invoices 27,9 млн ₸`. Therefore the canonical single PDF produces no domain contradiction even though the document explicitly contains four.

- [x] **Step 1: Write producer-path RED tests**

Assert that a parsed PDF table is available to the startup text inventory with safe page/table coordinates, and that a bounded row with an explicit contradiction marker plus two competing numeric/source observations creates one open domain contradiction. Include a negative test proving that a generic QA checklist line such as `CONTRADICTION: MRR` without competing values does not create a contradiction.

- [x] **Step 2: Materialize bounded PDF table text blocks**

Store the table and/or rows as ordinary bounded `TextBlock` records under the existing artifact store, with `page` and `table` provenance. Keep first-seen producer order and deduplicate repeated page/table representations deterministically so snapshot hashes remain stable and the fragment limit is still enforced.

- [x] **Step 3: Detect explicit numeric contradiction rows conservatively**

Support the table status shape only when the same bounded text contains a contradiction marker and at least two competing numeric observations with distinguishable source/context labels. Do not infer a conflict from a heading, fixture instruction, or unsupported checklist entry.

- [x] **Step 4: Run GREEN and canonical proof**

The parser, contradiction-service, and startup composition tests must pass. Processing the real NomadFlow PDF must expose the four known contradiction topics to the profile/advisor path without inventing a winner.

## Task 3: RED Tests For Honest Confidence, Gate 2, Progress, And Dashboard Copy

**Files:**
- Modify: `frontend/founder/components/founder-analysis-pages.test.ts`
- Modify: `frontend/founder/components/founder-analysis-pages.tsx`
- Modify: `frontend/founder/lib/readiness-presentation.test.ts`
- Modify: `frontend/founder/lib/readiness-presentation.ts`

**Interfaces:**
- Consumes: `StartupWorkspace` fields, report status, profile evidence refs.
- Produces: a founder-safe document-understood summary plus UI values that distinguish source facts, missing facts, contradictions, and pending calculations.

- [x] **Step 1: Write RED tests**

Assert these behaviors:
- `hasSourceBackedPrimaryProfile` requires a minimum core set, not any single field;
- every required Gate 2 core field must be `source_fact` with evidence; an inference or unresolved contradiction remains a visible blocker and cannot enable approval;
- `profileConfidenceScore` penalizes missing required fields and cannot show 70% from two populated fields;
- agent progress is derived from actual stage/report/advisor state, not literal `29` or `2 из 7`;
- Gate 2 shows at least five NomadFlow facts or explicit gaps, without filenames, paths, hashes, raw fragments, prompts, or internal reason codes;
- overview/project cards render extracted document facts and otherwise say what data is missing.

- [x] **Step 2: Run RED**

Run: `npm --prefix frontend/founder test -- founder-analysis-pages.test.ts readiness-presentation.test.ts`

Expected: FAIL on the hardcoded progress/confidence/generic copy assertions.

- [x] **Step 3: Implement minimal UI calculation changes**

Change only presentation helpers and local component logic:
- compute core profile coverage from `startup_name`, `one_line_description`, `problem`, `icp`, `pricing_revenue_model`, and `stage`;
- show confidence as weighted completeness plus source confidence;
- show progress from actual completed checkpoints;
- replace fixed success-like cards with fact-backed or missing-data cards;
- add a compact document-understood block built from the same profile presentation model used by Gate 2 and Overview.

- [x] **Step 4: Run GREEN**

Run the same frontend tests and confirm PASS.

## Task 4: RED Tests For Gap-Driven Advisor Questions

**Files:**
- Modify: `tests/unit/application/test_startup_advisor_service.py`
- Modify: `tests/unit/application/test_startup_advisor_api_service.py`
- Modify: `src/due_diligence_agent/application/services/startup_advisor_service.py`
- Modify: `src/due_diligence_agent/application/services/startup_advisor_api_service.py`

**Interfaces:**
- Consumes: active case profile fields and answered question state.
- Produces: `AdvisorQuestion` for the highest-impact missing or low-confidence field in that case.

- [x] **Step 1: Write RED tests**

Assert:
- if revenue/pricing is already source-backed but ICP is missing, next question targets `icp`;
- if core product/problem/stage are missing, they outrank secondary metrics;
- if the document contains a material contradiction, reconciliation of that contradiction outranks a generic missing-field question;
- for NomadFlow, the first question explains that CRM MRR/customer count conflicts with invoice/bank evidence and asks the founder to resolve it;
- answered questions are skipped per case;
- persisted answers replay correctly after service reconstruction even when dynamic gap ranking skipped earlier fixed-priority questions;
- private questions do not offer public research;
- the response exposes a founder-safe origin such as `document_gap`, `document_contradiction`, or `answered_state`, never an internal prompt or reason code.

- [x] **Step 2: Run RED**

Run: `py -3.13 -B -m pytest tests/unit/application/test_startup_advisor_service.py tests/unit/application/test_startup_advisor_api_service.py -q`

Expected: FAIL because current service uses a fixed tuple priority without profile gap input.

- [x] **Step 3: Implement minimal gap input**

Add a backwards-compatible way for the API facade to pass current profile gap and contradiction status into advisor question selection. Keep domain service deterministic and in-memory; do not add persistence beyond existing saved answer state.

Make replay independent of the current ranking order: persisted case-bound question/field identities must reconstruct answered state without asking a different fixed-priority question first.

- [x] **Step 4: Run GREEN**

Run the same pytest command and confirm PASS.

## Task 5: RED Tests For Semantic Answer Validation And Same-Case Recalculation

**Files:**
- Modify: `tests/unit/application/test_startup_advisor_api_service.py`
- Modify: `tests/api/test_startup_api.py`
- Modify: `src/due_diligence_agent/application/services/startup_advisor_api_service.py`
- Modify: `src/due_diligence_agent/application/startup_advisor_recalculation.py`

**Interfaces:**
- Consumes: `AdvisorAnswer(answer_type="manual", value=...)`.
- Produces: validation errors for wrong answer shape and a recalculation result with new `data_revision` for accepted answers.

- [x] **Step 1: Write RED tests**

Assert:
- answering a revenue/pricing question with only `60%` returns `advisor_manual_answer_semantic_mismatch`;
- answering a margin-related question with `60% gross margin` is accepted;
- resolving the NomadFlow MRR/customer contradiction with a specific period/source is accepted and removes or narrows that conflict only;
- a valid manual answer is attached to the active question's `field_key`;
- stale report lineage is invalidated and recalculation returns the same `case_id` with incremented revision;
- the API exposes a founder-safe before/after delta for fields, coverage, conflicts, and calculations changed by the accepted answer.
- an invalid recalculation-port payload or contract error is not silently converted into a successful applied answer with a generic deferred status.

- [x] **Step 2: Run RED**

Run: `py -3.13 -B -m pytest tests/unit/application/test_startup_advisor_api_service.py tests/api/test_startup_api.py -k "advisor" -q`

Expected: FAIL because current validation only checks non-empty manual text and shape.

- [x] **Step 3: Implement minimal semantic validator**

Add field-specific validators:
- revenue/pricing needs currency, MRR/ARR, price, tariff, contract value, or pricing model words;
- margin accepts percent only when the field expects margin/economics;
- ICP requires audience/segment/persona language;
- skip remains allowed but decreases confidence and does not create a fact.

Catch only expected operational recalculation failures. Validation/programmer contract errors must remain visible to tests through a founder-safe API error boundary instead of being swallowed by a broad `Exception` branch.

- [x] **Step 4: Run GREEN**

Run the same pytest command and confirm PASS.

## Task 6: RED Tests For Frontend Advisor Impact And Validation Feedback

**Files:**
- Modify: `frontend/founder/components/founder-advisor-pages.test.ts`
- Modify: `frontend/founder/lib/advisor-presentation.test.ts`
- Modify: `frontend/founder/components/founder-advisor-pages.tsx`
- Modify: `frontend/founder/lib/advisor-presentation.ts`
- Modify: `frontend/founder/lib/contracts.ts`
- Modify as needed: `frontend/founder/components/founder-workspace-controller.tsx`

**Interfaces:**
- Consumes: advisor API `question`, `answer`, `recalculation_data_revision`, and validation errors.
- Produces: question origin and impact labels that match the current gap, plus visible validation feedback when an answer is semantically wrong.

- [x] **Step 1: Write RED tests**

Assert:
- right-side impact cards depend on `question.field_key`, not fixed revenue/pricing strips;
- validation error for `advisor_manual_answer_semantic_mismatch` is displayed as founder-safe Russian copy;
- after a successful answer, UI shows updated revision/recalculation pending or done state from API response;
- the question screen states whether the question came from a missing fact or a document contradiction;
- the updated-analysis screen shows the real before/after delta rather than fixed impact strips.
- the progress pill uses API `answered_count`/`total_count`, not a literal `Шаг 1 из 4`;
- readiness/report presentation cannot combine state from another case merely because its numeric revision matches.

- [x] **Step 2: Run RED**

Run: `npm --prefix frontend/founder test -- founder-advisor-pages.test.ts advisor-presentation.test.ts`

Expected: FAIL on fixed impact card assumptions or missing validation copy.

- [x] **Step 3: Implement minimal presentation changes**

Bind advisor page copy to `question.field_key`, safe question origin, contradiction context, and recalculation delta from API response. Keep existing visual structure; change data flow and labels only.

- [x] **Step 4: Run GREEN**

Run the same frontend tests and confirm PASS.

## Task 7: End-To-End Same-Case Verification

**Files:**
- Modify or add only if needed: `tests/smoke/test_startup_browser_qa.py`, `tests/smoke/test_founder_workspace_boot.py`, or existing scripts under `scripts/`.
- Create final evidence note only if verification passes: `docs/verification/2026-08-21-founder-dynamic-analysis-verification.md`

**Interfaces:**
- Consumes: local backend, Founder frontend, generated test startup document.
- Produces: evidence that the user's screenshot issues are fixed in one real NomadFlow case and that a second fixture does not reuse its values.

- [x] **Step 1: Run targeted backend tests**

Run:
- `py -3.13 -B -m pytest tests/unit/llm/test_startup_profile_extraction.py tests/unit/application/test_startup_advisor_service.py tests/unit/application/test_startup_advisor_api_service.py -q`
- `py -3.13 -B -m pytest tests/api/test_startup_api.py -k "advisor or profile or startup" -q`

- [x] **Step 2: Run frontend checks**

Run:
- `npm --prefix frontend/founder test -- founder-analysis-pages.test.ts founder-advisor-pages.test.ts advisor-presentation.test.ts readiness-presentation.test.ts`
- `npm --prefix frontend/founder run typecheck`
- `npm --prefix frontend/founder run lint`

- [x] **Step 3: Run smoke path**

Use the existing startup smoke/browser script at exactly `1440x1000` to process the NomadFlow PDF and verify one same-case path reaches document summary, profile, overview/metrics, advisor, answer, recalculation, report, and Admin trace. Run a second-fixture comparison for dynamic values. If browser smoke is blocked by localhost/session state, record the blocker; do not call the user-visible fix complete from API tests alone.

- [x] **Step 4: Update verification doc**

Write a short verification note with commands, PASS/FAIL status, screenshots/JSON evidence, changed files, and residual risks. Do not claim Task 8/Queue 5 closure unless the full checkpoint gates pass.

## Task 8: Independent Review And Handoff

**Files:**
- Review the exact changed-file package for Tasks 2-7.
- Update: `docs/verification/2026-08-21-founder-dynamic-analysis-verification.md`

- [x] **Step 1: Run an independent code review**

Review for data invention, contradiction loss, privacy leakage, stale state, misleading confidence, unreachable branches, and regressions in the existing offline/OpenAI separation.

- [x] **Step 2: Resolve every blocking finding and rerun affected checks**

Do not suppress or merely document a correctness/privacy finding that can be fixed in scope.

- [x] **Step 3: Publish the final local handoff**

Record what now changes after upload/answer, exact verification commands and outcomes, screenshot locations, and any genuine external-integration gap. The user handoff must distinguish verified functionality from anything still unverified.

## Task 9: Post-Acceptance Dynamic Metrics And Evidence Hardening

This task was added after visual inspection of the first accepted 14-state run exposed three false-success signals: decimal confidences rendered as `0%`, profile coverage reused confidence instead of field coverage, and the browser evidence writer stored fixed zero counters. The same inspection also showed that financial observations existed in the PDF but were not projected into Founder analytics.

**Files:**
- Modify: `frontend/founder/components/founder-analysis-pages.tsx`
- Modify: `frontend/founder/lib/contracts.ts`
- Modify: `frontend/founder/lib/chart-presentation.ts`
- Modify: `src/due_diligence_agent/application/services/claim_extraction_service.py`
- Modify: `src/due_diligence_agent/application/services/startup_report_service.py`
- Modify: `src/due_diligence_agent/application/services/founder_report_presentation_service.py`
- Modify: `scripts/capture_founder_screenshots.mjs`
- Modify matching frontend/backend/browser regression tests.

**Acceptance:**
- Gate 2 parses backend decimal confidence strings and the canonical PDF displays a non-zero evidence-weighted confidence.
- Overview profile coverage uses covered fields (`9/18 = 50%` in the observed canonical revision), not confidence.
- Current MRR, gross-margin, net-burn, and runway observations are extracted line-by-line with comma/dot decimal support; target/forecast runway is excluded.
- The public report does not silently choose between equal-confidence conflicting values. Source observations, calculations, estimates, and contradictions remain visually distinct.
- Metrics UI shows real current observations where a unique supported value exists and an explicit contradiction state where it does not.
- Browser evidence derives counts from the approved same-case public profile/GTM/report state; no desktop-suite counter is initialized as a demo-only fixed zero.
- A fresh `1440x1000` NomadFlow run proves the metric changes, non-zero profile/evidence counts, advisor question origin, answer validation, recalculation revision, report artifacts, zero external calls, and Admin trace.

- [x] **Step 1: Add RED regressions for confidence and field coverage.**
- [x] **Step 2: Parse decimal confidence and bind overview coverage to field coverage.**
- [x] **Step 3: Add RED regressions and implement line-scoped financial observation extraction.**
- [x] **Step 4: Project honest metric provenance/status through backend and frontend.**
- [x] **Step 5: Replace fixed desktop-suite evidence zeroes with same-case public-state counts.**
- [x] **Step 6: Run full backend/frontend/static/privacy verification.**
- [x] **Step 7: Run and visually inspect a fresh 14-state browser journey.**
- [x] **Step 8: Complete independent review, verifier pass, and final handoff.**

**Task 9 completion evidence:** `artifacts/runtime/founder-dynamic-task9-nomadflow-20260821-17/`. The live PDF-only journey passed all 14 states at `1440x1000`; same-case public counters are non-zero; the final report contains current MRR `27.9m KZT`, net burn `22.4m KZT/month`, and runway `7.8 months`, while the superseded `28.6m KZT` MRR is absent from the selected report value. Independent code review and acceptance verification both returned `ACCEPTED` with no Critical or Important findings.
