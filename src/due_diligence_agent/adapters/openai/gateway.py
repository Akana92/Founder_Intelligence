from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Protocol, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.application.policies.budget import (
    BudgetGuard,
    BudgetReservation,
)
from due_diligence_agent.application.policies.data_egress import (
    DataEgressDenied,
    DataEgressPolicy,
    DisclosureScope,
    EgressFragment,
)
from due_diligence_agent.application.policies.model_routing import (
    ModelDecision,
    ModelRoutingPolicy,
)
from due_diligence_agent.ports.llm import (
    LLMBudgetRequest,
    LLMContextFragment,
    LLMRoutingContext,
    LLMUsage,
    StructuredLLMResult,
)
from due_diligence_agent.ports.tracing import AuditEvent, AuditSpool, TraceContext, TraceSanitizer

T = TypeVar("T", bound=BaseModel)


class AsyncResponsesParseClient(Protocol):
    async def parse(self, **kwargs: object) -> object: ...


class OpenAIAuditPersistenceError(RuntimeError):
    stable_error_code = "AUDIT_PERSISTENCE_ERROR"


class OpenAIMetadataSanitizationError(RuntimeError):
    stable_error_code = "METADATA_SANITIZATION_ERROR"


class OpenAISchemaValidationError(RuntimeError):
    stable_error_code = "SCHEMA_VALIDATION_FAILED"


