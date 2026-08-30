from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.application.services.claim_evidence_service import ClaimEvidenceService
from due_diligence_agent.application.services.claim_extraction_service import ClaimExtractionService
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import ContradictionStatus, SensitivityClass
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import (
    ClaimCategory,
    ClaimCriticality,
    ClaimStatus,
    StartupClaim,
)
from due_diligence_agent.domain.findings.models import Contradiction


def test_claim_is_contradicted_when_primary_calculation_disagrees() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.ARR,
        value=Decimal("2400000"),
        unit="USD",
        period="2025",
    )
    workbook_fact = _fact(
        artifact_id=artifact_id,
        name="arr",
        value=Decimal("1800000"),
        unit="USD",
        period="2025",
        source_priority=SourcePriority.SYSTEM_EXPORT,
    )
    calculation = _calculation(
        case_id=case_id,
        metric_name="arr",
        value=Decimal("1800000"),
        unit="USD",
        period="2025",
        input_fact_ids=(workbook_fact.id,),
    )

    matrix = ClaimEvidenceService().build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[workbook_fact],
        calculations=[calculation],
    )

    row = matrix.rows[0]
    assert row.status is ClaimStatus.CONTRADICTED
    assert row.links[0].relation == "contradicts"
    assert row.contradictions
    assert row.executive_summary_eligible is False


def test_unsupported_critical_claim_cannot_be_reported_as_fact() -> None:
    case_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=uuid4(),
        category=ClaimCategory.CUSTOMER_COUNT,
        value=Decimal("120"),
        unit="count",
        period="2025",
        criticality=ClaimCriticality.CRITICAL,
    )

    row = ClaimEvidenceService().build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[],
        calculations=[],
    ).rows[0]

    assert row.status is ClaimStatus.UNSUPPORTED
    assert row.executive_summary_eligible is False
    assert row.links[0].relation == "missing"


def test_claim_exact_match_is_verified_and_summary_eligible() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.GROSS_MARGIN,
        value=Decimal("62"),
        unit="percent",
        period="2025",
    )
    fact = _fact(
        artifact_id=artifact_id,
        name="gross_margin",
        value=Decimal("62.000"),
        unit="percent",
        period="2025",
        source_priority=SourcePriority.SYSTEM_EXPORT,
    )

    row = ClaimEvidenceService().build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[fact],
        calculations=[],
    ).rows[0]

    assert row.status is ClaimStatus.VERIFIED
    assert row.links[0].relation == "supports"
    assert row.executive_summary_eligible is True


def test_secondary_match_for_critical_financial_claim_is_partial() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.RUNWAY,
        value=Decimal("9.5"),
        unit="months",
        period="2025-Q2",
    )
    fact = _fact(
        artifact_id=artifact_id,
        name="runway",
        value=Decimal("9.5"),
        unit="months",
        period="2025-Q2",
        source_priority=SourcePriority.MANAGEMENT_NARRATIVE,
    )

    row = ClaimEvidenceService().build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[fact],
        calculations=[],
    ).rows[0]

    assert row.status is ClaimStatus.PARTIALLY_VERIFIED
    assert row.links[0].relation == "partially_supports"
    assert row.executive_summary_eligible is False


def test_fact_with_wrong_metric_identity_is_not_linked_by_value_substring() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.CUSTOMER_COUNT,
        value=Decimal("120"),
        unit="count",
        period="2025",
    )
    mismatched_fact = _fact(
        artifact_id=artifact_id,
        name="marketing_leads",
        value=Decimal("120"),
        unit="count",
        period="2025",
        source_priority=SourcePriority.SYSTEM_EXPORT,
    )

    row = ClaimEvidenceService().build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[mismatched_fact],
        calculations=[],
    ).rows[0]

    assert row.status is ClaimStatus.UNSUPPORTED
    assert row.links[0].relation == "missing"


def test_duplicate_evidence_does_not_create_duplicate_links() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    fact_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.ARR,
        value=Decimal("1800000"),
        unit="USD",
        period="2025",
    )
    fact = _fact(
        fact_id=fact_id,
        artifact_id=artifact_id,
        name="arr",
        value=Decimal("1800000"),
        unit="USD",
        period="2025",
        source_priority=SourcePriority.SYSTEM_EXPORT,
    )

    row = ClaimEvidenceService().build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[fact, fact],
        calculations=[],
    ).rows[0]

    assert [link.evidence_fact_id for link in row.links] == [fact_id]


