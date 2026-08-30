from uuid import UUID

from due_diligence_agent.domain.evidence.ledger import EvidenceLedger
from due_diligence_agent.ports.repositories import (
    ArtifactRepository,
    CalculationRepository,
    ContradictionRepository,
    EvidenceRepository,
    FindingRepository,
)


class EvidenceService:
    def __init__(
        self,
        *,
        artifact_repository: ArtifactRepository,
        evidence_repository: EvidenceRepository,
        contradiction_repository: ContradictionRepository,
        finding_repository: FindingRepository,
        calculation_repository: CalculationRepository,
    ) -> None:
        self._artifact_repository = artifact_repository
        self._evidence_repository = evidence_repository
        self._contradiction_repository = contradiction_repository
        self._finding_repository = finding_repository
        self._calculation_repository = calculation_repository

    def ledger_for_case(self, case_id: UUID) -> EvidenceLedger:
        return EvidenceLedger(
            case_id=case_id,
            artifact_repository=self._artifact_repository,
            evidence_repository=self._evidence_repository,
            contradiction_repository=self._contradiction_repository,
            finding_repository=self._finding_repository,
            calculation_repository=self._calculation_repository,
        )
