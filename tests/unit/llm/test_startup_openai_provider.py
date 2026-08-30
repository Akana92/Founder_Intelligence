from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar, TypedDict, cast
from uuid import UUID, uuid4

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, ValidationError

from due_diligence_agent.adapters.openai.startup_provider import (
    OpenAIStartupProvider,
    StartupProviderBridgeTimeoutError,
    StartupProviderContextLimitError,
    StartupProviderRestrictedContextError,
    StartupProviderResponse,
)
from due_diligence_agent.ports.startup_profile_extraction import StartupProfileExtractionPort
from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import (
    FindingStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.findings.models import Finding
from due_diligence_agent.ports.llm import (
    LLMBudgetRequest,
    LLMContextFragment,
    LLMRoutingContext,
    LLMUsage,
    StructuredLLMResult,
)
from due_diligence_agent.ports.tracing import TraceContext


CASE_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_CASE_ID = UUID("22222222-2222-4222-8222-222222222222")
ARTIFACT_ID = UUID("33333333-3333-4333-8333-333333333333")
REVENUE_FACT_ID = UUID("44444444-4444-4444-8444-444444444444")
COGS_FACT_ID = UUID("55555555-5555-4555-8555-555555555555")
RESTRICTED_FACT_ID = UUID("66666666-6666-4666-8666-666666666666")
OTHER_CASE_CALCULATION_ID = UUID("77777777-7777-4777-8777-777777777777")
GROSS_MARGIN_CALCULATION_ID = UUID("88888888-8888-4888-8888-888888888888")
APPROVAL_ID = UUID("99999999-9999-4999-8999-999999999999")
FINDING_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
T = TypeVar("T", bound=BaseModel)


def test_provider_builds_minimized_fragments_only_from_requested_in_case_records() -> None:
    gateway = RecordingGateway(
        response=ProviderResponseFactory.finding(
            evidence_fact_ids=[REVENUE_FACT_ID],
            calculation_ids=[GROSS_MARGIN_CALCULATION_ID],
        )
    )
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository(
            [
                _fact(REVENUE_FACT_ID, "ARR", Decimal("120000"), "USD", SensitivityClass.PUBLIC),
                _fact(COGS_FACT_ID, "COGS", Decimal("45000"), "USD", SensitivityClass.INTERNAL),
                _fact(RESTRICTED_FACT_ID, "Founder passport", "secret", None, SensitivityClass.RESTRICTED),
            ]
        ),
        calculation_repository=Repository(
            [
                _calculation(GROSS_MARGIN_CALCULATION_ID, CASE_ID),
                _calculation(OTHER_CASE_CALCULATION_ID, OTHER_CASE_ID),
            ]
        ),
        uuid_factory=lambda: FINDING_ID,
        clock=lambda: datetime(2026, 8, 13, tzinfo=UTC),
    )

    result = provider.analyze(
        case_id=str(CASE_ID),
        node_name="financial_analysis",
        disclosure_scope=_scope({SensitivityClass.INTERNAL}, redaction_policy_version="rules-redactor@1"),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID), str(COGS_FACT_ID)],
        remaining_calculation_ids=[str(GROSS_MARGIN_CALCULATION_ID)],
        invalidated_ids=[],
    )

    assert len(gateway.calls) == 1
    fragments = gateway.calls[0]["fragments"]
    assert [fragment.id for fragment in fragments] == [REVENUE_FACT_ID, COGS_FACT_ID, GROSS_MARGIN_CALCULATION_ID]
    assert {fragment.redaction_policy_version for fragment in fragments} == {"rules-redactor@1"}
    dumped = "\n".join(fragment.minimized_text for fragment in fragments)
    assert "ARR" in dumped
    assert "120000" in dumped
    assert "COGS" in dumped
    assert "Founder passport" not in dumped
    assert "secret" not in dumped
    assert "C:\\secret\\pitch.pdf" not in dumped
    assert fragments[1].sensitivity is SensitivityClass.INTERNAL
    assert fragments[1].redacted is True
    assert fragments[1].minimized is True
    finding = result["findings"][0]
    assert finding.case_id == CASE_ID
    assert finding.id == FINDING_ID
    assert finding.evidence_fact_ids == (REVENUE_FACT_ID,)
    assert finding.calculation_ids == (GROSS_MARGIN_CALCULATION_ID,)
    assert finding.author_node == "financial_analysis"
    assert finding.author_model == "gpt-test"
    assert finding.status is FindingStatus.REQUIRES_REVIEW
    assert finding.sensitivity is SensitivityClass.INTERNAL


