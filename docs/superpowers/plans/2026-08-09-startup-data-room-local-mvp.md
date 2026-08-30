# Startup Data-Room Local MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the verified Stage 1A local application with a complete Startup workflow that safely ingests a mixed-format data room, parses and redacts it locally, builds a claim–evidence matrix and deterministic startup metrics, pauses at disclosure/review gates, and produces evidence-backed Report JSON, HTML, and PDF with passing privacy and regression gates.

**Architecture:** Reuse the Stage 1A domain entities, repositories, Evidence Ledger, Metric Engine, Privacy/LLM Gateway, DataEgressPolicy, durable audit, report snapshot, renderers, Streamlit shell, and evaluator framework. Add only Startup-specific artifact inventory, parsers, OCR, sensitivity/redaction, workflow nodes, claim models, metric definitions, report sections, UI panels, and fixtures behind the existing ports.

**Tech Stack:** Stage 1A stack plus openpyxl, python-docx, PyMuPDF, pdfplumber, Pillow, optional Tesseract/pytesseract, optional Presidio, optional Docling, existing sentence-transformers/FAISS, LangGraph HITL, pytest golden fixtures.

## Global Constraints

- Prerequisite: Stage 1A Gate B is green and its shared contracts are committed.
- Do not duplicate or fork `Artifact`, `EvidenceFact`, `Calculation`, `Finding`, `Contradiction`, `Approval`, `ReportSnapshot`, `NodeResult`, `MetricEngine`, `DataEgressPolicy`, report renderers, repositories, or audit contracts.
- Any shared-contract change must be backward-compatible and pass both public and startup suites.
- Startup ingest is read-only analysis, not a Virtual Data Room: no sharing, external links, collaborative edits, e-signature, or granular document permissions.
- Allowed inputs: PDF, XLSX, CSV, DOCX, PNG/JPEG images, and ZIP containing only allowlisted types.
- Default limits: 100 files/case, 250 MB/file, 1 GB unpacked/case, archive depth 2, decompression ratio 100:1.
- Content sniffing, safe path resolution, quota enforcement, quarantine, and content-addressed storage occur before parsing.
- Parser/OCR/embedding/model artifacts are downloaded only during explicit setup, recorded by hash/license/version, and loaded in no-network mode during Startup analysis.
- Raw Startup artifacts remain local; `RESTRICTED` data never leaves the runtime.
- Highest sensitivity wins; derived data inherits the maximum input sensitivity until explicit re-identification-safe reclassification.
- Gate 2 occurs after classification/redaction and before any external LLM call; a newly detected higher class pauses the graph again.
- Denied disclosure continues only through local deterministic processing or produces an explicit HITL item; no hidden provider fallback.
- OCR or parser uncertainty never becomes verified evidence silently; low-confidence values require corroboration or HITL.
- Every critical claim has a source locator, calculation, contradiction, or `insufficient_data`.
- Startup metrics use the shared `MetricEngine` and `Decimal`; missing inputs never produce invented values.
- Reflexion remains bounded to two rounds; HITL Gates 3 and 4 reuse Stage 1A behavior.
- Report JSON remains canonical; Startup sections extend the common snapshot schema.
- Run the full Stage 1A suite after every task that changes a shared file.
- Gate C must pass before Startup LLM analysis; Gate D and combined Gate E must pass before declaring Stage 1B complete.

---

## Planned File Structure

| Area | New or extended files |
|---|---|
| Dependency gates | `pyproject.toml`, `uv.lock`, `scripts/smoke_stage1b.ps1` |
| Artifact safety | `domain/artifacts/safety.py`, `startup_inventory.py`, `ports/archive.py`, `adapters/documents/archive_inspector.py`, `application/services/data_room_service.py` |
| Parsing | `domain/documents/models.py`, `ports/parsers/document_parser.py`, `adapters/documents/pdf_parser.py`, `docx_parser.py`, `image_ocr.py`, optional `docling_parser.py`, `spreadsheet_parser.py`, `no_network_guard.py` |
| Privacy | `domain/privacy/models.py`, `adapters/privacy/rules_redactor.py`, `presidio_redactor.py`, `application/services/startup_privacy_service.py` |
| Claims | `domain/evidence/startup_claims.py`, `application/services/claim_extraction_service.py`, `workflows/startup/nodes/claims.py` |
| Metrics | `domain/metrics/startup.py`, `application/services/startup_metric_service.py` |
| Workflow | `workflows/startup/state.py`, `plan.py`, `nodes/*`, `graph.py` |
| Presentation/report | `adapters/reports/templates/startup_report.html.j2`, `presentation/streamlit/pages/startup_case.py`, mode-specific components |
| Evaluation | `tests/fixtures/startup_synthetic_saas_v1/*`, `document_parsing_v1/*`, `privacy_v1/*`, `tests/evaluation/startup/*`, `tests/e2e/test_startup_case_e2e.py` |

## Verification Gates

- **Gate C — Startup ingest/privacy:** unsafe archives/MIME are blocked, damaged files are quarantined, no-network mode is enforced, Gate 2 preview contains categories but no raw sensitive values, and trace/tool/retrieval privacy leak count is zero.
- **Gate D — Startup vertical:** `startup_synthetic_saas_v1` completes offline; all four planted critical contradictions are found; calculations, claims, report sections, trace completeness, and latency thresholds pass.
- **Gate E — Combined regression:** both Public and Startup suites pass; shared schemas remain compatible; both modes render immutable snapshots.

---

### Task 1: Lock Stage 1B Dependency Gates and Verify Stage 1A Contracts

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `scripts/smoke_stage1b.ps1`
- Create: `tests/contract/test_stage1b_prerequisites.py`

**Interfaces:**
- Produces: separately installable light-ingest, OCR, Presidio, and Docling groups plus a contract test proving the Stage 1A core is present.
- Consumes: Stage 1A package and Gate B artifacts.

- [ ] **Step 1: Write the failing prerequisite contract test**

```python
# tests/contract/test_stage1b_prerequisites.py
def test_stage1a_shared_contracts_are_available():
    from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
    from due_diligence_agent.domain.evidence.models import EvidenceFact, Calculation
    from due_diligence_agent.domain.reports.models import ReportSnapshot
    from due_diligence_agent.domain.metrics.engine import MetricEngine
    from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
    from due_diligence_agent.workflows.shared.node_result import NodeResult

    assert all([Artifact, SourceLocator, EvidenceFact, Calculation, ReportSnapshot, MetricEngine, DataEgressPolicy, NodeResult])
```

- [ ] **Step 2: Run Stage 1A Gate B and the prerequisite test**

