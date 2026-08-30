from __future__ import annotations

import importlib
import json
import random
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, NamedTuple, Protocol
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from due_diligence_agent.application.policies.budget import (
    BudgetExceeded,
    BudgetGuard,
    BudgetReservation,
)
from due_diligence_agent.domain.startup.market import (
    MarketSizingAssumption,
    MarketSizingEstimate,
    StartupCompetitor,
    StartupCompetitorCategory,
    StartupMarketResearchSnapshot,
    StartupMarketSizing,
    StartupPublicBenchmarkCandidate,
    StartupResearchPlan,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
)
from due_diligence_agent.ports.llm import LLMBudgetRequest, LLMUsage
from due_diligence_agent.ports.tracing import AuditEvent, AuditSpool

_MODEL = "gpt-5.6-luna"
_MAX_QUERIES = 3
_MAX_SOURCES = 5
_MAX_CANDIDATES = 3
_MAX_COMPETITORS = 6
_MAX_ASSUMPTIONS = 6
_MAX_OUTPUT_TOKENS = 3_000
# A public web_search response includes both retrieval and strict-schema synthesis.
# Live acceptance completed at 29.5s and twice hit the former 30s boundary, so keep
# a bounded 60s window while adapter-owned attempts stay capped and SDK retries stay off.
_TIMEOUT_SECONDS = 60.0
STARTUP_PUBLIC_RESEARCH_WORST_CASE_TOKENS = 20_000
_WORST_CASE_USD = Decimal("0.05")
_MAX_PROVIDER_ATTEMPTS = 2
_RETRY_BASE_SECONDS = 0.25
_RETRY_JITTER_SECONDS = 0.25
_LIVE_SOURCE_CONFIDENCE = Decimal("0.70")
_PROVENANCE = "live_public_research:web_search:url_citation"
_WEB_SEARCH_OUTPUT_ITEM_TYPES = frozenset({"web_search_call"})
_PROVIDER_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]\r\n]{1,160})\]\(https?://[^\s)]+\)",
    flags=re.IGNORECASE,
)
_PROVIDER_BARE_URL_RE = re.compile(r"https?://[^\s)\]]+", flags=re.IGNORECASE)
_PROVIDER_CITATION_TOKEN_RE = re.compile(r"cite[^]+")
_PROVIDER_TEXT_FIELDS = (
    "publisher",
    "source_class",
    "formula",
    "validation_plan",
    "rationale",
)
_MARKET_CONTEXT_TEXT_FIELDS = (
    "name",
    "text",
    "unit",
    "currency",
    "formula_version",
)
_BENCHMARK_CONTEXT_TEXT_FIELDS = (
    "input_key",
    "source_class",
    *_PROVIDER_TEXT_FIELDS,
)
_CONFIDENCE_NUMBER_SCHEMA: dict[str, object] = {
    "type": "string",
    "pattern": r"^(?:0(?:\.\d+)?|1(?:\.0+)?)$",
}
_BENCHMARK_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "benchmark_candidates",
        "competitors",
        "market_assumptions",
        "market_sizing",
    ],
    "properties": {
        "benchmark_candidates": {
            "type": "array",
            "maxItems": _MAX_CANDIDATES,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "input_key",
                    "source_url",
                    "provenance",
                    "publisher",
                    "publication_date",
                    "as_of",
                    "source_class",
                    "confidence",
                    "value",
                    "range_low",
                    "range_high",
                    "unit",
                    "period",
                    "formula",
                    "dependencies",
                    "validation_plan",
                    "rationale",
                ],
                "properties": {
                    "input_key": {
                        "type": "string",
                        "enum": ["acquisition_spend", "arpa", "monthly_price"],
                    },
                    "source_url": {"type": "string"},
                    "provenance": {"type": "string", "enum": ["public_benchmark"]},
                    "publisher": {"type": "string"},
                    "publication_date": {"type": ["string", "null"]},
                    "as_of": {"type": "string"},
                    "source_class": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "value": {"type": ["string", "null"]},
                    "range_low": {"type": ["string", "null"]},
                    "range_high": {"type": ["string", "null"]},
                    "unit": {"type": "string", "enum": ["KZT"]},
                    "period": {"type": "string", "enum": ["month"]},
                    "formula": {"type": "string"},
                    "dependencies": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {"type": "string"},
                    },
                    "validation_plan": {"type": "string"},
                    "rationale": {"type": "string"},
                },
            },
        },
        "competitors": {
            "type": "array",
            "maxItems": _MAX_COMPETITORS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "category", "source_url", "confidence"],
                "properties": {
                    "name": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [item.value for item in StartupCompetitorCategory],
                    },
                    "source_url": {"type": "string"},
                    "confidence": _CONFIDENCE_NUMBER_SCHEMA,
                },
            },
        },
        "market_assumptions": {
            "type": "array",
            "maxItems": _MAX_ASSUMPTIONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "source_url", "confidence", "as_of"],
                "properties": {
                    "text": {"type": "string"},
                    "source_url": {"type": "string"},
                    "confidence": _CONFIDENCE_NUMBER_SCHEMA,
                    "as_of": {"type": "string"},
                },
            },
        },
        "market_sizing": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["tam", "sam", "som"],
            "properties": {
                level: {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "value",
                        "unit",
                        "currency",
                        "source_url",
                        "confidence",
                        "as_of",
                        "formula_version",
                    ],
                    "properties": {
                        "value": {"type": "string"},
                        "unit": {"type": "string"},
                        "currency": {"type": "string"},
                        "source_url": {"type": "string"},
                        "confidence": _CONFIDENCE_NUMBER_SCHEMA,
                        "as_of": {"type": "string"},
                        "formula_version": {"type": "string"},
                    },
                }
                for level in ("tam", "sam", "som")
            },
        },
    },
}
_SENSITIVE_RE = re.compile(
    r"(?i)(?:%PDF|raw[_ -]?pdf|document[_ -]?text|filename|local[_ -]?path|"
    r"prompt|system\s+instructions|file://|[A-Za-z]:[\\/]|"
    r"[\w.+-]+@[\w.-]+\.[a-z]{2,}|api[_ -]?key|authorization|bearer|"
    r"password|secret|(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{8,}"
    r"(?![A-Za-z0-9_-])|\.(?:pdf|docx|xlsx|csv|pptx)(?:\b|$)|"
    r"(?<![A-Za-z0-9])(?:invoices?|invoice[_ -]+registers?|bank[_ -]+data|"
    r"bank[_ -]+statements?|banking[_ -]+(?:data|extracts?))(?![A-Za-z0-9])|"
    r"(?:инвойс(?:ы|ов)?|сч[её]т[ао]в?[_ -]+фактур|реестр[_ -]+сч[её]тов|"
    r"банковск\w+[_ -]+(?:выписк\w+|данн\w+)|выписк\w+[_ -]+банк\w+)|"
    r"\b(?:mrr|arr|burn(?:[_ -]+rate)?|cash(?:[_ -]+balance)?|revenue|"
    r"contracts?|customers|clients|cap[_ -]+table|internal[_ -]+financial)\b|"
    r"\b(?:customer|client)[_ -]+(?:count|counts|number|list|names?)\b)"
)
_PRIVATE_CONTEXT_RE = re.compile(
    r"(?i)(?:%PDF|raw[_ -]?pdf|document[_ -]?text|filename|local[_ -]?path|"
    r"prompt|system\s+instructions|file://|[A-Za-z]:[\\/]|"
    r"[\w.+-]+@[\w.-]+\.[a-z]{2,}|api[_ -]?key|authorization|bearer|"
    r"password|secret|(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{8,}"
    r"(?![A-Za-z0-9_-])|\.(?:pdf|docx|xlsx|csv|pptx)(?:\b|$)|"
    r"(?<![A-Za-z0-9])(?:invoices?|invoice[_ -]+registers?|bank[_ -]+data|"
    r"bank[_ -]+statements?|banking[_ -]+(?:data|extracts?))(?![A-Za-z0-9])|"
    r"(?:инвойс(?:ы|ов)?|сч[её]т[ао]в?[_ -]+фактур|реестр[_ -]+сч[её]тов|"
    r"банковск\w+[_ -]+(?:выписк\w+|данн\w+)|выписк\w+[_ -]+банк\w+)|"
    r"\b(?:mrr|arr|burn(?:[_ -]+rate)?|cash(?:[_ -]+balance)?|revenue|"
    r"contracts?|cap[_ -]+table|internal[_ -]+financial)\b|"
    r"\b(?:customer|client)[_ -]+(?:count|counts|number|list|names?)\b)"
)


