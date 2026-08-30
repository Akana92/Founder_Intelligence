from decimal import Decimal
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DDA_",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    runtime_profile: Literal["local", "self_hosted"] = "local"
    python_runtime: Literal["3.12", "3.13"] = "3.12"
    data_dir: Path = Path(".local")
    langsmith_tracing: bool = False
    audit_required: bool = True
    sec_user_agent: str = Field(default="", min_length=0)
    sec_max_requests_per_second: int = Field(default=10, ge=1, le=10)
    reflexion_max_rounds: int = Field(default=2, ge=0, le=2)
    embedding_model_dir: Path = Path("models/intfloat-multilingual-e5-base")


class OpenAIStartupSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )
    priced_model: ClassVar[str] = "gpt-5.6-luna"
    input_usd_per_million_tokens: ClassVar[Decimal] = Decimal("1.00")
    output_usd_per_million_tokens: ClassVar[Decimal] = Decimal("6.00")
    fixed_input_token_overhead: ClassVar[int] = 2_000

    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "OPENAI_STARTUP_API_KEY"),
    )
    model: str = Field(default="gpt-5.6-luna", validation_alias="OPENAI_STARTUP_MODEL")
    timeout_seconds: float = Field(
        default=20.0,
        ge=1.0,
        le=60.0,
        validation_alias="OPENAI_STARTUP_TIMEOUT_SECONDS",
    )
    max_retries: int = Field(
        default=0,
        ge=0,
        le=0,
        validation_alias="OPENAI_STARTUP_MAX_RETRIES",
    )
    max_input_tokens: int = Field(
        default=6_000,
        ge=500,
        le=20_000,
        validation_alias="OPENAI_STARTUP_MAX_INPUT_TOKENS",
    )
    max_output_tokens: int = Field(
        default=1_500,
        ge=100,
        le=2_000,
        validation_alias="OPENAI_STARTUP_MAX_OUTPUT_TOKENS",
    )
    per_call_usd_reservation: Decimal = Field(
        default=Decimal("0.05"),
        ge=Decimal("0.001"),
        le=Decimal("0.25"),
        validation_alias="OPENAI_STARTUP_PER_CALL_USD_RESERVATION",
    )
    per_case_usd_cap: Decimal = Field(
        default=Decimal("0.25"),
        ge=Decimal("0.01"),
        le=Decimal("1.00"),
        validation_alias="OPENAI_STARTUP_PER_CASE_USD_CAP",
    )

    @property
    def per_call_worst_case_usd_cost(self) -> Decimal:
        input_tokens = Decimal(self.max_input_tokens + self.fixed_input_token_overhead)
        output_tokens = Decimal(self.max_output_tokens)
        return (
            input_tokens * self.input_usd_per_million_tokens
            + output_tokens * self.output_usd_per_million_tokens
        ) / Decimal(1_000_000)

    @model_validator(mode="after")
    def _validate_budget_matches_priced_model(self) -> "OpenAIStartupSettings":
        if self.model != self.priced_model:
            raise ValueError(
                f"OPENAI_STARTUP_MODEL must be priced startup model {self.priced_model!r}"
            )
        if self.per_call_usd_reservation < self.per_call_worst_case_usd_cost:
            raise ValueError(
                "OPENAI_STARTUP_PER_CALL_USD_RESERVATION must be >= "
                "per_call_usd_reservation worst-case priced cost"
            )
        if self.per_case_usd_cap < self.per_call_usd_reservation:
            raise ValueError(
                "OPENAI_STARTUP_PER_CASE_USD_CAP must be >= per_case_usd_cap call reservation"
            )
        return self
