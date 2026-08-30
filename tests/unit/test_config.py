from decimal import Decimal

import pytest
from pydantic import ValidationError
from pydantic import SecretStr

from due_diligence_agent.config import OpenAIStartupSettings, Settings


def test_settings_are_local_and_privacy_safe_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DDA_DATA_DIR", str(tmp_path))
    settings = Settings()
    assert settings.runtime_profile == "local"
    assert settings.python_runtime == "3.12"
    assert settings.langsmith_tracing is False
    assert settings.audit_required is True
    assert settings.data_dir == tmp_path


def test_env_example_documents_embedding_model_dir():
    assert "DDA_EMBEDDING_MODEL_DIR=" in open(".env.example", encoding="utf-8").read()


def test_openai_startup_settings_are_optional_and_budget_capped_by_default(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = OpenAIStartupSettings(_env_file=None)

    assert settings.openai_api_key is None
    assert settings.model == "gpt-5.6-luna"
    assert settings.per_case_usd_cap == Decimal("0.25")
    assert settings.per_call_usd_reservation == Decimal("0.05")
    assert settings.per_call_usd_reservation <= settings.per_case_usd_cap
    assert settings.input_usd_per_million_tokens == Decimal("1.00")
    assert settings.output_usd_per_million_tokens == Decimal("6.00")
    assert settings.per_call_worst_case_usd_cost == Decimal("0.017000")
    assert settings.max_output_tokens <= 2_000
    assert settings.max_retries == 0


def test_openai_startup_settings_read_secret_without_leaking_raw_value(monkeypatch):
    raw_key = "test-openai-startup-provider-secret"
    monkeypatch.setenv("OPENAI_API_KEY", raw_key)

    settings = OpenAIStartupSettings(_env_file=None)

    assert isinstance(settings.openai_api_key, SecretStr)
    assert settings.openai_api_key.get_secret_value() == raw_key
    assert raw_key not in repr(settings)
    assert raw_key not in str(settings.model_dump())


def test_env_example_documents_openai_startup_provider_contract():
    env_example = open(".env.example", encoding="utf-8").read()

    assert "OPENAI_API_KEY=" in env_example
    assert "OPENAI_STARTUP_MODEL=gpt-5.6-luna" in env_example
    assert "OPENAI_STARTUP_MAX_RETRIES=0" in env_example
    assert "OPENAI_STARTUP_PER_CASE_USD_CAP=0.25" in env_example


def test_openai_startup_settings_reject_unknown_priced_model(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="priced startup model"):
        OpenAIStartupSettings(model="gpt-5.6-sol", _env_file=None)


def test_openai_startup_settings_reject_under_reserved_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="per_call_usd_reservation"):
        OpenAIStartupSettings(
            max_input_tokens=6_000,
            max_output_tokens=2_000,
            per_call_usd_reservation=Decimal("0.003"),
            _env_file=None,
        )


def test_openai_startup_settings_reject_case_cap_below_call_reservation(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="per_case_usd_cap"):
        OpenAIStartupSettings(
            per_call_usd_reservation=Decimal("0.05"),
            per_case_usd_cap=Decimal("0.04"),
            _env_file=None,
        )
