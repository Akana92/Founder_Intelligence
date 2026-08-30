from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Awaitable, Protocol, cast
from uuid import UUID, uuid5

import httpx
from pydantic import BaseModel, Field

from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.common import ArtifactParsingStatus, SensitivityClass
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.ports.collectors import (
    FilingArtifact,
    MarketDataSnapshot,
    NewsItem,
    SourceSnapshot,
)
from due_diligence_agent.ports.repositories import (
    ArtifactRepository,
    ArtifactStore,
    EvidenceRepository,
)
from due_diligence_agent.workflows.public_company.state import PublicCaseState
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus


_MARKET_FACT_NAMESPACE = UUID("1e9a9e0a-0c10-45dc-bab0-50c23eb47e95")
_NEWS_FACT_NAMESPACE = UUID("995b0b96-c5d5-40a9-b76d-3c95b867bb13")
_ARTIFACT_NAMESPACE = UUID("9a3b55cb-5d5d-4a37-946a-72e219f84c0f")
_SEC_FACT_NAMESPACE = UUID("cdf25588-51c0-4eb1-86d4-cf5f1c3b1588")
_RETRY_SLEEP_CAP_SECONDS = 30.0
_SEC_CONCEPT_NAMES = {
    "Revenues": "revenue",
    "Revenue": "revenue",
    "SalesRevenueNet": "revenue",
    "GrossProfit": "gross_profit",
}


class CollectionOutput(BaseModel):
    artifact_ids: list[str] = Field(default_factory=list)
    evidence_fact_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class AuditRecorder(Protocol):
    def record(self, node_name: str, result: NodeResult[Any], state: dict[str, Any]) -> None: ...


class AttemptGuard(Protocol):
    def check(
        self, *, node_name: str, attempt: int, state: dict[str, Any]
    ) -> NodeResult[None] | None: ...


AsyncSleeper = Callable[[float], Awaitable[None]]
SyncSleeper = Callable[[float], None]


class PublicCollectionDependencies(Protocol):
    sec: Any
    market: Any
    news: Any
    retrieval: Any
    artifact_repository: ArtifactRepository
    evidence_repository: EvidenceRepository
    artifact_store: ArtifactStore
    guard: AttemptGuard | None
    audit: AuditRecorder | None
    async_sleeper: AsyncSleeper | None
    sync_sleeper: SyncSleeper | None


def collect_sec(
    state: PublicCaseState,
    *,
    dependencies: PublicCollectionDependencies,
) -> dict[str, object]:
    return _run_coroutine_sync(async_collect_sec(state, dependencies=dependencies))


async def async_collect_sec(
    state: PublicCaseState,
    *,
    dependencies: PublicCollectionDependencies,
) -> dict[str, object]:
    result = await async_run_guarded(
        node_name="collect_sec",
        state=state,
        guard=getattr(dependencies, "guard", None),
        sleeper=getattr(dependencies, "async_sleeper", None),
        call=lambda: _collect_sec_once(state, dependencies),
    )
    return collection_update(
        "collect_sec", result, state=state, audit=dependencies.audit, primary=True
    )


def collect_market(
    state: PublicCaseState,
    *,
    dependencies: PublicCollectionDependencies,
) -> dict[str, object]:
    return _run_coroutine_sync(async_collect_market(state, dependencies=dependencies))


async def async_collect_market(
    state: PublicCaseState,
    *,
    dependencies: PublicCollectionDependencies,
) -> dict[str, object]:
    result = await async_run_guarded(
        node_name="collect_market",
        state=state,
        guard=getattr(dependencies, "guard", None),
        sleeper=getattr(dependencies, "async_sleeper", None),
        call=lambda: _collect_market_once(state, dependencies),
    )
    return collection_update("collect_market", result, state=state, audit=dependencies.audit)


def collect_news(
    state: PublicCaseState,
    *,
    dependencies: PublicCollectionDependencies,
) -> dict[str, object]:
    return _run_coroutine_sync(async_collect_news(state, dependencies=dependencies))


