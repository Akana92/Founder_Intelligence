from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from due_diligence_agent.adapters.startup.deterministic_profile_extractor import (
    DeterministicStartupProfileExtractor,
)
from due_diligence_agent.adapters.startup.profile_fragment_inventory import (
    _bounded_fragment_text,
    _selected_fragment_indices,
)
from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.application.services.startup_profile_service import StartupProfileService
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    ArtifactParsingStatus,
    CaseStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.documents.tabular import SpreadsheetParseResult
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.ports.startup_profile_extraction import (
    StartupProfileBoundedFragment,
    StartupProfileExtractedField,
    StartupProfileExtractionPort,
    StartupProfileExtractionRequest,
    StartupProfileExtractionResponse,
    StartupProfileExtractorInvalidOutputError,
    StartupProfileSafeRef,
)

CASE_ID = UUID("11111111-1111-4111-8111-111111111111")
PRIMARY_PROFILE_ID = UUID("22222222-2222-4222-8222-222222222222")
ARTIFACT_ID = UUID("33333333-3333-4333-8333-333333333333")
METRIC_FACT_ID = UUID("55555555-5555-4555-8555-555555555555")
OTHER_CASE_ID = UUID("44444444-4444-4444-8444-444444444444")
OTHER_ARTIFACT_ID = UUID("66666666-6666-4666-8666-666666666666")
DEFAULT_FRAGMENT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_build_primary_uses_redacted_text_fragments_for_normal_profile_fields() -> None:
    profile_repo = CapturingProfileRepository()
    service = StartupProfileService(
        case_repository=Repository([_case()]),
        artifact_repository=Repository([_artifact()]),
        parsed_artifact_repository=Repository([_spreadsheet_parse_result()]),
        evidence_repository=Repository([_metric_fact()]),
        startup_claim_repository=Repository([]),
        contradiction_repository=Repository([]),
        startup_profile_repository=profile_repo,
        deterministic_extractor=DeterministicStartupProfileExtractor(),
        external_extractor=None,
        fragment_inventory=FragmentInventory(
            (
                _fragment(
                    text=(
                        "Startup Name: LedgerPilot\n"
                        "Problem: finance teams reconcile reporting manually.\n"
                        "Solution: automated close workflows\n"
                        "ICP: seed-stage B2B SaaS CFOs"
                    ),
                ),
            )
        ),
    )

    profile = service.build_primary(CASE_ID)

    assert isinstance(profile, StartupProfile)
    assert profile_repo.added == [profile]
    assert profile.analysis_stage is StartupProfileAnalysisStage.PRIMARY
    assert profile.data_revision == 2
    assert profile.built_at == datetime(2026, 8, 13, 10, tzinfo=UTC)
    assert profile.fields[StartupProfileFieldName.STARTUP_NAME.value].values == ("LedgerPilot",)
    assert profile.fields[StartupProfileFieldName.PROBLEM.value].values == (
        "finance teams reconcile reporting manually.",
    )
    assert profile.fields[StartupProfileFieldName.SOLUTION.value].values == (
        "automated close workflows",
    )
    assert profile.fields[StartupProfileFieldName.ICP.value].values == ("seed-stage B2B SaaS CFOs",)


def test_build_primary_creates_valid_spreadsheet_only_profile_and_persists_it() -> None:
    profile_repo = CapturingProfileRepository()
    service = _service(profile_repo=profile_repo)

    profile = service.build_primary(CASE_ID)

    traction = profile.fields[StartupProfileFieldName.TRACTION.value]
    assert traction.status is StartupProfileFieldStatus.SOURCE_FACT
    assert traction.values == ("ARR: 120000 USD 2026",)
    assert traction.evidence_refs[0].artifact_id == ARTIFACT_ID
    assert profile.fields[StartupProfileFieldName.PROBLEM.value].status is (
        StartupProfileFieldStatus.INSUFFICIENT_DATA
    )


def test_build_primary_is_sparse_multilingual_and_order_independent() -> None:
    fragments_a = (
        _fragment(fragment_id=UUID("77777777-7777-4777-8777-777777777777"), text="Solution: Автоматизация закрытия месяца"),
        _fragment(fragment_id=UUID("88888888-8888-4888-8888-888888888888"), text="Problem: ручная сверка отчетов"),
    )
    fragments_b = tuple(reversed(fragments_a))
    service_a = _service(profile_repo=CapturingProfileRepository(), fragments=fragments_a)
    service_b = _service(profile_repo=CapturingProfileRepository(), fragments=fragments_b)

    profile_a = service_a.build_primary(CASE_ID)
    profile_b = service_b.build_primary(CASE_ID)

    assert profile_a.profile_id == profile_b.profile_id
    assert profile_a.profile_hash == profile_b.profile_hash
    assert profile_a.fields[StartupProfileFieldName.PROBLEM.value].values == ("ручная сверка отчетов",)
    assert profile_a.fields[StartupProfileFieldName.SOLUTION.value].values == (
        "Автоматизация закрытия месяца",
    )
    assert profile_a.fields[StartupProfileFieldName.STARTUP_NAME.value].status is (
        StartupProfileFieldStatus.INSUFFICIENT_DATA
    )


