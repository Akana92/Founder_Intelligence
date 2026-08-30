from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID

from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import AnalysisMode, ContradictionStatus
from due_diligence_agent.domain.evidence.models import Calculation
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.domain.reports.models import ReportSnapshot
from due_diligence_agent.domain.startup.advisor import (
    StartupImprovementEvidenceKind,
    StartupImprovementEvidenceRef,
    StartupImprovementProposal,
    StartupImprovementTargetArea,
    StartupVersionDelta,
)
from due_diligence_agent.domain.startup.gtm import (
    StartupGtmDimensionStatus,
    StartupGtmSnapshot,
)
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchSourceStatus,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.readiness import (
    StartupReadinessDimensionStatus,
    StartupReadinessSnapshot,
)


class StartupImprovementValidationError(ValueError):
    """The supplied canonical inputs do not share one immutable startup lineage."""


@dataclass(frozen=True)
class _ProposalText:
    recommendation: str
    rationale: str
    expected_effect: str


_UNRESOLVED_CONTRADICTION_STATUSES: Final[frozenset[ContradictionStatus]] = frozenset(
    {
        ContradictionStatus.OPEN,
        ContradictionStatus.AWAITING_EVIDENCE,
        ContradictionStatus.UNRESOLVED,
    }
)


class StartupImprovementService:
    """Creates offline-only proposals and version deltas from canonical startup data."""

    def generate_proposals(
        self,
        *,
        case: DueDiligenceCase,
        base_report_snapshot: ReportSnapshot,
        startup_profile: StartupProfile,
        startup_readiness: StartupReadinessSnapshot | None,
        startup_gtm: StartupGtmSnapshot | None,
        contradictions: Sequence[Contradiction],
        startup_market_research: StartupMarketResearchSnapshot | None,
        calculations: Sequence[Calculation],
        improvement_version: int,
    ) -> tuple[StartupImprovementProposal, ...]:
        self._validate_generation_lineage(
            case=case,
            base_report_snapshot=base_report_snapshot,
            startup_profile=startup_profile,
            startup_readiness=startup_readiness,
            startup_gtm=startup_gtm,
            contradictions=contradictions,
            startup_market_research=startup_market_research,
            calculations=calculations,
        )
        if improvement_version < 1:
            raise StartupImprovementValidationError("invalid_improvement_version")

        evidence = self._evidence_catalogue(
            market_research=startup_market_research,
            calculations=calculations,
        )
        texts = self._proposal_texts(
            profile=startup_profile,
            readiness=startup_readiness,
            gtm=startup_gtm,
            contradictions=contradictions,
            market_research=startup_market_research,
            calculations=calculations,
        )
        confidences = self._proposal_confidences(
            profile=startup_profile,
            readiness=startup_readiness,
            gtm=startup_gtm,
            contradictions=contradictions,
            market_research=startup_market_research,
            calculations=calculations,
        )

        return tuple(
            StartupImprovementProposal.create(
                case_id=case.case_id,
                base_report_snapshot_id=base_report_snapshot.id,
                base_report_snapshot_hash=base_report_snapshot.report_hash,
                base_case_revision=case.data_revision,
                improvement_version=improvement_version,
                target_area=area,
                recommendation_ru=texts[area].recommendation,
                rationale_ru=texts[area].rationale,
                expected_effect_ru=texts[area].expected_effect,
                evidence_refs=self._evidence_for_area(area, evidence),
                confidence=confidences[area],
            )
            for area in StartupImprovementTargetArea
        )

    def apply_decision(
        self,
        *,
        case: DueDiligenceCase,
        base_report_snapshot: ReportSnapshot,
        proposals: Sequence[StartupImprovementProposal],
        previous_version: int,
        accepted_proposal_ids: Sequence[UUID],
        rejected_proposal_ids: Sequence[UUID],
    ) -> StartupVersionDelta:
        self._validate_report_lineage(case=case, base_report_snapshot=base_report_snapshot)
        offered = tuple(proposals)
        offered_ids = tuple(proposal.proposal_id for proposal in offered)
        accepted = tuple(accepted_proposal_ids)
        rejected = tuple(rejected_proposal_ids)

        if len(offered_ids) != len(set(offered_ids)):
            raise StartupImprovementValidationError("duplicate_offered_proposal")
        if len(accepted) != len(set(accepted)) or len(rejected) != len(set(rejected)):
            raise StartupImprovementValidationError("duplicate_decision_id")
        if set(accepted) & set(rejected):
            raise StartupImprovementValidationError("overlap_decision_id")
        if previous_version < 1:
            raise StartupImprovementValidationError("invalid_improvement_version")

        for proposal in offered:
            if proposal.case_id != case.case_id:
                raise StartupImprovementValidationError("cross_case_proposal")
            if proposal.base_case_revision != case.data_revision:
                raise StartupImprovementValidationError("stale_revision_proposal")
            if proposal.base_report_snapshot_id != base_report_snapshot.id:
                raise StartupImprovementValidationError("stale_hash_proposal")
            if proposal.base_report_snapshot_hash != base_report_snapshot.report_hash:
                raise StartupImprovementValidationError("stale_hash_proposal")
            if proposal.improvement_version != previous_version:
                raise StartupImprovementValidationError("stale_improvement_version")

        unknown = (set(accepted) | set(rejected)) - set(offered_ids)
        if unknown:
            raise StartupImprovementValidationError("unknown_proposal_id")

        by_id = {proposal.proposal_id: proposal for proposal in offered}
        changed_fields = tuple(
            sorted({by_id[proposal_id].target_area.value for proposal_id in accepted})
        )
        return StartupVersionDelta(
            case_id=case.case_id,
            base_report_snapshot_id=base_report_snapshot.id,
            base_report_snapshot_hash=base_report_snapshot.report_hash,
            base_case_revision=case.data_revision,
            previous_version=previous_version,
            new_version=previous_version + (1 if accepted else 0),
            accepted_proposal_ids=accepted,
            rejected_proposal_ids=rejected,
            changed_fields=changed_fields,
        )

    @staticmethod
    def _validate_report_lineage(
        *,
        case: DueDiligenceCase,
        base_report_snapshot: ReportSnapshot,
    ) -> None:
        if case.mode is not AnalysisMode.STARTUP:
            raise StartupImprovementValidationError("non_startup_case")
        if base_report_snapshot.case_id != case.case_id:
            raise StartupImprovementValidationError("cross_case_report")
        if base_report_snapshot.data_revision != case.data_revision:
            raise StartupImprovementValidationError("stale_revision_report")

    @classmethod
    def _validate_generation_lineage(
        cls,
        *,
        case: DueDiligenceCase,
        base_report_snapshot: ReportSnapshot,
        startup_profile: StartupProfile,
        startup_readiness: StartupReadinessSnapshot | None,
        startup_gtm: StartupGtmSnapshot | None,
        contradictions: Sequence[Contradiction],
        startup_market_research: StartupMarketResearchSnapshot | None,
        calculations: Sequence[Calculation],
    ) -> None:
        cls._validate_report_lineage(case=case, base_report_snapshot=base_report_snapshot)
        if startup_profile.case_id != case.case_id:
            raise StartupImprovementValidationError("cross_case_profile")
        if startup_profile.data_revision != case.data_revision:
            raise StartupImprovementValidationError("stale_profile")
        if startup_readiness is not None:
            if startup_readiness.profile_id != startup_profile.profile_id:
                raise StartupImprovementValidationError("cross_profile_readiness")
            if startup_readiness.profile_hash != startup_profile.profile_hash:
                raise StartupImprovementValidationError("stale_readiness_hash")
            if startup_readiness.profile_revision != case.data_revision:
                raise StartupImprovementValidationError("stale_readiness")
        if startup_market_research is not None:
            if startup_market_research.case_id != case.case_id:
                raise StartupImprovementValidationError("cross_case_market_research")
            if startup_market_research.data_revision != case.data_revision:
                raise StartupImprovementValidationError("stale_market_research")
        if startup_gtm is not None:
            if startup_gtm.case_id != case.case_id:
                raise StartupImprovementValidationError("cross_case_gtm")
            if startup_gtm.profile_id != startup_profile.profile_id:
                raise StartupImprovementValidationError("cross_profile_gtm")
            if startup_gtm.data_revision != case.data_revision:
                raise StartupImprovementValidationError("stale_gtm")
            if startup_market_research is None:
                raise StartupImprovementValidationError("missing_market_research_for_gtm")
            if startup_gtm.market_research_snapshot_id != startup_market_research.snapshot_id:
                raise StartupImprovementValidationError("stale_gtm_market_research")
        if any(item.case_id != case.case_id for item in contradictions):
            raise StartupImprovementValidationError("cross_case_contradiction")
        if any(item.case_id != case.case_id for item in calculations):
            raise StartupImprovementValidationError("cross_case_calculation")

    @staticmethod
    def _evidence_catalogue(
        *,
        market_research: StartupMarketResearchSnapshot | None,
        calculations: Sequence[Calculation],
    ) -> dict[StartupImprovementEvidenceKind, tuple[StartupImprovementEvidenceRef, ...]]:
        public_facts: tuple[StartupImprovementEvidenceRef, ...] = ()
        live_inference: tuple[StartupImprovementEvidenceRef, ...] = ()
        if market_research is not None:
            public_facts = tuple(
                StartupImprovementEvidenceRef(
                    kind=StartupImprovementEvidenceKind.PUBLIC_FACT,
                    ref_id=source.source_id,
                    confidence=(
                        source.confidence
                        if source.confidence is not None
                        else Decimal("0.65")
                    ),
                )
                for source in market_research.sources
                if source.status is StartupResearchSourceStatus.SOURCE_FACT
            )
            if "live_inference" in market_research.labels:
                live_inference = (
                    StartupImprovementEvidenceRef(
                        kind=StartupImprovementEvidenceKind.LIVE_INFERENCE,
                        ref_id=market_research.snapshot_id,
                        confidence=Decimal("0.55"),
                    ),
                )
        local_calculations = tuple(
            StartupImprovementEvidenceRef(
                kind=StartupImprovementEvidenceKind.LOCAL_CALCULATION,
                ref_id=calculation.id,
                confidence=Decimal("0.80" if not calculation.warnings else "0.60"),
            )
            for calculation in sorted(calculations, key=lambda item: str(item.id))
        )
        return {
            StartupImprovementEvidenceKind.LIVE_INFERENCE: live_inference,
            StartupImprovementEvidenceKind.PUBLIC_FACT: public_facts,
            StartupImprovementEvidenceKind.LOCAL_CALCULATION: local_calculations,
        }

    @staticmethod
    def _evidence_for_area(
        area: StartupImprovementTargetArea,
        evidence: dict[
            StartupImprovementEvidenceKind,
            tuple[StartupImprovementEvidenceRef, ...],
        ],
    ) -> tuple[StartupImprovementEvidenceRef, ...]:
        public_and_inference = (
            evidence[StartupImprovementEvidenceKind.PUBLIC_FACT]
            + evidence[StartupImprovementEvidenceKind.LIVE_INFERENCE]
        )
        local = evidence[StartupImprovementEvidenceKind.LOCAL_CALCULATION]
        if area in {
            StartupImprovementTargetArea.POSITIONING,
            StartupImprovementTargetArea.GTM,
        }:
            return public_and_inference
        if area in {
            StartupImprovementTargetArea.MONETIZATION,
            StartupImprovementTargetArea.METRICS,
            StartupImprovementTargetArea.RISK_REDUCTION,
        }:
            return local
        return public_and_inference + local

    @staticmethod
    def _proposal_texts(
        *,
        profile: StartupProfile,
        readiness: StartupReadinessSnapshot | None,
        gtm: StartupGtmSnapshot | None,
        contradictions: Sequence[Contradiction],
        market_research: StartupMarketResearchSnapshot | None,
        calculations: Sequence[Calculation],
    ) -> dict[StartupImprovementTargetArea, _ProposalText]:
        positioning_supported = _supported_profile_count(
            profile,
            (
                StartupProfileFieldName.PROBLEM,
                StartupProfileFieldName.SOLUTION,
                StartupProfileFieldName.ICP,
                StartupProfileFieldName.GEOGRAPHY,
            ),
        )
        monetization_supported = _supported_profile_count(
            profile,
            (
                StartupProfileFieldName.BUSINESS_MODEL,
                StartupProfileFieldName.PRICING_REVENUE_MODEL,
            ),
        )
        readiness_gaps = _readiness_gap_count(readiness)
        gtm_gaps = _gtm_gap_count(gtm)
        unresolved_risks = sum(
            contradiction.status in _UNRESOLVED_CONTRADICTION_STATUSES
            for contradiction in contradictions
        )
        market_fact_count = sum(
            source.status is StartupResearchSourceStatus.SOURCE_FACT
            for source in market_research.sources
        ) if market_research is not None else 0
        calculation_count = len(calculations)

        return {
            StartupImprovementTargetArea.POSITIONING: _ProposalText(
                recommendation="Соберите позиционирование в одну проверяемую связку: проблема, решение, целевая аудитория и география.",
                rationale=f"В каноническом профиле подтверждено {positioning_supported} из 4 опор позиционирования; публичных фактов рынка: {market_fact_count}.",
                expected_effect="Команда получит более ясную формулировку ценности для клиентов и инвесторов.",
            ),
            StartupImprovementTargetArea.MONETIZATION: _ProposalText(
                recommendation="Зафиксируйте проверяемую гипотезу монетизации и свяжите её с подтверждаемыми единицами экономики.",
                rationale=f"В профиле подтверждено {monetization_supported} из 2 полей монетизации; локальных расчётов: {calculation_count}.",
                expected_effect="Станет проще проверить устойчивость модели дохода без подмены фактов предположениями.",
            ),
            StartupImprovementTargetArea.METRICS: _ProposalText(
                recommendation="Закройте пробелы готовности метрик и назначьте единый набор регулярно пересчитываемых показателей.",
                rationale=f"Канонический снимок готовности содержит {readiness_gaps} неподтверждённых измерений и {calculation_count} локальных расчётов.",
                expected_effect="Прогресс стартапа станет измеримым и воспроизводимым между циклами улучшений.",
            ),
            StartupImprovementTargetArea.GTM: _ProposalText(
                recommendation="Приоритизируйте один проверяемый канал выхода на рынок и свяжите его с этапным планом экспериментов.",
                rationale=f"В каноническом GTM-снимке остаётся {gtm_gaps} неполных измерений; публичных рыночных фактов: {market_fact_count}.",
                expected_effect="Команда сократит распыление и быстрее получит сопоставимый сигнал по каналу привлечения.",
            ),
            StartupImprovementTargetArea.RISK_REDUCTION: _ProposalText(
                recommendation="Разберите открытые противоречия по приоритету и закрепите для каждого проверяемое действие по снижению риска.",
                rationale=f"В канонических данных остаётся {unresolved_risks} нерешённых противоречий; доступно локальных расчётов: {calculation_count}.",
                expected_effect="Критические допущения станут явными, а решение по ним — прослеживаемым.",
            ),
            StartupImprovementTargetArea.INVESTOR_READINESS: _ProposalText(
                recommendation="Соберите инвестиционный пакет вокруг подтверждённых метрик, рыночных фактов и явно отмеченных допущений.",
                rationale=f"Для подготовки доступны {calculation_count} локальных расчётов, {market_fact_count} публичных фактов и {readiness_gaps} пробелов готовности.",
                expected_effect="Инвестор увидит границу между фактами, расчётами и выводами без завышения доказательности.",
            ),
        }

    @staticmethod
    def _proposal_confidences(
        *,
        profile: StartupProfile,
        readiness: StartupReadinessSnapshot | None,
        gtm: StartupGtmSnapshot | None,
        contradictions: Sequence[Contradiction],
        market_research: StartupMarketResearchSnapshot | None,
        calculations: Sequence[Calculation],
    ) -> dict[StartupImprovementTargetArea, Decimal]:
        profile_signal = Decimal(
            _supported_profile_count(profile, tuple(StartupProfileFieldName))
        ) / Decimal(len(StartupProfileFieldName))
        readiness_signal = Decimal("0.40") if readiness is None else Decimal("0.70")
        gtm_signal = Decimal("0.40") if gtm is None else Decimal("0.70")
        market_signal = Decimal("0.40") if market_research is None else Decimal("0.70")
        calculation_signal = Decimal("0.40") if not calculations else Decimal("0.80")
        risk_signal = Decimal("0.55") if contradictions else Decimal("0.70")
        return {
            StartupImprovementTargetArea.POSITIONING: _bounded_confidence((profile_signal + market_signal) / 2),
            StartupImprovementTargetArea.MONETIZATION: _bounded_confidence((profile_signal + calculation_signal) / 2),
            StartupImprovementTargetArea.METRICS: _bounded_confidence((readiness_signal + calculation_signal) / 2),
            StartupImprovementTargetArea.GTM: _bounded_confidence((gtm_signal + market_signal) / 2),
            StartupImprovementTargetArea.RISK_REDUCTION: _bounded_confidence((risk_signal + calculation_signal) / 2),
            StartupImprovementTargetArea.INVESTOR_READINESS: _bounded_confidence(
                (readiness_signal + market_signal + calculation_signal) / 3
            ),
        }


def _supported_profile_count(
    profile: StartupProfile,
    fields: tuple[StartupProfileFieldName, ...],
) -> int:
    return sum(
        profile.fields[field.value].status is StartupProfileFieldStatus.SOURCE_FACT
        for field in fields
    )


def _readiness_gap_count(readiness: StartupReadinessSnapshot | None) -> int:
    if readiness is None:
        return 0
    return sum(
        dimension.status is not StartupReadinessDimensionStatus.READY
        for dimension in readiness.metric_pack.dimensions
    )


def _gtm_gap_count(gtm: StartupGtmSnapshot | None) -> int:
    if gtm is None:
        return 0
    return sum(
        dimension.status is not StartupGtmDimensionStatus.SUPPORTED
        for dimension in gtm.dimensions
    )


def _bounded_confidence(value: Decimal) -> Decimal:
    bounded = min(Decimal("1"), max(Decimal("0"), value))
    return bounded.quantize(Decimal("0.01"))