Run:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas --group dev pytest tests/evaluation/test_public_us_frozen_v1.py tests/contract/test_stage1b_prerequisites.py -v
```

Expected: PASS before modifying dependencies. If Gate B fails, repair Stage 1A first and restart this task.

- [ ] **Step 3: Add isolated Stage 1B dependency groups**

```toml
# append under [dependency-groups] in pyproject.toml
stage1b-light-ingest = [
  { include-group = "stage1a" },
  "openpyxl>=3.1.5,<4",
  "python-docx>=1.2,<2",
  "pymupdf>=1.27,<2",
  "pdfplumber>=0.11.10,<0.12",
  "pillow>=12.3,<13",
]
stage1b-ocr-tesseract = ["pytesseract>=0.3.13,<0.4"]
stage1b-redaction-presidio = [
  "presidio-analyzer>=2.2.364,<2.3",
  "presidio-anonymizer>=2.2.364,<2.3",
]
stage1b-docling = ["docling>=2.115,<3"]
stage1b = [
  { include-group = "stage1b-light-ingest" },
  { include-group = "stage1a-rag-local" },
]
```

Docling, Presidio, and OCR remain adapter-gated; the light ingest group must work without them.

- [ ] **Step 4: Lock and smoke the light ingest group**

Run:

```powershell
uv lock --python 3.12
uv sync --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local python -c "import openpyxl,docx,fitz,pdfplumber; from PIL import Image; print('stage1b light ingest ok')"
uv run --python 3.13 --no-default-groups --group stage1b python -c "import openpyxl,docx,fitz,pdfplumber; from PIL import Image; print('py313 stage1b light ingest ok')"
```

Expected: Python 3.12 prints `stage1b light ingest ok`. The non-blocking Python 3.13 smoke prints `py313 stage1b light ingest ok`; if a native dependency lacks a compatible wheel, record it and keep Python 3.12 as the Gate D/E runtime.

- [ ] **Step 5: Add a staged smoke script**

`scripts/smoke_stage1b.ps1` runs the light ingest import first, then checks `tesseract --version`, Presidio, and Docling only when their named switches are supplied. It sets `HF_HUB_OFFLINE=1` and rejects unexpected model downloads during the no-network smoke.

- [ ] **Step 6: Commit dependency gates**

```powershell
git add pyproject.toml uv.lock scripts/smoke_stage1b.ps1 tests/contract/test_stage1b_prerequisites.py
git commit -m "chore: gate startup parser dependencies"
```

---

### Task 2: Implement Data-Room Inventory, Archive Safety, and Quarantine

**Files:**
- Create: `src/due_diligence_agent/domain/artifacts/safety.py`
- Create: `src/due_diligence_agent/domain/artifacts/startup_inventory.py`
- Create: `src/due_diligence_agent/ports/archive.py`
- Create: `src/due_diligence_agent/adapters/documents/archive_inspector.py`
- Create: `src/due_diligence_agent/application/services/data_room_service.py`
- Test: `tests/security/test_archive_safety.py`

**Interfaces:**
- Produces: `SafetyLimits`, `SafetyScanResult`, `DataRoomInventory`, `ArchiveInspectorPort`, and `DataRoomService.ingest()`.
- Consumes: Stage 1A `ArtifactStore`, repositories, audit, and `Artifact` model.

- [ ] **Step 1: Write failing hostile-archive tests**

```python
# tests/security/test_archive_safety.py
def test_zip_slip_member_is_quarantined(data_room_service, zip_slip_fixture):
    inventory = data_room_service.ingest("case-1", [zip_slip_fixture])
    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "zip_slip"


def test_archive_bomb_is_rejected_before_extraction(data_room_service, archive_bomb_fixture):
    inventory = data_room_service.ingest("case-1", [archive_bomb_fixture])
    assert inventory.quarantined[0].reason == "decompression_ratio_exceeded"
    assert inventory.unpacked_bytes == 0
```

- [ ] **Step 2: Run tests and confirm safety modules are missing**

Run: `uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/security/test_archive_safety.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define exact safety limits and scan results**

```python
# src/due_diligence_agent/domain/artifacts/safety.py
from pydantic import BaseModel, Field


class SafetyLimits(BaseModel):
    max_files: int = Field(default=100, ge=1)
    max_file_bytes: int = Field(default=250 * 1024 * 1024, ge=1)
    max_unpacked_bytes: int = Field(default=1024 * 1024 * 1024, ge=1)
    max_archive_depth: int = Field(default=2, ge=0, le=2)
    max_decompression_ratio: float = Field(default=100.0, gt=0, le=100.0)
    allowed_media_types: frozenset[str] = frozenset({
        "application/pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/png", "image/jpeg", "application/zip",
    })
```

- [ ] **Step 4: Implement safe inspection and content-addressed ingest**

Resolve each ZIP member against a dedicated temporary extraction root and reject paths that escape it. Inspect header signatures and Office ZIP internals rather than trusting extensions. Enforce file count, individual size, cumulative unpacked size, depth, and ratio before writing. Accepted bytes go to Stage 1A `ArtifactStore`; suspicious inputs go to `.local/quarantine/<case_id>/` with hash and reason. Source files are never modified.

- [ ] **Step 5: Run archive, MIME, and quota tests**

Run: `uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/security/test_archive_safety.py -v`

Expected: PASS for zip-slip, archive bomb, nested depth, unsupported MIME, over-quota, damaged ZIP, and safe mixed archive.

- [ ] **Step 6: Commit safe data-room ingest**

```powershell
git add src/due_diligence_agent/domain/artifacts src/due_diligence_agent/ports/archive.py src/due_diligence_agent/adapters/documents/archive_inspector.py src/due_diligence_agent/application/services/data_room_service.py tests/security/test_archive_safety.py
git commit -m "feat: add safe startup data room inventory"
```

---

### Task 3: Add Local PDF, DOCX, Image, and OCR Parsing

**Files:**
- Create: `src/due_diligence_agent/domain/documents/models.py`
- Create: `src/due_diligence_agent/ports/parsers/__init__.py`
- Create: `src/due_diligence_agent/ports/parsers/document_parser.py`
- Create: `src/due_diligence_agent/adapters/documents/pdf_parser.py`
- Create: `src/due_diligence_agent/adapters/documents/docx_parser.py`
- Create: `src/due_diligence_agent/adapters/documents/image_ocr.py`
- Create: `src/due_diligence_agent/adapters/documents/docling_parser.py`
- Create: `src/due_diligence_agent/adapters/documents/no_network_guard.py`
- Create: `src/due_diligence_agent/application/services/startup_parsing_service.py`
- Test: `tests/parsing/test_document_parsers.py`

**Interfaces:**
- Produces: `ParsedDocument`, `ParsedPage`, `ParsedTable`, `TextBlock`, `DocumentParserPort`, and parser selection.
- Consumes: accepted `Artifact` records and local artifact bytes from Task 2.

- [ ] **Step 1: Write failing locator and confidence tests**

```python
# tests/parsing/test_document_parsers.py
def test_scanned_value_is_not_verified_when_ocr_confidence_is_low(parsing_service, low_confidence_scan):
    parsed = parsing_service.parse(low_confidence_scan, no_network=True)
    value = parsed.pages[0].text_blocks[0]
    assert value.locator.kind == "image_region"
    assert value.confidence < Decimal("0.80")
    assert value.verification_status == "needs_review"


def test_docx_paragraph_has_stable_locator(parsing_service, sample_docx):
    parsed = parsing_service.parse(sample_docx, no_network=True)
    assert parsed.text_blocks[0].locator.value == "paragraph:1"
```

- [ ] **Step 2: Run tests and confirm parser contracts are missing**

Run: `uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/parsing/test_document_parsers.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define a parser-neutral document model**

```python
class TextBlock(BaseModel):
    text_ref: str
    content_hash: str
    locator: SourceLocator
    confidence: Decimal
    verification_status: Literal["candidate", "needs_review", "verified"]


