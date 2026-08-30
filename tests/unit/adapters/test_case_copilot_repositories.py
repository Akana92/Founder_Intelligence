from __future__ import annotations

import gc
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from due_diligence_agent.adapters.local_storage.case_copilot_repositories import (
    CaseScopeError,
    CaseStaleRevisionError,
    LocalCaseAssetRepository,
    LocalCaseCopilotThreadRepository,
    LocalCaseResearchJobRepository,
    LocalCaseScenarioRepository,
    LocalFounderStatementRepository,
)
from due_diligence_agent.domain.startup.assets import CaseAssetDraft
from due_diligence_agent.domain.startup.case_intake import FounderStatement
from due_diligence_agent.domain.startup.copilot import CopilotMessage, CopilotThread
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
)
from due_diligence_agent.domain.startup.scenario import ScenarioSelectionRecord, StartupScenarioSet
from due_diligence_agent.ports.repositories import CaseResearchJob

CASE_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CASE_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


@pytest.fixture
def local_tmp_path() -> Iterator[Path]:
    root = Path("tmp") / "task2_case_copilot_repositories"
    path = root / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        try:
            from due_diligence_agent.bootstrap.container import _cached_case_copilot_repositories
        except ModuleNotFoundError:
            pass
        else:
            _cached_case_copilot_repositories.cache_clear()
        gc.collect()
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        if resolved_path.parent != resolved_root:
            raise RuntimeError(f"refusing to clean unexpected test path: {resolved_path}")
        if path.exists():
            shutil.rmtree(path)


def test_thread_survives_repository_recreation(local_tmp_path: Path) -> None:
    first = LocalCaseCopilotThreadRepository(local_tmp_path, current_revision=lambda _case_id: 1)
    saved = first.save(_thread(case_id=CASE_A), expected_revision=1, idempotency_key="msg-1")

    second = LocalCaseCopilotThreadRepository(local_tmp_path, current_revision=lambda _case_id: 1)
    restored = second.get_current(CASE_A)

    assert restored == saved
    assert restored.messages[-1].message_id == UUID("11111111-1111-4111-8111-111111111111")
    with pytest.raises(CaseScopeError):
        second.get_for_case(CASE_B, restored.thread_id)


def test_duplicate_thread_idempotency_key_replays_without_overwriting(
    local_tmp_path: Path,
) -> None:
    repository = LocalCaseCopilotThreadRepository(local_tmp_path, current_revision=lambda _case_id: 1)
    original = repository.save(
        _thread(case_id=CASE_A, message_text="first answer"),
        expected_revision=1,
        idempotency_key="same-key",
    )

    replay = repository.save(
        _thread(case_id=CASE_A, message_text="second answer"),
        expected_revision=1,
        idempotency_key="same-key",
    )

    assert replay == original
    assert repository.get_current(CASE_A).messages[-1].content == "first answer"
    assert _json_file_count(local_tmp_path) == 1


def test_duplicate_idempotency_replays_original_after_case_revision_advances(
    local_tmp_path: Path,
) -> None:
    revisions = {CASE_A: 1}
    repository = LocalCaseCopilotThreadRepository(
        local_tmp_path,
        current_revision=lambda case_id: revisions[case_id],
    )
    original = repository.save(
        _thread(case_id=CASE_A, data_revision=1, message_text="saved before revision advance"),
        expected_revision=1,
        idempotency_key="retry-after-advance",
    )

    revisions[CASE_A] = 2
    replay = repository.save(
        _thread(case_id=CASE_A, data_revision=1, message_text="client retry after success"),
        expected_revision=1,
        idempotency_key="retry-after-advance",
    )

    assert replay == original
    assert repository.get_current(CASE_A).messages[-1].content == "saved before revision advance"
    assert _json_file_count(local_tmp_path) == 1


def test_stale_thread_revision_leaves_no_target_or_temp_json(local_tmp_path: Path) -> None:
    repository = LocalCaseCopilotThreadRepository(local_tmp_path, current_revision=lambda _case_id: 2)

    with pytest.raises(CaseStaleRevisionError):
        repository.save(_thread(case_id=CASE_A), expected_revision=1, idempotency_key="stale")

    assert list(local_tmp_path.rglob("*.json")) == []
    assert list(local_tmp_path.rglob("*.tmp")) == []


