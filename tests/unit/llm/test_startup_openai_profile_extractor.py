from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any, TypeVar, TypedDict, cast
from uuid import UUID

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel
from pydantic import ValidationError

from due_diligence_agent.adapters.openai.gateway import OpenAISchemaValidationError
from due_diligence_agent.adapters.openai.startup_profile_extractor import (
    OpenAIStartupProfileExtractionResponseWire,
    OpenAIStartupProfileExtractor,
    StartupProfileExtractionRestrictedContextError,
)
from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.domain.common import FindingSeverity, SensitivityClass
from due_diligence_agent.ports.llm import (
    LLMBudgetRequest,
    LLMContextFragment,
    LLMRoutingContext,
    LLMUsage,
    StructuredLLMResult,
)
from due_diligence_agent.ports.startup_profile_extraction import (
    StartupProfileExtractedField,
    StartupProfileExtractorInvalidOutputError,
    StartupProfileExtractionRequest,
    StartupProfileExtractionResponse,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
    StartupProfileSafeRef,
)
from due_diligence_agent.ports.tracing import TraceContext


CASE_ID = UUID("11111111-1111-4111-8111-111111111111")
ARTIFACT_ID = UUID("22222222-2222-4222-8222-222222222222")
FRAGMENT_ID = UUID("33333333-3333-4333-8333-333333333333")
APPROVAL_ID = UUID("44444444-4444-4444-8444-444444444444")
T = TypeVar("T", bound=BaseModel)


def test_openai_profile_extractor_sends_only_bounded_redacted_fragments_once() -> None:
    private_email = "founder" + "@" + "example.com"
    gateway = RecordingGateway(
        StartupProfileExtractionResponse(
            fields=(
                StartupProfileExtractedField(
                    field_name=StartupProfileFieldName.STARTUP_NAME,
                    normalized_values=("LedgerPilot",),
                    status=StartupProfileFieldStatus.SOURCE_FACT,
                    confidence=Decimal("0.88"),
                    refs=(_safe_ref(),),
                ),
            )
        )
    )

    extractor = OpenAIStartupProfileExtractor(gateway=gateway)
    response = extractor.extract(
        _request("Startup Name: LedgerPilot\nContact [REDACTED:email:1]"),
        disclosure_scope=_scope(),
    )

    assert response.fields[0].normalized_values == ("LedgerPilot",)
    assert response.fields[0].refs == (_safe_ref(),)
    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert issubclass(call["expected_schema"], OpenAIStartupProfileExtractionResponseWire)
    schema = to_strict_json_schema(call["expected_schema"])
    schema_text = str(schema)
    for provider_echo_field in (
        "artifact_id",
        "artifact_hash",
        "locator_hash",
        "page",
        "table",
        "cell",
    ):
        assert provider_echo_field not in schema_text
    assert "ref_ids" in schema_text
    assert not _schema_nodes_with_key(schema, "default")
    for node in _schema_nodes_with_key(schema, "properties"):
        assert node.get("additionalProperties") is False
        required = cast(list[str], node["required"])
        properties = cast(dict[str, object], node["properties"])
        assert set(required) == set(properties)
    assert call["budget_request"].worst_case_tokens == 4000
    assert call["budget_request"].worst_case_usd_cost == Decimal("0.05")
    assert call["routing_context"].latency_budget_ms == 60_000
    assert extractor._bridge_timeout_seconds == 135.0
    assert call["routing_context"].potential_finding_severity is FindingSeverity.MEDIUM
    assert call["trace_context"].redaction_policy_version == "rules-redactor@1"
    dumped = "\n".join(fragment.minimized_text for fragment in call["fragments"])
    assert "LedgerPilot" in dumped
    assert "[REDACTED:email:1]" in dumped
    assert private_email not in dumped
    assert all(fragment.redacted and fragment.minimized for fragment in call["fragments"])


def test_openai_profile_extractor_rejects_model_ref_ids_outside_request_schema() -> None:
    gateway = RecordingGateway(
        StartupProfileExtractionResponse(
            fields=(
                StartupProfileExtractedField(
                    field_name=StartupProfileFieldName.STARTUP_NAME,
                    normalized_values=("LedgerPilot",),
                    status=StartupProfileFieldStatus.SOURCE_FACT,
                    confidence=Decimal("0.88"),
                    refs=(
                        _safe_ref().model_copy(
                            update={"ref_id": UUID("99999999-9999-4999-8999-999999999999")}
                        ),
                    ),
                ),
            )
        )
    )

    with pytest.raises(StartupProfileExtractorInvalidOutputError):
        OpenAIStartupProfileExtractor(gateway=gateway).extract(_request("Startup Name: LedgerPilot"))

    assert len(gateway.calls) == 1


