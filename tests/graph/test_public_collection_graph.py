from __future__ import annotations

import asyncio
import json
import re
import threading
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore
from due_diligence_agent.adapters.local_storage.repositories import (
    LocalArtifactRepository,
    LocalCaseRepository,
    LocalEvidenceRepository,
)
from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.application.policies.content_rights import LicenseClass
from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.application.services.public_analysis_service import PublicAnalysisService
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator, StoredArtifact
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    CaseStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.metrics import MetricCalculationResult, MetricStatus
from due_diligence_agent.ports.collectors import (
    CompanyFactsSnapshot,
    CompanyIdentity,
    FilingArtifact,
    MarketDataSnapshot,
    MarketPricePoint,
    NewsItem,
    NewsProvenance,
    SourceSnapshot,
    SubmissionsSnapshot,
)
from due_diligence_agent.ports.retrieval import EvidenceChunk, RetrievalHit
from due_diligence_agent.workflows.public_company.graph import (
    PublicGraphDependencies,
    build_public_graph,
)
from due_diligence_agent.workflows.public_company.plan import validate_public_plan
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus
from due_diligence_agent.workflows.shared.plan import AnalysisPlan, PlanStep


CASE_ID = "11111111-1111-4111-8111-111111111111"
CASE_UUID = UUID(CASE_ID)
AS_OF = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
ARTIFACT_ID = UUID("22222222-2222-4222-8222-222222222222")
SECOND_ARTIFACT_ID = UUID("22222222-2222-4222-8222-222222222223")
FILING_FACT_ID = UUID("33333333-3333-4333-8333-333333333333")
SECOND_FILING_FACT_ID = UUID("33333333-3333-4333-8333-333333333334")
MARKET_FACT_ID = UUID("12c3f39b-6759-5742-ac7a-a2f6571f2fac")
NEWS_FACT_ID = UUID("bfaa50d9-eb35-5126-99cc-3a744f356014")
CALCULATION_ID = UUID("66666666-6666-4666-8666-666666666666")
CHUNK_ID = UUID("77777777-7777-4777-8777-777777777777")
SECOND_CHUNK_ID = UUID("77777777-7777-4777-8777-777777777778")
RAW_SENTINEL = "<html><body>Material liquidity risk secret prompt</body></html>"
NEWS_SENTINEL = "raw news body must never be audited"


