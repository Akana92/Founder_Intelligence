from __future__ import annotations

import json
from datetime import UTC, date, datetime
from hashlib import sha256
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx

from due_diligence_agent.adapters.http.fair_access import FairAccessLimiter
from due_diligence_agent.adapters.http.snapshot_cache import SnapshotCache, verify_fixture_manifest
from due_diligence_agent.adapters.sec.edgar import MissingUserAgentError, SecEdgarAdapter
from due_diligence_agent.workflows.shared.node_result import NodeStatus


FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "public_us_frozen_v1" / "sec"
TEST_USER_AGENT = "CapstoneN3 test@example.com"
AS_OF = date(2026, 6, 30)
APPLE_CIK = "0000320193"
BERKSHIRE_CIK = "0001067983"


@pytest.mark.asyncio
@respx.mock
async def test_sec_adapter_declares_user_agent_and_caches_response(tmp_path: Path) -> None:
    route = respx.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{APPLE_CIK}.json").mock(
        return_value=httpx.Response(200, json=_fixture_json("companyfacts.json"))
    )
    adapter = _adapter(tmp_path)

    first = await adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)
    second = await adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)

    assert route.call_count == 1
    assert route.calls[0].request.headers["User-Agent"] == TEST_USER_AGENT
    assert first.snapshot.content_hash == second.snapshot.content_hash
    assert first.snapshot.query == {"cik": APPLE_CIK}
    assert first.snapshot.retrieved_at.tzinfo == UTC
    with pytest.raises(TypeError):
        first.data["cik"] = "mutated"
    with pytest.raises(TypeError):
        first.data["facts"]["us-gaap"] = {}


def test_snapshot_cache_normalizes_query_and_rejects_conflicting_snapshot_bytes(
    tmp_path: Path,
) -> None:
    cache = SnapshotCache(tmp_path)
    first_key = cache.key(
        "sec", "/companyfacts", {"ticker": " AAPL ", "form": "10-K"}, AS_OF
    )
    second_key = cache.key(
        "sec", "/companyfacts", {"form": "10-K", "ticker": "AAPL"}, AS_OF
    )

    snapshot = cache.put_bytes(
        first_key,
        b'{"ok":true}',
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"ticker": "AAPL", "form": "10-K"},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )

    assert first_key == second_key
    assert cache.get(first_key).content_hash == snapshot.content_hash
    with pytest.raises(ValueError, match="immutable snapshot key conflict"):
        cache.put_bytes(
            first_key,
            b'{"ok":false}',
            provider="sec",
            provider_version="2026-08-09",
            source_url="https://data.sec.gov/example",
            query={"ticker": "AAPL", "form": "10-K"},
            as_of=AS_OF,
            media_type="application/json",
            license_class="public_primary",
        )


def test_snapshot_cache_rejects_corrupted_cached_payload(tmp_path: Path) -> None:
    cache = SnapshotCache(tmp_path)
    key = cache.key("sec", "/submissions", {"cik": APPLE_CIK}, AS_OF)
    snapshot = cache.put_bytes(
        key,
        b'{"ok":true}',
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/submissions/CIK0000320193.json",
        query={"cik": APPLE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )
    payload_path = tmp_path / "payloads" / snapshot.storage_ref
    payload_path.write_bytes(b'{"tampered":true}')

    with pytest.raises(ValueError, match="content hash mismatch"):
        cache.get(key)


@pytest.mark.asyncio
async def test_global_limiter_shares_one_ten_request_per_second_ceiling() -> None:
    clock = ManualClock()
    limiter = FairAccessLimiter(max_requests_per_second=10, clock=clock.now, sleeper=clock.sleep)

    for _ in range(10):
        await limiter.acquire()
    await limiter.acquire()

    assert clock.sleeps == [1.0]


@pytest.mark.asyncio
@respx.mock
async def test_retry_policy_retries_transient_failures_and_honors_retry_after(
    tmp_path: Path,
) -> None:
    route = respx.get(f"https://data.sec.gov/submissions/CIK{APPLE_CIK}.json").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.ConnectError("temporary network failure"),
            httpx.Response(200, json=_fixture_json("submissions.json")),
        ]
    )
    clock = ManualClock()
    adapter = _adapter(tmp_path, clock=clock)

    result = await adapter.list_submissions(APPLE_CIK, as_of=AS_OF)

    assert route.call_count == 3
    assert clock.sleeps[0] == 2.0
    assert result.snapshot.stale is False
    assert result.snapshot.primary_failure is None