def test_startup_claim_serialization_contains_only_safe_refs_and_canonical_query() -> None:
    raw_text = "Acme Health has ARR $2400000 from jane@acme.example and customer MegaBank"
    raw_query = "Acme Health ARR $2400000 jane@acme.example MegaBank"

    claim = StartupClaim.from_raw_text(
        id=uuid4(),
        case_id=uuid4(),
        raw_text=raw_text,
        category=ClaimCategory.ARR,
        source_artifact_id=uuid4(),
        locator=SourceLocator(kind="deck_text", value="slide:1"),
        criticality=ClaimCriticality.CRITICAL,
        raw_evidence_query=raw_query,
        normalized_name="arr",
        normalized_value=Decimal("2400000"),
        unit="USD",
        period="2025",
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.90"),
        extracted_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

    payload = repr(claim) + claim.model_dump_json()

    for leaked in ("Acme", "MegaBank", "jane@", "2400000", "$2400000", raw_text, raw_query):
        assert leaked not in payload
    assert claim.text_ref == claim.text_hash
    assert claim.evidence_query == "arr 2025"


def test_direct_startup_claim_rejects_noncanonical_evidence_queries() -> None:
    base = {
        "id": uuid4(),
        "case_id": uuid4(),
        "text_ref": "d" * 64,
        "text_hash": "d" * 64,
        "category": ClaimCategory.ARR,
        "source_artifact_id": uuid4(),
        "locator": SourceLocator(kind="deck_text", value="slide:1"),
        "criticality": ClaimCriticality.CRITICAL,
        "normalized_name": "arr",
        "normalized_value": Decimal("2400000"),
        "unit": "USD",
        "period": "2025",
        "sensitivity": SensitivityClass.CONFIDENTIAL,
        "confidence": Decimal("0.9"),
        "extracted_at": datetime(2026, 8, 9, 12, tzinfo=UTC),
    }

    accepted = StartupClaim(evidence_query="arr 2025", **base)
    assert accepted.model_dump()["evidence_query"] == "arr 2025"

    for raw_query in (
        "acme megabank customer concentration",
        "founder@example.com arr 2025",
        "jane founder arr",
        "arr 2025 2400000",
        "arr $2400000 2025",
        "arr q4 2025",
    ):
        try:
            StartupClaim(evidence_query=raw_query, **base)
        except ValueError as exc:
            assert "invalid canonical evidence query" in str(exc)
        else:
            raise AssertionError(f"noncanonical query was accepted: {raw_query}")


def test_other_claim_category_uses_literal_other_query() -> None:
    claim = StartupClaim(
        id=uuid4(),
        case_id=uuid4(),
        text_ref="d" * 64,
        text_hash="d" * 64,
        category=ClaimCategory.OTHER,
        source_artifact_id=uuid4(),
        locator=SourceLocator(kind="deck_text", value="slide:1"),
        criticality=ClaimCriticality.LOW,
        evidence_query="other",
        normalized_name="acme megabank customer concentration",
        normalized_value=None,
        unit=None,
        period=None,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.6"),
        extracted_at=datetime(2026, 8, 9, 12, tzinfo=UTC),
    )

    assert claim.model_dump()["evidence_query"] == "other"


def test_extraction_item_raw_fields_are_transient_and_excluded_from_serialization() -> None:
    from due_diligence_agent.domain.evidence.startup_claims import ClaimExtractionItem

    item = ClaimExtractionItem(
        text="Founder email founder@example.com says ARR is $2400000",
        category=ClaimCategory.ARR,
        source_artifact_id=uuid4(),
        locator=SourceLocator(kind="deck_text", value="slide:1"),
        criticality=ClaimCriticality.CRITICAL,
        evidence_query="founder@example.com ARR $2400000",
        normalized_name="arr",
        normalized_value=Decimal("2400000"),
        unit="USD",
        period="2025",
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.75"),
    )

    payload = repr(item) + item.model_dump_json()

    assert "founder@example.com" not in payload
    assert "$2400000" not in payload
    assert "2400000" not in payload


def test_fixture_claim_extractor_captures_all_frozen_unsupported_business_claims_safely() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    raw_text = (
        "Founder statement says procurement cycle reduction is 60 percent. "
        "Regulation-driven demand is accelerating without a cited source. "
        "Churn reduction reached 42 percent without a cohort. "
        "Conversion benchmark superiority is claimed without a source. "
        "Regulation-driven demand is repeated without new evidence."
    )
    locator = SourceLocator(kind="docx_paragraph", value="paragraph:1", artifact_id=artifact_id)
    extractor = ClaimExtractionService()

    claims = extractor.extract_fixture_claims(
        case_id=case_id,
        artifact_id=artifact_id,
        text=raw_text,
        locator=locator,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        period="unknown",
    )
    repeated = extractor.extract_fixture_claims(
        case_id=case_id,
        artifact_id=artifact_id,
        text=raw_text,
        locator=locator,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        period="unknown",
    )

    assert [claim.normalized_name for claim in claims] == [
        "procurement_cycle_reduction",
        "regulation_driven_demand",
        "churn_reduction",
        "conversion_benchmark_superiority",
    ]
    assert all(claim.category is ClaimCategory.OTHER for claim in claims)
    assert [claim.normalized_value for claim in claims] == [
        Decimal("60"),
        None,
        Decimal("42"),
        None,
    ]
    assert [(claim.text_ref, claim.text_hash) for claim in claims] == [
        (claim.text_ref, claim.text_hash) for claim in repeated
    ]
    assert all(claim.text_ref == claim.text_hash for claim in claims)

    payload = " ".join(claim.model_dump_json() for claim in claims)
    assert "Founder statement" not in payload
    assert "without a cited source" not in payload
    assert "without a cohort" not in payload
    assert "without a source" not in payload


def test_fixture_claim_extractor_keeps_financial_table_metrics_line_scoped() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    raw_text = "\n".join(
        (
            "MRR CONTRADICTION CRM 28,6 млн ₸; invoices 27,9 млн ₸",
            "Gross margin CONTRADICTION 74% operational; 70% fully loaded",
            "CAC payback CONTRADICTION 4,3 мес. заявлено; 5,5 мес. пересчет",
            "net burn за последние три месяца: 22,4 млн ₸",
            "runway: 7,8 месяца",
        )
    )
    locator = SourceLocator(kind="pdf_table", value="page:14/table:1", artifact_id=artifact_id)

    claims = ClaimExtractionService().extract_fixture_claims(
        case_id=case_id,
        artifact_id=artifact_id,
        text=raw_text,
        locator=locator,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        period="2026-06",
    )

    extracted = [
        (claim.normalized_name, claim.normalized_value, claim.unit, claim.period)
        for claim in claims
    ]
    assert extracted == [
        ("monthly_recurring_revenue", Decimal("28600000.0"), "KZT", "2026-06"),
        ("monthly_recurring_revenue", Decimal("27900000.0"), "KZT", "2026-06"),
        ("gross_margin", Decimal("74"), "percent", "2026-06"),
        ("gross_margin", Decimal("70"), "percent", "2026-06"),
        ("cac_payback", Decimal("4.3"), "months", "2026-06"),
        ("cac_payback", Decimal("5.5"), "months", "2026-06"),
        ("monthly_net_burn", Decimal("22400000.0"), "KZT/month", "2026-06"),
        ("runway", Decimal("7.8"), "months", "2026-06"),
    ]


def test_fixture_claim_extractor_reads_resolved_mrr_from_advisor_answer() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    locator = SourceLocator(kind="docx_paragraph", value="paragraph:1", artifact_id=artifact_id)

    claims = ClaimExtractionService().extract_fixture_claims(
        case_id=case_id,
        artifact_id=artifact_id,
        text=(
            "Revenue Model: Use bank and invoice register for June 2026: "
            "recognized MRR is 27.9m KZT; exclude CRM-only free-extension accounts."
        ),
        locator=locator,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        period="2026-06",
    )

    assert [
        (claim.normalized_name, claim.normalized_value, claim.unit, claim.period)
        for claim in claims
    ] == [
        ("monthly_recurring_revenue", Decimal("27900000.0"), "KZT", "2026-06"),
    ]


def test_fixture_claim_extractor_rejects_forward_looking_runway_targets() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    raw_text = "\n".join(
        (
            "Current mechanical runway: 7.8 months.",
            "Target runway after Seed round: 18 months.",
            "Прогноз runway после привлечения: 24 месяца.",
        )
    )
    locator = SourceLocator(kind="text", value="page:1", artifact_id=artifact_id)

    claims = ClaimExtractionService().extract_fixture_claims(
        case_id=case_id,
        artifact_id=artifact_id,
        text=raw_text,
        locator=locator,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        period="2026-06",
    )

    runway_values = [
        claim.normalized_value
        for claim in claims
        if claim.normalized_name == "runway"
    ]
    assert runway_values == [Decimal("7.8")]


def test_contradicted_claim_persists_domain_contradiction_with_stable_id() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    repo = _ContradictionRepository()
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.ARR,
        value=Decimal("2400000"),
        unit="USD",
        period="2025",
    )
    fact = _fact(
        artifact_id=artifact_id,
        name="arr",
        value=Decimal("1800000"),
        unit="USD",
        period="2025",
        source_priority=SourcePriority.SYSTEM_EXPORT,
    )

    first = ClaimEvidenceService(contradiction_repository=repo).build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[fact],
        calculations=[],
    )
    second = ClaimEvidenceService(contradiction_repository=repo).build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[fact],
        calculations=[],
    )

    row = first.rows[0]
    assert isinstance(row.contradictions[0], Contradiction)
    assert row.contradiction_ids == (row.contradictions[0].id,)
    assert row.contradictions[0].case_id == case_id
    assert row.contradictions[0].status is ContradictionStatus.OPEN
    assert row.contradictions[0].fact_ids == (fact.id,)
    assert row.contradictions[0].id == second.rows[0].contradictions[0].id
    assert len(repo.items) == 1


