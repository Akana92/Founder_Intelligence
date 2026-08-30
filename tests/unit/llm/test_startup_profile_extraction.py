from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from due_diligence_agent.adapters.startup.deterministic_profile_extractor import (
    DeterministicStartupProfileExtractor,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfileFieldName as DomainStartupProfileFieldName,
)
from due_diligence_agent.ports.startup_profile_extraction import (
    MAX_FRAGMENT_CHARS,
    MAX_FRAGMENTS,
    MAX_VALUES_PER_FIELD,
    StartupProfileBoundedFragment,
    StartupProfileExtractedField,
    StartupProfileExtractionRequest,
    StartupProfileExtractionResponse,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
    StartupProfileSafeRef,
)

CASE_ID = UUID("11111111-1111-4111-8111-111111111111")
ARTIFACT_ID = UUID("22222222-2222-4222-8222-222222222222")
FRAGMENT_ID = UUID("33333333-3333-4333-8333-333333333333")
FACT_ID = UUID("44444444-4444-4444-8444-444444444444")


def test_extraction_port_uses_canonical_profile_field_enums() -> None:
    assert StartupProfileFieldName is DomainStartupProfileFieldName


def test_request_rejects_unbounded_or_unredacted_fragments_before_adapter_call() -> None:
    allowed = _request_payload()

    with pytest.raises(ValidationError, match="redacted"):
        StartupProfileExtractionRequest.model_validate(
            {**allowed, "fragments": [{**_fragment_payload(), "redacted": False}]}
        )

    with pytest.raises(ValidationError, match="fragment text too long"):
        StartupProfileExtractionRequest.model_validate(
            {**allowed, "fragments": [{**_fragment_payload(), "text": "x" * (MAX_FRAGMENT_CHARS + 1)}]}
        )

    with pytest.raises(ValidationError, match="too many fragments"):
        StartupProfileExtractionRequest.model_validate(
            {
                **allowed,
                "fragments": [
                    {**_fragment_payload(), "fragment_id": str(UUID(int=index + 1))}
                    for index in range(MAX_FRAGMENTS + 1)
                ],
            }
        )


@pytest.mark.parametrize(
    "sentinel",
    [
        "founder" + "@" + "example.com",
        "sk" + "-proj-secret",
        "Bearer " + "secret-token",
        "C:" + "\\Users\\Akana\\secret.txt",
        "/" + "home/akana/secret.txt",
    ],
)
def test_bounded_fragment_rejects_raw_private_material_with_generic_error(sentinel: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        StartupProfileBoundedFragment.model_validate(
            {**_fragment_payload(), "text": f"Problem: manual close {sentinel}"}
        )

    message = str(exc_info.value)
    assert "unsafe fragment text" in message
    assert sentinel not in message


@pytest.mark.parametrize(
    "sentinel",
    [
        "founder" + "@" + "example.com",
        "sk" + "-proj-secret",
        "Bearer " + "secret-token",
        "C:" + "\\Users\\Akana\\secret.txt",
        "/" + "home/akana/secret.txt",
    ],
)
def test_request_rejects_raw_private_fragment_material_before_adapter_call(sentinel: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        StartupProfileExtractionRequest.model_validate(
            _request_payload(text=f"Problem: manual close {sentinel}")
        )

    message = str(exc_info.value)
    assert "unsafe fragment text" in message
    assert sentinel not in message


def test_bounded_fragment_allows_normal_startup_prose() -> None:
    fragment = StartupProfileBoundedFragment.model_validate(
        {
            **_fragment_payload(),
            "text": (
                "Problem: sales teams lose context across handoffs\n"
                "Solution: privacy-safe founder CRM workspace for seed-stage B2B SaaS"
            ),
        }
    )

    assert "privacy-safe founder CRM workspace" in fragment.text


def test_response_rejects_extra_keys_unsafe_status_and_unknown_refs() -> None:
    request = _request()
    safe_ref = _safe_ref()

    with pytest.raises(ValidationError, match="extra_forbidden"):
        StartupProfileExtractedField.model_validate(
            {
                "field_name": "startup_name",
                "normalized_values": ["Acme"],
                "status": "source_fact",
                "confidence": "0.9",
                "refs": [safe_ref.model_dump(mode="json")],
                "prompt_body": "must not be accepted",
            }
        )

    with pytest.raises(ValidationError, match="source_fact requires refs"):
        StartupProfileExtractedField(
            field_name=StartupProfileFieldName.STARTUP_NAME,
            normalized_values=("Acme",),
            status=StartupProfileFieldStatus.SOURCE_FACT,
            confidence=Decimal("0.9"),
        )

    response = StartupProfileExtractionResponse(
        fields=(
            StartupProfileExtractedField(
                field_name=StartupProfileFieldName.STARTUP_NAME,
                normalized_values=("Acme",),
                status=StartupProfileFieldStatus.SOURCE_FACT,
                confidence=Decimal("0.9"),
                refs=(safe_ref.model_copy(update={"ref_id": UUID("99999999-9999-4999-8999-999999999999")}),),
            ),
        )
    )

    with pytest.raises(ValueError, match="unknown extraction refs"):
        response.validate_against_request(request)


def test_response_rejects_unknown_claim_and_contradiction_refs_without_inventory() -> None:
    request = _request()
    for ref_type in ("claim", "contradiction"):
        response = StartupProfileExtractionResponse(
            fields=(
                StartupProfileExtractedField(
                    field_name=StartupProfileFieldName.PROBLEM,
                    normalized_values=("manual close",),
                    status=StartupProfileFieldStatus.SOURCE_FACT,
                    confidence=Decimal("0.7"),
                    refs=(
                        StartupProfileSafeRef(
                            ref_type=ref_type,
                            ref_id=UUID("99999999-9999-4999-8999-999999999999"),
                            artifact_id=ARTIFACT_ID,
                            artifact_hash=_hash("a"),
                            locator_hash=_hash("c"),
                            confidence=Decimal("0.7"),
                        ),
                    ),
                ),
            )
        )

        with pytest.raises(ValueError, match="unknown extraction refs"):
            response.validate_against_request(request)


def test_deterministic_extractor_uses_only_explicit_redacted_fragments_and_metrics() -> None:
    private_email = "founder" + "@" + "example.com"
    private_token = "sk" + "-proj-secret"
    private_path = "C:" + "\\secret"
    request = _request(
        text=(
            "Startup Name: LedgerPilot\n"
            "Problem: finance teams reconcile reports manually.\n"
            "Contact [REDACTED:email:1] for [REDACTED:path:1] [REDACTED:secret:1]"
        ),
        spreadsheet_facts=[
            {
                "evidence_fact_id": str(FACT_ID),
                "artifact_id": str(ARTIFACT_ID),
                "name": "ARR",
                "value_type": "decimal",
                "normalized_value": "120000",
                "unit": "USD",
                "period": "2026",
                "confidence": "0.91",
                "sensitivity": "public",
                "artifact_hash": _hash("a"),
                "locator_hash": _hash("c"),
                "table": "metrics",
                "cell": "B2",
            }
        ],
    )

    response = DeterministicStartupProfileExtractor().extract(request, disclosure_scope=None)

    by_name = {field.field_name: field for field in response.fields}
    assert by_name[StartupProfileFieldName.STARTUP_NAME].normalized_values == ("LedgerPilot",)
    assert by_name[StartupProfileFieldName.PROBLEM].normalized_values == (
        "finance teams reconcile reports manually.",
    )
    assert by_name[StartupProfileFieldName.TRACTION].normalized_values == ("ARR: 120000 USD 2026",)
    dumped = response.model_dump_json()
    assert private_email not in dumped
    assert private_token not in dumped
    assert private_path not in dumped


def test_deterministic_extractor_promotes_constrained_case_sentence_to_source_backed_one_line_description() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "SaaS case: backlog automation for finance teams.\n"
                "Problem: finance teams reconcile reports manually."
            ),
            allowed_field_names=["one_line_description"],
        ),
        disclosure_scope=None,
    )

    description = next(
        field for field in response.fields if field.field_name is StartupProfileFieldName.ONE_LINE_DESCRIPTION
    )

    assert description.normalized_values == ("SaaS case: backlog automation for finance teams.",)
    assert description.status is StartupProfileFieldStatus.SOURCE_FACT
    assert description.confidence == Decimal("0.72")
    assert len(description.refs) == 1
    assert description.refs[0].ref_type == "fragment"
    assert description.refs[0].ref_id == FRAGMENT_ID
    assert description.refs[0].artifact_id == ARTIFACT_ID
    assert description.refs[0].confidence == Decimal("0.72")


