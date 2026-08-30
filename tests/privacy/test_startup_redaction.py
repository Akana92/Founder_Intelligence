from __future__ import annotations

from decimal import Decimal
from dataclasses import dataclass
import socket
from uuid import uuid4

import pytest
from pydantic import ValidationError

from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore
from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.adapters.privacy.presidio_redactor import PresidioRedactor
from due_diligence_agent.adapters.privacy.rules_redactor import RulesRedactor
from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
from due_diligence_agent.application.services.startup_privacy_service import StartupPrivacyService
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.documents.models import TextBlock
from due_diligence_agent.domain.documents.tabular import NormalizedCell, NormalizedTable
from due_diligence_agent.domain.privacy.models import DisclosurePreview, RedactedContext


RAW_EMAIL = "john@example.com"
RAW_TOKEN = "Bearer sk-proj-secret-123"
RAW_IBAN = "KZ86125KZT5004100100"
RAW_PHONE = "+1 415 555 0199"
RAW_NAME = "Aigerim Tuleubayeva"
RAW_PRIVATE_LABEL = "Bearer sk-proj-label-123/customer@email.test/C:/vault"


@pytest.fixture
def startup_privacy_service(tmp_path) -> StartupPrivacyService:
    return StartupPrivacyService(
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        redactor=RulesRedactor(),
        egress_policy=DataEgressPolicy(),
        trace_sanitizer=StrictTraceSanitizer(),
    )


def test_highest_sensitivity_wins_for_mixed_table(startup_privacy_service: StartupPrivacyService) -> None:
    table = _table(
        [
            _cell(label="customer_email", value=RAW_EMAIL, row=1),
            _cell(label="arr", value=Decimal("1200000"), row=2),
        ]
    )

    summary = startup_privacy_service.classify(table, source_sensitivity=SensitivityClass.PUBLIC)

    assert summary.overall_class == SensitivityClass.RESTRICTED
    assert sorted(summary.field_classes.values()) == [
        SensitivityClass.PUBLIC,
        SensitivityClass.RESTRICTED,
    ]
    assert summary.category_counts["email"] == 1
    assert "customer_email" not in summary.model_dump_json()
    assert RAW_EMAIL not in summary.model_dump_json()
    assert "SensitivityClass" not in summary.model_dump_json()