def test_contradiction_without_repository_is_deterministic_with_injected_clock() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    detected_at = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.ARR,
        value=Decimal("2400000"),
        unit="USD",
        period="2025",
    )
    fact = _fact(
        artifact_id=artifact_id,
        name="arr",
        value=Decimal("1800000"),
        unit="USD",
        period="2025",
        source_priority=SourcePriority.SYSTEM_EXPORT,
    )
    service = ClaimEvidenceService(clock=lambda: detected_at)

    first = service.build(case_id=case_id, claims=[claim], evidence_facts=[fact]).rows[0]
    second = service.build(case_id=case_id, claims=[claim], evidence_facts=[fact]).rows[0]

    assert first.contradictions == second.contradictions
    assert first.contradictions[0].detected_at == detected_at


def test_claim_case_mismatch_fails_before_matrix_rows_are_returned() -> None:
    claim = _claim(
        case_id=uuid4(),
        artifact_id=uuid4(),
        category=ClaimCategory.ARR,
        value=Decimal("100"),
        unit="USD",
        period="2025",
    )

    try:
        ClaimEvidenceService().build(
            case_id=uuid4(),
            claims=[claim],
            evidence_facts=[],
        )
    except ValueError as exc:
        assert str(exc) == "claim_case_mismatch"
    else:
        raise AssertionError("claim from another case should fail closed")


