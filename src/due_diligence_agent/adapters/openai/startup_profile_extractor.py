from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from decimal import Decimal
from queue import Queue
from threading import Thread
from types import GenericAlias
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, create_model

from due_diligence_agent.adapters.openai.gateway import OpenAISchemaValidationError
from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.domain.common import FindingSeverity, SensitivityClass
from due_diligence_agent.ports.llm import (
    LLMBudgetRequest,
    LLMContextFragment,
    LLMGatewayPort,
    LLMRoutingContext,
    StructuredLLMResult,
)
from due_diligence_agent.ports.startup_profile_extraction import (
    StartupProfileExtractorInvalidOutputError,
    StartupProfileExtractedField,
    StartupProfileExtractionRequest,
    StartupProfileExtractionResponse,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
    StartupProfileSafeRef,
    max_sensitivity,
)
from due_diligence_agent.ports.tracing import TraceContext


_DEFAULT_LATENCY_BUDGET_MS = 60_000
_BRIDGE_SCHEDULING_MARGIN_SECONDS = 15.0


class StartupProfileExtractionRestrictedContextError(RuntimeError):
    stable_error_code = "STARTUP_PROFILE_EXTRACTION_RESTRICTED_CONTEXT"


class StartupProfileExtractionBridgeTimeoutError(TimeoutError):
    stable_error_code = "STARTUP_PROFILE_EXTRACTION_BRIDGE_TIMEOUT"


class OpenAIStartupProfileExtractedFieldWire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field_name: StartupProfileFieldName
    normalized_values: tuple[str, ...]
    status: StartupProfileFieldStatus
    confidence: float
    ref_ids: tuple[str, ...]
    reason_code: str | None


class OpenAIStartupProfileExtractionResponseWire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["startup_profile_extraction_response@1"]
    fields: tuple[OpenAIStartupProfileExtractedFieldWire, ...]
    gap_codes: tuple[str, ...]


def _profile_response_wire_schema(
    request: StartupProfileExtractionRequest,
) -> type[OpenAIStartupProfileExtractionResponseWire]:
    allowed_field_values = tuple(item.value for item in request.allowed_field_names)
    field_name_type = Literal.__getitem__(allowed_field_values)
    ref_ids_type = _bounded_reference_tuple_type(tuple(_request_ref_map(request)))
    field_model = create_model(
        "OpenAIStartupProfileBoundExtractedFieldWire",
        __base__=OpenAIStartupProfileExtractedFieldWire,
        field_name=(field_name_type, ...),
        ref_ids=(ref_ids_type, ...),
    )
    response_model = create_model(
        "OpenAIStartupProfileBoundExtractionResponseWire",
        __base__=OpenAIStartupProfileExtractionResponseWire,
        fields=(GenericAlias(tuple, (field_model, Ellipsis)), ...),
    )
    return response_model


def _bounded_reference_tuple_type(allowed_ids: tuple[UUID, ...]) -> object:
    if not allowed_ids:
        return Annotated[tuple[str, ...], Field(min_length=0, max_length=0)]
    allowed_values = tuple(str(item) for item in allowed_ids)
    item_type = Literal.__getitem__(allowed_values)
    return GenericAlias(tuple, (item_type, Ellipsis))