class ResponsesCreateClient(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _InvalidProviderResult(RuntimeError):
    pass


class _ParsedMarketContext(NamedTuple):
    competitors: tuple[StartupCompetitor, ...]
    assumptions: tuple[MarketSizingAssumption, ...]
    sizing: StartupMarketSizing | None


class OpenAIStartupWebResearchAdapter:
    """One-call public web-search adapter with canonical URL-citation output."""

    def __init__(
        self,
        *,
        responses_client: ResponsesCreateClient,
        clock: Any | None = None,
        budget_guard: BudgetGuard | None = None,
        audit_spool: AuditSpool | None = None,
        usage_cost_calculator: Callable[[LLMUsage], Decimal] | None = None,
        llm_call_recorder: Callable[..., None] | None = None,
        retry_sleep: Callable[[float], None] | None = None,
        retry_jitter: Callable[[float, float], float] | None = None,
    ) -> None:
        self._responses = responses_client
        self._clock = clock
        self._budget_guard = budget_guard
        self._audit_spool = audit_spool
        self._usage_cost_calculator = usage_cost_calculator
        self._llm_call_recorder = llm_call_recorder
        self._retry_sleep = retry_sleep or time.sleep
        self._retry_jitter = retry_jitter or random.uniform
        self.last_snapshot: StartupMarketResearchSnapshot | None = None

    @classmethod
    def from_openai(
        cls,
        *,
        api_key: str,
        budget_guard: BudgetGuard,
        audit_spool: AuditSpool,
        clock: Any | None = None,
        usage_cost_calculator: Callable[[LLMUsage], Decimal] | None = None,
        llm_call_recorder: Callable[..., None] | None = None,
    ) -> OpenAIStartupWebResearchAdapter:
        """Opt-in production construction; importing this module never imports the SDK."""

        openai = importlib.import_module("openai")
        client = openai.OpenAI(
            api_key=api_key,
            timeout=_TIMEOUT_SECONDS,
            max_retries=0,
        )
        return cls(
            responses_client=client.responses,
            clock=clock,
            budget_guard=budget_guard,
            audit_spool=audit_spool,
            usage_cost_calculator=usage_cost_calculator,
            llm_call_recorder=llm_call_recorder,
        )

    def collect(self, plan: StartupResearchPlan) -> StartupMarketResearchSnapshot:
        if plan.source_mode is not StartupResearchSourceMode.LIVE:
            raise ValueError("live startup research adapter requires live plan")
        queries = tuple(
            dict.fromkeys(
                normalized
                for query in plan.queries[: min(plan.max_queries, _MAX_QUERIES)]
                if (normalized := _safe_query(query))
            )
        )
        if not queries:
            raise RuntimeError("startup_public_research_safe_query_required")

        try:
            reservation = self._reserve(plan.case_id)
        except BudgetExceeded:
            self._audit(
                plan.case_id,
                request_id=plan.research_job_id,
                status="failed",
                query_count=len(queries),
                source_count=0,
                failure_code="budget_exceeded",
            )
            raise
        request = _provider_request(queries)
        attempt = 1
        span_started_at = time.perf_counter()
        tool_call_observed = False
        response: object | None = None
        reservation_settled = False
        try:
            while True:
                self._audit(
                    plan.case_id,
                    request_id=plan.research_job_id,
                    status="requested",
                    query_count=len(queries),
                    source_count=0,
                    attempt=attempt,
                    retry_count=attempt - 1,
                )
                try:
                    response = self._responses.create(**request)
                except Exception as exc:
                    if attempt >= _MAX_PROVIDER_ATTEMPTS or not _is_retryable_provider_error(exc):
                        raise
                    retry_delay = _RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + self._retry_jitter(
                        0.0, _RETRY_JITTER_SECONDS
                    )
                    self._retry_sleep(retry_delay)
                    attempt += 1
                    continue
                break
            retrieved_at = self._now()
            tool_call_observed = _response_has_web_search_call(response)
            if not tool_call_observed:
                raise _InvalidProviderResult("startup_public_research_web_search_call_required")
            if _response_incomplete(response):
                raise _InvalidProviderResult("startup_public_research_incomplete_output")
            sources = _sources_from_response(
                response,
                queries=queries,
                retrieved_at=retrieved_at,
            )
            if not sources:
                raise _InvalidProviderResult("startup_public_research_citations_required")
            candidates = _candidates_from_response(
                response,
                sources=sources,
                retrieved_at=retrieved_at,
            )
            market_context = _market_context_from_response(
                response,
                sources=sources,
                retrieved_at=retrieved_at,
            )
            usage = _observed_usage(response)
            actual_cost = self._reconcile(reservation, response)
            reservation_settled = True
            latency_ms = _elapsed_ms(span_started_at)
            self._audit(
                plan.case_id,
                request_id=plan.research_job_id,
                status="completed",
                query_count=len(queries),
                source_count=len(sources),
                attempt=attempt,
                retry_count=attempt - 1,
                latency_ms=latency_ms,
                usage=usage,
                cost_usd=actual_cost,
                tool_call_observed=tool_call_observed,
            )
            self._record_observed_llm_call(
                plan=plan,
                response=response,
                status="success",
                attempt=attempt,
                query_count=len(queries),
                source_count=len(sources),
                latency_ms=latency_ms,
            )
        except BudgetExceeded:
            self._release(reservation)
            self._audit(
                plan.case_id,
                request_id=plan.research_job_id,
                status="failed",
                query_count=len(queries),
                source_count=0,
                failure_code="budget_exceeded",
                attempt=attempt,
                retry_count=attempt - 1,
                latency_ms=_elapsed_ms(span_started_at),
                tool_call_observed=tool_call_observed,
            )
            raise
        except _InvalidProviderResult:
            usage = _observed_usage(response)
            actual_cost = self._actual_usd_cost(usage)
            if response is not None and not reservation_settled:
                actual_cost = self._reconcile(reservation, response)
            elif response is None:
                self._release(reservation)
            latency_ms = _elapsed_ms(span_started_at)
            self._audit(
                plan.case_id,
                request_id=plan.research_job_id,
                status="failed",
                query_count=len(queries),
                source_count=0,
                failure_code="invalid_output",
                attempt=attempt,
                retry_count=attempt - 1,
                latency_ms=latency_ms,
                usage=usage,
                cost_usd=actual_cost,
                tool_call_observed=tool_call_observed,
            )
            self._record_observed_llm_call(
                plan=plan,
                response=response,
                status="invalid",
                attempt=attempt,
                query_count=len(queries),
                source_count=0,
                latency_ms=latency_ms,
                error_code="invalid_output",
            )
            raise RuntimeError("startup_public_research_invalid_output") from None
        except Exception as exc:  # noqa: BLE001 - provider SDK errors share no stable base class
            usage = _observed_usage(response)
            actual_cost = self._actual_usd_cost(usage)
            if response is not None and not reservation_settled:
                actual_cost = self._reconcile(reservation, response)
            elif response is None:
                self._release(reservation)
            latency_ms = _elapsed_ms(span_started_at)
            if _is_provider_timeout(exc):
                self._audit(
                    plan.case_id,
                    request_id=plan.research_job_id,
                    status="failed",
                    query_count=len(queries),
                    source_count=0,
                    failure_code="provider_timeout",
                    attempt=attempt,
                    retry_count=attempt - 1,
                    latency_ms=latency_ms,
                    usage=usage,
                    cost_usd=actual_cost,
                    tool_call_observed=tool_call_observed,
                )
                self._record_observed_llm_call(
                    plan=plan,
                    response=response,
                    status="failed",
                    attempt=attempt,
                    query_count=len(queries),
                    source_count=0,
                    latency_ms=latency_ms,
                    error_code="provider_timeout",
                )
                raise RuntimeError("startup_public_research_timeout") from None
            self._audit(
                plan.case_id,
                request_id=plan.research_job_id,
                status="failed",
                query_count=len(queries),
                source_count=0,
                failure_code="provider_unavailable",
                attempt=attempt,
                retry_count=attempt - 1,
                latency_ms=latency_ms,
                usage=usage,
                cost_usd=actual_cost,
                tool_call_observed=tool_call_observed,
            )
            self._record_observed_llm_call(
                plan=plan,
                response=response,
                status="failed",
                attempt=attempt,
                query_count=len(queries),
                source_count=0,
                latency_ms=latency_ms,
                error_code="provider_unavailable",
            )
            raise RuntimeError("startup_public_research_unavailable") from None

        research_id = _research_id(queries, sources)
        snapshot = StartupMarketResearchSnapshot.build(
            case_id=plan.case_id,
            as_of=retrieved_at,
            source_mode=StartupResearchSourceMode.LIVE,
            research_id=research_id,
            competitors=market_context.competitors,
            sources=sources,
            sentiment_signals=(),
            assumptions=market_context.assumptions,
            sizing=market_context.sizing,
            public_benchmark_candidates=candidates,
            labels=("live_public_research", "live_inference", _MODEL),
            data_revision=1,
        )
        self.last_snapshot = snapshot
        return snapshot

    def _now(self) -> datetime:
        value = self._clock() if self._clock is not None else datetime.now(UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _reserve(self, case_id: UUID) -> BudgetReservation | None:
        if self._budget_guard is None:
            return None
        return self._budget_guard.reserve(
            LLMBudgetRequest(
                case_id=case_id,
                worst_case_tokens=STARTUP_PUBLIC_RESEARCH_WORST_CASE_TOKENS,
                worst_case_usd_cost=_WORST_CASE_USD,
            ),
            attempt="startup_public_web_research",
        )

    def _reconcile(
        self,
        reservation: BudgetReservation | None,
        response: object,
    ) -> Decimal | None:
        usage = _observed_usage(response)
        actual_cost = self._actual_usd_cost(usage)
        if reservation is not None and self._budget_guard is not None:
            self._budget_guard.reconcile(
                reservation,
                usage=usage,
                actual_usd_cost=actual_cost,
            )
        return actual_cost

    def _release(self, reservation: BudgetReservation | None) -> None:
        if reservation is not None and self._budget_guard is not None:
            self._budget_guard.release(reservation)

    def _actual_usd_cost(self, usage: LLMUsage | None) -> Decimal | None:
        if usage is None or self._usage_cost_calculator is None:
            return None
        return self._usage_cost_calculator(usage)

    def _record_observed_llm_call(
        self,
        *,
        plan: StartupResearchPlan,
        response: object | None,
        status: str,
        attempt: int,
        query_count: int,
        source_count: int,
        latency_ms: int,
        error_code: str | None = None,
    ) -> None:
        if self._llm_call_recorder is None or response is None:
            return
        usage = _observed_usage(response)
        if usage is None:
            return
        attributes: dict[str, object | None] = {
            "case_id": str(plan.case_id),
            "run_id": f"startup-public-research-{plan.research_job_id}",
            "correlation_id": f"research-job-{plan.research_job_id}",
            "workflow_type": "startup",
            "request_id": str(plan.research_job_id),
            "node_name": "public_research",
            "agent_role": "market",
            "status": status,
            "attempt": attempt,
            "retry_count": max(0, attempt - 1),
            "provider": "openai",
            "model": _MODEL,
            "tool": "web_search",
            "query_count": query_count,
            "source_count": source_count,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "schema_version": "startup_public_research_llm_span@1",
            "duration_ms": latency_ms,
            "latency_ms": latency_ms,
            "checkpoint_id": f"research-{plan.research_job_id}",
        }
        actual_cost = self._actual_usd_cost(usage)
        if actual_cost is not None:
            attributes["cost_usd"] = float(actual_cost)
        if error_code is not None:
            attributes["error_code"] = error_code
        try:
            self._llm_call_recorder(**attributes)
        except Exception:  # noqa: BLE001 - telemetry callbacks must not break public research
            return

    def _audit(
        self,
        case_id: UUID,
        *,
        request_id: UUID | None = None,
        status: str,
        query_count: int,
        source_count: int,
        failure_code: str | None = None,
        attempt: int = 1,
        retry_count: int = 0,
        latency_ms: int | None = None,
        usage: LLMUsage | None = None,
        cost_usd: Decimal | None = None,
        tool_call_observed: bool | None = None,
    ) -> None:
        if self._audit_spool is None:
            return
        now = self._now()
        attributes: dict[str, str | int | float | bool | None] = {
            "case_id": str(case_id),
            "status": status,
            "query_count": query_count,
            "source_count": source_count,
            "attempt": attempt,
            "retry_count": retry_count,
            "provider": "openai",
            "model": _MODEL,
            "tool": "web_search",
            "research_label": "live_public_research",
            "inference_label": "live_inference",
        }
        if request_id is not None:
            attributes["request_id"] = str(request_id)
        if failure_code is not None:
            attributes["failure_code"] = failure_code
        if latency_ms is not None:
            attributes["latency_ms"] = latency_ms
        if usage is not None:
            attributes["input_tokens"] = usage.input_tokens
            attributes["output_tokens"] = usage.output_tokens
            attributes["total_tokens"] = usage.total_tokens
        if cost_usd is not None:
            attributes["cost_usd"] = float(cost_usd)
        if tool_call_observed is not None:
            attributes["tool_call_observed"] = tool_call_observed
        self._audit_spool.append(
            AuditEvent(
                schema_version="audit_event@1",
                event_id=str(uuid4()),
                timestamp_utc=now.isoformat().replace("+00:00", "Z"),
                run_id=f"startup-public-research-{request_id or case_id}",
                correlation_id=(
                    f"research-job-{request_id}"
                    if request_id is not None
                    else f"case-{case_id}"
                ),
                span_name="startup.public_research",
                event_type="span",
                attributes=attributes,
            )
        )


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def _provider_request(queries: tuple[str, ...]) -> dict[str, object]:
    payload = {
        "schema_version": "startup_public_research_request@1",
        "queries": list(queries),
        "constraints": {
            "public_web_only": True,
            "max_queries": _MAX_QUERIES,
            "max_cited_sources": _MAX_SOURCES,
            "private_financial_or_customer_data": False,
            "private_invoice_or_bank_records": False,
        },
    }
    return {
        "model": _MODEL,
        "instructions": (
            "Search only the public web for the supplied sanitized queries. "
            "Return strict JSON with up to three quantitative public benchmark candidates, "
            "cited competitors, cited qualitative market assumptions, and cited TAM/SAM/SOM "
            "scenario estimates when the public sources support them. "
            "Every candidate source_url must be cited by the response. "
            "Every competitor, market assumption, and sizing source_url must be cited by the response. "
            "Use only values already published as KZT per month or KZT/month ranges. "
            "For TAM/SAM/SOM, provide public scenario estimates only; do not provide private company "
            "MRR, ARR, revenue, cash, burn, customers, contracts, invoices, invoice registers, "
            "bank statements, bank data, banking extracts, or founder-specific figures. "
            "Set publication_date to null when the cited source gives no publication date. "
            "Omit candidates that require currency or period conversion. "
            "Do not infer private startup financial, customer, contract, cash, invoice, or bank data."
        ),
        "input": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        "tools": [{"type": "web_search"}],
        "tool_choice": "required",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "startup_public_benchmark_candidates",
                "strict": True,
                "schema": _BENCHMARK_SCHEMA,
            }
        },
        "include": ["web_search_call.action.sources", "web_search_call.results"],
        "store": False,
        "max_output_tokens": _MAX_OUTPUT_TOKENS,
        "timeout": _TIMEOUT_SECONDS,
    }