async def async_collect_news(
    state: PublicCaseState,
    *,
    dependencies: PublicCollectionDependencies,
) -> dict[str, object]:
    result = await async_run_guarded(
        node_name="collect_news",
        state=state,
        guard=getattr(dependencies, "guard", None),
        sleeper=getattr(dependencies, "async_sleeper", None),
        call=lambda: _collect_news_once(state, dependencies),
    )
    return collection_update("collect_news", result, state=state, audit=dependencies.audit)


def run_guarded(
    *,
    node_name: str,
    state: PublicCaseState,
    guard: AttemptGuard | None,
    call: Callable[[], NodeResult[Any]],
    sleeper: SyncSleeper | None = None,
) -> NodeResult[Any]:
    primary_retryable: NodeResult[Any] | None = None
    sleep_fn = sleeper or __import__("time").sleep
    for attempt in range(1, 4):
        denial = (
            guard.check(node_name=node_name, attempt=attempt, state=dict(state)) if guard else None
        )
        if denial is not None:
            if primary_retryable is None:
                return denial
            return primary_retryable.model_copy(
                update={
                    "warnings": [
                        *primary_retryable.warnings,
                        *primary_retryable.errors,
                        *denial.errors,
                    ]
                }
            )
        try:
            result = call()
        except Exception as exc:
            mapped = _map_expected_exception(exc)
            if mapped is None:
                raise
            result = mapped
        if result.status is not NodeStatus.RETRYABLE_ERROR:
            if primary_retryable is not None and result.status is NodeStatus.SUCCESS:
                return result.model_copy(
                    update={
                        "warnings": [
                            *primary_retryable.warnings,
                            *primary_retryable.errors,
                            *result.warnings,
                        ]
                    }
                )
            return result
        if primary_retryable is None:
            primary_retryable = result
        if attempt == 3:
            return primary_retryable
        if result.retry_after_seconds:
            sleep_fn(min(float(result.retry_after_seconds), _RETRY_SLEEP_CAP_SECONDS))
    raise AssertionError("unreachable")


async def async_run_guarded(
    *,
    node_name: str,
    state: PublicCaseState,
    guard: AttemptGuard | None,
    sleeper: AsyncSleeper | None,
    call: Callable[[], NodeResult[Any] | Awaitable[NodeResult[Any]]],
) -> NodeResult[Any]:
    primary_retryable: NodeResult[Any] | None = None
    sleep_fn = sleeper or asyncio.sleep
    for attempt in range(1, 4):
        denial = (
            guard.check(node_name=node_name, attempt=attempt, state=dict(state)) if guard else None
        )
        if denial is not None:
            if primary_retryable is None:
                return denial
            return primary_retryable.model_copy(
                update={
                    "warnings": [
                        *primary_retryable.warnings,
                        *primary_retryable.errors,
                        *denial.errors,
                    ]
                }
            )
        try:
            result = call()
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            mapped = _map_expected_exception(exc)
            if mapped is None:
                raise
            result = mapped
        if result.status is not NodeStatus.RETRYABLE_ERROR:
            if primary_retryable is not None and result.status is NodeStatus.SUCCESS:
                return result.model_copy(
                    update={
                        "warnings": [
                            *primary_retryable.warnings,
                            *primary_retryable.errors,
                            *result.warnings,
                        ]
                    }
                )
            return result
        if primary_retryable is None:
            primary_retryable = result
        if attempt == 3:
            return primary_retryable
        if result.retry_after_seconds:
            await sleep_fn(min(float(result.retry_after_seconds), _RETRY_SLEEP_CAP_SECONDS))
    raise AssertionError("unreachable")


def collection_update(
    node_name: str,
    result: NodeResult[CollectionOutput],
    *,
    state: PublicCaseState,
    audit: AuditRecorder | None,
    primary: bool = False,
) -> dict[str, object]:
    compact = compact_result(node_name, result)
    if audit is not None:
        audit.record(node_name, compact, dict(state))

    output = result.data or CollectionOutput()
    warnings = [f"{node_name}:{warning}" for warning in result.warnings]
    errors = [f"{node_name}:{error}" for error in result.errors]
    if not primary and result.status is NodeStatus.RETRYABLE_ERROR:
        warnings.extend(errors)
        errors = []
    update: dict[str, object] = {
        "node_results": [_result_state(node_name, compact)],
        "warnings": warnings,
        "errors": errors if result.status is not NodeStatus.PARTIAL else [],
    }
    if output.artifact_ids:
        update["artifact_ids"] = output.artifact_ids
    if output.evidence_fact_ids:
        update["evidence_fact_ids"] = output.evidence_fact_ids
    if output.chunk_ids:
        update["chunk_ids"] = output.chunk_ids
    if primary and result.status is not NodeStatus.SUCCESS:
        update["primary_failure"] = _failure(node_name, result)
        update["status"] = "blocked"
    return update