@pytest.mark.asyncio
@respx.mock
async def test_retry_policy_stops_after_five_transient_attempts(tmp_path: Path) -> None:
    route = respx.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{APPLE_CIK}.json").mock(
        return_value=httpx.Response(503, json=_fixture_json("429.json"))
    )
    adapter = _adapter(tmp_path)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)

    assert route.call_count == 5


@pytest.mark.asyncio
@respx.mock
async def test_transient_failure_uses_stale_cache_with_primary_failure(tmp_path: Path) -> None:
    route = respx.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{APPLE_CIK}.json").mock(
        return_value=httpx.Response(200, json=_fixture_json("companyfacts.json"))
    )
    adapter = _adapter(tmp_path)
    await adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)
    route.mock(return_value=httpx.Response(503, json=_fixture_json("429.json")))
    stale_adapter = _adapter(tmp_path, refresh_existing=True)

    result = await stale_adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)

    assert result.snapshot.stale is True
    assert result.snapshot.primary_failure is not None
    assert result.snapshot.primary_failure.startswith("HTTPStatusError: Server error '503")
    assert result.data["cik"] == 320193


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "other"),
        ("provider_version", "2026-08-08"),
        ("query", {"cik": BERKSHIRE_CIK}),
        ("as_of", "2026-06-29"),
        ("license_class", "research_only"),
        ("source_url", "https://data.sec.gov/other/CIK0000320193.json"),
        ("source_url", "https://data.sec.gov:0/api/xbrl/companyfacts/CIK0000320193.json"),
        ("source_url", "https://data.sec.gov:444/api/xbrl/companyfacts/CIK0000320193.json"),
        ("source_url", "https://data.sec.gov/api/xbrl%2fcompanyfacts/CIK0000320193.json"),
    ],
)
@pytest.mark.asyncio
@respx.mock
async def test_sec_cache_hit_rejects_metadata_not_bound_to_request(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{APPLE_CIK}.json"
    route = respx.get(url).mock(return_value=httpx.Response(200, json=_fixture_json("companyfacts.json")))
    adapter = _adapter(tmp_path)
    await adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)
    _tamper_cache_metadata(
        tmp_path,
        adapter.cache.key(adapter.provider, url, {"cik": APPLE_CIK}, AS_OF),
        field,
        value,
    )

    with pytest.raises(ValueError, match=f"cache_context_mismatch:{field}"):
        await adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_sec_stale_cache_rejects_metadata_not_bound_to_request(tmp_path: Path) -> None:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{APPLE_CIK}.json"
    route = respx.get(url).mock(return_value=httpx.Response(200, json=_fixture_json("companyfacts.json")))
    adapter = _adapter(tmp_path)
    await adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)
    _tamper_cache_metadata(
        tmp_path,
        adapter.cache.key(adapter.provider, url, {"cik": APPLE_CIK}, AS_OF),
        "provider_version",
        "2026-08-08",
    )
    route.mock(return_value=httpx.Response(503, json=_fixture_json("429.json")))
    stale_adapter = _adapter(tmp_path, refresh_existing=True)

    with pytest.raises(ValueError, match="cache_context_mismatch:provider_version"):
        await stale_adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)


@pytest.mark.asyncio
@respx.mock
async def test_non_transient_primary_failures_do_not_use_stale_cache(tmp_path: Path) -> None:
    route = respx.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{APPLE_CIK}.json").mock(
        return_value=httpx.Response(200, json=_fixture_json("companyfacts.json"))
    )
    await _adapter(tmp_path).get_company_facts(APPLE_CIK, as_of=AS_OF)
    stale_adapter = _adapter(tmp_path, refresh_existing=True)

    for status_code in (400, 401, 403, 404):
        route.mock(return_value=httpx.Response(status_code))
        with pytest.raises(httpx.HTTPStatusError):
            await stale_adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)

    route.mock(return_value=httpx.Response(200, content=(FIXTURE_DIR / "malformed.json").read_bytes()))
    with pytest.raises((json.JSONDecodeError, ValueError)):
        await stale_adapter.get_company_facts(APPLE_CIK, as_of=AS_OF)


