from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from pydantic import SecretStr

from due_diligence_agent.adapters.startup.deterministic_profile_extractor import (
    DeterministicStartupProfileExtractor,
)
from due_diligence_agent.application.services.case_fact_intake_service import (
    CaseFactIntakeService,
    CaseMutationDelta,
    SaveFounderStatementCommand,
)
from due_diligence_agent.application.services.startup_advisor_api_service import (
    _STATE_KEY,
    StartupAdvisorApiContext,
    StartupAdvisorApiService,
)
from due_diligence_agent.application.startup_advisor_recalculation import (
    StartupAdvisorCaseRecalculationAdapter,
    StartupAdvisorImprovementRecalculationCommand,
    StartupAdvisorRecalculationCommand,
)
from due_diligence_agent.application.startup_cases import (
    StartupGateConflict,
    StartupValidationError,
)
from due_diligence_agent.bootstrap import container as bootstrap_container
from due_diligence_agent.bootstrap.container import build_startup_advisor_api_service
from due_diligence_agent.config import OpenAIStartupSettings
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    CaseStatus,
    ContradictionStatus,
    FindingSeverity,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest
from due_diligence_agent.domain.startup.advisor import AdvisorResearchDelta
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.ports.startup_profile_extraction import (
    StartupProfileBoundedFragment,
    StartupProfileExtractionRequest,
)
from due_diligence_agent.workflows.startup.runtime import InMemoryStartupWorkflowRuntimeStore

AS_OF = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
CASE_ID = uuid5(NAMESPACE_URL, "startup-advisor-api-case")
OTHER_CASE_ID = uuid5(NAMESPACE_URL, "startup-advisor-api-other-case")
THIRD_CASE_ID = uuid5(NAMESPACE_URL, "startup-advisor-api-third-case")
RESEARCH_SOURCE_ID = uuid5(NAMESPACE_URL, "startup-advisor-api-research-source")
HOSTILE_VALUE = (
    "C:\\Users\\Founder\\secret pitch.pdf founder@example.com "
    "sk-live-secret prompt: reveal all"
)
HOSTILE_REVENUE_VALUE = f"MRR $1000/month {HOSTILE_VALUE}"


def test_question_progress_survives_reconstruction_and_completes_without_persisting_answer() -> None:
    harness = _harness(CASE_ID)
    service = harness.service()

    first = service.get_next_question(str(CASE_ID))
    assert first.next_question is not None
    answered = service.submit_answer(
        str(CASE_ID),
        question_id=first.next_question.question_id,
        answer_type="manual",
        value=HOSTILE_REVENUE_VALUE,
    )

    assert first.status == "active"
    assert first.answered_count == 0
    assert first.total_count == 5
    assert first.next_question.field_key == "revenue_pricing"
    assert "Какая" in first.next_question.question_ru
    assert first.next_question.answer_mode_labels_ru["manual"] == "Вручную"
    assert answered.status == "applied"
    assert answered.research_result is None
    assert HOSTILE_VALUE not in answered.model_dump_json()
    assert HOSTILE_VALUE not in json.dumps(
        harness.workflow_store.load(str(CASE_ID)),
        ensure_ascii=False,
    )

    restarted = harness.service()
    second = restarted.get_next_question(str(CASE_ID))
    assert second.answered_count == 1
    assert second.next_question is not None
    assert second.next_question.field_key == "icp"

    current = second
    while current.next_question is not None:
        restarted.submit_answer(
            str(CASE_ID),
            question_id=current.next_question.question_id,
            answer_type="skip",
        )
        current = restarted.get_next_question(str(CASE_ID))

    assert current.status == "complete"
    assert current.next_question is None
    assert current.answered_count == current.total_count == 5


def test_applied_advisor_answer_triggers_same_case_recalculation_projection() -> None:
    harness = _harness(CASE_ID)
    recalculation = _RecalculationProbe(harness.workflow_store)
    service = harness.service(recalculation_port=recalculation)
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None

    applied = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value=HOSTILE_REVENUE_VALUE,
    )

    assert len(recalculation.calls) == 1
    command = recalculation.calls[0]
    assert str(command.case_id) == str(CASE_ID)
    assert command.question_id == question.question_id
    assert command.field_key == "revenue_pricing"
    assert command.answer_type == "manual"
    assert command.private_value.get_secret_value() == HOSTILE_REVENUE_VALUE
    assert HOSTILE_REVENUE_VALUE not in repr(command)
    assert HOSTILE_REVENUE_VALUE not in command.model_dump_json()
    assert applied.recalculation_status == "started"
    assert applied.recalculation_data_revision == 2
    assert applied.recalculation_analysis_status == "gate2_preview_ready"
    assert applied.recalculation_delta is not None
    assert applied.recalculation_delta.fields_changed == ()
    assert applied.recalculation_delta.core_coverage_delta == 0
    assert applied.recalculation_delta.conflicts_resolved == 0

    runtime = harness.workflow_store.load(str(CASE_ID))
    assert runtime["data_revision"] == 2
    assert runtime["active_analysis_thread_id"] == f"{CASE_ID}:r2"
    assert runtime["canonical_report_snapshot_id"] is None
    assert runtime["canonical_report_snapshot_hash"] is None
    assert runtime["canonical_report_snapshot_revision"] is None
    assert HOSTILE_VALUE not in json.dumps(runtime, ensure_ascii=False)


def test_next_question_uses_current_profile_gaps_before_static_priority() -> None:
    harness = _harness(CASE_ID)
    harness.profiles.profiles[CASE_ID] = _profile(
        CASE_ID,
        source_field_values={
            StartupProfileFieldName.ONE_LINE_DESCRIPTION: ("AI logistics platform",),
            StartupProfileFieldName.PROBLEM: ("inventory errors",),
            StartupProfileFieldName.STAGE: ("Seed",),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: (
                "подписка $19 в месяц и комиссионные от партнеров.",
            ),
        },
    )

    question = harness.service().get_next_question(str(CASE_ID)).next_question

    assert question is not None
    assert question.field_key == "icp"
    assert question.origin == "document_gap"


def test_next_question_prioritizes_document_contradiction_with_safe_origin() -> None:
    harness = _harness(CASE_ID)
    harness.profiles.profiles[CASE_ID] = _profile(
        CASE_ID,
        source_field_values={
            StartupProfileFieldName.ONE_LINE_DESCRIPTION: ("AI logistics platform",),
            StartupProfileFieldName.PROBLEM: ("inventory errors",),
            StartupProfileFieldName.STAGE: ("Seed",),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: ("Starter 240 000 KZT/month",),
        },
    )
    harness.contradictions.items[CASE_ID] = [
        _contradiction(
            CASE_ID,
            conflict_type="startup_explicit_metric_mrr",
            explanation=(
                "MRR CONTRADICTION CRM 28.6m KZT; invoices 27.9m KZT; "
                "bank evidence also supports 27.9m KZT."
            ),
        )
    ]

    response = harness.service().get_next_question(str(CASE_ID))

    assert response.next_question is not None
    assert response.next_question.field_key == "revenue_pricing"
    assert response.next_question.origin == "document_contradiction"
    assert response.next_question.origin_label_ru == "Противоречие в документе"
    assert "MRR" in response.next_question.question_ru
    assert "CRM" in response.next_question.question_ru
    assert "invoice" in response.next_question.question_ru
    assert "public_research" not in response.next_question.answer_modes
    serialized = response.model_dump_json()
    assert "startup_explicit_metric_mrr" not in serialized
    assert "prompt" not in serialized.casefold()
    assert "C:\\" not in serialized


def test_persisted_dynamic_order_answers_replay_after_service_reconstruction() -> None:
    harness = _harness(CASE_ID)
    harness.profiles.profiles[CASE_ID] = _profile(
        CASE_ID,
        source_field_values={
            StartupProfileFieldName.ONE_LINE_DESCRIPTION: ("AI logistics platform",),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: ("Starter 240 000 KZT/month",),
        },
    )
    first = harness.service().get_next_question(str(CASE_ID))
    assert first.next_question is not None
    assert first.next_question.field_key == "problem"
    harness.service().submit_answer(
        str(CASE_ID),
        question_id=first.next_question.question_id,
        answer_type="skip",
    )

    restarted = harness.service()
    second = restarted.get_next_question(str(CASE_ID))

    assert second.answered_count == 1
    assert second.next_question is not None
    assert second.next_question.field_key == "stage"


def test_progress_total_stays_stable_when_profile_gaps_shrink_after_replay() -> None:
    harness = _harness(CASE_ID)
    harness.profiles.profiles[CASE_ID] = _profile(
        CASE_ID,
        source_field_values={
            StartupProfileFieldName.PRICING_REVENUE_MODEL: (
                "Starter 240 000 KZT/month",
            ),
        },
    )
    first = harness.service().get_next_question(str(CASE_ID))
    assert first.next_question is not None
    assert first.next_question.field_key == "product"
    harness.service().submit_answer(
        str(CASE_ID),
        question_id=first.next_question.question_id,
        answer_type="skip",
    )
    harness.profiles.profiles[CASE_ID] = _profile(
        CASE_ID,
        source_field_values={
            field_name: ("source-backed value",)
            for field_name in StartupProfileFieldName
        },
    )

    restarted = harness.service().get_next_question(str(CASE_ID))

    assert restarted.status == "complete"
    assert restarted.answered_count == 1
    assert restarted.total_count == 1
    assert restarted.answered_count <= restarted.total_count