def test_same_ids_in_different_cases_stay_case_scoped(local_tmp_path: Path) -> None:
    repository = LocalCaseScenarioRepository(local_tmp_path, current_revision=lambda _case_id: 1)
    scenario_id = UUID("22222222-2222-4222-8222-222222222222")

    first = repository.save(
        _scenario(case_id=CASE_A, scenario_set_id=scenario_id, scenario_key="base"),
        expected_revision=1,
        idempotency_key="case-a",
    )
    second = repository.save(
        _scenario(case_id=CASE_B, scenario_set_id=scenario_id, scenario_key="optimistic"),
        expected_revision=1,
        idempotency_key="case-b",
    )

    assert repository.get_for_case(CASE_A, scenario_id) == first
    assert repository.get_for_case(CASE_B, scenario_id) == second
    assert repository.get_current(CASE_A).scenario_key == "base"
    assert repository.get_current(CASE_B).scenario_key == "optimistic"


def test_scenario_selection_records_are_durable_idempotent_and_case_scoped(local_tmp_path: Path) -> None:
    repository = LocalCaseScenarioRepository(local_tmp_path, current_revision=lambda _case_id: 1)
    original = repository.save_selection(
        _selection_record(
            case_id=CASE_A,
            old_scenario_key="base",
            new_scenario_key="optimistic",
        ),
        expected_revision=1,
        idempotency_key="select-key",
    )

    restarted = LocalCaseScenarioRepository(local_tmp_path, current_revision=lambda _case_id: 1)
    replay = restarted.get_selection_by_idempotency(CASE_A, "select-key")
    conflicting_retry = restarted.save_selection(
        _selection_record(
            case_id=CASE_A,
            old_scenario_key="optimistic",
            new_scenario_key="base",
        ),
        expected_revision=1,
        idempotency_key="select-key",
    )

    assert replay == original
    assert conflicting_retry == original
    assert restarted.get_selection_by_idempotency(CASE_B, "select-key") is None


def test_assumptions_research_jobs_and_assets_are_typed_restart_safe(
    local_tmp_path: Path,
) -> None:
    revisions = {CASE_A: 3}
    assumptions = LocalFounderStatementRepository(
        local_tmp_path,
        current_revision=lambda case_id: revisions[case_id],
    )
    jobs = LocalCaseResearchJobRepository(
        local_tmp_path,
        current_revision=lambda case_id: revisions[case_id],
    )
    assets = LocalCaseAssetRepository(
        local_tmp_path,
        current_revision=lambda case_id: revisions[case_id],
    )

    statement = assumptions.save(
        _statement(case_id=CASE_A, data_revision=3),
        expected_revision=3,
        idempotency_key="statement-1",
    )
    job = jobs.save(
        _research_job(case_id=CASE_A, data_revision=3),
        expected_revision=3,
        idempotency_key="job-1",
    )
    asset = assets.save(
        _asset(case_id=CASE_A, data_revision=3),
        expected_revision=3,
        idempotency_key="asset-1",
    )

    restarted_assumptions = LocalFounderStatementRepository(
        local_tmp_path,
        current_revision=lambda case_id: revisions[case_id],
    )
    restarted_jobs = LocalCaseResearchJobRepository(
        local_tmp_path,
        current_revision=lambda case_id: revisions[case_id],
    )
    restarted_assets = LocalCaseAssetRepository(
        local_tmp_path,
        current_revision=lambda case_id: revisions[case_id],
    )

    assert restarted_assumptions.get_current(CASE_A) == (statement,)
    assert restarted_jobs.get_for_case(CASE_A, job.job_id) == job
    restarted_job = restarted_jobs.get_for_case(CASE_A, job.job_id)
    assert restarted_job == job
    snapshot_payload = job.live_market_research_snapshot
    assert snapshot_payload is not None
    assert restarted_job == job.model_copy(
        update={
            "live_market_research_snapshot": snapshot_payload.model_dump(mode="python")
        }
    )
    assert restarted_job.requested_acquisition_mode == "live_public_research"
    assert restarted_job.selected_acquisition_mode == "provider_unconfigured"
    assert restarted_job.live_market_research_snapshot is not None
    assert restarted_job.live_market_research_snapshot.sources[0].source_url.unicode_string() == (
        "https://example.com/public-market"
    )
    assert restarted_job.live_market_research_snapshot.sources[0].status is StartupResearchSourceStatus.INFERENCE
    assert restarted_job.live_market_research_snapshot.sources[0].supports_primary_financial_metrics is False
    assert restarted_assets.get_current(CASE_A) == asset
    with pytest.raises(CaseScopeError):
        restarted_jobs.get_for_case(CASE_B, job.job_id)


def test_container_reuses_one_case_copilot_repository_bundle_per_root(
    local_tmp_path: Path,
) -> None:
    from due_diligence_agent.bootstrap.container import build_case_copilot_repositories

    first = build_case_copilot_repositories(local_tmp_path)
    second = build_case_copilot_repositories(local_tmp_path)

    assert second is first
    assert first.threads is second.threads