@pytest.mark.asyncio
@respx.mock
async def test_missing_primary_filing_blocks_critical_assertions(tmp_path: Path) -> None:
    respx.get(f"https://data.sec.gov/submissions/CIK{APPLE_CIK}.json").mock(
        return_value=httpx.Response(200, json=_fixture_json("submissions.json"))
    )
    respx.get(
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019326000001/aapl-2026-10k.htm"
    ).mock(return_value=httpx.Response(404))
    adapter = _adapter(tmp_path)

    await adapter.list_submissions(APPLE_CIK, as_of=AS_OF)
    result = await adapter.fetch_filing("0000320193-26-000001", as_of=AS_OF)

    assert result.status is NodeStatus.BLOCKED
    assert result.data is None
    assert result.errors == ["primary_filing_not_found:0000320193-26-000001"]


@pytest.mark.asyncio
@respx.mock
async def test_missing_primary_filing_ignores_unbound_poisoned_cache_entry(
    tmp_path: Path,
) -> None:
    filing_url = (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019326000001/aapl-2026-10k.htm"
    )
    respx.get(f"https://data.sec.gov/submissions/CIK{APPLE_CIK}.json").mock(
        return_value=httpx.Response(200, json=_fixture_json("submissions.json"))
    )
    respx.get(filing_url).mock(return_value=httpx.Response(404))
    adapter = _adapter(tmp_path, refresh_existing=True)
    await adapter.list_submissions(APPLE_CIK, as_of=AS_OF)
    query = {"accession_number": "0000320193-26-000001"}
    key = adapter.cache.key(adapter.provider, filing_url, query, AS_OF)
    adapter.cache.put_bytes(
        key,
        b"poisoned but validly hashed",
        provider="other",
        provider_version=adapter.provider_version,
        source_url=filing_url,
        query=query,
        as_of=AS_OF,
        media_type="text/html",
        license_class=adapter.license_class,
    )

    result = await adapter.fetch_filing("0000320193-26-000001", as_of=AS_OF)

    assert result.status is NodeStatus.BLOCKED
    assert result.data is None
    assert result.errors == ["primary_filing_not_found:0000320193-26-000001"]


@pytest.mark.asyncio
@respx.mock
async def test_resolve_company_uses_cached_ticker_map_and_filing_url_uses_issuer_cik(
    tmp_path: Path,
) -> None:
    ticker_route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_fixture_json("company_tickers.json"))
    )
    respx.get(f"https://data.sec.gov/submissions/CIK{BERKSHIRE_CIK}.json").mock(
        return_value=httpx.Response(200, json=_fixture_json("brk-submissions.json"))
    )
    filing_route = respx.get(
        "https://www.sec.gov/Archives/edgar/data/1067983/"
        "000106798326000001/brk-2026-10k.htm"
    ).mock(return_value=httpx.Response(200, content=b"<html>BRK filing</html>"))
    adapter = _adapter(tmp_path)

    identity = await adapter.resolve_company("BRK.B", as_of=AS_OF)
    await adapter.list_submissions(identity.cik, as_of=AS_OF)
    filing = await adapter.fetch_filing("0001067983-26-000001", as_of=AS_OF)

    assert ticker_route.call_count == 1
    assert identity.cik == BERKSHIRE_CIK
    assert identity.ticker == "BRK.B"
    assert identity.name == "BERKSHIRE HATHAWAY INC"
    assert filing.status is NodeStatus.SUCCESS
    assert filing.data is not None
    assert filing.data.content == b"<html>BRK filing</html>"
    assert filing_route.call_count == 1


@pytest.mark.asyncio
async def test_fetch_filing_blocks_without_issuer_submission_context(tmp_path: Path) -> None:
    result = await _adapter(tmp_path).fetch_filing("0001067983-26-000001", as_of=AS_OF)

    assert result.status is NodeStatus.BLOCKED
    assert result.errors == ["filing_metadata_context_required:0001067983-26-000001"]


