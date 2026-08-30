from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.ports.llm import (
    CodeInterpreterPort,
    CodeInterpreterResult,
    LLMBudgetRequest,
    LLMRoutingContext,
)
from due_diligence_agent.ports.tracing import TraceContext


class StartupCalculationAssistUnavailable(RuntimeError):
    """Stable policy failure raised before any provider call."""


class StartupCalculationAssistArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    content: bytes
    media_type: str
    sensitivity: SensitivityClass
    redacted: bool
    minimized: bool
    redaction_policy_version: str

    @field_validator("media_type", "redaction_policy_version")
    @classmethod
    def validate_safe_token(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 120 or any(character in normalized for character in "\r\n"):
            raise ValueError("artifact metadata must be a bounded token")
        return normalized


class StartupCalculationAssistRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    artifact: StartupCalculationAssistArtifact
    template_id: str
    routing_context: LLMRoutingContext
    trace_context: TraceContext
    network_policy: str = "disabled"

    @field_validator("template_id", "network_policy")
    @classmethod
    def validate_bounded_token(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized or len(normalized) > 80:
            raise ValueError("policy token must be bounded")
        return normalized


class StartupCalculationAssistPolicy:
    DESTINATION = "openai.code_interpreter"
    ALLOWED_TEMPLATES = {
        "unit_economics_summary@1": (
            "import csv, io\n"
            "rows = list(csv.DictReader(io.StringIO(DATA)))\n"
            "print('provisional_rows=' + str(len(rows)))\n"
        ),
    }

    def __init__(self, *, provider: CodeInterpreterPort, enabled: bool = False) -> None:
        self._provider = provider
        self._enabled = enabled

    async def run(
        self,
        request: StartupCalculationAssistRequest,
        *,
        disclosure_scope: DisclosureScope | None,
        budget_request: LLMBudgetRequest,
    ) -> CodeInterpreterResult:
        if not self._enabled:
            raise StartupCalculationAssistUnavailable("calculation_assist_disabled")
        if request.network_policy != "disabled":
            raise StartupCalculationAssistUnavailable("network_policy_must_be_disabled")
        code = self.ALLOWED_TEMPLATES.get(request.template_id)
        if code is None:
            raise StartupCalculationAssistUnavailable("template_not_allowed")
        if disclosure_scope is None:
            raise StartupCalculationAssistUnavailable("disclosure_required")
        if budget_request.worst_case_tokens <= 0 or budget_request.worst_case_usd_cost <= 0:
            raise StartupCalculationAssistUnavailable("budget_required")
        try:
            trace_case_id = UUID(request.trace_context.case_id)
        except ValueError as exc:
            raise StartupCalculationAssistUnavailable("invalid_trace_case_id") from exc
        if budget_request.case_id != trace_case_id:
            raise StartupCalculationAssistUnavailable("budget_case_mismatch")
        artifact = request.artifact
        if not artifact.redacted or not artifact.minimized:
            raise StartupCalculationAssistUnavailable("artifact_not_egress_ready")
        if artifact.sensitivity is SensitivityClass.RESTRICTED:
            raise StartupCalculationAssistUnavailable("restricted_artifact")
        if request.routing_context.sensitivity is not artifact.sensitivity:
            raise StartupCalculationAssistUnavailable("routing_sensitivity_mismatch")
        if disclosure_scope.destination != self.DESTINATION:
            raise StartupCalculationAssistUnavailable("disclosure_destination_mismatch")
        if disclosure_scope.egress_policy_version != DataEgressPolicy.version:
            raise StartupCalculationAssistUnavailable("egress_policy_mismatch")
        if artifact.sensitivity not in disclosure_scope.allowed_classes:
            raise StartupCalculationAssistUnavailable("disclosure_scope_mismatch")
        if artifact.redaction_policy_version not in disclosure_scope.redaction_policy_versions:
            raise StartupCalculationAssistUnavailable("redaction_policy_mismatch")

        result = await self._provider.run_public_analysis(
            _provider_artifact(artifact),
            code=code,
            budget_request=budget_request,
            routing_context=request.routing_context,
            trace_context=request.trace_context,
            disclosure_scope=disclosure_scope,
        )
        if not result.provisional or result.canonical_calculation_ids:
            raise StartupCalculationAssistUnavailable("non_provisional_result_rejected")
        return result


def _provider_artifact(artifact: StartupCalculationAssistArtifact) -> Any:
    """Keep the port adapter-neutral while preserving the structural input contract."""

    return artifact
