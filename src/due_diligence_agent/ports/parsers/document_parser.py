from typing import Protocol

from due_diligence_agent.domain.artifacts.models import Artifact
from due_diligence_agent.domain.documents.models import ParsedDocument


class DocumentParserPort(Protocol):
    parser_name: str
    parser_version: str

    def parse(self, artifact: Artifact, payload: bytes) -> ParsedDocument: ...
