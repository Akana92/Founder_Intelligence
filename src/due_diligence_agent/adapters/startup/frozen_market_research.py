from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.domain.startup.market import (
    StartupCompetitor,
    StartupCompetitorCategory,
    StartupMarketResearchSnapshot,
    StartupResearchPlan,
    StartupResearchSchema,
    StartupResearchSentiment,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
    StartupSentimentSignal,
)
from due_diligence_agent.ports.startup_research import StartupResearchPort


_ADAPTER_VERSION = "frozen_market_research@1"
_MANIFEST_VERSION = "startup_market_research_fixture_manifest@1"
_COMPETITORS_FILE = "sources/competitors.json"
_NEWS_FILE = "sources/news.json"


class StartupMarketFixtureUnavailableError(ValueError):
    stable_error_code = "startup_market_fixture_unavailable"
    retryable = False

    def __init__(self, message: str = "startup_market_fixture_unavailable") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class _FixtureFile:
    relative_path: str
    sha256_hex: str
    required: bool


class FrozenStartupMarketResearchAdapter(StartupResearchPort):
    def __init__(self, fixture_root: Path | Traversable) -> None:
        self._fixture_root = fixture_root

    @classmethod
    def from_fixture_dir(
        cls, fixture_root: Path | Traversable
    ) -> "FrozenStartupMarketResearchAdapter":
        return cls(fixture_root)

    def collect(self, plan: StartupResearchPlan) -> StartupMarketResearchSnapshot:
        if plan.source_mode is not StartupResearchSourceMode.FROZEN:
            raise ValueError("frozen startup research adapter requires frozen plan")

        manifest = self._load_manifest()
        fixture_files = self._manifest_files(manifest)
        labels = {"frozen_market_research", _ADAPTER_VERSION}
        unavailable_optional_paths: set[str] = set()
        for fixture_file in fixture_files:
            try:
                self._verify_fixture_hash(fixture_file)
            except StartupMarketFixtureUnavailableError:
                if fixture_file.required:
                    raise
                unavailable_optional_paths.add(fixture_file.relative_path)
                labels.add("diagnostic:optional_source_unavailable:news")

        try:
            competitors_payload = self._read_json_required(_COMPETITORS_FILE)
            sources = list(
                _sources_from_payload(
                    competitors_payload,
                    plan=plan,
                    file_name=_COMPETITORS_FILE,
                )
            )
            competitors = list(_competitors_from_payload(competitors_payload))
            as_of = _manifest_as_of(manifest)
            research_id = _research_id_from_manifest(manifest)
        except StartupMarketFixtureUnavailableError:
            raise
        except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
            raise StartupMarketFixtureUnavailableError(
                "startup market fixture required payload invalid"
            ) from exc
        sentiment_signals: list[StartupSentimentSignal] = []

        try:
            news_payload = (
                None
                if _NEWS_FILE in unavailable_optional_paths
                else self._read_json_optional(_NEWS_FILE)
            )
        except (OSError, json.JSONDecodeError, ValueError):
            news_payload = None
            labels.add("diagnostic:optional_source_unavailable:news")

        if news_payload is not None:
            try:
                news_sources = tuple(_sources_from_payload(news_payload, plan=plan, file_name=_NEWS_FILE))
                sources.extend(news_sources)
                source_lookup = {source.provenance: source for source in news_sources}
                sentiment_signals.extend(_sentiment_from_payload(news_payload, source_lookup=source_lookup))
                if any(source.stale for source in news_sources):
                    labels.add("diagnostic:stale_signal:news")
            except (KeyError, TypeError, ValueError):
                labels.add("diagnostic:optional_source_unavailable:news")
        else:
            labels.add("diagnostic:optional_source_unavailable:news")

        try:
            merged_competitors = _merge_competitors(competitors)
            return StartupMarketResearchSnapshot.build(
                case_id=plan.case_id,
                as_of=datetime.combine(as_of, datetime.min.time(), tzinfo=UTC),
                source_mode=StartupResearchSourceMode.FROZEN,
                research_id=research_id,
                competitors=tuple(merged_competitors),
                sources=tuple(sources),
                sentiment_signals=tuple(sentiment_signals),
                assumptions=(),
                sizing=None,
                labels=tuple(sorted(labels)),
                data_revision=1,
            )
        except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
            raise StartupMarketFixtureUnavailableError(
                "startup market fixture required payload invalid"
            ) from exc

    def _load_manifest(self) -> Mapping[str, Any]:
        manifest_path = self._fixture_resource("manifest.json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StartupMarketFixtureUnavailableError(
                "startup market fixture manifest unreadable"
            ) from exc
        if not isinstance(manifest, Mapping):
            raise StartupMarketFixtureUnavailableError("startup market fixture manifest invalid")
        if manifest.get("schema_version") != _MANIFEST_VERSION:
            raise StartupMarketFixtureUnavailableError(
                "startup market fixture manifest schema mismatch"
            )
        if manifest.get("research_schema_version") != StartupResearchSchema.VERSION:
            raise StartupMarketFixtureUnavailableError(
                "startup market fixture research schema mismatch"
            )
        return manifest

    def _manifest_files(self, manifest: Mapping[str, Any]) -> tuple[_FixtureFile, ...]:
        files: list[_FixtureFile] = []
        for required, section_name in ((True, "required_files"), (False, "optional_files")):
            section = manifest.get(section_name, {})
            if not isinstance(section, Mapping):
                raise StartupMarketFixtureUnavailableError(
                    "startup market fixture manifest file section invalid"
                )
            for relative_path, metadata in section.items():
                if not isinstance(relative_path, str) or not isinstance(metadata, Mapping):
                    raise StartupMarketFixtureUnavailableError(
                        "startup market fixture manifest file invalid"
                    )
                self._validate_manifest_relative_path(relative_path)
                digest = metadata.get("sha256")
                if not isinstance(digest, str) or len(digest) != 64:
                    raise StartupMarketFixtureUnavailableError(
                        "startup market fixture manifest hash invalid"
                    )
                files.append(_FixtureFile(relative_path=relative_path, sha256_hex=digest, required=required))
        if not any(item.relative_path == _COMPETITORS_FILE and item.required for item in files):
            raise StartupMarketFixtureUnavailableError(
                "startup market fixture competitors file missing"
            )
        return tuple(files)

    def _validate_manifest_relative_path(self, relative_path: str) -> None:
        if "\\" in relative_path or not relative_path.strip():
            raise StartupMarketFixtureUnavailableError(
                "startup market fixture manifest path invalid"
            )
        candidate = PurePosixPath(relative_path)
        if (
            candidate.is_absolute()
            or any(part in {"", ".", ".."} for part in candidate.parts)
            or any(":" in part for part in candidate.parts)
        ):
            raise StartupMarketFixtureUnavailableError(
                "startup market fixture manifest path invalid"
            )

    def _verify_fixture_hash(self, fixture_file: _FixtureFile) -> None:
        path = self._fixture_resource(fixture_file.relative_path)
        if not path.is_file():
            if fixture_file.required:
                raise StartupMarketFixtureUnavailableError(
                    "startup market fixture required file missing"
                )
            return
        actual = sha256(path.read_bytes()).hexdigest()
        if actual != fixture_file.sha256_hex:
            raise StartupMarketFixtureUnavailableError("startup market fixture hash mismatch")

    def _read_json_required(self, relative_path: str) -> Mapping[str, Any]:
        try:
            payload = json.loads(
                self._fixture_resource(relative_path).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise StartupMarketFixtureUnavailableError(
                f"startup market fixture required source invalid:{relative_path}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise StartupMarketFixtureUnavailableError(
                f"startup market fixture required source invalid:{relative_path}"
            )
        return payload

    def _read_json_optional(self, relative_path: str) -> Mapping[str, Any] | None:
        path = self._fixture_resource(relative_path)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"startup market fixture optional source invalid:{relative_path}")
        return payload

    def _fixture_resource(self, relative_path: str) -> Path | Traversable:
        return self._fixture_root.joinpath(*PurePosixPath(relative_path).parts)