def test_build_primary_preserves_fragment_inventory_order_for_extraction() -> None:
    extractor = RecordingFragmentOrderExtractor()
    fragments = (
        _fragment(
            fragment_id=UUID("88888888-8888-4888-8888-888888888888"),
            text="Problem: first relevant block",
        ),
        _fragment(
            fragment_id=UUID("77777777-7777-4777-8777-777777777777"),
            text="Solution: second relevant block",
        ),
    )
    service = _service(
        profile_repo=CapturingProfileRepository(),
        deterministic_extractor=extractor,
        fragments=fragments,
    )

    service.build_primary(CASE_ID)

    assert [fragment.fragment_id for fragment in extractor.requests[0].fragments] == [
        UUID("88888888-8888-4888-8888-888888888888"),
        UUID("77777777-7777-4777-8777-777777777777"),
    ]


def test_fragment_inventory_returns_later_high_relevance_before_coverage_fragments() -> None:
    source_fragments = [
        _fragment(
            fragment_id=UUID(f"10000000-0000-4000-8000-{index:012d}"),
            text="Administrative footer without founder profile signal.",
        )
        for index in range(8)
    ]
    source_fragments[0] = _fragment(
        fragment_id=UUID("10000000-0000-4000-8000-000000000000"),
        text="Problem: vague manual planning.",
    )
    source_fragments[6] = _fragment(
        fragment_id=UUID("10000000-0000-4000-8000-000000000006"),
        text=(
            "Problem: Клиенты FMCG теряют деньги из-за ручной маршрутизации закупок.\n"
            "Стадия Seed. География Казахстан. Growth 590000 ₸. Net burn 22.4."
        ),
    )

    selected = _selected_fragment_indices(source_fragments, limit=5)

    assert selected[0] == 6
    assert 0 in selected


def test_fragment_inventory_reserves_diverse_profile_semantic_categories() -> None:
    source_fragments = [
        _fragment(
            fragment_id=UUID(f"30000000-0000-4000-8000-{index:012d}"),
            text=f"CONTRADICTION duplicate metric row {index} value {index + 10}",
        )
        for index in range(32)
    ]
    category_rows = {
        22: "Product platform module for university admissions workflow.",
        23: "Customer segments: universities, students, parents, and education agents.",
        24: "Pricing tariffs: Starter 240000 KZT/month and Growth 690000 KZT/month.",
        25: "Market formulas: TAM SAM SOM model and rating fit methodology.",
        26: "Funding roadmap gate: 35.2M KZT platform round funds the next gate.",
        27: "Legal privacy consent for personal data is required before launch.",
        28: "Forecasts: revenue and EBITDA forecast for 2027-2031.",
    }
    for index, text in category_rows.items():
        source_fragments[index] = _fragment(
            fragment_id=UUID(f"30000000-0000-4000-8000-{index:012d}"),
            text=text,
        )

    selected = _selected_fragment_indices(source_fragments, limit=12)
    selected_text = "\n".join(source_fragments[index].text for index in selected)

    for expected in category_rows.values():
        assert expected in selected_text
    assert len(selected) == 12


def test_fragment_inventory_reserves_problem_pain_before_high_score_noise_crowds_it_out() -> None:
    source_fragments = [
        _fragment(
            fragment_id=UUID(f"31000000-0000-4000-8000-{index:012d}"),
            text=f"CONTRADICTION duplicated forecast privacy no-go gate row {index} value {index + 10}",
        )
        for index in range(36)
    ]
    category_rows = {
        23: "Product platform module for university admissions workflow.",
        24: "Customer segments: universities, students, parents, and education agents.",
        25: "Pricing tariffs: Starter 240000 KZT/month and Growth 690000 KZT/month.",
        26: "Market formulas: TAM SAM SOM model and rating fit methodology.",
        27: "Funding roadmap gate: 35.2M KZT platform round funds the next gate.",
        28: "Legal privacy consent for personal data is required before launch.",
        29: "Forecasts: revenue and EBITDA forecast for 2027-2031.",
        30: "Pain: admissions teams lose paid leads because requests are processed manually.",
    }
    for index, text in category_rows.items():
        source_fragments[index] = _fragment(
            fragment_id=UUID(f"31000000-0000-4000-8000-{index:012d}"),
            text=text,
        )

    selected = _selected_fragment_indices(source_fragments, limit=12)
    selected_text = "\n".join(source_fragments[index].text for index in selected)

    assert category_rows[30] in selected_text


