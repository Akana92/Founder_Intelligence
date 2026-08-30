from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
import asyncio
import json
import random
import re
from typing import TypeVar

import httpx

from due_diligence_agent.adapters.http.fair_access import FairAccessLimiter
from due_diligence_agent.adapters.http.snapshot_cache import SnapshotCache
from due_diligence_agent.ports.collectors import (
    CompanyFactsSnapshot,
    CompanyIdentity,
    FilingArtifact,
    SourceSnapshot,
    SubmissionsSnapshot,
)
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus


T = TypeVar("T")
Sleeper = Callable[[float], Awaitable[None]]


class MissingUserAgentError(ValueError):
    pass


class MissingFilingContextError(ValueError):
    pass


class SecEdgarAdapter:
    provider = "sec"
    provider_version = "2026-08-09"
    license_class = "public_primary"

    def __init__(
        self,
        *,
        user_agent: str,
        cache: SnapshotCache,
        limiter: FairAccessLimiter,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Sleeper = asyncio.sleep,
        jitter: Callable[[int], float] | None = None,
        refresh_existing: bool = False,
    ) -> None:
        clean_user_agent = user_agent.strip()
        if not clean_user_agent:
            raise MissingUserAgentError("DDA_SEC_USER_AGENT must be a nonblank application contact")
        self.user_agent = clean_user_agent
        self.cache = cache
        self.limiter = limiter
        self.client = client or httpx.AsyncClient()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper
        self._jitter = jitter or (lambda _attempt: random.uniform(0, 0.25))
        self._refresh_existing = refresh_existing
        self._submission_metadata_by_accession: dict[str, FilingMetadata] = {}

    async def resolve_company(self, ticker_or_cik: str, *, as_of: date = date.min) -> CompanyIdentity:
        if re.fullmatch(r"\d{1,10}", ticker_or_cik.strip()):
            return CompanyIdentity(cik=_normalize_cik(ticker_or_cik))
        url = "https://www.sec.gov/files/company_tickers.json"
        snapshot = await self._request_bytes(url, query={"ticker_map": "company_tickers"}, as_of=as_of)
        ticker_map = json.loads(self.cache.read_bytes(snapshot).decode("utf-8"))
        requested = ticker_or_cik.strip().upper()
        for entry in ticker_map.values():
            if str(entry["ticker"]).strip().upper() == requested:
                return CompanyIdentity(
                    cik=_normalize_cik(str(entry["cik_str"])),
                    ticker=str(entry["ticker"]).strip().upper(),
                    name=str(entry["title"]),
                    snapshot=snapshot,
                )
        raise ValueError(f"ticker_not_found:{ticker_or_cik}")

    async def list_submissions(self, cik: str, *, as_of: date) -> SubmissionsSnapshot:
        normalized = _normalize_cik(cik)
        url = f"https://data.sec.gov/submissions/CIK{normalized}.json"
        snapshot = await self._request_bytes(url, query={"cik": normalized}, as_of=as_of)
        data = json.loads(self.cache.read_bytes(snapshot).decode("utf-8"))
        self._index_submission_metadata(data)
        return SubmissionsSnapshot(data=data, snapshot=snapshot)

    async def get_company_facts(self, cik: str, *, as_of: date) -> CompanyFactsSnapshot:
        normalized = _normalize_cik(cik)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalized}.json"
        snapshot = await self._request_bytes(url, query={"cik": normalized}, as_of=as_of)
        data = json.loads(self.cache.read_bytes(snapshot).decode("utf-8"))
        return CompanyFactsSnapshot(data=data, snapshot=snapshot)

    async def fetch_filing(
        self, accession_number: str, *, as_of: date = date.min
    ) -> NodeResult[FilingArtifact]:
        try:
            metadata = await self._filing_metadata(accession_number, as_of=as_of)
        except MissingFilingContextError:
            return NodeResult(
                status=NodeStatus.BLOCKED,
                errors=[f"filing_metadata_context_required:{accession_number}"],
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return NodeResult(
                    status=NodeStatus.BLOCKED,
                    errors=[f"primary_filing_not_found:{accession_number}"],
                )
            raise
        url = _archive_url(metadata)
        query = {"accession_number": accession_number}
        key = self.cache.key(self.provider, url, query, as_of)
        try:
            snapshot = await self._request_bytes(url, query=query, as_of=as_of)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404 and not self._has_valid_request_cache(
                key,
                url,
                query=query,
                as_of=as_of,
            ):
                return NodeResult(
                    status=NodeStatus.BLOCKED,
                    errors=[f"primary_filing_not_found:{accession_number}"],
                )
            raise
        artifact = FilingArtifact(
            accession_number=accession_number,
            content=self.cache.read_bytes(snapshot),
            snapshot=snapshot,
        )
        return NodeResult(status=NodeStatus.SUCCESS, data=artifact)

    async def _filing_metadata(self, accession_number: str, *, as_of: date) -> FilingMetadata:
        normalized_accession = _normalize_accession(accession_number)
        if normalized_accession in self._submission_metadata_by_accession:
            return self._submission_metadata_by_accession[normalized_accession]
        raise MissingFilingContextError

    def _index_submission_metadata(self, data: dict[str, object]) -> None:
        recent = data.get("filings", {})
        if not isinstance(recent, dict):
            return
        recent = recent.get("recent", {})
        if not isinstance(recent, dict):
            return
        accessions = _string_list(recent.get("accessionNumber"))
        primary_documents = _string_list(recent.get("primaryDocument"))
        acceptance_times = _string_list(recent.get("acceptanceDateTime"))
        report_dates = _string_list(recent.get("reportDate"))
        issuer_cik = _normalize_cik(str(data.get("cik", "")))
        for index, accession in enumerate(accessions):
            if index >= len(primary_documents):
                continue
            normalized = _normalize_accession(accession)
            self._submission_metadata_by_accession[normalized] = FilingMetadata(
                issuer_cik=issuer_cik,
                accession_number=accession,
                primary_document=primary_documents[index],
                filing_acceptance_at=_optional_index(acceptance_times, index),
                effective_at=_optional_index(report_dates, index),
            )

    async def _request_bytes(
        self,
        url: str,
        *,
        query: dict[str, str],
        as_of: date,
    ) -> SourceSnapshot:
        key = self.cache.key(self.provider, url, query, as_of)
        cached = (
            self._get_cached_request_snapshot(key, url, query=query, as_of=as_of)
            if not self._refresh_existing
            else None
        )
        if cached is not None:
            return cached
        try:
            response = await self._send_with_retries(url, query=query)
            response.raise_for_status()
        except Exception as exc:
            if _is_transient_exception(exc):
                stale = self._get_cached_request_snapshot(
                    key,
                    url,
                    query=query,
                    as_of=as_of,
                    stale=True,
                    primary_failure=_failure_summary(exc),
                )
            else:
                stale = None
            if stale is not None:
                return stale
            raise
        media_type = response.headers.get("Content-Type", "application/octet-stream").split(";")[0]
        return self.cache.put_bytes(
            key,
            response.content,
            provider=self.provider,
            provider_version=self.provider_version,
            source_url=str(response.url),
            query=query,
            as_of=as_of,
            media_type=media_type,
            license_class=self.license_class,
            retrieved_at=self._clock(),
        )

    def _get_cached_request_snapshot(
        self,
        key: str,
        url: str,
        *,
        query: dict[str, str],
        as_of: date,
        stale: bool = False,
        primary_failure: str | None = None,
    ) -> SourceSnapshot | None:
        return self.cache.get_for_request(
            key,
            provider=self.provider,
            provider_version=self.provider_version,
            source_url=url,
            query=query,
            as_of=as_of,
            license_class=self.license_class,
            stale=stale,
            primary_failure=primary_failure,
        )

    def _has_valid_request_cache(
        self,
        key: str,
        url: str,
        *,
        query: dict[str, str],
        as_of: date,
    ) -> bool:
        try:
            return self._get_cached_request_snapshot(key, url, query=query, as_of=as_of) is not None
        except ValueError as exc:
            if str(exc).startswith(("cache_context_mismatch:", "cache_storage_ref_mismatch")):
                return False
            raise

    async def _send_with_retries(self, url: str, *, query: dict[str, str]) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, 6):
            await self.limiter.acquire()
            try:
                response = await self.client.get(
                    url,
                    params=query,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept-Encoding": "gzip, deflate",
                    },
                )
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt == 5:
                    raise
                await self._sleep_before_retry(attempt, None)
                continue
            if not _is_retryable_response(response) or attempt == 5:
                return response
            last_exc = httpx.HTTPStatusError("retryable status", request=response.request, response=response)
            await self._sleep_before_retry(attempt, response)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("unreachable retry loop")

    async def _sleep_before_retry(self, attempt: int, response: httpx.Response | None) -> None:
        retry_after = _retry_after_seconds(response, self._clock()) if response is not None else None
        delay = retry_after if retry_after is not None else min(30.0, (2 ** (attempt - 1)) + self._jitter(attempt))
        await self._sleeper(delay)