class OpenAIStartupProfileExtractor:
    def __init__(
        self,
        *,
        gateway: LLMGatewayPort,
        worst_case_tokens: int = 4_000,
        worst_case_usd_cost: Decimal = Decimal("0.05"),
        latency_budget_ms: int = _DEFAULT_LATENCY_BUDGET_MS,
        bridge_timeout_seconds: float | None = None,
    ) -> None:
        if latency_budget_ms < 1:
            raise ValueError("latency_budget_ms must be positive")
        if bridge_timeout_seconds is not None and bridge_timeout_seconds <= 0:
            raise ValueError("bridge_timeout_seconds must be positive")
        self._gateway = gateway
        self._worst_case_tokens = worst_case_tokens
        self._worst_case_usd_cost = worst_case_usd_cost
        self._latency_budget_ms = latency_budget_ms
        # A timeout can route once from the primary attempt to fallback. The sync bridge
        # must therefore cover two provider budgets plus bounded thread scheduling overhead.
        self._bridge_timeout_seconds = bridge_timeout_seconds or (
            (latency_budget_ms / 1_000) * 2 + _BRIDGE_SCHEDULING_MARGIN_SECONDS
        )

    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None = None,
    ) -> StartupProfileExtractionResponse:
        fragments = _llm_fragments(request)
        if any(fragment.sensitivity is SensitivityClass.RESTRICTED for fragment in fragments):
            raise StartupProfileExtractionRestrictedContextError(
                "STARTUP_PROFILE_EXTRACTION_RESTRICTED_CONTEXT"
            )
        expected_schema = _profile_response_wire_schema(request)
        try:
            result: StructuredLLMResult[OpenAIStartupProfileExtractionResponseWire] = _run_sync(
                self._gateway.complete_structured(
                    task=_task_prompt(),
                    fragments=fragments,
                    expected_schema=expected_schema,
                    budget_request=LLMBudgetRequest(
                        case_id=request.case_id,
                        worst_case_tokens=self._worst_case_tokens,
                        worst_case_usd_cost=self._worst_case_usd_cost,
                    ),
                    routing_context=LLMRoutingContext(
                        task_complexity="medium",
                        latency_budget_ms=self._latency_budget_ms,
                        schema_validation_failed=False,
                        potential_finding_severity=FindingSeverity.MEDIUM,
                        sensitivity=max_sensitivity(fragment.sensitivity for fragment in fragments),
                    ),
                trace_context=TraceContext(
                    request_id=f"startup-profile-{request.case_id}",
                    run_id=f"startup-api-{request.case_id}",
                    case_id=str(request.case_id),
                    correlation_id=str(request.case_id),
                        workflow_type="startup",
                        app_version="capstone-n3",
                        graph_version="startup@1",
                        redaction_policy_version=request.redaction_policy_version,
                    ),
                    disclosure_scope=disclosure_scope,
                ),
                timeout_seconds=self._bridge_timeout_seconds,
            )
            response = _profile_response_from_wire(result.data, request=request)
            return response.validate_against_request(request)
        except OpenAISchemaValidationError as exc:
            raise StartupProfileExtractorInvalidOutputError(str(exc)) from exc
        except ValueError as exc:
            raise StartupProfileExtractorInvalidOutputError(str(exc)) from exc


def _llm_fragments(request: StartupProfileExtractionRequest) -> list[LLMContextFragment]:
    fragments = [
        LLMContextFragment(
            id=fragment.fragment_id,
            minimized_text=(
                f"Fragment id={fragment.fragment_id} artifact={fragment.artifact_id} "
                f"artifact_hash={fragment.artifact_hash} locator_hash={fragment.locator_hash}\n"
                f"{fragment.text}"
            ),
            sensitivity=fragment.sensitivity,
            redacted=fragment.redacted,
            minimized=fragment.minimized,
            redaction_policy_version=fragment.redaction_policy_version,
        )
        for fragment in request.fragments
    ]
    fragments.extend(
        LLMContextFragment(
            id=fact.evidence_fact_id,
            minimized_text=(
                "SpreadsheetFact "
                f"id={fact.evidence_fact_id} artifact={fact.artifact_id} "
                f"name={fact.name!r} value={fact.normalized_value!r} value_type={fact.value_type} "
                f"unit={fact.unit or 'n/a'} period={fact.period or 'n/a'} "
                f"artifact_hash={fact.artifact_hash} locator_hash={fact.locator_hash} "
                f"table={fact.table or 'n/a'} cell={fact.cell or 'n/a'} confidence={fact.confidence}"
            ),
            sensitivity=fact.sensitivity,
            redacted=True,
            minimized=True,
            redaction_policy_version=request.redaction_policy_version,
        )
        for fact in request.spreadsheet_facts
    )
    return fragments


