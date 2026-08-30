from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal

import httpx

from due_diligence_agent.adapters.http.public_fixture_manifest import (
    verify_public_context_manifest,
)
from due_diligence_agent.application.policies.content_rights import (
    LicenseClass,
    may_store_full_text,
)
from due_diligence_agent.ports.collectors import NewsItem, NewsProvenance


GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


class GdeltNewsAdapter:
    provider = "gdelt"
    provider_version = "doc-api-2.0"
    default_license_class = LicenseClass.DISCOVERY_METADATA_ONLY

    def __init__(
        self,
        fixture_dir: Path | None = None,
        *,
        client: Any | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.fixture_dir = fixture_dir
        self.client = client or httpx.Client()
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def from_fixture_dir(cls, fixture_dir: Path) -> "GdeltNewsAdapter":
        return cls(fixture_dir=fixture_dir)

    def search(self, query: str, *, as_of: date) -> tuple[NewsItem, ...]:
        if self.fixture_dir is not None:
            manifest = verify_public_context_manifest(
                self.fixture_dir / "manifest.json",
                expected_provider=self.provider,
                expected_as_of=as_of,
                allowed_license_classes={
                    LicenseClass.DISCOVERY_METADATA_ONLY.value,
                    LicenseClass.RESEARCH_ONLY.value,
                    LicenseClass.RIGHTS_CLEARED_FULL_TEXT.value,
                },
                expected_query=query,
            )
            fixture_items: list[NewsItem] = []
            for name in sorted(manifest["files"]):
                if not name.startswith("story_"):
                    continue
                entry = manifest["files"][name]
                item = _load_news_fixture(self.fixture_dir, name)
                if item.query != query:
                    raise ValueError("news fixture query mismatch")
                if item.published_at.date() > as_of:
                    raise ValueError("news fixture published_at after as_of")
                if item.license_class.value != entry["license_class"]:
                    raise ValueError("news fixture license_class mismatch")
                if item.provenance.provider != self.provider:
                    raise ValueError("news fixture provenance provider mismatch")
                if item.provenance.provider != entry["provider"]:
                    raise ValueError("news fixture provenance provider mismatch")
                if item.response_hash != item.provenance.response_hash:
                    raise ValueError("news fixture provenance hash mismatch")
                fixture_items.append(item)
            return tuple(fixture_items)
        response = self.client.get(
            GDELT_DOC_URL,
            params={
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": "25",
                "enddatetime": as_of.strftime("%Y%m%d235959"),
            },
        )
        response.raise_for_status()
        payload = response.json()
        articles = payload.get("articles", [])
        if not isinstance(articles, list):
            raise ValueError("gdelt response missing articles")
        items: list[NewsItem] = []
        for article in articles:
            if isinstance(article, dict):
                item = news_item_from_gdelt_article(
                    article,
                    query=query,
                    retrieved_at=self._clock(),
                )
                if item.published_at.date() > as_of:
                    continue
                items.append(item)
        return tuple(items)

    def normalize_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for record in records:
            if "source_url" in record:
                item = news_item_from_payload(record, payload_path=None)
            else:
                item = news_item_from_gdelt_article(
                    record,
                    query=str(record.get("query", "")),
                    retrieved_at=datetime.now(UTC),
                )
            normalized.append(item.model_dump(mode="json"))
        return normalized


def news_item_from_payload(
    payload: dict[str, Any],
    *,
    payload_path: Path | None,
    response_hash: str | None = None,
) -> NewsItem:
    missing = [
        field
        for field in (
            "source_url",
            "publisher",
            "domain",
            "title",
            "snippet",
            "published_at",
            "query",
            "retrieved_at",
        )
        if field not in payload
    ]
    if missing:
        raise ValueError(f"news metadata missing:{','.join(missing)}")
    license_class = LicenseClass(payload.get("license_class", LicenseClass.DISCOVERY_METADATA_ONLY))
    body = payload.get("full_text") if may_store_full_text(license_class) else None
    computed_hash = (
        response_hash
        or str(payload.get("response_hash") or "")
        or (
            sha256(payload_path.read_bytes()).hexdigest()
            if payload_path is not None
            else sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        )
    )
    url = str(payload["source_url"])
    provenance_payload = payload.get("provenance")
    provenance = (
        NewsProvenance(**provenance_payload)
        if isinstance(provenance_payload, dict)
        else NewsProvenance(
            provider=GdeltNewsAdapter.provider,
            provider_version=GdeltNewsAdapter.provider_version,
            source_url=url,
            response_hash=computed_hash,
        )
    )
    return NewsItem(
        url=url,
        publisher=str(payload["publisher"]),
        domain=str(payload["domain"]),
        title=str(payload["title"]),
        snippet=str(payload["snippet"]),
        published_at=_parse_utc(str(payload["published_at"])),
        query=str(payload["query"]),
        retrieved_at=_parse_utc(str(payload["retrieved_at"])),
        response_hash=computed_hash,
        license_class=license_class,
        provenance=provenance,
        full_text=str(body) if body is not None else None,
        polarity=_news_polarity_from_payload(payload),
    )


def _load_news_fixture(fixture_dir: Path, name: str) -> NewsItem:
    path = _safe_fixture_path(fixture_dir, name)
    return news_item_from_payload(json.loads(path.read_text(encoding="utf-8")), payload_path=path)


def _safe_fixture_path(root: Path, name: str) -> Path:
    resolved_root = root.resolve()
    path = (resolved_root / name).resolve()
    if resolved_root not in path.parents:
        raise ValueError("fixture path escapes root")
    return path


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _metadata_from_gdelt_article(
    article: dict[str, Any], *, query: str, retrieved_at: datetime, published_at: datetime
) -> dict[str, Any]:
    url = str(article.get("url", "")).strip()
    if not url:
        raise ValueError("gdelt article missing url")
    return {
        "source_url": url,
        "publisher": str(article.get("sourceCommonName") or article.get("source") or ""),
        "domain": str(article.get("domain") or _domain_from_url(url)),
        "title": str(article.get("title") or ""),
        "snippet": str(article.get("snippet") or article.get("description") or ""),
        "published_at": published_at.isoformat().replace("+00:00", "Z"),
        "query": query,
        "retrieved_at": retrieved_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "license_class": LicenseClass.DISCOVERY_METADATA_ONLY.value,
    }


NewsPolarity = Literal["positive", "neutral", "negative"]


def _news_polarity_from_payload(payload: dict[str, Any]) -> NewsPolarity | None:
    value = payload.get("polarity")
    if value is None:
        return None
    label = str(value)
    if label == "positive":
        return "positive"
    if label == "neutral":
        return "neutral"
    if label == "negative":
        return "negative"
    raise ValueError("news polarity must be positive, neutral, or negative")


def news_item_from_gdelt_article(
    article: dict[str, Any], *, query: str, retrieved_at: datetime
) -> NewsItem:
    published_at = _parse_gdelt_datetime(
        str(article.get("seendate") or article.get("published_at") or "")
    )
    response_hash = _canonical_hash(article)
    return news_item_from_payload(
        _metadata_from_gdelt_article(
            article,
            query=query,
            retrieved_at=retrieved_at,
            published_at=published_at,
        ),
        payload_path=None,
        response_hash=response_hash,
    )


def _parse_gdelt_datetime(value: str) -> datetime:
    clean = value.strip()
    if len(clean) == 14 and clean.isdigit():
        return datetime.strptime(clean, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if clean:
        return _parse_utc(clean)
    raise ValueError("gdelt article missing seendate")


def _domain_from_url(url: str) -> str:
    return httpx.URL(url).host or ""


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _canonical_hash(payload: object) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
