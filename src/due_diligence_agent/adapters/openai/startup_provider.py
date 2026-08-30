from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from decimal import Decimal
from threading import Event, Lock, Thread
from types import GenericAlias
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

from due_diligence_agent.adapters.privacy.rules_redactor import RulesRedactor
from due_diligence_agent.domain.common import (
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.findings.models import Finding
from due_diligence_agent.ports.llm import (
    LLMBudgetRequest,
    LLMContextFragment,
    LLMGatewayPort,
    LLMRoutingContext,
    StructuredLLMResult,
)
from due_diligence_agent.ports.tracing import TraceContext


class OpenAIStartupProvider:
    def __init__(
        self,
        *,
        gateway: LLMGatewayPort,
        evidence_repository: Any,
        calculation_repository: Any,
        clock: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], UUID] = uuid4,
        redaction_policy_version: str = "startup-openai-provider@1",
        worst_case_tokens: int = 4_000,
        worst_case_usd_cost: Decimal = Decimal("0.05"),
        max_fragments: int = 24,
        max_context_chars: int = 12_000,
        max_findings: int = 8,
        llm_latency_budget_ms: int = 60_000,
        bridge_timeout_seconds: float | None = None,
    ) -> None:
        self._gateway = gateway
        self._evidence_repository = evidence_repository
        self._calculation_repository = calculation_repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._uuid_factory = uuid_factory
        self._redaction_policy_version = redaction_policy_version
        self._worst_case_tokens = worst_case_tokens
        self._worst_case_usd_cost = worst_case_usd_cost
        self._max_fragments = max_fragments
        self._max_context_chars = max_context_chars
        self._max_findings = max_findings
        self._llm_latency_budget_ms = llm_latency_budget_ms
        self._bridge_timeout_seconds = (
            bridge_timeout_seconds
            if bridge_timeout_seconds is not None
            else (llm_latency_budget_ms / 1_000 * 2) + 15
        )
        self._redactor = RulesRedactor()

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, list[Finding]]:
        case_uuid = UUID(case_id)
        invalidated = _uuid_set(invalidated_ids)
        requested_fact_ids = _uuid_tuple(remaining_evidence_fact_ids, excluded=invalidated)
        requested_calculation_ids = _uuid_tuple(remaining_calculation_ids, excluded=invalidated)
        facts = tuple(
            fact
            for fact in self._select_facts(case_uuid, requested_fact_ids)
            if not _is_document_text_block_lineage_marker(fact)
        )
        calculations = self._select_calculations(case_uuid, requested_calculation_ids)
        redaction_policy_version = _redaction_policy_version(
            disclosure_scope,
            default=self._redaction_policy_version,
        )
        fragments = [
            *(_fact_fragment(fact, redaction_policy_version, redactor=self._redactor) for fact in facts),
            *(
                _calculation_fragment(calculation, redaction_policy_version, redactor=self._redactor)
                for calculation in calculations
            ),
        ]
        if len(fragments) > self._max_fragments:
            raise StartupProviderContextLimitError("STARTUP_PROVIDER_CONTEXT_LIMIT")
        fragments = _bounded_fragments(fragments, max_context_chars=self._max_context_chars)
        if any(fragment.sensitivity == SensitivityClass.RESTRICTED for fragment in fragments):
            raise StartupProviderRestrictedContextError("STARTUP_PROVIDER_RESTRICTED_CONTEXT")
        if not fragments:
            return {
                "findings": [
                    Finding(
                        id=self._uuid_factory(),
                        case_id=case_uuid,
                        category=node_name,
                        severity=FindingSeverity.LOW,
                        claim=f"{node_name}: insufficient normalized evidence for OpenAI analysis.",
                        confidence=Decimal("0"),
                        status=FindingStatus.INSUFFICIENT_DATA,
                        author_node=node_name,
                        author_model=None,
                        sensitivity=SensitivityClass.PUBLIC,
                        created_at=self._clock(),
                    )
                ]
            }

        expected_schema = _provider_response_wire_schema(
            allowed_fact_ids=tuple(fact.id for fact in facts),
            allowed_calculation_ids=tuple(calculation.id for calculation in calculations),
        )
        result: StructuredLLMResult[OpenAIStartupProviderResponseWire] = _run_sync(
            self._gateway.complete_structured(
                task=_task_prompt(node_name),
                fragments=fragments,
                expected_schema=expected_schema,
                budget_request=LLMBudgetRequest(
                    case_id=case_uuid,
                    worst_case_tokens=self._worst_case_tokens,
                    worst_case_usd_cost=self._worst_case_usd_cost,
                ),
                routing_context=LLMRoutingContext(
                    task_complexity="medium",
                    latency_budget_ms=self._llm_latency_budget_ms,
                    schema_validation_failed=False,
                    potential_finding_severity=_node_severity(node_name),
                    sensitivity=_max_sensitivity(fragment.sensitivity for fragment in fragments),
                ),
                trace_context=TraceContext(
                    request_id=f"startup-provider-{node_name}-{case_uuid}",
                    run_id=f"startup-api-{case_uuid}",
                    case_id=str(case_uuid),
                    correlation_id=str(case_uuid),
                    workflow_type="startup",
                    app_version="capstone-n3",
                    graph_version="startup@1",
                    redaction_policy_version=redaction_policy_version,
                ),
                disclosure_scope=disclosure_scope,
            ),
            timeout_seconds=self._bridge_timeout_seconds,
        )
        response = _provider_response(result)
        source_sensitivity = _max_sensitivity(fragment.sensitivity for fragment in fragments)
        return {
            "findings": [
                item.to_domain(
                    case_id=case_uuid,
                    node_name=node_name,
                    author_model=result.model,
                    sensitivity=source_sensitivity,
                    allowed_fact_ids={fact.id for fact in facts},
                    allowed_calculation_ids={calculation.id for calculation in calculations},
                    fallback_id=self._uuid_factory,
                    created_at=self._clock(),
                )
                for item in response.findings[: self._max_findings]
            ]
        }

    def _select_facts(self, case_id: UUID, requested_ids: tuple[UUID, ...]) -> tuple[EvidenceFact, ...]:
        if not requested_ids:
            return ()
        facts_by_id = {
            fact.id: fact
            for fact in self._evidence_repository.list_for_case(case_id)
            if fact.id in requested_ids
        }
        _ensure_all_found(requested_ids, facts_by_id)
        return tuple(facts_by_id[item] for item in requested_ids)

    def _select_calculations(
        self,
        case_id: UUID,
        requested_ids: tuple[UUID, ...],
    ) -> tuple[Calculation, ...]:
        if not requested_ids:
            return ()
        calculations_by_id = {
            calculation.id: calculation
            for calculation in self._calculation_repository.list_for_case(case_id)
            if calculation.id in requested_ids
        }
        _ensure_all_found(requested_ids, calculations_by_id)
        return tuple(calculations_by_id[item] for item in requested_ids)


class StartupProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    findings: tuple["StartupProviderFinding", ...] = ()


class OpenAIStartupProviderFindingWire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    severity: FindingSeverity
    claim: str
    evidence_fact_ids: tuple[UUID, ...]
    calculation_ids: tuple[UUID, ...]
    confidence: float = Field(ge=0, le=1)


class OpenAIStartupProviderResponseWire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["startup_provider_response@1"]
    findings: tuple[OpenAIStartupProviderFindingWire, ...]


def _provider_response_wire_schema(
    *,
    allowed_fact_ids: tuple[UUID, ...],
    allowed_calculation_ids: tuple[UUID, ...],
) -> type[OpenAIStartupProviderResponseWire]:
    fact_reference_type = _bounded_reference_tuple_type(allowed_fact_ids)
    calculation_reference_type = _bounded_reference_tuple_type(allowed_calculation_ids)
    finding_model = create_model(
        "OpenAIStartupProviderBoundFindingWire",
        __base__=OpenAIStartupProviderFindingWire,
        evidence_fact_ids=(fact_reference_type, ...),
        calculation_ids=(calculation_reference_type, ...),
    )
    response_model = create_model(
        "OpenAIStartupProviderBoundResponseWire",
        __base__=OpenAIStartupProviderResponseWire,
        findings=(GenericAlias(tuple, (finding_model, Ellipsis)), ...),
    )
    return response_model


