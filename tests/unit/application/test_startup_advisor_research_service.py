from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.openai import startup_web_research
from due_diligence_agent.adapters.openai.startup_web_research import (
    OpenAIStartupWebResearchAdapter,
)
from due_diligence_agent.adapters.startup.frozen_market_research import (
    FrozenStartupMarketResearchAdapter,
)
from due_diligence_agent.application.case_copilot_contracts import (
    PrepareResearchPlanRequest,
    QueueResearchJobRequest,
)
from due_diligence_agent.application.policies.budget import BudgetGuard
from due_diligence_agent.application.services.case_research_job_service import (
    CaseResearchJobService,
    StartupResearchPortBenchmarkProvider,
)
from due_diligence_agent.application.services.startup_advisor_research_service import (
    StartupAdvisorResearchService,
)
from due_diligence_agent.application.services.startup_market_research_service import (
    StartupMarketResearchService,
)
from due_diligence_agent.config import OpenAIStartupSettings
from due_diligence_agent.domain.startup.advisor import AdvisorAnswer, AdvisorQuestion
from due_diligence_agent.domain.startup.market import (
    StartupCompetitorCategory,
    StartupResearchPlan,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.ports.repositories import CaseResearchJob, CaseResearchPlan
from due_diligence_agent.ports.tracing import AuditEvent

_CASE_ID = UUID("00000000-0000-0000-0000-000000000301")
_RESEARCH_JOB_ID = UUID("00000000-0000-0000-0000-000000000302")
_NOW = datetime(2026, 8, 16, 9, 30, tzinfo=UTC)
_FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "startup_market_research_v1"


def test_public_research_requires_explicit_consent_before_provider_call() -> None:
    service, client, fallback, profiles, _live = _build_research_service()

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(
            answer_type="public_research",
            consent_public_research=False,
        ),
    )

    assert delta.status == "blocked"
    assert "соглас" in delta.summary_ru.casefold()
    assert client.calls == []
    assert fallback.calls == 0
    assert profiles.calls == 0


def test_internal_metric_question_never_routes_to_web_search() -> None:
    service, client, fallback, profiles, _live = _build_research_service()

    delta = service.research(
        _CASE_ID,
        _question("revenue_pricing"),
        AdvisorAnswer(
            answer_type="public_research",
            consent_public_research=True,
        ),
    )

    assert delta.status == "blocked"
    assert "внутрен" in delta.summary_ru.casefold()
    assert client.calls == []
    assert fallback.calls == 0
    assert profiles.calls == 0


def test_live_public_research_returns_bounded_cited_sources() -> None:
    model_text = "LUNA_SYNTHESIS_SENTINEL_NOT_A_SOURCE_FACT"
    service, client, fallback, _profiles, live = _build_research_service(
        response=_provider_response(source_count=7, text=model_text)
    )

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(
            answer_type="public_research",
            consent_public_research=True,
        ),
    )

    assert delta.status == "deferred"
    assert len(delta.source_ids) == 5
    assert delta.fallback_used is False
    assert delta.fail_reason_ru == "case_research_job_mutated_case"
    assert len(client.calls) == 1
    assert fallback.calls == 0
    assert live.last_snapshot is not None
    assert live.last_snapshot.provenance == "live_public_research"
    assert "live_public_research" in live.last_snapshot.labels
    assert "live_inference" in live.last_snapshot.labels
    assert all(
        source.status is StartupResearchSourceStatus.INFERENCE
        and source.source_mode is StartupResearchSourceMode.LIVE
        and source.provenance == "live_public_research:web_search:url_citation"
        and source.source_hash.startswith("sha256:")
        and source.confidence == Decimal("0.70")
        for source in live.last_snapshot.sources
    )
    assert model_text not in live.last_snapshot.canonical_json()


def test_consent_public_research_writes_same_case_safe_tool_boundary() -> None:
    audit = _RecordingAuditSpool()
    service, client, fallback, _profiles, _live = _build_research_service(
        response=_provider_response(source_count=2),
        service_audit_spool=audit,
    )

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(
            answer_type="public_research",
            consent_public_research=True,
        ),
    )

    assert delta.status == "deferred"
    assert len(client.calls) == 1
    assert fallback.calls == 0
    [event] = [item for item in audit.events if item.span_name == "startup.advisor_public_research"]
    assert event.run_id == f"startup-api-{_CASE_ID}"
    assert event.correlation_id == str(_CASE_ID)
    assert event.attributes == {
        "agent_role": "market",
        "attempt": 1,
        "case_id": str(_CASE_ID),
        "evidence_count": 2,
        "fallback_used": "none",
        "latency_ms": event.attributes["latency_ms"],
        "node_name": "advisor_public_research",
        "retry_count": 0,
        "status": "deferred",
        "timeout_ms": 15_000,
        "tool": "public_web_search",
    }
    assert isinstance(event.attributes["latency_ms"], int | float)
    assert event.attributes["latency_ms"] >= 0
    serialized = repr(event)
    assert "public customer segment" not in serialized
    assert "example.com" not in serialized


def test_live_request_is_one_call_three_queries_and_contains_only_public_fields() -> None:
    profile = _profile(include_hostile_private_fields=True)
    service, client, _fallback, _profiles, _live = _build_research_service(
        profile=profile,
        response=_provider_response(source_count=2),
    )
    sentinels = (
        "%PDF-RAW-DOCUMENT-SENTINEL",
        "founder-private-deck.pdf",
        "C:\\Users\\Akana\\private\\founder-deck.pdf",
        "PROMPT-SENTINEL",
        "founder.sentinel@example.com",
        "sk-" + "proj-PRIVATE-SENTINEL-1234567890",
        "MRR-PRIVATE-SENTINEL",
        "CUSTOMER-CONTRACT-SENTINEL",
    )

    delta = service.research(
        _CASE_ID,
        _question("gtm_channel", hostile=True),
        AdvisorAnswer(
            answer_type="public_research",
            value=" ".join(sentinels),
            consent_public_research=True,
        ),
    )

    assert delta.status == "deferred"
    assert len(client.calls) == 1
    request = client.calls[0]
    request_dump = json.dumps(request, ensure_ascii=False, sort_keys=True)
    assert all(sentinel not in request_dump for sentinel in sentinels)
    assert "public channels context for comparable startup markets" in request_dump
    request_text = cast(dict[str, Any], request["text"])
    text_format = cast(dict[str, Any], request_text["format"])
    assert request["tools"] == [{"type": "web_search"}]
    assert request["tool_choice"] == "required"
    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True
    assert request["model"] == "gpt-5.6-luna"
    assert request["store"] is False
    assert request["max_output_tokens"] == 3_000
    assert request["timeout"] == 60.0
    assert len(json.loads(str(request["input"]))["queries"]) <= 3
    schema = cast(dict[str, Any], text_format["schema"])
    assert schema["required"] == [
        "benchmark_candidates",
        "competitors",
        "market_assumptions",
        "market_sizing",
    ]
    properties = cast(dict[str, Any], schema["properties"])
    assert set(properties) == {
        "benchmark_candidates",
        "competitors",
        "market_assumptions",
        "market_sizing",
    }
    market_sizing_schema = cast(dict[str, Any], properties["market_sizing"])
    assert market_sizing_schema["type"] == ["object", "null"]
    competitors_schema = cast(dict[str, Any], properties["competitors"])
    competitor_items = cast(dict[str, Any], competitors_schema["items"])
    competitor_properties = cast(dict[str, Any], competitor_items["properties"])
    competitor_confidence_schema = cast(dict[str, Any], competitor_properties["confidence"])
    assert competitor_confidence_schema["pattern"] == r"^(?:0(?:\.\d+)?|1(?:\.0+)?)$"


def test_public_pricing_analogs_query_reaches_responses_without_private_values() -> None:
    client = _RecordingResponses(_provider_response(source_count=1))
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
    )
    service = CaseResearchJobService(
        case_repository=_CaseRepo(revision=1),
        plan_repository=_PlanRepo(),
        job_repository=_JobRepo(),
        public_benchmark_repository=None,
        scenario_repository=None,
        research_provider=StartupResearchPortBenchmarkProvider(live),
        acquisition_mode="live_public_research",
        clock=lambda: _NOW,
    )
    plan = service.prepare_plan(
        _CASE_ID,
        PrepareResearchPlanRequest(
            focus="public_pricing_analogs",
            intent="Prepare public pricing analog research.",
            expected_case_revision=1,
        ),
    )

    job = service.queue_job(
        _CASE_ID,
        QueueResearchJobRequest(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            expected_case_revision=1,
            idempotency_key="public-pricing-analogs-live-query",
            consent_public_research=True,
        ),
    )

    assert job.status == "completed"
    assert job.reason is None
    assert len(job.source_refs) == 1
    assert len(client.calls) == 1
    payload = json.loads(str(client.calls[0]["input"]))
    assert payload["queries"] == ["Казахстан CRM SaaS тарифы цена тенге в месяц"]
    serialized = " ".join(payload["queries"]).casefold()
    for forbidden in ("mrr", "arr", "revenue", "customer_count", "contract", "founder"):
        assert forbidden not in serialized