def test_deterministic_extractor_aggregates_multiple_assumption_fragments() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["assumptions"],
            fragments=[
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333339",
                    "text": (
                        "Assumptions: Use finance forecast for July 2026: cash "
                        "balance $250,000, monthly net burn $42,000, runway about "
                        "6 months."
                    ),
                },
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333340",
                    "text": (
                        "Assumptions: Founder accepted a plan improvement for "
                        "positioning: align the offer around finance automation."
                    ),
                },
            ],
        ),
        disclosure_scope=None,
    )

    assumptions = next(
        field
        for field in response.fields
        if field.field_name is StartupProfileFieldName.ASSUMPTIONS
    )

    assert assumptions.status is StartupProfileFieldStatus.SOURCE_FACT
    assert assumptions.normalized_values == (
        (
            "Use finance forecast for July 2026: cash balance $250,000, "
            "monthly net burn $42,000, runway about 6 months."
        ),
        (
            "Founder accepted a plan improvement for positioning: align the "
            "offer around finance automation."
        ),
    )
    assert len(assumptions.refs) == 2


def test_deterministic_extractor_promotes_russian_startup_brief_to_source_backed_profile_fields() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "Название стартапа: NomadFlow AI\n"
                "Продукт: AI-помощник для цифровых кочевников, который собирает визы, жилье, бюджет и налоги в один маршрут.\n"
                "Проблема: удаленные специалисты тратят недели на сравнение стран, виз и стоимости жизни.\n"
                "ICP: фрилансеры и remote-first сотрудники с доходом от $3,000 в месяц.\n"
                "Стадия: MVP запущен, 120 пользователей в waitlist.\n"
                "Модель выручки: подписка $19 в месяц и комиссионные от партнеров.\n"
                "MRR: $2,400 в июле 2026.\n"
                "Валовая маржа: 74%.\n"
                "Runway: 7 месяцев."
            ),
            allowed_field_names=[
                "startup_name",
                "one_line_description",
                "problem",
                "icp",
                "stage",
                "pricing_revenue_model",
                "traction",
                "metric_pack_candidates",
            ],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}

    assert by_name[StartupProfileFieldName.STARTUP_NAME].normalized_values == ("NomadFlow AI",)
    assert by_name[StartupProfileFieldName.ONE_LINE_DESCRIPTION].normalized_values == (
        "AI-помощник для цифровых кочевников, который собирает визы, жилье, бюджет и налоги в один маршрут.",
    )
    assert by_name[StartupProfileFieldName.PROBLEM].normalized_values == (
        "удаленные специалисты тратят недели на сравнение стран, виз и стоимости жизни.",
    )
    assert by_name[StartupProfileFieldName.ICP].normalized_values == (
        "фрилансеры и remote-first сотрудники с доходом от $3,000 в месяц.",
    )
    assert by_name[StartupProfileFieldName.STAGE].normalized_values == (
        "MVP запущен, 120 пользователей в waitlist.",
    )
    assert by_name[StartupProfileFieldName.PRICING_REVENUE_MODEL].normalized_values == (
        "подписка $19 в месяц и комиссионные от партнеров.",
    )
    assert by_name[StartupProfileFieldName.TRACTION].normalized_values == (
        "MRR: $2,400 июле 2026",
        "Валовая маржа: 74%",
        "Runway: 7 месяцев",
    )
    assert by_name[StartupProfileFieldName.METRIC_PACK_CANDIDATES].normalized_values == (
        "MRR: $2,400 июле 2026",
        "Валовая маржа: 74%",
        "Runway: 7 месяцев",
    )
    for field_name in (
        StartupProfileFieldName.STARTUP_NAME,
        StartupProfileFieldName.ONE_LINE_DESCRIPTION,
        StartupProfileFieldName.PROBLEM,
        StartupProfileFieldName.ICP,
        StartupProfileFieldName.PRICING_REVENUE_MODEL,
        StartupProfileFieldName.TRACTION,
    ):
        assert by_name[field_name].status is StartupProfileFieldStatus.SOURCE_FACT
        assert by_name[field_name].refs[0].ref_id == FRAGMENT_ID


