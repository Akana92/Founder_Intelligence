from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from due_diligence_agent.domain.startup.market import StartupResearchPlan, StartupResearchSourceMode


PUBLIC_COMPARABLE_CONTEXT_NOTE = (
    "adapters/market_data/yfinance_demo.py is public-comparable secondary context for "
    "public-company benchmarks; it is not startup discovery and must not support private "
    "startup primary financial claims."
)

StartupWebSearchProvider: TypeAlias = Literal["web_search"]
StartupLiveResearchOutageCode: TypeAlias = Literal[
    "startup_live_research.disabled",
    "startup_live_research.web_search_timeout",
    "startup_live_research.web_search_unavailable",
]

_WEB_SEARCH_PROVIDER: StartupWebSearchProvider = "web_search"
_ALLOWED_OUTAGE_CODES: tuple[StartupLiveResearchOutageCode, ...] = (
    "startup_live_research.disabled",
    "startup_live_research.web_search_timeout",
    "startup_live_research.web_search_unavailable",
)


class StartupWebSearchProviderUnavailable(RuntimeError):
    """Raised when the allowlisted live web search provider is temporarily unavailable."""


class StartupWebSearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    case_id: UUID | None = None
    provider: StartupWebSearchProvider = _WEB_SEARCH_PROVIDER
    timeout_seconds: int = Field(ge=1, le=20)
    max_results: int = Field(ge=1, le=10)
    budget_units: int = Field(ge=1, le=10)
    budget_usd: Decimal = Field(default=Decimal("0.02"), ge=Decimal("0"), le=Decimal("0.05"))
    as_of: date

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("query is required")
        if len(normalized) > 120:
            raise ValueError("query exceeds bound")
        lowered = normalized.casefold()
        unsafe_markers = (
            "file://",
            "api_key=",
            "apikey=",
            "access_token=",
            "auth_token=",
            "authorization=",
            "secret=",
            "password=",
            "bearer ",
        )
        if any(marker in lowered for marker in unsafe_markers):
            raise ValueError("query is unsafe")
        return normalized


class StartupWebSearchHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    url: HttpUrl
    title: str
    published_on: date
    citation: str

    @field_validator("source_id", "title", "citation")
    @classmethod
    def validate_bounded_label(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("label is required")
        if len(normalized) > 140:
            raise ValueError("label exceeds bound")
        return normalized


class StartupWebSearchCitation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    citation_id: UUID
    title: str
    url: HttpUrl
    source_label: str
    as_of: date
    snippet_hash: str
    supports_primary_financial_metrics: bool = False

    @field_validator("title", "source_label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("label is required")
        if len(normalized) > 140:
            raise ValueError("label exceeds bound")
        return normalized

    @field_validator("snippet_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if len(normalized) == 64:
            normalized = f"sha256:{normalized}"
        if not normalized.startswith("sha256:") or len(normalized) != 71:
            raise ValueError("snippet hash must be sha256")
        if any(character not in "0123456789abcdef" for character in normalized.removeprefix("sha256:")):
            raise ValueError("snippet hash must be sha256")
        return normalized

    @field_validator("supports_primary_financial_metrics")
    @classmethod
    def validate_secondary_only(cls, value: bool) -> bool:
        if value:
            raise ValueError("citation cannot support primary financial metrics")
        return value


@dataclass(frozen=True)
class StartupWebSearchResult:
    citations: tuple[StartupWebSearchCitation, ...]
    outage_code: StartupLiveResearchOutageCode | None

    def __post_init__(self) -> None:
        if self.outage_code is not None and self.outage_code not in _ALLOWED_OUTAGE_CODES:
            raise ValueError("unsupported outage code")


@dataclass(frozen=True)
class StartupLiveResearchResult:
    partial: bool
    outage_codes: tuple[StartupLiveResearchOutageCode, ...]
    citations: tuple[StartupWebSearchCitation, ...]


class StartupWebSearchPort(Protocol):
    def search(self, request: StartupWebSearchRequest) -> StartupWebSearchResult: ...


class StartupLiveResearchPolicy:
    def __init__(
        self,
        *,
        adapter: StartupWebSearchPort | None = None,
        enabled: bool = False,
        max_queries: int = 3,
        mode: Literal["frozen", "live"] = "frozen",
    ) -> None:
        self._adapter = adapter
        self._enabled = enabled
        self._mode = mode
        self._max_queries = max(1, min(max_queries, 4))
        self.last_diagnostic_code: StartupLiveResearchOutageCode | None = None

    def search(self, request: StartupWebSearchRequest) -> StartupWebSearchResult:
        self.last_diagnostic_code = None
        if not self._enabled:
            self.last_diagnostic_code = "startup_live_research.disabled"
            return StartupWebSearchResult(citations=(), outage_code="startup_live_research.disabled")
        if self._mode != "live":
            self.last_diagnostic_code = "startup_live_research.disabled"
            return StartupWebSearchResult(citations=(), outage_code="startup_live_research.disabled")
        if request.provider != _WEB_SEARCH_PROVIDER:
            raise ValueError("provider_not_allowed")
        if self._adapter is None:
            self.last_diagnostic_code = "startup_live_research.web_search_unavailable"
            return StartupWebSearchResult(
                citations=(),
                outage_code="startup_live_research.web_search_unavailable",
            )
        bounded = request.model_copy(
            update={
                "timeout_seconds": min(request.timeout_seconds, 20),
                "max_results": min(request.max_results, 10),
                "budget_units": min(request.budget_units, 10),
            }
        )
        try:
            result = self._adapter.search(bounded)
        except TimeoutError:
            self.last_diagnostic_code = "startup_live_research.web_search_timeout"
            return StartupWebSearchResult(
                citations=(),
                outage_code="startup_live_research.web_search_timeout",
            )
        except StartupWebSearchProviderUnavailable:
            self.last_diagnostic_code = "startup_live_research.web_search_unavailable"
            return StartupWebSearchResult(
                citations=(),
                outage_code="startup_live_research.web_search_unavailable",
            )
        if not isinstance(result, StartupWebSearchResult):
            raise TypeError("StartupWebSearchPort.search must return StartupWebSearchResult")
        return result

    def collect(
        self,
        plan: StartupResearchPlan,
        *,
        web_search: StartupWebSearchPort,
        as_of: date,
    ) -> StartupLiveResearchResult:
        if not self._enabled or plan.source_mode is not StartupResearchSourceMode.LIVE:
            return StartupLiveResearchResult(
                partial=True,
                outage_codes=("startup_live_research.disabled",),
                citations=(),
            )
        citations: list[StartupWebSearchCitation] = []
        outage_codes: list[StartupLiveResearchOutageCode] = []
        for query in plan.queries[: min(self._max_queries, plan.max_queries)]:
            try:
                result = web_search.search(
                    StartupWebSearchRequest(
                        case_id=plan.case_id,
                        query=query,
                        as_of=as_of,
                        timeout_seconds=8,
                        max_results=5,
                        budget_units=2,
                        budget_usd=Decimal("0.02"),
                    )
                )
            except TimeoutError:
                outage_codes.append("startup_live_research.web_search_timeout")
                continue
            except StartupWebSearchProviderUnavailable:
                outage_codes.append("startup_live_research.web_search_unavailable")
                continue
            if not isinstance(result, StartupWebSearchResult):
                raise TypeError("StartupWebSearchPort.search must return StartupWebSearchResult")
            citations.extend(result.citations)
            if result.outage_code is not None:
                outage_codes.append(result.outage_code)
        return StartupLiveResearchResult(
            partial=bool(outage_codes),
            outage_codes=tuple(dict.fromkeys(outage_codes)),
            citations=tuple(citations),
        )
