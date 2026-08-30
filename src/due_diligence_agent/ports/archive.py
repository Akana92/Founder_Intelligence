from pathlib import Path
from typing import Protocol

from due_diligence_agent.domain.artifacts.safety import SafetyScanResult


class ArchiveInspectorPort(Protocol):
    def inspect(
        self,
        source: Path,
        *,
        remaining_files: int,
        remaining_unpacked_bytes: int,
    ) -> SafetyScanResult: ...