def test_calculation_case_mismatch_fails_before_matching() -> None:
    case_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=uuid4(),
        category=ClaimCategory.ARR,
        value=Decimal("100"),
        unit="USD",
        period="2025",
    )
    calculation = _calculation(
        case_id=uuid4(),
        metric_name="arr",
        value=Decimal("100"),
        unit="USD",
        period="2025",
        input_fact_ids=(),
    )

    try:
        ClaimEvidenceService().build(
            case_id=case_id,
            claims=[claim],
            evidence_facts=[],
            calculations=[calculation],
        )
    except ValueError as exc:
        assert str(exc) == "calculation_case_mismatch"
    else:
        raise AssertionError("calculation from another case should fail closed")


def test_count_claims_require_exact_match_not_global_decimal_tolerance() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.CUSTOMER_COUNT,
        value=Decimal("120"),
        unit="count",
        period="2025",
    )
    fact = _fact(
        artifact_id=artifact_id,
        name="customer_count",
        value=Decimal("120.005"),
        unit="count",
        period="2025",
        source_priority=SourcePriority.SYSTEM_EXPORT,
    )

    row = ClaimEvidenceService().build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[fact],
    ).rows[0]

    assert row.status is ClaimStatus.CONTRADICTED


def test_currency_claims_use_relative_and_absolute_tolerance_policy() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.ARR,
        value=Decimal("2400000"),
        unit="USD",
        period="2025",
    )
    rounded_fact = _fact(
        artifact_id=artifact_id,
        name="arr",
        value=Decimal("2405000"),
        unit="USD",
        period="2025",
        source_priority=SourcePriority.SYSTEM_EXPORT,
    )

    row = ClaimEvidenceService().build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[rounded_fact],
    ).rows[0]

    assert row.status is ClaimStatus.VERIFIED


