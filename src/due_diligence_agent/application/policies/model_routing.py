from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from due_diligence_agent.domain.common import FindingSeverity, SensitivityClass
from due_diligence_agent.ports.llm import LLMRoutingContext


class ModelProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model: str
    role: str


class ModelDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model: str
    role: str
    fallback: bool = False


class ModelRoutingPolicy:
    def __init__(
        self,
        *,
        default_profile: ModelProfile | None = None,
        high_reasoning_profile: ModelProfile | None = None,
    ) -> None:
        self.default_profile = default_profile or ModelProfile(
            provider="openai",
            model="gpt-5.6-terra",
            role="structured_analysis",
        )
        self.high_reasoning_profile = high_reasoning_profile or ModelProfile(
            provider="openai",
            model="gpt-5.6-sol",
            role="high_reasoning_verifier",
        )

    def select(
        self,
        routing_context: LLMRoutingContext,
        *,
        fallback: bool = False,
    ) -> ModelDecision:
        high_reasoning = (
            fallback
            or routing_context.schema_validation_failed
            or routing_context.task_complexity in {"high", "critical", "arbiter", "verifier"}
            or routing_context.potential_finding_severity
            in {FindingSeverity.HIGH, FindingSeverity.CRITICAL}
        )
        profile = self.high_reasoning_profile if high_reasoning else self.default_profile
        return ModelDecision(
            provider=profile.provider,
            model=profile.model,
            role=profile.role,
            fallback=fallback,
        )

    def can_external_route(self, routing_context: LLMRoutingContext) -> bool:
        return routing_context.sensitivity is not SensitivityClass.RESTRICTED
