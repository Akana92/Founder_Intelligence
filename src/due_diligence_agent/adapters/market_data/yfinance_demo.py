from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from due_diligence_agent.adapters.http.public_fixture_manifest import (
    verify_public_context_manifest,
)
from due_diligence_agent.application.policies.content_rights import LicenseClass
from due_diligence_agent.ports.collectors import MarketDataSnapshot, SourceSnapshot


class MissingOptionalMarketDependencyError(RuntimeError):
    pass


class YFinanceDemoAdapter:
    provider = "yfinance_demo"
    provider_version = "2026-08-09"
    license_class = LicenseClass.RESEARCH_ONLY

    def __init__(self, fixture_dir: Path | None = None) -> None:
        self.fixture_dir = fixture_dir

    @classmethod
    def from_fixture_dir(cls, fixture_dir: Path) -> "YFinanceDemoAdapter":
        return cls(fixture_dir=fixture_dir)

    def get_snapshot(self, ticker: str, *, as_of: date) -> MarketDataSnapshot:
        if self.fixture_dir is not None:
            requested_ticker = ticker.strip().upper()
            name = f"{requested_ticker.lower()}_market_snapshot.json"
            manifest = verify_public_context_manifest(
                self.fixture_dir / "manifest.json",
                expected_provider=self.provider,
                expected_as_of=as_of,
                allowed_license_classes={self.license_class.value},
                expected_ticker=requested_ticker,
            )
            if name not in manifest["files"]:
                raise ValueError(f"market fixture missing:{name}")
            entry = manifest["files"][name]
            snapshot = _load_market_fixture(self.fixture_dir, name)
            if snapshot.ticker != requested_ticker:
                raise ValueError("market fixture ticker mismatch")
            if snapshot.as_of != as_of or snapshot.snapshot.as_of != as_of:
                raise ValueError("market fixture as_of mismatch")
            if snapshot.snapshot.provider != self.provider:
                raise ValueError("market fixture provider mismatch")
            if snapshot.snapshot.provider != entry["provider"]:
                raise ValueError("market fixture provider mismatch")
            if snapshot.snapshot.license_class != self.license_class.value:
                raise ValueError("market fixture license_class mismatch")
            if snapshot.snapshot.license_class != entry["license_class"]:
                raise ValueError("market fixture license_class mismatch")
            if snapshot.snapshot.content_hash != entry["sha256"]:
                raise ValueError("market fixture hash mismatch")
            if any(price.date > as_of for price in snapshot.prices):
                raise ValueError("market fixture price date after as_of")
            return snapshot
        payload = self.fetch_live(ticker, as_of=as_of)
        return market_snapshot_from_payload(
            payload,
            payload_path=None,
            storage_ref=f"live:{_canonical_hash(payload)}",
        )

    def fetch_live(self, ticker: str, *, as_of: date) -> dict[str, Any]:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise MissingOptionalMarketDependencyError(
                "Install optional group stage1a-market-yfinance-demo before live market refresh"
            ) from exc
        start = as_of - timedelta(days=7)
        end = as_of + timedelta(days=1)
        history = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat())
        prices = [
            {
                "date": str(index.date()),
                "close": str(row["Close"]),
                "volume": int(row["Volume"]),
            }
            for index, row in history.iterrows()
            if index.date() <= as_of
        ]
        return {
            "ticker": ticker.upper(),
            "as_of": as_of.isoformat(),
            "currency": "USD",
            "market_cap": None,
            "prices": prices,
            "provider_payload": {"source": "live yfinance optional demo"},
            "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source_url": f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}",
        }


def market_snapshot_from_payload(
    payload: dict[str, Any],
    *,
    payload_path: Path | None,
    storage_ref: str | None = None,
) -> MarketDataSnapshot:
    digest = sha256(payload_path.read_bytes()).hexdigest() if payload_path else _canonical_hash(payload)
    as_of = date.fromisoformat(str(payload["as_of"]))
    snapshot = SourceSnapshot(
        provider=YFinanceDemoAdapter.provider,
        provider_version=YFinanceDemoAdapter.provider_version,
        source_url=str(payload["source_url"]),
        query={"ticker": str(payload["ticker"]).upper()},
        as_of=as_of,
        retrieved_at=_parse_utc(str(payload["retrieved_at"])),
        published_at=None,
        content_hash=digest,
        license_class=YFinanceDemoAdapter.license_class.value,
        media_type="application/json",
        storage_ref=storage_ref or (payload_path.name if payload_path else f"live:{digest}"),
    )
    return MarketDataSnapshot(
        ticker=str(payload["ticker"]).upper(),
        as_of=as_of,
        currency=str(payload["currency"]),
        market_cap=payload.get("market_cap"),
        prices=tuple(payload["prices"]),
        snapshot=snapshot,
    )


def _load_market_fixture(fixture_dir: Path, name: str) -> MarketDataSnapshot:
    path = _safe_fixture_path(fixture_dir, name)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return market_snapshot_from_payload(payload, payload_path=path)


def ensure_live_dependency_available() -> None:
    try:
        import yfinance  # noqa: F401  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise MissingOptionalMarketDependencyError(
            "Install optional group stage1a-market-yfinance-demo before live market refresh"
        ) from exc


def _safe_fixture_path(root: Path, name: str) -> Path:
    resolved_root = root.resolve()
    path = (resolved_root / name).resolve()
    if resolved_root not in path.parents:
        raise ValueError("fixture path escapes root")
    return path


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _canonical_hash(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
