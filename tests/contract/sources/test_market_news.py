from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from types import ModuleType
from typing import Any
from uuid import uuid4
import importlib.util
import sys

import httpx
import pytest

from due_diligence_agent.adapters.market_data.yfinance_demo import (
    YFinanceDemoAdapter,
    market_snapshot_from_payload,
)
from due_diligence_agent.adapters.news.gdelt import GdeltNewsAdapter, news_item_from_payload
from due_diligence_agent.application.policies.content_rights import (
    LicenseClass,
    may_store_full_text,
)
from due_diligence_agent.application.policies.source_priority import (
    SourcePriority,
    SourcePriorityPolicy,
)
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.ports.collectors import MarketDataPort, NewsItem, NewsSourcePort


FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "public_us_frozen_v1"
MARKET_DIR = FIXTURE_ROOT / "market"
NEWS_DIR = FIXTURE_ROOT / "news"
AS_OF = date(2026, 6, 30)


def test_demo_market_snapshot_is_always_secondary_unofficial_and_research_only() -> None:
    adapter = YFinanceDemoAdapter.from_fixture_dir(MARKET_DIR)

    snapshot = adapter.get_snapshot("AAPL", as_of=AS_OF)

    assert isinstance(adapter, MarketDataPort)
    assert snapshot.unofficial is True
    assert snapshot.research_only is True
    assert snapshot.license_class == LicenseClass.RESEARCH_ONLY
    assert snapshot.source_priority == SourcePriority.SECONDARY_AGGREGATOR
    assert snapshot.source_priority_label == "secondary_aggregator"
    assert snapshot.supports_primary_financial_metrics is False
    assert snapshot.snapshot.provider == "yfinance_demo"
    assert snapshot.snapshot.retrieved_at.tzinfo is UTC
    assert snapshot.snapshot.content_hash == _sha256(MARKET_DIR / "aapl_market_snapshot.json")
    with pytest.raises(Exception, match="frozen"):
        snapshot.prices[0].close = Decimal("999")


def test_market_port_get_snapshot_uses_fixture_path_without_yfinance() -> None:
    adapter: MarketDataPort = YFinanceDemoAdapter.from_fixture_dir(MARKET_DIR)

    snapshot = adapter.get_snapshot("AAPL", as_of=AS_OF)

    assert snapshot.ticker == "AAPL"
    assert snapshot.as_of == AS_OF
    assert snapshot.prices[0].close == Decimal("210.10")