def compact_result(node_name: str, result: NodeResult[Any]) -> NodeResult[None]:
    return NodeResult(
        status=result.status,
        data=None,
        data_refs=list(result.data_refs),
        warnings=list(result.warnings),
        errors=list(result.errors),
        fallback_used=result.fallback_used,
        retry_after_seconds=result.retry_after_seconds,
        trace_id=result.trace_id,
    )


def _result_state(node_name: str, result: NodeResult[Any]) -> dict[str, object]:
    return {
        "node_name": node_name,
        "status": result.status.value,
        "data_refs": [str(item) for item in result.data_refs],
        "warnings": list(result.warnings),
        "errors": list(result.errors),
        "fallback_used": result.fallback_used,
        "trace_id": result.trace_id,
    }


async def _collect_sec_once(
    state: PublicCaseState,
    dependencies: PublicCollectionDependencies,
) -> NodeResult[CollectionOutput]:
    case_id = UUID(state["case_id"])
    ticker = state["ticker"]
    as_of = datetime.fromisoformat(state["as_of"]).date()
    try:
        company = await _maybe_await(dependencies.sec.resolve_company(ticker, as_of=as_of))
        submissions = await _maybe_await(
            dependencies.sec.list_submissions(company.cik, as_of=as_of)
        )
        facts_snapshot = await _maybe_await(
            dependencies.sec.get_company_facts(company.cik, as_of=as_of)
        )
    except Exception as exc:
        mapped = _map_expected_exception(exc)
        if mapped is not None:
            return _empty_collection_result_from(mapped)
        raise

    artifact_ids: list[str] = []
    chunk_ids: list[str] = []
    for accession in _accessions(submissions.data):
        filing_result = await _fetch_filing(accession, as_of=as_of, dependencies=dependencies)
        if filing_result.status is not NodeStatus.SUCCESS or filing_result.data is None:
            return _empty_collection_result_from(filing_result)
        artifact_result = _persist_filing(case_id, filing_result.data, dependencies)
        if isinstance(artifact_result, NodeResult):
            return artifact_result
        artifact = artifact_result
        artifact_ids.append(str(artifact.id))
        chunks = dependencies.retrieval.index_filing(
            case_id=case_id,
            filing=filing_result.data,
            artifact_id=artifact.id,
            sensitivity=SensitivityClass.PUBLIC,
        )
        chunk_ids.extend(str(chunk.chunk_id) for chunk in chunks)

    evidence_ids = _persist_sec_facts(
        case_id=case_id,
        facts_data=facts_snapshot.data,
        submissions_data=submissions.data,
        artifact_ids=[UUID(item) for item in artifact_ids],
        retrieved_at=facts_snapshot.snapshot.retrieved_at,
        dependencies=dependencies,
    )
    output = CollectionOutput(
        artifact_ids=artifact_ids,
        evidence_fact_ids=evidence_ids,
        chunk_ids=chunk_ids,
    )
    requirement_error = _required_gross_margin_error(
        dependencies.evidence_repository.list_for_case(case_id),
        evidence_ids,
    )
    if requirement_error is not None:
        return NodeResult(
            status=NodeStatus.BLOCKED,
            data=output,
            data_refs=[*artifact_ids, *evidence_ids, *chunk_ids],
            errors=[requirement_error],
        )
    return NodeResult(
        status=NodeStatus.SUCCESS,
        data=output,
        data_refs=[*artifact_ids, *evidence_ids, *chunk_ids],
    )