def test_provider_uses_strict_schema_without_unsupported_defaults() -> None:
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([_fact(REVENUE_FACT_ID)]),
        calculation_repository=Repository([]),
    )

    provider.analyze(
        case_id=str(CASE_ID),
        node_name="market_analysis",
        disclosure_scope=_scope(),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    schema = to_strict_json_schema(gateway.calls[0]["expected_schema"])
    assert not _schema_nodes_with_key(schema, "default")
    for node in _schema_nodes_with_key(schema, "properties"):
        assert node.get("additionalProperties") is False
        required = cast(list[str], node["required"])
        properties = cast(dict[str, object], node["properties"])
        assert set(required) == set(properties)


def test_provider_constrains_response_references_to_requested_records() -> None:
    gateway = RecordingGateway(
        response=ProviderResponseFactory.finding(
            evidence_fact_ids=[REVENUE_FACT_ID],
            calculation_ids=[],
        )
    )
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([_fact(REVENUE_FACT_ID)]),
        calculation_repository=Repository([]),
    )

    provider.analyze(
        case_id=str(CASE_ID),
        node_name="financial_analysis",
        disclosure_scope=_scope(),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    expected_schema = gateway.calls[0]["expected_schema"]
    invalid_response = ProviderResponseFactory.finding(
        evidence_fact_ids=[COGS_FACT_ID],
        calculation_ids=[GROSS_MARGIN_CALCULATION_ID],
    )
    with pytest.raises(ValidationError):
        expected_schema.model_validate(invalid_response)

    validated = expected_schema.model_validate(gateway.response)
    assert validated.findings[0].evidence_fact_ids == (str(REVENUE_FACT_ID),)
    assert validated.findings[0].calculation_ids == ()


def test_provider_redacts_non_public_text_values_before_gateway() -> None:
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository(
            [
                _fact(
                    REVENUE_FACT_ID,
                    "Founder note",
                    "Contact founder@example.com with sk-proj-test-secret after 120000 USD ARR.",
                    None,
                    SensitivityClass.CONFIDENTIAL,
                )
            ]
        ),
        calculation_repository=Repository([]),
    )

    provider.analyze(
        case_id=str(CASE_ID),
        node_name="market_analysis",
        disclosure_scope=_scope({SensitivityClass.CONFIDENTIAL}),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    fragments = gateway.calls[0]["fragments"]
    assert len(fragments) == 1
    fragment_text = fragments[0].minimized_text
    assert fragments[0].redacted is True
    assert "founder@example.com" not in fragment_text
    assert "sk-proj-test-secret" not in fragment_text
    assert "[REDACTED:email:1]" in fragment_text
    assert "[REDACTED:secret:1]" in fragment_text
    assert "120000 USD ARR" in fragment_text


def test_provider_redacts_structured_text_values_before_gateway() -> None:
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository(
            [
                _fact(
                    REVENUE_FACT_ID,
                    "Dataroom metadata",
                    {
                        "arr": 120000,
                        "contact": "founder@example.com",
                        "notes": ["send token sk-proj-test-secret"],
                    },
                    None,
                    SensitivityClass.CONFIDENTIAL,
                )
            ]
        ),
        calculation_repository=Repository([]),
    )

    provider.analyze(
        case_id=str(CASE_ID),
        node_name="market_analysis",
        disclosure_scope=_scope({SensitivityClass.CONFIDENTIAL}),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    fragments = gateway.calls[0]["fragments"]
    assert len(fragments) == 1
    fragment_text = fragments[0].minimized_text
    assert fragments[0].redacted is True
    assert "founder@example.com" not in fragment_text
    assert "sk-proj-test-secret" not in fragment_text
    assert "[REDACTED:email:1]" in fragment_text
    assert "[REDACTED:secret:1]" in fragment_text
    assert "120000" in fragment_text


def test_provider_redacts_human_labels_before_gateway_but_keeps_ids_and_numbers() -> None:
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository(
            [
                _fact(
                    REVENUE_FACT_ID,
                    "ARR owner founder@example.com",
                    Decimal("120000"),
                    "USD",
                    SensitivityClass.CONFIDENTIAL,
                )
            ]
        ),
        calculation_repository=Repository(
            [
                _calculation(
                    GROSS_MARGIN_CALCULATION_ID,
                    CASE_ID,
                    metric_name="margin for sk-proj-test-secret",
                    unit="ratio founder@example.com",
                    period="2026 secret:topsecret",
                    warnings=("Check token sk-proj-warning-secret with founder@example.com",),
                )
            ]
        ),
    )

    provider.analyze(
        case_id=str(CASE_ID),
        node_name="financial_analysis",
        disclosure_scope=_scope({SensitivityClass.CONFIDENTIAL}),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
        remaining_calculation_ids=[str(GROSS_MARGIN_CALCULATION_ID)],
        invalidated_ids=[],
    )

    dumped = "\n".join(fragment.minimized_text for fragment in gateway.calls[0]["fragments"])
    assert "founder@example.com" not in dumped
    assert "sk-proj-test-secret" not in dumped
    assert "sk-proj-warning-secret" not in dumped
    assert "secret:topsecret" not in dumped
    assert "[REDACTED:email:1]" in dumped
    assert "[REDACTED:secret:1]" in dumped
    assert str(REVENUE_FACT_ID) in dumped
    assert str(GROSS_MARGIN_CALCULATION_ID) in dumped
    assert "120000" in dumped
    assert "0.625" in dumped


