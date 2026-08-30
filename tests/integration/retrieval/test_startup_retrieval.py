from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
from due_diligence_agent.application.services.startup_retrieval_service import (
    StartupRetrievalDenied,
    StartupRetrievalService,
)
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.documents.models import ParsedDocument, TextBlock
from due_diligence_agent.ports.retrieval import RetrievalHit


def test_external_context_excludes_restricted_chunks_and_never_exposes_text() -> None:
    case_id = uuid4()
    cash_ref = sha256(b"cash-ref").hexdigest()
    restricted_ref = sha256(b"restricted-ref").hexdigest()
    resolver = ResolverSpy(
        {
            cash_ref: "cash runway and customer concentration risk",
            restricted_ref: "restricted customer concentration details",
        }
    )
    service = StartupRetrievalService(
        index=FakeIndex(
            [
                _hit(cash_ref, SensitivityClass.PUBLIC, score=0.9, case_id=case_id),
                _hit(restricted_ref, SensitivityClass.RESTRICTED, score=0.99, case_id=case_id),
            ]
        ),
        text_resolver=resolver,
        egress_policy=DataEgressPolicy(),
    )

    results = service.search_for_destination(
        "customer_concentration",
        destination="external_llm",
        case_id=case_id,
        k=5,
        query_sensitivity=SensitivityClass.PUBLIC,
        query_redacted=True,
        query_minimized=True,
    )

    assert results
    assert all(result.sensitivity is not SensitivityClass.RESTRICTED for result in results)
    assert all(result.text is None for result in results)
    assert resolver.calls == []


def test_external_search_does_not_resolve_text_before_egress_denial() -> None:
    case_id = uuid4()
    confidential_ref = sha256(b"confidential-ref").hexdigest()
    service = StartupRetrievalService(
        index=FakeIndex(
            [_hit(confidential_ref, SensitivityClass.CONFIDENTIAL, score=0.9, case_id=case_id)]
        ),
        text_resolver=ResolverSpy({confidential_ref: "confidential customer data"}),
        egress_policy=DataEgressPolicy(),
    )

    results = service.search_for_destination(
        "customer_concentration",
        destination="external_llm",
        case_id=case_id,
        k=5,
        query_sensitivity=SensitivityClass.PUBLIC,
        query_redacted=True,
        query_minimized=True,
    )

    assert results == []
    assert service.last_egress_decision is not None
    assert service.last_egress_decision.reason == "approval_required"


def test_local_search_can_resolve_text_without_leaking_in_model_repr() -> None:
    case_id = uuid4()
    public_ref = sha256(b"public-ref").hexdigest()
    resolver = ResolverSpy({public_ref: "cash runway is 9.5 months"})
    service = StartupRetrievalService(
        index=FakeIndex([_hit(public_ref, SensitivityClass.PUBLIC, score=0.9, case_id=case_id)]),
        text_resolver=resolver,
        egress_policy=DataEgressPolicy(),
    )

    [result] = service.search_for_destination(
        "cash runway",
        destination="local_analysis",
        case_id=case_id,
        k=1,
    )

    assert result.text == "cash runway is 9.5 months"
    assert "cash runway" not in repr(result)
    assert "cash runway" not in result.model_dump_json(exclude={"text"})
    assert resolver.calls == [public_ref]


def test_external_query_is_egress_checked_before_index_search_or_embedding() -> None:
    index = FakeIndex([_hit(sha256(b"public-ref").hexdigest(), SensitivityClass.PUBLIC, score=0.9)])
    service = StartupRetrievalService(
        index=index,
        text_resolver=ResolverSpy({}),
        egress_policy=DataEgressPolicy(),
    )

    try:
        service.search_for_destination(
            "Acme customer founder@example.com concentration",
            destination="external_llm",
            case_id=uuid4(),
            k=5,
            query_sensitivity=SensitivityClass.CONFIDENTIAL,
            query_redacted=False,
            query_minimized=False,
        )
    except StartupRetrievalDenied as exc:
        payload = repr(exc) + str(exc)
        assert "Acme" not in payload
        assert "founder@example.com" not in payload
    else:
        raise AssertionError("external query should be denied before search")

    assert index.search_calls == []


def test_external_query_missing_classification_fails_closed_before_index_search() -> None:
    index = FakeIndex([])
    service = StartupRetrievalService(
        index=index,
        text_resolver=ResolverSpy({}),
        egress_policy=DataEgressPolicy(),
    )

    try:
        service.search_for_destination(
            "customer_concentration",
            destination="external_llm",
            case_id=uuid4(),
            k=5,
        )
    except StartupRetrievalDenied as exc:
        assert exc.reason == "query_classification_required"
    else:
        raise AssertionError("missing query classification should fail closed")

    assert index.search_calls == []