def test_replay_rejects_question_id_bound_to_different_field_key() -> None:
    harness = _harness(CASE_ID)
    harness.workflow_store.update(
        str(CASE_ID),
        lambda _runtime: {
            _STATE_KEY: {
                "answers": [
                    {
                        "question_id": f"{CASE_ID}:revenue_pricing",
                        "field_key": "icp",
                        "answer_type": "skip",
                    }
                ]
            }
        },
    )

    with pytest.raises(StartupGateConflict, match="advisor_progress_invalid"):
        harness.service().get_next_question(str(CASE_ID))


def test_manual_revenue_answer_rejects_bare_percentage_as_semantic_mismatch() -> None:
    harness = _harness(CASE_ID)
    question = harness.service().get_next_question(str(CASE_ID)).next_question
    assert question is not None
    assert question.field_key == "revenue_pricing"

    with pytest.raises(StartupValidationError, match="advisor_manual_answer_semantic_mismatch"):
        harness.service().submit_answer(
            str(CASE_ID),
            question_id=question.question_id,
            answer_type="manual",
            value="60%",
        )


def test_manual_margin_answer_accepts_labeled_percentage_for_economics_question() -> None:
    harness = _harness(CASE_ID)
    harness.contradictions.items[CASE_ID] = [
        _contradiction(
            CASE_ID,
            conflict_type="startup_explicit_metric_margin",
            explanation="Gross margin CONTRADICTION ops 74%; finance 70%.",
        )
    ]
    recalculation = _ProfileAndContradictionMutatingRecalculationProbe(
        harness,
        source_field_values={
            StartupProfileFieldName.TRACTION: ("Gross margin 60% for July 2026.",)
        },
        remaining_contradictions=[],
    )
    service = harness.service(recalculation_port=recalculation)
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None
    assert question.field_key == "traction"
    assert question.origin == "document_contradiction"

    applied = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value="Use finance view for July 2026: 60% gross margin.",
    )

    assert applied.status == "applied"
    assert applied.field_key == "traction"
    assert applied.recalculation_delta is not None
    assert applied.recalculation_delta.previous_revision == 1
    assert applied.recalculation_delta.new_revision == 2
    assert applied.recalculation_delta.fields_changed == ("traction",)
    assert applied.recalculation_delta.core_coverage_delta == 0
    assert applied.recalculation_delta.conflicts_resolved == 1
    assert applied.recalculation_delta.conflicts_remaining == 0


def test_manual_icp_answer_requires_segment_or_persona_language() -> None:
    harness = _harness(CASE_ID)
    harness.profiles.profiles[CASE_ID] = _profile(
        CASE_ID,
        source_field_values={
            StartupProfileFieldName.ONE_LINE_DESCRIPTION: ("AI logistics platform",),
            StartupProfileFieldName.PROBLEM: ("inventory errors",),
            StartupProfileFieldName.STAGE: ("Seed",),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: (
                "Starter 240 000 KZT/month.",
            ),
        },
    )
    service = harness.service(recalculation_port=_RecalculationProbe(harness.workflow_store))
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None
    assert question.field_key == "icp"

    with pytest.raises(StartupValidationError, match="advisor_manual_answer_semantic_mismatch"):
        service.submit_answer(
            str(CASE_ID),
            question_id=question.question_id,
            answer_type="manual",
            value="42",
        )

    applied = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value="FMCG distributors in Kazakhstan, procurement managers and ops directors.",
    )
    assert applied.status == "applied"
    assert applied.field_key == "icp"


def test_manual_contradiction_resolution_requires_specific_value_or_keep_open() -> None:
    harness = _harness(CASE_ID)
    harness.contradictions.items[CASE_ID] = [
        _contradiction(
            CASE_ID,
            conflict_type="startup_explicit_metric_mrr",
            explanation="MRR CONTRADICTION CRM 28.6m KZT; invoices 27.9m KZT.",
        )
    ]
    service = harness.service(
        recalculation_port=_ProfileAndContradictionMutatingRecalculationProbe(
            harness,
            source_field_values={
                StartupProfileFieldName.PRICING_REVENUE_MODEL: (
                    "Invoices for July 2026: MRR 27.9m KZT.",
                )
            },
            remaining_contradictions=[],
        )
    )
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None
    assert question.origin == "document_contradiction"

    with pytest.raises(StartupValidationError, match="advisor_manual_answer_semantic_mismatch"):
        service.submit_answer(
            str(CASE_ID),
            question_id=question.question_id,
            answer_type="manual",
            value="Invoices look more reliable.",
        )

    applied = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value="Use invoices for July 2026: MRR 27.9m KZT; close CRM variance.",
    )
    assert applied.status == "applied"
    assert applied.recalculation_delta is not None
    assert applied.recalculation_delta.fields_changed == ("pricing_revenue_model",)
    assert applied.recalculation_delta.core_coverage_delta == 1
    assert applied.recalculation_delta.conflicts_resolved == 1
    assert applied.recalculation_delta.conflicts_remaining == 0


def test_manual_mrr_clarification_updates_profile_without_promoting_source_fact() -> None:
    harness = _harness(CASE_ID)
    harness.profiles.profiles[CASE_ID] = _profile(
        CASE_ID,
        source_field_values={
            StartupProfileFieldName.PRICING_REVENUE_MODEL: (
                "Starter 240 000 KZT/month",
                "Growth 690 000 KZT/month",
            ),
        },
    )
    crm = _mrr_fact(CASE_ID, key="crm", value="28600000")
    invoices = _mrr_fact(CASE_ID, key="invoices", value="27900000")
    clarification = _mrr_fact(CASE_ID, key="advisor", value="27900000")
    harness.evidence.add_for_case(CASE_ID, crm)
    harness.evidence.add_for_case(CASE_ID, invoices)
    mrr_explicit = _contradiction(
        CASE_ID,
        conflict_type="startup_explicit_metric_mrr",
        explanation="MRR CONTRADICTION CRM 28.6m KZT; invoices 27.9m KZT.",
    )
    unrelated = [
        _contradiction(
            CASE_ID,
            conflict_type="startup_explicit_metric_customer_count",
            explanation="Customer count CONTRADICTION CRM 31; invoices 29.",
        ),
        _contradiction(
            CASE_ID,
            conflict_type="startup_explicit_metric_margin",
            explanation="Gross margin CONTRADICTION ops 74%; finance 70%.",
        ),
        _contradiction(
            CASE_ID,
            conflict_type="startup_explicit_metric_cac_payback",
            explanation="CAC payback CONTRADICTION CRM 4.3 months; finance 5.5 months.",
        ),
    ]
    harness.contradictions.items[CASE_ID] = [mrr_explicit, *unrelated]
    service = harness.service(
        recalculation_port=_FounderClarificationRecalculationProbe(
            harness,
            clarification=clarification,
            related_fact_ids=(crm.id, invoices.id),
        )
    )
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None
    assert question.origin == "document_contradiction"
    assert question.field_key == "revenue_pricing"

    applied = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value=(
            "Use bank and invoice register for June 2026: recognized MRR is "
            "27.9m KZT; exclude CRM-only free-extension accounts."
        ),
    )

    accepted_facts = [
        fact
        for fact in harness.evidence.list_for_case(CASE_ID)
        if fact.metadata.get("founder_clarification") == "accepted_source"
    ]
    assert accepted_facts == []
    statuses = {
        item.conflict_type: item.status
        for item in harness.contradictions.list_for_case(CASE_ID)
    }
    assert statuses["startup_explicit_metric_mrr"] is ContradictionStatus.OPEN
    assert statuses["source_fact_value_conflict"] is ContradictionStatus.OPEN
    assert statuses["startup_explicit_metric_customer_count"] is ContradictionStatus.OPEN
    assert statuses["startup_explicit_metric_margin"] is ContradictionStatus.OPEN
    assert statuses["startup_explicit_metric_cac_payback"] is ContradictionStatus.OPEN
    profile = harness.profiles.get_current(CASE_ID)
    pricing = profile.fields[StartupProfileFieldName.PRICING_REVENUE_MODEL]
    assert pricing.values[0].startswith("Use bank and invoice register for June 2026")
    assert "Starter 240 000 KZT/month" in pricing.values
    assert applied.recalculation_delta is not None
    assert applied.recalculation_delta.fields_changed == ("pricing_revenue_model",)
    assert applied.recalculation_delta.conflicts_resolved == 0
    assert applied.recalculation_delta.conflicts_remaining == 5