def _bounded_reference_tuple_type(allowed_ids: tuple[UUID, ...]) -> object:
    if not allowed_ids:
        return Annotated[tuple[str, ...], Field(min_length=0, max_length=0)]
    allowed_values = tuple(str(item) for item in allowed_ids)
    item_type = Literal.__getitem__(allowed_values)
    return GenericAlias(tuple, (item_type, Ellipsis))


class StartupProviderRestrictedContextError(RuntimeError):
    stable_error_code = "STARTUP_PROVIDER_RESTRICTED_CONTEXT"


class StartupProviderContextLimitError(RuntimeError):
    stable_error_code = "STARTUP_PROVIDER_CONTEXT_LIMIT"


class StartupProviderBridgeTimeoutError(TimeoutError):
    stable_error_code = "STARTUP_PROVIDER_BRIDGE_TIMEOUT"


class StartupProviderFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    severity: FindingSeverity
    claim: str
    evidence_fact_ids: tuple[UUID, ...] = ()
    calculation_ids: tuple[UUID, ...] = ()
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("claim")
    @classmethod
    def validate_claim(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("claim is required")
        return normalized[:800]

    def to_domain(
        self,
        *,
        case_id: UUID,
        node_name: str,
        author_model: str,
        sensitivity: SensitivityClass,
        allowed_fact_ids: set[UUID],
        allowed_calculation_ids: set[UUID],
        fallback_id: Callable[[], UUID],
        created_at: datetime,
    ) -> Finding:
        evidence_fact_ids = tuple(item for item in self.evidence_fact_ids if item in allowed_fact_ids)
        calculation_ids = tuple(item for item in self.calculation_ids if item in allowed_calculation_ids)
        if len(evidence_fact_ids) != len(self.evidence_fact_ids) or len(calculation_ids) != len(
            self.calculation_ids
        ):
            raise ValueError("startup_provider_result_reference_not_allowed")
        return Finding(
            id=fallback_id(),
            case_id=case_id,
            category=self.category,
            severity=self.severity,
            claim=self.claim,
            evidence_fact_ids=evidence_fact_ids,
            calculation_ids=calculation_ids,
            confidence=self.confidence,
            status=FindingStatus.REQUIRES_REVIEW,
            author_node=node_name,
            author_model=author_model,
            sensitivity=sensitivity,
            created_at=created_at,
        )


def _fact_fragment(
    fact: EvidenceFact,
    redaction_policy_version: str,
    *,
    redactor: RulesRedactor,
) -> LLMContextFragment:
    safe_name = _safe_text(fact.name, field_name="name", redactor=redactor)
    safe_value = _safe_value(fact.value, field_name=fact.name, redactor=redactor)
    safe_unit = _safe_optional_text(fact.unit, field_name="unit", redactor=redactor) or "n/a"
    safe_period = _safe_optional_text(fact.period, field_name="period", redactor=redactor) or "n/a"
    return LLMContextFragment(
        id=fact.id,
        minimized_text=(
            "EvidenceFact "
            f"id={fact.id} name={safe_name!r} value={safe_value!r} "
            f"value_type={fact.value_type} unit={safe_unit} period={safe_period} "
            f"confidence={fact.confidence} source={_locator_ref(fact)}"
        ),
        sensitivity=fact.sensitivity,
        redacted=(
            fact.sensitivity != SensitivityClass.PUBLIC
            or safe_name != _normalized_text(fact.name)
            or safe_value != _normalized_value(fact.value)
            or safe_unit != (fact.unit or "n/a")
            or safe_period != (fact.period or "n/a")
        ),
        minimized=True,
        redaction_policy_version=redaction_policy_version,
    )


def _is_document_text_block_lineage_marker(fact: EvidenceFact) -> bool:
    return (
        fact.name.startswith("document_text_block_")
        and isinstance(fact.value, str)
        and fact.value.startswith("text_block:")
        and fact.extraction_method == "startup-parsed-document@1"
        and fact.metadata.get("parser_boundary") == "startup_parsed_document"
    )


def _calculation_fragment(
    calculation: Calculation,
    redaction_policy_version: str,
    *,
    redactor: RulesRedactor,
) -> LLMContextFragment:
    safe_metric_name = _safe_text(calculation.metric_name, field_name="metric_name", redactor=redactor)
    safe_unit = _safe_text(calculation.unit, field_name="unit", redactor=redactor)
    safe_period = _safe_text(calculation.period, field_name="period", redactor=redactor)
    safe_warnings = tuple(
        _safe_text(warning, field_name="warning", redactor=redactor)
        for warning in calculation.warnings
    )
    return LLMContextFragment(
        id=calculation.id,
        minimized_text=(
            "Calculation "
            f"id={calculation.id} metric={safe_metric_name!r} value={calculation.value} "
            f"unit={safe_unit} period={safe_period} "
            f"input_fact_ids={[str(item) for item in calculation.input_fact_ids]} "
            f"warnings={list(safe_warnings)}"
        ),
        sensitivity=calculation.sensitivity,
        redacted=(
            calculation.sensitivity != SensitivityClass.PUBLIC
            or safe_metric_name != _normalized_text(calculation.metric_name)
            or safe_unit != _normalized_text(calculation.unit)
            or safe_period != _normalized_text(calculation.period)
            or safe_warnings != tuple(_normalized_text(warning) for warning in calculation.warnings)
        ),
        minimized=True,
        redaction_policy_version=redaction_policy_version,
    )


def _task_prompt(node_name: str) -> str:
    return (
        f"Generate startup due diligence findings for {node_name}. "
        "Use only supplied normalized evidence and calculation identifiers. "
        "Return schema_version='startup_provider_response@1' and concise, "
        "source-backed findings; do not invent facts or unsupported references."
    )


def _node_severity(node_name: str) -> FindingSeverity:
    if node_name == "risk_analysis":
        return FindingSeverity.HIGH
    if node_name == "market_analysis":
        return FindingSeverity.MEDIUM
    return FindingSeverity.MEDIUM


def _safe_value(value: object, *, field_name: str | None = None, redactor: RulesRedactor) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return _safe_text(value, field_name=field_name, redactor=redactor)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    serialized = _serialized_value(value)
    return _safe_text(serialized, field_name=field_name, redactor=redactor)


def _safe_text(text: str, *, field_name: str | None, redactor: RulesRedactor) -> str:
    normalized = _normalized_text(text)
    scan = redactor.detect(normalized, field_name=field_name)
    return scan.redacted_text[:160]


def _safe_optional_text(text: str | None, *, field_name: str | None, redactor: RulesRedactor) -> str | None:
    if text is None:
        return None
    return _safe_text(text, field_name=field_name, redactor=redactor)


def _normalized_text(text: str) -> str:
    return " ".join(text.split())[:160]


def _normalized_value(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return _normalized_text(value)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return _normalized_text(_serialized_value(value))


def _serialized_value(value: object) -> str:
    payload = _json_safe_value(value)
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _json_safe_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal | UUID | datetime):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, Sequence):
        return [_json_safe_value(item) for item in value]
    return {"type": type(value).__name__}


