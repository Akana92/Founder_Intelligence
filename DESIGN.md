---
name: Founder Launch Intelligence
description: Evidence-led startup launch readiness workspace built as a dark analytical case dossier.
colors:
  ink-950: "#040a11"
  ink-925: "#06101a"
  ink-900: "#07131f"
  ink-875: "#0a1825"
  ink-850: "#0d1d2b"
  line: "#203748"
  line-strong: "#31566b"
  text: "#eef7fa"
  text-soft: "#a9bac5"
  text-muted: "#768b99"
  cyan: "#25d7f3"
  cyan-deep: "#0bb6d0"
  teal: "#36cdb0"
  amber: "#f3b23f"
  red: "#ff716c"
  focus: "#8cecff"
typography:
  display:
    fontFamily: '"Segoe UI Variable", "Aptos", "Segoe UI", ui-sans-serif, system-ui, sans-serif'
    fontSize: "clamp(38px, 4.2vw, 68px)"
    fontWeight: 700
    lineHeight: 0.99
    letterSpacing: "-0.045em"
  headline:
    fontFamily: '"Segoe UI Variable", "Aptos", "Segoe UI", ui-sans-serif, system-ui, sans-serif'
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.025em"
  title:
    fontFamily: '"Segoe UI Variable", "Aptos", "Segoe UI", ui-sans-serif, system-ui, sans-serif'
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0"
  body:
    fontFamily: '"Segoe UI Variable", "Aptos", "Segoe UI", ui-sans-serif, system-ui, sans-serif'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  label:
    fontFamily: '"Cascadia Code", "SFMono-Regular", Consolas, monospace'
    fontSize: "10px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.12em"
rounded:
  none: "0"
  xs: "2px"
  sm: "4px"
  md: "6px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "18px"
  lg: "28px"
  xl: "42px"
components:
  button-primary:
    backgroundColor: "{colors.cyan}"
    textColor: "{colors.ink-950}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "0 18px"
    height: "46px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.cyan}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "0 18px"
    height: "46px"
  panel:
    backgroundColor: "{colors.ink-900}"
    textColor: "{colors.text}"
    rounded: "{rounded.none}"
    padding: "28px"
  chip-state:
    backgroundColor: "transparent"
    textColor: "{colors.text-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "5px 7px"
---

## Overview

**Creative North Star: "The Evidence Dossier"**

Founder Launch Intelligence is built as a dark analytical case file: a matte near-black workspace where uploaded materials become an evidence spine and two connected analysis horizons. The interface is dense enough for an investor-grade product demo, but its hierarchy stays calm: one primary upload action, one case, and no decorative hero imagery.

The system uses precise rules, compact cells, readable Russian product copy, and restrained status language to make uncertainty visible without turning the page into an operator console. Primary analysis and deep analysis are treated as horizons inside the same dossier, not as separate modes or competing dashboards.

**Key Characteristics:**
- Matte near-black navy surfaces with off-white human-facing text.
- Cyan marks primary action, navigation, progress, and evidence paths.
- Teal confirms available capability; amber warns; red is reserved for critical unavailable states.
- One-pixel rules, compact square controls, and soft 2-6px corners create structure without decorative depth.
- The first viewport always gives the upload action visual priority and never shows fake scores before evidence exists.

## Colors

The palette is a dark evidence workspace: ink fields establish seriousness, cyan draws the path of action and provenance, teal confirms availability, amber names caution, and red is used only for critical risk or unavailable states.

### Primary
- **Evidence Cyan**: Primary action fill, active navigation underline, current journey step, icons, evidence connectors, and link-like text actions.
- **Deep Evidence Cyan**: Dashed upload borders, secondary button borders, connector strokes, and low-intensity evidence accents.

### Secondary
- **Availability Teal**: Positive lifecycle and capability availability states.
- **Caution Amber**: Risk domain emphasis, warning icons, operator boundary affordances, and review-required states.
- **Critical Red**: Unavailable lifecycle states and critical risk indicators only.

