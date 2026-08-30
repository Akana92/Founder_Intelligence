from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from pydantic import ValidationError

from due_diligence_agent.domain.startup.readiness import (
    StartupAdaptiveQuestion,
    StartupMetricPack,
    StartupReadinessDimension,
    StartupReadinessDimensionStatus,
    StartupReadinessSnapshot,
)


def test_readiness_pack_schema_and_immutability() -> None:
    pack = _metric_pack(
        metric_ids=("mrr", "arr"),
        built_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(ValidationError, match="extra_forbidden"):
        StartupMetricPack.model_validate(
            pack.model_dump() | {"unexpected": "x"},
        )

    assert pack.schema_version == "startup_readiness@1"
    assert pack.model_config["frozen"]


def test_readiness_pack_deduplicates_and_sorts_metric_ids() -> None:
    pack = _metric_pack(metric_ids=("arr", "mrr", "arr", "cohort_retention"), built_at=datetime(2026, 8, 13, 11, 0, tzinfo=UTC))
    assert pack.metric_ids == ("arr", "cohort_retention", "mrr")


def test_readiness_pack_derives_deterministic_hash_and_id() -> None:
    build_at = datetime(2026, 8, 13, 12, 30, tzinfo=UTC)

    pack_a = _metric_pack(metric_ids=("arr", "mrr"), built_at=build_at)
    pack_b = _metric_pack(metric_ids=("mrr", "arr"), built_at=build_at)

    assert pack_a.pack_hash == pack_b.pack_hash
    assert pack_a.pack_id == pack_b.pack_id


def test_readiness_pack_adaptive_questions_are_stable_and_order_sensitive_by_weight() -> None:
    build_at = datetime(2026, 8, 13, 12, 45, tzinfo=UTC)
    question_alpha = StartupAdaptiveQuestion(
        question_id=_stable_uuid("adaptive-question-alpha"),
        question_code="runway",
        text="What is your current runway?",
        dimension_id=_stable_uuid("dimension-runway"),
        weight=5,
    )
    question_beta = StartupAdaptiveQuestion(
        question_id=_stable_uuid("adaptive-question-beta"),
        question_code="pilot",
        text="Do you have a signed pilot?",
        dimension_id=_stable_uuid("dimension-sales"),
        weight=1,
    )
    pack_unsorted = _metric_pack_payload(
        metric_ids=("mrr",),
        built_at=build_at,
        adaptive_questions=(question_alpha, question_beta),
    )
    pack_sorted = _metric_pack_payload(
        metric_ids=("mrr",),
        built_at=build_at,
        adaptive_questions=(question_beta, question_alpha),
    )

    assert pack_unsorted.adaptive_questions[0] == question_beta
    assert pack_sorted.adaptive_questions[0] == question_beta
    assert pack_unsorted.pack_hash == pack_sorted.pack_hash
    assert pack_unsorted.pack_id == pack_sorted.pack_id


def test_readiness_pack_direct_model_validate_stabilizes_equal_weight_adaptive_questions() -> None:
    question_alpha = StartupAdaptiveQuestion(
        question_id=_stable_uuid("adaptive-question-alpha-tie"),
        question_code="sales",
        text="Customer pipeline status?",
        dimension_id=_stable_uuid("dimension-sales"),
        weight=1,
    )
    question_beta = StartupAdaptiveQuestion(
        question_id=_stable_uuid("adaptive-question-beta-tie"),
        question_code="product",
        text="Product roadmap confidence?",
        dimension_id=_stable_uuid("dimension-product"),
        weight=1,
    )
    baseline = _metric_pack_payload(
        metric_ids=("arr",),
        built_at=datetime(2026, 8, 13, 13, 0, tzinfo=UTC),
        adaptive_questions=(question_beta, question_alpha),
    )

    unsorted_payload = baseline.model_dump()
    unsorted_payload["adaptive_questions"] = (
        question_alpha.model_dump(),
        question_beta.model_dump(),
    )
    normalized = StartupMetricPack.model_validate(unsorted_payload)
    assert normalized.adaptive_questions == baseline.adaptive_questions
    assert normalized.pack_hash == baseline.pack_hash
    assert normalized.pack_id == baseline.pack_id


def test_readiness_snapshot_deduplicates_and_stabilizes_reference_ids() -> None:
    pack = _metric_pack(metric_ids=("arr",), built_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC))
    calc_a = uuid4()
    calc_b = uuid4()
    diag = uuid4()
    snap_a = StartupReadinessSnapshot.build(
        profile_id=pack.profile_id,
        profile_hash=pack.profile_hash,
        profile_revision=4,
        metric_pack=pack,
        calculation_ids=(calc_a, calc_b),
        diagnostic_ids=(diag,),
        built_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
    )
    snap_b = StartupReadinessSnapshot.build(
        profile_id=pack.profile_id,
        profile_hash=pack.profile_hash,
        profile_revision=4,
        metric_pack=pack,
        calculation_ids=(calc_b, calc_a),
        diagnostic_ids=(diag,),
        built_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
    )

    assert snap_a.snapshot_hash == snap_b.snapshot_hash
    assert snap_a.snapshot_id == snap_b.snapshot_id
    assert snap_a.calculation_ids == tuple(sorted((calc_a, calc_b)))
    assert snap_b.calculation_ids == tuple(sorted((calc_a, calc_b)))
    assert snap_a.calculation_ids == snap_b.calculation_ids


