from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.roles import (
    StartupProductValidationDimension,
    StartupProductValidationDimensionName,
    StartupProductValidationDimensionStatus,
    StartupProductValidationSnapshot,
    StartupProductValidationStatus,
)


@dataclass(frozen=True)
class _DimensionRule:
    fields: tuple[StartupProfileFieldName, ...]
    required_supported: tuple[StartupProfileFieldName, ...]
    indirect_only: bool = False


_RULES: Mapping[StartupProductValidationDimensionName, _DimensionRule] = {
    StartupProductValidationDimensionName.PROBLEM_CLARITY: _DimensionRule(
        fields=(StartupProfileFieldName.PROBLEM,),
        required_supported=(StartupProfileFieldName.PROBLEM,),
    ),
    StartupProductValidationDimensionName.ICP_PRECISION: _DimensionRule(
        fields=(
            StartupProfileFieldName.ICP,
            StartupProfileFieldName.USERS,
            StartupProfileFieldName.BUYERS,
        ),
        required_supported=(StartupProfileFieldName.ICP,),
    ),
    StartupProductValidationDimensionName.PAIN_INTENSITY: _DimensionRule(
        fields=(StartupProfileFieldName.PROBLEM, StartupProfileFieldName.WEAKNESSES),
        required_supported=(),
        indirect_only=True,
    ),
    StartupProductValidationDimensionName.URGENCY: _DimensionRule(
        fields=(
            StartupProfileFieldName.PROBLEM,
            StartupProfileFieldName.TRACTION,
            StartupProfileFieldName.STAGE,
        ),
        required_supported=(),
        indirect_only=True,
    ),
    StartupProductValidationDimensionName.WILLINGNESS_TO_PAY: _DimensionRule(
        fields=(
            StartupProfileFieldName.PRICING_REVENUE_MODEL,
            StartupProfileFieldName.TRACTION,
        ),
        required_supported=(
            StartupProfileFieldName.PRICING_REVENUE_MODEL,
            StartupProfileFieldName.TRACTION,
        ),
    ),
    StartupProductValidationDimensionName.EXISTING_CUSTOMER_BEHAVIOR: _DimensionRule(
        fields=(StartupProfileFieldName.TRACTION,),
        required_supported=(StartupProfileFieldName.TRACTION,),
    ),
    StartupProductValidationDimensionName.ADOPTION_RISK: _DimensionRule(
        fields=(
            StartupProfileFieldName.WEAKNESSES,
            StartupProfileFieldName.CHANNELS_GTM,
        ),
        required_supported=(StartupProfileFieldName.WEAKNESSES,),
    ),
}


