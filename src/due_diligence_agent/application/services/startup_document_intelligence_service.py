from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from due_diligence_agent.domain.startup.roles import (
    StartupDocumentIntelligenceSnapshot,
    StartupDocumentIntelligenceStatus,
)


class StartupDocumentIntelligenceService:
    def analyze(
        self,
        *,
        case_id: UUID,
        data_revision: int,
        inventory_id: str,
        source_document_ids: Sequence[str],
        artifact_ids: Sequence[str],
        parsed_artifact_ids: Sequence[str],
        evidence_fact_ids: Sequence[str],
        startup_claim_ids: Sequence[str],
        quarantine_reason_codes: Sequence[str],
    ) -> StartupDocumentIntelligenceSnapshot:
        gaps: list[str] = []
        if not source_document_ids:
            gaps.append("document_intelligence.source_inventory_missing")
        if not artifact_ids:
            gaps.append("document_intelligence.accepted_artifacts_missing")
        if not parsed_artifact_ids:
            gaps.append("document_intelligence.parsed_artifacts_missing")
        elif len(set(parsed_artifact_ids)) < len(set(artifact_ids)):
            gaps.append("document_intelligence.parse_coverage_partial")
        if not evidence_fact_ids:
            gaps.append("document_intelligence.evidence_missing")
        if not startup_claim_ids:
            gaps.append("document_intelligence.claims_missing")
        if quarantine_reason_codes:
            gaps.append("document_intelligence.quarantine_present")

        blocked_codes = {
            "document_intelligence.source_inventory_missing",
            "document_intelligence.accepted_artifacts_missing",
            "document_intelligence.parsed_artifacts_missing",
        }
        if blocked_codes.intersection(gaps):
            status = StartupDocumentIntelligenceStatus.BLOCKED
        elif gaps:
            status = StartupDocumentIntelligenceStatus.PARTIAL
        else:
            status = StartupDocumentIntelligenceStatus.COMPLETE
        return StartupDocumentIntelligenceSnapshot.build(
            case_id=case_id,
            data_revision=data_revision,
            inventory_id=inventory_id,
            source_document_ids=tuple(source_document_ids),
            artifact_ids=tuple(artifact_ids),
            parsed_artifact_ids=tuple(parsed_artifact_ids),
            evidence_fact_ids=tuple(evidence_fact_ids),
            startup_claim_ids=tuple(startup_claim_ids),
            quarantine_reason_codes=tuple(quarantine_reason_codes),
            status=status,
            gap_codes=tuple(gaps),
        )