async def _collect_market_once(
    state: PublicCaseState,
    dependencies: PublicCollectionDependencies,
) -> NodeResult[CollectionOutput]:
    case_id = UUID(state["case_id"])
    as_of = datetime.fromisoformat(state["as_of"]).date()
    snapshot = await _maybe_await(dependencies.market.get_snapshot(state["ticker"], as_of=as_of))
    artifact = _persist_source_artifact(
        case_id=case_id,
        source_name="market",
        source_url=snapshot.snapshot.source_url,
        snapshot_hash=snapshot.snapshot.content_hash,
        payload={
            "ticker": snapshot.ticker,
            "as_of": snapshot.as_of.isoformat(),
            "market_cap": str(snapshot.market_cap) if snapshot.market_cap is not None else None,
            "currency": snapshot.currency,
            "source_url": snapshot.snapshot.source_url,
            "license_class": snapshot.snapshot.license_class,
        },
        snapshot=snapshot.snapshot,
        dependencies=dependencies,
    )
    if snapshot.market_cap is None:
        output = CollectionOutput(artifact_ids=[str(artifact.id)])
        return NodeResult(
            status=NodeStatus.PARTIAL,
            data=output,
            data_refs=output.artifact_ids,
            warnings=["market_cap_missing"],
        )
    fact = _market_fact(case_id, snapshot, artifact_id=artifact.id)
    _add_evidence_idempotent(fact, dependencies)
    output = CollectionOutput(artifact_ids=[str(artifact.id)], evidence_fact_ids=[str(fact.id)])
    return NodeResult(
        status=NodeStatus.SUCCESS,
        data=output,
        data_refs=[*output.artifact_ids, *output.evidence_fact_ids],
    )


async def _collect_news_once(
    state: PublicCaseState,
    dependencies: PublicCollectionDependencies,
) -> NodeResult[CollectionOutput]:
    case_id = UUID(state["case_id"])
    as_of = datetime.fromisoformat(state["as_of"]).date()
    try:
        items = await _maybe_await(dependencies.news.search(state["ticker"], as_of=as_of))
    except Exception as exc:
        result = getattr(exc, "result", None)
        if isinstance(result, NodeResult):
            return _empty_collection_result_from(result)
        mapped = _map_expected_exception(exc)
        if mapped is not None:
            return _empty_collection_result_from(mapped)
        raise
    evidence_ids: list[str] = []
    artifact_ids: list[str] = []
    for item in items:
        artifact = _persist_source_artifact(
            case_id=case_id,
            source_name="news",
            source_url=item.url,
            snapshot_hash=item.response_hash,
            payload={
                "url": item.url,
                "title": item.title,
                "publisher": item.publisher,
                "domain": item.domain,
                "published_at": item.published_at.isoformat(),
                "response_hash": item.response_hash,
                "license_class": item.license_class,
            },
            snapshot=SourceSnapshot(
                provider=item.provenance.provider,
                provider_version=item.provenance.provider_version,
                source_url=item.url,
                query={"ticker": state["ticker"], "url": item.url},
                as_of=as_of,
                retrieved_at=item.retrieved_at,
                published_at=item.published_at,
                content_hash=item.response_hash,
                license_class=str(item.license_class),
                media_type="application/json",
                storage_ref=f"news://{item.response_hash}",
            ),
            dependencies=dependencies,
        )
        fact = _news_fact(case_id, item, artifact_id=artifact.id)
        _add_evidence_idempotent(fact, dependencies)
        artifact_ids.append(str(artifact.id))
        evidence_ids.append(str(fact.id))
    output = CollectionOutput(artifact_ids=artifact_ids, evidence_fact_ids=evidence_ids)
    return NodeResult(
        status=NodeStatus.SUCCESS,
        data=output,
        data_refs=[*artifact_ids, *evidence_ids],
    )