def test_manual_founder_clarification_does_not_promote_to_source_fact() -> None:
    harness = _harness(CASE_ID)
    harness.profiles.profiles[CASE_ID] = _profile(
        CASE_ID,
        source_field_values={
            StartupProfileFieldName.PRICING_REVENUE_MODEL: (
                "Starter 240 000 KZT/month",
                "Growth 690 000 KZT/month",
            ),
        },
    )
    crm = _mrr_fact(CASE_ID, key="crm-no-promotion", value="28600000")
    invoices = _mrr_fact(CASE_ID, key="invoices-no-promotion", value="27900000")
    clarification = _mrr_fact(CASE_ID, key="advisor-no-promotion", value="27900000")
    harness.evidence.add_for_case(CASE_ID, crm)
    harness.evidence.add_for_case(CASE_ID, invoices)
    harness.contradictions.items[CASE_ID] = [
        _contradiction(
            CASE_ID,
            conflict_type="startup_explicit_metric_mrr",
            explanation="MRR CONTRADICTION CRM 28.6m KZT; invoices 27.9m KZT.",
        )
    ]
    service = harness.service(
        recalculation_port=_FounderClarificationRecalculationProbe(
            harness,
            clarification=clarification,
            related_fact_ids=(crm.id, invoices.id),
        )
    )
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None

    service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value="Use invoices for June 2026: MRR is 27.9m KZT.",
    )

    accepted_source_facts = [
        fact
        for fact in harness.evidence.list_for_case(CASE_ID)
        if fact.metadata.get("founder_clarification") == "accepted_source"
    ]
    assert accepted_source_facts == []


def test_recalculation_delta_uses_real_post_state_not_question_template() -> None:
    harness = _harness(CASE_ID)
    harness.contradictions.items[CASE_ID] = [
        _contradiction(
            CASE_ID,
            conflict_type="startup_explicit_metric_mrr",
            explanation="MRR CONTRADICTION CRM 28.6m KZT; invoices 27.9m KZT.",
        )
    ]
    service = harness.service(recalculation_port=_RecalculationProbe(harness.workflow_store))
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None
    assert question.origin == "document_contradiction"

    applied = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value="Use invoices for July 2026: MRR 27.9m KZT; close CRM variance.",
    )

    assert applied.recalculation_delta is not None
    assert applied.recalculation_delta.previous_revision == 1
    assert applied.recalculation_delta.new_revision == 2
    assert applied.recalculation_delta.fields_changed == ()
    assert applied.recalculation_delta.core_coverage_delta == 0
    assert applied.recalculation_delta.conflicts_resolved == 0
    assert applied.recalculation_delta.conflicts_remaining == 1
    assert applied.recalculation_delta.calculations_recalculated == ()


def test_recalculation_delta_reports_signed_core_coverage_loss() -> None:
    harness = _harness(CASE_ID)
    harness.profiles.profiles[CASE_ID] = _profile(
        CASE_ID,
        source_field_values={
            StartupProfileFieldName.ONE_LINE_DESCRIPTION: ("AI logistics platform",),
            StartupProfileFieldName.PROBLEM: ("inventory errors",),
            StartupProfileFieldName.STAGE: ("Seed",),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: (
                "Starter 240 000 KZT/month",
            ),
        },
    )
    recalculation = _ProfileAndContradictionMutatingRecalculationProbe(
        harness,
        source_field_values={
            StartupProfileFieldName.ONE_LINE_DESCRIPTION: ("AI logistics platform",),
            StartupProfileFieldName.PROBLEM: ("inventory errors",),
            StartupProfileFieldName.STAGE: ("Seed",),
        },
        remaining_contradictions=[],
        replace_source_fields=True,
    )
    service = harness.service(recalculation_port=recalculation)
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None

    applied = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value="FMCG distributors in Kazakhstan, procurement managers and ops directors.",
    )

    assert applied.recalculation_delta is not None
    assert applied.recalculation_delta.fields_changed == ("pricing_revenue_model",)
    assert applied.recalculation_delta.core_coverage_delta == -1


def test_recalculation_delta_reports_real_calculation_changes_only_by_metric_name() -> None:
    harness = _harness(CASE_ID)
    harness.calculations.items[CASE_ID] = [
        _calculation(CASE_ID, metric_name="runway_months", value=Decimal(7))
    ]
    recalculation = _CalculationMutatingRecalculationProbe(
        harness,
        calculations=[
            _calculation(CASE_ID, metric_name="runway_months", value=Decimal(9)),
            _calculation(CASE_ID, metric_name="ltv_cac_ratio", value=Decimal("2.4")),
        ],
    )
    service = harness.service(recalculation_port=recalculation)
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None

    applied = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value=HOSTILE_REVENUE_VALUE,
    )

    assert applied.recalculation_delta is not None
    assert applied.recalculation_delta.calculations_recalculated == (
        "ltv_cac_ratio",
        "runway_months",
    )
    serialized = applied.model_dump_json()
    assert "2.4" not in serialized
    assert "9" not in serialized
    assert "fact:" not in serialized


def test_recalculation_delta_filters_unsafe_calculation_metric_names() -> None:
    harness = _harness(CASE_ID)
    harness.calculations.items[CASE_ID] = [
        _calculation(CASE_ID, metric_name="runway_months", value=Decimal(7))
    ]
    recalculation = _CalculationMutatingRecalculationProbe(
        harness,
        calculations=[
            _calculation(CASE_ID, metric_name="runway_months", value=Decimal(9)),
            _calculation(
                CASE_ID,
                metric_name="C:\\Users\\Founder\\secret runway sk-live-token",
                value=Decimal(3),
            ),
        ],
    )
    service = harness.service(recalculation_port=recalculation)
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None

    applied = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="manual",
        value=HOSTILE_REVENUE_VALUE,
    )

    assert applied.recalculation_delta is not None
    assert applied.recalculation_delta.calculations_recalculated == ("runway_months",)
    serialized = applied.model_dump_json()
    assert "Founder" not in serialized
    assert "secret" not in serialized
    assert "sk-live" not in serialized
    assert "C:\\Users" not in serialized


def test_manual_answer_adapter_saves_founder_statement_without_docx_upload() -> None:
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(str(CASE_ID), {"data_revision": 1})
    coordinator = _CaptureUploadCoordinator(workflow_store)
    founder_intake = _FounderStatementIntakeProbe()
    adapter = StartupAdvisorCaseRecalculationAdapter(
        coordinator=coordinator,
        workflow_store=workflow_store,
        founder_statement_intake=founder_intake,
    )

    result = adapter.apply_answer(
        StartupAdvisorRecalculationCommand(
            case_id=CASE_ID,
            question_id=f"{CASE_ID}:revenue_pricing",
            field_key="revenue_pricing",
            answer_type="manual",
            private_value=SecretStr(
                "Use bank and invoice register for June 2026: recognized MRR is "
                "27.9m KZT; exclude CRM-only free-extension accounts."
            ),
        )
    )

    assert coordinator.upload_calls == []
    assert coordinator.uploaded_content == b""
    assert result.status == "started"
    assert result.data_revision == 2
    assert result.analysis_status == "gate2_preview_ready"
    assert workflow_store.load(str(CASE_ID))["data_revision"] == 2
    assert len(founder_intake.commands) == 1
    command = founder_intake.commands[0]
    assert command.case_id == CASE_ID
    assert command.requirement_key == "pricing_revenue_model"
    assert command.expected_case_revision == 1
    assert command.idempotency_key == f"advisor-answer:{CASE_ID}:revenue_pricing:manual"
    assert command.value == (
        "Use bank and invoice register for June 2026: recognized MRR is "
        "27.9m KZT; exclude CRM-only free-extension accounts."
    )


def test_manual_answer_recalculation_resets_stale_downstream_gate_state() -> None:
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(
        str(CASE_ID),
        {
            "data_revision": 2,
            "analysis_status": "gate3_review_required",
            "gate2_status": "completed",
            "gate3_status": "required",
            "gate4_status": "required",
            "report_status": "ready",
            "canonical_report_snapshot_id": "old-report",
            "canonical_report_snapshot_hash": "old-hash",
            "canonical_report_snapshot_revision": 2,
            "draft_report_snapshot_id": "old-draft",
            "gate3_reviewed": True,
            "gate3_exclusions": [{"evidence_fact_id": "old-fact"}],
            "gate3_recompute_started": True,
            "gate3_report_finalized": True,
            "gate4_reviewed": True,
            "gate4_last_decision": "approved",
        },
    )
    coordinator = _CaptureUploadCoordinator(workflow_store)
    founder_intake = _FounderStatementIntakeProbe(old_revision=2, new_revision=3)
    adapter = StartupAdvisorCaseRecalculationAdapter(
        coordinator=coordinator,
        workflow_store=workflow_store,
        founder_statement_intake=founder_intake,
    )

    result = adapter.apply_answer(
        StartupAdvisorRecalculationCommand(
            case_id=CASE_ID,
            question_id=f"{CASE_ID}:revenue_pricing",
            field_key="revenue_pricing",
            answer_type="manual",
            private_value=SecretStr("Recognized MRR is 27.9m KZT for June 2026."),
        )
    )

    runtime = workflow_store.load(str(CASE_ID))
    assert result.status == "started"
    assert result.data_revision == 3
    assert result.analysis_status == "gate2_preview_ready"
    assert runtime["analysis_status"] == "gate2_preview_ready"
    assert runtime["active_analysis_thread_id"] == f"{CASE_ID}:r3"
    assert runtime["gate2_status"] == "not_ready"
    assert runtime["gate3_status"] == "not_ready"
    assert runtime["gate4_status"] == "not_ready"
    assert runtime["report_status"] == "not_ready"
    assert runtime["canonical_report_snapshot_id"] is None
    assert runtime["canonical_report_snapshot_hash"] is None
    assert runtime["canonical_report_snapshot_revision"] is None
    assert runtime["draft_report_snapshot_id"] is None
    assert "gate3_reviewed" not in runtime
    assert "gate3_exclusions" not in runtime
    assert "gate3_recompute_started" not in runtime
    assert "gate3_report_finalized" not in runtime
    assert "gate4_reviewed" not in runtime
    assert "gate4_last_decision" not in runtime