class ParsedDocument(BaseModel):
    artifact_id: UUID
    pages: list[ParsedPage]
    tables: list[ParsedTable]
    text_blocks: list[TextBlock]
    parser_name: str
    parser_version: str
    confidence: Decimal
```

Raw text is stored locally by reference; workflow state and traces receive only IDs, hashes, counts, and confidence.

- [ ] **Step 4: Implement no-network parsers and OCR adapter**

Use PyMuPDF first for PDF text/page coordinates and pdfplumber for table fallback. Use python-docx for stable paragraph/table locators. Pillow validates and normalizes images. `TesseractOcrAdapter` is enabled only when the binary smoke succeeds; otherwise image/scanned pages return `parser_unavailable` without external OCR fallback. `DoclingDocumentParser` is imported and registered lazily only when the optional dependency group passes, its model files are present in the recorded local cache, and the no-network smoke succeeds; the light parser path remains the Gate C baseline. `NoNetworkGuard` fails tests if a parser opens a socket or attempts model-hub access.

- [ ] **Step 5: Run light parsing tests, then optional OCR smoke**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/parsing/test_document_parsers.py -v
uv sync --no-default-groups --group stage1b --group stage1b-ocr-tesseract
tesseract --version
uv run --no-default-groups --group stage1b --group stage1b-ocr-tesseract python -c "import pytesseract; print('ocr adapter ok')"
uv sync --no-default-groups --group stage1b --group stage1b-docling
uv run --no-default-groups --group stage1b --group stage1b-docling python -c "from docling.document_converter import DocumentConverter; print('docling adapter import ok')"
```

Expected: light parsers PASS; optional OCR reports its installed binary version; optional Docling imports only when explicitly selected. Before registering Docling in the application, run the same parser fixture with model files pre-cached and network blocked; any attempted download leaves the adapter disabled.

- [ ] **Step 6: Commit local document parsing**

```powershell
git add src/due_diligence_agent/domain/documents src/due_diligence_agent/ports/parsers src/due_diligence_agent/adapters/documents src/due_diligence_agent/application/services/startup_parsing_service.py tests/parsing/test_document_parsers.py
git commit -m "feat: add offline startup document parsing"
```

---

### Task 4: Parse XLSX/CSV into Normalized Tables and Cell-Level Evidence

**Files:**
- Create: `src/due_diligence_agent/adapters/documents/spreadsheet_parser.py`
- Create: `src/due_diligence_agent/application/services/table_normalization_service.py`
- Create: `src/due_diligence_agent/domain/documents/tabular.py`
- Test: `tests/parsing/test_spreadsheets.py`

**Interfaces:**
- Produces: `NormalizedTable`, cell-level `SourceLocator`, typed values, units/period hints, and DuckDB snapshot references.
- Consumes: `DocumentParserPort`, local artifact storage, and Stage 1A DuckDB/ledger services.

- [ ] **Step 1: Write failing spreadsheet tests**

```python
# tests/parsing/test_spreadsheets.py
def test_xlsx_value_preserves_sheet_and_cell_locator(spreadsheet_parser, financial_model_xlsx):
    table = spreadsheet_parser.parse(financial_model_xlsx, no_network=True).tables[0]
    revenue = table.find(label="Revenue", period="2025")
    assert revenue.locator.kind == "xlsx_cell"
    assert revenue.locator.value == "P&L!C12"
    assert revenue.value == Decimal("1800000")


def test_formula_without_cached_value_is_not_invented(spreadsheet_parser, formula_only_xlsx):
    cell = spreadsheet_parser.parse(formula_only_xlsx, no_network=True).tables[0].cells[0]
    assert cell.value is None
    assert cell.status == "insufficient_data"
```

- [ ] **Step 2: Run tests and confirm parser is missing**

Run: `uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/parsing/test_spreadsheets.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define normalized table contracts**

```python
class NormalizedCell(BaseModel):
    row: int
    column: int
    label: str | None
    period: str | None
    value: Decimal | str | date | None
    unit: str | None
    locator: SourceLocator
    status: Literal["candidate", "insufficient_data", "verified"]


class NormalizedTable(BaseModel):
    artifact_id: UUID
    name: str
    cells: list[NormalizedCell]
    snapshot_hash: str