def test_live_public_research_span_is_allowed_by_real_jsonl_audit_spool() -> None:
    client = _RecordingResponses(_provider_response(source_count=1))
    audit_root = Path(".codex-tmp-live-public-research-audit") / uuid4().hex
    audit_spool = JsonlAuditSpool(audit_root, max_mb=1)
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        audit_spool=audit_spool,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=(
                "published KZT per month pricing analogs for comparable Kazakhstan B2B SaaS products",
            ),
            max_queries=1,
        )
    )

    assert len(client.calls) == 1
    assert snapshot.sources
    audit_path = audit_root / "2026" / "08" / "16" / f"startup-public-research-{_CASE_ID}.jsonl"
    lines = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [line["span_name"] for line in lines] == [
        "startup.public_research",
        "startup.public_research",
    ]
    assert [line["attributes"]["status"] for line in lines] == ["requested", "completed"]


def test_live_public_research_audit_proves_openai_web_search_usage_and_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RecordingResponses(_provider_response(source_count=1))
    audit = _RecordingAuditSpool()
    elapsed = iter((10.0, 10.125))
    monkeypatch.setattr(startup_web_research.time, "perf_counter", lambda: next(elapsed))
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        audit_spool=audit,
    )

    live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            research_job_id=_RESEARCH_JOB_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public market context for comparable startup markets",),
            max_queries=1,
        )
    )

    assert [event.attributes["tool"] for event in audit.events] == [
        "web_search",
        "web_search",
    ]
    completed = audit.events[-1]
    assert completed.span_name == "startup.public_research"
    assert completed.attributes["status"] == "completed"
    assert completed.attributes["provider"] == "openai"
    assert completed.attributes["request_id"] == str(_RESEARCH_JOB_ID)
    assert completed.correlation_id == f"research-job-{_RESEARCH_JOB_ID}"
    assert completed.attributes["tool_call_observed"] is True
    assert completed.attributes["latency_ms"] == 125
    assert completed.attributes["input_tokens"] == 100
    assert completed.attributes["output_tokens"] == 50
    assert completed.attributes["total_tokens"] == 150
    serialized = repr(audit.events)
    assert "public market context for comparable startup markets" not in serialized
    assert "example.com" not in serialized


def test_live_public_research_records_observed_usage_and_cost_for_langsmith(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RecordingResponses(_provider_response(source_count=1))
    recorder = _RecordingLLMCalls()
    elapsed = iter((30.0, 30.125, 30.125))
    monkeypatch.setattr(startup_web_research.time, "perf_counter", lambda: next(elapsed))
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        usage_cost_calculator=lambda usage: (
            Decimal(usage.input_tokens) * Decimal("1.00")
            + Decimal(usage.output_tokens) * Decimal("6.00")
        )
        / Decimal(1_000_000),
        llm_call_recorder=recorder,
    )

    live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            research_job_id=_RESEARCH_JOB_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public market context for comparable startup markets",),
            max_queries=1,
        )
    )

    assert recorder.records == [
        {
            "case_id": str(_CASE_ID),
            "run_id": f"startup-public-research-{_RESEARCH_JOB_ID}",
            "correlation_id": f"research-job-{_RESEARCH_JOB_ID}",
            "workflow_type": "startup",
            "request_id": str(_RESEARCH_JOB_ID),
            "node_name": "public_research",
            "agent_role": "market",
            "status": "success",
            "attempt": 1,
            "retry_count": 0,
            "provider": "openai",
            "model": "gpt-5.6-luna",
            "tool": "web_search",
            "query_count": 1,
            "source_count": 1,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "cost_usd": 0.0004,
            "schema_version": "startup_public_research_llm_span@1",
            "duration_ms": 125,
            "latency_ms": 125,
            "checkpoint_id": f"research-{_RESEARCH_JOB_ID}",
        }
    ]
    serialized = repr(recorder.records)
    assert "public market context for comparable startup markets" not in serialized
    assert "example.com" not in serialized


def test_invalid_public_research_still_records_billed_usage_and_cost() -> None:
    client = _RecordingResponses(_provider_response_without_tool_call(source_count=1))
    budget_guard = BudgetGuard(
        default_token_limit=20_000,
        default_usd_limit=Decimal("0.05"),
    )
    recorder = _RecordingLLMCalls()
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        budget_guard=budget_guard,
        usage_cost_calculator=lambda usage: Decimal(usage.total_tokens) / Decimal(1_000_000),
        llm_call_recorder=recorder,
    )

    with pytest.raises(RuntimeError, match="startup_public_research_invalid_output"):
        live.collect(
            StartupResearchPlan(
                case_id=_CASE_ID,
                research_job_id=_RESEARCH_JOB_ID,
                source_mode=StartupResearchSourceMode.LIVE,
                queries=("public market context for comparable startup markets",),
                max_queries=1,
            )
        )

    [usage_record] = budget_guard.usage_for_case(_CASE_ID)
    assert usage_record.tokens == 150
    assert usage_record.usd_cost == Decimal("0.00015")
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0
    assert len(recorder.records) == 1
    assert recorder.records[0]["status"] == "invalid"
    assert recorder.records[0]["error_code"] == "invalid_output"
    assert recorder.records[0]["total_tokens"] == 150
    assert recorder.records[0]["cost_usd"] == 0.00015


def test_live_public_research_rejects_citations_without_observed_web_search_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RecordingResponses(_provider_response_without_tool_call(source_count=1))
    audit = _RecordingAuditSpool()
    elapsed = iter((20.0, 20.25))
    monkeypatch.setattr(startup_web_research.time, "perf_counter", lambda: next(elapsed))
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        audit_spool=audit,
    )

    with pytest.raises(RuntimeError, match="startup_public_research_invalid_output"):
        live.collect(
            StartupResearchPlan(
                case_id=_CASE_ID,
                source_mode=StartupResearchSourceMode.LIVE,
                queries=("public market context for comparable startup markets",),
                max_queries=1,
            )
        )

    assert len(client.calls) == 1
    assert live.last_snapshot is None
    assert [event.attributes["status"] for event in audit.events] == ["requested", "failed"]
    failed = audit.events[-1]
    assert failed.attributes["failure_code"] == "invalid_output"
    assert failed.attributes["tool"] == "web_search"
    assert failed.attributes["tool_call_observed"] is False
    assert failed.attributes["latency_ms"] == 250
    assert failed.attributes["input_tokens"] == 100
    assert failed.attributes["output_tokens"] == 50
    assert failed.attributes["total_tokens"] == 150
    serialized = repr(audit.events)
    assert "public market context for comparable startup markets" not in serialized
    assert "example.com" not in serialized


@pytest.mark.parametrize("tool_status", ["failed", "incomplete"])
def test_live_public_research_rejects_failed_web_search_call_status(
    monkeypatch: pytest.MonkeyPatch,
    tool_status: str,
) -> None:
    client = _RecordingResponses(_provider_response(source_count=1, tool_status=tool_status))
    audit = _RecordingAuditSpool()
    elapsed = iter((20.0, 20.25))
    monkeypatch.setattr(startup_web_research.time, "perf_counter", lambda: next(elapsed))
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        audit_spool=audit,
    )

    with pytest.raises(RuntimeError, match="startup_public_research_invalid_output"):
        live.collect(
            StartupResearchPlan(
                case_id=_CASE_ID,
                source_mode=StartupResearchSourceMode.LIVE,
                queries=("public market context for comparable startup markets",),
                max_queries=1,
            )
        )

    assert len(client.calls) == 1
    assert live.last_snapshot is None
    assert [event.attributes["status"] for event in audit.events] == ["requested", "failed"]
    assert audit.events[-1].attributes["failure_code"] == "invalid_output"
    assert audit.events[-1].attributes["tool_call_observed"] is False


