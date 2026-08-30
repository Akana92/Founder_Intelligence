from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any, Final, Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.common import SensitivityClass


STARTUP_DISCLOSURE_GATE: Final[Literal["startup_disclosure"]] = "startup_disclosure"
STARTUP_DISCLOSURE_SCOPE_VERSION = "startup_disclosure_scope@1"

_SAFE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_TEXT_RE = re.compile(r"^[a-z][a-z0-9_.@:-]{0,127}$")
_SAFE_DESTINATION_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UNSAFE_TEXT_MARKERS = re.compile(
    r"(?i)(@|sk-(?:live|proj)-|bearer\s+|api[_-]?key|secret|password|token|iban|bank|cap\s*table|customer)"
)


class ClassifiedDisclosureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    detected_classes: frozenset[SensitivityClass]
    overall_class: SensitivityClass
    redaction_policy_version: str
    egress_policy_version: str
    data_revision: int = Field(ge=1)
    content_hash: str
    artifact_counts: dict[str, int] = Field(default_factory=dict)
    mime_counts: dict[str, int] = Field(default_factory=dict)
    category_counts: dict[str, int] = Field(default_factory=dict)
    redacted_fragment_ids: tuple[UUID, ...] = ()
    minimized_fragment_refs: tuple[str, ...] = ()
    destination: str

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("minimized_fragment_refs")
    @classmethod
    def validate_minimized_fragment_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            _validate_sha256(item)
        return value

    @field_validator("artifact_counts", "mime_counts", "category_counts")
    @classmethod
    def validate_counts(cls, value: dict[str, int]) -> dict[str, int]:
        for key, count in value.items():
            if not _SAFE_KEY_RE.fullmatch(key):
                raise ValueError("unsafe_count_key")
            if count < 0:
                raise ValueError("negative_count")
        return value

    @field_validator("redaction_policy_version", "egress_policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        if not _SAFE_TEXT_RE.fullmatch(value):
            raise ValueError("unsafe_policy_version")
        return value

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        return _validate_destination(value)

    @model_validator(mode="after")
    def require_overall_class_in_detected_set(self) -> Self:
        if self.overall_class not in self.detected_classes:
            raise ValueError("overall_class_not_detected")
        return self


class DisclosurePreviewSafe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    overall_class: SensitivityClass
    detected_classes: tuple[SensitivityClass, ...]
    artifact_counts: dict[str, int]
    mime_counts: dict[str, int]
    category_counts: dict[str, int]
    fragment_count: int = Field(ge=0)
    redaction_policy_version: str
    egress_policy_version: str
    data_revision: int
    content_hash: str
    destination: str
    policy_explanation: str

    @field_validator("policy_explanation")
    @classmethod
    def reject_sensitive_explanation(cls, value: str) -> str:
        if _UNSAFE_TEXT_MARKERS.search(value):
            raise ValueError("unsafe_policy_explanation")
        return value


class StartupDisclosureApproval(Approval):
    model_config = ConfigDict(frozen=True, extra="forbid")

    gate: Literal["startup_disclosure"] = STARTUP_DISCLOSURE_GATE
    action: Literal["approved", "denied"]
    allowed_classes: frozenset[SensitivityClass]
    external_llm_allowed: bool
    approved_redaction_policy_version: str
    approved_egress_policy_version: str
    destination: str
    content_hash: str

    @field_validator("allowed_classes")
    @classmethod
    def reject_restricted(cls, value: frozenset[SensitivityClass]) -> frozenset[SensitivityClass]:
        if SensitivityClass.RESTRICTED in value:
            raise ValueError("restricted_not_exportable")
        return value

    @field_validator("approved_redaction_policy_version", "approved_egress_policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        if not _SAFE_TEXT_RE.fullmatch(value):
            raise ValueError("unsafe_policy_version")
        return value

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        return _validate_destination(value)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _validate_sha256(value)

    @model_validator(mode="after")
    def require_consistent_action(self) -> Self:
        if self.action == "approved" and not self.external_llm_allowed:
            raise ValueError("approved_requires_external_llm_allowed")
        if self.action == "denied" and self.external_llm_allowed:
            raise ValueError("denied_cannot_allow_external_llm")
        return self

    @classmethod
    def from_decision(
        cls,
        snapshot: ClassifiedDisclosureSnapshot,
        *,
        action: Literal["approved", "denied"],
        actor: str,
        destination: str,
        decided_at: datetime,
    ) -> StartupDisclosureApproval:
        checked_destination = _validate_destination(destination)
        allowed_classes = _exportable_classes(snapshot.detected_classes)
        payload = _scope_payload(
            snapshot,
            action=action,
            destination=checked_destination,
            allowed_classes=allowed_classes,
        )
        return cls(
            id=_approval_id(snapshot, action=action, destination=checked_destination),
            case_id=snapshot.case_id,
            gate=STARTUP_DISCLOSURE_GATE,
            action=action,
            actor=_validate_actor(actor),
            comment=_encode_scope(payload),
            decided_at=decided_at,
            data_revision=snapshot.data_revision,
            subject_hash=_hash_scope(payload),
            subject_version=1,
            allowed_classes=allowed_classes,
            external_llm_allowed=action == "approved",
            approved_redaction_policy_version=snapshot.redaction_policy_version,
            approved_egress_policy_version=snapshot.egress_policy_version,
            destination=checked_destination,
            content_hash=snapshot.content_hash,
        )

    @classmethod
    def from_base_approval(cls, approval: Approval) -> StartupDisclosureApproval:
        if approval.gate != STARTUP_DISCLOSURE_GATE:
            raise ValueError("approval_gate_mismatch")
        payload = _decode_scope(approval.comment)
        _require_scope_matches_base(payload, approval)
        if approval.subject_hash != _hash_scope(payload):
            raise ValueError("approval_scope_invalid")
        allowed_classes = _classes_from_payload(payload, "allowed_classes")
        detected_classes = _classes_from_payload(payload, "detected_classes")
        if allowed_classes != detected_classes:
            raise ValueError("approval_scope_invalid")
        action = _payload_str(payload, "action")
        if action == "approved":
            checked_action: Literal["approved", "denied"] = "approved"
        elif action == "denied":
            checked_action = "denied"
        else:
            raise ValueError("approval_scope_invalid")
        return cls(
            id=approval.id,
            case_id=approval.case_id,
            gate=STARTUP_DISCLOSURE_GATE,
            action=checked_action,
            actor=approval.actor,
            comment=approval.comment,
            decided_at=approval.decided_at,
            data_revision=approval.data_revision,
            subject_id=approval.subject_id,
            subject_hash=approval.subject_hash,
            subject_version=approval.subject_version,
            allowed_classes=allowed_classes,
            external_llm_allowed=action == "approved",
            approved_redaction_policy_version=_payload_str(payload, "redaction_policy_version"),
            approved_egress_policy_version=_payload_str(payload, "egress_policy_version"),
            destination=_payload_str(payload, "destination"),
            content_hash=_payload_str(payload, "content_hash"),
        )

    def as_base_approval(self) -> Approval:
        return Approval(
            id=self.id,
            case_id=self.case_id,
            gate=self.gate,
            action=self.action,
            actor=self.actor,
            comment=self.comment,
            decided_at=self.decided_at,
            data_revision=self.data_revision,
            subject_id=self.subject_id,
            subject_hash=self.subject_hash,
            subject_version=self.subject_version,
        )


def is_comment_safe_for_storage(comment: str | None) -> bool:
    if comment is None or not comment.strip():
        return True
    return len(comment) <= 240 and _UNSAFE_TEXT_MARKERS.search(comment) is None


def _scope_payload(
    snapshot: ClassifiedDisclosureSnapshot,
    *,
    action: str,
    destination: str,
    allowed_classes: frozenset[SensitivityClass],
) -> dict[str, Any]:
    return {
        "version": STARTUP_DISCLOSURE_SCOPE_VERSION,
        "case_id": str(snapshot.case_id),
        "action": action,
        "allowed_classes": sorted(item.value for item in allowed_classes),
        "detected_classes": sorted(item.value for item in snapshot.detected_classes),
        "data_revision": snapshot.data_revision,
        "content_hash": snapshot.content_hash,
        "redaction_policy_version": snapshot.redaction_policy_version,
        "egress_policy_version": snapshot.egress_policy_version,
        "destination": destination,
    }


def _encode_scope(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encoded = urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{STARTUP_DISCLOSURE_SCOPE_VERSION}:{encoded}"


def _decode_scope(comment: str | None) -> dict[str, Any]:
    if comment is None or not comment.startswith(f"{STARTUP_DISCLOSURE_SCOPE_VERSION}:"):
        raise ValueError("approval_scope_missing")
    encoded = comment.split(":", 1)[1]
    padded = encoded + ("=" * (-len(encoded) % 4))
    try:
        payload = json.loads(urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise ValueError("approval_scope_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("approval_scope_invalid")
    if payload.get("version") != STARTUP_DISCLOSURE_SCOPE_VERSION:
        raise ValueError("approval_scope_invalid")
    return payload


def _hash_scope(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def _approval_id(
    snapshot: ClassifiedDisclosureSnapshot,
    *,
    action: str,
    destination: str,
) -> UUID:
    seed = "|".join(
        (
            STARTUP_DISCLOSURE_GATE,
            str(snapshot.case_id),
            str(snapshot.data_revision),
            snapshot.content_hash,
            action,
            destination,
            snapshot.redaction_policy_version,
            snapshot.egress_policy_version,
            ",".join(sorted(item.value for item in snapshot.detected_classes)),
        )
    )
    return uuid5(NAMESPACE_URL, seed)


def _approval_id_from_payload(payload: dict[str, Any]) -> UUID:
    seed = "|".join(
        (
            STARTUP_DISCLOSURE_GATE,
            _payload_str(payload, "case_id"),
            str(_payload_int(payload, "data_revision")),
            _payload_str(payload, "content_hash"),
            _payload_str(payload, "action"),
            _payload_str(payload, "destination"),
            _payload_str(payload, "redaction_policy_version"),
            _payload_str(payload, "egress_policy_version"),
            ",".join(sorted(_payload_str_list(payload, "detected_classes"))),
        )
    )
    return uuid5(NAMESPACE_URL, seed)


def _require_scope_matches_base(payload: dict[str, Any], approval: Approval) -> None:
    action = _payload_str(payload, "action")
    if action not in {"approved", "denied"}:
        raise ValueError("approval_scope_invalid")
    if str(approval.case_id) != _payload_str(payload, "case_id"):
        raise ValueError("approval_scope_invalid")
    if approval.action != action:
        raise ValueError("approval_scope_invalid")
    if approval.data_revision != _payload_int(payload, "data_revision"):
        raise ValueError("approval_scope_invalid")
    if approval.subject_version != 1:
        raise ValueError("approval_scope_invalid")
    if approval.id != _approval_id_from_payload(payload):
        raise ValueError("approval_scope_invalid")


def _payload_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError("approval_scope_invalid")
    return value


def _payload_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("approval_scope_invalid")
    return value


def _payload_str_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("approval_scope_invalid")
    return value


def _classes_from_payload(
    payload: dict[str, Any],
    key: str,
) -> frozenset[SensitivityClass]:
    return frozenset(SensitivityClass(value) for value in _payload_str_list(payload, key))


def _exportable_classes(
    detected_classes: frozenset[SensitivityClass],
) -> frozenset[SensitivityClass]:
    return frozenset(detected_classes)


def _validate_destination(value: str) -> str:
    if not _SAFE_DESTINATION_RE.fullmatch(value):
        raise ValueError("unsafe_destination")
    return value


def _validate_actor(value: str) -> str:
    actor = value.strip()
    if not actor or len(actor) > 120 or _UNSAFE_TEXT_MARKERS.search(actor):
        raise ValueError("unsafe_actor")
    return actor


def _validate_sha256(value: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError("invalid_sha256")
    return value