def test_incompatible_units_are_rejected_before_tolerance_matching() -> None:
    case_id = uuid4()
    artifact_id = uuid4()
    claim = _claim(
        case_id=case_id,
        artifact_id=artifact_id,
        category=ClaimCategory.RUNWAY,
        value=Decimal("9"),
        unit="months",
        period="2025-Q2",
    )
    fact = _fact(
        artifact_id=artifact_id,
        name="runway",
        value=Decimal("9"),
        unit="weeks",
        period="2025-Q2",
        source_priority=SourcePriority.SYSTEM_EXPORT,
    )

    row = ClaimEvidenceService().build(
        case_id=case_id,
        claims=[claim],
        evidence_facts=[fact],
    ).rows[0]

    assert row.status is ClaimStatus.INSUFFICIENT_DATA


def _claim(
    *,
    case_id,
    artifact_id,
    category: ClaimCategory,
    value: Decimal,
    unit: str,
    period: str,
    criticality: ClaimCriticality = ClaimCriticality.CRITICAL,
) -> StartupClaim:
    return StartupClaim(
        id=uuid4(),
        case_id=case_id,
        text_ref="d" * 64,
        text_hash="d" * 64,
        category=category,
        source_artifact_id=artifact_id,
        locator=SourceLocator(kind="deck_text", value="slide:1", artifact_id=artifact_id),
        criticality=criticality,
        evidence_query=f"{category.value} {period}",
        normalized_name=category.value,
        normalized_value=value,
        unit=unit,
        period=period,
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.90"),
        extracted_at=datetime(2026, 8, 9, tzinfo=UTC),
    )


class _ContradictionRepository:
    def __init__(self) -> None:
        self.items: list[Contradiction] = []

    def add(self, contradiction: Contradiction) -> None:
        self.items.append(contradiction)

    def list_for_case(self, case_id) -> list[Contradiction]:
        return [item for item in self.items if item.case_id == case_id]


def _fact(
    *,
    artifact_id,
    name: str,
    value: Decimal,
    unit: str,
    period: str,
    source_priority: int,
    fact_id=None,
) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id or uuid4(),
        artifact_id=artifact_id,
        name=name,
        value=value,
        value_type="decimal",
        unit=unit,
        period=period,
        locator=SourceLocator(kind="xlsx_cell", value="P&L!C12", artifact_id=artifact_id),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.95"),
        source_priority=source_priority,
        extraction_method="spreadsheet",
        supporting_text_hash="a" * 64,
        retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
    )


def _calculation(
    *,
    case_id,
    metric_name: str,
    value: Decimal,
    unit: str,
    period: str,
    input_fact_ids: tuple,
) -> Calculation:
    return Calculation(
        id=uuid4(),
        case_id=case_id,
        metric_name=metric_name,
        formula_version=f"{metric_name}@1",
        input_fact_ids=input_fact_ids,
        value=value,
        unit=unit,
        period=period,
        warnings=(),
        calculated_at=datetime(2026, 8, 9, tzinfo=UTC),
        sensitivity=SensitivityClass.PUBLIC,
    )