def _persist_filing(
    case_id: UUID,
    filing: FilingArtifact,
    dependencies: PublicCollectionDependencies,
) -> Artifact | NodeResult[CollectionOutput]:
    artifact_id = _artifact_id_from_storage_ref(filing.snapshot.storage_ref)
    try:
        stored = dependencies.artifact_store.put_bytes(
            filing.content,
            media_type=filing.snapshot.media_type,
            artifact_id=artifact_id,
            source_snapshot_hash=filing.snapshot.content_hash,
            sensitivity=SensitivityClass.PUBLIC,
        )
    except ValueError as exc:
        if str(exc) == "artifact_content_conflict":
            return NodeResult(status=NodeStatus.BLOCKED, data=CollectionOutput(), errors=[str(exc)])
        raise
    artifact = Artifact(
        id=stored.artifact_id,
        case_id=case_id,
        content_hash=stored.content_hash,
        mime_type=stored.media_type,
        source=filing.snapshot.provider,
        source_url=filing.snapshot.source_url,
        normalized_query=tuple(sorted(filing.snapshot.query.items())),
        retrieved_at=filing.snapshot.retrieved_at,
        published_at=filing.snapshot.published_at,
        source_snapshot_hash=stored.source_snapshot_hash,
        storage_ref=stored.storage_ref,
        parsing_status=ArtifactParsingStatus.PARSED,
        sensitivity=SensitivityClass.PUBLIC,
    )
    add_result = _add_artifact_idempotent(artifact, dependencies)
    if add_result is not None:
        return add_result
    return artifact


def _persist_source_artifact(
    *,
    case_id: UUID,
    source_name: str,
    source_url: str,
    snapshot_hash: str,
    payload: Mapping[str, Any],
    snapshot: SourceSnapshot,
    dependencies: PublicCollectionDependencies,
) -> Artifact:
    artifact_id = uuid5(
        _ARTIFACT_NAMESPACE, f"{case_id}|{source_name}|{source_url}|{snapshot_hash}"
    )
    payload_bytes = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    stored = dependencies.artifact_store.put_bytes(
        payload_bytes,
        media_type="application/json",
        artifact_id=artifact_id,
        source_snapshot_hash=snapshot_hash,
        sensitivity=SensitivityClass.PUBLIC,
    )
    artifact = Artifact(
        id=stored.artifact_id,
        case_id=case_id,
        content_hash=stored.content_hash,
        mime_type=stored.media_type,
        source=source_name,
        source_url=source_url,
        normalized_query=tuple(
            sorted((str(key), str(value)) for key, value in snapshot.query.items())
        ),
        retrieved_at=snapshot.retrieved_at,
        published_at=snapshot.published_at,
        source_snapshot_hash=stored.source_snapshot_hash,
        storage_ref=stored.storage_ref,
        parsing_status=ArtifactParsingStatus.PARSED,
        sensitivity=SensitivityClass.PUBLIC,
    )
    add_result = _add_artifact_idempotent(artifact, dependencies)
    if add_result is not None:
        raise ValueError(add_result.errors[0] if add_result.errors else "artifact_conflict")
    return artifact


def _add_artifact_idempotent(
    artifact: Artifact,
    dependencies: PublicCollectionDependencies,
) -> NodeResult[CollectionOutput] | None:
    try:
        dependencies.artifact_repository.add(artifact)
        return None
    except ValueError as exc:
        if str(exc) != "artifact_already_exists":
            raise
        existing = dependencies.artifact_repository.get(artifact.id)
        if existing != artifact:
            return NodeResult(
                status=NodeStatus.BLOCKED,
                data=CollectionOutput(),
                errors=["artifact_content_conflict"],
            )
        return None


def _add_evidence_idempotent(
    fact: EvidenceFact,
    dependencies: PublicCollectionDependencies,
) -> None:
    try:
        dependencies.evidence_repository.add(fact)
    except ValueError as exc:
        if str(exc) != "evidence_fact_already_exists":
            raise
        existing = [
            item
            for item in dependencies.evidence_repository.list_for_case(
                dependencies.artifact_repository.get(fact.artifact_id).case_id
            )
            if item.id == fact.id
        ]
        if existing != [fact]:
            raise ValueError("evidence_fact_conflict") from exc


def _persist_fact_payloads(
    payloads: object,
    dependencies: PublicCollectionDependencies,
) -> list[str]:
    result: list[str] = []
    if not isinstance(payloads, Iterable) or isinstance(payloads, str | bytes | Mapping):
        return result
    for payload in payloads:
        fact = EvidenceFact.model_validate(payload)
        _add_evidence_idempotent(fact, dependencies)
        result.append(str(fact.id))
    return result


