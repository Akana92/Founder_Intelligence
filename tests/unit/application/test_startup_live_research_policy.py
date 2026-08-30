from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from due_diligence_agent.domain.startup.market import StartupResearchPlan, StartupResearchSourceMode
from due_diligence_agent.ports.startup_web_search import (
    PUBLIC_COMPARABLE_CONTEXT_NOTE,
    StartupLiveResearchOutageCode,
    StartupLiveResearchPolicy,
    StartupWebSearchProviderUnavailable,
    StartupWebSearchCitation,
    StartupWebSearchRequest,
    StartupWebSearchResult,
)


_AS_OF = date(2026, 8, 13)


def test_default_disabled_and_frozen_mode_make_zero_web_calls() -> None:
    plan = StartupResearchPlan(
        case_id=_uuid("case:live-policy"),
        source_mode=StartupResearchSourceMode.FROZEN,
        queries=("startup market competitors",),
    )
    port = _SpySearchPort()

    result = StartupLiveResearchPolicy().collect(plan, web_search=port, as_of=_AS_OF)

    assert port.calls == ()
    assert result.partial is True
    assert result.outage_codes == ("startup_live_research.disabled",)
    assert result.citations == ()


def test_enabled_policy_sends_bounded_allowlisted_requests_and_returns_citations() -> None:
    plan = StartupResearchPlan(
        case_id=_uuid("case:live-policy"),
        source_mode=StartupResearchSourceMode.LIVE,
        queries=("startup market competitors", "startup market size", "startup alternatives"),
    )
    citation = _citation("citation:1")
    port = _SpySearchPort(result=StartupWebSearchResult(citations=(citation,), outage_code=None))

    result = StartupLiveResearchPolicy(enabled=True, max_queries=1).collect(plan, web_search=port, as_of=_AS_OF)

    assert len(port.calls) == 1
    assert port.calls[0].query == "startup market competitors"
    assert port.calls[0].timeout_seconds == 8
    assert port.calls[0].budget_usd == Decimal("0.02")
    assert result.partial is False
    assert result.outage_codes == ()
    assert result.citations == (citation,)


def test_collect_uses_lower_of_policy_and_plan_query_limits() -> None:
    plan = StartupResearchPlan(
        case_id=_uuid("case:live-policy"),
        source_mode=StartupResearchSourceMode.LIVE,
        queries=(
            "startup market competitors",
            "startup market size",
            "startup alternatives",
            "startup pricing",
        ),
        max_queries=2,
    )
    port = _SpySearchPort()

    result = StartupLiveResearchPolicy(enabled=True, max_queries=4).collect(
        plan,
        web_search=port,
        as_of=_AS_OF,
    )

    assert tuple(call.query for call in port.calls) == (
        "startup market competitors",
        "startup market size",
    )
    assert result.outage_codes == ()


def test_web_outage_yields_partial_result_without_inventing_competitors() -> None:
    plan = StartupResearchPlan(
        case_id=_uuid("case:live-policy"),
        source_mode=StartupResearchSourceMode.LIVE,
        queries=("startup market competitors",),
    )

    result = StartupLiveResearchPolicy(enabled=True).collect(
        plan,
        web_search=_OutageSearchPort(),
        as_of=_AS_OF,
    )

    assert result.partial is True
    assert result.outage_codes == ("startup_live_research.web_search_timeout",)
    assert result.citations == ()


def test_provider_unavailable_maps_to_stable_outage_code_without_provider_text() -> None:
    plan = StartupResearchPlan(
        case_id=_uuid("case:live-policy"),
        source_mode=StartupResearchSourceMode.LIVE,
        queries=("startup market competitors",),
    )

    result = StartupLiveResearchPolicy(enabled=True).collect(
        plan,
        web_search=_ProviderUnavailablePort(),
        as_of=_AS_OF,
    )

    assert result.partial is True
    assert result.outage_codes == ("startup_live_research.web_search_unavailable",)


def test_collect_propagates_programmer_value_errors() -> None:
    plan = StartupResearchPlan(
        case_id=_uuid("case:live-policy"),
        source_mode=StartupResearchSourceMode.LIVE,
        queries=("startup market competitors",),
    )

    with pytest.raises(ValueError, match="programmer failure"):
        StartupLiveResearchPolicy(enabled=True).collect(
            plan,
            web_search=_ProgrammerFailurePort(),
            as_of=_AS_OF,
        )