def test_provider_rejects_unknown_or_out_of_case_references_before_network() -> None:
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([_fact(REVENUE_FACT_ID)]),
        calculation_repository=Repository([_calculation(OTHER_CASE_CALCULATION_ID, OTHER_CASE_ID)]),
    )

    with pytest.raises(ValueError, match="startup_provider_reference_not_found"):
        provider.analyze(
            case_id=str(CASE_ID),
            node_name="financial_analysis",
            disclosure_scope=_scope(),
            remaining_evidence_fact_ids=[str(uuid4())],
            remaining_calculation_ids=[],
            invalidated_ids=[],
        )

    with pytest.raises(ValueError, match="startup_provider_reference_not_found"):
        provider.analyze(
            case_id=str(CASE_ID),
            node_name="financial_analysis",
            disclosure_scope=_scope(),
            remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
            remaining_calculation_ids=[str(OTHER_CASE_CALCULATION_ID)],
            invalidated_ids=[],
        )

    assert gateway.calls == []


def test_provider_rejects_too_many_fragments_before_network() -> None:
    fact_ids = [
        UUID("aaaaaaaa-0000-4000-8000-000000000001"),
        UUID("aaaaaaaa-0000-4000-8000-000000000002"),
        UUID("aaaaaaaa-0000-4000-8000-000000000003"),
    ]
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([_fact(fact_id) for fact_id in fact_ids]),
        calculation_repository=Repository([]),
        max_fragments=2,
    )

    with pytest.raises(StartupProviderContextLimitError, match="STARTUP_PROVIDER_CONTEXT_LIMIT"):
        provider.analyze(
            case_id=str(CASE_ID),
            node_name="financial_analysis",
            disclosure_scope=_scope(),
            remaining_evidence_fact_ids=[str(fact_id) for fact_id in fact_ids],
            remaining_calculation_ids=[],
            invalidated_ids=[],
        )

    assert gateway.calls == []