def _persist_sec_facts(
    *,
    case_id: UUID,
    facts_data: Mapping[str, Any],
    submissions_data: Mapping[str, Any],
    artifact_ids: Sequence[UUID],
    retrieved_at: datetime,
    dependencies: PublicCollectionDependencies,
) -> list[str]:
    compact_payloads = facts_data.get("facts")
    if isinstance(compact_payloads, Iterable) and not isinstance(
        compact_payloads, Mapping | str | bytes
    ):
        return _persist_fact_payloads(compact_payloads, dependencies)
    accession_map = _accession_artifact_map(submissions_data, artifact_ids)
    evidence_ids: list[str] = []
    if not isinstance(compact_payloads, Mapping):
        return evidence_ids
    for taxonomy, concepts in compact_payloads.items():
        if not isinstance(concepts, Mapping):
            continue
        for concept, concept_payload in concepts.items():
            canonical_name = _SEC_CONCEPT_NAMES.get(str(concept))
            if canonical_name is None or not isinstance(concept_payload, Mapping):
                continue
            units = concept_payload.get("units")
            if not isinstance(units, Mapping):
                continue
            for unit, observations in units.items():
                if not isinstance(observations, Iterable) or isinstance(
                    observations, Mapping | str | bytes
                ):
                    continue
                for observation in observations:
                    if not isinstance(observation, Mapping) or "val" not in observation:
                        continue
                    artifact_ref = _artifact_for_observation(observation, accession_map)
                    if artifact_ref is None:
                        continue
                    artifact_id, accession = artifact_ref
                    fact = _sec_fact(
                        case_id=case_id,
                        artifact_id=artifact_id,
                        accession=accession,
                        retrieved_at=retrieved_at,
                        taxonomy=str(taxonomy),
                        concept=str(concept),
                        canonical_name=canonical_name,
                        unit=str(unit),
                        observation=observation,
                    )
                    _add_evidence_idempotent(fact, dependencies)
                    evidence_ids.append(str(fact.id))
    return evidence_ids


def _market_fact(case_id: UUID, snapshot: MarketDataSnapshot, *, artifact_id: UUID) -> EvidenceFact:
    fact_id = uuid5(
        _MARKET_FACT_NAMESPACE,
        f"{case_id}|{snapshot.ticker}|{snapshot.as_of.isoformat()}|market_cap",
    )
    return EvidenceFact(
        id=fact_id,
        artifact_id=artifact_id,
        name="market_cap",
        value=snapshot.market_cap,
        value_type="decimal",
        unit=snapshot.currency,
        period=snapshot.as_of.isoformat(),
        locator=SourceLocator(kind="market_data", value="market_cap"),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.90"),
        source_priority=snapshot.source_priority,
        extraction_method="market_snapshot",
        supporting_text_hash=snapshot.snapshot.content_hash,
        source_freshness_at=snapshot.snapshot.published_at,
        retrieved_at=snapshot.snapshot.retrieved_at,
    )


def _news_fact(case_id: UUID, item: NewsItem, *, artifact_id: UUID) -> EvidenceFact:
    fact_id = uuid5(_NEWS_FACT_NAMESPACE, f"{case_id}|{item.response_hash}|{item.url}")
    return EvidenceFact(
        id=fact_id,
        artifact_id=artifact_id,
        name="news_signal",
        value=item.title,
        value_type="text",
        unit=None,
        period=None,
        locator=SourceLocator(kind="news_metadata", value=item.url),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.75"),
        source_priority=None,
        extraction_method="news_metadata",
        supporting_text_hash=item.response_hash,
        source_freshness_at=item.published_at,
        retrieved_at=item.retrieved_at,
        metadata={"polarity": item.polarity} if item.polarity is not None else {},
    )


