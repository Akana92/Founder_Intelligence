from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, cast

import pytest

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.bootstrap.container import build_local_repositories
from due_diligence_agent.bootstrap.container import build_openai_startup_components
from due_diligence_agent.bootstrap.container import build_openai_startup_provider
from due_diligence_agent.config import OpenAIStartupSettings
from due_diligence_agent.ports.llm import LLMUsage


def test_openai_startup_provider_factory_uses_priced_reconciliation_and_affordable_token_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    provider_module = ModuleType("due_diligence_agent.adapters.openai.startup_provider")
    openai_module = ModuleType("openai")

    class FakeResponses:
        async def parse(self, **kwargs: object) -> object:
            raise AssertionError("factory test must not call OpenAI")

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured["client_kwargs"] = kwargs
            self.responses = FakeResponses()

    class FakeOpenAIStartupProvider:
        def __init__(self, **kwargs: object) -> None:
            captured["provider_kwargs"] = kwargs

    setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    setattr(provider_module, "OpenAIStartupProvider", FakeOpenAIStartupProvider)
    monkeypatch.setitem(
        sys.modules,
        "due_diligence_agent.adapters.openai.startup_provider",
        provider_module,
    )
    monkeypatch.setitem(sys.modules, "openai", openai_module)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_STARTUP_MAX_INPUT_TOKENS", "6000")
    monkeypatch.setenv("OPENAI_STARTUP_MAX_OUTPUT_TOKENS", "1500")
    monkeypatch.setenv("OPENAI_STARTUP_PER_CALL_USD_RESERVATION", "0.05")
    monkeypatch.setenv("OPENAI_STARTUP_PER_CASE_USD_CAP", "0.25")
    repositories = build_local_repositories(tmp_path / "metadata.sqlite3")
    settings = OpenAIStartupSettings(_env_file=None)  # type: ignore[call-arg]

    provider = build_openai_startup_provider(
        settings=settings,
        repositories=repositories,
        audit_spool=JsonlAuditSpool(tmp_path / "audit-spool"),
    )

    assert isinstance(provider, FakeOpenAIStartupProvider)
    provider_kwargs = cast(dict[str, Any], captured["provider_kwargs"])
    gateway = provider_kwargs["gateway"]
    budget_guard = gateway._budget_guard
    assert provider_kwargs["worst_case_tokens"] == 7_500
    assert provider_kwargs["worst_case_usd_cost"] == Decimal("0.017000")
    assert budget_guard.default_token_limit == 250_000
    assert budget_guard.default_usd_limit == Decimal("0.25")
    assert budget_guard.persistence_path == tmp_path / "startup-openai-budget.sqlite3"
    usage_cost_calculator = gateway._usage_cost_calculator
    assert usage_cost_calculator is not None
    assert usage_cost_calculator(
        LLMUsage(input_tokens=2_000, output_tokens=500, total_tokens=2_500)
    ) == Decimal("0.005")
    assert usage_cost_calculator(
        LLMUsage(input_tokens=0, output_tokens=500, total_tokens=2_500)
    ) == Decimal("0.015")
    repositories.database.close()


def test_openai_startup_components_share_one_gateway_without_network_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    provider_module = ModuleType("due_diligence_agent.adapters.openai.startup_provider")
    extractor_module = ModuleType("due_diligence_agent.adapters.openai.startup_profile_extractor")
    openai_module = ModuleType("openai")

    class FakeResponses:
        async def parse(self, **kwargs: object) -> object:
            raise AssertionError("factory test must not call OpenAI")

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured["client_kwargs"] = kwargs
            self.responses = FakeResponses()

    class FakeOpenAIStartupProvider:
        def __init__(self, **kwargs: object) -> None:
            captured["provider_kwargs"] = kwargs

    class FakeOpenAIStartupProfileExtractor:
        def __init__(self, **kwargs: object) -> None:
            captured["extractor_kwargs"] = kwargs

    setattr(openai_module, "AsyncOpenAI", FakeAsyncOpenAI)
    setattr(provider_module, "OpenAIStartupProvider", FakeOpenAIStartupProvider)
    setattr(extractor_module, "OpenAIStartupProfileExtractor", FakeOpenAIStartupProfileExtractor)
    monkeypatch.setitem(
        sys.modules,
        "due_diligence_agent.adapters.openai.startup_provider",
        provider_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "due_diligence_agent.adapters.openai.startup_profile_extractor",
        extractor_module,
    )
    monkeypatch.setitem(sys.modules, "openai", openai_module)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    repositories = build_local_repositories(tmp_path / "metadata.sqlite3")
    settings = OpenAIStartupSettings(_env_file=None)  # type: ignore[call-arg]

    components = build_openai_startup_components(
        settings=settings,
        repositories=repositories,
        audit_spool=JsonlAuditSpool(tmp_path / "audit-spool"),
    )

    assert components is not None
    assert isinstance(components.provider, FakeOpenAIStartupProvider)
    assert isinstance(components.profile_extractor, FakeOpenAIStartupProfileExtractor)
    provider_gateway = cast(dict[str, Any], captured["provider_kwargs"])["gateway"]
    extractor_gateway = cast(dict[str, Any], captured["extractor_kwargs"])["gateway"]
    assert provider_gateway is extractor_gateway
    assert cast(dict[str, Any], captured["provider_kwargs"])["worst_case_usd_cost"] == Decimal(
        "0.017000"
    )
    assert cast(dict[str, Any], captured["extractor_kwargs"])["worst_case_usd_cost"] == Decimal(
        "0.017000"
    )
    repositories.database.close()
