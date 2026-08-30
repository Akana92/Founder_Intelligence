from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from decimal import Decimal
import re
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.reports.models import (
    ReportSnapshot,
    ReproducibilityManifest,
)
from due_diligence_agent.application.services.startup_advisor_service import (
    StartupAdvisorService,
    advisor_field_key_for_contradiction,
    safe_contradiction_context,
)
from due_diligence_agent.application.services.startup_improvement_service import (
    StartupImprovementService,
)
from due_diligence_agent.application.startup_advisor_recalculation import (
    StartupAdvisorImprovementRecalculationCommand,
    StartupAdvisorRecalculationOperationalError,
    StartupAdvisorRecalculationCommand,
    StartupAdvisorRecalculationPort,
    StartupAdvisorRecalculationResult,
)
from due_diligence_agent.application.startup_cases import (
    StartupGateConflict,
    StartupNotFound,
    StartupValidationError,
)
from due_diligence_agent.domain.startup.advisor import (
    AdvisorAnswer,
    AdvisorQuestion,
    AdvisorResearchDelta,
    AnswerType,
    StartupImprovementProposal,
)
from due_diligence_agent.domain.startup.market import StartupMarketResearchSnapshot
from due_diligence_agent.domain.startup.readiness import StartupReadinessSnapshot
from due_diligence_agent.workflows.startup.runtime import StartupWorkflowRuntimeStore


_STATE_KEY = "startup_advisor_api_v1"
_PROPOSAL_INDEX_RECORD = "__startup_advisor_api_v1_proposal_index__"
_MAX_MANUAL_VALUE_LENGTH = 2000
_TOTAL_QUESTIONS = 8
_ADVISOR_DRAFT_REPORT_VERSION = "advisor-draft@1"
_ADVISOR_PROFILE_FIELD_KEYS = {
    "product": "one_line_description",
    "problem": "problem",
    "stage": "stage",
    "revenue_pricing": "pricing_revenue_model",
    "icp": "icp",
    "traction": "traction",
    "burn_cash": "metric_pack_candidates",
    "gtm_channel": "channels_gtm",
}
_BARE_PERCENT_RE = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*%\s*$")
_REVENUE_PRICING_SIGNAL_RE = re.compile(
    r"(?iu)(mrr|arr|revenue|выруч|цена|прайс|pricing|тариф|подписк|\$|usd|eur|kzt|₸|тенге|руб|месяц|month)"
)
_ICP_SIGNAL_RE = re.compile(
    r"(?iu)(icp|аудитор|сегмент|клиент|покупател|persona|персон|distributor|retail|manager|director|buyer|customer|segment)"
)
_MARGIN_SIGNAL_RE = re.compile(r"(?iu)(gross\s*margin|валов\w*\s+марж|марж)")
_CONTRADICTION_KEEP_OPEN_RE = re.compile(
    r"(?iu)(keep\s+(?:it\s+)?open|остав(?:ить|ьте).{0,30}открыт|не\s+закрыва)"
)
_CONTRADICTION_VALUE_RE = re.compile(
    r"(?iu)(\d+(?:[.,]\d+)?\s*(?:m|k|млн|тыс|%|kzt|₸|тенге|months?|мес)?)"
)
_CONTRADICTION_SOURCE_RE = re.compile(
    r"(?iu)(crm|invoice|invoices|bank|банк|сч[её]т|акт|finance|финанс|ops|операц)"
)
_CONTRADICTION_PERIOD_RE = re.compile(
    r"(?iu)(20\d{2}|q[1-4]|январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр|january|february|march|april|may|june|july|august|september|october|november|december)"
)
_CORE_ADVISOR_FIELD_KEYS = frozenset(
    {"product", "problem", "stage", "revenue_pricing", "icp"}
)
_CORE_PROFILE_FIELD_KEYS = frozenset(
    _ADVISOR_PROFILE_FIELD_KEYS[field_key] for field_key in _CORE_ADVISOR_FIELD_KEYS
)
_OPEN_CONTRADICTION_STATUSES = frozenset({"open", "awaiting_evidence", "unresolved"})
_SAFE_METRIC_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_PRIVATE_METRIC_NAME_RE = re.compile(
    r"(?i)([a-z]:[\\/]|\\\\|/users?/|/home/|sha256:|sk-(?:live|proj)|secret|bearer\s+|@)"
)