def _uuid_set(values: Sequence[str]) -> set[UUID]:
    return set(_uuid_tuple(values))


def _uuid_tuple(values: Sequence[str], *, excluded: set[UUID] | None = None) -> tuple[UUID, ...]:
    selected: list[UUID] = []
    seen: set[UUID] = set()
    blocked = excluded or set()
    for value in values:
        item = UUID(str(value))
        if item in blocked or item in seen:
            continue
        selected.append(item)
        seen.add(item)
    return tuple(sorted(selected))


def _ensure_all_found(requested_ids: tuple[UUID, ...], records_by_id: dict[UUID, object]) -> None:
    if set(records_by_id) != set(requested_ids):
        raise ValueError("startup_provider_reference_not_found")


def _provider_response(result: StructuredLLMResult[Any]) -> StartupProviderResponse:
    if isinstance(result.data, StartupProviderResponse):
        return result.data
    if isinstance(result.data, BaseModel):
        payload = result.data.model_dump(mode="json")
        payload.pop("schema_version", None)
        return StartupProviderResponse.model_validate(payload)
    return StartupProviderResponse.model_validate(result.data)


def _bounded_fragments(
    fragments: Sequence[LLMContextFragment],
    *,
    max_context_chars: int,
) -> list[LLMContextFragment]:
    if max_context_chars <= 0:
        raise StartupProviderContextLimitError("STARTUP_PROVIDER_CONTEXT_LIMIT")
    bounded: list[LLMContextFragment] = []
    remaining = max_context_chars
    for fragment in fragments:
        text = fragment.minimized_text
        if len(text) > remaining:
            text = text[:remaining]
        bounded.append(fragment.model_copy(update={"minimized_text": text}))
        remaining -= len(text)
        if remaining <= 0 and fragment != fragments[-1]:
            raise StartupProviderContextLimitError("STARTUP_PROVIDER_CONTEXT_LIMIT")
    return bounded


