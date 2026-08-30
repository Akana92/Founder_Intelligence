from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Generic, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic import field_validator

from due_diligence_agent.domain.common import FindingSeverity, SensitivityClass
from due_diligence_agent.ports.tracing import TraceContext

T = TypeVar("T", bound=BaseModel)


class LLMContextFragment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    minimized_text: str
    sensitivity: SensitivityClass
    redacted: bool
    minimized: bool
    redaction_policy_version: str


class LLMRoutingContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_complexity: str
    latency_budget_ms: int
    schema_validation_failed: bool
    potential_finding_severity: FindingSeverity
    sensitivity: SensitivityClass


class LLMBudgetRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    worst_case_tokens: int
    worst_case_usd_cost: Decimal

    @field_validator("worst_case_tokens")
    @classmethod
    def validate_tokens(cls, value: int) -> int:
        if value < 0:
            raise ValueError("budget tokens must be non-negative")
        return value

    @field_validator("worst_case_usd_cost")
    @classmethod
    def validate_cost(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("budget cost must be non-negative")
        return value


class LLMUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @field_validator("input_tokens", "output_tokens", "total_tokens")
    @classmethod
    def validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("usage tokens must be non-negative")
        return value


class StructuredLLMResult(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    data: T
    provider: str
    model: str
    role: str
    prompt_version: str
    schema_version: str
    usage: LLMUsage
    cost_usd: Decimal
    fallback_used: str | None = None
    errors: tuple[str, ...] = ()


class CodeInterpreterResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provisional: bool
    code_hash: str
    code_artifact_id: UUID
    output_artifact_id: UUID
    output_hash: str
    generated_artifact_ids: tuple[UUID, ...] = ()
    canonical_calculation_ids: tuple[UUID, ...] = ()


class LLMGatewayPort(Protocol):
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
    ) -> StructuredLLMResult[T]: ...


class CodeInterpreterPort(Protocol):
    async def run_public_analysis(
        self,
        artifact: Any,
        *,
        code: str,
        budget_request: LLMBudgetRequest,
        routing_context: LLMRoutingContext,
        trace_context: TraceContext,
        disclosure_scope: Any | None = None,
    ) -> CodeInterpreterResult: ...