### Neutral
- **Black Ink**: Page background and focus-ring inner contrast.
- **Shell Ink**: Sticky product bar, analysis board, case brief, and evidence spine panels.
- **Panel Ink**: Upload target, analysis horizon, honesty strip, and framed content surfaces.
- **Raised Ink**: Hover background for secondary controls and drag-active upload tint.
- **Rule Line**: Default 1px dividers, grid cell boundaries, and framed sections.
- **Strong Rule Line**: Emphasized borders, icon frames, scrollbars, and the evidence spine line.
- **Human Text**: Primary copy and headings.
- **Soft Text**: Supporting paragraphs and secondary explanations.
- **Muted Text**: Empty states, metadata, disabled controls, and low-priority labels.
- **Focus Cyan**: Visible keyboard focus ring on the dark surface.

### Named Rules

**The Evidence-Only Color Rule.** Cyan, teal, amber, and red must describe action, evidence, capability, or risk; they are not decorative accents.

**The Red Scarcity Rule.** Red appears only when the state is explicitly critical or unavailable, never as a generic heat-map color.

## Typography

**Display Font:** Segoe UI Variable with Aptos, Segoe UI, and system sans-serif fallbacks.
**Body Font:** Segoe UI Variable with Aptos, Segoe UI, and system sans-serif fallbacks.
**Label/Mono Font:** Cascadia Code with SFMono-Regular, Consolas, and monospace fallbacks.

**Character:** The type system is a humanist workhorse stack with a strong display weight for the first decision moment and compact mono labels for evidence, stage, status, and environment metadata. Monospace is deliberately narrow in use: identifiers, counts, statuses, step numbers, and source-like labels.

### Hierarchy
- **Display** (700, clamp(38px, 4.2vw, 68px), 0.99): The first-viewport headline and comparable-surface headline.
- **Headline** (700, 24px, tight): Section titles such as the analysis map and case brief.
- **Title** (700, 16px, 1.2): Horizon headers and compact panel titles.
- **Body** (400-700, 11-20px, 1.4-1.6): Founder-facing explanation, cells, upload help, and status details.
- **Label** (500-700, 8-13px, 0.05-0.13em when uppercase): Eyebrows, lifecycle chips, step numbers, environment markers, and compact evidence labels.

### Named Rules

**The Human-First Type Rule.** Use the sans stack for founder decisions and explanations; reserve monospace for evidence structure, not for the main product voice.

## Layout

The Founder Workspace uses a desktop-first dossier layout capped at 1680px. The sticky product bar is a three-column grid with brand, navigation, and a quiet delivery-profile label. The first viewport is a two-column hero: copy owns the wider left side and the upload panel owns the right side, visible without scrolling.

Below the first viewport, the analysis dossier is a three-column grid: analysis board, narrow evidence spine, and fixed-width case brief. The board contains two horizontal seven-domain horizons separated by a compact connector, while the case brief summarizes inventory, next steps, and runtime status.

The canonical visual acceptance target is the desktop layout at 1440px. Mobile layout, breakpoints, mobile smoke, and mobile mockups are out of scope; the historical mobile evidence remains an unchanged past verification artifact.

### Named Rules

**The Same-Case Rule.** Primary and deep analysis stay visually connected inside one case; do not split them into tabs, modes, or unrelated dashboards.

**The Above-The-Fold Upload Rule.** The universal upload target remains a first-view primary action on desktop.

## Elevation & Depth

Depth is conveyed through tonal layering, 1px borders, dashed upload boundaries, scrollable grids, and geometric connector lines. The built system has no ornamental shadows, no glassmorphism, and no glow-based hero treatment; even hover states use color shifts instead of lifted cards.

### Shadow Vocabulary
- **Focus Ring** (`0 0 0 3px var(--ink-950), 0 0 0 5px var(--focus)`): Keyboard focus visibility on buttons, links, labels, and focusable regions.

### Named Rules

**The Flat Dossier Rule.** Surfaces are flat by default; structure comes from ink layers, borders, and measurement lines rather than ambient shadow.

## Shapes

The form language is square-to-soft: most panels, cells, buttons, upload targets, and chips use square corners, while brand geometry and authored icons provide the memorable shape language. Borders are usually 1px solid rules, with a dashed cyan border only for the upload target. The brand mark and upload icon use rotated square geometry to keep the identity technical without becoming a terminal or finance-dashboard imitation.