def _redaction_policy_version(disclosure_scope: object | None, *, default: str) -> str:
    versions = getattr(disclosure_scope, "redaction_policy_versions", None)
    if not versions:
        return default
    return sorted(str(version) for version in versions)[0]


def _locator_ref(fact: EvidenceFact) -> str:
    if fact.locator.page is not None:
        return f"{fact.locator.kind}:page:{fact.locator.page}"
    return fact.locator.kind


def _max_sensitivity(values: Iterable[SensitivityClass]) -> SensitivityClass:
    order = {
        SensitivityClass.PUBLIC: 0,
        SensitivityClass.INTERNAL: 1,
        SensitivityClass.CONFIDENTIAL: 2,
        SensitivityClass.RESTRICTED: 3,
    }
    selected = list(values)
    if not selected:
        return SensitivityClass.PUBLIC
    return max(selected, key=lambda item: order[item])


def _run_sync[T](awaitable: Coroutine[Any, Any, T], *, timeout_seconds: float) -> T:
    return _ASYNC_PROVIDER_BRIDGE.run(awaitable, timeout_seconds=timeout_seconds)


async def _with_provider_timeout[T](
    awaitable: Coroutine[Any, Any, T],
    *,
    timeout_seconds: float,
) -> T:
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except TimeoutError as exc:
        raise StartupProviderBridgeTimeoutError("STARTUP_PROVIDER_BRIDGE_TIMEOUT") from exc


class _AsyncProviderBridge:
    def __init__(self) -> None:
        self._lock = Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: Thread | None = None

    def run[T](self, awaitable: Coroutine[Any, Any, T], *, timeout_seconds: float) -> T:
        future = asyncio.run_coroutine_threadsafe(
            _with_provider_timeout(awaitable, timeout_seconds=timeout_seconds),
            self._ensure_loop(),
        )
        try:
            return future.result(timeout=max(timeout_seconds, 0.0) + 0.25)
        except FutureTimeoutError as exc:
            future.cancel()
            raise StartupProviderBridgeTimeoutError("STARTUP_PROVIDER_BRIDGE_TIMEOUT") from exc

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and not self._loop.is_closed():
                return self._loop
            started = Event()
            loop = asyncio.new_event_loop()

            def runner() -> None:
                asyncio.set_event_loop(loop)
                started.set()
                loop.run_forever()

            thread = Thread(
                target=runner,
                name="startup-openai-provider-bridge",
                daemon=True,
            )
            thread.start()
            started.wait(timeout=1.0)
            if not started.is_set():
                raise StartupProviderBridgeTimeoutError("STARTUP_PROVIDER_BRIDGE_TIMEOUT")
            self._loop = loop
            self._thread = thread
            return loop


_ASYNC_PROVIDER_BRIDGE = _AsyncProviderBridge()
