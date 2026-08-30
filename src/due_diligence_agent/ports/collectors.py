from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Literal, Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from due_diligence_agent.application.policies.content_rights import (
    LicenseClass,
    may_store_full_text,
)
from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.domain.common import require_decimal, require_utc
from due_diligence_agent.workflows.shared.node_result import NodeResult


class SourceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    provider_version: str
    source_url: str
    query: Mapping[str, str]
    as_of: date
    retrieved_at: datetime
    published_at: datetime | None
    content_hash: str
    license_class: str
    media_type: str
    storage_ref: str
    stale: bool = False
    primary_failure: str | None = None

    @field_validator("retrieved_at", "published_at")
    @classmethod
    def validate_utc(cls, value: datetime | None) -> datetime | None:
        return require_utc(value)

    @field_validator("query", mode="after")
    @classmethod
    def freeze_query(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType({str(key): str(item) for key, item in value.items()})

    @field_serializer("query")
    def serialize_query(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)


class CompanyIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cik: str
    ticker: str | None = None
    name: str | None = None
    snapshot: SourceSnapshot | None = None


class SubmissionsSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    data: Mapping[str, Any]
    snapshot: SourceSnapshot

    @field_validator("data", mode="after")
    @classmethod
    def freeze_data(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return cast(Mapping[str, Any], deep_freeze(value))

    @field_serializer("data")
    def serialize_data(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], deep_thaw(value))


class CompanyFactsSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    data: Mapping[str, Any]
    snapshot: SourceSnapshot

    @field_validator("data", mode="after")
    @classmethod
    def freeze_data(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return cast(Mapping[str, Any], deep_freeze(value))

    @field_serializer("data")
    def serialize_data(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], deep_thaw(value))


class FilingArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accession_number: str
    content: bytes
    snapshot: SourceSnapshot


class MarketPricePoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    date: date
    close: Decimal
    volume: int

    @field_validator("close", mode="before")
    @classmethod
    def validate_close(cls, value: Any) -> Decimal:
        return require_decimal(value)


class MarketDataSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    as_of: date
    currency: str
    market_cap: Decimal | None
    prices: tuple[MarketPricePoint, ...]
    snapshot: SourceSnapshot
    unofficial: bool = True
    research_only: bool = True
    license_class: Literal["research_only"] = "research_only"
    source_priority: SourcePriority = SourcePriority.SECONDARY_AGGREGATOR
    supports_primary_financial_metrics: bool = False

    @field_validator("market_cap", mode="before")
    @classmethod
    def validate_market_cap(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @property
    def source_priority_label(self) -> str:
        return "secondary_aggregator"

    @model_validator(mode="after")
    def enforce_secondary_governance(self) -> "MarketDataSnapshot":
        if (
            not self.unofficial
            or not self.research_only
            or self.license_class != "research_only"
            or self.snapshot.license_class != "research_only"
            or self.source_priority != SourcePriority.SECONDARY_AGGREGATOR
            or self.supports_primary_financial_metrics
        ):
            raise ValueError("market data must remain secondary unofficial research-only context")
        return self


class NewsProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    provider_version: str
    source_url: str
    response_hash: str


class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    publisher: str
    domain: str
    title: str
    snippet: str
    published_at: datetime
    query: str
    retrieved_at: datetime
    response_hash: str
    license_class: LicenseClass
    provenance: NewsProvenance
    full_text: str | None = None
    polarity: Literal["positive", "neutral", "negative"] | None = None
    supports_event_narrative_claims: bool = True
    supports_primary_financial_metrics: bool = False

    @field_validator("published_at", "retrieved_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

    @model_validator(mode="after")
    def enforce_news_governance(self) -> "NewsItem":
        if not self.title.strip():
            raise ValueError("title is required")
        if not self.url.strip():
            raise ValueError("url is required")
        if self.supports_primary_financial_metrics:
            raise ValueError("news metadata cannot support primary financial metrics")
        if self.provenance.source_url != self.url:
            raise ValueError("news provenance source_url must match item url")
        if self.provenance.response_hash != self.response_hash:
            raise ValueError("news provenance response_hash must match item response_hash")
        if self.full_text is not None and not may_store_full_text(self.license_class):
            object.__setattr__(self, "full_text", None)
        return self


@runtime_checkable
class SecSourcePort(Protocol):
    async def resolve_company(self, ticker_or_cik: str, *, as_of: date) -> CompanyIdentity: ...

    async def list_submissions(self, cik: str, *, as_of: date) -> SubmissionsSnapshot: ...

    async def get_company_facts(self, cik: str, *, as_of: date) -> CompanyFactsSnapshot: ...

    async def fetch_filing(
        self, accession_number: str, *, as_of: date
    ) -> NodeResult[FilingArtifact]: ...


@runtime_checkable
class MarketDataPort(Protocol):
    def get_snapshot(self, ticker: str, *, as_of: date) -> MarketDataSnapshot: ...


@runtime_checkable
class NewsSourcePort(Protocol):
    def search(self, query: str, *, as_of: date) -> tuple[NewsItem, ...]: ...


def deep_freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(deep_freeze(item) for item in value)
    return value


def deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [deep_thaw(item) for item in value]
    return value
