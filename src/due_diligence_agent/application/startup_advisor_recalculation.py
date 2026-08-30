from __future__ import annotations

import re
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, Literal, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from due_diligence_agent.application.services.case_fact_intake_service import (
    CaseFactIntakeService,
    CaseMutationDelta,
    SaveFounderStatementCommand,
)
from due_diligence_agent.application.startup_cases import _revision_invalidation_values
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
)
from due_diligence_agent.workflows.startup.runtime import StartupWorkflowRuntimeStore

RecalculationAnswerType = Literal["manual", "file", "public_research"]
RecalculationStatus = Literal["not_requested", "started", "deferred"]
RecalculationAnalysisStatus = Literal[
    "awaiting_upload",
    "awaiting_start",
    "gate2_preview_ready",
    "gate3_review_required",
    "analysis_complete_report_pending",
    "failed",
]
_SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:@-]{0,159}$")
FOUNDER_CLARIFICATION_MARKER = "[[founder_clarification:accepted_source]]"
_PROFILE_LABEL_BY_ADVISOR_FIELD = {
    "product": "Description",
    "problem": "Problem",
    "stage": "Stage",
    "revenue_pricing": "Revenue Model",
    "icp": "ICP",
    "traction": "Traction",
    "burn_cash": "Assumptions",
    "gtm_channel": "GTM",
}
_REQUIREMENT_KEY_BY_ADVISOR_FIELD = {
    "product": "solution",
    "problem": "problem",
    "stage": "launch_date",
    "revenue_pricing": "pricing_revenue_model",
    "icp": "icp",
    "traction": "customer_count",
    "burn_cash": "burn",
    "gtm_channel": "channel",
}


class StartupAdvisorRecalculationCommand(BaseModel):
    """Private typed input for one same-case advisor recalculation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    question_id: str = Field(min_length=1, max_length=160, pattern=_SAFE_CODE.pattern)
    field_key: str = Field(min_length=1, max_length=80, pattern=_SAFE_CODE.pattern)
    answer_type: RecalculationAnswerType
    private_value: SecretStr | None = Field(default=None, repr=False)
    document_id: str | None = Field(default=None, max_length=120)
    research_source_ids: tuple[UUID, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_payload(self) -> StartupAdvisorRecalculationCommand:
        if self.answer_type in {"manual", "public_research"} and self.private_value is None:
            raise ValueError("private advisor evidence is required")
        if self.answer_type == "file" and not self.document_id:
            raise ValueError("advisor document binding is required")
        return self


class StartupAdvisorRecalculationResult(BaseModel):
    """Founder-safe proof that a canonical same-case recalculation was attempted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RecalculationStatus
    data_revision: int | None = Field(default=None, ge=1)
    analysis_status: RecalculationAnalysisStatus | None = None
    safe_error_code: str | None = Field(default=None, pattern=_SAFE_CODE.pattern)

    @model_validator(mode="after")
    def validate_result_shape(self) -> StartupAdvisorRecalculationResult:
        if self.status == "started" and (
            self.data_revision is None or self.analysis_status is None
        ):
            raise ValueError("started recalculation requires runtime revision and status")
        if self.status == "deferred" and self.safe_error_code is None:
            raise ValueError("deferred recalculation requires safe error code")
        return self


class StartupAdvisorRecalculationOperationalError(RuntimeError):
    """Expected, founder-safe recalculation failure at an external workflow boundary."""

    def __init__(self, code: str = "advisor_recalculation_failed") -> None:
        super().__init__(code)
        self.code = code