@pytest.mark.parametrize("node_name", ["financial_analysis", "risk_analysis", "market_analysis"])
def test_provider_excludes_document_text_block_lineage_markers_before_context_limits(
    node_name: str,
) -> None:
    lineage_fact_ids = [
        UUID(f"aaaaaaaa-1000-4000-8000-{index:012d}")
        for index in range(1, 5)
    ]
    lineage_facts = [
        _fact(
            fact_id,
            name=f"document_text_block_{index:03d}",
            value=f"text_block:{index:016x}",
            unit=None,
            sensitivity=SensitivityClass.CONFIDENTIAL,
        ).model_copy(
            update={
                "extraction_method": "startup-parsed-document@1",
                "metadata": {
                    "parser_boundary": "startup_parsed_document",
                    "text_hash": f"sha256:{index}",
                },
            }
        )
        for index, fact_id in enumerate(lineage_fact_ids, start=1)
    ]
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository(
            [
                *lineage_facts,
                _fact(REVENUE_FACT_ID, "gross_margin", Decimal("0.625"), "ratio"),
            ]
        ),
        calculation_repository=Repository([]),
        max_fragments=2,
    )

    result = provider.analyze(
        case_id=str(CASE_ID),
        node_name=node_name,
        disclosure_scope=_scope({SensitivityClass.CONFIDENTIAL}),
        remaining_evidence_fact_ids=[
            *(str(fact_id) for fact_id in lineage_fact_ids),
            str(REVENUE_FACT_ID),
        ],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    assert result["findings"] == []
    assert len(gateway.calls) == 1
    fragments = gateway.calls[0]["fragments"]
    assert [fragment.id for fragment in fragments] == [REVENUE_FACT_ID]
    assert "gross_margin" in fragments[0].minimized_text
    assert "document_text_block" not in fragments[0].minimized_text
    assert "text_block:" not in fragments[0].minimized_text


def test_provider_truncates_minimized_context_and_caps_finding_count() -> None:
    finding_ids = [
        UUID("bbbbbbbb-0000-4000-8000-000000000001"),
        UUID("bbbbbbbb-0000-4000-8000-000000000002"),
    ]
    emitted = iter(finding_ids)
    gateway = RecordingGateway(
        response={
            "schema_version": "startup_provider_response@1",
            "findings": [
                ProviderResponseFactory.finding_payload(
                    evidence_fact_ids=[REVENUE_FACT_ID],
                    calculation_ids=[],
                ),
                ProviderResponseFactory.finding_payload(
                    evidence_fact_ids=[REVENUE_FACT_ID],
                    calculation_ids=[],
                ),
            ]
        }
    )
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository(
            [_fact(REVENUE_FACT_ID, "Long note", "x" * 1_000, None, SensitivityClass.INTERNAL)]
        ),
        calculation_repository=Repository([]),
        uuid_factory=lambda: next(emitted),
        max_context_chars=160,
        max_findings=1,
    )

    result = provider.analyze(
        case_id=str(CASE_ID),
        node_name="risk_analysis",
        disclosure_scope=_scope({SensitivityClass.INTERNAL}),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    fragments = gateway.calls[0]["fragments"]
    assert sum(len(fragment.minimized_text) for fragment in fragments) <= 160
    assert len(result["findings"]) == 1
    assert result["findings"][0].id == finding_ids[0]
    assert result["findings"][0].status is FindingStatus.REQUIRES_REVIEW
    assert result["findings"][0].sensitivity is SensitivityClass.INTERNAL


def test_provider_does_not_call_openai_for_restricted_context() -> None:
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([_fact(RESTRICTED_FACT_ID, sensitivity=SensitivityClass.RESTRICTED)]),
        calculation_repository=Repository([]),
    )

    with pytest.raises(StartupProviderRestrictedContextError, match="STARTUP_PROVIDER_RESTRICTED_CONTEXT"):
        provider.analyze(
            case_id=str(CASE_ID),
            node_name="risk_analysis",
            disclosure_scope=_scope({SensitivityClass.RESTRICTED}),
            remaining_evidence_fact_ids=[str(RESTRICTED_FACT_ID)],
            remaining_calculation_ids=[],
            invalidated_ids=[],
        )

    assert gateway.calls == []


