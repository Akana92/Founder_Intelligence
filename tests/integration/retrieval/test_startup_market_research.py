from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import shutil
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5
import zipfile

import pytest

from due_diligence_agent.adapters.startup.frozen_market_research import FrozenStartupMarketResearchAdapter
from due_diligence_agent.domain.startup.market import (
    StartupCompetitorCategory,
    StartupMarketResearchSnapshot,
    StartupResearchPlan,
    StartupResearchSourceMode,
)
from due_diligence_agent.ports.startup_research import StartupResearchPort


FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "startup_market_research_v1"


def test_frozen_market_research_collects_deterministic_competitors_and_news() -> None:
    adapter: StartupResearchPort = FrozenStartupMarketResearchAdapter.from_fixture_dir(FIXTURE_ROOT)
    plan = _plan()

    snapshot = adapter.collect(plan)
    repeated = adapter.collect(plan)

    assert snapshot.snapshot_hash == repeated.snapshot_hash
    assert snapshot.snapshot_id == repeated.snapshot_id
    assert snapshot.snapshot_hash == (
        "sha256:6226be069f518e502418ea87761aa9728577e9fc4025ba2a4d73924130407e84"
    )
    assert snapshot.schema_version == "startup_market_research@1"
    assert snapshot.source_mode is StartupResearchSourceMode.FROZEN
    assert snapshot.provenance == "frozen_first"
    assert {competitor.category for competitor in snapshot.competitors} == set(StartupCompetitorCategory)
    hubspot = next(competitor for competitor in snapshot.competitors if competitor.name == "HubSpot")
    assert hubspot.confidence == Decimal("0.88")
    assert len(hubspot.source_ids) == 2
    assert len([competitor for competitor in snapshot.competitors if competitor.name == "HubSpot"]) == 1
    assert len(snapshot.sentiment_signals) == 2
    assert all(signal.supports_primary_financial_metrics is False for signal in snapshot.sentiment_signals)
    assert any(source.stale for source in snapshot.sources)
    assert all(source.confidence is None for source in snapshot.sources)
    assert "diagnostic:stale_signal:news" in snapshot.labels


def test_startup_market_fixture_resolves_from_package_resources_without_repo_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.bootstrap import container

    tmp_path = _test_temp_dir("package-resource")
    monkeypatch.setattr(container, "_project_root", lambda: tmp_path / "installed-runtime")

    fixture_root = container.startup_market_fixture_root()
    snapshot = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root).collect(_plan())

    assert snapshot.source_mode is StartupResearchSourceMode.FROZEN
    assert {competitor.category for competitor in snapshot.competitors} == set(StartupCompetitorCategory)
    assert "frozen_market_research" in snapshot.labels


def test_startup_market_fixture_reads_zip_package_resources_without_repo_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.bootstrap import container

    tmp_path = _test_temp_dir("zip-package-resource")
    archive_path = tmp_path / "startup-fixture.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("due_diligence_agent/", "")
        archive.writestr("due_diligence_agent/fixtures/", "")
        archive.writestr(f"due_diligence_agent/fixtures/{container.STARTUP_MARKET_FIXTURE_NAME}/", "")
        for fixture_file in FIXTURE_ROOT.rglob("*"):
            if fixture_file.is_file():
                archive.write(
                    fixture_file,
                    (
                        f"due_diligence_agent/fixtures/{container.STARTUP_MARKET_FIXTURE_NAME}/"
                        f"{fixture_file.relative_to(FIXTURE_ROOT).as_posix()}"
                    ),
                )

    monkeypatch.setattr(container, "_project_root", lambda: tmp_path / "installed-runtime")
    with zipfile.ZipFile(archive_path) as archive:
        monkeypatch.setattr(container.resources, "files", lambda _package: zipfile.Path(archive, "due_diligence_agent/"))

        fixture_root = container.startup_market_fixture_root()
        snapshot = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root).collect(_plan())

    assert snapshot.source_mode is StartupResearchSourceMode.FROZEN
    assert {competitor.category for competitor in snapshot.competitors} == set(StartupCompetitorCategory)
    assert "frozen_market_research" in snapshot.labels