class OpenAIGateway:
    def __init__(
        self,
        *,
        responses_client: AsyncResponsesParseClient,
        egress_policy: DataEgressPolicy,
        routing_policy: ModelRoutingPolicy,
        budget_guard: BudgetGuard,
        audit_spool: AuditSpool,
        destination: str = "openai.responses",
        prompt_version: str = "pv@1",
        schema_version: str = "schema@1",
        sanitizer: TraceSanitizer | None = None,
        max_output_tokens: int | None = None,
        usage_cost_calculator: Callable[[LLMUsage], Decimal] | None = None,
        llm_call_recorder: Callable[..., None] | None = None,
    ) -> None:
        if max_output_tokens is not None and max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        self._responses = responses_client
        self._egress_policy = egress_policy
        self._routing_policy = routing_policy
        self._budget_guard = budget_guard
        self._audit_spool = audit_spool
        self._destination = destination
        self._prompt_version = prompt_version
        self._schema_version = schema_version
        self._sanitizer = sanitizer or StrictTraceSanitizer()
        self._max_output_tokens = max_output_tokens
        self._usage_cost_calculator = usage_cost_calculator
        self._llm_call_recorder = llm_call_recorder

    async def complete_structured(
        self,
        *,
        task: str,
        fragments: Sequence[LLMContextFragment],
        expected_schema: type[T],
        budget_request: LLMBudgetRequest,
        routing_context: LLMRoutingContext,
        trace_context: TraceContext,
        disclosure_scope: DisclosureScope | None = None,
    ) -> StructuredLLMResult[T]:
        errors: list[str] = []
        repair_used = False

        attempts = ("primary", "schema_repair", "fallback")
        attempt_index = 0
        while attempt_index < len(attempts):
            attempt = attempts[attempt_index]
            fallback = attempt == "fallback"
            schema_retry = attempt != "primary"
            response: object | None = None
            attempt_started = perf_counter()
            prepared = self._prepare_attempt(
                attempt=attempt,
                task=task,
                fragments=fragments,
                budget_request=budget_request,
                routing_context=_routing_for_attempt(routing_context, schema_retry=schema_retry),
                trace_context=trace_context,
                disclosure_scope=disclosure_scope,
                fallback=fallback,
            )
            try:
                metadata = self._provider_metadata(trace_context, prepared.decision, attempt)
                request: dict[str, object] = {
                    "model": prepared.decision.model,
                    "instructions": prepared.task,
                    "input": self._approved_input(fragments),
                    "text_format": expected_schema,
                    "timeout": routing_context.latency_budget_ms / 1_000,
                    "store": False,
                    "metadata": metadata,
                }
                if self._max_output_tokens is not None:
                    request["max_output_tokens"] = self._max_output_tokens
                response = await self._responses.parse(**request)
                parsed_candidate = getattr(response, "output_parsed", None)
                if parsed_candidate is None:
                    raise ValueError("SCHEMA_VALIDATION_FAILED")
                if not isinstance(parsed_candidate, expected_schema):
                    parsed_candidate = expected_schema.model_validate(parsed_candidate)
            except asyncio.CancelledError:
                self._budget_guard.release(prepared.reservation)
                raise
            except ValueError:
                self._settle_schema_failure(prepared.reservation, response)
                self._record_observed_llm_call(
                    prepared=prepared,
                    attempt=attempt,
                    response=response,
                    trace_context=trace_context,
                    evidence_count=len(fragments),
                    attempt_started=attempt_started,
                    status="invalid",
                    error_code="invalid_output",
                )
                if not repair_used:
                    repair_used = True
                    attempt_index = 1
                    continue
                errors.append("SCHEMA_REPAIR_FAILED")
                if fallback:
                    raise OpenAISchemaValidationError("SCHEMA_VALIDATION_FAILED")
                attempt_index = 2
                continue
            except Exception as exc:
                if not _is_timeout_error(exc):
                    self._settle_client_failure(prepared.reservation, response)
                    self._record_observed_llm_call(
                        prepared=prepared,
                        attempt=attempt,
                        response=response,
                        trace_context=trace_context,
                        evidence_count=len(fragments),
                        attempt_started=attempt_started,
                        status="failed",
                        error_code="provider_error",
                    )
                    raise
                self._reconcile_response(prepared.reservation, response)
                self._record_observed_llm_call(
                    prepared=prepared,
                    attempt=attempt,
                    response=response,
                    trace_context=trace_context,
                    evidence_count=len(fragments),
                    attempt_started=attempt_started,
                    status="retry",
                    error_code="timeout",
                )
                if attempt == "schema_repair" and "SCHEMA_REPAIR_FAILED" not in errors:
                    errors.append("SCHEMA_REPAIR_FAILED")
                errors.append("PRIMARY_TIMEOUT" if not fallback else "FALLBACK_TIMEOUT")
                if fallback:
                    raise TimeoutError("FALLBACK_TIMEOUT") from exc
                attempt_index = 2
                continue

            usage = _usage_from_response(response)
            actual_usd_cost = self._actual_usd_cost(usage)
            usage_record = self._budget_guard.reconcile(
                prepared.reservation,
                usage=usage,
                actual_usd_cost=actual_usd_cost,
            )
            self._record_observed_llm_call(
                prepared=prepared,
                attempt=attempt,
                response=response,
                trace_context=trace_context,
                evidence_count=len(fragments),
                attempt_started=attempt_started,
                status="success",
            )
            result_usage = usage or LLMUsage(total_tokens=prepared.reservation.reserved_tokens)
            return StructuredLLMResult[T](
                data=parsed_candidate,
                provider=prepared.decision.provider,
                model=prepared.decision.model,
                role=prepared.decision.role,
                prompt_version=self._prompt_version,
                schema_version=self._schema_version,
                usage=result_usage,
                cost_usd=usage_record.usd_cost,
                fallback_used=prepared.decision.role if fallback else None,
                errors=tuple(errors),
            )
        raise OpenAISchemaValidationError("SCHEMA_VALIDATION_FAILED")

    def _reconcile_response(
        self,
        reservation: BudgetReservation,
        response: object | None,
    ) -> None:
        usage = _usage_from_response(response) if response is not None else None
        self._budget_guard.reconcile(
            reservation,
            usage=usage,
            actual_usd_cost=self._actual_usd_cost(usage),
        )

    def _settle_schema_failure(
        self,
        reservation: BudgetReservation,
        response: object | None,
    ) -> None:
        if response is None:
            self._budget_guard.release(reservation)
            return
        self._reconcile_response(reservation, response)

    def _settle_client_failure(
        self,
        reservation: BudgetReservation,
        response: object | None,
    ) -> None:
        if response is None:
            self._budget_guard.release(reservation)
            return
        self._reconcile_response(reservation, response)

    def _actual_usd_cost(self, usage: LLMUsage | None) -> Decimal | None:
        if usage is None or self._usage_cost_calculator is None:
            return None
        return self._usage_cost_calculator(usage)

    def _record_observed_llm_call(
        self,
        *,
        prepared: _PreparedAttempt,
        attempt: str,
        response: object | None,
        trace_context: TraceContext,
        evidence_count: int,
        attempt_started: float,
        status: str,
        error_code: str | None = None,
    ) -> None:
        if self._llm_call_recorder is None or response is None:
            return
        usage = _usage_from_response(response)
        if usage is None:
            return
        duration_ms = max(0, round((perf_counter() - attempt_started) * 1_000))
        attributes: dict[str, object | None] = {
            "case_id": trace_context.case_id,
            "run_id": trace_context.run_id,
            "correlation_id": trace_context.correlation_id,
            "workflow_type": trace_context.workflow_type,
            "request_id": trace_context.request_id,
            "node_name": "llm_call",
            "agent_role": prepared.decision.role,
            "status": status,
            "attempt": _attempt_number(attempt),
            "retry_count": max(0, _attempt_number(attempt) - 1),
            "provider": prepared.decision.provider,
            "model": prepared.decision.model,
            "tool": "responses.parse",
            "evidence_count": evidence_count,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "schema_version": "startup_llm_call_span@1",
            "duration_ms": duration_ms,
            "latency_ms": duration_ms,
            "checkpoint_id": f"llm-{uuid4().hex}",
        }
        actual_cost = self._actual_usd_cost(usage)
        if actual_cost is not None:
            attributes["cost_usd"] = float(actual_cost)
        if error_code is not None:
            attributes["error_code"] = error_code
        try:
            self._llm_call_recorder(**attributes)
        except Exception:  # noqa: BLE001 - telemetry callbacks must not break LLM calls
            return

    def _prepare_attempt(
        self,
        *,
        attempt: str,
        task: str,
        fragments: Sequence[LLMContextFragment],
        budget_request: LLMBudgetRequest,
        routing_context: LLMRoutingContext,
        trace_context: TraceContext,
        disclosure_scope: DisclosureScope | None,
        fallback: bool,
    ) -> _PreparedAttempt:
        decision = self._egress_policy.evaluate(
            _egress_fragments(fragments),
            destination=self._destination,
            disclosure_scope=disclosure_scope,
        )
        if not decision.allowed:
            raise DataEgressDenied(decision)
        model_decision = self._routing_policy.select(routing_context, fallback=fallback)
        reservation = self._budget_guard.reserve(budget_request, attempt=attempt)
        try:
            self._provider_metadata(trace_context, model_decision, attempt)
        except ValueError as exc:
            self._budget_guard.release(reservation)
            raise OpenAIMetadataSanitizationError("METADATA_SANITIZATION_ERROR") from exc
        try:
            self._audit_spool.append(
                _disclosure_event(
                    trace_context,
                    attributes={
                        "case_id": trace_context.case_id,
                        "correlation_id": trace_context.correlation_id,
                        "provider": model_decision.provider,
                        "model": model_decision.model,
                        "prompt_version": self._prompt_version,
                        "schema_version": self._schema_version,
                        "redaction_policy_version": trace_context.redaction_policy_version,
                        "status": "approved",
                        "attempt": _attempt_number(attempt),
                        "evidence_count": len(fragments),
                    },
                )
            )
        except Exception as exc:
            self._budget_guard.release(reservation)
            raise OpenAIAuditPersistenceError("AUDIT_PERSISTENCE_ERROR") from exc
        return _PreparedAttempt(decision=model_decision, reservation=reservation, task=task)

    def _approved_input(self, fragments: Sequence[LLMContextFragment]) -> str:
        return "\n\n".join(fragment.minimized_text for fragment in fragments)

    def _provider_metadata(
        self,
        trace_context: TraceContext,
        decision: ModelDecision,
        attempt: str,
    ) -> dict[str, str]:
        attributes = {
            "case_id": trace_context.case_id,
            "correlation_id": trace_context.correlation_id,
            "provider": decision.provider,
            "model": decision.model,
            "prompt_version": self._prompt_version,
            "schema_version": self._schema_version,
            "redaction_policy_version": trace_context.redaction_policy_version,
            "attempt": _attempt_number(attempt),
        }
        safe = self._sanitizer.sanitize_attributes(attributes)
        return {key: str(value) for key, value in safe.items() if value is not None}


