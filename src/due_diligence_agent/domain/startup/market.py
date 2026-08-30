from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal, cast
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationInfo,
    field_validator,
    model_validator,
)

from due_diligence_agent.domain.common import require_decimal, require_utc

_MAX_LABEL_LENGTH = 140
_MAX_QUERY_LENGTH = 120
_MAX_LABELS = 16
_MAX_QUERY_COUNT = 8
_MAX_SOURCE_REF_ID_LENGTH = 128
_MAX_SOURCE_LABEL_LENGTH = 80
_MAX_REASON_LENGTH = 80
_MAX_VERSION_LENGTH = 120
_MAX_BENCHMARK_TEXT_LENGTH = 240
_SCHEMA_VERSION = "startup_market_research@1"
_SHA256_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)(?:^|[^a-z0-9])(api[_-]?key|apikey|access[_-]?token|authorization|bearer|password|passwd|private[_-]?key|secret)(?=$|[^a-z0-9])",
)
_SENSITIVE_QUERY_KEY_RE = re.compile(
    r"(?i)(?:^|[&\s?])(api[_-]?key|access[_-]?token|authorization|auth[_-]?token|secret|token)[=:]",
)
_PRIVATE_PATH_RE = re.compile(
    r"(?i)(?:file://|[a-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+|(?:^|[\\/])(?:tmp|var|home|etc|users)(?:[\\/]|$)|~[\\/])",
)
_SAFE_PUBLIC_BENCHMARK_KEYS = frozenset({"acquisition_spend", "arpa", "monthly_price"})


class StartupResearchSchema:
    VERSION = _SCHEMA_VERSION


class StartupResearchSourceMode(StrEnum):
    FROZEN = "frozen"
    LIVE = "live"


class StartupResearchSourceStatus(StrEnum):
    SOURCE_FACT = "source_fact"
    INFERENCE = "inference"
    INSUFFICIENT_DATA = "insufficient_data"
    CONTRADICTION = "contradiction"


