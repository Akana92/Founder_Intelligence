from __future__ import annotations

import json
import re
from decimal import Decimal
from enum import StrEnum
from typing import Any, Final, Literal, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.common import require_decimal


AnswerType: TypeAlias = Literal["manual", "file", "public_research", "skip"]
AdvisorQuestionOrigin: TypeAlias = Literal[
    "static",
    "document_gap",
    "document_contradiction",
    "answered_state",
]
AdvisorResearchStatus: TypeAlias = Literal[
    "completed", "partial", "deferred", "blocked"
]
_ANSWER_MODE_LABELS_RU: Final[dict[AnswerType, str]] = {
    "manual": "Вручную",
    "file": "Файл",
    "public_research": "Публичный поиск",
    "skip": "Пропустить",
}
_SHA256_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_MAX_IMPROVEMENT_TEXT_LENGTH = 1200
_IMPROVEMENT_NAMESPACE = NAMESPACE_URL


class AdvisorQuestion(BaseModel):
    """One deterministic founder prompt and the analysis it unlocks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    field_key: str
    question_ru: str
    reason_ru: str
    unlocks_ru: str
    answer_modes: tuple[AnswerType, ...]
    origin: AdvisorQuestionOrigin = "static"
    origin_label_ru: str = "Базовый сценарий"
    context_ru: str | None = None
    bound_contradiction_id: UUID | None = Field(default=None, exclude=True, repr=False)
    answer_mode_labels_ru: dict[AnswerType, str] = Field(
        default_factory=lambda: dict(_ANSWER_MODE_LABELS_RU)
    )


class AdvisorAnswer(BaseModel):
    """A founder response to a single progressive-advisor question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer_type: AnswerType
    value: str | None = None
    consent_public_research: bool = False


class AdvisorResearchDelta(BaseModel):
    """Bounded result of one consent-gated public research request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: AdvisorResearchStatus
    summary_ru: str
    source_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    fallback_used: bool = False
    fail_reason_ru: str | None = None


class AdvisorDelta(BaseModel):
    """The deterministic, case-local effect of one submitted answer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    question_id: str
    field_key: str
    answer_type: AnswerType
    confidence_delta: int
    analysis_blocked: bool


class StartupImprovementTargetArea(StrEnum):
    POSITIONING = "positioning"
    MONETIZATION = "monetization"
    METRICS = "metrics"
    GTM = "gtm"
    RISK_REDUCTION = "risk_reduction"
    INVESTOR_READINESS = "investor_readiness"


class StartupImprovementEvidenceKind(StrEnum):
    LIVE_INFERENCE = "live_inference"
    PUBLIC_FACT = "public_fact"
    LOCAL_CALCULATION = "local_calculation"


