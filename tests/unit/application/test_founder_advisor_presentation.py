from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from due_diligence_agent.application.services.founder_advisor_presentation_service import (
    FounderAdvisorPresentationService,
)
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest


AS_OF = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def test_missing_values_become_actionable_russian_guidance() -> None:
    view = FounderAdvisorPresentationService().build(_snapshot_with_missing_mrr())

    card = view.metric_cards["mrr"]
    assert card.status == "needs_input"
    assert "не хватает данных" not in card.summary_ru.lower()
    assert card.next_unlock_ru is not None
    assert "добавьте MRR" in card.next_unlock_ru
    assert "точнее оценить выручку" in card.next_unlock_ru
    assert "MISSING" not in repr(view)


def test_confirmed_and_estimated_values_are_visually_distinct() -> None:
    view = FounderAdvisorPresentationService().build(
        _snapshot_with_confirmed_and_estimated_metrics()
    )

    confirmed = view.metric_cards["gross_margin"]
    estimated = view.metric_cards["tam"]

    assert confirmed.status == "confirmed"
    assert confirmed.next_unlock_ru
    assert estimated.status == "estimated"
    assert estimated.next_unlock_ru
    assert "гипотеза" in estimated.summary_ru.lower()


def test_canonical_calculation_row_wins_over_readiness_and_excludes_readiness_only_cards() -> None:
    view = FounderAdvisorPresentationService().build(
        _snapshot(
            metrics_rows=(
                (
                    "gross_margin",
                    "0.72",
                    "ratio",
                    "2026-08",
                    "gross_margin@1",
                    "calculation_ref=gross-margin",
                ),
                (
                    "gross_margin",
                    "ready",
                    "metric.calculated:gross_margin@1",
                    "dimension_ref=00000000-0000-0000-0000-000000000001",
                ),
                (
                    "activation",
                    "ready",
                    "method.profile_field:activation",
                    "dimension_ref=00000000-0000-0000-0000-000000000002",
                ),
            ),
            market_size_rows=(),
        )
    )

    assert tuple(view.metric_cards) == ("gross_margin",)
    card = view.metric_cards["gross_margin"]
    assert card.status == "confirmed"
    assert card.summary_ru == "Значение «Валовая маржа» подтверждено: 0.72."


def test_blocked_readiness_row_with_input_missing_never_replaces_a_calculation_card() -> None:
    view = FounderAdvisorPresentationService().build(
        _snapshot(
            metrics_rows=(
                (
                    "gross_margin",
                    "0.72",
                    "ratio",
                    "2026-08",
                    "gross_margin@1",
                    "calculation_ref=gross-margin",
                ),
                (
                    "gross_margin",
                    "blocked",
                    "input.missing:revenue",
                    "dimension_ref=00000000-0000-0000-0000-000000000003",
                ),
                (
                    "mrr",
                    "blocked",
                    "input.missing:monthly_recurring_revenue",
                    "dimension_ref=00000000-0000-0000-0000-000000000004",
                ),
            ),
            market_size_rows=(),
        )
    )

    assert tuple(view.metric_cards) == ("gross_margin",)
    card = view.metric_cards["gross_margin"]
    assert card.status == "confirmed"
    assert card.summary_ru == "Значение «Валовая маржа» подтверждено: 0.72."


def test_source_backed_metric_fact_rows_become_founder_cards_without_locator_leakage() -> None:
    view = FounderAdvisorPresentationService().build(
        _snapshot(
            metrics_rows=(
                (
                    "gross_margin",
                    "74",
                    "percent",
                    "2026-Q2",
                    "evidence_ref=00000000-0000-0000-0000-000000000011",
                ),
                (
                    "runway",
                    "7.8",
                    "months",
                    "2026-07",
                    "evidence_ref=00000000-0000-0000-0000-000000000012",
                ),
            ),
            market_size_rows=(),
        )
    )

    assert tuple(view.metric_cards) == ("gross_margin", "runway")
    assert view.metric_cards["gross_margin"].summary_ru == (
        "Значение «Валовая маржа» подтверждено: 74."
    )
    assert view.metric_cards["runway"].status == "confirmed"
    dumped = view.model_dump_json()
    assert "evidence_ref=" not in dumped
    assert "00000000-0000-0000-0000-000000000011" not in dumped


