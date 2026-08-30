# Public Company Local MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared local-first due-diligence core and a complete Public Company workflow that turns a supported US ticker into evidence-backed Report JSON, HTML, and PDF with deterministic metrics, HITL, bounded Reflexion, privacy controls, durable audit, and passing offline evaluation.

**Architecture:** Implement a Python modular monolith under `src/due_diligence_agent` with domain models at the center, application services around them, stable ports, and local adapters for SEC, SQLite, filesystem, DuckDB, FAISS, OpenAI, observability, reporting, and Streamlit. LangGraph owns Plan-and-Execute orchestration and checkpoints, while calculations, evidence validation, privacy, and report snapshots remain deterministic application/domain code.

**Tech Stack:** Python 3.12, uv lockfile, Pydantic 2, LangGraph, OpenAI Responses API/Code Interpreter adapter, httpx, SQLite, DuckDB, sentence-transformers, FAISS, OpenTelemetry, sanitized LangSmith adapter, Pandas, Jinja2, Plotly/Matplotlib, WeasyPrint with ReportLab fallback, Streamlit, pytest, Ragas for offline retrieval diagnostics, Ruff, mypy.

## Global Constraints

- Source of truth: `docs/superpowers/specs/2026-08-09-investment-due-diligence-agent-design.md`.
- Stage 1A supports only SEC-reporting issuers; unsupported jurisdictions return `unsupported_jurisdiction`.
- Pin `.python-version` to `3.12`; keep `requires-python = ">=3.12,<3.14"`; run Python 3.13 as a non-blocking compatibility smoke.
- Commit `uv.lock`; every dependency group is explicitly selected with `--no-default-groups`.
- SEC calls use a declared `User-Agent`, immutable cache, exponential backoff, and a maximum rate of 10 requests per second.
- `yfinance` is an optional research/demo adapter, never source-of-record and never sole evidence for a critical financial claim.
- News storage is metadata/snippet-only unless the source license explicitly permits full text.
- Every critical finding has primary evidence, deterministic calculation, or `insufficient_data`.
- Financial calculations consume normalized `EvidenceFact` IDs and use `Decimal`; LLM output never becomes a canonical number directly.
- Raw documents, prompts, completions, chunks, tool arguments/results, PII, and secrets never enter LangSmith or OpenTelemetry payloads.
- Durable local audit is mandatory; external exporter failure is non-blocking only while local audit persistence succeeds.
- Every LLM/model fallback re-runs `DataEgressPolicy`, preserves the same schema, records the primary failure, and cannot weaken privacy.
- LangGraph state stores IDs and compact typed structures, not complete filings or raw documents.
- Reflexion executes at most two rounds and stops when no new evidence or status change is produced.
- Report JSON is canonical; HTML and PDF render only from an immutable `ReportSnapshot`.
- Final PDF export requires Gate 4 approval and includes the mandatory investment/legal/tax disclaimer.
- Use TDD: failing targeted test, minimal implementation, passing targeted test, then proportional broader checks.
- Run `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas --group dev ruff check .`, `mypy src`, and `pytest` before Gate B.

---

## Planned File Structure