def test_deterministic_extractor_promotes_idea_text_brief_name_and_stage() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "Founder idea brief: SilkStock Planner\n\n"
                "Concept:\n"
                "SilkStock Planner is an inventory-planning SaaS for retailers.\n\n"
                "Known gaps:\n"
                "No uploaded document provides revenue, expense, burn, cash balance, "
                "customer count, ARR, MRR, or cohort metrics. The case is idea-only "
                "and should ask for evidence rather than infer operating metrics."
            ),
            allowed_field_names=["startup_name", "stage"],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}
    assert by_name[StartupProfileFieldName.STARTUP_NAME].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.STARTUP_NAME].normalized_values == ("SilkStock Planner",)
    assert by_name[StartupProfileFieldName.STAGE].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.STAGE].normalized_values == ("idea",)
    assert by_name[StartupProfileFieldName.STARTUP_NAME].refs[0].ref_id == FRAGMENT_ID
    assert by_name[StartupProfileFieldName.STAGE].refs[0].ref_id == FRAGMENT_ID


def test_deterministic_extractor_promotes_mid_row_delimiterless_stage_label() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "Дата среза 2026 Раунд Seed "
                "Стадия Рабочий продукт / pre-scale "
                "Бизнес-модель B2B SaaS"
            ),
            allowed_field_names=["stage"],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}
    stage = by_name[StartupProfileFieldName.STAGE]

    assert stage.status is StartupProfileFieldStatus.SOURCE_FACT
    assert stage.normalized_values == ("Рабочий продукт / pre-scale",)
    assert stage.refs[0].ref_id == FRAGMENT_ID


def test_deterministic_extractor_promotes_strong_document_semantics_into_existing_carriers() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "Solution module: platform for university admissions and Housing Management.\n"
                "Customer segments: universities, students, parents, and education agents.\n"
                "Pricing table: Starter 240000 KZT/month and Growth 690000 KZT/month.\n"
                "Market formulas: TAM SAM SOM model for university market sizing.\n"
                "Rating methodology: rating fit combines program fit and demand.\n"
                "Funding gate: 35.2M KZT platform round funds platform roadmap gate.\n"
                "Legal privacy risk: consent for personal data is required.\n"
                "Housing Management no-go: stop launch until fire-safety, sanitary, insurance, and landlord approvals.\n"
                "Forecasts: revenue and EBITDA forecast for 2027-2031."
            ),
            allowed_field_names=[
                "solution",
                "icp",
                "pricing_revenue_model",
                "assumptions",
                "weaknesses",
                "metric_pack_candidates",
            ],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}

    assert by_name[StartupProfileFieldName.SOLUTION].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.ICP].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.PRICING_REVENUE_MODEL].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.ASSUMPTIONS].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.WEAKNESSES].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.METRIC_PACK_CANDIDATES].status is StartupProfileFieldStatus.SOURCE_FACT
    source_fact_text = " | ".join(
        value
        for field in by_name.values()
        for value in field.normalized_values
    ).casefold()
    for marker in (
        "platform",
        "housing",
        "universities",
        "students",
        "kzt/month",
        "tam",
        "rating",
        "35.2m",
        "gate",
        "privacy",
        "no-go",
        "2027-2031",
    ):
        assert marker in source_fact_text


def test_deterministic_extractor_does_not_promote_forecast_funding_or_private_actuals_to_pricing_or_traction() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "Forecasts: revenue and EBITDA forecast for 2027-2031.\n"
                "Funding gate: 35.2M KZT platform round funds platform roadmap gate.\n"
                "Private actuals appendix: ARR of $1.2M, MRR of $100K, and 120 pilot customers."
            ),
            allowed_field_names=[
                "pricing_revenue_model",
                "traction",
                "assumptions",
                "metric_pack_candidates",
            ],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}

    assert by_name[StartupProfileFieldName.PRICING_REVENUE_MODEL].status is (
        StartupProfileFieldStatus.INSUFFICIENT_DATA
    )
    assert by_name[StartupProfileFieldName.TRACTION].status is StartupProfileFieldStatus.INSUFFICIENT_DATA
    assert by_name[StartupProfileFieldName.ASSUMPTIONS].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.METRIC_PACK_CANDIDATES].status is (
        StartupProfileFieldStatus.SOURCE_FACT
    )
    retained_text = " | ".join(
        value
        for field_name in (StartupProfileFieldName.ASSUMPTIONS, StartupProfileFieldName.METRIC_PACK_CANDIDATES)
        for value in by_name[field_name].normalized_values
    ).casefold()
    assert "forecast" in retained_text
    assert "35.2m" in retained_text


@pytest.mark.parametrize(
    "negative_pricing_text",
    (
        "Pricing terms are not stated in the uploaded document.",
        "No pricing is provided in the uploaded document.",
        "В документе не указаны тарифы.",
        "Нет модели выручки в загруженном документе.",
    ),
)
def test_deterministic_extractor_does_not_promote_negative_pricing_statements(
    negative_pricing_text: str,
) -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=negative_pricing_text,
            allowed_field_names=["pricing_revenue_model", "assumptions", "metric_pack_candidates"],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}

    assert by_name[StartupProfileFieldName.PRICING_REVENUE_MODEL].status is (
        StartupProfileFieldStatus.INSUFFICIENT_DATA
    )


def test_deterministic_extractor_recovers_name_from_minimized_idea_concept_sentence() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "SilkStock Planner is an inventory-planning SaaS for Central Asian "
                "independent retailers and regional distributors.\n"
                "No uploaded document provides revenue, expense, burn, cash balance, "
                "customer count, ARR, MRR, or cohort metrics. The case is idea-only "
                "and should ask for evidence rather than infer operating metrics."
            ),
            allowed_field_names=["startup_name", "stage"],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}
    assert by_name[StartupProfileFieldName.STARTUP_NAME].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.STARTUP_NAME].normalized_values == ("SilkStock Planner",)
    assert by_name[StartupProfileFieldName.STAGE].normalized_values == ("idea",)