class StartupImprovementEvidenceRef(BaseModel):
    """One immutable, typed reference used to justify an improvement proposal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: StartupImprovementEvidenceKind
    ref_id: UUID
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)


class StartupImprovementProposal(BaseModel):
    """A deterministic Russian recommendation bound to one frozen report lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: UUID
    case_id: UUID
    base_report_snapshot_id: UUID
    base_report_snapshot_hash: str
    base_case_revision: int = Field(ge=1)
    improvement_version: int = Field(ge=1)
    target_area: StartupImprovementTargetArea
    recommendation_ru: str
    rationale_ru: str
    expected_effect_ru: str
    evidence_refs: tuple[StartupImprovementEvidenceRef, ...] = Field(default_factory=tuple)
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @classmethod
    def create(
        cls,
        *,
        case_id: UUID,
        base_report_snapshot_id: UUID,
        base_report_snapshot_hash: str,
        base_case_revision: int,
        improvement_version: int,
        target_area: StartupImprovementTargetArea,
        recommendation_ru: str,
        rationale_ru: str,
        expected_effect_ru: str,
        evidence_refs: tuple[StartupImprovementEvidenceRef, ...],
        confidence: Decimal,
    ) -> "StartupImprovementProposal":
        normalized_hash = _normalize_sha256(base_report_snapshot_hash)
        normalized_text = tuple(
            _normalize_russian_text(value)
            for value in (recommendation_ru, rationale_ru, expected_effect_ru)
        )
        normalized_refs = _normalize_improvement_evidence_refs(evidence_refs)
        normalized_confidence = require_decimal(confidence)
        proposal_id = cls.derive_proposal_id(
            case_id=case_id,
            base_report_snapshot_id=base_report_snapshot_id,
            base_report_snapshot_hash=normalized_hash,
            base_case_revision=base_case_revision,
            improvement_version=improvement_version,
            target_area=target_area,
            recommendation_ru=normalized_text[0],
            rationale_ru=normalized_text[1],
            expected_effect_ru=normalized_text[2],
            evidence_refs=normalized_refs,
            confidence=normalized_confidence,
        )
        return cls(
            proposal_id=proposal_id,
            case_id=case_id,
            base_report_snapshot_id=base_report_snapshot_id,
            base_report_snapshot_hash=normalized_hash,
            base_case_revision=base_case_revision,
            improvement_version=improvement_version,
            target_area=target_area,
            recommendation_ru=normalized_text[0],
            rationale_ru=normalized_text[1],
            expected_effect_ru=normalized_text[2],
            evidence_refs=normalized_refs,
            confidence=normalized_confidence,
        )

    @classmethod
    def derive_proposal_id(cls, **values: Any) -> UUID:
        target = StartupImprovementTargetArea(values["target_area"])
        references = _normalize_improvement_evidence_refs(values["evidence_refs"])
        payload = {
            "case_id": str(values["case_id"]),
            "base_report_snapshot_id": str(values["base_report_snapshot_id"]),
            "base_report_snapshot_hash": _normalize_sha256(values["base_report_snapshot_hash"]),
            "base_case_revision": int(values["base_case_revision"]),
            "improvement_version": int(values["improvement_version"]),
            "target_area": target.value,
            "recommendation_ru": _normalize_russian_text(values["recommendation_ru"]),
            "rationale_ru": _normalize_russian_text(values["rationale_ru"]),
            "expected_effect_ru": _normalize_russian_text(values["expected_effect_ru"]),
            "evidence_refs": [
                {
                    "kind": reference.kind.value,
                    "ref_id": str(reference.ref_id),
                    "confidence": str(reference.confidence),
                }
                for reference in references
            ],
            "confidence": str(require_decimal(values["confidence"])),
        }
        canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return uuid5(_IMPROVEMENT_NAMESPACE, f"startup-improvement:{canonical}")

    @field_validator("base_report_snapshot_hash", mode="before")
    @classmethod
    def validate_report_hash(cls, value: Any) -> str:
        return _normalize_sha256(value)

    @field_validator("recommendation_ru", "rationale_ru", "expected_effect_ru", mode="before")
    @classmethod
    def validate_russian_text(cls, value: Any) -> str:
        return _normalize_russian_text(value)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def validate_evidence_refs(cls, value: Any) -> tuple[StartupImprovementEvidenceRef, ...]:
        return _normalize_improvement_evidence_refs(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @model_validator(mode="after")
    def validate_identity(self) -> "StartupImprovementProposal":
        expected = self.derive_proposal_id(
            **self.model_dump(mode="python", exclude={"proposal_id"})
        )
        if self.proposal_id != expected:
            raise ValueError("invalid proposal id")
        return self


class StartupVersionDelta(BaseModel):
    """Immutable outcome of one proposal decision against an exact report base."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    base_report_snapshot_id: UUID
    base_report_snapshot_hash: str
    base_case_revision: int = Field(ge=1)
    previous_version: int = Field(ge=1)
    new_version: int = Field(ge=1)
    accepted_proposal_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    rejected_proposal_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    changed_fields: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("base_report_snapshot_hash", mode="before")
    @classmethod
    def validate_report_hash(cls, value: Any) -> str:
        return _normalize_sha256(value)

    @field_validator("accepted_proposal_ids", "rejected_proposal_ids", mode="before")
    @classmethod
    def normalize_decision_ids(cls, value: Any) -> tuple[UUID, ...]:
        items = () if value is None else tuple(UUID(str(item)) for item in value)
        if len(items) != len(set(items)):
            raise ValueError("duplicate proposal ids")
        return tuple(sorted(items, key=str))

    @field_validator("changed_fields", mode="before")
    @classmethod
    def normalize_changed_fields(cls, value: Any) -> tuple[str, ...]:
        items = () if value is None else tuple(value)
        normalized = tuple(
            sorted({StartupImprovementTargetArea(item).value for item in items})
        )
        return normalized

    @model_validator(mode="after")
    def validate_version_semantics(self) -> "StartupVersionDelta":
        if set(self.accepted_proposal_ids) & set(self.rejected_proposal_ids):
            raise ValueError("overlapping proposal ids")
        expected_version = self.previous_version + (1 if self.accepted_proposal_ids else 0)
        if self.new_version != expected_version:
            raise ValueError("invalid improvement version transition")
        if not self.accepted_proposal_ids and self.changed_fields:
            raise ValueError("rejected-only decisions cannot change fields")
        return self


def _normalize_sha256(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid sha256 reference")
    match = _SHA256_RE.fullmatch(value.strip().casefold())
    if match is None:
        raise ValueError("invalid sha256 reference")
    return f"sha256:{match.group(1)}"


def _normalize_russian_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Russian proposal text must be a string")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("Russian proposal text must not be blank")
    if len(normalized) > _MAX_IMPROVEMENT_TEXT_LENGTH:
        raise ValueError("Russian proposal text exceeds the allowed bound")
    if _CYRILLIC_RE.search(normalized) is None:
        raise ValueError("Russian proposal text must contain Cyrillic")
    return normalized


def _normalize_improvement_evidence_refs(
    value: Any,
) -> tuple[StartupImprovementEvidenceRef, ...]:
    if value is None:
        return ()
    references = tuple(
        item
        if isinstance(item, StartupImprovementEvidenceRef)
        else StartupImprovementEvidenceRef.model_validate(item)
        for item in value
    )
    keys = tuple((reference.kind, reference.ref_id) for reference in references)
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate improvement evidence refs")
    return tuple(sorted(references, key=lambda item: (item.kind.value, str(item.ref_id))))