def test_fragment_inventory_keeps_real_smart_university_product_and_segment_table() -> None:
    cover_product = "Платформа поступления, независимый рейтинг подготовки"
    finance_table = (
        "Параметр Значение Параметр Значение\n"
        "Дата 25 августа 2026 Стадия Рабочий продукт / pre-scale\n"
        "Раунд 35,2 млн ₸ Плановый 2029 год, базовый сценарий\n"
        "платформы break-even\n"
        "География Казахстан; жильё — Алматы Формат Для обсуждения с партнёром/инвестором"
    )
    segment_header = "Сегмент Job-to-be-done Платёж Первый продукт"
    segment_table = (
        f"{segment_header}\n"
        "Абитуриент/родитель Выбрать вуз, грант, курс и план подготовки "
        "Freemium; в первой фазе не основной плательщик Навигатор, сравнение, советник, рейтинг\n"
        "ЕНТ-центр/частная школа Получить квалифицированный спрос и доказать результат "
        "300 тыс.–3,0 млн ₸/год + accepted lead Verified/Growth/Pro/Multi-branch\n"
        "Вуз Привлечь подходящих абитуриентов и объяснить программу "
        "2–4 млн ₸/год по мере зрелости Профиль, data feed, аналитика"
    )
    source_fragments = [
        _fragment(
            fragment_id=UUID(f"32000000-0000-4000-8000-{index:012d}"),
            text=f"CONTRADICTION forecast privacy no-go funding gate row {index} value {index + 10}",
        )
        for index in range(36)
    ]
    source_fragments[0] = _fragment(
        fragment_id=UUID("32000000-0000-4000-8000-000000000000"),
        text="SMART UNIVERSITY",
    )
    source_fragments[3] = _fragment(
        fragment_id=UUID("32000000-0000-4000-8000-000000000003"),
        text=cover_product,
    )
    source_fragments[11] = _fragment(
        fragment_id=UUID("32000000-0000-4000-8000-000000000011"),
        text=finance_table,
    )
    source_fragments[14] = _fragment(
        fragment_id=UUID("32000000-0000-4000-8000-000000000014"),
        text=segment_header,
    )
    source_fragments[29] = _fragment(
        fragment_id=UUID("32000000-0000-4000-8000-000000000029"),
        text=(
            "Платформу стоит финансировать как staged commercial validation на 35,2 млн ₸. "
            "Рейтинг — trust-layer. Housing Management — отдельная опция после ворот. "
            "Рыночная ипотечная покупка квартир — no-go."
        ),
    )
    source_fragments[30] = _fragment(
        fragment_id=UUID("32000000-0000-4000-8000-000000000030"),
        text=(
            "Рейтинг и реклама: privacy consent, funding roadmap, forecast 2027-2031, "
            "go/no-go gate and legal review."
        ),
    )
    source_fragments[31] = _fragment(
        fragment_id=UUID("32000000-0000-4000-8000-000000000031"),
        text=segment_table,
    )

    selected = _selected_fragment_indices(source_fragments, limit=12)
    selected_text = tuple(source_fragments[index].text for index in selected)

    assert cover_product in selected_text
    assert segment_table in selected_text
    assert segment_header not in selected_text
    assert source_fragments[29].text not in selected_text


def test_bounded_fragment_text_reserves_late_semantic_categories() -> None:
    early_high_relevance_lines = [
        (
            f"CONTRADICTION duplicate metric row {index}: revenue value {index + 10} "
            "requires founder clarification before it can be used."
        )
        for index in range(12)
    ]
    late_semantic_lines = (
        "Product platform modules support university admissions workflows.",
        "Customer segments include universities, students, parents, and education agents.",
        "Market formulas define TAM, SAM, and SOM without claiming private traction.",
        "Rating methodology combines program fit and verified eligibility inputs.",
        "Roadmap gate separates the 35.2M KZT platform round from later decisions.",
        "Legal privacy consent is required before personal data processing.",
        "Housing Management remains a no-go until fire-safety and landlord gates pass.",
        "Revenue and EBITDA for 2027-2031 remain forecasts, not actual results.",
    )

    excerpt = _bounded_fragment_text(
        "\n".join([*early_high_relevance_lines, *late_semantic_lines]),
        max_chars=800,
    )
    normalized = excerpt.casefold()

    assert len(excerpt) <= 800
    for marker in (
        "platform",
        "universit",
        "tam",
        "rating",
        "roadmap",
        "privacy",
        "no-go",
        "2027",
    ):
        assert marker in normalized