def test_deterministic_extractor_does_not_promote_planning_runway_targets_to_metrics() -> None:
    planning_only = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "Founder idea brief: SilkStock Planner\n"
                "Runway target: 12 months\n"
                "Scenario runway: 14 months\n"
                "Expected runway: 13 months\n"
                "Idea-only runway: 15 months\n"
                "Плановый runway: 10 месяцев\n"
                "Планируемый runway: 10 месяцев\n"
                "Прогноз runway: 9 месяцев\n"
                "Прогнозируемый runway: 9 месяцев\n"
                "Сценарный runway: 11 месяцев\n"
                "Ожидаемый runway: 8 месяцев"
            ),
            allowed_field_names=["traction", "metric_pack_candidates"],
        ),
        disclosure_scope=None,
    )

    for field in planning_only.fields:
        assert field.status is StartupProfileFieldStatus.INSUFFICIENT_DATA
        assert field.normalized_values == ()

    mixed = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "Runway target: 12 months\n"
                "Плановый runway: 10 месяцев\n"
                "Runway: 7 months"
            ),
            allowed_field_names=["traction", "metric_pack_candidates"],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in mixed.fields}
    assert by_name[StartupProfileFieldName.TRACTION].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.TRACTION].normalized_values == ("Runway: 7 months",)
    assert by_name[StartupProfileFieldName.METRIC_PACK_CANDIDATES].normalized_values == ("Runway: 7 months",)

    silkstock_planner = DeterministicStartupProfileExtractor().extract(
        _request(
            text="SilkStock Planner runway: 7 months",
            allowed_field_names=["traction", "metric_pack_candidates"],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in silkstock_planner.fields}
    assert by_name[StartupProfileFieldName.TRACTION].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.TRACTION].normalized_values == ("runway: 7 months",)
    assert by_name[StartupProfileFieldName.METRIC_PACK_CANDIDATES].normalized_values == ("runway: 7 months",)

    project_atlas = DeterministicStartupProfileExtractor().extract(
        _request(
            text="Project Atlas runway: 6 months",
            allowed_field_names=["traction", "metric_pack_candidates"],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in project_atlas.fields}
    assert by_name[StartupProfileFieldName.TRACTION].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.TRACTION].normalized_values == ("runway: 6 months",)
    assert by_name[StartupProfileFieldName.METRIC_PACK_CANDIDATES].normalized_values == ("runway: 6 months",)

    russian_product_name = DeterministicStartupProfileExtractor().extract(
        _request(
            text="SilkStock Планировщик runway: 5 months",
            allowed_field_names=["traction", "metric_pack_candidates"],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in russian_product_name.fields}
    assert by_name[StartupProfileFieldName.TRACTION].status is StartupProfileFieldStatus.SOURCE_FACT
    assert by_name[StartupProfileFieldName.TRACTION].normalized_values == ("runway: 5 months",)
    assert by_name[StartupProfileFieldName.METRIC_PACK_CANDIDATES].normalized_values == ("runway: 5 months",)


def test_deterministic_extractor_ignores_pdf_running_header_for_startup_name() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "NOMADFLOW AI | СИНТЕТИЧЕСКИЙ QA-ДОКУМЕНТ\n"
                "Capstone N3 • Не для инвестирования Стр. 1\n"
                "B2B SAAS ДЛЯ УПРАВЛЕНИЯ ЗАПАСАМИ\n"
                "NomadFlow AI"
            ),
            allowed_field_names=["startup_name"],
        ),
        disclosure_scope=None,
    )

    assert response.fields[0].normalized_values == ("NomadFlow AI",)