def test_live_public_research_extracts_only_cited_quantitative_benchmark_candidates() -> None:
    response = _provider_response(
        source_count=1,
        text=json.dumps(
            {
                "benchmark_candidates": [
                    {
                        "input_key": "arpa",
                        "source_url": "https://example.com/public-source-0",
                        "provenance": "public_benchmark",
                        "publisher": "Example Research",
                        "publication_date": "2026-08-01",
                        "as_of": "2026-08-01",
                        "source_class": "industry_report",
                        "confidence": "medium",
                        "value": None,
                        "range_low": "18500",
                        "range_high": "32500",
                        "unit": "KZT",
                        "period": "month",
                        "formula": "reported public KZT ARPA benchmark range",
                        "dependencies": ["public comparable companies"],
                        "validation_plan": "Use only as external context until case evidence confirms fit.",
                        "rationale": "Cited public range for comparable SaaS ARPA.",
                    },
                    {
                        "input_key": "arpa",
                        "source_url": "https://uncited.example.com/benchmark",
                        "provenance": "public_benchmark",
                        "publisher": "Uncited Research",
                        "publication_date": "2026-08-01",
                        "as_of": "2026-08-01",
                        "source_class": "industry_report",
                        "confidence": "medium",
                        "value": "999",
                        "range_low": None,
                        "range_high": None,
                        "unit": "KZT",
                        "period": "month",
                        "formula": "uncited value",
                        "dependencies": ["public comparable companies"],
                        "validation_plan": "Reject because source is not cited.",
                        "rationale": "Uncited provider claim.",
                    },
                    {
                        "input_key": "mrr",
                        "source_url": "https://example.com/public-source-0",
                        "provenance": "public_benchmark",
                        "publisher": "Example Research",
                        "publication_date": "2026-08-01",
                        "as_of": "2026-08-01",
                        "source_class": "industry_report",
                        "confidence": "medium",
                        "value": "1000",
                        "range_low": None,
                        "range_high": None,
                        "unit": "KZT",
                        "period": "month",
                        "formula": "private metric claim",
                        "dependencies": ["public comparable companies"],
                        "validation_plan": "Reject because MRR is private founder input.",
                        "rationale": "Private metric should not become public_benchmark.",
                    },
                ]
            },
            ensure_ascii=False,
        ),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public market context for comparable startup markets",),
            max_queries=1,
        )
    )

    assert len(snapshot.public_benchmark_candidates) == 1
    [candidate] = snapshot.public_benchmark_candidates
    assert candidate.input_key == "arpa"
    assert candidate.source_url == "https://example.com/public-source-0"
    assert candidate.value is None
    assert candidate.range_low == Decimal(18500)
    assert candidate.range_high == Decimal(32500)
    assert candidate.formula == "reported public KZT ARPA benchmark range"
    assert candidate.dependencies == ("public comparable companies",)
    assert candidate.source_ref == snapshot.sources[0].source_id


def test_live_public_research_omits_private_looking_cited_benchmark_text() -> None:
    response = _provider_response(
        source_count=2,
        text=json.dumps(
            {
                "benchmark_candidates": [
                    {
                        "input_key": "arpa",
                        "source_url": "https://example.com/public-source-1",
                        "provenance": "public_benchmark",
                        "publisher": "Example Research",
                        "publication_date": "2026-08-01",
                        "as_of": "2026-08-01",
                        "source_class": "industry_report",
                        "confidence": "medium",
                        "value": None,
                        "range_low": "18500",
                        "range_high": "32500",
                        "unit": "KZT",
                        "period": "month",
                        "formula": "reported public KZT ARPA benchmark range",
                        "dependencies": ["public comparable companies"],
                        "validation_plan": "Use only as external context until case evidence confirms fit.",
                        "rationale": "Cited public range for comparable SaaS ARPA.",
                    },
                    {
                        "input_key": "arpa",
                        "source_url": "https://example.com/public-source-0",
                        "provenance": "public_benchmark",
                        "publisher": "Founder private interview",
                        "publication_date": "2026-08-01",
                        "as_of": "2026-08-01",
                        "source_class": "private_contract_summary",
                        "confidence": "high",
                        "value": "999999",
                        "range_low": None,
                        "range_high": None,
                        "unit": "KZT",
                        "period": "month",
                        "formula": "Founder private MRR from customer contracts.",
                        "dependencies": ["founder ARR", "cash balance", "burn rate"],
                        "validation_plan": "Use founder private customer count.",
                        "rationale": "Private company revenue claim.",
                    },
                ],
                "competitors": [],
                "market_assumptions": [],
                "market_sizing": None,
            },
            ensure_ascii=False,
        ),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public market context for comparable startup markets",),
            max_queries=1,
        )
    )

    assert len(snapshot.public_benchmark_candidates) == 1
    [candidate] = snapshot.public_benchmark_candidates
    assert candidate.formula == "reported public KZT ARPA benchmark range"
    assert "private" not in snapshot.canonical_json().casefold()
    assert "mrr" not in snapshot.canonical_json().casefold()