def test_build_primary_uses_relevance_order_so_later_stronger_same_field_wins() -> None:
    source_fragments = [
        _fragment(
            fragment_id=UUID(f"20000000-0000-4000-8000-{index:012d}"),
            text="Administrative footer without founder profile signal.",
        )
        for index in range(8)
    ]
    source_fragments[0] = _fragment(
        fragment_id=UUID("20000000-0000-4000-8000-000000000000"),
        text="Problem: vague manual planning.",
    )
    source_fragments[6] = _fragment(
        fragment_id=UUID("20000000-0000-4000-8000-000000000006"),
        text=(
            "Problem: Клиенты FMCG теряют деньги из-за ручной маршрутизации закупок.\n"
            "Стадия Seed. География Казахстан. Growth 590000 ₸. Net burn 22.4."
        ),
    )
    selected_fragments = tuple(
        source_fragments[index]
        for index in _selected_fragment_indices(source_fragments, limit=5)
    )

    profile = _service(
        profile_repo=CapturingProfileRepository(),
        fragments=selected_fragments,
    ).build_primary(CASE_ID)

    assert profile.fields[StartupProfileFieldName.PROBLEM.value].values == (
        "Клиенты FMCG теряют деньги из-за ручной маршрутизации закупок.",
    )


def test_build_primary_ignores_navigation_control_labeled_solution_for_semantic_product_text() -> None:
    profile = _service(
        profile_repo=CapturingProfileRepository(),
        fragments=(
            _fragment(
                fragment_id=UUID("21000000-0000-4000-8000-000000000000"),
                text="Solution: go / pause Next action",
            ),
            _fragment(
                fragment_id=UUID("21000000-0000-4000-8000-000000000001"),
                text="Project develops a platform module for university admissions and housing workflow.",
            ),
        ),
    ).build_primary(CASE_ID)

    solution = profile.fields[StartupProfileFieldName.SOLUTION.value]
    assert solution.status is StartupProfileFieldStatus.SOURCE_FACT
    assert solution.values == (
        "Project develops a platform module for university admissions and housing workflow.",
    )


def test_build_primary_ignores_russian_control_table_rows_for_smart_university_semantics() -> None:
    profile = _service(
        profile_repo=CapturingProfileRepository(),
        fragments=(
            _fragment(
                fragment_id=UUID("22000000-0000-4000-8000-000000000000"),
                text=(
                    "Решение Go No-go / pause Следующее действие\n"
                    "Сегмент Job-to-be-done Платёж Первый продукт"
                ),
            ),
            _fragment(
                fragment_id=UUID("22000000-0000-4000-8000-000000000001"),
                text=(
                    "Smart University — платформа для автоматизации поступления в университеты, "
                    "рейтинга программ и управления заявками.\n"
                    "Клиенты: университеты, абитуриенты, родители и образовательные агенты."
                ),
            ),
        ),
    ).build_primary(CASE_ID)

    solution_values = profile.fields[StartupProfileFieldName.SOLUTION.value].values
    icp_values = profile.fields[StartupProfileFieldName.ICP.value].values

    joined_values = " ".join((*solution_values, *icp_values)).casefold()
    assert "go no-go" not in joined_values
    assert "job-to-be-done" not in joined_values
    assert "платёж первый продукт" not in joined_values
    assert any("платформа" in value.casefold() for value in solution_values)
    assert any("университет" in value.casefold() for value in icp_values)


def test_changed_source_or_revision_changes_primary_identity() -> None:
    profile_v2 = _service(
        profile_repo=CapturingProfileRepository(),
        fragments=(_fragment(text="Problem: manual close"),),
    ).build_primary(CASE_ID)
    changed_case = _case(data_revision=3, updated_at=datetime(2026, 8, 13, 11, tzinfo=UTC))
    changed_artifact = _artifact(source_snapshot_hash="c" * 64)
    changed = StartupProfileService(
        case_repository=Repository([changed_case]),
        artifact_repository=Repository([changed_artifact]),
        parsed_artifact_repository=Repository([_spreadsheet_parse_result()]),
        evidence_repository=Repository([_metric_fact()]),
        startup_claim_repository=Repository([]),
        contradiction_repository=Repository([]),
        startup_profile_repository=CapturingProfileRepository(),
        deterministic_extractor=DeterministicStartupProfileExtractor(),
        external_extractor=None,
        fragment_inventory=FragmentInventory(
            (_fragment(text="Problem: manual close", artifact_hash=_hash("c")),),
            expected_revision=3,
        ),
    ).build_primary(CASE_ID)

    assert changed.profile_id != profile_v2.profile_id
    assert changed.profile_hash != profile_v2.profile_hash
    assert changed.data_revision == 3