def test_manual_money_answer_adapter_builds_typed_founder_statement_command() -> None:
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(str(CASE_ID), {"data_revision": 1})
    coordinator = _CaptureUploadCoordinator(workflow_store)
    founder_intake = _FounderStatementIntakeProbe()
    adapter = StartupAdvisorCaseRecalculationAdapter(
        coordinator=coordinator,
        workflow_store=workflow_store,
        founder_statement_intake=founder_intake,
    )

    result = adapter.apply_answer(
        StartupAdvisorRecalculationCommand(
            case_id=CASE_ID,
            question_id=f"{CASE_ID}:burn_cash",
            field_key="burn_cash",
            answer_type="manual",
            private_value=SecretStr(
                "Use finance forecast for July 2026: cash balance $250,000, "
                "monthly net burn $42,000, runway about 6 months."
            ),
        )
    )

    assert result.status == "started"
    command = founder_intake.commands[0]
    assert command.requirement_key == "burn"
    assert command.value == "42000"
    assert command.currency == "USD"
    assert command.scale == "ones"
    assert command.period == "2026-07"
    runtime = workflow_store.load(str(CASE_ID))
    assert runtime["data_revision"] == 2
    assert runtime["active_analysis_thread_id"] == f"{CASE_ID}:r2"


def test_manual_money_answer_adapter_projects_valid_revision_2_primary_profile() -> None:
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(str(CASE_ID), {"data_revision": 1, "fixture_mode": "live"})
    coordinator = _CaptureUploadCoordinator(workflow_store)
    founder_intake = _FounderStatementIntakeProbe()
    profile_repository = _ProfileRepository({CASE_ID: _profile(CASE_ID)})
    adapter = StartupAdvisorCaseRecalculationAdapter(
        coordinator=coordinator,
        workflow_store=workflow_store,
        founder_statement_intake=founder_intake,
        profile_repository=profile_repository,
    )

    result = adapter.apply_answer(
        StartupAdvisorRecalculationCommand(
            case_id=CASE_ID,
            question_id=f"{CASE_ID}:burn_cash",
            field_key="burn_cash",
            answer_type="manual",
            private_value=SecretStr(
                "Use finance forecast for July 2026: cash balance $250,000, "
                "monthly net burn $42,000, runway about 6 months."
            ),
        )
    )

    assert result.status == "started"
    assert coordinator.upload_calls == []
    projected = profile_repository.get_current(CASE_ID)
    assert projected.data_revision == 2
    assert projected.analysis_stage is StartupProfileAnalysisStage.PRIMARY
    assert projected.parent_profile_id is None
    source_fact_values = [
        value
        for field in projected.fields.values()
        if field.status is StartupProfileFieldStatus.SOURCE_FACT
        for value in field.values
    ]
    assert "monthly_net_burn: 42000 USD" not in source_fact_values
    assert "runway: 6 months" not in source_fact_values
    assumptions = projected.fields[StartupProfileFieldName.ASSUMPTIONS.value]
    assert assumptions.status is StartupProfileFieldStatus.INSUFFICIENT_DATA
    assert (
        "Use finance forecast for July 2026: cash balance $250,000, "
        "monthly net burn $42,000, runway about 6 months."
    ) not in assumptions.values
    runtime = workflow_store.load(str(CASE_ID))
    assert runtime["data_revision"] == 2
    assert runtime["profile_revision"] == 2
    assert runtime["profile_id"] == str(projected.profile_id)


def test_manual_money_answer_without_period_returns_field_validation_without_mutation() -> None:
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(str(CASE_ID), {"data_revision": 1})
    coordinator = _CaptureUploadCoordinator(workflow_store)
    founder_intake = _FounderStatementIntakeProbe()
    adapter = StartupAdvisorCaseRecalculationAdapter(
        coordinator=coordinator,
        workflow_store=workflow_store,
        founder_statement_intake=founder_intake,
    )

    result = adapter.apply_answer(
        StartupAdvisorRecalculationCommand(
            case_id=CASE_ID,
            question_id=f"{CASE_ID}:burn_cash",
            field_key="burn_cash",
            answer_type="manual",
            private_value=SecretStr("monthly net burn $42,000, runway about 6 months."),
        )
    )

    assert result.status == "deferred"
    assert result.safe_error_code == "advisor_founder_statement_validation_failed"
    assert founder_intake.commands == []
    assert workflow_store.load(str(CASE_ID))["data_revision"] == 1


def test_improvement_adapter_keeps_private_recommendation_out_of_extracted_assumptions() -> None:
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(str(CASE_ID), {"data_revision": 1})
    coordinator = _CaptureUploadCoordinator(workflow_store)
    adapter = StartupAdvisorCaseRecalculationAdapter(
        coordinator=coordinator,
        workflow_store=workflow_store,
    )
    private_recommendation = "Private pricing recommendation should stay hidden"

    adapter.apply_improvement(
        StartupAdvisorImprovementRecalculationCommand(
            case_id=CASE_ID,
            proposal_id=uuid5(CASE_ID, "proposal:privacy"),
            target_area="positioning",
            private_recommendation=SecretStr(private_recommendation),
            private_rationale=SecretStr("Private rationale should stay hidden"),
            private_expected_effect=SecretStr("Private effect should stay hidden"),
        )
    )

    text = _docx_text(coordinator.uploaded_content)
    fragment = _fragment(text)
    extracted = DeterministicStartupProfileExtractor().extract(
        StartupProfileExtractionRequest(
            case_id=CASE_ID,
            data_revision=2,
            allowed_field_names=(StartupProfileFieldName.ASSUMPTIONS,),
            fragments=(fragment,),
            source_hashes=(fragment.artifact_hash,),
            egress_policy_version="test-egress@1",
            redaction_policy_version="test-redaction@1",
        )
    )
    field = extracted.fields[0]

    assert field.field_name is StartupProfileFieldName.ASSUMPTIONS
    assert field.status is StartupProfileFieldStatus.SOURCE_FACT
    assert field.normalized_values == (
        "Founder accepted a plan improvement for positioning.",
    )
    assert private_recommendation not in json.dumps(
        field.model_dump(mode="json"),
        ensure_ascii=False,
    )


def test_improvement_adapter_does_not_promote_prior_founder_assumptions_to_source_fact() -> None:
    manual_answer = (
        "Use finance forecast for July 2026: cash balance $250,000, monthly net "
        "burn $42,000, runway about 6 months."
    )
    previous_profile = _profile(
        CASE_ID,
        data_revision=2,
        source_field_values={
            StartupProfileFieldName.ONE_LINE_DESCRIPTION: ("AI logistics platform",),
            StartupProfileFieldName.PROBLEM: ("inventory errors",),
            StartupProfileFieldName.STAGE: ("Seed",),
        },
    )
    replacement_profile = _profile(
        CASE_ID,
        data_revision=3,
        source_field_values={
            StartupProfileFieldName.ONE_LINE_DESCRIPTION: ("AI logistics platform",),
            StartupProfileFieldName.PROBLEM: ("inventory errors",),
            StartupProfileFieldName.STAGE: ("Seed",),
            StartupProfileFieldName.ASSUMPTIONS: (
                "Founder accepted a plan improvement for positioning.",
            ),
        },
    )
    profile_repository = _ProfileRepository({CASE_ID: previous_profile})
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(
        str(CASE_ID),
        {
            "data_revision": 2,
            "fixture_mode": "live",
            "profile_id": str(previous_profile.profile_id),
            "profile_hash": previous_profile.profile_hash,
            "profile_revision": previous_profile.data_revision,
            "primary_profile_id": str(previous_profile.profile_id),
        },
    )
    coordinator = _ProfileReplacingUploadCoordinator(
        workflow_store,
        profile_repository=profile_repository,
        replacement_profile=replacement_profile,
    )
    adapter = StartupAdvisorCaseRecalculationAdapter(
        coordinator=coordinator,
        workflow_store=workflow_store,
        profile_repository=profile_repository,
    )

    result = adapter.apply_improvement(
        StartupAdvisorImprovementRecalculationCommand(
            case_id=CASE_ID,
            proposal_id=uuid5(CASE_ID, "proposal:privacy"),
            target_area="positioning",
            private_recommendation=SecretStr("Private pricing recommendation should stay hidden"),
            private_rationale=SecretStr("Private rationale should stay hidden"),
            private_expected_effect=SecretStr("Private effect should stay hidden"),
        )
    )

    assert result.status == "started"
    projected = profile_repository.get_current(CASE_ID)
    assumptions = projected.fields[StartupProfileFieldName.ASSUMPTIONS.value]
    assert assumptions.status is StartupProfileFieldStatus.SOURCE_FACT
    assert assumptions.values == ("Founder accepted a plan improvement for positioning.",)
    assert manual_answer not in assumptions.values
    assert projected.analysis_stage is StartupProfileAnalysisStage.PRIMARY
    assert projected.parent_profile_id is None
    runtime = workflow_store.load(str(CASE_ID))
    assert runtime["profile_revision"] == 3
    assert runtime["profile_id"] == str(projected.profile_id)


