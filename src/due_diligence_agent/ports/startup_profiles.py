from __future__ import annotations

from typing import Protocol
from uuid import UUID

from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
)


class StartupProfileRepository(Protocol):
    def add(self, profile: StartupProfile) -> None: ...

    def get(self, profile_id: UUID) -> StartupProfile: ...

    def list_for_case(self, case_id: UUID) -> list[StartupProfile]: ...

    def get_for_stage(
        self,
        case_id: UUID,
        data_revision: int,
        stage: StartupProfileAnalysisStage,
    ) -> StartupProfile: ...

    def get_current(self, case_id: UUID) -> StartupProfile: ...