def test_build_primary_rejects_fragment_with_unknown_or_mismatched_artifact_before_extraction() -> None:
    extractor = RecordingExtractor()
    service = _service(
        profile_repo=CapturingProfileRepository(),
        deterministic_extractor=extractor,
        fragments=(_fragment(artifact_id=OTHER_ARTIFACT_ID),),
    )

    with pytest.raises(ValueError, match="startup_profile_fragment_artifact_not_found"):
        service.build_primary(CASE_ID)

    assert extractor.calls == 0
    extractor = RecordingExtractor()
    service = _service(
        profile_repo=CapturingProfileRepository(),
        deterministic_extractor=extractor,
        fragments=(_fragment(artifact_hash=_hash("c")),),
    )
    with pytest.raises(ValueError, match="startup_profile_fragment_source_hash_mismatch"):
        service.build_primary(CASE_ID)

    assert extractor.calls == 0
    extractor = RecordingExtractor()
    service = _service(
        profile_repo=CapturingProfileRepository(),
        deterministic_extractor=extractor,
        fragments=(
            _fragment().model_copy(update={"redaction_policy_version": "rules-redactor@2"}),
        ),
    )
    with pytest.raises(ValueError, match="startup_profile_fragment_redaction_mismatch"):
        service.build_primary(CASE_ID)

    assert extractor.calls == 0


def test_build_primary_preserves_contradiction_ids_and_invalid_extractor_becomes_controlled_gap() -> None:
    contradiction_id = UUID("99999999-9999-4999-8999-999999999999")
    invalid_service = _service(
        profile_repo=CapturingProfileRepository(),
        contradiction_repository=Repository([_contradiction(contradiction_id)]),
        deterministic_extractor=InvalidExtractor(),
    )

    profile = invalid_service.build_primary(CASE_ID)

    assert profile.contradiction_ids == (contradiction_id,)
    assert "primary_profile_extraction_invalid" in profile.gap_codes
    assert profile.fields[StartupProfileFieldName.PROBLEM.value].status is (
        StartupProfileFieldStatus.INSUFFICIENT_DATA
    )


def test_profile_json_never_persists_path_email_or_token_from_redacted_fragments() -> None:
    private_email = "founder" + "@" + "example.com"
    private_token = "sk" + "-proj-secret"
    private_path = "C:" + "\\secret"
    profile = _service(
        profile_repo=CapturingProfileRepository(),
        fragments=(
            _fragment(
                text=(
                    "Problem: [REDACTED:email:1] cannot use [REDACTED:secret:1]\n"
                    "Solution: sanitized workflow"
                ),
            ),
        ),
    ).build_primary(CASE_ID)

    dumped = profile.model_dump_json()
    assert private_email not in dumped
    assert private_token not in dumped
    assert private_path not in dumped


def test_build_primary_is_idempotent_for_same_inputs() -> None:
    repo = CapturingProfileRepository()
    fragments = (_fragment(text="Problem: manual close"),)
    service = _service(profile_repo=repo, fragments=fragments)

    first = service.build_primary(CASE_ID)
    second = service.build_primary(CASE_ID)

    assert first.profile_id == second.profile_id
    assert first.profile_hash == second.profile_hash
    assert repo.added == [first]


def test_build_primary_reuses_current_primary_for_same_revision_without_reextracting() -> None:
    repo = CapturingProfileRepository()
    first = _service(profile_repo=repo).build_primary(CASE_ID)

    replay = _service(
        profile_repo=repo,
        deterministic_extractor=UnusedExtractor(),
    ).build_primary(CASE_ID)

    assert replay == first
    assert repo.added == [first]


def test_enrich_with_disclosure_calls_external_once_and_persists_child_profile() -> None:
    primary_repo = CapturingProfileRepository()
    primary_service = StartupProfileService(
        case_repository=Repository([_case()]),
        artifact_repository=Repository([_artifact()]),
        parsed_artifact_repository=Repository([_spreadsheet_parse_result()]),
        evidence_repository=Repository([_metric_fact()]),
        startup_claim_repository=Repository([]),
        contradiction_repository=Repository([]),
        startup_profile_repository=primary_repo,
        deterministic_extractor=DeterministicStartupProfileExtractor(),
        external_extractor=None,
    )
    primary = primary_service.build_primary(CASE_ID)
    profile_repo = CapturingProfileRepository(existing=primary)
    external = SuccessfulExtractor()
    service = StartupProfileService(
        case_repository=Repository([_case()]),
        artifact_repository=Repository([_artifact()]),
        parsed_artifact_repository=Repository([_spreadsheet_parse_result()]),
        evidence_repository=Repository([_metric_fact()]),
        startup_claim_repository=Repository([]),
        contradiction_repository=Repository([]),
        startup_profile_repository=profile_repo,
        deterministic_extractor=DeterministicStartupProfileExtractor(),
        external_extractor=external,
    )

    enriched = service.enrich(CASE_ID, primary.profile_id, disclosure_scope=_scope())

    assert external.calls == 1
    assert isinstance(enriched, StartupProfile)
    assert enriched.analysis_stage is StartupProfileAnalysisStage.ENRICHED
    assert enriched.parent_profile_id == primary.profile_id
    assert enriched.profile_id != primary.profile_id
    assert profile_repo.added == [enriched]
    assert enriched.fields[StartupProfileFieldName.SOLUTION.value].values == ("automated close workflows",)