def test_market_fixture_get_snapshot_rejects_ticker_and_as_of_mismatch(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture_dir(MARKET_DIR, tmp_path / "market")
    payload_path = fixture_dir / "msft_market_snapshot.json"
    shutil.copy2(fixture_dir / "aapl_market_snapshot.json", payload_path)
    manifest = _read_json(fixture_dir / "manifest.json")
    manifest["ticker"] = "MSFT"
    manifest["files"][payload_path.name] = {
        **manifest["files"]["aapl_market_snapshot.json"],
        "sha256": _sha256(payload_path),
    }
    _write_json(fixture_dir / "manifest.json", manifest)
    adapter = YFinanceDemoAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(ValueError, match="market fixture ticker mismatch"):
        adapter.get_snapshot("MSFT", as_of=AS_OF)

    fixture_dir = _copy_fixture_dir(MARKET_DIR, tmp_path / "market_as_of")
    adapter = YFinanceDemoAdapter.from_fixture_dir(fixture_dir)
    with pytest.raises(ValueError, match="manifest as_of mismatch"):
        adapter.get_snapshot("AAPL", as_of=date(2026, 6, 29))


def test_market_fixture_get_snapshot_verifies_manifest_hash_and_metadata(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture_dir(MARKET_DIR, tmp_path / "market")
    payload = _read_json(fixture_dir / "aapl_market_snapshot.json")
    payload["currency"] = "EUR"
    _write_json(fixture_dir / "aapl_market_snapshot.json", payload)
    adapter = YFinanceDemoAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(ValueError, match="fixture hash mismatch"):
        adapter.get_snapshot("AAPL", as_of=AS_OF)

    fixture_dir = _copy_fixture_dir(MARKET_DIR, tmp_path / "wrong_market_provider")
    manifest = _read_json(fixture_dir / "manifest.json")
    manifest["files"]["aapl_market_snapshot.json"]["provider"] = "wrong"
    _write_json(fixture_dir / "manifest.json", manifest)
    adapter = YFinanceDemoAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(ValueError, match="manifest provider mismatch"):
        adapter.get_snapshot("AAPL", as_of=AS_OF)

    fixture_dir = _copy_fixture_dir(MARKET_DIR, tmp_path / "wrong_market_license")
    manifest = _read_json(fixture_dir / "manifest.json")
    manifest["files"]["aapl_market_snapshot.json"]["license_class"] = "public_primary"
    _write_json(fixture_dir / "manifest.json", manifest)
    adapter = YFinanceDemoAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(ValueError, match="manifest license_class mismatch"):
        adapter.get_snapshot("AAPL", as_of=AS_OF)


def test_market_fixture_public_helpers_cannot_bypass_manifest_validation(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture_dir(MARKET_DIR, tmp_path / "market")
    payload = _read_json(fixture_dir / "aapl_market_snapshot.json")
    payload["ticker"] = "MSFT"
    _write_json(fixture_dir / "aapl_market_snapshot.json", payload)
    adapter = YFinanceDemoAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(AttributeError):
        getattr(adapter, "load_fixture")("aapl_market_snapshot.json")

    with pytest.raises(ValueError, match="fixture hash mismatch"):
        adapter.get_snapshot("AAPL", as_of=AS_OF)


def test_malformed_market_price_fails_deterministically(tmp_path: Path) -> None:
    fixture = tmp_path / "bad_market.json"
    payload = _read_json(MARKET_DIR / "aapl_market_snapshot.json")
    payload["prices"][0]["volume"] = "not-an-integer"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="volume"):
        market_snapshot_from_payload(payload, payload_path=fixture)


def test_live_market_snapshot_hashes_payload_without_cwd_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, "yfinance", _fake_yfinance_module())
    adapter = YFinanceDemoAdapter()

    snapshot = adapter.get_snapshot("AAPL", as_of=AS_OF)

    assert snapshot.ticker == "AAPL"
    assert snapshot.snapshot.content_hash
    assert not (tmp_path / "aapl_market_snapshot.json").exists()


def test_live_market_snapshot_uses_as_of_bounded_history_and_filters_future_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_yfinance = _fake_yfinance_module(include_future=True)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)
    adapter = YFinanceDemoAdapter()

    snapshot = adapter.get_snapshot("AAPL", as_of=AS_OF)

    assert fake_yfinance.calls == [
        {
            "ticker": "AAPL",
            "start": "2026-06-23",
            "end": "2026-07-01",
            "period": None,
        }
    ]
    assert [point.date for point in snapshot.prices] == [AS_OF]


def test_market_data_is_rejected_as_sole_critical_financial_evidence() -> None:
    policy = SourcePriorityPolicy()
    market_fact = EvidenceFact(
        id=uuid4(),
        artifact_id=uuid4(),
        name="market_cap",
        value=Decimal("2900000000000"),
        value_type="decimal",
        unit="USD",
        period="2026-06-30",
        locator=SourceLocator(kind="market_data", value="AAPL:market_cap"),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.80"),
        source_priority=SourcePriority.SECONDARY_AGGREGATOR,
        extraction_method="yfinance_demo",
        retrieved_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    assert policy.can_support_critical_claim([market_fact], category="valuation") is False
    assert policy.can_support_critical_claim([market_fact], category="market_context") is True


def test_task6_imports_without_importing_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    imported: list[str] = []
    real_import = __import__

    def guard_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "yfinance" or name.startswith("yfinance."):
            imported.append(name)
            raise AssertionError("yfinance must not be imported on fixture paths")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guard_import)

    adapter = YFinanceDemoAdapter.from_fixture_dir(MARKET_DIR)
    snapshot = adapter.get_snapshot("AAPL", as_of=AS_OF)

    assert snapshot.ticker == "AAPL"
    assert imported == []


