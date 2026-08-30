from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from due_diligence_agent.domain.common import SensitivityClass, require_utc


class ReproducibilityManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code_commit: str
    build_id: str
    dependency_lock_hash: str
    python_version: str
    package_versions: Mapping[str, str]
    provider_model_id: str
    model_alias_snapshot: str
    reasoning_parameters: Mapping[str, str]
    adapter_versions: Mapping[str, str]
    parser_versions: Mapping[str, str]
    embedding_model_version: str | None = None
    index_version: str | None = None
    redaction_policy_version: str
    locale: str
    timezone: str
    fx_source: str | None = None
    deterministic_seeds: Mapping[str, int]
    configuration_hash: str

    @field_validator(
        "package_versions",
        "reasoning_parameters",
        "adapter_versions",
        "parser_versions",
        mode="after",
    )
    @classmethod
    def freeze_str_mapping(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType(dict(value))

    @field_validator("deterministic_seeds", mode="after")
    @classmethod
    def freeze_int_mapping(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        return MappingProxyType(dict(value))

    @field_serializer(
        "package_versions",
        "reasoning_parameters",
        "adapter_versions",
        "parser_versions",
        "deterministic_seeds",
    )
    def serialize_mapping(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return dict(value)


class ReportSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    case_id: UUID
    report_hash: str
    case_snapshot_hash: str
    source_hashes: Mapping[str, str]
    as_of: datetime
    graph_version: str
    prompt_versions: Mapping[str, str]
    formula_versions: Mapping[str, str]
    model_versions: Mapping[str, str]
    trace_ids: tuple[str, ...] = ()
    sections: Mapping[str, Any] = Field(default_factory=dict)
    data_revision: int = 1
    json_artifact_ref: str
    html_artifact_ref: str | None = None
    pdf_artifact_ref: str | None = None
    content_hashes: Mapping[str, str]
    reproducibility: ReproducibilityManifest
    sensitivity: SensitivityClass
    created_at: datetime
    version: int = 1

    @field_validator("as_of", "created_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

    @field_validator(
        "source_hashes",
        "prompt_versions",
        "formula_versions",
        "model_versions",
        "content_hashes",
        mode="after",
    )
    @classmethod
    def freeze_mapping(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType(dict(value))

    @field_validator("sections", mode="after")
    @classmethod
    def freeze_sections(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        frozen = _deep_freeze(value)
        if not isinstance(frozen, Mapping):
            raise ValueError("sections must be a mapping")
        return frozen

    @field_serializer(
        "source_hashes",
        "prompt_versions",
        "formula_versions",
        "model_versions",
        "content_hashes",
    )
    def serialize_mapping(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)

    @field_serializer("sections")
    def serialize_sections(self, value: Mapping[str, Any]) -> dict[str, Any]:
        thawed = _deep_thaw(value)
        if not isinstance(thawed, dict):
            raise ValueError("sections must serialize as a mapping")
        return thawed


def _deep_freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value
