from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import NAMESPACE_URL, uuid5

import pytest

from due_diligence_agent.adapters.openai.startup_web_research import (
    _candidates_from_response,
    _market_context_from_response,
    _provider_request,
    _safe_query,
    _sources_from_response,
)
from due_diligence_agent.domain.startup.market import (
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
)


RETRIEVED_AT = datetime(2026, 8, 1, tzinfo=UTC)
PUBLIC_URL = "https://example.com/public-edtech-report"
SOURCE_ID = uuid5(NAMESPACE_URL, f"startup-public-source:{PUBLIC_URL}")


@pytest.mark.parametrize(
    "query",
    [
        "Smart University invoice_register lead benchmark",
        "Smart University bank_data market benchmark",
        "Smart University банковская выписка выручка",
        "Smart University реестр счетов клиентов",
    ],
)
def test_safe_query_rejects_invoice_bank_aliases_before_provider_call(query: str) -> None:
    assert _safe_query(query) == ""


def test_provider_instructions_explicitly_ban_invoice_and_bank_aliases() -> None:
    instructions = str(_provider_request(("Smart University public edtech CAC",))["instructions"])

    for forbidden in (
        "invoices",
        "invoice registers",
        "bank statements",
        "bank data",
        "banking extracts",
    ):
        assert forbidden in instructions


def test_provider_request_includes_web_search_results_source_metadata() -> None:
    request = _provider_request(("Smart University public edtech CAC",))

    assert "web_search_call.action.sources" in request["include"]
    assert "web_search_call.results" in request["include"]


def test_sources_from_response_accepts_web_search_results_include() -> None:
    response = {
        "output": [
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {"type": "search", "queries": ["Smart University public edtech CAC"]},
                "results": [
                    {
                        "type": "url",
                        "url": PUBLIC_URL,
                        "title": "Public edtech report",
                    }
                ],
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "benchmark_candidates": [],
                                "competitors": [],
                                "market_assumptions": [],
                                "market_sizing": None,
                            }
                        ),
                    }
                ],
            },
        ]
    }

    sources = _sources_from_response(
        response,
        queries=("Smart University public edtech CAC",),
        retrieved_at=RETRIEVED_AT,
    )

    assert [str(source.source_url).rstrip("/") for source in sources] == [PUBLIC_URL]
    assert sources[0].source_label == "Public edtech report"


def test_benchmark_candidates_reject_invoice_and_bank_aliases_in_candidate_dependencies() -> None:
    response = _response_with_payload(
        {
            "benchmark_candidates": [
                _candidate(
                    validation_plan="Validate against invoice_register before use.",
                    dependencies=["published KZT/month range", "bank_data cross-check"],
                ),
                _candidate(
                    input_key="arpa",
                    validation_plan="Validate against another public education pricing source.",
                    dependencies=["published KZT/month range"],
                ),
            ],
            "competitors": [],
            "market_assumptions": [],
            "market_sizing": None,
        }
    )

    candidates = _candidates_from_response(
        response,
        sources=(_source(),),
        retrieved_at=RETRIEVED_AT,
    )

    assert [candidate.input_key for candidate in candidates] == ["arpa"]


def test_market_context_rejects_invoice_and_bank_aliases_in_context_and_sizing() -> None:
    response = _response_with_payload(
        {
            "benchmark_candidates": [],
            "competitors": [
                {
                    "name": "Конкурент из банковской выписки",
                    "category": "direct",
                    "source_url": PUBLIC_URL,
                    "confidence": "0.7",
                }
            ],
            "market_assumptions": [
                {
                    "text": "Valid public edtech demand signal.",
                    "source_url": PUBLIC_URL,
                    "confidence": "0.7",
                    "as_of": "2026-08-01",
                },
                {
                    "text": "Demand based on реестр счетов клиентов.",
                    "source_url": PUBLIC_URL,
                    "confidence": "0.7",
                    "as_of": "2026-08-01",
                },
            ],
            "market_sizing": {
                "tam": _sizing("public_tam_using_bank_data"),
                "sam": _sizing("public_sam"),
                "som": _sizing("public_som"),
            },
        }
    )

    context = _market_context_from_response(
        response,
        sources=(_source(),),
        retrieved_at=RETRIEVED_AT,
    )

    assert context.competitors == ()
    assert [assumption.text for assumption in context.assumptions] == [
        "Valid public edtech demand signal."
    ]
    assert context.sizing is None


def _response_with_payload(payload: dict[str, object]) -> object:
    return {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(payload, ensure_ascii=False),
                    }
                ],
            }
        ]
    }


def _source() -> StartupResearchSource:
    return StartupResearchSource.model_validate(
        {
            "source_id": SOURCE_ID,
            "source_mode": StartupResearchSourceMode.LIVE,
            "source_hash": "sha256:" + ("a" * 64),
            "source_url": PUBLIC_URL,
            "source_label": "Public edtech report",
            "as_of": date(2026, 8, 1),
            "retrieved_at": RETRIEVED_AT,
            "query": "Smart University public edtech CAC",
            "provenance": "live_public_research:web_search:url_citation",
            "confidence": "0.70",
            "supports_primary_financial_metrics": False,
            "stale": False,
            "status": StartupResearchSourceStatus.INFERENCE,
        }
    )


def _candidate(
    *,
    input_key: str = "acquisition_spend",
    validation_plan: str,
    dependencies: list[str],
) -> dict[str, object]:
    return {
        "input_key": input_key,
        "source_url": PUBLIC_URL,
        "provenance": "public_benchmark",
        "publisher": "Public source",
        "publication_date": "2026-08-01",
        "as_of": "2026-08-01",
        "source_class": "industry_report",
        "confidence": "medium",
        "value": None,
        "range_low": "80000",
        "range_high": "120000",
        "unit": "KZT",
        "period": "month",
        "formula": "public KZT/month benchmark",
        "dependencies": dependencies,
        "validation_plan": validation_plan,
        "rationale": "Cited public benchmark.",
    }


def _sizing(formula_version: str) -> dict[str, object]:
    return {
        "value": "1000000",
        "unit": "learners",
        "currency": "KZT",
        "source_url": PUBLIC_URL,
        "confidence": "0.7",
        "as_of": "2026-08-01",
        "formula_version": formula_version,
    }