@pytest.mark.asyncio
async def test_invalid_accession_fails_deterministically(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid accession_number"):
        await _adapter(tmp_path).fetch_filing("missing-accession", as_of=AS_OF)


def test_snapshot_cache_rejects_forged_storage_ref_outside_payload_dir(tmp_path: Path) -> None:
    cache = SnapshotCache(tmp_path / "cache")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    key = cache.key("sec", "/facts", {"cik": APPLE_CIK}, AS_OF)
    cache.put_bytes(
        key,
        b"inside",
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"cik": APPLE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )
    metadata_path = tmp_path / "cache" / "metadata" / f"{key}.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["storage_ref"] = str(outside)
    metadata["content_hash"] = sha256(outside.read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid storage_ref"):
        cache.get(key)


def test_snapshot_cache_rejects_rebound_storage_ref_to_another_payload(tmp_path: Path) -> None:
    cache = SnapshotCache(tmp_path / "cache")
    first_key = cache.key("sec", "/facts", {"cik": APPLE_CIK}, AS_OF)
    second_key = cache.key("sec", "/facts", {"cik": BERKSHIRE_CIK}, AS_OF)
    cache.put_bytes(
        first_key,
        b"inside",
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"cik": APPLE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )
    second = cache.put_bytes(
        second_key,
        b"other-valid-payload",
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"cik": BERKSHIRE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )
    metadata_path = tmp_path / "cache" / "metadata" / f"{first_key}.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["storage_ref"] = second.storage_ref
    metadata["content_hash"] = second.content_hash
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="cache_storage_ref_mismatch"):
        cache.get(first_key)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "other"),
        ("media_type", "text/html"),
    ],
)
def test_snapshot_cache_put_existing_rejects_metadata_context_mismatch(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    cache = SnapshotCache(tmp_path / "cache")
    key = cache.key("sec", "/facts", {"cik": APPLE_CIK}, AS_OF)
    cache.put_bytes(
        key,
        b"inside",
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"cik": APPLE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )
    _tamper_cache_metadata_path(tmp_path / "cache" / "metadata" / f"{key}.json", field, value)

    with pytest.raises(ValueError, match=f"cache_context_mismatch:{field}"):
        cache.put_bytes(
            key,
            b"inside",
            provider="sec",
            provider_version="2026-08-09",
            source_url="https://data.sec.gov/example",
            query={"cik": APPLE_CIK},
            as_of=AS_OF,
            media_type="application/json",
            license_class="public_primary",
        )


def test_snapshot_cache_put_existing_accepts_same_context_equal_bytes(tmp_path: Path) -> None:
    cache = SnapshotCache(tmp_path / "cache")
    key = cache.key("sec", "/facts", {"cik": APPLE_CIK}, AS_OF)
    first = cache.put_bytes(
        key,
        b"inside",
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"cik": APPLE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )

    second = cache.put_bytes(
        key,
        b"inside",
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"cik": APPLE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )

    assert second == first


@pytest.mark.parametrize(
    ("path_kind", "message"),
    [
        ("metadata", "cache_metadata_symlink"),
        ("payload", "cache_payload_symlink"),
    ],
)
def test_snapshot_cache_rejects_symlinked_cache_files_before_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_kind: str,
    message: str,
) -> None:
    cache = SnapshotCache(tmp_path / "cache")
    key = cache.key("sec", "/facts", {"cik": APPLE_CIK}, AS_OF)
    snapshot = cache.put_bytes(
        key,
        b"inside",
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"cik": APPLE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )
    metadata_path = tmp_path / "cache" / "metadata" / f"{key}.json"
    payload_path = tmp_path / "cache" / "payloads" / snapshot.storage_ref
    symlink_path = metadata_path if path_kind == "metadata" else payload_path

    monkeypatch.setattr(Path, "is_symlink", lambda self: self == symlink_path)

    with pytest.raises(ValueError, match=message):
        cache.get(key)