def _json_file_count(root: Path) -> int:
    return len([path for path in root.rglob("*.json") if not path.name.endswith(".tmp")])


def _thread(
    *,
    case_id: UUID,
    data_revision: int = 1,
    message_text: str = "first answer",
) -> CopilotThread:
    return CopilotThread(
        thread_id=UUID("00000000-0000-4000-8000-000000000001"),
        case_id=case_id,
        data_revision=data_revision,
        messages=(
            CopilotMessage(
                message_id=UUID("11111111-1111-4111-8111-111111111111"),
                case_id=case_id,
                data_revision=data_revision,
                role="assistant",
                content=message_text,
            ),
        ),
    )


def _statement(*, case_id: UUID, data_revision: int) -> FounderStatement:
    return FounderStatement(
        statement_id=UUID("33333333-3333-4333-8333-333333333333"),
        case_id=case_id,
        data_revision=data_revision,
        field_key="buyer",
        value="Clinic owners",
        confidence=Decimal("0.70"),
        rationale="Founder statement from structured intake",
    )


def _scenario(
    *,
    case_id: UUID,
    scenario_set_id: UUID,
    scenario_key: str,
) -> StartupScenarioSet:
    return StartupScenarioSet(
        scenario_set_id=scenario_set_id,
        case_id=case_id,
        data_revision=1,
        scenario_key=scenario_key,
        inputs=(),
        metrics=(),
        rationale="Founder scenario",
        validation_plan="Validate with paid pilots",
        acceptance="proposed",
    )


def _selection_record(
    *,
    case_id: UUID,
    old_scenario_key: str,
    new_scenario_key: str,
) -> ScenarioSelectionRecord:
    return ScenarioSelectionRecord(
        selection_id=UUID("77777777-7777-4777-8777-777777777777"),
        case_id=case_id,
        data_revision=1,
        scenario_set_id=UUID("22222222-2222-4222-8222-222222222222"),
        old_scenario_key=old_scenario_key,  # type: ignore[arg-type]
        new_scenario_key=new_scenario_key,  # type: ignore[arg-type]
    )


def _research_job(*, case_id: UUID, data_revision: int) -> CaseResearchJob:
    return CaseResearchJob(
        job_id=UUID("44444444-4444-4444-8444-444444444444"),
        case_id=case_id,
        data_revision=data_revision,
        focus_key="market",
        status="completed",
        requested_acquisition_mode="live_public_research",
        selected_acquisition_mode="provider_unconfigured",
        acquisition_mode="provider_unconfigured",
        source_refs=(UUID("55555555-5555-4555-8555-555555555555"),),
        result_summary="Public benchmark sources accepted.",
        fail_reason=None,
        live_market_research_snapshot=_market_snapshot(case_id=case_id, data_revision=data_revision),
        updated_at=datetime(2026, 8, 22, tzinfo=UTC),
    )


def _market_snapshot(*, case_id: UUID, data_revision: int) -> StartupMarketResearchSnapshot:
    source = StartupResearchSource.model_validate(
        {
            "source_id": UUID("55555555-5555-4555-8555-555555555555"),
            "source_mode": StartupResearchSourceMode.LIVE,
            "source_hash": "sha256:" + "1" * 64,
            "source_url": "https://example.com/public-market",
            "source_label": "Example Public Market",
            "as_of": datetime(2026, 8, 1, tzinfo=UTC).date(),
            "retrieved_at": datetime(2026, 8, 22, tzinfo=UTC),
            "query": "public market context",
            "provenance": "public_research",
            "confidence": Decimal("0.7"),
            "supports_primary_financial_metrics": False,
            "status": StartupResearchSourceStatus.INFERENCE,
        }
    )
    return StartupMarketResearchSnapshot.build(
        case_id=case_id,
        as_of=datetime(2026, 8, 22, tzinfo=UTC),
        source_mode=StartupResearchSourceMode.LIVE,
        research_id=UUID("77777777-7777-4777-8777-777777777777"),
        competitors=(),
        sources=(source,),
        sentiment_signals=(),
        assumptions=(),
        sizing=None,
        labels=("live_public_research",),
        data_revision=data_revision,
        public_benchmark_candidates=(),
    )


def _asset(*, case_id: UUID, data_revision: int) -> CaseAssetDraft:
    return CaseAssetDraft(
        draft_id=UUID("66666666-6666-4666-8666-666666666666"),
        case_id=case_id,
        data_revision=data_revision,
        scenario_set_id=UUID("22222222-2222-4222-8222-222222222222"),
        draft_version=1,
        asset_key="gtm_launch_pack",
        body_markdown="Draft launch pack with cited assumptions.",
        source_refs=(),
        dependency_refs=(UUID("22222222-2222-4222-8222-222222222222"),),
    )