class _PreparedAttempt(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    decision: ModelDecision
    reservation: BudgetReservation
    task: str


def _egress_fragments(fragments: Sequence[LLMContextFragment]) -> tuple[EgressFragment, ...]:
    return tuple(
        EgressFragment(
            id=fragment.id,
            sensitivity=fragment.sensitivity,
            redacted=fragment.redacted,
            minimized=fragment.minimized,
            redaction_policy_version=fragment.redaction_policy_version,
        )
        for fragment in fragments
    )


def _usage_from_response(response: object) -> LLMUsage | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if isinstance(usage, Mapping):
        return _usage_from_values(
            input_tokens=usage.get("input_tokens", usage.get("prompt_tokens")),
            output_tokens=usage.get("output_tokens", usage.get("completion_tokens")),
            total_tokens=usage.get("total_tokens"),
        )
    return _usage_from_values(
        input_tokens=getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", None)),
        output_tokens=getattr(usage, "output_tokens", getattr(usage, "completion_tokens", None)),
        total_tokens=getattr(usage, "total_tokens", None),
    )


def _usage_from_values(
    *,
    input_tokens: object,
    output_tokens: object,
    total_tokens: object,
) -> LLMUsage | None:
    try:
        if total_tokens is None:
            return None
        return LLMUsage(
            input_tokens=_token_int(input_tokens, default=0),
            output_tokens=_token_int(output_tokens, default=0),
            total_tokens=_token_int(total_tokens),
        )
    except (TypeError, ValueError):
        return None


def _token_int(value: object, *, default: int | None = None) -> int:
    if value is None:
        if default is None:
            raise TypeError("missing token value")
        return default
    if isinstance(value, str | bytes | bytearray):
        return int(value)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return int(value)
    raise TypeError("invalid token value")


def _disclosure_event(
    trace_context: TraceContext,
    *,
    attributes: Mapping[str, str | int | float | bool | None],
) -> AuditEvent:
    return AuditEvent(
        schema_version="audit_event@1",
        event_id=f"event-{uuid4().hex}",
        timestamp_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        run_id=trace_context.run_id,
        correlation_id=trace_context.correlation_id,
        span_name="llm.call",
        event_type="disclosure",
        attributes=attributes,
    )


def _attempt_number(attempt: str) -> int:
    return {"primary": 1, "schema_repair": 2, "fallback": 3}.get(attempt, 0)


def _routing_for_attempt(
    routing_context: LLMRoutingContext,
    *,
    schema_retry: bool,
) -> LLMRoutingContext:
    if not schema_retry:
        return routing_context
    return routing_context.model_copy(update={"schema_validation_failed": True})


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    try:
        from openai import APITimeoutError
    except ImportError:
        return False
    return isinstance(exc, APITimeoutError)