def _sec_fact(
    *,
    case_id: UUID,
    artifact_id: UUID,
    accession: str,
    retrieved_at: datetime,
    taxonomy: str,
    concept: str,
    canonical_name: str,
    unit: str,
    observation: Mapping[str, Any],
) -> EvidenceFact:
    period = _observation_period(observation)
    observation_accession = str(observation.get("accn") or accession)
    filed = str(observation.get("filed") or "")
    form = str(observation.get("form") or "")
    locator_payload = {
        "taxonomy": taxonomy,
        "concept": concept,
        "accession": observation_accession,
        "form": form,
        "filed": filed,
        "start": str(observation.get("start", "")),
        "end": str(observation.get("end", "")),
    }
    locator_value = json.dumps(locator_payload, sort_keys=True, separators=(",", ":"))
    supporting_text_hash = hashlib.sha256(locator_value.encode("utf-8")).hexdigest()
    fact_id = uuid5(
        _SEC_FACT_NAMESPACE,
        f"{case_id}|{artifact_id}|{taxonomy}|{concept}|{unit}|{period}|{observation.get('val')}",
    )
    return EvidenceFact(
        id=fact_id,
        artifact_id=artifact_id,
        name=canonical_name,
        value=Decimal(str(observation["val"])),
        value_type="decimal",
        unit=unit,
        period=period,
        locator=SourceLocator(
            kind="sec_company_fact",
            value=locator_value,
            artifact_id=artifact_id,
        ),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.95"),
        source_priority=SourcePriority.OFFICIAL_OR_SIGNED,
        extraction_method="sec_companyfacts",
        supporting_text_hash=supporting_text_hash,
        source_freshness_at=_datetime_from_date(filed),
        retrieved_at=retrieved_at,
    )


def _accession_artifact_map(
    submissions_data: Mapping[str, Any], artifact_ids: Sequence[UUID]
) -> dict[str, tuple[UUID, str]]:
    recent = submissions_data.get("filings")
    if isinstance(recent, Mapping):
        recent = recent.get("recent")
    if not isinstance(recent, Mapping):
        return {}
    accessions = _string_list(recent.get("accessionNumber"))
    forms = _string_list(recent.get("form"))
    filed_dates = _string_list(recent.get("filingDate"))
    report_dates = _string_list(recent.get("reportDate"))
    result: dict[str, tuple[UUID, str]] = {}
    for index, artifact_id in enumerate(artifact_ids):
        if index < len(accessions):
            result[f"accession:{accessions[index]}"] = (artifact_id, accessions[index])
        if index < len(forms) and index < len(filed_dates):
            accession = accessions[index] if index < len(accessions) else ""
            result[f"form-filed:{forms[index]}:{filed_dates[index]}"] = (artifact_id, accession)
        if index < len(forms) and index < len(report_dates):
            accession = accessions[index] if index < len(accessions) else ""
            result[f"form-end:{forms[index]}:{report_dates[index]}"] = (artifact_id, accession)
    return result


def _artifact_for_observation(
    observation: Mapping[str, Any], accession_map: Mapping[str, tuple[UUID, str]]
) -> tuple[UUID, str] | None:
    accession = observation.get("accn")
    if accession is not None:
        artifact_ref = accession_map.get(f"accession:{accession}")
        if artifact_ref is not None:
            return artifact_ref
        return None
    form = observation.get("form")
    filed = observation.get("filed")
    if form is not None and filed is not None:
        artifact_ref = accession_map.get(f"form-filed:{form}:{filed}")
        if artifact_ref is not None:
            return artifact_ref
        return None
    end = observation.get("end")
    if form is not None and end is not None:
        return accession_map.get(f"form-end:{form}:{end}")
    if form is not None or filed is not None or end is not None:
        return None
    if len(accession_map) == 1:
        return next(iter(accession_map.values()), None)
    return None


def _observation_period(observation: Mapping[str, Any]) -> str:
    fy = observation.get("fy")
    fp = observation.get("fp")
    if fy is not None and fp:
        fp_text = str(fp).upper()
        if fp_text == "FY":
            return str(fy)
        if fp_text in {"Q1", "Q2", "Q3", "Q4"}:
            return f"{fy}-{fp_text}"
    if fy is not None and not fp:
        return str(fy)
    end = observation.get("end")
    if end is not None:
        return str(end)
    filed = observation.get("filed")
    return str(filed or "unknown")


