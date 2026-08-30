from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from decimal import Decimal
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from due_diligence_agent.application.policies.data_egress import (
    DataEgressPolicy,
    DisclosureScope,
    EgressDecision,
    EgressFragment,
)
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.documents.models import ParsedDocument, ParsedTable, TextBlock
from due_diligence_agent.ports.retrieval import EvidenceChunk, EvidenceIndexPort, RetrievalHit


STARTUP_CHUNK_CONFIG_VERSION = "startup-data-room-chunker@1"
_STARTUP_CHUNK_NAMESPACE = UUID("d44d773f-a43a-4ab5-b614-2d40e4eae80a")
_CHUNK_CONFIG_HASH = sha256(STARTUP_CHUNK_CONFIG_VERSION.encode("utf-8")).hexdigest()


class StartupRetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: UUID
    case_id: UUID
    artifact_id: UUID
    locator: SourceLocator
    content_hash: str
    sensitivity: SensitivityClass
    text_ref: str
    score: float
    text: str | None = Field(default=None, repr=False, exclude=True)


class StartupRetrievalDenied(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __repr__(self) -> str:
        return f"{type(self).__name__}(reason={self.reason!r})"


class StartupRetrievalService:
    def __init__(
        self,
        *,
        index: EvidenceIndexPort,
        text_resolver: Callable[[str], str],
        egress_policy: DataEgressPolicy,
    ) -> None:
        self._index = index
        self._text_resolver = text_resolver
        self._egress_policy = egress_policy
        self.last_egress_decision: EgressDecision | None = None
        self.indexed_chunk_ids: tuple[UUID, ...] = ()

    def build_chunk(
        self,
        *,
        case_id: UUID,
        artifact_id: UUID,
        text_ref: str,
        content_hash: str,
        locator: SourceLocator,
        sensitivity: SensitivityClass,
        parser_confidence: Decimal,
    ) -> EvidenceChunk:
        chunk_id = _chunk_id(
            case_id=case_id,
            artifact_id=artifact_id,
            text_ref=text_ref,
            locator=locator,
            parser_confidence=parser_confidence,
        )
        return EvidenceChunk(
            chunk_id=chunk_id,
            case_id=case_id,
            artifact_id=artifact_id,
            locator=locator.model_copy(update={"artifact_id": artifact_id}),
            content_hash=content_hash,
            sensitivity=sensitivity,
            text_ref=text_ref,
            chunk_config_hash=_CHUNK_CONFIG_HASH,
            chunk_config_version=STARTUP_CHUNK_CONFIG_VERSION,
        )

    def chunks_from_parsed_documents(
        self,
        *,
        case_id: UUID,
        documents: Iterable[ParsedDocument],
        sensitivity_by_text_ref: dict[str, SensitivityClass],
    ) -> tuple[EvidenceChunk, ...]:
        chunks: list[EvidenceChunk] = []
        for document in documents:
            for block in _document_blocks(document):
                chunks.append(
                    self.build_chunk(
                        case_id=case_id,
                        artifact_id=document.artifact_id,
                        text_ref=block.text_ref,
                        content_hash=block.content_hash,
                        locator=block.locator,
                        sensitivity=sensitivity_by_text_ref.get(
                            block.text_ref, SensitivityClass.RESTRICTED
                        ),
                        parser_confidence=block.confidence,
                    )
                )
        return tuple(chunks)

    def index_chunks(
        self,
        chunks: Sequence[EvidenceChunk],
        *,
        no_network: bool = True,
    ) -> None:
        if not no_network:
            raise ValueError("startup retrieval indexing is local-only")
        self._index.index(chunks)
        self.indexed_chunk_ids = tuple(chunk.chunk_id for chunk in chunks)

    def search_for_destination(
        self,
        query: str,
        *,
        destination: Literal["external_llm", "local_analysis"],
        case_id: UUID,
        k: int,
        disclosure_scope: DisclosureScope | None = None,
        query_sensitivity: SensitivityClass | None = None,
        query_redacted: bool = False,
        query_minimized: bool = False,
    ) -> list[StartupRetrievalResult]:
        if not query.strip():
            raise ValueError("blank query")
        if k < 1:
            raise ValueError("invalid k")

        if destination == "external_llm":
            self._gate_external_query(
                query,
                sensitivity=query_sensitivity,
                redacted=query_redacted,
                minimized=query_minimized,
                disclosure_scope=disclosure_scope,
            )

        hits = self._index.search(query, k=k, case_id=case_id)
        results: list[StartupRetrievalResult] = []
        for hit in hits:
            if hit.case_id != case_id:
                raise StartupRetrievalDenied("case_mismatch")
            if not isinstance(hit.sensitivity, SensitivityClass):
                raise StartupRetrievalDenied("missing_sensitivity")
            text = None
            if destination == "external_llm":
                decision = self._egress_policy.evaluate(
                    (_egress_fragment(hit),),
                    destination=destination,
                    disclosure_scope=disclosure_scope,
                )
                self.last_egress_decision = decision
                if not decision.allowed:
                    continue
            else:
                text = self._text_resolver(hit.text_ref)

            results.append(
                StartupRetrievalResult(
                    chunk_id=hit.chunk_id,
                    case_id=hit.case_id,
                    artifact_id=hit.artifact_id,
                    locator=hit.locator,
                    content_hash=hit.content_hash,
                    sensitivity=hit.sensitivity,
                    text_ref=hit.text_ref,
                    score=hit.score,
                    text=text,
                )
            )
        return results

    def _gate_external_query(
        self,
        query: str,
        *,
        sensitivity: SensitivityClass | None,
        redacted: bool,
        minimized: bool,
        disclosure_scope: DisclosureScope | None,
    ) -> None:
        if sensitivity is None:
            raise StartupRetrievalDenied("query_classification_required")
        if sensitivity is SensitivityClass.PUBLIC and _is_bounded_canonical_query(query):
            self.last_egress_decision = self._egress_policy.evaluate(
                (
                    EgressFragment(
                        id=uuid5(_STARTUP_CHUNK_NAMESPACE, sha256(query.encode()).hexdigest()),
                        sensitivity=sensitivity,
                        redacted=True,
                        minimized=True,
                        redaction_policy_version="startup-query@1",
                    ),
                ),
                destination="external_llm",
                disclosure_scope=disclosure_scope,
            )
            if not self.last_egress_decision.allowed:
                raise StartupRetrievalDenied(self.last_egress_decision.reason)
            return
        decision = self._egress_policy.evaluate(
            (
                EgressFragment(
                    id=uuid5(_STARTUP_CHUNK_NAMESPACE, sha256(query.encode()).hexdigest()),
                    sensitivity=sensitivity,
                    redacted=redacted,
                    minimized=minimized,
                    redaction_policy_version="startup-query@1",
                ),
            ),
            destination="external_llm",
            disclosure_scope=disclosure_scope,
        )
        self.last_egress_decision = decision
        if not decision.allowed:
            raise StartupRetrievalDenied(decision.reason)
        if not _is_bounded_canonical_query(query):
            raise StartupRetrievalDenied("unsafe_query")


def _document_blocks(document: ParsedDocument) -> tuple[TextBlock | ParsedTable, ...]:
    blocks: list[TextBlock | ParsedTable] = []
    blocks.extend(document.text_blocks)
    for page in document.pages:
        blocks.extend(page.text_blocks)
    blocks.extend(document.tables)
    return tuple(blocks)


def _chunk_id(
    *,
    case_id: UUID,
    artifact_id: UUID,
    text_ref: str,
    locator: SourceLocator,
    parser_confidence: Decimal,
) -> UUID:
    key = "\x1f".join(
        (
            str(case_id),
            str(artifact_id),
            text_ref,
            locator.kind,
            locator.value,
            str(parser_confidence.normalize()),
            STARTUP_CHUNK_CONFIG_VERSION,
        )
    )
    return uuid5(_STARTUP_CHUNK_NAMESPACE, key)


def _egress_fragment(hit: RetrievalHit) -> EgressFragment:
    return EgressFragment(
        id=hit.chunk_id,
        sensitivity=hit.sensitivity,
        redacted=hit.sensitivity is SensitivityClass.PUBLIC,
        minimized=True,
        redaction_policy_version="startup-redaction@1",
    )


def _is_bounded_canonical_query(query: str) -> bool:
    stripped = query.strip()
    if not stripped or len(stripped) > 80 or stripped != stripped.casefold():
        return False
    return all(char in "abcdefghijklmnopqrstuvwxyz0123456789_ -" for char in stripped)