def test_deterministic_extractor_promotes_nomadflow_pdf_fragments_and_preserves_metric_conflicts() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=[
                "startup_name",
                "one_line_description",
                "problem",
                "solution",
                "icp",
                "geography",
                "stage",
                "business_model",
                "pricing_revenue_model",
                "channels_gtm",
                "traction",
                "metric_pack_candidates",
            ],
            fragments=[
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333331",
                    "text_hash": _hash("1"),
                    "locator_hash": _hash("2"),
                    "text": (
                        "NomadFlow AI\n"
                        "Инвестиционный бизнес-план, Seed раунд\n"
                        "NomadFlow AI разрабатывает облачную платформу управления запасами, "
                        "закупками и маршрутизацией для дистрибьюторов Центральной Азии.\n"
                        "Наблюдаемая проблема клиентов: дистрибьюторы FMCG и региональный retail "
                        "теряют продажи из-за ручных остатков, закупок и маршрутов."
                    ),
                },
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333332",
                    "text_hash": _hash("3"),
                    "locator_hash": _hash("4"),
                    "text": (
                        "Профиль проекта\n"
                        "Решение NomadFlow AI: единый SaaS-слой для прогнозирования запасов, "
                        "автозаказа и оптимизации маршрутов доставки.\n"
                        "География запуска Казахстан; далее Узбекистан и Кыргызстан.\n"
                        "Стадия Seed.\n"
                        "Бизнес-модель B2B SaaS, ежемесячная подписка и enterprise-контракты."
                    ),
                },
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333333",
                    "text_hash": _hash("5"),
                    "locator_hash": _hash("6"),
                    "text": (
                        "Приоритетные сегменты: FMCG-дистрибьюторы, региональный retail, "
                        "фармацевтическая дистрибуция и производители.\n"
                        "Тарифы: Starter 240 000 ₸/мес, Growth 690 000 ₸/мес, "
                        "Enterprise 1 900 000 ₸/мес.\n"
                        "Модель выхода на рынок: пилоты с 3PL и отраслевые партнерства "
                        "в Казахстане."
                    ),
                },
            ],
            spreadsheet_facts=[
                _spreadsheet_fact_payload_for(
                    0,
                    name="MRR CRM",
                    normalized_value="28.6m",
                    unit="KZT",
                    period="2026-07",
                    table="CRM export",
                    cell="B4",
                ),
                _spreadsheet_fact_payload_for(
                    1,
                    name="MRR bank/invoices",
                    normalized_value="27.9m",
                    unit="KZT",
                    period="2026-07",
                    table="Invoices",
                    cell="B8",
                ),
                _spreadsheet_fact_payload_for(
                    2,
                    name="Customers CRM",
                    normalized_value="31",
                    unit="customers",
                    period="2026-07",
                    table="CRM export",
                    cell="C4",
                ),
                _spreadsheet_fact_payload_for(
                    3,
                    name="Customers invoiced",
                    normalized_value="29",
                    unit="customers",
                    period="2026-07",
                    table="Invoices",
                    cell="C8",
                ),
                _spreadsheet_fact_payload_for(
                    4,
                    name="Gross margin operational",
                    normalized_value="74",
                    unit="%",
                    period="2026-Q2",
                    table="P&L",
                    cell="D12",
                ),
                _spreadsheet_fact_payload_for(
                    5,
                    name="Gross margin fully loaded",
                    normalized_value="70",
                    unit="%",
                    period="2026-Q2",
                    table="P&L",
                    cell="D13",
                ),
                _spreadsheet_fact_payload_for(
                    6,
                    name="CAC payback reported",
                    normalized_value="4.3",
                    unit="months",
                    period="2026-Q2",
                    table="Unit economics",
                    cell="E9",
                ),
                _spreadsheet_fact_payload_for(
                    7,
                    name="CAC payback recalculated",
                    normalized_value="5.5",
                    unit="months",
                    period="2026-Q2",
                    table="Unit economics",
                    cell="E10",
                ),
            ],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}

    assert by_name[StartupProfileFieldName.STARTUP_NAME].normalized_values == ("NomadFlow AI",)
    assert by_name[StartupProfileFieldName.ONE_LINE_DESCRIPTION].normalized_values == (
        "облачную платформу управления запасами, закупками и маршрутизацией для дистрибьюторов Центральной Азии.",
    )
    assert by_name[StartupProfileFieldName.PROBLEM].normalized_values == (
        "дистрибьюторы FMCG и региональный retail теряют продажи из-за ручных остатков, закупок и маршрутов.",
    )
    assert by_name[StartupProfileFieldName.SOLUTION].normalized_values == (
        "единый SaaS-слой для прогнозирования запасов, автозаказа и оптимизации маршрутов доставки.",
    )
    assert by_name[StartupProfileFieldName.ICP].normalized_values == (
        "FMCG-дистрибьюторы, региональный retail, фармацевтическая дистрибуция и производители.",
    )
    assert by_name[StartupProfileFieldName.GEOGRAPHY].normalized_values == (
        "Казахстан; далее Узбекистан и Кыргызстан.",
    )
    assert by_name[StartupProfileFieldName.STAGE].normalized_values == ("Seed.",)
    assert by_name[StartupProfileFieldName.BUSINESS_MODEL].normalized_values == (
        "B2B SaaS, ежемесячная подписка и enterprise-контракты.",
    )
    assert by_name[StartupProfileFieldName.PRICING_REVENUE_MODEL].normalized_values == (
        "Starter 240 000 ₸/мес, Growth 690 000 ₸/мес, Enterprise 1 900 000 ₸/мес.",
    )
    assert by_name[StartupProfileFieldName.CHANNELS_GTM].normalized_values == (
        "пилоты с 3PL и отраслевые партнерства в Казахстане.",
    )

    metrics = by_name[StartupProfileFieldName.METRIC_PACK_CANDIDATES]
    assert metrics.status is StartupProfileFieldStatus.CONTRADICTION
    assert metrics.reason_code == "metric_conflicts_detected"
    assert metrics.normalized_values == (
        "MRR conflict: MRR CRM 28.6m KZT 2026-07 | MRR bank/invoices 27.9m KZT 2026-07",
        "Customers conflict: Customers CRM 31 customers 2026-07 | Customers invoiced 29 customers 2026-07",
        "Gross margin conflict: Gross margin operational 74 % 2026-Q2 | Gross margin fully loaded 70 % 2026-Q2",
        "CAC payback conflict: CAC payback reported 4.3 months 2026-Q2 | CAC payback recalculated 5.5 months 2026-Q2",
    )
    assert tuple(ref.cell for ref in metrics.refs) == ("B4", "B8", "C4", "C8", "D12", "D13", "E9", "E10")
    assert tuple(ref.table for ref in metrics.refs) == (
        "CRM export",
        "Invoices",
        "CRM export",
        "Invoices",
        "P&L",
        "P&L",
        "Unit economics",
        "Unit economics",
    )
    assert by_name[StartupProfileFieldName.PRICING_REVENUE_MODEL].refs[0].ref_id == UUID(
        "33333333-3333-4333-8333-333333333333"
    )
    assert by_name[StartupProfileFieldName.GEOGRAPHY].refs[0].ref_id == UUID(
        "33333333-3333-4333-8333-333333333332"
    )


def test_deterministic_extractor_handles_real_nomadflow_parser_rows_without_false_label_prefix_facts() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=[
                "solution",
                "geography",
                "stage",
                "pricing_revenue_model",
            ],
            fragments=[
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333334",
                    "text_hash": _hash("7"),
                    "locator_hash": _hash("8"),
                    "text": (
                        "Решение NomadFlow Control Tower\n"
                        "Стадия Seed Дата среза 30 июня 2026\n"
                        "География Казахстан; далее Узбекистан и Кыргызстан Раунд $1,2 млн\n"
                        "Тариф Ежемесячно Разовый запуск Включено\n"
                        "Starter 240 000 ₸ 0 базовая аналитика\n"
                        "Growth 690 000 ₸ 500 000 ₸ маршрутизация и закупки\n"
                        "Enterprise 1 900 000 ₸ индивидуально SLA и интеграции"
                    ),
                },
            ],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}

    assert by_name[StartupProfileFieldName.SOLUTION].status is StartupProfileFieldStatus.INSUFFICIENT_DATA
    assert by_name[StartupProfileFieldName.SOLUTION].normalized_values == ()
    assert by_name[StartupProfileFieldName.STAGE].normalized_values == ("Seed",)
    assert by_name[StartupProfileFieldName.GEOGRAPHY].normalized_values == (
        "Казахстан; далее Узбекистан и Кыргызстан",
    )
    assert by_name[StartupProfileFieldName.PRICING_REVENUE_MODEL].normalized_values == (
        "Starter 240 000 ₸ 0 базовая аналитика",
        "Growth 690 000 ₸ 500 000 ₸ маршрутизация и закупки",
        "Enterprise 1 900 000 ₸ индивидуально SLA и интеграции",
    )
    assert by_name[StartupProfileFieldName.PRICING_REVENUE_MODEL].refs[0].ref_id == UUID(
        "33333333-3333-4333-8333-333333333334"
    )


def test_deterministic_extractor_rejects_smart_university_cover_finance_row_as_solution() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["solution", "geography"],
            text=(
                "SMART UNIVERSITY БИЗНЕС-ПЛАН 2027-2031\n"
                "Прогноз платформы — до корпоративных аналогов и без\n"
                "Платформа поступления, независимый рейтинг подготовки и поэтапная "
                "вертикаль студенческого жилья\n"
                "Раунд платформы 35,2 млн ₸ Плановый break-even 2029 год, базовый сценарий\n"
                "География Казахстан; жильё - Алматы Формат Для обсуждения с партнёром/инвестором\n"
                "Ключевое инвестиционное решение Сначала построить прибыльную asset-light "
                "платформу и доказать B2B-спрос."
            ),
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}

    assert by_name[StartupProfileFieldName.SOLUTION].normalized_values == (
        "Платформа поступления, независимый рейтинг подготовки и поэтапная вертикаль студенческого жилья",
    )
    solution_text = " ".join(by_name[StartupProfileFieldName.SOLUTION].normalized_values)
    assert "break-even" not in solution_text
    assert "Прогноз платформы" not in solution_text
    assert by_name[StartupProfileFieldName.GEOGRAPHY].normalized_values == ("Казахстан, Алматы",)