def test_live_public_research_accepts_undated_cited_quantitative_benchmark_candidate() -> None:
    response = _provider_response(
        source_count=1,
        text=json.dumps(
            {
                "benchmark_candidates": [
                    {
                        "input_key": "monthly_price",
                        "source_url": "https://example.com/public-source-0",
                        "provenance": "public_benchmark",
                        "publisher": "Example Pricing Page",
                        "publication_date": "not stated",
                        "as_of": "2026-08-01",
                        "source_class": "pricing_page",
                        "confidence": "medium",
                        "value": "9000",
                        "range_low": None,
                        "range_high": None,
                        "unit": "KZT",
                        "period": "month",
                        "formula": "published KZT per month public pricing analog",
                        "dependencies": ["public pricing page"],
                        "validation_plan": "Use as market context; confirm fit against founder pricing.",
                        "rationale": "Cited public monthly price for a comparable SaaS product.",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=(
                "published KZT per month pricing analogs for comparable Kazakhstan B2B SaaS products",
            ),
            max_queries=1,
        )
    )

    [candidate] = snapshot.public_benchmark_candidates
    assert candidate.provenance == "public_benchmark"
    assert candidate.publication_date is None
    assert candidate.retrieval_date == _NOW.date()
    assert candidate.as_of.isoformat() == "2026-08-01"
    assert snapshot.sources[0].status is StartupResearchSourceStatus.INFERENCE
    assert 'publication_date":null' in candidate.model_dump_json()
    assert 'publication_date":"None"' not in candidate.model_dump_json()


def test_live_public_research_strips_provider_citation_urls_from_candidate_text() -> None:
    cited_url = "https://example.com/public-source-0"
    provider_url = f"{cited_url}?utm_source=openai"
    response = _provider_response(
        source_count=1,
        text=json.dumps(
            {
                "benchmark_candidates": [
                    {
                        "input_key": "monthly_price",
                        "source_url": cited_url,
                        "provenance": "public_benchmark",
                        "publisher": f"Example Pricing ([site]({provider_url}))",
                        "publication_date": None,
                        "as_of": "2026-08-01",
                        "source_class": "pricing_page",
                        "confidence": "medium",
                        "value": "9600",
                        "range_low": None,
                        "range_high": None,
                        "unit": "KZT",
                        "period": "month",
                        "formula": f"Published monthly price ([source]({provider_url})).",
                        "dependencies": [f"Public pricing page {provider_url}"],
                        "validation_plan": f"Confirm fit against the case using {provider_url}.",
                        "rationale": f"Cited public monthly price ([source]({provider_url})).",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("Казахстан CRM SaaS тарифы цена тенге в месяц",),
            max_queries=1,
        )
    )

    [candidate] = snapshot.public_benchmark_candidates
    serialized_text = " ".join(
        (
            candidate.publisher,
            candidate.formula,
            *candidate.dependencies,
            candidate.validation_plan,
            candidate.rationale,
        )
    )
    assert "http" not in serialized_text
    assert "utm_source" not in serialized_text
    assert candidate.source_url == cited_url


def test_live_public_research_extracts_only_cited_market_context_snapshot_items() -> None:
    response = _provider_response(
        source_count=2,
        text=json.dumps(
            {
                "benchmark_candidates": [
                    {
                        "input_key": "arpa",
                        "source_url": "https://example.com/public-source-0",
                        "provenance": "public_benchmark",
                        "publisher": "Example Research",
                        "publication_date": "2026-08-01",
                        "as_of": "2026-08-01",
                        "source_class": "industry_report",
                        "confidence": "medium",
                        "value": None,
                        "range_low": "18500",
                        "range_high": "32500",
                        "unit": "KZT",
                        "period": "month",
                        "formula": "reported public KZT ARPA benchmark range",
                        "dependencies": ["public comparable companies"],
                        "validation_plan": "Use only as external context until case evidence confirms fit.",
                        "rationale": "Cited public range for comparable SaaS ARPA.",
                    }
                ],
                "competitors": [
                    {
                        "name": "Public CRM Suite",
                        "category": "direct",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "0.74",
                    },
                    {
                        "name": "Uncited CRM",
                        "category": "direct",
                        "source_url": "https://uncited.example.com/competitor",
                        "confidence": "0.80",
                    },
                    {
                        "name": "Private MRR Analytics",
                        "category": "direct",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "0.80",
                    },
                ],
                "market_assumptions": [
                    {
                        "text": "Kazakhstan SMEs compare SaaS tools against manual spreadsheet workflows.",
                        "source_url": "https://example.com/public-source-1",
                        "confidence": "0.68",
                        "as_of": "2026-08-01",
                    },
                    {
                        "text": "Founder MRR is confirmed by private customer contracts.",
                        "source_url": "https://example.com/public-source-1",
                        "confidence": "0.90",
                        "as_of": "2026-08-01",
                    },
                ],
                "market_sizing": {
                    "tam": {
                        "value": "1000000",
                        "unit": "users",
                        "currency": "kzt",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "0.62",
                        "as_of": "2026-08-01",
                        "formula_version": "live_public_research_tam_sam_som@1",
                    },
                    "sam": {
                        "value": "250000",
                        "unit": "users",
                        "currency": "kzt",
                        "source_url": "https://example.com/public-source-1",
                        "confidence": "0.58",
                        "as_of": "2026-08-01",
                        "formula_version": "live_public_research_tam_sam_som@1",
                    },
                    "som": {
                        "value": "25000",
                        "unit": "users",
                        "currency": "kzt",
                        "source_url": "https://example.com/public-source-1",
                        "confidence": "0.52",
                        "as_of": "2026-08-01",
                        "formula_version": "live_public_research_tam_sam_som@1",
                    },
                },
            },
            ensure_ascii=False,
        ),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public market competitors and TAM SAM SOM for Kazakhstan SaaS",),
            max_queries=1,
        )
    )

    source_by_url = {_normalized_source_url(source): source for source in snapshot.sources}
    assert [competitor.name for competitor in snapshot.competitors] == ["Public CRM Suite"]
    assert snapshot.competitors[0].category is StartupCompetitorCategory.DIRECT
    assert snapshot.competitors[0].status is StartupResearchSourceStatus.INFERENCE
    assert snapshot.competitors[0].source_ids == (
        source_by_url["https://example.com/public-source-0"].source_id,
    )
    assert [assumption.text for assumption in snapshot.assumptions] == [
        "Kazakhstan SMEs compare SaaS tools against manual spreadsheet workflows."
    ]
    assert snapshot.assumptions[0].source_ids == (
        source_by_url["https://example.com/public-source-1"].source_id,
    )
    assert snapshot.assumptions[0].status is StartupResearchSourceStatus.INFERENCE
    assert snapshot.sizing is not None
    assert snapshot.sizing.tam.value == Decimal(1000000)
    assert snapshot.sizing.sam.value == Decimal(250000)
    assert snapshot.sizing.som.value == Decimal(25000)
    assert snapshot.sizing.tam.level is StartupResearchSourceStatus.INFERENCE
    assert snapshot.sizing.tam.source_refs == (
        source_by_url["https://example.com/public-source-0"].source_id,
    )
    assert snapshot.sizing.tam.assumption_refs == (snapshot.assumptions[0].assumption_id,)
    assert len(snapshot.public_benchmark_candidates) == 1
    assert snapshot.public_benchmark_candidates[0].input_key == "arpa"
    assert snapshot.public_benchmark_candidates[0].source_ref == (
        source_by_url["https://example.com/public-source-0"].source_id
    )
    assert not any(
        source.status is StartupResearchSourceStatus.SOURCE_FACT for source in snapshot.sources
    )
    assert not any(
        competitor.status is StartupResearchSourceStatus.SOURCE_FACT
        for competitor in snapshot.competitors
    )
    assert not any(
        assumption.status is StartupResearchSourceStatus.SOURCE_FACT
        for assumption in snapshot.assumptions
    )
    assert "Private MRR Analytics" not in snapshot.canonical_json()
    assert "Founder MRR" not in snapshot.canonical_json()


def test_live_public_research_keeps_valid_benchmark_when_rich_confidence_is_malformed() -> None:
    response = _provider_response(
        source_count=1,
        text=json.dumps(
            {
                "benchmark_candidates": [
                    {
                        "input_key": "monthly_price",
                        "source_url": "https://example.com/public-source-0",
                        "provenance": "public_benchmark",
                        "publisher": "Example Pricing Page",
                        "publication_date": None,
                        "as_of": "2026-08-01",
                        "source_class": "pricing_page",
                        "confidence": "medium",
                        "value": "9600",
                        "range_low": None,
                        "range_high": None,
                        "unit": "KZT",
                        "period": "month",
                        "formula": "Published monthly price.",
                        "dependencies": ["Public pricing page"],
                        "validation_plan": "Confirm fit against the case.",
                        "rationale": "Cited public monthly price.",
                    }
                ],
                "competitors": [
                    {
                        "name": "Malformed Confidence CRM",
                        "category": "direct",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "medium",
                    }
                ],
                "market_assumptions": [
                    {
                        "text": "Malformed confidence should be omitted item-locally.",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "high",
                        "as_of": "2026-08-01",
                    }
                ],
                "market_sizing": {
                    "tam": {
                        "value": "1000000",
                        "unit": "users",
                        "currency": "kzt",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "medium",
                        "as_of": "2026-08-01",
                        "formula_version": "live_public_research_tam_sam_som@1",
                    },
                    "sam": {
                        "value": "250000",
                        "unit": "users",
                        "currency": "kzt",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "medium",
                        "as_of": "2026-08-01",
                        "formula_version": "live_public_research_tam_sam_som@1",
                    },
                    "som": {
                        "value": "25000",
                        "unit": "users",
                        "currency": "kzt",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "medium",
                        "as_of": "2026-08-01",
                        "formula_version": "live_public_research_tam_sam_som@1",
                    },
                },
            },
            ensure_ascii=False,
        ),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public pricing and malformed rich market context",),
            max_queries=1,
        )
    )

    assert len(snapshot.public_benchmark_candidates) == 1
    assert snapshot.sources
    assert snapshot.competitors == ()
    assert snapshot.assumptions == ()
    assert snapshot.sizing is None


def test_live_public_research_omits_uncited_or_ungrounded_market_sizing() -> None:
    response = _provider_response(
        source_count=1,
        text=json.dumps(
            {
                "benchmark_candidates": [],
                "competitors": [],
                "market_assumptions": [],
                "market_sizing": {
                    "tam": {
                        "value": "1000000",
                        "unit": "users",
                        "currency": "kzt",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "0.62",
                        "as_of": "2026-08-01",
                        "formula_version": "live_public_research_tam_sam_som@1",
                    },
                    "sam": {
                        "value": "250000",
                        "unit": "users",
                        "currency": "kzt",
                        "source_url": "https://uncited.example.com/market-size",
                        "confidence": "0.58",
                        "as_of": "2026-08-01",
                        "formula_version": "live_public_research_tam_sam_som@1",
                    },
                    "som": {
                        "value": "25000",
                        "unit": "users",
                        "currency": "kzt",
                        "source_url": "https://example.com/public-source-0",
                        "confidence": "0.52",
                        "as_of": "2026-08-01",
                        "formula_version": "live_public_research_tam_sam_som@1",
                    },
                },
            },
            ensure_ascii=False,
        ),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public market sizing context for comparable startup markets",),
            max_queries=1,
        )
    )

    assert snapshot.sizing is None


def test_live_public_research_rejects_incomplete_truncated_json_instead_of_no_candidates() -> None:
    truncated = (
        '{"benchmark_candidates":[{"input_key":"arpa",'
        '"source_url":"https://example.com/public-source-0",'
        '"provenance":"public_benchmark","publisher":"Example Research",'
        '"publication_date"'
    )
    response = cast(Any, _provider_response(source_count=1, text=truncated))
    response.status = "incomplete"
    response.incomplete_details = SimpleNamespace(reason="max_output_tokens")
    client = _RecordingResponses(response)
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
    )

    with pytest.raises(RuntimeError, match="startup_public_research_invalid_output"):
        live.collect(
            StartupResearchPlan(
                case_id=_CASE_ID,
                source_mode=StartupResearchSourceMode.LIVE,
                queries=(
                    "published KZT per month pricing analogs for comparable Kazakhstan B2B SaaS products",
                ),
                max_queries=1,
            )
        )

    assert len(client.calls) == 1


def test_live_public_research_rejects_currency_or_period_that_would_corrupt_kzt_metrics() -> None:
    response = _provider_response(
        source_count=1,
        text=json.dumps(
            {
                "benchmark_candidates": [
                    {
                        "input_key": "acquisition_spend",
                        "source_url": "https://example.com/public-source-0",
                        "provenance": "public_benchmark",
                        "publisher": "Example Research",
                        "publication_date": "2026-08-01",
                        "as_of": "2026-08-01",
                        "source_class": "industry_report",
                        "confidence": "medium",
                        "value": "1000",
                        "range_low": None,
                        "range_high": None,
                        "unit": "USD",
                        "period": "year",
                        "formula": "reported public CAC without KZT conversion",
                        "dependencies": ["public comparable companies"],
                        "validation_plan": "Reject until KZT monthly conversion is cited.",
                        "rationale": "Wrong unit and period for scenario calculations.",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public unit economics benchmarks for comparable startup business models",),
            max_queries=1,
        )
    )

    assert snapshot.public_benchmark_candidates == ()


def test_live_public_research_accepts_action_sources_when_annotations_are_absent() -> None:
    response = SimpleNamespace(
        output=(
            SimpleNamespace(
                type="web_search_call",
                action={
                    "type": "search",
                    "query": "public market query",
                    "sources": [
                        {
                            "url": "https://example.com/action-source",
                            "title": "Action Source",
                            "published_date": "2026-08-01",
                        }
                    ],
                },
            ),
            SimpleNamespace(
                type="message",
                content=(
                    SimpleNamespace(
                        type="output_text",
                        text=json.dumps(
                            {
                                "benchmark_candidates": [
                                    {
                                        "input_key": "arpa",
                                        "source_url": "https://example.com/action-source",
                                        "provenance": "public_benchmark",
                                        "publisher": "Action Source",
                                        "publication_date": "2026-08-01",
                                        "as_of": "2026-08-01",
                                        "source_class": "industry_report",
                                        "confidence": "medium",
                                        "value": None,
                                        "range_low": "18500",
                                        "range_high": "32500",
                                        "unit": "KZT",
                                        "period": "month",
                                        "formula": "reported public KZT ARPA benchmark range",
                                        "dependencies": ["public comparable companies"],
                                        "validation_plan": (
                                            "Use only as external context until case evidence confirms fit."
                                        ),
                                        "rationale": "Cited public range for comparable SaaS ARPA.",
                                    }
                                ]
                            },
                            ensure_ascii=False,
                        ),
                        annotations=(),
                    ),
                ),
            ),
        ),
        usage=SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=150),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public market context for comparable startup markets",),
            max_queries=1,
        )
    )

    assert [str(source.source_url) for source in snapshot.sources] == [
        "https://example.com/action-source"
    ]
    assert len(snapshot.public_benchmark_candidates) == 1


@pytest.mark.parametrize("action_type", ["open_page", "find_in_page"])
def test_live_public_research_accepts_public_action_url_when_annotations_and_sources_are_absent(
    action_type: str,
) -> None:
    action_url = "https://example.com/action-page"
    response = SimpleNamespace(
        output=(
            SimpleNamespace(
                type="web_search_call",
                status="completed",
                action=SimpleNamespace(
                    type=action_type,
                    url=action_url,
                ),
            ),
            SimpleNamespace(
                type="message",
                content=(
                    SimpleNamespace(
                        type="output_text",
                        text=json.dumps(
                            {
                                "benchmark_candidates": [
                                    {
                                        "input_key": "arpa",
                                        "source_url": action_url,
                                        "provenance": "public_benchmark",
                                        "publisher": "Action Page",
                                        "publication_date": "2026-08-01",
                                        "as_of": "2026-08-01",
                                        "source_class": "industry_report",
                                        "confidence": "medium",
                                        "value": None,
                                        "range_low": "18500",
                                        "range_high": "32500",
                                        "unit": "KZT",
                                        "period": "month",
                                        "formula": "reported public KZT ARPA benchmark range",
                                        "dependencies": ["public comparable companies"],
                                        "validation_plan": (
                                            "Use only as external context until case evidence confirms fit."
                                        ),
                                        "rationale": "Cited public range for comparable SaaS ARPA.",
                                    }
                                ]
                            },
                            ensure_ascii=False,
                        ),
                        annotations=(),
                    ),
                ),
            ),
        ),
        usage=SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=150),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=_RecordingResponses(response),
        clock=lambda: _NOW,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public market context for comparable startup markets",),
            max_queries=1,
        )
    )

    assert [str(source.source_url) for source in snapshot.sources] == [action_url]
    assert len(snapshot.public_benchmark_candidates) == 1


def test_advisor_public_research_uses_durable_case_research_job_flow_not_live_side_path() -> None:
    profiles = _ProfileRepository(_profile())
    plans = _PlanRepo()
    jobs = _JobRepo()
    provider = _MixedBenchmarkProvider()
    direct_live = _RaisingResearchPort(RuntimeError("direct live side path called"))
    service = StartupAdvisorResearchService(
        profile_repository=cast(Any, profiles),
        market_research_service=StartupMarketResearchService(clock=lambda: _NOW),
        live_research_port=direct_live,
        fallback_research_port=_EmptyResearchPort(),
        case_research_service=CaseResearchJobService(
            case_repository=_CaseRepo(revision=1),
            plan_repository=plans,
            job_repository=jobs,
            public_benchmark_repository=None,
            scenario_repository=None,
            research_provider=provider,
            acquisition_mode="live_public_research",
            clock=lambda: _NOW,
        ),
    )

    answer = AdvisorAnswer(answer_type="public_research", consent_public_research=True)
    first = service.research(_CASE_ID, _question("icp"), answer)
    replay = service.research(_CASE_ID, _question("icp"), answer)

    assert direct_live.calls == 0
    assert provider.calls == 1
    assert first == replay
    assert first.status == "partial"
    assert first.fallback_used is False
    assert first.source_ids == ()
    [plan] = tuple(plans.records.values())
    assert plan.plan_hash
    assert plan.expires_at > plan.created_at
    [terminal_job] = tuple(jobs.records.values())
    idempotency_key = idempotency_key_for_test(_CASE_ID, _question("icp"), 1)
    running_job = jobs.idempotency[idempotency_key]
    assert jobs.idempotency[f"{idempotency_key}:result"].model_dump() == terminal_job.model_dump()
    assert running_job.status == "running"
    assert terminal_job.status == "partial"
    assert terminal_job.plan_id == plan.plan_id
    assert terminal_job.plan_hash == plan.plan_hash
    assert len(terminal_job.accepted_entries) == 1
    assert len(terminal_job.rejected_entries) == 1
    assert terminal_job.rejected_entries[0].reason_code == "invalid_benchmark_entry"

    profiles.profile = _profile(data_revision=2)
    case_service = cast(Any, service._case_research_service)
    case_service._cases.revision = 2
    revised = service.research(_CASE_ID, _question("icp"), answer)
    assert revised.status == "partial"
    assert provider.calls == 2
    assert len(plans.records) == 2


def test_direct_live_plan_drops_private_queries_before_one_provider_call() -> None:
    client = _RecordingResponses(_provider_response(source_count=1))
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
    )
    sentinels = (
        "MRR 9000 revenue pricing board-pack.xlsx founder-deck.pdf finance-internal.docx",
        "ARR customers contracts cap table client-counts.csv cap-table.pptx",
    )

    live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=(sentinels[0], "public competitor landscape Kazakhstan", sentinels[1]),
            max_queries=3,
        )
    )

    assert len(client.calls) == 1
    request_dump = json.dumps(client.calls[0], ensure_ascii=False, sort_keys=True)
    assert all(sentinel not in request_dump for sentinel in sentinels)
    assert "public competitor landscape Kazakhstan" in request_dump


