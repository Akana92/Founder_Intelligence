from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from due_diligence_agent.domain.startup.gtm import (
    StartupGtmDimension,
    StartupGtmDimensionName,
    StartupGtmDimensionStatus,
    StartupGtmExperimentCode,
    StartupGtmHorizon,
    StartupGtmLaunchPhase,
    StartupGtmSnapshot,
    StartupGtmStatus,
)
from due_diligence_agent.domain.startup.market import StartupMarketResearchSnapshot
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
)


@dataclass(frozen=True)
class _DimensionRule:
    fields: tuple[StartupProfileFieldName, ...]
    required_supported: tuple[StartupProfileFieldName, ...]
    product_dimensions: tuple[StartupProductValidationDimensionName, ...] = ()


_RULES: Mapping[StartupGtmDimensionName, _DimensionRule] = {
    StartupGtmDimensionName.AUDIENCE: _DimensionRule(
        fields=(
            StartupProfileFieldName.ICP,
            StartupProfileFieldName.USERS,
            StartupProfileFieldName.BUYERS,
        ),
        required_supported=(StartupProfileFieldName.ICP,),
        product_dimensions=(StartupProductValidationDimensionName.ICP_PRECISION,),
    ),
    StartupGtmDimensionName.GEOGRAPHY: _DimensionRule(
        fields=(StartupProfileFieldName.GEOGRAPHY,),
        required_supported=(StartupProfileFieldName.GEOGRAPHY,),
    ),
    StartupGtmDimensionName.CHANNELS: _DimensionRule(
        fields=(StartupProfileFieldName.CHANNELS_GTM,),
        required_supported=(StartupProfileFieldName.CHANNELS_GTM,),
    ),
    StartupGtmDimensionName.OFFER: _DimensionRule(
        fields=(
            StartupProfileFieldName.BUSINESS_MODEL,
            StartupProfileFieldName.PRICING_REVENUE_MODEL,
        ),
        required_supported=(
            StartupProfileFieldName.BUSINESS_MODEL,
            StartupProfileFieldName.PRICING_REVENUE_MODEL,
        ),
        product_dimensions=(StartupProductValidationDimensionName.WILLINGNESS_TO_PAY,),
    ),
    StartupGtmDimensionName.MARKET_CONTEXT: _DimensionRule(
        fields=(StartupProfileFieldName.COMPETITORS_MENTIONED,),
        required_supported=(StartupProfileFieldName.COMPETITORS_MENTIONED,),
    ),
    StartupGtmDimensionName.PRODUCT_PROOF: _DimensionRule(
        fields=(StartupProfileFieldName.TRACTION,),
        required_supported=(StartupProfileFieldName.TRACTION,),
        product_dimensions=(
            StartupProductValidationDimensionName.EXISTING_CUSTOMER_BEHAVIOR,
            StartupProductValidationDimensionName.VALIDATION_EVIDENCE,
        ),
    ),
    StartupGtmDimensionName.ADOPTION_RISK: _DimensionRule(
        fields=(
            StartupProfileFieldName.WEAKNESSES,
            StartupProfileFieldName.CHANNELS_GTM,
        ),
        required_supported=(StartupProfileFieldName.WEAKNESSES,),
        product_dimensions=(StartupProductValidationDimensionName.ADOPTION_RISK,),
    ),
}


