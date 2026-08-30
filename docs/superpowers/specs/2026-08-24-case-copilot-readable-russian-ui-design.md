# Case Copilot Readable Russian UI Design

## Goal

Make the existing Founder Workspace understandable to a Russian-speaking founder without exposing backend keys, identifiers, or debug prose as primary interface copy.

## Spatial thesis

- The founder's page is the primary task surface; Case Copilot supports it.
- The shell consumes the available viewport width (`width: 100%`, no fixed shell cap).
- The main column receives all remaining space through `minmax(0, 1fr)`.
- The desktop Copilot rail is fluid through `clamp(...)`; it does not determine the shell width.
- When the viewport cannot keep the main page readable, Copilot becomes a drawer instead of squeezing the page.
- The permanent desktop rail participates in normal document height. It must not use a nested `max-height` plus `overflow: auto`; only the drawer may scroll internally.
- Metric cards use responsive rows and natural height. Long Russian copy must wrap without clipping.

## Founder-facing language

Russian is the default language. Internal enum values remain in API/domain contracts but are mapped before rendering.

| Internal value | Founder-facing label |
| --- | --- |
| `source_fact` | Подтверждённый факт |
| `founder_statement` | Со слов основателя |
| `public_benchmark` | Публичный ориентир |
| `ai_scenario` | Сценарное допущение |
| `deterministic_calculation` | Расчёт по формуле |
| `contradiction` | Противоречие |
| `conservative` | Осторожный |
| `base` | Базовый |
| `optimistic` | Оптимистичный |

Action identifiers, roles, coverage states, metric keys, dependency keys, missing-value markers, and form labels receive the same presentation mapping. Common founder metrics may keep their abbreviation only with a Russian explanation, for example `MRR — ежемесячная регулярная выручка`.

## Disclosure hierarchy

1. Default card: localized metric name, readable localized range, and one short trust statement.
2. Collapsed `Как рассчитано и проверить`: localized provenance, range, formula explanation, humanized dependencies, source count/reference labels, and validation plan.
3. Raw UUIDs, action IDs, enum keys, and backend field keys are not normal founder-facing content. They remain in data contracts and may exist as non-visible diagnostic attributes, but must not appear in default copy.

## Product invariants

- `founder_statement`, `public_benchmark`, and `ai_scenario` never automatically become `source_fact`.
- Every scenario metric retains provenance, range, formula, dependencies, source references, and validation plan.
- Unknown actuals are never rendered as zero.
- Private operating metrics remain manual/file-only. Public benchmark research remains consent-gated.
- No backend or API contract change is required for this UI task.

## Acceptance

- At 1440x1000 the main page remains readable when Copilot is opened; Copilot uses a drawer if a side-by-side rail would squeeze the main surface.
- At 1920x1080 the shell uses the available width and shows a fluid 24-32rem Copilot rail.
- No default founder-facing copy contains raw values such as `source_fact`, `founder_statement`, `public_benchmark`, `ai_scenario`, `deterministic_calculation`, `open_fact_input`, `Scenario-only`, `missing:`, UUID dependencies, `sourceRefs`, or `validationPlan`.
- The manual founder input form and all Case Copilot sections are Russian.
- Metric cards have natural height and do not clip localized copy.
- Technical provenance requirements remain accessible through Russian expandable details.