def test_openai_public_research_port_builder_is_shared_by_advisor_and_case_copilot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.bootstrap.container import build_openai_startup_research_port

    captured: dict[str, Any] = {}
    fake_port = object()

    class _FakeSecret:
        def get_secret_value(self) -> str:
            return "test-api-key"

    def _fake_from_openai(**kwargs: Any) -> object:
        captured.update(kwargs)
        return fake_port

    monkeypatch.setattr(
        startup_web_research.OpenAIStartupWebResearchAdapter,
        "from_openai",
        _fake_from_openai,
    )
    settings = SimpleNamespace(
        openai_api_key=_FakeSecret(),
        max_input_tokens=200,
        max_output_tokens=100,
        per_case_usd_cap="0.01",
        input_usd_per_million_tokens=Decimal("1.00"),
        output_usd_per_million_tokens=Decimal("6.00"),
    )
    repositories = SimpleNamespace(
        database=SimpleNamespace(path=Path(".tmp-task6-shared-port") / "metadata.sqlite3")
    )
    recorder = _RecordingLLMCalls()

    port = build_openai_startup_research_port(
        settings=cast(Any, settings),
        repositories=cast(Any, repositories),
        audit_spool=cast(Any, _RecordingAuditSpool()),
        clock=lambda: _NOW,
        llm_call_recorder=recorder,
    )

    assert port is fake_port
    assert captured["api_key"] == "test-api-key"
    assert captured["clock"]() == _NOW
    assert captured["budget_guard"].persistence_path.name == (
        "startup-openai-public-research-budget.sqlite3"
    )
    assert captured["budget_guard"].default_token_limit == 20_000
    assert captured["llm_call_recorder"] is recorder
    usage_cost_calculator = cast(Any, captured["usage_cost_calculator"])
    assert usage_cost_calculator(
        SimpleNamespace(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
        )
    ) == Decimal("7.00")


