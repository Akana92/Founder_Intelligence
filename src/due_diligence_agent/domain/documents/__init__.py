"""Parser-neutral local document contracts."""

from due_diligence_agent.domain.documents.models import (
    ParsedDocument,
    ParsedPage,
    ParsedTable,
    TextBlock,
)
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact

__all__ = [
    "ParsedDocument",
    "ParsedPage",
    "ParsedStartupArtifact",
    "ParsedTable",
    "TextBlock",
]