def _normalize_cik(cik: str) -> str:
    digits = re.sub(r"\D", "", cik)
    if not digits:
        raise ValueError("cik must contain digits")
    return digits.zfill(10)


def _normalize_accession(accession_number: str) -> str:
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession_number.strip()):
        raise ValueError("invalid accession_number")
    return accession_number.replace("-", "")


def _is_retryable_response(response: httpx.Response) -> bool:
    return response.status_code == 429 or 500 <= response.status_code <= 599


def _is_transient_exception(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return _is_retryable_response(exc.response)
    return isinstance(exc, httpx.TimeoutException | httpx.ConnectError | httpx.NetworkError)


def _retry_after_seconds(response: httpx.Response | None, now: datetime) -> float | None:
    if response is None or "Retry-After" not in response.headers:
        return None
    value = response.headers["Retry-After"].strip()
    if value.isdigit():
        return min(30.0, float(value))
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return min(30.0, max(0.0, (parsed.astimezone(UTC) - now).total_seconds()))


def _failure_summary(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


class FilingMetadata:
    def __init__(
        self,
        *,
        issuer_cik: str,
        accession_number: str,
        primary_document: str,
        filing_acceptance_at: str | None,
        effective_at: str | None,
    ) -> None:
        self.issuer_cik = issuer_cik
        self.accession_number = accession_number
        self.primary_document = primary_document
        self.filing_acceptance_at = filing_acceptance_at
        self.effective_at = effective_at


def _archive_url(metadata: FilingMetadata) -> str:
    issuer_cik = str(int(metadata.issuer_cik))
    accession = _normalize_accession(metadata.accession_number)
    return (
        f"https://www.sec.gov/Archives/edgar/data/{issuer_cik}/"
        f"{accession}/{metadata.primary_document}"
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _optional_index(values: list[str], index: int) -> str | None:
    if index >= len(values):
        return None
    return values[index]
