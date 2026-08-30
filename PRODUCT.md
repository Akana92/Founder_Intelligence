# Founder Launch Intelligence

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

- Founder Workspace: Next.js App Router and React, consuming versioned `/api/v1` contracts only.
- Application API: FastAPI over the existing Python domain, workflow, evidence, metric, reporting, and tracing layers.
- Admin Console in delivery profile B: the existing Streamlit surface, kept separate from the founder product.
- Delivery profile C may replace local adapters and anonymous context with production identity, tenancy, storage, jobs, and operations without changing the analysis contract.

## Users

The primary user is a startup founder who wants a complete, structured assessment of a proposed or existing product before going to market. The user may not know which questions, metrics, or research methods are relevant and may have only a partial, inconsistent set of documents.

Secondary users are advisors or analysts reviewing the founder-facing report. Technical operators use the separate Admin Console and are not an audience for Founder Workspace.

## Product Purpose

Founder Launch Intelligence turns whatever startup material the founder already has into a guided market-readiness case. It must find the business model, claims, gaps, relevant metrics, risks, competitors, and next actions without requiring the founder to choose an industry, select a prepared demo project, or write a good prompt.

Success means that one upload flow produces a useful primary diagnosis, then continues into a deeper analysis inside the same case, with every important conclusion grounded in evidence, calculation, or an explicit insufficient-data state.

## Positioning

This is a launch-readiness instrument, not a general AI chat. Its defensible mechanism is an automatic evidence-led workflow that decides which questions and business metrics matter, detects contradictions, separates score from confidence and coverage, and converts missing proof into concrete validation work.

## Operating Context

- The founder may upload one document or a mixed data room: PDF/DOCX descriptions and decks, XLSX/CSV financial or cohort data, images, and a safe ZIP containing supported files.
- Incomplete data is valid input. Unsupported, unsafe, quarantined, low-confidence, and missing items remain visible rather than being silently treated as analyzed.
- Primary analysis begins automatically after safe parsing and returns the startup profile, strengths, weaknesses, gaps, initial risks, and applicable metric pack.
- Deep analysis continues the same case with market and competitor research, detailed calculations, scenarios, contradictions, bounded Reflexion, priority questions, and a 7/30/60/90 action plan.
- Guarded live research is used when permitted and available; dated cached or frozen evidence is the fallback. The user does not select the technical research mode.
- A versioned report snapshot is the shared source for JSON, HTML, and downloadable PDF outputs.

## Capabilities and Constraints

- Delivery profile B is the current commercial-demo target. Founder Workspace is a separate product-grade browser application; the Admin Console may remain on Streamlit.
- Profile B and future profile C provide the same primary and deep analysis. C adds authentication, RBAC, tenancy, multi-user workflows, production persistence and object storage, durable jobs, backups, SLOs, and operational controls.
- Founder Workspace never exposes model settings, fixture adapters, raw traces, internal prompts, or sensitive document content from observability systems.
- Admin Console owns tracing, privacy review, evaluations, budgets, cost/latency, and integrity diagnostics.
- Readiness score, confidence, and evidence coverage are distinct. A score is not an investment recommendation or an objective company valuation.
- Important market, competitor, sentiment, and comparable findings include source provenance, an `as-of` date, confidence, or an explicit local-only/partial limitation.
- The public-company workflow is a secondary comparable and market-context module, not a competing primary product mode.
- “Founder Launch Intelligence” is a working product name, not a final trademark.
- Open decisions: final public name and launch language; first-release OCR/redaction depth; post-demo delivery format; pricing and commercial packaging.

## Brand Commitments

- Voice: direct, calm, evidence-led, and understandable to a non-financial founder. Explain unfamiliar metrics instead of using unexplained finance jargon.
- The product shows conclusions, limitations, and a path to action. Technical depth belongs in Admin Console.
- Do not imitate a Bloomberg terminal, a developer console, or a generic AI assistant.
- No invented customers, benchmarks, testimonials, prices, or completeness claims.

## Evidence on Hand

- Canonical product specification: `docs/superpowers/specs/2026-08-11-founder-launch-intelligence-product-tz.md`.
- Delivery architecture and B-to-C boundaries: `docs/architecture/2026-08-12-sales-ready-hybrid-boundaries.md`.
- Existing reusable public-company analysis, evidence ledger, deterministic metrics, reporting, bounded Reflexion, tracing, and privacy foundation in the Python application.
- Frozen public-company fixtures and generated report paths are technical verification material, not founder-facing proof or a selectable demo catalog.
- No approved public brand mark, customer proof, pricing, or production deployment claim exists yet; the interface must not fabricate them.

## Product Principles

1. Start from the founder's documents, not from a prompt or taxonomy form.
2. Deliver value in two depths inside one case: immediate diagnosis first, researched decision support second.
3. Never turn missing or conflicting data into false certainty.
4. Connect every material conclusion to evidence, calculation, or an explicit limitation.
5. Separate founder decisions from operator diagnostics so the product remains clear and safe.

## Accessibility & Inclusion

- Desktop-only investor demonstration at 1440px. Mobile layout, breakpoint, smoke, and mockup requirements are out of scope for this product contract.
- Russian is the default language for the founder-facing product and report.
- WCAG AA contrast, visible focus states, keyboard-accessible upload and navigation, readable tables, and expandable evidence.
- Risk and status are communicated with text and symbols as well as color.
- Human-facing language remains legible and plain; monospace is reserved for identifiers, hashes, traces, and formulas.