def test_snapshot_cache_read_bytes_rejects_payload_symlink_after_get(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = SnapshotCache(tmp_path / "cache")
    key = cache.key("sec", "/facts", {"cik": APPLE_CIK}, AS_OF)
    cache.put_bytes(
        key,
        b"inside",
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"cik": APPLE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )
    snapshot = cache.get(key)
    assert snapshot is not None
    payload_path = tmp_path / "cache" / "payloads" / f"{key}.bin"

    monkeypatch.setattr(Path, "is_symlink", lambda self: self == payload_path)

    with pytest.raises(ValueError, match="cache_payload_symlink"):
        cache.read_bytes(snapshot)


def test_snapshot_cache_put_bytes_rejects_preexisting_payload_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = SnapshotCache(tmp_path / "cache")
    key = cache.key("sec", "/facts", {"cik": APPLE_CIK}, AS_OF)
    payload_path = tmp_path / "cache" / "payloads" / f"{key}.bin"
    payload_path.parent.mkdir(parents=True)
    payload_path.write_bytes(b"existing")

    monkeypatch.setattr(Path, "is_symlink", lambda self: self == payload_path)

    with pytest.raises(ValueError, match="cache_payload_symlink"):
        cache.put_bytes(
            key,
            b"inside",
            provider="sec",
            provider_version="2026-08-09",
            source_url="https://data.sec.gov/example",
            query={"cik": APPLE_CIK},
            as_of=AS_OF,
            media_type="application/json",
            license_class="public_primary",
        )


def test_source_snapshot_and_returned_sec_data_are_deeply_immutable(tmp_path: Path) -> None:
    cache = SnapshotCache(tmp_path / "cache")
    key = cache.key("sec", "/facts", {"cik": APPLE_CIK}, AS_OF)
    snapshot = cache.put_bytes(
        key,
        json.dumps(_fixture_json("companyfacts.json")).encode("utf-8"),
        provider="sec",
        provider_version="2026-08-09",
        source_url="https://data.sec.gov/example",
        query={"cik": APPLE_CIK},
        as_of=AS_OF,
        media_type="application/json",
        license_class="public_primary",
    )
    restored = cache.get(key)

    with pytest.raises(TypeError):
        snapshot.query["cik"] = "mutated"
    with pytest.raises(TypeError):
        restored.query["cik"] = "mutated"
    dumped = restored.model_dump(mode="json")
    assert dumped["query"] == {"cik": APPLE_CIK}


def test_fixture_manifest_hashes_match_committed_files() -> None:
    verified = verify_fixture_manifest(FIXTURE_DIR / "manifest.json")

    assert verified["submissions.json"] == sha256(
        (FIXTURE_DIR / "submissions.json").read_bytes()
    ).hexdigest()
    assert verified["companyfacts.json"] == sha256(
        (FIXTURE_DIR / "companyfacts.json").read_bytes()
    ).hexdigest()
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    for name in ("aapl-2026-10k.html", "aapl-2026-10q.html", "aapl-2026-xbrl.xml"):
        assert manifest["files"][name]["filing_acceptance_at"].endswith("Z")
        assert manifest["files"][name]["filing_date"] == "2026-06-30"
        assert manifest["files"][name]["report_period_end"] == "2026-06-30"
        assert "effective_at" in manifest["files"][name]


def test_refresh_script_fails_before_network_without_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DDA_SEC_USER_AGENT", raising=False)
    module = _load_refresh_script()

    with pytest.raises(SystemExit) as excinfo:
        module.main(
            [
                "--ticker",
                "AAPL",
                "--cik",
                APPLE_CIK,
                "--as-of",
                "2026-06-30",
                "--output",
                str(FIXTURE_DIR),
            ]
        )

    assert excinfo.value.code == 2


@respx.mock
def test_refresh_script_fetches_manifest_and_atomically_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DDA_SEC_USER_AGENT", TEST_USER_AGENT)
    output = tmp_path / "sec"
    output.mkdir()
    stale_file = output / "stale.txt"
    stale_file.write_text("remove me", encoding="utf-8")
    module = _load_refresh_script()
    _mock_refresh_routes()

    result = module.main(
        [
            "--ticker",
            "AAPL",
            "--cik",
            APPLE_CIK,
            "--as-of",
            "2026-06-30",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert not stale_file.exists()
    verified = verify_fixture_manifest(output / "manifest.json")
    assert set(verified) >= {
        "submissions.json",
        "companyfacts.json",
        "aapl-2026-10k.html",
        "aapl-2026-10q.html",
        "aapl-2026-xbrl.xml",
    }
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["aapl-2026-10k.html"]["filing_acceptance_at"].endswith("Z")
    assert manifest["files"]["aapl-2026-10k.html"]["filing_date"] == "2026-06-30"
    assert manifest["files"]["aapl-2026-10k.html"]["report_period_end"] == "2026-06-30"
    assert manifest["files"]["aapl-2026-10k.html"]["effective_at"] is None


@respx.mock
def test_refresh_script_uses_ticker_slug_and_realistic_index_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DDA_SEC_USER_AGENT", TEST_USER_AGENT)
    output = tmp_path / "sec"
    module = _load_refresh_script()
    _mock_refresh_routes(ticker_slug="brk-b", cik=BERKSHIRE_CIK)

    result = module.main(
        [
            "--ticker",
            "BRK.B",
            "--cik",
            BERKSHIRE_CIK,
            "--as-of",
            "2026-06-30",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert (output / "brk-b-2026-10k.html").exists()
    assert (output / "brk-b-2026-10q.html").exists()
    assert (output / "brk-b-2026-xbrl.xml").exists()


def test_refresh_publish_restores_original_output_when_publish_rename_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_refresh_script()
    output = tmp_path / "sec"
    output.mkdir()
    original_file = output / "original.txt"
    original_file.write_text("original", encoding="utf-8")
    temp_root = tmp_path / ".sec.tmp"
    temp_root.mkdir()
    (temp_root / "new.txt").write_text("new", encoding="utf-8")
    real_rename = Path.rename

    def fail_temp_publish(self: Path, target: Path) -> Path:
        if self == temp_root and target == output:
            raise OSError("forced publish failure")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_temp_publish)

    with pytest.raises(OSError, match="forced publish failure"):
        module._publish_directory(temp_root, output)

    assert output.exists()
    assert (output / "original.txt").read_text(encoding="utf-8") == "original"
    assert temp_root.exists()
    assert (temp_root / "new.txt").read_text(encoding="utf-8") == "new"
    assert not any(path.name.startswith(".sec.backup") for path in tmp_path.iterdir())


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        (
            [
                {"name": "aapl-20260630.htm", "type": "text.gif"},
                {"name": "aapl-20260630_htm.xml", "type": "text.gif"},
                {"name": "aapl-20260630_cal.xml", "type": "text.gif"},
                {"name": "aapl-20260630_def.xml", "type": "text/xml"},
                {"name": "FilingSummary.xml", "type": "text/xml"},
            ],
            "aapl-20260630_htm.xml",
        ),
        (
            [
                {"name": "issuer-20260630.htm", "type": "text.gif"},
                {"name": "issuer-20260630_htm.xml", "type": "text/xml"},
                {"name": "issuer-20260630_pre.xml", "type": "text/xml"},
            ],
            "issuer-20260630_htm.xml",
        ),
        (
            [
                {"name": "fallback-instance.xml", "type": "XML"},
                {
                    "name": "labeled-instance.xml",
                    "type": "text/xml",
                    "description": "EXTRACTED XBRL INSTANCE DOCUMENT",
                },
            ],
            "labeled-instance.xml",
        ),
    ],
)
def test_refresh_selects_realistic_xbrl_instance_candidates(
    items: list[dict[str, str]],
    expected: str,
) -> None:
    module = _load_refresh_script()

    assert module._select_xbrl_instance({"directory": {"item": items}}) == expected


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([{"name": "aapl-20260630_cal.xml", "type": "text/xml"}], "xbrl instance not found"),
        (
            [
                {"name": "first_htm.xml", "type": "text/xml"},
                {"name": "second_htm.xml", "type": "text.gif"},
            ],
            "ambiguous xbrl instance",
        ),
    ],
)
def test_refresh_rejects_missing_or_ambiguous_xbrl_instance(
    items: list[dict[str, str]],
    message: str,
) -> None:
    module = _load_refresh_script()

    with pytest.raises(ValueError, match=message):
        module._select_xbrl_instance({"directory": {"item": items}})