def _sources_from_payload(
    payload: Mapping[str, Any],
    *,
    plan: StartupResearchPlan,
    file_name: str,
) -> tuple[StartupResearchSource, ...]:
    raw_sources = payload.get("sources", ())
    if not isinstance(raw_sources, list):
        raise ValueError(f"startup market fixture sources invalid:{file_name}")
    sources: list[StartupResearchSource] = []
    for raw in raw_sources:
        if not isinstance(raw, Mapping):
            raise ValueError(f"startup market fixture source invalid:{file_name}")
        source_key = _required_str(raw, "source_key")
        source_id = _stable_uuid(f"source:{file_name}:{source_key}")
        source = StartupResearchSource.model_validate(
            {
                "source_id": source_id,
                "source_mode": StartupResearchSourceMode.FROZEN,
                "source_hash": f"sha256:{_source_hash(raw)}",
                "source_url": _required_str(raw, "url"),
                "source_label": _required_str(raw, "label"),
                "as_of": _parse_date(_required_str(raw, "as_of")),
                "retrieved_at": _parse_datetime(_required_str(raw, "retrieved_at")),
                "query": _query_for_source(plan, raw),
                "provenance": f"{file_name}:{source_key}",
                "supports_primary_financial_metrics": False,
                "stale": bool(raw.get("stale", False)),
                "status": StartupResearchSourceStatus(str(raw.get("status", StartupResearchSourceStatus.SOURCE_FACT.value))),
            }
        )
        sources.append(source)
    return tuple(sources)


