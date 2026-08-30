from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from due_diligence_agent.domain.common import SensitivityClass


class DisclosureScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: UUID
    allowed_classes: frozenset[SensitivityClass]
    destination: str
    egress_policy_version: str
    redaction_policy_versions: frozenset[str]


class EgressFragment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    sensitivity: SensitivityClass
    redacted: bool
    minimized: bool
    redaction_policy_version: str


class EgressDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    reason: str
    policy_version: str
    allowed_fragment_ids: tuple[str, ...] = Field(default_factory=tuple)
    denied_fragment_ids: tuple[str, ...] = Field(default_factory=tuple)
    approval_id: UUID | None = None


class DataEgressDenied(RuntimeError):
    def __init__(self, decision: EgressDecision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


class DataEgressPolicy:
    version = "egress@1"

    def evaluate(
        self,
        fragments: Sequence[EgressFragment],
        *,
        destination: str,
        disclosure_scope: DisclosureScope | None = None,
    ) -> EgressDecision:
        restricted = _ids_for(fragments, SensitivityClass.RESTRICTED)
        if restricted:
            return self._deny("restricted_data", restricted)

        non_public = tuple(
            fragment for fragment in fragments if fragment.sensitivity is not SensitivityClass.PUBLIC
        )
        if not non_public:
            return self._allow(fragments, disclosure_scope)

        if disclosure_scope is None:
            return self._deny("approval_required", _ids(non_public))
        if disclosure_scope.destination != destination:
            return self._deny("destination_mismatch", _ids(non_public))
        if disclosure_scope.egress_policy_version != self.version:
            return self._deny("egress_policy_mismatch", _ids(non_public))

        classes = frozenset(fragment.sensitivity for fragment in fragments)
        if not classes.issubset(disclosure_scope.allowed_classes):
            return self._deny("approval_required", _ids(non_public))

        versions = frozenset(fragment.redaction_policy_version for fragment in fragments)
        if not versions.issubset(disclosure_scope.redaction_policy_versions):
            return self._deny("redaction_policy_mismatch", _ids(non_public))
        if any(not fragment.redacted for fragment in non_public):
            return self._deny("redaction_required", _ids(non_public))
        if any(not fragment.minimized for fragment in non_public):
            return self._deny("minimization_required", _ids(non_public))

        return self._allow(fragments, disclosure_scope)

    def _allow(
        self,
        fragments: Sequence[EgressFragment],
        disclosure_scope: DisclosureScope | None,
    ) -> EgressDecision:
        return EgressDecision(
            allowed=True,
            reason="public_or_approved",
            policy_version=self.version,
            allowed_fragment_ids=_ids(fragments),
            approval_id=disclosure_scope.approval_id if disclosure_scope else None,
        )

    def _deny(self, reason: str, fragment_ids: tuple[str, ...]) -> EgressDecision:
        return EgressDecision(
            allowed=False,
            reason=reason,
            policy_version=self.version,
            denied_fragment_ids=fragment_ids,
        )


def _ids(fragments: Sequence[EgressFragment]) -> tuple[str, ...]:
    return tuple(str(fragment.id) for fragment in fragments)


def _ids_for(
    fragments: Sequence[EgressFragment],
    sensitivity: SensitivityClass,
) -> tuple[str, ...]:
    return tuple(str(fragment.id) for fragment in fragments if fragment.sensitivity is sensitivity)