def test_missing_required_competitors_has_stable_safe_error_code() -> None:
    tmp_path = _test_temp_dir("missing-required")
    fixture_root = _copy_fixture(tmp_path)
    (fixture_root / "sources" / "competitors.json").unlink()
    adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root)

    with pytest.raises(Exception) as excinfo:
        adapter.collect(_plan())

    assert getattr(excinfo.value, "stable_error_code", None) == "startup_market_fixture_unavailable"
    rendered = repr(excinfo.value)
    assert str(fixture_root) not in rendered
    assert "Traceback" not in rendered


def test_invalid_required_competitor_payload_has_stable_safe_error_code() -> None:
    tmp_path = _test_temp_dir("invalid-required-payload")
    fixture_root = _copy_fixture(tmp_path)
    competitors_path = fixture_root / "sources" / "competitors.json"
    payload = json.loads(competitors_path.read_text(encoding="utf-8"))
    payload["sources"] = "not-a-source-list"
    competitors_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = fixture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["required_files"]["sources/competitors.json"]["sha256"] = sha256(
        competitors_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root)

    with pytest.raises(Exception) as excinfo:
        adapter.collect(_plan())

    assert getattr(excinfo.value, "stable_error_code", None) == "startup_market_fixture_unavailable"
    rendered = repr(excinfo.value)
    assert str(fixture_root) not in rendered
    assert "Traceback" not in rendered


def test_missing_optional_news_stays_partial_without_synthetic_market_data() -> None:
    tmp_path = _test_temp_dir("missing-optional")
    fixture_root = _copy_fixture(tmp_path)
    (fixture_root / "sources" / "news.json").unlink()
    adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root)

    snapshot = adapter.collect(_plan())
    repeated = adapter.collect(_plan())

    assert snapshot.snapshot_hash == repeated.snapshot_hash
    assert snapshot.sentiment_signals == ()
    assert "diagnostic:optional_source_unavailable:news" in snapshot.labels
    assert {competitor.category for competitor in snapshot.competitors} == set(StartupCompetitorCategory)
    assert all(source.supports_primary_financial_metrics is False for source in snapshot.sources)


def test_market_snapshot_build_does_not_bypass_validation_with_model_construct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_model_construct(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("model_construct bypass is forbidden")

    monkeypatch.setattr(
        StartupMarketResearchSnapshot,
        "model_construct",
        fail_model_construct,
    )

    snapshot = FrozenStartupMarketResearchAdapter.from_fixture_dir(FIXTURE_ROOT).collect(
        _plan()
    )

    assert snapshot.source_mode is StartupResearchSourceMode.FROZEN


def test_manifest_tampering_fails_closed() -> None:
    tmp_path = _test_temp_dir("manifest-tamper")
    fixture_root = _copy_fixture(tmp_path)
    competitors_path = fixture_root / "sources" / "competitors.json"
    competitors = json.loads(competitors_path.read_text(encoding="utf-8"))
    competitors["competitors"][0]["name"] = "Tampered CRM"
    competitors_path.write_text(json.dumps(competitors), encoding="utf-8")

    adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root)

    with pytest.raises(ValueError) as excinfo:
        adapter.collect(_plan())
    assert getattr(excinfo.value, "stable_error_code", None) == "startup_market_fixture_unavailable"


def test_damaged_optional_news_yields_stable_partial_snapshot() -> None:
    tmp_path = _test_temp_dir("damaged-optional-news")
    fixture_root = _copy_fixture(tmp_path)
    news_path = fixture_root / "sources" / "news.json"
    news_path.write_text("{ damaged json", encoding="utf-8")
    manifest_path = fixture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["optional_files"]["sources/news.json"]["sha256"] = sha256(news_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root)

    snapshot = adapter.collect(_plan())
    repeated = adapter.collect(_plan())

    assert snapshot.snapshot_hash == repeated.snapshot_hash
    assert snapshot.sentiment_signals == ()
    assert "diagnostic:optional_source_unavailable:news" in snapshot.labels
    assert {competitor.category for competitor in snapshot.competitors} == set(StartupCompetitorCategory)