## Components

### Buttons
- **Shape:** Square rectangular controls with no radius.
- **Primary:** Evidence Cyan fill, Black Ink text, 46px minimum height, bold 13px label, and a plus sign aligned to the far edge.
- **Secondary:** Transparent background, Deep Evidence Cyan border, Evidence Cyan text, same 46px control height.
- **Disabled:** Transparent fill, Rule Line border, Muted Text, full-width when used for unavailable analysis start.
- **Hover / Focus:** Primary hover shifts to Focus Cyan; secondary hover shifts to Raised Ink; focus uses the two-layer Focus Ring.

### Upload Target
- **Style:** Full-height Panel Ink field with a dashed Deep Evidence Cyan border, centered upload icon, direct title/copy, primary button, and supported-format help.
- **State:** Drag-active changes the surface to Raised Ink and strengthens the border to Evidence Cyan without moving layout.
- **Inventory:** Selected files appear in a Shell Ink panel with file marks, truncated file names, candidate/review chips, and removable items.

### Navigation
- **Style:** Sticky Shell Ink product bar with brand mark, active underline, compact links, and no Admin navigation.
- **State:** Active navigation uses Evidence Cyan text plus a 2px underline; disabled case navigation uses muted text and a small bordered "soon" chip.

### Analysis Horizons
- **Style:** Panel Ink horizon frames with uppercase titles, compact state chips, and horizontally scrollable seven-domain grids on desktop.
- **Primary Horizon:** Shows one founder-readable domain summary plus an explicit empty-evidence state.
- **Deep Horizon:** Shows the deeper research lenses as compact lists, not as a separate mode.

### Domain Cells
- **Style:** 1px right borders, mono ordinal, cyan authored icon, compact title, and soft explanatory text.
- **Risk Cell:** Uses amber icon/list emphasis only for the risk domain; it does not color every uncertain cell as risk.

### Evidence Spine
- **Style:** Narrow vertical provenance lane with rotated mono label, one-pixel vertical rule, small square nodes, and an active cyan node when files exist.
- **Responsive:** Hidden at tablet widths and replaced by labels/connectors in the stacked layout.

### Case Brief
- **Style:** Fixed-width right rail on desktop, Shell Ink background, section dividers, inventory counts, next-step sequence, and runtime capability status.
- **State:** Empty inventory shows zeros and an honest "incomplete data is acceptable" explanation instead of a readiness score.

### Status Markers
- **Style:** Cyan square marks for loading/ready status, amber bordered warning icons for unavailable API or caution states, teal lifecycle chips for available capabilities, red lifecycle chips for unavailable capabilities.
- **Motion:** Loading status uses a stepped pulse; reduced-motion disables practical animation duration globally.

### Comparables Surface
- **Style:** Secondary research page keeps the same dark dossier language and adds a subtle 64px measurement grid in low-opacity cyan over Black Ink.
- **Boundary:** It is visibly separate from Admin and does not route the founder into operator tracing or diagnostics.

## Do's and Don'ts

### Do:
- **Do** keep universal upload as the first-view primary action.
- **Do** show primary and deep analysis as connected horizons inside the same case.
- **Do** use explicit empty states such as "needs materials" or "no evidence" before analysis exists.
- **Do** communicate warning and capability state with text and icons as well as color.
- **Do** keep Founder Workspace separate from Admin, tracing, evals, prompts, model controls, and raw operator logs.
- **Do** use the subtle measurement grid only on secondary comparables-style surfaces, not as a global decoration.

### Don't:
- **Don't** show fake scores, coverage, metrics, benchmarks, customers, or investment claims before evidence exists.
- **Don't** imitate Bloomberg terminals, developer consoles, generic AI chat, chatbot bubbles, or finance dashboards.
- **Don't** use purple AI gradients, neon glow, glossy glass, stock photography, decorative robots, or ornamental hero imagery.
- **Don't** use red for ordinary uncertainty or warning; amber handles caution and red stays critical.
- **Don't** split delivery profile B and future profile C into user-facing plans or modes.