def test_openai_profile_extractor_converts_gateway_schema_failure_to_invalid_output() -> None:
    gateway = SchemaFailureGateway()

    with pytest.raises(StartupProfileExtractorInvalidOutputError, match="SCHEMA_VALIDATION_FAILED"):
        OpenAIStartupProfileExtractor(gateway=gateway).extract(_request("Startup Name: LedgerPilot"))

    assert len(gateway.calls) == 1


def test_openai_profile_extractor_preserves_spreadsheet_fact_sensitivity_for_egress() -> None:
    gateway = RecordingGateway(StartupProfileExtractionResponse(fields=()))
    request = _request(
        "",
        fragments=[],
        spreadsheet_facts=[
            {
                "evidence_fact_id": str(FRAGMENT_ID),
                "artifact_id": str(ARTIFACT_ID),
                "name": "ARR",
                "value_type": "decimal",
                "normalized_value": "120000",
                "unit": "USD",
                "period": "2026",
                "confidence": "0.9",
                "sensitivity": "confidential",
                "artifact_hash": _hash("a"),
                "locator_hash": _hash("c"),
            }
        ],
    )

    OpenAIStartupProfileExtractor(gateway=gateway).extract(request, disclosure_scope=_scope())

    fragments = gateway.calls[0]["fragments"]
    assert len(fragments) == 1
    assert fragments[0].sensitivity is SensitivityClass.CONFIDENTIAL


def test_openai_profile_extractor_rejects_restricted_spreadsheet_fact_before_gateway() -> None:
    gateway = RecordingGateway(StartupProfileExtractionResponse(fields=()))
    request = _request(
        "",
        fragments=[],
        spreadsheet_facts=[
            {
                "evidence_fact_id": str(FRAGMENT_ID),
                "artifact_id": str(ARTIFACT_ID),
                "name": "ARR",
                "value_type": "decimal",
                "normalized_value": "120000",
                "unit": "USD",
                "period": "2026",
                "confidence": "0.9",
                "sensitivity": "restricted",
                "artifact_hash": _hash("a"),
                "locator_hash": _hash("c"),
            }
        ],
    )

    with pytest.raises(StartupProfileExtractionRestrictedContextError):
        OpenAIStartupProfileExtractor(gateway=gateway).extract(request, disclosure_scope=_scope())

    assert gateway.calls == []


@pytest.mark.parametrize(
    "sentinel",
    [
        "founder" + "@" + "example.com",
        "sk" + "-proj-secret",
        "Bearer " + "secret-token",
        "C:" + "\\Users\\Akana\\secret.txt",
        "/" + "home/akana/secret.txt",
    ],
)
def test_openai_profile_extractor_cannot_receive_raw_private_fragment_text(sentinel: str) -> None:
    gateway = RecordingGateway(StartupProfileExtractionResponse(fields=()))

    with pytest.raises(ValidationError) as exc_info:
        OpenAIStartupProfileExtractor(gateway=gateway).extract(
            _request(f"Problem: manual close {sentinel}"),
            disclosure_scope=_scope(),
        )

    message = str(exc_info.value)
    assert "unsafe fragment text" in message
    assert sentinel not in message
    assert gateway.calls == []