def test_skip_answer_does_not_request_recalculation_or_delta() -> None:
    harness = _harness(CASE_ID)
    recalculation = _RecalculationProbe(harness.workflow_store)
    service = harness.service(recalculation_port=recalculation)
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None

    skipped = service.submit_answer(
        str(CASE_ID),
        question_id=question.question_id,
        answer_type="skip",
    )

    assert skipped.status == "applied"
    assert skipped.confidence_delta == -1
    assert skipped.recalculation_status == "not_requested"
    assert skipped.recalculation_delta is None
    assert recalculation.calls == []
    runtime = harness.workflow_store.load(str(CASE_ID))
    assert runtime["data_revision"] == 1


def test_invalid_recalculation_result_is_not_reported_as_applied_deferred() -> None:
    harness = _harness(CASE_ID)
    service = harness.service(
        recalculation_port=_InvalidRecalculationPayloadProbe(harness.workflow_store)
    )
    question = service.get_next_question(str(CASE_ID)).next_question
    assert question is not None

    with pytest.raises(StartupGateConflict, match="advisor_recalculation_contract_invalid"):
        service.submit_answer(
            str(CASE_ID),
            question_id=question.question_id,
            answer_type="manual",
            value=HOSTILE_REVENUE_VALUE,
        )

    runtime = harness.workflow_store.load(str(CASE_ID))
    state = runtime.get(_STATE_KEY, {})
    assert state.get("answers") in (None, [])


def test_invalid_improvement_recalculation_result_is_not_reported_as_deferred() -> None:
    harness = _harness(CASE_ID)
    service = harness.service(
        recalculation_port=_InvalidRecalculationPayloadProbe(harness.workflow_store)
    )
    proposal = service.list_improvements(str(CASE_ID)).proposals[0]

    with pytest.raises(StartupGateConflict, match="advisor_recalculation_contract_invalid"):
        service.decide_improvement(
            str(CASE_ID),
            proposal_id=proposal.proposal_id,
            decision="accepted",
        )

    runtime = harness.workflow_store.load(str(CASE_ID))
    state = runtime.get(_STATE_KEY, {})
    assert state.get("decision_ledger") in (None, {})


def test_answer_rejects_stale_cross_case_and_unbound_file_question() -> None:
    harness = _harness(CASE_ID, OTHER_CASE_ID)
    service = harness.service()
    first = service.get_next_question(str(CASE_ID)).next_question
    other = service.get_next_question(str(OTHER_CASE_ID)).next_question
    assert first is not None
    assert other is not None

    service.submit_answer(
        str(CASE_ID),
        question_id=first.question_id,
        answer_type="skip",
    )
    with pytest.raises(StartupGateConflict, match="advisor_question_stale"):
        service.submit_answer(
            str(CASE_ID),
            question_id=first.question_id,
            answer_type="skip",
        )
    with pytest.raises(StartupGateConflict, match="advisor_question_cross_case"):
        service.submit_answer(
            str(CASE_ID),
            question_id=other.question_id,
            answer_type="skip",
        )

    current = service.get_next_question(str(CASE_ID)).next_question
    assert current is not None
    with pytest.raises(StartupGateConflict, match="advisor_document_not_in_case"):
        service.submit_answer(
            str(CASE_ID),
            question_id=current.question_id,
            answer_type="file",
            document_id="doc-other",
        )
    applied = service.submit_answer(
        str(CASE_ID),
        question_id=current.question_id,
        answer_type="file",
        document_id="doc-0001",
    )
    assert applied.status == "applied"
    persisted = json.dumps(harness.workflow_store.load(str(CASE_ID)), sort_keys=True)
    assert "doc-0001" in persisted
    assert "doc-other" not in persisted


def test_public_research_requires_consent_and_delegates_exactly_once() -> None:
    harness = _harness(CASE_ID)
    recalculation = _RecalculationProbe(harness.workflow_store)
    service = harness.service(recalculation_port=recalculation)
    first = service.get_next_question(str(CASE_ID)).next_question
    assert first is not None
    service.submit_answer(
        str(CASE_ID),
        question_id=first.question_id,
        answer_type="skip",
    )
    public_question = service.get_next_question(str(CASE_ID)).next_question
    assert public_question is not None
    assert "public_research" in public_question.answer_modes

    blocked = service.submit_answer(
        str(CASE_ID),
        question_id=public_question.question_id,
        answer_type="public_research",
        consent_public_research=False,
    )

    assert blocked.status == "blocked"
    assert blocked.total_count == service.get_next_question(str(CASE_ID)).total_count == 5
    assert blocked.research_result is not None
    assert blocked.research_result.status == "blocked"
    assert harness.research.calls == []
    assert recalculation.calls == []
    assert service.get_next_question(str(CASE_ID)).answered_count == 1
    blocked_state = json.dumps(harness.workflow_store.load(str(CASE_ID)), sort_keys=True)
    assert "blocked" in blocked_state
    assert "public customer segment" not in blocked_state

    completed = service.submit_answer(
        str(CASE_ID),
        question_id=public_question.question_id,
        answer_type="public_research",
        consent_public_research=True,
    )
    assert completed.status == "applied"
    assert completed.research_result is not None
    assert completed.research_result.status == "completed"
    assert completed.research_result.source_ids == (RESEARCH_SOURCE_ID,)
    assert len(harness.research.calls) == 1
    assert len(recalculation.calls) == 1
    assert recalculation.calls[0].answer_type == "public_research"
    assert completed.recalculation_status == "started"
    persisted = json.dumps(harness.workflow_store.load(str(CASE_ID)), sort_keys=True)
    assert "completed" in persisted
    assert "public customer segment" not in persisted


def test_deferred_durable_public_research_does_not_run_legacy_recalculation() -> None:
    harness = _harness(CASE_ID)
    harness.research.delta = AdvisorResearchDelta(
        status="deferred",
        summary_ru=(
            "Публичное исследование уже применено через durable Case Research job; "
            "legacy advisor recalculation не запускался."
        ),
        fail_reason_ru="case_research_job_mutated_case",
    )
    recalculation = _RecalculationProbe(harness.workflow_store)
    service = harness.service(recalculation_port=recalculation)
    first = service.get_next_question(str(CASE_ID)).next_question
    assert first is not None
    service.submit_answer(
        str(CASE_ID),
        question_id=first.question_id,
        answer_type="skip",
    )
    public_question = service.get_next_question(str(CASE_ID)).next_question
    assert public_question is not None

    response = service.submit_answer(
        str(CASE_ID),
        question_id=public_question.question_id,
        answer_type="public_research",
        consent_public_research=True,
    )

    assert response.status == "blocked"
    assert response.research_result is not None
    assert response.research_result.status == "deferred"
    assert response.research_result.fail_reason_ru == "case_research_job_mutated_case"
    assert len(harness.research.calls) == 1
    assert recalculation.calls == []
    assert service.get_next_question(str(CASE_ID)).answered_count == 1


def test_improvement_listing_is_stable_restart_safe_and_founder_safe() -> None:
    harness = _harness(CASE_ID)
    first = harness.service().list_improvements(str(CASE_ID))
    restarted = harness.service().list_improvements(str(CASE_ID))

    assert first == restarted
    assert first.improvement_version == 1
    assert len(first.proposals) == 6
    assert [proposal.target_area for proposal in first.proposals] == [
        "positioning",
        "monetization",
        "metrics",
        "gtm",
        "risk_reduction",
        "investor_readiness",
    ]
    serialized = first.model_dump_json()
    assert "MISSING" not in serialized
    assert "sha256:" not in serialized
    assert "snapshot_hash" not in serialized
    assert "C:\\" not in serialized
    assert "prompt" not in serialized.casefold()
    assert HOSTILE_VALUE not in serialized
    assert all(proposal.recommendation_ru for proposal in first.proposals)