def test_openai_advisor_builder_forwards_llm_call_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.bootstrap import container

    captured: dict[str, Any] = {}
    recorder = _RecordingLLMCalls()

    def _fake_port_builder(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(container, "build_openai_startup_research_port", _fake_port_builder)
    monkeypatch.setattr(
        container,
        "_build_case_research_job_service_for_advisor",
        lambda **_kwargs: None,
    )

    service = container.build_openai_startup_advisor_research_service(
        settings=cast(Any, SimpleNamespace()),
        repositories=cast(
            Any,
            SimpleNamespace(startup_profile_repository=_ProfileRepository(_profile())),
        ),
        audit_spool=cast(Any, _RecordingAuditSpool()),
        clock=lambda: _NOW,
        llm_call_recorder=recorder,
    )

    assert isinstance(service, StartupAdvisorResearchService)
    assert captured["llm_call_recorder"] is recorder


def test_search_outage_uses_cached_fallback_without_breaking_case() -> None:
    audit = _RecordingAuditSpool()
    provider_detail = "founder.failure@example.com " + "sk-" + "proj-FAILURE-1234567890"
    service, client, fallback, _profiles, _live = _build_research_service(
        provider_error=TimeoutError(provider_detail),
        audit_spool=audit,
    )

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(
            answer_type="public_research",
            consent_public_research=True,
        ),
    )

    assert delta.status == "deferred"
    assert delta.fallback_used is False
    assert delta.source_ids == ()
    assert delta.fail_reason_ru == "provider_failed"
    assert "secret" not in (delta.fail_reason_ru or "").casefold()
    assert len(client.calls) == 2
    assert fallback.calls == 0
    assert audit.events[-1].attributes["status"] == "failed"
    assert audit.events[-1].attributes["failure_code"] == "provider_timeout"
    assert provider_detail not in repr(audit.events)


def test_openai_sdk_timeout_maps_to_stable_provider_timeout_and_releases_budget() -> None:
    class APITimeoutError(Exception):
        pass

    APITimeoutError.__module__ = "openai"
    provider_detail = "founder.failure@example.com " + "sk-" + "proj-FAILURE-1234567890"
    audit = _RecordingAuditSpool()
    budget_guard = BudgetGuard(
        default_token_limit=20_000,
        default_usd_limit=Decimal("0.05"),
    )
    client = _RecordingResponses(
        _provider_response(source_count=1),
        error=APITimeoutError(provider_detail),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        budget_guard=budget_guard,
        audit_spool=audit,
    )

    with pytest.raises(RuntimeError, match="startup_public_research_timeout") as exc_info:
        live.collect(
            StartupResearchPlan(
                case_id=_CASE_ID,
                source_mode=StartupResearchSourceMode.LIVE,
                queries=("public market context for comparable startup markets",),
                max_queries=1,
            )
        )

    assert str(exc_info.value) == "startup_public_research_timeout"
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0
    assert len(client.calls) == 2
    assert audit.events[-1].attributes["status"] == "failed"
    assert audit.events[-1].attributes["failure_code"] == "provider_timeout"
    assert audit.events[-1].attributes["attempt"] == 2
    assert audit.events[-1].attributes["retry_count"] == 1
    assert provider_detail not in repr(audit.events)


@pytest.mark.parametrize(
    "provider_error",
    [
        TimeoutError("temporary timeout with " + "sk-" + "proj-SECRET"),
        type(
            "APIConnectionError",
            (Exception,),
            {"__module__": "openai"},
        )("network down"),
        type(
            "RateLimitError",
            (Exception,),
            {"__module__": "openai", "status_code": 429},
        )("rate limited"),
        type(
            "InternalServerError",
            (Exception,),
            {"__module__": "openai", "status_code": 503},
        )("server unavailable"),
    ],
)
def test_startup_public_research_retries_transient_provider_error_once_and_succeeds(
    provider_error: Exception,
) -> None:
    audit = _RecordingAuditSpool()
    budget_guard = BudgetGuard(
        default_token_limit=20_000,
        default_usd_limit=Decimal("0.05"),
    )
    client = _SequencedResponses(
        provider_error,
        _provider_response(source_count=1),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        budget_guard=budget_guard,
        audit_spool=audit,
        retry_sleep=lambda _delay: None,
        retry_jitter=lambda _start, _end: 0.0,
    )

    snapshot = live.collect(
        StartupResearchPlan(
            case_id=_CASE_ID,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("public market context for comparable startup markets",),
            max_queries=1,
        )
    )

    assert len(client.calls) == 2
    assert len(snapshot.sources) == 1
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0
    assert [event.attributes["status"] for event in audit.events] == [
        "requested",
        "requested",
        "completed",
    ]
    assert [event.attributes["attempt"] for event in audit.events] == [1, 2, 2]
    assert [event.attributes["retry_count"] for event in audit.events] == [0, 1, 1]
    assert "sk-" + "proj-SECRET" not in repr(audit.events)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
def test_startup_public_research_does_not_retry_non_transient_provider_errors(
    status_code: int,
) -> None:
    provider_error = type(
        "BadRequestError",
        (Exception,),
        {"__module__": "openai", "status_code": status_code},
    )("non retryable provider error " + "sk-" + "proj-SECRET")
    audit = _RecordingAuditSpool()
    budget_guard = BudgetGuard(
        default_token_limit=20_000,
        default_usd_limit=Decimal("0.05"),
    )
    client = _SequencedResponses(
        provider_error,
        _provider_response(source_count=1),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        budget_guard=budget_guard,
        audit_spool=audit,
        retry_sleep=lambda _delay: None,
        retry_jitter=lambda _start, _end: 0.0,
    )

    with pytest.raises(RuntimeError, match="startup_public_research_unavailable"):
        live.collect(
            StartupResearchPlan(
                case_id=_CASE_ID,
                source_mode=StartupResearchSourceMode.LIVE,
                queries=("public market context for comparable startup markets",),
                max_queries=1,
            )
        )

    assert len(client.calls) == 1
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0
    assert audit.events[-1].attributes["status"] == "failed"
    assert audit.events[-1].attributes["failure_code"] == "provider_unavailable"
    assert audit.events[-1].attributes["attempt"] == 1
    assert audit.events[-1].attributes["retry_count"] == 0
    assert "sk-" + "proj-SECRET" not in repr(audit.events)


def test_startup_public_research_does_not_retry_invalid_provider_output() -> None:
    audit = _RecordingAuditSpool()
    budget_guard = BudgetGuard(
        default_token_limit=20_000,
        default_usd_limit=Decimal("0.05"),
    )
    client = _SequencedResponses(
        _provider_response(
            source_count=0,
            text="INVALID_OUTPUT_SECRET " + "sk-" + "proj-SECRET",
        ),
        _provider_response(source_count=1),
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        budget_guard=budget_guard,
        audit_spool=audit,
        retry_sleep=lambda _delay: None,
        retry_jitter=lambda _start, _end: 0.0,
    )

    with pytest.raises(RuntimeError, match="startup_public_research_invalid_output"):
        live.collect(
            StartupResearchPlan(
                case_id=_CASE_ID,
                source_mode=StartupResearchSourceMode.LIVE,
                queries=("public market context for comparable startup markets",),
                max_queries=1,
            )
        )

    assert len(client.calls) == 1
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0
    assert audit.events[-1].attributes["failure_code"] == "invalid_output"
    assert audit.events[-1].attributes["attempt"] == 1
    assert audit.events[-1].attributes["retry_count"] == 0
    assert "sk-" + "proj-SECRET" not in repr(audit.events)