def test_missing_optional_news_yields_stable_partial_snapshot() -> None:
    tmp_path = _test_temp_dir("missing-optional-news")
    fixture_root = _copy_fixture(tmp_path)
    (fixture_root / "sources" / "news.json").unlink()
    adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root)

    snapshot = adapter.collect(_plan())
    repeated = adapter.collect(_plan())

    assert snapshot.snapshot_hash == repeated.snapshot_hash
    assert snapshot.sentiment_signals == ()
    assert "diagnostic:optional_source_unavailable:news" in snapshot.labels


def test_malformed_optional_news_with_valid_manifest_hash_yields_partial_snapshot() -> None:
    tmp_path = _test_temp_dir("malformed-optional-news")
    fixture_root = _copy_fixture(tmp_path)
    news_path = fixture_root / "sources" / "news.json"
    news_path.write_text(json.dumps({"sources": [{"missing": "source_key"}], "sentiment_signals": []}), encoding="utf-8")
    manifest_path = fixture_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["optional_files"]["sources/news.json"]["sha256"] = sha256(news_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root)

    snapshot = adapter.collect(_plan())

    assert snapshot.sentiment_signals == ()
    assert "diagnostic:optional_source_unavailable:news" in snapshot.labels
    assert {competitor.category for competitor in snapshot.competitors} == set(StartupCompetitorCategory)


def test_manifest_rejects_path_traversal_and_absolute_paths() -> None:
    tmp_path = _test_temp_dir("unsafe-manifest-paths")
    for unsafe_path in ("../outside.json", "sources\\news.json", "/tmp/news.json", "C:/tmp/news.json"):
        fixture_root = _copy_fixture(tmp_path / unsafe_path.replace("/", "_").replace("\\", "_").replace(":", "_"))
        manifest_path = fixture_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["optional_files"] = {unsafe_path: {"sha256": "0" * 64}}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_root)
        with pytest.raises(ValueError) as excinfo:
            adapter.collect(_plan())
        assert getattr(excinfo.value, "stable_error_code", None) == "startup_market_fixture_unavailable"


def test_research_identity_is_portable_across_fixture_copy_paths() -> None:
    tmp_path = _test_temp_dir("portable-identity")
    fixture_a = _copy_fixture(tmp_path / "copy-a")
    fixture_b = _copy_fixture(tmp_path / "copy-b")

    snapshot_a = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_a).collect(_plan())
    snapshot_b = FrozenStartupMarketResearchAdapter.from_fixture_dir(fixture_b).collect(_plan())

    assert snapshot_a.research_id == snapshot_b.research_id
    assert snapshot_a.snapshot_hash == snapshot_b.snapshot_hash
    assert snapshot_a.snapshot_id == snapshot_b.snapshot_id


def test_frozen_adapter_import_and_fixture_path_construct_no_network_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported: list[str] = []
    real_import = __import__

    def guard_import(name: str, *args: Any, **kwargs: Any) -> object:
        if name in {"httpx", "requests"} or name.startswith(("httpx.", "requests.")):
            imported.append(name)
            raise AssertionError("startup frozen market research must not import network clients")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guard_import)

    adapter = FrozenStartupMarketResearchAdapter.from_fixture_dir(FIXTURE_ROOT)
    snapshot = adapter.collect(_plan())

    assert snapshot.source_mode is StartupResearchSourceMode.FROZEN
    assert imported == []


def _plan() -> StartupResearchPlan:
    return StartupResearchPlan(
        case_id=uuid5(NAMESPACE_URL, "case:startup-market-fixture"),
        source_mode=StartupResearchSourceMode.FROZEN,
        queries=("b2b crm automation competitors",),
    )


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "startup_market_research_v1"
    shutil.copytree(FIXTURE_ROOT, target)
    return target


def _test_temp_dir(name: str) -> Path:
    path = Path("codex_tmp_pytest") / "task3-market-red" / f"{name}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path