def test_improvement_decisions_are_idempotent_versioned_and_restart_safe() -> None:
    harness = _harness(CASE_ID, OTHER_CASE_ID)
    service = harness.service()
    listed = service.list_improvements(str(CASE_ID))
    other = service.list_improvements(str(OTHER_CASE_ID))
    accepted_id = listed.proposals[0].proposal_id

    accepted = service.decide_improvement(
        str(CASE_ID),
        proposal_id=accepted_id,
        decision="accepted",
    )
    replayed = harness.service().decide_improvement(
        str(CASE_ID),
        proposal_id=accepted_id,
        decision="accepted",
    )

    assert accepted == replayed
    assert accepted.previous_version == 1
    assert accepted.new_version == 2
    assert accepted.changed_fields == ("positioning",)
    assert harness.service().list_improvements(str(CASE_ID)).improvement_version == 2
    with pytest.raises(StartupGateConflict, match="advisor_decision_conflict"):
        harness.service().decide_improvement(
            str(CASE_ID),
            proposal_id=accepted_id,
            decision="rejected",
        )
    with pytest.raises(StartupGateConflict, match="advisor_proposal_cross_case"):
        harness.service().decide_improvement(
            str(CASE_ID),
            proposal_id=other.proposals[0].proposal_id,
            decision="accepted",
        )
    with pytest.raises(StartupGateConflict, match="advisor_proposal_unknown"):
        harness.service().decide_improvement(
            str(CASE_ID),
            proposal_id=uuid5(NAMESPACE_URL, "unknown-advisor-proposal"),
            decision="accepted",
        )

    rejected_id = other.proposals[1].proposal_id
    rejected = service.decide_improvement(
        str(OTHER_CASE_ID),
        proposal_id=rejected_id,
        decision="rejected",
    )
    assert rejected.previous_version == rejected.new_version == 1
    assert rejected.changed_fields == ()


def test_accepted_improvement_triggers_same_case_recalculation_but_rejection_does_not() -> None:
    harness = _harness(CASE_ID, OTHER_CASE_ID)
    recalculation = _RecalculationProbe(harness.workflow_store)
    service = harness.service(recalculation_port=recalculation)
    accepted_proposal = service.list_improvements(str(CASE_ID)).proposals[0]

    accepted = service.decide_improvement(
        str(CASE_ID),
        proposal_id=accepted_proposal.proposal_id,
        decision="accepted",
    )

    assert len(recalculation.improvement_calls) == 1
    command = recalculation.improvement_calls[0]
    assert str(command.case_id) == str(CASE_ID)
    assert command.proposal_id == accepted_proposal.proposal_id
    assert command.target_area == accepted_proposal.target_area
    assert (
        command.private_recommendation.get_secret_value()
        == accepted_proposal.recommendation_ru
    )
    assert accepted_proposal.recommendation_ru not in repr(command)
    assert accepted_proposal.recommendation_ru not in command.model_dump_json()
    assert accepted.recalculation_status == "started"
    assert accepted.recalculation_data_revision == 2
    assert accepted.recalculation_analysis_status == "gate2_preview_ready"

    runtime = harness.workflow_store.load(str(CASE_ID))
    assert runtime["data_revision"] == 2
    assert runtime["active_analysis_thread_id"] == f"{CASE_ID}:r2"
    assert runtime["canonical_report_snapshot_id"] is None
    assert accepted_proposal.recommendation_ru not in json.dumps(
        runtime, ensure_ascii=False
    )

    rejected_proposal = service.list_improvements(str(OTHER_CASE_ID)).proposals[0]
    rejected = service.decide_improvement(
        str(OTHER_CASE_ID),
        proposal_id=rejected_proposal.proposal_id,
        decision="rejected",
    )
    assert rejected.recalculation_status == "not_requested"
    assert rejected.recalculation_data_revision is None
    assert len(recalculation.improvement_calls) == 1


def test_recalculation_adapter_surfaces_invalid_runtime_after_upload() -> None:
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(str(CASE_ID), {"data_revision": 1})
    coordinator = _InvalidRuntimeCoordinator(workflow_store)
    adapter = StartupAdvisorCaseRecalculationAdapter(
        coordinator=coordinator,
        workflow_store=workflow_store,
    )

    with pytest.raises(ValueError, match="data_revision"):
        adapter.apply_answer(
            StartupAdvisorRecalculationCommand(
                case_id=CASE_ID,
                question_id=f"{CASE_ID}:revenue_pricing",
                field_key="revenue_pricing",
                answer_type="public_research",
                private_value=SecretStr(HOSTILE_REVENUE_VALUE),
            )
        )


def test_recalculation_adapter_surfaces_invalid_runtime_after_reanalysis() -> None:
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(str(CASE_ID), {"data_revision": 1})
    coordinator = _InvalidRuntimeCoordinator(workflow_store)
    adapter = StartupAdvisorCaseRecalculationAdapter(
        coordinator=coordinator,
        workflow_store=workflow_store,
    )

    with pytest.raises(ValueError, match="data_revision"):
        adapter.apply_answer(
            StartupAdvisorRecalculationCommand(
                case_id=CASE_ID,
                question_id=f"{CASE_ID}:revenue_pricing",
                field_key="revenue_pricing",
                answer_type="file",
                document_id="doc-0001",
            )
        )


def test_decision_rejects_stale_report_lineage_without_exposing_hash() -> None:
    harness = _harness(THIRD_CASE_ID)
    listed = harness.service().list_improvements(str(THIRD_CASE_ID))
    proposal_id = listed.proposals[0].proposal_id
    revised_report = _report(THIRD_CASE_ID, hash_seed="revised")
    harness.reports.snapshots[revised_report.id] = revised_report
    harness.workflow_store.save(
        str(THIRD_CASE_ID),
        {
            "canonical_report_snapshot_id": str(revised_report.id),
            "canonical_report_snapshot_hash": revised_report.report_hash,
            "canonical_report_snapshot_revision": revised_report.data_revision,
        },
    )

    with pytest.raises(StartupGateConflict, match="advisor_proposal_stale") as exc_info:
        harness.service().decide_improvement(
            str(THIRD_CASE_ID),
            proposal_id=proposal_id,
            decision="accepted",
        )
    assert "sha256:" not in str(exc_info.value)


def test_missing_key_composition_keeps_live_adapter_unimported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "due_diligence_agent.adapters.openai.startup_web_research"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    temp_root = Path(".task4-composition-test")
    temp_root.mkdir(exist_ok=True)

    service = build_startup_advisor_api_service(
        data_dir=temp_root / "live",
        deterministic_data_dir=temp_root / "deterministic",
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        openai_settings=OpenAIStartupSettings(openai_api_key=None),
    )

    assert isinstance(service, StartupAdvisorApiService)
    assert module_name not in sys.modules


def test_advisor_api_composition_forwards_llm_call_recorder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    recorder_calls: list[dict[str, object | None]] = []
    captured: dict[str, object] = {}
    original_builder = bootstrap_container.build_openai_startup_advisor_research_service

    def recorder(**attributes: object | None) -> None:
        recorder_calls.append(attributes)

    def capture_builder(**kwargs: Any) -> object:
        captured.update(kwargs)
        return original_builder(**kwargs)

    monkeypatch.setattr(
        bootstrap_container,
        "build_openai_startup_advisor_research_service",
        capture_builder,
    )

    service = build_startup_advisor_api_service(
        data_dir=tmp_path / "live",
        deterministic_data_dir=tmp_path / "deterministic",
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        openai_settings=OpenAIStartupSettings(openai_api_key=None),
        llm_call_recorder=recorder,
    )

    assert isinstance(service, StartupAdvisorApiService)
    assert captured["llm_call_recorder"] is recorder
    assert recorder_calls == []


class _Harness:
    def __init__(self, case_ids: tuple[UUID, ...]) -> None:
        self.workflow_store = InMemoryStartupWorkflowRuntimeStore()
        self.intelligence_store = InMemoryStartupWorkflowRuntimeStore()
        cases = {_id: _case(_id) for _id in case_ids}
        profiles = {_id: _profile(_id) for _id in case_ids}
        reports = [_report(_id) for _id in case_ids]
        self.cases = _CaseRepository(cases)
        self.profiles = _ProfileRepository(profiles)
        self.reports = _ReportRepository({report.id: report for report in reports})
        self.research = _ResearchProbe()
        self.calculations = _CalculationRepository()
        self.contradictions = _ContradictionRepository()
        self.evidence = _EvidenceRepository()
        self.context = StartupAdvisorApiContext(
            case_repository=self.cases,
            profile_repository=self.profiles,
            report_repository=self.reports,
            calculation_repository=self.calculations,
            contradiction_repository=self.contradictions,
            gtm_repository=None,
            intelligence_store=self.intelligence_store,
            research_service=self.research,
        )
        object.__setattr__(self.context, "evidence_repository", self.evidence)
        for case_id in case_ids:
            report = _report(case_id)
            self.workflow_store.save(
                str(case_id),
                {
                    "case_exists": True,
                    "fixture_mode": "live",
                    "data_revision": 1,
                    "document_ids": ["doc-0001"],
                    "canonical_report_snapshot_id": str(report.id),
                    "canonical_report_snapshot_hash": report.report_hash,
                    "canonical_report_snapshot_revision": report.data_revision,
                },
            )

    def service(self, *, recalculation_port: Any | None = None) -> StartupAdvisorApiService:
        return StartupAdvisorApiService(
            workflow_store=self.workflow_store,
            live_context=self.context,
            deterministic_context=self.context,
            recalculation_port=recalculation_port,
        )


def _harness(*case_ids: UUID) -> _Harness:
    return _Harness(case_ids)


class _CaseRepository:
    def __init__(self, cases: dict[UUID, DueDiligenceCase]) -> None:
        self.cases = cases

    def get(self, case_id: UUID) -> DueDiligenceCase:
        try:
            return self.cases[case_id]
        except KeyError:
            raise KeyError(f"case_not_found:{case_id}") from None


