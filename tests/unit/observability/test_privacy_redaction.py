from __future__ import annotations

import pytest

from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer


def test_trace_sanitizer_rejects_prompt_document_filename_path_and_pii_fields() -> None:
    sanitizer = StrictTraceSanitizer()

    for key in (
        "prompt",
        "source_text",
        "document_text",
        "filename",
        "file_name",
        "path",
        "document_path",
        "email",
        "phone",
        "company_name",
        "person_name",
    ):
        with pytest.raises(ValueError, match="trace_attribute.disallowed"):
            sanitizer.sanitize_attributes({key: "sensitive"})


def test_trace_sanitizer_keeps_admin_safe_scalar_fields() -> None:
    sanitizer = StrictTraceSanitizer()

    assert sanitizer.sanitize_attributes(
        {
            "case_id": "case-1",
            "status": "success",
            "latency_ms": 12.5,
            "estimated_cost_usd": 0.01,
            "artifact_hash": "a" * 64,
            "report_format": "pdf",
            "redaction_policy_version": "privacy@1",
            "tool_call_observed": True,
        }
    ) == {
        "case_id": "case-1",
        "status": "success",
        "latency_ms": 12.5,
        "estimated_cost_usd": 0.01,
        "artifact_hash": "a" * 64,
        "report_format": "pdf",
        "redaction_policy_version": "privacy@1",
        "tool_call_observed": True,
    }


def test_trace_sanitizer_allows_only_the_stable_invalid_output_machine_code() -> None:
    sanitizer = StrictTraceSanitizer()

    assert sanitizer.sanitize_attributes(
        {
            "error_code": "invalid_output",
            "failure_code": "invalid_output",
        }
    ) == {
        "error_code": "invalid_output",
        "failure_code": "invalid_output",
    }

    with pytest.raises(ValueError, match="trace_attribute.value_sensitive"):
        sanitizer.sanitize_attributes({"failure_code": "raw_provider_output"})