class StartupCompetitorCategory(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    SUBSTITUTE = "substitute"
    DO_NOTHING = "do_nothing"
    POTENTIAL_ENTRANT = "potential_entrant"


class StartupResearchSentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class StartupResearchSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: UUID
    source_mode: StartupResearchSourceMode
    source_hash: str
    source_url: HttpUrl
    source_label: str
    as_of: date
    retrieved_at: datetime
    query: str
    provenance: str
    confidence: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    supports_primary_financial_metrics: bool = False
    stale: bool = False
    status: StartupResearchSourceStatus = StartupResearchSourceStatus.SOURCE_FACT

    @field_validator("source_hash")
    @classmethod
    def validate_source_hash(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if _SHA256_RE.fullmatch(normalized) is None:
            raise ValueError("source hash must be sha256")
        if ":" not in normalized:
            return f"sha256:{normalized}"
        return normalized

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: HttpUrl) -> HttpUrl:
        string = str(value)
        if len(string) > 512:
            raise ValueError("source url exceeds bound")
        parsed = urlsplit(string)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("source url must not include credentials")
        if parsed.fragment:
            raise ValueError("source url must not include fragment")
        if parsed.query and _SENSITIVE_QUERY_KEY_RE.search(parsed.query):
            raise ValueError("source url query contains sensitive key")
        return value

    @field_validator("source_label")
    @classmethod
    def validate_source_label(cls, value: str) -> str:
        return _validate_text_payload(value, _MAX_SOURCE_LABEL_LENGTH, "source label")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        return _validate_text_payload(value, _MAX_QUERY_LENGTH, "query")

    @field_validator("provenance")
    @classmethod
    def validate_provenance(cls, value: str) -> str:
        normalized = _validate_text_payload(value, _MAX_SOURCE_REF_ID_LENGTH, "provenance")
        if len(normalized) > _MAX_SOURCE_REF_ID_LENGTH:
            raise ValueError("provenance exceeds bound")
        return normalized

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("retrieved_at")
    @classmethod
    def validate_retrieved_at(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("retrieved_at must be UTC")
        if checked > datetime.now(UTC):
            raise ValueError("retrieved_at cannot be in the future")
        return checked

    @model_validator(mode="after")
    def enforce_secondary_only(self) -> "StartupResearchSource":
        if self.supports_primary_financial_metrics:
            raise ValueError("research source cannot support primary financial metrics")
        return self

    def canonical_payload_for_hash(self) -> dict[str, Any]:
        payload = self.model_dump(mode="python")
        if self.confidence is None:
            payload.pop("confidence", None)
        return payload


class StartupCompetitor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    category: StartupCompetitorCategory
    status: StartupResearchSourceStatus = StartupResearchSourceStatus.SOURCE_FACT
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    source_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    reason_code: str | None = None
    assumption_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    contradiction_ids: tuple[UUID, ...] = Field(default_factory=tuple)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("name is required")
        if len(normalized) > _MAX_LABEL_LENGTH:
            raise ValueError("name exceeds bound")
        if _SENSITIVE_TEXT_RE.search(normalized):
            raise ValueError("name contains sensitive material")
        return normalized

    @field_validator("reason_code")
    @classmethod
    def normalize_reason_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _validate_text_payload(value, _MAX_REASON_LENGTH, "reason code").casefold()
        return normalized

    @field_validator("source_ids", "assumption_refs", "contradiction_ids")
    @classmethod
    def normalize_source_refs(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return tuple(sorted(value))

    @model_validator(mode="after")
    def enforce_status(self) -> "StartupCompetitor":
        if self.status is StartupResearchSourceStatus.SOURCE_FACT and not self.source_ids:
            raise ValueError("source_fact competitor requires source ids")
        if self.status is StartupResearchSourceStatus.INFERENCE and not self.reason_code:
            raise ValueError("inference competitor requires reason code")
        if self.status is StartupResearchSourceStatus.CONTRADICTION and not (
            self.contradiction_ids or self.reason_code
        ):
            raise ValueError("contradiction competitor requires contradiction refs or reason code")
        if self.status is StartupResearchSourceStatus.INSUFFICIENT_DATA and self.source_ids:
            raise ValueError("insufficient_data competitor cannot include source ids")
        return self


class MarketSizingAssumption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    assumption_id: UUID
    text: str
    status: StartupResearchSourceStatus = StartupResearchSourceStatus.SOURCE_FACT
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    as_of: date
    source_mode: StartupResearchSourceMode
    source_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    lineage: tuple[UUID, ...] = Field(default_factory=tuple)
    reason_code: str | None = None

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _validate_text_payload(value, 500, "assumption text")

    @field_validator("reason_code")
    @classmethod
    def normalize_reason_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _validate_text_payload(value, _MAX_REASON_LENGTH, "reason code").casefold()
        return normalized

    @field_validator("source_ids", "lineage")
    @classmethod
    def normalize_source_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return tuple(sorted(value))

    @field_validator("source_mode")
    @classmethod
    def validate_source_mode(cls, value: StartupResearchSourceMode) -> StartupResearchSourceMode:
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @model_validator(mode="after")
    def enforce_status(self) -> "MarketSizingAssumption":
        if self.status is StartupResearchSourceStatus.SOURCE_FACT and not self.source_ids:
            raise ValueError("source_fact assumption requires source ids")
        if self.status is StartupResearchSourceStatus.INFERENCE and not self.reason_code:
            raise ValueError("inference assumption requires reason code")
        if self.status is StartupResearchSourceStatus.INSUFFICIENT_DATA and (
            self.source_ids or self.lineage or self.reason_code
        ):
            raise ValueError("insufficient_data assumption must be explicitly empty")
        return self


class MarketSizingEstimate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    estimate_id: UUID
    level: StartupResearchSourceStatus
    value: Decimal | None
    unit: str
    currency: str
    as_of: date
    source_mode: StartupResearchSourceMode
    formula_version: str
    assumption_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    source_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    confidence: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("1"))

    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("unit", "currency")
    @classmethod
    def normalize_unit_currency(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized:
            raise ValueError("unit and currency are required")
        if len(normalized) > 20:
            raise ValueError("unit/currency exceeds bound")
        return normalized

    @field_validator("formula_version")
    @classmethod
    def normalize_formula_version(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized:
            raise ValueError("formula version is required")
        if len(normalized) > _MAX_VERSION_LENGTH:
            raise ValueError("formula version exceeds bound")
        return normalized

    @field_validator("assumption_refs", "source_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return tuple(sorted(value))

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @model_validator(mode="after")
    def enforce_level(self) -> "MarketSizingEstimate":
        if self.level is StartupResearchSourceStatus.SOURCE_FACT:
            if self.value is None:
                raise ValueError("source_fact estimate requires value")
            if self.value <= Decimal("0"):
                raise ValueError("value must be > 0")
            if not self.source_refs:
                raise ValueError("source_fact estimate requires source refs")
        elif self.level is StartupResearchSourceStatus.INFERENCE:
            if self.value is not None and self.value <= Decimal("0"):
                raise ValueError("value must be > 0")
            if self.value is not None and not self.assumption_refs:
                raise ValueError("inference estimate requires assumption refs")
        else:
            if self.value is not None:
                raise ValueError("insufficient_data/contradiction cannot include values")
        return self


class StartupSentimentSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_id: UUID
    sentiment: StartupResearchSentiment
    subject: str
    as_of: datetime
    source_id: UUID
    source_mode: StartupResearchSourceMode
    supports_primary_financial_metrics: bool = False
    supports_event_narrative_claims: bool = False
    polarity_confidence: Decimal = Field(default=Decimal("0.5"), ge=Decimal("0"), le=Decimal("1"))

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        normalized = _validate_text_payload(value, _MAX_LABEL_LENGTH, "subject")
        if _SENSITIVE_TEXT_RE.search(normalized):
            raise ValueError("subject contains sensitive material")
        return normalized

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("as_of must be UTC")
        if checked > datetime.now(UTC):
            raise ValueError("sentiment as_of cannot be in the future")
        return checked

    @field_validator("polarity_confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any, info: ValidationInfo) -> Decimal:
        return require_decimal(value)

    @model_validator(mode="after")
    def enforce_secondary(self) -> "StartupSentimentSignal":
        if self.supports_primary_financial_metrics:
            raise ValueError("sentiment cannot support primary financial metrics")
        return self


class StartupResearchPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    research_job_id: UUID | None = None
    source_mode: StartupResearchSourceMode = StartupResearchSourceMode.FROZEN
    queries: tuple[str, ...] = Field(default_factory=tuple)
    max_queries: int = _MAX_QUERY_COUNT

    @field_validator("queries")
    @classmethod
    def normalize_queries(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_normalize_query(query) for query in value)
        if len(normalized) > _MAX_QUERY_COUNT:
            raise ValueError("too many queries")
        return normalized

    @field_validator("max_queries")
    @classmethod
    def validate_max_queries(cls, value: int) -> int:
        if not (1 <= value <= _MAX_QUERY_COUNT):
            raise ValueError("invalid max_queries")
        return value


class StartupPublicBenchmarkCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_key: str
    source_url: str
    provenance: Literal["public_benchmark"] = "public_benchmark"
    publisher: str
    publication_date: date | None
    retrieval_date: date
    as_of: date
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
    source_ref: UUID
    rationale: str

    @field_validator("provenance")
    @classmethod
    def validate_provenance(cls, value: str) -> str:
        if value != "public_benchmark":
            raise ValueError("public benchmark candidate provenance must be public_benchmark")
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
        return value

    @field_validator("input_key")
    @classmethod
    def validate_input_key(cls, value: str) -> str:
        normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
        if normalized not in _SAFE_PUBLIC_BENCHMARK_KEYS:
            raise ValueError("public benchmark input_key is not public-search eligible")
        return normalized

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (parsed.query and _SENSITIVE_QUERY_KEY_RE.search(parsed.query))
        ):
            raise ValueError("public benchmark source_url must be a safe cited https url")
        if parsed.path == "/" and not parsed.query:
            return normalized.rstrip("/")
        return normalized

    @field_validator(
        "publisher",
        "source_class",
        "period",
        "formula",
        "dependencies",
        "validation_plan",
        "rationale",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: object) -> object:
        if isinstance(value, str):
            return _validate_text_payload(value, _MAX_BENCHMARK_TEXT_LENGTH, "public benchmark text")
        if isinstance(value, list | tuple):
            return tuple(cls.normalize_text_fields(item) for item in value)
        return value

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        normalized = _validate_text_payload(value, 40, "public benchmark unit").upper()
        if normalized != "KZT":
            raise ValueError("public benchmark unit must be KZT")
        return normalized

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        normalized = _validate_text_payload(value, 40, "public benchmark period").casefold()
        if normalized != "month":
            raise ValueError("public benchmark period must be month")
        return normalized

    @field_validator("value", "range_low", "range_high", mode="before")
    @classmethod
    def normalize_decimal(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        normalized = require_decimal(value)
        if normalized < Decimal("0"):
            raise ValueError("public benchmark value must be >= 0")
        exponent = normalized.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("public benchmark value must have <= 2 decimal places")
        return normalized

    @model_validator(mode="after")
    def require_quantitative_shape(self) -> "StartupPublicBenchmarkCandidate":
        if not self.dependencies:
            raise ValueError("public benchmark dependencies must not be empty")
        has_value = self.value is not None
        has_low = self.range_low is not None
        has_high = self.range_high is not None
        if has_value and (has_low or has_high):
            raise ValueError("public benchmark requires exact value or ordered range")
        if not has_value and (not has_low or not has_high):
            raise ValueError("public benchmark requires value or complete range")
        if self.range_low is not None and self.range_high is not None and self.range_low > self.range_high:
            raise ValueError("public benchmark range_low cannot exceed range_high")
        return self


class StartupMarketSizing(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tam: MarketSizingEstimate
    sam: MarketSizingEstimate
    som: MarketSizingEstimate

    @model_validator(mode="after")
    def validate_hierarchy(self) -> "StartupMarketSizing":
        if self.tam.value is None and (self.sam.value is not None or self.som.value is not None):
            raise ValueError("tam is required when sam or som has value")
        if self.sam.value is None and self.som.value is not None:
            raise ValueError("sam is required when som has value")
        if self.tam.value is not None and self.sam.value is not None and self.sam.value > self.tam.value:
            raise ValueError("sam cannot exceed tam")
        if self.sam.value is not None and self.som.value is not None and self.som.value > self.sam.value:
            raise ValueError("som cannot exceed sam")
        present_levels = tuple(level for level in (self.tam, self.sam, self.som) if level.value is not None)
        if present_levels:
            currency = present_levels[0].currency
            unit = present_levels[0].unit
            if any(level.currency != currency for level in present_levels):
                raise ValueError("currency mismatch")
            if any(level.unit != unit for level in present_levels):
                raise ValueError("unit mismatch")
        return self


class StartupMarketResearchSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    snapshot_id: UUID
    snapshot_hash: str
    schema_version: str = StartupResearchSchema.VERSION
    research_id: UUID
    as_of: datetime
    source_mode: StartupResearchSourceMode
    competitors: tuple[StartupCompetitor, ...]
    sources: tuple[StartupResearchSource, ...]
    sentiment_signals: tuple[StartupSentimentSignal, ...]
    assumptions: tuple[MarketSizingAssumption, ...]
    sizing: StartupMarketSizing | None = None
    public_benchmark_candidates: tuple[StartupPublicBenchmarkCandidate, ...] = Field(
        default_factory=tuple
    )
    labels: tuple[str, ...] = Field(default_factory=tuple)
    provenance: str = "frozen_first"
    data_revision: int = Field(ge=1)

    @classmethod
    def build(
        cls,
        *,
        case_id: UUID,
        as_of: datetime,
        source_mode: StartupResearchSourceMode,
        research_id: UUID,
        competitors: tuple[StartupCompetitor, ...],
        sources: tuple[StartupResearchSource, ...],
        sentiment_signals: tuple[StartupSentimentSignal, ...],
        assumptions: tuple[MarketSizingAssumption, ...],
        sizing: StartupMarketSizing | None,
        labels: tuple[str, ...],
        data_revision: int,
        public_benchmark_candidates: tuple[StartupPublicBenchmarkCandidate, ...] = (),
    ) -> "StartupMarketResearchSnapshot":
        normalized_labels = tuple(sorted(set(_normalize_label(label) for label in labels)))
        sorted_competitors = tuple(sorted(competitors, key=lambda item: item.name))
        sorted_sources = tuple(sorted(sources, key=lambda item: str(item.source_id)))
        sorted_sentiment_signals = tuple(sorted(sentiment_signals, key=lambda item: str(item.signal_id)))
        sorted_assumptions = tuple(sorted(assumptions, key=lambda item: str(item.assumption_id)))
        sorted_public_benchmark_candidates = tuple(
            sorted(public_benchmark_candidates, key=_canonical_sort_key)
        )
        provenance = (
            "frozen_first"
            if source_mode is StartupResearchSourceMode.FROZEN
            else "live_public_research"
        )
        canonical_payload = {
            "case_id": case_id,
            "schema_version": StartupResearchSchema.VERSION,
            "research_id": research_id,
            "as_of": as_of,
            "source_mode": source_mode,
            "competitors": tuple(
                item.model_dump(mode="python") for item in sorted_competitors
            ),
            "sources": tuple(
                item.canonical_payload_for_hash() for item in sorted_sources
            ),
            "sentiment_signals": tuple(
                item.model_dump(mode="python") for item in sorted_sentiment_signals
            ),
            "assumptions": tuple(
                item.model_dump(mode="python") for item in sorted_assumptions
            ),
            "sizing": sizing.model_dump(mode="python") if sizing is not None else None,
            "public_benchmark_candidates": tuple(
                item.model_dump(mode="python") for item in sorted_public_benchmark_candidates
            ),
            "labels": normalized_labels,
            "provenance": provenance,
            "data_revision": data_revision,
        }
        snapshot_hash = cls.derive_snapshot_hash(canonical_payload)
        snapshot_id = cls.derive_snapshot_id(case_id=case_id, snapshot_hash=snapshot_hash)
        return cls.model_validate(
            {
                "case_id": case_id,
                "snapshot_id": snapshot_id,
                "snapshot_hash": snapshot_hash,
                "schema_version": StartupResearchSchema.VERSION,
                "research_id": research_id,
                "as_of": as_of,
                "source_mode": source_mode,
                "competitors": sorted_competitors,
                "sources": sorted_sources,
                "sentiment_signals": sorted_sentiment_signals,
                "assumptions": sorted_assumptions,
                "sizing": sizing,
                "public_benchmark_candidates": sorted_public_benchmark_candidates,
                "labels": normalized_labels,
                "provenance": provenance,
                "data_revision": data_revision,
            }
        )

    @field_validator("snapshot_hash")
    @classmethod
    def validate_snapshot_hash(cls, value: str) -> str:
        if not value.startswith("sha256:"):
            raise ValueError("snapshot_hash must be sha256")
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("snapshot_hash must be valid sha256")
        return value

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("as_of must be UTC")
        if checked > datetime.now(UTC):
            raise ValueError("as_of cannot be in the future")
        return checked

    @field_validator("provenance")
    @classmethod
    def validate_provenance(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {
            "frozen_first",
            "frozen",
            "live",
            "live_public_research",
        }:
            raise ValueError("invalid provenance")
        return normalized

    @field_validator("labels")
    @classmethod
    def normalize_labels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_normalize_label(label) for label in value)
        if len(normalized) > _MAX_LABELS:
            raise ValueError("too many labels")
        return tuple(sorted(set(normalized)))

    @field_validator(
        "competitors",
        "sources",
        "sentiment_signals",
        "assumptions",
        "public_benchmark_candidates",
    )
    @classmethod
    def normalize_collections(cls, value: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(sorted(value, key=_canonical_sort_key))

    @model_validator(mode="after")
    def enforce_graph_constraints(self) -> "StartupMarketResearchSnapshot":
        if self.schema_version != StartupResearchSchema.VERSION:
            raise ValueError("invalid schema version")

        source_ids = {item.source_id for item in self.sources}
        assumption_ids = {item.assumption_id for item in self.assumptions}

        for sentiment in self.sentiment_signals:
            if sentiment.source_id not in source_ids:
                raise ValueError("sentiment source id missing")
            if self.source_mode is StartupResearchSourceMode.FROZEN and sentiment.source_mode is not StartupResearchSourceMode.FROZEN:
                raise ValueError("frozen snapshot cannot include live sentiment")
            if sentiment.supports_primary_financial_metrics:
                raise ValueError("sentiment cannot support primary financial metrics")

        for competitor in self.competitors:
            for source_id in competitor.source_ids:
                if source_id not in source_ids:
                    raise ValueError("competitor source id missing")
            for assumption_id in competitor.assumption_refs:
                if assumption_id not in assumption_ids:
                    raise ValueError("competitor assumption ref missing")
            if competitor.status is StartupResearchSourceStatus.CONTRADICTION and not (competitor.contradiction_ids or competitor.reason_code):
                raise ValueError("contradiction competitor requires contradiction refs")

        for assumption in self.assumptions:
            if assumption.source_mode is StartupResearchSourceMode.LIVE and self.source_mode is StartupResearchSourceMode.FROZEN:
                raise ValueError("frozen snapshot cannot include live assumption")
            for source_id in assumption.source_ids:
                if source_id not in source_ids:
                    raise ValueError("assumption source id missing")
            for lineage_id in assumption.lineage:
                if lineage_id not in assumption_ids:
                    raise ValueError("assumption lineage id missing")

        if self.sizing is not None:
            for estimate in (self.sizing.tam, self.sizing.sam, self.sizing.som):
                if self.source_mode is StartupResearchSourceMode.FROZEN and estimate.source_mode is not StartupResearchSourceMode.FROZEN:
                    raise ValueError("frozen snapshot cannot include live estimate")
                for source_id in estimate.source_refs:
                    if source_id not in source_ids:
                        raise ValueError("sizing source ref missing")
                for assumption_id in estimate.assumption_refs:
                    if assumption_id not in assumption_ids:
                        raise ValueError("sizing assumption ref missing")

        for candidate in self.public_benchmark_candidates:
            if candidate.source_ref not in source_ids:
                raise ValueError("public benchmark source ref missing")
            if not any(_normalize_public_url(str(source.source_url)) == candidate.source_url for source in self.sources):
                raise ValueError("public benchmark source url missing")

        expected_hash = self.derive_snapshot_hash(self.canonical_payload_for_hash())
        if self.snapshot_hash != expected_hash:
            raise ValueError("snapshot_hash must be recomputed from payload")
        expected_id = self.derive_snapshot_id(
            case_id=self.case_id,
            snapshot_hash=self.snapshot_hash,
        )
        if self.snapshot_id != expected_id:
            raise ValueError("snapshot_id must be derived from case id and snapshot_hash")

        for source in self.sources:
            if self.source_mode is StartupResearchSourceMode.FROZEN and source.source_mode is not StartupResearchSourceMode.FROZEN:
                raise ValueError("frozen snapshot requires frozen sources")
        return self

    @classmethod
    def derive_snapshot_id(cls, *, case_id: UUID, snapshot_hash: str) -> UUID:
        return uuid5(NAMESPACE_URL, f"startup-market-research:{case_id}:{snapshot_hash}")

    @classmethod
    def derive_snapshot_hash(cls, payload: Mapping[str, Any]) -> str:
        return f"sha256:{sha256(_canonical_json(_canonicalize(payload)).encode('utf-8')).hexdigest()}"

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="python", exclude={"snapshot_id", "snapshot_hash"})
        payload["sources"] = tuple(
            source.canonical_payload_for_hash() for source in self.sources
        )
        return cast(dict[str, Any], _canonicalize(payload))

    def canonical_payload_for_hash(self) -> Mapping[str, Any]:
        return self.canonical_payload()

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_payload())


def _normalize_label(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("label must be string")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("label must not be blank")
    if len(normalized) > _MAX_LABEL_LENGTH:
        raise ValueError("label too long")
    return normalized


def _normalize_query(value: Any) -> str:
    return _validate_text_payload(value, _MAX_QUERY_LENGTH, "query")


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, AnyUrl):
        return str(value)
    if isinstance(value, tuple):
        return sorted(
            [_canonicalize(item) for item in value],
            key=_canonical_sort_key,
        )
    if isinstance(value, list):
        return sorted(
            [_canonicalize(item) for item in value],
            key=_canonical_sort_key,
        )
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _validate_text_payload(value: Any, max_len: int, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if len(normalized) > max_len:
        raise ValueError(f"{field_name} exceeds bound")
    if _SENSITIVE_TEXT_RE.search(normalized):
        raise ValueError(f"{field_name} contains sensitive material")
    if _SENSITIVE_QUERY_KEY_RE.search(normalized):
        raise ValueError(f"{field_name} contains sensitive query key")
    if _PRIVATE_PATH_RE.search(normalized):
        raise ValueError(f"{field_name} contains private path token")
    return normalized


def _normalize_public_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if parsed.path == "/" and not parsed.query:
        return normalized.rstrip("/")
    return normalized


def _canonical_sort_key(value: Any) -> str:
    return _canonical_json(_canonicalize(value))