class _ProfileRepository:
    def __init__(self, profiles: dict[UUID, StartupProfile]) -> None:
        self.profiles = dict(profiles)
        self.history = list(profiles.values())

    def get_current(self, case_id: UUID) -> StartupProfile:
        try:
            return self.profiles[case_id]
        except KeyError:
            raise KeyError(f"profile_not_found:{case_id}") from None

    def get_for_stage(
        self,
        case_id: UUID,
        data_revision: int,
        stage: StartupProfileAnalysisStage,
    ) -> StartupProfile:
        for profile in reversed(self.history):
            if (
                profile.case_id == case_id
                and profile.data_revision == data_revision
                and profile.analysis_stage is stage
            ):
                return profile
        raise KeyError(f"profile_not_found:{case_id}:{data_revision}:{stage.value}")

    def add(self, profile: StartupProfile) -> None:
        self.history.append(profile)
        self.profiles[profile.case_id] = profile


class _ReportRepository:
    def __init__(self, snapshots: dict[UUID, ReportSnapshot]) -> None:
        self.snapshots = snapshots

    def get_snapshot(self, snapshot_id: UUID) -> ReportSnapshot:
        try:
            return self.snapshots[snapshot_id]
        except KeyError:
            raise KeyError(f"report_not_found:{snapshot_id}") from None


class _EmptyListRepository:
    def list_for_case(self, case_id: UUID) -> list[Any]:
        return []


class _ContradictionRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, list[Contradiction]] = {}

    def list_for_case(self, case_id: UUID) -> list[Contradiction]:
        return list(self.items.get(case_id, []))

    def replace(self, contradiction: Contradiction) -> None:
        items = self.items.get(contradiction.case_id, [])
        for index, current in enumerate(items):
            if current.id == contradiction.id:
                items[index] = contradiction
                return
        raise KeyError(f"contradiction_not_found:{contradiction.id}")


class _EvidenceRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, list[EvidenceFact]] = {}
        self.case_ids_by_artifact: dict[UUID, UUID] = {}

    def add_for_case(self, case_id: UUID, fact: EvidenceFact) -> None:
        self.case_ids_by_artifact[fact.artifact_id] = case_id
        self.items.setdefault(case_id, []).append(fact)

    def add(self, fact: EvidenceFact) -> None:
        case_id = self.case_ids_by_artifact[fact.artifact_id]
        if any(current.id == fact.id for current in self.items.get(case_id, [])):
            raise ValueError("evidence_fact_already_exists")
        self.items.setdefault(case_id, []).append(fact)

    def list_for_case(self, case_id: UUID) -> list[EvidenceFact]:
        return list(self.items.get(case_id, []))


class _CalculationRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, list[Calculation]] = {}

    def list_for_case(self, case_id: UUID) -> list[Calculation]:
        return list(self.items.get(case_id, []))


class _ResearchProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.delta = AdvisorResearchDelta(
            status="completed",
            summary_ru="Публичное исследование завершено.",
            source_ids=(RESEARCH_SOURCE_ID,),
        )

    def research(self, case_id: UUID, question: object, answer: object) -> AdvisorResearchDelta:
        self.calls.append({"case_id": case_id, "question": question, "answer": answer})
        return self.delta


class _RecalculationProbe:
    def __init__(self, workflow_store: InMemoryStartupWorkflowRuntimeStore) -> None:
        self.workflow_store = workflow_store
        self.calls: list[Any] = []
        self.improvement_calls: list[Any] = []

    def apply_answer(self, command: Any) -> dict[str, object]:
        self.calls.append(command)
        case_id = str(command.case_id)
        self.workflow_store.update(
            case_id,
            lambda _runtime: {
                "data_revision": 2,
                "active_analysis_thread_id": f"{case_id}:r2",
                "analysis_status": "gate2_preview_ready",
                "gate2_status": "required",
                "gate3_status": "not_ready",
                "gate4_status": "not_ready",
                "report_status": "not_ready",
                "canonical_report_snapshot_id": None,
                "canonical_report_snapshot_hash": None,
                "canonical_report_snapshot_revision": None,
            },
        )
        return {
            "status": "started",
            "data_revision": 2,
            "analysis_status": "gate2_preview_ready",
            "safe_error_code": None,
        }

    def apply_improvement(self, command: Any) -> dict[str, object]:
        self.improvement_calls.append(command)
        case_id = str(command.case_id)
        self.workflow_store.update(
            case_id,
            lambda _runtime: {
                "data_revision": 2,
                "active_analysis_thread_id": f"{case_id}:r2",
                "analysis_status": "gate2_preview_ready",
                "gate2_status": "required",
                "gate3_status": "not_ready",
                "gate4_status": "not_ready",
                "report_status": "not_ready",
                "canonical_report_snapshot_id": None,
                "canonical_report_snapshot_hash": None,
                "canonical_report_snapshot_revision": None,
            },
        )
        return {
            "status": "started",
            "data_revision": 2,
            "analysis_status": "gate2_preview_ready",
            "safe_error_code": None,
        }


class _ProfileAndContradictionMutatingRecalculationProbe(_RecalculationProbe):
    def __init__(
        self,
        harness: _Harness,
        *,
        source_field_values: dict[StartupProfileFieldName, tuple[str, ...]],
        remaining_contradictions: list[Contradiction],
        replace_source_fields: bool = False,
    ) -> None:
        super().__init__(harness.workflow_store)
        self._harness = harness
        self._source_field_values = source_field_values
        self._remaining_contradictions = remaining_contradictions
        self._replace_source_fields = replace_source_fields

    def apply_answer(self, command: Any) -> dict[str, object]:
        result = super().apply_answer(command)
        case_id = command.case_id
        current = self._harness.profiles.get_current(case_id)
        merged_values = (
            {}
            if self._replace_source_fields
            else {
                StartupProfileFieldName(field_name): field.values
                for field_name, field in current.fields.items()
                if field.status is StartupProfileFieldStatus.SOURCE_FACT
            }
        )
        merged_values.update(self._source_field_values)
        self._harness.profiles.profiles[case_id] = _profile(
            case_id,
            source_field_values=merged_values,
            data_revision=2,
        )
        self._harness.contradictions.items[case_id] = list(self._remaining_contradictions)
        return result


class _FounderClarificationRecalculationProbe(_RecalculationProbe):
    def __init__(
        self,
        harness: _Harness,
        *,
        clarification: EvidenceFact,
        related_fact_ids: tuple[UUID, ...],
    ) -> None:
        super().__init__(harness.workflow_store)
        self._harness = harness
        self._clarification = clarification
        self._related_fact_ids = related_fact_ids

    def apply_answer(self, command: Any) -> dict[str, object]:
        result = super().apply_answer(command)
        case_id = command.case_id
        current = self._harness.profiles.get_current(case_id)
        existing_values = current.fields[
            StartupProfileFieldName.PRICING_REVENUE_MODEL
        ].values
        self._harness.profiles.profiles[case_id] = _profile(
            case_id,
            source_field_values={
                StartupProfileFieldName.PRICING_REVENUE_MODEL: (
                    command.private_value.get_secret_value(),
                    *existing_values,
                )
            },
            data_revision=2,
        )
        self._harness.evidence.add_for_case(case_id, self._clarification)
        self._harness.contradictions.items.setdefault(case_id, []).append(
            _contradiction(
                case_id,
                conflict_type="source_fact_value_conflict",
                explanation=(
                    "Conflicting normalized numeric values were extracted from "
                    "different source artifacts."
                ),
                fact_ids=self._related_fact_ids,
            )
        )
        return result


class _CalculationMutatingRecalculationProbe(_RecalculationProbe):
    def __init__(
        self,
        harness: _Harness,
        *,
        calculations: list[Calculation],
    ) -> None:
        super().__init__(harness.workflow_store)
        self._harness = harness
        self._calculations = calculations

    def apply_answer(self, command: Any) -> dict[str, object]:
        result = super().apply_answer(command)
        self._harness.calculations.items[command.case_id] = list(self._calculations)
        return result


class _InvalidRecalculationPayloadProbe:
    def __init__(self, workflow_store: InMemoryStartupWorkflowRuntimeStore) -> None:
        self.workflow_store = workflow_store

    def apply_answer(self, command: Any) -> dict[str, object]:
        del command
        return {"status": "started", "data_revision": 0, "analysis_status": "unknown"}

    def apply_improvement(self, command: Any) -> dict[str, object]:
        del command
        return {"status": "started", "data_revision": 0, "analysis_status": "unknown"}


class _InvalidRuntimeCoordinator:
    def __init__(self, workflow_store: InMemoryStartupWorkflowRuntimeStore) -> None:
        self._workflow_store = workflow_store

    def upload_documents(self, case_id: str, **_kwargs: object) -> None:
        self._save_invalid_runtime(case_id)

    def reanalyze_existing_documents(self, case_id: str, **_kwargs: object) -> None:
        self._save_invalid_runtime(case_id)

    def _save_invalid_runtime(self, case_id: str) -> None:
        self._workflow_store.update(
            case_id,
            lambda _runtime: {
                "data_revision": "invalid",
                "analysis_status": "gate2_preview_ready",
            },
        )