def test_sync_refresh_retry_after_is_bounded_and_never_sleeps_for_real(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_refresh_script()
    sleeps: list[float] = []
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleeps.append(round(seconds, 3)))
    client = FakeSyncClient(
        [
            httpx.Response(429, headers={"Retry-After": "not-a-date"}),
            httpx.Response(429, headers={"Retry-After": "Wed, 01 Jan 2020 00:00:00 GMT"}),
            httpx.Response(429, headers={"Retry-After": "Wed, 09 Aug 2026 12:00:20 GMT"}),
            httpx.Response(429, headers={"Retry-After": "999999"}),
            httpx.Response(200, content=b"ok"),
        ]
    )
    monkeypatch.setattr(
        module,
        "_refresh_now",
        lambda: datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    payload = module._get_bytes(client, NoopSyncLimiter(), "https://example.test")

    assert payload == b"ok"
    assert sleeps == [1.0, 0.0, 20.0, 30.0]


@pytest.mark.asyncio
@respx.mock
async def test_retry_after_invalid_past_future_and_oversized_values_are_bounded(
    tmp_path: Path,
) -> None:
    route = respx.get(f"https://data.sec.gov/submissions/CIK{APPLE_CIK}.json").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "not-a-date"}),
            httpx.Response(429, headers={"Retry-After": "Wed, 01 Jan 2020 00:00:00 GMT"}),
            httpx.Response(429, headers={"Retry-After": "Wed, 09 Aug 2026 12:00:20 GMT"}),
            httpx.Response(429, headers={"Retry-After": "999999"}),
            httpx.Response(200, json=_fixture_json("submissions.json")),
        ]
    )
    clock = ManualClock()
    adapter = _adapter(tmp_path, clock=clock)

    await adapter.list_submissions(APPLE_CIK, as_of=AS_OF)

    assert route.call_count == 5
    assert clock.sleeps == [1.0, 0.0, 20.0, 30.0]