def test_deterministic_extractor_stops_real_smart_university_geography_at_format_column() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["geography"],
            text=(
                "Параметр Значение Параметр Значение\n"
                "Дата 25 августа 2026 Стадия Рабочий продукт / pre-scale\n"
                "Раунд 35,2 млн ₸ Плановый 2029 год, базовый сценарий\n"
                "платформы break-even\n"
                "География Казахстан; жильё — Алматы Формат Для обсуждения с партнёром/инвестором"
            ),
        ),
        disclosure_scope=None,
    )

    geography = response.fields[0]

    assert geography.status is StartupProfileFieldStatus.SOURCE_FACT
    assert geography.normalized_values == ("Казахстан, Алматы",)


def test_deterministic_extractor_recognizes_uppercase_two_word_startup_heading() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["startup_name"],
            text="SMART UNIVERSITY",
        ),
        disclosure_scope=None,
    )

    startup_name = response.fields[0]

    assert startup_name.status is StartupProfileFieldStatus.SOURCE_FACT
    assert startup_name.normalized_values == ("SMART UNIVERSITY",)


def test_deterministic_extractor_keeps_known_metric_conflicts_under_numeric_noise() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["metric_pack_candidates"],
            spreadsheet_facts=[
                _spreadsheet_fact_payload_for(
                    0,
                    name="Warehouse count",
                    normalized_value="14",
                    unit="sites",
                    period="2026-Q2",
                    table="Ops",
                    cell="A1",
                ),
                _spreadsheet_fact_payload_for(
                    1,
                    name="SKUs",
                    normalized_value="12000",
                    unit="items",
                    period="2026-Q2",
                    table="Ops",
                    cell="A2",
                ),
                _spreadsheet_fact_payload_for(
                    2,
                    name="MRR CRM",
                    normalized_value="28.6m",
                    unit="KZT",
                    period="2026-07",
                    table="CRM export",
                    cell="B4",
                ),
                _spreadsheet_fact_payload_for(
                    3,
                    name="MRR bank/invoices",
                    normalized_value="27.9m",
                    unit="KZT",
                    period="2026-07",
                    table="Invoices",
                    cell="B8",
                ),
                _spreadsheet_fact_payload_for(
                    4,
                    name="API calls",
                    normalized_value="900000",
                    unit="calls",
                    period="2026-07",
                    table="Product",
                    cell="A3",
                ),
                _spreadsheet_fact_payload_for(
                    5,
                    name="Customers CRM",
                    normalized_value="31",
                    unit="customers",
                    period="2026-07",
                    table="CRM export",
                    cell="C4",
                ),
                _spreadsheet_fact_payload_for(
                    6,
                    name="Customers invoiced",
                    normalized_value="29",
                    unit="customers",
                    period="2026-07",
                    table="Invoices",
                    cell="C8",
                ),
                _spreadsheet_fact_payload_for(
                    7,
                    name="Routes optimized",
                    normalized_value="1800",
                    unit="routes",
                    period="2026-07",
                    table="Product",
                    cell="A4",
                ),
                _spreadsheet_fact_payload_for(
                    8,
                    name="Gross margin operational",
                    normalized_value="74",
                    unit="%",
                    period="2026-Q2",
                    table="P&L",
                    cell="D12",
                ),
                _spreadsheet_fact_payload_for(
                    9,
                    name="Gross margin fully loaded",
                    normalized_value="70",
                    unit="%",
                    period="2026-Q2",
                    table="P&L",
                    cell="D13",
                ),
                _spreadsheet_fact_payload_for(
                    10,
                    name="CAC payback reported",
                    normalized_value="4.3",
                    unit="months",
                    period="2026-Q2",
                    table="Unit economics",
                    cell="E9",
                ),
                _spreadsheet_fact_payload_for(
                    11,
                    name="CAC payback recalculated",
                    normalized_value="5.5",
                    unit="months",
                    period="2026-Q2",
                    table="Unit economics",
                    cell="E10",
                ),
            ],
        ),
        disclosure_scope=None,
    )

    metrics = response.fields[0]

    assert metrics.status is StartupProfileFieldStatus.CONTRADICTION
    assert metrics.reason_code == "metric_conflicts_detected"
    assert metrics.normalized_values == (
        "MRR conflict: MRR CRM 28.6m KZT 2026-07 | MRR bank/invoices 27.9m KZT 2026-07",
        "Customers conflict: Customers CRM 31 customers 2026-07 | Customers invoiced 29 customers 2026-07",
        "Gross margin conflict: Gross margin operational 74 % 2026-Q2 | Gross margin fully loaded 70 % 2026-Q2",
        "CAC payback conflict: CAC payback reported 4.3 months 2026-Q2 | CAC payback recalculated 5.5 months 2026-Q2",
        "Warehouse count: 14 sites 2026-Q2",
        "SKUs: 12000 items 2026-Q2",
        "API calls: 900000 calls 2026-07",
        "Routes optimized: 1800 routes 2026-07",
    )
    assert response.gap_codes == (
        "metric_conflict_cac_payback",
        "metric_conflict_customers",
        "metric_conflict_gross_margin",
        "metric_conflict_mrr",
    )
    assert tuple(ref.cell for ref in metrics.refs) == (
        "B4",
        "B8",
        "C4",
        "C8",
        "D12",
        "D13",
        "E9",
        "E10",
        "A1",
        "A2",
        "A3",
        "A4",
    )