def test_public_graph_calls_real_ports_persists_ids_and_resumes_from_sqlite(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    config = _thread_config()

    first = graph.invoke(
        {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()}, config=config
    )
    assert first["status"] == "awaiting_scope_approval"

    resumed = graph.invoke(Command(resume={"approved": True}), config=config)

    assert resumed["case_id"] == CASE_ID
    assert resumed["status"] == "completed"
    assert {str(ARTIFACT_ID), str(SECOND_ARTIFACT_ID)} <= set(resumed["artifact_ids"])
    assert len(resumed["artifact_ids"]) == 4
    assert set(resumed["evidence_fact_ids"]) == {
        str(FILING_FACT_ID),
        str(SECOND_FILING_FACT_ID),
        str(MARKET_FACT_ID),
        str(NEWS_FACT_ID),
    }
    assert resumed["chunk_ids"] == [str(CHUNK_ID), str(SECOND_CHUNK_ID)]
    assert resumed["calculation_ids"] == [str(CALCULATION_ID)]
    assert deps.sec.calls == [
        "resolve_company:AAPL",
        "list_submissions:0000320193",
        "get_company_facts:0000320193",
        "fetch_filing:0000320193-26-000001",
        "fetch_filing:0000320193-26-000002",
    ]
    assert deps.market.calls == ["get_snapshot:AAPL"]
    assert deps.news.calls == ["search:AAPL"]
    assert {ARTIFACT_ID, SECOND_ARTIFACT_ID} <= {item.id for item in deps.artifact_repository.saved}
    assert len(deps.artifact_repository.saved) == 4
    assert {item.id for item in deps.evidence_repository.saved} == {
        FILING_FACT_ID,
        SECOND_FILING_FACT_ID,
        MARKET_FACT_ID,
        NEWS_FACT_ID,
    }


def test_frozen_sec_companyfacts_fixture_maps_required_revenue_and_gross_profit(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)
    deps.sec.submissions_data = _fixture_json("sec/submissions.json")
    deps.sec.company_facts_data = _fixture_json("sec/companyfacts.json")

    result = _complete(graph)

    assert result["status"] == "completed"
    facts = {fact.name: fact for fact in deps.evidence_repository.saved}
    revenue = facts["revenue"]
    gross_profit = facts["gross_profit"]
    assert revenue.value == Decimal("1000000")
    assert revenue.unit == "USD"
    assert revenue.period == "2026"
    assert gross_profit.value == Decimal("400000")
    assert gross_profit.unit == "USD"
    assert gross_profit.period == "2026"
    assert revenue.artifact_id == ARTIFACT_ID
    assert revenue.locator.kind == "sec_company_fact"
    assert '"taxonomy":"us-gaap"' in revenue.locator.value
    assert '"concept":"Revenues"' in revenue.locator.value
    assert revenue.locator.artifact_id == ARTIFACT_ID
    assert revenue.source_priority == SourcePriority.OFFICIAL_OR_SIGNED
    assert revenue.extraction_method == "sec_companyfacts"
    assert revenue.supporting_text_hash is not None
    assert re.fullmatch(r"[0-9a-f]{64}", revenue.supporting_text_hash)
    assert '"accession":"0000320193-26-000001"' in revenue.locator.value
    assert RAW_SENTINEL not in revenue.locator.value
    assert revenue.retrieved_at == AS_OF


def test_nested_sec_companyfacts_maps_required_revenue_and_gross_profit(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)
    deps.sec.company_facts_data = _companyfacts(
        _xbrl_observation("Revenues", "1000", accession="0000320193-26-000001"),
        _xbrl_observation("GrossProfit", "400", accession="0000320193-26-000001"),
    )

    result = _complete(graph)

    facts = {fact.name: fact for fact in deps.evidence_repository.saved}
    assert result["status"] == "completed"
    assert facts["revenue"].period == "2026"
    assert facts["gross_profit"].period == "2026"


@pytest.mark.parametrize(
    ("concept", "missing"),
    [("Revenues", "gross_profit"), ("GrossProfit", "revenue")],
)
def test_sec_companyfacts_blocks_when_one_required_official_fact_is_missing(
    tmp_path: Path,
    concept: str,
    missing: str,
) -> None:
    graph, deps = _graph(tmp_path)
    deps.sec.company_facts_data = _companyfacts(
        _xbrl_observation(concept, "1000", accession="0000320193-26-000001")
    )

    result = _complete(graph)

    assert result["status"] == "blocked"
    assert (
        result["primary_failure"]
        == f"collect_sec:sec_companyfacts_required_facts_missing:{missing}"
    )
    sec_facts = [
        fact
        for fact in deps.evidence_repository.saved
        if fact.source_priority == SourcePriority.OFFICIAL_OR_SIGNED
    ]
    assert len(sec_facts) == 1
    assert str(sec_facts[0].id) in result["evidence_fact_ids"]
    assert deps.retrieval.calls == 0
    assert deps.metric_service.calls == 0


def test_xbrl_quarterly_period_is_not_labeled_as_annual(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    deps.sec.company_facts_data = _companyfacts(
        _xbrl_observation("Revenues", "250", accession="0000320193-26-000002", fy=2026, fp="Q2"),
        _xbrl_observation("GrossProfit", "100", accession="0000320193-26-000002", fy=2026, fp="Q2"),
    )

    result = _complete(graph)

    assert result["status"] == "completed"
    assert {
        fact.period
        for fact in deps.evidence_repository.saved
        if fact.name in {"revenue", "gross_profit"}
    } == {"2026-Q2"}


def test_sec_companyfacts_blocks_when_required_facts_have_no_compatible_period(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)
    deps.sec.company_facts_data = _companyfacts(
        _xbrl_observation("Revenues", "1000", accession="0000320193-26-000001", fy=2026, fp="FY"),
        _xbrl_observation("GrossProfit", "100", accession="0000320193-26-000002", fy=2026, fp="Q2"),
    )

    result = _complete(graph)

    sec_facts = [
        fact for fact in deps.evidence_repository.saved if fact.name in {"revenue", "gross_profit"}
    ]
    assert result["status"] == "blocked"
    assert (
        result["primary_failure"]
        == "collect_sec:sec_companyfacts_required_facts_missing:compatible_period"
    )
    assert {fact.name for fact in sec_facts} == {"revenue", "gross_profit"}
    assert {fact.period for fact in sec_facts} == {"2026", "2026-Q2"}
    assert {fact.artifact_id for fact in sec_facts} == {ARTIFACT_ID, SECOND_ARTIFACT_ID}
    assert {str(fact.id) for fact in sec_facts} <= set(result["evidence_fact_ids"])
    assert {str(ARTIFACT_ID), str(SECOND_ARTIFACT_ID)} <= set(result["artifact_ids"])
    assert deps.retrieval.calls == 0
    assert deps.metric_service.calls == 0


def test_sec_observation_with_second_accession_uses_second_filing_artifact(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)
    deps.sec.company_facts_data = _companyfacts(
        _xbrl_observation("Revenues", "250", accession="0000320193-26-000002", fy=2026, fp="Q2"),
        _xbrl_observation("GrossProfit", "100", accession="0000320193-26-000002", fy=2026, fp="Q2"),
    )

    result = _complete(graph)

    assert result["status"] == "completed"
    assert {
        fact.artifact_id
        for fact in deps.evidence_repository.saved
        if fact.name in {"revenue", "gross_profit"}
    } == {SECOND_ARTIFACT_ID}


def test_unknown_sec_accession_is_skipped_and_required_fact_failure_is_compact(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)
    deps.sec.company_facts_data = _companyfacts(
        _xbrl_observation("Revenues", "1000", accession="0000320193-99-999999"),
        _xbrl_observation("GrossProfit", "400", accession="0000320193-99-999999"),
    )

    result = _complete(graph)

    assert result["status"] == "blocked"
    assert result["primary_failure"] == "collect_sec:sec_companyfacts_required_facts_missing"
    assert [fact for fact in deps.evidence_repository.saved if fact.source_priority == 1] == []
    assert deps.retrieval.calls == 0


def test_sec_collection_blocks_when_no_required_official_companyfacts_exist(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    deps.sec.company_facts_data = {
        "facts": {"us-gaap": {"EntityCommonStockSharesOutstanding": {"units": {}}}}
    }

    result = _complete(graph)

    assert result["status"] == "blocked"
    assert result["primary_failure"] == "collect_sec:sec_companyfacts_required_facts_missing"
    assert deps.retrieval.calls == 0
    assert deps.metric_service.calls == 0


def test_market_and_news_facts_use_their_own_source_artifacts(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)

    _complete(graph)

    artifacts_by_id = {artifact.id: artifact for artifact in deps.artifact_repository.saved}
    facts_by_name = {fact.name: fact for fact in deps.evidence_repository.saved}
    market_artifact = artifacts_by_id[facts_by_name["market_cap"].artifact_id]
    news_artifact = artifacts_by_id[facts_by_name["news_signal"].artifact_id]
    assert market_artifact.source == "market"
    assert market_artifact.source_url == "https://example.test/market"
    assert market_artifact.sensitivity is SensitivityClass.PUBLIC
    assert facts_by_name["market_cap"].artifact_id not in {ARTIFACT_ID, SECOND_ARTIFACT_ID}
    assert news_artifact.source == "news"
    assert news_artifact.source_url == "https://example.test/news"
    assert news_artifact.sensitivity is SensitivityClass.PUBLIC
    assert facts_by_name["news_signal"].artifact_id not in {ARTIFACT_ID, SECOND_ARTIFACT_ID}


def test_market_missing_market_cap_persists_artifact_but_no_zero_fact(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    deps.market.market_cap = None

    result = _complete(graph)

    market_artifacts = [
        artifact for artifact in deps.artifact_repository.saved if artifact.source == "market"
    ]
    assert result["status"] == "completed"
    assert len(market_artifacts) == 1
    assert "collect_market:market_cap_missing" in result["warnings"]
    assert "market_cap" not in {fact.name for fact in deps.evidence_repository.saved}
    assert all(fact.value != Decimal("0") for fact in deps.evidence_repository.saved)


def test_market_and_news_data_refs_include_source_artifacts_and_evidence_ids(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)

    result = _complete(graph)

    node_refs = {
        node_result["node_name"]: set(node_result["data_refs"])
        for node_result in result["node_results"]
        if node_result["node_name"] in {"collect_market", "collect_news"}
    }
    artifacts_by_source = {
        artifact.source: artifact.id for artifact in deps.artifact_repository.saved
    }
    facts_by_name = {fact.name: fact.id for fact in deps.evidence_repository.saved}
    assert str(artifacts_by_source["market"]) in node_refs["collect_market"]
    assert str(facts_by_name["market_cap"]) in node_refs["collect_market"]
    assert str(artifacts_by_source["news"]) in node_refs["collect_news"]
    assert str(facts_by_name["news_signal"]) in node_refs["collect_news"]


@pytest.mark.asyncio
async def test_public_graph_ainvoke_awaits_async_sources(tmp_path: Path) -> None:
    config = _thread_config()
    deps = _deps()
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "async-sources.sqlite3")) as saver:
        graph = build_public_graph(deps, checkpointer=saver)
        first = await graph.ainvoke(
            {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()}, config=config
        )
        result = await graph.ainvoke(Command(resume={"approved": True}), config=config)

    assert first["status"] == "awaiting_scope_approval"
    assert result["status"] == "completed"
    assert deps.sec.calls[:3] == [
        "resolve_company:AAPL",
        "list_submissions:0000320193",
        "get_company_facts:0000320193",
    ]


@pytest.mark.asyncio
async def test_public_graph_ainvoke_uses_native_async_sqlite_saver(tmp_path: Path) -> None:
    deps = _deps()
    async with AsyncSqliteSaver.from_conn_string(
        str(tmp_path / "async-checkpoints.sqlite3")
    ) as saver:
        graph = build_public_graph(deps, checkpointer=saver)
        first = await graph.ainvoke(
            {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()},
            config=_thread_config(),
        )
        result = await graph.ainvoke(Command(resume={"approved": True}), config=_thread_config())

    assert first["status"] == "awaiting_scope_approval"
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_approved_plan_fans_out_sec_market_and_news_concurrently(tmp_path: Path) -> None:
    deps = _deps()
    barrier = FanoutBarrier(expected={"sec", "market", "news"})
    deps.sec = BarrierSecSource(barrier)
    deps.market = BarrierMarketSource(barrier)
    deps.news = BarrierNewsSource(barrier)
    async with AsyncSqliteSaver.from_conn_string(
        str(tmp_path / "fanout-checkpoints.sqlite3")
    ) as saver:
        graph = build_public_graph(deps, checkpointer=saver)
        await graph.ainvoke(
            {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()},
            config=_thread_config(),
        )
        result = await graph.ainvoke(Command(resume={"approved": True}), config=_thread_config())

    assert result["status"] == "completed"
    assert barrier.entered == {"sec", "market", "news"}


def test_public_graph_exposes_formal_collector_join_edge(tmp_path: Path) -> None:
    deps = _deps()
    with _sqlite_saver(tmp_path / "checkpoints.sqlite3") as saver:
        graph = build_public_graph(deps, checkpointer=saver)

    assert graph.task11_waiting_edges == (
        (("collect_sec", "collect_market", "collect_news"), "normalize_collection"),
    )


def test_transient_http_exceptions_are_retryable_and_audit_uses_stable_codes(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)
    request = httpx.Request("GET", "https://example.test/sec")
    deps.sec.resolve_results = [
        httpx.ConnectError("raw socket failure with private payload", request=request),
        CompanyIdentity(cik="0000320193", ticker="AAPL", name="Apple Inc."),
    ]

    result = _complete(graph)

    serialized_audit = _serialized(deps.audit.payloads)
    assert result["status"] == "completed"
    assert deps.sec.calls.count("resolve_company:AAPL") == 2
    assert deps.guard.calls_by_node("collect_sec") == [1, 2]
    assert "source_transient:connect_error" in serialized_audit
    assert "raw socket failure" not in serialized_audit


def test_unexpected_programmer_errors_are_not_swallowed(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    deps.market.raise_unexpected = RuntimeError("programmer bug should surface")

    graph.invoke(
        {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()},
        config=_thread_config(),
    )
    with pytest.raises(RuntimeError, match="programmer bug should surface"):
        graph.invoke(Command(resume={"approved": True}), config=_thread_config())


def test_local_sqlite_retry_restart_is_idempotent_for_identical_persisted_ids(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    db_path = tmp_path / "case.sqlite3"
    object_path = tmp_path / "objects"
    deps = _local_deps(db_path=db_path, object_path=object_path)
    deps.sec.fetch_results = [
        NodeResult(status=NodeStatus.SUCCESS, data=_filing("0000320193-26-000001", ARTIFACT_ID)),
        NodeResult(
            status=NodeStatus.RETRYABLE_ERROR,
            errors=["temporary_filing_timeout"],
            retry_after_seconds=0,
        ),
        NodeResult(
            status=NodeStatus.SUCCESS,
            data=_filing("0000320193-26-000001", ARTIFACT_ID),
        ),
        NodeResult(
            status=NodeStatus.SUCCESS,
            data=_filing("0000320193-26-000002", SECOND_ARTIFACT_ID),
        ),
    ]

    with _sqlite_saver(checkpoint_path) as first_saver:
        graph = build_public_graph(deps, checkpointer=first_saver)
        graph.invoke(
            {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()},
            config=_thread_config(),
        )
        first = graph.invoke(Command(resume={"approved": True}), config=_thread_config())
        assert first["status"] == "completed"
    assert deps.db is not None
    deps.db.close()

    with _sqlite_saver(checkpoint_path) as second_saver:
        restarted_deps = _local_deps(db_path=db_path, object_path=object_path)
        restarted = build_public_graph(restarted_deps, checkpointer=second_saver)
        completed = restarted.invoke(Command(resume={"approved": True}), config=_thread_config())

    assert completed["status"] == "completed"
    assert restarted_deps.db is not None
    assert (
        len(restarted_deps.db.fetch_all("SELECT id FROM artifacts WHERE case_id = ?", (CASE_ID,)))
        == 4
    )
    assert len(restarted_deps.evidence_repository.list_for_case(CASE_UUID)) >= 4


def test_duplicate_artifact_id_with_different_content_fails_closed(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    deps.artifact_store.saved[ARTIFACT_ID] = b"original bytes"
    deps.artifact_store.conflicting_payload_for = ARTIFACT_ID

    graph.invoke(
        {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()},
        config=_thread_config(),
    )
    result = graph.invoke(Command(resume={"approved": True}), config=_thread_config())

    assert result["status"] == "blocked"
    assert result["primary_failure"] == "collect_sec:artifact_content_conflict"


def test_denied_scope_ends_before_sources_retrieval_or_metrics(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    graph.invoke(
        {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()}, config=_thread_config()
    )

    denied = graph.invoke(Command(resume={"approved": False}), config=_thread_config())

    assert denied["status"] == "blocked"
    assert denied["errors"] == ["scope:approval_denied"]
    assert denied["primary_failure"] == "scope:approval_denied"
    assert denied.get("artifact_ids", []) == []
    assert denied.get("evidence_fact_ids", []) == []
    assert deps.no_downstream_calls()
    assert deps.audit.events == ["scope", "scope_gate"]


def test_retrieval_retry_success_rechecks_guard_before_each_attempt(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    deps.retrieval.results = [
        NodeResult(
            status=NodeStatus.RETRYABLE_ERROR,
            errors=["temporary_index_lock"],
            retry_after_seconds=0,
        ),
        NodeResult(status=NodeStatus.SUCCESS, data_refs=[str(CHUNK_ID)]),
    ]

    result = _complete(graph)

    assert result["status"] == "completed"
    assert result["chunk_ids"] == [str(CHUNK_ID), str(SECOND_CHUNK_ID)]
    assert deps.retrieval.calls == 2
    assert deps.guard.calls_by_node("retrieve") == [1, 2]
    assert deps.metric_service.calls == 1


def test_retrieval_retry_exhaustion_blocks_and_does_not_calculate(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    deps.retrieval.results = [
        NodeResult(
            status=NodeStatus.RETRYABLE_ERROR,
            errors=["temporary_index_lock"],
            retry_after_seconds=0,
        ),
        NodeResult(
            status=NodeStatus.RETRYABLE_ERROR, errors=["second_failure"], retry_after_seconds=0
        ),
        NodeResult(
            status=NodeStatus.RETRYABLE_ERROR, errors=["third_failure"], retry_after_seconds=0
        ),
    ]

    result = _complete(graph)

    assert result["status"] == "blocked"
    assert result["primary_failure"] == "retrieve:temporary_index_lock"
    assert "retrieve:temporary_index_lock" in result["errors"]
    assert deps.retrieval.calls == 3
    assert deps.metric_service.calls == 0


def test_retrieval_sync_retry_after_is_capped_and_preserves_primary_failure(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)
    recorded_sleeps: list[float] = []
    deps.sync_sleeper = recorded_sleeps.append
    deps.retrieval.results = [
        NodeResult(
            status=NodeStatus.RETRYABLE_ERROR,
            errors=["temporary_index_lock"],
            retry_after_seconds=120,
        ),
        NodeResult(
            status=NodeStatus.RETRYABLE_ERROR,
            errors=["second_failure"],
            retry_after_seconds=45,
        ),
        NodeResult(
            status=NodeStatus.RETRYABLE_ERROR,
            errors=["third_failure"],
            retry_after_seconds=90,
        ),
    ]

    result = _complete(graph)

    assert result["status"] == "blocked"
    assert result["primary_failure"] == "retrieve:temporary_index_lock"
    assert "retrieve:temporary_index_lock" in result["errors"]
    assert "retrieve:second_failure" not in result["errors"]
    assert "retrieve:third_failure" not in result["errors"]
    assert recorded_sleeps == [30.0, 30.0]
    assert deps.retrieval.calls == 3
    assert deps.guard.calls_by_node("retrieve") == [1, 2, 3]
    assert deps.metric_service.calls == 0


@pytest.mark.parametrize(
    "exception_factory",
    [
        lambda request: httpx.ConnectError(
            "raw socket failure with private payload", request=request
        ),
        lambda request: httpx.TimeoutException("raw timeout private payload", request=request),
        lambda request: httpx.HTTPStatusError(
            "raw 429 private payload",
            request=request,
            response=httpx.Response(429, request=request),
        ),
        lambda request: httpx.HTTPStatusError(
            "raw 503 private payload",
            request=request,
            response=httpx.Response(503, request=request),
        ),
    ],
)
def test_retrieval_expected_http_exceptions_retry_compactly_without_raw_text(
    tmp_path: Path,
    exception_factory: Any,
) -> None:
    graph, deps = _graph(tmp_path)
    request = httpx.Request("GET", "https://example.test/retrieval")
    deps.retrieval.exceptions = [
        exception_factory(request),
        exception_factory(request),
        exception_factory(request),
    ]
    deps.sync_sleeper = lambda _seconds: None

    result = _complete(graph)

    serialized = _serialized(result) + _serialized(deps.audit.payloads)
    assert result["status"] == "blocked"
    assert result["primary_failure"].startswith("retrieve:source_transient:")
    assert deps.retrieval.calls == 3
    assert deps.guard.calls_by_node("retrieve") == [1, 2, 3]
    assert "raw " not in serialized
    assert deps.metric_service.calls == 0


def test_retrieval_unexpected_programmer_error_propagates(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    deps.retrieval.exceptions = [RuntimeError("programmer retrieval bug should surface")]

    graph.invoke(
        {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()},
        config=_thread_config(),
    )
    with pytest.raises(RuntimeError, match="programmer retrieval bug should surface"):
        graph.invoke(Command(resume={"approved": True}), config=_thread_config())


def test_guard_denial_before_retry_stops_without_second_source_call_and_preserves_primary_failure(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)
    deps.news.results = [
        NodeResult(
            status=NodeStatus.RETRYABLE_ERROR,
            errors=["temporary_news_outage"],
            retry_after_seconds=0,
        )
    ]
    deps.guard.deny = {("collect_news", 2): "budget_denied"}

    result = _complete(graph)

    assert result["status"] == "completed"
    assert result["warnings"] == [
        "collect_news:temporary_news_outage",
        "collect_news:budget_denied",
    ]
    assert deps.news.calls == ["search:AAPL"]
    assert deps.guard.calls_by_node("collect_news") == [1, 2]
    assert deps.metric_service.calls == 1


def test_blocked_and_failed_source_results_are_not_retried(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)
    deps.sec.fetch_results = [
        NodeResult(status=NodeStatus.BLOCKED, errors=["sec_primary_unavailable"])
    ]

    result = _complete(graph)

    assert result["status"] == "blocked"
    assert result["primary_failure"] == "collect_sec:sec_primary_unavailable"
    assert deps.sec.calls.count("fetch_filing:0000320193-26-000001") == 1
    assert deps.guard.calls_by_node("collect_sec") == [1]


def test_audit_checkpoint_and_state_do_not_contain_raw_filing_news_or_prompt_text(
    tmp_path: Path,
) -> None:
    graph, deps = _graph(tmp_path)

    completed_public_state = _complete(graph)

    serialized = _serialized(completed_public_state) + _serialized(deps.audit.payloads)
    checkpoint_bytes = (tmp_path / "checkpoints.sqlite3").read_bytes()
    assert RAW_SENTINEL not in serialized
    assert RAW_SENTINEL.encode() not in checkpoint_bytes
    assert NEWS_SENTINEL not in serialized
    assert NEWS_SENTINEL.encode() not in checkpoint_bytes
    assert "secret prompt" not in serialized
    assert b"secret prompt" not in checkpoint_bytes


def test_every_task11_graph_node_records_one_privacy_safe_audit_event(tmp_path: Path) -> None:
    graph, deps = _graph(tmp_path)

    _complete(graph)

    assert deps.audit.events[:3] == ["scope", "scope_gate", "plan"]
    assert Counter(deps.audit.events) == Counter(
        [
            "scope",
            "scope_gate",
            "plan",
            "collect_sec",
            "collect_market",
            "collect_news",
            "normalize_collection",
            "retrieve",
            "calculate",
            "normalize",
        ]
    )
    assert all("data" not in payload for payload in deps.audit.payloads)


def test_checkpoint_can_resume_after_saver_restart(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    deps = _deps()
    with _sqlite_saver(checkpoint_path) as first_saver:
        graph = build_public_graph(deps, checkpointer=first_saver)
        first = graph.invoke(
            {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()},
            config=_thread_config(),
        )
        assert first["status"] == "awaiting_scope_approval"

    with _sqlite_saver(checkpoint_path) as second_saver:
        restarted = build_public_graph(deps, checkpointer=second_saver)
        resumed = restarted.invoke(Command(resume={"approved": True}), config=_thread_config())

    assert resumed["status"] == "completed"
    assert resumed["case_id"] == CASE_ID
    assert resumed["evidence_fact_ids"]


def test_public_analysis_service_uses_case_id_as_thread_id(tmp_path: Path) -> None:
    deps = _deps()
    with _sqlite_saver(tmp_path / "service-checkpoints.sqlite3") as saver:
        service = PublicAnalysisService(build_public_graph(deps, checkpointer=saver))

        first = service.start(ticker="aapl", case_id=CASE_ID)
        resumed = service.resume(case_id=CASE_ID, decision={"approved": True})

    assert first["status"] == "awaiting_scope_approval"
    assert resumed["case_id"] == CASE_ID
    assert resumed["status"] == "completed"


@pytest.mark.parametrize(
    ("plan", "message"),
    [
        (
            AnalysisPlan(
                objectives=["x"],
                token_budget=1,
                steps=[
                    PlanStep(
                        task_id="x",
                        node_name="not_registered",
                        required_output_schema="SecCollectionResult",
                    )
                ],
            ),
            "plan.node.unsupported:not_registered",
        ),
        (
            AnalysisPlan(
                objectives=["x"],
                token_budget=1,
                steps=[
                    PlanStep(
                        task_id="x",
                        node_name="collect_sec",
                        required_output_schema="WrongSchema",
                    )
                ],
            ),
            "plan.schema.unregistered:WrongSchema",
        ),
        (
            AnalysisPlan(
                objectives=["x"],
                token_budget=1,
                steps=[
                    PlanStep(
                        task_id="x",
                        node_name="collect_sec",
                        depends_on=["missing"],
                        required_output_schema="SecCollectionResult",
                    )
                ],
            ),
            "plan.depends_on.unknown:missing",
        ),
        (
            AnalysisPlan(
                objectives=["x"],
                token_budget=1,
                steps=[
                    PlanStep(
                        task_id="x",
                        node_name="collect_sec",
                        required_output_schema="SecCollectionResult",
                    ),
                    PlanStep(
                        task_id="x",
                        node_name="collect_market",
                        required_output_schema="MarketCollectionResult",
                    ),
                ],
            ),
            "plan.task_id.duplicate",
        ),
        (
            AnalysisPlan(
                objectives=["x"],
                token_budget=1,
                steps=[
                    PlanStep(
                        task_id="x",
                        node_name="collect_sec",
                        depends_on=["y"],
                        required_output_schema="SecCollectionResult",
                    ),
                    PlanStep(
                        task_id="y",
                        node_name="collect_market",
                        depends_on=["x"],
                        required_output_schema="MarketCollectionResult",
                    ),
                ],
            ),
            "plan.depends_on.cycle:x",
        ),
    ],
)
def test_public_plan_validator_rejects_invalid_plans(plan: AnalysisPlan, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_public_plan(plan)


def _complete(graph: Any) -> dict[str, Any]:
    graph.invoke(
        {"ticker": "AAPL", "case_id": CASE_ID, "as_of": AS_OF.isoformat()},
        config=_thread_config(),
    )
    return cast(
        dict[str, Any], graph.invoke(Command(resume={"approved": True}), config=_thread_config())
    )


def _graph(tmp_path: Path) -> tuple[Any, "FakeDependencies"]:
    deps = _deps()
    saver_context = _sqlite_saver(tmp_path / "checkpoints.sqlite3")
    saver = saver_context.__enter__()
    deps.saver_context = saver_context
    return build_public_graph(deps, checkpointer=saver), deps


def _deps() -> "FakeDependencies":
    artifact_repository = FakeArtifactRepository()
    evidence_repository = FakeEvidenceRepository()
    audit = FakeAudit()
    return FakeDependencies(
        sec=FakeSecSource(),
        market=FakeMarketSource(),
        news=FakeNewsSource(),
        retrieval=FakeRetrievalService(),
        metric_service=FakeMetricService(),
        audit=audit,
        artifact_repository=artifact_repository,
        evidence_repository=evidence_repository,
        artifact_store=FakeArtifactStore(),
        guard=FakeAttemptGuard(),
        async_sleeper=_no_sleep,
        sync_sleeper=lambda _seconds: None,
    )


@contextmanager
def _sqlite_saver(path: Path) -> Iterator[SqliteSaver]:
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver


def _thread_config() -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": CASE_ID}}


def _serialized(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)


@dataclass
class FakeDependencies(PublicGraphDependencies):
    sec: "FakeSecSource"
    market: "FakeMarketSource"
    news: "FakeNewsSource"
    retrieval: "FakeRetrievalService"
    metric_service: "FakeMetricService"
    audit: "FakeAudit"
    artifact_repository: Any
    evidence_repository: Any
    artifact_store: Any
    guard: "FakeAttemptGuard"
    async_sleeper: Any | None = None
    sync_sleeper: Any | None = None
    saver_context: Any | None = None

    def no_downstream_calls(self) -> bool:
        return not (
            self.sec.calls
            or self.market.calls
            or self.news.calls
            or self.retrieval.calls
            or self.metric_service.calls
        )


class FakeSecSource:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.resolve_results: list[CompanyIdentity | Exception] = []
        self.fetch_results: list[NodeResult[FilingArtifact]] = []
        self.submissions_data: dict[str, Any] = {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
                    "form": ["10-K", "10-Q"],
                    "filingDate": ["2026-06-30", "2026-06-30"],
                    "reportDate": ["2026-06-30", "2026-06-30"],
                }
            }
        }
        self.company_facts_data: dict[str, Any] = {
            "facts": [
                _fact_payload(FILING_FACT_ID, ARTIFACT_ID, "revenue", "500", "sec_fact", "2025"),
                _fact_payload(
                    SECOND_FILING_FACT_ID,
                    SECOND_ARTIFACT_ID,
                    "gross_profit",
                    "200",
                    "sec_fact",
                    "2025",
                ),
            ]
        }

    async def resolve_company(self, ticker_or_cik: str, *, as_of: date) -> CompanyIdentity:
        self.calls.append(f"resolve_company:{ticker_or_cik}")
        if self.resolve_results:
            result = self.resolve_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return CompanyIdentity(cik="0000320193", ticker=ticker_or_cik, name="Apple Inc.")

    async def list_submissions(self, cik: str, *, as_of: date) -> SubmissionsSnapshot:
        self.calls.append(f"list_submissions:{cik}")
        return SubmissionsSnapshot(
            data=self.submissions_data,
            snapshot=_snapshot("sec-submissions", as_of),
        )

    async def get_company_facts(self, cik: str, *, as_of: date) -> CompanyFactsSnapshot:
        self.calls.append(f"get_company_facts:{cik}")
        return CompanyFactsSnapshot(
            data=self.company_facts_data,
            snapshot=_snapshot("sec-facts", as_of),
        )

    async def fetch_filing(
        self, accession_number: str, *, as_of: date
    ) -> NodeResult[FilingArtifact]:
        self.calls.append(f"fetch_filing:{accession_number}")
        if self.fetch_results:
            return self.fetch_results.pop(0)
        artifact_id = ARTIFACT_ID if accession_number.endswith("000001") else SECOND_ARTIFACT_ID
        return NodeResult(
            status=NodeStatus.SUCCESS,
            data=FilingArtifact(
                accession_number=accession_number,
                content=RAW_SENTINEL.encode("utf-8"),
                snapshot=_snapshot(
                    f"sec-filing-{artifact_id}",
                    as_of,
                    storage_ref=f"fixture://{artifact_id}",
                ),
            ),
        )


class FakeMarketSource:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.raise_unexpected: Exception | None = None
        self.market_cap: Decimal | None = Decimal("3000")

    def get_snapshot(self, ticker: str, *, as_of: date) -> MarketDataSnapshot:
        self.calls.append(f"get_snapshot:{ticker}")
        if self.raise_unexpected is not None:
            raise self.raise_unexpected
        return MarketDataSnapshot(
            ticker=ticker,
            as_of=as_of,
            currency="USD",
            market_cap=self.market_cap,
            prices=(MarketPricePoint(date=as_of, close=Decimal("195.25"), volume=100),),
            snapshot=_snapshot("market", as_of, license_class="research_only"),
        )


class FakeNewsSource:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.results: list[NodeResult[tuple[NewsItem, ...]]] = []

    def search(self, query: str, *, as_of: date) -> tuple[NewsItem, ...]:
        self.calls.append(f"search:{query}")
        if self.results:
            result = self.results.pop(0)
            if result.status is NodeStatus.RETRYABLE_ERROR:
                raise RetryableSourceError(result)
        return (
            NewsItem(
                url="https://example.test/news",
                publisher="Example",
                domain="example.test",
                title="Apple supplier update",
                snippet=NEWS_SENTINEL,
                published_at=AS_OF,
                query=query,
                retrieved_at=AS_OF,
                response_hash="d" * 64,
                license_class=LicenseClass.DISCOVERY_METADATA_ONLY,
                provenance=NewsProvenance(
                    provider="fixture",
                    provider_version="news@1",
                    source_url="https://example.test/news",
                    response_hash="d" * 64,
                ),
            ),
        )


class FakeRetrievalService:
    def __init__(self) -> None:
        self.calls = 0
        self.results: list[NodeResult[dict[str, Any]]] = []
        self.exceptions: list[Exception] = []

    def index_filing(
        self,
        *,
        case_id: UUID,
        filing: FilingArtifact,
        sensitivity: SensitivityClass,
        artifact_id: UUID | None = None,
    ) -> tuple[EvidenceChunk, ...]:
        target_artifact_id = artifact_id or (
            ARTIFACT_ID if filing.accession_number.endswith("000001") else SECOND_ARTIFACT_ID
        )
        return (
            EvidenceChunk(
                chunk_id=CHUNK_ID
                if filing.accession_number.endswith("000001")
                else SECOND_CHUNK_ID,
                case_id=case_id,
                artifact_id=target_artifact_id,
                locator=SourceLocator(kind="sec_filing_section", value="section:0001:risk"),
                content_hash="e" * 64,
                sensitivity=sensitivity,
                text_ref="f" * 64,
                chunk_config_hash="a" * 64,
            ),
        )

    def search(self, query: str, *, k: int, case_id: UUID) -> list[RetrievalHit]:
        self.calls += 1
        if self.exceptions:
            raise self.exceptions.pop(0)
        if self.results:
            result = self.results.pop(0)
            if result.status is NodeStatus.RETRYABLE_ERROR:
                raise RetryableSourceError(result)
        return [
            RetrievalHit(
                chunk_id=CHUNK_ID,
                case_id=case_id,
                artifact_id=ARTIFACT_ID,
                locator=SourceLocator(kind="sec_filing_section", value="section:0001:risk"),
                content_hash="e" * 64,
                sensitivity=SensitivityClass.PUBLIC,
                text_ref="f" * 64,
                chunk_config_hash="a" * 64,
                chunk_config_version="filing-html-chunker@1",
                model_id="fake-embedding@1",
                model_revision="fake",
                index_version="faiss-flat-ip@1",
                score=0.9,
            )
        ]


class FakeMetricService:
    def __init__(self) -> None:
        self.calls = 0

    def calculate(
        self,
        case_id: UUID,
        metric_name: str,
        *,
        evidence_fact_ids: list[UUID],
        as_of: datetime | None = None,
    ) -> MetricCalculationResult:
        self.calls += 1
        return MetricCalculationResult(
            status=MetricStatus.CALCULATED,
            metric_name=metric_name,
            formula_version="gross_margin@1",
            value=Decimal("0.400000"),
            display_value="40.0000%",
            unit="ratio",
            period="2025",
            input_evidence_ids=tuple(evidence_fact_ids[:2]),
            calculation_id=CALCULATION_ID,
        )


class FakeArtifactRepository:
    def __init__(self) -> None:
        self.saved: list[Artifact] = []

    def add(self, artifact: Artifact) -> None:
        if artifact.id not in [item.id for item in self.saved]:
            self.saved.append(artifact)

    def get(self, artifact_id: UUID) -> Artifact:
        for artifact in self.saved:
            if artifact.id == artifact_id:
                return artifact
        raise KeyError(f"artifact_not_found:{artifact_id}")


class FakeEvidenceRepository:
    def __init__(self) -> None:
        self.saved: list[EvidenceFact] = []

    def add(self, fact: EvidenceFact) -> None:
        if fact.id not in [item.id for item in self.saved]:
            self.saved.append(fact)

    def list_for_case(self, case_id: UUID) -> list[EvidenceFact]:
        return list(self.saved)


class FakeArtifactStore:
    def __init__(self) -> None:
        self.saved: dict[UUID, bytes] = {}
        self.conflicting_payload_for: UUID | None = None

    def put_bytes(
        self,
        payload: bytes,
        *,
        media_type: str,
        artifact_id: UUID | None = None,
        source_snapshot_hash: str | None = None,
        sensitivity: SensitivityClass = SensitivityClass.RESTRICTED,
    ) -> StoredArtifact:
        target = artifact_id or ARTIFACT_ID
        saved_payload = self.saved.get(target)
        payload_to_store = b"different bytes" if self.conflicting_payload_for == target else payload
        if saved_payload is not None and saved_payload != payload_to_store:
            raise ValueError("artifact_content_conflict")
        self.saved[target] = payload_to_store
        return StoredArtifact(
            artifact_id=target,
            content_hash=sha256(payload_to_store).hexdigest(),
            source_snapshot_hash=source_snapshot_hash or "c" * 64,
            storage_ref=f"artifact://{target}",
            media_type=media_type,
            byte_size=len(payload_to_store),
            stored_at=AS_OF,
            sensitivity=sensitivity,
        )

    def read_bytes(self, content_hash: str) -> bytes:
        raise NotImplementedError


class FakeAttemptGuard:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.deny: dict[tuple[str, int], str] = {}

    def check(
        self, *, node_name: str, attempt: int, state: dict[str, Any]
    ) -> NodeResult[None] | None:
        self.calls.append((node_name, attempt))
        denial = self.deny.get((node_name, attempt))
        if denial is None:
            return None
        return NodeResult(status=NodeStatus.BLOCKED, errors=[denial])

    def calls_by_node(self, node_name: str) -> list[int]:
        return [attempt for name, attempt in self.calls if name == node_name]


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.payloads: list[dict[str, Any]] = []

    def record(self, node_name: str, result: NodeResult[Any], state: dict[str, Any]) -> None:
        self.events.append(node_name)
        self.payloads.append(
            {
                "node_name": node_name,
                "status": result.status.value,
                "data_refs": list(result.data_refs),
                "warnings": list(result.warnings),
                "errors": list(result.errors),
                "case_id": state.get("case_id"),
            }
        )


class RetryableSourceError(Exception):
    def __init__(self, result: NodeResult[Any]) -> None:
        super().__init__(result.errors[0] if result.errors else "retryable")
        self.result = result


class FanoutBarrier:
    def __init__(self, *, expected: set[str]) -> None:
        self.expected = expected
        self.entered: set[str] = set()
        self._condition = threading.Condition()

    async def enter(self, name: str) -> None:
        await asyncio.to_thread(self.enter_sync, name)

    def enter_sync(self, name: str) -> None:
        with self._condition:
            self.entered.add(name)
            if self.entered >= self.expected:
                self._condition.notify_all()
                return
            if not self._condition.wait_for(lambda: self.entered >= self.expected, timeout=2):
                raise AssertionError(f"fanout barrier timed out after {name}")


class BarrierSecSource(FakeSecSource):
    def __init__(self, barrier: FanoutBarrier) -> None:
        super().__init__()
        self._barrier = barrier

    async def resolve_company(self, ticker_or_cik: str, *, as_of: date) -> CompanyIdentity:
        await self._barrier.enter("sec")
        return await super().resolve_company(ticker_or_cik, as_of=as_of)


class BarrierMarketSource(FakeMarketSource):
    def __init__(self, barrier: FanoutBarrier) -> None:
        super().__init__()
        self._barrier = barrier

    async def get_snapshot(self, ticker: str, *, as_of: date) -> MarketDataSnapshot:  # type: ignore[override]
        await self._barrier.enter("market")
        return super().get_snapshot(ticker, as_of=as_of)


class BarrierNewsSource(FakeNewsSource):
    def __init__(self, barrier: FanoutBarrier) -> None:
        super().__init__()
        self._barrier = barrier

    async def search(self, query: str, *, as_of: date) -> tuple[NewsItem, ...]:  # type: ignore[override]
        await self._barrier.enter("news")
        return super().search(query, as_of=as_of)


@dataclass
class LocalGraphDependencies(FakeDependencies):
    db: SQLiteDatabase | None = None


def _local_deps(*, db_path: Path, object_path: Path) -> LocalGraphDependencies:
    db = SQLiteDatabase(db_path)
    try:
        LocalCaseRepository(db).add(_case())
    except ValueError as exc:
        if str(exc) != "case_already_exists":
            raise
    return LocalGraphDependencies(
        sec=FakeSecSource(),
        market=FakeMarketSource(),
        news=FakeNewsSource(),
        retrieval=FakeRetrievalService(),
        metric_service=FakeMetricService(),
        audit=FakeAudit(),
        artifact_repository=LocalArtifactRepository(db),
        evidence_repository=LocalEvidenceRepository(db),
        artifact_store=LocalArtifactStore(object_path),
        guard=FakeAttemptGuard(),
        async_sleeper=_no_sleep,
        sync_sleeper=lambda _seconds: None,
        db=db,
    )


def _case() -> DueDiligenceCase:
    return DueDiligenceCase(
        case_id=CASE_UUID,
        mode=AnalysisMode.PUBLIC_COMPANY,
        entity_name="Apple Inc.",
        entity_identifier="AAPL",
        jurisdiction="US_SEC",
        scope=("public_company_stage1a",),
        as_of=AS_OF,
        base_currency="USD",
        privacy_policy="public-company-local@1",
        budget_policy="stage1a-local@1",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.PUBLIC,
        created_at=AS_OF,
        updated_at=AS_OF,
        workflow_version="public-company-local@1",
    )


def _filing(accession_number: str, artifact_id: UUID) -> FilingArtifact:
    payload = f"<html><body>{accession_number} filing</body></html>".encode()
    return FilingArtifact(
        accession_number=accession_number,
        content=payload,
        snapshot=SourceSnapshot(
            provider="sec",
            provider_version="fixture@1",
            source_url=f"https://example.test/{accession_number}",
            query={"accession_number": accession_number},
            as_of=AS_OF.date(),
            retrieved_at=AS_OF,
            published_at=AS_OF,
            content_hash=sha256(payload).hexdigest(),
            license_class=LicenseClass.PUBLIC_PRIMARY,
            media_type="text/html",
            storage_ref=f"fixture://{artifact_id}",
        ),
    )


def _fixture_json(relative_path: str) -> dict[str, Any]:
    path = Path("tests/fixtures/public_us_frozen_v1") / relative_path
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _companyfacts(*observations: dict[str, Any]) -> dict[str, Any]:
    facts: dict[str, Any] = {"us-gaap": {}}
    for observation in observations:
        concept = observation.pop("concept")
        unit = observation.pop("unit")
        facts["us-gaap"].setdefault(concept, {"units": {}})["units"].setdefault(unit, []).append(
            observation
        )
    return {"facts": facts}


def _xbrl_observation(
    concept: str,
    value: str,
    *,
    accession: str | None,
    fy: int = 2026,
    fp: str = "FY",
    unit: str = "USD",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "concept": concept,
        "unit": unit,
        "fy": fy,
        "fp": fp,
        "form": "10-K" if fp == "FY" else "10-Q",
        "filed": "2026-06-30",
        "start": "2025-07-01",
        "end": "2026-06-30",
        "val": value,
    }
    if accession is not None:
        result["accn"] = accession
    return result


async def _no_sleep(_seconds: float) -> None:
    return None


def _snapshot(
    provider: str,
    as_of: date,
    *,
    license_class: str = "public",
    storage_ref: str | None = None,
) -> SourceSnapshot:
    return SourceSnapshot(
        provider=provider,
        provider_version="fixture@1",
        source_url=f"https://example.test/{provider}",
        query={"ticker": "AAPL"},
        as_of=as_of,
        retrieved_at=AS_OF,
        published_at=AS_OF,
        content_hash=("1" if "000001" in provider or str(ARTIFACT_ID) in provider else "2") * 64,
        license_class=license_class,
        media_type="text/html",
        storage_ref=storage_ref or f"fixture://{provider}",
    )


def _fact_payload(
    fact_id: UUID,
    artifact_id: UUID,
    name: str,
    value: str,
    locator_kind: str,
    period: str,
    *,
    value_type: str = "decimal",
) -> dict[str, Any]:
    return {
        "id": str(fact_id),
        "artifact_id": str(artifact_id),
        "name": name,
        "value": value,
        "value_type": value_type,
        "unit": "USD" if value_type == "decimal" else None,
        "period": period if value_type == "decimal" else None,
        "locator": {"kind": locator_kind, "value": name, "artifact_id": str(artifact_id)},
        "sensitivity": "public",
        "confidence": "0.95",
        "source_priority": 1,
        "extraction_method": "fixture",
        "supporting_text_hash": "c" * 64,
        "source_freshness_at": AS_OF.isoformat(),
        "retrieved_at": AS_OF.isoformat(),
    }