```

- [ ] **Step 4: Implement safe XLSX and CSV parsing**

Load XLSX with `data_only=True`, never execute macros, reject XLSM, preserve sheet/cell locators, and emit `insufficient_data` for formulas lacking cached values. Detect CSV encoding from an allowlist, cap rows/columns by configuration, preserve row/column locators, and write normalized snapshots to DuckDB. Convert candidate financial cells into `EvidenceFact` only after period/unit validation.

- [ ] **Step 5: Run parser and public regression tests**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/parsing/test_spreadsheets.py tests/unit/metrics/test_public_metrics.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit tabular parsing**

```powershell
git add src/due_diligence_agent/adapters/documents/spreadsheet_parser.py src/due_diligence_agent/application/services/table_normalization_service.py src/due_diligence_agent/domain/documents/tabular.py tests/parsing/test_spreadsheets.py
git commit -m "feat: normalize startup spreadsheets"
```

---

### Task 5: Classify Sensitivity, Redact Locally, and Enforce No-Network Privacy

**Files:**
- Create: `src/due_diligence_agent/domain/privacy/models.py`
- Create: `src/due_diligence_agent/adapters/privacy/rules_redactor.py`
- Create: `src/due_diligence_agent/adapters/privacy/presidio_redactor.py`
- Create: `src/due_diligence_agent/application/services/startup_privacy_service.py`
- Test: `tests/privacy/test_startup_redaction.py`
- Fixtures: `tests/fixtures/privacy_v1/*`

**Interfaces:**
- Produces: `SensitivitySummary`, `RedactedContext`, `DisclosurePreview`, field/cell-level labels, and derived-data classification.
- Consumes: parsed documents/tables and Stage 1A `DataEgressPolicy`/trace sanitizer.

- [ ] **Step 1: Write failing privacy-precedence tests**

```python
# tests/privacy/test_startup_redaction.py
from due_diligence_agent.domain.common import SensitivityClass


def test_highest_sensitivity_wins_for_mixed_table(startup_privacy_service, mixed_customer_table):
    summary = startup_privacy_service.classify(mixed_customer_table)
    assert summary.overall_class == SensitivityClass.RESTRICTED
    assert summary.field_classes["email"] == SensitivityClass.RESTRICTED


def test_disclosure_preview_contains_categories_not_values(startup_privacy_service, pii_document):
    preview = startup_privacy_service.build_preview(pii_document)
    serialized = preview.model_dump_json()
    assert "john@example.com" not in serialized
    assert preview.category_counts["email"] == 1
```

- [ ] **Step 2: Run tests and confirm privacy adapters are missing**

Run: `uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/privacy/test_startup_redaction.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define sensitivity and redaction outputs**

```python
class SensitivitySummary(BaseModel):
    overall_class: SensitivityClass
    field_classes: dict[str, SensitivityClass]
    category_counts: dict[str, int]
    policy_version: str


class RedactedContext(BaseModel):
    fragment_ids: list[UUID]
    local_text_refs: list[str]
    sensitivity: SensitivityClass
    redaction_counts: dict[str, int]
    content_hash: str
```

`domain/privacy/models.py` imports and reuses `SensitivityClass` from the Stage 1A `domain/common.py`; it must not define a second enum. Persisted artifacts, evidence, chunks, approvals, trace metadata, and report sections therefore share the same serialized sensitivity values.

- [ ] **Step 4: Implement deterministic rules and optional Presidio enrichment**

Rules detect emails, phones, banking/IBAN-like values, authorization/secret patterns, IDs, and named fields. `PresidioRedactor` may add detections after its local NLP model is explicitly cached; it cannot reduce a deterministic sensitivity classification. Redacted fragments stay local by reference. Re-identification checks block export when remaining quasi-identifiers are too specific.

- [ ] **Step 5: Prove no-network mode and zero trace leakage**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/privacy/test_startup_redaction.py tests/privacy/test_ai_egress.py tests/unit/observability -v
uv sync --no-default-groups --group stage1b --group stage1b-redaction-presidio
uv run --no-default-groups --group stage1b --group stage1b-redaction-presidio python -c "import presidio_analyzer,presidio_anonymizer; print('presidio adapter ok')"
```

Expected: privacy leak count zero across traces, tool payload mocks, retrieved chunks, exception strings, and disclosure preview.

- [ ] **Step 6: Commit startup privacy classification**

```powershell
git add src/due_diligence_agent/domain/privacy src/due_diligence_agent/adapters/privacy src/due_diligence_agent/application/services/startup_privacy_service.py tests/privacy/test_startup_redaction.py tests/fixtures/privacy_v1
git commit -m "feat: add startup sensitivity and redaction"
```

---

### Task 6: Build Startup Claim Extraction and Claim–Evidence Matrix

**Files:**
- Create: `src/due_diligence_agent/domain/evidence/startup_claims.py`
- Create: `src/due_diligence_agent/application/services/claim_extraction_service.py`
- Create: `src/due_diligence_agent/application/services/claim_evidence_service.py`
- Create: `src/due_diligence_agent/application/services/startup_retrieval_service.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/claims.py`
- Test: `tests/unit/evidence/test_startup_claims.py`
- Test: `tests/integration/retrieval/test_startup_retrieval.py`

**Interfaces:**
- Produces: `StartupClaim`, `ClaimEvidenceLink`, `ClaimEvidenceMatrix`, extraction schema, and status resolution.
- Consumes: Stage 1A Evidence Ledger/retrieval/LLM gateway plus redacted Startup contexts.

- [ ] **Step 1: Write failing claim-status tests**

```python
# tests/unit/evidence/test_startup_claims.py
def test_claim_is_contradicted_when_primary_calculation_disagrees(matrix_service, deck_claim, workbook_fact):
    matrix = matrix_service.build([deck_claim], [workbook_fact])
    row = matrix.rows[0]
    assert row.status == ClaimStatus.CONTRADICTED
    assert row.links[0].relation == "contradicts"


def test_unsupported_critical_claim_cannot_be_reported_as_fact(matrix_service, unsupported_claim):
    row = matrix_service.build([unsupported_claim], []).rows[0]
    assert row.status == ClaimStatus.UNSUPPORTED
    assert row.executive_summary_eligible is False
```

```python
# tests/integration/retrieval/test_startup_retrieval.py
def test_external_context_excludes_restricted_chunks(startup_retrieval_service, mixed_sensitivity_chunks):
    results = startup_retrieval_service.search_for_destination(
        "customer concentration",
        destination="external_llm",
        chunks=mixed_sensitivity_chunks,
        k=5,
    )

    assert results
    assert all(result.sensitivity != "restricted" for result in results)
    assert all(result.text is None for result in results)
```

- [ ] **Step 2: Run tests and confirm claim models are absent**

Run: `uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/unit/evidence/test_startup_claims.py tests/integration/retrieval/test_startup_retrieval.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define typed claims and evidence links**

```python
class ClaimStatus(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT_DATA = "insufficient_data"


class ClaimEvidenceLink(BaseModel):
    claim_id: UUID
    evidence_fact_id: UUID | None
    calculation_id: UUID | None
    relation: Literal["supports", "partially_supports", "contradicts", "missing"]
    confidence: Decimal
```

- [ ] **Step 4: Implement extraction and deterministic status resolution**

The structured extraction schema requires claim text, category, source artifact, locator, criticality, and evidence query. It runs only after Gate 2 if an external model is used; fixture/local adapters remain available. `StartupRetrievalService` converts parsed text/table blocks into stable chunks carrying artifact ID, local text reference, content hash, source locator, parser confidence, and sensitivity. It reuses the Stage 1A `EvidenceIndexPort`, but filters candidates through `DataEgressPolicy` before resolving local text for an external destination. Search results passed between nodes contain IDs, locators, scores, and sensitivity only. `ClaimEvidenceService` retrieves candidates, applies source priority, links calculations, and resolves status deterministically. It writes first-class `Contradiction` records for ARR, margin, runway, customer count, or any incompatible normalized value.

- [ ] **Step 5: Run claim and Evidence Ledger tests**

Run: `uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/unit/evidence/test_startup_claims.py tests/integration/retrieval/test_startup_retrieval.py tests/unit/evidence/test_ledger.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the claim–evidence matrix**

```powershell
git add src/due_diligence_agent/domain/evidence/startup_claims.py src/due_diligence_agent/application/services/claim_* src/due_diligence_agent/application/services/startup_retrieval_service.py src/due_diligence_agent/workflows/startup/nodes/claims.py tests/unit/evidence/test_startup_claims.py tests/integration/retrieval/test_startup_retrieval.py
git commit -m "feat: add startup claim evidence matrix"
```

---

### Task 7: Add Versioned Startup and Unit-Economics Metrics

**Files:**
- Create: `src/due_diligence_agent/domain/metrics/startup.py`
- Create: `src/due_diligence_agent/application/services/startup_metric_service.py`
- Test: `tests/unit/metrics/test_startup_metrics.py`
- Golden: `tests/golden/startup_synthetic_saas_v1/metrics.json`

**Interfaces:**
- Produces: startup `MetricDefinition` registrations and `StartupMetricService.calculate_available()`.
- Consumes: Stage 1A `MetricEngine` and normalized evidence IDs from spreadsheets/documents.

- [ ] **Step 1: Write failing runway and missing-input tests**

```python
# tests/unit/metrics/test_startup_metrics.py
from decimal import Decimal


def test_runway_is_calculated_from_cash_and_normalized_monthly_burn(startup_metric_service, facts):
    result = startup_metric_service.calculate(
        "runway_months",
        facts(cash="950000", monthly_net_burn="100000"),
    )
    assert result.value == Decimal("9.5")
    assert result.formula_version == "runway_months@1"


def test_ltv_without_explicit_model_is_insufficient_data(startup_metric_service, facts):
    result = startup_metric_service.calculate("ltv", facts(arpa="100", churn="0.05"), assumptions={})
    assert result.status == "insufficient_data"
```

- [ ] **Step 2: Run tests and confirm definitions are absent**

Run: `uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/unit/metrics/test_startup_metrics.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Register exact startup formulas**

Register MRR, ARR, period growth, gross margin, net burn, runway, CAC, explicit-model LTV, LTV/CAC, CAC payback, logo/revenue churn, NRR, burn multiple, conditional Rule of 40, and cohort retention. Each definition names inputs, units, valid business/stage conditions, formula version, and display rounding.

```python
RUNWAY = MetricDefinition(
    name="runway_months", version="1", required_inputs=("cash", "monthly_net_burn"), unit="months",
    formula=lambda v: v["cash"] / v["monthly_net_burn"],
)
```

- [ ] **Step 4: Enforce comparable periods, units, and missing-data results**

`StartupMetricService` rejects mixed currencies without an explicit FX fact, non-monthly burn without normalization, incompatible cohort periods, zero/negative denominators, and conditional metrics outside their applicability rules. It returns a typed `Calculation` with evidence IDs or `insufficient_data`, never an exception-derived guess.

- [ ] **Step 5: Run startup and public metric suites**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/unit/metrics/test_startup_metrics.py tests/unit/metrics/test_public_metrics.py -v
```

Expected: PASS with `Decimal` tolerance `1e-6`.

- [ ] **Step 6: Commit startup metrics**

```powershell
git add src/due_diligence_agent/domain/metrics/startup.py src/due_diligence_agent/application/services/startup_metric_service.py tests/unit/metrics/test_startup_metrics.py tests/golden/startup_synthetic_saas_v1/metrics.json
git commit -m "feat: add startup unit economics metrics"
```

---

### Task 8: Add HITL Gate 2 for Startup Disclosure Approval

**Files:**
- Create: `src/due_diligence_agent/domain/approvals/startup_disclosure.py`
- Create: `src/due_diligence_agent/application/services/startup_disclosure_service.py`
- Create: `src/due_diligence_agent/presentation/streamlit/pages/startup_disclosure.py`
- Test: `tests/graph/test_startup_disclosure_gate.py`

**Interfaces:**
- Produces: immutable `StartupDisclosureApproval`, shared `DisclosureScope`, redacted disclosure preview, approval audit event, and a resumable Gate 2 decision.
- Consumes: Stage 1A `ApprovalRepository`, `DataEgressPolicy`, audit writer, checkpoint store, and sensitivity summary from Task 5.

- [ ] **Step 1: Write failing tests for the default-deny gate**

```python
# tests/graph/test_startup_disclosure_gate.py
import pytest

from due_diligence_agent.application.policies.data_egress import DataEgressDenied
from due_diligence_agent.domain.common import SensitivityClass


@pytest.mark.asyncio
async def test_external_provider_is_not_called_without_gate_2_approval(
    startup_disclosure_service,
    gateway,
    external_llm_spy,
    classified_case,
    risk_output_schema,
):
    scope = startup_disclosure_service.resolve_scope(classified_case)

    assert scope is None
    with pytest.raises(DataEgressDenied):
        await gateway.complete_structured(
            task="startup_risk",
            context=classified_case.redacted_fragments,
            schema=risk_output_schema,
            disclosure_scope=scope,
        )
    external_llm_spy.assert_not_called()


def test_new_higher_sensitivity_invalidates_prior_approval(
    startup_disclosure_service,
    approved_confidential_case,
):
    approved_confidential_case.detected_classes.add(SensitivityClass.RESTRICTED)

    scope = startup_disclosure_service.resolve_scope(approved_confidential_case)

    assert scope is None
    assert startup_disclosure_service.last_invalidation_reason == "sensitivity_scope_changed"


def test_preview_contains_counts_but_not_raw_values(
    startup_disclosure_service,
    classified_case_with_secrets,
):
    preview = startup_disclosure_service.build_preview(classified_case_with_secrets)

    assert preview.category_counts["credential_like"] == 1
    assert "sk-live-secret" not in preview.model_dump_json()
```

- [ ] **Step 2: Run the gate tests and confirm the approval model is absent**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/graph/test_startup_disclosure_gate.py -v
```

Expected: FAIL on import.

- [ ] **Step 3: Define the immutable approval contract**

```python
# src/due_diligence_agent/domain/approvals/startup_disclosure.py
from typing import Literal

from pydantic import ConfigDict

from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.common import SensitivityClass


class StartupDisclosureApproval(Approval):
    model_config = ConfigDict(frozen=True)

    gate: Literal["startup_disclosure"] = "startup_disclosure"
    allowed_classes: frozenset[SensitivityClass]
    external_llm_allowed: bool
    approved_redaction_policy_version: str
```

Persist the approval with the exact sensitivity set, redaction-policy version, actor, UTC `decided_at`, `data_revision`, and content hash. Reusing an approval requires all of those scope fields to match the current classified case. Reject any approval whose `allowed_classes` contains `RESTRICTED`; that class is non-exportable by invariant.

- [ ] **Step 4: Implement default-deny authorization and audit behavior**

`StartupDisclosureService.resolve_scope()` validates the approval against the current case revision, detected sensitivity set, and redaction-policy version, then returns the shared Stage 1A `DisclosureScope` or `None`. It never calls a provider. The LLM Gateway passes that scope and the minimized fragments to `DataEgressPolicy.evaluate()` and receives the canonical `EgressDecision`; the workflow maps its reason to `approved_external`, `local_deterministic_only`, or `approval_required`. The service records `startup_disclosure.previewed`, `startup_disclosure.approved`, `startup_disclosure.denied`, or `startup_disclosure.invalidated` in the durable audit log without raw field values.

The Streamlit page shows:

- artifact counts and MIME groups;
- detected sensitivity classes and category counts;
- redaction-policy version and an explanation of what may leave the machine;
- explicit allow/deny controls and an optional comment;
- no document excerpts, PII, banking values, credentials, cap-table values, or customer names.

- [ ] **Step 5: Run Gate 2, privacy, and public egress tests**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/graph/test_startup_disclosure_gate.py tests/privacy/test_startup_redaction.py tests/privacy/test_ai_egress.py -v
```

Expected: PASS; external provider spy has zero calls for missing or denied approval, and the preview contains no seeded secret.

- [ ] **Step 6: Run Gate C before building the Startup graph**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/security/test_archive_safety.py tests/parsing/test_document_parsers.py tests/parsing/test_spreadsheets.py tests/privacy/test_startup_redaction.py tests/integration/retrieval/test_startup_retrieval.py tests/graph/test_startup_disclosure_gate.py tests/privacy/test_ai_egress.py tests/unit/observability -v
```

Expected: PASS; unsafe inputs are blocked/quarantined, parser no-network tests pass, low-confidence OCR is not verified, restricted chunks never reach external context, Gate 2 is default-deny and invalidates on sensitivity changes, and trace/privacy leak count is zero. Task 9 does not start until this Gate C command is green.

- [ ] **Step 7: Commit Gate 2 and Gate C evidence**

```powershell
git add src/due_diligence_agent/domain/approvals/startup_disclosure.py src/due_diligence_agent/application/services/startup_disclosure_service.py src/due_diligence_agent/presentation/streamlit/pages/startup_disclosure.py tests/graph/test_startup_disclosure_gate.py
git commit -m "feat: add startup disclosure approval gate"
```

---

### Task 9: Build the Resumable Startup LangGraph Workflow

**Files:**
- Create: `src/due_diligence_agent/workflows/startup/state.py`
- Create: `src/due_diligence_agent/workflows/startup/plan.py`
- Create: `src/due_diligence_agent/workflows/startup/graph.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/ingest.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/parse.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/disclosure.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/evidence.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/metrics.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/financial.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/risk.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/market.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/reflexion.py`
- Create: `src/due_diligence_agent/workflows/startup/nodes/report.py`
- Create: `src/due_diligence_agent/application/services/startup_analysis_service.py`
- Test: `tests/graph/test_startup_workflow.py`

**Interfaces:**
- Produces: compiled, checkpointed `startup_data_room` graph and `StartupAnalysisService`.
- Consumes: Task 2–8 services plus shared Stage 1A planner contract, `NodeResult`, HITL commands, repositories, durable audit, tracing, report builder, and SQLite checkpoint store.

- [ ] **Step 1: Write failing pause, resume, and restart tests**

```python
# tests/graph/test_startup_workflow.py
from langgraph.types import Command


def test_startup_graph_pauses_at_disclosure_and_resumes(
    startup_graph,
    startup_case_input,
    gate_2_approval,
):
    config = {"configurable": {"thread_id": "startup-case-1"}}

    paused = startup_graph.invoke(startup_case_input, config)
    assert paused["status"] == "approval_required"
    assert paused["pending_gate"] == "startup_disclosure"

    resumed = startup_graph.invoke(Command(resume=gate_2_approval.model_dump()), config)
    assert resumed["pending_gate"] != "startup_disclosure"


def test_checkpoint_can_resume_after_process_restart(
    startup_graph_factory,
    startup_case_input,
    sqlite_checkpoint_path,
    gate_2_approval,
):
    config = {"configurable": {"thread_id": "restart-case"}}
    startup_graph_factory(sqlite_checkpoint_path).invoke(startup_case_input, config)

    restarted = startup_graph_factory(sqlite_checkpoint_path)
    result = restarted.invoke(Command(resume=gate_2_approval.model_dump()), config)

    assert result["case_id"] == startup_case_input["case_id"]
    assert result["run_id"] == startup_case_input["run_id"]
    assert result["correlation_id"] == startup_case_input["correlation_id"]
```

- [ ] **Step 2: Run the workflow tests and confirm the graph is absent**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/graph/test_startup_workflow.py -v
```

Expected: FAIL on import.

- [ ] **Step 3: Define an ID-only checkpoint state**

```python
# src/due_diligence_agent/workflows/startup/state.py
from typing import TypedDict


class StartupWorkflowState(TypedDict):
    case_id: str
    run_id: str
    correlation_id: str
    plan_id: str | None
    inventory_id: str | None
    parsed_artifact_ids: list[str]
    sensitivity_summary_id: str | None
    approval_ids: list[str]
    evidence_fact_ids: list[str]
    startup_claim_ids: list[str]
    calculation_ids: list[str]
    finding_ids: list[str]
    contradiction_ids: list[str]
    report_snapshot_id: str | None
    reflexion_round: int
    pending_gate: str | None
    status: str
    error_code: str | None
```

Checkpoint state stores IDs and small control values only. Parsed text, tables, retrieved chunks, redacted context, raw LLM payloads, and report bodies remain in their repositories or content-addressed artifact storage.

- [ ] **Step 4: Implement plan-and-execute routing**

Create a versioned `StartupAnalysisPlan` using the shared `AnalysisPlan`/`PlanStep` contract. Its node registry is exactly `ingest`, `parse`, `classify_redact`, `disclosure`, `evidence`, `claims`, `metrics`, `financial_analysis`, `risk_analysis`, `market_analysis`, `reflexion`, and `report`; LLM output may order or skip only conditionally available analytical modules and cannot introduce arbitrary tools. The compiled flow is:

```text
create case
  -> ingest and safety scan
  -> local parse/OCR/table extraction
  -> classify and redact
  -> Gate 2 disclosure approval
  -> versioned analysis plan
  -> evidence extraction and claim–evidence matrix
  -> deterministic startup metrics
  -> specialized financial, risk, and market/competition analysis
  -> bounded Reflexion
  -> Gate 3 review/exclusions
  -> immutable report snapshot
  -> Gate 4 final approval
  -> JSON/HTML/PDF rendering
```

If disclosure is denied, the graph takes the local deterministic branch; any LLM-dependent step returns `blocked_by_policy` with an actionable HITL item rather than making an external call. Every node returns the shared `NodeResult[T]`, emits a durable audit event, and opens a sanitized span with status, duration, input/output IDs, fallback marker, and schema version. Reuse the Stage 1A retry policy unchanged: only typed retryable failures, no more than three node attempts, and no retries for privacy, budget, schema, unsupported-content, or deterministic validation failures.

- [ ] **Step 5: Enforce bounded Reflexion and dependency invalidation**

The Reflexion node performs at most two rounds and checks unsupported critical claims, source conflicts, calculation mismatches, stale evidence, missing citations, and policy violations. It can request only registered recovery actions: retrieve more local evidence, rerun an affected calculation, downgrade a finding, create a contradiction, or add a review question.

Gate 3 exclusion invalidates all downstream calculations, findings, contradictions, and report snapshots that depend on excluded evidence. The graph recomputes only affected nodes from stored dependency edges and records the invalidation chain.

- [ ] **Step 6: Add workflow invariants and provider-denial tests**

Extend `tests/graph/test_startup_workflow.py` to prove:

- every executed node has one durable audit event;
- every LLM span is sanitized;
- denied Gate 2 approval produces zero external calls;
- Reflexion stops by round two even when a contradiction remains unresolved;
- excluding a spreadsheet cell invalidates its dependent metric and finding;
- a simulated restart resumes from SQLite without repeating completed ingest/parsing nodes;
- an unexpected node exception becomes typed workflow failure and never leaks document content.

- [ ] **Step 7: Run workflow, security, and shared public graph suites**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/graph/test_startup_workflow.py tests/graph/test_public_collection_graph.py tests/privacy/test_startup_redaction.py tests/unit/observability -v
```

Expected: PASS; checkpoint, denial, invalidation, Reflexion, trace, and audit assertions all pass.

- [ ] **Step 8: Commit the Startup graph**

```powershell
git add src/due_diligence_agent/workflows/startup src/due_diligence_agent/application/services/startup_analysis_service.py tests/graph/test_startup_workflow.py
git commit -m "feat: orchestrate startup due diligence workflow"
```

---

### Task 10: Extend the Shared Report and Streamlit UI for Startup Cases

**Files:**
- Create: `src/due_diligence_agent/adapters/reports/templates/startup_report.html.j2`
- Create: `src/due_diligence_agent/application/services/startup_report_sections.py`
- Create: `src/due_diligence_agent/presentation/streamlit/pages/startup_case.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/data_room_inventory.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/claim_evidence_matrix.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/startup_metrics.py`
- Modify: `src/due_diligence_agent/presentation/streamlit/app.py`
- Modify: `src/due_diligence_agent/presentation/cli.py`
- Modify: `src/due_diligence_agent/bootstrap/container.py`
- Test: `tests/e2e/test_startup_report.py`

**Interfaces:**
- Produces: Startup sections in the shared canonical `ReportSnapshot`, Startup case/progress/evidence screens, CLI commands `render-fixture`/`smoke-ui`, and Gate 4-controlled JSON/HTML/PDF downloads.
- Consumes: Startup workflow IDs, shared repositories, report builder/renderers, chart renderer, approval service, and immutable snapshot contract.

- [ ] **Step 1: Write failing report completeness and approval tests**

```python
# tests/e2e/test_startup_report.py
def test_startup_report_contains_required_sections(startup_report_service, approved_startup_state):
    snapshot = startup_report_service.freeze(approved_startup_state)

    assert snapshot.mode == "startup"
    assert set(snapshot.sections) >= {
        "metadata",
        "executive_summary",
        "investment_thesis",
        "counter_thesis",
        "company_profile",
        "evidence_coverage",
        "financial_metrics",
        "risk_matrix",
        "missing_data",
        "next_steps",
        "methodology",
        "decision_owner",
        "claim_evidence_matrix",
        "business_model",
        "traction",
        "unit_economics",
        "burn_and_runway",
        "market_and_competition",
        "team_and_governance",
        "questions_for_management",
        "contradictions",
        "source_and_calculation_appendix",
        "disclaimer",
    }


def test_gate_4_rejection_blocks_final_pdf(startup_report_service, rejected_startup_state, tmp_path):
    result = startup_report_service.render(rejected_startup_state, tmp_path)

    assert result.final_pdf is None
    assert result.draft_html.exists()
    assert result.draft_json.exists()
```

- [ ] **Step 2: Run the report tests and confirm Startup sections are absent**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/e2e/test_startup_report.py -v
```

Expected: FAIL because Startup report assembly is not registered.

- [ ] **Step 3: Extend the canonical snapshot without forking the schema**

`StartupReportSections` maps Startup claims, metrics, findings, contradictions, questions, charts, and source locators into the Stage 1A mode-extension field. It never reads parser-specific objects. The cap-table section is included only when explicit cap-table evidence is available and is marked analytical, not legal advice. Every material number links to a `Calculation`; every critical narrative statement links to evidence, contradiction, or `insufficient_data`.

Required report sections are:

- Executive Summary with confidence and unresolved critical questions;
- claim–evidence matrix;
- business model and monetization;
- traction and customer evidence;
- unit economics;
- burn, cash, and runway;
- market and competition;
- team and governance;
- conditional cap-table analysis;
- questions for founders/management;
- contradictions and unresolved issues;
- sources, calculations, assumptions, versions, hashes, and trace IDs appendix;
- disclaimer: research aid only, not investment, legal, tax, or accounting advice.

- [ ] **Step 4: Add Startup UI panels inside the shared shell**

The case page supports read-only upload into the local data-room service, inventory/quarantine status, parser confidence warnings, Gate 2 preview, analysis plan/progress, claim–evidence filters, metric formulas and inputs, contradictions/HITL inbox, Gate 3 exclusions, and Gate 4 report approval. It uses repository IDs to load content and never places raw document text in Streamlit query parameters, logs, or trace metadata.

The UI must distinguish:

- `draft`, `approval_required`, `running`, `blocked_by_policy`, `review_required`, `approved`, and `completed` states;
- supported, partial, contradicted, unsupported, and insufficient-data claims;
- verified parser values from low-confidence/OCR-derived values;
- approved final downloads from clearly watermarked draft downloads.

Extend the Stage 1A CLI parser with `render-fixture --dataset --output` and `smoke-ui --mode --timeout-seconds`. Both commands use `build_container()`; the fixture command forces offline adapters, while the smoke command starts Streamlit on an ephemeral local port, checks its health endpoint, and terminates the child process within the requested timeout.

- [ ] **Step 5: Render the frozen fixture and inspect all three formats**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/e2e/test_startup_report.py -v
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local python -m due_diligence_agent.presentation.cli render-fixture --dataset startup_synthetic_saas_v1 --output .local/report-smoke/startup
```

Expected: tests PASS; command writes `report.json`, `report.html`, and `report.pdf` only for the approved fixture. JSON validates against the shared schema; HTML and PDF contain the same snapshot ID and source hashes.

- [ ] **Step 6: Run the Streamlit smoke test**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev python -m due_diligence_agent.presentation.cli smoke-ui --mode startup --timeout-seconds 20
```

Expected: exit `0`; the app starts, registers the Startup page and components, loads the frozen case, and stops within 20 seconds without network access.

- [ ] **Step 7: Commit the Startup report and UI**

```powershell
git add src/due_diligence_agent/adapters/reports/templates/startup_report.html.j2 src/due_diligence_agent/application/services/startup_report_sections.py src/due_diligence_agent/presentation/streamlit src/due_diligence_agent/presentation/cli.py src/due_diligence_agent/bootstrap/container.py tests/e2e/test_startup_report.py
git commit -m "feat: add startup report and review UI"
```

---

### Task 11: Build Frozen Startup Fixtures and Enforce Gates C, D, and E

**Files:**
- Create: `tests/fixtures/startup_synthetic_saas_v1/manifest.json`
- Create: `tests/fixtures/startup_synthetic_saas_v1/deck.pdf`
- Create: `tests/fixtures/startup_synthetic_saas_v1/financial_model.xlsx`
- Create: `tests/fixtures/startup_synthetic_saas_v1/customers.csv`
- Create: `tests/fixtures/startup_synthetic_saas_v1/governance.docx`
- Create: `tests/fixtures/startup_synthetic_saas_v1/scanned_invoice.png`
- Create: `tests/fixtures/startup_synthetic_saas_v1/data_room.zip`
- Create: `tests/fixtures/startup_synthetic_saas_v1/damaged.pdf`
- Create: `tests/fixtures/document_parsing_v1/manifest.json`
- Create: `tests/fixtures/privacy_v1/manifest.json`
- Create: `tests/golden/startup_synthetic_saas_v1/report_snapshot.json`
- Create: `tests/evaluation/startup/test_ingest.py`
- Create: `tests/evaluation/startup/test_parsing.py`
- Create: `tests/evaluation/startup/test_claims.py`
- Create: `tests/evaluation/startup/test_metrics.py`
- Create: `tests/evaluation/startup/test_privacy.py`
- Create: `tests/evaluation/startup/test_report.py`
- Create: `tests/e2e/test_startup_case_e2e.py`
- Create: `scripts/generate_startup_fixtures.py`
- Create: `scripts/run_stage1b_eval.ps1`
- Modify: `README.md`

**Interfaces:**
- Produces: immutable offline datasets, golden outputs, Stage 1B evaluation command, and combined Stage 1A/1B regression evidence.
- Consumes: shared evaluator framework and all Stage 1A/Stage 1B production paths.

- [ ] **Step 1: Write the blocking Stage 1B threshold test**

```python
# tests/e2e/test_startup_case_e2e.py
def test_startup_synthetic_saas_v1_meets_blocking_thresholds(eval_runner):
    result = eval_runner.run("startup_synthetic_saas_v1")

    assert result.schema_validity == 1.0
    assert result.critical_evidence_coverage == 1.0
    assert result.unsupported_critical_claim_rate == 0.0
    assert result.numerical_accuracy == 1.0
    assert result.unit_period_consistency == 1.0
    assert result.contradiction_recall == 1.0
    assert result.contradiction_precision >= 0.80
    assert result.retrieval_recall_at_5 >= 0.90
    assert result.ocr_false_verified_count == 0
    assert result.privacy_leak_count == 0
    assert result.trace_completeness == 1.0
    assert result.reflexion_max_rounds <= 2
    assert result.budget_violations == 0
    assert result.report_completeness == 1.0
    assert result.offline_latency_minutes <= 30
```

- [ ] **Step 2: Run the test and confirm the frozen dataset is absent**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group eval-ragas --group dev pytest tests/e2e/test_startup_case_e2e.py -v
```

Expected: FAIL because `startup_synthetic_saas_v1` is not registered.

- [ ] **Step 3: Generate and freeze the synthetic SaaS data room**

Create deterministic synthetic documents with no real company or person data. The same facts appear in multiple formats with these planted contradictions:

| Claim | Deck | Primary calculation/source | Expected result |
|---|---:|---:|---|
| ARR | USD 2.4M | Financial workbook USD 1.8M | contradiction |
| Gross margin | 80% | Revenue/COGS calculation 62% | contradiction |
| Runway | 18 months | Cash/net-burn calculation 9.5 months | contradiction |
| Customers | 120 | Deduplicated active customer CSV 87 | contradiction |

Include a pitch-deck PDF, formula-bearing XLSX, customer CSV, governance DOCX, scanned invoice image, safe ZIP, damaged PDF, and seeded synthetic PII, bank-account-like, token-like, and credential-like strings. `manifest.json` records each file hash, generator version, `as_of`, expected locators, expected sensitivity categories, expected quarantine outcomes, and licenses for any generated font/model asset.

`scripts/generate_startup_fixtures.py` uses a fixed seed (`20260809`) and only local PyMuPDF, openpyxl, python-docx, Pillow, `csv`, and `zipfile` APIs. It builds the Startup, parsing, and privacy fixture directories together and refuses to overwrite a non-empty target unless every existing hash already matches its generated manifest.

Run:

```powershell
uv run --no-default-groups --group stage1b python scripts/generate_startup_fixtures.py --seed 20260809 --as-of 2026-06-30 --fixtures-root tests/fixtures
```

Expected: exit `0`; all three manifests and their named fixture payloads are present, a second run is byte-identical, and the script prints `startup fixture hashes verified`.

- [ ] **Step 4: Freeze parser, privacy, and retrieval benchmarks**

`document_parsing_v1` covers PDF text, PDF table, DOCX paragraph/table, XLSX formula/cached value, CSV quoted/newline cells, image OCR, damaged file, unsupported MIME, zip-slip, nested archive, and decompression-ratio cases. Each expected output includes locator and confidence.

`privacy_v1` seeds names, emails, phones, addresses, banking identifiers, access-token patterns, passwords, customer rows, cap-table values, and raw document excerpts. The forbidden-string corpus is checked against provider mocks, trace exports, local spool, exceptions, retrieved LLM context, tool inputs/results, and generated public logs.

Create 20 labeled Startup retrieval queries spanning deck, workbook, CSV, DOCX, and OCR. The expected relevant chunk IDs are stable and sensitivity-filtered; restricted chunks cannot enter an external-provider retrieval context even if they rank in the local index.

- [ ] **Step 5: Implement evaluators from measured artifacts**

Each evaluator calculates its score from persisted artifacts and golden truth. No evaluator may set a pass flag directly. `scripts/run_stage1b_eval.ps1` runs Gate C security/parser tests first, then Gate D e2e/report tests, then Gate E combined regression. It writes `.local/evals/stage1b/eval-result.json` with dataset hashes, `uv.lock` hash, git commit, Python/uv/package versions, model hashes, trace/audit coverage, latency, and every failed assertion.

- [ ] **Step 6: Run Gate C**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group dev pytest tests/security/test_archive_safety.py tests/privacy/test_startup_redaction.py tests/evaluation/startup/test_ingest.py tests/evaluation/startup/test_parsing.py tests/evaluation/startup/test_privacy.py -v
```

Expected: PASS; unsafe archives and unsupported MIME are blocked, damaged input is quarantined, no-network mode is enforced, Gate 2 preview leaks no values, and privacy leak count is `0`.

- [ ] **Step 7: Run Gate D**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group eval-ragas --group dev pytest tests/evaluation/startup tests/e2e/test_startup_case_e2e.py tests/e2e/test_startup_report.py -v
```

Expected: PASS; all four planted contradictions are detected, contradiction precision is at least `0.80`, all golden calculations match with `Decimal` tolerance `1e-6`, retrieval recall@5 is at least `0.90`, report completeness is `100%`, and offline runtime is at most 30 minutes excluding HITL wait.

- [ ] **Step 8: Run Gate E and the complete quality suite**

Run:

```powershell
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group eval-ragas --group dev ruff check .
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group eval-ragas --group dev mypy src
uv run --no-default-groups --group stage1b-light-ingest --group stage1a-rag-local --group eval-ragas --group dev pytest --cov=due_diligence_agent --cov-report=term-missing
```

Expected: all commands exit `0`; Public `public_us_frozen_v1` and Startup `startup_synthetic_saas_v1` pass, shared schema compatibility tests pass, report snapshots remain immutable, and no Stage 1A metric, workflow, trace, or report regression is present.

- [ ] **Step 9: Document exact local setup and verification**

Update `README.md` with Python 3.12/uv setup, explicit dependency groups, optional Tesseract/Presidio/Docling setup gates, environment variables without secrets, offline fixture execution, Streamlit launch, Gate 2/3/4 behavior, report locations, data retention, disclaimer, and copy-paste Stage 1A/Stage 1B evaluation commands.

- [ ] **Step 10: Commit the verified Stage 1B vertical slice**

```powershell
git add tests/fixtures/startup_synthetic_saas_v1 tests/fixtures/document_parsing_v1 tests/fixtures/privacy_v1 tests/golden/startup_synthetic_saas_v1 tests/evaluation/startup tests/e2e/test_startup_case_e2e.py scripts/generate_startup_fixtures.py scripts/run_stage1b_eval.ps1 README.md
git commit -m "test: verify startup data room local MVP"
```

## Stage 1B Completion Evidence

Before declaring the approved local MVP complete, preserve these artifacts:

- Gate C, Gate D, and Gate E `eval-result.json` outputs;
- approved Startup Report JSON, HTML, and PDF with one immutable snapshot ID;
- all fixture, model, dependency-lock, and report source hashes;
- claim–evidence matrix showing the four planted contradictions;
- calculation records for ARR, gross margin, runway, and customer count;
- proof of no-network parsing and zero privacy leaks across traces, tool payloads, provider mocks, spool, logs, and reports;
- proof that denied Gate 2 approval makes zero external calls and still permits local deterministic work;
- proof of checkpoint recovery and Gate 3 dependency invalidation;
- full Ruff, mypy, and pytest output for both Public and Startup modes;
- documented remaining limitations: synthetic Startup evaluation only, optional parser adapters are feature-gated, and the output is not investment, legal, tax, or accounting advice.