def test_sec_adapter_rejects_blank_user_agent(tmp_path: Path) -> None:
    with pytest.raises(MissingUserAgentError):
        _adapter(tmp_path, user_agent=" ")


def _adapter(
    tmp_path: Path,
    *,
    user_agent: str = TEST_USER_AGENT,
    clock: ManualClock | None = None,
    refresh_existing: bool = False,
) -> SecEdgarAdapter:
    manual_clock = clock or ManualClock()
    return SecEdgarAdapter(
        user_agent=user_agent,
        cache=SnapshotCache(tmp_path / "snapshots"),
        limiter=FairAccessLimiter(clock=manual_clock.now, sleeper=manual_clock.sleep),
        clock=lambda: datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        sleeper=manual_clock.sleep,
        jitter=lambda _attempt: 0.0,
        refresh_existing=refresh_existing,
    )


def _fixture_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _tamper_cache_metadata(tmp_path: Path, key: str, field: str, value: object) -> None:
    _tamper_cache_metadata_path(tmp_path / "snapshots" / "metadata" / f"{key}.json", field, value)


def _tamper_cache_metadata_path(metadata_path: Path, field: str, value: object) -> None:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = value
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")


def _mock_refresh_routes(*, ticker_slug: str = "aapl", cik: str = APPLE_CIK) -> None:
    submissions = _fixture_json("submissions.json")
    submissions["cik"] = cik
    submissions["tickers"] = [ticker_slug.upper()]
    submissions["filings"]["recent"]["primaryDocument"] = [
        f"{ticker_slug}-2026-10k.htm",
        f"{ticker_slug}-2026-10q.htm",
    ]
    respx.get(f"https://data.sec.gov/submissions/CIK{cik}.json").mock(
        return_value=httpx.Response(200, json=submissions)
    )
    respx.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json").mock(
        return_value=httpx.Response(200, json=_fixture_json("companyfacts.json"))
    )
    cik_no_zeros = str(int(cik))
    respx.get(
        f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/"
        f"000032019326000001/{ticker_slug}-2026-10k.htm"
    ).mock(return_value=httpx.Response(200, content=(FIXTURE_DIR / "aapl-2026-10k.html").read_bytes()))
    respx.get(
        f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/"
        f"000032019326000002/{ticker_slug}-2026-10q.htm"
    ).mock(return_value=httpx.Response(200, content=(FIXTURE_DIR / "aapl-2026-10q.html").read_bytes()))
    respx.get(
        f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/"
        "000032019326000001/index.json"
    ).mock(return_value=httpx.Response(200, json=_fixture_json("aapl-2026-index.json")))
    respx.get(
        f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/"
        "000032019326000001/aapl-2026-xbrl.xml"
    ).mock(return_value=httpx.Response(200, content=(FIXTURE_DIR / "aapl-2026-xbrl.xml").read_bytes()))


def _load_refresh_script() -> ModuleType:
    script_path = Path(__file__).parents[3] / "scripts" / "refresh_sec_fixtures.py"
    spec = importlib.util.spec_from_file_location("refresh_sec_fixtures", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("refresh_sec_fixtures.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManualClock:
    def __init__(self) -> None:
        self.current = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.current

    async def sleep(self, seconds: float) -> None:
        rounded = round(seconds, 3)
        self.sleeps.append(rounded)
        self.current += seconds


class FakeSyncClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, url: str) -> httpx.Response:
        response = self.responses[self.calls]
        self.calls += 1
        response.request = httpx.Request("GET", url)
        return response


class NoopSyncLimiter:
    def acquire(self) -> None:
        return None