def test_disclosure_preview_contains_categories_not_values(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    block = _stored_text_block(
        startup_privacy_service,
        f"Founder email {RAW_EMAIL}; bank account {RAW_IBAN}; auth {RAW_TOKEN}",
    )

    preview = startup_privacy_service.build_preview([block], source_sensitivity=SensitivityClass.PUBLIC)
    serialized = preview.model_dump_json()

    assert isinstance(preview, DisclosurePreview)
    assert preview.category_counts["email"] == 1
    assert preview.category_counts["banking"] == 1
    assert preview.category_counts["secret"] == 1
    assert RAW_EMAIL not in serialized
    assert RAW_IBAN not in serialized
    assert RAW_TOKEN not in serialized
    assert "[REDACTED:email:1]" in serialized
    assert "john@" not in repr(preview)


def test_public_source_redacted_context_stores_safe_confidential_refs_and_never_serializes_raw_pii(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    blocks = [
        _stored_text_block(startup_privacy_service, f"Customer {RAW_EMAIL} signed with phone {RAW_PHONE}"),
        _stored_text_block(startup_privacy_service, "Public ARR was USD 1200000"),
    ]

    context = startup_privacy_service.redact_context(blocks, source_sensitivity=SensitivityClass.PUBLIC)
    serialized = context.model_dump_json()

    assert isinstance(context, RedactedContext)
    assert context.sensitivity == SensitivityClass.CONFIDENTIAL
    assert len(context.fragment_ids) == 2
    assert len(context.local_text_refs) == 2
    assert context.redaction_counts["email"] == 1
    assert context.redaction_counts["phone"] == 1
    assert RAW_EMAIL not in serialized
    assert RAW_PHONE not in serialized
    assert RAW_EMAIL not in repr(context)
    stored_payloads = [
        startup_privacy_service.artifact_store.read_bytes(text_ref).decode("utf-8")
        for text_ref in context.local_text_refs
    ]
    assert any("[REDACTED:email:1]" in payload for payload in stored_payloads)
    assert any("[REDACTED:phone:1]" in payload for payload in stored_payloads)
    assert all(RAW_EMAIL not in payload and RAW_PHONE not in payload for payload in stored_payloads)


def test_kzt_financial_table_numbers_do_not_trigger_phone_redaction(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    block = _stored_text_block(
        startup_privacy_service,
        (
            "Base case\n"
            "49 0 38 6 33 3\n"
            "mln KZT revenue, mln KZT EBITDA, margin percent.\n"
            "School CAC\n"
            "450 250 600 10 20\n"
            "thousand KZT range and first sales count."
        ),
    )

    context = startup_privacy_service.redact_context(
        [block],
        source_sensitivity=SensitivityClass.PUBLIC,
    )
    stored_payload = startup_privacy_service.artifact_store.read_bytes(
        context.local_text_refs[0]
    ).decode("utf-8")

    assert "phone" not in context.redaction_counts
    assert "[REDACTED:phone:" not in stored_payload
    assert "49 0 38 6 33 3" in stored_payload
    assert "450 250 600 10 20" in stored_payload


def test_explicit_phone_in_financial_context_still_triggers_restricted_redaction(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    block = _stored_text_block(
        startup_privacy_service,
        f"MRR 40k KZT. Finance contact phone {RAW_PHONE}. Runway 18 months.",
    )

    context = startup_privacy_service.redact_context(
        [block],
        source_sensitivity=SensitivityClass.PUBLIC,
    )
    stored_payload = startup_privacy_service.artifact_store.read_bytes(
        context.local_text_refs[0]
    ).decode("utf-8")

    assert context.redaction_counts["phone"] == 1
    assert RAW_PHONE not in stored_payload
    assert "[REDACTED:phone:" in stored_payload


@pytest.mark.parametrize("label", ["Phone", "Телефон"])
def test_plain_phone_with_explicit_label_in_financial_context_is_redacted(
    startup_privacy_service: StartupPrivacyService,
    label: str,
) -> None:
    raw_phone = "415 555 0199"
    block = _stored_text_block(
        startup_privacy_service,
        f"MRR 40k KZT. {label} {raw_phone}. Runway 18 months.",
    )

    context = startup_privacy_service.redact_context(
        [block],
        source_sensitivity=SensitivityClass.PUBLIC,
    )
    stored_payload = startup_privacy_service.artifact_store.read_bytes(
        context.local_text_refs[0]
    ).decode("utf-8")

    assert context.redaction_counts["phone"] == 1
    assert raw_phone not in stored_payload
    assert "[REDACTED:phone:" in stored_payload


def test_export_preview_fails_closed_for_quasi_identifiers(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    preview = startup_privacy_service.build_preview(
        [
            _stored_text_block(
                startup_privacy_service,
                "Synthetic customer in Almaty, Kazakhstan, CFO rare logistics segment",
            ),
            _stored_text_block(startup_privacy_service, "Sensitive contact available under NDA"),
        ],
        source_sensitivity=SensitivityClass.CONFIDENTIAL,
    )

    decision = startup_privacy_service.evaluate_external_export(preview, destination="openai.responses")

    assert decision.allowed is False
    assert decision.reason == "reidentification_risk"
    assert "Almaty" not in repr(decision)


def test_trace_tool_and_exception_payloads_do_not_accept_raw_sensitive_values(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    context = startup_privacy_service.redact_context(
        [_stored_text_block(startup_privacy_service, f"token={RAW_TOKEN}")],
        source_sensitivity=SensitivityClass.PUBLIC,
    )

    attributes = startup_privacy_service.trace_attributes_for_context(context, status="ready")
    sanitized = StrictTraceSanitizer().sanitize_attributes(attributes)

    assert sanitized["redaction_policy_version"] == startup_privacy_service.policy_version
    assert sanitized["chunk_count"] == 1
    assert RAW_TOKEN not in repr(sanitized)
    with pytest.raises(ValueError, match="trace_attribute"):
        StrictTraceSanitizer().sanitize_attributes({"payload": RAW_TOKEN})
    with pytest.raises(ValidationError):
        RedactedContext(
            fragment_ids=context.fragment_ids,
            local_text_refs=context.local_text_refs,
            sensitivity=context.sensitivity,
            redaction_counts=context.redaction_counts,
            content_hash=context.content_hash,
            raw_text=RAW_TOKEN,
        )


def test_presidio_adapter_is_optional_lazy_and_cannot_downgrade_rules(monkeypatch) -> None:
    adapter = PresidioRedactor(local_model_path=None)
    rules = RulesRedactor()
    text = f"Contact {RAW_EMAIL}. Public market size is 1B."

    monkeypatch.setattr(adapter, "_load_analyzer", lambda: None)
    result = adapter.detect(text, existing=rules.detect(text))

    assert result.available is False
    assert result.reason == "presidio_unavailable"
    assert result.detections[0].category == "email"
    assert result.sensitivity == SensitivityClass.RESTRICTED
    assert RAW_EMAIL not in repr(result)


def test_presidio_only_detection_is_redacted_from_preview_and_stored_context(tmp_path) -> None:
    service = StartupPrivacyService(
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        redactor=RulesRedactor(presidio_redactor=PresidioRedactor(
            local_model_path=tmp_path,
            analyzer_factory=lambda: _FakeAnalyzer([_AnalyzerResult("PERSON", 8, 26)]),
        )),
        egress_policy=DataEgressPolicy(),
        trace_sanitizer=StrictTraceSanitizer(),
    )
    block = _stored_text_block(service, f"Founder {RAW_NAME} owns pricing strategy")

    preview = service.build_preview([block], source_sensitivity=SensitivityClass.PUBLIC)
    context = service.redact_context([block], source_sensitivity=SensitivityClass.PUBLIC)
    stored_payload = service.artifact_store.read_bytes(context.local_text_refs[0]).decode("utf-8")

    assert preview.category_counts["person_name"] == 1
    assert "[REDACTED:person_name:1]" in preview.model_dump_json()
    assert "[REDACTED:person_name:1]" in stored_payload
    for surface in (preview.model_dump_json(), repr(preview), context.model_dump_json(), repr(context), stored_payload):
        assert RAW_NAME not in surface


def test_presidio_factory_runs_under_no_network_and_returns_safe_unavailable(tmp_path) -> None:
    def network_attempting_factory() -> object:
        socket.create_connection(("example.com", 443), timeout=0.01)
        return _FakeAnalyzer([])

    adapter = PresidioRedactor(local_model_path=tmp_path, analyzer_factory=network_attempting_factory)
    existing = RulesRedactor().detect("No deterministic PII")

    result = adapter.detect("No deterministic PII", existing=existing)

    assert result.available is False
    assert result.reason == "presidio_unavailable"
    assert "example.com" not in repr(result)
    assert "socket" not in repr(result)


def test_presidio_unusual_exceptions_are_typed_unavailable_without_leaking(tmp_path) -> None:
    def failing_factory() -> object:
        raise RuntimeError(f"boom {RAW_TOKEN}")

    adapter = PresidioRedactor(local_model_path=tmp_path, analyzer_factory=failing_factory)
    result = adapter.detect("plain text", existing=RulesRedactor().detect("plain text"))

    assert result.available is False
    assert result.reason == "presidio_unavailable"
    assert RAW_TOKEN not in repr(result)


def test_sensitive_field_labels_are_replaced_by_stable_safe_ids(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    table = _table(
        [
            _cell(label=RAW_PRIVATE_LABEL, value="non-pii internal value", row=1),
            _cell(label=f"{RAW_PRIVATE_LABEL}#2", value=RAW_EMAIL, row=2),
            _cell(label="https://customer.example/account", value="CUST-1234", row=3),
        ]
    )

    summary = startup_privacy_service.classify(table)
    serialized = summary.model_dump_json()

    assert all(key.startswith("field_") for key in summary.field_classes)
    assert len(summary.field_classes) == 3
    for raw in (RAW_PRIVATE_LABEL, RAW_EMAIL, "customer.example", "C:/vault"):
        assert raw not in serialized
        assert raw not in repr(summary)


def test_restricted_source_without_pii_stays_restricted_and_external_egress_is_denied(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    raw = "Stealth pricing: enterprise tier starts at 24000"
    block = _stored_text_block(startup_privacy_service, raw)

    preview = startup_privacy_service.build_preview(
        [block],
        source_sensitivity=SensitivityClass.RESTRICTED,
    )
    context = startup_privacy_service.redact_context(
        [block],
        source_sensitivity=SensitivityClass.RESTRICTED,
    )
    decision = startup_privacy_service.evaluate_external_export(preview, destination="openai.responses")

    assert preview.overall_class == SensitivityClass.RESTRICTED
    assert context.sensitivity == SensitivityClass.RESTRICTED
    assert preview.category_counts["restricted_source"] == 1
    assert "[REDACTED:restricted_source:1]" in preview.model_dump_json()
    assert raw not in preview.model_dump_json()
    assert raw not in repr(preview)
    stored_payload = startup_privacy_service.artifact_store.read_bytes(context.local_text_refs[0]).decode("utf-8")
    assert stored_payload == "[REDACTED:restricted_source:1]"
    assert raw not in stored_payload
    assert decision.allowed is False
    assert decision.reason == "restricted_data"


@pytest.mark.parametrize(
    ("source_sensitivity", "raw", "expected_category", "expected_token"),
    [
        (
            SensitivityClass.INTERNAL,
            "Internal channel plan for marketplace fee experiments",
            "internal_source",
            "[REDACTED:internal_source:1]",
        ),
        (
            SensitivityClass.CONFIDENTIAL,
            "Confidential CAC model with supplier rebate assumptions",
            "confidential_source",
            "[REDACTED:confidential_source:1]",
        ),
        (
            SensitivityClass.RESTRICTED,
            f"Restricted founder contact {RAW_EMAIL} and secret partner economics",
            "restricted_source",
            "[REDACTED:restricted_source:1]",
        ),
    ],
)
def test_non_public_sources_are_whole_fragment_minimized(
    startup_privacy_service: StartupPrivacyService,
    source_sensitivity: SensitivityClass,
    raw: str,
    expected_category: str,
    expected_token: str,
) -> None:
    block = _stored_text_block(startup_privacy_service, raw)

    preview = startup_privacy_service.build_preview([block], source_sensitivity=source_sensitivity)
    context = startup_privacy_service.redact_context([block], source_sensitivity=source_sensitivity)
    stored_payload = startup_privacy_service.artifact_store.read_bytes(context.local_text_refs[0]).decode("utf-8")

    assert preview.overall_class == source_sensitivity
    assert preview.category_counts[expected_category] == 1
    assert expected_token in preview.model_dump_json()
    assert stored_payload == expected_token
    for surface in (preview.model_dump_json(), repr(preview), context.model_dump_json(), repr(context), stored_payload):
        assert raw not in surface
        assert RAW_EMAIL not in surface


def test_default_source_sensitivity_fails_closed_to_restricted(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    block = _stored_text_block(startup_privacy_service, "No direct PII here")

    preview = startup_privacy_service.build_preview([block])

    assert preview.overall_class == SensitivityClass.RESTRICTED


def test_quasi_identifier_categories_are_structured_and_do_not_match_redaction_markers(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    block = _stored_text_block(
        startup_privacy_service,
        "Brazil launch plan dated 2026-07-31 for CFOs in rare quantum logistics segment",
    )
    banking_block = _stored_text_block(startup_privacy_service, f"IBAN {RAW_IBAN}")

    preview = startup_privacy_service.build_preview(
        [block, banking_block],
        source_sensitivity=SensitivityClass.PUBLIC,
    )

    assert preview.quasi_identifier_count == 4
    assert preview.quasi_identifier_counts == {
        "exact_date": 1,
        "geography": 1,
        "rare_segment": 1,
        "role_title": 1,
    }
    assert "[REDACTED:banking:1]" in preview.model_dump_json()
    assert "banking" not in preview.quasi_identifier_counts


def test_textblock_locator_never_carries_or_overrides_raw_sensitive_content(
    startup_privacy_service: StartupPrivacyService,
) -> None:
    block = _stored_text_block(
        startup_privacy_service,
        f"Stored private contact {RAW_EMAIL}",
        locator_value="page:1:block:1",
    )

    preview = startup_privacy_service.build_preview([block], source_sensitivity=SensitivityClass.PUBLIC)

    assert preview.category_counts["email"] == 1
    assert RAW_EMAIL not in block.model_dump_json()
    assert RAW_EMAIL not in repr(block.locator)
    assert "page:1:block:1" in block.model_dump_json()


def test_presidio_direct_contract_redacts_presidio_only_detection(tmp_path) -> None:
    existing = RulesRedactor().detect(f"Founder {RAW_NAME} owns pricing", base_sensitivity=SensitivityClass.PUBLIC)
    adapter = PresidioRedactor(
        local_model_path=tmp_path,
        analyzer_factory=lambda: _FakeAnalyzer([_AnalyzerResult("PERSON", 8, 26)]),
    )

    result = adapter.detect(f"Founder {RAW_NAME} owns pricing", existing=existing)

    assert result.category_counts == {"person_name": 1}
    assert "[REDACTED:person_name:1]" in result.redacted_text
    assert RAW_NAME not in result.redacted_text
    assert RAW_NAME not in repr(result)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (-1, 4),
        (2, 2),
        (7, 2),
        (0, 10_000),
    ],
)
def test_presidio_invalid_spans_fail_closed_without_counting_or_redacting(
    tmp_path,
    start: int,
    end: int,
) -> None:
    text = f"Founder {RAW_NAME} owns pricing"
    existing = RulesRedactor().detect(text, base_sensitivity=SensitivityClass.PUBLIC)
    adapter = PresidioRedactor(
        local_model_path=tmp_path,
        analyzer_factory=lambda: _FakeAnalyzer([_AnalyzerResult("PERSON", start, end)]),
    )

    result = adapter.detect(text, existing=existing)

    assert result.available is False
    assert result.reason == "presidio_invalid_span"
    assert result.detections == existing.detections
    assert result.redacted_text == existing.redacted_text
    assert "person_name" not in result.category_counts
    assert RAW_NAME in result.redacted_text
    assert RAW_TOKEN not in repr(result)


def test_presidio_overlapping_valid_spans_union_redaction_has_no_inner_raw_leak(tmp_path) -> None:
    text = "Founder Aigerim Tuleubayeva-RawHidden owns pricing"
    existing = RulesRedactor().detect(text, base_sensitivity=SensitivityClass.PUBLIC)
    adapter = PresidioRedactor(
        local_model_path=tmp_path,
        analyzer_factory=lambda: _FakeAnalyzer(
                [
                    _AnalyzerResult("PERSON", 8, 26),
                    _AnalyzerResult("PERSON", 16, 37),
                ]
            ),
        )

    result = adapter.detect(text, existing=existing)

    assert result.reason is None
    assert result.category_counts == {"person_name": 1}
    assert result.redacted_text == "Founder [REDACTED:person_name:1] owns pricing"
    assert "Tuleubayeva" not in result.redacted_text
    assert "RawHidden" not in result.redacted_text


def _table(cells: list[NormalizedCell]) -> NormalizedTable:
    return NormalizedTable(
        artifact_id=uuid4(),
        name="customers",
        cells=cells,
        snapshot_hash="a" * 64,
        snapshot_ref="b" * 64,
        row_count=max(cell.row for cell in cells),
        column_count=1,
    )


def _cell(*, label: str, value: str | Decimal, row: int) -> NormalizedCell:
    return NormalizedCell(
        row=row,
        column=1,
        label=label,
        period=None,
        value=value,
        unit=None,
        locator=SourceLocator(kind="xlsx_cell", value=f"Customers!A{row}", cell=f"A{row}"),
        status="verified",
    )


def _stored_text_block(
    service: StartupPrivacyService,
    text: str,
    *,
    locator_value: str = "page:1:block:1",
) -> TextBlock:
    stored = service.artifact_store.put_bytes(
        text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        sensitivity=SensitivityClass.RESTRICTED,
    )
    return TextBlock(
        text_ref=stored.content_hash,
        content_hash=stored.content_hash,
        char_count=len(text),
        locator=SourceLocator(kind="text", value=locator_value),
        confidence=Decimal("1"),
        verification_status="verified",
    )


@dataclass(frozen=True)
class _AnalyzerResult:
    entity_type: str
    start: int
    end: int


class _FakeAnalyzer:
    def __init__(self, results: list[_AnalyzerResult]) -> None:
        self._results = results

    def analyze(self, *, text: str, language: str) -> list[_AnalyzerResult]:
        del text, language
        return self._results