def test_readiness_snapshot_deduplicates_reference_ids_on_duplicates() -> None:
    pack = _metric_pack(metric_ids=("arr",), built_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC))
    calc_a = uuid4()
    diag_a = uuid4()
    snap = StartupReadinessSnapshot.build(
        profile_id=pack.profile_id,
        profile_hash=pack.profile_hash,
        profile_revision=4,
        metric_pack=pack,
        calculation_ids=(calc_a, calc_a),
        diagnostic_ids=(diag_a, diag_a),
        built_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
    )

    assert snap.calculation_ids == (calc_a,)
    assert snap.diagnostic_ids == (diag_a,)


def test_readiness_pack_model_validate_normalizes_metric_ids_and_rejects_invalid_profile_hash() -> None:
    baseline = _metric_pack(
        metric_ids=("arr", "cohort_retention", "mrr"),
        built_at=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
    )
    payload = baseline.model_dump()
    payload["metric_ids"] = (" arr ", "arr", "MRR", "cohort_retention")
    payload["pack_hash"] = baseline.pack_hash
    payload["pack_id"] = baseline.pack_id

    pack = StartupMetricPack.model_validate(
        {
            "profile_id": payload["profile_id"],
            "profile_hash": payload["profile_hash"],
            "profile_revision": payload["profile_revision"],
            "schema_version": payload["schema_version"],
            "pack_id": payload["pack_id"],
            "pack_hash": payload["pack_hash"],
            "metric_ids": payload["metric_ids"],
            "dimensions": (
                StartupReadinessDimension(
                    dimension_id=_stable_uuid("business_model"),
                    metric_id="mrr",
                    status=StartupReadinessDimensionStatus.READY,
                ).model_dump(),
            ),
            "adaptive_questions": (),
            "built_at": datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        }
    )
    assert pack.metric_ids == ("arr", "cohort_retention", "mrr")

    with pytest.raises(ValidationError, match="invalid sha256 reference"):
        StartupMetricPack.model_validate(
            {
                "profile_id": payload["profile_id"],
                "profile_hash": "not-a-hash",
                "profile_revision": 4,
                "schema_version": "startup_readiness@1",
                "pack_id": "00000000-0000-4000-8000-000000000001",
                "pack_hash": "sha256:" + ("b" * 64),
                "metric_ids": ("arr",),
                "dimensions": (),
                "adaptive_questions": (),
                "built_at": datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
            }
        )


def test_readiness_snapshot_model_validate_rejects_invalid_profile_hash() -> None:
    pack = _metric_pack(metric_ids=("mrr",), built_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC))
    with pytest.raises(ValidationError, match="invalid sha256 reference"):
        StartupReadinessSnapshot.model_validate(
            {
                "profile_id": pack.profile_id,
                "profile_hash": "definitely-not-hash",
                "profile_revision": 4,
                "schema_version": "startup_readiness@1",
                "snapshot_id": "00000000-0000-4000-8000-000000000001",
                "snapshot_hash": "sha256:" + ("f" * 64),
                "metric_pack": pack,
                "calculation_ids": (),
                "diagnostic_ids": (),
                "built_at": datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
            }
        )


def test_readiness_pack_rejects_too_many_adaptive_questions() -> None:
    with pytest.raises(ValidationError, match="at most 3"):
        _metric_pack_payload(
            metric_ids=("mrr",),
            built_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
            adaptive_questions=(
                StartupAdaptiveQuestion(
                    question_id=uuid4(),
                    question_code="q1",
                    text="q1",
                    dimension_id=uuid4(),
                    weight=1,
                ),
                StartupAdaptiveQuestion(
                    question_id=uuid4(),
                    question_code="q2",
                    text="q2",
                    dimension_id=uuid4(),
                    weight=1,
                ),
                StartupAdaptiveQuestion(
                    question_id=uuid4(),
                    question_code="q3",
                    text="q3",
                    dimension_id=uuid4(),
                    weight=1,
                ),
                StartupAdaptiveQuestion(
                    question_id=uuid4(),
                    question_code="q4",
                    text="q4",
                    dimension_id=uuid4(),
                    weight=1,
                ),
            ),
        )