def _task_prompt() -> str:
    return (
        "Extract a bounded StartupProfile v1 from only the supplied redacted fragments and "
        "spreadsheet evidence facts. Return only supported allowed fields, normalized values, status, "
        "confidence, compact ref_ids copied from supplied id values, and stable reason/gap codes. "
        "Do not echo ref metadata, invent facts, emit unknown refs, or add one insufficient-data field "
        "for every absent value; summarize missing coverage with gap_codes."
    )


def _profile_response_from_wire(
    response: OpenAIStartupProfileExtractionResponseWire,
    *,
    request: StartupProfileExtractionRequest,
) -> StartupProfileExtractionResponse:
    refs_by_id = _request_ref_map(request)
    fields: list[StartupProfileExtractedField] = []
    for field in response.fields:
        confidence = Decimal(str(field.confidence))
        refs: list[StartupProfileSafeRef] = []
        for raw_ref_id in field.ref_ids:
            ref_id = UUID(str(raw_ref_id))
            try:
                ref = refs_by_id[ref_id]
            except KeyError as exc:
                raise ValueError("startup_profile_result_reference_not_allowed") from exc
            if ref.ref_type == "fragment":
                ref = ref.model_copy(update={"confidence": confidence})
            refs.append(ref)
        fields.append(
            StartupProfileExtractedField(
                field_name=StartupProfileFieldName(field.field_name),
                normalized_values=field.normalized_values,
                status=StartupProfileFieldStatus(field.status),
                confidence=confidence,
                refs=tuple(refs),
                reason_code=field.reason_code,
            )
        )
    return StartupProfileExtractionResponse(
        fields=tuple(fields),
        gap_codes=response.gap_codes,
    )


def _request_ref_map(
    request: StartupProfileExtractionRequest,
) -> dict[UUID, StartupProfileSafeRef]:
    refs_by_id: dict[UUID, StartupProfileSafeRef] = {}

    def add(ref: StartupProfileSafeRef) -> None:
        existing = refs_by_id.get(ref.ref_id)
        if existing is not None and existing != ref:
            raise ValueError("startup_profile_request_reference_collision")
        refs_by_id[ref.ref_id] = ref

    for fragment in request.fragments:
        add(
            StartupProfileSafeRef(
                ref_type="fragment",
                ref_id=fragment.fragment_id,
                artifact_id=fragment.artifact_id,
                artifact_hash=fragment.artifact_hash,
                locator_hash=fragment.locator_hash,
                page=fragment.page,
                table=fragment.table,
                cell=fragment.cell,
            )
        )
    for fact in request.spreadsheet_facts:
        add(
            StartupProfileSafeRef(
                ref_type="evidence_fact",
                ref_id=fact.evidence_fact_id,
                artifact_id=fact.artifact_id,
                artifact_hash=fact.artifact_hash,
                locator_hash=fact.locator_hash,
                table=fact.table,
                cell=fact.cell,
                confidence=fact.confidence,
            )
        )
    for ref in request.allowed_refs:
        add(ref)
    return refs_by_id


def _run_sync[T](awaitable: Coroutine[Any, Any, T], *, timeout_seconds: float) -> T:
    async def with_timeout() -> T:
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise StartupProfileExtractionBridgeTimeoutError(
                "STARTUP_PROFILE_EXTRACTION_BRIDGE_TIMEOUT"
            ) from exc

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(with_timeout())

    queue: Queue[tuple[bool, T | BaseException]] = Queue(maxsize=1)

    def runner() -> None:
        try:
            queue.put((True, asyncio.run(with_timeout())))
        except BaseException as exc:  # pragma: no cover - defensive bridge
            queue.put((False, exc))

    thread = Thread(target=runner, name="startup-openai-profile-bridge", daemon=True)
    thread.start()
    thread.join(timeout=max(timeout_seconds, 0.0) + 0.25)
    if thread.is_alive() or queue.empty():
        raise StartupProfileExtractionBridgeTimeoutError("STARTUP_PROFILE_EXTRACTION_BRIDGE_TIMEOUT")
    ok, payload = queue.get()
    if ok:
        return cast(T, payload)
    if isinstance(payload, BaseException):
        raise payload
    raise RuntimeError("startup_profile_extraction_bridge_failed")
