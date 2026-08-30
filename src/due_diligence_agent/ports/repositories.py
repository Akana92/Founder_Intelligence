from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.artifacts.models import Artifact, StoredArtifact
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.reports.models import ReportSnapshot
from due_diligence_agent.domain.startup.assets import CaseAssetDraft
from due_diligence_agent.domain.startup.case_intake import CaseValueKind, FounderStatement
from due_diligence_agent.domain.startup.copilot import CopilotThread
from due_diligence_agent.domain.startup.market import StartupMarketResearchSnapshot
from due_diligence_agent.domain.startup.profile import StartupProfile, StartupProfileAnalysisStage
from due_diligence_agent.domain.startup.scenario import (
    ScenarioInput,
    ScenarioSelectionRecord,
    StartupScenarioSet,
)

_PUBLIC_BENCHMARK_INPUT_KEYS = frozenset({"acquisition_spend", "arpa", "monthly_price"})

CaseResearchJobStatus = Literal[
    "planned",
    "queued",
    "running",
    "completed",
    "partial",
    "deferred",
    "blocked",
    "failed",
]
ResearchAcquisitionMode = Literal[
    "deterministic_offline_fixture",
    "live_public_research",
    "provider_unconfigured",
]


class CaseResearchPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: UUID
    case_id: UUID
    research_job_id: UUID | None = None
    data_revision: int = Field(ge=1)
    status: Literal["prepared"] = "prepared"
    focus_key: str
    intent: str
    plan_hash: str
    query_previews: tuple[str, ...]
    manual_only_keys: tuple[str, ...]
    consent_text: str
    created_at: datetime
    expires_at: datetime

    @field_validator(
        "focus_key",
        "intent",
        "plan_hash",
        "query_previews",
        "manual_only_keys",
        "consent_text",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = " ".join(value.strip().split())
            if not normalized:
                raise ValueError("text value must not be blank")
            return normalized
        if isinstance(value, tuple):
            return tuple(cls.normalize_text(item) for item in value)
        if isinstance(value, list):
            return tuple(cls.normalize_text(item) for item in value)
        return value


class PublicBenchmarkEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    input_key: str
    provenance: Literal[CaseValueKind.PUBLIC_BENCHMARK] = CaseValueKind.PUBLIC_BENCHMARK
    url: str
    publisher: str
    publication_date: str | None
    retrieval_date: str
    as_of: str
    source_class: str
    confidence: Literal["low", "medium", "high"]
    value: Decimal | None = None
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    unit: str
    period: str
    formula: str
    dependencies: tuple[str, ...]
    validation_plan: str
    source_refs: tuple[UUID, ...]
    rationale: str

    @field_validator(
        "input_key",
        "url",
        "publisher",
        "retrieval_date",
        "as_of",
        "source_class",
        "unit",
        "period",
        "formula",
        "dependencies",
        "validation_plan",
        "rationale",
        mode="before",
    )
    @classmethod
    def normalize_entry_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = " ".join(value.strip().split())
            if not normalized:
                raise ValueError("text value must not be blank")
            return normalized
        if isinstance(value, tuple):
            return tuple(cls.normalize_entry_text(item) for item in value)
        if isinstance(value, list):
            return tuple(cls.normalize_entry_text(item) for item in value)
        return value

    @field_validator("publication_date", mode="before")
    @classmethod
    def normalize_publication_date(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = " ".join(value.strip().casefold().split())
            if normalized in {"", "not stated", "not available", "unknown", "n/a", "na", "null", "none"}:
                return None
            return " ".join(value.strip().split())
        return value

    @field_validator("input_key")
    @classmethod
    def validate_public_benchmark_input_key(cls, value: str) -> str:
        normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
        if normalized not in _PUBLIC_BENCHMARK_INPUT_KEYS:
            raise ValueError("public_benchmark input_key is not public-search eligible")
        return normalized

    @field_validator("unit")
    @classmethod
    def validate_public_benchmark_unit(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized != "KZT":
            raise ValueError("public_benchmark unit must be KZT")
        return normalized

    @field_validator("period")
    @classmethod
    def validate_public_benchmark_period(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized != "month":
            raise ValueError("public_benchmark period must be month")
        return normalized

    @field_validator("value", "range_low", "range_high")
    @classmethod
    def validate_public_benchmark_decimal(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value < Decimal(0):
            raise ValueError("public_benchmark value must be >= 0")
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("public_benchmark value must have <= 2 decimal places")
        return value

    @model_validator(mode="after")
    def require_quantitative_value_or_ordered_range(self) -> "PublicBenchmarkEntry":
        if not self.dependencies:
            raise ValueError("public_benchmark dependencies must not be empty")
        if not self.source_refs:
            raise ValueError("public_benchmark source_refs must not be empty")
        has_value = self.value is not None
        has_low = self.range_low is not None
        has_high = self.range_high is not None
        if has_value and (has_low or has_high):
            raise ValueError("public_benchmark requires exactly one quantitative shape: exact value or ordered range")
        if not has_value and (not has_low or not has_high):
            raise ValueError("public_benchmark requires value or complete range")
        if self.range_low is not None and self.range_high is not None and self.range_low > self.range_high:
            raise ValueError("public_benchmark range_low cannot exceed range_high")
        return self


class RejectedResearchEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rejected_id: UUID
    reason_code: str
    input_key: str | None = None
    provenance: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("reason_code", "input_key", "provenance", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        normalized = " ".join(value.strip().split())
        return normalized[:160] if normalized else None

    @field_validator("metadata", mode="before")
    @classmethod
    def normalize_metadata(cls, value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or item is None:
                continue
            normalized_key = " ".join(key.strip().split())[:80]
            normalized_value = " ".join(str(item).strip().split())[:160]
            if normalized_key and normalized_value:
                result[normalized_key] = normalized_value
        return result


class CaseResearchJob(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    focus_key: str
    status: CaseResearchJobStatus
    requested_acquisition_mode: ResearchAcquisitionMode = "provider_unconfigured"
    selected_acquisition_mode: ResearchAcquisitionMode = "provider_unconfigured"
    # Legacy persisted jobs predate this replay-stable field; fail closed instead of
    # inferring live execution from status, provider names, URLs, or source strings.
    acquisition_mode: ResearchAcquisitionMode = "provider_unconfigured"
    plan_id: UUID | None = None
    plan_hash: str | None = None
    request_fingerprint: str | None = None
    source_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    result_summary: str | None = None
    reason: str | None = None
    fail_reason: str | None = None
    retry_of_job_id: UUID | None = None
    accepted_entries: tuple[PublicBenchmarkEntry, ...] = Field(default_factory=tuple)
    rejected_entries: tuple[RejectedResearchEntry, ...] = Field(default_factory=tuple)
    citations: tuple[str, ...] = Field(default_factory=tuple)
    manual_only_keys: tuple[str, ...] = Field(default_factory=tuple)
    changed_blocks: tuple[str, ...] = Field(default_factory=tuple)
    stale_scenario_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    live_market_research_snapshot: StartupMarketResearchSnapshot | None = None
    old_revision: int | None = None
    new_revision: int | None = None
    updated_at: datetime

    @field_validator(
        "focus_key",
        "plan_hash",
        "request_fingerprint",
        "result_summary",
        "reason",
        "fail_reason",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("text value must be a string")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("text value must not be blank")
        return normalized

    @field_validator("rejected_entries", mode="before")
    @classmethod
    def migrate_rejected_entries(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        migrated: list[object] = []
        for item in value:
            if isinstance(item, dict) and "reason_code" not in item:
                migrated.append(
                    {
                        "rejected_id": item.get("entry_id") or item.get("rejected_id"),
                        "reason_code": "legacy_rejected_benchmark_entry",
                        "input_key": item.get("input_key"),
                        "provenance": str(item.get("provenance") or ""),
                        "metadata": {},
                    }
                )
            else:
                migrated.append(item)
        return tuple(migrated)

    def __eq__(self, other: object) -> bool:
        payload = _research_job_payload(other)
        if payload is None:
            return NotImplemented
        return (
            self.job_id == payload.get("job_id")
            and self.case_id == payload.get("case_id")
            and self.data_revision == payload.get("data_revision")
            and self.focus_key == payload.get("focus_key", payload.get("focus"))
            and self.status == payload.get("status")
            and self.acquisition_mode
            == payload.get("acquisition_mode", "provider_unconfigured")
            and self.requested_acquisition_mode
            == payload.get("requested_acquisition_mode", "provider_unconfigured")
            and self.selected_acquisition_mode
            == payload.get("selected_acquisition_mode", "provider_unconfigured")
            and self.plan_id == payload.get("plan_id")
            and self.plan_hash == payload.get("plan_hash")
            and self.request_fingerprint == payload.get("request_fingerprint")
            and tuple(str(ref) for ref in self.source_refs)
            == tuple(str(ref) for ref in payload.get("source_refs", ()))
            and self.result_summary == payload.get("result_summary")
            and self.reason == payload.get("reason")
            and self.fail_reason == payload.get("fail_reason")
            and self.retry_of_job_id == payload.get("retry_of_job_id")
            and tuple(_benchmark_payload(entry) for entry in self.accepted_entries)
            == tuple(_payloads(payload.get("accepted_entries")))
            and tuple(_rejected_payload(entry) for entry in self.rejected_entries)
            == tuple(_payloads(payload.get("rejected_entries")))
            and self.citations == tuple(payload.get("citations", ()))
            and self.manual_only_keys == tuple(payload.get("manual_only_keys", ()))
            and self.changed_blocks == tuple(payload.get("changed_blocks", ()))
            and self.stale_scenario_ids == tuple(payload.get("stale_scenario_ids", ()))
            and _market_snapshot_payload(self.live_market_research_snapshot)
            == _market_snapshot_payload(payload.get("live_market_research_snapshot"))
            and self.old_revision == payload.get("old_revision")
            and self.new_revision == payload.get("new_revision")
            and self.updated_at == payload.get("updated_at")
        )


_CASE_RESEARCH_JOB_FIELDS = (
    "job_id",
    "case_id",
    "data_revision",
    "focus_key",
    "status",
    "requested_acquisition_mode",
    "selected_acquisition_mode",
    "acquisition_mode",
    "plan_id",
    "plan_hash",
    "request_fingerprint",
    "source_refs",
    "result_summary",
    "reason",
    "fail_reason",
    "retry_of_job_id",
    "accepted_entries",
    "rejected_entries",
    "citations",
    "manual_only_keys",
    "changed_blocks",
    "stale_scenario_ids",
    "live_market_research_snapshot",
    "old_revision",
    "new_revision",
    "updated_at",
)


def _research_job_payload(value: object) -> dict[str, Any] | None:
    if isinstance(value, CaseResearchJob):
        return {field: getattr(value, field) for field in _CASE_RESEARCH_JOB_FIELDS}
    return _model_payload(value)


def _model_payload(value: object) -> dict[str, Any] | None:
    dumper = getattr(value, "model_dump", None)
    if not callable(dumper):
        return None
    payload = dumper(mode="python")
    return payload if isinstance(payload, dict) else None


def _payloads(values: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    payloads: list[dict[str, Any]] = []
    for value in values:
        payload = _model_payload(value)
        if payload is not None:
            payloads.append(payload)
        elif isinstance(value, dict):
            payloads.append(value)
    return tuple(payloads)


def _market_snapshot_payload(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, StartupMarketResearchSnapshot):
        return value.model_dump(mode="python")
    if isinstance(value, dict):
        try:
            return StartupMarketResearchSnapshot.model_validate(value).model_dump(mode="python")
        except (TypeError, ValueError):
            return value
    payload = _model_payload(value)
    if payload is None:
        return None
    try:
        return StartupMarketResearchSnapshot.model_validate(payload).model_dump(mode="python")
    except (TypeError, ValueError):
        return payload


def _benchmark_payload(entry: PublicBenchmarkEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "provenance": entry.provenance,
        "input_key": entry.input_key,
        "url": entry.url,
        "publisher": entry.publisher,
        "publication_date": entry.publication_date,
        "retrieval_date": entry.retrieval_date,
        "as_of": entry.as_of,
        "source_class": entry.source_class,
        "confidence": entry.confidence,
        "value": entry.value,
        "range": {
            "low": entry.range_low,
            "high": entry.range_high,
        },
        "unit": entry.unit,
        "period": entry.period,
        "formula": entry.formula,
        "dependencies": tuple(entry.dependencies),
        "validation_plan": entry.validation_plan,
        "source_refs": tuple(str(ref) for ref in entry.source_refs),
    }


def _rejected_payload(entry: RejectedResearchEntry) -> dict[str, Any]:
    return entry.model_dump(mode="python")


class CaseRepository(Protocol):
    def add(self, case: DueDiligenceCase) -> None: ...
    def get(self, case_id: UUID) -> DueDiligenceCase: ...
    def advance_data_revision(
        self,
        case_id: UUID,
        *,
        expected_revision: int,
        updated_case: DueDiligenceCase,
    ) -> DueDiligenceCase: ...


class ArtifactRepository(Protocol):
    def add(self, artifact: Artifact) -> None: ...
    def get(self, artifact_id: UUID) -> Artifact: ...


class ParsedStartupArtifactRepository(Protocol):
    def add(self, parsed_artifact: ParsedStartupArtifact) -> None: ...
    def get_for_case(self, case_id: UUID, artifact_id: UUID) -> ParsedStartupArtifact: ...
    def list_for_case(self, case_id: UUID) -> list[ParsedStartupArtifact]: ...


class StartupProfileRepository(Protocol):
    def add(self, profile: StartupProfile) -> None: ...
    def get(self, profile_id: UUID) -> StartupProfile: ...
    def list_for_case(self, case_id: UUID) -> list[StartupProfile]: ...
    def get_for_stage(
        self,
        case_id: UUID,
        data_revision: int,
        stage: StartupProfileAnalysisStage,
    ) -> StartupProfile: ...
    def get_current(self, case_id: UUID) -> StartupProfile: ...


class CaseAssumptionRepository(Protocol):
    def get_current(self, case_id: UUID) -> tuple[FounderStatement, ...]: ...
    def get_by_idempotency(
        self,
        case_id: UUID,
        idempotency_key: str,
    ) -> FounderStatement | None: ...
    def save(
        self,
        value: FounderStatement,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> FounderStatement: ...
    def get_for_case(self, case_id: UUID, statement_id: UUID) -> FounderStatement: ...
    def list_for_case(self, case_id: UUID) -> tuple[FounderStatement, ...]: ...


class CaseScenarioRepository(Protocol):
    def get_current(self, case_id: UUID) -> StartupScenarioSet: ...
    def get_by_idempotency(
        self,
        case_id: UUID,
        idempotency_key: str,
    ) -> StartupScenarioSet | None: ...
    def save(
        self,
        value: StartupScenarioSet,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> StartupScenarioSet: ...
    def get_selection_by_idempotency(
        self,
        case_id: UUID,
        idempotency_key: str,
    ) -> ScenarioSelectionRecord | None: ...
    def save_selection(
        self,
        value: ScenarioSelectionRecord,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> ScenarioSelectionRecord: ...
    def get_for_case(self, case_id: UUID, scenario_set_id: UUID) -> StartupScenarioSet: ...
    def list_for_case(self, case_id: UUID) -> tuple[StartupScenarioSet, ...]: ...


class CasePublicBenchmarkRepository(Protocol):
    def get_current(self, case_id: UUID) -> tuple[ScenarioInput, ...]: ...
    def save(
        self,
        value: ScenarioInput,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> ScenarioInput: ...
    def get_for_case(self, case_id: UUID, input_id: UUID) -> ScenarioInput: ...
    def list_for_case(self, case_id: UUID) -> tuple[ScenarioInput, ...]: ...


class CaseCopilotThreadRepository(Protocol):
    def get_current(self, case_id: UUID) -> CopilotThread: ...
    def save(
        self,
        value: CopilotThread,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> CopilotThread: ...
    def get_for_case(self, case_id: UUID, thread_id: UUID) -> CopilotThread: ...


class CaseResearchJobRepository(Protocol):
    def get_current(self, case_id: UUID) -> CaseResearchJob: ...
    def save(
        self,
        value: CaseResearchJob,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> CaseResearchJob: ...
    def get_for_case(self, case_id: UUID, job_id: UUID) -> CaseResearchJob: ...
    def list_for_case(self, case_id: UUID) -> tuple[CaseResearchJob, ...]: ...


class CaseResearchPlanRepository(Protocol):
    def get_current(self, case_id: UUID) -> CaseResearchPlan: ...
    def save(
        self,
        value: CaseResearchPlan,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> CaseResearchPlan: ...
    def get_for_case(self, case_id: UUID, plan_id: UUID) -> CaseResearchPlan: ...
    def list_for_case(self, case_id: UUID) -> tuple[CaseResearchPlan, ...]: ...


class CaseAssetRepository(Protocol):
    def get_current(self, case_id: UUID) -> CaseAssetDraft: ...
    def save(
        self,
        value: CaseAssetDraft,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> CaseAssetDraft: ...
    def get_for_case(self, case_id: UUID, draft_id: UUID) -> CaseAssetDraft: ...
    def list_for_case(self, case_id: UUID) -> tuple[CaseAssetDraft, ...]: ...


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
    def replace(self, contradiction: Contradiction) -> None: ...
    def list_for_case(self, case_id: UUID) -> list[Contradiction]: ...


class ApprovalRepository(Protocol):
    def add(self, approval: Approval) -> None: ...
    def list_for_case(self, case_id: UUID) -> list[Approval]: ...


class ReportRepository(Protocol):
    def add_snapshot(self, snapshot: ReportSnapshot) -> None: ...
    def get_snapshot(self, snapshot_id: UUID) -> ReportSnapshot: ...


class ArtifactStore(Protocol):
    def put_bytes(
        self,
        payload: bytes,
        *,
        media_type: str,
        artifact_id: UUID | None = None,
        source_snapshot_hash: str | None = None,
        sensitivity: SensitivityClass = SensitivityClass.RESTRICTED,
    ) -> StoredArtifact: ...

    def read_bytes(self, content_hash: str) -> bytes: ...
