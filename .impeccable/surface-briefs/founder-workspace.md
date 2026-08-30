# Founder Workspace surface brief

## Scope and mode

- Primary target: `frontend/founder/app/page.tsx`
- Surface: Founder Workspace — New analysis
- Mode: Operate
- Delivery profile: B — Sales-Ready Hybrid
- Product name: “Founder Launch Intelligence” is a working name, not a final trademark.

## Audience, job, and primary action

- Audience: a startup founder with one document or an incomplete mixed data room who may not know the right market, finance, or product questions.
- Job: understand whether the proposed product is ready for market, what is strong, what is missing, what conflicts, which metrics matter, who competes, and what to do next.
- Primary action: upload the founder's own materials. Do not ask for an industry, demo vertical, prepared project, analysis mode, or prompt.
- Product promise: a useful primary diagnosis starts automatically; deep analysis continues inside the same case.

## First viewport contract

Within five seconds, a first-time viewer must understand all three facts:

1. This product analyzes the founder's own startup materials.
2. Incomplete materials are acceptable.
3. One case produces an immediate primary analysis and a deeper evidence-backed analysis.

The working headline is: **“Загрузите материалы — получите карту выхода на рынок”**.

The upload target and its button are visible without scrolling. The first viewport also previews the seven analysis domains and the relationship between primary and deep analysis, but it does not invent a readiness score before data exists.

## Chosen composition

Approved comp: `.impeccable/mocks/founder-workspace-comp-c-case-dossier.png`

Approval basis: the implementation plan delegates selection by task clarity and investor-demo comprehension. Composition C wins because it makes the upload action immediate, shows the two analysis depths as connected horizons of one dossier, and preserves honest pre-upload states. Composition A is denser than necessary at entry. Composition B is visually strong but its illustrative score could be read as a product claim before analysis.

The memorable moment is the **evidence spine**: accepted documents accumulate along one central line while the primary horizon appears first and the deep horizon extends, challenges, and sources it. The user never switches between “modes”; depth grows inside the case.

Generated alternatives retained for traceability:

- `.impeccable/mocks/founder-workspace-comp-a-evidence-runway.png`
- `.impeccable/mocks/founder-workspace-comp-b-depth-staircase.png`
- `.impeccable/mocks/founder-workspace-comp-c-case-dossier.png`

The comp is a north star, not source content. Misspelled generated text, illustrative values, dates, IDs, scores, and unsupported file or privacy claims must not be literalized. In particular, the generated pre-upload risk cell must ship as an explicit “Нужны материалы” state rather than “Требует внимания” or named risk categories until evidence exists.

## Visual world

- Restrained deep navy / near-black matte analytics surface.
- Off-white human-facing text with high contrast.
- Cyan and teal identify system progress, evidence, provenance, and the primary action.
- Amber and red appear only with explicit warning/risk labels and icons.
- Humanist workhorse UI typography; use local system faces such as Segoe UI Variable/Aptos. Monospace is limited to IDs, hashes, traces, formulas, and source dates.
- Precise 1px rules, square-to-soft 2–6px corners, minimal elevation, no glossy glass or ornamental shadows.
- No generic purple AI gradients, neon glow, terminal texture, chatbot bubbles, Bloomberg imitation, decorative robots, stock photography, or finance jargon without an explanation.

## Important states

- Empty: no files, no score, no false coverage; explain that incomplete input is valid.
- Drag-active: unmistakable target highlight without changing layout.
- Selected files: inventory with type, size, parsing state, and removable items.
- Unsupported/quarantined/low-confidence: plain-language reason and effect on analysis; warning is not color-only.
- Parsing and primary analysis: founder-readable stage names, not internal graph or model names.
- Primary ready: snapshot remains visible when deep analysis begins.
- Deep partial: name the unavailable branch, why it is unavailable, its `as-of`/coverage, and what remains usable.
- Deep ready: show which primary findings were confirmed, changed, or rejected.
- Error: retain accepted files and available results; offer a safe retry or continuation.

## Founder and Admin boundary

Founder Workspace contains decisions, evidence summaries, limitations, and next actions. It does not contain raw traces, prompts, model controls, fixture switches, eval internals, token logs, or sensitive raw document content from observability.

Admin Console remains a separate route/application for tracing, privacy, evaluations, cost/latency, budgets, and integrity. A quiet environment/version label may be visible to a demo operator, but it is not founder navigation.

## B-to-C upgrade boundary

Profile C is not shown as a user-selectable plan or analysis mode. The Founder Workspace consumes stable `/api/v1` capabilities and case resources. C may later add authentication, RBAC, tenancy, multi-user collaboration, Postgres/object storage, durable jobs, backup/SLO controls, and production operations while preserving this surface's product language and the primary/deep case model.

## Direction contract for the emitted page

<!--
THESIS: One evidence dossier grows from incomplete documents into two connected analysis horizons; refuse the category-default dashboard of unrelated KPI cards.
OWN-WORLD: Matte near-black navy fields, off-white human text, cyan evidence paths, amber/red labeled risk, one-pixel rules, compact square controls, and no ornamental glow.
STORY: The founder sees that any material is enough, uploads once, receives a primary diagnosis, then watches deeper research test the same case and turn gaps into actions.
FIRST VIEWPORT: A slim product bar; headline left and upload action right; below, a wide two-horizon analysis map, central evidence spine, and narrow case brief. Upload remains above the fold.
FORM: Case dossier fold, structure 7, seed key 24519428.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
-->

## Implementation inventory

| Visible ingredient | Commitment | Medium |
|---|---|---|
| Product bar | Working name, New analysis active, Cases and Public comparables secondary; no Admin | Semantic HTML/CSS |
| Intro band | Headline at roughly 60% width; upload action owns the right 40% | Semantic HTML/CSS |
| Upload target | Native file input behind an accessible label/button; drag state; accepted-format help | Semantic HTML/CSS, authored SVG upload icon |
| Analysis map | Two connected horizons across Problem, Customer, Market, Competition, Business model, Metrics, Risks | Semantic sections/grid, CSS rules, authored SVG icons |
| Evidence spine | Vertical provenance path linking document intake to both horizons | CSS/SVG; animated only when state changes |
| Empty domain cells | Explicit “Нет данных” or “Нужны материалы”, never fake values | Semantic HTML/CSS |
| Case brief | Data-room inventory, coverage, and next-step sequence | Semantic HTML/CSS |
| Status/risk | Icon + label + explanation; cyan for progress, amber/red only for risk | HTML/CSS, authored SVG icon |
| Bottom action strip | Reassurance about incomplete data plus repeated upload action | Semantic HTML/CSS |
| Core copy and controls | Never rasterized | Semantic HTML |
| Generated comp | Reference for topology, scale, density, material, and hierarchy only | Design reference; not shipped as UI raster |

## Responsive and accessibility rules

- Desktop reference viewport: 1440×900.
- On narrow screens: stack intro and upload; show Primary and Deep as two consecutive sections; retain the evidence relationship through labels and a compact connector; do not shrink the desktop matrix into unreadable cells.
- Keyboard users can reach navigation, file input, remove/retry controls, evidence expansion, and analysis sections in reading order.
- Focus is visible on the dark surface. Contrast targets WCAG AA. Status never relies on color alone.
- Motion is short and stateful; respect `prefers-reduced-motion`.

## Unresolved decisions

- Final public product name and launch language.
- Final file-size limits and the supported-format set for the first release.
- Exact OCR/redaction depth and the post-demo hosting format.
- Pricing and commercial packaging.