def test_enrich_reuses_current_enriched_profile_for_same_revision_without_reextracting() -> None:
    primary = _service(profile_repo=CapturingProfileRepository()).build_primary(CASE_ID)
    profile_repo = CapturingProfileRepository(existing=primary)
    first = _service(
        profile_repo=profile_repo,
        external_extractor=SuccessfulExtractor(),
    ).enrich(CASE_ID, primary.profile_id, disclosure_scope=_scope())

    replay = _service(
        profile_repo=profile_repo,
        external_extractor=UnusedExtractor(),
    ).enrich(CASE_ID, primary.profile_id, disclosure_scope=_scope())

    assert replay == first
    assert profile_repo.added == [first]


def test_enrich_validates_primary_case_revision_stage_before_external_call() -> None:
    external = SuccessfulExtractor()
    wrong_case_primary = _service(profile_repo=CapturingProfileRepository()).build_primary(CASE_ID)
    wrong_case_primary = wrong_case_primary.model_copy(update={"case_id": OTHER_CASE_ID})
    stale_primary = _service(profile_repo=CapturingProfileRepository()).build_primary(CASE_ID)
    stale_primary = stale_primary.model_copy(update={"data_revision": 1})
    enriched_primary = _service(profile_repo=CapturingProfileRepository()).build_primary(CASE_ID)
    enriched_primary = enriched_primary.model_copy(
        update={
            "analysis_stage": StartupProfileAnalysisStage.ENRICHED,
            "parent_profile_id": PRIMARY_PROFILE_ID,
        }
    )

    for primary in (wrong_case_primary, stale_primary, enriched_primary):
        service = _service(
            profile_repo=CapturingProfileRepository(existing=primary),
            external_extractor=external,
        )
        with pytest.raises(ValueError, match="startup_profile_primary_mismatch"):
            service.enrich(CASE_ID, primary.profile_id, disclosure_scope=_scope())

    assert external.calls == 0


def test_enrich_passes_redacted_fragments_to_external_once_after_approval() -> None:
    primary = _service(
        profile_repo=CapturingProfileRepository(),
        fragments=(_fragment(text="Problem: manual close"),),
    ).build_primary(CASE_ID)
    external = RecordingSuccessfulExtractor()
    service = _service(
        profile_repo=CapturingProfileRepository(existing=primary),
        external_extractor=external,
        fragments=(_fragment(text="Solution: automated workflows"),),
    )

    service.enrich(CASE_ID, primary.profile_id, disclosure_scope=_scope())

    assert external.calls == 1
    assert external.requests[0].fragments[0].text == "Solution: automated workflows"


def test_enrich_without_disclosure_returns_primary_profile_without_external_call() -> None:
    primary = _service(profile_repo=CapturingProfileRepository()).build_primary(CASE_ID)
    external = RecordingExtractor()
    service = _service(
        profile_repo=CapturingProfileRepository(existing=primary),
        external_extractor=external,
    )

    result: object = service.enrich(CASE_ID, primary.profile_id, disclosure_scope=None)

    assert result is primary
    assert external.calls == 0


@pytest.mark.parametrize("exc", [TimeoutError("timeout"), RuntimeError("network")])
def test_build_primary_propagates_non_controlled_extractor_failures(exc: Exception) -> None:
    service = _service(
        profile_repo=CapturingProfileRepository(),
        deterministic_extractor=RaisingExtractor(exc),
        fragments=(_fragment(text="Problem: manual close"),),
    )

    with pytest.raises(type(exc), match=str(exc)):
        service.build_primary(CASE_ID)


def test_build_primary_converts_only_controlled_invalid_output_to_gap() -> None:
    profile = _service(
        profile_repo=CapturingProfileRepository(),
        deterministic_extractor=RaisingExtractor(
            StartupProfileExtractorInvalidOutputError("invalid structured output")
        ),
        fragments=(_fragment(text="Problem: manual close"),),
    ).build_primary(CASE_ID)

    assert "primary_profile_extraction_invalid" in profile.gap_codes


def test_enrich_converts_external_timeout_to_controlled_gap_without_failing_workflow() -> None:
    primary = _service(profile_repo=CapturingProfileRepository()).build_primary(CASE_ID)
    profile_repo = CapturingProfileRepository(existing=primary)
    service = _service(
        profile_repo=profile_repo,
        external_extractor=RaisingExtractor(TimeoutError("provider timeout")),
        fragments=(_fragment(text="Problem: manual close"),),
    )

    enriched = service.enrich(CASE_ID, primary.profile_id, disclosure_scope=_scope())

    assert enriched.analysis_stage is StartupProfileAnalysisStage.ENRICHED
    assert enriched.parent_profile_id == primary.profile_id
    assert enriched.fields == primary.fields
    assert "external_profile_extraction_timeout" in enriched.gap_codes
    assert profile_repo.added == [enriched]