class RecordingGateway:
    def __init__(self, response: StartupProfileExtractionResponse) -> None:
        self.response = response
        self.calls: list[GatewayCall] = []

    async def complete_structured(
        self,
        *,
        task: str,
        fragments: Sequence[LLMContextFragment],
        expected_schema: type[T],
        budget_request: LLMBudgetRequest,
        routing_context: LLMRoutingContext,
        trace_context: TraceContext,
        disclosure_scope: Any | None = None,
    ) -> StructuredLLMResult[T]:
        self.calls.append(
            cast(
                GatewayCall,
                {
                "task": task,
                "fragments": fragments,
                "expected_schema": expected_schema,
                "budget_request": budget_request,
                "routing_context": routing_context,
                "trace_context": trace_context,
                "disclosure_scope": disclosure_scope,
                },
            )
        )
        wire_payload = {
            "schema_version": self.response.schema_version,
            "fields": [
                {
                    "field_name": field.field_name.value,
                    "normalized_values": list(field.normalized_values),
                    "status": field.status.value,
                    "confidence": float(field.confidence),
                    "ref_ids": [str(ref.ref_id) for ref in field.refs],
                    "reason_code": field.reason_code,
                }
                for field in self.response.fields
            ],
            "gap_codes": list(self.response.gap_codes),
        }
        return StructuredLLMResult[T](
            data=expected_schema.model_validate(wire_payload),
            provider="openai",
            model="gpt-test",
            role="primary",
            prompt_version="pv-test",
            schema_version="schema-test",
            usage=LLMUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            cost_usd=Decimal("0.001"),
        )


class SchemaFailureGateway:
    def __init__(self) -> None:
        self.calls: list[GatewayCall] = []

    async def complete_structured(
        self,
        *,
        task: str,
        fragments: Sequence[LLMContextFragment],
        expected_schema: type[T],
        budget_request: LLMBudgetRequest,
        routing_context: LLMRoutingContext,
        trace_context: TraceContext,
        disclosure_scope: Any | None = None,
    ) -> StructuredLLMResult[T]:
        self.calls.append(
            cast(
                GatewayCall,
                {
                    "task": task,
                    "fragments": fragments,
                    "expected_schema": expected_schema,
                    "budget_request": budget_request,
                    "routing_context": routing_context,
                    "trace_context": trace_context,
                    "disclosure_scope": disclosure_scope,
                },
            )
        )
        raise OpenAISchemaValidationError("SCHEMA_VALIDATION_FAILED")


class GatewayCall(TypedDict):
    task: str
    fragments: Sequence[LLMContextFragment]
    expected_schema: type[BaseModel]
    budget_request: LLMBudgetRequest
    routing_context: LLMRoutingContext
    trace_context: TraceContext
    disclosure_scope: Any | None


def _request(
    text: str,
    *,
    fragments: list[dict[str, object]] | None = None,
    spreadsheet_facts: list[dict[str, object]] | None = None,
) -> StartupProfileExtractionRequest:
    return StartupProfileExtractionRequest.model_validate(
        {
            "schema_version": "startup_profile_extraction_request@1",
            "case_id": str(CASE_ID),
            "data_revision": 1,
            "allowed_field_names": ["startup_name"],
            "fragments": fragments if fragments is not None else [
                {
                    "fragment_id": str(FRAGMENT_ID),
                    "artifact_id": str(ARTIFACT_ID),
                    "text": text,
                    "text_hash": _hash("b"),
                    "artifact_hash": _hash("a"),
                    "locator_hash": _hash("c"),
                    "sensitivity": "internal",
                    "redacted": True,
                    "minimized": True,
                    "redaction_policy_version": "rules-redactor@1",
                }
            ],
            "spreadsheet_facts": spreadsheet_facts or [],
            "source_hashes": [_hash("a")],
            "egress_policy_version": "egress@1",
            "redaction_policy_version": "rules-redactor@1",
        }
    )


def _safe_ref() -> StartupProfileSafeRef:
    return StartupProfileSafeRef(
        ref_type="fragment",
        ref_id=FRAGMENT_ID,
        artifact_id=ARTIFACT_ID,
        artifact_hash=_hash("a"),
        locator_hash=_hash("c"),
        confidence=Decimal("0.88"),
    )


def _scope() -> DisclosureScope:
    return DisclosureScope(
        approval_id=APPROVAL_ID,
        allowed_classes=frozenset({
            SensitivityClass.PUBLIC,
            SensitivityClass.INTERNAL,
            SensitivityClass.CONFIDENTIAL,
        }),
        destination="openai.responses",
        egress_policy_version="egress@1",
        redaction_policy_versions=frozenset({"rules-redactor@1"}),
    )


def _hash(char: str) -> str:
    return f"sha256:{char * 64}"


def _schema_nodes_with_key(value: object, key: str) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    if isinstance(value, dict):
        if key in value:
            matches.append(value)
        for child in value.values():
            matches.extend(_schema_nodes_with_key(child, key))
    elif isinstance(value, list):
        for child in value:
            matches.extend(_schema_nodes_with_key(child, key))
    return matches