def test_news_discards_restricted_full_text_and_never_serializes_it(tmp_path: Path) -> None:
    restricted_payload = _read_json(NEWS_DIR / "restricted_story_input.json")
    restricted_payload["full_text"] = (
        "Restricted full article body that must be discarded before serialization."
    )
    (tmp_path / "restricted_story_input.json").write_text(
        json.dumps(restricted_payload),
        encoding="utf-8",
    )
    item = news_item_from_payload(
        restricted_payload,
        payload_path=tmp_path / "restricted_story_input.json",
    )
    serialized = item.model_dump_json()

    assert item.full_text is None
    assert "Restricted full article body" not in serialized
    assert "Restricted full article body" not in _fixture_tree_text(NEWS_DIR)


def test_news_item_model_boundary_discards_disallowed_full_text() -> None:
    item = NewsItem(
        url="https://restricted.example/body",
        publisher="Restricted Example",
        domain="restricted.example",
        title="Restricted body",
        snippet="Snippet only.",
        published_at=datetime(2026, 6, 28, tzinfo=UTC),
        query="AAPL",
        retrieved_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        response_hash="a" * 64,
        license_class=LicenseClass.RESEARCH_ONLY,
        provenance={
            "provider": "gdelt",
            "provider_version": "doc-api-2.0",
            "source_url": "https://restricted.example/body",
            "response_hash": "a" * 64,
        },
        full_text="Restricted full article body that must not survive.",
    )

    assert item.full_text is None
    assert "Restricted full article body" not in item.model_dump_json()


def test_rights_cleared_full_text_is_the_only_allowed_body_path() -> None:
    restricted = news_item_from_payload(
        _read_json(NEWS_DIR / "restricted_story_input.json"),
        payload_path=NEWS_DIR / "restricted_story_input.json",
    )
    rights_cleared = news_item_from_payload(
        _read_json(NEWS_DIR / "rights_cleared_story_input.json"),
        payload_path=NEWS_DIR / "rights_cleared_story_input.json",
    )

    assert may_store_full_text(LicenseClass.RESEARCH_ONLY) is False
    assert may_store_full_text(LicenseClass.DISCOVERY_METADATA_ONLY) is False
    assert may_store_full_text(LicenseClass.PUBLIC_PRIMARY) is False
    assert may_store_full_text(LicenseClass.RIGHTS_CLEARED_FULL_TEXT) is True
    assert restricted.full_text is None
    assert rights_cleared.full_text == "Rights-cleared article body for offline contract testing."


def test_news_metadata_is_immutable_utc_hashed_and_non_financial_primary() -> None:
    adapter = GdeltNewsAdapter.from_fixture_dir(NEWS_DIR)

    item = adapter.search("AAPL", as_of=AS_OF)[0]

    assert isinstance(adapter, NewsSourcePort)
    assert item.query == "AAPL"
    assert item.published_at.tzinfo is UTC
    assert item.retrieved_at.tzinfo is UTC
    assert item.response_hash == _canonical_hash(
        {
            "url": "https://example.com/business/aapl-supplier-context",
            "sourceCommonName": "Example Business",
            "domain": "example.com",
            "title": "Apple supplier update draws investor attention",
            "snippet": "Apple supplier news creates a neutral context item for the frozen demo.",
            "seendate": "20260624133000",
        }
    )
    assert item.response_hash != _sha256(NEWS_DIR / "story_1.json")
    assert item.provenance.provider == "gdelt"
    assert item.provenance.source_url == item.url
    assert item.provenance.response_hash == item.response_hash
    assert item.supports_event_narrative_claims is True
    assert item.supports_primary_financial_metrics is False
    assert item.polarity == "neutral"
    with pytest.raises(Exception, match="frozen"):
        item.title = "mutated"