| Area | Files and responsibility |
|---|---|
| Project | `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `.gitignore`, `README.md` |
| Configuration | `src/due_diligence_agent/config.py`, `src/due_diligence_agent/bootstrap/container.py` |
| Domain | `domain/common.py`, `domain/cases/models.py`, `domain/artifacts/models.py`, `domain/evidence/models.py`, `domain/evidence/ledger.py`, `domain/metrics/*`, `domain/findings/models.py`, `domain/approvals/models.py`, `domain/reports/models.py` |
| Application | `application/services/case_service.py`, `evidence_service.py`, `public_analysis_service.py`, `report_service.py`; `application/policies/*` |
| Ports | `ports/repositories.py`, `collectors.py`, `retrieval.py`, `llm.py`, `tracing.py`, `rendering.py` |
| Local adapters | `adapters/local_storage/*`, `adapters/sec/*`, `adapters/market_data/*`, `adapters/news/*`, `adapters/retrieval/*`, `adapters/openai/*`, `adapters/observability/*`, `adapters/reports/*` |
| Workflows | `workflows/shared/node_result.py`, `reflexion.py`; `workflows/public_company/state.py`, `plan.py`, `nodes/*`, `graph.py` |
| Presentation | `presentation/streamlit/app.py`, `pages/public_case.py`, `components/*`, `cli.py` |
| Evaluation | `evals/runner.py`, `evals/metrics.py`, `tests/fixtures/public_us_frozen_v1/*`, `tests/e2e/*`, `tests/evaluation/*` |

## Verification Gates

- **Gate A — Foundation contracts:** domain schemas, ports, repositories, local audit, trace sanitizer, `ReportSnapshot`, and `ReproducibilityManifest` pass unit/contract tests.
- **Gate B — Public vertical:** `public_us_frozen_v1` completes offline with 100% critical evidence coverage, 100% golden calculations, 100% required report sections, 100% trace completeness, zero privacy leaks, checkpoint recovery, and exporter-outage fallback.

---

### Task 1: Bootstrap the Locked Python Project

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/due_diligence_agent/__init__.py`
- Create: `src/due_diligence_agent/config.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: validated `Settings`, Python 3.12 runtime pin, named uv groups, and a reproducible dependency lock used by every later task.
- Consumes: none.

- [ ] **Step 1: Write the failing configuration test**

```python
# tests/unit/test_config.py
from due_diligence_agent.config import Settings


def test_settings_are_local_and_privacy_safe_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DDA_DATA_DIR", str(tmp_path))
    settings = Settings()
    assert settings.runtime_profile == "local"
    assert settings.python_runtime == "3.12"
    assert settings.langsmith_tracing is False
    assert settings.audit_required is True
    assert settings.data_dir == tmp_path
```

- [ ] **Step 2: Run the test to verify the package is absent**

Run: `uv run --python 3.12 --with pytest pytest tests/unit/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'due_diligence_agent'`.

- [ ] **Step 3: Add the project metadata and dependency groups**

```toml
# pyproject.toml
[project]
name = "investment-dd-agent"
version = "0.1.0"
requires-python = ">=3.12,<3.14"
dependencies = []

[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/due_diligence_agent"]

[tool.uv]
default-groups = []

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true

[tool.uv.sources]
torch = [{ index = "pytorch-cpu" }]
torchvision = [{ index = "pytorch-cpu" }]

[dependency-groups]
core = [
  "pydantic>=2.13.4,<3",
  "pydantic-settings>=2.10,<3",
  "python-dotenv>=1.2.2,<2",
  "httpx>=0.28.1,<1",
  "tenacity>=9.1.4,<10",
]
workflow = ["langgraph>=1.2.9,<2", "langgraph-checkpoint-sqlite>=3.1,<4"]
llm-openai = ["openai>=2.38,<3"]
observability-local = [
  "opentelemetry-api>=1.44,<2",
  "opentelemetry-sdk>=1.44,<2",
  "opentelemetry-exporter-otlp-proto-http>=1.44,<2",
]
observability-langsmith = ["langsmith>=0.10,<0.11"]
stage1a-data = ["pandas>=3.0.3,<3.1,!=3.0.4", "duckdb>=1.5.4,<1.6", "beautifulsoup4>=4.15,<5"]
stage1a-ui-report = [
  "streamlit>=1.60,<2",
  "jinja2>=3.1,<4",
  "weasyprint>=69,<70",
  "matplotlib>=3.11,<3.12",
  "plotly>=6.9,<7",
]
stage1a-rag-local = ["sentence-transformers>=5.6,<6", "faiss-cpu>=1.14,<2"]
stage1a-market-yfinance-demo = ["yfinance>=1.5,<2"]
reportlab-fallback = ["reportlab>=5,<6"]
eval-ragas = ["ragas>=0.4.3,<0.5"]
stage1a = [
  { include-group = "core" },
  { include-group = "workflow" },
  { include-group = "llm-openai" },
  { include-group = "observability-local" },
  { include-group = "stage1a-data" },
  { include-group = "stage1a-ui-report" },
]
dev = [
  "pytest>=9.1,<10",
  "pytest-asyncio>=1.3,<2",
  "pytest-cov>=7.1,<8",
  "respx>=0.22,<1",
  "ruff>=0.15.22,<0.16",
  "mypy>=2.3,<3",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["due_diligence_agent"]
```

- [ ] **Step 4: Add safe default settings**

```python
# src/due_diligence_agent/config.py
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DDA_", env_file=".env", extra="ignore")

    runtime_profile: Literal["local", "self_hosted"] = "local"
    python_runtime: Literal["3.12", "3.13"] = "3.12"
    data_dir: Path = Path(".local")
    langsmith_tracing: bool = False
    audit_required: bool = True
    sec_user_agent: str = Field(default="", min_length=0)
    sec_max_requests_per_second: int = Field(default=10, ge=1, le=10)
    reflexion_max_rounds: int = Field(default=2, ge=0, le=2)
```

Create `.python-version` with `3.12`, `.gitignore` with `.venv/`, `.env`, `.local/`, `.omx/`, Python caches, coverage outputs, and generated reports; `.env.example` contains names only and no credentials.

- [ ] **Step 5: Lock, sync, and run the dependency smoke**

Run:

```powershell
uv python install 3.12 3.13
uv python pin 3.12
uv lock --python 3.12
uv sync --no-default-groups --group stage1a --group stage1a-rag-local --group dev
uv run --no-default-groups --group stage1a --group stage1a-rag-local python -c "import pydantic,httpx,langgraph,openai,pandas,duckdb,streamlit,matplotlib,plotly,weasyprint,sentence_transformers,faiss; import langgraph.checkpoint.sqlite; print('stage1a ok')"
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/test_config.py -v
uv run --python 3.13 --no-default-groups --group stage1a --group stage1a-rag-local python -c "import pydantic,httpx,langgraph,openai,pandas,duckdb,streamlit,matplotlib,plotly,weasyprint,sentence_transformers,faiss; print('py313 stage1a ok')"
```

Expected: Python 3.12 imports print `stage1a ok`; test PASS; `uv.lock` exists. The Python 3.13 compatibility smoke prints `py313 stage1a ok`; if it fails only because a declared optional/native dependency lacks a 3.13 wheel, record the package/version in the reproducibility manifest and keep Python 3.12 as the Gate B runtime.

- [ ] **Step 6: Commit the bootstrap**

```powershell
git add pyproject.toml uv.lock .python-version .env.example .gitignore README.md src tests/unit/test_config.py
git commit -m "chore: bootstrap local due diligence project"
```

---

### Task 2: Define Shared Domain Contracts and Node Results

**Files:**
- Create: `src/due_diligence_agent/domain/common.py`
- Create: `src/due_diligence_agent/domain/cases/models.py`
- Create: `src/due_diligence_agent/domain/artifacts/models.py`
- Create: `src/due_diligence_agent/domain/evidence/models.py`
- Create: `src/due_diligence_agent/domain/findings/models.py`
- Create: `src/due_diligence_agent/domain/approvals/models.py`
- Create: `src/due_diligence_agent/domain/reports/models.py`
- Create: `src/due_diligence_agent/workflows/shared/node_result.py`
- Test: `tests/unit/domain/test_models.py`

**Interfaces:**
- Produces: `DueDiligenceCase`, `Artifact`, `StoredArtifact`, `SourceLocator`, `EvidenceFact`, `Calculation`, `Finding`, `Contradiction`, `Approval`, `ReproducibilityManifest`, `ReportSnapshot`, and generic `NodeResult[T]`.
- Consumes: `Settings` from Task 1.

- [ ] **Step 1: Write failing invariant tests**

```python
# tests/unit/domain/test_models.py
from decimal import Decimal
from uuid import uuid4

import pytest

from due_diligence_agent.domain.common import AnalysisMode, SensitivityClass
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus


def test_evidence_requires_period_and_unit_for_numeric_value():
    with pytest.raises(ValueError, match="period and unit"):
        EvidenceFact(
            id=uuid4(), artifact_id=uuid4(), name="revenue", value=Decimal("10"),
            value_type="decimal", unit=None, period=None,
            locator=SourceLocator(kind="sec_fact", value="Revenue"),
            sensitivity=SensitivityClass.PUBLIC, confidence=Decimal("1"),
        )


def test_node_result_has_typed_partial_status():
    result = NodeResult[list[str]](status=NodeStatus.PARTIAL, data=["fact-1"], warnings=["stale"])
    assert result.status is NodeStatus.PARTIAL
    assert result.data == ["fact-1"]
```

- [ ] **Step 2: Run the tests and confirm missing models**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/domain/test_models.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Implement the enums and core evidence contract**

```python
# src/due_diligence_agent/domain/common.py
from enum import StrEnum


class AnalysisMode(StrEnum):
    PUBLIC_COMPANY = "public_company"
    STARTUP = "startup"


class SensitivityClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

```python
# src/due_diligence_agent/domain/evidence/models.py
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass


class EvidenceFact(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    artifact_id: UUID
    name: str
    value: Any
    value_type: Literal["decimal", "integer", "text", "date", "boolean"]
    unit: str | None
    period: str | None
    locator: SourceLocator
    sensitivity: SensitivityClass
    confidence: Decimal
    retrieved_at: datetime | None = None

    @model_validator(mode="after")
    def require_numeric_context(self) -> "EvidenceFact":
        if self.value_type in {"decimal", "integer"} and (not self.unit or not self.period):
            raise ValueError("numeric evidence requires period and unit")
        return self
```

- [ ] **Step 4: Implement the remaining immutable entities and `NodeResult`**

```python
# src/due_diligence_agent/workflows/shared/node_result.py
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class NodeStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    RETRYABLE_ERROR = "retryable_error"
    BLOCKED = "blocked"
    FAILED = "failed"


class NodeResult(BaseModel, Generic[T]):
    status: NodeStatus
    data: T | None = None
    data_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    fallback_used: str | None = None
    retry_after_seconds: float | None = None
    trace_id: str | None = None
```

```python
# src/due_diligence_agent/domain/approvals/models.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Approval(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    case_id: UUID
    gate: str
    action: str
    actor: str
    comment: str | None = None
    decided_at: datetime
    data_revision: int
```

Implement the other model files with `ConfigDict(frozen=True)`, UUID identifiers, UTC timestamps, source hashes, sensitivity, and version fields exactly named in the design spec. `ReportSnapshot` contains `reproducibility: ReproducibilityManifest` and content hashes but stores no raw source text.

- [ ] **Step 5: Run domain tests and typecheck**

Run:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/domain/test_models.py -v
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev mypy src/due_diligence_agent/domain src/due_diligence_agent/workflows/shared/node_result.py
```

Expected: PASS.

- [ ] **Step 6: Commit the domain contracts**

```powershell
git add src/due_diligence_agent/domain src/due_diligence_agent/workflows/shared tests/unit/domain
git commit -m "feat: define shared due diligence domain contracts"
```

---

### Task 3: Implement Local Repositories and Content-Addressed Storage

**Files:**
- Create: `src/due_diligence_agent/ports/repositories.py`
- Create: `src/due_diligence_agent/adapters/local_storage/sqlite_db.py`
- Create: `src/due_diligence_agent/adapters/local_storage/repositories.py`
- Create: `src/due_diligence_agent/adapters/local_storage/artifact_store.py`
- Create: `src/due_diligence_agent/application/services/case_service.py`
- Test: `tests/integration/storage/test_local_repositories.py`

**Interfaces:**
- Produces: `CaseRepository`, `ArtifactRepository`, `EvidenceRepository`, `CalculationRepository`, `FindingRepository`, `ContradictionRepository`, `ApprovalRepository`, `ReportRepository`, `ArtifactStore`, and local implementations.
- Consumes: immutable domain models from Task 2.

- [ ] **Step 1: Write failing persistence tests**

```python
# tests/integration/storage/test_local_repositories.py
from pathlib import Path

from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore


def test_artifact_store_is_content_addressed_and_immutable(tmp_path: Path):
    store = LocalArtifactStore(tmp_path)
    first = store.put_bytes(b"same filing", media_type="text/html")
    second = store.put_bytes(b"same filing", media_type="text/html")
    assert first.content_hash == second.content_hash
    assert first.storage_ref == second.storage_ref
    assert Path(first.storage_ref).read_bytes() == b"same filing"
```

- [ ] **Step 2: Run the test and confirm the adapter is missing**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/integration/storage/test_local_repositories.py -v`

Expected: FAIL on import.

- [ ] **Step 3: Define repository protocols**

```python
# src/due_diligence_agent/ports/repositories.py
from typing import Protocol
from uuid import UUID

from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.artifacts.models import Artifact, StoredArtifact
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.reports.models import ReportSnapshot


class CaseRepository(Protocol):
    def add(self, case: DueDiligenceCase) -> None: ...
    def get(self, case_id: UUID) -> DueDiligenceCase: ...


class ArtifactRepository(Protocol):
    def add(self, artifact: Artifact) -> None: ...
    def get(self, artifact_id: UUID) -> Artifact: ...


class EvidenceRepository(Protocol):
    def add(self, fact: EvidenceFact) -> None: ...
    def list_for_case(self, case_id: UUID) -> list[EvidenceFact]: ...


class CalculationRepository(Protocol):
    def add(self, calculation: Calculation) -> None: ...
    def list_for_case(self, case_id: UUID) -> list[Calculation]: ...


class FindingRepository(Protocol):
    def add(self, finding: Finding) -> None: ...
    def list_for_case(self, case_id: UUID) -> list[Finding]: ...


class ContradictionRepository(Protocol):
    def add(self, contradiction: Contradiction) -> None: ...
    def list_for_case(self, case_id: UUID) -> list[Contradiction]: ...


class ApprovalRepository(Protocol):
    def add(self, approval: Approval) -> None: ...
    def list_for_case(self, case_id: UUID) -> list[Approval]: ...


class ReportRepository(Protocol):
    def add_snapshot(self, snapshot: ReportSnapshot) -> None: ...
    def get_snapshot(self, snapshot_id: UUID) -> ReportSnapshot: ...


class ArtifactStore(Protocol):
    def put_bytes(self, payload: bytes, *, media_type: str) -> StoredArtifact: ...
    def read_bytes(self, content_hash: str) -> bytes: ...
```

- [ ] **Step 4: Implement SQLite schema and filesystem storage**

```python
# src/due_diligence_agent/adapters/local_storage/artifact_store.py
from hashlib import sha256
from pathlib import Path

from due_diligence_agent.domain.artifacts.models import StoredArtifact


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put_bytes(self, payload: bytes, *, media_type: str) -> StoredArtifact:
        digest = sha256(payload).hexdigest()
        target = self.root / "objects" / digest[:2] / digest
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(payload)
        return StoredArtifact(content_hash=digest, media_type=media_type, storage_ref=str(target))

    def read_bytes(self, content_hash: str) -> bytes:
        target = self.root / "objects" / content_hash[:2] / content_hash
        return target.read_bytes()
```

Create normalized SQLite tables for cases, artifacts, evidence facts, calculations, findings, contradictions, approvals, report snapshots, and workflow checkpoints. Serialize Pydantic models as canonical JSON; use primary keys and append-only snapshot inserts. `CaseService.create_public_case()` rejects an empty ticker and non-SEC mode.

- [ ] **Step 5: Verify persistence and schema creation**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/integration/storage/test_local_repositories.py -v`

Expected: PASS, including save/reload and snapshot immutability tests.

- [ ] **Step 6: Commit local persistence**

```powershell
git add src/due_diligence_agent/ports src/due_diligence_agent/adapters/local_storage src/due_diligence_agent/application/services/case_service.py tests/integration/storage
git commit -m "feat: add local repositories and artifact storage"
```

---

### Task 4: Build the Evidence Ledger and Source-Priority Policy

**Files:**
- Create: `src/due_diligence_agent/domain/evidence/ledger.py`
- Create: `src/due_diligence_agent/application/policies/source_priority.py`
- Create: `src/due_diligence_agent/application/services/evidence_service.py`
- Test: `tests/unit/evidence/test_ledger.py`

**Interfaces:**
- Produces: `EvidenceLedger.add_fact()`, `EvidenceLedger.find_conflicts()`, `EvidenceLedger.coverage()`, and `SourcePriorityPolicy.can_support_critical_claim()`.
- Consumes: `EvidenceFact`, `Contradiction`, and repositories from Tasks 2–3.

- [ ] **Step 1: Write failing ledger tests**

```python
# tests/unit/evidence/test_ledger.py
def test_conflicting_primary_facts_are_preserved_and_linked(make_fact):
    ledger = make_ledger()
    first = make_fact(name="revenue", value="100", priority="official_filing")
    second = make_fact(name="revenue", value="120", priority="official_filing")
    ledger.add_fact(first)
    ledger.add_fact(second)
    conflicts = ledger.find_conflicts(name="revenue", period=first.period)
    assert {first.id, second.id} == set(conflicts[0].evidence_fact_ids)


def test_secondary_source_cannot_support_critical_financial_claim(make_fact):
    policy = SourcePriorityPolicy()
    fact = make_fact(priority="secondary_aggregator")
    assert policy.can_support_critical_claim([fact], category="liquidity") is False
```

- [ ] **Step 2: Run tests and confirm missing ledger behavior**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/evidence/test_ledger.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Implement source priority and conflict preservation**

```python
# src/due_diligence_agent/application/policies/source_priority.py
from enum import IntEnum


class SourcePriority(IntEnum):
    MODEL_INFERENCE = 10
    SECONDARY_AGGREGATOR = 20
    LICENSED_METADATA = 30
    MANAGEMENT_NARRATIVE = 40
    SYSTEM_EXPORT = 50
    OFFICIAL_OR_SIGNED = 60


class SourcePriorityPolicy:
    def can_support_critical_claim(self, facts, *, category: str) -> bool:
        if category in {"valuation", "growth", "liquidity", "debt", "solvency"}:
            return any(f.source_priority >= SourcePriority.OFFICIAL_OR_SIGNED for f in facts)
        return bool(facts)
```

`EvidenceLedger.add_fact()` inserts a new immutable fact rather than overwriting. `find_conflicts()` compares normalized name, period, unit, and incompatible values; it writes a first-class `Contradiction`. `coverage()` returns the fraction of critical findings having primary evidence, calculations, or explicit `insufficient_data`.

- [ ] **Step 4: Run ledger tests**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/evidence/test_ledger.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the evidence layer**

```powershell
git add src/due_diligence_agent/domain/evidence src/due_diligence_agent/application/policies src/due_diligence_agent/application/services/evidence_service.py tests/unit/evidence
git commit -m "feat: add provenance-aware evidence ledger"
```

---

### Task 5: Implement Immutable HTTP Cache and SEC EDGAR Adapter

**Files:**
- Create: `src/due_diligence_agent/ports/collectors.py`
- Create: `src/due_diligence_agent/adapters/http/fair_access.py`
- Create: `src/due_diligence_agent/adapters/http/snapshot_cache.py`
- Create: `src/due_diligence_agent/adapters/sec/edgar.py`
- Create: `src/due_diligence_agent/adapters/sec/models.py`
- Create: `scripts/refresh_sec_fixtures.py`
- Test: `tests/contract/sources/test_sec_edgar.py`
- Fixtures: `tests/fixtures/public_us_frozen_v1/sec/*`

**Interfaces:**
- Produces: `SecSourcePort.resolve_company()`, `list_submissions()`, `get_company_facts()`, `fetch_filing()`, plus immutable `SourceSnapshot` provenance.
- Consumes: storage and source-priority contracts from Tasks 3–4.

- [ ] **Step 1: Write failing SEC contract tests**

```python
# tests/contract/sources/test_sec_edgar.py
import pytest


@pytest.mark.asyncio
async def test_sec_adapter_declares_user_agent_and_caches_response(sec_adapter, sec_mock):
    await sec_adapter.get_company_facts("0000320193")
    await sec_adapter.get_company_facts("0000320193")
    assert sec_mock.calls.call_count == 1
    assert sec_mock.calls[0].request.headers["User-Agent"] == "CapstoneN3 test@example.com"


@pytest.mark.asyncio
async def test_missing_primary_filing_blocks_critical_assertions(sec_adapter_without_filing):
    result = await sec_adapter_without_filing.fetch_filing("missing-accession")
    assert result.status == "blocked"
```

- [ ] **Step 2: Run the SEC tests and confirm missing adapters**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/contract/sources/test_sec_edgar.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define source contracts and provenance**

```python
# src/due_diligence_agent/ports/collectors.py
from datetime import date, datetime
from typing import Protocol

from pydantic import BaseModel


class SecSourcePort(Protocol):
    async def resolve_company(self, ticker_or_cik: str) -> "CompanyIdentity": ...
    async def list_submissions(self, cik: str, *, as_of: date) -> "SubmissionsSnapshot": ...
    async def get_company_facts(self, cik: str, *, as_of: date) -> "CompanyFactsSnapshot": ...
    async def fetch_filing(self, accession_number: str) -> "FilingArtifact": ...


class SourceSnapshot(BaseModel):
    provider: str
    provider_version: str
    source_url: str
    query: dict[str, str]
    retrieved_at: datetime
    published_at: datetime | None
    content_hash: str
    license_class: str
    stale: bool = False
```

- [ ] **Step 4: Implement fair access, cache keys, and SEC endpoints**

`FairAccessLimiter.acquire()` enforces at most 10 requests/second. `SnapshotCache.key()` hashes provider, endpoint, normalized query, and `as_of`. `SecEdgarAdapter` calls `data.sec.gov/submissions`, `data.sec.gov/api/xbrl/companyfacts`, and filing archives through one `_request_json()` method, always with the configured `User-Agent`. Retry only timeouts, connection failures, HTTP 429, and HTTP 5xx; honor `Retry-After`, otherwise use exponential backoff with jitter capped at 30 seconds and at most five attempts. Do not retry schema, authorization, 4xx other than 429, or content-hash failures. Cache fallback marks `stale=True` and records the primary failure; a missing uncached primary filing returns `NodeStatus.BLOCKED` for dependent financial assertions.

```python
async def _request_json(self, url: str, *, query: dict[str, str], as_of: date) -> SourceSnapshot:
    key = self.cache.key("sec", url, query, as_of)
    if cached := self.cache.get(key):
        return cached
    await self.limiter.acquire()
    response = await self.client.get(url, params=query, headers={"User-Agent": self.user_agent})
    response.raise_for_status()
    return self.cache.put_response(key, response, provider="sec", license_class="public_primary")
```

- [ ] **Step 5: Freeze and hash the SEC fixtures**

Create fixture files `submissions.json`, `companyfacts.json`, one 10-K HTML, one 10-Q HTML, one XBRL sample, `429.json`, `malformed.json`, and `manifest.json`. `manifest.json` records file SHA-256, retrieval URL, frozen `as_of`, and license class. Tests read fixtures only; `scripts/refresh_sec_fixtures.py` requires configured `DDA_SEC_USER_AGENT`, writes through a temporary directory, verifies every hash, and is never invoked by pytest.

Run once when intentionally refreshing the frozen source set:

```powershell
uv run --no-default-groups --group stage1a python scripts/refresh_sec_fixtures.py --ticker AAPL --cik 0000320193 --as-of 2026-06-30 --output tests/fixtures/public_us_frozen_v1/sec
```

Expected: exit `0`; manifest contains the declared SEC URLs, acceptance/effective timestamps, license class, and hashes for every fixture. A missing `DDA_SEC_USER_AGENT` fails before the first network request.

- [ ] **Step 6: Run SEC tests and the broader evidence suite**

Run:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/contract/sources/test_sec_edgar.py tests/unit/evidence -v
```

Expected: PASS.

- [ ] **Step 7: Commit SEC ingestion**

```powershell
git add src/due_diligence_agent/ports/collectors.py src/due_diligence_agent/adapters/http src/due_diligence_agent/adapters/sec scripts/refresh_sec_fixtures.py tests/contract/sources tests/fixtures/public_us_frozen_v1/sec
git commit -m "feat: add cached SEC EDGAR source adapter"
```

---

### Task 6: Add Secondary Market Data and Metadata-Only News Adapters

**Files:**
- Create: `src/due_diligence_agent/adapters/market_data/yfinance_demo.py`
- Create: `src/due_diligence_agent/adapters/news/gdelt.py`
- Create: `src/due_diligence_agent/application/policies/content_rights.py`
- Create: `scripts/refresh_public_context_fixtures.py`
- Modify: `src/due_diligence_agent/ports/collectors.py`
- Test: `tests/contract/sources/test_market_news.py`
- Fixtures: `tests/fixtures/public_us_frozen_v1/market/*`
- Fixtures: `tests/fixtures/public_us_frozen_v1/news/*`

**Interfaces:**
- Produces: `MarketDataPort.get_snapshot()`, `NewsSourcePort.search()`, and source records that cannot masquerade as primary evidence.
- Consumes: `SourceSnapshot`, cache, and evidence policies from Tasks 4–5.

- [ ] **Step 1: Write failing licensing and provenance tests**

```python
# tests/contract/sources/test_market_news.py
def test_demo_market_snapshot_is_always_secondary(market_adapter):
    snapshot = market_adapter.from_fixture("market_history.csv")
    assert snapshot.unofficial is True
    assert snapshot.research_only is True
    assert snapshot.source_priority == "secondary_aggregator"


def test_news_discards_full_text_without_storage_rights(news_adapter):
    item = news_adapter.from_fixture("restricted_story.json")
    assert item.full_text is None
    assert item.title and item.url and item.snippet and item.published_at
```

- [ ] **Step 2: Run the adapter tests and confirm missing implementations**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/contract/sources/test_market_news.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Implement the strict content-rights policy**

```python
# src/due_diligence_agent/application/policies/content_rights.py
from enum import StrEnum


class LicenseClass(StrEnum):
    PUBLIC_PRIMARY = "public_primary"
    DISCOVERY_METADATA_ONLY = "discovery_metadata_only"
    RIGHTS_CLEARED_FULL_TEXT = "rights_cleared_full_text"
    RESEARCH_ONLY = "research_only"


def may_store_full_text(license_class: LicenseClass) -> bool:
    return license_class is LicenseClass.RIGHTS_CLEARED_FULL_TEXT
```

- [ ] **Step 4: Implement adapters and fixture-only test paths**

`YFinanceDemoAdapter` is installed only through `stage1a-market-yfinance-demo`; it tags every result `unofficial=True`, `research_only=True`. `GdeltNewsAdapter.search()` retains URL, publisher, title, snippet, publication timestamp, query, retrieval timestamp, and response hash. Full article text is discarded unless `may_store_full_text()` returns true. News facts may support event/narrative claims but never primary financial metrics.

- [ ] **Step 5: Verify tests without installing yfinance**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/contract/sources/test_market_news.py -v`

Expected: PASS using frozen fixture adapters. Then run the optional import smoke separately:

```powershell
uv sync --no-default-groups --group stage1a --group stage1a-market-yfinance-demo
uv run --no-default-groups --group stage1a --group stage1a-market-yfinance-demo python -c "import yfinance; print('optional market adapter ok')"
```

Refresh market/news context only through an explicit non-test command:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-market-yfinance-demo python scripts/refresh_public_context_fixtures.py --ticker AAPL --as-of 2026-06-30 --market-output tests/fixtures/public_us_frozen_v1/market --news-output tests/fixtures/public_us_frozen_v1/news
```

Expected: exit `0`; market records are marked unofficial/secondary/research-only, news files contain only URL/title/source/published timestamp/license/snippet metadata, and both manifests contain immutable hashes.

- [ ] **Step 6: Commit market/news adapters**

```powershell
git add src/due_diligence_agent/ports/collectors.py src/due_diligence_agent/adapters/market_data src/due_diligence_agent/adapters/news src/due_diligence_agent/application/policies/content_rights.py scripts/refresh_public_context_fixtures.py tests/contract/sources/test_market_news.py tests/fixtures/public_us_frozen_v1/market tests/fixtures/public_us_frozen_v1/news
git commit -m "feat: add governed market and news adapters"
```

---

### Task 7: Parse Filings and Build the Local Evidence Retrieval Index

**Files:**
- Create: `src/due_diligence_agent/ports/retrieval.py`
- Create: `src/due_diligence_agent/application/services/filing_parsing_service.py`
- Create: `src/due_diligence_agent/application/services/retrieval_service.py`
- Create: `src/due_diligence_agent/adapters/retrieval/local_embeddings.py`
- Create: `src/due_diligence_agent/adapters/retrieval/faiss_index.py`
- Create: `scripts/cache_embedding_model.py`
- Test: `tests/integration/retrieval/test_public_retrieval.py`

**Interfaces:**
- Produces: `EvidenceIndexPort.index()`, `search()`, stable chunk locators, and an offline model-artifact manifest.
- Consumes: SEC filing artifacts from Task 5 and local artifact storage from Task 3.

- [ ] **Step 1: Write the failing retrieval test**

```python
# tests/integration/retrieval/test_public_retrieval.py
def test_retrieval_returns_locators_without_copying_text_to_trace(frozen_filing, retrieval_service, trace_spy):
    retrieval_service.index_filing(frozen_filing)
    hits = retrieval_service.search("material liquidity risk", k=5)
    assert hits[0].locator.kind == "sec_filing_section"
    assert hits[0].artifact_id == frozen_filing.artifact_id
    assert all(hit.content_hash for hit in hits)
    assert "material liquidity risk" not in trace_spy.serialized_payload()
```

- [ ] **Step 2: Run the retrieval test and confirm missing contracts**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/integration/retrieval/test_public_retrieval.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define retrieval contracts**

```python
# src/due_diligence_agent/ports/retrieval.py
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID


class EvidenceIndexPort(Protocol):
    def index(self, chunks: Sequence["EvidenceChunk"]) -> None: ...
    def search(self, query: str, *, k: int, case_id: UUID) -> list["RetrievalHit"]: ...
```

`EvidenceChunk` contains `chunk_id`, `artifact_id`, locator, content hash, sensitivity, and local text reference. `RetrievalHit` returns the same IDs and score; raw text is loaded by the application service only after policy evaluation.

- [ ] **Step 4: Implement deterministic chunking, embeddings, and FAISS persistence**

Parse 10-K/10-Q HTML with BeautifulSoup into section-aware chunks. Use fixed chunk size/overlap and deterministic IDs derived from artifact hash, locator, and chunk index. `LocalEmbeddingAdapter` loads only a cached allowlisted model directory with `local_files_only=True`; it records model hash, license, model-card URL, and version in `model-manifest.json`. Gate B uses the CPU-friendly `intfloat/multilingual-e5-base` profile. Configuration may select `BAAI/bge-m3` only after a separate hardware, license, hash, memory, and offline-load smoke passes; changing models creates a new index version and reruns retrieval evaluation. `FaissEvidenceIndex` stores vectors plus an immutable JSON metadata sidecar.

- [ ] **Step 5: Cache the model explicitly and prove offline operation**

Run:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local python scripts/cache_embedding_model.py --model intfloat/multilingual-e5-base --output .local/models/multilingual-e5-base
$env:HF_HUB_OFFLINE='1'
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/integration/retrieval/test_public_retrieval.py -v
```

Expected: PASS with network disabled after the setup cache exists.

- [ ] **Step 6: Commit retrieval without committing downloaded model weights**

```powershell
git add src/due_diligence_agent/ports/retrieval.py src/due_diligence_agent/application/services/filing_parsing_service.py src/due_diligence_agent/application/services/retrieval_service.py src/due_diligence_agent/adapters/retrieval scripts/cache_embedding_model.py tests/integration/retrieval
git commit -m "feat: add offline filing evidence retrieval"
```

---

### Task 8: Implement the Versioned Deterministic Metric Engine

**Files:**
- Create: `src/due_diligence_agent/domain/metrics/definitions.py`
- Create: `src/due_diligence_agent/domain/metrics/engine.py`
- Create: `src/due_diligence_agent/domain/metrics/public_company.py`
- Create: `src/due_diligence_agent/application/services/public_metric_service.py`
- Test: `tests/unit/metrics/test_public_metrics.py`
- Golden: `tests/golden/public_us_frozen_v1/metrics.json`

**Interfaces:**
- Produces: `MetricEngine.calculate(definition, facts) -> Calculation` and registered public metric definitions.
- Consumes: normalized `EvidenceFact` IDs from the Evidence Ledger.

- [ ] **Step 1: Write failing exact-calculation tests**

```python
# tests/unit/metrics/test_public_metrics.py
from decimal import Decimal


def test_revenue_growth_uses_decimal_and_evidence_ids(metric_engine, fact):
    current = fact("revenue", "120", period="2025", unit="USD")
    prior = fact("revenue", "100", period="2024", unit="USD")
    result = metric_engine.calculate("revenue_growth", [current, prior])
    assert result.value == Decimal("0.2")
    assert result.input_evidence_ids == [current.id, prior.id]
    assert result.formula_version == "revenue_growth@1"


def test_division_by_zero_returns_insufficient_data(metric_engine, fact):
    result = metric_engine.calculate("current_ratio", [fact("assets", "10"), fact("liabilities", "0")])
    assert result.status == "insufficient_data"
```

- [ ] **Step 2: Run tests and confirm missing engine**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/metrics/test_public_metrics.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Implement metric definitions and registry**

```python
# src/due_diligence_agent/domain/metrics/definitions.py
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    version: str
    required_inputs: tuple[str, ...]
    unit: str
    formula: Callable[[dict[str, Decimal]], Decimal]


PUBLIC_METRICS = {
    "revenue_growth": MetricDefinition(
        name="revenue_growth", version="1", required_inputs=("current", "prior"), unit="ratio",
        formula=lambda v: (v["current"] / v["prior"]) - Decimal("1"),
    ),
    "gross_margin": MetricDefinition(
        name="gross_margin", version="1", required_inputs=("gross_profit", "revenue"), unit="ratio",
        formula=lambda v: v["gross_profit"] / v["revenue"],
    ),
}
```

- [ ] **Step 4: Add all required public metrics and validation**

Register revenue growth, gross/operating/net margin, free cash flow, net debt, current ratio, interest coverage, EV/Sales, EV/EBITDA, P/E, dilution, and working-capital trend. The engine validates units and periods, returns `insufficient_data` for missing/invalid denominators, emits warnings for incomparable periods, and stores formula version plus ordered evidence IDs.

- [ ] **Step 5: Run golden metric tests**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/metrics/test_public_metrics.py -v`

Expected: PASS with intermediate `Decimal` tolerance `1e-6` and exact display rounding from the metric definition.

- [ ] **Step 6: Commit the metric engine**

```powershell
git add src/due_diligence_agent/domain/metrics src/due_diligence_agent/application/services/public_metric_service.py tests/unit/metrics tests/golden/public_us_frozen_v1/metrics.json
git commit -m "feat: add deterministic public metric engine"
```

---

### Task 9: Add Durable Local Audit and OpenTelemetry Export Fallback

**Files:**
- Create: `src/due_diligence_agent/ports/tracing.py`
- Create: `src/due_diligence_agent/adapters/observability/context.py`
- Create: `src/due_diligence_agent/adapters/observability/privacy.py`
- Create: `src/due_diligence_agent/adapters/observability/audit_spool.py`
- Create: `src/due_diligence_agent/adapters/observability/metrics.py`
- Create: `src/due_diligence_agent/adapters/observability/otel.py`
- Test: `tests/unit/observability/test_audit_spool.py`
- Test: `tests/unit/observability/test_exporter_fallback.py`
- Test: `tests/unit/observability/test_metrics_contract.py`

**Interfaces:**
- Produces: `TraceContext`, `AuditEvent`, `AuditSpool`, `TraceSanitizer`, `configure_otel()`, and `DurableFallbackSpanExporter`.
- Consumes: content hashes and version metadata from Tasks 2–8.

- [ ] **Step 1: Write failing audit and outage tests**

```python
# tests/unit/observability/test_exporter_fallback.py
def test_exporter_failure_spools_sanitized_event_without_failing_workflow(tmp_path, failing_exporter):
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    exporter = DurableFallbackSpanExporter(failing_exporter, spool, sanitizer=StrictTraceSanitizer())
    result = exporter.export([unsafe_test_span(prompt="secret prompt", output="secret output")])
    assert result.name == "FAILURE"
    payload = "".join(path.read_text() for path in tmp_path.rglob("*.jsonl"))
    assert "secret prompt" not in payload
    assert "secret output" not in payload
    assert '"span_name":"llm.call"' in payload
```

- [ ] **Step 2: Run tests and confirm observability modules are absent**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/observability/test_audit_spool.py tests/unit/observability/test_exporter_fallback.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define trace and audit contracts**

```python
# src/due_diligence_agent/ports/tracing.py
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class TraceContext:
    request_id: str
    run_id: str
    case_id: str
    correlation_id: str
    workflow_type: Literal["public_company", "startup"]
    app_version: str
    graph_version: str
    redaction_policy_version: str


@dataclass(frozen=True)
class AuditEvent:
    schema_version: str
    event_id: str
    timestamp_utc: str
    run_id: str
    correlation_id: str
    span_name: str
    event_type: str
    attributes: Mapping[str, str | int | float | bool | None]


class AuditSpool(Protocol):
    def append(self, event: AuditEvent) -> str: ...
    def read_batch(self, limit: int = 100) -> list[AuditEvent]: ...
    def mark_flushed(self, event_ids: Sequence[str]) -> None: ...
```

- [ ] **Step 4: Implement sanitized JSONL spool and OTel setup**

Use `.local/audit-spool/YYYY/MM/DD/<run_id>.jsonl`, UTF-8, one canonical JSON event per line, atomic append, 256 MB default rotation, and no payload fields. `configure_otel()` sets `service.name=investment-due-diligence-agent`, uses `BatchSpanProcessor`, and instruments mandatory spans: `workflow.invoke`, `sec.fetch`, `document.ingest`, `chunk.create`, `embedding.create`, `retrieval.search`, `llm.call`, `analysis.module`, and `report.generate`. The same `correlation_id` is stored in the local audit event, OTel span, sanitized LangSmith metadata, workflow state, and `ReportSnapshot`.

`metrics.py` registers privacy-safe counters/histograms for workflow/node outcomes and duration, collector/provider calls, retries, fallbacks, policy denials, budget denials, audit-spool bytes, and report-render outcomes. Metric attributes use the same allowlist as traces and never include case/company/person names or raw source values.

`StrictTraceSanitizer` allowlists IDs/hashes, versions, public SEC identifiers, counts, latency, tokens, cost, status, and scores. It rejects `input.value`, `output.value`, GenAI messages/system instructions/tool arguments/results, retrieval content, and exception text before persistence or export.

- [ ] **Step 5: Test exporter outage and audit failure policy**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/observability -v`

Expected: invalid exporter endpoint does not fail a workflow-sized test; sanitized event is spooled. A forced spool-write failure raises `AUDIT_PERSISTENCE_ERROR` when `audit_required=True`. Metrics-contract tests prove the required instrument names exist and reject disallowed attribute keys.

- [ ] **Step 6: Commit local observability**

```powershell
git add src/due_diligence_agent/ports/tracing.py src/due_diligence_agent/adapters/observability tests/unit/observability
git commit -m "feat: add durable privacy-safe audit tracing"
```

---

### Task 10: Implement Data Egress Policy, OpenAI Gateway, and Sanitized LangSmith

**Files:**
- Create: `src/due_diligence_agent/ports/llm.py`
- Create: `src/due_diligence_agent/application/policies/data_egress.py`
- Create: `src/due_diligence_agent/application/policies/budget.py`
- Create: `src/due_diligence_agent/application/policies/model_routing.py`
- Create: `src/due_diligence_agent/adapters/openai/gateway.py`
- Create: `src/due_diligence_agent/adapters/openai/code_interpreter.py`
- Create: `src/due_diligence_agent/adapters/observability/langsmith.py`
- Test: `tests/privacy/test_ai_egress.py`
- Test: `tests/privacy/test_langsmith_masking.py`
- Test: `tests/contract/test_foundation_gate.py`
- Test: `tests/unit/llm/test_budget_guard.py`
- Test: `tests/unit/llm/test_code_interpreter.py`
- Test: `tests/unit/llm/test_model_fallback.py`

**Interfaces:**
- Produces: `LLMGatewayPort.complete_structured()`, `CodeInterpreterPort.run_public_analysis()`, `DisclosureScope`, `EgressDecision`, `DataEgressDenied`, `DataEgressPolicy.evaluate()`, `BudgetGuard.reserve()`, and `ModelRoutingPolicy.select()`.
- Consumes: trace sanitizer/audit from Task 9 and sensitivity metadata from Task 2.

- [ ] **Step 1: Write failing privacy and fallback tests**

```python
# tests/privacy/test_ai_egress.py
import pytest


@pytest.mark.asyncio
async def test_restricted_context_never_reaches_external_provider(gateway, provider_spy):
    with pytest.raises(DataEgressDenied):
        await gateway.complete_structured(
            task="risk_analysis", context=[restricted_fragment("John, john@example.com")], schema=RiskOutput,
        )
    assert provider_spy.calls == []


@pytest.mark.asyncio
async def test_fallback_rechecks_policy_and_preserves_schema(gateway_with_failing_primary):
    result = await gateway_with_failing_primary.complete_structured(
        task="public_risk", context=[public_fragment("10-K liquidity risk")], schema=RiskOutput,
    )
    assert isinstance(result.data, RiskOutput)
    assert result.fallback_used == "high_reasoning_verifier"
    assert result.errors == ["PRIMARY_TIMEOUT"]
```

```python
# tests/unit/llm/test_budget_guard.py
import pytest

from due_diligence_agent.application.policies.budget import BudgetExceeded


@pytest.mark.asyncio
async def test_hard_budget_blocks_provider_call(gateway, provider_spy, exhausted_case_budget, risk_schema):
    with pytest.raises(BudgetExceeded):
        await gateway.complete_structured(
            task="public_risk",
            context=[public_fragment("10-K liquidity risk")],
            schema=risk_schema,
            budget=exhausted_case_budget,
        )

    assert provider_spy.calls == []
```

```python
# tests/unit/llm/test_code_interpreter.py
def test_code_interpreter_output_is_provisional(code_interpreter, public_analysis_artifact):
    result = code_interpreter.run_public_analysis(public_analysis_artifact)

    assert result.provisional is True
    assert result.code_hash
    assert result.output_artifact_id
    assert result.canonical_calculation_ids == []
```

```python
# tests/contract/test_foundation_gate.py
def test_gate_a_shared_foundation_contracts_are_importable():
    from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
    from due_diligence_agent.domain.artifacts.models import Artifact, StoredArtifact
    from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
    from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest
    from due_diligence_agent.ports.repositories import ArtifactStore, EvidenceRepository
    from due_diligence_agent.ports.tracing import AuditSpool, TraceSanitizer
    from due_diligence_agent.workflows.shared.node_result import NodeResult

    assert all(
        (
            Artifact,
            StoredArtifact,
            EvidenceFact,
            Calculation,
            ReportSnapshot,
            ReproducibilityManifest,
            ArtifactStore,
            EvidenceRepository,
            AuditSpool,
            TraceSanitizer,
            DataEgressPolicy,
            NodeResult,
        )
    )
```

- [ ] **Step 2: Run tests and confirm missing gateway**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/privacy/test_ai_egress.py tests/contract/test_foundation_gate.py tests/unit/llm/test_budget_guard.py tests/unit/llm/test_code_interpreter.py tests/unit/llm/test_model_fallback.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define egress and model-routing decisions**

```python
# src/due_diligence_agent/application/policies/data_egress.py
from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from due_diligence_agent.domain.common import SensitivityClass


class DisclosureScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    approval_id: UUID
    allowed_classes: frozenset[SensitivityClass]
    approved_redaction_policy_version: str


class EgressFragment(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    sensitivity: SensitivityClass
    redacted: bool
    minimized: bool
    redaction_policy_version: str


class EgressDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: str
    policy_version: str
    allowed_fragment_ids: list[str] = Field(default_factory=list)
    approval_id: UUID | None = None


class DataEgressDenied(RuntimeError):
    def __init__(self, decision: EgressDecision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


class DataEgressPolicy:
    version = "egress@1"

    def evaluate(
        self,
        fragments: Sequence[EgressFragment],
        *,
        destination: str,
        disclosure_scope: DisclosureScope | None = None,
    ) -> EgressDecision:
        if any(f.sensitivity is SensitivityClass.RESTRICTED for f in fragments):
            return EgressDecision(
                allowed=False,
                reason="restricted_data",
                policy_version=self.version,
            )
        non_public = {
            fragment.sensitivity
            for fragment in fragments
            if fragment.sensitivity is not SensitivityClass.PUBLIC
        }
        if non_public:
            if disclosure_scope is None or not non_public.issubset(
                disclosure_scope.allowed_classes
            ):
                return EgressDecision(
                    allowed=False,
                    reason="approval_required",
                    policy_version=self.version,
                )
            approved_version = disclosure_scope.approved_redaction_policy_version
            if any(f.redaction_policy_version != approved_version for f in fragments):
                return EgressDecision(
                    allowed=False,
                    reason="approval_required",
                    policy_version=self.version,
                )
            if any(not f.redacted or not f.minimized for f in fragments):
                return EgressDecision(
                    allowed=False,
                    reason="redaction_required",
                    policy_version=self.version,
                )
        return EgressDecision(
            allowed=True,
            reason="public_or_approved",
            policy_version=self.version,
            allowed_fragment_ids=[str(f.id) for f in fragments],
            approval_id=disclosure_scope.approval_id if disclosure_scope else None,
        )
```

The policy also validates that `disclosure_scope.approved_redaction_policy_version` matches the fragments' current redaction-policy version. Any new or higher sensitivity class, reclassification, destination change, or policy-version change invalidates the scope and returns `approval_required`. Public Company calls use no scope and pass only `PUBLIC` fragments.

- [ ] **Step 4: Implement structured Responses API calls and provisional Code Interpreter**

`LLMGatewayPort.complete_structured()` and `OpenAIGateway.complete_structured()` accept task name, fragment IDs, expected Pydantic model, budget, routing context, and optional `DisclosureScope`. The gateway always calls `DataEgressPolicy.evaluate()` immediately before each primary or fallback request; a denied decision raises `DataEgressDenied` before provider invocation. It sends only policy-approved minimized text, parses directly to the schema, permits one schema-repair attempt, records prompt/schema/model versions, and writes a sanitized disclosure audit. Default OpenAI profile maps standard tasks to GPT-5.6 Terra and high-reasoning verifier/arbiter tasks to GPT-5.6 Sol through configuration rather than domain imports.

`BudgetGuard.reserve()` atomically checks the per-case token and cost ceilings before the primary call, schema-repair call, Code Interpreter call, and every fallback. A call whose worst-case reservation exceeds either remaining limit raises `BudgetExceeded` before provider invocation. Completion records reconcile reserved versus actual usage in the durable audit; unused reservation is released, while provider-reported usage remains append-only.

`OpenAICodeInterpreterAdapter` accepts only public or explicitly approved sanitized artifacts. Its code, stdout/stderr metadata, and generated files are stored as content-addressed provisional artifacts with hashes; raw payloads do not enter traces. Outputs are tagged `provisional=True`; canonical numeric output must be recomputed by `MetricEngine` before entering a finding.

- [ ] **Step 5: Configure sanitized LangSmith as optional export**

Set `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true` when enabled. Provide hide functions that return empty inputs/outputs and sanitize metadata with the same allowlist as OTel. Mock tests assert that no prompts, completions, chunks, files, PII, or tool payloads are attached.

Install and test this adapter only through its explicit optional group:

```powershell
uv sync --no-default-groups --group stage1a --group stage1a-rag-local --group observability-langsmith --group dev
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group observability-langsmith --group dev pytest tests/privacy/test_langsmith_masking.py -v
```

Expected: PASS; mocked LangSmith inputs and outputs are empty, metadata contains only allowlisted hashes/IDs/versions/counts, and disabling the group leaves local OTel/audit fully functional through a lazy adapter import.

- [ ] **Step 6: Run privacy, fallback, and trace-contract tests**

Run:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/privacy tests/unit/llm tests/unit/observability -v
```

Expected: PASS; privacy leak count is zero; fallback preserves schema and primary error.

- [ ] **Step 7: Run Gate A before workflow implementation**

Run:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/unit/domain tests/integration/storage tests/unit/evidence tests/unit/observability tests/privacy tests/contract/test_foundation_gate.py -v
```

Expected: PASS; the shared domain, ports, local repositories, immutable storage, Evidence Ledger, `ReportSnapshot`, reproducibility manifest, local audit, trace sanitizer, and egress boundary are verified before Task 11 starts.

- [ ] **Step 8: Commit the governed AI boundary and Gate A**

```powershell
git add src/due_diligence_agent/ports/llm.py src/due_diligence_agent/application/policies src/due_diligence_agent/adapters/openai src/due_diligence_agent/adapters/observability/langsmith.py tests/privacy tests/unit/llm tests/contract/test_foundation_gate.py
git commit -m "feat: add privacy-governed AI gateway"
```

---

### Task 11: Build the Public Plan-and-Execute LangGraph with Checkpoints

**Files:**
- Create: `src/due_diligence_agent/workflows/public_company/state.py`
- Create: `src/due_diligence_agent/workflows/shared/plan.py`
- Create: `src/due_diligence_agent/workflows/public_company/plan.py`
- Create: `src/due_diligence_agent/workflows/public_company/nodes/scope.py`
- Create: `src/due_diligence_agent/workflows/public_company/nodes/collect.py`
- Create: `src/due_diligence_agent/workflows/public_company/nodes/normalize.py`
- Create: `src/due_diligence_agent/workflows/public_company/nodes/metrics.py`
- Create: `src/due_diligence_agent/workflows/public_company/graph.py`
- Create: `src/due_diligence_agent/application/services/public_analysis_service.py`
- Test: `tests/graph/test_public_collection_graph.py`

**Interfaces:**
- Produces: shared `PlanStep`/`AnalysisPlan`, `PublicCaseState`, public node registry/plan validator, `build_public_graph()`, and `PublicAnalysisService.start()/resume()`.
- Consumes: source adapters, evidence ledger, retrieval, metrics, AI gateway, repositories, audit, and `NodeResult`.

- [ ] **Step 1: Write failing graph and checkpoint tests**

```python
# tests/graph/test_public_collection_graph.py
import json

from langgraph.types import Command


def test_public_graph_pauses_for_scope_and_resumes_from_sqlite(public_graph, thread_config):
    first = public_graph.invoke({"ticker": "AAPL", "case_id": "case-1"}, config=thread_config)
    assert first["status"] == "awaiting_scope_approval"
    resumed = public_graph.invoke(Command(resume={"approved": True}), config=thread_config)
    assert resumed["case_id"] == "case-1"
    assert resumed["evidence_fact_ids"]


def test_state_contains_ids_not_raw_filing_text(completed_public_state):
    serialized = json.dumps(completed_public_state)
    assert "<html" not in serialized.lower()
    assert completed_public_state["artifact_ids"]
```

- [ ] **Step 2: Run tests and confirm the graph is missing**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/graph/test_public_collection_graph.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Define typed plan and compact state**

```python
# src/due_diligence_agent/workflows/shared/plan.py
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    task_id: str
    node_name: str
    depends_on: list[str] = Field(default_factory=list)
    required_output_schema: str


class AnalysisPlan(BaseModel):
    objectives: list[str]
    steps: list[PlanStep]
    token_budget: int
    max_reflexion_rounds: int = Field(default=2, ge=0, le=2)
```

`public_company/plan.py` initially validates `node_name` against `collect_sec`, `collect_market`, `collect_news`, `retrieve`, and `calculate`; dependencies must form an acyclic graph and every `required_output_schema` must be registered. Task 12 extends the same registry with analysis/reflexion/synthesis nodes. `PublicCaseState` contains case/ticker/as-of/status, compact plan, artifact/evidence/calculation/finding/contradiction IDs, warnings/errors, approvals, Reflexion round count, report snapshot ID, correlation ID, and trace ID. It never contains raw filing/news text.

- [ ] **Step 4: Implement Gate 1 and collection execution**

Use LangGraph `interrupt()` for scope confirmation. After approval, the plan node emits a validated `AnalysisPlan`; SEC, market, and news nodes may run in parallel, while normalization waits for collectors. Every node returns `NodeResult`, records a local audit event, and writes only IDs to state. Apply graph retry only to `RETRYABLE_ERROR`, at most three node attempts, honoring `retry_after_seconds`; privacy/policy denial, invalid schema after one repair, budget denial, unsupported jurisdiction, and deterministic validation failures are never retried. Every retry/fallback rechecks budget and egress policy and preserves the primary failure. Persist checkpoints with SQLite using `case_id` as thread ID.

- [ ] **Step 5: Verify happy path, partial source failure, and restart**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/graph/test_public_collection_graph.py -v`

Expected: PASS for happy path, news partial failure, missing-primary blocked path, Gate 1 resume, and process-restart checkpoint recovery.

- [ ] **Step 6: Commit the collection graph**

```powershell
git add src/due_diligence_agent/workflows/shared/plan.py src/due_diligence_agent/workflows/public_company src/due_diligence_agent/application/services/public_analysis_service.py tests/graph/test_public_collection_graph.py
git commit -m "feat: add checkpointed public analysis workflow"
```

---

### Task 12: Add Risk Analysis, Bounded Reflexion, and HITL Gates 3–4

**Files:**
- Create: `src/due_diligence_agent/domain/findings/risk.py`
- Create: `src/due_diligence_agent/workflows/shared/reflexion.py`
- Create: `src/due_diligence_agent/workflows/public_company/nodes/financial_analysis.py`
- Create: `src/due_diligence_agent/workflows/public_company/nodes/risk_analysis.py`
- Create: `src/due_diligence_agent/workflows/public_company/nodes/market_analysis.py`
- Create: `src/due_diligence_agent/workflows/public_company/nodes/reflexion.py`
- Create: `src/due_diligence_agent/workflows/public_company/nodes/approvals.py`
- Modify: `src/due_diligence_agent/workflows/public_company/plan.py`
- Modify: `src/due_diligence_agent/workflows/public_company/graph.py`
- Test: `tests/graph/test_public_reflexion_hitl.py`

**Interfaces:**
- Produces: evidence-backed financial/risk/market findings, `RiskFinding`, `ReflexionDecision`, `should_continue_reflexion()`, Gate 3 contradiction actions, and Gate 4 snapshot approval.
- Consumes: public graph state, LLM gateway, Evidence Ledger, and calculations.

- [ ] **Step 1: Write failing Reflexion/HITL tests**

```python
# tests/graph/test_public_reflexion_hitl.py
def test_reflexion_stops_after_two_rounds_even_when_critic_requests_more(make_state):
    state = make_state(reflexion_rounds=2, new_evidence_ids=["fact-2"])
    assert should_continue_reflexion(state, max_rounds=2) is False


def test_excluding_artifact_invalidates_dependents(approval_service, seeded_dependencies):
    result = approval_service.exclude_artifact(seeded_dependencies.artifact_id, actor="reviewer")
    assert set(result.invalidated_fact_ids) == set(seeded_dependencies.fact_ids)
    assert result.report_snapshot_invalidated is True


def test_rejected_freeze_never_creates_final_pdf(report_service, draft_snapshot):
    outcome = report_service.apply_freeze_decision(draft_snapshot.id, approved=False, actor="reviewer")
    assert outcome.final_pdf_allowed is False
```

- [ ] **Step 2: Run tests and confirm missing decision logic**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/graph/test_public_reflexion_hitl.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Implement typed risk and Reflexion decisions**

```python
class ReflexionDecision(BaseModel):
    continue_loop: bool
    reason: Literal["verified", "new_counter_evidence", "no_progress", "max_rounds", "insufficient_data"]
    new_evidence_ids: list[str] = Field(default_factory=list)
    updated_finding_ids: list[str] = Field(default_factory=list)


def should_continue_reflexion(state: PublicCaseState, *, max_rounds: int = 2) -> bool:
    return state["reflexion_rounds"] < max_rounds and bool(state["new_evidence_ids"] or state["updated_finding_ids"])
```

Extend the public node registry with `financial_analysis`, `risk_analysis`, `market_analysis`, `reflexion`, and `synthesize`. Financial analysis interprets only registered calculations and normalized evidence; when Code Interpreter is configured, it may add exploratory public-data analyses, but every numeric candidate must be recalculated by `MetricEngine` before the finding status can become verified. Market analysis combines market metadata, corporate events, and a labeled news polarity summary while preserving their secondary-source status. Risk findings include category, probability, impact, severity, evidence/calculation IDs, counter-evidence IDs, confidence, and status. All three specialized nodes emit the shared `Finding` contract rather than maintaining independent agent memory. The critic can change finding status or add counter-evidence; it cannot edit facts or calculations.

- [ ] **Step 4: Wire Gate 3 and Gate 4 consequences**

Gate 3 supports accept source, exclude artifact, request evidence, reclassify, and leave unresolved. Artifact exclusion invalidates the complete dependency chain and affected snapshot. Unresolved critical contradictions are forced into Executive Summary. Gate 4 rejection preserves draft JSON/HTML and blocks final PDF; approval creates an immutable snapshot.

- [ ] **Step 5: Run graph risk/HITL tests**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/graph/test_public_reflexion_hitl.py tests/graph/test_public_collection_graph.py -v`

Expected: PASS; every loop is bounded and every approval creates an audit event.

- [ ] **Step 6: Commit risk and HITL behavior**

```powershell
git add src/due_diligence_agent/domain/findings src/due_diligence_agent/workflows/shared/reflexion.py src/due_diligence_agent/workflows/public_company src/due_diligence_agent/application/services tests/graph
git commit -m "feat: add bounded reflexion and review gates"
```

---

### Task 13: Build Canonical Report JSON, Charts, HTML, and PDF

**Files:**
- Create: `src/due_diligence_agent/ports/rendering.py`
- Create: `src/due_diligence_agent/application/services/report_service.py`
- Create: `src/due_diligence_agent/adapters/reports/charts.py`
- Create: `src/due_diligence_agent/adapters/reports/html_renderer.py`
- Create: `src/due_diligence_agent/adapters/reports/pdf_renderer.py`
- Create: `src/due_diligence_agent/adapters/reports/reportlab_renderer.py`
- Create: `src/due_diligence_agent/adapters/reports/templates/public_report.html.j2`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/e2e/test_public_report.py`

**Interfaces:**
- Produces: `ReportBuilder.build_public() -> ReportSnapshot`, `HtmlRenderer.render()`, and `PdfRenderer.render()`.
- Consumes: approved state/facts/calculations/findings, Gate 4 decision, audit trace IDs, and dependency/version metadata.

- [ ] **Step 1: Write failing report-contract tests**

```python
# tests/e2e/test_public_report.py
import pytest

from due_diligence_agent.application.services.report_service import ReportFreezeRequired


def test_report_json_is_canonical_and_contains_required_sections(report_service, approved_public_case):
    snapshot = report_service.build_public(approved_public_case)
    assert snapshot.sections.keys() >= {
        "metadata", "executive_summary", "investment_thesis", "counter_thesis",
        "company_profile", "evidence_coverage", "financial_metrics", "risk_matrix",
        "contradictions", "missing_data", "next_steps", "methodology",
        "source_and_calculation_appendix", "disclaimer", "decision_owner",
        "filing_timeline", "financial_trends", "capital_structure", "valuation",
        "sec_risk_factor_changes", "corporate_events", "news_coverage",
    }
    assert snapshot.reproducibility.dependency_lock_hash
    assert snapshot.trace_ids


def test_final_pdf_requires_freeze_approval(report_service, draft_snapshot, tmp_path):
    with pytest.raises(ReportFreezeRequired):
        report_service.render_final_pdf(draft_snapshot, tmp_path)


def test_reportlab_fallback_preserves_snapshot_identity(
    report_service_with_failing_weasyprint,
    approved_snapshot,
    tmp_path,
):
    result = report_service_with_failing_weasyprint.render_final_pdf(
        approved_snapshot,
        tmp_path,
    )

    assert result.pdf_path.read_bytes().startswith(b"%PDF")
    assert result.snapshot_id == approved_snapshot.id
    assert result.fallback_used == "reportlab"
```

- [ ] **Step 2: Run tests and confirm renderers are missing**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/e2e/test_public_report.py -v`

Expected: FAIL on imports.

- [ ] **Step 3: Implement canonical report building and reproducibility manifest**

```python
class ReportBuilder:
    def build_public(self, case: DueDiligenceCase, facts, calculations, findings, contradictions) -> ReportSnapshot:
        sections = build_required_public_sections(case, facts, calculations, findings, contradictions)
        manifest = ReproducibilityManifest.capture(
            code_commit=current_git_commit(),
            dependency_lock_hash=sha256_file(Path("uv.lock")),
            graph_version="public-graph@1",
            redaction_policy_version="egress@1",
        )
        return ReportSnapshot.create(case_id=case.id, sections=sections, reproducibility=manifest)
```

The snapshot records code/build ID, Python/packages, model alias resolution and reasoning settings, adapter/parser/embedding/index versions, source hashes/timestamps, timezone/locale, FX source, configuration hash, and deterministic seeds. It never embeds raw source documents.

- [ ] **Step 4: Implement charts and safe renderers**

Use Plotly for UI. Use Matplotlib as the deterministic default static renderer. `HtmlRenderer` renders a server-owned Jinja template with autoescape and no external URL loading. `PdfRenderer` uses WeasyPrint on the generated HTML. Smoke the optional ReportLab backend, then add `{ include-group = "reportlab-fallback" }` to `stage1a`; `ReportLabRenderer` is used only for a typed WeasyPrint backend/runtime failure and records the primary failure plus `fallback_used="reportlab"`. Schema, approval, privacy, template-sanitization, or content-validation failures never trigger fallback. The mandatory disclaimer states that the report is analytical support, not legal/tax/personal investment advice, performs no transaction, requires human decision, and is limited by sources/date/jurisdiction.

Run before enabling the fallback in `stage1a`:

```powershell
uv sync --no-default-groups --group stage1a --group stage1a-rag-local --group reportlab-fallback --group dev
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group reportlab-fallback python -c "import reportlab; print('reportlab fallback ok')"
```

After that smoke passes, update the aggregate group so every normal Stage 1A report run includes the verified fallback:

```toml
# pyproject.toml
stage1a = [
  { include-group = "core" },
  { include-group = "workflow" },
  { include-group = "llm-openai" },
  { include-group = "observability-local" },
  { include-group = "stage1a-data" },
  { include-group = "stage1a-ui-report" },
  { include-group = "reportlab-fallback" },
]
```

Expected: `reportlab fallback ok`; the forced-WeasyPrint-failure test produces a structurally complete PDF from the same immutable snapshot and records the fallback.

- [ ] **Step 5: Verify JSON/HTML/PDF artifacts and hashes**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/e2e/test_public_report.py -v`

Expected: PASS; PDF begins with `%PDF`; JSON and HTML hashes match the snapshot manifest; rejected Gate 4 produces draft-only JSON/HTML.

- [ ] **Step 6: Commit reporting**

```powershell
git add pyproject.toml uv.lock src/due_diligence_agent/ports/rendering.py src/due_diligence_agent/application/services/report_service.py src/due_diligence_agent/adapters/reports tests/e2e/test_public_report.py
git commit -m "feat: generate reproducible public reports"
```

---

### Task 14: Assemble the Application, CLI, and Streamlit Public UI

**Files:**
- Create: `src/due_diligence_agent/bootstrap/container.py`
- Create: `src/due_diligence_agent/presentation/cli.py`
- Create: `src/due_diligence_agent/presentation/streamlit/app.py`
- Create: `src/due_diligence_agent/presentation/streamlit/pages/public_case.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/evidence.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/metrics.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/risks.py`
- Create: `src/due_diligence_agent/presentation/streamlit/components/audit.py`
- Modify: `pyproject.toml`
- Test: `tests/smoke/test_application_boot.py`

**Interfaces:**
- Produces: `build_container(settings) -> AppContainer`, CLI commands `run-public`/`run-eval`, and one shared Streamlit shell.
- Consumes: all Stage 1A ports/adapters/services/workflows.

- [ ] **Step 1: Write the failing application smoke test**

```python
# tests/smoke/test_application_boot.py
def test_local_container_boots_without_network_or_api_key(local_settings):
    container = build_container(local_settings, use_fixture_adapters=True)
    assert container.public_analysis_service is not None
    assert container.audit_spool is not None
    assert container.settings.langsmith_tracing is False
```

- [ ] **Step 2: Run the smoke test and confirm bootstrap is missing**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/smoke/test_application_boot.py -v`

Expected: FAIL on import.

- [ ] **Step 3: Implement explicit dependency composition**

```python
@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    public_analysis_service: PublicAnalysisService
    report_service: ReportService
    audit_spool: AuditSpool


def build_container(settings: Settings, *, use_fixture_adapters: bool = False) -> AppContainer:
    repositories = build_local_repositories(settings.data_dir / "metadata.sqlite3")
    sources = build_fixture_sources() if use_fixture_adapters else build_live_sources(settings)
    audit = JsonlAuditSpool(settings.data_dir / "audit-spool")
    return compose_services(settings, repositories, sources, audit)
```

No module-level network clients, databases, or model downloads are allowed. Bootstrap creates every adapter explicitly.

- [ ] **Step 4: Implement CLI and Streamlit flow**

CLI:

```text
uv run --no-default-groups --group stage1a --group stage1a-rag-local python -m due_diligence_agent.presentation.cli run-public --ticker AAPL --as-of 2026-06-30 --fixture public_us_frozen_v1
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas python -m due_diligence_agent.presentation.cli run-eval --dataset public_us_frozen_v1
```

Streamlit pages expose New Case, source inventory, workflow status, Evidence Ledger, metrics/charts, risk matrix, contradictions/HITL inbox, sanitized trace summary, report preview, and approved download. Unsupported Startup mode is displayed as unavailable in Stage 1A; no dummy workflow is registered.

- [ ] **Step 5: Add project entry points and run smoke tests**

Add to `pyproject.toml`:

```toml
[project.scripts]
investment-dd = "due_diligence_agent.presentation.cli:main"
```

Run:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group dev pytest tests/smoke/test_application_boot.py -v
uv run --no-default-groups --group stage1a --group stage1a-rag-local python -m due_diligence_agent.presentation.cli --help
```

Expected: PASS and CLI usage output.

- [ ] **Step 6: Commit the application shell**

```powershell
git add pyproject.toml uv.lock src/due_diligence_agent/bootstrap src/due_diligence_agent/presentation tests/smoke
git commit -m "feat: add local public analysis application"
```

---

### Task 15: Freeze `public_us_frozen_v1` and Enforce Gate B

**Files:**
- Create: `src/due_diligence_agent/evals/metrics.py`
- Create: `src/due_diligence_agent/evals/runner.py`
- Create: `tests/fixtures/public_us_frozen_v1/manifest.json`
- Create: `tests/golden/public_us_frozen_v1/report_snapshot.json`
- Create: `tests/evaluation/test_public_us_frozen_v1.py`
- Create: `tests/e2e/test_public_case_e2e.py`
- Create: `scripts/run_stage1a_eval.ps1`
- Modify: `README.md`

**Interfaces:**
- Produces: `EvaluationResult`, `run_public_eval(dataset)`, a copy-paste Gate B command, and a complete offline public-company demonstration.
- Consumes: the assembled Stage 1A application from Tasks 1–14.

- [ ] **Step 1: Write the failing Gate B test**

```python
# tests/evaluation/test_public_us_frozen_v1.py
def test_public_us_frozen_v1_meets_blocking_thresholds(eval_runner):
    result = eval_runner.run("public_us_frozen_v1")
    assert result.schema_validity == 1.0
    assert result.critical_evidence_coverage == 1.0
    assert result.unsupported_critical_claim_rate == 0.0
    assert result.numerical_accuracy == 1.0
    assert result.unit_period_consistency == 1.0
    assert result.retrieval_recall_at_5 >= 0.90
    assert result.privacy_leak_count == 0
    assert result.trace_completeness == 1.0
    assert result.reflexion_max_rounds <= 2
    assert result.budget_violations == 0
    assert result.offline_latency_minutes <= 15
    assert result.report_completeness == 1.0
    assert result.exporter_outage_non_blocking is True
    assert result.checkpoint_recovery is True
```

- [ ] **Step 2: Run the evaluation test and confirm the runner is absent**

Run: `uv run --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas --group dev pytest tests/evaluation/test_public_us_frozen_v1.py -v`

Expected: FAIL on import.

- [ ] **Step 3: Build the frozen dataset manifest and evaluators**

Use one supported SEC issuer snapshot with 10-K, 10-Q, Company Facts, market fixture, at least five news metadata records, 20 labeled retrieval queries, expected metrics, expected source locators, source hashes, and `as_of`. Add negative scenarios: SEC 429, missing filing, malformed JSON, stale market quote, restricted article payload, LLM timeout, exporter outage, and process restart.

`EvaluationResult` calculates every threshold from artifacts rather than hardcoded success flags. Use Ragas only for retrieval/evidence-grounding diagnostics over the 20 labeled queries and only in configurations that consume frozen references/local embeddings without an external judge call; any Ragas metric requiring an LLM judge is non-blocking and disabled in offline CI. Required recall@5, citation coverage, financial correctness, contradiction status, privacy, budgets, and report completeness remain deterministic custom evaluators. The runner writes `eval-result.json` with dataset hash, lock hash, commit ID, environment versions, measured latency, configured token/cost budget, unit/period consistency, and pass/fail reasons. The news fixture has labeled positive/neutral/negative metadata examples; the evaluator checks the simple polarity label without treating news as evidence for financial facts.

- [ ] **Step 4: Add the end-to-end offline case**

```python
# tests/e2e/test_public_case_e2e.py
def test_ticker_to_approved_pdf_offline(fixture_container, tmp_path):
    case = fixture_container.case_service.create_public_case("AAPL", as_of="2026-06-30")
    state = fixture_container.public_analysis_service.run_with_approvals(case.id, approve_all=True)
    outputs = fixture_container.report_service.render_approved(state.report_snapshot_id, tmp_path)
    assert outputs.json.exists() and outputs.html.exists() and outputs.pdf.exists()
    assert state.status == "completed"
```

- [ ] **Step 5: Run targeted evaluation and fix only measured failures**

Run:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas --group dev pytest tests/evaluation/test_public_us_frozen_v1.py tests/e2e/test_public_case_e2e.py -v
```

Expected: PASS; offline runtime is at most 15 minutes on the documented reference machine, excluding HITL wait.

- [ ] **Step 6: Run the full Stage 1A quality gate**

Run:

```powershell
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas --group dev ruff check .
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas --group dev mypy src
uv run --no-default-groups --group stage1a --group stage1a-rag-local --group eval-ragas --group dev pytest --cov=due_diligence_agent --cov-report=term-missing
```

Expected: all commands exit `0`; Gate A and Gate B criteria pass. Record Python/uv versions and `uv.lock` hash in `eval-result.json`.

- [ ] **Step 7: Commit the verified Stage 1A vertical slice**

```powershell
git add src/due_diligence_agent/evals tests/fixtures tests/golden tests/evaluation tests/e2e scripts/run_stage1a_eval.ps1 README.md
git commit -m "test: verify public company local MVP"
```

## Stage 1A Completion Evidence

Before starting Stage 1B, attach these artifacts to the implementation handoff:

- `eval-result.json` with Gate B pass;
- Report JSON, HTML, and PDF from `public_us_frozen_v1`;
- local sanitized audit JSONL;
- `uv.lock` hash and runtime manifest;
- full lint, typecheck, and pytest output;
- proof that invalid OTLP/LangSmith export does not stop the case while local audit remains durable;
- proof that checkpoint resume works after a simulated restart.
