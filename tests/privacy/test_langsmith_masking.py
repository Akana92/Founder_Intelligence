from __future__ import annotations

import importlib
import os
from uuid import uuid4

import pytest

from due_diligence_agent.adapters.observability.langsmith import (
    LangSmithTraceAdapter,
    LangSmithTraceConfig,
)
from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer


def test_disabled_langsmith_adapter_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    imported: list[str] = []
    real_import = importlib.import_module

    def recording_import(name: str, package: str | None = None) -> object:
        imported.append(name)
        if name == "langsmith":
            raise AssertionError("disabled adapter must not import langsmith")
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", recording_import)

    adapter = LangSmithTraceAdapter(LangSmithTraceConfig(enabled=False))

    assert adapter.client is None
    callbacks = adapter.callbacks(metadata={"prompt": "secret prompt", "email": "john@example.com"})
    assert callbacks.client is None
    assert callbacks.metadata == {}
    assert callbacks.hide_inputs({"prompt": "secret prompt"}) == {}
    assert callbacks.hide_outputs({"completion": "secret output"}) == {}
    assert "langsmith" not in imported


def test_disabled_langsmith_callbacks_do_not_sanitize_metadata() -> None:
    adapter = LangSmithTraceAdapter(
        LangSmithTraceConfig(enabled=False),
        sanitizer=ExplodingSanitizer(),
    )

    callbacks = adapter.callbacks(metadata={"email": "john@example.com"})

    assert callbacks.client is None
    assert callbacks.metadata == {}


def test_enabled_langsmith_hides_io_and_sanitizes_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = RecordingLangSmithFactory()
    adapter = LangSmithTraceAdapter(
        LangSmithTraceConfig(enabled=True),
        client_factory=factory,
    )

    callbacks = adapter.callbacks(
        metadata={
            "case_id": "case-10",
            "model": "gpt-5.6-terra",
            "schema_version": "risk@1",
            "input.value": "secret prompt",
            "email": "john@example.com",
        }
    )

    assert os.environ["LANGSMITH_HIDE_INPUTS"] == "true"
    assert os.environ["LANGSMITH_HIDE_OUTPUTS"] == "true"
    assert callbacks.hide_inputs(
        {
            "case_id": "case-10",
            "prompt": "secret prompt",
            "email": "john@example.com",
        }
    ) == {"case_id": "case-10"}
    assert callbacks.hide_outputs(
        {
            "status": "success",
            "completion": "secret output",
            "api_key": "sk-test",
        }
    ) == {"status": "success"}
    assert callbacks.metadata == {
        "case_id": "case-10",
        "model": "gpt-5.6-terra",
        "schema_version": "risk@1",
    }
    assert factory.created == 1
    assert factory.kwargs["hide_inputs"](
        {
            "run_id": "startup-api-case-10",
            "prompt": "secret prompt",
        }
    ) == {"run_id": "startup-api-case-10"}
    assert factory.kwargs["hide_outputs"](
        {
            "status": "success",
            "completion": "secret output",
        }
    ) == {"status": "success"}
    assert factory.kwargs["hide_metadata"](
        {
            "case_id": "case-10",
            "input.value": "secret prompt",
            "usage_metadata": {
                "input_tokens": 120,
                "output_tokens": 45,
                "total_tokens": 165,
                "total_cost": 0.00123,
                "prompt": "secret prompt",
            },
        }
    ) == {
        "case_id": "case-10",
        "usage_metadata": {
            "input_tokens": 120,
            "output_tokens": 45,
            "total_tokens": 165,
            "total_cost": 0.00123,
        },
    }
    assert factory.kwargs["omit_traced_runtime_info"] is True
    assert factory.env_at_creation == {
        "LANGSMITH_HIDE_INPUTS": "true",
        "LANGSMITH_HIDE_OUTPUTS": "true",
    }


def test_enabled_langsmith_default_client_uses_langsmith_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeLangSmithModule:
        @staticmethod
        def Client(**kwargs: object) -> object:
            captured.update(kwargs)
            return object()

    monkeypatch.setenv("LANGSMITH_API_KEY", "sentinel-langsmith-key")
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.setattr(importlib, "import_module", lambda _: FakeLangSmithModule)

    adapter = LangSmithTraceAdapter(LangSmithTraceConfig(enabled=True))

    assert adapter.client is not None
    assert captured["api_key"] == "sentinel-langsmith-key"
    assert captured["hide_inputs"]({"prompt": "secret prompt"}) == {}
    assert captured["hide_outputs"]({"completion": "secret output"}) == {}


def test_langsmith_startup_metadata_allowlist_accepts_safe_operational_fields() -> None:
    safe = StrictTraceSanitizer().sanitize_attributes(
        {
            "case_id": str(uuid4()),
            "run_id": "startup-api-case-1",
            "node_name": "report",
            "agent_role": "report",
            "gate": "gate4",
            "gate_status": "completed",
            "duration_ms": 12,
            "retry_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "ls_provider": "openai",
            "ls_model_name": "gpt-5.6-terra",
            "report_id": str(uuid4()),
            "report_revision": 1,
            "report_checksum": "a" * 64,
            "exporter_provider": "langsmith",
        }
    )

    assert safe["agent_role"] == "report"
    assert safe["gate"] == "gate4"
    assert safe["report_revision"] == 1
    assert safe["exporter_provider"] == "langsmith"
    assert safe["ls_provider"] == "openai"
    assert safe["ls_model_name"] == "gpt-5.6-terra"


@pytest.mark.parametrize(
    "key",
    [
        "filename",
        "local_path",
        "prompt",
        "document_text",
        "private_name",
        "api_key",
    ],
)
def test_langsmith_startup_metadata_rejects_payload_and_identity_fields(key: str) -> None:
    with pytest.raises(ValueError, match="trace_attribute.disallowed"):
        StrictTraceSanitizer().sanitize_attributes({key: "unsafe"})


class RecordingLangSmithFactory:
    def __init__(self) -> None:
        self.created = 0
        self.kwargs: dict[str, object] = {}
        self.env_at_creation: dict[str, str | None] = {}

    def __call__(self, **kwargs: object) -> object:
        self.created += 1
        self.kwargs = kwargs
        self.env_at_creation = {
            "LANGSMITH_HIDE_INPUTS": os.environ.get("LANGSMITH_HIDE_INPUTS"),
            "LANGSMITH_HIDE_OUTPUTS": os.environ.get("LANGSMITH_HIDE_OUTPUTS"),
        }
        return object()


class ExplodingSanitizer:
    def sanitize_attributes(
        self,
        metadata: object,
        *,
        drop_disallowed: bool = False,
    ) -> dict[str, object]:
        raise AssertionError("disabled LangSmith callbacks must not sanitize")