def _sources_from_response(
    response: object,
    *,
    queries: tuple[str, ...],
    retrieved_at: datetime,
) -> tuple[StartupResearchSource, ...]:
    citations: list[tuple[str, str, date]] = []
    seen_urls: set[str] = set()
    for output_item in _sequence(_value(response, "output", ())):
        for content_item in _sequence(_value(output_item, "content", ())):
            for annotation in _sequence(_value(content_item, "annotations", ())):
                if _value(annotation, "type") != "url_citation":
                    continue
                url = _normalize_public_url(str(_value(annotation, "url", "")))
                if not url or url in seen_urls:
                    continue
                title = " ".join(str(_value(annotation, "title", "")).split())
                if not title:
                    title = "Публичный источник"
                as_of = _citation_date(annotation, fallback=retrieved_at.date())
                citations.append((url, title[:80], as_of))
                seen_urls.add(url)
                if len(citations) >= _MAX_SOURCES:
                    break
            if len(citations) >= _MAX_SOURCES:
                break
        if _value(output_item, "type") == "web_search_call":
            action = _value(output_item, "action", {})
            action_type = str(_value(action, "type", "")).strip().lower()
            if action_type in {"open_page", "find_in_page"}:
                action_url = _normalize_public_url(str(_value(action, "url", "")))
                if action_url and action_url not in seen_urls:
                    citations.append(
                        (
                            action_url,
                            "Публичный источник",
                            _citation_date(action, fallback=retrieved_at.date()),
                        )
                    )
                    seen_urls.add(action_url)
            for source in _sequence(_value(action, "sources", ())):
                url = _normalize_public_url(str(_value(source, "url", "")))
                if not url or url in seen_urls:
                    continue
                title = " ".join(str(_value(source, "title", "")).split())
                if not title:
                    title = "Публичный источник"
                as_of = _citation_date(source, fallback=retrieved_at.date())
                citations.append((url, title[:80], as_of))
                seen_urls.add(url)
                if len(citations) >= _MAX_SOURCES:
                    break
            for result in _sequence(_value(output_item, "results", ())):
                url = _normalize_public_url(str(_value(result, "url", "")))
                if not url or url in seen_urls:
                    continue
                title = " ".join(str(_value(result, "title", "")).split())
                if not title:
                    title = "Публичный источник"
                as_of = _citation_date(result, fallback=retrieved_at.date())
                citations.append((url, title[:80], as_of))
                seen_urls.add(url)
                if len(citations) >= _MAX_SOURCES:
                    break
        if len(citations) >= _MAX_SOURCES:
            break

    query = queries[0]
    sources: list[StartupResearchSource] = []
    for url, title, as_of in citations:
        metadata = {
            "url": url,
            "title": title,
            "as_of": as_of.isoformat(),
            "retrieved_at": retrieved_at.isoformat(),
            "query": query,
            "provenance": _PROVENANCE,
            "confidence": str(_LIVE_SOURCE_CONFIDENCE),
        }
        digest = sha256(
            json.dumps(
                metadata,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        sources.append(
            StartupResearchSource.model_validate(
                {
                    "source_id": uuid5(NAMESPACE_URL, f"startup-public-source:{url}"),
                    "source_mode": StartupResearchSourceMode.LIVE,
                    "source_hash": f"sha256:{digest}",
                    "source_url": url,
                    "source_label": title,
                    "as_of": as_of,
                    "retrieved_at": retrieved_at,
                    "query": query,
                    "provenance": _PROVENANCE,
                    "confidence": _LIVE_SOURCE_CONFIDENCE,
                    "supports_primary_financial_metrics": False,
                    "stale": False,
                    "status": StartupResearchSourceStatus.INFERENCE,
                }
            )
        )
    return tuple(sources)


def _candidates_from_response(
    response: object,
    *,
    sources: tuple[StartupResearchSource, ...],
    retrieved_at: datetime,
) -> tuple[StartupPublicBenchmarkCandidate, ...]:
    cited_sources = {_normalize_public_url(str(source.source_url)): source for source in sources}
    raw_payload = _json_payload_from_response(response)
    raw_candidates = raw_payload.get("benchmark_candidates")
    if not isinstance(raw_candidates, list):
        return ()
    candidates: list[StartupPublicBenchmarkCandidate] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_candidates[:_MAX_CANDIDATES]:
        if not isinstance(raw, Mapping):
            continue
        source_url = _normalize_public_url(str(raw.get("source_url") or ""))
        source = cited_sources.get(source_url)
        if source is None or _has_private_benchmark_context(raw):
            continue
        payload = dict(raw)
        payload["source_url"] = source_url
        payload["retrieval_date"] = retrieved_at.date().isoformat()
        payload["source_ref"] = source.source_id
        for field_name in _PROVIDER_TEXT_FIELDS:
            payload[field_name] = _strip_provider_citations(payload.get(field_name))
        dependencies = payload.get("dependencies")
        if isinstance(dependencies, list | tuple):
            payload["dependencies"] = [
                _strip_provider_citations(dependency) for dependency in dependencies
            ]
        try:
            candidate = StartupPublicBenchmarkCandidate.model_validate(payload)
        except (InvalidOperation, ValueError):
            continue
        key = (candidate.input_key, candidate.source_url)
        if key in seen:
            continue
        candidates.append(candidate)
        seen.add(key)
    return tuple(candidates)


def _market_context_from_response(
    response: object,
    *,
    sources: tuple[StartupResearchSource, ...],
    retrieved_at: datetime,
) -> _ParsedMarketContext:
    cited_sources = {_normalize_public_url(str(source.source_url)): source for source in sources}
    raw_payload = _json_payload_from_response(response)
    assumptions = _assumptions_from_payload(
        raw_payload,
        cited_sources=cited_sources,
        retrieved_at=retrieved_at,
    )
    return _ParsedMarketContext(
        competitors=_competitors_from_payload(raw_payload, cited_sources=cited_sources),
        assumptions=assumptions,
        sizing=_sizing_from_payload(
            raw_payload,
            cited_sources=cited_sources,
            assumptions=assumptions,
            retrieved_at=retrieved_at,
        ),
    )


def _competitors_from_payload(
    raw_payload: Mapping[str, object],
    *,
    cited_sources: Mapping[str, StartupResearchSource],
) -> tuple[StartupCompetitor, ...]:
    raw_competitors = raw_payload.get("competitors")
    if not isinstance(raw_competitors, list):
        return ()
    competitors: list[StartupCompetitor] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_competitors[:_MAX_COMPETITORS]:
        if not isinstance(raw, Mapping):
            continue
        source = _source_for_raw_url(raw.get("source_url"), cited_sources)
        if source is None or _has_private_market_context(raw):
            continue
        try:
            competitor = StartupCompetitor.model_validate(
                {
                    "name": _strip_provider_citations(raw.get("name")),
                    "category": raw.get("category"),
                    "status": StartupResearchSourceStatus.INFERENCE,
                    "confidence": raw.get("confidence"),
                    "source_ids": (source.source_id,),
                    "reason_code": "live_public_research",
                }
            )
        except (InvalidOperation, ValueError):
            continue
        key = (competitor.name.casefold(), competitor.category.value)
        if key in seen:
            continue
        competitors.append(competitor)
        seen.add(key)
    return tuple(competitors)


def _assumptions_from_payload(
    raw_payload: Mapping[str, object],
    *,
    cited_sources: Mapping[str, StartupResearchSource],
    retrieved_at: datetime,
) -> tuple[MarketSizingAssumption, ...]:
    raw_assumptions = raw_payload.get("market_assumptions")
    if not isinstance(raw_assumptions, list):
        return ()
    assumptions: list[MarketSizingAssumption] = []
    seen: set[tuple[str, UUID]] = set()
    for raw in raw_assumptions[:_MAX_ASSUMPTIONS]:
        if not isinstance(raw, Mapping):
            continue
        source = _source_for_raw_url(raw.get("source_url"), cited_sources)
        if source is None or _has_private_market_context(raw):
            continue
        text = str(_strip_provider_citations(raw.get("text")) or "")
        as_of = str(raw.get("as_of") or source.as_of or retrieved_at.date().isoformat())[:10]
        assumption_id = uuid5(
            NAMESPACE_URL,
            f"startup-public-assumption:{source.source_id}:{as_of}:{text}",
        )
        try:
            assumption = MarketSizingAssumption.model_validate(
                {
                    "assumption_id": assumption_id,
                    "text": text,
                    "status": StartupResearchSourceStatus.INFERENCE,
                    "confidence": raw.get("confidence"),
                    "as_of": as_of,
                    "source_mode": StartupResearchSourceMode.LIVE,
                    "source_ids": (source.source_id,),
                    "reason_code": "live_public_research",
                }
            )
        except (InvalidOperation, ValueError):
            continue
        key = (assumption.text.casefold(), source.source_id)
        if key in seen:
            continue
        assumptions.append(assumption)
        seen.add(key)
    return tuple(assumptions)


def _sizing_from_payload(
    raw_payload: Mapping[str, object],
    *,
    cited_sources: Mapping[str, StartupResearchSource],
    assumptions: tuple[MarketSizingAssumption, ...],
    retrieved_at: datetime,
) -> StartupMarketSizing | None:
    raw_sizing = raw_payload.get("market_sizing")
    if not isinstance(raw_sizing, Mapping) or not assumptions:
        return None
    assumption_refs = tuple(assumption.assumption_id for assumption in assumptions)
    estimates: dict[str, MarketSizingEstimate] = {}
    for level_name in ("tam", "sam", "som"):
        raw_estimate = raw_sizing.get(level_name)
        if not isinstance(raw_estimate, Mapping):
            return None
        estimate = _sizing_estimate_from_payload(
            level_name,
            raw_estimate,
            cited_sources=cited_sources,
            assumption_refs=assumption_refs,
            retrieved_at=retrieved_at,
        )
        if estimate is None:
            return None
        estimates[level_name] = estimate
    try:
        return StartupMarketSizing.model_validate(estimates)
    except (InvalidOperation, ValueError):
        return None


def _sizing_estimate_from_payload(
    level_name: str,
    raw: Mapping[str, object],
    *,
    cited_sources: Mapping[str, StartupResearchSource],
    assumption_refs: tuple[UUID, ...],
    retrieved_at: datetime,
) -> MarketSizingEstimate | None:
    source = _source_for_raw_url(raw.get("source_url"), cited_sources)
    if source is None or _has_private_market_context(raw):
        return None
    value = raw.get("value")
    unit = _strip_provider_citations(raw.get("unit"))
    currency = _strip_provider_citations(raw.get("currency"))
    as_of = str(raw.get("as_of") or source.as_of or retrieved_at.date().isoformat())[:10]
    formula_version = _strip_provider_citations(
        raw.get("formula_version") or "live_public_research_tam_sam_som@1"
    )
    estimate_id = uuid5(
        NAMESPACE_URL,
        "startup-public-sizing:"
        f"{level_name}:{source.source_id}:{as_of}:{value}:{unit}:{currency}:{formula_version}",
    )
    try:
        return MarketSizingEstimate.model_validate(
            {
                "estimate_id": estimate_id,
                "level": StartupResearchSourceStatus.INFERENCE,
                "value": value,
                "unit": unit,
                "currency": currency,
                "as_of": as_of,
                "source_mode": StartupResearchSourceMode.LIVE,
                "formula_version": formula_version,
                "assumption_refs": assumption_refs,
                "source_refs": (source.source_id,),
                "confidence": raw.get("confidence"),
            }
        )
    except (InvalidOperation, ValueError):
        return None


def _source_for_raw_url(
    raw_url: object,
    cited_sources: Mapping[str, StartupResearchSource],
) -> StartupResearchSource | None:
    source_url = _normalize_public_url(str(raw_url or ""))
    return cited_sources.get(source_url)


def _has_private_market_context(raw: Mapping[str, object]) -> bool:
    for field_name in _MARKET_CONTEXT_TEXT_FIELDS:
        if _text_has_private_context(raw.get(field_name)):
            return True
    return False


def _has_private_benchmark_context(raw: Mapping[str, object]) -> bool:
    for field_name in _BENCHMARK_CONTEXT_TEXT_FIELDS:
        if _text_has_private_context(raw.get(field_name)):
            return True
    dependencies = raw.get("dependencies")
    if isinstance(dependencies, list | tuple):
        return any(_text_has_private_context(dependency) for dependency in dependencies)
    return False


def _text_has_private_context(value: object) -> bool:
    if value is None:
        return False
    stripped = _strip_provider_citations(value)
    if not isinstance(stripped, str):
        return False
    return _PRIVATE_CONTEXT_RE.search(stripped) is not None


def _strip_provider_citations(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = _PROVIDER_MARKDOWN_LINK_RE.sub(r"\1", value)
    normalized = _PROVIDER_BARE_URL_RE.sub("", normalized)
    normalized = _PROVIDER_CITATION_TOKEN_RE.sub("", normalized)
    normalized = re.sub(r"\(\s*\)", "", normalized)
    return " ".join(normalized.strip().split())


def _json_payload_from_response(response: object) -> dict[str, object]:
    for output_item in _sequence(_value(response, "output", ())):
        if _value(output_item, "type") not in {"message", None}:
            continue
        for content_item in _sequence(_value(output_item, "content", ())):
            if _value(content_item, "type") != "output_text":
                continue
            text = str(_value(content_item, "text", "")).strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return {}


def _response_incomplete(response: object) -> bool:
    if _value(response, "status") == "incomplete":
        return True
    details = _value(response, "incomplete_details", None)
    reason = _value(details, "reason", None)
    return isinstance(reason, str) and bool(reason.strip())


def _response_has_web_search_call(response: object) -> bool:
    return any(
        _value(output_item, "type") in _WEB_SEARCH_OUTPUT_ITEM_TYPES
        and _web_search_call_status_successful(output_item)
        for output_item in _sequence(_value(response, "output", ()))
    )


def _web_search_call_status_successful(output_item: object) -> bool:
    status = _value(output_item, "status", None)
    if status is None:
        return True
    return str(status).strip().lower() in {"completed", "success", "succeeded"}


def _is_provider_timeout(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    for cls in type(exc).mro():
        if (
            cls.__name__ == "APITimeoutError"
            and cls.__module__.split(".", maxsplit=1)[0] == "openai"
        ):
            return True
    return False


def _is_retryable_provider_error(exc: Exception) -> bool:
    if _is_provider_timeout(exc):
        return True
    openai_class_names = {
        cls.__name__
        for cls in type(exc).mro()
        if cls.__module__.split(".", maxsplit=1)[0] == "openai"
    }
    if openai_class_names.intersection(
        {"APIConnectionError", "RateLimitError", "InternalServerError"}
    ):
        return True
    status_code = getattr(exc, "status_code", None)
    return bool(
        openai_class_names
        and isinstance(status_code, int)
        and (status_code == 429 or status_code >= 500)
    )


def _normalize_public_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if parsed.path == "/" and not parsed.query:
        return normalized.rstrip("/")
    return normalized


def _safe_query(value: str) -> str:
    normalized = " ".join(value.strip().split())[:120].rstrip()
    if not normalized or _SENSITIVE_RE.search(normalized) is not None:
        return ""
    return normalized


def _citation_date(annotation: object, *, fallback: date) -> date:
    for key in ("as_of", "published_on", "published_date"):
        raw = _value(annotation, key)
        if isinstance(raw, date):
            return raw
        if isinstance(raw, str):
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                continue
    return fallback


def _research_id(
    queries: tuple[str, ...],
    sources: tuple[StartupResearchSource, ...],
) -> UUID:
    seed = json.dumps(
        {
            "model": _MODEL,
            "queries": queries,
            "sources": [
                {
                    "source_id": str(source.source_id),
                    "source_hash": source.source_hash,
                }
                for source in sources
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return uuid5(NAMESPACE_URL, f"startup-public-research:{seed}")


def _usage(response: object) -> LLMUsage:
    return _observed_usage(response) or LLMUsage()


def _observed_usage(response: object | None) -> LLMUsage | None:
    if response is None:
        return None
    usage = _value(response, "usage", {})
    if usage is None or usage == {}:
        return None
    input_tokens = _non_negative_int(_value(usage, "input_tokens", 0))
    output_tokens = _non_negative_int(_value(usage, "output_tokens", 0))
    total_tokens = _non_negative_int(_value(usage, "total_tokens", input_tokens + output_tokens))
    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float | str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def _value(value: object, key: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()