def _competitors_from_payload(payload: Mapping[str, Any]) -> tuple[StartupCompetitor, ...]:
    raw_competitors = payload.get("competitors", ())
    if not isinstance(raw_competitors, list):
        raise ValueError("startup market fixture competitors invalid")
    competitors: list[StartupCompetitor] = []
    for raw in raw_competitors:
        if not isinstance(raw, Mapping):
            raise ValueError("startup market fixture competitor invalid")
        source_refs = tuple(
            _stable_uuid(f"source:{_COMPETITORS_FILE}:{str(source_key)}")
            for source_key in _required_list(raw, "source_keys")
        )
        competitors.append(
            StartupCompetitor(
                name=_required_str(raw, "name"),
                category=StartupCompetitorCategory(str(raw["category"])),
                status=StartupResearchSourceStatus(str(raw.get("status", StartupResearchSourceStatus.SOURCE_FACT.value))),
                confidence=Decimal(str(raw.get("confidence", "0.5"))),
                source_ids=source_refs,
                reason_code=cast(str | None, raw.get("reason_code")),
            )
        )
    return tuple(competitors)


def _merge_competitors(competitors: list[StartupCompetitor]) -> tuple[StartupCompetitor, ...]:
    merged: dict[tuple[str, StartupCompetitorCategory], StartupCompetitor] = {}
    for competitor in competitors:
        key = (competitor.name.casefold(), competitor.category)
        current = merged.get(key)
        if current is None:
            merged[key] = competitor
            continue
        merged[key] = StartupCompetitor(
            name=current.name,
            category=current.category,
            status=current.status,
            confidence=max(current.confidence, competitor.confidence),
            source_ids=tuple(sorted(set((*current.source_ids, *competitor.source_ids)))),
            reason_code=current.reason_code or competitor.reason_code,
            assumption_refs=tuple(sorted(set((*current.assumption_refs, *competitor.assumption_refs)))),
            contradiction_ids=tuple(sorted(set((*current.contradiction_ids, *competitor.contradiction_ids)))),
        )
    return tuple(sorted(merged.values(), key=lambda item: (item.category.value, item.name.casefold())))


def _sentiment_from_payload(
    payload: Mapping[str, Any],
    *,
    source_lookup: Mapping[str, StartupResearchSource],
) -> tuple[StartupSentimentSignal, ...]:
    raw_signals = payload.get("sentiment_signals", ())
    if not isinstance(raw_signals, list):
        raise ValueError("startup market fixture sentiment invalid")
    signals: list[StartupSentimentSignal] = []
    for raw in raw_signals:
        if not isinstance(raw, Mapping):
            raise ValueError("startup market fixture sentiment invalid")
        source_key = _required_str(raw, "source_key")
        source = source_lookup.get(f"{_NEWS_FILE}:{source_key}")
        if source is None:
            raise ValueError("startup market fixture sentiment source missing")
        subject = _required_str(raw, "subject")
        as_of = _parse_datetime(_required_str(raw, "as_of"))
        signals.append(
            StartupSentimentSignal(
                signal_id=_stable_uuid(f"sentiment:{source.source_id}:{subject}:{as_of.isoformat()}"),
                sentiment=StartupResearchSentiment(str(raw["sentiment"])),
                subject=subject,
                as_of=as_of,
                source_id=source.source_id,
                source_mode=StartupResearchSourceMode.FROZEN,
                supports_primary_financial_metrics=False,
                supports_event_narrative_claims=bool(raw.get("supports_event_narrative_claims", False)),
                polarity_confidence=Decimal(str(raw.get("polarity_confidence", "0.5"))),
            )
        )
    return tuple(signals)


def _manifest_as_of(manifest: Mapping[str, Any]) -> date:
    value = manifest.get("as_of")
    if not isinstance(value, str):
        raise ValueError("startup market fixture manifest as_of invalid")
    return _parse_date(value)


def _research_id_from_manifest(manifest: Mapping[str, Any]) -> UUID:
    payload = {
        "adapter_version": _ADAPTER_VERSION,
        "manifest_version": manifest.get("schema_version"),
        "research_schema_version": manifest.get("research_schema_version"),
        "as_of": manifest.get("as_of"),
        "required_files": _manifest_hashes(manifest.get("required_files")),
        "optional_files": _manifest_hashes(manifest.get("optional_files")),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return uuid5(NAMESPACE_URL, f"startup-market-research:{encoded}")


def _manifest_hashes(section: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(section, Mapping):
        return ()
    hashes: list[tuple[str, str]] = []
    for relative_path, metadata in section.items():
        if isinstance(relative_path, str) and isinstance(metadata, Mapping):
            digest = metadata.get("sha256")
            if isinstance(digest, str):
                hashes.append((relative_path, digest.casefold()))
    return tuple(sorted(hashes))


def _query_for_source(plan: StartupResearchPlan, raw: Mapping[str, Any]) -> str:
    raw_query = raw.get("query")
    if isinstance(raw_query, str) and raw_query.strip():
        return raw_query
    if plan.queries:
        return plan.queries[0]
    return "startup market research frozen fixture"


def _source_hash(raw: Mapping[str, Any]) -> str:
    payload = {str(key): raw[key] for key in sorted(raw) if key != "source_hash"}
    return sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def _required_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ValueError(f"startup market fixture field required:{key}")
    return value


def _required_list(raw: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"startup market fixture list required:{key}")
    return tuple(value)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("startup market fixture datetime must be UTC")
    return parsed.astimezone(UTC)


def _stable_uuid(seed: str) -> UUID:
    return uuid5(NAMESPACE_URL, seed)