def test_founder_clarification_with_highest_confidence_selects_confirmed_mrr_value() -> None:
    view = FounderAdvisorPresentationService().build(
        _snapshot(
            metrics_rows=(
                (
                    "monthly_recurring_revenue",
                    "27900000",
                    "KZT",
                    "unknown",
                    "status=source_fact",
                    "confidence=0.95",
                    "evidence_ref=00000000-0000-0000-0000-000000000021",
                ),
                (
                    "monthly_recurring_revenue",
                    "27900000",
                    "KZT",
                    "unknown",
                    "status=source_fact",
                    "confidence=0.70",
                    "evidence_ref=00000000-0000-0000-0000-000000000022",
                ),
                (
                    "monthly_recurring_revenue",
                    "28600000",
                    "KZT",
                    "unknown",
                    "status=source_fact",
                    "confidence=0.70",
                    "evidence_ref=00000000-0000-0000-0000-000000000023",
                ),
            ),
            market_size_rows=(),
        )
    )

    card = view.metric_cards["monthly_recurring_revenue"]
    assert card.status == "confirmed"
    assert card.summary_ru == "Значение «MRR» подтверждено: 27900000."


def test_canonical_source_statuses_map_to_all_founder_card_statuses() -> None:
    view = FounderAdvisorPresentationService().build(
        _snapshot(
            metrics_rows=(
                (
                    "gross_margin",
                    "0.72",
                    "ratio",
                    "2026-08",
                    "gross_margin@1",
                    "calculation_ref=gross-margin",
                ),
            ),
            market_size_rows=(
                (
                    "tam",
                    "inference",
                    "12000000",
                    "customers",
                    "USD",
                    "as_of=2026-08-16",
                    "source_mode=frozen",
                    "formula=market_sizing@1",
                ),
                (
                    "sam",
                    "insufficient_data",
                    "MISSING",
                    "customers",
                    "USD",
                    "as_of=2026-08-16",
                    "source_mode=frozen",
                    "formula=market_sizing@1",
                ),
                (
                    "som",
                    "contradiction",
                    "MISSING",
                    "customers",
                    "USD",
                    "as_of=2026-08-16",
                    "source_mode=frozen",
                    "formula=market_sizing@1",
                ),
            ),
        )
    )

    assert view.metric_cards["gross_margin"].status == "confirmed"
    assert view.metric_cards["tam"].status == "estimated"
    assert view.metric_cards["sam"].status == "needs_input"
    assert view.metric_cards["som"].status == "contradiction"


def _snapshot_with_missing_mrr() -> ReportSnapshot:
    return _snapshot(
        metrics_rows=(
            (
                "mrr",
                "MISSING",
                "USD/month",
                "2026-08",
                "mrr@1",
                "input.missing:monthly_recurring_revenue",
            ),
        ),
        market_size_rows=(),
    )


def _snapshot_with_confirmed_and_estimated_metrics() -> ReportSnapshot:
    return _snapshot(
        metrics_rows=(
            (
                "gross_margin",
                "0.72",
                "ratio",
                "2026-08",
                "gross_margin@1",
                "calculation_ref=gross-margin",
            ),
        ),
        market_size_rows=(
            (
                "tam",
                "assumption",
                "12000000",
                "customers",
                "USD",
                "as_of=2026-08-16",
            ),
        ),
    )


def _snapshot(
    *, metrics_rows: tuple[tuple[str, ...], ...], market_size_rows: tuple[tuple[str, ...], ...]
) -> ReportSnapshot:
    return ReportSnapshot(
        id=uuid5(NAMESPACE_URL, "founder-advisor-presentation"),
        case_id=uuid5(NAMESPACE_URL, "founder-advisor-presentation-case"),
        report_hash="sha256:" + "a" * 64,
        case_snapshot_hash="sha256:" + "b" * 64,
        source_hashes={},
        as_of=AS_OF,
        graph_version="startup@1",
        prompt_versions={"report": "startup-report@1"},
        formula_versions={},
        model_versions={"analysis": "offline"},
        sections={
            "metrics": {
                "title": "Metrics",
                "summary": "Canonical metrics.",
                "status": "PARTIAL",
                "rows": metrics_rows,
                "items": (),
            },
            "market_size": {
                "title": "Market Size",
                "summary": "Canonical market sizing.",
                "status": "PARTIAL",
                "rows": market_size_rows,
                "items": (),
            },
        },
        json_artifact_ref="sha256:" + "c" * 64,
        content_hashes={"json": "sha256:" + "c" * 64},
        reproducibility=ReproducibilityManifest(
            code_commit="test",
            build_id="test",
            dependency_lock_hash="sha256:" + "d" * 64,
            python_version="3.13",
            package_versions={},
            provider_model_id="offline",
            model_alias_snapshot="offline",
            reasoning_parameters={},
            adapter_versions={},
            parser_versions={},
            redaction_policy_version="test",
            locale="en-US",
            timezone="UTC",
            deterministic_seeds={},
            configuration_hash="sha256:" + "e" * 64,
        ),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
    )