def test_missing_chunk_sensitivity_fails_closed_before_return_or_resolution() -> None:
    public_ref = sha256(b"public-ref").hexdigest()
    hit = _hit(public_ref, SensitivityClass.PUBLIC, score=0.9).model_copy(
        update={"sensitivity": None}
    )
    resolver = ResolverSpy({public_ref: "cash runway is 9.5 months"})
    service = StartupRetrievalService(
        index=FakeIndex([hit]),
        text_resolver=resolver,
        egress_policy=DataEgressPolicy(),
    )

    try:
        service.search_for_destination(
            "cash_runway",
            destination="local_analysis",
            case_id=hit.case_id,
            k=1,
        )
    except StartupRetrievalDenied as exc:
        assert exc.reason == "missing_sensitivity"
    else:
        raise AssertionError("missing hit sensitivity should fail closed")

    assert resolver.calls == []


def test_case_mismatch_hit_fails_closed_before_return_or_resolution() -> None:
    requested_case_id = uuid4()
    public_ref = sha256(b"public-ref").hexdigest()
    hit = _hit(public_ref, SensitivityClass.PUBLIC, score=0.9, case_id=uuid4())
    resolver = ResolverSpy({public_ref: "cash runway is 9.5 months"})
    service = StartupRetrievalService(
        index=FakeIndex([hit]),
        text_resolver=resolver,
        egress_policy=DataEgressPolicy(),
    )

    try:
        service.search_for_destination(
            "cash_runway",
            destination="local_analysis",
            case_id=requested_case_id,
            k=1,
        )
    except StartupRetrievalDenied as exc:
        assert exc.reason == "case_mismatch"
    else:
        raise AssertionError("case-mismatched hit should fail closed")

    assert resolver.calls == []


def test_chunks_from_parsed_documents_have_stable_ids_hashes_and_locators() -> None:
    artifact_id = uuid4()
    case_id = uuid4()
    text_hash = sha256(b"ARR is 1.8M").hexdigest()
    parsed = ParsedDocument(
        artifact_id=artifact_id,
        detected_mime_type="application/pdf",
        text_blocks=[
            TextBlock(
                text_ref=text_hash,
                content_hash=text_hash,
                char_count=12,
                locator=SourceLocator(
                    kind="pdf_text", value="page:1:block:1", artifact_id=artifact_id, page=1
                ),
                confidence=Decimal("0.91"),
                verification_status="candidate",
            )
        ],
        parser_name="fixture",
        parser_version="1",
        confidence=Decimal("0.91"),
        status="parsed",
    )
    service = StartupRetrievalService(
        index=FakeIndex([]),
        text_resolver=ResolverSpy({text_hash: "ARR is 1.8M"}),
        egress_policy=DataEgressPolicy(),
    )

    first = service.chunks_from_parsed_documents(
        case_id=case_id,
        documents=[parsed],
        sensitivity_by_text_ref={text_hash: SensitivityClass.PUBLIC},
    )
    second = service.chunks_from_parsed_documents(
        case_id=case_id,
        documents=[parsed],
        sensitivity_by_text_ref={text_hash: SensitivityClass.PUBLIC},
    )

    assert first == second
    assert first[0].content_hash == text_hash
    assert first[0].locator.value == "page:1:block:1"


def test_no_network_fixture_path_indexes_existing_chunks() -> None:
    service = StartupRetrievalService(
        index=FakeIndex([]),
        text_resolver=ResolverSpy({}),
        egress_policy=DataEgressPolicy(),
    )
    chunk = service.build_chunk(
        case_id=uuid4(),
        artifact_id=uuid4(),
        text_ref="b" * 64,
        content_hash="c" * 64,
        locator=SourceLocator(kind="fixture", value="chunk:1"),
        sensitivity=SensitivityClass.PUBLIC,
        parser_confidence=Decimal("0.99"),
    )

    service.index_chunks([chunk], no_network=True)

    assert service.indexed_chunk_ids == (chunk.chunk_id,)


class FakeIndex:
    def __init__(self, hits: list[RetrievalHit]) -> None:
        self.hits = hits
        self.indexed = []
        self.search_calls: list[tuple[str, int, object]] = []

    def index(self, chunks) -> None:
        self.indexed.extend(chunks)

    def search(self, query: str, *, k: int, case_id) -> list[RetrievalHit]:
        assert query.strip()
        self.search_calls.append((query, k, case_id))
        return self.hits[:k]


class ResolverSpy:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.calls: list[str] = []

    def __call__(self, text_ref: str) -> str:
        self.calls.append(text_ref)
        try:
            return self.values[text_ref]
        except KeyError:
            raise AssertionError(f"unexpected text resolution: {text_ref}") from None


def _hit(
    text_ref: str,
    sensitivity: SensitivityClass,
    *,
    score: float,
    case_id=None,
) -> RetrievalHit:
    artifact_id = uuid4()
    return RetrievalHit(
        chunk_id=uuid4(),
        case_id=case_id or uuid4(),
        artifact_id=artifact_id,
        locator=SourceLocator(kind="fixture", value=text_ref, artifact_id=artifact_id),
        content_hash=sha256(text_ref.encode()).hexdigest(),
        sensitivity=sensitivity,
        text_ref=text_ref,
        chunk_config_hash="d" * 64,
        chunk_config_version="startup-chunker@1",
        model_id="fixture",
        model_revision="1",
        index_version="fixture-index",
        score=score,
    )
