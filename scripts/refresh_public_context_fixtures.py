from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Protocol

from due_diligence_agent.adapters.http.public_fixture_manifest import (
    verify_public_context_manifest,
)
from due_diligence_agent.adapters.market_data.yfinance_demo import (
    YFinanceDemoAdapter,
    ensure_live_dependency_available,
)
from due_diligence_agent.adapters.news.gdelt import GdeltNewsAdapter, news_item_from_gdelt_article
from due_diligence_agent.application.policies.content_rights import LicenseClass


GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


class MarketProvider(Protocol):
    def fetch(self, ticker: str, *, as_of: date) -> dict[str, Any]: ...


class NewsProvider(Protocol):
    def fetch(self, query: str, *, as_of: date) -> list[dict[str, Any]]: ...


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--market-output", required=True)
    parser.add_argument("--news-output", required=True)
    args = parser.parse_args(argv)
    try:
        ensure_live_dependency_available()
    except RuntimeError as exc:
        parser.exit(2, f"{exc}\n")
    refresh_public_context_fixtures(
        ticker=args.ticker,
        as_of=date.fromisoformat(args.as_of),
        market_output=Path(args.market_output),
        news_output=Path(args.news_output),
        market_provider=_LiveMarketProvider(),
        news_provider=_LiveNewsProvider(),
    )
    return 0


def refresh_public_context_fixtures(
    *,
    ticker: str,
    as_of: date,
    market_output: Path,
    news_output: Path,
    market_provider: MarketProvider,
    news_provider: NewsProvider,
) -> None:
    market_output = market_output.resolve()
    news_output = news_output.resolve()
    market_output.parent.mkdir(parents=True, exist_ok=True)
    news_output.parent.mkdir(parents=True, exist_ok=True)
    temp_parent = market_output.parent
    market_temp = Path(tempfile.mkdtemp(prefix=f".{market_output.name}.", dir=temp_parent))
    news_temp = Path(tempfile.mkdtemp(prefix=f".{news_output.name}.", dir=news_output.parent))
    try:
        _write_market_fixture(market_temp, ticker=ticker, as_of=as_of, provider=market_provider)
        _write_news_fixtures(news_temp, query=ticker, as_of=as_of, provider=news_provider)
        verify_public_context_manifest(
            market_temp / "manifest.json",
            expected_provider=YFinanceDemoAdapter.provider,
            expected_as_of=as_of,
            allowed_license_classes={LicenseClass.RESEARCH_ONLY.value},
        )
        verify_public_context_manifest(
            news_temp / "manifest.json",
            expected_provider=GdeltNewsAdapter.provider,
            expected_as_of=as_of,
            allowed_license_classes={
                LicenseClass.DISCOVERY_METADATA_ONLY.value,
                LicenseClass.RESEARCH_ONLY.value,
                LicenseClass.RIGHTS_CLEARED_FULL_TEXT.value,
            },
        )
        _publish_directories([(market_temp, market_output), (news_temp, news_output)])
    except Exception:
        for temp_root in (market_temp, news_temp):
            if temp_root.exists():
                shutil.rmtree(temp_root)
        raise


def _write_market_fixture(
    output: Path,
    *,
    ticker: str,
    as_of: date,
    provider: MarketProvider,
) -> None:
    payload = provider.fetch(ticker, as_of=as_of)
    name = f"{_slug(ticker)}_market_snapshot.json"
    _write_json(output / name, payload)
    _write_json(
        output / "manifest.json",
        {
            "provider": YFinanceDemoAdapter.provider,
            "ticker": ticker.upper(),
            "as_of": as_of.isoformat(),
            "license_class": LicenseClass.RESEARCH_ONLY.value,
            "files": {
                name: {
                    "provider": YFinanceDemoAdapter.provider,
                    "retrieval_url": str(payload["source_url"]),
                    "as_of": as_of.isoformat(),
                    "license_class": LicenseClass.RESEARCH_ONLY.value,
                    "sha256": _sha256(output / name),
                }
            },
        },
    )


def _write_news_fixtures(
    output: Path,
    *,
    query: str,
    as_of: date,
    provider: NewsProvider,
) -> None:
    records = provider.fetch(query, as_of=as_of)
    if len(records) < 5:
        raise ValueError("at least five news metadata records are required")
    adapter = GdeltNewsAdapter()
    files: dict[str, dict[str, str]] = {}
    for index, record in enumerate(records, start=1):
        if "source_url" in record:
            item = adapter.normalize_records([record])[0]
        else:
            item = news_item_from_gdelt_article(
                record,
                query=query,
                retrieved_at=datetime_now_utc(),
            ).model_dump(mode="json")
        name = f"story_{index}.json"
        _write_json(output / name, _news_fixture_payload(item))
        files[name] = {
            "provider": GdeltNewsAdapter.provider,
            "retrieval_url": f"{GDELT_DOC_URL}?query={query}&mode=artlist",
            "as_of": as_of.isoformat(),
            "license_class": str(item["license_class"]),
            "sha256": _sha256(output / name),
        }
    _write_json(
        output / "manifest.json",
        {
            "provider": GdeltNewsAdapter.provider,
            "query": query,
            "as_of": as_of.isoformat(),
            "license_class": LicenseClass.DISCOVERY_METADATA_ONLY.value,
            "files": files,
        },
    )


def _publish_directories(pairs: list[tuple[Path, Path]]) -> None:
    backups: list[tuple[Path, Path]] = []
    published: list[tuple[Path, Path]] = []
    try:
        for temp_root, output in pairs:
            backup = output.with_name(f".{output.name}.backup.{os.getpid()}")
            if backup.exists():
                shutil.rmtree(backup)
            if output.exists():
                output.rename(backup)
                backups.append((backup, output))
            temp_root.rename(output)
            published.append((temp_root, output))
    except Exception:
        for _temp_root, output in reversed(published):
            if output.exists():
                shutil.rmtree(output)
        for backup, output in reversed(backups):
            if backup.exists() and not output.exists():
                backup.rename(output)
        raise
    else:
        for backup, _output in backups:
            if backup.exists():
                shutil.rmtree(backup)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "_" for character in value)
    return "_".join(part for part in slug.split("_") if part)


class _LiveMarketProvider:
    def fetch(self, ticker: str, *, as_of: date) -> dict[str, Any]:
        return YFinanceDemoAdapter().fetch_live(ticker, as_of=as_of)


class _LiveNewsProvider:
    def __init__(
        self,
        *,
        client: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        self.client = client
        self.clock = clock

    def fetch(self, query: str, *, as_of: date) -> list[dict[str, Any]]:
        return [
            _news_fixture_payload(item.model_dump(mode="json"))
            for item in GdeltNewsAdapter(client=self.client, clock=self.clock).search(query, as_of=as_of)
        ]


def _news_fixture_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "source_url": item["url"],
        "publisher": item["publisher"],
        "domain": item["domain"],
        "title": item["title"],
        "snippet": item["snippet"],
        "published_at": item["published_at"],
        "query": item["query"],
        "retrieved_at": item["retrieved_at"],
        "license_class": item["license_class"],
        "response_hash": item["response_hash"],
        "provenance": item["provenance"],
    }
    if item.get("full_text") is not None:
        payload["full_text"] = item["full_text"]
    return payload


def datetime_now_utc() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