def test_fallback_exception_returns_truthful_deferred_delta() -> None:
    fallback = _RaisingResearchPort(RuntimeError("private fallback detail"))
    service, _client, returned_fallback, _profiles, _live = _build_research_service(
        provider_error=TimeoutError("provider unavailable"),
        fallback_port=fallback,
    )

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(answer_type="public_research", consent_public_research=True),
    )

    assert delta.status == "deferred"
    assert delta.fallback_used is False
    assert delta.source_ids == ()
    assert "сохран" not in delta.summary_ru.casefold()
    assert "private" not in repr(delta).casefold()
    assert returned_fallback.calls == 0


def test_empty_fallback_returns_truthful_deferred_delta() -> None:
    fallback = _EmptyResearchPort()
    service, _client, returned_fallback, _profiles, _live = _build_research_service(
        provider_error=TimeoutError("provider unavailable"),
        fallback_port=fallback,
    )

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(answer_type="public_research", consent_public_research=True),
    )

    assert delta.status == "deferred"
    assert delta.fallback_used is False
    assert delta.source_ids == ()
    assert returned_fallback.calls == 0


def test_budget_exceeded_uses_cached_fallback_and_writes_safe_failure_audit() -> None:
    audit = _RecordingAuditSpool()
    service, client, fallback, _profiles, _live = _build_research_service(
        budget_guard=BudgetGuard(
            default_token_limit=0,
            default_usd_limit=Decimal(0),
        ),
        audit_spool=audit,
    )

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(answer_type="public_research", consent_public_research=True),
    )

    assert delta.status == "deferred"
    assert delta.fallback_used is False
    assert delta.source_ids == ()
    assert client.calls == []
    assert fallback.calls == 0
    assert audit.events[-1].attributes["status"] == "failed"
    assert audit.events[-1].attributes["failure_code"] == "budget_exceeded"


def test_zero_citation_provider_result_uses_fallback_and_audits_invalid_output() -> None:
    audit = _RecordingAuditSpool()
    model_text = "ZERO_CITATION_LUNA_TEXT_WITHOUT_SOURCE_FACT"
    service, client, fallback, _profiles, live = _build_research_service(
        response=_provider_response(source_count=0, text=model_text),
        audit_spool=audit,
    )

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(answer_type="public_research", consent_public_research=True),
    )

    assert delta.status == "deferred"
    assert delta.fallback_used is False
    assert len(client.calls) == 1
    assert fallback.calls == 0
    assert live.last_snapshot is None
    assert audit.events[-1].attributes["status"] == "failed"
    assert audit.events[-1].attributes["failure_code"] == "invalid_output"
    assert model_text not in repr(audit.events)


def test_opt_in_openai_construction_disables_sdk_retries_and_uses_bounded_web_search_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_calls: list[dict[str, object]] = []
    client = _RecordingResponses(_provider_response(source_count=1))

    class FakeOpenAIModule:
        @staticmethod
        def OpenAI(**kwargs: object) -> object:
            constructor_calls.append(kwargs)
            return SimpleNamespace(responses=client)

    monkeypatch.setattr(
        cast(Any, startup_web_research).importlib,
        "import_module",
        lambda module_name: FakeOpenAIModule if module_name == "openai" else None,
    )

    OpenAIStartupWebResearchAdapter.from_openai(
        api_key="test-only-not-a-real-key",
        budget_guard=BudgetGuard(
            default_token_limit=3_000,
            default_usd_limit=Decimal("0.05"),
        ),
        audit_spool=_RecordingAuditSpool(),
        clock=lambda: _NOW,
    )

    assert constructor_calls == [
        {
            "api_key": "test-only-not-a-real-key",
            "timeout": 60.0,
            "max_retries": 0,
        }
    ]


def test_missing_key_container_composition_returns_truthful_deferred_without_fallback_success() -> (
    None
):
    from due_diligence_agent.bootstrap.container import (
        build_openai_startup_advisor_research_service,
    )

    profiles = _ProfileRepository(_profile())
    repositories = SimpleNamespace(startup_profile_repository=profiles)
    audit = _RecordingAuditSpool()
    service = build_openai_startup_advisor_research_service(
        settings=cast(Any, OpenAIStartupSettings)(openai_api_key=None, _env_file=None),
        repositories=cast(Any, repositories),
        audit_spool=cast(Any, audit),
        clock=lambda: _NOW,
    )

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(answer_type="public_research", consent_public_research=True),
    )

    assert delta.status == "deferred"
    assert delta.fallback_used is False
    assert delta.source_ids == ()
    [tool_event] = [
        event for event in audit.events if event.span_name == "startup.advisor_public_research"
    ]
    assert tool_event.run_id == f"startup-api-{_CASE_ID}"
    assert tool_event.attributes["status"] == "deferred"
    assert tool_event.attributes["attempt"] == 0
    assert tool_event.attributes["error_code"] == "durable_research_flow_required"
    assert tool_event.attributes["fallback_used"] == "none"


def test_container_composes_advisor_research_from_repository_and_ports() -> None:
    from due_diligence_agent.bootstrap.container import (
        build_startup_advisor_research_service,
    )

    profile = _profile()
    profiles = _ProfileRepository(profile)
    client = _RecordingResponses(_provider_response(source_count=1))
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
    )
    fallback = _CountingResearchPort(
        FrozenStartupMarketResearchAdapter.from_fixture_dir(_FIXTURE_ROOT)
    )

    service = build_startup_advisor_research_service(
        profile_repository=profiles,
        live_research_port=live,
        fallback_research_port=fallback,
        clock=lambda: _NOW,
    )

    delta = service.research(
        _CASE_ID,
        _question("icp"),
        AdvisorAnswer(
            answer_type="public_research",
            consent_public_research=True,
        ),
    )
    assert delta.status == "deferred"
    assert len(client.calls) == 0


class _ProfileRepository:
    def __init__(self, profile: StartupProfile) -> None:
        self.profile = profile
        self.calls = 0

    def get_current(self, case_id: UUID) -> StartupProfile:
        self.calls += 1
        assert case_id == self.profile.case_id
        return self.profile