class ProfileRepository:
    def __init__(self, profile: object) -> None:
        self.profile = profile

    def get(self, profile_id: UUID) -> object:
        assert profile_id == PRIMARY_PROFILE_ID
        return self.profile


class CapturingProfileRepository:
    def __init__(self, existing: StartupProfile | None = None) -> None:
        self.added: list[StartupProfile] = []
        self._existing = existing

    def add(self, profile: StartupProfile) -> None:
        self.added.append(profile)

    def get(self, profile_id: UUID) -> StartupProfile:
        if self._existing is not None and self._existing.profile_id == profile_id:
            return self._existing
        for profile in reversed(self.added):
            if profile.profile_id == profile_id:
                return profile
        raise KeyError(profile_id)

    def get_for_stage(
        self,
        case_id: UUID,
        data_revision: int,
        stage: StartupProfileAnalysisStage,
    ) -> StartupProfile:
        candidates = [
            profile
            for profile in (self._existing, *self.added)
            if profile is not None
            and profile.case_id == case_id
            and profile.data_revision == data_revision
            and profile.analysis_stage is stage
        ]
        if not candidates:
            raise KeyError((case_id, data_revision, stage))
        return candidates[-1]


class Repository:
    def __init__(self, records: list[object]) -> None:
        self.records = records

    def get(self, record_id: UUID) -> object:
        for record in self.records:
            if getattr(record, "id", getattr(record, "case_id", getattr(record, "artifact_id", None))) == record_id:
                return record
        raise KeyError(record_id)

    def list_for_case(self, case_id: UUID) -> list[object]:
        return [
            record
            for record in self.records
            if getattr(record, "case_id", case_id) == case_id
        ]


class FragmentInventory:
    def __init__(
        self,
        fragments: tuple[StartupProfileBoundedFragment, ...],
        *,
        expected_case_id: UUID = CASE_ID,
        expected_revision: int = 2,
    ) -> None:
        self._fragments = fragments
        self._expected_case_id = expected_case_id
        self._expected_revision = expected_revision
        self.calls: list[tuple[UUID, int]] = []

    def list_for_case_revision(
        self,
        case_id: UUID,
        data_revision: int,
    ) -> tuple[StartupProfileBoundedFragment, ...]:
        self.calls.append((case_id, data_revision))
        assert (case_id, data_revision) == (self._expected_case_id, self._expected_revision)
        return self._fragments


class RecordingExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfileExtractionResponse:
        del request, disclosure_scope
        self.calls += 1
        raise AssertionError("external extractor must not be called without disclosure scope")


class SuccessfulExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfileExtractionResponse:
        assert disclosure_scope is not None
        self.calls += 1
        fact = request.spreadsheet_facts[0]
        return StartupProfileExtractionResponse(
            fields=(
                StartupProfileExtractedField(
                    field_name=StartupProfileFieldName.SOLUTION,
                    normalized_values=("automated close workflows",),
                    status=StartupProfileFieldStatus.SOURCE_FACT,
                    confidence=Decimal("0.82"),
                    refs=(
                        StartupProfileSafeRef(
                            ref_type="evidence_fact",
                            ref_id=fact.evidence_fact_id,
                            artifact_id=fact.artifact_id,
                            artifact_hash=fact.artifact_hash,
                            locator_hash=fact.locator_hash,
                            confidence=fact.confidence,
                        ),
                    ),
                ),
            )
        )


class RecordingSuccessfulExtractor(SuccessfulExtractor):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[StartupProfileExtractionRequest] = []

    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfileExtractionResponse:
        self.requests.append(request)
        return super().extract(request, disclosure_scope=disclosure_scope)


class RecordingFragmentOrderExtractor:
    def __init__(self) -> None:
        self.requests: list[StartupProfileExtractionRequest] = []

    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfileExtractionResponse:
        del disclosure_scope
        self.requests.append(request)
        return StartupProfileExtractionResponse(fields=())


class InvalidExtractor:
    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfileExtractionResponse:
        del request, disclosure_scope
        return StartupProfileExtractionResponse(
            fields=(
                StartupProfileExtractedField(
                    field_name=StartupProfileFieldName.PROBLEM,
                    normalized_values=("manual close",),
                    status=StartupProfileFieldStatus.SOURCE_FACT,
                    confidence=Decimal("0.8"),
                    refs=(
                        StartupProfileSafeRef(
                            ref_type="fragment",
                            ref_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                            artifact_id=ARTIFACT_ID,
                            artifact_hash=_hash("b"),
                            locator_hash=_hash("d"),
                            confidence=Decimal("0.8"),
                        ),
                    ),
                ),
            )
        )


