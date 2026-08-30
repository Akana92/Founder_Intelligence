# Smart University Real-Document Acceptance Plan

> **Status:** owner-requested continuation route for a fresh chat. Execute with `superpowers:subagent-driven-development`, strict TDD and review gates. This plan extends the accepted Case Copilot v1 Tasks 1-11; it does not repeat them.

## Goal

Make the real 29-page Smart University business plan complete the Founder Intelligence journey:

```text
PDF upload
-> document receipt and processing progress
-> source-grounded project profile
-> stage-aware questions
-> founder statements / explicit unknowns
-> consented public benchmarks
-> deterministic scenario metrics
-> risks, alternatives and actions
-> versioned GTM launch pack and report
```

Source PDF:

`C:\Users\Akana\OneDrive\Рабочий стол\Smart_University_Full_Business_Plan_2026.pdf`

## Non-negotiable boundaries

- `founder_statement`, `public_benchmark` and `ai_scenario` never automatically become `source_fact`.
- A PDF statement may be recorded as an uploaded-document fact with its locator, but this means “stated in the document”, not “independently verified”.
- Public research may add only public market, ICP, competitor, pricing, channel, regulatory and benchmark context.
- Public research must not fill actual MRR, ARR, revenue, burn, cash, customer count, contracts, invoices or bank data.
- Scenario metrics retain provenance, range, formula, dependencies, source references and validation plan.
- Keep the current dirty WIP. Do not reset, clean, checkout, revert or stash.
- Local commits are allowed after passing review gates. Do not push, merge, deploy or publish images without a separate request.

## Task A — Reproduce and freeze the real-PDF upload failure

### RED

1. Add a focused backend regression test that uploads the Smart University PDF, or a minimized fixture preserving the failing structure, with `auto_start=true`.
2. Assert the upload does not return `409 startup_document_intelligence_input_invalid`.
3. Assert a successful upload cannot report Gate 2/profile readiness without a readable profile containing source-linked fields.
4. Add a frontend orchestration regression: an upload failure must remain on the Documents step, preserve the selected-document receipt, show the exact founder-safe cause and offer retry; it must not render a stable empty Profile step.

First required RED evidence:

```powershell
py -3.13 -B -m pytest tests/api/test_startup_smart_university_real_document.py -q -p no:cacheprovider
```

Expected initial failure: the real PDF path reaches document intelligence and returns `409 startup_document_intelligence_input_invalid`.

### GREEN

Trace the original `ValueError` inside `StartupDocumentIntelligenceService.analyze`, fix the smallest violated input/normalization boundary, and retain fail-closed behavior for genuinely invalid inputs. Do not merely suppress the exception or fake a profile.

### Review gates

1. Spec-compliance review: upload works, source locators remain valid, no provenance weakening.
2. Code-quality review: no hardcode to Smart University, no raw document leakage, no duplicate analysis path.

## Task B — Make real-document progress and recovery understandable

### RED

- After server acceptance, the UI shows an accepted-document receipt, processing stage and last known status.
- `Ожидает материалы` cannot appear after documents were accepted.
- A disabled Gate 2 action exposes the exact missing prerequisite and a working repair action.
- A Case Copilot no-action state hides unusable answer controls and offers a real recovery action.
- Long work shows a Russian loader and prevents duplicate submission.

### GREEN

Implement the smallest presentation/orchestration changes. Inline rail and modal drawer semantics must remain distinct. Keep the existing visual direction.

## Task C — Validate Smart University extraction and stage

Expected classification: use the existing `first_sales` stage unless current domain evidence proves a new enum is required. The document describes a working product/pre-scale company, not an idea-only project.

The extracted profile must separate:

- platform product and later housing vertical;
- uploaded-document claims from externally verified facts;
- actual current capabilities from forecasts and gates;
- the 35.2M KZT platform round from the separate 8M KZT housing-management pilot;
- 2027-2031 forecasts from actual performance.

Acceptance checks include product modules, target customers, pricing tiers, market formulas, rating methodology, funding tranches, roadmap gates, legal/privacy risks and housing no-go conditions.

## Task D — Repair and prove public research on the real case

### RED

- A consented job never falls into a generic “check consent” error when consent is already present.
- Deferred, stale-plan, provider-unconfigured, provider-failed and contract-invalid paths display different founder-safe recovery copy.
- A completed/partial job produces visible sources and before/after scenario changes.
- Private revenue/MRR/cash/burn remain manual/file only.

### GREEN

Verify deterministic-offline first. Then, using credentials only from `D:\Agents\Projects\Capstone N3\.env`, run one configured-live public-search proof if external egress is available. Never print secret values.

## Task E — Run the complete Smart University acceptance journey

For the same persisted case:

1. Upload the PDF and observe a source-grounded profile.
2. Confirm/correct the profile.
3. Answer or explicitly skip prioritized commercial gaps.
4. Run consented public research for eligible external context.
5. Inspect conservative/base/optimistic metrics and their provenance.
6. Verify market, risks, recommendations and 7/30/60/90 plan update.
7. Generate and download a versioned GTM launch pack with assumptions and limitations.
8. Restart containers and prove the case, thread, research job, selected scenario and asset survive.

Minimum Smart University outputs:

- deterministic market-size reconstruction with assumption labels;
- tariff economics and lead-cost examples;
- gross margin, CAC payback and LTV/CAC only when dependencies are eligible;
- 2027-2031 revenue/EBITDA shown as forecasts, not actuals;
- platform and housing economics kept separate;
- risk register covering commercial traction, data freshness/SLA, rating anti-fraud and appeals, privacy/legal/tax, and housing legal/fire/sanitary gates;
- launch pack with the twelve Case Copilot sections plus platform thesis, rating methodology, B2B pilot plan, housing decision tree, tranche plan and provenance appendix.

## Task F — Verification and owner handoff

Run focused backend tests first, then proportional backend regression, frontend tests/typecheck/lint/build, Docker health checks and a real browser journey. Save a verification note and a Russian owner guide explaining exactly how to use each stage of the product.

Stop only when the real PDF is user-testable through the complete journey, or when a genuine external blocker is proved with founder-safe evidence and a working fallback.
