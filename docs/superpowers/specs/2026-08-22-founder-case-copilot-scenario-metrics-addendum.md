# Founder Intelligence Case Copilot v1 — Scenario Metrics And Launch Pack Addendum

**Status:** owner-approved product direction on 2026-08-22
**Extends:** `docs/superpowers/specs/2026-08-22-founder-case-copilot-v1-design.md`
**Priority:** this addendum wins only where it adds or clarifies scenario behaviour; all privacy, evidence, revision and same-case invariants of the base specification remain mandatory.

## 1. Owner outcome

An idea-stage founder may upload an arbitrary startup document that contains a concept, desired product and launch timing but no financial model. The product must not block the founder or fill the workspace with unexplained zeroes. Case Copilot must guide the founder through the missing decisions, construct explicitly labelled planning scenarios, calculate dependent metrics deterministically and prepare a founder-usable go-to-market document.

The canonical journey is:

```text
idea document
  -> stage-aware extraction
  -> prioritized Copilot questions
  -> founder-approved statements and assumptions
  -> optional consented public benchmarks
  -> conservative / base / optimistic scenarios
  -> deterministic metrics and readiness projection
  -> strengths / weaknesses / risks / alternatives
  -> GTM launch pack and 7 / 30 / 60 / 90-day plan
```

## 2. Non-negotiable evidence boundary

Every value used by the product has exactly one visible provenance kind:

| Kind | Meaning | May be shown as actual performance? |
|---|---|---|
| `source_fact` | Eligible uploaded/internal evidence supports the value | Yes |
| `founder_statement` | The founder explicitly supplied or accepted the value | No; it remains founder-declared until independently evidenced |
| `public_benchmark` | A cited external source describes a market or comparable range | No |
| `deterministic_calculation` | Code calculated the value from typed dependencies | Only with the dependency provenance shown |
| `ai_scenario` | Copilot proposed a planning assumption or forecast range | No |
| `contradiction` | Eligible sources disagree or a value is unresolved | No |

Accepting a Copilot proposal never converts `ai_scenario`, `public_benchmark` or `founder_statement` into `source_fact`. Only eligible evidence processed through the existing Evidence Ledger may create `source_fact`.

Private startup facts remain manual/file only: actual MRR, ARR, recognised revenue, burn, cash balance, actual customer count, contracts, invoices and bank data. Public research may return only external context such as market size, public competitor pricing, channel benchmarks, adoption signals and comparable ranges.

## 3. Adaptive question contract

Case Copilot asks one highest-value question at a time. Ranking uses the detected stage, unresolved contradictions, metric dependency graph, readiness contribution and expected decision impact.

The first idea-stage sequence covers:

1. problem, solution and ICP;
2. buyer, user and purchase trigger;
3. pricing and revenue model;
4. MVP scope, launch date, team and available budget;
5. acquisition channel and funnel assumptions;
6. delivery cost, operating cost, cash and funding constraints;
7. evidence already collected and the next validation experiment.

Each question response offers only valid modes for its registry entry:

- structured manual entry;
- selected case document;
- prepare public research plan;
- `не знаю` / skip with the next safe route.

The UI must explain why the question matters, the expected input shape, which metric or decision it unlocks and what changes after acceptance. Draft input survives validation errors and page navigation.

## 4. Scenario contract

One scenario set belongs to one `case_id` and one `data_revision`. It contains `conservative`, `base` and `optimistic` scenarios. Each scenario input contains:

- canonical metric/input key;
- lower and upper bound, or an exact typed value when exactness is justified;
- unit, currency/scale where applicable and period/date;
- provenance kind;
- source or dependency references;
- confidence;
- rationale;
- validation plan;
- founder acceptance state.

Scenario values prefer ranges and must not use fake precision. A scenario set becomes stale when any dependency, accepted assumption, public benchmark or case revision changes.

The deterministic metric engine owns arithmetic. Minimum derived projections:

```text
MRR forecast       = monthly price * projected paying customers
ARR forecast       = MRR forecast * 12
gross margin       = (revenue - cost of goods sold) / revenue
net burn           = monthly operating expenses - monthly revenue
runway             = cash balance / positive net burn
CAC                 = acquisition spend / acquired customers
LTV                 = ARPA * gross margin / churn, only when all inputs are eligible
LTV/CAC             = LTV / CAC
CAC payback months  = CAC / (ARPA * gross margin)
```

Actual churn and retention are not inventable before cohort data exists. The UI may show cited benchmark or AI-scenario ranges, but labels them as projections and shows the validation requirement.

## 5. Stage-aware UI contract

The main route depends on project stage:

- `idea` -> Idea Validation;
- `first_sales` -> Traction Validation;
- `growth` -> Growth Analytics.

Every metric card remains visible, but it must show one of:

- actual supported value;
- deterministic calculation;
- scenario range;
- contradiction;
- explicit missing dependency and a working action.

The overview displays two separate measures:

- `fact_coverage`: evidence-backed understanding of the real project;
- `scenario_completeness`: completeness of the accepted planning model.

An idea-only project therefore does not appear as a failed `0/100` company. It may have low fact coverage and a useful scenario draft at the same time.

The scenario selector updates metric cards, charts, risks and actions between conservative, base and optimistic views without mutating facts. Every card exposes formula, inputs, provenance, confidence, period and `what_would_confirm`.

## 6. Copilot advice contract

Advice is case- and scenario-specific. It includes:

- supported strengths;
- weaknesses and missing proof;
- business, market, monetisation and execution risks;
- explicit counter-thesis;
- at least two viable action alternatives when a material choice exists;
- expected effect, effort, prerequisite, metric and validation criterion;
- a recommended next action that can be executed or opened in the UI.

Advice never changes facts or assumptions silently. A typed action and explicit founder confirmation are required before a case mutation.

## 7. GTM launch pack

Case Copilot generates a versioned draft launch pack from the current profile, accepted founder statements, public research, selected scenario, risks and action plan. It contains:

1. executive summary;
2. problem, solution, ICP, buyer and purchase trigger;
3. value proposition and positioning;
4. market, competitors and alternatives with citations;
5. business model and public pricing context;
6. conservative/base/optimistic unit-economics table;
7. recommended pricing and acquisition experiments;
8. funnel and measurement plan;
9. strengths, weaknesses, risks and counter-thesis;
10. 7 / 30 / 60 / 90-day plan;
11. validation backlog;
12. provenance, assumptions and limitations appendix.

The launch pack is a generated draft, never evidence. Preview and download are real actions. Regeneration records the source revision and selected scenario.

## 8. Completion criteria

The extension is user-testable only when two different idea-stage documents prove the following:

1. different extracted profiles and prioritized questions;
2. founder answers persist as `founder_statement`, not `source_fact`;
3. `не знаю` produces the correct manual-only or researchable route;
4. public research cannot request private startup facts;
5. three scenario sets produce different deterministic metric ranges;
6. fact coverage remains distinct from scenario completeness;
7. metrics, risks and actions update after an accepted answer or benchmark;
8. Copilot gives project-specific strengths, weaknesses and alternatives;
9. a GTM launch pack preview/download is generated with a provenance appendix;
10. restart preserves the thread, accepted assumptions, research jobs, scenario selection and generated assets;
11. no active CTA lacks a handler or explicit blocker reason;
12. backend tests, privacy checks, frontend tests, typecheck, lint, build and browser E2E pass with fresh evidence.