def test_provider_returns_insufficient_data_finding_without_network_when_no_context() -> None:
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([]),
        calculation_repository=Repository([]),
        uuid_factory=lambda: FINDING_ID,
        clock=lambda: datetime(2026, 8, 13, tzinfo=UTC),
    )

    result = provider.analyze(
        case_id=str(CASE_ID),
        node_name="market_analysis",
        disclosure_scope=_scope(),
        remaining_evidence_fact_ids=[],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    assert gateway.calls == []
    finding = result["findings"][0]
    assert finding.status is FindingStatus.INSUFFICIENT_DATA
    assert finding.category == "market_analysis"
    assert finding.evidence_fact_ids == ()
    assert finding.calculation_ids == ()


def test_provider_does_not_implement_profile_extraction_boundary() -> None:
    provider = OpenAIStartupProvider(
        gateway=RecordingGateway(response=ProviderResponseFactory.empty()),
        evidence_repository=Repository([]),
        calculation_repository=Repository([]),
    )

    assert not isinstance(provider, StartupProfileExtractionPort)
    assert not hasattr(provider, "extract")


def test_provider_sync_bridge_works_inside_running_event_loop() -> None:
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([_fact(REVENUE_FACT_ID)]),
        calculation_repository=Repository([]),
    )

    async def run_provider() -> dict[str, list[Finding]]:
        return provider.analyze(
            case_id=str(CASE_ID),
            node_name="financial_analysis",
            disclosure_scope=_scope(),
            remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
            remaining_calculation_ids=[],
            invalidated_ids=[],
        )

    result = asyncio.run(run_provider())

    assert result == {"findings": []}
    assert len(gateway.calls) == 1


def test_provider_uses_live_llm_latency_budget_and_bridge_margin() -> None:
    gateway = RecordingGateway(response=ProviderResponseFactory.empty())
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([_fact(REVENUE_FACT_ID)]),
        calculation_repository=Repository([]),
    )

    provider.analyze(
        case_id=str(CASE_ID),
        node_name="financial_analysis",
        disclosure_scope=_scope(),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    assert gateway.calls[0]["routing_context"].latency_budget_ms == 60_000
    assert provider._bridge_timeout_seconds == 135.0


def test_provider_sync_bridge_times_out_inside_running_event_loop() -> None:
    gateway = HangingGateway()
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([_fact(REVENUE_FACT_ID)]),
        calculation_repository=Repository([]),
        bridge_timeout_seconds=0.01,
    )

    async def run_provider() -> None:
        provider.analyze(
            case_id=str(CASE_ID),
            node_name="financial_analysis",
            disclosure_scope=_scope(),
            remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
            remaining_calculation_ids=[],
            invalidated_ids=[],
        )

    with pytest.raises(StartupProviderBridgeTimeoutError, match="STARTUP_PROVIDER_BRIDGE_TIMEOUT"):
        asyncio.run(run_provider())


