from __future__ import annotations

from typing import Protocol
from uuid import UUID

from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact


class ParsedStartupArtifactRepository(Protocol):
    def add(self, artifact: ParsedStartupArtifact) -> None: ...
    def get_for_case(self, case_id: UUID, artifact_id: UUID) -> ParsedStartupArtifact: ...
    def list_for_case(self, case_id: UUID) -> list[ParsedStartupArtifact]: ...