class RaisingExtractor:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfileExtractionResponse:
        del request, disclosure_scope
        raise self._exc


class UnusedExtractor:
    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfileExtractionResponse:
        del request, disclosure_scope
        raise AssertionError("unused")


class UnusedRepository:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"unused repository method {name}")


def _service(
    *,
    profile_repo: CapturingProfileRepository,
    contradiction_repository: Repository | None = None,
    deterministic_extractor: StartupProfileExtractionPort | None = None,
    external_extractor: StartupProfileExtractionPort | None = None,
    fragments: tuple[StartupProfileBoundedFragment, ...] = (),
) -> StartupProfileService:
    return StartupProfileService(
        case_repository=Repository([_case()]),
        artifact_repository=Repository([_artifact()]),
        parsed_artifact_repository=Repository([_spreadsheet_parse_result()]),
        evidence_repository=Repository([_metric_fact()]),
        startup_claim_repository=Repository([]),
        contradiction_repository=contradiction_repository or Repository([]),
        startup_profile_repository=profile_repo,
        deterministic_extractor=deterministic_extractor or DeterministicStartupProfileExtractor(),
        external_extractor=external_extractor,
        fragment_inventory=FragmentInventory(fragments),
    )


def _case(
    *,
    data_revision: int = 2,
    updated_at: datetime | None = None,
) -> DueDiligenceCase:
    now = updated_at or datetime(2026, 8, 13, 10, tzinfo=UTC)
    return DueDiligenceCase(
        case_id=CASE_ID,
        mode=AnalysisMode.STARTUP,
        entity_name="LedgerPilot",
        entity_identifier="ledgerpilot",
        jurisdiction="US",
        scope=("startup",),
        as_of=now,
        base_currency="USD",
        privacy_policy="startup@1",
        budget_policy="startup@1",
        status=CaseStatus.RUNNING,
        sensitivity=SensitivityClass.PUBLIC,
        created_at=now,
        updated_at=now,
        workflow_version="startup@1",
        data_revision=data_revision,
    )


def _artifact(*, source_snapshot_hash: str = "b" * 64) -> Artifact:
    now = datetime(2026, 8, 13, 10, tzinfo=UTC)
    return Artifact(
        id=ARTIFACT_ID,
        case_id=CASE_ID,
        content_hash="a" * 64,
        mime_type="text/csv",
        source="startup_upload",
        retrieved_at=now,
        source_snapshot_hash=source_snapshot_hash,
        parsing_status=ArtifactParsingStatus.PARSED,
        sensitivity=SensitivityClass.PUBLIC,
    )


def _spreadsheet_parse_result() -> ParsedStartupArtifact:
    return ParsedStartupArtifact.from_spreadsheet(
        SpreadsheetParseResult(artifact_id=ARTIFACT_ID, status="parsed"),
        case_id=CASE_ID,
        detected_mime_type="text/csv",
        parser_name="unit",
        parser_version="unit@1",
    )


def _metric_fact() -> EvidenceFact:
    return EvidenceFact(
        id=METRIC_FACT_ID,
        artifact_id=ARTIFACT_ID,
        name="ARR",
        value=Decimal(120000),
        value_type="decimal",
        unit="USD",
        period="2026",
        locator=SourceLocator(kind="cell", value="C:\\secret\\metrics.csv#B2", artifact_id=ARTIFACT_ID, table="m", cell="B2"),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.91"),
    )


def _fragment(
    *,
    fragment_id: UUID = DEFAULT_FRAGMENT_ID,
    artifact_id: UUID = ARTIFACT_ID,
    text: str = "Problem: manual close",
    artifact_hash: str = "sha256:" + "b" * 64,
) -> StartupProfileBoundedFragment:
    return StartupProfileBoundedFragment(
        fragment_id=fragment_id,
        artifact_id=artifact_id,
        text=text,
        text_hash=_hash("d"),
        artifact_hash=artifact_hash,
        locator_hash=_hash("e"),
        sensitivity=SensitivityClass.PUBLIC,
        redacted=True,
        minimized=True,
        redaction_policy_version="rules-redactor@1",
    )


def _contradiction(contradiction_id: UUID) -> object:
    return SimpleNamespace(id=contradiction_id, case_id=CASE_ID)


def _hash(char: str) -> str:
    return f"sha256:{char * 64}"


def _scope() -> DisclosureScope:
    return DisclosureScope(
        approval_id=UUID("55555555-5555-4555-8555-555555555555"),
        allowed_classes=frozenset({SensitivityClass.PUBLIC}),
        destination="openai.responses",
        egress_policy_version="egress@1",
        redaction_policy_versions=frozenset({"rules-redactor@1"}),
    )