class StartupAdvisorImprovementRecalculationCommand(BaseModel):
    """Private typed input for applying one accepted improvement to the case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    proposal_id: UUID
    target_area: str = Field(min_length=1, max_length=80, pattern=_SAFE_CODE.pattern)
    private_recommendation: SecretStr = Field(repr=False)
    private_rationale: SecretStr = Field(repr=False)
    private_expected_effect: SecretStr = Field(repr=False)

    @model_validator(mode="after")
    def validate_private_text(self) -> StartupAdvisorImprovementRecalculationCommand:
        for value in (
            self.private_recommendation,
            self.private_rationale,
            self.private_expected_effect,
        ):
            if not value.get_secret_value().strip():
                raise ValueError("private improvement text is required")
        return self


class StartupAdvisorRecalculationPort(Protocol):
    def apply_answer(
        self, command: StartupAdvisorRecalculationCommand
    ) -> StartupAdvisorRecalculationResult | dict[str, object]: ...

    def apply_improvement(
        self, command: StartupAdvisorImprovementRecalculationCommand
    ) -> StartupAdvisorRecalculationResult | dict[str, object]: ...


class StartupAdvisorCaseRecalculationAdapter:
    """Projects private advisor evidence through the canonical upload/start boundary."""

    def __init__(
        self,
        *,
        coordinator: Any,
        workflow_store: StartupWorkflowRuntimeStore,
        founder_statement_intake: CaseFactIntakeService | None = None,
        deterministic_founder_statement_intake: CaseFactIntakeService | None = None,
        profile_repository: Any | None = None,
        deterministic_profile_repository: Any | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._workflow_store = workflow_store
        self._founder_statement_intake = founder_statement_intake
        self._deterministic_founder_statement_intake = deterministic_founder_statement_intake
        self._profile_repository = profile_repository
        self._deterministic_profile_repository = deterministic_profile_repository

    def apply_answer(
        self, command: StartupAdvisorRecalculationCommand
    ) -> StartupAdvisorRecalculationResult:
        if command.answer_type == "file":
            return self._reanalyze_existing_document(
                case_id=str(command.case_id),
                document_id=str(command.document_id),
            )
        if command.answer_type == "manual":
            return self._apply_founder_statement(command)
        case_id = str(command.case_id)
        result = self._apply_private_document(
            case_id=case_id,
            filename="advisor-evidence.docx",
            content=_advisor_evidence_docx(command),
            document_class_hint="advisor_evidence",
        )
        return result

    def apply_improvement(
        self, command: StartupAdvisorImprovementRecalculationCommand
    ) -> StartupAdvisorRecalculationResult:
        result = self._apply_private_document(
            case_id=str(command.case_id),
            filename="advisor-improvement.docx",
            content=_advisor_improvement_docx(command),
            document_class_hint="advisor_improvement",
        )
        return result

    def _apply_founder_statement(
        self,
        command: StartupAdvisorRecalculationCommand,
    ) -> StartupAdvisorRecalculationResult:
        runtime = self._workflow_store.load(str(command.case_id))
        founder_statement_intake = self._founder_statement_intake_for(runtime)
        if founder_statement_intake is None:
            return StartupAdvisorRecalculationResult(
                status="deferred",
                safe_error_code="advisor_founder_statement_intake_unavailable",
            )
        if command.private_value is None:
            return StartupAdvisorRecalculationResult(
                status="deferred",
                safe_error_code="advisor_private_value_required",
            )
        revision = runtime.get("data_revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            return StartupAdvisorRecalculationResult(
                status="deferred",
                safe_error_code="advisor_runtime_revision_unavailable",
            )
        fact_command = _advisor_fact_command(command, expected_revision=revision)
        if fact_command is None:
            return StartupAdvisorRecalculationResult(
                status="deferred",
                safe_error_code="advisor_founder_statement_validation_failed",
            )
        delta = founder_statement_intake.save_founder_statement(fact_command)
        return self._mutation_result(
            str(command.case_id),
            delta,
            fact_command=fact_command,
        )

    def _mutation_result(
        self,
        case_id: str,
        delta: CaseMutationDelta,
        *,
        fact_command: SaveFounderStatementCommand | None = None,
    ) -> StartupAdvisorRecalculationResult:
        if not delta.accepted:
            return StartupAdvisorRecalculationResult(
                status="deferred",
                safe_error_code="advisor_founder_statement_validation_failed",
            )
        profile_update = self._project_manual_profile(
            case_id,
            delta,
            fact_command=fact_command,
        )
        updated = self._workflow_store.update(
            case_id,
            lambda runtime: {
                **runtime,
                **_revision_invalidation_values(
                    delta.new_revision,
                    f"{case_id}:r{delta.new_revision}",
                ),
                "analysis_status": "gate2_preview_ready",
                "analysis_start_claim_data_revision": delta.new_revision,
                "analysis_start_claim_thread_id": f"{case_id}:r{delta.new_revision}",
                **profile_update,
            },
        )
        try:
            self._seed_recalculated_analysis(
                case_id=case_id,
                data_revision=delta.new_revision,
                runtime=updated,
            )
        except Exception as exc:  # noqa: BLE001 - boundary must remain founder-safe
            safe_code = _safe_error_code(exc)
            return StartupAdvisorRecalculationResult(
                status="deferred",
                safe_error_code=safe_code,
            )
        return self._runtime_result(case_id)

    def _seed_recalculated_analysis(
        self,
        *,
        case_id: str,
        data_revision: int,
        runtime: dict[str, Any],
    ) -> None:
        documents = [
            item
            for item in runtime.get("documents", [])
            if isinstance(item, dict) and isinstance(item.get("document_id"), str)
        ]
        document_ids = [str(item["document_id"]) for item in documents]
        source_refs = [
            dict(item)
            for item in runtime.get("source_refs", [])
            if isinstance(item, dict)
        ]
        if not document_ids or not source_refs:
            return
        thread_id = f"{case_id}:r{data_revision}"
        payload = {
            "case_id": case_id,
            "run_id": f"startup-api-{case_id}",
            "correlation_id": case_id,
            "source_document_ids": document_ids,
            "source_refs": source_refs,
            "data_revision": data_revision,
            "fixture_mode": runtime.get("fixture_mode"),
            "execution_mode": runtime.get("provider_status"),
        }
        service = self._coordinator._analysis_service_for(
            str(runtime.get("fixture_mode") or "live")
        )
        result = service.start(payload, thread_id=thread_id)
        projected = self._coordinator._project_graph_result(result)
        self._workflow_store.update(
            case_id,
            lambda current: (
                projected
                if current.get("active_analysis_thread_id") == thread_id
                and current.get("data_revision") == data_revision
                else {}
            ),
        )

    def _founder_statement_intake_for(
        self,
        runtime: dict[str, Any],
    ) -> CaseFactIntakeService | None:
        if runtime.get("fixture_mode") == "deterministic_offline":
            return self._deterministic_founder_statement_intake or self._founder_statement_intake
        return self._founder_statement_intake

    def _profile_repository_for(self, runtime: dict[str, Any]) -> Any | None:
        if runtime.get("fixture_mode") == "deterministic_offline":
            return self._deterministic_profile_repository or self._profile_repository
        return self._profile_repository

    def _profile_repositories_for(self, runtime: dict[str, Any]) -> tuple[Any, ...]:
        preferred = self._profile_repository_for(runtime)
        repositories: list[Any] = []
        for repository in (
            preferred,
            self._profile_repository,
            self._deterministic_profile_repository,
        ):
            if repository is not None and all(repository is not item for item in repositories):
                repositories.append(repository)
        return tuple(repositories)

    def _project_manual_profile(
        self,
        case_id: str,
        delta: CaseMutationDelta,
        *,
        fact_command: SaveFounderStatementCommand | None,
    ) -> dict[str, Any]:
        if delta.changed_keys != ("burn",) or fact_command is None:
            return {}
        runtime = self._workflow_store.load(case_id)
        repository = self._profile_repository_for(runtime)
        if repository is None:
            return {}
        try:
            previous = _latest_profile_for_revision(
                repository,
                UUID(case_id),
                delta.old_revision,
            )
        except (KeyError, LookupError, ValueError):
            return {}
        fields = dict(previous.fields)
        profile = StartupProfile.build(
            case_id=UUID(case_id),
            schema_version=previous.schema_version,
            profile_version=previous.profile_version,
            extractor_version=previous.extractor_version,
            analysis_stage=StartupProfileAnalysisStage.PRIMARY,
            parent_profile_id=None,
            data_revision=delta.new_revision,
            source_hashes=previous.source_hashes,
            parse_outcomes=previous.parse_outcomes,
            fields=fields,
            gap_codes=previous.gap_codes,
            contradiction_ids=previous.contradiction_ids,
            case_revision_at=datetime.now(UTC),
        )
        repository.add(profile)
        return {
            "profile_id": str(profile.profile_id),
            "profile_hash": profile.profile_hash,
            "profile_revision": profile.data_revision,
            "primary_profile_id": str(profile.profile_id),
        }

    def _reanalyze_existing_document(
        self,
        *,
        case_id: str,
        document_id: str,
    ) -> StartupAdvisorRecalculationResult:
        try:
            self._coordinator.reanalyze_existing_documents(
                case_id,
                document_ids=[document_id],
                metadata={"document_class_hint": "advisor_file_binding"},
            )
            return self._runtime_result(case_id)
        except StartupAdvisorRecalculationOperationalError as exc:
            return StartupAdvisorRecalculationResult(status="deferred", safe_error_code=exc.code)

    def _apply_private_document(
        self,
        *,
        case_id: str,
        filename: str,
        content: bytes,
        document_class_hint: str,
    ) -> StartupAdvisorRecalculationResult:
        try:
            self._coordinator.upload_documents(
                case_id,
                files=[
                    {
                        "filename": filename,
                        "content_type": (
                            "application/vnd.openxmlformats-officedocument."
                            "wordprocessingml.document"
                        ),
                        "content": content,
                    }
                ],
                auto_start=True,
                metadata={"document_class_hint": document_class_hint},
            )
            return self._runtime_result(case_id)
        except StartupAdvisorRecalculationOperationalError as exc:
            return StartupAdvisorRecalculationResult(status="deferred", safe_error_code=exc.code)

    def _runtime_result(self, case_id: str) -> StartupAdvisorRecalculationResult:
        runtime = self._workflow_store.load(case_id)
        revision = runtime.get("data_revision")
        analysis_status = runtime.get("analysis_status")
        return StartupAdvisorRecalculationResult.model_validate(
            {
                "status": "started",
                "data_revision": revision,
                "analysis_status": analysis_status,
                "safe_error_code": None,
            }
        )


def _advisor_evidence_docx(command: StartupAdvisorRecalculationCommand) -> bytes:
    if command.private_value is None:
        raise ValueError("advisor_private_value_required")
    label = _PROFILE_LABEL_BY_ADVISOR_FIELD.get(command.field_key, "Assumptions")
    value = f"{label}: {command.private_value.get_secret_value()}"
    if command.answer_type == "manual":
        value = f"{value} {FOUNDER_CLARIFICATION_MARKER}"
    return _private_docx((value,))


def _advisor_requirement_key(field_key: str) -> str:
    return _REQUIREMENT_KEY_BY_ADVISOR_FIELD.get(field_key, field_key)


def _advisor_fact_command(
    command: StartupAdvisorRecalculationCommand,
    *,
    expected_revision: int,
) -> SaveFounderStatementCommand | None:
    if command.private_value is None:
        return None
    requirement_key = _advisor_requirement_key(command.field_key)
    raw_value = command.private_value.get_secret_value()
    update: dict[str, object] = {
        "case_id": command.case_id,
        "requirement_key": requirement_key,
        "value": raw_value,
        "declared_source": f"advisor manual answer:{command.question_id}",
        "expected_case_revision": expected_revision,
        "idempotency_key": f"advisor-answer:{command.case_id}:{command.field_key}:{command.answer_type}",
    }
    if requirement_key == "burn":
        amount = _extract_money_amount(raw_value, ("monthly net burn", "net burn", "burn"))
        period = _extract_month_period(raw_value)
        if amount is None or period is None:
            return None
        update["value"] = amount
        update["currency"] = "USD" if "$" in raw_value else "KZT"
        update["scale"] = "ones"
        update["period"] = period
    return SaveFounderStatementCommand.model_validate(update)


def _extract_money_amount(value: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        pattern = rf"{re.escape(label)}\s+\$?([0-9][0-9,._ ]*)"
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match is not None:
            normalized = re.sub(r"[^0-9.]", "", match.group(1))
            return normalized or None
    return None


def _extract_month_period(value: str) -> str | None:
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b",
        value,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }
    return f"{match.group(2)}-{months[match.group(1).casefold()]}"


def _latest_profile_for_revision(
    repository: Any,
    case_id: UUID,
    data_revision: int,
) -> StartupProfile:
    getter = getattr(repository, "get_for_stage", None)
    if callable(getter):
        return cast(
            StartupProfile,
            getter(case_id, data_revision, StartupProfileAnalysisStage.PRIMARY),
        )
    profiles = [
        cast(StartupProfile, profile)
        for profile in repository.list_for_case(case_id)
        if profile.data_revision == data_revision
        and profile.analysis_stage is StartupProfileAnalysisStage.PRIMARY
    ]
    if not profiles:
        raise KeyError(f"startup_profile_stage_not_found:{case_id}:{data_revision}")
    return profiles[-1]


def is_founder_clarification_text(text: str) -> bool:
    return FOUNDER_CLARIFICATION_MARKER in text


def without_founder_clarification_marker(text: str) -> str:
    return text.replace(FOUNDER_CLARIFICATION_MARKER, "").strip()


def _advisor_improvement_docx(
    command: StartupAdvisorImprovementRecalculationCommand,
) -> bytes:
    return _private_docx(
        (
            (
                "Assumptions: Founder accepted a plan improvement for "
                f"{command.target_area}."
            ),
            f"Rationale: {command.private_rationale.get_secret_value()}",
            f"Expected effect: {command.private_expected_effect.get_secret_value()}",
        )
    )


def _private_docx(paragraphs: tuple[str, ...]) -> bytes:
    from docx import Document

    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def _safe_error_code(exc: Exception) -> str:
    raw = getattr(exc, "code", None)
    candidate = raw if isinstance(raw, str) else exc.__class__.__name__
    normalized = re.sub(r"[^a-z0-9_.:@-]+", "_", candidate.casefold()).strip("_")
    return (normalized or "advisor_recalculation_failed")[:160]