def test_provider_sync_bridge_reuses_one_event_loop_for_reused_async_gateway() -> None:
    gateway = LoopBoundGateway()
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=Repository([_fact(REVENUE_FACT_ID)]),
        calculation_repository=Repository([]),
    )

    provider.analyze(
        case_id=str(CASE_ID),
        node_name="financial_analysis",
        disclosure_scope=_scope(),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )
    provider.analyze(
        case_id=str(CASE_ID),
        node_name="risk_analysis",
        disclosure_scope=_scope(),
        remaining_evidence_fact_ids=[str(REVENUE_FACT_ID)],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    assert len(gateway.calls) == 2


class Repository:
    def __init__(self, records: list[object]) -> None:
        self.records = records
        self.case_ids: list[UUID] = []

    def list_for_case(self, case_id: UUID) -> list[object]:
        self.case_ids.append(case_id)
        return [
            record
            for record in self.records
            if getattr(record, "case_id", case_id) == case_id
        ]


class RecordingGateway:
    def __init__(self, *, response: object) -> None:
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
        del task, budget_request, trace_context, disclosure_scope
        self.calls.append(
            {
                "fragments": fragments,
                "expected_schema": expected_schema,
                "routing_context": routing_context,
            }
        )
        response = cast(
            T,
            self.response
            if isinstance(self.response, StartupProviderResponse)
            else expected_schema.model_validate(self.response),
        )
        return StructuredLLMResult[T](
            data=response,
            provider="openai",
            model="gpt-test",
            role="primary",
            prompt_version="pv-test",
            schema_version="schema-test",
            usage=LLMUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            cost_usd=Decimal("0.001"),
        )


class HangingGateway:
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
        del task, fragments, expected_schema, budget_request, routing_context, trace_context, disclosure_scope
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class LoopBoundGateway(RecordingGateway):
    def __init__(self) -> None:
        super().__init__(response=ProviderResponseFactory.empty())
        self._loop: asyncio.AbstractEventLoop | None = None

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
        current_loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = current_loop
        elif self._loop is not current_loop:
            raise RuntimeError("reused_async_client_crossed_event_loop")
        return await super().complete_structured(
            task=task,
            fragments=fragments,
            expected_schema=expected_schema,
            budget_request=budget_request,
            routing_context=routing_context,
            trace_context=trace_context,
            disclosure_scope=disclosure_scope,
        )


class GatewayCall(TypedDict):
    fragments: Sequence[LLMContextFragment]
    expected_schema: type[BaseModel]
    routing_context: LLMRoutingContext


class ProviderResponseFactory:
    @staticmethod
    def empty() -> dict[str, object]:
        return {"schema_version": "startup_provider_response@1", "findings": []}

    @staticmethod
    def finding(
        *,
        evidence_fact_ids: list[UUID],
        calculation_ids: list[UUID],
    ) -> dict[str, object]:
        return {
            "schema_version": "startup_provider_response@1",
            "findings": [
                ProviderResponseFactory.finding_payload(
                    evidence_fact_ids=evidence_fact_ids,
                    calculation_ids=calculation_ids,
                )
            ],
        }

    @staticmethod
    def finding_payload(
        *,
        evidence_fact_ids: list[UUID],
        calculation_ids: list[UUID],
    ) -> dict[str, object]:
        return {
            "category": "unit_economics",
            "severity": "high",
            "claim": "Gross margin needs validation before scaling.",
            "evidence_fact_ids": [str(item) for item in evidence_fact_ids],
            "calculation_ids": [str(item) for item in calculation_ids],
            "confidence": "0.82",
        }


def _fact(
    fact_id: UUID,
    name: str = "ARR",
    value: object = Decimal("120000"),
    unit: str | None = "USD",
    sensitivity: SensitivityClass = SensitivityClass.PUBLIC,
) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id,
        artifact_id=ARTIFACT_ID,
        name=name,
        value=value,
        value_type="decimal" if isinstance(value, Decimal) else "text",
        unit=unit,
        period="2026" if isinstance(value, Decimal) else None,
        locator=SourceLocator(kind="pdf", value="C:\\secret\\pitch.pdf#page=1", artifact_id=ARTIFACT_ID, page=1),
        sensitivity=sensitivity,
        confidence=Decimal("0.90"),
        supporting_text_hash="sha256:fact",
        metadata={},
    )


def _calculation(
    calculation_id: UUID,
    case_id: UUID,
    *,
    metric_name: str = "gross_margin",
    unit: str = "ratio",
    period: str = "2026",
    warnings: tuple[str, ...] = (),
) -> Calculation:
    return Calculation(
        id=calculation_id,
        case_id=case_id,
        metric_name=metric_name,
        formula_version="startup_metric@1",
        input_fact_ids=(REVENUE_FACT_ID, COGS_FACT_ID),
        value=Decimal("0.625"),
        unit=unit,
        period=period,
        warnings=warnings,
        calculated_at=datetime(2026, 8, 13, tzinfo=UTC),
        sensitivity=SensitivityClass.INTERNAL,
    )


def _scope(
    allowed: set[SensitivityClass] | None = None,
    *,
    redaction_policy_version: str = "startup-openai-provider@1",
) -> DisclosureScope:
    return DisclosureScope(
        approval_id=APPROVAL_ID,
        allowed_classes=frozenset(allowed or {SensitivityClass.PUBLIC}),
        destination="openai.responses",
        egress_policy_version="egress@1",
        redaction_policy_versions=frozenset({redaction_policy_version}),
    )


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