def test_search_rejects_unapproved_provider_before_adapter_call() -> None:
    port = _SpySearchPort()
    request = StartupWebSearchRequest.model_construct(
        case_id=_uuid("case:live-policy"),
        query="startup market competitors",
        provider="gdelt",
        as_of=_AS_OF,
        timeout_seconds=8,
        max_results=5,
        budget_units=2,
        budget_usd=Decimal("0.02"),
    )

    with pytest.raises(ValueError, match="provider_not_allowed"):
        StartupLiveResearchPolicy(adapter=port, enabled=True, mode="live").search(request)

    assert port.calls == ()


def test_search_returns_typed_result_and_rejects_malformed_adapter_response() -> None:
    citation = _citation("citation:typed-search")
    request = StartupWebSearchRequest(
        case_id=_uuid("case:live-policy"),
        query="startup market competitors",
        as_of=_AS_OF,
        timeout_seconds=8,
        max_results=5,
        budget_units=2,
        budget_usd=Decimal("0.02"),
    )

    result = StartupLiveResearchPolicy(
        adapter=_SpySearchPort(result=StartupWebSearchResult(citations=(citation,), outage_code=None)),
        enabled=True,
        mode="live",
    ).search(request)

    assert result == StartupWebSearchResult(citations=(citation,), outage_code=None)
    with pytest.raises(TypeError, match="StartupWebSearchResult"):
        StartupLiveResearchPolicy(
            adapter=_MalformedSearchPort(),
            enabled=True,
            mode="live",
        ).search(request)


def test_outage_code_is_stable_allowlisted_value() -> None:
    outage_code: StartupLiveResearchOutageCode = "startup_live_research.web_search_unavailable"
    StartupWebSearchResult(
        citations=(),
        outage_code=outage_code,
    )

    with pytest.raises(ValueError, match="unsupported outage code"):
        StartupWebSearchResult(
            citations=(),
            outage_code=cast(StartupLiveResearchOutageCode, "provider said quota exceeded"),
        )


def test_search_citations_are_bounded_and_secondary_only() -> None:
    with pytest.raises(ValueError, match="primary financial"):
        StartupWebSearchCitation.model_validate(
            {
                "citation_id": _uuid("citation:bad"),
                "title": "Revenue proof",
                "url": "https://example.com/revenue",
                "source_label": "Example",
                "as_of": _AS_OF,
                "snippet_hash": "sha256:" + ("b" * 64),
                "supports_primary_financial_metrics": True,
            }
        )

    assert "yfinance_demo.py" in PUBLIC_COMPARABLE_CONTEXT_NOTE
    assert "public-comparable secondary context" in PUBLIC_COMPARABLE_CONTEXT_NOTE
    assert "startup discovery" in PUBLIC_COMPARABLE_CONTEXT_NOTE


@dataclass
class _SpySearchPort:
    result: StartupWebSearchResult = StartupWebSearchResult(citations=(), outage_code=None)

    def __post_init__(self) -> None:
        self.calls: tuple[StartupWebSearchRequest, ...] = ()

    def search(self, request: StartupWebSearchRequest) -> StartupWebSearchResult:
        self.calls = (*self.calls, request)
        return self.result


class _OutageSearchPort:
    def search(self, request: StartupWebSearchRequest) -> StartupWebSearchResult:
        raise TimeoutError("network timeout")


class _ProviderUnavailablePort:
    def search(self, request: StartupWebSearchRequest) -> StartupWebSearchResult:
        raise StartupWebSearchProviderUnavailable("provider said quota exceeded")


class _ProgrammerFailurePort:
    def search(self, request: StartupWebSearchRequest) -> StartupWebSearchResult:
        raise ValueError("programmer failure")


class _MalformedSearchPort:
    def search(self, request: StartupWebSearchRequest) -> StartupWebSearchResult:
        return ("not", "a", "result")  # type: ignore[return-value]


def _citation(seed: str) -> StartupWebSearchCitation:
    return StartupWebSearchCitation.model_validate(
        {
            "citation_id": _uuid(seed),
            "title": "Market map",
            "url": "https://example.com/market-map",
            "source_label": "Example Research",
            "as_of": _AS_OF,
            "snippet_hash": "sha256:" + ("a" * 64),
        }
    )


def _uuid(seed: str) -> UUID:
    return uuid5(NAMESPACE_URL, seed)