def test_deterministic_extractor_uses_tariff_header_context_across_split_fragments_with_row_refs() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["pricing_revenue_model"],
            fragments=[
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333335",
                    "text_hash": _hash("9"),
                    "locator_hash": _hash("a"),
                    "text": "Тариф Ежемесячно Разовый запуск Включено",
                },
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333336",
                    "text_hash": _hash("c"),
                    "locator_hash": _hash("d"),
                    "text": "Starter 240 000 ₸ 0 базовая аналитика",
                },
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333337",
                    "text_hash": _hash("e"),
                    "locator_hash": _hash("f"),
                    "text": "Growth 690 000 ₸ 500 000 ₸ маршрутизация и закупки",
                },
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333338",
                    "text_hash": _hash("0"),
                    "locator_hash": _hash("1"),
                    "text": "Enterprise 1 900 000 ₸ индивидуально SLA и интеграции",
                },
            ],
        ),
        disclosure_scope=None,
    )

    pricing = response.fields[0]

    assert pricing.normalized_values == (
        "Starter 240 000 ₸ 0 базовая аналитика",
        "Growth 690 000 ₸ 500 000 ₸ маршрутизация и закупки",
        "Enterprise 1 900 000 ₸ индивидуально SLA и интеграции",
    )
    assert tuple(ref.ref_id for ref in pricing.refs) == (
        UUID("33333333-3333-4333-8333-333333333336"),
        UUID("33333333-3333-4333-8333-333333333337"),
        UUID("33333333-3333-4333-8333-333333333338"),
    )


def test_deterministic_extractor_uses_subscription_tariff_header_context_for_pricing_rows() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["pricing_revenue_model"],
            fragments=[
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333345",
                    "text_hash": _hash("1"),
                    "locator_hash": _hash("2"),
                    "text": "Тариф Подписка Accepted lead Что получает школа",
                },
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333346",
                    "text_hash": _hash("3"),
                    "locator_hash": _hash("4"),
                    "text": "Starter 180 000 ₸ 30 accepted leads базовая CRM школы",
                },
                {
                    **_fragment_payload(),
                    "fragment_id": "33333333-3333-4333-8333-333333333347",
                    "text_hash": _hash("5"),
                    "locator_hash": _hash("6"),
                    "text": "Growth 390 000 ₸ 90 accepted leads аналитика и интеграции",
                },
            ],
        ),
        disclosure_scope=None,
    )

    pricing = response.fields[0]

    assert pricing.normalized_values == (
        "Starter 180 000 ₸ 30 accepted leads базовая CRM школы",
        "Growth 390 000 ₸ 90 accepted leads аналитика и интеграции",
    )


def test_deterministic_extractor_uses_segment_payment_jtbd_table_for_buyers() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["buyers"],
            text=(
                "Сегмент Job-to-be-done Платёж Первый продукт\n"
                "Частные школы снизить стоимость заявки Accepted lead кабинет школы\n"
                "Языковые центры быстрее закрывать набор Подписка CRM воронки\n"
            ),
        ),
        disclosure_scope=None,
    )

    buyers = response.fields[0]

    assert buyers.status is StartupProfileFieldStatus.SOURCE_FACT
    assert buyers.normalized_values == ("Частные школы", "Языковые центры")


def test_deterministic_extractor_rejects_tier_like_rows_without_tariff_currency_context() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["pricing_revenue_model"],
            text="Starter users get onboarded first\nGrowth plan will be discussed later",
        ),
        disclosure_scope=None,
    )

    pricing = response.fields[0]

    assert pricing.status is StartupProfileFieldStatus.INSUFFICIENT_DATA
    assert pricing.normalized_values == ()


def test_deterministic_extractor_marks_exact_eight_known_metric_conflicts_as_contradiction_with_both_refs() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["metric_pack_candidates"],
            spreadsheet_facts=[
                _spreadsheet_fact_payload_for(
                    0,
                    name="MRR CRM",
                    normalized_value="28.6m",
                    unit="KZT",
                    period="2026-07",
                    table="CRM export",
                    cell="B4",
                ),
                _spreadsheet_fact_payload_for(
                    1,
                    name="MRR bank/invoices",
                    normalized_value="27.9m",
                    unit="KZT",
                    period="2026-07",
                    table="Invoices",
                    cell="B8",
                ),
                _spreadsheet_fact_payload_for(
                    2,
                    name="Customers CRM",
                    normalized_value="31",
                    unit="customers",
                    period="2026-07",
                    table="CRM export",
                    cell="C4",
                ),
                _spreadsheet_fact_payload_for(
                    3,
                    name="Customers invoiced",
                    normalized_value="29",
                    unit="customers",
                    period="2026-07",
                    table="Invoices",
                    cell="C8",
                ),
                _spreadsheet_fact_payload_for(
                    4,
                    name="Gross margin operational",
                    normalized_value="74",
                    unit="%",
                    period="2026-Q2",
                    table="P&L",
                    cell="D12",
                ),
                _spreadsheet_fact_payload_for(
                    5,
                    name="Gross margin fully loaded",
                    normalized_value="70",
                    unit="%",
                    period="2026-Q2",
                    table="P&L",
                    cell="D13",
                ),
                _spreadsheet_fact_payload_for(
                    6,
                    name="CAC payback reported",
                    normalized_value="4.3",
                    unit="months",
                    period="2026-Q2",
                    table="Unit economics",
                    cell="E9",
                ),
                _spreadsheet_fact_payload_for(
                    7,
                    name="CAC payback recalculated",
                    normalized_value="5.5",
                    unit="months",
                    period="2026-Q2",
                    table="Unit economics",
                    cell="E10",
                ),
            ],
        ),
        disclosure_scope=None,
    )

    metrics = response.fields[0]

    assert metrics.status is StartupProfileFieldStatus.CONTRADICTION
    assert metrics.reason_code == "metric_conflicts_detected"
    assert metrics.normalized_values == (
        "MRR conflict: MRR CRM 28.6m KZT 2026-07 | MRR bank/invoices 27.9m KZT 2026-07",
        "Customers conflict: Customers CRM 31 customers 2026-07 | Customers invoiced 29 customers 2026-07",
        "Gross margin conflict: Gross margin operational 74 % 2026-Q2 | Gross margin fully loaded 70 % 2026-Q2",
        "CAC payback conflict: CAC payback reported 4.3 months 2026-Q2 | CAC payback recalculated 5.5 months 2026-Q2",
    )
    assert tuple(ref.cell for ref in metrics.refs) == ("B4", "B8", "C4", "C8", "D12", "D13", "E9", "E10")
    assert response.gap_codes == (
        "metric_conflict_cac_payback",
        "metric_conflict_customers",
        "metric_conflict_gross_margin",
        "metric_conflict_mrr",
    )