class StartupProductValidationService:
    def evaluate(
        self,
        profile: StartupProfile,
        *,
        evidence_fact_ids: Sequence[str],
        startup_claim_ids: Sequence[str],
        claim_status_by_id: Mapping[str, str],
        contradiction_ids: Sequence[str],
    ) -> StartupProductValidationSnapshot:
        allowed_evidence = {str(item) for item in evidence_fact_ids}
        allowed_contradictions = {str(item) for item in contradiction_ids}
        dimensions = [
            self._profile_dimension(
                profile,
                name,
                _RULES[name],
                allowed_evidence=allowed_evidence,
                allowed_contradictions=allowed_contradictions,
            )
            for name in StartupProductValidationDimensionName
            if name is not StartupProductValidationDimensionName.VALIDATION_EVIDENCE
        ]
        dimensions.append(
            self._validation_evidence_dimension(
                evidence_fact_ids=evidence_fact_ids,
                startup_claim_ids=startup_claim_ids,
                claim_status_by_id=claim_status_by_id,
                contradiction_ids=contradiction_ids,
            )
        )
        statuses = {item.status for item in dimensions}
        if StartupProductValidationDimensionStatus.CONTRADICTED in statuses:
            status = StartupProductValidationStatus.CONTRADICTED
        elif statuses == {StartupProductValidationDimensionStatus.SUPPORTED}:
            status = StartupProductValidationStatus.SUPPORTED
        elif statuses == {StartupProductValidationDimensionStatus.MISSING}:
            status = StartupProductValidationStatus.INSUFFICIENT
        else:
            status = StartupProductValidationStatus.PARTIAL
        return StartupProductValidationSnapshot.build(
            case_id=profile.case_id,
            profile_id=profile.profile_id,
            profile_hash=profile.profile_hash,
            profile_revision=profile.data_revision,
            status=status,
            dimensions=tuple(dimensions),
            built_at=profile.built_at,
        )

    @staticmethod
    def _profile_dimension(
        profile: StartupProfile,
        name: StartupProductValidationDimensionName,
        rule: _DimensionRule,
        *,
        allowed_evidence: set[str],
        allowed_contradictions: set[str],
    ) -> StartupProductValidationDimension:
        fields = tuple(profile.fields[field_name.value] for field_name in rule.fields)
        evidence_ids = _available_evidence_ids(fields, allowed_evidence)
        contradiction_ids = _active_contradiction_ids(
            fields,
            allowed_contradictions=allowed_contradictions,
        )
        if contradiction_ids or any(
            field.status is StartupProfileFieldStatus.CONTRADICTION
            and len(
                {
                    str(reference.evidence_id)
                    for reference in field.evidence_refs
                    if str(reference.evidence_id) in allowed_evidence
                }
            )
            >= 2
            for field in fields
        ):
            status = StartupProductValidationDimensionStatus.CONTRADICTED
            reason = f"product_validation.contradiction:{name.value}"
        else:
            supported_fields = {
                field.name
                for field in fields
                if field.status is StartupProfileFieldStatus.SOURCE_FACT
                and _field_has_allowed_evidence(field, allowed_evidence)
            }
            indirect_fields = {
                field.name
                for field in fields
                if field.status is StartupProfileFieldStatus.INFERENCE
                and _field_has_allowed_dependencies(field, allowed_evidence)
            }
            if (
                rule.required_supported
                and set(rule.required_supported).issubset(supported_fields)
                and not rule.indirect_only
            ):
                status = StartupProductValidationDimensionStatus.SUPPORTED
                reason = f"product_validation.evidence:{name.value}"
            elif supported_fields or indirect_fields:
                status = StartupProductValidationDimensionStatus.PARTIAL
                reason = f"product_validation.partial:{name.value}"
            else:
                status = StartupProductValidationDimensionStatus.MISSING
                reason = f"product_validation.missing:{name.value}"
        return StartupProductValidationDimension(
            name=name,
            status=status,
            evidence_fact_ids=evidence_ids,
            startup_claim_ids=(),
            contradiction_ids=contradiction_ids,
            reason_code=reason,
            gap_code=(
                f"product_validation.missing:{name.value}"
                if status is StartupProductValidationDimensionStatus.MISSING
                else None
            ),
        )

    @staticmethod
    def _validation_evidence_dimension(
        *,
        evidence_fact_ids: Sequence[str],
        startup_claim_ids: Sequence[str],
        claim_status_by_id: Mapping[str, str],
        contradiction_ids: Sequence[str],
    ) -> StartupProductValidationDimension:
        claim_ids = tuple(sorted({str(item) for item in startup_claim_ids}))
        evidence_ids = tuple(sorted({str(item) for item in evidence_fact_ids}))
        statuses = {
            str(claim_status_by_id.get(claim_id, "insufficient_data"))
            for claim_id in claim_ids
        }
        name = StartupProductValidationDimensionName.VALIDATION_EVIDENCE
        if "contradicted" in statuses:
            status = StartupProductValidationDimensionStatus.CONTRADICTED
            reason = "product_validation.contradiction:validation_evidence"
        elif "verified" in statuses and evidence_ids:
            status = StartupProductValidationDimensionStatus.SUPPORTED
            reason = "product_validation.evidence:validation_evidence"
        elif claim_ids or evidence_ids:
            status = StartupProductValidationDimensionStatus.PARTIAL
            reason = "product_validation.partial:validation_evidence"
        else:
            status = StartupProductValidationDimensionStatus.MISSING
            reason = "product_validation.missing:validation_evidence"
        return StartupProductValidationDimension(
            name=name,
            status=status,
            evidence_fact_ids=evidence_ids,
            startup_claim_ids=claim_ids,
            contradiction_ids=(
                tuple(sorted({str(item) for item in contradiction_ids}))
                if status is StartupProductValidationDimensionStatus.CONTRADICTED
                else ()
            ),
            reason_code=reason,
            gap_code=(
                "product_validation.missing:validation_evidence"
                if status is StartupProductValidationDimensionStatus.MISSING
                else None
            ),
        )


def _available_evidence_ids(
    fields: Sequence[StartupProfileField],
    allowed_evidence: set[str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(reference.evidence_id)
                for field in fields
                for reference in field.evidence_refs
                if str(reference.evidence_id) in allowed_evidence
            }
        )
    )


def _active_contradiction_ids(
    fields: Sequence[StartupProfileField],
    *,
    allowed_contradictions: set[str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(contradiction_id)
                for field in fields
                for contradiction_id in field.contradiction_ids
                if str(contradiction_id) in allowed_contradictions
            }
        )
    )


def _field_has_allowed_evidence(
    field: StartupProfileField,
    allowed_evidence: set[str],
) -> bool:
    return any(str(reference.evidence_id) in allowed_evidence for reference in field.evidence_refs)


def _field_has_allowed_dependencies(
    field: StartupProfileField,
    allowed_evidence: set[str],
) -> bool:
    return any(str(reference) in allowed_evidence for reference in field.dependency_refs)