def test_news_fixture_polarity_label_survives_title_heuristic_conflict(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture_dir(NEWS_DIR, tmp_path / "news")
    story = _read_json(fixture_dir / "story_4.json")
    story["title"] = "Apple expands supplier program with positive customer momentum"
    story["polarity"] = "negative"
    _write_json(fixture_dir / "story_4.json", story)
    manifest = _read_json(fixture_dir / "manifest.json")
    manifest["files"]["story_4.json"]["sha256"] = _sha256(fixture_dir / "story_4.json")
    _write_json(fixture_dir / "manifest.json", manifest)

    item = GdeltNewsAdapter.from_fixture_dir(fixture_dir).search("AAPL", as_of=AS_OF)[3]

    assert item.title == "Apple expands supplier program with positive customer momentum"
    assert item.polarity == "negative"


def test_news_item_rejects_inconsistent_provenance_hash_or_url() -> None:
    with pytest.raises(ValueError, match="provenance"):
        NewsItem(
            url="https://example.com/a",
            publisher="Example",
            domain="example.com",
            title="Inconsistent provenance",
            snippet="Snippet.",
            published_at=datetime(2026, 6, 28, tzinfo=UTC),
            query="AAPL",
            retrieved_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
            response_hash="a" * 64,
            license_class=LicenseClass.DISCOVERY_METADATA_ONLY,
            provenance={
                "provider": "gdelt",
                "provider_version": "doc-api-2.0",
                "source_url": "https://example.com/b",
                "response_hash": "b" * 64,
            },
        )


def test_news_port_search_can_fetch_gdelt_metadata_with_mocked_client() -> None:
    client = FakeGdeltClient(
        {
            "articles": [
                {
                    "url": "https://example.com/gdelt/aapl",
                    "sourceCommonName": "Example Business",
                    "domain": "example.com",
                    "title": "Apple GDELT metadata item",
                    "snippet": "GDELT-provided snippet only.",
                    "seendate": "20260630120000",
                },
                {
                    "url": "https://example.com/gdelt/aapl-future",
                    "sourceCommonName": "Example Business",
                    "domain": "example.com",
                    "title": "Future item after as_of",
                    "snippet": "Must be filtered out.",
                    "seendate": "20260701120000",
                },
            ]
        }
    )
    adapter: NewsSourcePort = GdeltNewsAdapter(
        client=client,
        clock=lambda: datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    items = adapter.search("AAPL", as_of=AS_OF)

    assert client.urls == ["https://api.gdeltproject.org/api/v2/doc/doc"]
    assert client.params[0]["query"] == "AAPL"
    assert client.params[0]["enddatetime"] == "20260630235959"
    assert len(items) == 1
    assert items[0].url == "https://example.com/gdelt/aapl"
    assert items[0].full_text is None
    assert items[0].published_at == datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    assert items[0].response_hash == _canonical_hash(client.payload["articles"][0])


def test_gdelt_live_response_hash_is_stable_across_retrieval_clocks() -> None:
    payload = {
        "articles": [
            {
                "url": "https://example.com/gdelt/aapl",
                "sourceCommonName": "Example Business",
                "domain": "example.com",
                "title": "Apple GDELT metadata item",
                "snippet": "GDELT-provided snippet only.",
                "seendate": "20260630120000",
            }
        ]
    }
    morning = GdeltNewsAdapter(
        client=FakeGdeltClient(payload),
        clock=lambda: datetime(2026, 8, 9, 8, 0, tzinfo=UTC),
    ).search("AAPL", as_of=AS_OF)[0]
    evening = GdeltNewsAdapter(
        client=FakeGdeltClient(payload),
        clock=lambda: datetime(2026, 8, 9, 20, 0, tzinfo=UTC),
    ).search("AAPL", as_of=AS_OF)[0]

    assert morning.retrieved_at != evening.retrieved_at
    assert morning.response_hash == evening.response_hash == _canonical_hash(payload["articles"][0])


def test_news_fixture_search_rejects_query_and_as_of_mismatch() -> None:
    adapter = GdeltNewsAdapter.from_fixture_dir(NEWS_DIR)

    with pytest.raises(ValueError, match="manifest query mismatch"):
        adapter.search("MSFT", as_of=AS_OF)
    with pytest.raises(ValueError, match="manifest as_of mismatch"):
        adapter.search("AAPL", as_of=date(2026, 6, 29))


def test_news_fixture_search_rejects_future_or_wrong_query_records(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture_dir(NEWS_DIR, tmp_path / "news")
    story = _read_json(fixture_dir / "story_1.json")
    story["published_at"] = "2026-07-01T00:00:00Z"
    _write_json(fixture_dir / "story_1.json", story)
    manifest = _read_json(fixture_dir / "manifest.json")
    manifest["files"]["story_1.json"]["sha256"] = _sha256(fixture_dir / "story_1.json")
    _write_json(fixture_dir / "manifest.json", manifest)
    adapter = GdeltNewsAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(ValueError, match="news fixture published_at after as_of"):
        adapter.search("AAPL", as_of=AS_OF)

    fixture_dir = _copy_fixture_dir(NEWS_DIR, tmp_path / "wrong_record_query")
    story = _read_json(fixture_dir / "story_1.json")
    story["query"] = "MSFT"
    _write_json(fixture_dir / "story_1.json", story)
    manifest = _read_json(fixture_dir / "manifest.json")
    manifest["files"]["story_1.json"]["sha256"] = _sha256(fixture_dir / "story_1.json")
    _write_json(fixture_dir / "manifest.json", manifest)
    adapter = GdeltNewsAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(ValueError, match="news fixture query mismatch"):
        adapter.search("AAPL", as_of=AS_OF)


def test_news_fixture_search_verifies_manifest_hash_and_metadata(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture_dir(NEWS_DIR, tmp_path / "news")
    story = _read_json(fixture_dir / "story_1.json")
    story["snippet"] = "Tampered after manifest hash."
    _write_json(fixture_dir / "story_1.json", story)
    adapter = GdeltNewsAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(ValueError, match="fixture hash mismatch"):
        adapter.search("AAPL", as_of=AS_OF)

    fixture_dir = _copy_fixture_dir(NEWS_DIR, tmp_path / "wrong_news_license")
    manifest = _read_json(fixture_dir / "manifest.json")
    manifest["files"]["story_1.json"]["license_class"] = "public_primary"
    _write_json(fixture_dir / "manifest.json", manifest)
    adapter = GdeltNewsAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(ValueError, match="manifest license_class mismatch"):
        adapter.search("AAPL", as_of=AS_OF)

    fixture_dir = _copy_fixture_dir(NEWS_DIR, tmp_path / "wrong_news_provider")
    manifest = _read_json(fixture_dir / "manifest.json")
    manifest["files"]["story_1.json"]["provider"] = "wrong"
    _write_json(fixture_dir / "manifest.json", manifest)
    adapter = GdeltNewsAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(ValueError, match="manifest provider mismatch"):
        adapter.search("AAPL", as_of=AS_OF)


def test_news_fixture_public_helpers_cannot_bypass_manifest_validation(tmp_path: Path) -> None:
    fixture_dir = _copy_fixture_dir(NEWS_DIR, tmp_path / "news")
    story = _read_json(fixture_dir / "story_1.json")
    story["query"] = "MSFT"
    _write_json(fixture_dir / "story_1.json", story)
    adapter = GdeltNewsAdapter.from_fixture_dir(fixture_dir)

    with pytest.raises(AttributeError):
        getattr(adapter, "load_fixture")("story_1.json")
    with pytest.raises(AttributeError):
        getattr(adapter, "load_all_fixture_records")()

    with pytest.raises(ValueError, match="fixture hash mismatch"):
        adapter.search("AAPL", as_of=AS_OF)


def test_news_fixture_has_at_least_five_metadata_records_and_complete_hash_manifest() -> None:
    adapter = GdeltNewsAdapter.from_fixture_dir(NEWS_DIR)

    items = adapter.search("AAPL", as_of=AS_OF)
    manifest = json.loads((NEWS_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert len(items) >= 5
    assert all(
        item.full_text is None
        for item in items
        if item.license_class != LicenseClass.RIGHTS_CLEARED_FULL_TEXT
    )
    for name, entry in manifest["files"].items():
        assert entry["sha256"] == _sha256(NEWS_DIR / name)
        assert entry["retrieval_url"].startswith("https://api.gdeltproject.org/")
        assert entry["provider"] == "gdelt"
        assert entry["as_of"] == "2026-06-30"
        assert entry["license_class"] in {license_class.value for license_class in LicenseClass}


def test_malformed_news_metadata_fails_deterministically() -> None:
    with pytest.raises(ValueError, match="title"):
        news_item_from_payload(
            _read_json(NEWS_DIR / "malformed_missing_title.json"),
            payload_path=NEWS_DIR / "malformed_missing_title.json",
        )


def test_refresh_script_uses_temp_output_validates_before_publish_and_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_refresh_script()
    output_market = tmp_path / "market"
    output_news = tmp_path / "news"
    output_market.mkdir()
    output_news.mkdir()
    (output_market / "original.txt").write_text("original-market", encoding="utf-8")
    (output_news / "original.txt").write_text("original-news", encoding="utf-8")
    calls: list[str] = []

    class FakeMarketProvider:
        def fetch(self, ticker: str, *, as_of: date) -> dict[str, Any]:
            calls.append(f"market:{ticker}:{as_of.isoformat()}")
            return _read_json(MARKET_DIR / "aapl_market_snapshot.json")

    class FakeNewsProvider:
        def fetch(self, query: str, *, as_of: date) -> list[dict[str, Any]]:
            calls.append(f"news:{query}:{as_of.isoformat()}")
            return [_read_json(NEWS_DIR / f"story_{index}.json") for index in range(1, 6)]

    original_verify_public_context_manifest = module.verify_public_context_manifest

    def fail_news_manifest(
        path: Path,
        *,
        expected_provider: str,
        expected_as_of: date,
        allowed_license_classes: set[str],
    ) -> dict[str, Any]:
        if path.parent.name.startswith(f".{output_news.name}."):
            raise ValueError("forced manifest failure")
        return original_verify_public_context_manifest(
            path,
            expected_provider=expected_provider,
            expected_as_of=expected_as_of,
            allowed_license_classes=allowed_license_classes,
        )

    monkeypatch.setattr(module, "verify_public_context_manifest", fail_news_manifest)

    with pytest.raises(ValueError, match="forced manifest failure"):
        module.refresh_public_context_fixtures(
            ticker="AAPL",
            as_of=AS_OF,
            market_output=output_market,
            news_output=output_news,
            market_provider=FakeMarketProvider(),
            news_provider=FakeNewsProvider(),
        )

    assert calls == ["market:AAPL:2026-06-30", "news:AAPL:2026-06-30"]
    assert (output_market / "original.txt").read_text(encoding="utf-8") == "original-market"
    assert (output_news / "original.txt").read_text(encoding="utf-8") == "original-news"


def test_refresh_persists_news_response_hash_and_provenance_without_body_leak(
    tmp_path: Path,
) -> None:
    module = _load_refresh_script()
    output_market = tmp_path / "market"
    output_news = tmp_path / "news"
    raw_articles = [
        {
            "url": f"https://example.com/gdelt/aapl-{index}",
            "sourceCommonName": "Example Business",
            "domain": "example.com",
            "title": f"Apple GDELT metadata item {index}",
            "snippet": "GDELT-provided snippet only.",
            "seendate": "20260630120000",
            "full_text": "Restricted full article body must never be published.",
        }
        for index in range(1, 6)
    ]

    class FakeMarketProvider:
        def fetch(self, ticker: str, *, as_of: date) -> dict[str, Any]:
            return _read_json(MARKET_DIR / "aapl_market_snapshot.json")

    class FakeNewsProvider:
        def fetch(self, query: str, *, as_of: date) -> list[dict[str, Any]]:
            return raw_articles

    module.refresh_public_context_fixtures(
        ticker="AAPL",
        as_of=AS_OF,
        market_output=output_market,
        news_output=output_news,
        market_provider=FakeMarketProvider(),
        news_provider=FakeNewsProvider(),
    )

    refreshed = GdeltNewsAdapter.from_fixture_dir(output_news).search("AAPL", as_of=AS_OF)[0]
    persisted = _read_json(output_news / "story_1.json")
    assert refreshed.response_hash == _canonical_hash(raw_articles[0])
    assert refreshed.provenance.response_hash == refreshed.response_hash
    assert refreshed.provenance.source_url == refreshed.url
    assert persisted["response_hash"] == refreshed.response_hash
    assert persisted["provenance"]["provider"] == "gdelt"
    assert "Restricted full article body" not in _fixture_tree_text(output_news)


def test_refresh_requires_minimum_five_news_records_before_publish(tmp_path: Path) -> None:
    module = _load_refresh_script()
    output_market = tmp_path / "market"
    output_news = tmp_path / "news"

    class FakeMarketProvider:
        def fetch(self, ticker: str, *, as_of: date) -> dict[str, Any]:
            return _read_json(MARKET_DIR / "aapl_market_snapshot.json")

    class TooFewNewsProvider:
        def fetch(self, query: str, *, as_of: date) -> list[dict[str, Any]]:
            return [_read_json(NEWS_DIR / "story_1.json")]

    with pytest.raises(ValueError, match="at least five news metadata records"):
        module.refresh_public_context_fixtures(
            ticker="AAPL",
            as_of=AS_OF,
            market_output=output_market,
            news_output=output_news,
            market_provider=FakeMarketProvider(),
            news_provider=TooFewNewsProvider(),
        )

    assert not output_market.exists()
    assert not output_news.exists()


def test_refresh_manifest_validation_rejects_wrong_provider_or_license(tmp_path: Path) -> None:
    module = _load_refresh_script()
    market = tmp_path / "market"
    market.mkdir()
    source = MARKET_DIR / "aapl_market_snapshot.json"
    (market / source.name).write_bytes(source.read_bytes())
    (market / "manifest.json").write_text(
        json.dumps(
            {
                "provider": "wrong",
                "as_of": "2026-06-30",
                "license_class": "research_only",
                "files": {
                    source.name: {
                        "provider": "wrong",
                        "retrieval_url": "https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
                        "as_of": "2026-06-30",
                        "license_class": "research_only",
                        "sha256": _sha256(source),
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest provider"):
        module.verify_public_context_manifest(
            market / "manifest.json",
            expected_provider="yfinance_demo",
            expected_as_of=AS_OF,
            allowed_license_classes={LicenseClass.RESEARCH_ONLY.value},
        )


def test_live_news_provider_uses_gdelt_adapter_with_injected_client() -> None:
    module = _load_refresh_script()
    client = FakeGdeltClient(
        {
            "articles": [
                {
                    "url": f"https://example.com/gdelt/aapl-{index}",
                    "sourceCommonName": "Example Business",
                    "domain": "example.com",
                    "title": f"Apple GDELT metadata item {index}",
                    "snippet": "GDELT-provided snippet only.",
                    "seendate": "20260630120000",
                }
                for index in range(1, 6)
            ]
        }
    )
    provider = module._LiveNewsProvider(
        client=client,
        clock=lambda: datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    records = provider.fetch("AAPL", as_of=AS_OF)

    assert len(records) == 5
    assert records[0]["source_url"] == "https://example.com/gdelt/aapl-1"
    assert "full_text" not in records[0]


def test_refresh_script_rejects_missing_yfinance_before_partial_live_publish(
    tmp_path: Path,
) -> None:
    module = _load_refresh_script()

    with pytest.raises(SystemExit) as excinfo:
        module.main(
            [
                "--ticker",
                "AAPL",
                "--as-of",
                "2026-06-30",
                "--market-output",
                str(tmp_path / "market"),
                "--news-output",
                str(tmp_path / "news"),
            ]
        )

    assert excinfo.value.code == 2
    assert not (tmp_path / "market").exists()
    assert not (tmp_path / "news").exists()


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _canonical_hash(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _copy_fixture_dir(source: Path, target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target)
    return Path(shutil.copytree(source, target))


def _fixture_tree_text(root: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.json")))


def _load_refresh_script() -> ModuleType:
    script_path = Path(__file__).parents[3] / "scripts" / "refresh_public_context_fixtures.py"
    spec = importlib.util.spec_from_file_location("refresh_public_context_fixtures", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("refresh_public_context_fixtures.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeGdeltClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.urls: list[str] = []
        self.params: list[dict[str, str]] = []

    def get(self, url: str, *, params: dict[str, str]) -> httpx.Response:
        self.urls.append(url)
        self.params.append(params)
        return httpx.Response(200, json=self.payload, request=httpx.Request("GET", url))


def _fake_yfinance_module(*, include_future: bool = False) -> object:
    calls: list[dict[str, str | None]] = []

    class FakeIndex:
        def __init__(self, value: date) -> None:
            self._value = value

        def date(self) -> date:
            return self._value

    class FakeHistory:
        def iterrows(self) -> list[tuple[FakeIndex, dict[str, object]]]:
            rows = [
                (FakeIndex(date(2026, 6, 30)), {"Close": Decimal("212.05"), "Volume": 40123456})
            ]
            if include_future:
                rows.append((FakeIndex(date(2026, 7, 1)), {"Close": Decimal("999"), "Volume": 1}))
            return rows

    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(
            self,
            *,
            start: str | None = None,
            end: str | None = None,
            period: str | None = None,
        ) -> FakeHistory:
            calls.append({"ticker": self.ticker, "start": start, "end": end, "period": period})
            return FakeHistory()

    return SimpleNamespace(Ticker=FakeTicker, calls=calls)