def test_deterministic_extractor_pairs_first_distinct_metric_values_when_duplicate_precedes_competitor() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            allowed_field_names=["metric_pack_candidates"],
            spreadsheet_facts=[
                _spreadsheet_fact_payload_for(
                    0,
                    name="MRR CRM",
                    normalized_value="28.6m",
                    unit="KZT",
                    period="2026-07",
                    table="CRM export",
                    cell="B4",
                ),
                _spreadsheet_fact_payload_for(
                    1,
                    name="MRR forecast duplicate",
                    normalized_value="28.6m",
                    unit="KZT",
                    period="2026-07",
                    table="Forecast",
                    cell="B5",
                ),
                _spreadsheet_fact_payload_for(
                    2,
                    name="MRR bank/invoices",
                    normalized_value="27.9m",
                    unit="KZT",
                    period="2026-07",
                    table="Invoices",
                    cell="B8",
                ),
            ],
        ),
        disclosure_scope=None,
    )

    metrics = response.fields[0]

    assert metrics.status is StartupProfileFieldStatus.CONTRADICTION
    assert metrics.normalized_values == (
        "MRR conflict: MRR CRM 28.6m KZT 2026-07 | MRR bank/invoices 27.9m KZT 2026-07",
    )
    assert tuple(ref.cell for ref in metrics.refs) == ("B4", "B8")
    assert response.gap_codes == ("metric_conflict_mrr",)


def test_deterministic_extractor_does_not_promote_generic_prose_to_source_backed_one_line_description() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            text=(
                "Our team helps finance leaders save time with operational automation.\n"
                "Problem: finance teams reconcile reports manually."
            ),
            allowed_field_names=["one_line_description"],
        ),
        disclosure_scope=None,
    )

    description = next(
        field for field in response.fields if field.field_name is StartupProfileFieldName.ONE_LINE_DESCRIPTION
    )

    assert description.normalized_values == ()
    assert description.status is StartupProfileFieldStatus.INSUFFICIENT_DATA
    assert description.refs == ()
    assert description.confidence == Decimal(0)


def test_deterministic_extractor_skips_oversized_labeled_value_with_gap_not_truncation() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(text=f"Problem: {'x' * 260}"),
        disclosure_scope=None,
    )

    problem = next(field for field in response.fields if field.field_name is StartupProfileFieldName.PROBLEM)
    assert problem.status is StartupProfileFieldStatus.INSUFFICIENT_DATA
    assert problem.normalized_values == ()
    assert response.gap_codes == ("deterministic_value_too_long",)


def test_deterministic_extractor_caps_spreadsheet_metrics_and_keeps_refs_aligned() -> None:
    response = DeterministicStartupProfileExtractor().extract(
        _request(
            spreadsheet_facts=[
                _spreadsheet_fact_payload(index)
                for index in range(MAX_VALUES_PER_FIELD + 2)
            ],
        ),
        disclosure_scope=None,
    )

    by_name = {field.field_name: field for field in response.fields}
    traction = by_name[StartupProfileFieldName.TRACTION]
    metric_pack = by_name[StartupProfileFieldName.METRIC_PACK_CANDIDATES]
    expected_values = tuple(f"Metric {index}: {1000 + index} USD 2026" for index in range(MAX_VALUES_PER_FIELD))
    expected_ref_ids = tuple(UUID(int=0x44444444444444448444000000000000 + index) for index in range(MAX_VALUES_PER_FIELD))

    assert traction.normalized_values == expected_values
    assert tuple(ref.ref_id for ref in traction.refs) == expected_ref_ids
    assert metric_pack.normalized_values == expected_values
    assert tuple(ref.ref_id for ref in metric_pack.refs) == expected_ref_ids
    assert response.gap_codes == ("deterministic_spreadsheet_metrics_truncated",)


def _request(
    *,
    text: str = "Startup Name: Acme",
    allowed_field_names: list[str] | None = None,
    spreadsheet_facts: list[dict[str, object]] | None = None,
    fragments: list[dict[str, object]] | None = None,
) -> StartupProfileExtractionRequest:
    return StartupProfileExtractionRequest.model_validate(
        _request_payload(
            text=text,
            allowed_field_names=allowed_field_names,
            spreadsheet_facts=spreadsheet_facts,
            fragments=fragments,
        )
    )


def _request_payload(
    *,
    text: str = "Startup Name: Acme",
    allowed_field_names: list[str] | None = None,
    spreadsheet_facts: list[dict[str, object]] | None = None,
    fragments: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "startup_profile_extraction_request@1",
        "case_id": str(CASE_ID),
        "data_revision": 1,
        "allowed_field_names": allowed_field_names
        if allowed_field_names is not None
        else ["startup_name", "problem", "traction", "metric_pack_candidates"],
        "fragments": fragments if fragments is not None else [{**_fragment_payload(), "text": text}],
        "spreadsheet_facts": spreadsheet_facts or [],
        "source_hashes": [_hash("a")],
        "egress_policy_version": "egress@1",
        "redaction_policy_version": "rules-redactor@1",
    }


def _fragment_payload() -> dict[str, object]:
    return {
        "fragment_id": str(FRAGMENT_ID),
        "artifact_id": str(ARTIFACT_ID),
        "text": "Startup Name: Acme",
        "text_hash": _hash("b"),
        "artifact_hash": _hash("a"),
        "locator_hash": _hash("c"),
        "sensitivity": "public",
        "redacted": True,
        "minimized": True,
        "redaction_policy_version": "rules-redactor@1",
    }


def _safe_ref() -> StartupProfileSafeRef:
    return StartupProfileSafeRef(
        ref_type="fragment",
        ref_id=FRAGMENT_ID,
        artifact_id=ARTIFACT_ID,
        artifact_hash=_hash("a"),
        locator_hash=_hash("c"),
        page=1,
        confidence=Decimal("0.9"),
    )


def _spreadsheet_fact_payload(index: int) -> dict[str, object]:
    return _spreadsheet_fact_payload_for(
        index,
        name=f"Metric {index}",
        normalized_value=str(1000 + index),
        unit="USD",
        period="2026",
        table="metrics",
        cell=f"B{index + 2}",
    )


def _spreadsheet_fact_payload_for(
    index: int,
    *,
    name: str,
    normalized_value: str,
    unit: str,
    period: str,
    table: str,
    cell: str,
) -> dict[str, object]:
    return {
        "evidence_fact_id": str(UUID(int=0x44444444444444448444000000000000 + index)),
        "artifact_id": str(ARTIFACT_ID),
        "name": name,
        "value_type": "decimal",
        "normalized_value": normalized_value,
        "unit": unit,
        "period": period,
        "confidence": "0.91",
        "sensitivity": "public",
        "artifact_hash": _hash("a"),
        "locator_hash": _hash("c"),
        "table": table,
        "cell": cell,
    }


def _hash(char: str) -> str:
    return f"sha256:{char * 64}"