class StartupGtmService:
    def evaluate(
        self,
        profile: StartupProfile,
        *,
        product_validation: StartupProductValidationSnapshot,
        market_research: StartupMarketResearchSnapshot,
        evidence_fact_ids: Sequence[str],
        finding_ids: Sequence[str],
        contradiction_ids: Sequence[str],
    ) -> StartupGtmSnapshot:
        if product_validation.case_id != profile.case_id:
            raise ValueError("product validation belongs to another case")
        if (
            product_validation.profile_id != profile.profile_id
            or product_validation.profile_hash != profile.profile_hash
            or product_validation.profile_revision != profile.data_revision
        ):
            raise ValueError("gtm_product_validation_lineage_mismatch")
        if market_research.case_id != profile.case_id:
            raise ValueError("market research belongs to another case")
        if market_research.data_revision != profile.data_revision:
            raise ValueError("gtm_market_research_lineage_mismatch")
        allowed_evidence = {str(item) for item in evidence_fact_ids}
        allowed_contradictions = {str(item) for item in contradiction_ids}
        product_dimensions = {item.name: item for item in product_validation.dimensions}
        dimensions = tuple(
            self._dimension(
                profile,
                name,
                _RULES[name],
                product_dimensions=product_dimensions,
                market_research=market_research,
                allowed_evidence=allowed_evidence,
                allowed_contradictions=allowed_contradictions,
            )
            for name in StartupGtmDimensionName
        )
        statuses = {item.status for item in dimensions}
        critical = {
            item.name: item.status
            for item in dimensions
            if item.name
            in {
                StartupGtmDimensionName.AUDIENCE,
                StartupGtmDimensionName.CHANNELS,
                StartupGtmDimensionName.OFFER,
            }
        }
        if StartupGtmDimensionStatus.CONTRADICTED in statuses:
            status = StartupGtmStatus.CONTRADICTED
        elif statuses == {StartupGtmDimensionStatus.SUPPORTED}:
            status = StartupGtmStatus.SUPPORTED
        elif statuses == {StartupGtmDimensionStatus.MISSING} or any(
            item is StartupGtmDimensionStatus.MISSING for item in critical.values()
        ):
            status = StartupGtmStatus.INSUFFICIENT
        else:
            status = StartupGtmStatus.PARTIAL
        return StartupGtmSnapshot.build(
            case_id=profile.case_id,
            profile_id=profile.profile_id,
            product_validation_snapshot_id=product_validation.snapshot_id,
            market_research_snapshot_id=market_research.snapshot_id,
            data_revision=profile.data_revision,
            status=status,
            dimensions=dimensions,
            launch_plan=self._launch_plan(dimensions),
            finding_ids=finding_ids,
            built_at=profile.built_at,
        )

    @staticmethod
    def _dimension(
        profile: StartupProfile,
        name: StartupGtmDimensionName,
        rule: _DimensionRule,
        *,
        product_dimensions: Mapping[
            StartupProductValidationDimensionName, StartupProductValidationDimension
        ],
        market_research: StartupMarketResearchSnapshot,
        allowed_evidence: set[str],
        allowed_contradictions: set[str],
    ) -> StartupGtmDimension:
        fields = tuple(profile.fields[field_name.value] for field_name in rule.fields)
        evidence_ids = _available_evidence_ids(fields, allowed_evidence)
        product_items = tuple(
            product_dimensions[dimension]
            for dimension in rule.product_dimensions
            if dimension in product_dimensions
        )
        product_contradictions = {
            contradiction_id
            for item in product_items
            for contradiction_id in item.contradiction_ids
            if contradiction_id in allowed_contradictions
        }
        field_contradictions = {
            str(contradiction_id)
            for field in fields
            for contradiction_id in field.contradiction_ids
            if str(contradiction_id) in allowed_contradictions
        }
        contradiction_refs = tuple(sorted(product_contradictions | field_contradictions))
        market_source_ids = (
            tuple(str(source.source_id) for source in market_research.sources)
            if name is StartupGtmDimensionName.MARKET_CONTEXT
            else ()
        )
        if contradiction_refs:
            status = StartupGtmDimensionStatus.CONTRADICTED
        else:
            supported_fields = {
                field.name
                for field in fields
                if field.status is StartupProfileFieldStatus.SOURCE_FACT
                and _field_has_allowed_evidence(field, allowed_evidence)
            }
            partial_fields = {
                field.name
                for field in fields
                if field.status is StartupProfileFieldStatus.INFERENCE
                and any(str(ref) in allowed_evidence for ref in field.dependency_refs)
            }
            product_statuses = {
                item.status for item in product_items
            }
            if name is StartupGtmDimensionName.MARKET_CONTEXT:
                if market_source_ids and set(rule.required_supported).issubset(supported_fields):
                    status = StartupGtmDimensionStatus.SUPPORTED
                elif market_source_ids or supported_fields or partial_fields:
                    status = StartupGtmDimensionStatus.PARTIAL
                else:
                    status = StartupGtmDimensionStatus.MISSING
            elif set(rule.required_supported).issubset(supported_fields):
                status = StartupGtmDimensionStatus.SUPPORTED
                if StartupProductValidationDimensionStatus.CONTRADICTED in product_statuses:
                    status = StartupGtmDimensionStatus.PARTIAL
                elif (
                    StartupProductValidationDimensionStatus.PARTIAL in product_statuses
                    or StartupProductValidationDimensionStatus.MISSING in product_statuses
                ):
                    status = StartupGtmDimensionStatus.PARTIAL
            elif supported_fields or partial_fields:
                status = StartupGtmDimensionStatus.PARTIAL
            else:
                status = StartupGtmDimensionStatus.MISSING
        return StartupGtmDimension(
            name=name,
            status=status,
            evidence_fact_ids=evidence_ids,
            market_source_ids=market_source_ids,
            contradiction_ids=contradiction_refs,
            reason_code=f"gtm.{status.value}:{name.value}",
            gap_code=f"gtm.missing:{name.value}" if status is StartupGtmDimensionStatus.MISSING else None,
        )

    @staticmethod
    def _launch_plan(
        dimensions: Sequence[StartupGtmDimension],
    ) -> tuple[StartupGtmLaunchPhase, ...]:
        by_name = {item.name: item for item in dimensions}
        day_7: list[StartupGtmExperimentCode] = []
        if any(
            item.status is StartupGtmDimensionStatus.CONTRADICTED
            for item in dimensions
        ):
            day_7.append(StartupGtmExperimentCode.RESOLVE_CONTRADICTIONS)
        if by_name[StartupGtmDimensionName.AUDIENCE].status is not StartupGtmDimensionStatus.SUPPORTED:
            day_7.append(StartupGtmExperimentCode.CLARIFY_AUDIENCE)
        if not day_7:
            day_7.append(StartupGtmExperimentCode.MEASURE_CHANNEL_SIGNAL)

        day_30: list[StartupGtmExperimentCode] = []
        if by_name[StartupGtmDimensionName.GEOGRAPHY].status is not StartupGtmDimensionStatus.SUPPORTED:
            day_30.append(StartupGtmExperimentCode.VALIDATE_GEOGRAPHY)
        if by_name[StartupGtmDimensionName.CHANNELS].status is not StartupGtmDimensionStatus.SUPPORTED:
            day_30.append(StartupGtmExperimentCode.VALIDATE_CHANNEL)
        else:
            day_30.append(StartupGtmExperimentCode.MEASURE_CHANNEL_SIGNAL)

        day_60: list[StartupGtmExperimentCode] = []
        for dimension, code in (
            (StartupGtmDimensionName.OFFER, StartupGtmExperimentCode.VALIDATE_OFFER),
            (
                StartupGtmDimensionName.PRODUCT_PROOF,
                StartupGtmExperimentCode.VALIDATE_PRODUCT_PROOF,
            ),
            (
                StartupGtmDimensionName.MARKET_CONTEXT,
                StartupGtmExperimentCode.VALIDATE_MARKET_POSITIONING,
            ),
            (
                StartupGtmDimensionName.ADOPTION_RISK,
                StartupGtmExperimentCode.VALIDATE_ADOPTION_RISK,
            ),
        ):
            if by_name[dimension].status is not StartupGtmDimensionStatus.SUPPORTED:
                day_60.append(code)

        return (
            StartupGtmLaunchPhase(
                horizon=StartupGtmHorizon.DAY_7,
                experiment_codes=tuple(day_7),
            ),
            StartupGtmLaunchPhase(
                horizon=StartupGtmHorizon.DAY_30,
                experiment_codes=tuple(day_30),
            ),
            StartupGtmLaunchPhase(
                horizon=StartupGtmHorizon.DAY_60,
                experiment_codes=tuple(day_60),
            ),
            StartupGtmLaunchPhase(
                horizon=StartupGtmHorizon.DAY_90,
                experiment_codes=(StartupGtmExperimentCode.REVIEW_LAUNCH_EVIDENCE,),
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


def _field_has_allowed_evidence(
    field: StartupProfileField,
    allowed_evidence: set[str],
) -> bool:
    return any(
        str(reference.evidence_id) in allowed_evidence
        for reference in field.evidence_refs
    )