class AdvisorQuestionDto(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    field_key: str
    question_ru: str
    reason_ru: str
    unlocks_ru: str
    answer_modes: tuple[AnswerType, ...]
    origin: Literal[
        "static",
        "document_gap",
        "document_contradiction",
        "answered_state",
    ] = "static"
    origin_label_ru: str = "Базовый сценарий"
    context_ru: str | None = None
    answer_mode_labels_ru: dict[AnswerType, str]


class AdvisorNextQuestionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    status: Literal["active", "complete"]
    next_question: AdvisorQuestionDto | None
    answered_count: int = Field(ge=0, le=_TOTAL_QUESTIONS)
    total_count: int = _TOTAL_QUESTIONS


class AdvisorResearchResultDto(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["completed", "partial", "deferred", "blocked"]
    summary_ru: str
    source_ids: tuple[UUID, ...]
    fallback_used: bool
    fail_reason_ru: str | None


class AdvisorRecalculationDeltaDto(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    previous_revision: int
    new_revision: int
    fields_changed: tuple[str, ...]
    core_coverage_delta: int
    conflicts_resolved: int = Field(ge=0)
    conflicts_remaining: int = Field(ge=0)
    calculations_recalculated: tuple[str, ...] = ()
    calculations_pending: tuple[str, ...] = ()


class AdvisorAnswerResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    question_id: str
    field_key: str
    answer_type: AnswerType
    status: Literal["applied", "blocked"]
    confidence_delta: int
    analysis_blocked: bool
    answered_count: int = Field(ge=0, le=_TOTAL_QUESTIONS)
    total_count: int = _TOTAL_QUESTIONS
    research_result: AdvisorResearchResultDto | None = None
    recalculation_status: Literal["not_requested", "started", "deferred"] = (
        "not_requested"
    )
    recalculation_data_revision: int | None = Field(default=None, ge=1)
    recalculation_analysis_status: str | None = None
    recalculation_delta: AdvisorRecalculationDeltaDto | None = None


class StartupImprovementProposalDto(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: UUID
    target_area: str
    recommendation_ru: str
    rationale_ru: str
    expected_effect_ru: str
    evidence_kinds: tuple[str, ...]
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))


class StartupImprovementsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    improvement_version: int = Field(ge=1)
    proposals: tuple[StartupImprovementProposalDto, ...]


class StartupImprovementDecisionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    proposal_id: UUID
    decision: Literal["accepted", "rejected"]
    previous_version: int = Field(ge=1)
    new_version: int = Field(ge=1)
    changed_fields: tuple[str, ...]
    recalculation_status: Literal["not_requested", "started", "deferred"] = (
        "not_requested"
    )
    recalculation_data_revision: int | None = Field(default=None, ge=1)
    recalculation_analysis_status: str | None = None


@dataclass(frozen=True)
class StartupAdvisorApiContext:
    case_repository: Any
    profile_repository: Any
    report_repository: Any
    calculation_repository: Any
    contradiction_repository: Any
    gtm_repository: Any | None
    intelligence_store: StartupWorkflowRuntimeStore
    research_service: Any
    evidence_repository: Any | None = None


@dataclass(frozen=True)
class _AdvisorProgressCounts:
    answered_count: int
    total_count: int


class StartupAdvisorApiService:
    """Restart-safe founder API facade over existing advisor domain services."""

    def __init__(
        self,
        *,
        workflow_store: StartupWorkflowRuntimeStore,
        live_context: StartupAdvisorApiContext,
        deterministic_context: StartupAdvisorApiContext,
        recalculation_port: StartupAdvisorRecalculationPort | None = None,
    ) -> None:
        self._workflow_store = workflow_store
        self._live_context = live_context
        self._deterministic_context = deterministic_context
        self._improvements = StartupImprovementService()
        self._recalculation_port = recalculation_port

    def get_next_question(self, case_id: str) -> AdvisorNextQuestionResponse:
        case_uuid, runtime, context = self._resolve(case_id)
        state = self._state(runtime)
        advisor = self._replay(case_uuid, state)
        profile_field_statuses = self._profile_field_statuses(context, case_uuid)
        contradiction_contexts = self._contradiction_contexts(context, case_uuid)
        question = advisor.next_question(
            case_uuid,
            profile_field_statuses=profile_field_statuses,
            contradiction_contexts=contradiction_contexts,
        )
        progress = self._advisor_progress_counts(
            advisor=advisor,
            answers=self._answers(state),
            profile_field_statuses=profile_field_statuses,
            contradiction_contexts=contradiction_contexts,
        )
        return AdvisorNextQuestionResponse(
            case_id=case_id,
            status="complete" if question is None else "active",
            next_question=(
                AdvisorQuestionDto.model_validate(question.model_dump(mode="python"))
                if question is not None
                else None
            ),
            answered_count=progress.answered_count,
            total_count=progress.total_count,
        )

    def submit_answer(
        self,
        case_id: str,
        *,
        question_id: str,
        answer_type: AnswerType,
        value: str | None = None,
        document_id: str | None = None,
        consent_public_research: bool = False,
    ) -> AdvisorAnswerResponse:
        case_uuid, runtime, context = self._resolve(case_id)
        state = self._state(runtime)
        advisor = self._replay(case_uuid, state)
        profile_field_statuses = self._profile_field_statuses(context, case_uuid)
        contradiction_contexts = self._contradiction_contexts(context, case_uuid)
        question = advisor.next_question(
            case_uuid,
            profile_field_statuses=profile_field_statuses,
            contradiction_contexts=contradiction_contexts,
        )
        self._validate_question(case_id, question_id, question)
        assert question is not None
        self._validate_answer_shape(
            runtime=runtime,
            question=question,
            answer_type=answer_type,
            value=value,
            document_id=document_id,
        )
        answer = AdvisorAnswer(
            answer_type=answer_type,
            value=(value if answer_type == "manual" else None),
            consent_public_research=consent_public_research,
        )

        research_delta: AdvisorResearchDelta | None = None
        if answer_type == "public_research":
            if not consent_public_research or answer_type not in question.answer_modes:
                research_delta = AdvisorResearchDelta(
                    status="blocked",
                    summary_ru=(
                        "Публичный поиск заблокирован: требуется явное согласие."
                        if not consent_public_research
                        else "Публичный поиск недоступен для внутреннего вопроса."
                    ),
                    fail_reason_ru=(
                        "Нет явного согласия на публичный поиск."
                        if not consent_public_research
                        else "Внутренние данные нельзя передавать в публичный поиск."
                    ),
                )
                self._record_research_status(
                    case_id=case_id,
                    state=state,
                    question=question,
                    delta=research_delta,
                )
                progress = self._advisor_progress_counts(
                    advisor=advisor,
                    answers=self._answers(state),
                    profile_field_statuses=profile_field_statuses,
                    contradiction_contexts=contradiction_contexts,
                )
                return self._answer_response(
                    case_id=case_id,
                    question=question,
                    answer_type=answer_type,
                    status="blocked",
                    answered_count=progress.answered_count,
                    total_count=progress.total_count,
                    research_delta=research_delta,
                )
            research_delta = context.research_service.research(case_uuid, question, answer)
            self._record_research_status(
                case_id=case_id,
                state=state,
                question=question,
                delta=research_delta,
            )
            if research_delta.status in {"blocked", "deferred"}:
                progress = self._advisor_progress_counts(
                    advisor=advisor,
                    answers=self._answers(state),
                    profile_field_statuses=profile_field_statuses,
                    contradiction_contexts=contradiction_contexts,
                )
                return self._answer_response(
                    case_id=case_id,
                    question=question,
                    answer_type=answer_type,
                    status="blocked",
                    answered_count=progress.answered_count,
                    total_count=progress.total_count,
                    research_delta=research_delta,
                )

        delta = advisor.apply_answer(
            case_uuid,
            question_id,
            answer,
            profile_field_statuses=profile_field_statuses,
            contradiction_contexts=contradiction_contexts,
        )
        profile_snapshot_before = self._profile_source_snapshot(context, case_uuid)
        open_conflict_ids_before = self._open_contradiction_ids(context, case_uuid)
        calculation_snapshot_before = self._calculation_snapshot(context, case_uuid)
        evidence_fact_ids_before = self._evidence_fact_ids(context, case_uuid)
        binding: dict[str, Any] = {
            "question_id": question.question_id,
            "field_key": question.field_key,
            "answer_type": answer_type,
        }
        if answer_type == "file":
            binding["document_id"] = document_id
        if research_delta is not None:
            binding["research_status"] = research_delta.status
            binding["source_ids"] = [str(item) for item in research_delta.source_ids]
        recalculation = self._recalculate_answer(
            case_id=case_id,
            runtime_before=runtime,
            question=question,
            answer_type=answer_type,
            value=value,
            document_id=document_id,
            research_delta=research_delta,
        )
        self._reconcile_founder_clarification(
            context=context,
            case_id=case_uuid,
            question=question,
            answer_type=answer_type,
            recalculation=recalculation,
            evidence_fact_ids_before=evidence_fact_ids_before,
        )
        binding["recalculation"] = recalculation.model_dump(mode="json")
        answers = [*self._answers(state), binding]
        state["answers"] = answers
        self._save_state(case_id, state)
        progress = self._advisor_progress_counts(
            advisor=advisor,
            answers=answers,
            profile_field_statuses=profile_field_statuses,
            contradiction_contexts=contradiction_contexts,
        )
        return AdvisorAnswerResponse(
            case_id=case_id,
            question_id=question.question_id,
            field_key=question.field_key,
            answer_type=answer_type,
            status="applied",
            confidence_delta=delta.confidence_delta,
            analysis_blocked=delta.analysis_blocked,
            answered_count=progress.answered_count,
            total_count=progress.total_count,
            research_result=self._research_dto(research_delta),
            recalculation_status=recalculation.status,
            recalculation_data_revision=recalculation.data_revision,
            recalculation_analysis_status=recalculation.analysis_status,
            recalculation_delta=self._recalculation_delta(
                case_id=case_id,
                context=context,
                case_uuid=case_uuid,
                runtime_before=runtime,
                answer_type=answer_type,
                recalculation=recalculation,
                profile_snapshot_before=profile_snapshot_before,
                open_conflict_ids_before=open_conflict_ids_before,
                calculation_snapshot_before=calculation_snapshot_before,
            ),
        )

    def list_improvements(self, case_id: str) -> StartupImprovementsResponse:
        case_uuid, runtime, context = self._resolve(case_id)
        state = self._state(runtime)
        version = self._improvement_version(state)
        case, report, proposals = self._generate_proposals(
            case_id=case_uuid,
            runtime=runtime,
            context=context,
            improvement_version=version,
        )
        state["proposal_base"] = {
            "case_id": case_id,
            "source": (
                "advisor_draft"
                if report.prompt_versions.get("report") == _ADVISOR_DRAFT_REPORT_VERSION
                else "canonical_report"
            ),
            "report_id": str(report.id),
            "report_hash": report.report_hash,
            "case_revision": case.data_revision,
            "improvement_version": version,
            "proposal_ids": [str(item.proposal_id) for item in proposals],
        }
        self._save_state(case_id, state)
        self._index_proposals(case_id, proposals)
        return StartupImprovementsResponse(
            case_id=case_id,
            improvement_version=version,
            proposals=tuple(self._proposal_dto(item) for item in proposals),
        )

    def decide_improvement(
        self,
        case_id: str,
        *,
        proposal_id: UUID,
        decision: Literal["accepted", "rejected"],
    ) -> StartupImprovementDecisionResponse:
        case_uuid, runtime, context = self._resolve(case_id)
        state = self._state(runtime)
        proposal_key = str(proposal_id)
        ledger = self._decision_ledger(state)
        prior = ledger.get(proposal_key)
        if isinstance(prior, dict):
            if prior.get("decision") != decision:
                raise StartupGateConflict("advisor_decision_conflict")
            return StartupImprovementDecisionResponse.model_validate(prior)

        owner = self._proposal_owner(proposal_key)
        if owner is None:
            raise StartupGateConflict("advisor_proposal_unknown")
        if owner != case_id:
            raise StartupGateConflict("advisor_proposal_cross_case")
        base = state.get("proposal_base")
        if not isinstance(base, dict) or proposal_key not in base.get("proposal_ids", []):
            raise StartupGateConflict("advisor_proposal_stale")
        if not self._lineage_is_current(runtime, base):
            raise StartupGateConflict("advisor_proposal_stale")

        version = self._improvement_version(state)
        if base.get("improvement_version") != version:
            raise StartupGateConflict("advisor_proposal_stale")
        case, report, proposals = self._generate_proposals(
            case_id=case_uuid,
            runtime=runtime,
            context=context,
            improvement_version=version,
        )
        if proposal_id not in {item.proposal_id for item in proposals}:
            raise StartupGateConflict("advisor_proposal_stale")
        delta = self._improvements.apply_decision(
            case=case,
            base_report_snapshot=report,
            proposals=proposals,
            previous_version=version,
            accepted_proposal_ids=(proposal_id,) if decision == "accepted" else (),
            rejected_proposal_ids=(proposal_id,) if decision == "rejected" else (),
        )
        selected_proposal = next(
            item for item in proposals if item.proposal_id == proposal_id
        )
        recalculation = self._recalculate_improvement(
            case_id=case_id,
            decision=decision,
            proposal=selected_proposal,
        )
        response = StartupImprovementDecisionResponse(
            case_id=case_id,
            proposal_id=proposal_id,
            decision=decision,
            previous_version=delta.previous_version,
            new_version=delta.new_version,
            changed_fields=delta.changed_fields,
            recalculation_status=recalculation.status,
            recalculation_data_revision=recalculation.data_revision,
            recalculation_analysis_status=recalculation.analysis_status,
        )
        ledger[proposal_key] = response.model_dump(mode="json")
        state["decision_ledger"] = ledger
        state["improvement_version"] = delta.new_version
        if decision == "accepted":
            state.pop("proposal_base", None)
        self._save_state(case_id, state)
        return response

    def _resolve(
        self, case_id: str
    ) -> tuple[UUID, dict[str, Any], StartupAdvisorApiContext]:
        try:
            case_uuid = UUID(case_id)
        except ValueError:
            raise StartupNotFound("case_not_found") from None
        runtime = self._workflow_store.load(case_id)
        if runtime.get("case_exists") is not True:
            raise StartupNotFound("case_not_found")
        context = (
            self._deterministic_context
            if runtime.get("fixture_mode") == "deterministic_offline"
            else self._live_context
        )
        return case_uuid, runtime, context

    @staticmethod
    def _state(runtime: dict[str, Any]) -> dict[str, Any]:
        state = runtime.get(_STATE_KEY)
        return dict(state) if isinstance(state, dict) else {}

    @staticmethod
    def _answers(state: dict[str, Any]) -> list[dict[str, Any]]:
        raw = state.get("answers")
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]

    @staticmethod
    def _decision_ledger(state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("decision_ledger")
        return dict(raw) if isinstance(raw, dict) else {}

    @staticmethod
    def _improvement_version(state: dict[str, Any]) -> int:
        raw = state.get("improvement_version", 1)
        return raw if isinstance(raw, int) and raw >= 1 else 1

    def _replay(self, case_id: UUID, state: dict[str, Any]) -> StartupAdvisorService:
        advisor = StartupAdvisorService()
        for binding in self._answers(state):
            question_id = binding.get("question_id")
            field_key = binding.get("field_key")
            if not isinstance(question_id, str) or not isinstance(field_key, str):
                raise StartupGateConflict("advisor_progress_invalid")
            bound_field_key = self._bound_field_key(case_id, question_id)
            if bound_field_key != field_key:
                raise StartupGateConflict("advisor_progress_invalid")
            answer_type = binding.get("answer_type")
            if answer_type not in {"manual", "file", "public_research", "skip"}:
                raise StartupGateConflict("advisor_progress_invalid")
            try:
                AdvisorAnswer(
                    answer_type=cast(AnswerType, answer_type),
                    consent_public_research=answer_type == "public_research",
                )
            except ValueError:
                raise StartupGateConflict("advisor_progress_invalid") from None
            try:
                advisor.mark_answered(case_id, field_key)
            except ValueError:
                raise StartupGateConflict("advisor_progress_invalid") from None
        return advisor

    @staticmethod
    def _bound_field_key(case_id: UUID, question_id: str) -> str:
        prefix, separator, field_key = question_id.partition(":")
        if separator:
            if prefix != str(case_id) or not field_key:
                raise StartupGateConflict("advisor_progress_invalid")
            return field_key
        return question_id

    @staticmethod
    def _validate_question(
        case_id: str,
        question_id: str,
        current: AdvisorQuestion | None,
    ) -> None:
        prefix, separator, _field = question_id.partition(":")
        if separator and prefix != case_id:
            raise StartupGateConflict("advisor_question_cross_case")
        if current is None or current.question_id != question_id:
            raise StartupGateConflict("advisor_question_stale")

    @staticmethod
    def _validate_answer_shape(
        *,
        runtime: dict[str, Any],
        question: AdvisorQuestion,
        answer_type: AnswerType,
        value: str | None,
        document_id: str | None,
    ) -> None:
        if answer_type not in {"manual", "file", "public_research", "skip"}:
            raise StartupValidationError("advisor_answer_type_invalid")
        if answer_type == "manual":
            if value is None or not value.strip() or len(value) > _MAX_MANUAL_VALUE_LENGTH:
                raise StartupValidationError("advisor_manual_answer_invalid")
            StartupAdvisorApiService._validate_manual_answer_semantics(question, value)
        elif value is not None:
            raise StartupValidationError("advisor_answer_shape_invalid")
        if answer_type == "file":
            document_ids = runtime.get("document_ids", [])
            if document_id is None or document_id not in document_ids:
                raise StartupGateConflict("advisor_document_not_in_case")
        elif document_id is not None:
            raise StartupValidationError("advisor_answer_shape_invalid")
        if answer_type != "public_research" and answer_type not in question.answer_modes:
            raise StartupValidationError("advisor_answer_type_unavailable")

    @staticmethod
    def _validate_manual_answer_semantics(question: AdvisorQuestion, value: str) -> None:
        normalized = " ".join(value.strip().split())
        if question.origin == "document_contradiction":
            if _CONTRADICTION_KEEP_OPEN_RE.search(normalized):
                return
            if (
                _CONTRADICTION_VALUE_RE.search(normalized) is None
                or _CONTRADICTION_SOURCE_RE.search(normalized) is None
                or _CONTRADICTION_PERIOD_RE.search(normalized) is None
            ):
                raise StartupValidationError("advisor_manual_answer_semantic_mismatch")
            return
        if question.field_key == "revenue_pricing":
            if _BARE_PERCENT_RE.fullmatch(normalized) or _REVENUE_PRICING_SIGNAL_RE.search(normalized) is None:
                raise StartupValidationError("advisor_manual_answer_semantic_mismatch")
        elif question.field_key == "icp":
            if _ICP_SIGNAL_RE.search(normalized) is None:
                raise StartupValidationError("advisor_manual_answer_semantic_mismatch")
        elif question.field_key == "traction" and _MARGIN_SIGNAL_RE.search(
            f"{question.question_ru} {question.context_ru or ''} {normalized}"
        ):
            if _BARE_PERCENT_RE.fullmatch(normalized):
                raise StartupValidationError("advisor_manual_answer_semantic_mismatch")

    @staticmethod
    def _answer_response(
        *,
        case_id: str,
        question: AdvisorQuestion,
        answer_type: AnswerType,
        status: Literal["applied", "blocked"],
        answered_count: int,
        research_delta: AdvisorResearchDelta,
        total_count: int,
    ) -> AdvisorAnswerResponse:
        return AdvisorAnswerResponse(
            case_id=case_id,
            question_id=question.question_id,
            field_key=question.field_key,
            answer_type=answer_type,
            status=status,
            confidence_delta=0,
            analysis_blocked=status == "blocked",
            answered_count=answered_count,
            total_count=total_count,
            research_result=StartupAdvisorApiService._research_dto(research_delta),
        )

    @staticmethod
    def _advisor_progress_counts(
        *,
        advisor: StartupAdvisorService,
        answers: list[dict[str, Any]],
        profile_field_statuses: dict[str, str],
        contradiction_contexts: tuple[dict[str, object], ...],
    ) -> _AdvisorProgressCounts:
        answered_field_keys = {
            field_key
            for answer in answers
            if isinstance((field_key := answer.get("field_key")), str)
        }
        question_universe = set(
            advisor.total_field_keys(
                profile_field_statuses=profile_field_statuses,
                contradiction_contexts=contradiction_contexts,
            )
        )
        question_universe.update(answered_field_keys)
        return _AdvisorProgressCounts(
            answered_count=len(answered_field_keys),
            total_count=len(question_universe),
        )

    def _recalculate_answer(
        self,
        *,
        case_id: str,
        runtime_before: dict[str, Any],
        question: AdvisorQuestion,
        answer_type: AnswerType,
        value: str | None,
        document_id: str | None,
        research_delta: AdvisorResearchDelta | None,
    ) -> StartupAdvisorRecalculationResult:
        if answer_type == "skip" or self._recalculation_port is None:
            return StartupAdvisorRecalculationResult(status="not_requested")
        private_value: SecretStr | None = None
        if answer_type == "manual" and value is not None:
            private_value = SecretStr(value)
        elif answer_type == "public_research" and research_delta is not None:
            private_value = SecretStr(research_delta.summary_ru)
        try:
            command = StartupAdvisorRecalculationCommand(
                case_id=UUID(case_id),
                question_id=question.question_id,
                field_key=question.field_key,
                answer_type=answer_type,
                private_value=private_value,
                document_id=document_id,
                research_source_ids=(
                    research_delta.source_ids if research_delta is not None else ()
                ),
            )
            return StartupAdvisorRecalculationResult.model_validate(
                self._recalculation_port.apply_answer(command)
            )
        except StartupAdvisorRecalculationOperationalError as exc:
            return StartupAdvisorRecalculationResult(
                status="deferred",
                safe_error_code=exc.code,
            )
        except ValidationError:
            raise StartupGateConflict("advisor_recalculation_contract_invalid") from None

    @staticmethod
    def _reconcile_founder_clarification(
        *,
        context: StartupAdvisorApiContext,
        case_id: UUID,
        question: AdvisorQuestion,
        answer_type: AnswerType,
        recalculation: StartupAdvisorRecalculationResult,
        evidence_fact_ids_before: frozenset[UUID],
    ) -> None:
        del (
            context,
            case_id,
            question,
            answer_type,
            recalculation,
            evidence_fact_ids_before,
        )

    def _recalculation_delta(
        self,
        *,
        case_id: str,
        context: StartupAdvisorApiContext,
        case_uuid: UUID,
        runtime_before: dict[str, Any],
        answer_type: AnswerType,
        recalculation: StartupAdvisorRecalculationResult,
        profile_snapshot_before: dict[str, tuple[str, ...]],
        open_conflict_ids_before: frozenset[UUID],
        calculation_snapshot_before: dict[str, tuple[tuple[str, ...], ...]],
    ) -> AdvisorRecalculationDeltaDto | None:
        if answer_type == "skip" or recalculation.status != "started":
            return None
        previous_revision = runtime_before.get("data_revision")
        if type(previous_revision) is not int:
            return None
        runtime_after = self._workflow_store.load(case_id)
        new_revision = recalculation.data_revision
        if new_revision is None and type(runtime_after.get("data_revision")) is int:
            new_revision = int(runtime_after["data_revision"])
        if new_revision is None or new_revision <= previous_revision:
            return None
        profile_snapshot_after = self._profile_source_snapshot(context, case_uuid)
        open_conflict_ids_after = self._open_contradiction_ids(context, case_uuid)
        calculation_snapshot_after = self._calculation_snapshot(context, case_uuid)
        changed_profile_fields = tuple(
            sorted(
                field_name
                for field_name in (
                    profile_snapshot_before.keys() | profile_snapshot_after.keys()
                )
                if profile_snapshot_before.get(field_name)
                != profile_snapshot_after.get(field_name)
            )
        )
        core_before = _CORE_PROFILE_FIELD_KEYS.intersection(profile_snapshot_before.keys())
        core_after = _CORE_PROFILE_FIELD_KEYS.intersection(profile_snapshot_after.keys())
        recalculated_metric_names = tuple(
            sorted(
                metric_name
                for metric_name in (
                    calculation_snapshot_before.keys()
                    | calculation_snapshot_after.keys()
                )
                if calculation_snapshot_before.get(metric_name)
                != calculation_snapshot_after.get(metric_name)
            )
        )
        report_before_ready = runtime_before.get("report_status") == "ready"
        report_after_pending = runtime_after.get("report_status") in {"not_ready", "pending"}
        return AdvisorRecalculationDeltaDto(
            previous_revision=previous_revision,
            new_revision=new_revision,
            fields_changed=changed_profile_fields,
            core_coverage_delta=len(core_after) - len(core_before),
            conflicts_resolved=len(open_conflict_ids_before - open_conflict_ids_after),
            conflicts_remaining=len(open_conflict_ids_after),
            calculations_recalculated=recalculated_metric_names,
            calculations_pending=(
                ("report",) if report_after_pending or report_before_ready else ()
            ),
        )

    def _recalculate_improvement(
        self,
        *,
        case_id: str,
        decision: Literal["accepted", "rejected"],
        proposal: StartupImprovementProposal,
    ) -> StartupAdvisorRecalculationResult:
        if decision == "rejected" or self._recalculation_port is None:
            return StartupAdvisorRecalculationResult(status="not_requested")
        try:
            command = StartupAdvisorImprovementRecalculationCommand(
                case_id=UUID(case_id),
                proposal_id=proposal.proposal_id,
                target_area=proposal.target_area.value,
                private_recommendation=SecretStr(proposal.recommendation_ru),
                private_rationale=SecretStr(proposal.rationale_ru),
                private_expected_effect=SecretStr(proposal.expected_effect_ru),
            )
            return StartupAdvisorRecalculationResult.model_validate(
                self._recalculation_port.apply_improvement(command)
            )
        except StartupAdvisorRecalculationOperationalError as exc:
            return StartupAdvisorRecalculationResult(
                status="deferred",
                safe_error_code=exc.code,
            )
        except ValidationError:
            raise StartupGateConflict("advisor_recalculation_contract_invalid") from None

    @staticmethod
    def _research_dto(
        delta: AdvisorResearchDelta | None,
    ) -> AdvisorResearchResultDto | None:
        if delta is None:
            return None
        return AdvisorResearchResultDto.model_validate(delta.model_dump(mode="python"))

    def _generate_proposals(
        self,
        *,
        case_id: UUID,
        runtime: dict[str, Any],
        context: StartupAdvisorApiContext,
        improvement_version: int,
    ) -> tuple[Any, Any, tuple[StartupImprovementProposal, ...]]:
        try:
            case = context.case_repository.get(case_id)
            profile = context.profile_repository.get_current(case_id)
            report_id = UUID(str(runtime["canonical_report_snapshot_id"]))
            report = context.report_repository.get_snapshot(report_id)
            if not self._lineage_is_current(
                runtime,
                {
                    "source": "canonical_report",
                    "report_id": str(report.id),
                    "report_hash": report.report_hash,
                    "case_revision": case.data_revision,
                },
            ):
                raise StartupGateConflict("advisor_improvements_not_ready")
        except (KeyError, ValueError):
            state = self._state(runtime)
            if not self._answers(state):
                raise StartupGateConflict("advisor_improvements_not_ready") from None
            report = self._advisor_draft_report_snapshot(
                case=case,
                runtime=runtime,
                answers=self._answers(state),
            )
        intelligence = context.intelligence_store.load(str(case_id))
        readiness = self._artifact_snapshot(
            intelligence, "startup_readiness_artifact", StartupReadinessSnapshot
        )
        market = self._artifact_snapshot(
            intelligence,
            "startup_market_research_artifact",
            StartupMarketResearchSnapshot,
        )
        gtm = None
        if context.gtm_repository is not None and intelligence.get("gtm_snapshot_id"):
            try:
                gtm = context.gtm_repository.get_current(str(case_id))
            except (KeyError, ValueError):
                raise StartupGateConflict("advisor_improvements_not_ready") from None
        try:
            calculations = context.calculation_repository.list_for_case(case_id)
            contradictions = context.contradiction_repository.list_for_case(case_id)
            proposals = self._improvements.generate_proposals(
                case=case,
                base_report_snapshot=report,
                startup_profile=profile,
                startup_readiness=readiness,
                startup_gtm=gtm,
                contradictions=contradictions,
                startup_market_research=market,
                calculations=calculations,
                improvement_version=improvement_version,
            )
        except (KeyError, ValueError):
            raise StartupGateConflict("advisor_improvements_not_ready") from None
        return case, report, proposals

    @staticmethod
    def _artifact_snapshot(
        runtime: dict[str, Any], key: str, model: type[BaseModel]
    ) -> Any | None:
        artifact = runtime.get(key)
        if not isinstance(artifact, dict):
            return None
        snapshot = artifact.get("snapshot")
        if not isinstance(snapshot, dict):
            raise StartupGateConflict("advisor_improvements_not_ready")
        try:
            return model.model_validate(snapshot)
        except ValueError:
            raise StartupGateConflict("advisor_improvements_not_ready") from None

    @staticmethod
    def _lineage_is_current(runtime: dict[str, Any], base: dict[str, Any]) -> bool:
        if base.get("source") == "advisor_draft":
            return (
                runtime.get("canonical_report_snapshot_id") is None
                and runtime.get("data_revision") == base.get("case_revision")
                and isinstance(base.get("report_id"), str)
                and isinstance(base.get("report_hash"), str)
            )
        return (
            runtime.get("canonical_report_snapshot_id") == base.get("report_id")
            and runtime.get("canonical_report_snapshot_hash") == base.get("report_hash")
            and runtime.get("canonical_report_snapshot_revision")
            == base.get("case_revision")
        )

    @staticmethod
    def _advisor_draft_report_snapshot(
        *,
        case: Any,
        runtime: dict[str, Any],
        answers: list[dict[str, Any]],
    ) -> ReportSnapshot:
        preimage = "|".join(
            (
                "startup-advisor-draft-report",
                str(case.case_id),
                str(case.data_revision),
                str(len(answers)),
                str(runtime.get("active_analysis_thread_id", "")),
            )
        )
        digest = sha256(preimage.encode("utf-8")).hexdigest()
        report_id = uuid5(NAMESPACE_URL, f"startup-advisor-draft-report:{case.case_id}:{digest}")
        manifest = ReproducibilityManifest(
            code_commit="local",
            build_id="advisor-draft",
            dependency_lock_hash="sha256:" + "0" * 64,
            python_version="offline",
            package_versions={},
            provider_model_id="offline",
            model_alias_snapshot="offline",
            reasoning_parameters={"network": "disabled"},
            adapter_versions={},
            parser_versions={"advisor": _ADVISOR_DRAFT_REPORT_VERSION},
            embedding_model_version="offline",
            index_version="none",
            redaction_policy_version=case.privacy_policy,
            locale="ru-RU",
            timezone="UTC",
            fx_source=case.base_currency,
            deterministic_seeds={"advisor_draft": 1},
            configuration_hash=f"sha256:{digest}",
        )
        return ReportSnapshot(
            id=report_id,
            case_id=case.case_id,
            report_hash=f"sha256:{digest}",
            case_snapshot_hash=f"sha256:{sha256(case.model_dump_json().encode('utf-8')).hexdigest()}",
            source_hashes={"advisor-draft": f"sha256:{digest}"},
            as_of=case.as_of,
            graph_version=case.workflow_version,
            prompt_versions={"report": _ADVISOR_DRAFT_REPORT_VERSION},
            formula_versions={"advisor": _ADVISOR_DRAFT_REPORT_VERSION},
            model_versions={"analysis": "offline"},
            trace_ids=(),
            sections={},
            data_revision=case.data_revision,
            json_artifact_ref=f"sha256:{digest}",
            html_artifact_ref=None,
            pdf_artifact_ref=None,
            content_hashes={"json": f"sha256:{digest}"},
            reproducibility=manifest,
            sensitivity=SensitivityClass.CONFIDENTIAL,
            created_at=case.as_of,
            version=1,
        )

    @staticmethod
    def _proposal_dto(
        proposal: StartupImprovementProposal,
    ) -> StartupImprovementProposalDto:
        return StartupImprovementProposalDto(
            proposal_id=proposal.proposal_id,
            target_area=proposal.target_area.value,
            recommendation_ru=proposal.recommendation_ru,
            rationale_ru=proposal.rationale_ru,
            expected_effect_ru=proposal.expected_effect_ru,
            evidence_kinds=tuple(sorted({item.kind.value for item in proposal.evidence_refs})),
            confidence=proposal.confidence,
        )

    def _save_state(self, case_id: str, state: dict[str, Any]) -> None:
        self._workflow_store.update(case_id, lambda _current: {_STATE_KEY: state})

    def _record_research_status(
        self,
        *,
        case_id: str,
        state: dict[str, Any],
        question: AdvisorQuestion,
        delta: AdvisorResearchDelta,
    ) -> None:
        raw = state.get("research_statuses")
        statuses = dict(raw) if isinstance(raw, dict) else {}
        statuses[question.question_id] = {
            "field_key": question.field_key,
            "status": delta.status,
            "source_ids": [str(item) for item in delta.source_ids],
            "fallback_used": delta.fallback_used,
        }
        state["research_statuses"] = statuses
        self._save_state(case_id, state)

    def _index_proposals(
        self, case_id: str, proposals: tuple[StartupImprovementProposal, ...]
    ) -> None:
        def update(current: dict[str, Any]) -> dict[str, Any]:
            owners = current.get("owners")
            index = dict(owners) if isinstance(owners, dict) else {}
            index.update({str(item.proposal_id): case_id for item in proposals})
            return {"owners": index}

        self._workflow_store.update(_PROPOSAL_INDEX_RECORD, update)

    def _proposal_owner(self, proposal_id: str) -> str | None:
        index = self._workflow_store.load(_PROPOSAL_INDEX_RECORD).get("owners")
        if not isinstance(index, dict):
            return None
        owner = index.get(proposal_id)
        return owner if isinstance(owner, str) else None

    @staticmethod
    def _profile_field_statuses(
        context: StartupAdvisorApiContext,
        case_id: UUID,
    ) -> dict[str, str]:
        try:
            profile = context.profile_repository.get_current(case_id)
        except (KeyError, ValueError):
            return {}
        statuses: dict[str, str] = {}
        for advisor_field, profile_field in _ADVISOR_PROFILE_FIELD_KEYS.items():
            field = profile.fields.get(profile_field)
            if field is None:
                continue
            statuses[advisor_field] = str(field.status)
        return statuses

    @staticmethod
    def _evidence_fact_ids(
        context: StartupAdvisorApiContext,
        case_id: UUID,
    ) -> frozenset[UUID]:
        if context.evidence_repository is None:
            return frozenset()
        try:
            facts = context.evidence_repository.list_for_case(case_id)
        except (KeyError, ValueError):
            return frozenset()
        return frozenset(fact.id for fact in facts)

    @staticmethod
    def _profile_source_snapshot(
        context: StartupAdvisorApiContext,
        case_id: UUID,
    ) -> dict[str, tuple[str, ...]]:
        try:
            profile = context.profile_repository.get_current(case_id)
        except (KeyError, ValueError):
            return {}
        snapshot: dict[str, tuple[str, ...]] = {}
        for field_name, field in profile.fields.items():
            if str(getattr(field, "status", "")).casefold() != "source_fact":
                continue
            values = getattr(field, "values", ())
            snapshot[str(field_name)] = tuple(str(value) for value in values)
        return snapshot

    @staticmethod
    def _open_contradiction_ids(
        context: StartupAdvisorApiContext,
        case_id: UUID,
    ) -> frozenset[UUID]:
        try:
            contradictions = tuple(context.contradiction_repository.list_for_case(case_id))
        except (KeyError, ValueError):
            return frozenset()
        return frozenset(
            contradiction.id
            for contradiction in contradictions
            if str(getattr(contradiction, "status", "")).casefold()
            in _OPEN_CONTRADICTION_STATUSES
        )

    @staticmethod
    def _calculation_snapshot(
        context: StartupAdvisorApiContext,
        case_id: UUID,
    ) -> dict[str, tuple[tuple[str, ...], ...]]:
        try:
            calculations = tuple(context.calculation_repository.list_for_case(case_id))
        except (KeyError, ValueError):
            return {}
        snapshot: dict[str, list[tuple[str, ...]]] = {}
        for calculation in calculations:
            metric_name = StartupAdvisorApiService._safe_metric_name(
                str(getattr(calculation, "metric_name", ""))
            )
            if metric_name is None:
                continue
            signature = (
                str(getattr(calculation, "formula_version", "")),
                str(getattr(calculation, "value", "")),
                str(getattr(calculation, "unit", "")),
                str(getattr(calculation, "period", "")),
                str(getattr(calculation, "version", "")),
            )
            snapshot.setdefault(metric_name, []).append(signature)
        return {
            metric_name: tuple(sorted(signatures))
            for metric_name, signatures in snapshot.items()
        }

    @staticmethod
    def _safe_metric_name(value: str) -> str | None:
        stripped = value.strip()
        if not stripped or _PRIVATE_METRIC_NAME_RE.search(stripped):
            return None
        normalized = stripped.casefold().replace("-", "_")
        if _SAFE_METRIC_NAME_RE.fullmatch(normalized) is None:
            return None
        return normalized

    @staticmethod
    def _contradiction_contexts(
        context: StartupAdvisorApiContext,
        case_id: UUID,
    ) -> tuple[dict[str, object], ...]:
        try:
            contradictions = tuple(context.contradiction_repository.list_for_case(case_id))
        except (KeyError, ValueError):
            return ()
        contexts: list[dict[str, object]] = []
        for contradiction in contradictions:
            status = str(getattr(contradiction, "status", ""))
            conflict_type = str(getattr(contradiction, "conflict_type", ""))
            explanation = str(getattr(contradiction, "explanation", ""))
            field_key = advisor_field_key_for_contradiction(
                conflict_type=conflict_type,
                explanation=explanation,
            )
            contexts.append(
                safe_context := safe_contradiction_context(
                    field_key=field_key,
                    conflict_type=conflict_type,
                    explanation=explanation,
                    status=status,
                )
            )
            safe_context["contradiction_id"] = contradiction.id
        return tuple(contexts)


def _clarification_metric_names(conflict_type: str, explanation: str) -> frozenset[str]:
    normalized = _normalized_fact_name(f"{conflict_type} {explanation}")
    if "mrr" in normalized or "monthly_recurring_revenue" in normalized:
        return frozenset({"mrr", "monthly_recurring_revenue"})
    if "arr" in normalized or "annual_recurring_revenue" in normalized:
        return frozenset({"arr", "annual_recurring_revenue"})
    if "gross_margin" in normalized:
        return frozenset({"gross_margin", "gross_margin_ratio"})
    if "cac_payback" in normalized:
        return frozenset({"cac_payback", "cac_payback_months"})
    if "customer_count" in normalized:
        return frozenset({"customer_count", "customers"})
    return frozenset()


def _normalized_fact_name(value: str) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "_", value.strip().casefold()).strip("_")


def _same_fact_identity(
    source_fact: EvidenceFact,
    candidate: EvidenceFact | None,
    *,
    accepted_names: frozenset[str],
) -> bool:
    if candidate is None:
        return False
    if {
        _normalized_fact_name(source_fact.name),
        _normalized_fact_name(candidate.name),
    }.difference(accepted_names):
        return False
    return (
        (source_fact.unit or "").strip().casefold()
        == (candidate.unit or "").strip().casefold()
        and (source_fact.period or "").strip().casefold()
        == (candidate.period or "").strip().casefold()
    )


def _accepted_founder_fact(
    *,
    case_id: UUID,
    question: AdvisorQuestion,
    source_fact: EvidenceFact,
) -> EvidenceFact:
    accepted_id = uuid5(
        NAMESPACE_URL,
        (
            f"founder-clarification:{case_id}:{question.question_id}:"
            f"{source_fact.id}:{source_fact.value}"
        ),
    )
    return source_fact.model_copy(
        update={
            "id": accepted_id,
            "confidence": max(source_fact.confidence, Decimal("0.95")),
            "source_priority": int(SourcePriority.MANAGEMENT_NARRATIVE),
            "extraction_method": "founder_clarification",
            "metadata": {
                **source_fact.metadata,
                "founder_clarification": "accepted_source",
            },
        }
    )