def _required_gross_margin_error(
    facts: Sequence[EvidenceFact], evidence_ids: Sequence[str]
) -> str | None:
    selected = [fact for fact in facts if str(fact.id) in set(evidence_ids)]
    periods_by_name: dict[str, set[str]] = {"revenue": set(), "gross_profit": set()}
    for fact in selected:
        if fact.name in periods_by_name and fact.period:
            periods_by_name[fact.name].add(fact.period)
    if not periods_by_name["revenue"] and not periods_by_name["gross_profit"]:
        return "sec_companyfacts_required_facts_missing"
    if not periods_by_name["revenue"]:
        return "sec_companyfacts_required_facts_missing:revenue"
    if not periods_by_name["gross_profit"]:
        return "sec_companyfacts_required_facts_missing:gross_profit"
    if not (periods_by_name["revenue"] & periods_by_name["gross_profit"]):
        return "sec_companyfacts_required_facts_missing:compatible_period"
    return None


def _datetime_from_date(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(f"{value}T00:00:00+00:00")


def _first_artifact_id(state: PublicCaseState) -> UUID:
    artifact_ids = state.get("artifact_ids", [])
    if not artifact_ids:
        raise ValueError("primary_artifact_required")
    return UUID(artifact_ids[0])


def _empty_collection_result_from(result: NodeResult[Any]) -> NodeResult[CollectionOutput]:
    return NodeResult(
        status=result.status,
        data=CollectionOutput(),
        data_refs=list(result.data_refs),
        warnings=list(result.warnings),
        errors=list(result.errors),
        fallback_used=result.fallback_used,
        retry_after_seconds=result.retry_after_seconds,
        trace_id=result.trace_id,
    )


def _accessions(data: Mapping[str, Any]) -> Sequence[str]:
    filings = data.get("filings")
    if isinstance(filings, Mapping):
        recent = filings.get("recent")
        if isinstance(recent, Mapping):
            values = recent.get("accessionNumber")
            if isinstance(values, list | tuple):
                return [str(value) for value in values]
    return []


def _string_list(value: object) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return []


def _artifact_id_from_storage_ref(storage_ref: str) -> UUID | None:
    value = storage_ref.rsplit("/", 1)[-1]
    try:
        return UUID(value)
    except ValueError:
        return None


def _failure(node_name: str, result: NodeResult[Any]) -> str:
    detail = result.errors[0] if result.errors else result.status.value
    return f"{node_name}:{detail}"


async def _fetch_filing(
    accession: str,
    *,
    as_of: date,
    dependencies: PublicCollectionDependencies,
) -> NodeResult[FilingArtifact]:
    try:
        return cast(
            NodeResult[FilingArtifact],
            await _maybe_await(dependencies.sec.fetch_filing(accession, as_of=as_of)),
        )
    except Exception as exc:
        mapped = _map_expected_exception(exc)
        if mapped is not None:
            return mapped.model_copy(update={"data": None})
        raise


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _run_coroutine_sync(awaitable: Coroutine[Any, Any, dict[str, object]]) -> dict[str, object]:
    with asyncio.Runner() as runner:
        return runner.run(awaitable)


def _map_expected_exception(exc: Exception) -> NodeResult[Any] | None:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == 429:
            return NodeResult(
                status=NodeStatus.RETRYABLE_ERROR,
                errors=["source_transient:rate_limited"],
                retry_after_seconds=1,
            )
        if 500 <= status_code <= 599:
            return NodeResult(
                status=NodeStatus.RETRYABLE_ERROR,
                errors=["source_transient:http_5xx"],
                retry_after_seconds=1,
            )
        if 400 <= status_code <= 499:
            return NodeResult(status=NodeStatus.BLOCKED, errors=["source_blocked:http_4xx"])
        return NodeResult(status=NodeStatus.FAILED, errors=["source_failed:http_status"])
    if isinstance(exc, httpx.TimeoutException | httpx.ConnectError | httpx.NetworkError):
        return NodeResult(
            status=NodeStatus.RETRYABLE_ERROR,
            errors=[f"source_transient:{_exception_code(exc)}"],
            retry_after_seconds=1,
        )
    if isinstance(exc, ValueError) and str(exc) in {
        "artifact_content_conflict",
        "evidence_fact_conflict",
        "referential_integrity_violation",
    }:
        return NodeResult(status=NodeStatus.BLOCKED, errors=[str(exc)])
    return None


def _exception_code(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.NetworkError):
        return "network_error"
    return "unknown"