class _RecordingResponses:
    def __init__(self, response: object, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class _RecordingLLMCalls:
    def __init__(self) -> None:
        self.records: list[dict[str, object | None]] = []

    def __call__(self, **attributes: object | None) -> None:
        self.records.append(attributes)


class _SequencedResponses:
    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _CountingResearchPort:
    def __init__(self, delegate: FrozenStartupMarketResearchAdapter) -> None:
        self.delegate = delegate
        self.calls = 0

    def collect(self, plan: Any) -> Any:
        self.calls += 1
        return self.delegate.collect(plan)


class _RaisingResearchPort:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def collect(self, _plan: Any) -> Any:
        self.calls += 1
        raise self.error


class _EmptyResearchPort:
    def __init__(self) -> None:
        self.calls = 0

    def collect(self, _plan: Any) -> Any:
        self.calls += 1
        return SimpleNamespace(sources=())


class _CaseRepo:
    def __init__(self, *, revision: int) -> None:
        self.revision = revision

    def get(self, case_id: UUID) -> object:
        assert case_id == _CASE_ID
        return SimpleNamespace(case_id=case_id, data_revision=self.revision)


class _PlanRepo:
    def __init__(self) -> None:
        self.records: dict[UUID, CaseResearchPlan] = {}

    def save(
        self,
        value: CaseResearchPlan,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> CaseResearchPlan:
        existing = next(
            (
                record
                for record in self.records.values()
                if record.case_id == value.case_id
                and record.data_revision == expected_revision
                and idempotency_key == f"research-plan:{record.plan_hash}"
            ),
            None,
        )
        if existing is not None:
            return existing
        self.records[value.plan_id] = value
        return value

    def get_for_case(self, case_id: UUID, plan_id: UUID) -> CaseResearchPlan:
        value = self.records[plan_id]
        if value.case_id != case_id:
            raise KeyError(plan_id)
        return value


class _JobRepo:
    def __init__(self) -> None:
        self.records: dict[UUID, CaseResearchJob] = {}
        self.idempotency: dict[str, CaseResearchJob] = {}

    def save(
        self,
        value: CaseResearchJob,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> CaseResearchJob:
        if idempotency_key in self.idempotency:
            return self.idempotency[idempotency_key]
        self.records[value.job_id] = value
        self.idempotency[idempotency_key] = value
        return value

    def get_by_idempotency(self, case_id: UUID, idempotency_key: str) -> CaseResearchJob | None:
        value = self.idempotency.get(idempotency_key)
        return value if value is not None and value.case_id == case_id else None

    def list_for_case(self, case_id: UUID) -> tuple[CaseResearchJob, ...]:
        return tuple(value for value in self.records.values() if value.case_id == case_id)


class _MixedBenchmarkProvider:
    def __init__(self) -> None:
        self.calls = 0

    def collect(self, _plan: CaseResearchPlan) -> list[dict[str, object]]:
        self.calls += 1
        return [
            _valid_benchmark_payload(),
            {
                **_valid_benchmark_payload(),
                "dependencies": (),
            },
        ]


def _valid_benchmark_payload() -> dict[str, object]:
    return {
        "entry_id": uuid5(NAMESPACE_URL, "advisor-benchmark-entry"),
        "input_key": "arpa",
        "provenance": "public_benchmark",
        "url": "https://example.com/public-advisor-benchmark",
        "publisher": "Example Research",
        "publication_date": "2026-08-01",
        "retrieval_date": "2026-08-22",
        "as_of": "2026-08-01",
        "source_class": "industry_report",
        "confidence": "medium",
        "value": "42",
        "unit": "KZT",
        "period": "month",
        "formula": "reported public benchmark value",
        "dependencies": ("public comparable companies",),
        "validation_plan": "Use only as external context until founder-specific evidence exists.",
        "source_refs": (uuid5(NAMESPACE_URL, "advisor-source-ref"),),
        "rationale": "Cited public benchmark for comparable public context.",
    }


def idempotency_key_for_test(
    case_id: UUID,
    question: AdvisorQuestion,
    data_revision: int,
) -> str:
    digest = sha256(
        f"{case_id}:{data_revision}:{question.question_id}:{question.field_key}".encode()
    ).hexdigest()
    return f"advisor-public-research:{digest}"


class _RecordingAuditSpool:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> str:
        self.events.append(event)
        return "memory://startup-public-research-audit"

    def read_batch(self, limit: int = 100) -> list[AuditEvent]:
        return self.events[:limit]

    def mark_flushed(self, _event_ids: object) -> None:
        return None


def _build_research_service(
    *,
    profile: StartupProfile | None = None,
    response: object | None = None,
    provider_error: Exception | None = None,
    fallback_port: Any | None = None,
    budget_guard: BudgetGuard | None = None,
    audit_spool: _RecordingAuditSpool | None = None,
    service_audit_spool: _RecordingAuditSpool | None = None,
) -> tuple[
    StartupAdvisorResearchService,
    _RecordingResponses,
    Any,
    _ProfileRepository,
    OpenAIStartupWebResearchAdapter,
]:
    current_profile = profile or _profile()
    profiles = _ProfileRepository(current_profile)
    client = _RecordingResponses(
        response or _provider_response(source_count=1),
        error=provider_error,
    )
    live = OpenAIStartupWebResearchAdapter(
        responses_client=client,
        clock=lambda: _NOW,
        budget_guard=budget_guard,
        audit_spool=audit_spool,
    )
    fallback = fallback_port or _CountingResearchPort(
        FrozenStartupMarketResearchAdapter.from_fixture_dir(_FIXTURE_ROOT)
    )
    service = StartupAdvisorResearchService(
        profile_repository=cast(Any, profiles),
        market_research_service=StartupMarketResearchService(clock=lambda: _NOW),
        live_research_port=live,
        fallback_research_port=fallback,
        case_research_service=CaseResearchJobService(
            case_repository=_CaseRepo(revision=current_profile.data_revision),
            plan_repository=_PlanRepo(),
            job_repository=_JobRepo(),
            public_benchmark_repository=None,
            scenario_repository=None,
            research_provider=StartupResearchPortBenchmarkProvider(live),
            acquisition_mode="live_public_research",
            clock=lambda: _NOW,
        ),
        audit_spool=service_audit_spool,
    )
    return service, client, fallback, profiles, live


def _provider_response(
    *,
    source_count: int,
    tool_status: str | None = None,
    text: str = "Модельная сводка не является фактом источника.",
) -> object:
    annotations = [
        {
            "type": "url_citation",
            "url": f"https://example.com/public-source-{index}",
            "title": f"Public source {index}",
        }
        for index in range(source_count)
    ]
    return SimpleNamespace(
        output=(
            SimpleNamespace(
                type="web_search_call",
                action={"type": "search", "queries": ["public market query"]},
                **({} if tool_status is None else {"status": tool_status}),
            ),
            SimpleNamespace(
                type="message",
                content=(
                    SimpleNamespace(
                        type="output_text",
                        text=text,
                        annotations=annotations,
                    ),
                ),
            ),
        ),
        usage=SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=150),
    )


def _provider_response_without_tool_call(
    *,
    source_count: int,
    text: str = "Модельная сводка не является фактом источника.",
) -> object:
    annotations = [
        {
            "type": "url_citation",
            "url": f"https://example.com/public-source-{index}",
            "title": f"Public source {index}",
        }
        for index in range(source_count)
    ]
    return SimpleNamespace(
        output=(
            SimpleNamespace(
                type="message",
                content=(
                    SimpleNamespace(
                        type="output_text",
                        text=text,
                        annotations=annotations,
                    ),
                ),
            ),
        ),
        usage=SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=150),
    )


def _normalized_source_url(source: Any) -> str:
    return str(source.source_url).rstrip("/")


def _question(field_key: str, *, hostile: bool = False) -> AdvisorQuestion:
    hostile_text = (
        "%PDF-RAW-DOCUMENT-SENTINEL founder-private-deck.pdf "
        "C:\\Users\\Akana\\private\\founder-deck.pdf PROMPT-SENTINEL "
        "founder.sentinel@example.com " + "sk-" + "proj-PRIVATE-SENTINEL-1234567890"
        if hostile
        else "Публично проверяемая тема"
    )
    return AdvisorQuestion(
        question_id=f"{_CASE_ID}:{field_key}",
        field_key=field_key,
        question_ru=hostile_text,
        reason_ru=hostile_text,
        unlocks_ru=hostile_text,
        answer_modes=("public_research",),
    )


def _profile(
    *,
    include_hostile_private_fields: bool = False,
    data_revision: int = 1,
) -> StartupProfile:
    fields = {
        name.value: StartupProfileField(
            name=name,
            status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
            confidence=Decimal(0),
        )
        for name in StartupProfileFieldName
    }
    fields[StartupProfileFieldName.SOLUTION.value] = _profile_field(
        StartupProfileFieldName.SOLUTION,
        ("AI due diligence copilot",),
    )
    fields[StartupProfileFieldName.ICP.value] = _profile_field(
        StartupProfileFieldName.ICP,
        ("seed-stage founders",),
    )
    fields[StartupProfileFieldName.GEOGRAPHY.value] = _profile_field(
        StartupProfileFieldName.GEOGRAPHY,
        ("Kazakhstan",),
    )
    if include_hostile_private_fields:
        fields[StartupProfileFieldName.PRICING_REVENUE_MODEL.value] = _profile_field(
            StartupProfileFieldName.PRICING_REVENUE_MODEL,
            (
                "MRR-PRIVATE-SENTINEL $9999",
                "sk-" + "proj-PRIVATE-SENTINEL-1234567890",
            ),
        )
        fields[StartupProfileFieldName.TRACTION.value] = _profile_field(
            StartupProfileFieldName.TRACTION,
            (
                "CUSTOMER-CONTRACT-SENTINEL founder.sentinel@example.com",
                "%PDF-RAW-DOCUMENT-SENTINEL founder-private-deck.pdf",
                "C:\\Users\\Akana\\private\\founder-deck.pdf PROMPT-SENTINEL",
            ),
        )
    return StartupProfile.build(
        case_id=_CASE_ID,
        schema_version="startup_profile@1",
        profile_version="primary@1",
        extractor_version="test@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=data_revision,
        source_hashes={"upload": "sha256:" + ("a" * 64)},
        parse_outcomes={"upload": "parsed"},
        fields=fields,
        case_revision_at=_NOW,
    )


def _profile_field(
    name: StartupProfileFieldName,
    values: tuple[str, ...],
) -> StartupProfileField:
    return StartupProfileField(
        name=name,
        status=StartupProfileFieldStatus.INFERENCE,
        values=values,
        confidence=Decimal("0.7"),
        dependency_refs=(uuid5(NAMESPACE_URL, f"dependency:{name.value}"),),
        reason_code="founder_provided",
    )
