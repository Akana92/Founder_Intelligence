from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from due_diligence_agent.application.services.case_question_service import APPROVED_REQUIREMENT_KEYS, requirement_registry
from due_diligence_agent.application.startup_cases import StartupGateConflict
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.startup.case_intake import FounderStatement
from due_diligence_agent.domain.startup.copilot import CopilotQuestion


_MONEY_KEYS = frozenset(
    {
        "monthly_price",
        "available_budget",
        "revenue",
        "mrr",
        "burn",
        "cash_balance",
        "cogs",
        "gross_margin",
        "cac",
    }
)
_DEPENDENT_SCENARIO_KEYS = frozenset(
    {"monthly_price", "revenue", "mrr", "burn", "cash_balance", "customer_count"}
)


class SaveFounderStatementCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    requirement_key: str
    value: str
    currency: str | None = None
    scale: str | None = None
    period: str | None = None
    declared_source: str | None = None
    supporting_evidence_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    rationale: str | None = None
    validation_plan: str | None = None
    expected_case_revision: int = Field(ge=0)
    idempotency_key: str

    @field_validator("requirement_key", "value", "idempotency_key", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("text value must be a string")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("text value must not be blank")
        return normalized

    @field_validator("rationale", "validation_plan", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("text value must be a string")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("text value must not be blank")
        return normalized


class FieldValidationError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    message: str


class CaseMutationDelta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    accepted: bool
    old_revision: int = Field(ge=1)
    new_revision: int = Field(ge=1)
    changed_keys: tuple[str, ...] = Field(default_factory=tuple)
    stale_scenario_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    stale_report_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    metric_before: dict[str, str] = Field(default_factory=dict)
    metric_after: dict[str, str] = Field(default_factory=dict)
    readiness_before: dict[str, int] = Field(default_factory=dict)
    readiness_after: dict[str, int] = Field(default_factory=dict)
    next_question: Any | None = None
    validation_errors: tuple[FieldValidationError, ...] = Field(default_factory=tuple)
    original_draft: str | None = None


@dataclass(frozen=True)
class _StoredResult:
    command_fingerprint: tuple[object, ...]
    delta: CaseMutationDelta


class CaseFactIntakeService:
    def __init__(
        self,
        *,
        case_repository: Any,
        assumption_repository: Any,
        question_service_factory: Callable[[tuple[FounderStatement, ...]], Any] | None = None,
    ) -> None:
        self._case_repository = case_repository
        self._assumption_repository = assumption_repository
        self._question_service_factory = question_service_factory
        self._idempotency: dict[tuple[UUID, str], _StoredResult] = {}

    def save_founder_statement(
        self,
        command: SaveFounderStatementCommand,
    ) -> CaseMutationDelta:
        replay_key = (command.case_id, command.idempotency_key)
        fingerprint = _fingerprint(command)
        replay = self._idempotency.get(replay_key)
        if replay is not None:
            if replay.command_fingerprint != fingerprint:
                raise StartupGateConflict("idempotency_key_conflict")
            return replay.delta
        durable_replay = self._durable_replay(command)
        if durable_replay is not None:
            self._idempotency[replay_key] = _StoredResult(fingerprint, durable_replay)
            return durable_replay

        case = self._load_case(command.case_id)
        old_revision = _case_revision(case)
        self._validate_expected_revision(command.expected_case_revision, old_revision)
        errors = _validate_command(command)
        if errors:
            return CaseMutationDelta(
                accepted=False,
                old_revision=old_revision,
                new_revision=old_revision,
                original_draft=command.value,
                validation_errors=tuple(errors),
            )

        new_revision = old_revision + 1
        updated_case = case.model_copy(
            update={"data_revision": new_revision, "updated_at": datetime.now(UTC)}
        )
        try:
            advanced = self._case_repository.advance_data_revision(
                command.case_id,
                expected_revision=old_revision,
                updated_case=updated_case,
            )
        except ValueError:
            raise StartupGateConflict("case_revision_conflict") from None
        statement = FounderStatement(
            statement_id=uuid5(
                NAMESPACE_URL,
                f"founder-statement:{command.case_id}:{new_revision}:{command.requirement_key}:{command.idempotency_key}",
            ),
            case_id=command.case_id,
            data_revision=_case_revision(advanced),
            field_key=command.requirement_key,
            value=_canonical_statement_value(command),
            confidence=Decimal("0.80"),
            source_refs=command.supporting_evidence_refs,
            period=command.period,
            declared_source=command.declared_source,
            rationale=command.rationale or f"Declared by founder: {command.declared_source}",
            validation_plan=(
                command.validation_plan
                or "Replace with eligible source evidence before treating this as source_fact."
            ),
        )
        self._assumption_repository.save(
            statement,
            expected_revision=statement.data_revision,
            idempotency_key=command.idempotency_key,
        )
        answers = tuple(self._assumption_repository.get_current(command.case_id))
        delta = CaseMutationDelta(
            accepted=True,
            old_revision=old_revision,
            new_revision=statement.data_revision,
            changed_keys=(command.requirement_key,),
            stale_scenario_ids=_stale_scenario_ids(command.case_id, command.requirement_key),
            stale_report_ids=(uuid5(command.case_id, f"report:{command.requirement_key}"),),
            metric_before={command.requirement_key: "missing"},
            metric_after={command.requirement_key: "founder_statement"},
            readiness_before={"answered": max(0, len(answers) - 1)},
            readiness_after={"answered": len(answers)},
            next_question=self._next_question(command.case_id, answers),
        )
        self._idempotency[replay_key] = _StoredResult(fingerprint, delta)
        return delta

    def _durable_replay(
        self,
        command: SaveFounderStatementCommand,
    ) -> CaseMutationDelta | None:
        get_by_idempotency = getattr(self._assumption_repository, "get_by_idempotency", None)
        if get_by_idempotency is None:
            return None
        statement = get_by_idempotency(command.case_id, command.idempotency_key)
        if statement is None:
            return None
        if not _statement_matches_command(statement, command):
            raise StartupGateConflict("idempotency_key_conflict")
        answers = _answers_through_revision(
            tuple(self._assumption_repository.get_current(command.case_id)),
            statement.data_revision,
        )
        old_revision = max(1, statement.data_revision - 1)
        return CaseMutationDelta(
            accepted=True,
            old_revision=old_revision,
            new_revision=statement.data_revision,
            changed_keys=(command.requirement_key,),
            stale_scenario_ids=_stale_scenario_ids(command.case_id, command.requirement_key),
            stale_report_ids=(uuid5(command.case_id, f"report:{command.requirement_key}"),),
            metric_before={command.requirement_key: "missing"},
            metric_after={command.requirement_key: "founder_statement"},
            readiness_before={"answered": max(0, len(answers) - 1)},
            readiness_after={"answered": len(answers)},
            next_question=self._next_question(command.case_id, answers),
        )

    def _load_case(self, case_id: UUID) -> DueDiligenceCase:
        try:
            case: DueDiligenceCase = self._case_repository.get(case_id)
        except KeyError:
            raise StartupGateConflict("case_scope_mismatch") from None
        if getattr(case, "case_id", case_id) != case_id:
            raise StartupGateConflict("case_scope_mismatch")
        return case

    @staticmethod
    def _validate_expected_revision(expected_revision: int, actual_revision: int) -> None:
        if expected_revision != actual_revision:
            raise StartupGateConflict("case_revision_conflict")

    def _next_question(
        self,
        case_id: UUID,
        answers: tuple[FounderStatement, ...],
    ) -> CopilotQuestion | Any | None:
        if self._question_service_factory is not None:
            return self._question_service_factory(answers).next_question(
                case_id,
                page_context="overview",
                focus_key=None,
            )
        return None


def _validate_command(command: SaveFounderStatementCommand) -> list[FieldValidationError]:
    errors: list[FieldValidationError] = []
    if command.requirement_key not in APPROVED_REQUIREMENT_KEYS:
        errors.append(FieldValidationError(field="requirement_key", message="unknown key"))
        return errors
    schema = requirement_registry()[command.requirement_key].input_schema
    if "amount" in schema and _parse_amount(command.value) is None:
        errors.append(FieldValidationError(field="amount", message="amount is required"))
    for field in ("scale", "currency", "period", "declared_source"):
        if field in schema and not _present(getattr(command, field)):
            errors.append(FieldValidationError(field=field, message=f"{field} is required"))
    return errors


def _parse_amount(value: str) -> Decimal | None:
    normalized = (
        value.casefold()
        .replace("million", "")
        .replace("m", "")
        .replace(",", ".")
        .strip()
    )
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _present(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _case_revision(case: Any) -> int:
    revision = getattr(case, "data_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise StartupGateConflict("case_revision_conflict")
    return revision


def _canonical_statement_value(command: SaveFounderStatementCommand) -> str:
    parts = [command.value]
    if command.scale:
        parts.append(f"scale={command.scale}")
    if command.currency:
        parts.append(f"currency={command.currency}")
    if command.period:
        parts.append(f"period={command.period}")
    return "; ".join(parts)


def _stale_scenario_ids(case_id: UUID, key: str) -> tuple[UUID, ...]:
    if key not in _DEPENDENT_SCENARIO_KEYS:
        return ()
    return (uuid5(case_id, f"scenario:{key}"),)


def _fingerprint(command: SaveFounderStatementCommand) -> tuple[object, ...]:
    return (
        command.requirement_key,
        command.value,
        command.currency,
        command.scale,
        command.period,
        command.declared_source,
        command.supporting_evidence_refs,
        command.rationale,
        command.validation_plan,
        command.expected_case_revision,
    )


def _statement_matches_command(
    statement: FounderStatement,
    command: SaveFounderStatementCommand,
) -> bool:
    expected_rationale = command.rationale or f"Declared by founder: {command.declared_source}"
    expected_validation_plan = (
        command.validation_plan
        or "Replace with eligible source evidence before treating this as source_fact."
    )
    return (
        statement.case_id == command.case_id
        and statement.field_key == command.requirement_key
        and statement.value == _canonical_statement_value(command)
        and statement.source_refs == command.supporting_evidence_refs
        and statement.period == command.period
        and statement.declared_source == command.declared_source
        and statement.rationale == expected_rationale
        and statement.validation_plan == expected_validation_plan
    )


def _answers_through_revision(
    answers: tuple[FounderStatement, ...],
    data_revision: int,
) -> tuple[FounderStatement, ...]:
    return tuple(
        answer
        for answer in answers
        if not isinstance(answer.data_revision, bool) and answer.data_revision <= data_revision
    )


__all__ = [
    "CaseFactIntakeService",
    "CaseMutationDelta",
    "FieldValidationError",
    "SaveFounderStatementCommand",
]