class _CaptureUploadCoordinator:
    def __init__(self, workflow_store: InMemoryStartupWorkflowRuntimeStore) -> None:
        self._workflow_store = workflow_store
        self.uploaded_content: bytes = b""
        self.upload_calls: list[dict[str, object]] = []

    def upload_documents(
        self,
        case_id: str,
        *,
        files: list[dict[str, object]],
        **_kwargs: object,
    ) -> None:
        self.upload_calls.append({"case_id": case_id, "files": files, **_kwargs})
        content = files[0].get("content")
        assert isinstance(content, bytes)
        self.uploaded_content = content
        self._workflow_store.update(
            case_id,
            lambda _runtime: {
                "data_revision": 2,
                "analysis_status": "gate2_preview_ready",
            },
        )


class _ProfileReplacingUploadCoordinator(_CaptureUploadCoordinator):
    def __init__(
        self,
        workflow_store: InMemoryStartupWorkflowRuntimeStore,
        *,
        profile_repository: _ProfileRepository,
        replacement_profile: StartupProfile,
    ) -> None:
        super().__init__(workflow_store)
        self._profile_repository = profile_repository
        self._replacement_profile = replacement_profile

    def upload_documents(
        self,
        case_id: str,
        *,
        files: list[dict[str, object]],
        **kwargs: object,
    ) -> None:
        self.upload_calls.append({"case_id": case_id, "files": files, **kwargs})
        content = files[0].get("content")
        assert isinstance(content, bytes)
        self.uploaded_content = content
        self._profile_repository.add(self._replacement_profile)
        self._workflow_store.update(
            case_id,
            lambda runtime: {
                **runtime,
                "data_revision": self._replacement_profile.data_revision,
                "analysis_status": "gate2_preview_ready",
                "profile_id": str(self._replacement_profile.profile_id),
                "profile_hash": self._replacement_profile.profile_hash,
                "profile_revision": self._replacement_profile.data_revision,
                "primary_profile_id": str(self._replacement_profile.profile_id),
            },
        )


class _FounderStatementIntakeProbe(CaseFactIntakeService):
    def __init__(self, *, old_revision: int = 1, new_revision: int = 2) -> None:
        self.commands: list[SaveFounderStatementCommand] = []
        self.old_revision = old_revision
        self.new_revision = new_revision

    def save_founder_statement(self, command: SaveFounderStatementCommand) -> CaseMutationDelta:
        self.commands.append(command)
        return CaseMutationDelta(
            accepted=True,
            old_revision=self.old_revision,
            new_revision=self.new_revision,
            changed_keys=(command.requirement_key,),
            stale_scenario_ids=(uuid5(command.case_id, f"scenario:{command.requirement_key}"),),
            stale_report_ids=(uuid5(command.case_id, f"report:{command.requirement_key}"),),
            metric_before={command.requirement_key: "missing"},
            metric_after={command.requirement_key: "founder_statement"},
            readiness_before={"answered": 0},
            readiness_after={"answered": 1},
            next_question=None,
            validation_errors=(),
            original_draft=command.value,
        )


def _case(case_id: UUID) -> DueDiligenceCase:
    return DueDiligenceCase(
        case_id=case_id,
        mode=AnalysisMode.STARTUP,
        entity_name="FounderCo",
        entity_identifier=str(case_id),
        jurisdiction="KZ",
        scope=("startup",),
        as_of=AS_OF,
        base_currency="KZT",
        privacy_policy="startup-local@1",
        budget_policy="offline",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
        updated_at=AS_OF,
        workflow_version="startup-graph@1",
        data_revision=1,
    )


def _profile(
    case_id: UUID,
    *,
    source_field_values: dict[StartupProfileFieldName, tuple[str, ...]] | None = None,
    data_revision: int = 1,
) -> StartupProfile:
    if source_field_values is None:
        source_field_values = {
            StartupProfileFieldName.ONE_LINE_DESCRIPTION: ("AI logistics platform",),
            StartupProfileFieldName.PROBLEM: ("inventory errors",),
            StartupProfileFieldName.STAGE: ("Seed",),
        }
    fields = {
        name.value: (
            StartupProfileField(
                name=name,
                status=StartupProfileFieldStatus.SOURCE_FACT,
                values=source_field_values[name],
                confidence=Decimal("0.87"),
                evidence_refs=(
                    StartupProfileEvidenceRef(
                        evidence_id=uuid5(case_id, f"evidence:{name.value}"),
                        artifact_id=uuid5(case_id, "artifact:profile"),
                        artifact_hash="sha256:" + "a" * 64,
                        locator_hash="sha256:" + "b" * 64,
                        field_name=name,
                        confidence=Decimal("0.87"),
                    ),
                ),
            )
            if name in source_field_values
            else StartupProfileField(
                name=name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                confidence=Decimal(0),
                reason_code=f"{name.value}_missing",
            )
        )
        for name in StartupProfileFieldName
    }
    return StartupProfile.build(
        case_id=case_id,
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="deterministic-profile@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=data_revision,
        source_hashes={"pitch-deck": "sha256:" + "a" * 64},
        parse_outcomes={"pitch-deck": "parsed"},
        fields=fields,
        gap_codes=("startup_missing",),
        case_revision_at=AS_OF,
    )


def _report(case_id: UUID, *, hash_seed: str = "base") -> ReportSnapshot:
    report_hash = "sha256:" + uuid5(case_id, hash_seed).hex * 2
    return ReportSnapshot(
        id=uuid5(case_id, f"report:{hash_seed}"),
        case_id=case_id,
        report_hash=report_hash,
        case_snapshot_hash="sha256:" + "b" * 64,
        source_hashes={},
        as_of=AS_OF,
        graph_version="startup@1",
        prompt_versions={"report": "startup-report@1"},
        formula_versions={},
        model_versions={"analysis": "offline"},
        sections={"summary": {"status": "MISSING", "raw": HOSTILE_VALUE}},
        data_revision=1,
        json_artifact_ref="C:\\private\\report.json",
        content_hashes={"json": "sha256:" + "c" * 64},
        reproducibility=ReproducibilityManifest(
            code_commit="test",
            build_id="test",
            dependency_lock_hash="sha256:" + "d" * 64,
            python_version="3.13",
            package_versions={},
            provider_model_id="offline",
            model_alias_snapshot="offline",
            reasoning_parameters={"prompt": HOSTILE_VALUE},
            adapter_versions={},
            parser_versions={},
            redaction_policy_version="test",
            locale="ru-KZ",
            timezone="UTC",
            deterministic_seeds={},
            configuration_hash="sha256:" + "e" * 64,
        ),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
        version=99,
    )


def _contradiction(
    case_id: UUID,
    *,
    conflict_type: str,
    explanation: str,
    fact_ids: tuple[UUID, ...] = (),
) -> Contradiction:
    return Contradiction(
        id=uuid5(case_id, f"contradiction:{conflict_type}:{explanation}"),
        case_id=case_id,
        conflict_type=conflict_type,
        fact_ids=fact_ids,
        explanation=explanation,
        severity=FindingSeverity.HIGH,
        status=ContradictionStatus.OPEN,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        detected_at=AS_OF,
    )


def _mrr_fact(case_id: UUID, *, key: str, value: str) -> EvidenceFact:
    artifact_id = uuid5(case_id, f"mrr-artifact:{key}")
    return EvidenceFact(
        id=uuid5(case_id, f"mrr-fact:{key}:{value}"),
        artifact_id=artifact_id,
        name="monthly_recurring_revenue",
        value=Decimal(value),
        value_type="decimal",
        unit="KZT",
        period="2026-06",
        locator=SourceLocator(
            kind="cell",
            value=f"mrr:{key}",
            artifact_id=artifact_id,
            table="metrics",
            cell="B2",
        ),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.70"),
        source_priority=40,
        extraction_method="fixture",
    )


def _calculation(
    case_id: UUID,
    *,
    metric_name: str,
    value: Decimal,
    formula_version: str = "startup-metric@1",
    unit: str = "months",
    period: str = "2026-07",
) -> Calculation:
    return Calculation(
        id=uuid5(case_id, f"calculation:{metric_name}:{value}:{unit}:{period}"),
        case_id=case_id,
        metric_name=metric_name,
        formula_version=formula_version,
        input_fact_ids=(uuid5(case_id, f"fact:{metric_name}:input"),),
        value=value,
        unit=unit,
        period=period,
        warnings=(),
        calculated_at=AS_OF,
        sensitivity=SensitivityClass.CONFIDENTIAL,
    )


def _docx_text(content: bytes) -> str:
    from io import BytesIO

    from docx import Document

    document = Document(BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _fragment(text: str) -> StartupProfileBoundedFragment:
    return StartupProfileBoundedFragment(
        fragment_id=uuid5(CASE_ID, f"fragment:{text}"),
        artifact_id=uuid5(CASE_ID, "artifact:adapter-docx"),
        text=text,
        text_hash="sha256:" + sha256(text.encode("utf-8")).hexdigest(),
        artifact_hash="sha256:" + "d" * 64,
        locator_hash="sha256:" + "e" * 64,
        page=1,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        redacted=True,
        minimized=True,
        redaction_policy_version="test-redaction@1",
    )
