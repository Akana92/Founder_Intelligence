from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from due_diligence_agent.application.services.filing_parsing_service import FilingParsingService
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.ports.collectors import FilingArtifact
from due_diligence_agent.ports.repositories import ArtifactStore
from due_diligence_agent.ports.retrieval import (
    EvidenceChunk,
    EvidenceIndexPort,
    RetrievalAuditEvent,
    RetrievalHit,
)


class RetrievalAuditSink:
    def record(self, event: RetrievalAuditEvent) -> None: ...


class RetrievalService:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        parser: FilingParsingService,
        index: EvidenceIndexPort,
        audit_sink: RetrievalAuditSink | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._parser = parser
        self._index = index
        self._audit_sink = audit_sink

    def index_filing(
        self,
        *,
        case_id: UUID,
        filing: FilingArtifact,
        sensitivity: SensitivityClass,
        artifact_id: UUID | None = None,
    ) -> tuple[EvidenceChunk, ...]:
        filing_hash = sha256(filing.content).hexdigest()
        if filing.snapshot.content_hash != filing_hash:
            raise ValueError("filing content hash mismatch")
        stored_filing = self._artifact_store.put_bytes(
            filing.content,
            media_type=filing.snapshot.media_type,
            artifact_id=artifact_id,
            source_snapshot_hash=filing.snapshot.content_hash,
            sensitivity=sensitivity,
        )
        parsed = self._parser.parse(
            case_id=case_id,
            artifact_id=stored_filing.artifact_id,
            filing=filing,
        )
        chunks: list[EvidenceChunk] = []
        for parsed_chunk in parsed:
            stored_chunk = self._artifact_store.put_bytes(
                parsed_chunk.text.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                artifact_id=stored_filing.artifact_id,
                source_snapshot_hash=stored_filing.content_hash,
                sensitivity=sensitivity,
            )
            chunks.append(
                EvidenceChunk(
                    chunk_id=parsed_chunk.chunk_id,
                    case_id=case_id,
                    artifact_id=stored_filing.artifact_id,
                    locator=parsed_chunk.locator.model_copy(
                        update={"artifact_id": stored_filing.artifact_id}
                    ),
                    content_hash=stored_chunk.content_hash,
                    sensitivity=sensitivity,
                    text_ref=stored_chunk.content_hash,
                    chunk_config_hash=parsed_chunk.chunk_config_hash,
                )
            )
        self._index.index(chunks)
        self._record(
            RetrievalAuditEvent(
                event_type="index",
                case_id=case_id,
                artifact_id=stored_filing.artifact_id,
                chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
                content_hashes=tuple(chunk.content_hash for chunk in chunks),
                count=len(chunks),
                status="success",
            )
        )
        return tuple(chunks)

    def search(self, query: str, *, k: int, case_id: UUID) -> list[RetrievalHit]:
        if not query.strip():
            raise ValueError("blank query")
        if k < 1:
            raise ValueError("invalid k")
        hits = self._index.search(query, k=k, case_id=case_id)
        self._record(
            RetrievalAuditEvent(
                event_type="search",
                case_id=case_id,
                chunk_ids=tuple(hit.chunk_id for hit in hits),
                content_hashes=tuple(hit.content_hash for hit in hits),
                count=len(hits),
                k=k,
                status="success",
            )
        )
        return hits

    def _record(self, event: RetrievalAuditEvent) -> None:
        if self._audit_sink is not None:
            self._audit_sink.record(event)