def test_readiness_snapshot_ties_profile_and_pack_identity() -> None:
    pack = _metric_pack(metric_ids=("mrr", "arr"), built_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC))

    snapshot = StartupReadinessSnapshot.build(
        profile_id=pack.profile_id,
        profile_hash=pack.profile_hash,
        profile_revision=4,
        metric_pack=pack,
        calculation_ids=(uuid4(), uuid4()),
        diagnostic_ids=(uuid4(),),
        built_at=datetime(2026, 8, 13, 10, 30, tzinfo=UTC),
    )

    assert snapshot.profile_id == pack.profile_id
    assert snapshot.profile_hash == pack.profile_hash
    assert snapshot.profile_revision == 4
    assert snapshot.metric_pack.pack_id == pack.pack_id
    assert snapshot.snapshot_id == snapshot.derive_snapshot_id(profile_id=snapshot.profile_id, snapshot_hash=snapshot.snapshot_hash)


def test_readiness_dimension_notes_must_be_safe() -> None:
    with pytest.raises(ValidationError, match="notes"):
        StartupReadinessDimension(
            dimension_id=_stable_uuid("business_model"),
            metric_id="mrr",
            status=StartupReadinessDimensionStatus.READY,
            notes="file:/tmp/secret.txt",
        )

    with pytest.raises(ValidationError, match="notes"):
        StartupReadinessDimension(
            dimension_id=_stable_uuid("business_model"),
            metric_id="mrr",
            status=StartupReadinessDimensionStatus.READY,
            notes="  ",
        )

    dimension = StartupReadinessDimension(
        dimension_id=_stable_uuid("business_model"),
        metric_id="mrr",
        status=StartupReadinessDimensionStatus.READY,
        notes="Startup is in discovery stage",
    )
    assert dimension.notes == "Startup is in discovery stage"


def test_readiness_snapshot_requires_profile_revision_and_reference_ids() -> None:
    pack = _metric_pack(metric_ids=("mrr",), built_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC))

    with pytest.raises(ValidationError, match="greater than or equal"):
        StartupReadinessSnapshot.build(
            profile_id=pack.profile_id,
            profile_hash=pack.profile_hash,
            profile_revision=0,
            metric_pack=pack,
            calculation_ids=(uuid4(),),
            diagnostic_ids=(),
            built_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        )


def test_readiness_snapshot_rejects_bad_schema_version() -> None:
    pack = _metric_pack(metric_ids=("mrr",), built_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC))
    valid = StartupReadinessSnapshot.build(
        profile_id=pack.profile_id,
        profile_hash=pack.profile_hash,
        profile_revision=4,
        metric_pack=pack,
        calculation_ids=(uuid4(),),
        diagnostic_ids=(),
        built_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
    )

    with pytest.raises(ValidationError, match="schema_version"):
        StartupReadinessSnapshot.model_validate({**valid.model_dump(), "schema_version": "startup_readiness@2"})


def _metric_pack_payload(
    *,
    metric_ids: tuple[str, ...],
    built_at: datetime,
    dimensions: tuple[StartupReadinessDimension, ...] | None = None,
    adaptive_questions: tuple[StartupAdaptiveQuestion, ...] | None = None,
) -> StartupMetricPack:
    if dimensions is None:
        dimensions = (
            StartupReadinessDimension(
                dimension_id=_stable_uuid("business_model"),
                metric_id="mrr",
                status=StartupReadinessDimensionStatus.READY,
            ),
        )
    if adaptive_questions is None:
        adaptive_questions = ()
    profile_id = uuid5(NAMESPACE_URL, "case:77777777-7777-4777-8777-777777777777")
    profile_hash = "sha256:" + ("a" * 64)
    return StartupMetricPack.build(
        profile_id=profile_id,
        profile_hash=profile_hash,
        profile_revision=4,
        metric_ids=metric_ids,
        built_at=built_at,
        dimensions=dimensions,
        adaptive_questions=adaptive_questions,
    )


def _metric_pack(
    *,
    metric_ids: tuple[str, ...],
    built_at: datetime,
) -> StartupMetricPack:
    return _metric_pack_payload(metric_ids=metric_ids, built_at=built_at)


def _stable_uuid(seed: str) -> UUID:
    return uuid5(NAMESPACE_URL, seed)
